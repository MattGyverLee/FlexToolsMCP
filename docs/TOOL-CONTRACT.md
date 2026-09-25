# Tool Response Contract

**Contract version:** `tool-responses/1.0`

Every response emitted by FlexToolsMCP tools (success and error) carries a
`_contract` key stamped with the version string above. Consumers can read
`_contract` to detect which shape and error-code vocabulary to expect.

---

## Envelope shapes

### Success envelope

All successful tool responses share these guaranteed keys:

| Key | Type | Value |
|---|---|---|
| `_contract` | string | `"tool-responses/1.0"` |
| `status` | string | `"ok"` |
| `op_id` | string or null | operation identifier (may be absent) |

Additional tool-specific data keys are spread at the top level alongside
these envelope keys. Success models use `extra="ignore"` so unknown keys
are forward-compatible.

Success responses may also carry optional top-level `update_notice`,
`workspace_notice`, and `project_adopted_notice` blocks — see
[update_notice](#update_notice-advisory-block),
[workspace_notice](#workspace_notice-advisory-block), and
[project_adopted_notice](#project_adopted_notice-advisory-block) below.

`flextools_run_module` success responses may also include an optional
`effect_check` advisory when a write-enabled run was classified as mutating at
preflight but LCM recorded zero undoable actions (issue #143). The block is
informational only — it does not change `status` or fail the run.

| Key | Type | Meaning |
|---|---|---|
| `signal` | string | `"lcm_undoable_action_count"` (only signal today) |
| `lcm_undoable_action_count` | int | Observed count after execution (zero triggers the advisory) |
| `verdict` | string | `"no_observable_effect"` when mutating preflight and zero actions |
| `note` | string | Human-readable explanation for the caller |

#### Graceful discovery redirect (issue #80)

`flextools_run_module` may return a **`status: "ok"`** response that did **not**
execute the submitted code — a *gentle workflow redirect*, not an error. This
happens on a READ-ONLY run when the referenced APIs weren't discovered yet and
couldn't all be auto-resolved: the server inlines the API docs it could find
and asks the caller to apply them and resubmit, rather than rejecting. Because
it is a success envelope (not an error), it never trips error handling — but a
consumer must not treat it as a completed run. Distinguishing keys:

| Key | Type | Value |
|---|---|---|
| `status` | string | `"ok"` |
| `executed` | bool | `false` (the code was **not** run) |
| `discovery_redirect` | object | `{needs_resubmit: true, reason, undiscovered, prefer_tools}` |
| `_inline_discovery` | object | inlined `get_object_api`-shaped docs to apply |
| `capability_suggestions` | array | optional `search_by_capability`-backed method hits |

Recovery: apply the inlined shapes and resubmit the same `run_module` call.
Proactive discovery (`get_object_api` / `search_by_capability` first) avoids the
hop entirely. In structured telemetry (`operations.jsonl`) this closes with
`outcome: "discovery_redirect"` — counted as neither a green run nor a reject.
Provenance note: passing `source: "existing"` (code from disk / pasted by the
human) skips the discovery gates entirely — but write-safety and casting checks
always run regardless, so `source` can never relax a safety gate.

### Error envelope

Every rejection emits **both** a flat (canonical) shape and a deprecated
nested shape in the **same payload**. Both shapes carry identical content.

**Flat (canonical) top-level keys — read these:**

| Key | Type | Notes |
|---|---|---|
| `_contract` | string | `"tool-responses/1.0"` |
| `status` | string | `"error"` |
| `error_code` | string | one of the 39 codes below |
| `message` | string | human-readable description |
| `hint` | string or null | optional recovery suggestion |
| `op_id` | string or null | operation identifier (may be absent) |

Per-code detail keys (see table below) are also spread at the top level.

**Nested (deprecated) key — retained for backward compat:**

```json
"error": {
  "code": "<same as error_code>",
  "message": "<same as message>",
  "<detail keys>": "..."
}
```

The nested `error` object contains the same fields as the flat shape under
a different key (`code` instead of `error_code`). It exists only for
callers written before the flat shape was introduced.

---

## Error codes and detail fields

Detail models use `extra="forbid"`, so the field lists below are
authoritative. All detail fields are optional unless noted.

| Error code | Detail fields |
|---|---|
| `syntax_error` | `line`, `col`, `offending_token`, `parser_message` |
| `server_state_error` | `server_state`, `component`, `state_description` |
| `internal_error` | `error_type`, `traceback`, `tool` -- unhandled exception in a tool handler (issue #89); traceback is for operator triage, not for end-user display |
| `session_not_initialized` | `tool`, `_diagnostic`, `available_task_examples` (list), `hint` -- dispatch gate before any handler runs (issue #243) |
| `unknown_tool` | `tool` -- tool name not registered in the dispatch router (issue #243) |
| `invalid_input` | `tool`, `received_arguments` -- Pydantic argument validation failed before the handler ran (issue #243) |
| `partial_module_structure` | `missing_elements` (list), `has_main`, `has_docs_dict`, `has_flextools_binding` |
| `unprotected_writes` | `mutating_calls` (list), `write_certification_required` |
| `casting_issues_detected` | `casting_issues` (list), `polymorphic_collections`, `general_guidance` -- issue #40 B-1: on a READ-ONLY run (`write_enabled=false`), this code is emitted (and the run rejected) only if at least one `casting_issues[*].severity` is `"error"` (a known-pattern hit, or a genuine attribute typo). If every issue is `"warning"` (an index-derived lookup with no corroborating known pattern), the run **proceeds instead of rejecting** -- see "Read-only casting severity downgrade" below. WRITE-enabled runs are unaffected: this code still rejects at every severity. |
| `api_discovery_required` | `detected_candidates` (list), `auto_discovered_pending_validation` (list; entities auto-granted on read-only runs but not yet validated via `get_object_api`, issue #244), `session`, `missing_entity`, `suggested_tool_call` |
| `undiscovered_entity` | `undiscovered`, `imported_undiscovered` (list), `session`, `closest_matches` (list) |
| `undefined_variables` | `undefined_vars` (list), `guidance` |
| `missing_imports` | `missing_imports` (list), `api_mode`, `guidance` |
| `wrong_library_imports` | `wrong_imports` (list), `api_mode`, `affected_symbols` (list), `guidance` |
| `invalid_api_mode` | `allowed_modes` (required list), `received`, `hint` |
| `invalid_api_chain` | `issues` (list), `guidance` |
| `nested_unit_of_work` | `constructs` (list), `guidance` |
| `hvo_literal_write_risk` | `findings` (list), `next_steps` (list) -- issue #103; write-enabled runs only, a bare integer literal reached an `*_or_hvo` parameter (see `validators.detect_hvo_literal_args`) |
| `project_locked` | `guidance` (required string), `lock_file_path`, `verdict`, `sharing_enabled`, `holder_pid`, `holder_process`, `remedy` |
| `project_drive_unavailable` | `attempted_path`, `hint` |
| `project_path_mismatch` | `attempted_path`, `discovered_at`, `hint` |
| `project_not_found` | `attempted_path`, `hint`, `recovery` (default `"list_projects"`) |
| `runtime_error` | `stderr`, `traceback`, `exit_code`, `error_type` — plus optional `did_you_mean` (list[str]) and `help` (str) when the runner diagnosed an `AttributeError` with a recoverable suggestion (see [below](#did_you_mean-and-help-on-runtime_error)) |
| `parser_engine_mismatch` | `configured_engine` (required string), `supported_engines` (required list), `hint` (required string) |
| `parser_core_missing` | `signal` (required; `absent` \| `foreign_install` \| `incompatible_surface` \| `load_failed`), `expected_path` (required string), `detected_version` -- **reported and never compared: there is no version floor**, this is a standing guarantee with a regression test behind it (SPEC 16), `missing_members` (required list), `lcmodel_install_path`, `install_hint` (required string), `load_error` |
| `parser_agent_missing` | `agent_guid` (required string), `agent_name` (required; always `"HermitCrab"`), `active_engine` (required string), `probe_source` (required; `bootstrap_absent` \| `lookup_failed`), `hint` (required string) |
| `parser_tool_missing` | `component` (required; `"fieldworks_hermitcrab"` \| `"GenerateHCConfig.exe"`), `expected_path` (required string), `install_hint` (required string). First emitted by `flextools_parse_sandbox` (CP5): FieldWorks' bundled `SIL.Machine.Morphology.HermitCrab.dll` must be present, and `GenerateHCConfig.exe` must be found when a config may be generated. Both are repaired by repairing FieldWorks, so both carry the same `install_hint`. The CP5 re-plan retired the `"hc"` value along with the `hc` console tool. |
| `parse_morph_unresolved` | **Exactly five keys, in this order**: `morph`, `position` (0-based index in the decomposition), `resolved_to` (required; `none` \| `ambiguous` \| `no_msa`), `candidates` (required list of `{headword, sense, msa_hvo, entry_hvo}` -- **`msa_hvo: null` IS the `no_msa` signal**), `hint` (required string). The three `resolved_to` values are kept distinct because they call for three different actions: fix the spelling, pick the homograph, or add an analysis to the entry. **No parse runs** for a request that raises this. |
| `parse_run_not_found` | `run_id` (required string), `available_runs` (required list -- the handles that DO exist, named rather than counted), `hint` (required string). The only refusal `flextools_parse_status` issues. |
| `parse_job_cancelled` | `run_id` (required string), `words_completed` (required int -- the partial results are readable), `state_at_cancel` (required string), `hint` (required string). Raised when something tries to **act** on a run that has already ended. **Not** raised by `flextools_parse_status`: asking about a terminal run is a successful query. |
| `parse_scope_empty` | **In this order**: `scope` (required object -- the scope as given), `matched_texts` (list -- what DID match, so a misspelled genre is told apart from an unused one), `hint` (required string). Raised by `flextools_parse_text` when a scope resolves to no texts. **Not** reused for a never-tokenized text: a text with structure but no unique wordforms gets its own conservative wording, and the response does not assert it has no words. |
| `parse_scope_ambiguous` | **In this order**: `scope` (required object), `requested` (required string -- the genre as typed), `candidates` (list -- EVERY matching genre, never a sample). Matching is case-insensitive over genre name and abbreviation, so the collisions are often ones the caller could not predict. |
| `parse_scope_mismatch` | **In this order**: `baseline_fingerprint` (required object), `current_fingerprint` (required object), `differing_fields` (list -- which fingerprint fields disagree), `hint` (required string). Raised by `flextools_parse_diff` when two runs do not describe the same scope. Overridable: a forced comparison covers the intersection only and says so. |
| `parser_timeout` | **In this order**: `timeout_seconds` (required number), `words_completed` (required int -- the partial results survive), `run_id` (required string), `hint` (required string). **Not** used by the bounded measurement: a measurement stopped at its bound is a successful result (`outcome: "terminated_at_bound"`), not this refusal. First emitted by `flextools_parse_sandbox` (CP5), as a terminal run state. |
| `parser_job_failed` | **In this order**: `state_at_failure` (required string), `failure` (required; `out_of_memory` \| `crashed` \| `cancelled` \| `engine_unavailable` \| `id_map_invalid` -- kept distinct because the remedies differ; the last two are CP5's sandbox worker: its config never loaded into a usable Morpher, or its `lcm-ids.json` id map failed validation), `words_completed` (required int), `words_total` (required int), `run_id` (required string), `log_path` (required string). |
| `parser_filing_in_progress` | **In this order**: `run_id` (required string), `started_at` (required string, ISO-8601 UTC), `words_completed` (required int), `hint` (required string -- names `flextools_parse_status(run_id=...)`). Raised by `flextools_parse_text(apply=true)` when a filing job is already running on the project, before the engine check, the scope, the preview, the backup or any parse. The claim is not a project lock: read-only parses, single-word tries and the run-reading tools are not refused on its account. |
| `grammar_load_unclean` | **In this order**: `signal` (required; `morpher_null` \| `new_load_errors` \| `eligible_forms_dropped`), `new_error_count` (required int), `baseline_error_count` (required int), `baseline_source` (required; `this_run` \| `absent` \| `prior_run:<run_id>`), `log_path` (string or null), then, appended after those five: `new_errors` (list), `dropped_entries` (list of `{entry_guid, headword}`), `baseline_eligible_count` (int or null), `eligible_count` (int or null). Raised by `flextools_parse_text(apply=true)` when the grammar did not load cleanly: the parser could not be built, this load logged errors the baseline did not, or fewer lexical forms are eligible to reach the grammar than in the baseline (which the loader does without logging anything). **There is no override**: the only way past `new_load_errors` or `eligible_forms_dropped` is a read-only `flextools_parse_text` of the same scope, which re-baselines. |
| `parser_config_failed` | **In this order**: `exit_code` (int or null -- null when the generator never returned one: it timed out or could not be started), `stderr_tail` (required string -- the last 20 lines of the combined generator output, ASCII with non-ASCII escaped, capped at 4 KiB), `log_path` (required string -- the run's `sandbox/generate-config.log`), `run_id` (string or null -- null only when generation failed before a run existed, i.e. `flextools_parse_sandbox(action="create_sandbox")`). Raised by `flextools_parse_sandbox` when `GenerateHCConfig.exe` did not produce a config. Generation is judged from its output, not its exit code: a run that exits 0 without the generator's `Writing completed.` line is a failure. |
| `parse_sandbox_refused` | **In this order**: `reason` (required; `name_invalid` \| `sandbox_exists` \| `sandbox_not_found` \| `corpus_exists` \| `corpus_not_found` \| `corpus_invalid` \| `run_not_seedable` \| `insufficient_disk_space` \| `word_file_invalid` -- a closed enum, kept distinct because the remedies differ), `name` (string or null), `path` (string or null), `hint` (required string), `needed_bytes` (int or null), `free_bytes` (int or null -- these two are set only for `insufficient_disk_space`). The sandbox tool's own pre-run refusals; every one fires before a file is created. |

---

## `did_you_mean` and `help` on `runtime_error`

When the execution handler diagnoses an `AttributeError` in the subprocess
output, it may attach two additional optional top-level keys to the
`runtime_error` response — **outside** the `RuntimeErrorDetail` Pydantic model
(which covers only `stderr`, `traceback`, `exit_code`, `error_type`):

| Key | Type | Description |
|---|---|---|
| `did_you_mean` | list[str] | Candidate corrected names, or `[]` when none cleared the suggestion floor. |
| `help` | string | Human-readable recovery hint. When `did_you_mean` is `[]` (no close match found), `help` always carries an explicit pointer to `flextools_get_object_api` and/or `flextools_search_by_capability` — never an empty string or vague guidance (issue #69 guarantee). |

Both keys are absent when the runner did not detect an `AttributeError`, or when
the polymorphic-cast path produced a concrete rewrite (which takes precedence).

**`did_you_mean=[]` guarantee (issue #69).** Before issue #69 was fixed, the
fuzzy-match path could surface a nonsense suggestion (e.g. `PossibilityList →
PLPL`) or emit an empty `help` string when no candidate cleared the internal
ratio floor. After #69, the floor is a shared constant (`_MIN_SUGGESTION_RATIO =
0.6`) and every no-match path explicitly sets `did_you_mean: []` plus a `help`
string that names at least one discovery tool. Callers can therefore distinguish
"we have a specific suggestion" (`len(did_you_mean) >= 1`) from "we don't know,
use discovery" (`did_you_mean == []`) without parsing `help`.

**Raw-handle aliases.** `project.LangProject`, `project.LangProj`, and
`project.LanguageProject` are mapped to `project.lp`; `project.LexDb` and
`project.LexDbOA` are mapped to `project.lexDB`. These aliases always win over
the fuzzy matcher and produce `did_you_mean: ["lp"]` / `["lexDB"]` rather than
an empty list.

---

## Deprecation timeline

The nested `error` object is a **transitional shape** retained during the
`tool-responses/1.0` window.

- **Today (1.0):** flat top-level keys and nested `error` object are
  emitted in parallel. Both carry identical content.
- **At tool-responses/2.0:** the nested `error` block is removed. Only the
  flat shape is emitted.

Stability promise: `error_code` strings and all existing keys are
**append-only** within a major version. Removals and renames bump the
major version and receive a CHANGELOG entry under the heading
**"Tool contract"**.

---

## Upgrade instructions

Callers currently reading `error.code` from the nested shape should migrate
to the top-level `error_code` key before `tool-responses/2.0`.

**Before (reading nested shape):**

```python
data = json.loads(response_text)
if data.get("error"):
    code = data["error"]["code"]
    msg  = data["error"]["message"]
```

**After (reading flat canonical shape):**

```python
data = json.loads(response_text)
if data.get("status") == "error":
    code = data["error_code"]
    msg  = data["message"]
```

Both forms work today. The nested `error` block disappears at
`tool-responses/2.0`.

---

## RunModuleSuccess envelope (run_module tool)

In addition to the base success keys, successful `run_module` responses may
include the following optional fields when read-only auto-discovery occurred
(issue #47). All three are `null` / absent when no auto-discovery took place.

| Key | Type | Description |
|---|---|---|
| `auto_discovered` | list[string] or null | Entity names auto-discovered on this READ-ONLY run. These entities will re-trigger the `undiscovered_entity` gate on the first WRITE run (write-gate isolation via `validated_apis` vs `auto_discovered_apis`). |
| `_inline_discovery` | object or null | Inline API docs for auto-discovered entities. Same compact shape as the `_inline_discovery` key present in `undiscovered_entity` and `api_discovery_required` rejection payloads. Leading underscore is intentional: consistent with `_inline_discovery` and `_assistance` reject-payload keys that clients already parse. |
| `discovery_note` | string or null | Advisory note explaining write-gate re-trigger semantics for the auto-discovered entities. |

These fields are defined in `RunModuleSuccess` (`response_models.py`) with
aliases matching the key strings above. The `_inline_discovery` alias uses the
`KEY_INLINE_DISCOVERY = "_inline_discovery"` constant from `response_keys.py`.

### UoW mode flags (issue #153)

Every executed `run_module` response whose runner reached the OpenProject-time
capability probe also carries:

| Key | Type | Description |
|---|---|---|
| `undoable` | bool | The `OpenProject(undoable=...)` mode the runner actually chose after probing `flexicon.CAPABILITIES` for `"per-operation-uow"`. |
| `timestamps_updated` | bool | Whether DateModified stamping is active for mutations in this session. Same value as `undoable` today (stamping rides the undoable path). |

Under the declared `pyflexicon` floor both are `true`. A `false` value means
an unsupported install silently would have degraded to the legacy
non-undoable session envelope; the flags (and a `report.Warning`) make that
defence-in-depth fallback visible instead of silent. Absent only when the
subprocess never reached the probe (e.g. failed before OpenProject setup).

---

## Read-only casting severity downgrade (`run_module`, issue #40 B-1)

**Contract change:** `casting_issues_detected` no longer fires on every
READ-ONLY run that has a casting issue. The casting gate's per-issue
`severity` field (already present in `casting_issues[*].severity` before
this change) is now consulted at the reject decision:

- **WRITE-enabled runs (`write_enabled=true`):** unchanged. Any casting
  issue, at any severity, still hard-rejects with `casting_issues_detected`.
- **READ-ONLY runs (`write_enabled=false`):**
  - If **any** issue is `severity: "error"` (a known-pattern hit from
    `KNOWN_CASTING_PATTERNS`, or a genuine attribute typo merged in from
    `detect_interface_attribute_typos`), the run still hard-rejects exactly
    as before.
  - If **every** issue is `severity: "warning"` (found only via the
    index-derived `casting_index` lookup, with no corroborating known
    pattern), the run **no longer rejects**. It proceeds, and the issues are
    surfaced instead as non-blocking advisories in the success response's
    `warnings` (list[string]) field, each formatted as
    `"[casting] N polymorphic property access issue(s) were detected but did
    NOT block this READ-ONLY run..."` followed by one `"  line L: property --
    fix"` line per issue (capped at 10).

Rationale: a read-only script that guesses a required cast wrong raises a
`TypeError` at runtime -- costing one iteration, with no risk of data
corruption. The `"warning"` severity tier is exactly the low-confidence path.
Forcing a hard preflight reject for that tier was disproportionate to the
risk and was the single largest source of false preflight rejections
observed in practice.

As of this branch, issue #97 Bug 1 (the `fix` string used to confidently
name a single, sometimes-wrong interface even when the underlying pick was
genuinely ambiguous) is repaired -- `fix` no longer picks `defined_on[0]`
unconditionally. It is instead built from a three-way outcome, matching
whether the same candidate set could be resolved to one definite interface:

- **Resolved** -- exactly one interface can be determined (from
  `available_on`, the casting index, or a receiver-name tie-break): `fix` is
  `"Cast {obj} to {interface}"`, naming the identical interface reported in
  the issue's `cast_interface` field.
- **Ambiguous** -- multiple candidate interfaces remain and none can be
  singled out: `fix` names the candidate set (or, above a display cap,
  states the count without listing them) and explicitly flags that no
  single one is a confident pick. `cast_interface` is `null` in this case --
  `fix` and `cast_interface` never disagree.
- **No usable candidate** -- no I-prefixed interface is available at all:
  `fix` degrades to a generic "concrete type" placeholder rather than
  ever raising an `IndexError` or naming a definite target with no
  evidence.

(Note: issue #97 itself tracks more than this one bug and is **not**
closed -- only Bug 1, the `fix`-string construction described above, is
repaired here.)

This downgrade is **gate-local to the casting gate's warning tier only**.
No other preflight gate is affected: `unprotected_writes`,
`hvo_literal_write_risk`, and `nested_unit_of_work` all continue to
hard-reject exactly as before, on both read-only and write-enabled runs, at
every severity they detect. Detection and reporting for the casting gate
itself are also unaffected -- `casting_issues`, `rewrite`, and
`imports_needed` are computed identically regardless of whether the run
ultimately rejects or proceeds with a warning.

---

## Parser diagnostic-level result fields (`flextools_try_word`, `flextools_parse_status`)

`flextools_try_word`'s `explain` and `restricted` levels, and
`flextools_parse_status`'s `result_summary`, carry additional success
fields reporting outcome, not only trace availability. Additive only --
this did **not** add an error code and did **not** move the count above
(`:69`); `tool-responses/1.0` is unchanged, following the same
additive-optional pattern as `update_notice` / `workspace_notice` /
`diagnostic_report` / `inherited_from` below.

**`flextools_try_word`, per level:**

| Level | Fields | Notes |
|---|---|---|
| `plain` | `parsed` (bool), `analysis_count` (int) | unchanged |
| `explain` | `parsed` (bool), `analysis_count` (int) | derived from the trace document's own `<Analysis>` children -- identical to, not an approximation of, `ParseWord`'s own count |
| `restricted` | `hypothesis_held` (bool), `restricted_analysis_count` (int) | **never** `parsed`/`analysis_count` -- a restricted trace answers "does my restriction still admit an analysis," never "does this word parse at all," and those names are reserved for the unrestricted question -- the keys are absent from the object entirely, never present and set to false |

**The `parse_error` case (`explain` / `restricted` only).** If HermitCrab's
own tracing failed, the trace document carries `<Error>` instead of any
`<Analysis>`; the same applies if the trace document has no `Root` at all
and so cannot be inspected for either. The response then reports
`parse_error` (a message string) and emits **neither** of the pair above --
a zero-`<Analysis>` document does not distinguish "no analysis" from "the
parse itself errored," so neither field would be honest. `parse_error`
**replaces** both pairs rather than joining them: the object carries
`parse_error` alone, never alongside an absent-but-implied `parsed` or
`hypothesis_held`. `trace_available`/`trace_path` are still reported if a
trace file was written before the error. This is a deliberate asymmetry
with `plain`, where the underlying exception propagates and the request
fails outright instead of succeeding with a `parse_error` field.

**`flextools_parse_status`, `result_summary`:**

| Field | Counts |
|---|---|
| `parsed` | entries carrying a `parsed` key (`plain`/`explain`) where it is `true` -- never incremented for `restricted` entries, which do not carry this key |
| `hypotheses_held` | `restricted` entries whose `hypothesis_held` is `true` |

One integer is not allowed to stand for two different questions: a batch of
`restricted` runs previously reported `result_summary.parsed: 0`
unconditionally, indistinguishable from every word failing to parse. A
`parse_error` entry counts toward neither `parsed` nor `hypotheses_held` --
it answers neither question.

---

## Inherited member fields (`get_object_api`, `resolve_property`)

`get_object_api` and `resolve_property` responses may carry additional
optional fields when the target entity has ancestors in its `interfaces`
closure (issue #86, inheritance-resolution CP2): `inherited_from` is emitted
by both tools, while `total_properties_including_inherited` and
`total_methods_including_inherited` are produced by `paginate_entity()` and
so appear on `get_object_api` responses only. Like `update_notice` and
`workspace_notice`, these are **additive optional fields** -- adding them did
**not** bump the contract version, continuing the same additive-optional
pattern already established by `auto_discovered`, `diagnostic_report`,
`update_notice`, and `workspace_notice`.

| Key | Location | Type | Description |
|---|---|---|---|
| `inherited_from` | per property/method item | string or absent | Name of the ancestor interface the member was merged in from. Absent (not `null`) on members the entity declares itself. Own members always shadow an ancestor member of the same name ("child wins" -- no entity ever emits two entries for the same name). |
| `total_properties_including_inherited` | top-level | integer | Combined count of own-declared **and** merged-inherited properties. `total_properties` is unchanged and stays byte-identical to today's own-only count; this is a new, separate key, not a redefinition. |
| `total_methods_including_inherited` | top-level | integer | Combined count of own-declared **and** merged-inherited methods. `total_methods` is unchanged and stays byte-identical to today's own-only count; this is a new, separate key, not a redefinition. |

**Scope (issue #86, CP2).** Only `I*` interface entities receive the merge.
Class-side ancestor merging is **not** covered by these fields -- class
hierarchies have real semantic overrides (a subclass narrowing
`can_write: true` to `false`, for example) that need a policy decision before
they can be merged safely, and that policy is tracked separately from this
change.

**`summary_only` treatment.** `inherited_from` survives `summary_only`
truncation the same way `casting_notes` does -- it is cheap (one short string
per row) and lets a caller distinguish own-vs-inherited members with a single
`.get("inherited_from")` check without requesting the full (non-summary)
response.

Built by `collect_inherited_members()`, merged into the `properties` /
`methods` candidate lists in `paginate_entity()` (`api.py:575`) before the
existing pagination and `summary_only` logic runs, so filtering, totals,
slicing, and the casting-index join stay consistent with the merged view
rather than the own-only one.

---

## `diagnostic_report` advisory block (run_module tool)

Successful `run_module` responses may additionally carry a `diagnostic_report`
advisory block. It is an **additive optional field** on `RunModuleSuccess`
(diagnostic-report feature, CP3; spec `specs/diagnostic-report/SPEC.md` §6.5,
§10). Adding it did **not** bump the contract version — it follows the same
additive-optional pattern as the `auto_discovered` / `_inline_discovery` /
`discovery_note` fields above (resolved question Q5).

| Key | Type | Description |
|---|---|---|
| `diagnostic_report` | object or null | Present only when this success close *resolves* an earlier same-turn reportable failure and the underlying failure signature has not been dedupe-suppressed. `null` / absent otherwise. |

**When it fires.** The block is attached at the run_module **success close**
(`outcome == "ok"`) when the *same turn* earlier contained a reportable failure
(spec §6.1 — a `runtime_fail`, an `invalid_api_chain`, or a recurring
`casting_issues_detected`) that this success appears to have worked around
(spec §6.2). It fires at most **once per distinct failure signature** (spec
§6.3–6.4); a signature the user marked "don't ask again" is suppressed across
restarts.

> **v1 limitation (accepted).** Because the advisory lives only on
> `RunModuleSuccess`, a turn that fails reportably and is then *abandoned*
> (no same-turn `ok` close) is never auto-offered. Recovery is the explicit
> `flextools_prepare_report` tool. Tracked in
> [issue #72](https://github.com/MattGyverLee/FlexToolsMCP/issues/72); see
> SPEC.md §6.5/§10.

**Shape.** When present, the object carries these keys (this is an advisory
surface, not an `extra="forbid"` detail model — treat the list as descriptive,
not exhaustive, and forward-compatible):

| Key | Type | Description |
|---|---|---|
| `signature` | string | Stable, code-independent hash of the underlying inconsistency (spec §6.3). Keyed on `(exception-class, normalized failing symbol)` / offending chain / casting signature — **never** on `code_sha256`. The dedupe/"don't ask again" identity. |
| `title` | string | Suggested issue/email title, e.g. `"[auto-report] PolymorphicAttributeError: <intent>"`. |
| `summary` | string | Short human-readable outcome/error/intent summary. |
| `report_path` | string | Absolute path to the local report file the MCP wrote (`~/.flextoolsmcp/reports/report_<ts>.md`). Writing it transmits nothing. |
| `transports` | object | Prepared transport **strings only** (see below). |
| `likely_contains_lexical_data` | boolean | Code-**shape** sensitivity flag (spec §9, Q4): true when the slice's code shape suggests lexical data (glosses/definitions/headwords) reaches `report.Info`. Drives only the email-vs-GitHub *framing* Claude presents — never the local file's fidelity and never the send decision. Detected from code shape, never from content. |
| `error_code` | string | The anchor failure's `error_code` (may be empty). |

The `transports` object carries three prepared artifacts plus an availability
flag:

| Key | Type | Description |
|---|---|---|
| `gh_available` | boolean | Whether a `gh` executable is on PATH (informs whether Claude should *prefer* the `gh` option). |
| `gh` | object | `{"argv": [...], "display": "<shell string>"}` — the exact `gh issue create ... --body-file <report> --label auto-report` argv. |
| `github_url` | object | `{"url", "body_text", "body_bytes", "url_bytes"}` — prefilled "new issue" URL; body is a short summary capped at ~8 KB. |
| `mailto` | object | `{"uri", "body_text", "body_bytes"}` — `mailto:` URI with a short body; the full-fidelity payload is the local report file the user attaches. |

**Hard guarantee — the MCP never transmits.** Every string in `transports` is
*built, never invoked*. No `run_module` / diagnostic-report code path spawns
`gh`, opens a browser, sends mail, or opens a socket — this is enforced
structurally by a static AST scan and a dynamic monkeypatch test (spec §8.1/§12;
`tests/test_diagnostic_no_transmission.py`). A human must take any send action.

The field is defined in `RunModuleSuccess` (`response_models.py`) with alias
`KEY_DIAGNOSTIC_REPORT = "diagnostic_report"` (`response_keys.py`). The block is
built by `build_advisory_for_success_close()` in
`handlers/diagnostic_report.py`.

---

## `update_notice` advisory block

Success responses may carry an optional top-level `update_notice` block when a
newer `flextools-mcp` release is known to be available on PyPI (issue #79). It
is an **additive optional field** — adding it did **not** bump the contract
version, following the same additive-optional pattern as `diagnostic_report`
and the `auto_discovered` / `_inline_discovery` fields. It is absent when no
update is known, when the user has opted out
(`FLEXTOOLSMCP_NO_UPDATE_CHECK=1`), for source/dev installs, and after it has
already been emitted once in the current server process.

| Key | Type | Description |
|---|---|---|
| `installed` | string | The currently running `flextools-mcp` version. |
| `latest` | string | The newest version seen on PyPI (from a ~24h-cached check). |
| `update_available` | boolean | Always `true` when the block is present. |
| `message` | string | Human-readable summary for the assistant to relay. |
| `upgrade_commands` | object | `{uvx, uv_tool, pip}` — the upgrade command for each install method (users are on mixed methods and the server can't reliably detect which). |

**Behavior guarantees.** The version check is cached in
`~/.flextoolsmcp/update-check.json` and the network is contacted at most once
per ~24h on a background daemon thread — the tool-call path only *reads* the
cache and never blocks on the network. Any failure (offline, timeout, malformed
response, corrupt cache, unresolvable home) fails open to *no notice* and never
raises into the op path. The block is emitted at most once per process.

Built by `get_update_notice()` in `flextoolsmcp/update_check.py`, attached in
`build_response_with_context()`.

---

## `workspace_notice` advisory block

Success responses may carry an optional top-level `workspace_notice` block when
the server's working directory is inside a source checkout of FlexToolsMCP or of
one of the libraries it documents (LibLCM, Flexicon, FlexLibs, FLExTools,
FieldWorks). Like `update_notice` it is an **additive optional field** and did
**not** bump the contract version.

Why it exists: users who find the project on GitHub often clone it and open that
clone as their workspace. The assistant then answers FLEx questions by *reading
the repository* — grepping the bundled index, opening templates, walking
`specs/`, or parsing LCM model XML / `.fwdata` directly — instead of calling the
`flextools_*` tools that serve the same data already parsed. Installing from PyPI
makes this less likely but not impossible: the checkout can still be the working
directory while the code runs from `site-packages` or a `uvx` cache.

| Key | Type | Description |
|---|---|---|
| `detected_repo` | string | Signature key of the matched checkout (e.g. `flextools-mcp`, `liblcm`). |
| `repo_root` | string | Absolute path of the checkout root that matched. |
| `cwd` | string | The resolved working directory that triggered the check. |
| `running_from_this_checkout` | boolean | `true` when the executing package also lives in that checkout (a maintainer's source/editable install) rather than being an unrelated clone. |
| `message` | string | Human-readable summary for the assistant to relay, including the suggested move to an empty folder. |
| `suggested_workspace` | string | A concrete empty-folder path to offer (`~/flex-scripts`). |
| `assistant_directive` | array of strings | Explicit do-not-read instructions plus the tool to call instead. |
| `opt_out_env_var` | string | Always `FLEXTOOLSMCP_NO_WORKSPACE_CHECK`. |

**Behavior guarantees.** Detection is a bounded walk up from cwd (at most
`MAX_ANCESTOR_DEPTH` = 6 ancestors) doing `exists()` probes for two markers per
repo — no file reads, no network. Two markers are required so an ordinary folder
that merely contains a `pyproject.toml` or a `flexicon/` directory does not trip
it. Any failure (unresolvable cwd, permission error) fails open to *no notice*
and never raises into the op path. Setting
`FLEXTOOLSMCP_NO_WORKSPACE_CHECK=1` disables the feature entirely — the escape
hatch for maintainers who legitimately work inside the repo.

**Emission points.** On the response envelope the block is emitted at most once
per process, matching `update_notice`. Two surfaces report it *every* time
instead, because both are moments where the setup can still be changed:

- `flextools_start` — adds a `WORKSPACE: …` line to `warnings` and the full
  block as `workspace_notice`.
- `flextools_health` — adds the same `WORKSPACE: …` line to `warnings`.

Built by `get_workspace_notice()` in `flextoolsmcp/workspace_check.py`.

---

## `project_adopted_notice` advisory block

Success and error responses may carry an optional top-level
`project_adopted_notice` block when a tool call **re-points** the session
project from one already-set name to another (issue #174; deferred from #168
ruling R6). It is an **additive optional field** and did **not** bump the
contract version.

| Key | Type | Description |
|---|---|---|
| `previous_project` | string | Session project name before this call adopted a new one. |
| `project` | string | Canonical project name now stored on the session. |
| `message` | string | Human-readable summary naming both projects and stating that unqualified calls target the new project until changed again. |

**Behavior guarantees.** Emitted only when the session already had a non-empty
`project_name` and this call's resolved `project_name` differs — first adoption
from an empty session is silent. The block is queued on adoption and consumed
into **one** response envelope (success or error) for that call; it is not
repeated on later calls. Write gating is unchanged: this is advisory only.

Built by `adopt_resolved_project()` in `flextoolsmcp/project_adoption.py`,
attached in `response_utils.build_response_with_context()` and
`response_utils.error_response()`.

---

## Source of truth

The models that enforce this contract are in:

- `src/flextoolsmcp/server/response_models.py` -- Pydantic envelope and detail models
- `src/flextoolsmcp/response_utils.py` -- `CONTRACT_VERSION`, `error_response()`, `build_response_with_context()`
