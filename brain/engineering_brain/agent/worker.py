"""Base worker agent with registry.

Workers are domain-specific agents that receive a sub-question + brain
knowledge and produce structured WorkerResult via a single LLM call.
"""

from __future__ import annotations

import logging
from abc import ABC
from typing import Any

from engineering_brain.agent.brain_access import BrainAccess
from engineering_brain.agent.config import AgentConfig
from engineering_brain.agent.llm_client import LLMClient
from engineering_brain.agent.parsing import parse_claims
from engineering_brain.agent.runtime_cards import RuntimeCard, load_card
from engineering_brain.agent.types import WorkerResult

logger = logging.getLogger(__name__)


class WorkerAgent(ABC):
    """Abstract base class for domain worker agents."""

    # Subclasses set this
    domain: str = "general"
    card_id: str = "general_worker"

    def __init__(
        self,
        brain_access: BrainAccess,
        llm_client: LLMClient,
        config: AgentConfig,
    ) -> None:
        self._brain = brain_access
        self._llm = llm_client
        self._config = config
        self._card: RuntimeCard | None = None

    def get_card(self) -> RuntimeCard:
        """Load this worker's runtime card (cached)."""
        if self._card is None:
            self._card = load_card(self.card_id, cards_dir=self._config.cards_dir)
        return self._card

    def execute(self, question: str, technologies: list[str] | None = None) -> WorkerResult:
        """Execute the worker: retrieve brain knowledge, call LLM, parse result.

        Steps:
        1. brain_access.format_context(sub_question)
        2. Build prompt from card + knowledge context
        3. llm_client.call_json() -> parse into WorkerResult
        """
        card = self.get_card()
        domains = self._get_domains()

        # Step 1: Retrieve knowledge
        context = self._brain.format_context(
            question,
            technologies=technologies,
            domains=domains,
        )

        # Step 2: Build prompt
        system_prompt = card.build_system_prompt()
        user_message = self._build_user_message(question, context)

        # Step 3: LLM call
        try:
            result = self._llm.call_json(
                system_prompt=system_prompt,
                user_message=user_message,
                model=self._config.model,
            )
            data = result["data"]
            tokens = result["input_tokens"] + result["output_tokens"]
        except Exception as exc:
            logger.error("Worker %s LLM call failed: %s", self.card_id, exc)
            return WorkerResult(
                worker_id=self.card_id,
                domain=self.domain,
                gaps=[f"LLM call failed: {type(exc).__name__}"],
            )

        # Step 4: Parse into WorkerResult
        return self._parse_result(data, tokens)

    def _get_domains(self) -> list[str]:
        """Return domain list for brain queries."""
        return [self.domain] if self.domain != "general" else []

    def _build_user_message(self, question: str, context: str) -> str:
        """Build the user message with question + knowledge context."""
        parts = [
            f"## Question\n{question}",
        ]
        if context:
            parts.append(f"\n## Knowledge from Engineering Brain\n{context}")
        else:
            parts.append(
                "\n## Knowledge from Engineering Brain\n"
                "No relevant knowledge found in the brain for this query."
            )
        parts.append(
            "\nRespond with a JSON object containing 'claims', 'gaps', "
            "and 'contradictions_found' arrays."
        )
        return "\n".join(parts)

    def _parse_result(self, data: dict[str, Any], tokens: int) -> WorkerResult:
        """Parse LLM JSON response into a WorkerResult."""
        # Guard against non-dict LLM response (e.g., JSON array)
        if not isinstance(data, dict):
            logger.warning("Worker %s LLM returned non-dict: %s", self.card_id, type(data))
            return WorkerResult(
                worker_id=self.card_id,
                domain=self.domain,
                gaps=["LLM returned non-object JSON"],
                tokens_used=tokens,
            )

        claims = parse_claims(data.get("claims", []))
        nodes_consulted = sum(len(c.evidence) for c in claims)

        return WorkerResult(
            worker_id=self.card_id,
            domain=self.domain,
            claims=claims,
            gaps=[str(g) for g in data.get("gaps", [])],
            contradictions_found=[str(c) for c in data.get("contradictions_found", [])],
            nodes_consulted=nodes_consulted,
            tokens_used=tokens,
        )
