# PRISM

Structural code analysis for AI agent loops. Tree-sitter powered, 25+ metrics across
12 languages, single command.

```bash
prism path/to/file.py
prism path/to/project/
prism . --visualize
```

[![python-3.12](https://img.shields.io/badge/python-3.12-blue)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

## Setup

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

```bash
git clone <repo-url> ~/prism
cd ~/prism
uv sync
uv tool install .
prism src/file.py
```

## Speed

| Target | Time |
|---|---|
| Single file (~200 loc) | ~1s |
| Small project (14 files, 3K loc) | ~12s |
| Medium project (1.2K files) | ~12s |

Heaviest operations (churn hotspots, module graph) scale with git history and
import graph depth, not file count.

## Metrics (25+ across 12 languages)

| Category | Metrics |
|---|---|
| **Complexity** | Cyclomatic, cognitive, boolean complexity, nesting depth, NLOC, Maintainability Index |
| **Size** | Function length, parameter count, import depth |
| **Architecture** | God class, module instability (Ca/Ce), cyclic imports (full path), public/private ratio |
| **Dead Code** | Dead functions (cross-file via module graph), unused exports, unused imports, unused variables, unused classes, unreachable code, unused files |
| **Risk** | Error handling coverage (50+ risky calls per language), function purity (interprocedural) |
| **Clones** | In-file + cross-file code clones (structural + token-based) |
| **Change** | Churn hotspots (complexity × change frequency), structural diff (functions added/removed/changed vs git HEAD) |
| **Rules** | Architecture import rules (may_not, may_only with glob patterns) |
| **Visualization** | Dependency graph (Graphviz DOT, SVG, PNG) |

All metrics work across: **Python, JavaScript, TypeScript, Go, Rust, Java, Ruby, PHP, C, C++, HCL (Terraform), Zig**.

## Features

- **Cross-language dead code detection** — one tool that finds dead Python functions, unused Rust imports, unreachable Java code, and dead Go classes in a single run
- **Module graph** — BFS reachability from entry points to detect truly unused files and cross-file dead functions
- **Confidence levels** — 60-100% per finding, not just binary flags
- **Entry point awareness** — configurable per-project entry points
- **Whitelist** — suppress false positives via config
- **Per-language risky call lists** — 36-116 risky call patterns per language
- **Churn hotspots** — complexity × git change frequency to find refactoring targets
- **Architecture enforcement** — may_not/may_only import rules
- **Graphviz visualization** — `prism . --visualize` produces dependency graphs

## Output

JSON with measurements, project-level meta (NLOC, avg complexity, language breakdown), and optional visualization.

```bash
prism . | jq '.meta'
# { "total_files": 14, "total_nloc": 3592, "avg_cyclomatic": 13.3, "languages": {"python": 14} }
```

## Config

Optional `.prism.toml` in project root:

```toml
[project]
entry_points = ["main", "handler", "app"]

[dead_code]
whitelist = { "register_routes" = "Called by framework" }

[import_rules]
"features-must-not-import-features" = { pattern = "features/*", may_not = ["features/*"], severity = "error" }
```

## Dev

```bash
make fmt && make check && make test
```

52 tests across 10 domain-specific test files. Runner: `pytest`, formatter: `ruff`, typechecker: `mypy`, security: `bandit`.

## Project Layout

```
src/prism/
  main.py              CLI entry point
  config.py             TOML config loading
  engine/               tree-sitter measurement engine
  enrich/               caller enrichment, import resolver, module graph, import rules
  output/               Graphviz visualization
tests/
  test_*.py             10 domain-specific test files (52 tests)
```

## License

MIT — see [LICENSE](./LICENSE).
