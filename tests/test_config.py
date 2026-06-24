"""Tests for configuration loading."""

from __future__ import annotations


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
