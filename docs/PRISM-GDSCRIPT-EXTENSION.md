# Extending PRISM for GDScript / Godot

**Status:** Unimplemented — design notes for future work.

---

## Why GDScript Is Different

GDScript looks like Python but isn't. It has signals, groups, node references,
built-in types (Vector2, Color, NodePath), and Godot-specific decorators
(`@onready`, `@export`, `@tool`). Most of PRISM's 16 tree-sitter measurements
work in principle, but the signal-to-noise ratio is different from Python.

**What works today (if grammar is added):**

| Metric | Signal in GDScript |
|---|---|
| `function_length` | Verbose `_process` and `_ready` methods are common — catches oversized lifecycle functions |
| `parameter_count` | Useful — Godot signals and custom methods often accumulate params |
| `nesting_depth` | Deep conditionals in state machines, input handling, or UI logic |
| `cognitive_complexity` | Useful — GDScript's lack of pattern matching leads to deep `if/elif` chains |
| `dead_function` | Orphaned utility functions, unused signal handlers |
| `code_clone` | Copied input handling or animation code between scenes |
| `public_ratio` | Misuse of `var` vs `@export var` vs `static var` — public signals vs private implementation |

**What works poorly or not at all:**

| Metric | Why |
|---|---|
| `cyclic_import` | GDScript's node-based scene system makes file-level cycles less meaningful — cycles exist at the scene tree level, not the script level |
| `module_instability` | GDScript's autoload/singleton pattern breaks standard module coupling analysis |
| `function_impurity` | GDScript has no purity concept — side effects are assumed |

---

## What Would Need to Change

### Step 1: Add the Grammar

The grammar exists:

```
PrestonKnopp/tree-sitter-gdscript → language key: "gdscript"
```

Add to `src/prism/engine/languages.py` as a new entry:

```python
"gdscript": {
    "grammar": ts_language_gdscript(),
    "extensions": [".gd"],
    "queries": {
        "function_definition": "(function_definition name: (identifier) @name) @func",
        # same pattern as Python, but node type names may differ
    },
```

### Step 2: Validate Queries

GDScript's AST node types need dumping first:

```bash
python3 -c "
from tree_sitter_gdscript import language
from tree_sitter import Parser
p = Parser()
p.set_language(language())
tree = p.parse(b'func hello(): pass')
print(tree.root_node.sexp())
"
```

Expected node types: `function_definition`, `identifier`, `parameters`,
`body`, `if_statement`, `match_statement`, `for_statement`, `signal_statement`,
`class_definition`, etc. — mostly similar to Python but with GDScript additions.

### Step 3: Extension Detection

Add to `src/prism/engine/languages.py`:

```python
".gd": "gdscript",
```

### Step 4: Semgrep Rules (GDScript-Specific)

If Semgrep supports GDScript (unlikely — check registry), curated rules would
target Godot-specific pitfalls:

| Rule ID | What It Detects |
|---|---|
| `prism.godot.export-without-type` | `@export var name` without type hint (should be `@export var name: String`) |
| `prism.godot.onready-in-method` | `@onready` used on non-field variable |
| `prism.godot.process-without-delta` | `func _process(delta):` that doesn't use `delta` |
| `prism.godot.signal-with-connect` | Signal connected via code when `node.connect()` would be cleaner |
| `prism.godot.scene-path-hardcode` | Hardcoded `res://` paths instead of preload or `@export` references |

Realistically, Semgrep community support for GDScript is minimal to none.
These rules would be PRISM-curated-only, if written.

---

## The Godot Ecosystem Context

GDScript exists inside a broader Godot pipeline. PRISM alone misses most of what
matters for Godot projects:

| Tool | What It Does | PRISM Overlap |
|---|---|---|
| **Godot editor built-in debugger** | Runtime breakpoints, frame profiling, memory tracking | Zero — PRISM has no runtime |
| **godot-lsp** | IDE integration, autocomplete, type checking | Zero — LSP is semantic, PRISM is structural |
| **gdlint / gdtoolkit** | Linting, formatting, style enforcement | Partial — gdlint covers some patterns PRISM would need custom rules for anyway |
| **Scene tree** | Node hierarchy, scene references, signal connections | Zero — PRISM doesn't parse `.tscn` or `.tres` files |
| **C# (Godot Mono)** | Alternative scripting language | Separate — would need C# tree-sitter grammar |

**PRISM's niche for Godot is narrow:** structural awareness during agent-driven
code generation — catching oversized `_process` functions, excessive signal
handler parameters, and deeply nested UI logic. It's not a replacement for the
Godot debugger or gdlint.

---

## Implementation Probability

| Factor | Assessment |
|---|---|
| Grammar exists | ✅ Yes — `tree-sitter-gdscript` is on GitHub and crates.io |
| Grammar packaged for Python | ⚠️ Check — may need manual build / pip availability |
| Tree-sitter queries port | Low effort — GDScript AST is similar to Python, queries mostly copy-paste with renamed node types |
| Extension mapping | Trivial — one line in `languages.py` |
| Semgrep support | ❌ Unlikely — Semgrep community has no GDScript coverage |
| Maintenance burden | Medium — Godot releases can change GDScript syntax (4.0 was a big break) |
| Real-world demand | ❓ Only if you write GDScript regularly |

**Verdict:** Low priority. The grammar exists, the porting effort is small, but
the value depends entirely on how much Godot work you do. If GDScript becomes
a regular part of your workflow, it's a one-hour integration. Until then, the
adversarial review step in SKILL.md already covers GDScript via the model's
general-purpose reading ability.
