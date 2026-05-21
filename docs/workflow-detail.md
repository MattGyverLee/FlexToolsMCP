# FlexToolsMCP — Workflow Detail Pages

Textual companion to the six detail SVGs in `docs/workflow-detail-*.svg`. Complements [`workflow-map-with-foundation.svg`](workflow-map-with-foundation.svg), the integrated overview.

---

## Detail 1 — Stages 1 & 2: Session Start & Module Scaffold

> Runtime contract is established here, before any code is written.

### Stage 1 — Session Start

**Tool:** `flextools_start`

#### Inputs

| Parameter | Type | Notes |
| --- | --- | --- |
| `api_mode` | string | `"flexlibs2"` ★ recommended · `"flexlibs_stable"` · `"liblcm"` |
| `project_name` | string, optional | FieldWorks project name (can be set later) |
| `write_enabled` | bool | **default FALSE** — dry-run by default |
| `task` | string, optional | natural-language task hint for early discovery |

All settings can be updated later; `project_name` and `write_enabled` are also accepted on `run_module`.

#### Internal actions (in order)

1. `session_id = strftime("%Y%m%d-%H%M%S")`
2. `session_state.clear_discovered_apis()` — forces re-discovery
3. `api_versions ← detected from APIIndex` (liblcm, flexlibs2, flexlibs_stable)
4. `session_state.configure(api_mode, output_type="auto", project, write, versions)`
5. `rotate_logging_to_session(session_id)` — per-session log file

No subprocess. No DB connection. Cheap, idempotent, restart-friendly.

#### Response — the runtime primer (5 sections)

Pushed proactively so the AI sees runtime invariants BEFORE writing code.

- **output** — `report.Info / report.Warning / report.Error / report.Blank`. `print()` works but bypasses message counts and ref links.
- **clickable_refs** — `project.BuildGotoURL(obj) → str`; passed as 2nd arg to `report.*` makes the message clickable in FlexTools UI.
- **write_protection** — `if modifyAllowed: <mutation>` required for any DB mutation; refused at validation if missing (gate 4).
- **multistring_placeholder** — FLEx stores `'***'` for unset multilingual fields. flexlibs2 wrapper getters normalize to `''`; raw C# access still returns `'***'`.
- **namespace_helpers** — pre-injected, no import needed: `is_empty_multistring(text)`, `FLEX_EMPTY_PLACEHOLDER`, `find_writing_system(project, query)`, `list_writing_systems(project)`. ⚠ MCP-runner only — these helpers are NOT present when the module runs in FlexTools.

Plus `next_steps` (5-step user guide), `mode_info`, session summary, warnings (e.g. "WRITE MODE ENABLED" if `write_enabled=True` or "no project_name set").

#### Safeguards

- ✓ Read-only by default (`write_enabled=False` unless explicitly opted in)
- ✓ Session ID generated for log isolation (per-session file)
- ✓ Discovered-APIs set cleared — every session re-discovers (no stale state)
- ✓ Runtime primer pushed proactively, before authoring
- ✓ Warning emitted if `write_enabled=True` or `project_name` empty

### Stage 2 — Module Scaffold

**Tools:** `flextools_start_module` (interactive wizard) · `flextools_get_module_template` (direct fetch)

#### `flextools_start_module` — interactive wizard

**REQUIRED**

| Field | Notes |
| --- | --- |
| `module_name` | `"Export Custom Data"` |
| `synopsis` | 1–2 sentence description |
| `api_target` | `flexlibs2` ★ · `flexlibs_stable` · `liblcm` |
| `modifies_db` | bool — gates the write-guard auto-injection |
| `domain` | `lexicon` · `grammar` · `texts` · `media` · `general` |

**CONDITIONAL** (asked when `modifies_db=True`)

| Field | Notes |
| --- | --- |
| `include_dry_run` | bool — RECOMMENDED true (bakes `DRY_RUN` flag) |

**OPTIONAL** — `test_project` encourages backup-first testing.

#### `flextools_get_module_template` — direct template fetch

| Parameter | Notes |
| --- | --- |
| `flavor` | `flexlibs2` · `flexlibs_stable` · `liblcm` (aliases: `stable`, `advanced`) |

Returns `template + flavor guidance + style-guide refs + 5-step next_steps`. Module-init cache saves 50–100 ms per repeat request.

#### Generated template structure

```python
# Module header (name, synopsis, api_target)
from flextoolslib import *

DRY_RUN = True   # injected if include_dry_run

docs = {FTM_Name, FTM_Version, FTM_ModifiesDB,
        FTM_Synopsis, FTM_Description}

def Main(project, report, modifyAllowed):
    if not modifyAllowed:     # auto-injected on writes
        report.Error("write access required")
        return
    if DRY_RUN:               # if include_dry_run
        report.Warning("DRY RUN mode — no changes")
    report.Info("Starting...")
    # TODO: implementation
    report.Info("Done.")

FlexToolsModule = FlexToolsModuleClass(Main, docs)

if __name__ == '__main__':
    print(FlexToolsModule.Help())
```

Three required pieces: `docs` dict, `Main()`, `FlexToolsModule` binding. Gate 3 catches partials.

#### Safeguards

- ✓ `if modifyAllowed:` guard auto-injected when `modifies_db=True`
- ✓ `DRY_RUN` flag baked in (recommended for any write module)
- ✓ `FLEXTOOLS-STYLE-GUIDE.md` references in response (key sections cited)
- ✓ `test_project` field encourages running on backup project first
- ✓ Three flavors with explicit aliases (no silent flavor mismatch)

---

## Detail 2 — API Index Foundation

> The substrate every other stage stands on. Without these indexes the AI guesses; with them every signature is cited from source.

Pre-computed at refresh time via AST (Python) + .NET reflection. Versioned per library. Loaded once at server startup.

### Source indexes

#### `liblcm_api.json`
- **Source:** LibLCM C# assemblies (FieldWorks data layer)
- **Extraction:** .NET reflection via pythonnet — reads compiled DLLs, captures interfaces, classes, properties, methods, generic args, attribute metadata
- **Coverage:** 100% — every public symbol, every overload
- **Refresh:** `python src/refresh.py --liblcm-only`
- Requires pythonnet + FieldWorks DLLs at refresh time only

#### `flexlibs2_api.json` ★
- **Source:** FlexLibs 2.0 Python wrapper (~90% LCM coverage)
- **Extraction:** AST static analysis — parses `.py` files, captures Operations classes, decorators, type hints, docstrings, inline examples
- **Coverage:** ~1400 methods · 99% docs · 82% examples
- **Refresh:** `python src/refresh.py --flexlibs2-only`
- Primary recommendation for new modules — best documentation

#### `flexlibs_api.json`
- **Source:** FlexLibs stable (legacy shallow wrapper)
- **Extraction:** AST static analysis (same parser as flexlibs2)
- **Coverage:** ~40 functions · stable, FW-version-tolerant
- **Use when:** FieldWorks < 9.0 or compatibility-bound scripts
- **Refresh:** `refresh.py --flexlibs-only`
- LibLCM fallback covers the gaps the stable wrapper doesn't reach

### Derived structures

| Structure | Consumer | What it does |
| --- | --- | --- |
| **Semantic embeddings** | `search_by_capability` | sentence-transformers vectors over method summaries / names / docs. Lazily loaded. Query `"add a gloss to a sense"` → `LexSenseOperations.SetGloss` |
| **Casting index** | gate 5 + helper-injection tier | map `(entity_type, property) → cast_target`. e.g. `ICmObject.HeadWord` requires cast to `ILexEntry(obj).HeadWord`. Drives `detect_casting_needs()` and the none/minimal/full helper injection |
| **Navigation graph** | `get_navigation_path` | directed graph of entity-to-entity paths. e.g. `ILexEntry → ILexSense → ILexExample → ILexExampleSentence`. Returns code skeleton with traversals, casts, null-safety |
| **Examples corpus** | `find_examples` | CRUD samples extracted from docstrings + inline code blocks. Indexed by method_name, operation_type (create/read/update/delete/iterate/search), object_type |

### Cross-cutting artifacts

#### Bridge files (cross-flavor coverage map)
- Consumers: `get_wrapper_dependencies`, `find_wrappers_for_lcm`
- Files: `flexlibs2_lcm_bridge_*.json`, `flexlibs_lcm_bridge_*.json`, `reverse_mapping_liblcm-*.json`
- Forward: wrapper method → LCM internals it touches
- Reverse: LCM symbol → wrappers that cover it
- Surfaces gaps explicitly — `<coverage gap>` rather than silent absence

#### Version multiplexing
- Multiple versions coexist in `/index/`: `flexlibs2_api_v2.1.5.json`, `flexlibs2_api_v2.2.0.json` ← active per session
- Server detects installed library version, loads matching index, auto-refreshes if missing
- See `docs/VERSIONING.md` for the full resolution algorithm

#### Refresh process — regeneration is offline
- No network, no external API calls, auditable
- `python src/refresh.py` — refresh all three indexes
- Flags: `--flexlibs2-only`, `--flexlibs-only`, `--liblcm-only`
- Run when source library updates, or first-time setup, or version change detected
- See `flexlibs2_analyzer.py`, `liblcm_extractor.py`

### Consumers — what reads from the foundation

**Stage 3 — every discovery tool**
- `search_by_capability` (embeddings) · `get_object_api` (entities)
- `get_navigation_path` (graph) · `find_examples` (corpus)
- `resolve_property` (casting index) · `list_categories`
- `get_wrapper_dependencies` · `find_wrappers_for_lcm` (bridges)

**Pre-flight gates (Stage 5)**
- Gate 4 — mutation patterns from index drive `certify_readonly`
- Gate 5 — `casting_index` drives `detect_casting_needs`
- Gate 9 — known import patterns per `api_mode`
- Gate 10 — entity-name typo difflib match against index

**Error hints & recommendations**
- `did_you_mean` — looked up against entity/method names
- `PolymorphicAttributeError` — casting suggestions from index
- Pattern tracker — recommendations cite real method paths
- Cross-flavor advisories — bridge files name missing wrappers

> Without the foundation, none of the above can cite real signatures — and the AI is back to guessing.

---

## Detail 3 — Stages 3 & 4: API Discovery & Code Authoring

> The AI cites real signatures here, then writes code that respects the runtime contract.

### Stage 3 — API Discovery (eight tools, one mandate)

Every method name must come from the index. Every Stage 3 tool call adds entries to `session_state.discovered_apis`. Gate 6 in the pre-flight gauntlet refuses `run_module` if that set is empty — this is the structural reason the AI cannot ship code without first citing real signatures from the index.

#### `search_by_capability` — semantic NL search via embeddings
- **in:** `query`, optional `api_mode`
- **out:** ranked methods + similarity
- example: `"how to add gloss to sense"` → `LexSenseOperations.SetGloss`, `LexSenseOperations.AddGloss`
- Registers as `discovered_api` on every hit

#### `get_object_api` ★ — drill into entity-level API surface
- **in:** `object_type`, `summary_only`
- **out:** methods, properties, signatures, examples, **`import_statement`**
- `summary_only=true` to peek at large entities, then full call for specifics
- **REQUIRED** before using an API in `run_module`

#### `get_navigation_path` — find paths between entity types
- **in:** `from_object`, `to_object`
- **out:** traversal path + code skeleton
- example: `ILexEntry → ILexSense → ILexExample → ILexExampleSentence`
- includes null-safety + cast operations in the skeleton

#### `find_examples` — code samples by method/operation/object
- **in:** `method_name | operation_type | object_type`
- **out:** snippet + surrounding context
- `operation_type ∈ {create, read, update, delete, iterate, search}`
- 82% of flexlibs2 methods have at least one example

#### `resolve_property` — casting / property resolution
- **in:** `property_name`, `context_entity`
- **out:** casting requirement, polymorphic warnings, fix snippets per flavor
- Used to fix "X has no attribute Y" errors. e.g. `ICmObject.HeadWord` → `ILexEntry(obj).HeadWord`
- Also called automatically when gate 5 trips

#### `get_wrapper_dependencies` — wrapper method → LCM internals
- **in:** `method` (`Class.Method`), `library`
- **out:** `lcm_deps`, properties, methods, repositories, factories, `mapping_type`
- Use to see what a wrapper "really" does, or whether dropping to liblcm gets you more
- Reads from `flexlibs2_lcm_bridge_*.json`

#### `find_wrappers_for_lcm` — LCM symbol → wrapper coverage
- **in:** `lcm_name`, `kind`, `include[]`
- **out:** coverage per library + **`gaps[]`**
- `kind ∈ {entity, factory, repository, method, property, auto}`
- Explicit `gaps[]` — never silently absent. "if no wrapper covers it, drop to api_mode='liblcm'"

#### `list_categories` / `list_entities_in_category` — taxonomy navigation
- Categories: lexicon, grammar, texts, media, notebook, lists, system
- Useful when the AI doesn't yet know which entity it should be looking at
- Low-cost orientation; shouldn't dominate discovery

### Stage 4 — Code Authoring (LLM-side, off-server)

Must respect the runtime primer.

#### Assembly from building blocks, not invention from memory

Stage 4 is the moment the AI assembles a module from concrete artifacts handed forward by the previous stages — not an invention pass against training memory. Each prior stage produces a building block that drops directly into the source:

- **From Stage 1 (runtime primer)** — calling conventions: `report.*` signatures, `project.BuildGotoURL`, the `if modifyAllowed:` guard, `'***'` normalization, the pre-injected namespace helpers.
- **From Stage 2 (template)** — the module skeleton: `docs` dict, `Main(project, report, modifyAllowed)`, `FlexToolsModule` binding, the auto-injected write-guard and `DRY_RUN` flag.
- **From Stage 3 — `get_object_api`** — the verbatim `import_statement` plus exact method signatures, parameter names, and return types for every entity touched.
- **From Stage 3 — `get_navigation_path`** — a code skeleton for entity-to-entity traversal with null-safety and casts already in place.
- **From Stage 3 — `find_examples`** — real CRUD snippets that anchor call shape (argument order, paired calls, surrounding loop structure).
- **From Stage 3 — `resolve_property` / `find_wrappers_for_lcm`** — casting fixes and explicit `gaps[]` advisories that decide whether to stay in flexlibs2 or drop to liblcm.

Every method name in the finished module traces back to an audit trail of lookups. If a needed call wasn't discovered, the AI is expected to return to Stage 3 rather than guess; gate 6 enforces this structurally.

#### DO — invariants from the runtime primer

**Output**
```python
report.Info(msg)   report.Warning(msg)   report.Error(msg)
report.Blank()
```

**Clickable refs (FlexTools UI integration)**
```python
report.Info(f"Updated {hw}", project.BuildGotoURL(sense))
```
2nd arg must be a concrete LCM object — not an HVO or string.

**Write protection — guard ALL mutations**
```python
if modifyAllowed:
    sense.Gloss.set_String(ws, "new gloss")
```
Refused at gate 4 if missing — even in dry-run mode.

**Multistring `'***'` placeholder**

Wrapper getters normalize `'***'` → `''`. Use:
```python
if not LexSenseOperations(p).GetGloss(s):  ...
```
Direct C# access (`sense.Gloss.BestAnalysisAlternative.Text`) still returns `'***'`.

**Pre-injected helpers** — no import needed: `is_empty_multistring`, `find_writing_system`, `list_writing_systems`.

#### DON'T — anti-patterns the gauntlet will reject

| Anti-pattern | Caught by |
| --- | --- |
| Use a method you didn't discover | Gate 6 (empty `discovered_apis`); Gate 10 catches typos |
| Mutate without a guard | Gate 4 — even one unguarded mutation blocks the whole script |
| Mix import flavors (e.g. `from flexlibs import ...` in flexlibs2 mode) | Gate 9 (wrong-library imports) — the silent-fail risk |
| Access polymorphic property without cast (`sense.Owner.HeadWord`) | Gate 5 — sends you to `resolve_property` |
| Define a partial module (`def Main` without `docs` + `FlexToolsModule` binding) | Gate 3 |

---

## Detail 4 — Stages 5 & 6: Run Module & Inspect / Undo

> The only stage that touches the database — and the only stage that records, learns, and rolls back.

### Stage 5 — Run Module

**Tool:** `flextools_run_module` — twice (5a dry-run REQUIRED · 5b write-mode promotion)

#### Dual-pass execution

**5a · Dry-run pass** — REQUIRED FIRST
- `write_enabled = False  →  modifyAllowed = False`
- Code runs end-to-end, but every `if modifyAllowed:` branch is skipped
- Verifies: report output, message counts, clickable refs, no exceptions
- **Goal:** prove the read path before risking the write path

→ **promote** — only when 5a is clean

**5b · Write-mode pass**
- `write_enabled = True  →  modifyAllowed = True`
- Per-project `asyncio.Lock` acquired. Mutations actually run. Undo entry recorded.
- Both passes traverse the 12-gate gauntlet — gate 11 (write lock) only fires on 5b.

#### Subprocess execution flow

1. 12-gate pre-flight (see Detail 5)
2. Build runner script with embedded `MODULE_CODE`
3. Reconfigure stdout/stderr to UTF-8 (errors=replace)
4. Inject fake `flextoolslib` (`FlexToolsModuleClass`, `FTM_*`)
5. Inject `SimpleReporter` + namespace helpers
6. Inject three-tier casting helpers (none/minimal/full)
7. Spawn subprocess via `run_script_async` (timeout=300s)
8. `FLExInitialize() → OpenProject(name, write_enabled)`
9. `exec(MODULE_CODE)` — prefer `Main(p, r, write_enabled)`
10. `CloseProject() · FLExCleanup()`
11. Print `===FLEXTOOLS_RESULT_JSON===` + result dict
12. Parent parses, attaches certification + did_you_mean hints

Subprocess isolation — module exception cannot crash the MCP server itself.

#### SimpleReporter (in subprocess)

Mimics FLExTools `FTReporter` so modules behave identically inside MCP and inside FlexTools GUI.

- **Methods:** `Info`, `Warning`, `Error`, `Blank`, `Debug`, `ProgressStart/Update/Stop`, `FileURL`
- **Each call:** appends to in-memory message list AND prints to console (transparent reporting)
- **Buffer cap:** 10000 messages — overflow drops oldest and increments `dropped_message_count`
- **Counts tracked:** `info_count`, `warning_count`, `error_count`, `total_messages`
- If buffer overflowed, summary surfaces `dropped_messages: N` so the AI can warn the user.

#### Pattern tracker

Every run records, recommendations follow.

- **Records:** code, success, error, error_type per operation
- **Categorizes:** `api_patterns` (success/failure counts), `error_patterns`
- **Generates recommendations:**
  - `preferred_patterns` — high success rate
  - `patterns_to_avoid` — high failure rate
  - `common_errors_needing_fix`
- Persisted to `~/.flextoolsmcp/logs/patterns.json` — survives sessions.

### Stage 6 — Inspect & Undo

Three tools for review, learning, and rollback.

#### `flextools_get_operation_logs`

Logs + recommendations dashboard.

- **Reads:** `~/.flextoolsmcp/logs/operations.log`
- **Inputs:** `log_lines`, `errors_only`, `include_patterns`
- **Returns:**
  - `recent_logs` (last N lines)
  - `recommendations` (preferred/avoid/errors)
  - `statistics`: `total_operations`, `total_successes`, `total_failures`, `success_rate`, `unique_api_patterns`, `unique_error_patterns`
- `errors_only=true` to focus on failures across the session
- Recommendations feed back into Stage 3 discovery

#### `flextools_get_session_history`

Audit trail + undo availability.

- **Reads:** `session_state.operations_history`
- **Inputs:** `include_operations` (full code/output)
- **Returns:**
  - `initialized`, `api_mode`, `project`, `write_enabled`
  - history summary (counts by tool/result)
  - `undo_available`, `redo_available`
  - `next_steps` (contextual)
- Each `OperationRecord` captures: `timestamp`, `tool`, `args_summary`, `script_code`, `output`, `success`, `undoable`, `project`, `extracted_details`
- Three stacks: `operations_history` (full), `undo_stack`, `redo_stack`

#### `flextools_undo_last_operation`

Queues a rollback, doesn't auto-execute.

- **Pre-conditions:** `can_undo() == True`, `write_enabled` was `True`
- **Action:** `pop_undo()` returns the `OperationRecord`, returns the operation summary, reports `remaining_undoable`, `redo_available`
- **Note:** Tool does NOT auto-call `ActionHandler.Undo()`. User reviews, then runs `Undo()` via `run_module`.
- Review-first design — undo is intentional, not automatic.

---

## Detail 5 — Pre-flight Gauntlet

> 12 gates before the subprocess launches. Each gate returns a structured error. Red gates HARD BLOCK execution. Runs on every pass (5a and 5b).

### Architectural notes

- AST parsed ONCE (gate 2) and reused across gates 3–10 — no redundant parsing.
- Gates short-circuit: first failure returns immediately with a structured `error_code` and remediation hint.
- Gate 5 also drives the three-tier helper-injection strategy (none/minimal/full) — lighter context cost when no casting issues are detected.
- Gate 11 acquires the per-project `asyncio.Lock` only when `write_enabled=True` AND code is mutating.

### The 12 gates

| # | Gate | Validator | HARD BLOCK | Catches | Error code |
| --- | --- | --- | --- | --- | --- |
| 1 | Server health | `validate_server_state()` |  | kernel state not initialized; `api_index`, `pattern_tracker`, `log_dir` reachable | `server_state_error` |
| 2 | AST / syntax parse | `ast.parse(code)` |  | `SyntaxError` — missing colons, unclosed parens, bad indent. Tree feeds gates 3–10 | `syntax_error` + line# |
| 3 | Partial module | `detect_partial_module_structure()` | ✓ | `def Main` + missing `docs` / `FlexToolsModule` binding. Override: `skip_module_check=True` | `partial_module_structure` |
| 4 | Unprotected mutation | `certify_script_readonly()` | ✓ | any mutation outside a recognized guard (`if modifyAllowed:`, `project.writeEnabled`, `with project.modifyEnabled:`) | `unprotected_code` |
| 5 | Polymorphic casting | `detect_casting_needs()` | ✓ | base interface property access (e.g. `sense.Owner.HeadWord`). Drives helper-injection tier. Reads `casting_index` from foundation | `casting_issues_detected` |
| 6 | API discovery gate | `len(session.discovered_apis) > 0` |  | "I'll just write code from memory" — no Stage 3 tool was called | `api_discovery_required` |
| 7 | Undefined variables | `detect_undefined_variables()` |  | MCP-internal names that leaked. Allows: imports, locals, FlexTools-provided (`project`, `report`, `modifyAllowed`) | `undefined_variables` |
| 8 | Missing Operations imports | `detect_missing_operations_imports()` |  | uses `LexEntryOperations`, `LexSenseOperations` etc. without importing. Enforces the `import_statement` contract from `get_object_api` | `missing_imports` |
| 9 | Wrong-library imports | `detect_wrong_library_imports()` |  | imports that don't match `api_mode` (e.g. `from flexlibs import ...` in flexlibs2 mode). The silent-fail risk | `wrong_library_imports` |
| 10 | Invalid project chain | `detect_invalid_project_chains()` |  | `project.<name>` typos. Conservative — only blocks when difflib finds a high-confidence match (≥0.7) | `invalid_api_chain` |
| 11 | Per-project write lock | `get_project_write_lock(name)` |  | acquires `asyncio.Lock` keyed by project. Fires only when `write_enabled=True` AND mutating (5b pass) | (lock acquisition) |
| 12 | Subprocess timeout | `run_script_async(timeout=300)` |  | configurable via `timeout_seconds`. UTF-8 reconfigured stdout/err. Temp `.py` cleaned up on exit | `Execution timeout` |

---

## Detail 6 — Cross-Cutting Safeguards

> Defense in depth — every gate has a fallback, every state change is recorded, every flavor mismatch is surfaced. No single check is load-bearing; failure of any one is recoverable.

### Safety defaults

#### Read-only by default
- **Where:** `flextools_start`, `flextools_run_module`
- **What:** `write_enabled` defaults to `False` everywhere unless explicitly opted in by the user
- **Why:** dry-run is the cheap path; mutations should be a deliberate, named choice
- **Cascade:** `modifyAllowed=False` inside `Main`; gate 11 (write lock) doesn't fire; undo stack stays empty
- A user must say "yes, write" twice — `start()` and `run_module()`

#### Dry-run before write (5a → 5b)
- **Where:** Stage 5 dual-pass pattern
- **What:** always run with `write_enabled=False` first, verify report output, then promote to write
- **Why:** the read path exercises every code path that isn't behind `if modifyAllowed:` — typos, casts, imports, output shape are all covered before risk
- **Convention:** the AI must show 5a output to the user before requesting `write_enabled=True`

#### Mandatory API discovery
- **Where:** gate 6 + Stage 3 tools
- **What:** `run_module` refuses with `api_discovery_required` when `session.discovered_apis` is empty
- **Why:** the AI cannot ship code from memory; every method name must come from a Stage 3 lookup
- **Cascade:** hallucination risk reduced because the foundation is the source-of-truth for every cited signature
- Override: `skip_api_check=true` (intentional escape hatch)

#### Auto-injected modifyAllowed guard
- **Where:** `flextools_start_module` wizard
- **What:** when `modifies_db=True`, the scaffolded `Main()` starts with `if not modifyAllowed: return`
- **Why:** users (and AIs) often forget the guard; baking it into the template removes the trap
- **Cascade:** gate 4 (unprotected mutation) becomes a backstop, not a primary line of defense
- `DRY_RUN` flag also injected when `include_dry_run=True`

### Isolation & runtime

#### Per-project async write lock
- **Where:** gate 11, `get_project_write_lock(name)`
- **What:** `asyncio.Lock` keyed by project name; acquired only when `write_enabled=True` AND mutating
- **Why:** two concurrent CUD ops on the same project can corrupt the database — locks serialize them
- **Granularity:** by project name, not global — read-only ops and ops on other projects don't queue
- Read-only ops never lock (parallelizable by design)

#### Subprocess isolation + UTF-8 reconfig
- **Where:** `run_script_async`, runner template
- **What:** module code runs in a child process; stdout/stderr reconfigured to UTF-8 errors=replace
- **Why:** module exception cannot crash the MCP server; tones, IPA, Yi script never break the result marker
- **Recovery:** on subprocess crash the runner returns a structured error rather than raising on the server
- Default timeout 300s; temp `.py` cleaned up on exit

#### Bounded reporter buffer (10k messages)
- **Where:** `SimpleReporter` inside the runner
- **What:** `max_messages=10000`, oldest dropped on overflow
- **Why:** verbose loops (every entry, every sense) can produce 100k+ messages — naive collection OOMs
- **Surface:** `dropped_message_count` returned in summary; "Output exceeded buffer" note added if `>0`
- Most-recent retained — the tail of execution is what matters

#### Three-tier casting helper injection
- **Where:** `_get_casting_helpers_code()` before `exec`
- **What:** three injection levels:
  - `none` → no casting issues, skip helpers
  - `minimal` → inject only the names code touches
  - `full` → inject the whole suite (defensive default)
- **Why:** lighter context cost when not needed, full safety when ambiguity exists
- Tier chosen by gate 5 pre-flight result

### Learning & visibility

#### Pattern learning loop
- **Where:** `pattern_tracker` · `~/.flextoolsmcp/logs/patterns.json`
- **What:** every run records `(code, success, error, type)`; tracker classifies into preferred / to-avoid / errors
- **Loop:** Stage 5 records → Stage 6 reads → recommendations surfaced → Stage 3 considers them
- **Persistence:** survives sessions; corpus grows over time, recommendations get sharper
- Self-tuning — no manual curation required

#### Undo stack (`ActionHandler.Undo`)
- **Where:** `session.undo_stack`, `undo_last_operation`
- **What:** every CUD op recorded as `OperationRecord` with timestamp, code, output, project
- **Review-first design:** tool returns the operation to undo but does NOT auto-call `ActionHandler.Undo()`
- **Why:** undo must be intentional — user reviews, then runs `ActionHandler.Undo()` via `run_module`
- Three stacks: history (full), undo, redo

#### Cross-flavor coverage gaps surfaced
- **Where:** bridge files, `find_wrappers_for_lcm`
- **What:** response includes explicit `gaps[]` list naming libraries with no coverage for the requested symbol
- **Why:** silent absence is the worst-case — the AI tries to use a wrapper method that doesn't exist
- **Action:** when `gaps[]` is non-empty, advisory says "drop to api_mode='liblcm' for this operation"
- Negative knowledge surfaced as positive guidance

#### Runtime primer pushed at start
- **Where:** `flextools_start` response · `RUNTIME_PRIMER`
- **What:** 5-section payload pushed proactively (output, refs, write protection, '***', helpers)
- **Why:** the AI sees runtime invariants BEFORE writing any code — primes the conventions
- **Saves:** the Dennis-style debugging arc where the AI reinvents reporters, write guards, '***' handling
- Proactive teaching beats reactive correction
