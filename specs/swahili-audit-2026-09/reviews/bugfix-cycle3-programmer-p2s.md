# Programmer cycle 3 -- two P2 carryovers (#93 CP4 primer defect + #96 teardown branch)

## Deliverable 1 -- impossible remedy in `shared_mode_read_back.note`

**OLD** (`admin.py`, pre-fix):
> "Do not treat a stale read-back as a dropped write: the data is safely in
> the shared commit log the whole time. Do not paper over this by polling a
> fresh session and waiting N seconds -- there is no N that is safe. If a
> caller must verify its own write, it needs a LIVE peer session (one that
> stays open and calls Commit again), not a new one."

**NEW**:
> "Do not treat a stale read-back as a dropped write: the data is safely in
> the shared commit log the whole time. Do not paper over this by polling a
> fresh session and waiting N seconds -- there is no N that is safe.
> In-session verification of a shared-mode write is not currently possible
> with run_module: every call opens a brand-new session, and a brand-new
> session only ever sees the last master flush. Instead, check the FLEx UI
> on the master peer -- it sees the write through its own live cache
> (Commit / ReconcileForeignChanges), not through a fresh read. If the
> write must be confirmed programmatically, that requires a session that
> stays open and calls Commit again; run_module cannot provide one."

Chose **option (b)**: state plainly that in-session verification is not
possible with `run_module`, and point to the FLEx UI instead. The
root-cause doc (`bugfix-cycle1-explore-96.md` sec. 5) explicitly names this
as the truthful verification path already in use elsewhere in the spec
("the change appears in the FLEx UI ... the master's own cache -- which
does see it"), while sec. 6 remedy 1 (write-enabled `SaveChanges()`
reconciliation) needs a new flexicon entry point that doesn't exist yet --
not something `run_module` can do today, so (a) would still be a false
promise. `why` was left untouched (already correct, test-locked).

## Lock test fix

Replaced the blacklist with a structural regex requiring no digit+unit
duration anywhere in the entry:
```python
duration_pattern = re.compile(
    r"\b\d+\s*(?:s|sec|secs|second|seconds|m|min|mins|minute|minutes|"
    r"hr|hrs|hour|hours)\b",
    re.IGNORECASE,
)
match = duration_pattern.search(blob)
assert match is None, ...
```
Verified it doesn't false-positive against the current entry (empty match
list). Added `import re`.

## Deliverable 2 -- both-failures branch

Added `test_body_error_preserved_when_teardown_also_fails` to
`TestRunnerScriptRuntime`: script body `raise ValueError('body failure
before teardown')`, combined with `close_raises=True`. Asserts `success is
False`, the original body text `"body failure before teardown"` is still
present in `payload["error"]` (preserved, not clobbered), the teardown text
`"simulated ConflictingSave during teardown"` is additionally present in
the same field, and `payload["teardown_error"]["type"] == "RuntimeError"`.
This confirms the additive (append, not overwrite) contract at
`execution.py:3866-3888`.

## Test run

`python -m pytest -q` -> **1053 passed, 4 skipped in 40.76s** (baseline
1052/4 + 1 new test). No flake from
`test_new_exact_file_visible_after_write` this run.

Commit: (see below)
