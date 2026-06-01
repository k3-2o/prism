"""Semgrep subprocess runner — runs scans and parses JSON output."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

_SEMGREP_MIN_VERSION = (1, 80, 0)


def _check_semgrep() -> str | None:
    """Return 'semgrep' if available and recent enough, else None."""
    try:
        result = subprocess.run(
            ["semgrep", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        version_str = result.stdout.strip()
        parts = version_str.split(".")
        if len(parts) >= 2:
            major = int(parts[0])
            minor = int(parts[1])
            if (major, minor) >= (1, 80):
                return "semgrep"
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None


def run_semgrep(
    target_path: str,
    prism_rules_dir: str | None = None,
    include_community: bool = False,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    """Run Semgrep on target_path and return parsed results.

    By default, runs only PRISM-curated rules (bundled, no network).
    Set include_community=True to also run Semgrep community rules
    (slower but catches web security / IaC issues).

    Returns empty list if semgrep is not available or scan fails.
    """
    semgrep_bin = _check_semgrep()
    if not semgrep_bin:
        return []

    configs: list[str] = []

    # PRISM curated rules — each individual YAML file must be passed separately
    if prism_rules_dir and Path(prism_rules_dir).exists():
        rule_dir = Path(prism_rules_dir).resolve()
        for yaml_file in sorted(rule_dir.glob("*.yaml")) + sorted(rule_dir.glob("*.yml")):
            configs.append(str(yaml_file))

    # Community rules are opt-in (slower, needs network)
    if include_community:
        configs.append("auto")

    if not configs:
        return []  # No rules to run

    cmd = [semgrep_bin, "--json", "--no-rewrite-rule-ids"]
    for c in configs:
        cmd.extend(["--config", c])
    cmd.append(target_path)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode not in (0, 1):
            # 0 = no findings, 1 = findings found, other = error
            return []

        output = json.loads(result.stdout)
    except (json.JSONDecodeError, subprocess.TimeoutExpired, FileNotFoundError):
        return []

    raw_results = output.get("results", [])
    return [_normalize_semgrep_finding(r) for r in raw_results]


def _normalize_semgrep_finding(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a Semgrep result into PRISM's finding shape."""
    extra = raw.get("extra", {})
    sev_raw = extra.get("severity", "INFO")
    severity = {"ERROR": "critical", "WARNING": "medium", "INFO": "low"}.get(sev_raw, "medium")
    path = raw.get("path", "")
    start = raw.get("start", {})

    return {
        "source": "semgrep-community"
        if not raw.get("check_id", "").startswith("prism.")
        else "semgrep-curated",
        "rule": raw.get("check_id", "unknown"),
        "severity": severity,
        "message": extra.get("message", ""),
        "location": {
            "file": path,
            "line": start.get("line", 0),
            "column": start.get("col", 0),
        },
        "context": {
            "function": "",
            "signature": "",
            "body_lines": 0,
            "callers": [],
        },
    }
