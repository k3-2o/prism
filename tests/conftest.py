"""Shared test helpers for the PRISM test suite."""

from __future__ import annotations

import json
from pathlib import Path


def run_prism_on_file(content: str, tmp_path: Path) -> dict:
    """Write content to a temp file and run PRISM on it, returning parsed JSON."""
    f = tmp_path / "test.py"
    f.write_text(content)
    result = _run_prism(str(f))
    return result


def _run_prism(path: str) -> dict:
    """Run PRISM via CLI and return parsed output."""
    import subprocess

    result = subprocess.run(
        ["uv", "run", "prism", path],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=Path(__file__).resolve().parent.parent,
    )
    return json.loads(result.stdout)


def find_metrics(results: dict, metric: str) -> list[dict]:
    """Find all findings of a given metric type across all files."""
    findings: list[dict] = []
    for info in results.get("files", {}).values():
        for f in info.get("findings", []):
            if f["metric"] == metric:
                findings.append(f)
    return findings


def has_metric_for_function(results: dict, metric: str, func_name: str) -> bool:
    """Check if a function has a specific metric finding."""
    for info in results.get("files", {}).values():
        for f in info.get("findings", []):
            if f["metric"] == metric and f.get("function") == func_name:
                return True
    return False
