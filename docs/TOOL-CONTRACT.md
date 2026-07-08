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

## Source of truth

The models that enforce this contract are in:

- `src/flextoolsmcp/server/response_models.py` -- Pydantic envelope and detail models
- `src/flextoolsmcp/response_utils.py` -- `CONTRACT_VERSION`, `error_response()`, `build_response_with_context()`
