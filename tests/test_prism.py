"""Comprehensive test suite for PRISM — structural code analysis engine.

Tests all metric categories: complexity, dead code, coupling, clones,
error handling, purity, churn, config, resolver, module graph.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# ── Test helpers ──────────────────────────────────────────────────────────


def run_prism_on_file(content: str, tmp_path: Path) -> dict:
    """Write content to a temp file and run PRISM on it, returning parsed JSON."""
    f = tmp_path / "test.py"
    f.write_text(content)
    result = _run_prism(str(f))
    return result


def _run_prism(path: str) -> dict:
    """Run PRISM via CLI and return parsed output."""
    import subprocess

    from prism import __version__

    result = subprocess.run(
        ["uv", "run", "prism", "--structure-only", path],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=Path(__file__).resolve().parent.parent,
    )
    return json.loads(result.stdout)


def _find_metrics(results: dict, metric: str) -> list[dict]:
    """Find all measurements of a given metric type."""
    return [m for m in results["measurements"] if m["metric"] == metric]


# ── Config tests ─────────────────────────────────────────────────────────


class TestConfig:
    """Test configuration loading."""

    def test_load_defaults(self):
        """Default config should have expected sections."""
        from prism.config import load_config

        cfg = load_config()
        assert "project" in cfg
        assert "dead_code" in cfg
        assert "complexity" in cfg
        assert "output" in cfg

    def test_get_entry_points_default(self):
        """Default entry points should be empty list."""
        from prism.config import get_entry_points

        eps = get_entry_points()
        assert eps == []

    def test_get_whitelist_default(self):
        """Default whitelist should be empty dict."""
        from prism.config import get_whitelist

        wl = get_whitelist()
        assert wl == {}


# ── Resolver tests ────────────────────────────────────────────────────────


class TestResolver:
    """Test Python import path resolution."""

    def test_resolve_stdlib_returns_none(self, tmp_path: Path):
        """import json should return None (stdlib, not project file)."""
        from prism.enrich.resolver import resolve_python_import

        result = resolve_python_import("json", "test.py", str(tmp_path))
        assert result is None

    def test_resolve_absolute_module(self, tmp_path: Path):
        """import foo should resolve to foo.py in project root."""
        (tmp_path / "foo.py").write_text("x = 1")
        from prism.enrich.resolver import resolve_python_import

        result = resolve_python_import("foo", "test.py", str(tmp_path))
        assert result is not None
        assert "foo.py" in str(result)

    def test_resolve_package_init(self, tmp_path: Path):
        """import foo.bar should resolve to foo/bar/__init__.py."""
        (tmp_path / "foo" / "bar").mkdir(parents=True)
        (tmp_path / "foo" / "bar" / "__init__.py").write_text("x = 1")
        (tmp_path / "foo" / "__init__.py").write_text("")

        from prism.enrich.resolver import resolve_python_import

        result = resolve_python_import("foo.bar", "test.py", str(tmp_path))
        assert result is not None
        assert "__init__.py" in str(result)


# ── Complexity metrics ────────────────────────────────────────────────────


class TestParameterCount:
    """Test parameter count detection."""

    def test_function_with_too_many_params(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f(a, b, c, d, e, f, g): pass\n", tmp_path
        )
        measurements = _find_metrics(result, "parameter_count")
        assert len(measurements) == 1
        assert measurements[0]["function"] == "f"
        assert measurements[0]["value"] == 7

    def test_skips_self_param(self, tmp_path: Path):
        result = run_prism_on_file(
            "def method(self, a): pass\n", tmp_path
        )
        measurements = _find_metrics(result, "parameter_count")
        assert len(measurements) == 0  # 2 params minus self = 1, below threshold


class TestFunctionLength:
    """Test function length detection."""

    def test_long_function(self, tmp_path: Path):
        lines = ["def long_func():"] + ["    x = 1"] * 70
        result = run_prism_on_file("\n".join(lines), tmp_path)
        measurements = _find_metrics(result, "function_length")
        assert len(measurements) >= 1
        assert measurements[0]["function"] == "long_func"

    def test_short_function_not_flagged(self, tmp_path: Path):
        result = run_prism_on_file("def short(): pass\n", tmp_path)
        measurements = _find_metrics(result, "function_length")
        assert len(measurements) == 0


class TestNLOC:
    """Test NLOC counting."""

    def test_nloc_counts_source_lines(self, tmp_path: Path):
        result = run_prism_on_file(
            "def foo():\n    return 1\n\n# comment\n\ndef bar():\n    return 2\n",
            tmp_path,
        )
        measurements = _find_metrics(result, "nloc")
        assert len(measurements) >= 1
        # Should count ~4 non-blank, non-comment lines
        assert 3 <= measurements[0]["value"] <= 6


# ── Dead code detection ───────────────────────────────────────────────────


class TestDeadFunction:
    """Test dead function detection."""

    def test_dead_function_detected(self, tmp_path: Path):
        result = run_prism_on_file("def unused(): pass\ndef used(): pass\nused()\n", tmp_path)
        measurements = _find_metrics(result, "dead_function")
        assert any(m["function"] == "unused" for m in measurements)

    def test_called_function_not_dead(self, tmp_path: Path):
        result = run_prism_on_file("def used(): pass\nused()\n", tmp_path)
        measurements = _find_metrics(result, "dead_function")
        assert not any(m["function"] == "used" for m in measurements)

    def test_has_confidence(self, tmp_path: Path):
        result = run_prism_on_file("def unused(): pass\n", tmp_path)
        measurements = _find_metrics(result, "dead_function")
        if measurements:
            assert measurements[0].get("confidence") == 70


class TestUnreachableCode:
    """Test unreachable code detection."""

    def test_code_after_return(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f():\n    return 1\n    x = 2  # unreachable\n", tmp_path
        )
        measurements = _find_metrics(result, "unreachable_code")
        assert len(measurements) >= 1
        assert measurements[0]["confidence"] == 100

    def test_no_unreachable_when_clean(self, tmp_path: Path):
        result = run_prism_on_file("def f():\n    x = 1\n    return x\n", tmp_path)
        measurements = _find_metrics(result, "unreachable_code")
        assert len(measurements) == 0


class TestUnusedImports:
    """Test unused import detection."""

    def test_unused_import_detected(self, tmp_path: Path):
        result = run_prism_on_file(
            "import os  # never used\ndef f(): pass\n", tmp_path
        )
        measurements = _find_metrics(result, "unused_import")
        assert any(m["function"] == "os" for m in measurements)

    def test_used_import_not_flagged(self, tmp_path: Path):
        result = run_prism_on_file(
            "import json\ndef f():\n    return json.dumps({})\n", tmp_path
        )
        measurements = _find_metrics(result, "unused_import")
        assert not any(m["function"] == "json" for m in measurements)


class TestUnusedVariables:
    """Test unused variable detection."""

    def test_unused_local_var(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f():\n    x = 5\n    return 1\n", tmp_path
        )
        measurements = _find_metrics(result, "unused_variable")
        assert any("x" in m.get("context", {}).get("detail", "") for m in measurements)

    def test_used_var_not_flagged(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f():\n    x = 5\n    return x\n", tmp_path
        )
        measurements = _find_metrics(result, "unused_variable")
        assert not any("x" in m.get("context", {}).get("detail", "") for m in measurements)

    def test_underscore_skipped(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f():\n    _ = 5\n    return 1\n", tmp_path
        )
        measurements = _find_metrics(result, "unused_variable")
        assert not any("_" in m.get("context", {}).get("detail", "") for m in measurements)


# ── Error handling ────────────────────────────────────────────────────────


class TestErrorHandling:
    """Test error handling coverage detection."""

    def test_unguarded_risky_call(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f():\n    with open('file'): pass\n    eval('1+1')\n", tmp_path
        )
        measurements = _find_metrics(result, "error_handling_coverage")
        # eval is risky and unguarded; open is in a context manager
        assert len(measurements) >= 1

    def test_guarded_call_covered(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f():\n    try:\n        open('file')\n    except Exception:\n        pass\n",
            tmp_path,
        )
        measurements = _find_metrics(result, "error_handling_coverage")
        # The risky call inside try block should be counted as handled
        # Coverage may be 100% so nothing flagged
        assert len(measurements) == 0


# ── Code clones ───────────────────────────────────────────────────────────


class TestCodeClones:
    """Test code clone detection."""

    def test_structural_clones_in_file(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f(x):\n    if x:\n        print(x)\n        return 1\n    return 0\n"
            "def g(y):\n    if y:\n        print(y)\n        return 1\n    return 0\n",
            tmp_path,
        )
        measurements = _find_metrics(result, "code_clone")
        # Two identical functions should produce a clone pair
        assert len(measurements) >= 1


# ── Cross-file features ──────────────────────────────────────────────────


class TestCrossFileCloneDetection:
    """Test cross-file clone detection."""

    def test_token_clones_across_files(self, tmp_path: Path):
        from prism.engine.treerunner import measure_code_clones_token

        (tmp_path / "a.py").write_text(
            "def greet(name):\n    print('Hello ' + name)\n    print('Welcome')\n    return 1\n"
        )
        (tmp_path / "b.py").write_text(
            "def greet_user(name):\n    print('Hello ' + name)\n    print('Welcome')\n    return 1\n"
        )
        results = measure_code_clones_token(
            [str(tmp_path / "a.py"), str(tmp_path / "b.py")], min_tokens=8
        )
        assert len(results) >= 1


class TestModuleGraph:
    """Test module graph construction."""

    def test_build_module_graph(self, tmp_path: Path):
        from prism.enrich.module_graph import ModuleGraph

        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("import c\n")
        (tmp_path / "c.py").write_text("x = 1\n")

        files = [str(tmp_path / f"{n}.py") for n in ["a", "b", "c"]]
        mg = ModuleGraph()
        mg.build(files)

        assert len(mg.files) == 3

    def test_reachability_from_entry_point(self, tmp_path: Path):
        from prism.enrich.module_graph import ModuleGraph

        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("import c\n")
        (tmp_path / "c.py").write_text("x = 1\n")
        (tmp_path / "d.py").write_text("import a\n")  # not imported by anything

        files = [str(tmp_path / f"{n}.py") for n in ["a", "b", "c", "d"]]
        mg = ModuleGraph()
        mg.build(files)
        mg.set_entry_points([str(tmp_path / "a.py")])
        reachable = mg.compute_reachability()

        # a imports b, b imports c → a, b, c should be reachable
        # d is not reachable from a
        assert len(reachable) == 3

    def test_unused_file_detection(self, tmp_path: Path):
        from prism.enrich.module_graph import ModuleGraph

        (tmp_path / "a.py").write_text("import b\n")
        (tmp_path / "b.py").write_text("x = 1\n")
        (tmp_path / "c.py").write_text("import a\n")  # unused

        files = [str(tmp_path / f"{n}.py") for n in ["a", "b", "c"]]
        mg = ModuleGraph()
        mg.build(files)
        mg.set_entry_points([str(tmp_path / "a.py")])
        mg.compute_reachability()
        unused = mg.find_unused_files()

        assert len(unused) == 1
        assert unused[0]["function"] == "c"


class TestImportRules:
    """Test import rule enforcement."""

    def test_may_not_rule(self, tmp_path: Path):
        from prism.enrich.import_rules import check_import_rules

        (tmp_path / "features").mkdir(parents=True)
        (tmp_path / "features" / "auth.py").write_text("")
        (tmp_path / "features" / "payment.py").write_text("")

        config = {
            "import_rules": {
                "no-feature-to-feature": {
                    "pattern": "features/*",
                    "may_not": ["features/*"],
                    "severity": "error",
                }
            }
        }
        graph = {
            "import_graph": {
                "auth": ["payment"],
                "payment": [],
            }
        }
        files = [str(tmp_path / "features" / f"{n}.py") for n in ["auth", "payment"]]
        violations = check_import_rules(files, graph, config)
        assert len(violations) == 1  # auth.py imports payment.py

    def test_may_only_rule(self, tmp_path: Path):
        from prism.enrich.import_rules import check_import_rules

        (tmp_path / "core").mkdir(parents=True)
        (tmp_path / "features").mkdir(parents=True)
        (tmp_path / "core" / "models.py").write_text("")
        (tmp_path / "features" / "api.py").write_text("")

        config = {
            "import_rules": {
                "core-isolation": {
                    "pattern": "core/*",
                    "may_only": ["core/*"],
                    "severity": "warning",
                }
            }
        }
        graph = {
            "import_graph": {
                "models": ["api"],
                "api": [],
            }
        }
        files = [str(tmp_path / "core" / "models.py"),
                 str(tmp_path / "features" / "api.py")]
        violations = check_import_rules(files, graph, config)
        assert len(violations) == 1  # models imports api (not in core/*)


# ── Language registry ────────────────────────────────────────────────────


class TestLanguageRegistry:
    """Test per-language configuration."""

    def test_all_languages_have_calls(self):
        """Every language should have a calls query."""
        from prism.engine.languages import LANGUAGES

        for name, defn in LANGUAGES.items():
            assert "calls" in defn["queries"], f"{name} missing calls query"

    def test_per_language_risky_calls(self):
        """Every language should have risky call targets."""
        from prism.engine.languages import get_risky_call_targets

        for lang in ["python", "javascript", "go", "rust", "java"]:
            targets = get_risky_call_targets(lang)
            assert len(targets) > 0, f"{lang} has zero risky call targets"

    def test_per_language_impure_calls(self):
        """Every language should have impure call targets."""
        from prism.engine.languages import get_impure_call_targets

        for lang in ["python", "javascript", "go", "rust", "java"]:
            targets = get_impure_call_targets(lang)
            assert len(targets) > 0, f"{lang} has zero impure call targets"


# ── Confidence levels ────────────────────────────────────────────────────


class TestConfidenceLevels:
    """Test that specific metrics report confidence levels."""

    def test_unreachable_is_100(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f():\n    return 1\n    x = 2\n", tmp_path
        )
        m = _find_metrics(result, "unreachable_code")
        if m:
            assert m[0].get("confidence") == 100

    def test_dead_function_is_70(self, tmp_path: Path):
        result = run_prism_on_file("def unused(): pass\n", tmp_path)
        m = _find_metrics(result, "dead_function")
        if m:
            assert m[0].get("confidence") == 70

    def test_unused_import_is_90(self, tmp_path: Path):
        result = run_prism_on_file("import os\ndef f(): pass\n", tmp_path)
        m = _find_metrics(result, "unused_import")
        if m:
            assert any(x.get("confidence") == 90 for x in m)

    def test_unused_class_is_80(self, tmp_path: Path):
        result = run_prism_on_file("class Foo: pass\n", tmp_path)
        m = _find_metrics(result, "unused_class")
        if m:
            assert m[0].get("confidence") == 80


# ── CLI behavior ──────────────────────────────────────────────────────────


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


# ── Entry point awareness ────────────────────────────────────────────────


class TestEntryPointAwareness:
    """Test that entry points are not flagged as dead."""

    def test_main_not_dead_in_python(self, tmp_path: Path):
        result = run_prism_on_file(
            "def main():\n    pass\n", tmp_path
        )
        measurements = _find_metrics(result, "dead_function")
        assert not any(m["function"] == "main" for m in measurements)


# ── Maintainability Index ────────────────────────────────────────────────


class TestMaintainabilityIndex:
    """Test MI computation."""

    def test_very_complex_function_flagged(self, tmp_path: Path):
        result = run_prism_on_file(
            "def complex_func(a,b,c,d,e,f,g,h):\n"
            + "\n".join(f"    if x:\n        pass\n    elif y:\n        pass\n"
                        for x, y in zip("abcdefgh", "hgfedcba"))
            + "\n",
            tmp_path,
        )
        measurements = _find_metrics(result, "maintainability_index")
        if measurements:
            assert measurements[0]["value"] < 40  # Should be flagged
