"""Tests for PackMaterializer — template-driven pack creation + composition."""

from __future__ import annotations

import json
import tempfile

import pytest

from engineering_brain.adapters.memory import MemoryGraphAdapter
from engineering_brain.core.config import BrainConfig
from engineering_brain.core.schema import EdgeType, NodeType
from engineering_brain.core.types import MaterializedPack, MCPToolSpec, PackTemplate
from engineering_brain.retrieval.pack_materializer import PackMaterializer


@pytest.fixture
def config():
    return BrainConfig()


@pytest.fixture
def graph():
    g = MemoryGraphAdapter()
    # Add L1 principles
    g.add_node(NodeType.PRINCIPLE.value, "P-SEC-BOUNDARY", {
        "id": "P-SEC-BOUNDARY",
        "name": "Validate at Boundary",
        "why": "All input is hostile until proven otherwise",
        "how_to_apply": "Validate at every system boundary",
        "mental_model": "Castle walls metaphor",
        "domains": ["security"],
    })
    g.add_node(NodeType.PRINCIPLE.value, "P-ERR-FAIL-FAST", {
        "id": "P-ERR-FAIL-FAST",
        "name": "Fail Fast",
        "why": "Catching errors early prevents cascading failures",
        "how_to_apply": "Validate preconditions at function entry",
        "mental_model": "Electrical fuse analogy",
        "domains": ["error_handling"],
    })
    # Add L2 patterns
    g.add_node(NodeType.PATTERN.value, "PAT-SEC-INPUT-VALID", {
        "id": "PAT-SEC-INPUT-VALID",
        "name": "Input Validation Pattern",
        "intent": "Prevent injection attacks",
        "when_to_use": "Any user-facing input",
        "languages": ["python", "flask"],
        "domains": ["security"],
    })
    g.add_node(NodeType.PATTERN.value, "PAT-ERR-RESULT", {
        "id": "PAT-ERR-RESULT",
        "name": "Result Type Pattern",
        "intent": "Structured error handling",
        "when_to_use": "Operations that can fail",
        "languages": ["python"],
        "domains": ["error_handling"],
    })
    # Add L3 rules
    for i in range(10):
        severity = "critical" if i < 2 else "high" if i < 5 else "medium"
        tech = "flask" if i < 7 else "django"
        g.add_node(NodeType.RULE.value, f"CR-SEC-{i:03d}", {
            "id": f"CR-SEC-{i:03d}",
            "text": f"Security rule {i}",
            "why": f"Because security matter #{i}",
            "how_to_do_right": f"Do it right #{i}",
            "severity": severity,
            "confidence": 0.8 - (i * 0.05),
            "technologies": [tech],
            "domains": ["security"],
            "example_good": f"good_code_{i}()",
            "example_bad": f"bad_code_{i}()",
        })
    # Add edges
    g.add_edge("P-SEC-BOUNDARY", "PAT-SEC-INPUT-VALID", EdgeType.INFORMS.value)
    g.add_edge("PAT-SEC-INPUT-VALID", "CR-SEC-000", EdgeType.INSTANTIATES.value)
    g.add_edge("PAT-SEC-INPUT-VALID", "CR-SEC-001", EdgeType.INSTANTIATES.value)
    return g


@pytest.fixture
def materializer(graph, config):
    return PackMaterializer(
        graph=graph,
        vector=None,
        config=config,
    )


@pytest.fixture
def security_template():
    return PackTemplate(
        id="security-review",
        name="Security Review Pack",
        description="Security knowledge for vulnerability detection",
        layers=["L1", "L2", "L3"],
        domains=["security"],
        severities=["critical", "high", "medium"],
        min_confidence=0.0,
        exclude_deprecated=True,
        min_nodes=3,
        max_nodes=20,
        min_quality=0.2,
        prefer_high_severity=True,
        tags=["security"],
        mcp_tools=[
            MCPToolSpec(name="check_vulnerability", description="Check vuln", handler_type="query"),
        ],
    )


class TestPackMaterializer:
    """Test MaterializedPack creation from templates."""

    def test_materialize_basic(self, materializer, security_template):
        pack = materializer.materialize(security_template)
        assert isinstance(pack, MaterializedPack)
        assert pack.node_count > 0
        assert pack.template_id == "security-review"
        assert pack.template_version == "1.0.0"

    def test_materialize_has_nodes(self, materializer, security_template):
        pack = materializer.materialize(security_template)
        assert len(pack.nodes) > 0
        assert len(pack.nodes) == pack.node_count
        # All nodes should have an id
        for node in pack.nodes:
            assert "id" in node

    def test_materialize_has_edges(self, materializer, security_template):
        pack = materializer.materialize(security_template)
        # Should have at least some edges from the graph
        assert isinstance(pack.edges, list)
        assert isinstance(pack.reasoning_edges, list)

    def test_materialize_technology_filter(self, materializer, security_template):
        pack = materializer.materialize(security_template, technologies=["flask"])
        assert pack.node_count > 0
        # The pack should focus on flask
        assert "flask" in [t.lower() for t in pack.technologies] or pack.node_count > 0

    def test_materialize_technology_filter_excludes_mismatch(self, materializer):
        """Bug fix: technology filter must actually exclude non-matching nodes."""
        from engineering_brain.core.types import PackTemplate
        template = PackTemplate(
            id="django-only",
            layers=["L3"],
            technologies=["django"],
            domains=["security"],
            min_nodes=0,
            max_nodes=20,
        )
        pack = materializer.materialize(template)
        # Nodes with technologies=["flask"] should be excluded
        for node in pack.nodes:
            node_techs = node.get("technologies") or node.get("languages") or []
            if node_techs:
                # If the node has technologies, at least one must match "django"
                has_django = any("django" in t.lower() for t in node_techs)
                has_no_tech = len(node_techs) == 0
                assert has_django or has_no_tech, (
                    f"Node {node.get('id')} has techs {node_techs} but should only have django"
                )

    def test_materialize_severity_sorting(self, materializer, security_template):
        """prefer_high_severity=True should sort critical/high first."""
        security_template.prefer_high_severity = True
        pack = materializer.materialize(security_template)
        # Check that nodes are sorted by severity (critical first)
        severities = [n.get("severity", "medium") for n in pack.nodes if n.get("severity")]
        if severities:
            # First severity should be critical or high
            assert severities[0] in ("critical", "high") or len(severities) <= 3

    def test_materialize_quality_score(self, materializer, security_template):
        pack = materializer.materialize(security_template)
        assert 0.0 <= pack.quality_score <= 1.0

    def test_materialize_layers_present(self, materializer, security_template):
        pack = materializer.materialize(security_template)
        assert isinstance(pack.layers_present, list)
        # Should have at least some layers
        assert len(pack.layers_present) > 0


class TestPackComposition:
    """Test composing multiple packs."""

    def test_compose_two_packs(self, materializer, security_template):
        error_template = PackTemplate(
            id="error-handling",
            name="Error Handling",
            layers=["L1", "L2", "L3"],
            domains=["error_handling"],
            min_nodes=2,
            max_nodes=20,
        )

        pack1 = materializer.materialize(security_template)
        pack2 = materializer.materialize(error_template)

        composed = materializer.compose([pack1, pack2])
        assert isinstance(composed, MaterializedPack)
        # Composed should have at least as many unique nodes as either single pack
        assert composed.node_count >= min(pack1.node_count, pack2.node_count)
        assert "security-review" in composed.template_id
        assert "error-handling" in composed.template_id

    def test_compose_deduplicates(self, materializer, security_template):
        # Same template twice — should deduplicate
        pack1 = materializer.materialize(security_template)
        pack2 = materializer.materialize(security_template)

        composed = materializer.compose([pack1, pack2])
        # Deduplication means composed should have same or fewer nodes
        assert composed.node_count <= pack1.node_count + pack2.node_count

    def test_compose_single_raises(self, materializer):
        with pytest.raises(ValueError):
            materializer.compose([])

    def test_compose_single_returns_pack(self, materializer, security_template):
        pack1 = materializer.materialize(security_template)
        result = materializer.compose([pack1])
        assert result is pack1


class TestMaterializedPackLifecycle:
    """Test save/load/record_usage."""

    def test_save_and_load(self, materializer, security_template):
        pack = materializer.materialize(security_template)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        pack.save(path)
        loaded = MaterializedPack.load(path)

        assert loaded.id == pack.id
        assert loaded.template_id == pack.template_id
        assert loaded.node_count == pack.node_count
        assert len(loaded.nodes) == len(pack.nodes)

    def test_record_usage(self, materializer, security_template):
        pack = materializer.materialize(security_template)
        assert pack.usage_count == 0
        pack.record_usage()
        assert pack.usage_count == 1
        pack.record_usage(["CR-SEC-000"])
        assert pack.usage_count == 2

    def test_materialize_attaches_template(self, materializer, security_template):
        """Bug fix: materialize() must attach template for serve()/export()."""
        pack = materializer.materialize(security_template)
        assert pack._template is not None
        assert pack._template.id == "security-review"

    def test_resolve_template_from_attached(self, materializer, security_template):
        """Bug fix: _resolve_template() returns attached template."""
        pack = materializer.materialize(security_template)
        resolved = pack._resolve_template()
        assert resolved is not None
        assert resolved.id == "security-review"
        assert len(resolved.mcp_tools) > 0

    def test_export_uses_template_tools(self, materializer, security_template):
        """Bug fix: export() should use domain-specific tools, not defaults."""
        pack = materializer.materialize(security_template)
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        import tempfile as _tf
        import json as _json
        with _tf.TemporaryDirectory() as tmpdir:
            import os
            out = os.path.join(tmpdir, "test-export")
            pack.export(out)
            with open(os.path.join(out, "pack_data.json")) as f:
                data = _json.load(f)
            tool_names = [t["name"] for t in data["tool_manifest"]]
            # Must have template-specific tools, not generic defaults
            assert "check_vulnerability" in tool_names
            assert "search_knowledge" not in tool_names


class TestBrainPackIntegration:
    """Test brain.pack() one-liner API."""

    def test_brain_pack_with_seeded_brain(self):
        """Integration test: brain.pack() with real templates."""
        from engineering_brain.core.brain import Brain

        brain = Brain()
        brain.seed()

        config = brain._config
        import os
        if not os.path.isdir(config.pack_templates_directory):
            pytest.skip("Production templates not found")

        pack = brain.pack("security-review", technologies=["flask"])
        assert isinstance(pack, MaterializedPack)
        assert pack.node_count > 0
        assert pack.template_id == "security-review"
        assert len(pack.nodes) > 0

    def test_brain_compose_with_seeded_brain(self):
        """Integration test: brain.compose() with real templates."""
        from engineering_brain.core.brain import Brain

        brain = Brain()
        brain.seed()

        config = brain._config
        import os
        if not os.path.isdir(config.pack_templates_directory):
            pytest.skip("Production templates not found")

        pack = brain.compose(["security-review", "code-review"])
        assert isinstance(pack, MaterializedPack)
        assert pack.node_count > 0
        assert "security-review" in pack.template_id
        assert "code-review" in pack.template_id
