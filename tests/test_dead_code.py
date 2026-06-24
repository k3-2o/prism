"""Tests for dead code detection: dead_functions, unreachable, unused imports/vars/classes.

Also covers: confidence levels, entry point awareness, whitelist.
"""

from __future__ import annotations

from pathlib import Path

from tests.conftest import find_metrics, has_metric_for_function, run_prism_on_file


class TestDeadFunction:
    """Test dead function detection."""

    def test_dead_function_detected(self, tmp_path: Path):
        result = run_prism_on_file("def unused(): pass\ndef used(): pass\nused()\n", tmp_path)
        assert has_metric_for_function(result, "dead_function", "unused")

    def test_called_function_not_dead(self, tmp_path: Path):
        result = run_prism_on_file("def used(): pass\nused()\n", tmp_path)
        assert not has_metric_for_function(result, "dead_function", "used")

    def test_has_confidence(self, tmp_path: Path):
        result = run_prism_on_file("def unused(): pass\n", tmp_path)
        m = find_metrics(result, "dead_function")
        if m:
            assert m[0].get("confidence") == 70


class TestUnreachableCode:
    """Test unreachable code detection."""

    def test_code_after_return(self, tmp_path: Path):
        result = run_prism_on_file("def f():\n    return 1\n    x = 2  # unreachable\n", tmp_path)
        m = find_metrics(result, "unreachable_code")
        assert len(m) >= 1
        assert m[0]["confidence"] == 100

    def test_no_unreachable_when_clean(self, tmp_path: Path):
        result = run_prism_on_file("def f():\n    x = 1\n    return x\n", tmp_path)
        assert len(find_metrics(result, "unreachable_code")) == 0

    def test_code_after_raise(self, tmp_path: Path):
        result = run_prism_on_file("def f():\n    raise ValueError()\n    x = 1\n", tmp_path)
        assert len(find_metrics(result, "unreachable_code")) >= 1


class TestUnusedImports:
    """Test unused import detection."""

    def test_unused_import_detected(self, tmp_path: Path):
        result = run_prism_on_file("import os  # never used\ndef f(): pass\n", tmp_path)
        assert has_metric_for_function(result, "unused_import", "os")

    def test_used_import_not_flagged(self, tmp_path: Path):
        result = run_prism_on_file("import json\ndef f():\n    return json.dumps({})\n", tmp_path)
        assert not has_metric_for_function(result, "unused_import", "json")


class TestUnusedVariables:
    """Test unused variable detection."""

    def test_unused_local_var(self, tmp_path: Path):
        result = run_prism_on_file("def f():\n    x = 5\n    return 1\n", tmp_path)
        m = find_metrics(result, "unused_variable")
        assert len(m) >= 1
        assert any("x" in d.get("detail", "") for d in m)

    def test_used_var_not_flagged(self, tmp_path: Path):
        result = run_prism_on_file("def f():\n    x = 5\n    return x\n", tmp_path)
        m = find_metrics(result, "unused_variable")
        assert not any("x" in d.get("detail", "") for d in m)

    def test_underscore_skipped(self, tmp_path: Path):
        result = run_prism_on_file("def f():\n    _ = 5\n    return 1\n", tmp_path)
        m = find_metrics(result, "unused_variable")
        assert not any("_" in d.get("detail", "") for d in m)

    def test_loop_var_unused(self, tmp_path: Path):
        result = run_prism_on_file("def f():\n    for i in range(3):\n        pass\n", tmp_path)
        m = find_metrics(result, "unused_variable")
        assert any("i" in d.get("detail", "") for d in m)


class TestConfidenceLevels:
    """Test that specific metrics report correct confidence levels."""

    def test_unreachable_is_100(self, tmp_path: Path):
        result = run_prism_on_file("def f():\n    return 1\n    x = 2\n", tmp_path)
        m = find_metrics(result, "unreachable_code")
        if m:
            assert m[0].get("confidence") == 100

    def test_dead_function_is_70(self, tmp_path: Path):
        result = run_prism_on_file("def unused(): pass\n", tmp_path)
        m = find_metrics(result, "dead_function")
        if m:
            assert m[0].get("confidence") == 70

    def test_unused_import_is_90(self, tmp_path: Path):
        result = run_prism_on_file("import os\ndef f(): pass\n", tmp_path)
        m = find_metrics(result, "unused_import")
        if m:
            assert any(x.get("confidence") == 90 for x in m)

    def test_unused_class_is_80(self, tmp_path: Path):
        result = run_prism_on_file("class Foo: pass\n", tmp_path)
        m = find_metrics(result, "unused_class")
        if m:
            assert m[0].get("confidence") == 80


class TestEntryPointAwareness:
    """Test that entry points are not flagged as dead."""

    def test_main_not_dead_in_python(self, tmp_path: Path):
        result = run_prism_on_file("def main():\n    pass\n", tmp_path)
        assert not has_metric_for_function(result, "dead_function", "main")
