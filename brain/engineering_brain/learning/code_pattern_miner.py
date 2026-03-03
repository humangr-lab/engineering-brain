"""Code pattern miner for the Engineering Knowledge Brain.

Mines knowledge from source code via AST analysis. Extracts recurring patterns
that can become L4 Findings in the knowledge graph:
- Error handling patterns (try/except structures)
- API conventions (decorator patterns, route definitions)
- Security patterns (input validation, auth checks)
- Import patterns (common dependency clusters)

Reference: AST-based code mining (Allamanis et al. "Mining Idioms" ESEC/FSE 2014).
"""

from __future__ import annotations

import ast
import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


PATTERN_TYPES = [
    "error_handling",
    "api_convention",
    "security_check",
    "import_cluster",
    "naming_convention",
]


@dataclass
class MinedPattern:
    """A single pattern extracted from source code."""

    pattern_type: str
    description: str
    code_snippet: str
    filepath: str
    line_number: int
    frequency: int = 1
    technologies: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    signature: str = ""  # Dedup key

    def __post_init__(self) -> None:
        if not self.signature:
            self.signature = f"{self.pattern_type}:{self.description[:80]}"


class CodePatternMiner:
    """Mine knowledge from source code via AST analysis.

    Produces L4 Finding proposals from recurring code patterns.
    """

    def __init__(
        self,
        graph: Any = None,
        config: Any = None,
    ) -> None:
        self._graph = graph
        self._config = config
        self._patterns: dict[str, list[MinedPattern]] = {t: [] for t in PATTERN_TYPES}
        self._files_processed: int = 0
        # Frequency counter for dedup across files
        self._pattern_freq: Counter[str] = Counter()

    def mine_file(self, filepath: str) -> list[MinedPattern]:
        """Mine patterns from a single Python file via AST."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                source = f.read()
        except (OSError, IOError):
            return []

        try:
            tree = ast.parse(source, filename=filepath)
        except SyntaxError:
            return []

        self._files_processed += 1
        found: list[MinedPattern] = []

        found.extend(self._extract_error_patterns(tree, filepath))
        found.extend(self._extract_api_patterns(tree, filepath))
        found.extend(self._extract_security_patterns(tree, filepath))
        found.extend(self._extract_import_clusters(tree, filepath))

        # Track frequencies
        for p in found:
            self._pattern_freq[p.signature] += 1
            p.frequency = self._pattern_freq[p.signature]
            self._patterns[p.pattern_type].append(p)

        return found

    def mine_directory(
        self,
        dirpath: str,
        batch_size: int = 10,
    ) -> list[MinedPattern]:
        """Mine patterns from all Python files in a directory.

        Processes in batches to avoid memory spikes.
        """
        all_patterns: list[MinedPattern] = []
        py_files = []

        for root, _dirs, files in os.walk(dirpath):
            for fname in files:
                if fname.endswith(".py"):
                    py_files.append(os.path.join(root, fname))

        for i in range(0, len(py_files), batch_size):
            batch = py_files[i:i + batch_size]
            for fpath in batch:
                patterns = self.mine_file(fpath)
                all_patterns.extend(patterns)

        return all_patterns

    def _extract_error_patterns(
        self,
        tree: ast.Module,
        filepath: str,
    ) -> list[MinedPattern]:
        """Extract try/except patterns: which exceptions are caught, how they're handled."""
        patterns: list[MinedPattern] = []

        _TryStar = getattr(ast, "TryStar", None)  # Python 3.11+
        _try_types = (ast.Try,) if _TryStar is None else (ast.Try, _TryStar)
        for node in ast.walk(tree):
            if not isinstance(node, _try_types):
                continue

            for handler in node.handlers:
                exc_name = ""
                if handler.type:
                    if isinstance(handler.type, ast.Name):
                        exc_name = handler.type.id
                    elif isinstance(handler.type, ast.Attribute):
                        exc_name = ast.dump(handler.type)

                # Detect bare except (bad practice)
                if handler.type is None:
                    patterns.append(MinedPattern(
                        pattern_type="error_handling",
                        description="Bare except clause catches all exceptions including SystemExit/KeyboardInterrupt",
                        code_snippet=f"except:  # line {handler.lineno}",
                        filepath=filepath,
                        line_number=handler.lineno,
                        domains=["code_quality"],
                        signature="error_handling:bare_except",
                    ))
                elif exc_name == "Exception":
                    # Check if it's re-raised or logged
                    has_reraise = any(
                        isinstance(s, ast.Raise) for s in handler.body
                    )
                    has_log = any(
                        isinstance(s, ast.Expr)
                        and isinstance(getattr(s, "value", None), ast.Call)
                        and "log" in ast.dump(s.value).lower()
                        for s in handler.body
                    )
                    if not has_reraise and not has_log:
                        patterns.append(MinedPattern(
                            pattern_type="error_handling",
                            description=f"Catching {exc_name} without re-raising or logging silences errors",
                            code_snippet=f"except {exc_name}:  # line {handler.lineno}",
                            filepath=filepath,
                            line_number=handler.lineno,
                            domains=["code_quality"],
                            signature="error_handling:silent_exception",
                        ))
                    elif has_log:
                        patterns.append(MinedPattern(
                            pattern_type="error_handling",
                            description=f"Catching {exc_name} with logging — good practice",
                            code_snippet=f"except {exc_name}: log(...)  # line {handler.lineno}",
                            filepath=filepath,
                            line_number=handler.lineno,
                            domains=["code_quality"],
                            signature="error_handling:logged_exception",
                        ))

                # Detect pass-only handlers
                if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                    patterns.append(MinedPattern(
                        pattern_type="error_handling",
                        description=f"Exception handler with only 'pass' silently swallows {exc_name or 'all'} errors",
                        code_snippet=f"except {exc_name or '...'}: pass  # line {handler.lineno}",
                        filepath=filepath,
                        line_number=handler.lineno,
                        domains=["code_quality"],
                        signature="error_handling:pass_only",
                    ))

        return patterns

    def _extract_api_patterns(
        self,
        tree: ast.Module,
        filepath: str,
    ) -> list[MinedPattern]:
        """Extract decorator-based API patterns (Flask routes, FastAPI endpoints, etc.)."""
        patterns: list[MinedPattern] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            for decorator in node.decorator_list:
                dec_text = ast.dump(decorator)

                # Flask/FastAPI route decorators
                if "route" in dec_text.lower() or "app." in dec_text.lower():
                    techs = []
                    if "flask" in dec_text.lower() or "app.route" in dec_text.lower():
                        techs = ["flask"]
                    elif "fastapi" in dec_text.lower() or "router." in dec_text.lower():
                        techs = ["fastapi"]

                    patterns.append(MinedPattern(
                        pattern_type="api_convention",
                        description=f"API endpoint: {node.name}()",
                        code_snippet=f"@...route  def {node.name}():  # line {node.lineno}",
                        filepath=filepath,
                        line_number=node.lineno,
                        technologies=techs,
                        domains=["api"],
                        signature=f"api_convention:route_{node.name}",
                    ))

                # Auth decorators
                if any(kw in dec_text.lower() for kw in ["login_required", "auth", "permission", "jwt_required"]):
                    patterns.append(MinedPattern(
                        pattern_type="security_check",
                        description=f"Auth-protected endpoint: {node.name}()",
                        code_snippet=f"@auth_decorator def {node.name}():  # line {node.lineno}",
                        filepath=filepath,
                        line_number=node.lineno,
                        domains=["security"],
                        signature=f"security_check:auth_{node.name}",
                    ))

        return patterns

    def _extract_security_patterns(
        self,
        tree: ast.Module,
        filepath: str,
    ) -> list[MinedPattern]:
        """Extract security-related patterns (validation, sanitization)."""
        patterns: list[MinedPattern] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_text = ast.dump(node)

                # SQL injection risk: string formatting in DB calls
                if any(kw in call_text.lower() for kw in ["execute", "raw", "cursor"]):
                    # Check if f-string or format is used
                    for arg in node.args:
                        if isinstance(arg, ast.JoinedStr):  # f-string
                            patterns.append(MinedPattern(
                                pattern_type="security_check",
                                description="SQL query built with f-string — potential SQL injection",
                                code_snippet=f"execute(f'...')  # line {node.lineno}",
                                filepath=filepath,
                                line_number=node.lineno,
                                domains=["security", "database"],
                                signature="security_check:sql_fstring",
                            ))

                # Input validation patterns
                if any(kw in call_text.lower() for kw in ["validate", "sanitize", "escape", "clean"]):
                    patterns.append(MinedPattern(
                        pattern_type="security_check",
                        description="Input validation/sanitization call detected",
                        code_snippet=f"validate/sanitize call  # line {node.lineno}",
                        filepath=filepath,
                        line_number=node.lineno,
                        domains=["security"],
                        signature="security_check:input_validation",
                    ))

        return patterns

    def _extract_import_clusters(
        self,
        tree: ast.Module,
        filepath: str,
    ) -> list[MinedPattern]:
        """Extract frequently co-imported module groups."""
        imports: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module.split(".")[0])

        if len(imports) < 2:
            return []

        # Deduplicate
        unique_imports = sorted(set(imports))
        if len(unique_imports) > 1:
            cluster_key = ",".join(unique_imports[:10])  # Cap at 10
            return [MinedPattern(
                pattern_type="import_cluster",
                description=f"Import cluster: {', '.join(unique_imports[:8])}",
                code_snippet=f"imports: {cluster_key}",
                filepath=filepath,
                line_number=1,
                signature=f"import_cluster:{cluster_key}",
            )]

        return []

    def propose_findings(self, min_frequency: int = 3) -> list[dict[str, Any]]:
        """Convert mined patterns into L4 Finding proposals.

        A pattern that appears >= min_frequency times becomes a Finding.
        Confidence = min(1.0, frequency / 10).
        """
        findings: list[dict[str, Any]] = []
        seen_sigs: set[str] = set()

        for ptype, patterns in self._patterns.items():
            for pattern in patterns:
                freq = self._pattern_freq.get(pattern.signature, pattern.frequency)
                if freq < min_frequency:
                    continue
                if pattern.signature in seen_sigs:
                    continue
                seen_sigs.add(pattern.signature)

                confidence = min(1.0, freq / 10.0)
                findings.append({
                    "pattern_type": pattern.pattern_type,
                    "description": pattern.description,
                    "code_snippet": pattern.code_snippet,
                    "frequency": freq,
                    "confidence": confidence,
                    "technologies": pattern.technologies,
                    "domains": pattern.domains,
                    "source_files": [pattern.filepath],
                    "severity": "medium" if pattern.pattern_type != "security_check" else "high",
                })

        # Sort by frequency descending
        findings.sort(key=lambda f: f["frequency"], reverse=True)
        logger.info(
            "Proposed %d findings from %d patterns (min_frequency=%d)",
            len(findings), sum(len(v) for v in self._patterns.values()), min_frequency,
        )
        return findings

    def stats(self) -> dict[str, Any]:
        """Patterns found per type, files processed."""
        return {
            "files_processed": self._files_processed,
            "patterns_by_type": {k: len(v) for k, v in self._patterns.items()},
            "total_patterns": sum(len(v) for v in self._patterns.values()),
            "unique_signatures": len(self._pattern_freq),
        }
