# Quickstart: validating the exclusive-access gate

Run everything from the worktree `C:\Github\FlexToolsMCP-exclusive-access`.
Live steps use **Sena 3** only. Never use Claude-Swahili.

## Offline (no FieldWorks needed)

```powershell
.venv\Scripts\python -m pytest -q -m "not requires_flex" tests/test_exclusive_access_detect.py tests/test_exclusive_access_gate.py tests/test_response_contract.py tests/test_docs_no_undo_claims.py | Select-Object -Last 20
python tests/make_golden.py --regen
python scripts/validate_integrity.py server
```

Expected results:
- All tests pass.
- The golden diff adds only `requires_exclusive_access.json`.
- The integrity check exits 0.

## Live (FieldWorks 9.3.x, Sena 3 with sharing on)

Record each step's pre and post state in `evidence/live-gate.md`.

| # | Setup | Action | Expected |
|---|---|---|---|
| V1 | FLEx open on Sena 3 | `run_module`, write-enabled and confirmed, with a script that calls `project.WritingSystems.Ensure(<an existing analysis tag>)` inside `if modifyAllowed:` | Refused with `requires_exclusive_access` before any subprocess starts. FLEx keeps running. No `.ldml` file changes (compare mtimes) |
| V2 | Same | Same script with `validate_only=true` | `project_lock.exclusive_access.blocking == true` |
| V3 | Close FLEx | Re-submit the V1 call unchanged | Passes the gate. `Ensure` on an existing tag is a no-op (pre/post WS list identical). Reopen FLEx: no crash |
| V4 | FLEx open | Ordinary write: set a gloss on a `zzExclTest` entry the run created, then delete that entry | Not refused by the gate. Shared-mode advisory present |
| V5 | FLEx open | Call A writes a gloss on a `zzExclTest` entry. Call B, write-enabled, reads it back with sync-at-open on, then with it off | Record whether B sees A's write in each case. This decides whether sync-at-open ships (research R5) |
| V6 | FLEx open, after V4 | In FLEx, navigate away and back, then check Edit > Undo | The gloss appears after navigating away and back (F5 alone does not show it). Undo does not offer the MCP's change |
| V7 | FLEx open (`needs-human`) | Class B harness (research R9): a peer adds the `zzExclTest` custom-field definition, with no data, and commits. Close and reopen FLEx | Record whether the definition survived. Expected: it is gone. If it survived, delete it through the FLEx Custom Fields dialog |

Clean up: delete every `zzExclTest` object in the same session, and confirm
with a read-only listing.
