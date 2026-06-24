"""PRISM CLI entry point."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from prism import __version__
from prism.config import _deep_merge, load_config
from prism.engine.languages import extension_to_language
from prism.engine.semgrep_runner import run_semgrep
from prism.engine.treerunner import run as treerunner_run
from prism.engine.treerunner import run_project as treerunner_run_project
from prism.enrich.enricher import discover_project_files, enrich_by_line, enrich_measurements

# Path to PRISM-curated Semgrep rules, shipped with the package
_PRISM_RULES_DIR = str(Path(__file__).resolve().parent / "rules")


def _build_output(
    path: str,
    structure_only: bool,
    include_community: bool,
    config: dict | None = None,
) -> dict:
    p = Path(path)
    if p.is_dir():
        return _build_project_output(str(p.resolve()), structure_only, include_community, config)

    measurements = treerunner_run(path)
    project_files = discover_project_files(str(p.parent))
    measurements = enrich_measurements(measurements, path, project_files, fast=structure_only)

    semgrep_findings = _run_semgrep_if_needed(
        path, structure_only, include_community, project_files
    )

    community = [f for f in semgrep_findings if f.get("source") == "semgrep-community"]
    curated = [f for f in semgrep_findings if f.get("source") == "semgrep-curated"]

    return {
        "version": __version__,
        "file": path,
        "language": _detect_language(path),
        "mode": "structure-only" if structure_only else "full",
        "measurements_count": len(measurements),
        "measurements": measurements,
        "semgrep_community": community,
        "semgrep_curated": curated,
    }


def _run_semgrep_if_needed(
    path: str, structure_only: bool, include_community: bool, project_files: list[str]
) -> list[dict]:
    if structure_only:
        return []
    raw = run_semgrep(path, prism_rules_dir=_PRISM_RULES_DIR, include_community=include_community)
    enriched = []
    cache: dict = {}
    for f in raw:
        enriched.append(enrich_by_line(f, path, project_files, _cache=cache))
    return enriched


def _detect_project_language(files: list[str]) -> str:
    """Detect the primary language of a project from its file extensions."""
    from prism.engine.languages import extension_to_language

    langs: dict[str, int] = {}
    for f in files:
        ext = Path(f).suffix.lower()
        lang = extension_to_language(ext)
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
    if not langs:
        return "unknown"
    return max(langs, key=lambda k: langs[k])


def _build_project_output(
    root: str,
    structure_only: bool,
    include_community: bool,
    config: dict | None = None,
) -> dict:
    files = discover_project_files(root)
    project_lang = _detect_project_language(files) if files else "unknown"
    if not files:
        return {
            "version": __version__,
            "file": root,
            "language": project_lang,
            "mode": "structure-only" if structure_only else "full",
            "measurements_count": 0,
            "measurements": [],
            "semgrep_community": [],
            "semgrep_curated": [],
        }

    result = treerunner_run_project(files)
    all_measurements = result["measurements"]
    project_meta = result["meta"]

    if not structure_only:
        for f in files:
            file_measurements = [
                x for x in all_measurements if x.get("location", {}).get("file") == f
            ]
            other_files = [x for x in files if x != f]
            enrich_measurements(file_measurements, f, other_files)
    else:
        for f in files:
            file_measurements = [
                x for x in all_measurements if x.get("location", {}).get("file") == f
            ]
            other_files = [x for x in files if x != f]
            enrich_measurements(file_measurements, f, other_files, fast=True)

    all_community: list[dict] = []
    all_curated: list[dict] = []
    if not structure_only:
        semgrep_cache: dict = {}
        for f in files:
            raw = run_semgrep(
                f, prism_rules_dir=_PRISM_RULES_DIR, include_community=include_community
            )
            other_files = [x for x in files if x != f]
            for finding in raw:
                finding = enrich_by_line(finding, f, other_files, _cache=semgrep_cache)
            all_community.extend(x for x in raw if x.get("source") == "semgrep-community")
            all_curated.extend(x for x in raw if x.get("source") == "semgrep-curated")

    return {
        "version": __version__,
        "file": root,
        "language": project_lang,
        "mode": "structure-only" if structure_only else "full",
        "measurements_count": len(all_measurements),
        "measurements": all_measurements,
        "meta": project_meta,
        "semgrep_community": all_community,
        "semgrep_curated": all_curated,
    }


def _detect_language(path: str) -> str:
    ext = Path(path).suffix.lower()
    lang = extension_to_language(ext)
    return lang if lang else "unknown"


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--structure-only",
    is_flag=True,
    default=False,
    help="Skip Semgrep scan, run tree-sitter measurements only.",
)
@click.option(
    "--community",
    is_flag=True,
    default=False,
    help="Include Semgrep community rules (slower, needs network). "
    "Default is PRISM-curated rules only.",
)
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
@click.version_option(__version__)
def cli(
    path: str,
    structure_only: bool,
    community: bool,
    config_path: str | None,
    entry_points: tuple[str, ...] | None,
) -> None:
    """Analyze PATH and return enriched JSON structural measurements.

    By default runs tree-sitter measurements + PRISM-curated Semgrep rules.
    Use --community to include the full Semgrep community rule set (slower).
    Use --structure-only to skip Semgrep entirely (fastest).

    --entry-points can be specified multiple times to mark functions that
    should never be flagged as dead code (e.g., --entry-points main
    --entry-points handler).
    """
    try:
        # Load config: project config, then override with CLI flags
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

        output = _build_output(path, structure_only, community, config)
        # Attach config info to output for transparency
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
