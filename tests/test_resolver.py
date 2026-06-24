"""Tests for import path resolution (Python)."""

from __future__ import annotations

from pathlib import Path


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

    def test_resolve_src_layout(self, tmp_path: Path):
        """Import should resolve under src/ directory for src-layout projects."""
        (tmp_path / "src" / "mypkg").mkdir(parents=True)
        (tmp_path / "src" / "mypkg" / "module.py").write_text("x = 1")

        from prism.enrich.resolver import resolve_python_import

        result = resolve_python_import("mypkg.module", "src/test.py", str(tmp_path))
        assert result is not None
        assert "module.py" in str(result)
