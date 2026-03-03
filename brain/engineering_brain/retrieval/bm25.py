"""BM25 sparse retrieval index for the Engineering Knowledge Brain.

Okapi BM25 scoring provides lexical matching complementary to vector
similarity. Particularly strong for exact technology names, error codes,
and API identifiers that semantic embeddings may under-weight.

Reference: Robertson, S. & Zaragoza, H. (2009). The Probabilistic
           Relevance Framework: BM25 and Beyond.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + punctuation tokenizer, lowercased."""
    return re.findall(r"[a-z0-9_]+", text.lower())


class BM25Index:
    """In-memory BM25 index over knowledge node text fields."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._doc_freqs: dict[str, int] = {}      # term -> count of docs containing it
        self._doc_lens: dict[str, int] = {}        # node_id -> doc length
        self._doc_tfs: dict[str, Counter] = {}     # node_id -> term frequency counter
        self._avg_dl: float = 0.0
        self._n_docs: int = 0

    def index(self, nodes: list[dict[str, Any]]) -> None:
        """Build the inverted index from a list of knowledge nodes."""
        self._doc_freqs.clear()
        self._doc_lens.clear()
        self._doc_tfs.clear()

        for node in nodes:
            nid = node.get("id", "")
            if not nid:
                continue
            text = self._node_to_text(node)
            tokens = _tokenize(text)
            if not tokens:
                continue

            tf = Counter(tokens)
            self._doc_tfs[nid] = tf
            self._doc_lens[nid] = len(tokens)

            for term in tf:
                self._doc_freqs[term] = self._doc_freqs.get(term, 0) + 1

        self._n_docs = len(self._doc_tfs)
        total_len = sum(self._doc_lens.values())
        self._avg_dl = total_len / self._n_docs if self._n_docs > 0 else 1.0

    def score(self, query: str) -> dict[str, float]:
        """Score all indexed nodes against a query. Returns node_id -> BM25 score."""
        if self._n_docs == 0:
            return {}

        query_terms = _tokenize(query)
        if not query_terms:
            return {}

        scores: dict[str, float] = {}
        for nid, tf in self._doc_tfs.items():
            s = 0.0
            dl = self._doc_lens[nid]
            for term in query_terms:
                if term not in tf:
                    continue
                f = tf[term]
                df = self._doc_freqs.get(term, 0)
                # IDF: log((N - df + 0.5) / (df + 0.5) + 1)
                idf = math.log((self._n_docs - df + 0.5) / (df + 0.5) + 1.0)
                # TF normalization
                numerator = f * (self.k1 + 1)
                denominator = f + self.k1 * (1 - self.b + self.b * dl / self._avg_dl)
                s += idf * numerator / denominator
            if s > 0:
                scores[nid] = s

        return scores

    @property
    def size(self) -> int:
        """Number of indexed documents."""
        return self._n_docs

    @staticmethod
    def _node_to_text(node: dict[str, Any]) -> str:
        """Extract searchable text from a knowledge node."""
        parts: list[str] = []
        for field in ("text", "name", "statement", "intent", "why",
                       "how_to_do_right", "how_to_apply", "description",
                       "when_applies", "when_not_applies"):
            val = node.get(field, "")
            if val:
                parts.append(str(val))
        # Include technologies and domains as searchable text
        for list_field in ("technologies", "languages", "domains"):
            vals = node.get(list_field, [])
            if isinstance(vals, list):
                parts.extend(str(v) for v in vals)
        return " ".join(parts)
