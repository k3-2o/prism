---
name: prism
description: Deep deterministic structural code analysis. Trigger when analyzing code quality, reviewing project structure, measuring complexity, finding dead code, detecting cyclic imports, checking function purity, reviewing code clones, or preparing a final audit before commit. Use when the user says "prism", "analyze this", "review this code", "check for issues", "audit", "complexity check", "dead code", or "structural analysis".
---

# PRISM — Structural Code Analysis

PRISM is a structural fact-checker. It counts parameters, nesting depth, dead
functions, cyclic imports, code clones, and similar quantitative properties.
It does not understand the code's purpose, domain constraints, or whether a
high count is actually a problem in context. A function with 9 parameters may
be the correct design for its domain. A 172-line function may be appropriate
for the complexity it handles.

**These measurements exist for your awareness — integrate them into your own
judgment. You have the full context. You decide what to act on and what to
leave as-is.**

A measurement exceeding a threshold is NOT a mandate to fix. It is a structural
fact. You decide whether it matters in this specific context.

## Three Speed Tiers

PRISM has three modes selectable via a flag:

| Mode | Command | Latency | When to use |
|---|---|---|---|
| Structure-only | `--structure-only` | ~0.5s | Every iteration — fast structural check |
| Default | *(no flag)* | ~10s | Every 3-5 iterations — adds curated Semgrep rules |
| Community | `--community` | ~50s | Final audit before commit — adds full Semgrep community library |

Choose the appropriate tier for your current task. The user may explicitly
request a mode, or you can decide based on context.

## How to call PRISM

```bash
cd <project-dir> && uv run prism [--structure-only|--community] <path>
```

Examples:

```bash
uv run prism --structure-only src/auth.py         # fast check on one file
uv run prism src/auth.py                          # default: + curated rules
uv run prism --community src/                     # full project audit
uv run prism --structure-only src/                # fast project-level check
```

If you are unfamiliar with the project structure, use `ls` to explore first.
PRISM auto-detects language from file extension.

## What PRISM measures (16 metrics)

```
size:          function_length, parameter_count, import_depth
complexity:    cyclomatic_complexity, cognitive_complexity,
               boolean_complexity, nesting_depth
architecture:  god_class, module_instability, cyclic_import
risk:          error_handling_coverage, function_impurity, dead_function
design:        code_clone, public_ratio
diff:          diff_function_added/removed/changed
```

Supported languages: Python, JavaScript, TypeScript, Go, Rust, Java, Ruby, PHP,
C, C++, HCL (Terraform), Zig.

## What PRISM does NOT cover

- Logical correctness — it cannot tell if the code does the right thing
- Validation adequacy — it does not check input validation or edge cases
- Naming conventions — no judgment on identifier quality
- Security best practices — it has no domain-specific security knowledge
- Error handling adequacy — it counts try/except coverage but doesn't know
  if the right exceptions are caught or handled properly
- Test coverage — no execution data
- Performance — no runtime measurement

**These gaps are your responsibility.** After reviewing PRISM's output, read
the measured files directly and look for issues PRISM cannot detect.

## The workflow

1. **Call PRISM** — choose the right speed tier for the task
2. **Acknowledge the measurements** — note what exceeded thresholds and what
   didn't. Remember: a high count may be correct design choice.
3. **Read the measured files** — especially if they are not already in your
   context. PRISM's cross-file caller enrichment is its strongest value —
   it shows callers you may not have loaded.
4. **Review adversarially** — look for logical errors, validation gaps,
   naming problems, and security concerns that PRISM missed.
5. **Decide what to act on** — not every threshold exceedance needs a fix.
   You have the full context. You decide.

Custom Semgrep rules live in `src/prism/rules/`. PRISM ships 5 example rules.
If the project needs domain-specific pattern checks, write new Semgrep YAML
rules following the example format and save them there — PRISM loads them
automatically on the next scan.
