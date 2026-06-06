---
name: prism
description: "Structural code analysis — measures cyclomatic complexity, nesting depth, function length, dead functions, cyclic imports, code clones, error handling coverage, parameter counts, and more across 12 languages. Use when: reviewing code quality before commit, auditing for structural issues, cross-checking your own analysis, quantifying complexity of flagged functions, or preparing a final review. Trigger words: analyze, audit, review, complexity, dead code, structural analysis, code quality, metrics."
compatibility: "Requires `prism` CLI on PATH. Install from github.com/k3-2o/prism."
---

# PRISM — Structural Code Analysis

## Setup

Check if prism is available:

```bash
which prism
```

If not found, ask the user: **"prism is not installed. Install it from github.com/k3-2o/prism?"**
If they agree, clone and install:

```bash
git clone https://github.com/k3-2o/prism ~/prism && cd ~/prism && uv tool install .
```

Then verify:

```bash
which prism
```

## Workflow

### Step 1: Run PRISM

Choose speed based on context:

| Situation | Command | Speed |
|---|---|---|
| Quick check after an edit | `prism --structure-only <file>` | ~0.5s |
| Every 3-5 iterations | `prism <file>` or `prism <dir>` | ~10s |
| Final audit before commit | `prism --community <dir>` | ~50s |

Default to `--structure-only`. Use `--community` only for final reviews.

### Step 2: Read the Output

PRISM outputs JSON. Look for:

- **Metrics exceeding thresholds** (cognitive complexity > 15, cyclomatic > 10, function length > 60, nesting > 4)
- **Dead functions** — zero callers within the analyzed scope
- **Code clones** — similar code blocks (similarity > 0.8)
- **Cyclic imports** — modules that import each other
- **Error handling gaps** — functions with unguarded risky calls

Each measurement includes the function name, location, current value, threshold, and cross-file callers.

### Step 3: Read the Flagged Code Yourself

PRISM gives you numbers, not code. For every flagged measurement, read the file:

- **Complexity flags** — is the function genuinely hard to follow, or is it a state machine that needs the branches?
- **Dead function flags** — is it truly dead (no callers), or is it an entry point (main(), CLI command, API handler)?
- **Code clones** — is it a natural pattern (getter/setter pairs) or actual duplication?
- **Error handling** — PRISM counts try/except coverage but doesn't know if the *right* exception is caught

### Step 4: Adversarial Review

Read the code with an adversarial mindset. PRISM measures structure — it cannot
judge whether the code is *correct*. For every file that was scanned, read beyond
the flags and look for anything that feels wrong.

PRISM's blind spots include (but are not limited to):

- **Logical correctness** — wrong operators, inverted conditions, off-by-one, incorrect assumptions, invariant violations, contradictions
- **Missing edge cases** — null/empty inputs, boundary values, concurrent access, error paths not considered
- **API misuse** — wrong function called, incorrect arguments, missing arguments, wrong return type assumed, error swallowing
- **Architecture / design** — layering breaks, misplaced responsibility, leaky abstractions, over-engineering, inconsistent patterns
- **Security / safety** — unvalidated user input, sensitive data exposure, missing auth checks, unsafe defaults
- **Data flow** — values passed incorrectly across call boundaries, forgotten state transitions, dropped return values
- **Readability / intention** — misleading names, dead comments, commented code, unclear control flow, unnecessary complexity

This list is not exhaustive. Treat it as a starting point. The goal is to find
what PRISM cannot, not to check items off a list.

**Do not decide yet.** Simply note each finding. The adversarial review is
observation, not judgment. Decisions happen in Step 5 when PRISM flags and
adversarial findings are weighed together.

### Step 5: Decide What to Act On

For each flag and each adversarial finding, make a decision:

- **✅ Leave it** — if context justifies the measurement (dataclass with 9 params, state machine with high complexity)
- **🔨 Fix it** — if the finding reveals a genuine issue (dead legacy function, cyclic import, code clone, missing edge case, logic bug)
- **🔨 Remove it** — if it's truly dead code with no future use

### Step 6: Structure Your Response

Present findings in this order:

1. **What PRISM found** — the flagged measurements worth mentioning
2. **What you saw when you read the code** — your own reading of each flagged area
3. **What your adversarial review found** — issues PRISM cannot detect (logic gaps, edge cases, API misuse, architecture violations)
4. **What you decided** — per flag and adversarial finding: ✅ leave, 🔨 fix, or 🔨 remove
5. **What you're doing** — actual changes or next steps

## When to Skip

Do not use PRISM when:
- The codebase is not one of: Python, JS, TS, Go, Rust, Java, Ruby, PHP, C, C++, HCL, Zig
- You need logical correctness analysis (PRISM cannot evaluate whether code does the right thing)
- You need a security audit (PRISM has no security domain knowledge)
- The file is under 50 lines where you can see everything yourself
- Speed matters and you're already confident in the code quality

## Custom Semgrep Rules

Add project-specific Semgrep YAML rules to `~/.prism/rules/`. PRISM loads them automatically on the next scan. Useful for catching project-specific anti-patterns.

## Metrics Reference

PRISM measures 16 metrics. Move detailed docs to reference files if needed, but here are the key thresholds:

| Metric | Threshold | What it means |
|---|---|---|
| `function_length` | > 60 lines | Function may be doing too much |
| `cyclomatic_complexity` | > 10 | Too many decision paths |
| `cognitive_complexity` | > 15 | Hard to follow mentally |
| `nesting_depth` | > 4 | Too many nested control structures |
| `parameter_count` | > 6 | Too many arguments |
| `code_clone` | > 0.8 similarity | Likely duplicated code |
| `boolean_complexity` | > 3 | Complex boolean expression |
