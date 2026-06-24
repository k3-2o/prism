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
    """Find all measurements of a given metric type."""
    return [m for m in results["measurements"] if m["metric"] == metric]


def has_metric_for_function(results: dict, metric: str, func_name: str) -> bool:
    """Check if a function has a specific metric flagged."""
    for m in results["measurements"]:
        if m["metric"] == metric and m["function"] == func_name:
            return True
    return False
