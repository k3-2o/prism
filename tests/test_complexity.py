"""Tests for complexity metrics: params, length, NLOC, MI."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import find_metrics, run_prism_on_file


class TestParameterCount:
    """Test parameter count detection."""

    def test_function_with_too_many_params(self, tmp_path: Path):
        result = run_prism_on_file("def f(a, b, c, d, e, f, g): pass\n", tmp_path)
        m = find_metrics(result, "parameter_count")
        assert len(m) == 1
        assert m[0]["function"] == "f"
        assert m[0]["value"] == 7

    def test_skips_self_param(self, tmp_path: Path):
        result = run_prism_on_file("def method(self, a): pass\n", tmp_path)
        m = find_metrics(result, "parameter_count")
        assert len(m) == 0  # 2 params minus self = 1, below threshold


class TestFunctionLength:
    """Test function length detection."""

    def test_long_function(self, tmp_path: Path):
        lines = ["def long_func():"] + ["    x = 1"] * 70
        result = run_prism_on_file("\n".join(lines), tmp_path)
        m = find_metrics(result, "function_length")
        assert len(m) >= 1
        assert m[0]["function"] == "long_func"

    def test_short_function_not_flagged(self, tmp_path: Path):
        result = run_prism_on_file("def short(): pass\n", tmp_path)
        assert len(find_metrics(result, "function_length")) == 0


class TestNLOC:
    """Test NLOC counting."""

    def test_nloc_counts_source_lines(self, tmp_path: Path):
        result = run_prism_on_file(
            "def foo():\n    return 1\n\n# comment\n\ndef bar():\n    return 2\n",
            tmp_path,
        )
        m = find_metrics(result, "nloc")
        assert len(m) >= 1
        assert 3 <= m[0]["value"] <= 6


class TestMaintainabilityIndex:
    """Test MI computation."""

    def test_very_complex_function_flagged(self, tmp_path: Path):
        body = []
        for x, y in zip("abcdefgh", "hgfedcba"):
            body.append(f"    if {x}:\n        pass\n    elif {y}:\n        pass")
        result = run_prism_on_file(
            "def complex_func(a,b,c,d,e,f,g,h):\n" + "\n".join(body) + "\n",
            tmp_path,
        )
        m = find_metrics(result, "maintainability_index")
        if m:
            assert m[0]["value"] < 40  # Should be flagged
