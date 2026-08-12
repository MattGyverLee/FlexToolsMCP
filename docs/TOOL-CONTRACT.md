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

Success responses may also carry optional top-level `update_notice` and
`workspace_notice` blocks — see
[update_notice](#update_notice-advisory-block) and
[workspace_notice](#workspace_notice-advisory-block) below.

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
| `error_code` | string | one of the 16 codes below |
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
| `partial_module_structure` | `missing_elements` (list), `has_main`, `has_docs_dict`, `has_flextools_binding` |
| `unprotected_writes` | `mutating_calls` (list), `write_certification_required` |
| `casting_issues_detected` | `casting_issues` (list), `polymorphic_collections`, `general_guidance` |
| `api_discovery_required` | `detected_candidates` (list), `session`, `missing_entity`, `suggested_tool_call` |
| `undiscovered_entity` | `undiscovered`, `imported_undiscovered` (list), `session`, `closest_matches` (list) |
| `undefined_variables` | `undefined_vars` (list), `guidance` |
| `missing_imports` | `missing_imports` (list), `api_mode`, `guidance` |
| `wrong_library_imports` | `wrong_imports` (list), `api_mode`, `affected_symbols` (list), `guidance` |
| `invalid_api_chain` | `issues` (list), `guidance` |
| `project_locked` | `guidance` (required string), `lock_file_path` |
| `project_drive_unavailable` | `attempted_path`, `hint` |
| `project_path_mismatch` | `attempted_path`, `discovered_at`, `hint` |
| `project_not_found` | `attempted_path`, `hint`, `recovery` (default `"list_projects"`) |
| `runtime_error` | `stderr`, `traceback`, `exit_code`, `error_type` |

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

## Source of truth

The models that enforce this contract are in:

- `src/flextoolsmcp/server/response_models.py` -- Pydantic envelope and detail models
- `src/flextoolsmcp/response_utils.py` -- `CONTRACT_VERSION`, `error_response()`, `build_response_with_context()`
