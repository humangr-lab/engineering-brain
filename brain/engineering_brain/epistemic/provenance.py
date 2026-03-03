"""Provenance tracking for epistemic opinion computations.

Every opinion transformation (bootstrap, reinforce, decay, contradiction
resolve) creates an append-only provenance record. This enables:
- Audit trail: "why does this node have b=0.85?"
- Debugging: trace unexpected opinion values back to their source
- Transparency: show users how knowledge confidence was computed

Note: This is an append-only ordered list, not a cryptographic hash chain.
Records are stored sequentially and their integrity relies on the storage
layer. A future enhancement could add hash-linking (each record hashing the
previous) for tamper-evidence, but the current design prioritizes simplicity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    """Single provenance entry for an opinion computation."""

    operation: str      # "bootstrap", "cbf_reinforce", "decay", "contradiction_resolve"
    timestamp: str      # ISO 8601
    inputs: tuple[dict[str, Any], ...]  # tuple for frozen hashability
    output: dict[str, Any]              # {ep_b, ep_d, ep_u, ep_a}
    reason: str         # human-readable explanation

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "timestamp": self.timestamp,
            "inputs": list(self.inputs),
            "output": self.output,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProvenanceRecord:
        return cls(
            operation=d["operation"],
            timestamp=d["timestamp"],
            inputs=tuple(d.get("inputs", [])),
            output=d.get("output", {}),
            reason=d.get("reason", ""),
        )


@dataclass
class ProvenanceChain:
    """Append-only provenance chain for a node's epistemic history."""

    records: list[ProvenanceRecord] = field(default_factory=list)

    def add(self, record: ProvenanceRecord) -> None:
        """Append a provenance record."""
        self.records.append(record)

    def record(
        self,
        operation: str,
        inputs: list[dict[str, Any]],
        output: dict[str, Any],
        reason: str,
    ) -> ProvenanceRecord:
        """Create and append a provenance record with current timestamp."""
        rec = ProvenanceRecord(
            operation=operation,
            timestamp=datetime.now(timezone.utc).isoformat(),
            inputs=tuple(inputs),
            output=output,
            reason=reason,
        )
        self.records.append(rec)
        return rec

    def latest(self) -> ProvenanceRecord | None:
        """Get most recent provenance record."""
        return self.records[-1] if self.records else None

    def summary(self) -> str:
        """Human-readable summary of the provenance chain."""
        if not self.records:
            return "no provenance recorded"
        ops = {}
        for r in self.records:
            ops[r.operation] = ops.get(r.operation, 0) + 1
        parts = [f"{op} {count}x" for op, count in ops.items()]
        return ", ".join(parts)

    def to_list(self) -> list[dict[str, Any]]:
        """Serialize to list of dicts for storage."""
        return [r.to_dict() for r in self.records]

    @classmethod
    def from_list(cls, data: list[dict[str, Any]]) -> ProvenanceChain:
        """Deserialize from list of dicts."""
        chain = cls()
        for d in data:
            chain.records.append(ProvenanceRecord.from_dict(d))
        return chain
