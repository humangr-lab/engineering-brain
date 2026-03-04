"""Task-driven knowledge retrieval for the Engineering Knowledge Brain.

Instead of auto-detecting everything from free-text task descriptions,
tasks explicitly declare what knowledge they need. This module reads
those declarations and fetches the right knowledge from the brain.

DESIGN: Tasks carry `knowledge_tags` (technologies), `knowledge_domains`,
and `knowledge_file_type`. The spec phase auto-populates these from the
task description. The exec phase reads them and injects precise knowledge.

Usage by pipeline agents:
    from engineering_brain.retrieval.task_knowledge import (
        get_knowledge_for_task,
        enrich_task_with_knowledge,
        auto_tag_task,
    )

    # At spec phase — auto-detect and store tags on each task
    task = auto_tag_task(task)
    # task now has: knowledge_tags=["Flask","CORS"], knowledge_domains=["security","api"]

    # At exec phase — fetch knowledge using stored tags
    knowledge_text = get_knowledge_for_task(task)
    # inject knowledge_text into the agent's prompt

    # Or in one shot — enrich the task dict with a knowledge_text field
    task = enrich_task_with_knowledge(task)
    # task["knowledge_text"] = "## Engineering Knowledge\n..."
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Singleton brain reference (set by init_task_knowledge or lazily created)
_brain_instance = None


def init_task_knowledge(brain: Any) -> None:
    """Initialize the module with an existing Brain instance.

    Call this once at startup (e.g., from StackDataBridge) to avoid
    re-seeding the brain on every call.
    """
    global _brain_instance
    _brain_instance = brain


def _get_brain() -> Any:
    """Get the Brain singleton via centralized factory."""
    global _brain_instance
    if _brain_instance is not None:
        return _brain_instance
    try:
        from engineering_brain.core.brain_factory import get_brain

        _brain_instance = get_brain()
    except Exception as e:
        logger.warning("task_knowledge: Brain not available: %s", e)
        return None
    return _brain_instance


def _llm_extract_tags(task_description: str) -> dict | None:
    """LLM-enhanced tag extraction. Returns None on failure."""
    from engineering_brain.llm_helpers import brain_llm_call_json, is_llm_enabled

    if not is_llm_enabled("BRAIN_LLM_TASK_TAGGING"):
        return None
    system = (
        "Extract engineering tags from a task description. "
        'Return ONLY JSON: {"technologies": ["Flask"], "domains": ["security"]}. '
        "domains from: security, api, database, testing, performance, architecture, "
        "devops, ui, general. Return empty lists if nothing clearly applies."
    )
    return brain_llm_call_json(system, f"Task: {task_description[:1200]}", max_tokens=150)


def auto_tag_task(task: dict[str, Any]) -> dict[str, Any]:
    """3-layer auto-detection of knowledge requirements (KTP).

    Layer 1 (EXPLICIT): Keyword detection from task description
    Layer 2 (IMPLIED): Technology Implication Graph (TIG) lookup
    Layer 3 (CONTEXTUAL): AST analysis of existing code files

    Populates:
    - knowledge_tags: list of technology names (e.g. ["Flask", "CORS"])
    - knowledge_domains: list of domain names (e.g. ["security", "api", "cors"])
    - knowledge_file_type: file extension (e.g. ".py")
    - knowledge_phase: pipeline phase (e.g. "exec")
    - knowledge_provenance: dict mapping each tag to its detection source

    Already-present tags are preserved (explicit > auto-detected).
    """
    from engineering_brain.retrieval.context_extractor import (
        apply_technology_implications,
        extract_ast_context,
        extract_context,
    )

    # Build description from available task fields
    desc = _extract_task_description(task)
    if not desc:
        return task

    # Already-present tags are explicit (highest priority) — skip re-detection
    if "knowledge_tags" in task and "knowledge_domains" in task:
        return task

    # Layer 1: EXPLICIT — keyword detection from description (existing logic)
    ctx = extract_context(
        desc,
        technologies=task.get("knowledge_tags"),
        file_type=task.get("knowledge_file_type", ""),
        phase=task.get("knowledge_phase", ""),
        domains=task.get("knowledge_domains"),
    )

    # LLM tag augmentation (before TIG and AST layers)
    llm_tags = _llm_extract_tags(desc)
    if llm_tags:
        for t in llm_tags.get("technologies") or []:
            if isinstance(t, str) and t and t not in ctx.technologies:
                ctx.technologies.append(t)
        for d in llm_tags.get("domains") or []:
            d_lower = d.lower() if isinstance(d, str) else ""
            if d_lower and d_lower not in ctx.domains:
                ctx.domains.append(d_lower)

    provenance: dict[str, str] = {}
    for t in ctx.technologies:
        provenance[t] = "explicit"
    for d in ctx.domains:
        provenance[d] = "explicit"

    # Layer 2: IMPLIED — Technology Implication Graph
    text_lower = desc.lower()
    try:
        tig_domains = apply_technology_implications(ctx.technologies, text_lower)
        for d in tig_domains:
            if d not in ctx.domains:
                ctx.domains.append(d)
            if d not in provenance:
                provenance[d] = "tig"
    except Exception as exc:
        logger.debug("Technology implications (TIG) failed: %s", exc)

    # Layer 3: CONTEXTUAL — AST analysis (if file paths available)
    file_paths = _extract_file_paths(task)
    if file_paths:
        try:
            ast_techs, ast_domains = extract_ast_context(file_paths)
            for t in ast_techs:
                if t not in ctx.technologies:
                    ctx.technologies.append(t)
                if t not in provenance:
                    provenance[t] = "ast"
            for d in ast_domains:
                if d not in ctx.domains:
                    ctx.domains.append(d)
                if d not in provenance:
                    provenance[d] = "ast"
        except Exception as exc:
            logger.debug("AST context extraction failed: %s", exc)

    # Store tags — don't overwrite explicit values
    if "knowledge_tags" not in task:
        task["knowledge_tags"] = ctx.technologies
    if "knowledge_domains" not in task:
        task["knowledge_domains"] = ctx.domains
    if "knowledge_file_type" not in task:
        task["knowledge_file_type"] = ctx.file_types[0] if ctx.file_types else ""
    if "knowledge_phase" not in task:
        task["knowledge_phase"] = ctx.phase
    task["knowledge_provenance"] = provenance

    return task


def get_knowledge_for_task(task: dict[str, Any], budget_chars: int | None = None) -> str:
    """Fetch relevant engineering knowledge for a task.

    Reads the task's knowledge_tags/knowledge_domains (populated by auto_tag_task
    or explicitly set by spec phase) and queries the brain.

    Args:
        task: Task dict with knowledge_tags, knowledge_domains, etc.
        budget_chars: Override the default context budget.

    Returns:
        Formatted knowledge text ready for prompt injection.
        Empty string if brain is not available (graceful degradation).
    """
    brain = _get_brain()
    if brain is None:
        return ""

    # Read tags from task (or fall back to auto-detection from description)
    tags = task.get("knowledge_tags") or []
    domains = task.get("knowledge_domains") or []
    file_type = task.get("knowledge_file_type", "")
    phase = task.get("knowledge_phase", "exec")
    desc = _extract_task_description(task)

    # If no tags at all, auto-detect from description
    if not tags and not domains and desc:
        task = auto_tag_task(task)
        tags = task.get("knowledge_tags") or []
        domains = task.get("knowledge_domains") or []
        file_type = task.get("knowledge_file_type", "")
        phase = task.get("knowledge_phase", "exec")

    try:
        result = brain.query(
            task_description=desc,
            technologies=tags if tags else None,
            file_type=file_type,
            phase=phase,
            domains=domains if domains else None,
            budget_chars=budget_chars,
        )
        if result.formatted_text:
            # Collect served node IDs from all layers (principles, patterns, rules, evidence)
            served_ids: list[str] = []
            for layer in (result.principles, result.patterns, result.rules, result.evidence):
                for node in layer:
                    nid = node.get("id", "")
                    if nid:
                        served_ids.append(nid)

            if served_ids:
                try:
                    brain.observe_query(
                        rule_ids=served_ids,
                        query=desc,
                        technologies=tags or [],
                        file_type=file_type,
                    )
                except Exception as exc:
                    logger.debug("Failed to record brain query observation: %s", exc)
                # Store node IDs on task for later outcome feedback
                task["_brain_node_ids"] = served_ids

            logger.info(
                "task_knowledge: %d chars for task (tags=%s, domains=%s)",
                len(result.formatted_text),
                tags[:3],
                domains[:3],
            )
            return result.formatted_text
    except Exception as e:
        logger.debug("task_knowledge: query failed: %s", e)

    return ""


def enrich_task_with_knowledge(
    task: dict[str, Any],
    budget_chars: int | None = None,
) -> dict[str, Any]:
    """One-shot: auto-tag + fetch knowledge + store on task dict.

    After this call, task["knowledge_text"] contains the formatted knowledge
    ready for prompt injection. If the brain is not available, the field
    is set to empty string (graceful degradation).
    """
    task = auto_tag_task(task)
    task["knowledge_text"] = get_knowledge_for_task(task, budget_chars=budget_chars)
    return task


def enrich_tasks_batch(
    tasks: list[dict[str, Any]],
    budget_chars: int | None = None,
) -> list[dict[str, Any]]:
    """Batch enrich multiple tasks with knowledge.

    Useful for enriching all granular_tasks at once before exec phase.
    Uses deduplication: tasks with identical knowledge_tags get the same
    knowledge text (no redundant brain queries).
    """
    cache: dict[str, tuple[str, list[str]]] = {}  # (text, node_ids)
    enriched = []

    for task in tasks:
        task = auto_tag_task(task)
        # Cache key from tags + domains + file_type
        cache_key = _task_cache_key(task)

        if cache_key in cache:
            _cached_text, _cached_ids = cache[cache_key]
            task["knowledge_text"] = _cached_text
            if _cached_ids:
                task["_brain_node_ids"] = _cached_ids
        else:
            text = get_knowledge_for_task(task, budget_chars=budget_chars)
            node_ids = task.get("_brain_node_ids", [])
            cache[cache_key] = (text, node_ids)
            task["knowledge_text"] = text

        enriched.append(task)

    logger.info(
        "task_knowledge: enriched %d tasks (%d unique knowledge sets)",
        len(enriched),
        len(cache),
    )
    return enriched


def _extract_task_description(task: dict[str, Any]) -> str:
    """Extract the best description text from a task dict.

    Tasks can have different field names depending on pipeline context.
    """
    for field in (
        "description",
        "instruction",
        "task_description",
        "task_prompt",
        "prompt",
        "objective",
    ):
        val = task.get(field)
        if val and isinstance(val, str):
            return val
    # Fall back to deliverable + file name
    parts = []
    for field in ("deliverable", "file_path", "file_name", "target_file"):
        val = task.get(field)
        if val and isinstance(val, str):
            parts.append(val)
    return " ".join(parts)


def _extract_file_paths(task: dict[str, Any]) -> list[str]:
    """Extract file paths from task for AST analysis (Layer 3).

    Looks for Python file paths in standard task fields.
    Returns empty list if no paths found.
    """
    paths: list[str] = []
    for field in ("deliverable", "file_path", "file_name", "target_file"):
        val = task.get(field)
        if val and isinstance(val, str) and val.endswith(".py"):
            paths.append(val)
    return paths


def _task_cache_key(task: dict[str, Any]) -> str:
    """Create a cache key from task knowledge tags."""
    tags = tuple(sorted(task.get("knowledge_tags") or []))
    domains = tuple(sorted(task.get("knowledge_domains") or []))
    ft = task.get("knowledge_file_type", "")
    phase = task.get("knowledge_phase", "exec")
    return f"{tags}|{domains}|{ft}|{phase}"


# =========================================================================
# Epoch-Based Knowledge Versioning (Pull Model)
# =========================================================================


def get_brain_version() -> int:
    """Get current brain write counter (for epoch versioning).

    Pipeline calls this BEFORE a batch of concurrent agents start,
    and AFTER they complete, to detect if new knowledge was added
    during execution (e.g., by learn_from_finding).

    Returns:
        Monotonic integer. 0 if brain not available.
    """
    brain = _get_brain()
    if brain is None:
        return 0
    return brain.version


def check_knowledge_delta(pre_version: int) -> dict[str, Any]:
    """Compare current brain version against pre-batch snapshot.

    Used after a batch of concurrent agents completes to check
    if any agent added knowledge during execution.

    Args:
        pre_version: Version snapshot taken before batch started.

    Returns:
        {"changed": bool, "delta": int, "pre": int, "post": int}
    """
    post = get_brain_version()
    return {
        "changed": post > pre_version,
        "delta": post - pre_version,
        "pre": pre_version,
        "post": post,
    }
