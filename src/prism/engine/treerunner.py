"""Tree-sitter structural measurement engine — multi-language support.

Uses the language registry (languages.py) to dispatch to the correct
tree-sitter grammar, queries, and thresholds for each file type.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tree_sitter import QueryCursor, Tree

from prism.config import get_whitelist, load_config
from prism.engine.languages import (
    LANGUAGES,
    extension_to_language,
    get_entry_points,
    get_ignore_names,
    get_impure_call_targets,
    get_parser,
    get_queries,
    get_risky_call_targets,
    get_thresholds,
    supported_extensions,
)
from prism.enrich.module_graph import ModuleGraph

# ── Code cache ───────────────────────────────────────────────────────────

_CODE_CACHE: dict[int, bytes] = {}
_LANG_CACHE: dict[int, str] = {}


def parse_file(path: str | Path) -> tuple[Tree, bytes, str]:
    """Parse a file, returning (tree, data_bytes, language_name)."""
    parser, lang = _get_parser_for_file(str(path))
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        raise ValueError(f"Cannot read file: {path} — {e}") from e
    try:
        tree = parser.parse(data)
    except Exception as e:
        raise ValueError(f"Cannot parse file: {path} — {e}") from e
    _CODE_CACHE[id(tree)] = data
    _LANG_CACHE[id(tree)] = lang
    return tree, data, lang


def _text(data: bytes, node: Any) -> str:
    """Extract text from bytes using node byte-range."""
    return data[node.start_byte : node.end_byte].decode("utf-8")


# ── Parser / language lookup ─────────────────────────────────────────────


def _get_parser_for_file(path: str) -> tuple[Any, str]:
    """Return (parser, language_name) for a file path."""
    ext = Path(path).suffix.lower()
    lang = extension_to_language(ext)
    if not lang:
        raise ValueError(
            f"Unsupported file type: {ext}. Supported: {', '.join(supported_extensions())}"
        )
    return get_parser(lang), lang


# ── Query helpers ────────────────────────────────────────────────────────


def _get_matches(query: Any, root: Any) -> list[tuple[int, dict[str, list[Any]]]]:
    cursor = QueryCursor(query)
    return list(cursor.matches(root))


def _get_captures(query: Any, root: Any) -> dict[str, list[Any]]:
    cursor = QueryCursor(query)
    return cursor.captures(root)


# ── Measurement helpers ──────────────────────────────────────────────────


def _count_parameters(params_node: Any, data: bytes, lang: str) -> int:
    """Count explicit parameters, excluding language-specific self/cls/this."""
    skipped = {"self", "cls", "this", "_", "mut self", "&self", "&mut self"}
    count = 0
    for child in params_node.children:
        child_text = _text(data, child)
        ctype = child.type

        # Skip keywords like self/cls/this
        if ctype == "identifier" and child_text in skipped:
            continue

        # Count actual parameter nodes
        if ctype in (
            "identifier",
            "typed_parameter",
            "default_parameter",
            "required_parameter",
            "optional_parameter",
            "formal_parameter",
            "parameter",
        ):
            # Skip if it's a keyword token
            if child_text in skipped:
                continue
            count += 1
        elif ctype in ("list_splat_pattern", "dictionary_splat_pattern"):
            count += 1  # *args, **kwargs
        elif ctype in ("rest_pattern", "hash_splat_pattern"):
            count += 1  # JS ...args, Ruby **kwargs

    return count


def _make_measurement(
    metric: str,
    function: str,
    value: int | float | None,
    threshold: int | float | None,
    location: dict,
    confidence: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "source": "structure",
        "metric": metric,
        "function": function,
        "value": value,
        "threshold": threshold,
        "location": location,
        "confidence": confidence,
        "context": {"callers": [], **extra},
    }


# ── Measurements ─────────────────────────────────────────────────────────


def measure_parameter_count(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Return functions with parameter count above language-specific threshold."""
    queries = get_queries(lang)
    thresholds = get_thresholds(lang)
    max_params = thresholds["parameter_count"]
    findings: list[dict[str, Any]] = []

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        params_node = None
        func_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "params" and nodes:
                params_node = nodes[0]
            elif name == "func" and nodes:
                func_node = nodes[0]

        if not func_name or not func_node:
            continue

        param_count = _count_parameters(params_node, data, lang) if params_node else 0
        line = func_node.start_point[0] + 1

        if param_count > max_params:
            findings.append(
                _make_measurement(
                    "parameter_count",
                    func_name,
                    param_count,
                    max_params,
                    {"file": file_path, "line": line},
                    signature=_text(data, func_node).split("\n")[0].strip(),
                )
            )

    return findings


def measure_nesting_depth(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Find functions with nesting depth above language-specific threshold.

    Uses AST walk of control structures (if/for/while/switch/try) instead of
    indent heuristic. More accurate and language-aware.
    """
    queries = get_queries(lang)
    thresholds = get_thresholds(lang)
    max_depth = thresholds["nesting_depth"]
    decision_types = set(LANGUAGES.get(lang, {}).get("decision_types", []))
    findings: list[dict[str, Any]] = []

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]

        if not func_name or not func_node:
            continue

        line = func_node.start_point[0] + 1

        # Walk the AST counting control structure nesting depth
        max_nest = _compute_ast_nesting(func_node, decision_types, 0)

        if max_nest > max_depth:
            findings.append(
                _make_measurement(
                    "nesting_depth",
                    func_name,
                    max_nest,
                    max_depth,
                    {"file": file_path, "line": line},
                )
            )

    return findings


def _compute_ast_nesting(node: Any, decision_types: set[str], depth: int) -> int:
    """Walk AST recursively, tracking max nesting depth of control structures.

    A control structure (if/for/while/switch/try) increments depth for its
    children. Non-control nodes pass depth unchanged.
    """
    current_depth = depth
    if node.type in decision_types:
        current_depth = depth + 1

    max_child_depth = current_depth
    for child in node.children:
        child_depth = _compute_ast_nesting(child, decision_types, current_depth)
        if child_depth > max_child_depth:
            max_child_depth = child_depth

    return max_child_depth


def measure_function_length(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Find functions longer than language-specific threshold."""
    queries = get_queries(lang)
    thresholds = get_thresholds(lang)
    max_lines = thresholds["function_length"]
    findings: list[dict[str, Any]] = []

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]

        if not func_name or not func_node:
            continue

        length = func_node.end_point[0] - func_node.start_point[0] + 1
        line = func_node.start_point[0] + 1

        if length > max_lines:
            findings.append(
                _make_measurement(
                    "function_length",
                    func_name,
                    length,
                    max_lines,
                    {"file": file_path, "line": line},
                )
            )

    return findings


def measure_dead_code(tree: Tree, data: bytes, file_path: str, lang: str) -> list[dict[str, Any]]:
    """Find functions defined but never called within the same file.

    If the language supports export detection (JS/TS), exported functions
    with no in-file calls are flagged as 'unused_export' instead of
    'dead_function' — they're API surface that may be used cross-file.
    """
    queries = get_queries(lang)
    ignore_names = set(get_ignore_names(lang)) | set(get_entry_points(lang))

    # Load whitelist from config to suppress false positives
    try:
        _cfg = load_config()
        whitelist = set(get_whitelist(_cfg).keys())
        ignore_names |= whitelist
    except Exception:
        pass

    defined: dict[str, int] = {}
    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]
        if func_name and func_node:
            defined[func_name] = func_node.start_point[0] + 1

    # Collect exported names (JS/TS)
    exported: set[str] = set()
    if "exports" in queries:
        for node in _get_captures(queries["exports"], tree.root_node).get("name", []):
            exported.add(_text(data, node))

    called: set[str] = set()
    captures = _get_captures(queries["calls"], tree.root_node)
    for node in captures.get("name", []):
        called.add(_text(data, node))

    # Also collect all identifier references for non-function export checking.
    # Skip export statements — names only in export declarations don't count.
    all_ids: set[str] = set()
    _collect_identifiers(tree.root_node, data, all_ids, skip_extra=frozenset({"export_statement"}))

    findings: list[dict[str, Any]] = []

    # Check functions
    for name, line in defined.items():
        if name in ignore_names:
            continue
        if name.startswith("__") and name.endswith("__"):
            continue  # Python dunders
        if name not in called:
            # Export-aware: exported + uncalled → unused_export
            if name in exported:
                findings.append(
                    _make_measurement(
                        "unused_export",
                        name,
                        0,
                        None,
                        {"file": file_path, "line": line},
                        confidence=60,
                    )
                )
            else:
                findings.append(
                    _make_measurement(
                        "dead_function",
                        name,
                        0,
                        None,
                        {"file": file_path, "line": line},
                        confidence=70,
                    )
                )

    # Check non-function exports (variables, classes)
    if "exports" in queries:
        export_lines: dict[str, int] = {}
        for node in _get_captures(queries["exports"], tree.root_node).get("name", []):
            export_lines[_text(data, node)] = node.start_point[0] + 1
        # Names that appear in export declarations themselves shouldn't count as "used"
        used_outside_exports = all_ids - set(export_lines.keys())
        for name in sorted(exported):
            if name not in defined and name not in used_outside_exports:
                line = export_lines.get(name, 1)
                findings.append(
                    _make_measurement(
                        "unused_export",
                        name,
                        0,
                        None,
                        {"file": file_path, "line": line},
                        confidence=60,
                    )
                )

    return findings


# ── Cyclic imports (cross-file) ──────────────────────────────────────────


def _extract_project_imports(
    data: bytes, lang: str, file_path: str, project_files: set[str]
) -> set[str]:
    """Extract local module names imported by this file, resolved to actual file paths."""
    try:
        parser = get_parser(lang)
    except ValueError:
        return set()
    tree = parser.parse(data)
    queries = get_queries(lang)
    resolved: set[str] = set()
    project_root = str(_find_project_root(file_path))

    for node in _get_captures(queries["imports"], tree.root_node).get("name", []):
        import_text = _text(data, node)
        import_text = import_text.strip("\"'")

        is_from = "." in import_text and not import_text.startswith(".")
        resolved_path = _resolve_as_project_import(
            import_text, file_path, project_root, is_from, project_files, lang
        )
        if resolved_path:
            resolved.add(resolved_path)

    return resolved


def _resolve_as_project_import(
    import_text: str,
    from_file: str,
    project_root: str,
    is_from: bool,
    project_files: set[str],
    lang: str,
) -> str | None:
    """Try to resolve an import to a project file path."""
    if lang == "python":
        from prism.enrich.resolver import resolve_python_import

        resolved = resolve_python_import(import_text, from_file, project_root, is_from)
        if resolved and resolved in project_files:
            return resolved
        # Fallback: try dotted path as filesystem path
        parts = import_text.split(".")
        for i in range(len(parts), 0, -1):
            candidate = str(Path(project_root).joinpath(*parts[:i]).with_suffix(".py"))
            if candidate in project_files:
                return candidate
            init_candidate = str(Path(project_root).joinpath(*parts[:i], "__init__.py"))
            if init_candidate in project_files:
                return init_candidate
    else:
        path_str = import_text.replace("/", ".").replace("\\", ".")
        parts = path_str.split(".")
        for f in project_files:
            f_stem = Path(f).stem
            if parts[0] == f_stem:
                return f
    return None


def _find_project_root(file_path: str) -> Path:
    """Find the project root by looking for .git or common markers."""
    p = Path(file_path).resolve()
    for parent in [p] + list(p.parents):
        if (parent / ".git").exists():
            return parent
        if (parent / "pyproject.toml").exists():
            return parent
        if (parent / "requirements.txt").exists():
            return parent
    return p.parent


def measure_cyclic_imports(files: list[str], base_dir: str) -> list[dict[str, Any]]:
    """Detect cyclic import chains across files in the given list."""
    import_graph: dict[str, set[str]] = {}
    file_paths: dict[str, str] = {}
    project_files_set = {str(Path(f).resolve()) for f in files}

    for fpath in files:
        p = Path(fpath)
        try:
            data = p.read_bytes()
        except Exception:
            continue
        module_key = str(p.resolve())
        file_paths[module_key] = str(p)
        lang = extension_to_language(p.suffix.lower()) or "python"
        imports = _extract_project_imports(data, lang, str(p), project_files_set)
        import_graph[module_key] = imports

    cycles = _find_cycles(import_graph)

    findings: list[dict[str, Any]] = []
    for cycle in cycles:
        cycle_path = []
        for node in cycle:
            try:
                rel = Path(node).relative_to(Path.cwd())
                cycle_path.append(str(rel))
            except ValueError:
                cycle_path.append(Path(node).stem)

        for node in cycle:
            if node not in file_paths:
                continue
            findings.append(
                _make_measurement(
                    "cyclic_import",
                    Path(node).stem,
                    len(cycle),
                    1,
                    {"file": file_paths[node], "line": 1},
                    cycle=cycle_path,
                    detail=f"{' → '.join(cycle_path)} ({len(cycle)} modules)",
                )
            )
    return findings


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """Simple cycle detection. Returns all elementary cycles."""
    cycles: list[list[str]] = []
    visited: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> None:
        if node in path:
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            if not any(set(cycle) == set(c) for c in cycles):
                cycles.append(cycle)
            return
        if node in visited:
            return
        visited.add(node)
        path.append(node)
        for neighbor in graph.get(node, set()):
            if neighbor in graph:
                dfs(neighbor)
        path.pop()

    for node in graph:
        dfs(node)

    return cycles


# ── Cyclomatic complexity ────────────────────────────────────────────────


def measure_cyclomatic_complexity(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Count decision points per function.

    Each if, for, while, except, and boolean operator (and/or) adds 1
    to the complexity score. Base complexity is 1 (function entry).
    Threshold: >10 is complex, >20 is high risk.
    """
    queries = get_queries(lang)
    thresholds = get_thresholds(lang)
    max_complexity = thresholds.get("cyclomatic_complexity", 10)
    decision_types = set(LANGUAGES.get(lang, {}).get("decision_types", []))

    if not decision_types:
        return []  # Language doesn't support this metric

    findings: list[dict[str, Any]] = []

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]

        if not func_name or not func_node:
            continue

        # Walk the function body and count decision points
        complexity = 1  # Base: function entry point
        counter: list[int] = [0]
        _walk_and_count(func_node, decision_types, counter)
        complexity += counter[0]
        line = func_node.start_point[0] + 1

        if complexity > max_complexity:
            findings.append(
                _make_measurement(
                    "cyclomatic_complexity",
                    func_name,
                    complexity,
                    max_complexity,
                    {"file": file_path, "line": line},
                )
            )

    return findings


def _walk_and_count(node: Any, decision_types: set[str], counter: list[int]) -> None:
    """Walk the AST subtree, counting decision points."""
    if node.type in decision_types:
        counter[0] += 1
    for child in node.children:
        _walk_and_count(child, decision_types, counter)


# ── Cognitive complexity ─────────────────────────────────────────────────


def measure_cognitive_complexity(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """SonarSource cognitive complexity — nesting-weighted cyclomatic.

    Each decision point adds 1 base + 2 per nesting level.
    `if` inside `if` inside `if` = 1 + (1+2) + (1+4) = 9.
    Threshold: >15 is hard to understand.
    """
    queries = get_queries(lang)
    decision_types = set(LANGUAGES.get(lang, {}).get("decision_types", []))

    if not decision_types:
        return []

    findings: list[dict[str, Any]] = []

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]

        if not func_name or not func_node:
            continue

        score = _compute_cognitive(func_node, decision_types, 0)
        line = func_node.start_point[0] + 1

        if score > 15:
            findings.append(
                _make_measurement(
                    "cognitive_complexity", func_name, score, 15, {"file": file_path, "line": line}
                )
            )

    return findings


def _compute_cognitive(node: Any, decision_types: set[str], depth: int) -> int:
    """Compute cognitive complexity for a subtree. Recursive with depth tracking.

    Each decision point at depth N adds 1 + 2*N to the score.
    """
    score = 0
    if node.type in decision_types:
        score += 1 + (2 * depth)
        depth += 1  # Increase nesting for children

    for child in node.children:
        score += _compute_cognitive(child, decision_types, depth)
    return score


# ── Module coupling (afferent/efferent) ──────────────────────────────────


def measure_module_coupling(files: list[str]) -> list[dict[str, Any]]:
    """Compute afferent (Ca) and efferent (Ce) coupling for each module.

    Ca: how many modules import this one (incoming dependencies).
    Ce: how many project modules this one imports (outgoing dependencies).
    Instability: Ce / (Ca + Ce). 0 = perfectly stable, 1 = perfectly unstable.

    Reports modules with instability > 0.8 (too unstable — fragile)
    or < 0.2 and Ce > 0 (too stable — possibly dead weight).
    """
    imports_from: dict[str, set[str]] = {}
    module_paths: dict[str, str] = {}
    project_files_set = {str(Path(f).resolve()) for f in files}

    for fpath in files:
        p = Path(fpath)
        try:
            data = p.read_bytes()
        except Exception:
            continue
        module_key = str(p.resolve())
        module_paths[module_key] = str(fpath)

        ext = p.suffix.lower()
        lang = extension_to_language(ext)
        if not lang:
            continue

        imported = _extract_project_imports(data, lang, str(p), project_files_set)
        imports_from[module_key] = {m for m in imported if m != module_key}

    # Compute Ca (incoming) for each module
    ca: dict[str, int] = {}
    for module, deps in imports_from.items():
        for dep in deps:
            ca[dep] = ca.get(dep, 0) + 1

    # Compute Ce (outgoing) for each module
    ce: dict[str, int] = {m: len(deps) for m, deps in imports_from.items()}

    findings: list[dict[str, Any]] = []
    for module, path in module_paths.items():
        incoming = ca.get(module, 0)
        outgoing = ce.get(module, 0)
        total = incoming + outgoing
        instability = outgoing / total if total > 0 else 0.0

        if instability > 0.8 and outgoing > 3:
            findings.append(
                _make_measurement(
                    "module_instability",
                    module,
                    round(instability, 2),
                    0.8,
                    {"file": path, "line": 1},
                    detail=f"Ce={outgoing}, Ca={incoming}, too many outgoing dependencies",
                )
            )
        elif instability < 0.2 and outgoing == 0 and incoming > 5:
            findings.append(
                _make_measurement(
                    "module_instability",
                    module,
                    round(instability, 2),
                    0.8,
                    {"file": path, "line": 1},
                    detail=(
                        f"Ce={outgoing}, Ca={incoming}"
                        " — no outgoing deps, possibly dead abstraction"
                    ),
                )
            )

    return findings


# ── Structural diff (git-aware) ──────────────────────────────────────────


# ── Structural diff helpers ──────────────────────────────────────────────


def _fetch_git_head(file_path: str) -> bytes | None:
    """Get the git HEAD version of a file, or None if unavailable."""
    import subprocess

    try:
        rel_path = Path(file_path).resolve()
        git_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=rel_path.parent,
        ).stdout.strip()
        if not git_root:
            return None
        rel = rel_path.relative_to(Path(git_root))
        head_result = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=rel_path.parent,
        )
        if head_result.returncode != 0:
            return None
        return head_result.stdout.encode("utf-8")
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        return None


def _parse_func_defs(tree: Tree, data: bytes, lang: str) -> dict[str, tuple[int, int, int]]:
    """Extract function names -> (line, param_count, estimated_cc)."""
    queries = get_queries(lang)
    funcs: dict[str, tuple[int, int, int]] = {}

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        params_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]
            elif name == "params" and nodes:
                params_node = nodes[0]
        if func_name and func_node:
            pc = _count_parameters(params_node, data, lang) if params_node else 0
            cc = _estimate_cc(func_node)
            funcs[func_name] = (func_node.start_point[0] + 1, pc, cc)

    return funcs


def _compute_diff_changes(
    current: dict[str, tuple[int, int, int]],
    head: dict[str, tuple[int, int, int]],
    file_path: str,
) -> list[dict[str, Any]]:
    """Compare two function sets and produce diff measurements."""
    findings: list[dict[str, Any]] = []

    for name, (line, pc, cc) in current.items():
        if name not in head:
            findings.append(
                _make_measurement(
                    "diff_function_added",
                    name,
                    0,
                    None,
                    {"file": file_path, "line": line},
                    detail=f"params={pc}, complexity={cc}",
                )
            )

    for name, (line, pc, cc) in head.items():
        if name not in current:
            findings.append(
                _make_measurement(
                    "diff_function_removed",
                    name,
                    0,
                    None,
                    {"file": file_path, "line": line},
                    detail=f"params={pc}, complexity={cc}",
                )
            )

    for name in set(current) & set(head):
        cur_line, cur_pc, cur_cc = current[name]
        _, head_pc, head_cc = head[name]
        changes = []
        if cur_pc != head_pc:
            changes.append(f"params:{head_pc}->{cur_pc}")
        if cur_cc != head_cc and abs(cur_cc - head_cc) > 2:
            changes.append(f"complexity:{head_cc}->{cur_cc}")
        if changes:
            findings.append(
                _make_measurement(
                    "diff_function_changed",
                    name,
                    0,
                    None,
                    {"file": file_path, "line": cur_line},
                    detail=", ".join(changes),
                )
            )

    return findings


def structural_diff(file_path: str) -> list[dict[str, Any]]:
    """Compare current file against git HEAD for added / removed / changed functions."""
    head_code = _fetch_git_head(file_path)
    if head_code is None:
        return []

    try:
        current_tree, current_data, lang = parse_file(file_path)
    except ValueError:
        return []

    try:
        parser = _get_parser_for_file(file_path)[0]
        head_tree = parser.parse(head_code)
    except Exception:
        return []

    current_funcs = _parse_func_defs(current_tree, current_data, lang)
    head_funcs = _parse_func_defs(head_tree, head_code, lang)

    return _compute_diff_changes(current_funcs, head_funcs, file_path)


def _fetch_git_version_at_commit(file_path: str, commit: str) -> bytes | None:
    """Get the content of a file at a specific git commit."""
    import subprocess

    try:
        rel_path = Path(file_path).resolve()
        git_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=rel_path.parent,
        ).stdout.strip()
        if not git_root:
            return None
        rel = rel_path.relative_to(Path(git_root).resolve())
        result = subprocess.run(
            ["git", "show", f"{commit}:{rel}"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=Path(git_root).resolve(),
        )
        if result.returncode != 0:
            return None
        return result.stdout.encode("utf-8")
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        return None


def measure_churn_hotspots(
    file_path: str,
    num_commits: int = 10,
    hotspot_threshold: float = 2.0,
) -> list[dict[str, Any]]:
    """Find functions that changed frequently AND have high complexity.

    Analyzes the last N git commits, tracks which functions changed in each
    commit, and computes hotspot = churn_rate * cyclomatic_complexity.

    High hotspot scores indicate functions that are both complex AND
    frequently modified — the highest-value refactoring targets.
    """
    import subprocess

    try:
        rel_path = Path(file_path).resolve()
        git_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=rel_path.parent,
        ).stdout.strip()
        if not git_root:
            return []
        rel = rel_path.relative_to(Path(git_root).resolve())

        # Get the last N commit hashes
        log_result = subprocess.run(
            ["git", "log", "--oneline", f"-{num_commits}", "--", str(rel)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=Path(git_root).resolve(),
        )
        if log_result.returncode != 0 or not log_result.stdout.strip():
            return []

        commits = [line.split()[0] for line in log_result.stdout.strip().split("\n")]
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        return []

    if not commits:
        return []

    # Get the current version to parse function defs and compute CC
    try:
        current_tree, current_data, lang = parse_file(file_path)
    except ValueError:
        return []
    current_funcs = _parse_func_defs(current_tree, current_data, lang)

    # Track which functions changed in each commit
    churn_counts: dict[str, int] = {}  # func_name -> number of commits it changed in

    # Use current version as the "previous" state for the first comparison
    # We iterate from oldest to newest to track changes
    prev_funcs = current_funcs

    for commit in commits:
        # Get the file at this commit
        try:
            parser = _get_parser_for_file(file_path)[0]
        except ValueError:
            continue

        code = _fetch_git_version_at_commit(file_path, commit)
        if code is None:
            continue

        try:
            commit_tree = parser.parse(code)
        except Exception:
            continue

        commit_funcs = _parse_func_defs(commit_tree, code, lang)

        # Find functions that differ between this commit and the "previous" state
        # (added, removed, or changed)
        all_names = set(commit_funcs) | set(prev_funcs)
        for name in all_names:
            if name in commit_funcs and name not in prev_funcs:
                churn_counts[name] = churn_counts.get(name, 0) + 1
            elif name not in commit_funcs and name in prev_funcs:
                churn_counts[name] = churn_counts.get(name, 0) + 1
            elif name in commit_funcs and name in prev_funcs:
                if commit_funcs[name] != prev_funcs[name]:
                    churn_counts[name] = churn_counts.get(name, 0) + 1

        prev_funcs = commit_funcs

    total_commits = len(commits)
    findings: list[dict[str, Any]] = []

    for func_name, (line, pc, cc) in current_funcs.items():
        churn_count = churn_counts.get(func_name, 0)
        if churn_count == 0:
            continue
        churn_rate = churn_count / total_commits
        hotspot = churn_rate * cc

        if hotspot > hotspot_threshold:
            findings.append(
                _make_measurement(
                    "churn_hotspot",
                    func_name,
                    round(hotspot, 2),
                    hotspot_threshold,
                    {"file": file_path, "line": line},
                    detail=(
                        f"churn={churn_count}/{total_commits}"
                        f" ({round(churn_rate * 100)}%), CC={cc}, hotspot={round(hotspot, 2)}"
                    ),
                )
            )

    return findings


def _estimate_cc(func_node: Any) -> int:
    """Quick cyclomatic complexity estimate for diff comparison."""
    decision_types = {
        "if_statement",
        "elif_clause",
        "for_statement",
        "while_statement",
        "except_clause",
        "boolean_operator",
    }
    counter = [0]
    _walk_and_count(func_node, decision_types, counter)
    return 1 + counter[0]


# ── Boolean expression complexity ────────────────────────────────────────


def measure_boolean_complexity(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Count conditions inside single if statements.

    An expression like `if a and b or c:` has 3 conditions.
    Threshold: >3 conditions in a single branch is hard to read.
    """
    queries = get_queries(lang)
    bool_ops = set(LANGUAGES.get(lang, {}).get("boolean_operator_types", []))

    if not bool_ops:
        return []

    findings: list[dict[str, Any]] = []
    # Find all if statements (or equivalents) in each function
    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]
        if not func_name or not func_node:
            continue

        # Walk the function looking for if_statement conditions
        _walk_if_conditions(func_node, bool_ops, func_name, data, findings, file_path)

    return findings


def _walk_if_conditions(
    node: Any,
    bool_ops: set[str],
    func_name: str,
    data: bytes,
    findings: list[dict[str, Any]],
    file_path: str,
) -> None:
    """Walk the AST looking for if statements and counting their condition complexity."""
    # Python: condition is the first child of if_statement (before `:`)
    # JS/Go/Rust: condition is the child named `condition`
    if node.type in ("if_statement", "if_expression", "conditional_expression"):
        # Find the condition subtree
        condition = None
        for child in node.children:
            if child.type in ("condition",) or child.is_named and condition is None:
                if condition is None and child.type != ":":
                    condition = child
                    break

        if condition:
            count = _count_bool_ops(condition, bool_ops)
            if count > 3:  # threshold for reporting
                line = condition.start_point[0] + 1
                condition_text = _text(data, condition)[:60]
                findings.append(
                    _make_measurement(
                        "boolean_complexity",
                        func_name,
                        count,
                        3,
                        {"file": file_path, "line": line},
                        detail=condition_text,
                    )
                )

    for child in node.children:
        _walk_if_conditions(child, bool_ops, func_name, data, findings, file_path)


def _count_bool_ops(node: Any, bool_ops: set[str]) -> int:
    """Count the number of boolean operators in a condition subtree."""
    count = 0
    # In Python, boolean_operator nodes have the operator as a child (text: "and" or "or")
    # In other languages, binary_expression nodes have an operator field
    if node.type in bool_ops:
        count += 1
    elif node.type == "boolean_operator":
        # A boolean_operator node itself counts as a decision branch point
        count += 1

    for child in node.children:
        count += _count_bool_ops(child, bool_ops)
    return count


# ── God class detection ──────────────────────────────────────────────────


def measure_god_class(tree: Tree, data: bytes, file_path: str, lang: str) -> list[dict[str, Any]]:
    """Detect classes with too many methods, dependencies, or lines.

    A god class has too many responsibilities. Measured by:
    - Method count (>10)
    - Lines of code (>100)
    - Number of dependencies injected via __init__ (>6)
    """
    queries = get_queries(lang)
    thresholds = get_thresholds(lang)
    max_methods = thresholds.get("god_class_methods", 10)
    max_deps = thresholds.get("god_class_deps", 6)
    max_lines = thresholds.get("god_class_lines", 100)

    # Check if the language has a class query
    if "classes" not in queries:
        return []

    findings: list[dict[str, Any]] = []

    for _pat_idx, captures in _get_matches(queries["classes"], tree.root_node):
        class_name = ""
        body_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                class_name = _text(data, nodes[0])
            elif name == "class" and nodes:
                body_node = nodes[0]

        if not class_name or not body_node:
            continue

        # Count methods
        method_count = _count_children_by_type(
            body_node, "function_definition", "method_definition"
        )

        # Count lines
        total_lines = body_node.end_point[0] - body_node.start_point[0] + 1

        # Count dependencies (parameters in __init__ that look like services)
        dep_count = _count_init_deps(body_node, data)

        issues = []
        if method_count > max_methods:
            issues.append(f"methods:{method_count}")
        if total_lines > max_lines:
            issues.append(f"lines:{total_lines}")
        if dep_count > max_deps:
            issues.append(f"deps:{dep_count}")

        if issues:
            line = body_node.start_point[0] + 1
            findings.append(
                _make_measurement(
                    "god_class",
                    class_name,
                    method_count,
                    max_methods,
                    {"file": file_path, "line": line},
                    detail=", ".join(issues),
                    total_lines=total_lines,
                    dependency_count=dep_count,
                )
            )

    return findings


def _count_children_by_type(node: Any, *types: str) -> int:
    """Count direct children matching any of the given types."""
    count = 0
    for child in node.children:
        if child.type in types:
            count += 1
        # Also search deeper for nested function definitions
        count += _count_children_by_type(child, *types)
    return count


def _find_init_method(body_node: Any, data: bytes) -> Any | None:
    """Find the __init__ method definition in a class body."""
    for child in body_node.children:
        if child.type != "function_definition":
            continue
        first_line = _text(data, child).split("\n")[0]
        if "__init__" in first_line:
            return child
    return None


def _find_params_node(func_node: Any) -> Any | None:
    """Find the parameters node in a function definition."""
    for child in func_node.children:
        if child.type == "parameters":
            return child
    return None


def _count_service_params(params_node: Any, data: bytes) -> int:
    """Count non-self, non-private params that look like service dependencies."""
    count = 0
    for p in params_node.children:
        if p.type not in ("identifier", "typed_parameter", "default_parameter"):
            continue
        text = _text(data, p)
        if text not in ("self", "cls") and not text.startswith("_"):
            count += 1
    return count


def _count_init_deps(body_node: Any, data: bytes) -> int:
    """Count dependencies in __init__ parameters that look like services."""
    init_method = _find_init_method(body_node, data)
    if init_method is None:
        return 0
    params_node = _find_params_node(init_method)
    if params_node is None:
        return 0
    return _count_service_params(params_node, data)


# ── Error handling coverage ──────────────────────────────────────────────

# AST node types that represent function/method calls (language-agnostic)
_RISKY_NODE_TYPES: set[str] = {
    "call",
    "call_expression",
    "method_invocation",
}


def measure_error_handling(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """For each function, report the ratio of risky calls that are try-guarded.

    A risky call (file I/O, network, parsing, eval, subprocess) is counted as
    handled if it has a try/except ancestor in the AST. Low coverage (<80%)
    means the function may fail silently at runtime.
    """
    queries = get_queries(lang)
    findings: list[dict[str, Any]] = []

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]
        if not func_name or not func_node:
            continue

        # Count total risky calls and handled ones
        total = 0
        handled = 0

        risky_targets = get_risky_call_targets(lang)
        for child in func_node.children:
            t, h = _count_risky_calls(child, data, risky_targets)
            total += t
            handled += h

        if total == 0:
            continue

        coverage = handled / total
        if coverage < 0.8:
            line = func_node.start_point[0] + 1
            unguarded = total - handled
            findings.append(
                _make_measurement(
                    "error_handling_coverage",
                    func_name,
                    round(coverage, 2),
                    0.8,
                    {"file": file_path, "line": line},
                    detail=f"{unguarded} of {total} risky calls unguarded",
                )
            )

    return findings


def _count_risky_calls(node: Any, data: bytes, risky_targets: list[str]) -> tuple[int, int]:
    """Count (total_risky_calls, handled_risky_calls) in a subtree.

    A call is risky if its target name matches known risky operations.
    A call is handled if it has a try/except or try/catch ancestor.
    """
    total = 0
    handled = 0

    if node.type in ("try_statement", "try_block", "try"):
        # Everything inside try is considered handled
        for child in node.children:
            t, h = _count_risky_in_try(child, data, risky_targets)
            total += t
            handled += t  # All calls inside try are counted as handled
    elif node.type in _RISKY_NODE_TYPES:
        # Check if this call targets a risky function
        call_text = _text(data, node)
        is_risky = any(rf in call_text for rf in risky_targets)
        if is_risky:
            total += 1
            # Check parent chain for try/except
            parent = node.parent
            while parent:
                if parent.type in (
                    "try_statement",
                    "try_block",
                    "try",
                    "except_clause",
                    "except_block",
                    "catch",
                ):
                    handled += 1
                    break
                parent = parent.parent
        else:
            # Recurse into call arguments to find nested risky calls
            for child in node.children:
                t, h = _count_risky_calls(child, data, risky_targets)
                total += t
                handled += h
    else:
        for child in node.children:
            t, h = _count_risky_calls(child, data, risky_targets)
            total += t
            handled += h

    return total, handled


def _count_risky_in_try(node: Any, data: bytes, risky_targets: list[str]) -> tuple[int, int]:
    """Count risky calls inside a try block — all counted as handled."""
    total = 0
    if node.type in _RISKY_NODE_TYPES:
        call_text = _text(data, node)
        if any(rf in call_text for rf in risky_targets):
            total += 1
    for child in node.children:
        t, _ = _count_risky_in_try(child, data, risky_targets)
        total += t
    return total, 0  # handled counted by caller


# ── Public/private ratio ────────────────────────────────────────────────


def measure_visibility_ratio(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Report the ratio of public to private top-level functions.

    A function is private if its name starts with `_` (Python convention)
    or is not exported (JS/TS convention: no `export` keyword).
    A module with 100% public functions has no encapsulation.
    """
    queries = get_queries(lang)
    findings: list[dict[str, Any]] = []

    public = 0
    private = 0

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
        if not func_name:
            continue
        if func_name.startswith("_"):
            private += 1
        else:
            public += 1

    total = public + private
    if total == 0:
        return []

    public_ratio = public / total
    if public_ratio > 0.9 and private > 0:
        findings.append(
            _make_measurement(
                "public_ratio",
                Path(file_path).stem,
                round(public_ratio, 2),
                0.9,
                {"file": file_path, "line": 1},
                detail=f"{public} public, {private} private — no encapsulation",
            )
        )

    return findings


# ── NLOC (source lines of code) ──────────────────────────────────────────


def measure_nloc(tree: Tree, data: bytes, file_path: str, lang: str) -> list[dict[str, Any]]:
    """Count non-blank, non-comment, non-import source lines of code.

    Returns a single measurement with the total NLOC for the file.
    Uses tree-sitter to identify comment and import nodes for accurate
    counting across languages.
    """
    queries = get_queries(lang)

    # Collect line ranges of comments
    comment_lines: set[int] = set()
    _collect_comment_lines(tree.root_node, data, comment_lines)

    # Collect line ranges of imports
    import_lines: set[int] = set()
    for node in _get_captures(queries["imports"], tree.root_node).get("name", []):
        import_lines.add(node.start_point[0])

    lines = data.decode("utf-8").split("\n")
    nloc = 0
    for i, line in enumerate(lines):
        if i in comment_lines or i in import_lines:
            continue
        stripped = line.strip()
        if stripped and not stripped.startswith(("#", "//", "/*", "*", "--")):
            nloc += 1

    return [
        _make_measurement(
            "nloc",
            Path(file_path).stem,
            nloc,
            None,
            {"file": file_path, "line": 1},
        )
    ]


def _collect_comment_lines(node: Any, data: bytes, comment_lines: set[int]) -> None:
    """Walk AST and collect line numbers of all comment nodes."""
    if node.type == "comment":
        for line_no in range(node.start_point[0], node.end_point[0] + 1):
            comment_lines.add(line_no)
    for child in node.children:
        _collect_comment_lines(child, data, comment_lines)


# ── Maintainability Index ───────────────────────────────────────────────


def measure_maintainability_index(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Compute Maintainability Index per function.

    MI = max(0, 100 - (CC * 3 + nesting_depth * 5 + param_count * 2 + func_length / 10))

    Threshold: < 40 = "needs attention", < 20 = "hard to maintain"
    Uses existing decision_types and thresholds from the language registry.
    """
    queries = get_queries(lang)
    decision_types = set(LANGUAGES.get(lang, {}).get("decision_types", []))
    findings: list[dict[str, Any]] = []

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        params_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]
            elif name == "params" and nodes:
                params_node = nodes[0]

        if not func_name or not func_node:
            continue

        # Compute cyclomatic complexity
        cc = 1
        counter: list[int] = [0]
        _walk_and_count(func_node, decision_types, counter)
        cc += counter[0]

        # Compute nesting depth (AST-based)
        nesting = _compute_ast_nesting(func_node, decision_types, 0)

        # Count parameters
        param_count = _count_parameters(params_node, data, lang) if params_node else 0

        # Compute function length
        func_length = func_node.end_point[0] - func_node.start_point[0] + 1

        # Maintainability Index (simplified, no Halstead)
        mi = 100 - (cc * 3 + nesting * 5 + param_count * 2 + func_length / 10)
        mi = max(0, round(mi, 1))

        line = func_node.start_point[0] + 1
        if mi < 40:
            findings.append(
                _make_measurement(
                    "maintainability_index",
                    func_name,
                    mi,
                    40,
                    {"file": file_path, "line": line},
                    detail=f"CC={cc}, nest={nesting}, params={param_count}, len={func_length}",
                )
            )

    return findings


# ── Import depth ─────────────────────────────────────────────────────────


def measure_import_depth(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Report imports that are unreasonably deep.

    `from foo.bar.baz.qux import thing` — depth 4.
    Deep imports suggests tight coupling to internal package structure.
    Threshold: depth > 3.
    """
    queries = get_queries(lang)
    findings: list[dict[str, Any]] = []

    for node in _get_captures(queries["imports"], tree.root_node).get("name", []):
        import_text = _text(data, node).strip("\"'")
        depth = import_text.count(".") + 1
        if depth > 3:
            line = node.start_point[0] + 1
            findings.append(
                _make_measurement(
                    "import_depth",
                    import_text,
                    depth,
                    3,
                    {"file": file_path, "line": line},
                )
            )

    return findings


# ── Code clone detection ────────────────────────────────────────────────


def measure_code_clones(tree: Tree, data: bytes, file_path: str, lang: str) -> list[dict[str, Any]]:
    """Detect structurally similar functions (code clones).

    Builds a structural signature for each function body by recording the
    sequence of non-identifier, non-literal AST node types (limited to 4
    levels deep). Pairwise comparison uses n-gram Jaccard similarity for
    O(m+n) per pair instead of O(m*n) LCS.

    Threshold: >0.8 structural similarity without being identical functions.
    """
    queries = get_queries(lang)
    findings: list[dict[str, Any]] = []

    # Build structural signatures for each function
    funcs: dict[str, list[str]] = {}
    func_lines: dict[str, int] = {}

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]
        if func_name and func_node:
            sig = _build_structural_signature(func_node, max_depth=4)
            if len(sig) >= 10:
                funcs[func_name] = sig
                func_lines[func_name] = func_node.start_point[0] + 1

    # Compare all pairs with length prefilter
    names = list(funcs.keys())
    for i in range(len(names)):
        sig_a = funcs[names[i]]
        len_a = len(sig_a)
        for j in range(i + 1, len(names)):
            sig_b = funcs[names[j]]
            len_b = len(sig_b)
            # Quick length check: if lengths differ by >25%, similarity can't exceed 0.8
            if len_a < len_b:
                if len_a / len_b < 0.75:
                    continue
            else:
                if len_b / len_a < 0.75:
                    continue
            similarity = _signature_similarity(sig_a, sig_b)
            if similarity > 0.8:
                findings.append(
                    _make_measurement(
                        "code_clone",
                        names[i],
                        round(similarity, 2),
                        0.8,
                        {"file": file_path, "line": func_lines[names[i]]},
                        detail=f"similar to {names[j]} ({round(similarity * 100)}%)",
                    )
                )

    return findings


def measure_code_clones_project(
    files: list[str], similarity_threshold: float = 0.8, min_tokens: int = 10
) -> list[dict[str, Any]]:
    """Detect structurally similar functions across all project files.

    Builds structural signatures for every function in every file, then
    compares all pairs across files (skipping same-file and cross-language).
    """
    all_funcs: list[tuple[str, str, str, int, list[str]]] = []

    for fpath in files:
        ext = Path(fpath).suffix.lower()
        lang = extension_to_language(ext)
        if not lang:
            continue
        try:
            data = Path(fpath).read_bytes()
            parser = get_parser(lang)
            tree = parser.parse(data)
        except Exception:
            continue

        queries = get_queries(lang)
        for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
            func_name = ""
            func_node = None
            for name, nodes in captures.items():
                if name == "name" and nodes:
                    func_name = _text(data, nodes[0])
                elif name == "func" and nodes:
                    func_node = nodes[0]
            if func_name and func_node:
                sig = _build_structural_signature(func_node, max_depth=4)
                if len(sig) >= min_tokens:
                    all_funcs.append((fpath, lang, func_name, func_node.start_point[0] + 1, sig))

    findings: list[dict[str, Any]] = []
    for i in range(len(all_funcs)):
        file_a, lang_a, name_a, line_a, sig_a = all_funcs[i]
        len_a = len(sig_a)
        for j in range(i + 1, len(all_funcs)):
            file_b, lang_b, name_b, line_b, sig_b = all_funcs[j]
            if lang_a != lang_b:
                continue
            if file_a == file_b:
                continue
            len_b = len(sig_b)
            if len_a < len_b:
                if len_a / len_b < 0.75:
                    continue
            else:
                if len_b / len_a < 0.75:
                    continue
            similarity = _signature_similarity(sig_a, sig_b)
            if similarity > similarity_threshold:
                findings.append(
                    _make_measurement(
                        "code_clone",
                        name_a,
                        round(similarity, 2),
                        similarity_threshold,
                        {"file": file_a, "line": line_a},
                        detail=(
                            f"similar to {name_b} in {Path(file_b).name}"
                            f" ({round(similarity * 100)}%)"
                        ),
                    )
                )

    return findings


def _build_structural_signature(node: Any, max_depth: int = 6) -> list[str]:
    """Walk a function body and record the sequence of meaningful node types.

    Limits depth to `max_depth` to keep signatures short. Skips identifiers
    and literals to focus on structure (if, for, while, call, etc.).
    """
    _SKIP_TYPES = {
        "identifier",
        "string",
        "number",
        "comment",
        "integer",
        "float",
        "true",
        "false",
        "null",
        "None",
        ":",
        ".",
        ",",
        ";",
    }
    sig: list[str] = []

    def walk(n: Any, depth: int) -> None:
        if depth > max_depth:
            return
        if n.type not in _SKIP_TYPES:
            sig.append(n.type)
        for child in n.children:
            walk(child, depth + 1)

    walk(node, 0)
    return sig


def _signature_similarity(a: list[str], b: list[str]) -> float:
    """Compute overlap coefficient using LCS ratio.

    Signatures are short (depth-limited to 4 levels), so LCS is fast enough
    and more accurate than n-gram Jaccard for structural comparison.
    """
    if not a or not b:
        return 0.0
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        ai = a[i - 1]
        dp_i = dp[i]
        dp_im1 = dp[i - 1]
        for j in range(1, n + 1):
            if ai == b[j - 1]:
                dp_i[j] = dp_im1[j - 1] + 1
            else:
                dp_i[j] = dp_im1[j] if dp_im1[j] > dp_i[j - 1] else dp_i[j - 1]
    lcs = dp[m][n]
    return lcs / max(m, n)


# ── Function purity ──────────────────────────────────────────────────────


def measure_function_purity(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Detect impure functions — those with side effects.

    A function is impure if it:
    - Assigns to module-level variables
    - Modifies its parameters
    - Calls known-impure functions (I/O, random, time, etc.)

    Pure functions are easier to test, cache, and reason about.
    """
    queries = get_queries(lang)

    # Module-level variable names (assigned at top level)
    module_vars = _find_module_vars(tree, data)

    # Per-language known-impure function targets
    impure_targets = get_impure_call_targets(lang)

    findings: list[dict[str, Any]] = []

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]
        if not func_name or not func_node:
            continue

        issues: list[str] = []
        impure = _check_purity(func_node, data, module_vars, set(), impure_targets)

        if impure.get("global_assign"):
            issues.append(f"modifies {len(impure['global_assign'])} module variable(s)")
        if impure.get("param_mutation"):
            issues.append(f"mutates parameter(s): {', '.join(impure['param_mutation'][:3])}")
        if impure.get("impure_calls"):
            issues.append(f"calls impure: {', '.join(impure['impure_calls'][:3])}")

        if issues:
            line = func_node.start_point[0] + 1
            findings.append(
                _make_measurement(
                    "function_impurity",
                    func_name,
                    len(issues),
                    1,
                    {"file": file_path, "line": line},
                    detail="; ".join(issues),
                )
            )

    return findings


def _find_module_vars(tree: Tree, data: bytes) -> set[str]:
    """Find variable names assigned at module level (top of file)."""
    vars_set: set[str] = set()
    root = tree.root_node

    for child in root.children:
        if child.type in ("expression_statement", "assignment"):
            for sub in child.children:
                if sub.type == "identifier":
                    vars_set.add(_text(data, sub))
        elif child.type == "decorated_definition":
            for sub in child.children:
                if sub.type == "identifier":
                    vars_set.add(_text(data, sub))

    return vars_set


def _check_purity(
    node: Any,
    data: bytes,
    module_vars: set[str],
    param_names: set[str],
    impure_targets: list[str] | None = None,
) -> dict:
    """Check a function body for impurity signals.

    Returns dict with keys: global_assign, param_mutation, impure_calls.
    """
    result: dict = {
        "global_assign": [],
        "param_mutation": [],
        "impure_calls": [],
    }

    # Collect parameter names from function definition
    for child in node.children:
        if child.type in ("parameters", "formal_parameters", "parameter_list"):
            for param in child.children:
                if param.type in ("identifier", "typed_parameter", "default_parameter"):
                    for sub in param.children if param.type != "identifier" else [param]:
                        if sub.type == "identifier":
                            param_names.add(_text(data, sub))

    _walk_purity(node, data, module_vars, param_names, result, impure_targets or [])

    # Deduplicate
    for key in result:
        result[key] = list(set(result[key]))

    return result


def _walk_purity(
    node: Any,
    data: bytes,
    module_vars: set[str],
    param_names: set[str],
    result: dict,
    impure_targets: list[str],
) -> None:
    """Walk the AST checking for impurity patterns."""

    # Assignment to module-level var or parameter
    if node.type in ("assignment", "augmented_assignment"):
        for child in node.children:
            if child.type == "identifier":
                name = _text(data, child)
                if name in module_vars:
                    result["global_assign"].append(name)
                if name in param_names:
                    result["param_mutation"].append(name)

    # Call to known-impure function
    if node.type in _RISKY_NODE_TYPES:
        call_text = _text(data, node)
        for impure_target in impure_targets:
            if impure_target in call_text:
                result["impure_calls"].append(impure_target)

    for child in node.children:
        _walk_purity(child, data, module_vars, param_names, result, impure_targets)


# ── Unreachable code detection ──────────────────────────────────────────

# Terminal node type keywords — any node whose type contains one of these
# is a flow-terminating statement. Works across all tree-sitter grammars.
_TERMINAL_KEYWORDS = frozenset(
    {
        "return",
        "break",
        "continue",
        "raise",
        "throw",
        "panic",
    }
)


def measure_unreachable_code(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Find code that follows return/break/continue/raise/throw statements.

    Detects code after a terminal statement within the same block.
    This is code that can never execute — 100% confidence.

    Works generically across all languages by matching node type keywords.
    No per-language configuration needed.
    """
    queries = get_queries(lang)
    findings: list[dict[str, Any]] = []

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]

        if not func_name or not func_node:
            continue

        # Walk the function body looking for terminal statements
        unreachable_lines: list[int] = []
        _find_unreachable(func_node, data, _TERMINAL_KEYWORDS, unreachable_lines)

        if unreachable_lines:
            line = func_node.start_point[0] + 1
            findings.append(
                _make_measurement(
                    "unreachable_code",
                    func_name,
                    len(unreachable_lines),
                    None,
                    {"file": file_path, "line": line},
                    confidence=100,
                    detail=(
                        f"{len(unreachable_lines)} unreachable at lines {unreachable_lines[:5]}"
                    ),
                )
            )

    return findings


def _find_unreachable(
    node: Any,
    data: bytes,
    terminal_keywords: frozenset[str],
    unreachable_lines: list[int],
) -> bool:
    """Walk the AST recursively.

    For each node, check if it's a terminal statement. If it is, check if
    it has a next sibling — if yes, those siblings are unreachable.

    Returns True if this subtree contains a terminal (to propagate upward).
    """
    # Only named nodes can be terminal statements.
    # Anonymous nodes (keywords like 'return', 'break') should be skipped.
    if node.is_named:
        # Check if THIS node is a terminal statement (return, break, etc.)
        is_terminal = any(kw in node.type for kw in terminal_keywords)

        if is_terminal:
            # Check if terminal has a next sibling in the same block
            parent = node.parent
            if parent is not None:
                siblings = [c for c in parent.children]
                idx = siblings.index(node)
                # Everything after this terminal is unreachable
                for sibling in siblings[idx + 1 :]:
                    # Skip comments — they often appear after return on the same line
                    if sibling.is_named and sibling.type != "comment":
                        unreachable_lines.append(sibling.start_point[0] + 1)
                # Don't recurse into children of terminal (they don't execute)
                return True

    # Recurse into children
    child_terminal = False
    for child in node.children:
        if _find_unreachable(child, data, terminal_keywords, unreachable_lines):
            child_terminal = True
            break  # Stop processing siblings after terminal child

    return child_terminal


# ── Unused imports ───────────────────────────────────────────────────────

# Node types that contain import statements — used to exclude identifiers
# inside imports from the "used names" set.
_IMPORT_NODE_TYPES = frozenset(
    {
        "import_statement",
        "import_from_statement",
        "import_declaration",
        "import",
        "use_declaration",
        "preproc_include",
        "namespace_use_clause",
    }
)


def measure_unused_imports(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Find imported names that are never referenced in the file.

    For each import statement, extract the specific names being imported.
    Then check if each name appears anywhere else in the file as an
    identifier reference. If not, it's unused.

    Works across languages by using the existing imports query +
    walking the tree for additional per-language import patterns.
    """
    queries = get_queries(lang)

    # Step 1: Collect imported names from the imports query
    imported_names: set[str] = set()
    import_lines: dict[str, int] = {}

    for node in _get_captures(queries["imports"], tree.root_node).get("name", []):
        name = _text(data, node)
        imported_names.add(name)
        # Track the first line where this name appears
        if name not in import_lines:
            import_lines[name] = node.start_point[0] + 1

    # Step 2: Extract individual names from 'from X import Y' style imports
    # These often capture the module name instead of the specific import names
    _collect_from_import_names(tree.root_node, data, lang, imported_names, import_lines)

    # Remove module names from 'from X import Y' — we only want the
    # specific imported symbols, not the source module.
    _remove_module_names(tree.root_node, data, imported_names, lang)

    if not imported_names:
        return []

    # Step 3: Collect all identifier references in non-import code
    used_names: set[str] = set()
    _collect_identifiers(tree.root_node, data, used_names, imported=False)

    # Step 4: Find unused imports
    findings: list[dict[str, Any]] = []
    for name in sorted(imported_names):
        if name not in used_names:
            line = import_lines.get(name, 1)
            findings.append(
                _make_measurement(
                    "unused_import",
                    name,
                    0,
                    None,
                    {"file": file_path, "line": line},
                    confidence=90,
                )
            )

    return findings


def _collect_from_import_names(
    node: Any,
    data: bytes,
    lang: str,
    imported_names: set[str],
    import_lines: dict[str, int],
) -> None:
    """Walk the AST for 'from X import Y' style imports and extract the
    specific imported names (Y), not just the module name (X).

    Different languages have different AST structures for this:
    - Python: import_from_statement → child dotted_name nodes
    - JS/TS: import_specifier nodes within import_statement
    """
    if node.type == "import_from_statement":
        # Python: from dataclasses import dataclass, field
        # The individual names are dotted_name children of import_from_statement
        for child in node.children:
            if child.type == "dotted_name":
                # Check this is a direct child (imported name), not the module name
                # Module name is typically the first dotted_name child
                name = _text(data, child)
                # Only add names that aren't already tracked (module names)
                if name not in imported_names:
                    imported_names.add(name)
                    if name not in import_lines:
                        import_lines[name] = child.start_point[0] + 1

    elif node.type == "import_specifier":
        # JS/TS: import { foo, bar } from 'module'
        for child in node.children:
            if child.type in ("identifier", "property_identifier"):
                name = _text(data, child)
                imported_names.add(name)
                if name not in import_lines:
                    import_lines[name] = child.start_point[0] + 1

    elif node.type == "import_clause":
        # JS/TS default import: import express from 'module'
        # The default import name is a direct identifier child
        for child in node.children:
            if child.type == "identifier":
                name = _text(data, child)
                # Don't add if it's already tracked (e.g., from specifier)
                if name not in import_lines:
                    imported_names.add(name)
                    import_lines[name] = child.start_point[0] + 1

    # Recurse
    for child in node.children:
        _collect_from_import_names(child, data, lang, imported_names, import_lines)


def _collect_identifiers(
    node: Any,
    data: bytes,
    used_names: set[str],
    imported: bool = False,
    skip_extra: frozenset[str] | None = None,
) -> None:
    """Walk the AST collecting identifier text, skipping import nodes.

    When imported=True, we're inside an import statement and should skip.
    skip_extra: additional node types to skip (e.g., export_statement).
    """
    # Skip import and optionally export subtrees
    if node.type in _IMPORT_NODE_TYPES:
        return
    if skip_extra and node.type in skip_extra:
        return

    # Collect identifiers
    if node.type == "identifier" and node.is_named:
        name = _text(data, node)
        if name:
            used_names.add(name)

    # Recurse into children
    for child in node.children:
        _collect_identifiers(child, data, used_names, imported, skip_extra)


def _remove_module_names(
    node: Any,
    data: bytes,
    imported_names: set[str],
    lang: str = "",
) -> None:
    """Remove module names from 'from X import Y' and 'import { X } from Y'
    style imports. The module path is not an imported symbol — we only
    want the specific symbols being imported.
    """
    if node.type == "import_from_statement":
        # Python: from pathlib import Path
        for child in node.children:
            if child.type == "dotted_name":
                name = _text(data, child)
                imported_names.discard(name)
                break

    elif node.type == "import_statement":
        # JS/TS: import { X } from 'module'
        # Only discard the quoted version of the source string.
        # Don't strip quotes and discard — that would remove legitimate
        # import names like 'express' (added by _collect_from_import_names).
        for child in node.children:
            if child.type == "string":
                name = _text(data, child)
                # Only discard the exact string with quotes
                imported_names.discard(name)
                break

    for child in node.children:
        _remove_module_names(child, data, imported_names, lang)


# ── Unused classes ───────────────────────────────────────────────────────


def measure_unused_classes(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Find classes defined but never referenced within the same file.

    Mirrors the dead_function detection for class definitions.
    A class is unused if its name never appears as an identifier
    reference anywhere in the file outside its own definition.
    """
    queries = get_queries(lang)

    # Check if the language has a classes query
    if "classes" not in queries:
        return []

    # Step 1: Collect defined class names
    defined: dict[str, int] = {}
    for _pat_idx, captures in _get_matches(queries["classes"], tree.root_node):
        class_name = ""
        for name, nodes in captures.items():
            if name == "name" and nodes:
                class_name = _text(data, nodes[0])
        if class_name:
            defined[class_name] = nodes[0].start_point[0] + 1 if nodes else 1

    if not defined:
        return []

    # Step 2: Collect all identifier references from calls and general use
    # Uses the calls query for constructor calls (ClassName()) AND
    # general identifier walk (excluding class definitions themselves).
    called_names: set[str] = set()
    for node in _get_captures(queries["calls"], tree.root_node).get("name", []):
        called_names.add(_text(data, node))

    # Also collect identifiers from the full tree, excluding own-definition names
    all_identifiers: set[str] = set()
    _collect_identifiers(tree.root_node, data, all_identifiers)
    # Remove class definition names from the used set (they always appear
    # in their own definition and we don't want to count that as usage)
    own_names = set(defined.keys())

    # A class is used if it appears in calls OR in general identifiers.
    # The calls query captures constructor calls like Greeter().
    # The identifier walk catches everything else (type annotations, etc.).
    # Only subtract own_names from identifiers, not from calls — a class
    # that's called is definitely used regardless of its own definition.
    used_names = called_names | (all_identifiers - own_names)

    # Step 3: Find unused classes
    findings: list[dict[str, Any]] = []
    for name, line in defined.items():
        if name not in used_names:
            findings.append(
                _make_measurement(
                    "unused_class",
                    name,
                    0,
                    None,
                    {"file": file_path, "line": line},
                    confidence=80,
                )
            )

    return findings


# ── Unused variables (scope-aware) ─────────────────────────────────────


# Node types where the FIRST child is a variable definition (store).
_STORE_PARENT_TYPES = frozenset(
    {
        "assignment",  # Python: x = ... (only first child is store)
        "augmented_assignment",  # Python: x += ... (only first child is store)
        "variable_declarator",  # JS/TS: let x = ... (name child only)
        "for_statement",  # Python: for x in ... (first child only)
        "for_in_statement",  # JS: for (x in ...)
        "for_of_statement",  # JS: for (x of ...)
    }
)

# Identifiers to always skip (builtins and common always-alive names)
_ALIVE_NAMES = frozenset(
    {
        "_",
        "self",
        "cls",
        "this",
        "super",
        "undefined",
        "null",
        "None",
        "True",
        "False",
    }
)


def measure_unused_variables(
    tree: Tree, data: bytes, file_path: str, lang: str
) -> list[dict[str, Any]]:
    """Detect local variables that are assigned but never read.

    For each function scope, check every identifier. Only the FIRST
    child of assignment-like nodes is a "store" (definition).
    All other identifiers in the function are "reads" (references).

    Reports identifiers that are stored but never read elsewhere.
    """
    queries = get_queries(lang)
    findings: list[dict[str, Any]] = []

    for _pat_idx, captures in _get_matches(queries["functions"], tree.root_node):
        func_name = ""
        func_node = None
        for name, nodes in captures.items():
            if name == "name" and nodes:
                func_name = _text(data, nodes[0])
            elif name == "func" and nodes:
                func_node = nodes[0]
        if not func_name or not func_node:
            continue

        defined: set[str] = set()  # identifiers in store position
        seen: set[str] = set()  # identifiers appearing anywhere

        _walk_var_usage(func_node, data, defined, seen)

        # An identifier is "used" if it appears in non-store position
        unused = defined - seen - _ALIVE_NAMES
        unused.discard(func_name)

        if unused:
            for var_name in sorted(unused):
                findings.append(
                    _make_measurement(
                        "unused_variable",
                        func_name,
                        0,
                        None,
                        {"file": file_path, "line": func_node.start_point[0] + 1},
                        confidence=60,
                        detail=f"variable '{var_name}' assigned but never read",
                    )
                )

    return findings


def _walk_var_usage(
    node: Any,
    data: bytes,
    defined: set[str],
    seen: set[str],
) -> None:
    """Walk AST. Track identifier positions.

    An identifier is a DEFINITION (store) if its parent is in
    _STORE_PARENT_TYPES AND it appears at the store index for that type.
    Otherwise it's a REFERENCE (read).
    """
    if node.type == "identifier" and node.is_named:
        name = _text(data, node)
        parent = node.parent
        is_store = False
        if parent is not None and parent.type in _STORE_PARENT_TYPES:
            siblings = list(parent.children)
            try:
                idx = siblings.index(node)
            except ValueError:
                idx = -1
            # Per-type store index:
            if parent.type == "for_statement":
                is_store = idx == 1  # after "for" keyword
            else:
                is_store = idx == 0  # first child for assignment/declarator
        if is_store:
            defined.add(name)
        elif name:
            seen.add(name)

    for child in node.children:
        _walk_var_usage(child, data, defined, seen)


def run(file_path: str, project_files: list[str] | None = None) -> list[dict[str, Any]]:
    """Run all structural measurements on a single file."""
    tree, data, lang = parse_file(file_path)

    findings: list[dict[str, Any]] = []
    findings.extend(measure_parameter_count(tree, data, file_path, lang))
    findings.extend(measure_nesting_depth(tree, data, file_path, lang))
    findings.extend(measure_function_length(tree, data, file_path, lang))
    findings.extend(measure_dead_code(tree, data, file_path, lang))
    findings.extend(measure_cyclomatic_complexity(tree, data, file_path, lang))
    findings.extend(measure_cognitive_complexity(tree, data, file_path, lang))
    findings.extend(measure_boolean_complexity(tree, data, file_path, lang))
    findings.extend(measure_god_class(tree, data, file_path, lang))
    findings.extend(measure_error_handling(tree, data, file_path, lang))
    findings.extend(measure_visibility_ratio(tree, data, file_path, lang))
    findings.extend(measure_nloc(tree, data, file_path, lang))
    findings.extend(measure_maintainability_index(tree, data, file_path, lang))
    findings.extend(measure_import_depth(tree, data, file_path, lang))
    findings.extend(measure_code_clones(tree, data, file_path, lang))
    findings.extend(measure_function_purity(tree, data, file_path, lang))
    findings.extend(measure_unreachable_code(tree, data, file_path, lang))
    findings.extend(measure_unused_imports(tree, data, file_path, lang))
    findings.extend(measure_unused_classes(tree, data, file_path, lang))
    findings.extend(measure_unused_variables(tree, data, file_path, lang))
    findings.extend(structural_diff(file_path))
    findings.extend(measure_churn_hotspots(file_path))

    return findings


def run_project(files: list[str]) -> dict[str, Any]:
    """Run structural measurements across a project, including cyclic imports and coupling.

    Returns {"measurements": [...], "meta": {...}} where meta contains project-level
    aggregation (total files, NLOC, avg complexity, language breakdown).
    """
    findings: list[dict[str, Any]] = []
    for f in files:
        try:
            findings.extend(run(f))
        except (ValueError, Exception):
            continue  # Skip unsupported files
    findings.extend(measure_cyclic_imports(files, ""))
    findings.extend(measure_module_coupling(files))
    findings.extend(measure_code_clones_project(files))

    # Build module graph for cross-file dead code detection
    project_import_graph: dict[str, list[str]] = {}
    try:
        mg = ModuleGraph()
        mg.build(files)

        # Set entry points from config + language defaults
        cfg = load_config()
        config_entry_points = cfg.get("project", {}).get("entry_points", [])
        entry_points = list(config_entry_points)
        for f in files:
            ext = Path(f).suffix.lower()
            lang = extension_to_language(ext)
            if lang:
                entry_points.extend(get_entry_points(lang))
        mg.set_entry_points(entry_points)
        mg.compute_reachability()

        # Add unused file and cross-file dead function findings
        findings.extend(mg.find_unused_files())
        findings.extend(mg.find_cross_file_dead_functions())

        # Use module graph's import graph for visualization
        project_import_graph = mg.get_import_graph()
    except Exception:
        project_import_graph = {}

    # Compute project-level meta
    nloc_values = [m["value"] for m in findings if m["metric"] == "nloc" and m["value"] is not None]
    cc_values = [
        m["value"]
        for m in findings
        if m["metric"] == "cyclomatic_complexity" and m["value"] is not None
    ]
    cog_values = [
        m["value"]
        for m in findings
        if m["metric"] == "cognitive_complexity" and m["value"] is not None
    ]
    nest_values = [
        m["value"] for m in findings if m["metric"] == "nesting_depth" and m["value"] is not None
    ]

    total_nloc = sum(nloc_values) if nloc_values else 0
    avg_cc = round(sum(cc_values) / len(cc_values), 1) if cc_values else 0
    avg_cog = round(sum(cog_values) / len(cog_values), 1) if cog_values else 0
    max_nest = max(nest_values) if nest_values else 0

    # Language breakdown
    from collections import Counter

    lang_count: Counter = Counter()
    for f in files:
        ext = Path(f).suffix.lower()
        lang = extension_to_language(ext)
        if lang:
            lang_count[lang] += 1

    meta = {
        "total_files": len(files),
        "total_nloc": total_nloc,
        "avg_cyclomatic": avg_cc,
        "avg_cognitive": avg_cog,
        "max_nesting": max_nest,
        "languages": dict(lang_count.most_common()),
        "import_graph": project_import_graph,
    }

    return {"measurements": findings, "meta": meta}
