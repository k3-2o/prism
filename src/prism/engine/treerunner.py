"""Tree-sitter structural measurement engine — multi-language support.

Uses the language registry (languages.py) to dispatch to the correct
tree-sitter grammar, queries, and thresholds for each file type.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tree_sitter import QueryCursor, Tree

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
    **extra: Any,
) -> dict[str, Any]:
    return {
        "source": "structure",
        "metric": metric,
        "function": function,
        "value": value,
        "threshold": threshold,
        "location": location,
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
    """Find functions with nesting depth above language-specific threshold."""
    queries = get_queries(lang)
    thresholds = get_thresholds(lang)
    max_depth = thresholds["nesting_depth"]
    text = data.decode("utf-8")
    lines = text.split("\n")
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

        start_line = func_node.start_point[0]
        end_line = func_node.end_point[0]
        line = start_line + 1

        max_depth = 0
        for i in range(start_line, min(end_line + 1, len(lines))):
            raw = lines[i]
            if raw.strip() and not raw.strip().startswith(("#", "//", "/*")):
                indent = len(raw) - len(raw.lstrip())
                depth = indent // 4
                if depth > max_depth:
                    max_depth = depth

        if max_depth > thresholds["nesting_depth"]:
            findings.append(
                _make_measurement(
                    "nesting_depth",
                    func_name,
                    max_depth,
                    thresholds["nesting_depth"],
                    {"file": file_path, "line": line},
                )
            )

    return findings


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
                    )
                )

    return findings


# ── Cyclic imports (cross-file) ──────────────────────────────────────────


def _extract_module_imports(data: bytes, lang: str) -> set[str]:
    """Extract local module names imported by this file."""
    try:
        parser = get_parser(lang)
    except ValueError:
        return set()
    tree = parser.parse(data)
    queries = get_queries(lang)
    imports: set[str] = set()
    for node in _get_captures(queries["imports"], tree.root_node).get("name", []):
        import_text = _text(data, node)
        # Clean up quotes and path separators
        import_text = import_text.strip("\"'")
        parts = import_text.replace("/", ".").replace("\\", ".").split(".")
        if len(parts) >= 1:
            imports.add(parts[0])
    return imports


def measure_cyclic_imports(files: list[str], base_dir: str) -> list[dict[str, Any]]:
    """Detect cyclic import chains across files in the given list."""
    import_graph: dict[str, set[str]] = {}
    file_paths: dict[str, str] = {}

    for fpath in files:
        p = Path(fpath)
        try:
            data = p.read_bytes()
        except Exception:
            continue
        module_name = p.stem
        file_paths[module_name] = str(p)
        lang = extension_to_language(p.suffix.lower()) or "python"
        imports = _extract_module_imports(data, lang)
        # Filter to only modules that exist in our project
        project_stems = {Path(f).stem for f in files}
        imports = {m for m in imports if m in project_stems}
        import_graph[module_name] = imports

    cycles = _find_cycles(import_graph)

    findings: list[dict[str, Any]] = []
    for cycle in cycles:
        for node in cycle:
            if node not in file_paths:
                continue
            findings.append(
                _make_measurement(
                    "cyclic_import",
                    node,
                    len(cycle),
                    1,
                    {"file": file_paths[node], "line": 1},
                    cycle=cycle,
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
    # Build import graph: module_name -> set of imported project module names
    imports_from: dict[str, set[str]] = {}
    module_paths: dict[str, str] = {}

    for fpath in files:
        p = Path(fpath)
        try:
            data = p.read_bytes()
        except Exception:
            continue
        module_name = p.stem
        module_paths[module_name] = str(fpath)

        ext = p.suffix.lower()
        lang = extension_to_language(ext)
        if not lang:
            continue

        project_stems = {Path(f).stem for f in files}
        imported = _extract_module_imports(data, lang)
        imports_from[module_name] = {m for m in imported if m in project_stems and m != module_name}

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
                )
            )

    return findings


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
    findings.extend(measure_import_depth(tree, data, file_path, lang))
    findings.extend(measure_code_clones(tree, data, file_path, lang))
    findings.extend(measure_function_purity(tree, data, file_path, lang))
    findings.extend(measure_unreachable_code(tree, data, file_path, lang))
    findings.extend(measure_unused_imports(tree, data, file_path, lang))
    findings.extend(measure_unused_classes(tree, data, file_path, lang))
    findings.extend(structural_diff(file_path))

    return findings


def run_project(files: list[str]) -> list[dict[str, Any]]:
    """Run structural measurements across a project, including cyclic imports and coupling."""
    findings: list[dict[str, Any]] = []
    for f in files:
        try:
            findings.extend(run(f))
        except (ValueError, Exception):
            continue  # Skip unsupported files
    findings.extend(measure_cyclic_imports(files, ""))
    findings.extend(measure_module_coupling(files))
    return findings
