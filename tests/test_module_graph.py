"""Tests for module graph: build, reachability, unused files."""

from __future__ import annotations

from pathlib import Path


class TestModuleGraph:
    """Test module graph construction and analysis."""

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

        # a imports b, b imports c → a, b, c reachable; d is not
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

    def test_unused_file_skips_init(self, tmp_path: Path):
        """__init__.py should not be reported as unused."""
        from prism.enrich.module_graph import ModuleGraph

        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("")
        (tmp_path / "main.py").write_text("import pkg\n")

        files = [str(tmp_path / "pkg" / "__init__.py"), str(tmp_path / "main.py")]
        mg = ModuleGraph()
        mg.build(files)
        mg.set_entry_points([str(tmp_path / "main.py")])
        mg.compute_reachability()
        unused = mg.find_unused_files()

        assert len(unused) == 0  # __init__ should be skipped
