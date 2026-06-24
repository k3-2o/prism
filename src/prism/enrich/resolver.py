"""Import path resolver — resolves import statements to file paths.

Currently supports Python only. JS/TS, Go, Rust support added as needed.

Resolution rules (Python):
  - `import foo` → `foo.py` or `foo/__init__.py`
  - `import foo.bar` → `foo/bar.py` or `foo/bar/__init__.py`
  - `from foo import bar` → `foo/bar.py` or `foo/__init__.py` (bar is a symbol)
  - `from . import foo` → relative to current file
  - `from ..bar import baz` → relative with parent directory
"""

from __future__ import annotations

from pathlib import Path


def resolve_python_import(
    import_text: str,
    from_file: str,
    project_root: str,
    is_from_import: bool = False,
) -> str | None:
    """Resolve a Python import statement to an actual file path.

    Args:
        import_text: The text of the import (e.g., "foo.bar" or ".module").
        from_file: The file that contains the import statement.
        project_root: The project root directory.
        is_from_import: True if this is a 'from X import Y' statement.

    Returns:
        Resolved file path, or None if unresolvable (stdlib, third-party, etc.).
    """
    project_root = str(Path(project_root).resolve())
    from_dir = Path(from_file).resolve().parent

    # Handle relative imports
    if import_text.startswith("."):
        return _resolve_relative_python(import_text, from_dir, project_root)

    # Handle absolute imports
    return _resolve_absolute_python(import_text, project_root)


def _resolve_relative_python(
    import_text: str,
    from_dir: Path,
    project_root: str,
) -> str | None:
    """Resolve a relative Python import like '.foo' or '..bar.baz'."""
    # Count leading dots to determine parent directory depth
    leading_dots = 0
    for ch in import_text:
        if ch == ".":
            leading_dots += 1
        else:
            break

    # The module path after the dots
    module_path = import_text[leading_dots:]

    # Navigate up from from_dir
    search_dir = from_dir
    for _ in range(leading_dots - 1):
        search_dir = search_dir.parent

    resolved = _find_python_module(module_path, search_dir, project_root)
    return resolved


def _resolve_absolute_python(
    import_text: str,
    project_root: str,
) -> str | None:
    """Resolve an absolute Python import like 'foo.bar' to a file path."""
    resolved = _find_python_module(import_text, Path(project_root), project_root)
    return resolved


def _find_python_module(
    module_path: str,
    search_dir: Path,
    project_root: str,
) -> str | None:
    """Try to find a module file given a dotted path and search directory.

    E.g., 'foo.bar' → search_dir/foo/bar.py or search_dir/foo/bar/__init__.py
    Also checks under src/ and lib/ for src-layout projects.
    """
    parts = module_path.split(".") if module_path else []

    # Directories to search (in priority order)
    search_dirs = [search_dir]
    # Also check src/ and lib/ directories if search_dir is project root
    for subdir in ["src", "lib", "python"]:
        candidate = search_dir / subdir
        if candidate.is_dir():
            search_dirs.append(candidate)

    for sdir in search_dirs:
        result = _try_find_in_dir(parts, sdir, project_root)
        if result:
            return result

    return None


def _try_find_in_dir(parts: list[str], search_dir: Path, project_root: str) -> str | None:
    """Try to find a module in a single search directory."""
    # Try progressively shorter paths (full path first, then shorter)
    for i in range(len(parts), 0, -1):
        sub_parts = parts[:i]

        # Build directory path for the package
        pkg_dir = search_dir.joinpath(*sub_parts)

        # Check if it's a file
        pkg_file = pkg_dir.with_suffix(".py")
        if pkg_file.exists():
            try:
                pkg_file.resolve().relative_to(project_root)
                return str(pkg_file)
            except ValueError:
                continue

        # Check if it's a package (directory with __init__.py)
        init_file = pkg_dir / "__init__.py"
        if init_file.exists():
            try:
                init_file.resolve().relative_to(project_root)
                return str(init_file)
            except ValueError:
                continue

        # Check if it's a directory without __init__.py
        if pkg_dir.is_dir():
            try:
                pkg_dir.resolve().relative_to(project_root)
                # Namespace package — might have __init__ elsewhere, skip
                return None
            except ValueError:
                continue

    return None


def resolve_import(
    import_statement_data: dict,
    from_file: str,
    project_root: str,
    language: str,
) -> str | None:
    """Resolve an import statement to a file path.

    Args:
        import_statement_data: Dict with keys 'text', 'is_from_import', etc.
        from_file: The file containing this import.
        project_root: The project root directory.
        language: The source language (e.g., 'python', 'javascript').

    Returns:
        Resolved file path, or None if unresolvable.
    """
    text = import_statement_data.get("text", "")
    is_from = import_statement_data.get("is_from_import", False)

    if language == "python":
        return resolve_python_import(text, from_file, project_root, is_from)

    # For other languages, fall back to simple filename matching
    return _resolve_simple_filename(text, from_file, project_root)


def _resolve_simple_filename(import_text: str, from_file: str, project_root: str) -> str | None:
    """Simple filename-based resolution for non-Python languages.

    Handles: './foo', '../bar', 'module/path', etc.
    """
    p = Path(import_text)

    # Relative path
    if import_text.startswith((".", "/")):
        from_dir = Path(from_file).resolve().parent
        candidate = (from_dir / p).resolve()
    else:
        candidate = (Path(project_root) / p).resolve()

    # Check common extensions
    for ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".php"]:
        with_ext = candidate.with_suffix(ext)
        if with_ext.exists():
            try:
                with_ext.relative_to(project_root)
                return str(with_ext)
            except ValueError:
                return None

    return None
