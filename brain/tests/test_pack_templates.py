"""Tests for PackTemplateRegistry — template loading, inheritance, discovery."""

from __future__ import annotations

import os
import tempfile

import pytest
import yaml

from engineering_brain.core.config import BrainConfig
from engineering_brain.core.types import MCPToolSpec, PackTemplate
from engineering_brain.retrieval.pack_templates import (
    PackTemplateRegistry,
    reset_template_registry,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    """Reset the singleton between tests."""
    reset_template_registry()
    yield
    reset_template_registry()


@pytest.fixture
def templates_dir():
    """Create a temp directory with test templates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Template 1: base template
        base = {
            "id": "base",
            "name": "Base Template",
            "description": "A base template",
            "layers": ["L1", "L2", "L3"],
            "domains": ["general"],
            "min_nodes": 5,
            "max_nodes": 50,
            "tags": ["base"],
            "mcp_tools": [
                {
                    "name": "search",
                    "description": "Search knowledge",
                    "handler_type": "query",
                },
            ],
        }
        with open(os.path.join(tmpdir, "base.yaml"), "w") as f:
            yaml.dump(base, f)

        # Template 2: child extends base
        child = {
            "id": "child",
            "name": "Child Template",
            "description": "Extends base",
            "extends": ["base"],
            "domains": ["security"],
            "severities": ["critical", "high"],
            "prefer_high_severity": True,
            "tags": ["security", "child"],
            "mcp_tools": [
                {
                    "name": "check_vuln",
                    "description": "Check vulnerabilities",
                    "handler_type": "query",
                },
            ],
        }
        with open(os.path.join(tmpdir, "child.yaml"), "w") as f:
            yaml.dump(child, f)

        # Template 3: standalone
        standalone = {
            "id": "standalone",
            "name": "Standalone",
            "description": "No inheritance",
            "layers": ["L0", "L1"],
            "domains": ["testing"],
            "technologies": ["python*", "flask"],
            "tags": ["testing"],
        }
        with open(os.path.join(tmpdir, "standalone.yaml"), "w") as f:
            yaml.dump(standalone, f)

        yield tmpdir


class TestPackTemplateLoading:
    """Test template loading from YAML files."""

    def test_load_templates(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        templates = registry.list_templates()
        assert len(templates) == 3

    def test_get_template_by_id(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        t = registry.get("base")
        assert t.id == "base"
        assert t.name == "Base Template"
        assert "L1" in t.layers
        assert "L2" in t.layers
        assert "L3" in t.layers

    def test_get_nonexistent_raises(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        with pytest.raises(KeyError):
            registry.get("nonexistent")

    def test_mcp_tools_loaded(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        t = registry.get("base")
        assert len(t.mcp_tools) == 1
        assert t.mcp_tools[0].name == "search"
        assert isinstance(t.mcp_tools[0], MCPToolSpec)

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = PackTemplateRegistry(templates_dir=tmpdir)
            assert registry.size == 0
            assert registry.list_templates() == []

    def test_nonexistent_directory(self):
        registry = PackTemplateRegistry(templates_dir="/nonexistent/path")
        assert registry.size == 0


class TestPackTemplateInheritance:
    """Test template inheritance via `extends`."""

    def test_child_inherits_layers(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        child = registry.get("child")
        # Child doesn't set layers, should inherit from base
        assert "L1" in child.layers
        assert "L2" in child.layers
        assert "L3" in child.layers

    def test_child_overrides_domains(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        child = registry.get("child")
        # Child explicitly sets domains
        assert child.domains == ["security"]

    def test_child_adds_severities(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        child = registry.get("child")
        assert "critical" in child.severities
        assert "high" in child.severities

    def test_child_overrides_bool(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        child = registry.get("child")
        assert child.prefer_high_severity is True

    def test_child_keeps_own_identity(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        child = registry.get("child")
        assert child.id == "child"
        assert child.name == "Child Template"
        assert child.description == "Extends base"

    def test_child_has_own_mcp_tools(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        child = registry.get("child")
        assert len(child.mcp_tools) == 1
        assert child.mcp_tools[0].name == "check_vuln"


class TestPackTemplateSearch:
    """Test template search and discovery."""

    def test_search_by_tag(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        results = registry.search(tags=["security"])
        assert len(results) == 1
        assert results[0].id == "child"

    def test_search_by_tag_base(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        results = registry.search(tags=["base"])
        assert len(results) == 1
        assert results[0].id == "base"

    def test_search_by_domain(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        results = registry.search(domain="testing")
        assert len(results) == 1
        assert results[0].id == "standalone"

    def test_search_by_technology(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        results = registry.search(technology="flask")
        assert len(results) == 1
        assert results[0].id == "standalone"

    def test_search_no_match(self, templates_dir: str):
        registry = PackTemplateRegistry(templates_dir=templates_dir)
        results = registry.search(tags=["nonexistent"])
        assert len(results) == 0


class TestPackTemplateModel:
    """Test PackTemplate Pydantic model."""

    def test_model_creation(self):
        t = PackTemplate(id="test")
        assert t.id == "test"
        assert t.version == "1.0.0"
        assert t.layers == []
        assert t.min_nodes == 5
        assert t.max_nodes == 80

    def test_model_with_tools(self):
        t = PackTemplate(
            id="test",
            mcp_tools=[
                MCPToolSpec(name="search", description="Search", handler_type="query"),
            ],
        )
        assert len(t.mcp_tools) == 1
        assert t.mcp_tools[0].name == "search"

    def test_model_serialization_roundtrip(self):
        t = PackTemplate(
            id="test",
            name="Test",
            layers=["L1", "L3"],
            domains=["security"],
            tags=["sec"],
            mcp_tools=[MCPToolSpec(name="t1", handler_type="query")],
        )
        data = t.model_dump()
        t2 = PackTemplate(**data)
        assert t2.id == t.id
        assert t2.layers == t.layers
        assert len(t2.mcp_tools) == 1


class TestProductionTemplates:
    """Test that the 10 production YAML templates load correctly."""

    def test_production_templates_load(self):
        config = BrainConfig()
        templates_dir = config.pack_templates_directory
        if not os.path.isdir(templates_dir):
            pytest.skip(f"Production templates dir not found: {templates_dir}")

        registry = PackTemplateRegistry(templates_dir=templates_dir)
        templates = registry.list_templates()
        assert len(templates) >= 10, f"Expected >=10 templates, got {len(templates)}"

    def test_all_production_templates_have_id(self):
        config = BrainConfig()
        templates_dir = config.pack_templates_directory
        if not os.path.isdir(templates_dir):
            pytest.skip(f"Production templates dir not found: {templates_dir}")

        registry = PackTemplateRegistry(templates_dir=templates_dir)
        for t in registry.list_templates():
            assert t.id, "Template missing id"
            assert t.name, f"Template {t.id} missing name"

    def test_security_review_template(self):
        config = BrainConfig()
        registry = PackTemplateRegistry(config=config)
        try:
            t = registry.get("security-review")
        except KeyError:
            pytest.skip("security-review template not found")
        assert t.prefer_high_severity is True
        assert "security" in t.domains
        assert len(t.mcp_tools) >= 4
        assert any(tool.name == "check_vulnerability" for tool in t.mcp_tools)
