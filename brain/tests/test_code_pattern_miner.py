"""Tests for the CodePatternMiner (Gap 3 — AST-based code pattern mining).

Covers:
- MinedPattern dataclass defaults and custom signatures
- PATTERN_TYPES constant
- Error handling pattern extraction (bare except, silent exception, pass-only)
- API convention pattern extraction (Flask routes)
- Security pattern extraction (SQL f-string injection)
- Import cluster extraction
- Directory mining with batch processing
- Finding proposal frequency threshold
- Stats structure
"""

from __future__ import annotations

import os
import sys
import tempfile
import shutil

import pytest

# Ensure src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from engineering_brain.learning.code_pattern_miner import (
    CodePatternMiner,
    MinedPattern,
    PATTERN_TYPES,
)


# =============================================================================
# Temp file helpers
# =============================================================================


def _write_temp_file(content: str) -> str:
    """Write content to a temporary .py file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".py")
    with os.fdopen(fd, "w") as f:
        f.write(content)
    return path


# =============================================================================
# Code snippets for testing
# =============================================================================

BARE_EXCEPT_CODE = """\
try:
    x = 1
except:
    pass
"""

SILENT_EXCEPTION_CODE = """\
try:
    x = 1
except Exception:
    x = 0
"""

PASS_ONLY_HANDLER_CODE = """\
try:
    risky()
except ValueError:
    pass
"""

FLASK_ROUTE_CODE = """\
from flask import Flask
app = Flask(__name__)

@app.route("/api/users")
def get_users():
    return []
"""

SQL_FSTRING_CODE = """\
def query_db(name):
    cursor.execute(f"SELECT * FROM users WHERE name = '{name}'")
"""

IMPORT_CLUSTER_CODE = """\
import os
import sys
import json
from collections import Counter
"""

CLEAN_CODE = """\
def add(a, b):
    return a + b
"""


# =============================================================================
# 1. MinedPattern dataclass tests
# =============================================================================


def test_mined_pattern_default_signature():
    """Auto-generates signature from pattern_type:description[:80]."""
    p = MinedPattern(
        pattern_type="error_handling",
        description="Bare except clause catches all exceptions",
        code_snippet="except:",
        filepath="test.py",
        line_number=5,
    )
    assert p.signature == "error_handling:Bare except clause catches all exceptions"


def test_mined_pattern_custom_signature():
    """Uses provided signature instead of auto-generating."""
    p = MinedPattern(
        pattern_type="error_handling",
        description="Some description",
        code_snippet="except:",
        filepath="test.py",
        line_number=5,
        signature="custom:my_signature",
    )
    assert p.signature == "custom:my_signature"


# =============================================================================
# 2. PATTERN_TYPES constant
# =============================================================================


def test_pattern_types_defined():
    """PATTERN_TYPES contains exactly 5 expected types."""
    assert len(PATTERN_TYPES) == 5
    assert "error_handling" in PATTERN_TYPES
    assert "api_convention" in PATTERN_TYPES
    assert "security_check" in PATTERN_TYPES
    assert "import_cluster" in PATTERN_TYPES
    assert "naming_convention" in PATTERN_TYPES


# =============================================================================
# 3. Error handling pattern extraction
# =============================================================================


def test_mine_bare_except():
    """Detects bare except clause (except: without exception type)."""
    path = _write_temp_file(BARE_EXCEPT_CODE)
    try:
        miner = CodePatternMiner()
        patterns = miner.mine_file(path)

        bare = [p for p in patterns if p.signature == "error_handling:bare_except"]
        assert len(bare) >= 1
        assert bare[0].pattern_type == "error_handling"
        assert "bare except" in bare[0].description.lower() or "Bare except" in bare[0].description
        assert bare[0].filepath == path
    finally:
        os.unlink(path)


def test_mine_silent_exception():
    """Detects except Exception without re-raise or logging."""
    path = _write_temp_file(SILENT_EXCEPTION_CODE)
    try:
        miner = CodePatternMiner()
        patterns = miner.mine_file(path)

        silent = [p for p in patterns if p.signature == "error_handling:silent_exception"]
        assert len(silent) >= 1
        assert silent[0].pattern_type == "error_handling"
        assert "Exception" in silent[0].description
        assert silent[0].filepath == path
    finally:
        os.unlink(path)


def test_mine_pass_only_handler():
    """Detects except handler with only 'pass' in body."""
    path = _write_temp_file(PASS_ONLY_HANDLER_CODE)
    try:
        miner = CodePatternMiner()
        patterns = miner.mine_file(path)

        pass_only = [p for p in patterns if p.signature == "error_handling:pass_only"]
        assert len(pass_only) >= 1
        assert pass_only[0].pattern_type == "error_handling"
        assert "pass" in pass_only[0].description.lower()
        assert pass_only[0].filepath == path
    finally:
        os.unlink(path)


# =============================================================================
# 4. API convention pattern extraction
# =============================================================================


def test_mine_flask_route():
    """Detects @app.route decorator as API convention pattern."""
    path = _write_temp_file(FLASK_ROUTE_CODE)
    try:
        miner = CodePatternMiner()
        patterns = miner.mine_file(path)

        api_patterns = [p for p in patterns if p.pattern_type == "api_convention"]
        assert len(api_patterns) >= 1

        route_pat = api_patterns[0]
        assert "get_users" in route_pat.description
        assert route_pat.filepath == path
        assert "flask" in route_pat.technologies or "api" in route_pat.domains
    finally:
        os.unlink(path)


# =============================================================================
# 5. Security pattern extraction
# =============================================================================


def test_mine_sql_fstring():
    """Detects execute(f'...') as SQL injection risk."""
    path = _write_temp_file(SQL_FSTRING_CODE)
    try:
        miner = CodePatternMiner()
        patterns = miner.mine_file(path)

        security = [p for p in patterns if p.signature == "security_check:sql_fstring"]
        assert len(security) >= 1
        assert security[0].pattern_type == "security_check"
        assert "sql" in security[0].description.lower() or "SQL" in security[0].description
        assert "security" in security[0].domains
        assert security[0].filepath == path
    finally:
        os.unlink(path)


# =============================================================================
# 6. Import cluster extraction
# =============================================================================


def test_mine_import_clusters():
    """Detects co-imported modules as import cluster."""
    path = _write_temp_file(IMPORT_CLUSTER_CODE)
    try:
        miner = CodePatternMiner()
        patterns = miner.mine_file(path)

        clusters = [p for p in patterns if p.pattern_type == "import_cluster"]
        assert len(clusters) >= 1

        cluster = clusters[0]
        assert "import_cluster:" in cluster.signature
        # The cluster should contain the imported module names
        assert "collections" in cluster.description or "collections" in cluster.code_snippet
        assert "os" in cluster.description or "os" in cluster.code_snippet
        assert "sys" in cluster.description or "sys" in cluster.code_snippet
        assert "json" in cluster.description or "json" in cluster.code_snippet
    finally:
        os.unlink(path)


# =============================================================================
# 7. Directory mining
# =============================================================================


def test_mine_directory_batch():
    """Processes directory with multiple .py files in batches."""
    tmpdir = tempfile.mkdtemp()
    try:
        # Create multiple Python files with patterns
        for i in range(5):
            fpath = os.path.join(tmpdir, f"module_{i}.py")
            with open(fpath, "w") as f:
                f.write(BARE_EXCEPT_CODE)

        miner = CodePatternMiner()
        patterns = miner.mine_directory(tmpdir, batch_size=2)

        # Should have processed all 5 files
        assert miner._files_processed == 5
        # Each file has at least a bare_except + pass_only pattern
        assert len(patterns) >= 5

        bare_excepts = [p for p in patterns if p.signature == "error_handling:bare_except"]
        assert len(bare_excepts) == 5

        # The frequency counter should track cumulative occurrences
        stats = miner.stats()
        assert stats["files_processed"] == 5
        assert stats["total_patterns"] >= 5
    finally:
        shutil.rmtree(tmpdir)


# =============================================================================
# 8. Propose findings with frequency threshold
# =============================================================================


def test_propose_findings_frequency_threshold():
    """Only proposes findings when pattern frequency >= min_frequency."""
    tmpdir = tempfile.mkdtemp()
    try:
        # Create 5 files each with a bare except so frequency = 5
        for i in range(5):
            fpath = os.path.join(tmpdir, f"file_{i}.py")
            with open(fpath, "w") as f:
                f.write(BARE_EXCEPT_CODE)

        miner = CodePatternMiner()
        miner.mine_directory(tmpdir)

        # With min_frequency=3, bare_except (freq=5) should be proposed
        findings_low = miner.propose_findings(min_frequency=3)
        bare_sigs = [f for f in findings_low if f["pattern_type"] == "error_handling"]
        assert len(bare_sigs) >= 1

        # With min_frequency=10, nothing should be proposed (only 5 files)
        findings_high = miner.propose_findings(min_frequency=10)
        assert len(findings_high) == 0
    finally:
        shutil.rmtree(tmpdir)


# =============================================================================
# 9. Stats structure
# =============================================================================


def test_stats_structure():
    """Stats dict contains expected keys with correct types."""
    miner = CodePatternMiner()

    # Mine at least one file so stats are populated
    path = _write_temp_file(BARE_EXCEPT_CODE)
    try:
        miner.mine_file(path)
    finally:
        os.unlink(path)

    stats = miner.stats()

    assert "files_processed" in stats
    assert "patterns_by_type" in stats
    assert "total_patterns" in stats
    assert "unique_signatures" in stats

    assert isinstance(stats["files_processed"], int)
    assert isinstance(stats["patterns_by_type"], dict)
    assert isinstance(stats["total_patterns"], int)
    assert isinstance(stats["unique_signatures"], int)

    assert stats["files_processed"] == 1
    assert stats["total_patterns"] >= 1

    # patterns_by_type should have keys for all PATTERN_TYPES
    for pt in PATTERN_TYPES:
        assert pt in stats["patterns_by_type"]


# =============================================================================
# 10. Edge cases
# =============================================================================


def test_mine_file_nonexistent():
    """Mining a nonexistent file returns empty list without error."""
    miner = CodePatternMiner()
    patterns = miner.mine_file("/nonexistent/path/file.py")
    assert patterns == []


def test_mine_file_syntax_error():
    """Mining a file with syntax errors returns empty list without error."""
    path = _write_temp_file("def broken(\n")
    try:
        miner = CodePatternMiner()
        patterns = miner.mine_file(path)
        assert patterns == []
    finally:
        os.unlink(path)


def test_mine_clean_code_no_bad_patterns():
    """Clean code without anti-patterns produces no error_handling/security patterns."""
    path = _write_temp_file(CLEAN_CODE)
    try:
        miner = CodePatternMiner()
        patterns = miner.mine_file(path)

        error_patterns = [p for p in patterns if p.pattern_type == "error_handling"]
        security_patterns = [p for p in patterns if p.pattern_type == "security_check"]
        assert len(error_patterns) == 0
        assert len(security_patterns) == 0
    finally:
        os.unlink(path)
