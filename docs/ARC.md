# PRISM — Structural Code Analysis for AI Agent Loops

**Version:** 0.3.0
**Status:** Production-grade, 52 tests, 10 phases complete
**Language:** Python 3.12+
**Package Manager:** uv (Astral)
**Linter/Formatter:** ruff (Astral)

---

## Table of Contents

1. [What Is PRISM](#1-what-is-prism)
2. [Quick Start](#2-quick-start)
3. [Architecture Overview](#3-architecture-overview)
4. [File Reference](#4-file-reference)
5. [CLI Reference](#5-cli-reference)
6. [Output Format](#6-output-format)
7. [Metrics Reference](#7-metrics-reference)
8. [Config](#8-config)
9. [Speed](#9-speed)
10. [Architecture Decision Record](#10-architecture-decision-record)
11. [Known Issues](#11-known-issues)
12. [Future Work](#12-future-work)

---

## 1. What Is PRISM

PRISM is a CLI tool that produces structured JSON about code across 12 languages. Single tree-sitter engine, no external runtime dependencies.

### Supported Languages

| Language | Extensions |
|---|---|
| Python | `.py` |
| JavaScript | `.js .jsx .mjs .cjs` |
| TypeScript | `.ts .tsx .mts .cts` |
| Go | `.go` |
| Rust | `.rs` |
| Java | `.java` |
| Ruby | `.rb .rake .gemspec` |
| PHP | `.php` |
| C | `.c .h` |
| C++ | `.cpp .cc .cxx .hpp .hh .hxx` |
| HCL | `.tf .tfvars .hcl` |
| Zig | `.zig` |

---

## 2. Quick Start

```bash
git clone <repo-url> ~/prism && cd ~/prism
uv sync
uv tool install .
prism src/file.py       # single file
prism .                 # full project
prism . --visualize     # dependency graph
prism . --filter dead_function,unused_import  # focused view
```

---

## 3. Architecture Overview

```
prism <path>
  │
  ├─ parse_file() → tree-sitter AST
  │    └─ per-file measurements (25+ metrics)
  │
  ├─ run_project()
  │    ├─ cyclic imports (resolved paths, full cycle output)
  │    ├─ module coupling (Ca/Ce, instability)
  │    ├─ cross-file clones (structural + token-based)
  │    ├─ ModuleGraph → BFS reachability
  │    │    ├─ unused files
  │    │    └─ cross-file dead functions
  │    └─ import rule enforcement
  │
  ├─ caller enrichment (cross-file callers)
  │
  └─ output formatting (grouped by file, summary)
```

### File Reference

```
src/prism/
  main.py              CLI entry point
  config.py             TOML config loading
  engine/
    languages.py        12 languages: queries, thresholds, risky calls, entry points
    treerunner.py       All measurement functions (25+ metrics, 2600 loc)
  enrich/
    enricher.py         Cross-file caller discovery
    resolver.py         Python import path resolution
    module_graph.py     Import graph + BFS reachability
    import_rules.py     Architecture boundary enforcement
  output/
    viz.py              Graphviz DOT generator
tests/
  conftest.py           Shared helpers
  test_*.py             10 domain-specific test files (52 tests)
```

---

## 4. CLI Reference

```
prism PATH [OPTIONS]
```

| Flag | Description |
|---|---|
| `PATH` | File or directory to analyze |
| `--config PATH` | Path to .prism.toml config file |
| `--entry-points NAME` | Mark function as entry point (repeatable) |
| `--filter metric1,metric2` | Only show specific metric types |
| `--compact` | One line per finding, machine-readable |
| `--visualize` | Generate dependency graph DOT file |
| `--visualize-format dot\|svg\|png` | Graph output format (requires graphviz) |

---

## 5. Output Format

Structured JSON grouped by file:

```json
{
  "prism": {"version": "0.3.0", "entry_points": ["main"]},
  "project": {
    "root": ".",
    "primary_language": "python",
    "files_scanned": 14,
    "total_nloc": 3592,
    "languages": {"python": 14}
  },
  "summary": {
    "findings": 454,
    "by_metric": {"code_clone": 112, "dead_function": 32, ...}
  },
  "files": {
    "src/prism/main.py": {
      "nloc": 263,
      "language": "python",
      "findings": [
        {
          "metric": "dead_function",
          "function": "cli",
          "line": 184,
          "confidence": 70,
          "detail": "no callers in any project file",
          "callers": [
            {"function": "...", "file": "...", "line": 1}
          ]
        }
      ]
    }
  },
  "import_graph": {"main": ["config", "languages", "treerunner"]}
}
```

Compact mode (`--compact`):
```
src/prism/config.py: f=get_entry_points m=dead_function l=103 c=70 v=0
```

---

## 6. Metrics Reference

### Complexity
| Metric | Description | Confidence |
|---|---|---|
| `cyclomatic_complexity` | Decision points per function | — |
| `cognitive_complexity` | Nesting-weighted decision count | — |
| `boolean_complexity` | Conditions in single `if` expression | — |
| `nesting_depth` | Maximum AST control-structure depth | — |
| `nloc` | Non-blank, non-comment source lines | — |
| `maintainability_index` | 100 − (CC×3 + nesting×5 + params×2 + len÷10) | — |

### Size
| Metric | Description |
|---|---|
| `function_length` | Lines per function |
| `parameter_count` | Arguments per function (excl. self/cls/this) |
| `import_depth` | Depth of dotted imports (>3 flagged) |

### Architecture
| Metric | Description |
|---|---|
| `god_class` | Classes with too many methods/lines/deps |
| `module_instability` | Ca/Ce coupling ratio (>0.8 or <0.2 flagged) |
| `cyclic_import` | Import cycles with full path output |
| `import_rule_violation` | Custom architecture rule violations |

### Dead Code
| Metric | Description | Confidence |
|---|---|---|
| `dead_function` | No callers in any project file | 70% |
| `unused_export` | JS/TS export with no cross-file consumers | 60% |
| `unused_import` | Imported name never referenced | 90% |
| `unused_variable` | Local variable assigned but never read | 60% |
| `unused_class` | Class defined but never referenced | 80% |
| `unreachable_code` | Code after return/break/raise/throw | 100% |
| `unused_file` | File not reachable from any entry point | 80% |

### Risk
| Metric | Description |
|---|---|
| `error_handling_coverage` | Ratio of guarded/total risky calls |
| `function_impurity` | Module var mutation, param mutation, impure calls (interprocedural) |

### Clones
| Metric | Description |
|---|---|
| `code_clone` | Structural (AST-based) or token-based, in-file + cross-file |

### Change
| Metric | Description |
|---|---|
| `churn_hotspot` | Complexity × commit frequency (>2.0 flagged) |
| `diff_function_added` | Function present but not in git HEAD |
| `diff_function_removed` | Function in HEAD but gone |
| `diff_function_changed` | Function with changed params/complexity |

---

## 7. Config

Optional `.prism.toml` in project root or `~/.prism/config.toml`:

```toml
[project]
entry_points = ["main", "handler", "app"]

[dead_code]
whitelist = { "register_routes" = "Called by framework at import time" }

[complexity]
cyclomatic_threshold = 10
clone_similarity = 0.8

[import_rules]
"features-no-features" = { pattern = "features/*", may_not = ["features/*"], severity = "error" }
"core-isolation" = { pattern = "core/*", may_only = ["core/*"], severity = "warning" }
```

---

## 8. Speed

| Target | Time |
|---|---|
| Single file (~200 loc) | ~1s |
| PRISM's own codebase (14 files, 3.5K loc) | ~13s |
| Medium project (1.2K files) | ~13s |

Bottleneck: churn hotspots (git history lookup per file) and module graph (parses all files).

---

## 9. Architecture Decision Record

- **ADR-1: No Auto-Fix** — PRISM is a counter, not a fixer. It reports measurements. Tools like ruff/eslint/knip handle fixing.
- **ADR-2: Tree-sitter Only** — No semgrep, no external analysis engines. Pure tree-sitter AST queries. Removed in v0.3.0.
- **ADR-3: JSON Output** — Structured JSON with optional compact mode. No plain-text/table output.
- **ADR-4: Per-Language Configuration** — Thresholds, risky call lists, and entry points are per-language in `languages.py`.

---

## 10. Known Issues

- **Aliased imports**: `from foo import bar as baz` — cross-file dead function detection uses definition names, not import aliases. Functions imported under aliases may appear dead.
- **Dynamic calls**: `getattr(obj, "method")()`, `__import__()`, reflection — not tracked.
- **Monorepo support**: No workspace-level analysis. Each `prism .` run is per-directory.
- **JS/TS import resolution**: Falls back to stem matching for non-Python languages. Full path resolution only for Python.

---

## 11. Future Work

- Multi-language import resolution (JS/TS tsconfig paths, Go go.mod)
- Monorepo/workspace support
- Plugin system for framework-specific entry points (like Knip's 150+ plugins)
- HTML/Markdown output formats
