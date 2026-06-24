"""PRISM CLI entry point."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from prism import __version__
from prism.config import _deep_merge, load_config
from prism.engine.languages import extension_to_language
from prism.engine.treerunner import run as treerunner_run
from prism.engine.treerunner import run_project as treerunner_run_project
from prism.enrich.enricher import discover_project_files, enrich_measurements
from prism.output.viz import render_dependency_graph, try_render_svg


def _build_output(
    path: str,
    config: dict | None = None,
    visualize: bool = False,
    visualize_format: str = "dot",
) -> dict:
    p = Path(path)
    if p.is_dir():
        return _build_project_output(
            str(p.resolve()),
            config,
            visualize=visualize,
            visualize_format=visualize_format,
        )

    measurements = treerunner_run(path)
    project_files = discover_project_files(str(p.parent))
    measurements = enrich_measurements(measurements, path, project_files, fast=True)

    return {
        "version": __version__,
        "file": path,
        "language": _detect_language(path),
        "measurements_count": len(measurements),
        "measurements": measurements,
    }


def _detect_project_language(files: list[str]) -> str:
    """Detect the primary language of a project from its file extensions."""
    langs: dict[str, int] = {}
    for f in files:
        ext = Path(f).suffix.lower()
        lang = extension_to_language(ext)
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
    return max(langs, key=lambda k: langs[k]) if langs else "unknown"


def _build_project_output(
    root: str,
    config: dict | None = None,
    visualize: bool = False,
    visualize_format: str = "dot",
) -> dict:
    files = discover_project_files(root)
    project_lang = _detect_project_language(files) if files else "unknown"
    if not files:
        return {
            "version": __version__,
            "file": root,
            "language": project_lang,
            "measurements_count": 0,
            "measurements": [],
        }

    result = treerunner_run_project(files)
    all_measurements = result["measurements"]
    project_meta = result["meta"]

    # Fast caller enrichment
    for f in files:
        file_measurements = [x for x in all_measurements if x.get("location", {}).get("file") == f]
        other_files = [x for x in files if x != f]
        enrich_measurements(file_measurements, f, other_files, fast=True)

    output: dict = {
        "version": __version__,
        "file": root,
        "language": project_lang,
        "measurements_count": len(all_measurements),
        "measurements": all_measurements,
        "meta": project_meta,
    }

    if visualize:
        _generate_visualization(files, all_measurements, root, output, visualize_format)

    return output


def _generate_visualization(
    files: list[str],
    measurements: list[dict],
    root: str,
    output: dict,
    viz_format: str,
) -> None:
    """Generate dependency graph visualization."""
    meta = output.get("meta", {})
    import_graph: dict[str, list[str]] = meta.get("import_graph", {})

    cycles: list[list[str]] = []
    for m in measurements:
        if m.get("metric") == "cyclic_import":
            cycle_path = m.get("context", {}).get("cycle", [])
            if cycle_path and cycle_path not in cycles:
                cycles.append(cycle_path)

    file_labels: dict[str, str] = {}
    for m in measurements:
        if m.get("metric") == "nloc":
            mod_name = m.get("function", "")
            val = m.get("value", 0)
            if mod_name:
                file_labels[mod_name] = f"{mod_name} ({val} NLOC)"

    root_name = Path(root).name
    dot_path = f"{root_name}-deps.dot"
    render_dependency_graph(dict(import_graph), cycles, dot_path, file_labels=file_labels or None)

    output["visualization"] = dot_path

    if viz_format != "dot":
        rendered = try_render_svg(dot_path, viz_format)
        if rendered:
            output["visualization_rendered"] = rendered
        else:
            output["visualization_error"] = "dot command not found; install graphviz"


def _detect_language(path: str) -> str:
    ext = Path(path).suffix.lower()
    lang = extension_to_language(ext)
    return lang if lang else "unknown"


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True),
    default=None,
    help="Path to .prism.toml config file.",
)
@click.option(
    "--entry-points",
    "entry_points",
    multiple=True,
    default=None,
    help="Function names to treat as entry points (never flagged as dead). "
    "Can be specified multiple times.",
)
@click.option(
    "--visualize",
    is_flag=True,
    default=False,
    help="Generate a dependency graph DOT file.",
)
@click.option(
    "--visualize-format",
    "visualize_format",
    type=click.Choice(["dot", "svg", "png"]),
    default="dot",
    help="Output format for visualization (default: dot). Requires graphviz.",
)
@click.version_option(__version__)
def cli(
    path: str,
    config_path: str | None,
    entry_points: tuple[str, ...] | None,
    visualize: bool = False,
    visualize_format: str = "dot",
) -> None:
    """Analyze PATH and return JSON structural measurements.

    Runs tree-sitter structural analysis across 12 languages.
    Use --entry-points to mark functions that should never be
    flagged as dead code. Use --visualize for dependency graphs.
    """
    try:
        config = load_config(
            project_root=str(Path(path).resolve().parent if not Path(path).is_dir() else path)
        )
        if config_path:
            import tomllib

            with open(config_path, "rb") as f:
                file_cfg = tomllib.load(f)
            config = _deep_merge(config, file_cfg)
        if entry_points:
            config.setdefault("project", {})["entry_points"] = list(entry_points)

        output = _build_output(path, config, visualize=visualize, visualize_format=visualize_format)
        output["config"] = {
            "entry_points": config.get("project", {}).get("entry_points", []),
        }
        click.echo(json.dumps(output, indent=2))
    except Exception as e:
        click.echo(
            json.dumps(
                {
                    "version": __version__,
                    "file": path,
                    "status": "error",
                    "error": str(e),
                },
                indent=2,
            ),
            err=True,
        )
        sys.exit(1)
