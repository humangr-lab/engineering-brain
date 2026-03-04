"""Raw LLM baseline — direct query to Claude without knowledge graph.

Asks the LLM to generate engineering rules/patterns for a given task,
then matches the response against Brain node IDs by text similarity.

Optional: requires BRAIN_AGENT_API_KEY environment variable.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from .base import BaselineSystem, SystemResult

logger = logging.getLogger(__name__)

_PROMPT_TEMPLATE = """\
You are a senior software engineer. Given the following task, list the most important \
engineering rules, patterns, and best practices that apply.

Task: {task}
Technologies: {technologies}
Domains: {domains}

Return a JSON array of objects, each with:
- "text": the rule or pattern (one sentence)
- "technologies": list of relevant technologies
- "domains": list of relevant domains
- "severity": "critical", "high", "medium", or "low"

Return ONLY the JSON array, no other text."""


class RawLLMSystem(BaselineSystem):
    """Direct LLM query — no knowledge graph, no retrieval."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self._model = model
        self._client: Any = None
        self._brain: Any = None

    @property
    def name(self) -> str:
        return f"Raw LLM ({self._model.split('-')[1]})"

    @property
    def description(self) -> str:
        return (
            f"Direct query to {self._model} without any knowledge graph or retrieval. "
            "The LLM generates engineering rules from its training data. "
            "Results are matched to Brain nodes by text overlap for metric comparison."
        )

    def setup(self) -> None:
        api_key = os.environ.get("BRAIN_AGENT_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "Raw LLM baseline requires BRAIN_AGENT_API_KEY. "
                "Set it or use --systems brain,naive_rag,graph_rag to skip."
            )

        try:
            import anthropic

            self._client = anthropic.Anthropic(api_key=api_key)
        except ImportError:
            raise RuntimeError("Raw LLM baseline requires 'anthropic' package: pip install anthropic")

        # Also seed a Brain instance for node matching
        from engineering_brain.core.brain import Brain

        self._brain = Brain()
        self._brain.seed()

    def query(
        self,
        task_description: str,
        technologies: list[str],
        domains: list[str],
    ) -> SystemResult:
        prompt = _PROMPT_TEMPLATE.format(
            task=task_description,
            technologies=", ".join(technologies) if technologies else "general",
            domains=", ".join(domains) if domains else "general",
        )

        start = time.monotonic()
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        elapsed = (time.monotonic() - start) * 1000

        # Parse LLM response
        text = response.content[0].text.strip()
        token_count = response.usage.input_tokens + response.usage.output_tokens

        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code blocks
            if "```" in text:
                json_str = text.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
                items = json.loads(json_str.strip())
            else:
                items = []

        # Match LLM-generated items to Brain node IDs
        ranked_ids, raw_results = self._match_to_brain_nodes(items, technologies, domains)

        return SystemResult(
            ranked_ids=ranked_ids,
            raw_results=raw_results,
            latency_ms=elapsed,
            token_count=token_count,
            metadata={"model": self._model, "raw_items": len(items)},
        )

    def _match_to_brain_nodes(
        self,
        items: list[dict],
        technologies: list[str],
        domains: list[str],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Match LLM-generated items to Brain nodes by querying for each item."""
        seen_ids: set[str] = set()
        ranked_ids: list[str] = []
        raw_results: list[dict[str, Any]] = []

        for item in items[:20]:  # Cap at 20 items
            item_text = item.get("text", "")
            if not item_text:
                continue
            # Use the Brain to find matching nodes
            result = self._brain.query(
                task_description=item_text,
                technologies=technologies or None,
                domains=domains or None,
                phase="exec",
            )
            for layer_key in ("rules", "patterns", "principles", "evidence"):
                for node in getattr(result, layer_key, []):
                    nid = node.get("id", "")
                    if nid and nid not in seen_ids:
                        seen_ids.add(nid)
                        ranked_ids.append(nid)
                        raw_results.append(node)

        return ranked_ids, raw_results

    def teardown(self) -> None:
        self._client = None
        self._brain = None
