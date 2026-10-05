# Contract delta: `tool-responses/1.0` -> `tool-responses/1.1` (CP2 only)

CP1 ships no contract change; responses stay `tool-responses/1.0`.

CP2 changes `CONTRACT_VERSION` (`response_utils.py:19`) to
`tool-responses/1.1` and adds a section to `docs/TOOL-CONTRACT.md`. No key or
error code is removed or renamed, so this is a minor bump under constitution IV.

## New section for TOOL-CONTRACT.md: "Rejection precedence (1.1)"

A `tools/call` is checked in this order. The first failing check decides the
response:

1. **Tool exists**: otherwise `unknown_tool` (`tool`).
2. **Arguments valid** against the tool's input model: otherwise
   `invalid_input` (`tool`, `received_arguments`).
3. **Session ready**: a cold session auto-initializes for read-only tools and
   `run_module`; any other tool gets `session_not_initialized`.
4. The handler runs. An unhandled exception gives `internal_error`
   (`error_type`, `traceback`, `tool`), whether it was raised in the handler or
   around it.

Rejections at steps 1 and 2 do not change session state.

## Behavior changes from 1.0 (CHANGELOG "Behavior" bullets)

| Situation | 1.0 | 1.1 |
|---|---|---|
| cold session, unknown tool | `session_not_initialized` | `unknown_tool` |
| cold session, non-read-only tool, bad arguments | plain text `Input validation error: ...` | `invalid_input` envelope |
| any session, schema-invalid arguments | plain text `Input validation error: ...`, error flag set | `invalid_input` envelope, error flag set |
| exception outside the handler | plain text `Error: ...`, error flag set | `internal_error` envelope, error flag set |
| `invalid_input`, `unknown_tool`, `internal_error`, `session_not_initialized` envelopes | error flag false | error flag **true** |
| verdict differences found by the parity audit | (each listed) | (each listed) |

## Error-flag note for TOOL-CONTRACT.md

From 1.1, results carrying any of the four codes above set the MCP result's
`isError`. Other error codes keep `isError=false` until PR-E.
