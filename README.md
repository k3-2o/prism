# PRISM

Structural code analysis for AI agent loops. Uses tree-sitter (16 metrics across
12 languages) + Semgrep (curated rules for dev-tooling correctness gaps).

```bash
prism path/to/file.py              
prism --structure-only path/       
prism --community path/            
```

[![python-3.12](https://img.shields.io/badge/python-3.12-blue)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](./LICENSE)

## Setup

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

```bash
# Install uv (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and install
git clone <repo-url> ~/prism
cd ~/prism
uv sync

# Option A: run with uv (no install)
uv run prism src/file.py

# Option B: install globally
uv tool install .
prism src/file.py
```

## Speed Tiers

| Mode | Command | Speed | What It Does |
|---|---|---|---|
| Structure-only | `prism --structure-only <path>` | Fast | Tree-sitter measurements only |
| Default | `prism <path>` | Moderate | Above + 11 curated Semgrep rules |
| Community | `prism --community <path>` | Slow | Above + full Semgrep community library |

Suitable for single files (~1s), full projects scale with file count.

## Metrics (16 total)

| Category | What It Measures |
|---|---|
| **Size** | Function length, parameter count, import depth |
| **Complexity** | Cyclomatic & cognitive complexity, boolean complexity, nesting depth |
| **Architecture** | God class, module instability, cyclic imports |
| **Risk** | Error handling coverage, function impurity, dead functions |
| **Design** | Code clones, public/private ratio |
| **Change** | Functions added/removed/changed (vs git HEAD) |

All metrics work across: Python, JavaScript, TypeScript, Go, Rust, Java, Ruby,
PHP, C, C++, HCL (Terraform), Zig.

## Custom Rules

PRISM ships 11 example Semgrep rules (5 Python, 6 TypeScript) covering
console-vs-logging, process exit codes, non-null assertions, any types,
unhandled promises, and async patterns. Add more by writing YAML files to
`src/prism/rules/` — they're picked up automatically.

## For pi Users

An agent skill at `docs/PRISM-SKILL.md` teaches the model PRISM's philosophy
and adversarial workflow. Install:

```bash
mkdir -p ~/.pi/agent/skills/prism
cp docs/PRISM-SKILL.md ~/.pi/agent/skills/prism/SKILL.md
# /reload in pi
```

## Project Layout

```
src/prism/
  main.py        CLI entry point
  engine/        tree-sitter + Semgrep runners
  enrich/        cross-file caller enrichment
  rules/         Semgrep rules (YAML, 11 files)
docs/
  PRISM.md       full spec
  PRISM-SKILL.md agent skill
```

## License

MIT — see [LICENSE](./LICENSE).
