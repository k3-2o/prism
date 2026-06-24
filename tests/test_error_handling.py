"""Tests for error handling coverage detection."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import find_metrics, run_prism_on_file


class TestErrorHandling:
    """Test error handling coverage detection."""

    def test_unguarded_risky_call(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f():\n    with open('file'): pass\n    eval('1+1')\n", tmp_path
        )
        assert len(find_metrics(result, "error_handling_coverage")) >= 1

    def test_guarded_call_covered(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f():\n    try:\n        open('file')\n    except Exception:\n        pass\n",
            tmp_path,
        )
        assert len(find_metrics(result, "error_handling_coverage")) == 0

    def test_subprocess_risky_call(self, tmp_path: Path):
        result = run_prism_on_file(
            "import subprocess\ndef f():\n    subprocess.run(['ls'])\n", tmp_path
        )
        m = find_metrics(result, "error_handling_coverage")
        assert len(m) >= 1
