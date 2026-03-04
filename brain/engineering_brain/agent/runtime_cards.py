"""Runtime card loader for agent YAML definitions.

Same pattern as the brains pipeline runtime_card_loader.py:
YAML safe_load, cache, sanitize (prompt injection detection).
3-tier fallback: card -> default template -> error.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Suspicious patterns that might indicate prompt injection in card YAML
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(?:a\s+)?(?:new|different)", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),
    re.compile(r"<\|(?:im_start|system|endoftext)\|>", re.IGNORECASE),
]

# Built-in cards directory (relative to this file)
_BUILTIN_CARDS_DIR = Path(__file__).parent.parent / "configs" / "agent_cards"


@dataclass(frozen=True)
class RuntimeCard:
    """An agent's runtime configuration loaded from YAML."""

    agent_id: str
    version: str = "1.0.0"
    level: int = 1  # 0=orchestrator, 1=worker
    reports_to: str = "orchestrator"
    role: str = ""
    goal: str = ""
    backstory: str = ""
    key_skills: list[str] = field(default_factory=list)
    key_constraints: list[str] = field(default_factory=list)
    decompose_instructions: str = ""  # orchestrator only
    synthesize_instructions: str = ""  # orchestrator only
    worker_instructions: str = ""  # worker only

    def build_system_prompt(self) -> str:
        """Build the system prompt for this agent from its card fields."""
        parts = [f"# Role: {self.role}"]
        if self.goal:
            parts.append(f"\n## Goal\n{self.goal}")
        if self.backstory:
            parts.append(f"\n## Backstory\n{self.backstory}")
        if self.key_skills:
            parts.append("\n## Key Skills")
            for skill in self.key_skills:
                parts.append(f"- {skill}")
        if self.key_constraints:
            parts.append("\n## Constraints")
            for constraint in self.key_constraints:
                parts.append(f"- {constraint}")
        if self.worker_instructions:
            parts.append(f"\n## Instructions\n{self.worker_instructions}")
        return "\n".join(parts)

    def build_decompose_prompt(self) -> str:
        """Build decomposition prompt (orchestrator only)."""
        parts = [f"# Role: {self.role}"]
        if self.goal:
            parts.append(f"\n## Goal\n{self.goal}")
        if self.decompose_instructions:
            parts.append(f"\n## Decomposition Instructions\n{self.decompose_instructions}")
        if self.key_constraints:
            parts.append("\n## Constraints")
            for constraint in self.key_constraints:
                parts.append(f"- {constraint}")
        return "\n".join(parts)

    def build_synthesize_prompt(self) -> str:
        """Build synthesis prompt (orchestrator only)."""
        parts = [f"# Role: {self.role}"]
        if self.goal:
            parts.append(f"\n## Goal\n{self.goal}")
        if self.synthesize_instructions:
            parts.append(f"\n## Synthesis Instructions\n{self.synthesize_instructions}")
        if self.key_constraints:
            parts.append("\n## Constraints")
            for constraint in self.key_constraints:
                parts.append(f"- {constraint}")
        return "\n".join(parts)


def _validate_card(data: dict[str, Any]) -> None:
    """Validate card data for prompt injection patterns. Raises ValueError."""
    text_fields = [
        "role",
        "goal",
        "backstory",
        "decompose_instructions",
        "synthesize_instructions",
        "worker_instructions",
    ]
    for field_name in text_fields:
        value = data.get(field_name, "")
        if not isinstance(value, str):
            continue
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(value):
                raise ValueError(
                    f"Suspicious content in card field '{field_name}': "
                    f"matched pattern {pattern.pattern!r}"
                )
    # Also check list fields
    for field_name in ("key_skills", "key_constraints"):
        items = data.get(field_name, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, str):
                continue
            for pattern in _INJECTION_PATTERNS:
                if pattern.search(item):
                    raise ValueError(
                        f"Suspicious content in card list '{field_name}': "
                        f"matched pattern {pattern.pattern!r}"
                    )


def _ensure_string_list(value: Any, field_name: str = "") -> list[str]:
    """Coerce a YAML value to a list of strings, raising on wrong types."""
    if not isinstance(value, list):
        label = f" for '{field_name}'" if field_name else ""
        raise ValueError(f"Expected a list{label}, got {type(value).__name__}")
    return [str(item) for item in value]


def _parse_card(data: dict[str, Any]) -> RuntimeCard:
    """Parse validated dict into a RuntimeCard."""
    agent_id = data.get("agent_id", "")
    if not agent_id:
        raise ValueError("Card missing required 'agent_id' field")
    return RuntimeCard(
        agent_id=agent_id,
        version=str(data.get("version", "1.0.0")),
        level=int(data.get("level", 1)),
        reports_to=str(data.get("reports_to", "orchestrator")),
        role=str(data.get("role", "")),
        goal=str(data.get("goal", "")),
        backstory=str(data.get("backstory", "")),
        key_skills=_ensure_string_list(data.get("key_skills", []), "key_skills"),
        key_constraints=_ensure_string_list(data.get("key_constraints", []), "key_constraints"),
        decompose_instructions=str(data.get("decompose_instructions", "")),
        synthesize_instructions=str(data.get("synthesize_instructions", "")),
        worker_instructions=str(data.get("worker_instructions", "")),
    )


# Module-level card cache
_card_cache: dict[str, RuntimeCard] = {}


def load_card(agent_id: str, cards_dir: str = "") -> RuntimeCard:
    """Load a runtime card by agent_id.

    3-tier fallback:
    1. Custom cards_dir (if provided)
    2. Built-in cards from configs/agent_cards/
    3. Raise FileNotFoundError

    Cards are cached by (agent_id, cards_dir) after first load.
    """
    # Validate agent_id to prevent path traversal
    if not re.match(r"^[a-z][a-z0-9_]*$", agent_id):
        raise ValueError(
            f"Invalid agent_id {agent_id!r}: must be lowercase alphanumeric + underscores"
        )

    cache_key = f"{agent_id}:{cards_dir}"
    if cache_key in _card_cache:
        return _card_cache[cache_key]

    card_filename = f"{agent_id}.yml"

    # Tier 1: custom directory
    if cards_dir:
        custom_path = Path(cards_dir) / card_filename
        if custom_path.is_file():
            card = _load_from_file(custom_path)
            _card_cache[cache_key] = card
            return card

    # Tier 2: built-in cards
    builtin_path = _BUILTIN_CARDS_DIR / card_filename
    if builtin_path.is_file():
        card = _load_from_file(builtin_path)
        _card_cache[cache_key] = card
        return card

    raise FileNotFoundError(
        f"Agent card '{agent_id}' not found in {cards_dir or 'default'} or built-in cards"
    )


def _load_from_file(path: Path) -> RuntimeCard:
    """Load and parse a single YAML card file."""
    with open(path) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Card file {path} must be a YAML mapping")
    _validate_card(data)
    return _parse_card(data)


def clear_card_cache() -> None:
    """Clear the card cache (for testing)."""
    _card_cache.clear()
