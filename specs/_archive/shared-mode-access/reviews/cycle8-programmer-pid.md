# Cycle 8 -- programmer report: finding (k) PID-liveness fix + remedy wording

## FIX 1 -- finding (k), `_pid_is_alive` (project_access.py:168-225)

Per finding (k) (live-cp4.md ~line 1374) and the secondary-observation
context, a successful `OpenProcess` alone is not proof of life: Windows
keeps a terminated process's kernel object alive while any handle (the
crash reporter, in the live session) remains open, so a freshly-dead PID
still read as "open_shared"/"process still running" -- worst exactly in
the post-crash window where `stale_lock` matters most.

Fix: after `OpenProcess` succeeds, call `GetExitCodeProcess` on the handle
and require `STILL_ACTIVE` (259, new `_STILL_ACTIVE` constant, line 64)
before returning True; `CloseHandle` now runs in a `finally` so it always
fires. If `GetExitCodeProcess` itself fails, fall back to the pre-fix
"trust the handle" behavior rather than guess. Added an inline comment
(project_access.py:200-205) naming the accepted STILL_ACTIVE ambiguity (a
live process cannot be distinguished from one that exited with code 259).
The pre-existing `ERROR_ACCESS_DENIED` branch (line 209-215) and the POSIX
`os.kill(pid, 0)` path (line 217-225) are untouched. No psutil added
(subprocess_helpers.py:29 decision preserved). `ctypes.wintypes` is now
imported under an `if sys.platform == "win32":` guard (line 47-48) so the
module still imports cleanly on POSIX.

## FIX 2 -- `ENABLE_SHARING_REMEDY` (project_access.py:240-252)

Per the "holder never reopened" observation (live-cp4.md ~line 258): the
lock file was byte-identical before/after the sharing flag flip and FLEx's
own PID/start-time did not change, yet the peer open succeeded immediately.
Softened the reopen claim from "FLEx will ask to reopen the project --
let it, because the flag is read once when the cache opens" to:

> "If FLEx offers to reopen the project, accepting is recommended for its
> own cache coherence, but it is not required for this server to attach:
> a live #93 session observed the peer open succeed immediately after only
> the .plsx flag flip, with no reopen and no lock-file change."

Kept the recommendation, dropped the "required to work" claim. "Sharing
tab" and "never writes LexiconSettings.plsx" substrings preserved (pinned
by tests/test_shared_mode_lock_diagnosis.py:61-62 and
tests/test_shared_mode_write_gate.py:84-85,94,258).

## Tests

tests/test_shared_mode_access.py: 30 -> 33 passed (added
`TestPidIsAliveWindowsExitCode`, skipped off-Windows): OpenProcess-succeeds
+ non-259 exit -> dead; OpenProcess-succeeds + 259 -> alive; regression
pinning the `ERROR_ACCESS_DENIED` branch never calls `GetExitCodeProcess`.
Mocks `ctypes.windll` via a `_FakeKernel32`/`_FakeWindll` seam -- no
subprocess, no real PID. No existing assertion weakened or deleted.
tests/test_shared_mode_write_gate.py + tests/test_shared_mode_lock_diagnosis.py:
21 passed, unchanged (neither pinned the removed reopen sentence). Full
suite (`-k "not requires_flex"`): 1125 passed, 2 skipped. Pyright on the
changed file: 0 errors, 0 warnings.

## Deliberately not done

Did not touch execution.py or validators.py (sibling task). Did not probe
the live Sena 3 project (static/unit only, per constraint). Did not widen
`_pid_is_alive`'s POSIX branch or add psutil.
