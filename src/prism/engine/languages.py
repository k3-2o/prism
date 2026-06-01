"""Language registry — maps file extensions to tree-sitter grammars, queries, and thresholds.

Each language entry defines everything needed to parse and measure code in that
language: which tree-sitter grammar to load, what AST queries to run, what node
type names to look for, and what thresholds to apply.

Adding a new language:
  1. `uv add tree-sitter-<lang>`  (install the PyPI package)
  2. Add an entry to LANGUAGES dict below
  3. Write tree-sitter queries for functions, calls, imports
  4. Set appropriate thresholds

The queries use capture names (@func, @name, @params) that are language-agnostic
even though the AST node types differ.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from tree_sitter import Language, Parser, Query


# ── Type aliases ────────────────────────────────────────────────────────

LanguageDef = dict[str, Any]


def _make_parser(import_path: str, lang_attr: str = "language") -> Parser:
    """Dynamically import a tree-sitter language package and create a parser."""
    import importlib

    mod = importlib.import_module(import_path)
    lang_fn = getattr(mod, lang_attr)
    lang = Language(lang_fn())
    parser = Parser()
    parser.language = lang
    return parser


def _build_query(lang: Language, query_str: str) -> Query:
    return Query(lang, query_str)


# ── Language definitions ────────────────────────────────────────────────

LANGUAGES: dict[str, LanguageDef] = {}


def _register(name: str, defn: LanguageDef) -> None:
    defn["name"] = name
    LANGUAGES[name] = defn


# ── Python ───────────────────────────────────────────────────────────────

_register(
    "python",
    {
        "extensions": [".py"],
        "import_path": "tree_sitter_python",
        "lang_attr": "language",
        "thresholds": {
            "parameter_count": 6,
            "nesting_depth": 4,
            "function_length": 60,
            "cyclomatic_complexity": 10,
            "cognitive_complexity": 15,
            "boolean_complexity": 3,
            "god_class_methods": 10,
            "god_class_deps": 6,
            "god_class_lines": 100,
        },
        "queries": {
            "functions": """
            (function_definition
              name: (identifier) @name
              parameters: (parameters) @params) @func
        """,
            "calls": """
            (call function: (identifier) @name) @call
        """,
            "imports": """
            (import_statement name: (dotted_name) @name)
            (import_from_statement module_name: (dotted_name) @name)
        """,
            "classes": """
            (class_definition
              name: (identifier) @name
              body: (block) @body) @class
        """,
        },
        "ignore_names": [],
        # Node types that count as +1 to cyclomatic complexity
        "decision_types": [
            "if_statement",
            "elif_clause",
            "for_statement",
            "while_statement",
            "except_clause",
            "boolean_operator",
        ],
        # Node types inside conditions that represent boolean operators
        "boolean_operator_types": ["and", "or"],
    },
)

# ── JavaScript ───────────────────────────────────────────────────────────

_register(
    "javascript",
    {
        "extensions": [".js", ".jsx", ".mjs", ".cjs"],
        "import_path": "tree_sitter_javascript",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 50},
        "queries": {
            "functions": """
            (function_declaration
              name: (identifier) @name
              parameters: (formal_parameters) @params) @func
            (arrow_function
              parameters: (formal_parameters) @params) @func
            (method_definition
              name: (property_identifier) @name
              parameters: (formal_parameters) @params) @func
        """,
            "calls": """
            (call_expression function: (identifier) @name) @call
            (call_expression function: (member_expression property: (property_identifier) @name)) @call
        """,
            "imports": """
            (import_statement source: (string) @name)
        """,
        },
        "ignore_names": ["constructor"],
    },
)

# ── TypeScript ───────────────────────────────────────────────────────────

_register(
    "typescript",
    {
        "extensions": [".ts", ".tsx", ".mts", ".cts"],
        "import_path": "tree_sitter_typescript",
        "lang_attr": "language_typescript",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 50},
        "queries": {
            "functions": """
            (function_declaration
              name: (identifier) @name
              parameters: (formal_parameters) @params) @func
            (arrow_function
              parameters: (formal_parameters) @params) @func
            (method_definition
              name: (property_identifier) @name
              parameters: (formal_parameters) @params) @func
        """,
            "calls": """
            (call_expression function: (identifier) @name) @call
            (call_expression function: (member_expression property: (property_identifier) @name)) @call
        """,
            "imports": """
            (import_statement source: (string) @name)
        """,
        },
        "ignore_names": ["constructor"],
    },
)

# ── Go ───────────────────────────────────────────────────────────────────

_register(
    "go",
    {
        "extensions": [".go"],
        "import_path": "tree_sitter_go",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 50},
        "queries": {
            "functions": """
            (function_declaration
              name: (identifier) @name
              parameters: (parameter_list) @params) @func
            (method_declaration
              name: (field_identifier) @name
              parameters: (parameter_list) @params) @func
        """,
            "calls": """
            (call_expression function: (identifier) @name) @call
            (call_expression function: (selector_expression field: (field_identifier) @name)) @call
        """,
            "imports": """
            (import_spec (interpreted_string_literal) @name)
        """,
        },
        "ignore_names": ["init", "main"],
    },
)

# ── Rust ─────────────────────────────────────────────────────────────────

_register(
    "rust",
    {
        "extensions": [".rs"],
        "import_path": "tree_sitter_rust",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 60},
        "queries": {
            "functions": """
            (function_item
              name: (identifier) @name
              parameters: (parameters) @params) @func
        """,
            "calls": """
            (call_expression function: (identifier) @name) @call
            (call_expression function: (scoped_identifier name: (identifier) @name)) @call
        """,
            "imports": """
            (use_declaration (scoped_identifier (identifier) @name))
            (use_declaration (use_list (identifier) @name))
        """,
        },
        "ignore_names": ["main"],
    },
)

# ── Java ─────────────────────────────────────────────────────────────────

_register(
    "java",
    {
        "extensions": [".java"],
        "import_path": "tree_sitter_java",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 50},
        "queries": {
            "functions": "(method_declaration name: (identifier) @name parameters: (formal_parameters) @params) @func",
            "calls": "(method_invocation name: (identifier) @name) @call",
            "imports": "(import_declaration (scoped_identifier (identifier) @name))",
        },
        "ignore_names": [],
    },
)

# ── Ruby ─────────────────────────────────────────────────────────────────

_register(
    "ruby",
    {
        "extensions": [".rb", ".rake", ".gemspec"],
        "import_path": "tree_sitter_ruby",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 40},
        "queries": {
            "functions": "(method name: (identifier) @name parameters: (method_parameters) @params) @func",
            "calls": "(call method: (identifier) @name) @call",
            "imports": "(call method: (identifier) @name)",
        },
        "ignore_names": ["initialize"],
    },
)

# ── PHP ──────────────────────────────────────────────────────────────────

_register(
    "php",
    {
        "extensions": [".php"],
        "import_path": "tree_sitter_php",
        "lang_attr": "language_php",
        "thresholds": {"parameter_count": 5, "nesting_depth": 4, "function_length": 50},
        "queries": {
            "functions": "(function_definition name: (name) @name parameters: (formal_parameters) @params) @func",
            "calls": "(function_call_expression function: (qualified_name (name) @name)) @call",
            "imports": "(namespace_use_clause (qualified_name (name) @name))",
        },
        "ignore_names": ["__construct"],
    },
)

# ── C ────────────────────────────────────────────────────────────────────

_register(
    "c",
    {
        "extensions": [".c", ".h"],
        "import_path": "tree_sitter_c",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 6, "nesting_depth": 4, "function_length": 40},
        "queries": {
            "functions": """
            (function_definition
              declarator: (function_declarator
                declarator: (identifier) @name
                parameters: (parameter_list) @params)) @func
        """,
            "calls": """
            (call_expression function: (identifier) @name) @call
        """,
            "imports": """
            (preproc_include path: (string_literal) @name)
            (preproc_include path: (system_lib_string) @name)
        """,
        },
        "ignore_names": ["main"],
    },
)

# ── C++ ──────────────────────────────────────────────────────────────────

_register(
    "cpp",
    {
        "extensions": [".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx"],
        "import_path": "tree_sitter_cpp",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 6, "nesting_depth": 4, "function_length": 40},
        "queries": {
            "functions": """
            (function_definition
              declarator: (function_declarator
                declarator: (identifier) @name
                parameters: (parameter_list) @params)) @func
        """,
            "calls": """
            (call_expression function: (identifier) @name) @call
        """,
            "imports": """
            (preproc_include path: (string_literal) @name)
            (preproc_include path: (system_lib_string) @name)
        """,
        },
        "ignore_names": ["main"],
    },
)

# ── HCL (Terraform) ──────────────────────────────────────────────────────

_register(
    "hcl",
    {
        "extensions": [".tf", ".tfvars", ".hcl"],
        "import_path": "tree_sitter_hcl",
        "lang_attr": "language",
        "thresholds": {"parameter_count": 8, "nesting_depth": 3, "function_length": 40},
        "queries": {
            "functions": "(block (identifier) @name) @func",
            "calls": "(function_call (identifier) @name) @call",
            "imports": "(function_call (identifier) @name) @call",
        },
        "ignore_names": [],
    },
)

# ── Zig ──────────────────────────────────────────────────────────────────

_register(
    "zig",
    {
        "extensions": [".zig"],
        "import_path": "tree_sitter_zig",
        "lang_attr": "language",
        "thresholds": {
            "parameter_count": 5,
            "nesting_depth": 4,
            "function_length": 50,
            "cyclomatic_complexity": 10,
            "cognitive_complexity": 15,
            "boolean_complexity": 3,
            "god_class_methods": 10,
            "god_class_deps": 6,
            "god_class_lines": 100,
        },
        "queries": {
            "functions": "(function_declaration name: (identifier) @name (parameters) @params) @func",
            "calls": "(call_expression (identifier) @name) @call",
            "imports": "(builtin_function (builtin_identifier) @name)",
        },
        "ignore_names": ["main"],
        "decision_types": [
            "if_expression",
            "else_if",
            "for_expression",
            "while_expression",
            "catch_expression",
            "try_expression",
            "switch_expression",
            "boolean_operator",
        ],
        "boolean_operator_types": ["and", "or"],
    },
)

# ── Extension-to-language map (built lazily) ─────────────────────────────

_EXT_TO_LANG: dict[str, str] | None = None


def extension_to_language(ext: str) -> str | None:
    """Return the language name for a file extension, or None."""
    global _EXT_TO_LANG
    if _EXT_TO_LANG is None:
        _EXT_TO_LANG = {}
        for lang_name, defn in LANGUAGES.items():
            for e in defn["extensions"]:
                # Already registered? The first registration wins (priority order)
                if e not in _EXT_TO_LANG:
                    _EXT_TO_LANG[e] = lang_name
    return _EXT_TO_LANG.get(ext.lower())


# ── Parser cache (lazy, per-language) ────────────────────────────────────

_PARSERS: dict[str, Parser] = {}
_QUERIES_CACHE: dict[str, dict[str, Query]] = {}


def get_parser(lang: str) -> Parser:
    """Get or create a parser for the given language."""
    if lang not in _PARSERS:
        defn = LANGUAGES.get(lang)
        if not defn:
            raise ValueError(f"Unknown language: {lang}")
        _PARSERS[lang] = _make_parser(defn["import_path"], defn["lang_attr"])
    return _PARSERS[lang]


def get_queries(lang: str) -> dict[str, Query]:
    """Get or create compiled queries for the given language."""
    if lang not in _QUERIES_CACHE:
        defn = LANGUAGES.get(lang)
        if not defn:
            raise ValueError(f"Unknown language: {lang}")
        parser = get_parser(lang)
        lang_obj = parser.language
        queries: dict[str, Query] = {}
        for qname, qstr in defn["queries"].items():
            queries[qname] = Query(lang_obj, qstr)
        _QUERIES_CACHE[lang] = queries
    return _QUERIES_CACHE[lang]


def get_thresholds(lang: str) -> dict[str, int]:
    """Get thresholds for the given language."""
    defn = LANGUAGES.get(lang)
    if not defn:
        raise ValueError(f"Unknown language: {lang}")
    return dict(defn["thresholds"])


def get_ignore_names(lang: str) -> list[str]:
    """Get function names to ignore for the given language."""
    defn = LANGUAGES.get(lang)
    if not defn:
        return []
    return list(defn.get("ignore_names", []))


def supported_languages() -> list[str]:
    """Return list of all registered language names."""
    return list(LANGUAGES.keys())


def supported_extensions() -> list[str]:
    """Return list of all registered file extensions."""
    exts: list[str] = []
    for defn in LANGUAGES.values():
        exts.extend(defn["extensions"])
    return sorted(set(exts))
