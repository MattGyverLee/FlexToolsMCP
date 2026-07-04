# FlexToolsMCP — Workflow Summary

A compact view of the six-stage workflow: what the user does, what it unlocks, and how the system protects them. For implementation specifics see [`workflow-detail.md`](workflow-detail.md).

---

## The Six Stages at a Glance

| # | Stage | Tool(s) | What it does for the user |
| --- | --- | --- | --- |
| 1 | Session Start | `flextools_start` | Establishes the runtime contract before a single line is written |
| 2 | Module Scaffold | `flextools_start_module` · `flextools_get_module_template` | Hands back a conformant template with the write-guard already wired |
| 3 | API Discovery | 8 search/lookup tools | Replaces guessing with cited signatures from the indexed source |
| 4 | Code Authoring | (LLM-side) | AI writes against real APIs and the runtime primer's invariants |
| 5 | Run Module | `flextools_run_module` (twice) | Dry-run first, write-mode second — both pass the same gauntlet |
| 6 | Inspect & Undo | `get_operation_logs` · `get_session_history` · `undo_last_operation` | Review, learn, and roll back |

---

## Stage 1 — Session Start

### Workflow
User picks an `api_mode` (`flexicon` recommended) and optionally a project. `write_enabled` defaults to `False`.

### Opportunity
The session response is a **runtime primer** — five sections pushed proactively so the AI sees runtime invariants *before* writing code:

- **output** — `report.Info / Warning / Error / Blank`
- **clickable_refs** — `project.BuildGotoURL(obj)` for FlexTools UI navigation
- **write_protection** — the `if modifyAllowed:` contract
- **multistring_placeholder** — how `'***'` empty fields are normalized
- **namespace_helpers** — pre-injected utilities (MCP-runner only, not in FlexTools GUI)

This replaces the failure mode where the AI reinvents reporters, guards, and empty-field checks from scratch.

### Safeguards
- Read-only by default — must opt in to write mode explicitly
- Discovered-APIs set cleared on every session — no stale lookups carry over
- Warnings emitted when `write_enabled=True` or `project_name` is empty

---

## Stage 2 — Module Scaffold

### Workflow
Either the interactive wizard (`flextools_start_module`) collects name/synopsis/api_target/`modifies_db`/domain, or the user fetches a template directly (`flextools_get_module_template`).

### Opportunity
The generated template is conformant out of the box: `docs` dict, `Main()`, `FlexToolsModule` binding — the three pieces gate 3 will check for. When `modifies_db=True`, the write-guard is **auto-injected**, so users can't forget it.

### Safeguards
- `if not modifyAllowed: return` baked in for write modules
- `DRY_RUN` flag baked in when `include_dry_run=True`
- Style-guide references cited in the response
- `test_project` field encourages running on a backup first
- Three flavors with explicit aliases — no silent flavor mismatch

---

## Stage 3 — API Discovery

### Workflow
The AI uses up to eight discovery tools to cite real signatures from the indexed source. Every call adds entries to `discovered_apis`.

| Tool | Use when |
| --- | --- |
| `search_by_capability` ★ | Natural-language intent — "how to add a gloss to a sense" |
| `get_object_api` ★ | Drilling into a specific entity's surface (returns the required `import_statement`) |
| `get_navigation_path` | Finding a path between entity types (returns a code skeleton) |
| `find_examples` | CRUD samples by method/operation/object |
| `resolve_property` | Fixing "no attribute" errors via casting suggestions |
| `get_wrapper_dependencies` | Seeing what a wrapper "really" does under the hood |
| `find_wrappers_for_lcm` | Surfacing **explicit gaps** when a symbol isn't wrapped |
| `list_categories` / `list_entities_in_category` | Orientation when the target entity isn't yet known |

### Opportunity
Discovery is the source-of-truth substitute for the AI's training memory. Every method name in the eventual module came from a lookup the user can audit. Cross-flavor gaps are surfaced as `gaps[]`, never silently absent — when no wrapper covers a symbol, the response says so and points to `api_mode='liblcm'`.

### Safeguards
- Gate 6 refuses `run_module` when `discovered_apis` is empty — structurally prevents code-from-memory
- Gate 10 catches typos via difflib match against the index

---

## Stage 4 — Code Authoring (LLM-side)

### Workflow
The AI assembles the module body from the building blocks gathered in stages 1–3, rather than inventing it from training memory. Each prior stage hands forward a concrete artifact that drops directly into the code:

- **From Stage 1 (runtime primer)** — the calling conventions: `report.*` signatures, `project.BuildGotoURL`, the `if modifyAllowed:` guard, the `'***'` normalization rule, the pre-injected helpers.
- **From Stage 2 (template)** — the module skeleton: `docs` dict, `Main(project, report, modifyAllowed)`, `FlexToolsModule` binding, the auto-injected write-guard and `DRY_RUN` flag.
- **From Stage 3 — `get_object_api`** — the **`import_statement`** (verbatim) and the exact method signatures, parameter names, and return types for the entities being touched.
- **From Stage 3 — `get_navigation_path`** — a code skeleton for entity-to-entity traversal, with null-safety and casts already in place.
- **From Stage 3 — `find_examples`** — real CRUD snippets that anchor the call shape (argument order, paired calls, surrounding loop structure).
- **From Stage 3 — `resolve_property` / `find_wrappers_for_lcm`** — casting fixes and explicit `gaps[]` advisories that decide whether to stay in flexicon or drop to liblcm.

The result is structured, concrete, compilable code where every method name traces back to an audit trail of lookups — not a plausible-sounding hallucination. If a needed call wasn't discovered, the AI is expected to go back to Stage 3 rather than guess; gate 6 enforces this structurally.

### The contract (DO)

```python
report.Info(f"Updated {hw}", project.BuildGotoURL(sense))   # 2nd arg = LCM object

if modifyAllowed:                                            # guard ALL mutations
    sense.Gloss.set_String(ws, "new gloss")

if not LexSenseOperations(p).GetGloss(s):                    # wrapper getters normalize ''
    ...
```

### Anti-patterns that will be rejected (DON'T)

| Anti-pattern | Caught by |
| --- | --- |
| Use a method you didn't discover | Gate 6 (empty discovery); Gate 10 (typos) |
| Mutate without a guard | Gate 4 — even one unguarded mutation blocks |
| Mix import flavors (`from flexlibs ...` in flexicon mode) | Gate 9 — the silent-fail risk |
| Polymorphic property access without a cast | Gate 5 — routes to `resolve_property` |
| Partial module (`def Main` without `docs` + binding) | Gate 3 |

### Opportunity
The runtime primer + discovery citations + style guide produce code that is correct on the first run more often — the cost of authoring drops because the rework loop is shorter.

---

## Stage 5 — Run Module

### Workflow — dual-pass execution

**5a · Dry-run** (REQUIRED FIRST)
- `write_enabled=False` → `modifyAllowed=False`
- Code runs end-to-end; every `if modifyAllowed:` branch is skipped
- Verifies report output, refs, and absence of exceptions

**5b · Write-mode** (only after 5a is clean)
- `write_enabled=True` → `modifyAllowed=True`
- Per-project lock acquired; mutations actually run; undo entry recorded

Both passes traverse the same 12-gate gauntlet.

### Opportunity
The dry-run pass exercises every code path that isn't behind the write guard — typos, casts, imports, and output shape are all caught before any database risk. The user sees the report output and confirms intent before promoting.

### Safeguards — the 12-gate gauntlet

Hard-block gates (✓) refuse execution; advisory gates return structured errors.

| # | Gate | ✓ | What it catches |
| --- | --- | --- | --- |
| 1 | Server health |  | Kernel state not initialized |
| 2 | Syntax parse |  | `SyntaxError` (tree reused by 3–10) |
| 3 | Partial module | ✓ | `def Main` without `docs` / `FlexToolsModule` |
| 4 | Unprotected mutation | ✓ | Any mutation outside a recognized guard |
| 5 | Polymorphic casting | ✓ | Base-interface property access without a cast |
| 6 | API discovery |  | Empty `discovered_apis` set |
| 7 | Undefined variables |  | Names that aren't imports/locals/FlexTools-provided |
| 8 | Missing Operations imports |  | Uses `LexSenseOperations` etc. without importing |
| 9 | Wrong-library imports |  | Imports that don't match `api_mode` (silent-fail risk) |
| 10 | Invalid project chain |  | `project.<typo>` caught via difflib |
| 11 | Per-project write lock |  | Serializes concurrent writes to the same project |
| 12 | Subprocess timeout |  | 300s default; subprocess crash can't take down the server |

Additional runtime safeguards:
- **Subprocess isolation** — module exceptions can't crash the MCP server
- **UTF-8 stdout/stderr** — IPA, tones, Yi script never break the result marker
- **Bounded reporter buffer (10k messages)** — verbose loops don't OOM; oldest dropped, count surfaced

---

## Stage 6 — Inspect & Undo

### Workflow
Three review-and-rollback tools, each addressing a different question.

| Tool | Question it answers |
| --- | --- |
| `flextools_get_operation_logs` | What worked, what failed, and what should I prefer next time? |
| `flextools_get_session_history` | What happened in this session, and what can I undo? |
| `flextools_undo_last_operation` | Queue a rollback for the most recent CUD operation |

### Opportunity
- **Pattern learning loop** — every run records success/failure; recommendations sharpen over sessions and feed back into Stage 3 discovery
- **Audit trail** — every operation captured with timestamp, code, output, and project
- **Review-first undo** — `undo_last_operation` returns the operation summary but does *not* auto-execute `ActionHandler.Undo()`. The user reviews, then runs the rollback intentionally.

### Safeguards
- Undo stack only populates when `write_enabled=True`
- Pattern tracker persists across sessions, so bad-pattern advisories survive restart
- Three stacks (history / undo / redo) — full operation context preserved

---

## Cross-Cutting Safeguards (defense in depth)

No single check is load-bearing; failure of any one is recoverable.

### Safety defaults
- **Read-only by default** at both `start` and `run_module` — write mode requires saying yes twice
- **Dry-run before write** is the convention; the AI is expected to show 5a output before requesting promotion
- **Mandatory API discovery** — gate 6 makes "code from memory" structurally impossible (override available as an intentional escape hatch)
- **Auto-injected `modifyAllowed` guard** in scaffolded write modules — the template removes the trap

### Isolation & runtime
- **Per-project async write lock** — concurrent CUD ops on the same project serialize; reads and other projects don't queue
- **Subprocess isolation + UTF-8 reconfig** — module crashes contained; non-Latin scripts safe
- **Bounded reporter buffer** — verbose loops degrade gracefully (drop-oldest, surfaced count)
- **Three-tier casting helper injection** — minimal context cost when no casting is needed, full safety when ambiguity exists

### Learning & visibility
- **Pattern learning loop** — success/failure recorded, recommendations surfaced, fed back into discovery
- **Undo stack with review-first semantics** — rollback is intentional, never automatic
- **Cross-flavor coverage gaps surfaced explicitly** — `gaps[]` in `find_wrappers_for_lcm` responses turns silent absence into actionable guidance
- **Runtime primer pushed at session start** — the AI sees the conventions before authoring, not after a failure
