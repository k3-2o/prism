"""Tests for CLI output structure and behavior."""

from __future__ import annotations

import json
from pathlib import Path

from tests.conftest import run_prism_on_file


class TestCLI:
    """Test CLI output structure."""

    def test_output_has_version(self, tmp_path: Path):
        result = run_prism_on_file("def f(): pass\n", tmp_path)
        assert "version" in result
        assert "measurements" in result
        assert isinstance(result["measurements"], list)

    def test_output_has_meta_for_project(self, tmp_path: Path):
        """Running on a directory should include meta."""
        (tmp_path / "test.py").write_text("def f(): pass\n")
        import subprocess

        result = subprocess.run(
            ["uv", "run", "prism", "--structure-only", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        data = json.loads(result.stdout)
        assert "meta" in data
        assert "total_files" in data["meta"]

    def test_config_info_in_output(self, tmp_path: Path):
        result = run_prism_on_file("def f(): pass\n", tmp_path)
        assert "config" in result
        assert "entry_points" in result["config"]
