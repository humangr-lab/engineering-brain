"""Tests for 3-layer Knowledge Triage Protocol (KTP).

Tests cover:
- Layer 1 (EXPLICIT): keyword detection from task description
- Layer 2 (IMPLIED): Technology Implication Graph (TIG) lookup
- Layer 3 (CONTEXTUAL): AST analysis of existing code files
- Epoch versioning: brain write counter + delta check
- KnowledgeShoppingList: merge + provenance tracking
"""

from __future__ import annotations

import os
import tempfile
import textwrap

import pytest


# ──────────────────────────────────────────────────────────────────────
# Layer 1: EXPLICIT keyword detection (existing behavior preserved)
# ──────────────────────────────────────────────────────────────────────

def test_layer1_explicit_keyword_detection():
    """Layer 1 detects technologies from task description keywords."""
    from engineering_brain.retrieval.task_knowledge import auto_tag_task

    task = {"description": "Create a Flask web server with CORS support"}
    task = auto_tag_task(task)

    assert "Flask" in task["knowledge_tags"]
    assert "CORS" in task["knowledge_tags"]
    assert "knowledge_provenance" in task


def test_layer1_already_tagged_tasks_preserved():
    """Tasks with explicit tags are NOT re-tagged."""
    from engineering_brain.retrieval.task_knowledge import auto_tag_task

    task = {
        "description": "Create a Flask web server",
        "knowledge_tags": ["CustomTech"],
        "knowledge_domains": ["custom_domain"],
    }
    task = auto_tag_task(task)

    assert task["knowledge_tags"] == ["CustomTech"]
    assert task["knowledge_domains"] == ["custom_domain"]


def test_layer1_empty_description():
    """Tasks with no description are returned unchanged."""
    from engineering_brain.retrieval.task_knowledge import auto_tag_task

    task = {}
    result = auto_tag_task(task)
    assert result == {}


# ──────────────────────────────────────────────────────────────────────
# Layer 2: TIG — Technology Implication Graph
# ──────────────────────────────────────────────────────────────────────

def test_layer2_tig_always_domains():
    """TIG 'always' domains are added unconditionally for detected tech."""
    from engineering_brain.retrieval.context_extractor import apply_technology_implications

    domains = apply_technology_implications(["Flask"], "create web server")

    assert "cors" in domains
    assert "error_handling" in domains
    assert "input_validation" in domains


def test_layer2_tig_conditional_routes():
    """TIG conditional domains are added when condition keywords match."""
    from engineering_brain.retrieval.context_extractor import apply_technology_implications

    # With route keywords
    domains_with = apply_technology_implications(["Flask"], "create web server with routes and endpoints")
    assert "path_traversal" in domains_with
    assert "auth_middleware" in domains_with

    # Without route keywords
    domains_without = apply_technology_implications(["Flask"], "create web server")
    assert "path_traversal" not in domains_without


def test_layer2_tig_conditional_database():
    """TIG detects database conditions correctly."""
    from engineering_brain.retrieval.context_extractor import apply_technology_implications

    domains = apply_technology_implications(["Flask"], "create web server with database models")
    assert "sql_injection" in domains
    assert "orm_patterns" in domains


def test_layer2_tig_unknown_tech():
    """TIG gracefully handles unknown technologies."""
    from engineering_brain.retrieval.context_extractor import apply_technology_implications

    domains = apply_technology_implications(["UnknownTech123"], "some description")
    assert domains == []


def test_layer2_tig_subprocess():
    """TIG expands subprocess to command_injection etc."""
    from engineering_brain.retrieval.context_extractor import apply_technology_implications

    domains = apply_technology_implications(["subprocess"], "run external command")
    assert "command_injection" in domains
    assert "path_sanitization" in domains
    assert "timeout" in domains


def test_layer2_tig_yaml_loading():
    """TIG loads from YAML file correctly."""
    from engineering_brain.retrieval.context_extractor import _load_tig

    tig = _load_tig()
    assert isinstance(tig, dict)
    assert "flask" in tig
    assert "always" in tig["flask"]
    assert len(tig["flask"]["always"]) >= 3


def test_layer2_full_auto_tag_with_tig():
    """auto_tag_task applies TIG expansion end-to-end."""
    from engineering_brain.retrieval.task_knowledge import auto_tag_task

    task = {"description": "Create a Flask web server with user endpoints"}
    task = auto_tag_task(task)

    # Flask detected by Layer 1
    assert "Flask" in task["knowledge_tags"]
    # TIG should add cors, error_handling etc.
    domains = task["knowledge_domains"]
    assert any(d in domains for d in ["cors", "error_handling", "input_validation"]), \
        f"Expected TIG domains in {domains}"


# ──────────────────────────────────────────────────────────────────────
# Layer 3: AST — Code analysis
# ──────────────────────────────────────────────────────────────────────

def test_layer3_ast_import_detection():
    """AST analysis detects technologies from Python imports."""
    from engineering_brain.retrieval.context_extractor import extract_ast_context

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(textwrap.dedent("""\
            import flask
            from sqlalchemy import Column
            import subprocess
        """))
        f.flush()
        path = f.name

    try:
        techs, domains = extract_ast_context([path])
        assert "Flask" in techs
        assert "SQLAlchemy" in techs
        assert "sql_injection" in domains
        assert "command_injection" in domains
    finally:
        os.unlink(path)


def test_layer3_ast_graceful_on_missing_file():
    """AST analysis returns empty on non-existent file."""
    from engineering_brain.retrieval.context_extractor import extract_ast_context

    techs, domains = extract_ast_context(["/nonexistent/file.py"])
    assert techs == []
    assert domains == []


def test_layer3_ast_graceful_on_syntax_error():
    """AST analysis returns empty on file with syntax errors."""
    from engineering_brain.retrieval.context_extractor import extract_ast_context

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def broken(\n  this is not valid python")
        f.flush()
        path = f.name

    try:
        techs, domains = extract_ast_context([path])
        assert techs == []
        assert domains == []
    finally:
        os.unlink(path)


def test_layer3_ast_from_import():
    """AST handles 'from X import Y' correctly."""
    from engineering_brain.retrieval.context_extractor import extract_ast_context

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("from flask import Flask, jsonify\n")
        f.flush()
        path = f.name

    try:
        techs, domains = extract_ast_context([path])
        assert "Flask" in techs
        assert "cors" in domains or "api" in domains or "security" in domains
    finally:
        os.unlink(path)


# ──────────────────────────────────────────────────────────────────────
# Provenance tracking
# ──────────────────────────────────────────────────────────────────────

def test_provenance_tracking():
    """auto_tag_task records provenance for each detected tag."""
    from engineering_brain.retrieval.task_knowledge import auto_tag_task

    task = {"description": "Create a Flask web server"}
    task = auto_tag_task(task)

    prov = task.get("knowledge_provenance", {})
    assert prov, "Expected provenance dict"
    # Flask should be "explicit" (keyword detection)
    assert prov.get("Flask") == "explicit"
    # TIG-expanded domains should be "tig"
    tig_items = [k for k, v in prov.items() if v == "tig"]
    assert len(tig_items) > 0, f"Expected TIG items in provenance: {prov}"


# ──────────────────────────────────────────────────────────────────────
# KnowledgeShoppingList
# ──────────────────────────────────────────────────────────────────────

def test_shopping_list_merge():
    """KnowledgeShoppingList.merge() deduplicates and preserves priority."""
    from engineering_brain.retrieval.context_extractor import KnowledgeShoppingList

    a = KnowledgeShoppingList(
        technologies=["Flask"],
        domains=["cors", "security"],
        provenance={"Flask": "explicit", "cors": "tig", "security": "explicit"},
    )
    b = KnowledgeShoppingList(
        technologies=["Flask", "Redis"],
        domains=["cors", "caching"],
        provenance={"Flask": "ast", "Redis": "ast", "cors": "explicit", "caching": "ast"},
    )

    merged = a.merge(b)
    assert "Flask" in merged.technologies
    assert "Redis" in merged.technologies
    assert "cors" in merged.domains
    assert "caching" in merged.domains
    # Flask should keep "explicit" (higher priority than "ast")
    assert merged.provenance["Flask"] == "explicit"
    # cors should upgrade to "explicit" (from b)
    assert merged.provenance["cors"] == "explicit"
    # Redis should be "ast" (only in b)
    assert merged.provenance["Redis"] == "ast"


# ──────────────────────────────────────────────────────────────────────
# Epoch versioning
# ──────────────────────────────────────────────────────────────────────

def test_brain_version_counter():
    """Brain.version increments on add_rule."""
    from engineering_brain import Brain

    brain = Brain(adapter="memory")
    assert brain.version == 0

    brain.add_rule(text="Test rule 1", why="Testing")
    assert brain.version == 1

    brain.add_rule(text="Test rule 2", why="Testing")
    assert brain.version == 2


def test_brain_version_all_write_methods():
    """Brain.version increments on all write methods."""
    from engineering_brain import Brain

    brain = Brain(adapter="memory")
    v = brain.version

    brain.add_axiom(statement="Test axiom")
    assert brain.version == v + 1

    brain.add_principle(name="Test", why="Why", how="How")
    assert brain.version == v + 2

    brain.add_pattern(name="Test", intent="Intent", when_to_use="When")
    assert brain.version == v + 3

    brain.add_rule(text="Test rule", why="Why")
    assert brain.version == v + 4


def test_check_knowledge_delta():
    """check_knowledge_delta detects changes between snapshots."""
    from engineering_brain.retrieval.task_knowledge import (
        init_task_knowledge,
        get_brain_version,
        check_knowledge_delta,
    )
    from engineering_brain import Brain

    brain = Brain(adapter="memory")
    init_task_knowledge(brain)

    pre = get_brain_version()
    brain.add_rule(text="New rule", why="Test")
    delta = check_knowledge_delta(pre)

    assert delta["changed"] is True
    assert delta["delta"] == 1
    assert delta["pre"] == pre
    assert delta["post"] == pre + 1


def test_check_knowledge_delta_no_change():
    """check_knowledge_delta reports no change when nothing written."""
    from engineering_brain.retrieval.task_knowledge import (
        init_task_knowledge,
        get_brain_version,
        check_knowledge_delta,
    )
    from engineering_brain import Brain

    brain = Brain(adapter="memory")
    init_task_knowledge(brain)

    pre = get_brain_version()
    delta = check_knowledge_delta(pre)

    assert delta["changed"] is False
    assert delta["delta"] == 0


# ──────────────────────────────────────────────────────────────────────
# Batch enrichment with 3-layer tagging
# ──────────────────────────────────────────────────────────────────────

def test_enrich_tasks_batch():
    """enrich_tasks_batch works with the new 3-layer tagging."""
    from engineering_brain.retrieval.task_knowledge import (
        init_task_knowledge,
        enrich_tasks_batch,
    )
    from engineering_brain import Brain

    brain = Brain(adapter="memory")
    brain.seed()
    init_task_knowledge(brain)

    tasks = [
        {"description": "Create a Flask web server"},
        {"description": "Set up Redis caching"},
    ]
    enriched = enrich_tasks_batch(tasks)

    assert len(enriched) == 2
    for t in enriched:
        assert "knowledge_tags" in t
        assert "knowledge_domains" in t
        assert "knowledge_provenance" in t


# ──────────────────────────────────────────────────────────────────────
# TIG graceful degradation
# ──────────────────────────────────────────────────────────────────────

def test_tig_graceful_degradation():
    """TIG falls back to inline data if YAML is missing."""
    from engineering_brain.retrieval import context_extractor

    # Force reload by clearing cache
    original = context_extractor._TIG_DATA
    context_extractor._TIG_DATA = None

    try:
        tig = context_extractor._load_tig()
        assert isinstance(tig, dict)
        assert "flask" in tig  # Should have at least flask from inline or YAML
    finally:
        context_extractor._TIG_DATA = original
