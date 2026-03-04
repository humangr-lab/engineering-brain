"""Tests for OntologyAligner — SKOS-based ontology alignment for taxonomy tags.

Tests cover:
- URI prefix expansion (Wikidata, DBpedia, Schema.org, passthrough)
- Applying and removing alignments (exact, broad, narrow, related)
- Duplicate prevention on apply
- Invalid match type / unknown tag rejection
- SKOS export format
- Batch alignment coverage (align_all)
- SKOS file import from JSON (tempfile)
- Statistics structure and counts
- Cosine similarity helper

Gap 6: Ontology Alignment
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

_SRC = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "src")
sys.path.insert(0, os.path.abspath(_SRC))

from engineering_brain.core.taxonomy import Tag, TagRegistry
from engineering_brain.retrieval.ontology_aligner import (
    MATCH_TYPES,
    ONTOLOGY_PREFIXES,
    OntologyAligner,
)

# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture
def simple_registry() -> TagRegistry:
    """A small registry with three tags for alignment tests."""
    registry = TagRegistry()
    registry.register(Tag(id="python", facet="technology", display_name="Python"))
    registry.register(Tag(id="flask", facet="technology", display_name="Flask"))
    registry.register(Tag(id="security", facet="domain", display_name="Security"))
    return registry


@pytest.fixture
def aligner(simple_registry: TagRegistry) -> OntologyAligner:
    return OntologyAligner(simple_registry)


# =====================================================================
# URI expansion
# =====================================================================


class TestExpandUri:
    def test_expand_uri_wikidata(self):
        """wd:Q28865 expands to Wikidata full URL."""
        result = OntologyAligner._expand_uri("wd:Q28865")
        assert result == "https://www.wikidata.org/wiki/Q28865"

    def test_expand_uri_dbpedia(self):
        """dbr:Python expands to DBpedia full URL."""
        result = OntologyAligner._expand_uri("dbr:Python")
        assert result == "https://dbpedia.org/resource/Python"

    def test_expand_uri_schema(self):
        """schema:WebApplication expands to Schema.org full URL."""
        result = OntologyAligner._expand_uri("schema:WebApplication")
        assert result == "https://schema.org/WebApplication"

    def test_expand_uri_owl(self):
        """owl:Thing expands to OWL full URL."""
        result = OntologyAligner._expand_uri("owl:Thing")
        assert result == "http://www.w3.org/2002/07/owl#Thing"

    def test_expand_uri_no_prefix(self):
        """A full URL without a known prefix is returned unchanged."""
        uri = "https://example.com/foo"
        result = OntologyAligner._expand_uri(uri)
        assert result == uri


# =====================================================================
# apply_alignment
# =====================================================================


class TestApplyAlignment:
    def test_apply_alignment_exact_match(
        self, aligner: OntologyAligner, simple_registry: TagRegistry
    ):
        """Applying an exact_match alignment adds the expanded URI to the tag."""
        ok = aligner.apply_alignment("python", "exact_match", "wd:Q28865")
        assert ok is True

        tag = simple_registry.get("python")
        assert "https://www.wikidata.org/wiki/Q28865" in tag.exact_match

    def test_apply_alignment_broad_match(
        self, aligner: OntologyAligner, simple_registry: TagRegistry
    ):
        """Applying a broad_match alignment works correctly."""
        ok = aligner.apply_alignment("flask", "broad_match", "schema:WebApplication")
        assert ok is True

        tag = simple_registry.get("flask")
        assert "https://schema.org/WebApplication" in tag.broad_match

    def test_apply_alignment_narrow_match(
        self, aligner: OntologyAligner, simple_registry: TagRegistry
    ):
        """Applying a narrow_match alignment works correctly."""
        ok = aligner.apply_alignment("security", "narrow_match", "dbr:Computer_security")
        assert ok is True

        tag = simple_registry.get("security")
        assert "https://dbpedia.org/resource/Computer_security" in tag.narrow_match

    def test_apply_alignment_related_match(
        self, aligner: OntologyAligner, simple_registry: TagRegistry
    ):
        """Applying a related_match alignment works correctly."""
        ok = aligner.apply_alignment("python", "related_match", "dbr:Guido_van_Rossum")
        assert ok is True

        tag = simple_registry.get("python")
        assert "https://dbpedia.org/resource/Guido_van_Rossum" in tag.related_match

    def test_apply_alignment_invalid_match_type(self, aligner: OntologyAligner):
        """An invalid match type returns False."""
        ok = aligner.apply_alignment("python", "invalid_type", "wd:Q28865")
        assert ok is False

    def test_apply_alignment_unknown_tag(self, aligner: OntologyAligner):
        """Aligning a tag that does not exist in the registry returns False."""
        ok = aligner.apply_alignment("nonexistent_tag", "exact_match", "wd:Q28865")
        assert ok is False

    def test_apply_alignment_no_duplicates(
        self, aligner: OntologyAligner, simple_registry: TagRegistry
    ):
        """Applying the same alignment twice does not create a duplicate entry."""
        aligner.apply_alignment("python", "exact_match", "wd:Q28865")
        result_second = aligner.apply_alignment("python", "exact_match", "wd:Q28865")
        assert result_second is False

        tag = simple_registry.get("python")
        assert tag.exact_match.count("https://www.wikidata.org/wiki/Q28865") == 1


# =====================================================================
# remove_alignment
# =====================================================================


class TestRemoveAlignment:
    def test_remove_alignment(self, aligner: OntologyAligner, simple_registry: TagRegistry):
        """Removing a previously applied alignment returns True and clears the URI."""
        aligner.apply_alignment("python", "exact_match", "wd:Q28865")
        tag = simple_registry.get("python")
        assert len(tag.exact_match) == 1

        ok = aligner.remove_alignment("python", "exact_match", "wd:Q28865")
        assert ok is True
        assert len(tag.exact_match) == 0

    def test_remove_alignment_nonexistent(self, aligner: OntologyAligner):
        """Removing an alignment that was never applied returns False."""
        ok = aligner.remove_alignment("python", "exact_match", "wd:Q99999")
        assert ok is False

    def test_remove_alignment_unknown_tag(self, aligner: OntologyAligner):
        """Removing from a nonexistent tag returns False."""
        ok = aligner.remove_alignment("nonexistent", "exact_match", "wd:Q28865")
        assert ok is False

    def test_remove_alignment_invalid_match_type(self, aligner: OntologyAligner):
        """Removing with an invalid match type returns False."""
        ok = aligner.remove_alignment("python", "bad_type", "wd:Q28865")
        assert ok is False


# =====================================================================
# export_skos
# =====================================================================


class TestExportSkos:
    def test_export_skos_format(self, aligner: OntologyAligner):
        """Export returns a dict with 'alignments' list containing correct structure."""
        aligner.apply_alignment("python", "exact_match", "wd:Q28865")
        aligner.apply_alignment("python", "broad_match", "schema:ComputerLanguage")
        aligner.apply_alignment("flask", "exact_match", "wd:Q28927463")

        exported = aligner.export_skos()

        assert "alignments" in exported
        assert isinstance(exported["alignments"], list)
        assert len(exported["alignments"]) == 2  # python and flask

        tag_ids = {entry["tag_id"] for entry in exported["alignments"]}
        assert "python" in tag_ids
        assert "flask" in tag_ids

        python_entry = next(e for e in exported["alignments"] if e["tag_id"] == "python")
        assert "exact_match" in python_entry
        assert "broad_match" in python_entry
        assert "https://www.wikidata.org/wiki/Q28865" in python_entry["exact_match"]
        assert "https://schema.org/ComputerLanguage" in python_entry["broad_match"]

    def test_export_skos_empty(self, aligner: OntologyAligner):
        """Export with no alignments returns an empty list."""
        exported = aligner.export_skos()
        assert exported == {"alignments": []}

    def test_export_skos_excludes_unaligned(self, aligner: OntologyAligner):
        """Tags with no mappings are excluded from the export."""
        aligner.apply_alignment("python", "exact_match", "wd:Q28865")

        exported = aligner.export_skos()
        tag_ids = {entry["tag_id"] for entry in exported["alignments"]}
        assert "security" not in tag_ids  # no alignments applied to security


# =====================================================================
# align_all (coverage report)
# =====================================================================


class TestAlignAll:
    def test_align_all_coverage(self, aligner: OntologyAligner):
        """align_all reports correct aligned/unaligned counts and coverage."""
        # Initially all unaligned
        report = aligner.align_all()
        assert report["total_tags"] == 3
        assert report["aligned"] == 0
        assert report["unaligned"] == 3
        assert report["coverage"] == pytest.approx(0.0)

        # Align one tag
        aligner.apply_alignment("python", "exact_match", "wd:Q28865")
        report = aligner.align_all()
        assert report["aligned"] == 1
        assert report["unaligned"] == 2
        assert report["coverage"] == pytest.approx(1.0 / 3.0)

    def test_align_all_full_coverage(self, aligner: OntologyAligner):
        """When all tags are aligned, coverage is 1.0."""
        aligner.apply_alignment("python", "exact_match", "wd:Q28865")
        aligner.apply_alignment("flask", "broad_match", "schema:WebApplication")
        aligner.apply_alignment("security", "related_match", "dbr:Computer_security")

        report = aligner.align_all()
        assert report["aligned"] == 3
        assert report["unaligned"] == 0
        assert report["coverage"] == pytest.approx(1.0)


# =====================================================================
# import_skos_file
# =====================================================================


class TestImportSkosFile:
    def test_import_skos_file(self, aligner: OntologyAligner, simple_registry: TagRegistry):
        """Importing a JSON SKOS file applies all alignments and returns the count."""
        data = {
            "alignments": [
                {"tag_id": "python", "exact_match": ["wd:Q28865"]},
                {"tag_id": "flask", "broad_match": ["schema:WebApplication"]},
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
        ) as f:
            json.dump(data, f)
            tmp_path = f.name

        try:
            count = aligner.import_skos_file(tmp_path)
            assert count == 2

            python_tag = simple_registry.get("python")
            assert "https://www.wikidata.org/wiki/Q28865" in python_tag.exact_match

            flask_tag = simple_registry.get("flask")
            assert "https://schema.org/WebApplication" in flask_tag.broad_match
        finally:
            os.unlink(tmp_path)

    def test_import_skos_file_multiple_uris(
        self, aligner: OntologyAligner, simple_registry: TagRegistry
    ):
        """Import with multiple URIs per match type applies each one."""
        data = {
            "alignments": [
                {
                    "tag_id": "python",
                    "exact_match": ["wd:Q28865", "dbr:Python_(programming_language)"],
                },
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
        ) as f:
            json.dump(data, f)
            tmp_path = f.name

        try:
            count = aligner.import_skos_file(tmp_path)
            assert count == 2

            tag = simple_registry.get("python")
            assert len(tag.exact_match) == 2
        finally:
            os.unlink(tmp_path)

    def test_import_skos_file_nonexistent(self, aligner: OntologyAligner):
        """Importing from a nonexistent path returns 0."""
        count = aligner.import_skos_file("/nonexistent/path/to/skos.json")
        assert count == 0

    def test_import_skos_file_skips_unknown_tags(self, aligner: OntologyAligner):
        """Tags referenced in the file but absent from the registry are skipped."""
        data = {
            "alignments": [
                {"tag_id": "nonexistent_tag", "exact_match": ["wd:Q12345"]},
                {"tag_id": "python", "exact_match": ["wd:Q28865"]},
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
        ) as f:
            json.dump(data, f)
            tmp_path = f.name

        try:
            count = aligner.import_skos_file(tmp_path)
            assert count == 1  # Only python was applied
        finally:
            os.unlink(tmp_path)


# =====================================================================
# stats
# =====================================================================


class TestStats:
    def test_stats_structure(self, aligner: OntologyAligner):
        """stats() returns a dict with expected keys and correct types."""
        stats = aligner.stats()

        assert "total_tags" in stats
        assert "aligned" in stats
        assert "unaligned" in stats
        assert "coverage" in stats
        assert "match_type_counts" in stats
        assert "total_mappings" in stats

        assert isinstance(stats["total_tags"], int)
        assert isinstance(stats["aligned"], int)
        assert isinstance(stats["unaligned"], int)
        assert isinstance(stats["coverage"], float)
        assert isinstance(stats["match_type_counts"], dict)
        assert isinstance(stats["total_mappings"], int)

        # All match types present in counts
        for mt in MATCH_TYPES:
            assert mt in stats["match_type_counts"]

    def test_stats_counts_match_types(self, aligner: OntologyAligner):
        """stats() counts each match type correctly."""
        aligner.apply_alignment("python", "exact_match", "wd:Q28865")
        aligner.apply_alignment("python", "broad_match", "schema:ComputerLanguage")
        aligner.apply_alignment("flask", "exact_match", "wd:Q28927463")

        stats = aligner.stats()
        assert stats["match_type_counts"]["exact_match"] == 2
        assert stats["match_type_counts"]["broad_match"] == 1
        assert stats["match_type_counts"]["narrow_match"] == 0
        assert stats["match_type_counts"]["related_match"] == 0
        assert stats["total_mappings"] == 3

    def test_stats_empty(self, aligner: OntologyAligner):
        """stats() on a fresh aligner returns zeros for mappings."""
        stats = aligner.stats()
        assert stats["total_tags"] == 3
        assert stats["aligned"] == 0
        assert stats["total_mappings"] == 0


# =====================================================================
# Cosine similarity
# =====================================================================


class TestCosine:
    def test_cosine_identical(self):
        """Cosine of identical vectors is 1.0."""
        assert OntologyAligner._cosine([1, 0], [1, 0]) == pytest.approx(1.0)

    def test_cosine_orthogonal(self):
        """Cosine of orthogonal vectors is 0.0."""
        assert OntologyAligner._cosine([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_cosine_opposite(self):
        """Cosine of opposite vectors is -1.0."""
        assert OntologyAligner._cosine([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_cosine_empty(self):
        """Cosine of empty vectors returns 0.0."""
        assert OntologyAligner._cosine([], []) == 0.0

    def test_cosine_zero_vector(self):
        """Cosine with a zero vector returns 0.0."""
        assert OntologyAligner._cosine([0, 0], [1, 0]) == 0.0

    def test_cosine_length_mismatch(self):
        """Cosine of vectors with different lengths returns 0.0."""
        assert OntologyAligner._cosine([1, 0], [1, 0, 0]) == 0.0


# =====================================================================
# align_tag
# =====================================================================


class TestAlignTag:
    def test_align_tag_returns_current_mappings(self, aligner: OntologyAligner):
        """Without candidates, align_tag returns the tag's current SKOS mappings."""
        aligner.apply_alignment("python", "exact_match", "wd:Q28865")

        result = aligner.align_tag("python")
        assert result["tag_id"] == "python"
        assert "https://www.wikidata.org/wiki/Q28865" in result["exact_match"]

    def test_align_tag_unknown_returns_error(self, aligner: OntologyAligner):
        """Aligning an unknown tag returns an error dict."""
        result = aligner.align_tag("nonexistent_tag")
        assert "error" in result

    def test_align_tag_with_candidates_no_embedder(self, aligner: OntologyAligner):
        """With candidates but no embedder, returns candidates unscored."""
        candidates = [
            {"uri": "wd:Q28865", "label": "Python", "match_type": "exact_match"},
        ]
        result = aligner.align_tag("python", candidates=candidates)
        assert result["method"] == "no_scoring"
        assert len(result["candidates"]) == 1


# =====================================================================
# Constants
# =====================================================================


class TestConstants:
    def test_ontology_prefixes_are_complete(self):
        """ONTOLOGY_PREFIXES has exactly the expected keys."""
        assert set(ONTOLOGY_PREFIXES.keys()) == {"wd", "dbr", "schema", "owl"}

    def test_match_types_are_complete(self):
        """MATCH_TYPES has exactly the expected values."""
        assert {"exact_match", "broad_match", "narrow_match", "related_match"} == MATCH_TYPES
