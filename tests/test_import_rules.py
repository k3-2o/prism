"""Tests for import rule enforcement."""

from __future__ import annotations

from pathlib import Path


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
        graph = {"import_graph": {"auth": ["payment"], "payment": []}}
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
        graph = {"import_graph": {"models": ["api"], "api": []}}
        files = [
            str(tmp_path / "core" / "models.py"),
            str(tmp_path / "features" / "api.py"),
        ]
        violations = check_import_rules(files, graph, config)
        assert len(violations) == 1  # models imports api (not in core/*)

    def test_no_rules_no_violations(self, tmp_path: Path):
        from prism.enrich.import_rules import check_import_rules

        (tmp_path / "a.py").write_text("")
        violations = check_import_rules([str(tmp_path / "a.py")], {"import_graph": {"a": []}}, {})
        assert len(violations) == 0
