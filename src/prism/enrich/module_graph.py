"""Module graph — builds import dependency graph and computes reachability.

Enables cross-file dead code detection (unused files, cross-file dead functions)
and provides the foundation for interprocedural analysis.

Architecture:
  - ModuleGraph.build(files) parses all files, resolves imports to file paths
  - set_entry_points() marks entry points (main, handlers, config)
  - compute_reachability() BFS from entry points through the import graph
  - find_unused_files() returns files not reachable from any entry point
  - find_cross_file_dead_functions() returns functions never referenced anywhere
"""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from prism.engine.languages import (
    extension_to_language,
    get_parser,
    get_queries,
)


class ModuleInfo:
    """Information about a single module (file)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.stem: str = Path(path).stem
        self.lang: str = ""
        self.imports: set[str] = set()  # resolved file paths this imports
        self.exports: set[str] = set()  # names exported (JS/TS)
        self.defined_functions: set[str] = set()  # functions defined here
        self.called_functions: set[str] = set()  # functions called from here


class ModuleGraph:
    """Import dependency graph with BFS reachability analysis."""

    def __init__(self) -> None:
        self.files: dict[str, ModuleInfo] = {}  # file_path -> ModuleInfo
        self.entry_points: list[str] = []  # entry point file paths
        self.reachable: set[str] = set()  # file paths reachable from entry points
        self._reverse_imports: dict[str, set[str]] = defaultdict(set)  # module -> importers

    def build(self, files: list[str]) -> None:
        """Parse all files, extract imports, resolve to file paths.

        Populates self.files with ModuleInfo for each supported file.
        """
        project_root = _find_project_root_for_graph(files)

        for fpath in files:
            p = Path(fpath)
            ext = p.suffix.lower()
            lang = extension_to_language(ext)
            if not lang:
                continue

            info = ModuleInfo(str(p.resolve()))
            info.lang = lang

            try:
                data = p.read_bytes()
            except Exception:
                continue

            # Parse with tree-sitter
            try:
                parser = get_parser(lang)
                tree = parser.parse(data)
            except Exception:
                continue

            queries = get_queries(lang)
            root = tree.root_node

            # Extract imports and resolve them
            info.imports = self._resolve_imports(data, lang, str(p), project_root, files)

            # Extract exports (JS/TS)
            if "exports" in queries:
                for node in _get_export_names(queries, root, data):
                    info.exports.add(node)

            # Extract defined function names
            for name in _get_defined_functions(queries, root, data):
                info.defined_functions.add(name)

            # Extract called function names (in-file)
            for name in _get_called_functions(queries, root, data):
                info.called_functions.add(name)

            self.files[str(p.resolve())] = info

        # Build reverse import map
        for fpath, info in self.files.items():
            for imported in info.imports:
                self._reverse_imports[imported].add(fpath)

    def _resolve_imports(
        self,
        data: bytes,
        lang: str,
        from_file: str,
        project_root: str,
        all_files: list[str],
    ) -> set[str]:
        """Extract and resolve import statements to file paths."""
        try:
            parser = get_parser(lang)
            tree = parser.parse(data)
        except Exception:
            return set()

        queries = get_queries(lang)
        resolved: set[str] = set()
        file_set = {str(Path(f).resolve()) for f in all_files}

        for node in _get_captures(queries["imports"], tree.root_node).get("name", []):
            import_text = _text(data, node).strip("\"'")
            resolved_path = _resolve_single_import(
                import_text, from_file, project_root, file_set, lang
            )
            if resolved_path:
                resolved.add(resolved_path)

        return resolved

    def set_entry_points(self, points: list[str]) -> None:
        """Set entry point file paths or module names.

        Args:
            points: list of file paths or module stem names to treat as entry points.
        """
        self.entry_points = []
        resolved_files = set(self.files.keys())

        for point in points:
            # Try as file path first
            p = Path(point)
            if p.exists() and str(p.resolve()) in resolved_files:
                self.entry_points.append(str(p.resolve()))
                continue

            # Try as module stem name
            for fpath in resolved_files:
                if Path(fpath).stem == point:
                    self.entry_points.append(fpath)
                    break

    def compute_reachability(self) -> set[str]:
        """BFS from entry points through the import graph.

        Returns set of reachable file paths.
        """
        if not self.entry_points:
            # If no entry points configured, all files are considered reachable
            self.reachable = set(self.files.keys())
            return self.reachable

        reachable: set[str] = set()
        queue: deque[str] = deque()

        for ep in self.entry_points:
            if ep in self.files:
                reachable.add(ep)
                queue.append(ep)

        while queue:
            current = queue.popleft()
            info = self.files.get(current)
            if not info:
                continue

            for imported in info.imports:
                if imported not in reachable and imported in self.files:
                    reachable.add(imported)
                    queue.append(imported)

        self.reachable = reachable
        return reachable

    def find_unused_files(self) -> list[dict[str, Any]]:
        """Find project files not reachable from any entry point.

        Skips __init__.py (package markers) and __main__.py (module entry).
        Returns measurement dicts for each unused file.
        """
        if not self.reachable:
            return []

        unused: list[dict[str, Any]] = []
        for fpath, info in self.files.items():
            if fpath not in self.reachable:
                # Skip package markers and module entry points
                if info.stem in ("__init__", "__main__"):
                    continue
                unused.append(
                    {
                        "source": "structure",
                        "metric": "unused_file",
                        "function": info.stem,
                        "value": 0,
                        "threshold": None,
                        "confidence": 80,
                        "location": {"file": info.path, "line": 1},
                        "context": {
                            "callers": [],
                            "detail": f"not reachable from entry points: {self.entry_points}",
                        },
                    }
                )

        return unused

    def find_cross_file_dead_functions(self) -> list[dict[str, Any]]:
        """Find functions that are defined but never called anywhere in the project.

        For each function in each reachable file, checks whether the function name
        appears as a call target in any other file. Functions that are called
        in-file are excluded (they're not dead).

        Returns measurement dicts.
        """
        # Build the full set of ALL called function names across ALL files
        all_called: set[str] = set()
        for info in self.files.values():
            all_called.update(info.called_functions)

        # Build the full set of exported names
        all_exported: set[str] = set()
        for info in self.files.values():
            all_exported.update(info.exports)

        dead: list[dict[str, Any]] = []
        seen: set[str] = set()

        for fpath, info in self.files.items():
            # Only check reachable files
            if fpath not in self.reachable:
                continue

            # Skip __init__ files — they're package markers, not real modules
            if info.stem == "__init__":
                continue

            for func_name in info.defined_functions:
                # Skip dunder methods (__init__, __str__, etc.) — called implicitly
                if func_name.startswith("__") and func_name.endswith("__"):
                    continue

                key = f"{info.stem}:{func_name}"
                if key in seen:
                    continue
                seen.add(key)

                # Skip if called in-file
                if func_name in info.called_functions:
                    continue

                # Skip if called in any other file
                if func_name in all_called:
                    continue

                # Check if exported — if so, mark as unused_export instead
                if func_name in all_exported:
                    dead.append(
                        {
                            "source": "structure",
                            "metric": "unused_export",
                            "function": func_name,
                            "value": 0,
                            "threshold": None,
                            "confidence": 70,
                            "location": {"file": info.path, "line": 1},
                            "context": {
                                "callers": [],
                                "detail": "exported but no cross-file callers found",
                            },
                        }
                    )
                else:
                    dead.append(
                        {
                            "source": "structure",
                            "metric": "dead_function",
                            "function": func_name,
                            "value": 0,
                            "threshold": None,
                            "confidence": 80,
                            "location": {"file": info.path, "line": 1},
                            "context": {
                                "callers": [],
                                "detail": "no callers in any project file",
                            },
                        }
                    )

        return dead

    def get_import_graph(self) -> dict[str, list[str]]:
        """Get the import graph as module_stem -> [imported_stems].

        Useful for visualization.
        """
        graph: dict[str, list[str]] = {}
        for fpath, info in self.files.items():
            stem = info.stem
            deps = [Path(p).stem for p in info.imports if Path(p).stem != stem]
            if deps:
                graph[stem] = sorted(set(deps))
        return graph


# ── Helper functions ──────────────────────────────────────────────────────


def _text(data: bytes, node: Any) -> str:
    """Extract text from bytes using node byte-range."""
    return data[node.start_byte : node.end_byte].decode("utf-8")


def _get_captures(query: Any, root: Any) -> dict[str, list[Any]]:
    """Get all captures from a query match."""
    from tree_sitter import QueryCursor

    cursor = QueryCursor(query)
    return cursor.captures(root)


def _get_export_names(queries: dict, root: Any, data: bytes) -> list[str]:
    """Extract exported names from JS/TS export queries."""
    if "exports" not in queries:
        return []
    names: list[str] = []
    for node in _get_captures(queries["exports"], root).get("name", []):
        names.append(_text(data, node))
    return names


def _get_defined_functions(queries: dict, root: Any, data: bytes) -> list[str]:
    """Extract function names defined in a file."""
    from tree_sitter import QueryCursor

    names: list[str] = []
    for _pat_idx, captures in QueryCursor(queries["functions"]).matches(root):
        for n, nodes in captures.items():
            if n == "name" and nodes:
                names.append(_text(data, nodes[0]))
    return names


def _get_called_functions(queries: dict, root: Any, data: bytes) -> list[str]:
    """Extract function names called in a file."""
    names: list[str] = []
    for node in _get_captures(queries["calls"], root).get("name", []):
        names.append(_text(data, node))
    return names


def _resolve_single_import(
    import_text: str,
    from_file: str,
    project_root: str,
    file_set: set[str],
    lang: str,
) -> str | None:
    """Resolve a single import statement to a project file path."""
    if lang == "python":
        try:
            from prism.enrich.resolver import resolve_python_import

            resolved = resolve_python_import(import_text, from_file, project_root)
            if resolved and str(Path(resolved).resolve()) in file_set:
                return str(Path(resolved).resolve())
        except Exception:
            pass

    # Fallback: try stem matching
    parts = import_text.replace("/", ".").replace("\\", ".").split(".")
    if parts:
        for f in file_set:
            if Path(f).stem == parts[0]:
                return f

    return None


def _find_project_root_for_graph(files: list[str]) -> str:
    """Find common parent directory of all files."""
    if not files:
        return "."
    paths = [Path(f).resolve() for f in files]
    common = paths[0]
    for p in paths[1:]:
        while common not in p.parents and common != p:
            common = common.parent
    return str(common)
