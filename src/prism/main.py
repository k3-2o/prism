"""PRISM CLI entry point."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import click

from prism import __version__
from prism.config import _deep_merge, load_config
from prism.engine.languages import extension_to_language
from prism.engine.treerunner import run as treerunner_run
from prism.engine.treerunner import run_project as treerunner_run_project
from prism.enrich.enricher import discover_project_files, enrich_measurements
from prism.output.viz import render_dependency_graph, try_render_svg


def _format_single_output(path: str, measurements: list[dict], config: dict | None = None) -> dict:
    """Format measurements for a single file into the structured output."""
    lang = _detect_language(path)
    nloc = 0

    findings: list[dict] = []
    for m in measurements:
        f = _condense_finding(m)
        findings.append(f)
        if m["metric"] == "nloc":
            nloc = m.get("value", 0)

    return {
        "prism": {"version": __version__},
        "project": {
            "root": str(Path(path).resolve().parent),
            "primary_language": lang,
            "files_scanned": 1,
            "total_nloc": nloc,
        },
        "summary": _build_summary(findings),
        "files": {path: {"nloc": nloc, "language": lang, "findings": findings}},
    }


def _format_project_output(
    root: str,
    files: list[str],
    all_measurements: list[dict],
    project_meta: dict,
    config: dict | None = None,
    visualize: bool = False,
    visualize_format: str = "dot",
) -> dict:
    """Format measurements for a project into the structured output."""
    project_lang = _detect_project_language(files) if files else "unknown"

    # Group measurements by file
    by_file: dict[str, list[dict]] = defaultdict(list)
    for m in all_measurements:
        fpath = m.get("location", {}).get("file", "")
        if fpath:
            by_file[fpath].append(m)

    # Build structured file entries
    files_output: dict[str, dict] = {}
    for fpath in sorted(by_file):
        findings: list[dict] = []
        file_nloc = 0
        for m in by_file[fpath]:
            f = _condense_finding(m)
            findings.append(f)
            if m["metric"] == "nloc":
                file_nloc = m.get("value", 0)

        ext = Path(fpath).suffix.lower()
        file_lang = extension_to_language(ext) or "unknown"

        files_output[fpath] = {
            "nloc": file_nloc,
            "language": file_lang,
            "findings": sorted(findings, key=lambda x: (x.get("line", 1), x.get("metric", ""))),
        }

    output: dict = {
        "prism": {"version": __version__},
        "project": {
            "root": root,
            "primary_language": project_lang,
            "files_scanned": project_meta.get("total_files", len(files)),
            "total_nloc": project_meta.get("total_nloc", 0),
            "languages": project_meta.get("languages", {}),
        },
        "summary": _build_summary(all_measurements),
        "files": files_output,
    }

    if project_meta.get("import_graph"):
        output["import_graph"] = project_meta["import_graph"]

    if visualize:
        _generate_visualization(files, all_measurements, root, output, visualize_format)

    return output


def _condense_finding(m: dict) -> dict:
    """Condense a raw measurement into a compact finding dict.

    Strips redundant fields (source, threshold) and nests caller info
    with relative paths for readability.
    """
    finding: dict = {
        "metric": m["metric"],
        "function": m.get("function", ""),
        "value": m.get("value"),
        "line": m.get("location", {}).get("line", 1),
    }

    if m.get("confidence") is not None:
        finding["confidence"] = m["confidence"]

    ctx = m.get("context", {})
    if ctx.get("detail"):
        finding["detail"] = ctx["detail"]

    callers = ctx.get("callers", [])
    if callers:
        clean_callers = []
        for c in callers:
            clean_callers.append(
                {
                    "function": c.get("function", ""),
                    "file": c.get("file", ""),
                    "line": c.get("line", 0),
                }
            )
        finding["callers"] = clean_callers

    if ctx.get("cycle"):
        finding["cycle"] = ctx["cycle"]

    return finding


def _build_summary(measurements: list[dict]) -> dict:
    """Build summary counts from raw measurements."""
    from collections import Counter

    by_metric = Counter(m["metric"] for m in measurements)
    return {
        "findings": len(measurements),
        "by_metric": dict(by_metric.most_common()),
    }


def _build_output(
    path: str,
    config: dict | None = None,
    visualize: bool = False,
    visualize_format: str = "dot",
) -> dict:
    p = Path(path)
    if p.is_dir():
        return _build_project_wrapper(str(p.resolve()), config, visualize, visualize_format)

    measurements = treerunner_run(path)
    project_files = discover_project_files(str(p.parent))
    measurements = enrich_measurements(measurements, path, project_files, fast=True)

    return _format_single_output(path, measurements, config)


def _build_project_wrapper(
    root: str,
    config: dict | None = None,
    visualize: bool = False,
    visualize_format: str = "dot",
) -> dict:
    files = discover_project_files(root)
    if not files:
        return {
            "prism": {"version": __version__},
            "project": {
                "root": root,
                "primary_language": "unknown",
                "files_scanned": 0,
                "total_nloc": 0,
            },
            "summary": {"findings": 0, "by_metric": {}},
            "files": {},
        }

    result = treerunner_run_project(files)
    all_measurements = result["measurements"]
    project_meta = result["meta"]

    # Fast caller enrichment
    for f in files:
        file_measurements = [x for x in all_measurements if x.get("location", {}).get("file") == f]
        other_files = [x for x in files if x != f]
        enrich_measurements(file_measurements, f, other_files, fast=True)

    return _format_project_output(
        root, files, all_measurements, project_meta, config, visualize, visualize_format
    )


def _detect_project_language(files: list[str]) -> str:
    langs: dict[str, int] = {}
    for f in files:
        ext = Path(f).suffix.lower()
        lang = extension_to_language(ext)
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
    return max(langs, key=lambda k: langs[k]) if langs else "unknown"


def _generate_visualization(
    files: list[str],
    measurements: list[dict],
    root: str,
    output: dict,
    viz_format: str,
) -> None:
    import_graph: dict[str, list[str]] = output.get("import_graph", {})

    cycles: list[list[str]] = []
    for m in measurements:
        if m.get("metric") == "cyclic_import":
            cycle_path = m.get("context", {}).get("cycle", [])
            if cycle_path and cycle_path not in cycles:
                cycles.append(cycle_path)

    file_labels: dict[str, str] = {}
    file_section = output.get("files", {})
    for fpath, info in file_section.items():
        stem = Path(fpath).stem
        file_labels[stem] = f"{stem} ({info.get('nloc', 0)} NLOC)"

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
        output["prism"]["entry_points"] = config.get("project", {}).get("entry_points", [])

        click.echo(json.dumps(output, indent=2))
    except Exception as e:
        click.echo(
            json.dumps(
                {
                    "prism": {"version": __version__},
                    "status": "error",
                    "error": str(e),
                    "file": path,
                },
                indent=2,
            ),
            err=True,
        )
        sys.exit(1)
