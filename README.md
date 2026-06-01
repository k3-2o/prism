# PRISM

Structural code analysis for AI agent loops. One CLI, 16 tree-sitter measurements,
Semgrep rules (curated + custom). Runs on Python 3.12+ with `uv`.

```
uv run prism path/to/file.py          → JSON: params, nesting, dead code, clones, cyclics...
uv run prism --structure-only path/   → tree-sitter only (~0.5s)
uv run prism --community path/        → + Semgrep community rules (~50s)
```

---

## Portable Setup (New Machine)

```bash
# Clone
git clone <repo-url> prism
cd prism

# Install dependencies (Python 3.12+ required)
uv sync

# Run on any file
uv run prism path/to/file.py
```

**Pi extension** — copy `prism.ts` to `~/.pi/agent/extensions/`.
Edit the `PRISM_DIR` constant at the top of the file to point to your
local clone path. Then `/reload` in pi. The model discovers the `prism`
tool automatically.

**Environment variable** — alternatively, set `PRISM_DIR` to the repo path:
```bash
export PRISM_DIR=/home/you/prism
```
The extension checks this before falling back to the hardcoded default.

---

## Custom Semgrep Rules

PRISM ships with 5 example Python rules covering dev tooling and correctness gaps
that Semgrep's community library misses. These are **templates** — you can (and should)
generate rules for your own project's domain.

### How It Works

PRISM loads every `.yaml` file from `src/prism/rules/` automatically. Drop a file in,
it runs on the next scan. No code changes needed.

### The Prompt

To generate custom rules for your project, tell your agent:

> Research common security vulnerabilities and code quality patterns specific
> to [YOUR DOMAIN: e.g., CLI tools in Rust, game engines in C++, data pipelines in Python].
> Use the Semgrep registry, CVE databases, OWASP cheat sheets, and your knowledge
> of the domain. Compile a focused list of the top 10-15 patterns that matter.
>
> Then write Semgrep YAML rules for each pattern, following this exact format:
>
> ```yaml
> rules:
>   - id: prism.custom.unique-rule-name
>     pattern: |
>       <code pattern to match>
>     message: >
>       Plain explanation of why this pattern is a problem and what to use instead.
>       Keep it actionable — the model reading this needs to understand the fix.
>     languages: [python]
>     severity: WARNING  # ERROR | WARNING | INFO
> ```
>
> Save each rule to `src/prism/rules/` with a descriptive filename.
> PRISM picks them up on the next scan.

### Example Rules (Shipped)

| File | What It Detects |
|---|---|
| `print-vs-logging.yaml` | `print()` used in library code instead of logging |
| `unchecked-exit-codes.yaml` | `sys.exit(0)` in what looks like an error branch |
| `signal-handler-registration.yaml` | `signal.signal()` registered without handler cleanup review |
| `comparison-pitfalls.yaml` | `is True/False/None` instead of `==` or truthiness |
| `unused-return.yaml` | `shutil.rmtree()` called without error handling |

Use these as templates. The pattern: identify a recurring structural issue in your
domain, write a pattern, explain the fix in the message.

---

## The Three Speed Tiers

| Mode | Flag | Latency | When |
|---|---|---|---|
| Structure-only | `--structure-only` | ~0.5s | Every agent iteration — tree-sitter only |
| Default | *(none)* | ~10s | Every few iterations — adds curated Semgrep rules |
| Community | `--community` | ~50s | Before commit, final audit — adds Semgrep community rules |

---

## All 16 Tree-Sitter Measurements

```
size:          function_length, parameter_count, import_depth
complexity:    cyclomatic_complexity, cognitive_complexity, boolean_complexity, nesting_depth
architecture:  god_class, module_instability, cyclic_import
risk:          error_handling_coverage, function_impurity, dead_function
design:        code_clone, public_ratio
diff:          diff_function_added/removed/changed
```

Every measurement is language-agnostic. 12 languages supported
(Python, JavaScript, TypeScript, Go, Rust, Java, Ruby, PHP, C, C++, HCL, Zig).

---

## Quick Start

```bash
cd ~/prism
uv sync

# Single file
uv run prism src/auth.py

# Project mode
uv run prism src/
```
