# Cycle-5 programmer -- primer scoping fix (#96 QC P2-3)

Commit: `ffd4bf4`

## Change

`src/flextoolsmcp/server/handlers/admin.py`, `RUNTIME_PRIMER["shared_mode_read_back"]["note"]`.

OLD:
> "...In-session verification of a shared-mode write is not currently
> possible with run_module: every call opens a brand-new session, and a
> brand-new session only ever sees the last master flush. Instead, check
> the FLEx UI on the master peer..."

NEW:
> "...In-session verification of a shared-mode write is not currently
> possible with run_module: every call opens a brand-new session, and a
> brand-new READ-ONLY session only ever sees the last master flush (a
> write-enabled fresh session that calls SaveChanges() first may see the
> write via Commit-driven reconciliation, but this path is untested).
> Instead, check the FLEx UI on the master peer..."

## Confirmation

- `why` field: byte-unchanged (verified via diff -- only the `note` field's
  hunk touched).
- No-duration property: unchanged and still enforced. `duration_pattern`
  regex in the lock test scans the whole entry blob; the added clause
  contains no digit+unit token. Test asserts `match is None`.
- No test assertion updated. `tests/test_issue96_teardown_visibility.py`
  pins only the `description` sentence ("a fresh read-only session under a
  live FLEx master shows the last master save, not your write") and the
  regex -- neither pins the sentence that changed, so no edit was needed.

## Test run

`python -m pytest -q` -> `1107 passed, 4 skipped, 12 subtests passed in
48.67s`, matching the stated baseline exactly. No flakes observed this run.
