# PRISM

Structural code analysis for AI agent loops. 16 tree-sitter measurements across
12 languages, Semgrep rule integration, and a pi agent harness extension.

```bash
uv run prism path/to/file.py          # default (~10s)
uv run prism --structure-only path/   # fast iteration (~0.5s)
uv run prism --community path/        # full audit (~50s)
```

[!["mode": "structure-only"](https://img.shields.io/badge/python-3.12-blue)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](./LICENSE)
[![Built with uv](https://img.shields.io/badge/built%20with-uv-purple)](https://github.com/astral-sh/uv)

---

## What It Does

PRISM is a CLI tool that produces structured JSON about your code. It combines
two engines:

- **Tree-sitter** (sub-millisecond) — 16 quantitative measurements: parameter
  counts, nesting depth, cyclomatic complexity, cognitive complexity, code clones,
  dead functions, cyclic imports, module coupling, error handling coverage,
  function purity, public/private ratio, import depth, structural diffs.
- **Semgrep** (pattern matching) — curated rules for dev tooling and correctness
  gaps that Semgrep's community library doesn't cover. Community rules available
  via opt-in.

The output is designed for AI agent loops — structured JSON with a `role` field
that frames PRISM as a fact-checker, not a judge. Measurements are accurate but
not exhaustive. You decide what to act on.

## Setup

**Prerequisites:** Python 3.12+, [`uv`](https://github.com/astral-sh/uv), and
[`semgrep`](https://github.com/semgrep/semgrep) (for rule-based scanning).

```bash
git clone <repo-url> prism
cd prism
uv sync
uv run prism path/to/file.py
```

### Pi Agent Extension

The [`prism.ts`](./prism.ts) file registers `prism` as a tool callable by the
LLM in the [pi coding agent](https://pi.dev). Copy it to your extensions
directory and set the `PRISM_DIR` environment variable:

```bash
cp prism.ts ~/.pi/agent/extensions/
export PRISM_DIR=/path/to/prism
# Then /reload in pi
```

The model discovers the `prism` tool automatically and can call it with one of
three modes: `structure-only`, `default`, or `community`.

## Three Speed Tiers

| Mode | Flag | Latency | Use Case |
|---|---|---|---|
| Structure-only | `--structure-only` | ~0.5s | Every agent iteration |
| Default | *(none)* | ~10s | Every few iterations |
| Community | `--community` | ~50s | Final audit before commit |

## All 16 Measurements

```
size:          function_length, parameter_count, import_depth
complexity:    cyclomatic_complexity, cognitive_complexity, boolean_complexity, nesting_depth
architecture:  god_class, module_instability, cyclic_import
risk:          error_handling_coverage, function_impurity, dead_function
design:        code_clone, public_ratio
diff:          diff_function_added/removed/changed
```

### Supported Languages

Python, JavaScript, TypeScript, Go, Rust, Java, Ruby, PHP, C, C++, HCL, Zig.

## Custom Semgrep Rules

PRISM ships with 5 example Python rules for dev tooling and correctness.
You can — and should — generate rules for your own domain by telling your agent:

> Research common patterns specific to [your domain], then write Semgrep YAML
> rules following the examples in `src/prism/rules/`. Save them there — PRISM
> loads them automatically on the next scan.

## Project Structure

```
prism.ts              — pi agent extension
src/prism/
  main.py             — CLI entry point
  engine/             — tree-sitter + Semgrep runners
  enrich/             — cross-file caller enrichment
  rules/              — curated Semgrep rules (YAML)
docs/                 — spec documentation
```

## License

MIT — see [LICENSE](./LICENSE).
