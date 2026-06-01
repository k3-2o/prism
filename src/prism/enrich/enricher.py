"""Caller enrichment — find cross-file callers for functions with measurements."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tree_sitter import Query, QueryCursor

from prism.engine.languages import (
    extension_to_language,
    get_parser,
    get_queries,
    supported_extensions,
)


def discover_project_files(root: str) -> list[str]:
    """Recursively find all supported source files under root, excluding venvs."""
    excluded = {
        "venv",
        ".venv",
        ".env",
        "env",
        "node_modules",
        "__pycache__",
        ".git",
        "target",
        "build",
        "dist",
        ".terraform",
    }
    files: list[str] = []
    root_path = Path(root).resolve()
    exts = tuple(supported_extensions())
    for p in root_path.rglob("*"):
        if p.suffix.lower() not in exts:
            continue
        if any(part in excluded for part in p.relative_to(root_path).parts):
            continue
        files.append(str(p))
    return sorted(files)


def find_cross_file_callers(
    function_name: str,
    target_file: str,
    project_files: list[str],
) -> list[dict[str, Any]]:
    """Search all project files for calls to function_name outside target_file."""
    callers: list[dict[str, Any]] = []

    for fpath in project_files:
        if fpath == target_file:
            continue
        try:
            data = Path(fpath).read_bytes()
        except Exception:
            continue

        ext = Path(fpath).suffix.lower()
        lang = extension_to_language(ext)
        if not lang:
            continue

        try:
            parser = get_parser(lang)
            queries = get_queries(lang)
        except ValueError:
            continue

        tree = parser.parse(data)
        cursor = QueryCursor(queries["calls"])

        for _pat_idx, captures in cursor.matches(tree.root_node):
            for name, nodes in captures.items():
                if name != "name":
                    continue
                for node in nodes:
                    func_text = data[node.start_byte : node.end_byte].decode("utf-8")
                    if func_text == function_name:
                        enclosing = _find_enclosing_function(node, data)
                        line = node.start_point[0] + 1
                        callers.append(
                            {
                                "function": enclosing or "<module>",
                                "file": fpath,
                                "line": line,
                            }
                        )

    # Deduplicate
    seen: set[tuple[str, str, int]] = set()
    unique: list[dict[str, Any]] = []
    for c in callers:
        key = (c["file"], c["function"], c["line"])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def _find_enclosing_function(node: Any, data: bytes) -> str | None:
    """Walk up the tree to find the enclosing function definition.

    Uses a generic approach: looks for any node whose type contains
    'function', 'method', or 'constructor' as a heuristic across languages.
    """
    current = node.parent
    while current is not None:
        ctype = current.type
        if any(tag in ctype for tag in ("function", "method", "constructor")):
            for child in current.children:
                if child.type in ("identifier", "property_identifier", "field_identifier", "name"):
                    return data[child.start_byte : child.end_byte].decode("utf-8")
            return "<anonymous>"
        current = current.parent
    return None


def _find_function_at_line(root: Any, data: bytes, line: int) -> dict[str, Any] | None:
    """Find the function or method that contains a given 1-indexed line number."""
    target = line - 1
    from tree_sitter import Query, QueryCursor

    # Use a broad query that captures any function-like construct
    lang = None
    # We need the language object for the query. Use the root's tree to find it.
    # Actually, let's just walk the tree for this — simpler and language-agnostic.
    cursor = root.walk()
    reached_root = False
    while not reached_root:
        node = cursor.node
        ctype = node.type
        if any(tag in ctype for tag in ("function", "method", "constructor")):
            start = node.start_point[0]
            end = node.end_point[0]
            if start <= target <= end:
                name = ""
                for child in node.children:
                    if child.type in (
                        "identifier",
                        "property_identifier",
                        "field_identifier",
                        "name",
                    ):
                        name = data[child.start_byte : child.end_byte].decode("utf-8")
                        break
                func_text = data[node.start_byte : node.end_byte].decode("utf-8")
                signature = func_text.split("\n")[0].strip()
                body_lines = end - start + 1
                return {
                    "function": name,
                    "signature": signature,
                    "body_lines": body_lines,
                }
        if cursor.goto_first_child():
            continue
        if cursor.goto_next_sibling():
            continue
        reached_root = cursor.goto_parent()
        while not reached_root:
            if cursor.goto_next_sibling():
                break
            reached_root = cursor.goto_parent()
    return None


def enrich_by_line(
    finding: dict[str, Any],
    target_file: str,
    project_files: list[str] | None,
) -> dict[str, Any]:
    """Enrich a Semgrep finding by finding its enclosing function."""
    line = finding.get("location", {}).get("line", 0)
    if not line:
        return finding

    ext = Path(target_file).suffix.lower()
    lang = extension_to_language(ext)
    if not lang:
        return finding

    try:
        data = Path(target_file).read_bytes()
        parser = get_parser(lang)
        tree = parser.parse(data)
        func_info = _find_function_at_line(tree.root_node, data, line)
    except Exception:
        return finding

    if func_info:
        ctx = finding.setdefault("context", {})
        ctx["function"] = func_info.get("function", "")
        ctx["signature"] = func_info.get("signature", "")
        ctx["body_lines"] = func_info.get("body_lines", 0)

        func_name = func_info.get("function", "")
        if func_name and project_files:
            callers = find_cross_file_callers(func_name, target_file, project_files)
            ctx["callers"] = callers

    return finding


def enrich_measurements(
    items: list[dict[str, Any]],
    target_file: str,
    project_files: list[str] | None,
) -> list[dict[str, Any]]:
    """Attach cross-file caller information to each measurement."""
    if not project_files:
        return items

    enriched: list[dict[str, Any]] = []
    for item in items:
        func_name = item.get("function", "")
        if func_name:
            callers = find_cross_file_callers(func_name, target_file, project_files)
            if callers:
                item.setdefault("context", {})["callers"] = callers
        enriched.append(item)

    return enriched
