"""Tests for provenance tracking."""

from __future__ import annotations

import pytest

from engineering_brain.epistemic.provenance import ProvenanceChain, ProvenanceRecord


class TestProvenanceRecord:
    def test_creation(self):
        rec = ProvenanceRecord(
            operation="bootstrap",
            timestamp="2026-02-19T10:00:00+00:00",
            inputs=({"source": "L3 prior", "opinion": {"b": 0.3, "d": 0, "u": 0.7}},),
            output={"ep_b": 0.5, "ep_d": 0, "ep_u": 0.5, "ep_a": 0.5},
            reason="bootstrapped from L3 prior + 2 sources",
        )
        assert rec.operation == "bootstrap"
        assert len(rec.inputs) == 1

    def test_to_dict_roundtrip(self):
        rec = ProvenanceRecord(
            operation="cbf_reinforce",
            timestamp="2026-02-19T11:00:00+00:00",
            inputs=({"source": "EV-001"},),
            output={"ep_b": 0.7},
            reason="positive reinforcement",
        )
        d = rec.to_dict()
        assert d["operation"] == "cbf_reinforce"
        assert isinstance(d["inputs"], list)

        restored = ProvenanceRecord.from_dict(d)
        assert restored.operation == rec.operation
        assert restored.timestamp == rec.timestamp
        assert restored.reason == rec.reason

    def test_frozen(self):
        rec = ProvenanceRecord(
            operation="decay",
            timestamp="2026-02-19T12:00:00+00:00",
            inputs=(),
            output={},
            reason="temporal decay",
        )
        with pytest.raises(AttributeError):
            rec.operation = "changed"


class TestProvenanceChain:
    def test_empty_chain(self):
        chain = ProvenanceChain()
        assert chain.latest() is None
        assert chain.summary() == "no provenance recorded"

    def test_add_and_latest(self):
        chain = ProvenanceChain()
        rec = ProvenanceRecord(
            operation="bootstrap",
            timestamp="2026-02-19T10:00:00+00:00",
            inputs=(),
            output={"ep_b": 0.5},
            reason="initial bootstrap",
        )
        chain.add(rec)
        assert chain.latest() == rec

    def test_record_convenience(self):
        chain = ProvenanceChain()
        rec = chain.record(
            operation="cbf_reinforce",
            inputs=[{"source": "EV-001"}],
            output={"ep_b": 0.7},
            reason="positive reinforcement",
        )
        assert chain.latest() == rec
        assert rec.timestamp  # should have auto-generated timestamp

    def test_summary(self):
        chain = ProvenanceChain()
        chain.record("bootstrap", [], {}, "init")
        chain.record("cbf_reinforce", [], {}, "reinforce 1")
        chain.record("cbf_reinforce", [], {}, "reinforce 2")
        chain.record("decay", [], {}, "temporal decay")

        summary = chain.summary()
        assert "bootstrap 1x" in summary
        assert "cbf_reinforce 2x" in summary
        assert "decay 1x" in summary

    def test_to_list_from_list_roundtrip(self):
        chain = ProvenanceChain()
        chain.record("bootstrap", [{"x": 1}], {"ep_b": 0.5}, "init")
        chain.record("decay", [], {"ep_b": 0.4}, "decay")

        data = chain.to_list()
        assert len(data) == 2

        restored = ProvenanceChain.from_list(data)
        assert len(restored.records) == 2
        assert restored.records[0].operation == "bootstrap"
        assert restored.records[1].operation == "decay"

    def test_append_only(self):
        """Chain only grows, never shrinks."""
        chain = ProvenanceChain()
        for i in range(5):
            chain.record(f"op_{i}", [], {}, f"reason {i}")
        assert len(chain.records) == 5
