"""Import rule enforcement — architecture boundary checking.

Enforces user-defined rules about which modules are allowed to import
from which other modules. Like dependency-cruiser, but language-agnostic.

Rule format (in .prism.toml):
    [import_rules.features]
    pattern = "features/*"
    may_not = ["features/*"]       # features can't import from other features
    may_only = ["core/*", "shared/*"]  # features may only import from core/shared
    severity = "error"
"""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any


def check_import_rules(
    files: list[str],
    module_graph_data: dict[str, Any],
    config: dict | None = None,
) -> list[dict[str, Any]]:
    """Check all imports against configured rules.

    Args:
        files: list of project file paths
        module_graph_data: data from ModuleGraph
        config: PRISM config dict

    Returns:
        list of rule violation measurement dicts
    """
    if not config:
        return []

    rules_section = config.get("import_rules", {})
    if not rules_section:
        return []

    # Parse rules
    rules: list[dict] = []
    for rule_name, rule_def in rules_section.items():
        if not isinstance(rule_def, dict):
            continue
        pattern = rule_def.get("pattern", "")
        may_not = rule_def.get("may_not", [])
        may_only = rule_def.get("may_only", [])
        severity = rule_def.get("severity", "error")
        note = rule_def.get("note", "")

        if pattern and (may_not or may_only):
            rules.append(
                {
                    "name": rule_name,
                    "pattern": pattern,
                    "may_not": may_not if isinstance(may_not, list) else [may_not],
                    "may_only": may_only if isinstance(may_only, list) else [may_only],
                    "severity": severity,
                    "note": note,
                }
            )

    if not rules:
        return []

    # Get import data from module graph
    import_graph = module_graph_data.get("import_graph", {})

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for src_file in files:
        src_stem = Path(src_file).stem
        deps = import_graph.get(src_stem, [])

        for dep_stem in deps:
            # Find the actual source file path for the dependency
            dep_file = _find_file_by_stem(dep_stem, files)

            for rule in rules:
                # Check if source matches rule pattern
                if not _matches_pattern(src_file, rule["pattern"]):
                    continue

                # Check may_not rules
                for forbidden in rule.get("may_not", []):
                    if _matches_pattern(dep_file, forbidden):
                        key = (src_file, dep_file, rule["name"])
                        if key in seen:
                            continue
                        seen.add(key)
                        findings.append(
                            {
                                "source": "structure",
                                "metric": "import_rule_violation",
                                "function": Path(src_file).stem,
                                "value": 0,
                                "threshold": None,
                                "confidence": 100,
                                "location": {"file": src_file, "line": 1},
                                "context": {
                                    "callers": [],
                                    "detail": (
                                        f"imports {Path(dep_file).stem} from {dep_file},"
                                        f" violates '{rule['name']}'"
                                        f" (severity: {rule['severity']}):"
                                        f" may not import from '{forbidden}'"
                                    ),
                                    "rule": rule["name"],
                                    "severity": rule["severity"],
                                },
                            }
                        )

                # Check may_only rules
                for allowed in rule.get("may_only", []):
                    if not _matches_pattern(dep_file, allowed):
                        key = (src_file, dep_file, rule["name"])
                        if key in seen:
                            continue
                        seen.add(key)
                        findings.append(
                            {
                                "source": "structure",
                                "metric": "import_rule_violation",
                                "function": Path(src_file).stem,
                                "value": 0,
                                "threshold": None,
                                "confidence": 100,
                                "location": {"file": src_file, "line": 1},
                                "context": {
                                    "callers": [],
                                    "detail": (
                                        f"imports {Path(dep_file).stem} from {dep_file},"
                                        f" violates '{rule['name']}'"
                                        f" (severity: {rule['severity']}):"
                                        f" may only import from {rule.get('may_only', [])}"
                                    ),
                                    "rule": rule["name"],
                                    "severity": rule["severity"],
                                },
                            }
                        )

    return findings


def _matches_pattern(file_path: str, pattern: str) -> bool:
    """Check if a file path matches a glob pattern.

    Patterns can use *, **, ? like in fnmatch.
    Special cases:
        "features/*" matches "src/features/auth.py"
        "core/*" matches "src/core/models.py"
    """
    # Strip leading/trailing whitespace
    pattern = pattern.strip()

    # Try matching against the full path
    if fnmatch.fnmatch(file_path, pattern):
        return True

    # Try matching against just the filename
    if fnmatch.fnmatch(Path(file_path).stem, pattern):
        return True

    # Try matching against path segments (e.g., "features/*" against "src/features/foo.py")
    parts = Path(file_path).parts
    for i in range(len(parts) - 1):
        partial = str(Path(*parts[i:]))
        if fnmatch.fnmatch(partial, pattern):
            return True

    return False


def _find_file_by_stem(stem: str, files: list[str]) -> str:
    """Find a file path by its stem name."""
    for f in files:
        if Path(f).stem == stem:
            return f
    return stem  # fallback
