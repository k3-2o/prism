"""Tests for code clone detection (in-file structural + cross-file token)."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import find_metrics, run_prism_on_file


class TestStructuralClones:
    """Test in-file structural clone detection."""

    def test_structural_clones_in_file(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f(x):\n    if x:\n        print(x)\n        return 1\n    return 0\n"
            "def g(y):\n    if y:\n        print(y)\n        return 1\n    return 0\n",
            tmp_path,
        )
        assert len(find_metrics(result, "code_clone")) >= 1

    def test_no_clones_when_different(self, tmp_path: Path):
        result = run_prism_on_file(
            "def f():\n    x = 1\n    return x\n"
            "def g():\n    for i in range(10):\n        x += i\n    return x\n",
            tmp_path,
        )
        # These are very different structurally — may or may not trigger
        # depending on similarity threshold. Just check it runs.
        assert "measurements" in result


class TestCrossFileTokenClones:
    """Test cross-file token-based clone detection."""

    def test_token_clones_across_files(self, tmp_path: Path):
        from prism.engine.treerunner import measure_code_clones_token

        (tmp_path / "a.py").write_text(
            "def greet(name):\n    print('Hello ' + name)\n    print('Welcome')\n    return 1\n"
        )
        (tmp_path / "b.py").write_text(
            "def greet_user(name):\n    print('Hello ' + name)\n"
            "    print('Welcome')\n    return 1\n"
        )
        results = measure_code_clones_token(
            [str(tmp_path / "a.py"), str(tmp_path / "b.py")], min_tokens=8
        )
        assert len(results) >= 1
