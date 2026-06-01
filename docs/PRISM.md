# PRISM — Structural Code Analysis for AI Agent Loops

**Version:** 0.1.0  
**Status:** Working prototype, validated, ready for agent integration  
**Language:** Python 3.12+ (CLI) + TypeScript (pi extension)  
**Package Manager:** uv (Astral)  
**Linter/Formatter:** ruff (Astral)  

---

## Table of Contents

1. [What Is PRISM](#1-what-is-prism)
2. [Quick Start](#2-quick-start)
3. [Architecture Overview](#3-architecture-overview)
4. [File Reference](#4-file-reference)
5. [CLI Reference](#5-cli-reference)
6. [Output Format (JSON Schema)](#6-output-format-json-schema)
7. [Pi Extension](#7-pi-extension)
8. [Curated Semgrep Rules](#8-curated-semgrep-rules)
9. [Performance Benchmarks](#9-performance-benchmarks)
10. [Validation Results](#10-validation-results)
11. [Architecture Decision Record](#11-architecture-decision-record)
12. [Known Issues & Caveats](#12-known-issues--caveats)
13. [Open Questions](#13-open-questions)
14. [Future Work](#14-future-work)
15. [Build History](#15-build-history)

---

## 1. What Is PRISM

PRISM is a CLI tool that produces structured JSON about code across 11 languages + HCL. It combines two analysis engines:

| Engine | What It Measures | Latency |
|---|---|---|
| **Tree-sitter** (AST queries) | Parameter counts, nesting depth, function length, dead code (per-file), cyclic imports (cross-file), callers (cross-file) | ~0.5s |
| **Semgrep** (pattern matching) | Curated rules: dev tooling exit codes, print vs logging, signal handling, comparison pitfalls, unchecked errors. Optional community rules: SQLi, XSS, command injection, insecure deserialization, etc. | ~10s (curated), ~50s (+ community) |

### Supported Languages

| Language | Extensions | Param threshold | Nesting threshold | Length threshold |
|---|---|---|---|---|
| Python | `.py` | 6 | 4 | 60 |
| JavaScript | `.js .jsx .mjs .cjs` | 5 | 4 | 50 |
| TypeScript | `.ts .tsx .mts .cts` | 5 | 4 | 50 |
| Go | `.go` | 5 | 4 | 50 |
| Rust | `.rs` | 5 | 4 | 60 |
| Java | `.java` | 5 | 4 | 50 |
| Ruby | `.rb .rake .gemspec` | 5 | 4 | 40 |
| PHP | `.php` | 5 | 4 | 50 |
| C | `.c .h` | 6 | 4 | 40 |
| C++ | `.cpp .cc .cxx .hpp .hh .hxx` | 6 | 4 | 40 |
| HCL / Terraform | `.tf .tfvars .hcl` | 8 | 3 | 40 |
| Zig | `.zig` | 5 | 4 | 50 |

Language is auto-detected from the file extension. Adding a new language requires:
1. `uv add tree-sitter-<lang>` to install the grammar
2. An entry in `src/prism/engine/languages.py` with queries and thresholds
3. No changes to the measurement engine — queries use language-agnostic capture names (`@func`, `@name`, `@params`)

### What PRISM Is NOT

- NOT a substitute for the model's own code analysis
- NOT an orchestrator of multiple scanners (SecLoop, AppSec-Sentinel already do that)
- NOT a "fix loop" tool (the agent owns the loop, PRISM is a tool inside it)
- NOT a prose generator (output is JSON, the model interprets it)
- NOT a whole-program analysis tool (CodeQL, Joern do that — minutes/hours, not sub-second)
- NOT a runtime error detector (race conditions, deadlocks, memory leaks are outside scope)
- NOT a logical reasoning engine (invariant violations, contradictions are outside scope)

### Core Philosophy

PRISM's output is named `measurements`, not `findings`. This is deliberate — "findings" implies an authoritative diagnostic, while "measurements" frames the data as quantitative facts the model should incorporate into its own broader analysis. A `note` field explicitly tells the model these measurements are not exhaustive.

---

## 2. Quick Start

```bash
# Install
cd ~/prism
uv sync

# Run
uv run prism path/to/file.py              # default: tree-sitter + curated rules (~10s)
uv run prism --structure-only file.py     # tree-sitter only (~0.5s)
uv run prism --community file.py          # + community Semgrep rules (~50s)

# Project-wide analysis
uv run prism path/to/directory/

# Output is JSON to stdout
```

**Prerequisites:** 
- Python 3.12+
- uv installed
- Internet on first run of `--community` mode (downloads Semgrep community rules)

**Multi-language:** PRISM auto-detects language from file extension. All 11 languages listed in section 1 are supported out of the box.

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    PRISM CLI (prism <path>)                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────┐   ┌──────────────────────────────┐ │
│  │   Tree-sitter AST   │   │   Semgrep (subprocess)       │ │
│  │   (in-process)      │   │   — curated rules (bundled)  │ │
│  │                     │   │   — community rules (opt-in) │ │
│  │   • parameter_count │   │                              │ │
│  │   • nesting_depth   │   │   Returns JSON with:         │ │
│  │   • function_length │   │   • rule ID                  │ │
│  │   • dead_function   │   │   • severity                 │ │
│  │   • cyclic_import   │   │   • message                  │ │
│  │                     │   │   • location (file, line)    │ │
│  └─────────┬───────────┘   └─────────────┬────────────────┘ │
│            │                              │                  │
│            └──────────┬───────────────────┘                  │
│                       ▼                                     │
│            ┌──────────────────┐                             │
│            │   Enricher       │                             │
│            │   (tree-sitter)  │                             │
│            │                  │                             │
│            │   • For each     │                             │
│            │     measurement: │                             │
│            │     find cross-  │                             │
│            │     file callers │                             │
│            │                  │                             │
│            │   • For each     │                             │
│            │     Semgrep      │                             │
│            │     finding:     │                             │
│            │     find         │                             │
│            │     enclosing    │                             │
│            │     function +   │                             │
│            │     callers      │                             │
│            └────────┬─────────┘                             │
│                     ▼                                       │
│            ┌──────────────────┐                             │
│            │   JSON Output    │                             │
│            │   measurements[] │                             │
│            │   semgrep_comm[] │                             │
│            │   semgrep_cur[]  │                             │
│            │   + note, lang,  │                             │
│            │     version      │                             │
│            └──────────────────┘                             │
└─────────────────────────────────────────────────────────────┘
```

### Language Registry (Multi-Language Architecture)

Language-specific logic is centralized in `src/prism/engine/languages.py`. Each language entry defines:

- **Extensions** — file extensions that map to this language
- **Grammar** — tree-sitter grammar package and attribute name (e.g., `tree_sitter_python.language`)
- **Queries** — tree-sitter query strings using consistent capture names (`@func`, `@name`, `@params` for functions; `@name` for calls and imports)
- **Thresholds** — per-language thresholds for parameter count, nesting depth, and function length
- **Ignore names** — function names to exclude from dead code detection (e.g., `main`, `init`, `initialize`)

Queries use the same capture names across all languages even though AST node types differ:
- `@func` — the function/block node
- `@name` — the function name identifier
- `@params` — the parameter list node

This means measurement functions in `treerunner.py` are language-agnostic — they iterate query matches and read captures without knowing the language. Adding a new language requires only a new entry in the registry, no code changes to the measurement engine.

### Data Flow

1. **Parse phase:** Both tree-sitter and Semgrep run independently on the target file(s)
2. **Measurement phase:** Tree-sitter runs 5 AST queries, produces structured measurements
3. **Scan phase:** Semgrep runs bundled curated rules (and optionally community rules)
4. **Enrichment phase:** 
   - Structural measurements get cross-file callers attached 
   - Semgrep findings get enclosing function name, signature, body length, and cross-file callers
5. **Output phase:** Everything merged into a single JSON document, printed to stdout

### Three Speed Tiers (Design Intent)

| Mode | Flag | Typical Latency | Intended Use |
|---|---|---|---|
| **Structure-only** | `--structure-only` | ~0.5s | Every agent iteration — fast, tree-sitter only |
| **Default** | *(none)* | ~10s | Every 3-5 iterations — adds curated Semgrep rules |
| **Community** | `--community` | ~50s | Before commit, final review — adds full Semgrep community rules |

The agent decides which mode to call based on context. The pi extension exposes all three via the `mode` parameter.

---

## 4. File Reference

### Python CLI (`~/prism/`)

```
~/prism/
  pyproject.toml                      # uv-managed, ruff configured, scripts: prism
  uv.lock                             # Lockfile (generated)
  .python-version                     # 3.12
  .venv/                              # Virtual environment (generated)
  src/prism/
    __init__.py                       # __version__ = "0.1.0"
    __main__.py                       # python -m prism support
    main.py                           # Click CLI entry point
    
    engine/
      __init__.py
      languages.py                    # Multi-language registry: grammars, queries, thresholds
      treerunner.py                   # Tree-sitter AST measurements (language-agnostic)
      semgrep_runner.py               # Semgrep subprocess runner
      
    enrich/
      __init__.py
      enricher.py                     # Cross-file caller detection + line-based enrichment
      
    output/
      __init__.py                     # (reserved — currently uses json.dumps directly)
      
    rules/                            # Bundled curated Semgrep rules (YAML)
      comparison-pitfalls.yaml        # is vs == with literals, truthy comparisons
      print-vs-logging.yaml           # print() in non-script code
      signal-handler-registration.yaml # signal.signal() usage
      unchecked-exit-codes.yaml       # sys.exit(0) in error branches
      unused-return.yaml              # shutil.rmtree() unchecked
```

### Pi Extension (`~/.pi/agent/extensions/prism.ts`)

```
~/.pi/agent/extensions/prism.ts       # Auto-discovered by pi, registers `prism` tool
```

---

## 5. CLI Reference

### `prism [OPTIONS] PATH`

**Arguments:**

| Argument | Description |
|---|---|
| `PATH` | File or directory to analyze. Required. Must exist. |

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--structure-only` | `false` | Skip Semgrep, run tree-sitter measurements only (fastest) |
| `--community` | `false` | Include Semgrep community rules (slowest, needs network) |
| `--version` | - | Show version and exit |
| `--help` | - | Show help and exit |

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Success (no errors) |
| 1 | Error occurred |

**Behavioral notes:**
- If PATH is a file, analyzes that file + discovers sibling files for caller enrichment
- If PATH is a directory, discovers all `.py` files recursively (excluding venvs, node_modules, .git, __pycache__)
- `--structure-only` and `--community` are mutually exclusive with each other (`--community` implies full mode)
- Semgrep must be installed (it's a pip dependency of the project)
- Community rules require internet on first run (cached afterward by Semgrep)

### Examples

```bash
# Structure-only (fast iteration)
uv run prism --structure-only src/auth.py

# Default (curated rules)
uv run prism src/auth.py

# Full audit with community rules
uv run prism --community src/auth.py

# Project-wide analysis
uv run prism src/

# Working directory mode
cd ~/project && uv run prism .
```

---

## 6. Output Format (JSON Schema)

```json
{
  "version": "0.1.0",
  "role": "PRISM is a structural fact-checker. It counts parameters, nesting depth, dead functions, cyclic imports, code clones, and similar quantitative properties. It does not understand the code's purpose, domain constraints, or whether a high count is actually a problem in context. A function with 9 parameters may be the correct design for its domain. A 172-line function may be appropriate for the complexity it handles. These measurements exist for your awareness — integrate them into your own judgment. You have the full context. You decide what to act on and what to leave as-is.",
  "scope": {
    "covers": ["size", "complexity", "coupling", "dead_code", "code_clones", "function_purity"],
    "does_not_cover": ["logical_correctness", "validation_adequacy", "naming_conventions", "security_best_practices", "error_handling_logical_adequacy", "test_coverage", "performance"]
  },
  "file": "src/auth.py",
  "language": "python",
  "mode": "default",
  "measurements_count": 3,
  "measurements": [
    {
      "source": "structure",
      "metric": "parameter_count",
      "function": "__init__",
      "value": 16,
      "threshold": 6,
      "location": {
        "file": "src/auth.py",
        "line": 7
      },
      "context": {
        "signature": "def __init__(self, db_conn, cache, logger, rate_limiter, token_signer, session_store, email_sender, sms_gateway):",
        "callers": []
      }
    },
    {
      "source": "structure",
      "metric": "dead_function",
      "function": "validate_token",
      "value": 0,
      "threshold": null,
      "location": {
        "file": "src/auth.py",
        "line": 9
      },
      "context": {
        "callers": []
      }
    }
  ],
  "semgrep_community": [],
  "semgrep_curated": []
}
```

### Structural Metrics Reference

| Metric | Source | Value Type | Threshold | Description |
|---|---|---|---|---|
| `parameter_count` | tree-sitter | int | >6 | Number of explicit function parameters (excluding self/cls, counting *args/**kwargs as 1 each) |
| `nesting_depth` | tree-sitter | int | >4 | Max indentation depth (in 4-space units) within a function body |
| `function_length` | tree-sitter | int | >60 | Lines of code from `def` line to end of function body |
| `dead_function` | tree-sitter | 0 | null | Function defined but never called within its own file. Dunder methods (`__x__`) are excluded. Method calls (`obj.method()`) are NOT detected as callers — only direct calls (`method()`) are. |
| `cyclic_import` | tree-sitter | cycle_len | >1 | Module is part of a circular import chain. `context.cycle` lists the full cycle. |
| `module_instability` | tree-sitter | float | >0.8 | Martin's instability metric: Ce/(Ca+Ce). >0.8 means too many outgoing dependencies (fragile). <0.2 with 0 outgoing means possible dead weight. `context.detail` shows Ca and Ce values. Available in project mode only. |
| `diff_function_added` | tree-sitter + git | 0 | null | Function exists in current file but not in git HEAD. New code that may need review. |
| `diff_function_removed` | tree-sitter + git | 0 | null | Function existed in git HEAD but not in current file. |
| `diff_function_changed` | tree-sitter + git | 0 | null | Function signature (parameter count) or complexity changed from git HEAD. `context.detail` lists what changed. |
| `error_handling_coverage` | tree-sitter | float | <0.8 | Ratio of risky calls (I/O, network, eval, subprocess) that are inside try/except. Low coverage means the function will crash silently on failure. |
| `public_ratio` | tree-sitter | float | >0.9 | Ratio of public to total top-level functions. High ratio means the module has no encapsulation (everything is exposed). |
| `import_depth` | tree-sitter | int | >3 | Number of dot-separated segments in an import path. `from foo.bar.baz.qux import thing` = depth 4. Deep imports indicate tight coupling. |
| `code_clone` | tree-sitter | float (similarity) | >0.8 | Two functions with structurally similar AST bodies but different names. Detects copy-paste that text search misses. `context.detail` names the similar function. |
| `function_impurity` | tree-sitter | int (issue count) | >0 | Function has side effects: modifies module-level variables, mutates parameters, or calls known-impure functions (print, random, time, os, subprocess). `context.detail` lists specific issues. |
| `cyclomatic_complexity` | tree-sitter | int | >10 | McCabe's complexity: counts decision points (if, for, while, except, &&, \|\|) + 1 for the function entry. >20 is high risk. |
| `cognitive_complexity` | tree-sitter | int | >15 | SonarSource cognitive complexity: nesting-weighted. Each decision point at depth N adds 1 + 2*N. Catches deeply nested control flow that raw cyclomatic misses. |
| `boolean_complexity` | tree-sitter | int | >3 | Number of boolean operators (and/or/&&/\|\|) inside a single `if` condition. `if a and b or c:` = 3 conditions. `context.detail` shows the condition text. |
| `god_class` | tree-sitter | int (methods) | >10 | Class with too many methods, dependencies, or lines. `context.detail` lists which thresholds were exceeded (`methods:N`, `deps:N`, `lines:N`). `context.total_lines` and `context.dependency_count` provide raw values. |

Thresholds vary per language. See the language registry in `src/prism/engine/languages.py` for exact values.

### Cardinal Rules for the Model

1. **Every field is deterministic** — tree-sitter measurements are exact, not heuristic
2. **Every field is verifiable** — the model can check: does this function actually have 16 parameters? Yes, tree-sitter counted them exactly
3. **No instructions** — PRISM never says "fix like this" or "check for X". It reports. The model decides
4. **Cross-file callers are the primary enrichment** — this is the hardest thing for the model to compute from context alone (may not have loaded the caller's file)
5. **The `role` field sets the frame** — PRISM is a counter, not a judge. The `role` field explicitly tells the model that a high count may be correct in context, and that the model's own judgment takes priority over any measurement.
6. **The `scope` field draws the boundary** — `scope.covers` lists what PRISM checked. `scope.does_not_cover` lists what the model must handle itself. The model should not create false positives in these areas just to "be thorough" — if there's no concrete evidence of a problem, the measurement is that PRISM doesn't measure it, not that there's a problem.
7. **A measurement is not a mandate** — exceeding a threshold does not mean a fix is required. It means: "here is a structural fact. The model decides whether it matters in this context."

---

## 7. Pi Extension

**Location:** `~/.pi/agent/extensions/prism.ts` (auto-discovered by pi on `/reload` or restart)

**What it does:** Registers a custom tool called `prism` that the LLM can call during agent sessions.

**Tool definition:**

```typescript
{
  name: "prism",
  label: "PRISM",
  description: "Analyze code and return structured measurements...",
  parameters: {
    path: string,     // File or directory to analyze
    mode: enum        // "structure-only" | "default" | "community"
  }
}
```

**Execution:** Async via Node.js `child_process.exec` (does NOT block the terminal UI). The AbortSignal is wired to kill the subprocess. stderr (Semgrep progress) is captured for error reporting.

**Prompt guidelines included:**
- Three speed tiers explained
- Note that measurements are NOT exhaustive
- Use as hints, not a complete diagnostic

**Reload:** After modifying the extension, run `/reload` in pi or restart pi.

---

## 8. Custom Semgrep Rules — Agent-Driven

PRISM does NOT ship a curated library of Semgrep rules for every domain. Writing good rules requires domain expertise that PRISM doesn't have. Instead, PRISM ships **5 example rules** showing the format. The agent researches its own domain and writes its own rules.

**To generate rules for your project, give your agent a prompt like:**

> Research common security vulnerabilities and code quality patterns specific to
> [YOUR DOMAIN]. Use the Semgrep registry, CVE databases, OWASP cheat sheets,
> and your knowledge of the domain. Compile a focused list of the top 10-15 patterns.
> Then write Semgrep YAML rules following the example format in `src/prism/rules/`.
> Save each rule with a descriptive filename. PRISM loads them automatically.

### Example Rules (Shipped as Templates)

Five rules shipped in `src/prism/rules/` to demonstrate the format:

| Rule ID | What It Detects | Example |
|---|---|---|
| `prism.dev-tooling.print-in-library` | `print()` used in non-script code | `print(f"Error: {msg}")` in a library function |
| `prism.dev-tooling.unchecked-exit-code` | `sys.exit(0)` called from error path | `if error: sys.exit(0)` should be `sys.exit(1)` |
| `prism.dev-tooling.signal-without-handler` | `signal.signal()` registration | Reminds the model to verify handler correctness |
| `prism.correctness.is-with-number-literal` | `is` used with `True/False/None/0/1` | `if data is True:` should be `if data:` |
| `prism.correctness.is-with-string-literal` | `is` used with string literal | `if x is "hello":` should be `if x == "hello":` |
| `prism.correctness.unused-shutil-return` | `shutil.rmtree()` without error handling | `shutil.rmtree(path)` can raise PermissionError |

### Semgrep Community Coverage vs PRISM's Gap

The Semgrep community rule library (downloaded via `--community`) focuses heavily on **web security and IaC misconfigurations** across many languages. It barely touches dev tooling, correctness, or architecture in any language.

| Language | Community Rules | What Community Covers | What Community MISSES (PRISM fills) |
|---|---|---|---|
| Python | **378** | SQLi, XSS, command injection, deserialization, crypto, secrets, subprocess | Exit codes, print-vs-logging, signal handling, comparison pitfalls, unchecked returns |
| JavaScript | **213** | XSS, DOM manipulation, prototype pollution, eval, insecure fetch | Console.log in libs, missing error handling, arg count mismatches |
| TypeScript | **207** | Same as JS + React/Angular patterns | Same as JS |
| Terraform/HCL | **364** | Open S3 buckets, unencrypted storage, overly permissive IAM | Block nesting depth, unused blocks, reference chains |
| Java | **128** | SQLi, XXE, deserialization, path traversal, crypto | Method parameter counts, nested try blocks, unused private methods |
| Go | **97** | SQLi, command injection, HTTP security, crypto | Exposed goroutines, unchecked errors, fmt.Println in libraries |
| Ruby | **89** | SQLi, command injection, unsafe YAML, mass assignment | puts in libraries, method length, rescue without specific class |
| PHP | **64** | SQLi, XSS, file inclusion, eval, deserialization | Function length, nesting depth, unused functions |
| C | **17** | Buffer overflow (limited), format string, memory | Function parameter count, nesting, dead code |
| Rust | **11** | Very few — unsafe blocks, command injection | Parameter count, nesting depth, dead code, function length |

**The gap is consistent across all languages:** Community rules are strong at "injection goes in, secrets leak out" but weak at "this function is too long, too nested, has too many parameters, or these exports are dead." PRISM's curated rules address the second category — but currently only for Python. Expanding curated rules to other languages means writing the same logical patterns with different syntax for each language.

**Rule format:** Standard Semgrep YAML. Each file contains a `rules:` list with standard Semgrep fields. Rules are loaded individually via `--config <file>` for each YAML file (Semgrep does NOT recurse into directories).

**Expansion:** Rules are easy to add — write a YAML file in `src/prism/rules/`, it's automatically picked up on next scan. No code changes needed.

---

## 9. Performance Benchmarks

Measured on a 3-file project (30-100 lines each) using `time`:

| Mode | Cold Start | Cached | Notes |
|---|---|---|---|
| `--structure-only` | **0.5s** | ~0.3s | No Semgrep overhead |
| default (curated) | **11s** | ~8-10s | Semgrep Python startup dominates |
| `--community` | **50s** | ~40-45s | 290 community rules downloaded + parsed |

**The bottleneck is Semgrep's Python startup,** not the rules themselves. Even with 0 rules, Semgrep takes ~8s to start. This is a known limitation of Semgrep's architecture (Python CLI → OCaml engine via subprocess). Mitigation: use `--structure-only` for fast iterations, defer full scans to occasional checkpoints.

---

## 10. Validation Results

A controlled experiment was conducted to test whether PRISM enrichment improves model code fix quality.

### Methodology

Three test cases, each run twice:
- **Control:** Model given raw file, asked to "find and fix structural issues"
- **Treatment:** Model given same file + PRISM JSON output, asked the same

Both runs used the same model (Claude) in pi's print mode with identical prompts except for the PRISM injection.

### Test Case 1: Parameter Count (Small File)

**File:** 3 functions with 7-9 parameters, 50 lines total, all visible in one screen

| Metric | Control (no PRISM) | Treatment (with PRISM) |
|---|---|---|
| `create_order` | 9 → 5 params (dataclass) | 9 → 5 params (dict) |
| `process_payment` | 8 → 1 param (dataclass) | 8 → 3 params (dicts) |
| `ship_order` | 7 → 1 param (dataclass) | 7 → 3 params (dict) |
| Type hints added | ✅ Full annotations | ❌ None |
| Input validation | ✅ ValueError checks | ❌ None |
| Hardcoded returns fixed | ✅ Yes | ❌ No |
| Refactoring depth | Deep — dataclasses, type-safe | Shallow — dicts, lighter |

**Winner: Control.** The model did better without PRISM. PRISM's output anchored the model — it addressed exactly what was measured and stopped. The control did open-ended analysis and found more issues.

### Test Case 2: Cross-File Dead Code

**File:** Two files, one with `get_user()`, `send_email()`, `get_user_count()` — `get_user_count` has no callers

| Metric | Control (no PRISM) | Treatment (with PRISM) |
|---|---|---|
| `get_user_count` removed | ❌ Kept (not noticed) | ✅ Removed |
| `get_user` kept | ✅ Yes (has callers) | ✅ Yes (has callers) |
| Type hints/docs added | ✅ Yes | ✅ Yes |

**Winner: Treatment.** PRISM showed `get_user_count` has zero callers, which the control missed. The model correctly removed it.

### Test Case 3: God Object (100 lines)

**File:** `UserManager` class with 16-param `__init__`, 9-param `create_user`, nesting depth 8, 3 dead legacy methods, 1 dead helper

| Metric | Control (no PRISM) | Treatment (with PRISM) |
|---|---|---|
| `__init__` params reduced | ✅ 16→4 (dataclasses) | ✅ 16→4 (dataclasses) |
| `create_user` params reduced | ❌ Kept at 9 | ✅ 9→1 (UserData dataclass) |
| Nesting flattened | ✅ Early returns | ✅ Early returns |
| Dead code removed | ✅ All removed | ✅ All removed |

**Winner: Treatment.** Control missed the 9-param `create_user` buried in the class. PRISM flagged it with both `parameter_count` (>6) and `nesting_depth` (>4), guaranteeing the model noticed.

### Summary Table

| Scenario | PRISM Helps? | Why |
|---|---|---|
| Small file, visible issues | ❌ Hurts | Anchors model to measured issues, misses unmeasured ones |
| Large file, buried issues | ✅ Helps | Guarantees model notices things it might scroll past |
| Cross-file dead code | ✅ Helps | Model can't easily compute callers across files |
| Cross-file callers (signature change) | ✅ Helps | PRISM lists callers the model may not have loaded |
| Cyclic imports | ✅ Helps | Model reading one file can't detect cycles |
| Every iteration of agent loop | ⚠️ Only `--structure-only` | Full mode too slow for per-iteration use |

### Design Changes From Validation

The test directly informed two output design decisions:

1. **`findings` → `measurements`**: The word "findings" implies an authoritative diagnostic. "Measurements" frames the data as quantitative facts.
2. **Added `role` field**: Explicitly states PRISM is a counter, not a judge. The model decides what to act on. Prevents anchoring.

### Custom Semgrep Rules: Agent-Driven Approach

**Decision:** PRISM does NOT ship a curated library of Semgrep rules for every domain. Instead, it ships 5 Python examples and a prompt recipe. The agent researches its own domain (CLI tools, compilers, game engines, web apps) and writes its own Semgrep YAML rules.

**Rationale:**
- Writing good Semgrep rules requires domain expertise PRISM doesn't have
- The agent already has the domain context — it knows what project it's building
- The agent can research CVE databases, OWASP guides, and known patterns for the specific domain
- PRISM's 5 shipped rules serve as format examples, not as the complete set

**Workflow:**
```
Agent: "I'm building a CLI tool in Rust"
  → agent researches known CLI vulnerabilities
  → compiles list of 10-15 patterns
  → writes Semgrep YAML rules
  → saves to src/prism/rules/
  → PRISM picks them up automatically
```

**Impact:** No unbounded knowledge base maintenance. No domain expertise required from PRISM. The agent does the research, writes the rules, and they work immediately.

---

## 11. Architecture Decision Record

### ADR-1: Output Format — JSON, not prose

**Status:** Accepted  
**Context:** The original PRISM concept proposed a "briefing engine" that would generate narrative analysis from structural data.  
**Decision:** Output structured JSON only. Deterministic code cannot produce useful explanatory prose — the output would be templated and hollow. The model interprets the data.  
**Consequence:** Simpler code, no templating engine, no pseudo-narrative that misleads the model. The model is free to draw its own conclusions.

### ADR-2: No fix loop — agent owns the loop

**Status:** Accepted  
**Context:** Multiple tools (SecLoop, AppSec-Sentinel) already ship the "scan → LLM fix → verify" pattern.  
**Decision:** PRISM does NOT call the LLM, apply patches, or iterate. It is a pure function: code in, facts out. The agent owns orchestration.  
**Consequence:** PRISM stays small, focused, and reusable across different agent harnesses.

### ADR-3: No program slicing, no call graph, no CFG/DFG/PDG

**Status:** Accepted  
**Context:** These analysis techniques require whole-program analysis, are imprecise for dynamic languages (Python), and are computationally heavy.  
**Decision:** Only tree-sitter AST queries survive. The "5-layer stack" collapsed to one layer.  
**Consequence:** PRISM is fast (~0.5s for structure-only) but cannot detect deep interprocedural bugs. This is an accepted limitation.

### ADR-4: Semgrep community rules are opt-in

**Status:** Accepted  
**Context:** Semgrep community rules take ~40-50s to run due to Python startup overhead + 290 rule parsing.  
**Decision:** By default, PRISM runs only its 5 bundled curated rules. Community rules require `--community` flag.  
**Consequence:** Default mode is ~10s (acceptable for occasional use). Community mode is ~50s (acceptable for final audit). Structure-only mode is ~0.5s (acceptable for every iteration).

### ADR-5: `measurements` not `findings`

**Status:** Accepted  
**Context:** Validation Testing showed PRISM's output anchored the model, causing it to focus only on measured issues and miss unmeasured ones.  
**Decision:** The output key is `measurements`, not `findings`. A `note` field explicitly states the data is not exhaustive.  
**Consequence:** Reduces anchoring effect. Model treats the data as hints, not a complete diagnostic.

### ADR-6: Cross-file callers are the primary enrichment

**Status:** Accepted  
**Context:** The model already has the file it wrote in context. It can count parameters, see nesting, and trace intra-file calls. But it may not have loaded the caller's file.  
**Decision:** Every measurement and Semgrep finding gets cross-file caller info attached. This is PRISM's strongest value-add.  
**Consequence:** When the model is about to change a function's signature, PRISM guarantees it sees who calls that function and where.

### ADR-7: Multi-language via registry pattern

**Status:** Accepted  
**Context:** The original build was Python-only. Expanding to 10+ languages required adding tree-sitter grammars and language-specific queries.  
**Decision:** Centralize all language-specific logic in `languages.py` — a registry that maps extensions to grammars, queries, thresholds, and ignore lists. Measurement functions in `treerunner.py` are language-agnostic, using capture names (@func, @name, @params) that are consistent across languages.  
**Consequence:** Adding a new language requires only a registry entry + `uv add tree-sitter-<lang>`. No changes to the measurement engine, enrichment logic, or output formatting. However, each language's queries must be individually tested and debugged — AST node types differ unpredictably across grammars.

### ADR-8: Python-only launch (tree-sitter)

**Status:** Superseded  
**Context:** Originally launched with Python-only tree-sitter support.  
**Decision:** Superseded by ADR-7 — multi-language support now covers 11 languages.  
**Consequence:** The language registry pattern allowed multi-language expansion without refactoring the measurement engine.

### ADR-9: One command, no subcommands

**Status:** Accepted  
**Context:** The original concept proposed `prism audit`, `prism fix`, `prism slice`, `prism blast`, `prism watch`, `prism init`.  
**Decision:** One shape: `prism <path>`. Flags control behavior (`--structure-only`, `--community`). Everything else is the agent's responsibility.  
**Consequence:** Simpler interface, easier to document, easier for the model to discover and use.

### ADR-10: No additional scanners (Trivy, Gitleaks, Bandit)

**Status:** Accepted  
**Context:** Every extra scanner adds install dependencies, output format normalization, false positive management, and failure points. SecLoop and AppSec-Sentinel already cover the "multi-scanner launcher" space.  
**Decision:** PRISM integrates only Semgrep (via subprocess) and tree-sitter (via Python bindings). No other scanners.  
**Consequence:** Tiny dependency surface. PRISM does not compete in the saturated "orchestrate everything" space.

### ADR-11: No implication chains / domain awareness

**Status:** Accepted  
**Context:** The concept of detecting structural signals ("this is a CLI tool") and mapping them to concerns ("check exit codes, signal handling") was explored.  
**Decision:** Dropped. Technically possible but requires a hand-authored knowledge base covering every domain, language, and framework. Maintenance burden is unbounded for a solo or small-team tool.  
**Consequence:** PRISM does not tell the model what to check. It reports measurements. The model's training is sufficient to infer what matters for the domain.

### ADR-12: `uv` + `ruff` for project tooling

**Status:** Accepted  
**Context:** Astral's toolchain (uv, ruff) provides fast, modern Python project management.  
**Decision:** Use `uv` for dependency management, virtual environments, and running. Use `ruff` for linting and formatting.  
**Consequence:** No pip, no venv, no setup.py, no black/flake8/isort. Single toolchain.

---

## 12. Known Issues & Caveats

### Dead Code Detection Is Per-File Only

The `dead_function` metric reports functions that are never called within their own file. A function that has cross-file callers will still appear as "dead" in its own file's measurements, but the caller enrichment context will list those cross-file callers. The model must reconcile the two.

### Method Calls Not Detected As "Calls"

The dead code detection query `(call function: (identifier) @call_name)` only catches direct function calls like `foo()`. Method calls like `obj.foo()` have a different AST structure (`attribute` node under `call`) and are NOT matched. This means `__init__` methods, class methods, and any method called via `self.method()` will appear as dead code if nothing calls them directly.

**Mitigation:** Methods named `__init__` are excluded from dead function reporting. Other methods may produce false positives.

### Cyclic Import Detection Is Bounded

The cyclic import detection only considers modules that exist as `.py` files in the scanned project. Imports of installed packages, standard library modules, or modules outside the project root are ignored. A cycle involving shared utility modules may not be detected if the utility module is outside the project root.

### Semgrep Startup Latency

Semgrep's Python CLI takes ~8-10s to start even with zero rules. This is a Semgrep architecture limitation (Python bootstrap → OCaml engine via subprocess). PRISM cannot speed this up. Structure-only mode (`--structure-only`) completely avoids Semgrep.

### Curated Rules Are Examples, Not Exhaustive

The 5 shipped rules are format examples, not a complete library. The agent is expected to research its own domain and write rules for the patterns that matter. See the README for the agent prompt recipe.

### Language Detection Is Extension-Based

Language is detected solely from file extension. A `.js` file is always JavaScript, a `.ts` file is always TypeScript. Files with unconventional extensions (e.g., `.foo.jsx`) may not be detected. No content-based language detection exists.

### Tree-Sitter Query Fragility Per Language

Each language's queries use different AST node type names. Adding a new language requires testing each query individually — "Impossible pattern" and "Invalid node type" errors are common during development. Single-line query strings avoid Python whitespace issues with triple-quoted strings in the registry dict.

### Semgrep Rules Are Python-Only

The 5 curated Semgrep rules and community rules (opt-in) only work on Python files. When running on non-Python files, Semgrep findings are empty. Only tree-sitter measurements are available for non-Python languages.

### Tree-Sitter's Ceiling — What Structural Analysis Cannot Measure

Tree-sitter's capabilities are bounded by what can be determined from the AST without running the code. PRISM has reached this ceiling — 16 metrics across 8 categories covering every structural dimension:

| Dimension | Covered By |
|---|---|
| Size | `function_length`, `parameter_count`, `import_depth` |
| Complexity | `cyclomatic_complexity`, `cognitive_complexity`, `boolean_complexity`, `nesting_depth` |
| Structure | `god_class`, `dead_function` |
| Coupling | `cyclic_import`, `module_instability`, `import_depth` |
| Correctness risk | `error_handling_coverage`, `function_impurity` |
| Duplication | `code_clone` |
| Encapsulation | `public_ratio` |
| Change awareness | `diff_function_added/removed/changed` |

**What remains outside tree-sitter's reach (and PRISM will never measure):**

| Category | Why Tree-Sitter Can't Do It | Requires |
|---|---|---|
| Runtime behavior (race conditions, deadlocks, leaks) | No execution trace | Dynamic analysis / runtime |
| Test coverage | No execution data | Instrumentation / runtime |
| Performance profiling | No execution timing | Profiler / runtime |
| Memory usage | No heap visibility | Memory profiler / runtime |
| Logical correctness | AST doesn't encode intent | Formal verification / human review |
| Data flow across function boundaries | No type information in dynamic languages | Type inference / whole-program analysis |
| Taint tracking (user input → sink) | Requires type-aware data flow | Specialized taint engine (Semgrep does this partially) |
| API semantic correctness | "Is this function called with the right arguments?" | Semantic understanding / runtime |

**PRISM's 16 metrics are the complete set of high-signal structural measurements.** The remaining academic metric categories (Halstead metrics, ABC, exit point density, comment density) were evaluated and rejected: Halstead metrics correlate weakly with actual defects, ABC is ecosystem-specific (Ruby), exit points produce high false positives, and comment density requires context PRISM doesn't have.

Any measurement beyond these 16 requires either running the code or semantic understanding — both explicitly outside PRISM's scope.

---

## 13. Open Questions

### Q1: Does the enrichment actually matter?

The validation test showed mixed results. PRISM helps on larger files and cross-file scenarios but can hurt on small files by anchoring the model. The `note` field and `measurements` naming mitigate anchoring but don't eliminate it. **A broader test (10+ files, diverse domains) is needed to confirm the overall value proposition before investing in marketing or distribution.**

### Q2: What curated rules to write next?

The 5 existing rules are a start. Priority candidates:
- API design: "function called with wrong argument count" (requires cross-file)
- Architecture: "layer violation" (requires user-defined boundary config)
- Dev tooling: "environment variable read without default"
- Correctness: "bare except" (Semgrep has this already — would be community)
- Async: "await inside non-async function"

### Q3: What are the right default thresholds?

Parameter count >6, nesting depth >4, function length >60 — these were chosen as reasonable defaults but may need tuning per project or per language. Should thresholds be configurable?

### Q4: Python-only or multi-language?

Tree-sitter grammars exist for most languages, but each requires:
- Written queries (different node type names)
- Curated Semgrep rules (different patterns)
- Test suite

Python-only keeps the project manageable. Expansion should be driven by user demand.

### Q5: Distribution model?

Currently: git clone + `uv sync`. Options for distribution:
- PyPI package (requires packaging, CI, versioning)
- Standalone binary via PyInstaller or similar (avoids Python dependency for users)
- No distribution (personal tool, not shared)

### Q6: What's the pi extension's long-term home?

Currently at `~/.pi/agent/extensions/prism.ts`. If PRISM becomes a PyPI package, the extension could be published as a pi package. If PRISM stays a personal tool, the current single-file extension is fine.

---

## 14. Future Work

### Short-term (if continuing)

- **More curated rules** — Expand to 10-15 rules covering API gaps, architecture, async patterns
- **Configurable thresholds** — Allow user to set parameter count, nesting, length thresholds per-project
- **Test suite** — Unit tests for tree-sitter queries, integration tests for Semgrep runner, output format validation
- **MCP server** — Expose PRISM as an MCP tool for Claude Desktop and other MCP-compatible clients

### Medium-term

- **Language expansion** — JavaScript/TypeScript (tree-sitter grammars are excellent), Go (good grammar), Rust (good grammar)
- **Rule suggestions** — Analyze cross-file caller patterns and suggest rules the user might want to write
- **Incremental scanning** — Track file modification times, only re-scan changed files

### Long-term (if value holds)

- **PRISM as a pi package** — Publish the extension on npm for easy installation
- **Community rule contributions** — Accept contributed curated rules via PRs
- **Benchmark suite** — Track how well PRISM's measurements correlate with actual code quality improvements

### Explicitly NOT planned

- **Program slicing** — Rejected, imprecise for dynamic languages
- **Full call graph** — Rejected, too heavy for the precision achievable
- **LLM integration** — PRISM does not call the LLM, never will
- **Fix loop** — Agent owns the loop, PRISM does not apply patches
- **Runtime analysis** — Outside scope, requires execution
- **Dependency scanning** — Trivy/osv-scanner exist, not PRISM's job

---

## 15. Build History

### Session 1 (2026-05-29): Concept deconstruction

**Duration:** ~4 hours  
**Outcome:** Original PRISM concept pressure-tested. Program slicing, call graphs, CFG/DFG/PDG, "briefing engine," fix loop, multi-command CLI, implication chains, domain awareness, and 5-layer analysis stack all rejected. Surviving core: three-column JSON (tree-sitter measurements + Semgrep community rules + curated Semgrep rules) with cross-file caller enrichment.

### Session 2 (2026-06-01): Build + validation

**Duration:** ~6 hours  
**Outcome:** Full prototype built and validated.

| Step | What | Time |
|---|---|---|
| 1 | Project skeleton (`uv init`, `pyproject.toml`, click CLI) | ~30 min |
| 2 | Tree-sitter measurements (params, nesting, dead code, cyclic imports) | ~3 hr |
| 3 | Cross-file caller enrichment | ~2 hr |
| 4 | Validation gate (3 test cases, control vs treatment) | ~2 hr |
| 5 | Semgrep integration + 5 curated rules | ~3 hr |
| 6 | Curated rules expanded (5 rules shipped) | ~1 hr |
| 7 | Pi extension (`~/.pi/agent/extensions/prism.ts`) | ~1 hr |

**Validation finding:** PRISM helps when the model can't trivially compute the measurement (large files, cross-file callers, buried metrics). PRISM can hurt on small files by anchoring the model's focus. Mitigated by `measurements` naming + `note` field.

**Performance finding:** Semgrep startup dominates latency (~8s minimum even with 0 rules). Three-tier speed design (`--structure-only` at 0.5s, default at 10s, `--community` at 50s) accepts this limitation.

### Session 3 (2026-06-01): Multi-language expansion

**Duration:** ~2 hours  
**Outcome:** PRISM expanded from Python-only to 11 languages + HCL.

| Step | What | Time |
|---|---|---|
| 1 | Install 10 tree-sitter grammar packages via `uv add` | ~5 min |
| 2 | Build `languages.py` — centralized registry with per-language queries and thresholds | ~30 min |
| 3 | Refactor `treerunner.py` — language-agnostic measurement functions dispatching via registry | ~30 min |
| 4 | Debug language-specific queries (6 languages had incorrect AST node types or field names) | ~45 min |
| 5 | Update `enricher.py` — language-agnostic tree walk using node type heuristics | ~10 min |

**Debugging notes for future language additions:**
- Always test queries individually with `Query(lang, qstr)` before adding to the registry
- "Impossible pattern" errors mean the pattern can never match — usually a wrong field name or child ordering
- "Invalid node type" errors mean a node type doesn't exist in the grammar — check the actual AST via `parser.parse()` and tree walk
- Use single-line query strings to avoid whitespace issues with triple-quoted strings in Python dicts

### Session 4 (2026-06-01): Cyclomatic complexity, boolean complexity, god class detection

**Duration:** ~1 hour  
**Outcome:** Three new tree-sitter-only metrics implemented, adding quantitative code quality signals that Semgrep cannot provide.

| Metric | What it measures | Implementation |
|---|---|---|
| `cyclomatic_complexity` | Decision points per function (if, for, while, except, and/or) + 1 | `_walk_and_count()` — walks AST subtree counting decision node types |
| `boolean_complexity` | Boolean operators inside single if conditions | `_walk_if_conditions()` — finds if_statement nodes, counts and/or in condition subtree |
| `god_class` | Class methods, lines, and dependencies | `measure_god_class()` — uses classes query, counts methods + deps + lines |

All three are language-agnostic, driven by `decision_types` and `boolean_operator_types` lists in the language registry.

**Total metrics:** 8 tree-sitter measurements + Semgrep findings across 3 tiers.

### Session 5 (2026-06-01): Cognitive complexity, module coupling, structural diff

**Duration:** ~1 hour  
**Outcome:** Three more high-leverage tree-sitter capabilities added targeting readability, architecture, and changelog awareness.

### Session 6 (2026-06-01): Error handling, public ratio, import depth, clones, purity

**Duration:** ~1.5 hours  
**Outcome:** Five more metrics added, bringing PRISM to 16 total tree-sitter measurements — the final set.

| Metric | What it measures | Value |
|---|---|---|
| `error_handling_coverage` | Ratio of risky calls inside try/except for each function | Caught `safe_load`: 0/2 risky calls guarded |
| `public_ratio` | Public vs private top-level functions per module | Caught test module: 10 public, 1 private (91%) |
| `import_depth` | Dot-depth of import statements | Caught `os.path.join.something` depth 4 (threshold 3) |
| `code_clone` | Structural similarity between function ASTs | Caught 3 identical helpers + 2 clone loops |
| `function_impurity` | Side effects: global mutation, param mutation, impure calls | Caught `impure_function`: modifies global, calls random/print |

**Implementation notes:**
- `measure_error_handling` walks each function's AST, identifies calls matching a set of risky function names (open, eval, subprocess, fetch, etc.), and checks if a try/except ancestor exists. Ratio = handled / total.
- `measure_visibility_ratio` counts function names starting with `_` as private, everything else as public. Language-agnostic.
- `measure_import_depth` counts dots in import path strings from the imports query.
- `measure_code_clones` builds a structural signature (sequence of non-identifier AST node types) for each function and compares pairs via longest-common-subsequence. Signature length must be >= 10 to avoid trivial matches. Similarity threshold: 0.8.
- `measure_function_purity` scans for three impurity signals: module variable assignment, parameter mutation, and calls to known-impure functions (I/O, random, time, subprocess). Module-level variables are detected by scanning top-level assignments.

**Total metrics:** 16 tree-sitter measurements + structural diff + Semgrep findings.

### Final Metric Count

| Category | Count | Metrics |
|---|---|---|
| Basic structure | 4 | param count, nesting depth, function length, cyclic imports |
| Dead code | 1 | dead_function |
| Complexity | 3 | cyclomatic, cognitive, boolean |
| Architecture | 2 | god class, module instability |
| Error handling | 1 | error_handling_coverage |
| Encapsulation | 1 | public_ratio |
| Coupling | 1 | import_depth |
| Duplication | 1 | code_clone |
| Purity | 1 | function_impurity |
| Diff | 3 | diff_function_added/removed/changed |
| Semgrep | dynamic | curated + community rules |
| **Total** | **16+** | tree-sitter only, sub-millisecond after parse |

| Capability | What it measures | Why it matters |
|---|---|---|
| **Cognitive complexity** | Nesting-weighted cyclomatic. `if` inside `if` inside `if` = depth weight. SonarSource metric. | More accurate at predicting readability than raw cyclomatic. `highly_complex` scored 172 vs cyclomatic 17. |
| **Module instability** | Martin's Ce/(Ca+Ce) per module. Afferent (incoming) vs efferent (outgoing) coupling count. | Flags modules that are too unstable (fragile, too many outgoing deps) or too stable (dead weight, no outgoing deps). Available in project mode. |
| **Structural diff** | Tree-sitter AST comparison between current file and git HEAD. Detects added/removed/changed functions and signatures. | Gives the model awareness of what changed since last commit without running git diff. Available via `structural_diff()` in treerunner. |

**Architectural notes:**
- All three are pure tree-sitter (no Semgrep, no network, sub-millisecond after parse)
- Module coupling uses the same import graph infrastructure as cyclic import detection
- Structural diff requires git but uses `git show HEAD:path` — no working tree modifications
- Configuration for all three lives in the language registry (`decision_types`, thresholds)

**Total metrics:** 11 tree-sitter measurements + Semgrep findings + structural diff.

---

*End of specification. If you are an AI reading this with no prior context: you have the full picture. Do not re-invent rejected concepts. Do not add program slicing, call graphs, LLM integration, fix loops, implication chains, or additional scanners. The validated, tested, working concept is documented above.*
