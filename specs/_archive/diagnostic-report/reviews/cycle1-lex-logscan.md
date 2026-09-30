# Log-Scan Evidence — REPORTABLE_CODES grounding (issue #71)

**Phase A (scan only). No issues filed, no state written.**

## Sources
- `~/.flextoolsmcp/logs/operations.jsonl` (113 lines, all fields present incl. `error_code`, `outcome`, `preflight_gate`)
- `~/.flextoolsmcp/logs/operations.log` (43,616 lines, text)
- No `~/.flextoolsmcp/reports/` directory exists on this machine.

## error_code frequency (n=113 ops)
| outcome | error_code | count |
|---|---|---|
| preflight_reject | unprotected_writes | 42 |
| ok | (none) | 40 |
| preflight_reject | casting_issues_detected | 19 |
| preflight_reject | api_discovery_required | 5 |
| runtime_fail | PolymorphicAttributeError | 3 |
| runtime_fail | runtime_error | 2 |
| preflight_reject | invalid_api_chain | 1 |
| preflight_reject | undiscovered_entity | 1 |

Notably absent from this sample: `partial_module_structure` (0 hits in jsonl; 0 in operations.log) and any generic `SyntaxError` (0 hits). So the "ordinary user syntax error / structure nudge" class is not evidenced here — either it's rare in practice or not yet a distinct logged code.

## Reportable (LibLCM-workaround / inconsistency signal) vs not
- **Worth reporting:** `PolymorphicAttributeError` (3x) — all three trace to `'ILcmServiceLocator' object has no attribute 'GetInstance'` per `operations.log` (lines 41967, 42000-42008, 43288-43296), a genuine API-shape surprise, not user typo.
- **Worth reporting:** `casting_issues_detected` (19x) and `api_discovery_required` (5x) — these are preflight *gates*, not crashes, but their high frequency (24/113 = 21% of all ops) and recurring user_intent text ("verify...", "check whether...", "resolve live GUID...") indicate real API-discovery friction, not fat-fingered code.
- **Not obviously reportable as bugs:** `unprotected_writes` (42x, 37% of all ops) — this is the safety gate working as designed (write attempted without `write_enabled`/confirmation); it's a workflow/UX signal, not a library inconsistency.
- **runtime_error** (2x) and **invalid_api_chain/undiscovered_entity** (1x each) — too few occurrences here to cluster; would need signature text to classify.

## §11.2 "workaround taken" signal — confirmed pattern
Sorting `operations.jsonl` by project+seq shows repeated same-`user_intent` retries where a reject/fail is immediately followed by `ok`:
- 2026-07-12, project "Ejagham Mini": seq4 `casting_issues_detected` reject -> seq5-6 `PolymorphicAttributeError` runtime_fail (x2) -> seq7 `ok`, all same user_intent ("Check whether Ejagham Mini contains complex-form/variant LexEntryRefs...").
- Same project/date: seq27-28 `runtime_error` (x2) -> seq29 `ok`, same user_intent ("Verify census surfaces end-to-end...").
- Four more casting_issues_detected-reject-then-ok pairs same day (seq9->10, 11->12, 13->14, 25->26), each <30s apart, same user_intent text.

This is solid, reproducible evidence that a "fail -> quick retry, same intent -> ok" sequence is a real, frequent pattern (7+ instances in one day) and should ground the §11.2 inference signal.

## If no logs existed
Would need: `operations.jsonl` with `error_code`/`outcome`/`user_intent`/`seq`/`project` fields (or equivalent), plus `operations.log` tracebacks to confirm root exception class per code.
