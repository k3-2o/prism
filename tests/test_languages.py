"""Tests for language registry."""

from __future__ import annotations


class TestLanguageRegistry:
    """Test per-language configuration."""

    def test_all_languages_have_calls(self):
        """Every language should have a calls query."""
        from prism.engine.languages import LANGUAGES

        for name, defn in LANGUAGES.items():
            assert "calls" in defn["queries"], f"{name} missing calls query"

    def test_all_languages_have_functions(self):
        """Every language should have a functions query."""
        from prism.engine.languages import LANGUAGES

        for name, defn in LANGUAGES.items():
            assert "functions" in defn["queries"], f"{name} missing functions query"

    def test_all_languages_have_imports(self):
        """Every language should have an imports query."""
        from prism.engine.languages import LANGUAGES

        for name, defn in LANGUAGES.items():
            assert "imports" in defn["queries"], f"{name} missing imports query"

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

    def test_per_language_entry_points(self):
        """Every language should have entry points."""
        from prism.engine.languages import get_entry_points

        for lang in ["python", "javascript", "go", "rust", "java"]:
            points = get_entry_points(lang)
            assert len(points) > 0, f"{lang} has zero entry points"
