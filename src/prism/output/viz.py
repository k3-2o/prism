"""Graphviz output — render dependency graphs as DOT files.

Usage:
    prism . --visualize            # produces <project>-deps.dot
    prism . --visualize --visualize-format svg   # also runs dot -Tsvg
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def build_import_graph(
    files: list[str],
    measurements: list[dict[str, Any]],
) -> dict[str, set[str]]:
    """Build a dependency graph from measurements.

    Extracts module-level import relationships from cyclic_import and
    module_coupling measurements, plus direct file-to-module mapping.
    """
    graph: dict[str, set[str]] = {}
    file_modules: dict[str, str] = {}

    # Map files to readable node names
    for m in measurements:
        fpath = m.get("location", {}).get("file", "")
        if fpath:
            name = Path(fpath).stem
            file_modules[fpath] = name

    return graph


def render_dependency_graph(
    import_graph: dict,
    cycles: list[list[str]],
    output_path: str,
    file_labels: dict[str, str] | None = None,
) -> None:
    """Write a Graphviz DOT file from an import graph.

    import_graph: mapping of module name -> list/set of imported module names
    cycles: list of cycle paths (each a list of module names)
    output_path: path to write the .dot file
    file_labels: optional mapping of module -> display label
    """
    """Write a Graphviz DOT file from the import graph.

    Args:
        import_graph: mapping of module → set of imported modules
        cycles: list of cycle paths (each a list of module names)
        output_path: path to write the .dot file
        file_labels: optional mapping of module → display label (e.g., "file.py (142 NLOC)")
    """
    if not import_graph:
        _write_empty_dot(output_path)
        return

    # Collect all nodes
    all_nodes: set[str] = set(import_graph.keys())
    for deps in import_graph.values():
        all_nodes.update(list(deps))

    # Identify cycle nodes (any node that appears in a cycle)
    cycle_nodes: set[str] = set()
    for cycle in cycles:
        cycle_nodes.update(cycle)

    with open(output_path, "w") as f:
        f.write("digraph G {\n")
        f.write("  rankdir=LR;\n")
        f.write("  overlap=false;\n")
        f.write('  fontname="Monospace";\n')
        f.write('  node [shape=box, style=rounded, fontname="Monospace"];\n')
        f.write('  edge [fontname="Monospace", fontsize=10];\n')
        f.write("\n")

        # Nodes
        for node in sorted(all_nodes):
            label = file_labels.get(node, node) if file_labels else node
            attrs = [f'label="{label}"']
            if node in cycle_nodes:
                attrs.append('color="red"')
                attrs.append("penwidth=2.0")
            f.write(f'  "{node}" [{", ".join(attrs)}];\n')

        f.write("\n")

        # Edges
        for src, deps in sorted(import_graph.items()):
            # deps is either list[str] or set[str]; sorted() works with both
            for dst in sorted(list(deps)):
                edge_attrs = []
                if src in cycle_nodes or dst in cycle_nodes:
                    edge_attrs.append('color="red"')
                attrs_str = f" [{', '.join(edge_attrs)}]" if edge_attrs else ""
                f.write(f'  "{src}" -> "{dst}"{attrs_str};\n')

        f.write("}\n")


def _write_empty_dot(output_path: str) -> None:
    """Write a minimal DOT file with a single message node."""
    with open(output_path, "w") as f:
        f.write("digraph G {\n")
        f.write("  node [shape=box, style=rounded];\n")
        f.write('  empty [label="No dependencies found"];\n')
        f.write("}\n")


def try_render_svg(dot_path_str: str, fmt: str = "svg") -> str | None:
    """Attempt to render a .dot file to SVG/PNG using the `dot` command.

    Returns the output file path, or None if `dot` is not available.
    """
    dot_file = Path(dot_path_str)
    output_path = dot_file.with_suffix(f".{fmt}")

    try:
        result = subprocess.run(
            ["dot", f"-T{fmt}", str(dot_file), "-o", str(output_path)],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return str(output_path)
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
