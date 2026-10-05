# Data model: mcp2-only

There is no persistent data. The "entities" are the request-path shapes the
adapter and the tests reason about.

## Wire golden (from PR-0, read-only here)

| Field | Meaning |
|---|---|
| `request` | `tools/list`, or `tools/call` with `name` and `arguments` |
| `case` | `success`, `invalid_input`, `unknown_tool`, `cold_non_readonly`, `cold_readonly_autoinit`, `configure_raises` |
| `text` | normalized content text (timestamps, paths, update and workspace notices masked) |
| `is_error` | the result's error flag |
| `contract` | read from `CONTRACT_VERSION`, never a literal |

CP1 must match every record in both eras. CP2 regenerates only the
`invalid_input`, `unknown_tool` and `configure_raises` records, plus the
cold-session records whose code changes (see the precedence table).

## Protocol era

| Era | How negotiated in tests | Result shape |
|---|---|---|
| `2026-07-28` | `Client(..., mode='auto')` | full result (`resultType` etc. handled by the SDK) |
| `2025-11-25` | `Client(..., mode='legacy')` | same tool results |
| `2024-11-05`, `2025-03-26` | older clients | text only; not newly tested here |

## Call outcome (adapter output)

| Kind | CP1 | CP2 |
|---|---|---|
| handler content | `CallToolResult(content=[...])`, `is_error` False | same, but `is_error` True when the classifier finds a hard code |
| handler mid-call input request | passed through unchanged | unchanged |
| schema violation | `is_error` True, text `Input validation error: <msg>` | removed; becomes `invalid_input` envelope from the dispatcher |
| escaped exception | `is_error` True, text `Error: <exc>` | `is_error` True, `internal_error` envelope (`error_type`, `traceback`, `tool`) |

## Rejection precedence

| Situation | CP1 (unchanged from today) | CP2 |
|---|---|---|
| cold session, unknown tool | `session_not_initialized` | `unknown_tool` |
| cold session, non-read-only tool, bad args | `Input validation error` text (schema pre-check runs first) | `invalid_input` |
| cold session, non-read-only tool, good args | `session_not_initialized` | `session_not_initialized` |
| cold session, read-only tool (or `run_module`) | auto-init, then the handler | auto-init, then the handler |
| warm session, bad args | `Input validation error` text | `invalid_input` |
| warm session, unknown tool | `unknown_tool` | `unknown_tool` |

State rule (CP2, FR-023): a call that ends in `unknown_tool` or
`invalid_input` never touches session state. The session stays cold.

## Error-flag classifier (CP2)

Input: the handler's response payload. Output: `is_error` bool.

1. Read the code from the top-level `error_code`, then the nested
   `error.code`, then a top-level string `error`.
2. `is_error = code in {"invalid_input", "unknown_tool", "internal_error",
   "session_not_initialized"}`.
3. A payload with no recognizable code gives `False`, which is unchanged.

PR-E later extends the set; the function is shared code so PR-E reuses it.
