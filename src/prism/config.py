"""Configuration loader for PRISM.

Loads settings from:
1. `~/.prism/config.toml` — user-level global config
2. `.prism.toml` — project-level config (in project root)
3. CLI flags — highest priority, override both

Config sections:
  [project]
  entry_points = ["main", "handler", "app"]

  [dead_code]
  confidence = true
  whitelist = { name = "reason why it's not dead" }

  [complexity]
  cyclomatic_threshold = 10
  cognitive_threshold = 15
  clone_similarity = 0.8
  clone_min_tokens = 10

  [output]
  format = "json"

Returns a flat dict or a Config dataclass.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

# Default configuration
DEFAULT_CONFIG: dict[str, Any] = {
    "project": {
        "entry_points": [],
    },
    "dead_code": {
        "confidence": True,
        "whitelist": {},
    },
    "complexity": {
        "cyclomatic_threshold": 10,
        "cognitive_threshold": 15,
        "clone_similarity": 0.8,
        "clone_min_tokens": 10,
        "churn_hotspot_threshold": 2.0,
    },
    "output": {
        "format": "json",
    },
}

_GLOBAL_CONFIG_PATH = Path.home() / ".prism" / "config.toml"


def _load_toml(path: Path) -> dict[str, Any]:
    """Load a TOML file, returning empty dict if missing or malformed."""
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError):
        return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. override wins."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def load_config(project_root: str | None = None) -> dict[str, Any]:
    """Load and merge configuration from all sources.

    Priority (lowest to highest):
    1. DEFAULT_CONFIG
    2. ~/.prism/config.toml
    3. .prism.toml (project root)
    4. CLI flags should be merged by caller
    """
    config = dict(DEFAULT_CONFIG)

    # Global user config
    global_cfg = _load_toml(_GLOBAL_CONFIG_PATH)
    config = _deep_merge(config, global_cfg)

    # Project-level config
    if project_root:
        project_cfg = _load_toml(Path(project_root) / ".prism.toml")
        config = _deep_merge(config, project_cfg)

    return config


def get_entry_points(config: dict[str, Any] | None = None) -> list[str]:
    """Get entry point names from config."""
    if config is None:
        config = load_config()
    return config.get("project", {}).get("entry_points", [])


def get_whitelist(config: dict[str, Any] | None = None) -> dict[str, str]:
    """Get dead code whitelist from config."""
    if config is None:
        config = load_config()
    return config.get("dead_code", {}).get("whitelist", {})


def get_threshold_override(metric: str, config: dict[str, Any] | None = None) -> int | None:
    """Get a threshold override from config, or None."""
    if config is None:
        config = load_config()
    key = f"{metric}_threshold"
    return config.get("complexity", {}).get(key)
