# Contract: `requires_exclusive_access`

Additive under the current tool-response contract major. The error-code count
goes from 46 to 47.

## When it fires

`flextools_run_module` with `write_enabled=true`, when the script contains at
least one exclusive-only operation (see `data-model.md`) and the access probe
reports `open_shared` or `unknown`. It fires before the confirmation gate,
before the pre-write backup, and before any subprocess starts.

## Response (error envelope, per docs/TOOL-CONTRACT.md)

```json
{
  "_contract": "tool-responses/1.x",
  "status": "error",
  "error_code": "requires_exclusive_access",
  "message": "This script changes writing systems or custom fields, which is not safe while FieldWorks has 'Sena 3' open. Close FieldWorks, re-submit this same call, then reopen FieldWorks.",
  "detail": {
    "error_code": "requires_exclusive_access",
    "guidance": "1. Close FieldWorks (all windows for this project). 2. Re-submit this exact run_module call unchanged. 3. Reopen FieldWorks after it finishes.",
    "verdict": "open_shared",
    "holder_pid": 68436,
    "holder_process": "FieldWorks",
    "operations": [
      {"key": "ws.create", "category": "writing_system", "failure_class": "crashes_holder",
       "call": "WritingSystemOperations.Create", "line": 12, "source": "wrapper"}
    ],
    "remedy": "Close FieldWorks, re-submit unchanged, reopen FieldWorks."
  }
}
```

The envelope keys (`_contract`, `status`, `op_id`, the nested `error` object
during its deprecation window) come from `error_response()` as they do for
every code. The golden fixture pins the exact shape.

## Conditional `WritingSystems.Ensure()` (FR-002b)

- Operations rows carry `conditional` (true for `Ensure`). The detail adds
  `stage`: `preflight` for the up-front refusal, `runtime` when flexicon's
  peer schema guard refused during the run.
- A literal `Ensure` that would add a writing system is refused up front.
  The message ends with the reason, e.g. "Ensure('qaa-x-new') on line 2 would
  add a vernacular writing system: 'qaa-x-new' is not active as vernacular in
  the project."
- The decision comes from the project's active writing-system lists, read
  from its `.fwdata` without opening the project. When the file cannot be
  read, the call is left to the runtime guard.
- An allowed run carries `exclusive_access` on its success result (see
  data-model.md).
- A runtime refusal comes back as the run's error with
  `error_code: requires_exclusive_access`, `stage: runtime`, `guidance` and
  `remedy`. Writes made earlier in the script are already saved.

## Assistance hint (`_ASSISTANCE_HINTS_BY_ERROR_CODE`)

> Ask the user to close FieldWorks, wait until they confirm, then re-submit the
> identical call. Do not rewrite the script to avoid the gate, and do not ask
> them to close FieldWorks for ordinary edits. Tell them they can reopen
> FieldWorks once the run finishes.

## validate_only

`project_lock.exclusive_access` = `{required, operations, blocking}` (see
`data-model.md`). This is additive, and the existing `project_lock` keys are
unchanged.

## Changed text, same keys

- The `open_shared` advisory no longer warns, after the fact, about
  custom-field and writing-system changes. It points to this gate instead.
- `_diagnose_project_open_error` on `open_shared` no longer says "Close
  FieldWorks and retry".
- The `shared_mode_read_back` note states the read-only limit instead of
  "untested".
