# Data model: Exclusive-access gate

## ExclusiveOnlyOperation (table row)

Lives in `server/exclusive_access.py` as `EXCLUSIVE_ONLY_OPERATIONS`, a tuple of
frozen rows. It is the single source for the detector, the refusal message
and the docs table (a test checks that `docs/SHARED-MODE.md` lists every
category).

| Field | Type | Notes |
|---|---|---|
| `key` | str | Stable id, e.g. `ws.create`, `cf.create`, `ws.raw.manager_set` |
| `category` | `"writing_system"` \| `"custom_field"` | |
| `failure_class` | `"crashes_holder"` \| `"silently_lost"` | WS rows are `crashes_holder` (seen live). CF rows are `silently_lost` (from source) |
| `wrapper` | `(class, frozenset[method])` or None | e.g. `("WritingSystemOperations", {"Create","Ensure",...})` |
| `raw_names` | frozenset[str] | Attribute names that match on their own (unique to the LCM interface) |
| `raw_receiver_methods` | `(frozenset[receiver], frozenset[method])` or None | Generic method names, matched only on these receivers |
| `raw_assignments` | frozenset[str] | Attribute names whose assignment counts (`MarkForDeletion`, `DefaultFontSize`, ...) |
| `reason` | str | Plain language, one sentence |
| `evidence` | str | Citation (live evidence file or LCM source line) |

Validation: every `wrapper` method must exist in the shipped flexicon index
with `is_mutating: true`. A test enforces this, so a flexicon rename turns CI
red. Value methods (`SetValue` and the others) must never appear.

## ExclusiveOnlyMatch (detector output)

| Field | Type |
|---|---|
| `key` | str (row key) |
| `category` | str |
| `failure_class` | str |
| `call` | str, rendered as `Class.Method` or `ast.unparse` of the receiver plus attribute |
| `line` | int \| None (wrapper rows from the certifier may lack a line; the detector fills it from its own AST pass where it can) |
| `source` | `"wrapper"` \| `"raw"` |

`detect_exclusive_only_operations(code, tree, cert) -> list[ExclusiveOnlyMatch]`
returns the matches de-duplicated on `(key, line)` and sorted by line.

## RequiresExclusiveAccessDetail (error detail, `extra="forbid"`)

Field order follows `ProjectLockedDetail`: shared fields first, then the
gate-specific ones.

| Field | Type | Notes |
|---|---|---|
| `error_code` | `Literal["requires_exclusive_access"]` | |
| `guidance` | str | The close, re-submit, reopen steps |
| `verdict` | `"open_shared"` \| `"unknown"` | |
| `holder_pid` | int \| None | From the probe |
| `holder_process` | str \| None | |
| `operations` | list[ExclusiveOnlyMatch] | At least one |
| `remedy` | str | Same text as `guidance`, but for `unknown` it also explains that FLEx could not be confirmed closed |

## Gate decision (state)

| `write_enabled` | matches | probe verdict | Outcome |
|---|---|---|---|
| False | any | any | No gate (guarded code does not run) |
| True | none | any | No gate. Existing behavior |
| True | yes | `free`, `stale_lock` | Passes this gate. The existing write path decides |
| True | yes | `open_shared` | **Refused**: `requires_exclusive_access` |
| True | yes | `unknown` | **Refused**: `requires_exclusive_access` (FLEx could not be confirmed closed) |
| True | yes | `open_exclusive`, `held_by_other` | `project_locked` (existing refusal; this gate defers) |

## validate_only addition

`project_lock.exclusive_access` = `{required: bool, operations:
list[ExclusiveOnlyMatch], blocking: bool}`. `blocking` is true when the real
run would refuse under the table above. The key is present only when the
probe ran.

## Conditional calls (FR-002b amendment)

- `ExclusiveOnlyOperation.conditional` and `ExclusiveOnlyMatch.conditional`
  (bool, default False). Only `ws.ensure` (`WritingSystemOperations.Ensure`)
  sets it. `ws.wrapper` keeps the other writing-system mutators.
- Active lists (`exclusive_access.read_active_writing_systems(fwdata_path)`):
  `{vernacular: [tag], analysis: [tag]}` from the LangProject `CurVernWss` /
  `CurAnalysisWss` `<Uni>` elements, streamed from the `.fwdata`, or None.
  It is pure filesystem and never opens the project. The `.ldml` store is
  not used: store-present does not mean active. `execution._ACTIVE_WS_CACHE`
  caches the result per `.fwdata` path on `(size, mtime_ns)`, so a cache hit
  costs one `stat()`. A failed read is not cached.
- Guard probe (`execution._peer_schema_guard_available`): in the server
  process. A mismatch with the run's flexicon fails closed through
  `PEER_SCHEMA_GUARD='required'`.
- `plan_conditional(matches, ensure_call_args(tree), active, guard_available)`
  returns `ConditionalPlan{refuse, notes, satisfied, deferred}`. Rules:
  - any unconditional match refuses everything;
  - no guard refuses everything;
  - a literal tag active in its category is satisfied;
  - a literal tag that would be added refuses;
  - a non-literal tag, or an unreadable file, is deferred.
- Runner `PEER_SCHEMA_GUARD`: `off` (verdict not gated), `on` (gated,
  backstop), `required` (a conditional call was allowed; the run stops with
  `PeerSchemaGuardUnavailable` if the guard cannot be enabled).
- Success result: `exclusive_access` = `{decision: "allowed_conditional",
  verdict, satisfied, deferred_to_runtime, note}`.
- `RequiresExclusiveAccessDetail.stage`: `preflight` | `runtime`.
- validate_only: when only conditional matches remain on a gated verdict, it
  makes the same plan from the same file read: `blocking` (refuse or not),
  `conditional: true`, `deferred_to_runtime`, and `notes` when it refuses.

## Sync-at-open note (US5, conditional)

If the step ships, it adds `shared_mode.sync_at_open` = `{attempted: bool, ok:
bool, error: str | None}` to write-enabled results on `open_shared` projects.
The read-only `shared_mode_read_back` note keeps its key, and only its text
changes.
