# Extending PRISM for HCL / Terraform

**Status:** Unimplemented — design notes for future work.

---

## Why HCL Is Different

HCL is declarative. It has blocks, not functions. No control flow, no parameters,
no classes, no import system. Most of PRISM's 16 tree-sitter measurements simply
don't apply.

**What works today:**

| Metric | Signal |
|---|---|
| `nesting_depth` | Catches deeply nested blocks (resource > dynamic > nested block) |
| `diff_function_*` | Catches added/removed/changed blocks between git refs |
| `function_length` | Measures block line count — weak but functional |

**What's missing but could be built:**

| Potential Metric | What It Would Catch | Priority |
|---|---|---|
| **`resource_attribute_count`** | Resources with too many attributes (doing too much). Count attributes in a `resource` block. Threshold > 30. | High |
| **`unused_variable`** | Variable declared in `variables.tf` but never referenced in any `.tf` file. | High |
| **`hardcoded_value`** | String literals in resource blocks that look like they should be variables (`"t2.micro"` where `var.instance_type` is the pattern). | Medium |
| **`reference_chain_depth`** | `module.web.aws_instance.app.security_group` — deep dot-chains signal tight coupling. Depth > 4. | Medium |
| **`missing_output`** | Resources with `exported = true` or similar that produce data, but no `output` block captures it. | Low |

---

## Implementation Guide

### File Structure

Create a new file `src/prism/engine/hcl_metrics.py` — separate from the main 16-metric
`treerunner.py`. This keeps HCL-specific logic isolated. The `run()` function in
`treerunner.py` would call `hcl_metrics.run()` when the language is `"hcl"`.

### Step 1: Resource Attribute Count

Tree-sitter query for resource blocks:

```
(resource body: (body) @body)
```

Walk children of `body`, count children of type `attribute`. Report if > 30.

```python
def measure_resource_attributes(tree, data, file_path):
    query = Query(lang, "(resource body: (body) @body)")
    count = 0
    for match in query.matches(tree.root_node):
        body = match.captures["body"][0]
        for child in body.children:
            if child.type == "attribute":
                count += 1
    if count > 30:
        # report resource with too many attributes
```

### Step 2: Unused Variables

Parse all `.tf` files in the project. Collect variable declarations from
`variables.tf` (or any file with `variable` blocks). Then scan all other `.tf`
files for references to `var.<name>`. Any variable declared but never referenced
is unused.

```
variable "region" {}      → declared name: "region"
var.region                 → referenced name: "region"
```

### Step 3: Hardcoded Values

This is the trickiest. Heuristics for detecting hardcoded values that should be variables:
- String literals that appear more than once across the codebase (DRY violations)
- String literals that match patterns like instance types, AMI IDs, CIDR blocks
- Number literals for configuration values (port numbers, timeout seconds, size limits)

Approach: collect all string literals from resource blocks. Group by value.
Report values that appear 3+ times across different resources.

### Step 4: Reference Chain Depth

Walk `reference` nodes in the AST. Count dot-separated segments.

`module.web.aws_instance.app` → depth 4

Report if any reference has depth > 4.

### Step 5: Wire Into PRISM

In `src/prism/main.py`, when `_detect_language` returns `"hcl"`, call
`hcl_metrics.run(file_path)` alongside the standard `treerunner.run()`.

```python
if lang == "hcl":
    from prism.engine import hcl_metrics
    findings.extend(hcl_metrics.run(tree, data, file_path))
```

No changes needed to output format — the new measurements follow the same
`_make_measurement()` pattern and appear in the same `measurements` array.

---

## Or Just Use Dedicated Tools

PRISM will never be as good at Terraform analysis as:

- **tflint** — checks provider-specific issues (unused arguments, invalid types)
- **checkov** — checks security misconfigurations (open S3 buckets, unencrypted storage)
- **terraform validate** — checks syntax and reference validity

PRISM's value for HCL is narrow: it gives the agent structural awareness during
code generation. The metrics above would make it genuinely useful, but they're
not a replacement for dedicated tools in CI/CD.
