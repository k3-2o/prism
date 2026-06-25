---
name: prism
description: "Structural code analysis — measures cyclomatic complexity, cognitive complexity, nesting depth, function length, dead functions (cross-file), unused imports/variables/classes/exports, unreachable code, code clones (structural + token-based), error handling coverage, function purity (interprocedural), god classes, cyclic imports (full path), module instability, churn hotspots, maintainability index, and more across 12 languages. Supports --filter, --fast, --compact, --visualize, entry point awareness, confidence levels, import rule enforcement. Use when: reviewing code quality before commit, auditing for structural issues, cross-checking your own analysis, finding dead code, quantifying complexity, or preparing a final review. Trigger words: analyze, audit, review, complexity, dead code, structural analysis, code quality, metrics, prism."
compatibility: "Requires `prism` CLI on PATH. Install from github.com/k3-2o/prism."
---

# PRISM — Structural Code Analysis (v0.3.0)

## Setup

```bash
which prism
```

If not found:
```bash
git clone https://github.com/k3-2o/prism ~/prism && cd ~/prism && uv tool install .
```

---

## How to Use (Decision Guide)

**⚠️ PRISM is not instant on large repos. The agent MUST size the repo first.**

### Step 0 — Size the repo

```bash
find . -type f \( -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.jsx" -o -name "*.go" -o -name "*.rs" -o -name "*.java" -o -name "*.rb" -o -name "*.php" -o -name "*.c" -o -name "*.cpp" -o -name "*.zig" \) | wc -l
```

### Step 1 — Decide and communicate

Based on the file count, pick the command AND tell the user why:

| Files | Command | Time | What to tell the user |
|---|---|---|---|
| **1** | `prism path/to/file.py` | ~1s | "Running PRISM on this file — one second." |
| **2–49** | `prism .` | ~10-20s | "Running full analysis on <N> files — about 15 seconds." |
| **50–500** | `prism . --fast` | ~5-15s | "<N> files — running fast mode (skips churn/clones/module graph). If you want the full analysis with churn hotspots and dependency graphs, say so and I'll run it in a tmux background pane." |
| **500+** | `prism . --fast` + offer tmux | ~15-60s (fast) | "Repo is huge (<N> files). Running fast mode now. Full analysis (churn, clones, module graph) would take minutes — want me to queue it in a tmux background pane?" |

**Never run `prism .` without --fast on a 500+ file repo without warning the user first.**

### Step 2 — After running, summarize don't dump

Don't paste raw JSON. Read the `summary.by_metric` and tell the user:
- How many findings total
- Top categories (e.g., "89 dead functions, 47 unused imports, 12 unreachable code errors")
- The most interesting finding (e.g., "`handle_request` in `server.py` is dead code — no callers anywhere")

### When to use --fast

`--fast` skips: churn hotspots (git history), cross-file clones (structural + token), module graph (BFS reachability, unused files, cross-file dead functions), interprocedural purity, import rules. It still gives you: complexity, dead code (in-file), unused imports/variables/classes, unreachable code, error handling, god classes, cyclic imports, module coupling.

### When to use other flags

**DO NOT use these casually. They exist for specific situations only.**

| Flag | Use when | DO NOT use when |
|---|---|---|
| `--filter dead_function,unused_import` | I am hunting dead code specifically. I ran the full audit first, saw the summary, and now I'm drilling into one category. | I'm running the first pass. Give the full picture first. |
| `--compact` | I am piping output into another tool, writing a script, or doing CI. | I am going to read the output myself. JSON is easier to navigate. |
| `--visualize` | I am discussing architecture, dependencies, or "how are these files connected?" | I am doing metrics or dead code. A DOT file adds nothing. |
| `--entry-points main,handler` | The project is a framework app (Flask, Next.js, Express) and I see files like `app.py`, `routes.py`, `pages/` that would be flagged as dead. | The project is a library or CLI tool where every public function is an intentional export. |

### Full analysis on huge repos — tmux background

If the user has 500+ files and wants full analysis, offer this exact command:

```bash
tmux new-session -d -s prism-audit 'cd /path/to/repo && prism . > prism-full.json 2>&1 && echo "DONE — results in prism-full.json"'
```

Tell the user: "It's running in tmux session 'prism-audit'. Check progress with `tmux attach -t prism-audit`. Results go to `prism-full.json`."

---

## Reading the Output

PRISM outputs JSON structured as:

```json
{
  "prism": {"version": "0.3.0"},
  "project": {"root": ".", "files_scanned": 14, "total_nloc": 3592, ...},
  "summary": {"findings": 454, "by_metric": {"dead_function": 32, "code_clone": 112, ...}},
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
          "callers": [{"function": "...", "file": "...", "line": 1}]
        }
      ]
    }
  },
  "import_graph": {"main": ["config", "languages"]}
}
```

Key points:
- `summary.by_metric` gives an instant overview of what's flagged
- `files` is grouped by file path — file name appears once, findings sorted by line number
- `confidence` ranges from 60% (likely dead) to 100% (certain)
- `detail` explains why the finding was flagged
- `callers` shows cross-file callers (empty list = no callers found)
- `import_graph` shows module dependencies for visualization

---

## What PRISM Finds

### Dead Code (cross-file)
| Metric | What | Confidence |
|---|---|---|
| `dead_function` | No callers in any project file (cross-file via module graph) | 70% |
| `unused_export` | JS/TS export with no cross-file consumers | 60% |
| `unused_import` | Imported name never referenced | 90% |
| `unused_variable` | Local variable assigned but never read | 60% |
| `unused_class` | Class defined but never referenced | 80% |
| `unreachable_code` | Code after return/break/raise/throw | 100% |
| `unused_file` | File not reachable from any entry point (BFS) | 80% |

### Complexity
| Metric | Threshold | Confidence |
|---|---|---|
| `cyclomatic_complexity` | > 10 | — |
| `cognitive_complexity` | > 15 | — |
| `boolean_complexity` | > 3 conditions in one if | — |
| `nesting_depth` | > 4 (AST-based, not indent) | — |
| `nloc` | Source lines of code (per file) | — |
| `maintainability_index` | < 40 (100 − CC×3 − nest×5 − params×2 − len÷10) | — |

### Architecture
| Metric | What |
|---|---|
| `god_class` | Methods > 10, lines > 100, or deps > 6 |
| `module_instability` | Ce/(Ca+Ce) > 0.8 (unstable) or < 0.2 (dead weight) |
| `cyclic_import` | Full cycle path: A → B → C → A |
| `import_rule_violation` | Custom may_not/may_only rules violated |

### Risk
| Metric | What |
|---|---|
| `error_handling_coverage` | Ratio of risky calls that are try-guarded (< 80% flagged). 50+ risky call patterns per language |
| `function_impurity` | Module var mutation, param mutation, impure calls. Interprocedural (follows call graph) |

### Clones
| Metric | What |
|---|---|
| `code_clone` | AST structural + token-based, in-file + cross-file |

### Change
| Metric | What |
|---|---|
| `churn_hotspot` | Complexity × commit frequency (> 2.0 flagged) |
| `diff_function_added/removed/changed` | Functions added/removed/changed vs git HEAD |

---

## Config (.prism.toml)

```toml
[project]
entry_points = ["main", "handler"]

[dead_code]
whitelist = { "register_routes" = "Called by framework" }

[import_rules]
"no-feature-to-feature" = { pattern = "features/*", may_not = ["features/*"], severity = "error" }
"core-isolation" = { pattern = "core/*", may_only = ["core/*"], severity = "warning" }
```

---

## The Adversarial Review Workflow

### Step 1: Run PRISM

```bash
prism . --filter dead_function,unused_import,unreachable_code,unused_variable
```

### Step 2: Read the flagged code

For every finding, read the actual file. PRISM gives numbers, not code.

- **Dead function** — is it truly dead, or is it called dynamically (getattr, reflection, framework)?
- **Unused import** — is it used in type annotations only? (Python: `TYPE_CHECKING` blocks)
- **Unreachable code** — is the return/break/raise intentional and the dead code leftover?
- **Unused variable** — is it assigned for side effects? Is it a tuple unpack?

### Step 3: Adversarial review

Read beyond the flags. PRISM measures structure, not correctness. Look for:

- Logical correctness — wrong operators, off-by-one, inverted conditions
- Missing edge cases — null/empty inputs, boundary values, concurrent access
- API misuse — wrong function called, incorrect arguments, error swallowing
- Architecture breaks — layering violations, wrong responsibility, leaky abstractions
- Security — unvalidated input, sensitive data exposure, missing checks
- Readability — misleading names, dead comments, unnecessary complexity

### Step 4: Decide

For each finding:

| Decision | When |
|---|---|
| ✅ **Leave it** | Context justifies it (state machine with high CC, framework entry point) |
| 🔨 **Fix it** | Genuine issue (dead legacy function, cyclic import, clone, logic bug) |
| 🔨 **Remove it** | Truly dead code with no future use |

### Step 5: Structure your response

1. What PRISM found — flagged measurements worth mentioning
2. What you saw reading the code — your own assessment
3. Adversarial findings — issues PRISM can't detect
4. Decision per finding — ✅ / 🔨 / 🔨
5. What you're doing — actual changes

---

## When to Skip PRISM

- Codebase is not one of the 12 supported languages
- File is under 50 lines (just read it)
- You need logical correctness analysis (PRISM measures structure)
- You need a full security audit (use bandit, gosec, semgrep separately)
