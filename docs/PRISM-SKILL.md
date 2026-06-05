---
name: prism
description: "Structural code analysis via tree-sitter and Semgrep for code review, auditing, and quality checks. Use when reviewing code quality, auditing before commit, checking complexity/dead code/cyclic imports/coupling/purity, or preparing a final review. Trigger words: prism, analyze, audit, review, complexity, dead code, structural analysis."
compatibility: "Requires Python 3.12+ and uv. The project must have PRISM installed (uv sync in the prism project directory)."
---

# PRISM — Structural Code Analysis for Agent Judgment

## What This Skill Is For

This skill gives you access to PRISM, a tool that produces **structural measurements** about code — parameter counts, nesting depth, function length, cyclomatic complexity, dead functions, cyclic imports, code clones, error handling coverage, and more across 12 languages.

**But this is not a "run tool → get answer" skill.** PRISM is a **counter, not a judge**. It outputs numbers. You provide the judgment. You have context about the codebase, its domain, its constraints. PRISM does not. Use the numbers as input to your own analysis, not as authoritative findings.

## When to Use This Skill

Use PRISM when you need to:

- **Audit code quality** before committing or merging
- **Find structural issues** the model might miss (cross-file dead code, cyclic imports, code clones across large files)
- **Cross-check your own analysis** — use PRISM as an adversarial second pass to catch things you overlooked
- **Quantify complexity** — get objective numbers for functions that feel complex
- **Prepare a final review** with the `--community` flag for comprehensive pattern matching

Do NOT use PRISM when:

- The codebase is not Python/JS/TS/Go/Rust/Java/Ruby/PHP/C/C++/HCL/Zig
- You need logical correctness analysis (PRISM cannot evaluate whether code does the right thing)
- You need security audit (PRISM has no domain-specific security knowledge)
- Speed matters more than thoroughness on small files (<50 lines where you can see everything)

## How PRISM Works

PRISM has three speed tiers. Choose based on your task:

| Mode | Command | Speed | When to Use |
|---|---|---|---|
| Structure-only | `uv run prism --structure-only <path>` | ~0.5s | Every iteration — fast structural check |
| Default | `uv run prism <path>` | ~10s | Every 3-5 iterations — adds 5 curated Semgrep rules |
| Community | `uv run prism --community <path>` | ~50s | Final audit before commit — full Semgrep community library |

**Default to `--structure-only` for speed.** Use default or `--community` only when you need pattern-based checks or are doing a final review.

## The Adversarial Workflow (5 Steps)

This is the correct way to use PRISM. Follow these steps in order.

### Step 1: Call PRISM with the Right Tier

Choose your mode based on context:

```bash
# Fast structural check on a single file
uv run prism --structure-only src/auth.py

# Full file with curated rules
uv run prism src/auth.py

# Full project audit with community rules
uv run prism --community src/

# Fast project-level structural scan
uv run prism --structure-only src/
```

### Step 2: Read the Output — But Don't Accept It as Truth

PRISM outputs JSON. Read it. Note:

- Which metrics exceeded thresholds
- Which functions are flagged
- Cross-file callers (this is PRISM's strongest signal — it shows you callers you may not have loaded)

**But interrogate the output.** Ask yourself:
- Is this threshold actually appropriate for this codebase? (A Django view with 8 params might be fine. A utility function with 8 params might not.)
- Is this "dead function" actually an API entry point? PRISM only checks intra-file calls.
- Does this code clone actually matter, or is it a natural pattern in this domain?

**A measurement exceeding a threshold is NOT a mandate to fix.** It is a structural fact. You decide.

### Step 3: Read the Measured Files Yourself

PRISM gives you numbers. It does NOT give you the code. You must read the files PRISM analyzed — especially:

- Functions flagged for high complexity or length
- Files with cyclic imports
- Code that PRISM flagged as cloned
- Error handling coverage gaps

When reading, look for things PRISM **cannot** measure:
- Logical correctness — does this code actually do the right thing?
- Validation — are edge cases handled? Are inputs sanitized?
- Naming — are function/variable names clear and accurate?
- Security — are authentication, authorization, and data protection handled?
- Error handling quality — PRISM counts try/except but doesn't know if the *right* exception is caught or handled correctly
- Performance — are there N+1 queries, unnecessary allocations, or expensive operations in hot paths?
- Testability — is the code structured to be testable?

**PRISM is a cheap complement to your own analysis, not a replacement for it.**

### Step 4: Review Adversarially — Use PRISM to Catch Your Own Blind Spots

Here's the key insight most reviews miss: **you should use PRISM to check your own work.**

Before PRISM, you might have read a file and said "this looks fine." After running PRISM, you might discover:
- A function you didn't notice has 12 parameters
- A function you assumed was called from elsewhere has zero callers
- Two files you wrote independently have the same logic
- A module you thought was independent is part of a cyclic import chain

**Run PRISM as your adversarial second pass.** Then re-read the files and ask: "What did I miss the first time? What did PRISM catch that I should have caught myself?"

### Step 5: Decide What to Act On

Combine everything:
1. PRISM's measurements
2. Your own reading of the code
3. Your understanding of the project's domain, constraints, and conventions

Then decide:

```text
PRISM flags function X for parameter_count >6.
You read function X. It's a __init__ in a dataclass with 9 params.
Decision: ✅ Leave it. Dataclass constructors naturally have many params.

PRISM flags function Y for dead_function (zero callers).
You read function Y. It's a legacy helper with no callers in the codebase.
Decision: 🔨 Remove it.

PRISM flags module Z for cyclic_import.
You read both files. They reference each other's types.
Decision: 🔨 Refactor into a shared types module.
```

**Not every flag needs a fix. Context decides.**

### A Good Pattern for Structuring Your Response

When you've run PRISM and worked through the steps above, your response tends to be clearer if you walk through your thinking in this order:

1. **What PRISM found** — the measurements worth mentioning
2. **What you saw when you read the code** — your own reading of the flagged areas
3. **What you decided** — for each flag: ✅ leave it (with why), 🔨 fix it, or 🔨 remove it
4. **What you're doing** — the actual changes or next steps

You don't have to follow this rigidly. But if your response feels messy, try this shape. It keeps the judgment visible before any action.

## What PRISM Measures (16 Metrics)

| Category | Metrics | What to Watch For |
|---|---|---|
| Size | `function_length`, `parameter_count`, `import_depth` | Long functions, too many params, deep imports |
| Complexity | `cyclomatic_complexity`, `cognitive_complexity`, `boolean_complexity`, `nesting_depth` | Hard-to-follow control flow |
| Architecture | `god_class`, `module_instability`, `cyclic_import` | Design problems across modules |
| Risk | `error_handling_coverage`, `function_impurity`, `dead_function` | Functions that fail silently or are unused |
| Design | `code_clone`, `public_ratio` | Duplicated code, encapsulation issues |
| Change | `diff_function_added/removed/changed` | What changed since last commit (requires git) |

Supported languages: Python, JavaScript, TypeScript, Go, Rust, Java, Ruby, PHP, C, C++, HCL (Terraform), Zig.

## What PRISM Does NOT Measure (Your Responsibility)

| PRISM Cannot | You Must Check |
|---|---|
| Whether code is logically correct | Read the code. Does it do what it should? |
| Whether inputs are validated | Check for edge cases, missing validation |
| Whether naming is clear | Read function/variable names |
| Whether security is adequate | Check auth, injection, secret handling |
| Whether error handling is correct | PRISM only counts try/except. Does it catch the right thing? |
| Whether testing exists | Check for test files |
| Whether performance is acceptable | Look for N+1, hot loops, expensive ops |
| Whether the design fits the domain | You know the project's constraints. PRISM doesn't. |

## Custom Semgrep Rules

PRISM ships 5 example rules in `src/prism/rules/` showing the YAML format. For domain-specific pattern checks, write new Semgrep YAML rules and save them there — PRISM loads them automatically on the next scan. This is useful for catching project-specific anti-patterns that generic rules miss.

## Common Pitfalls

- **Don't over-index on threshold violations.** A 200-line function might be the cleanest way to handle a complex state machine. Judge by context, not by the number.
- **Don't trust "dead function" blindly.** If a function has cross-file callers listed in its enrichment context, it's not dead — PRISM only checks intra-file calls directly.
- **Don't skip reading the files.** PRISM's output is not a substitute for reading the code. Always read the files behind the numbers.
- **Don't forget to check your own blind spots.** PRISM can catch things you overlooked. Use it as an adversarial second pass.
- **Don't use `--community` for every iteration.** It's 50s. Use `--structure-only` for fast iterations and `--community` only for final audits.
