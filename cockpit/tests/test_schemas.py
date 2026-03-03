"""Schema validation tests.

Ensures all JSON schemas are well-formed and all example files
validate against their respective schemas.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator


# -- Schema well-formedness --------------------------------------------------


class TestSchemasWellFormed:
    """Verify that every .json file in schemas/ is a valid JSON Schema."""

    def test_graph_data_schema_is_valid(self, schemas_dir: Path):
        schema_file = schemas_dir / "graph_data.json"
        assert schema_file.exists(), "schemas/graph_data.json must exist"
        schema = json.loads(schema_file.read_text())
        Draft202012Validator.check_schema(schema)

    def test_cockpit_schema_is_valid(self, schemas_dir: Path):
        schema_file = schemas_dir / "cockpit_schema.json"
        assert schema_file.exists(), "schemas/cockpit_schema.json must exist"
        schema = json.loads(schema_file.read_text())
        Draft202012Validator.check_schema(schema)

    def test_all_schemas_are_valid(self, schemas_dir: Path):
        """Every .json file in schemas/ must be a valid JSON Schema."""
        schema_files = sorted(schemas_dir.glob("*.json"))
        assert len(schema_files) > 0, "At least one schema must exist"
        for schema_file in schema_files:
            schema = json.loads(schema_file.read_text())
            Draft202012Validator.check_schema(schema)


# -- Embedded examples -------------------------------------------------------


class TestEmbeddedExamples:
    """Validate the 'examples' array embedded in each schema."""

    def test_graph_data_embedded_examples(self, schemas_dir: Path):
        schema = json.loads((schemas_dir / "graph_data.json").read_text())
        validator = Draft202012Validator(schema)
        examples = schema.get("examples", [])
        assert len(examples) >= 1, "graph_data schema should have at least 1 example"
        for i, example in enumerate(examples):
            errors = list(validator.iter_errors(example))
            assert errors == [], f"example[{i}] failed: {errors[0].message if errors else ''}"

    def test_cockpit_schema_embedded_examples(self, schemas_dir: Path):
        schema = json.loads((schemas_dir / "cockpit_schema.json").read_text())
        validator = Draft202012Validator(schema)
        examples = schema.get("examples", [])
        assert len(examples) >= 1, "cockpit_schema should have at least 1 example"
        for i, example in enumerate(examples):
            errors = list(validator.iter_errors(example))
            assert errors == [], f"example[{i}] failed: {errors[0].message if errors else ''}"


# -- Example files -----------------------------------------------------------


class TestExampleFiles:
    """Validate real example files against their schemas."""

    def test_engineering_brain_graph_data(self, schemas_dir: Path, examples_dir: Path):
        """examples/engineering-brain/graph_data.json must validate."""
        schema_file = schemas_dir / "graph_data.json"
        example_file = examples_dir / "engineering-brain" / "graph_data.json"
        if not example_file.exists():
            pytest.skip("engineering-brain example not present")

        schema = json.loads(schema_file.read_text())
        data = json.loads(example_file.read_text())
        validator = Draft202012Validator(schema)
        errors = list(validator.iter_errors(data))
        assert errors == [], f"Validation failed: {errors[0].message if errors else ''}"

    def test_engineering_brain_graph_has_nodes(self, examples_dir: Path):
        """The example graph should have a non-trivial number of nodes."""
        example_file = examples_dir / "engineering-brain" / "graph_data.json"
        if not example_file.exists():
            pytest.skip("engineering-brain example not present")

        data = json.loads(example_file.read_text())
        assert len(data["nodes"]) >= 1, "Example graph should have at least 1 node"
        assert isinstance(data["edges"], list), "Edges should be a list"


# -- Invalid graph rejection -------------------------------------------------


class TestInvalidGraphs:
    """Ensure the schema correctly rejects invalid data."""

    def _get_validator(self, schemas_dir: Path) -> Draft202012Validator:
        schema = json.loads((schemas_dir / "graph_data.json").read_text())
        return Draft202012Validator(schema)

    def test_empty_object_is_invalid(self, schemas_dir: Path):
        validator = self._get_validator(schemas_dir)
        errors = list(validator.iter_errors({}))
        assert len(errors) > 0, "Empty object should be rejected (missing nodes, edges)"

    def test_missing_nodes_is_invalid(self, schemas_dir: Path):
        validator = self._get_validator(schemas_dir)
        errors = list(validator.iter_errors({"edges": []}))
        assert len(errors) > 0, "Missing 'nodes' should be rejected"

    def test_missing_edges_is_invalid(self, schemas_dir: Path):
        validator = self._get_validator(schemas_dir)
        errors = list(validator.iter_errors({"nodes": [{"id": "a"}]}))
        assert len(errors) > 0, "Missing 'edges' should be rejected"

    def test_empty_nodes_is_invalid(self, schemas_dir: Path):
        validator = self._get_validator(schemas_dir)
        errors = list(validator.iter_errors({"nodes": [], "edges": []}))
        assert len(errors) > 0, "Empty nodes array should be rejected (minItems: 1)"

    def test_node_without_id_is_invalid(self, schemas_dir: Path):
        validator = self._get_validator(schemas_dir)
        data = {"nodes": [{"label": "no id"}], "edges": []}
        errors = list(validator.iter_errors(data))
        assert len(errors) > 0, "Node without 'id' should be rejected"

    def test_edge_without_from_is_invalid(self, schemas_dir: Path):
        validator = self._get_validator(schemas_dir)
        data = {"nodes": [{"id": "a"}], "edges": [{"to": "a"}]}
        errors = list(validator.iter_errors(data))
        assert len(errors) > 0, "Edge without 'from' should be rejected"

    def test_edge_without_to_is_invalid(self, schemas_dir: Path):
        validator = self._get_validator(schemas_dir)
        data = {"nodes": [{"id": "a"}], "edges": [{"from": "a"}]}
        errors = list(validator.iter_errors(data))
        assert len(errors) > 0, "Edge without 'to' should be rejected"

    def test_minimal_valid_graph(self, schemas_dir: Path):
        """Sanity: the simplest valid graph should pass."""
        validator = self._get_validator(schemas_dir)
        data = {"nodes": [{"id": "x"}], "edges": []}
        errors = list(validator.iter_errors(data))
        assert errors == [], f"Minimal valid graph should pass: {errors[0].message if errors else ''}"

    def test_additional_properties_rejected_at_root(self, schemas_dir: Path):
        """Root-level additional properties should be rejected."""
        validator = self._get_validator(schemas_dir)
        data = {"nodes": [{"id": "a"}], "edges": [], "extra_field": True}
        errors = list(validator.iter_errors(data))
        assert len(errors) > 0, "Additional root properties should be rejected"
