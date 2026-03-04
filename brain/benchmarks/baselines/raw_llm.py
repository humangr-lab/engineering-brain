"""Raw LLM baseline — direct query to Claude without knowledge graph.

Asks the LLM to generate engineering rules/patterns for a given task,
then matches the response against Brain node IDs by embedding cosine
similarity ONLY (no graph expansion, no scoring signals).

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
    """Direct LLM query — no knowledge graph, no retrieval.

    Node matching uses embedding cosine similarity only, ensuring the
    LLM baseline is fully independent from the Brain's scoring pipeline.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self._model = model
        self._client: Any = None
        self._embedder: Any = None
        self._node_index: list[tuple[str, list[float], dict]] = []  # (id, vector, metadata)

    @property
    def name(self) -> str:
        return f"Raw LLM ({self._model.split('-')[1]})"

    @property
    def description(self) -> str:
        return (
            f"Direct query to {self._model} without any knowledge graph or retrieval. "
            "The LLM generates engineering rules from its training data. "
            "Results are matched to Brain nodes by embedding cosine similarity only "
            "(no graph expansion, no scoring signals)."
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
        except ImportError as exc:
            raise RuntimeError(
                "Raw LLM baseline requires 'anthropic' package: pip install anthropic"
            ) from exc

        # Build embedding index from seed data (independent of Brain scoring)
        self._build_node_index()

    def _build_node_index(self) -> None:
        """Build an embedding index of all seed nodes for cosine matching.

        Uses the same fastembed model as the Brain but only for embedding —
        no graph traversal, no scoring signals, no query expansion.
        """
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise RuntimeError(
                "Raw LLM node matching requires fastembed: pip install fastembed"
            ) from exc

        from engineering_brain.retrieval.embedder import cosine_similarity

        self._cosine = cosine_similarity
        self._embed_model = TextEmbedding()

        # Load all seed nodes directly (bypass Brain query pipeline entirely)
        from engineering_brain.core.brain import Brain

        brain = Brain()
        brain.seed()

        # Extract all nodes from the graph
        all_nodes = brain._graph.get_all_nodes()
        logger.info("Raw LLM: indexing %d nodes for embedding matching", len(all_nodes))

        texts_to_embed = []
        node_data = []
        for node in all_nodes:
            nid = node.get("id", "")
            text = node.get("text", "")
            if not nid or not text:
                continue
            texts_to_embed.append(text[:512])  # Cap text length for embedding
            node_data.append((nid, node))

        # Batch embed all node texts
        embeddings = list(self._embed_model.embed(texts_to_embed))

        self._node_index = []
        for i, (nid, node) in enumerate(node_data):
            vec = [float(x) for x in embeddings[i]]
            self._node_index.append((nid, vec, node))

        logger.info("Raw LLM: indexed %d node embeddings", len(self._node_index))

        # Clean up the Brain — we only needed it for node data
        del brain

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

        # Match LLM items to nodes by embedding cosine similarity only
        ranked_ids, raw_results = self._match_by_embedding(items)

        return SystemResult(
            ranked_ids=ranked_ids,
            raw_results=raw_results,
            latency_ms=elapsed,
            token_count=token_count,
            metadata={"model": self._model, "raw_items": len(items)},
        )

    def _match_by_embedding(
        self,
        items: list[dict],
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """Match LLM-generated items to Brain nodes by cosine similarity only.

        For each LLM item, embed its text and find the closest node in the
        pre-computed embedding index. No graph traversal, no scoring.
        """
        seen_ids: set[str] = set()
        ranked_ids: list[str] = []
        raw_results: list[dict[str, Any]] = []

        for item in items[:20]:  # Cap at 20 items
            item_text = item.get("text", "")
            if not item_text:
                continue

            # Embed the LLM-generated text
            item_vec = list(self._embed_model.embed([item_text]))[0]
            item_vec = [float(x) for x in item_vec]

            # Find top-3 nearest nodes by cosine similarity
            scored = []
            for nid, node_vec, node in self._node_index:
                if nid in seen_ids:
                    continue
                sim = self._cosine(item_vec, node_vec)
                scored.append((sim, nid, node))

            scored.sort(key=lambda x: x[0], reverse=True)

            for sim, nid, node in scored[:3]:
                if nid not in seen_ids and sim > 0.3:  # Minimum similarity threshold
                    seen_ids.add(nid)
                    ranked_ids.append(nid)
                    raw_results.append(node)

        return ranked_ids, raw_results

    def teardown(self) -> None:
        self._client = None
        self._node_index = []
        self._embedder = None
