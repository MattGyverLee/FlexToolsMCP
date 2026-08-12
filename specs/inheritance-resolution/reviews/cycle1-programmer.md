# Cycle 1 - Programmer report - Issue #85

## Fix

`src/flextoolsmcp/server/handlers/discovery.py::handle_get_navigation_path`:
changed signature `args: GetNavigationPathInput` -> `args: dict`, and body
`args.from_object` / `args.to_object` -> `args.get("from_object")` /
`args.get("to_object")`, matching every sibling handler. Removed the now-unused
`from ..models import GetNavigationPathInput` import (still imported/used
correctly in `dispatch.py` for input *validation*, unaffected).

## Tests

New file `tests/test_issue85_navigation_path.py` (7 tests, all passing):
1. Dispatch-path test via the real `server.call_tool()` (validate ->
   `model_dump()` -> `handler(dict)`) -- the exact repro path that had zero
   coverage and shipped the bug.
2. Direct-call test locking `handle_get_navigation_path` against a plain dict.
3-4. Nav-path smoke tests against the shipped
   `navigation_graph_liblcm-v11.0.0.json`.

**Important deviation from the cycle-1 plan**: `IFsFeatStruc -> IFsFeatDefn`
does NOT resolve post-fix. I verified a genuine 2-hop path exists in the raw
graph data (confirmed by an independent BFS replay), but running it through
the now-reachable `find_path_bfs()` exposed a **second, unrelated,
pre-existing bug**: commit `2053e12` ("Wave 3 Efficiency: Parent tracking")
never records `parent[end]` before reconstructing the path, so
`while node in parent` at the target fails immediately and EVERY match
(direct-edge or multi-hop) reconstructs to `[]`, indistinguishable from "not
found". This was invisible until now because #85's crash meant the BFS
branch never ran in the live tool, and no unit test called `find_path_bfs()`
directly. Per the narrow scope for #85, I did NOT fix this -- I pinned the
current (buggy) behavior in the test with a detailed comment and added an
isolated `TestFindPathBfsReconstructionBug` unit test (2 cases, trivial
graphs) reproducing it independent of the shipped index. The
`ILexSense -> IFsSymFeatVal` case still correctly returns `found:false` for
the originally-intended reason (#86/CP2, no downcast edge in the graph).

## Test suite

Full suite: **953 passed, 2 skipped, 0 failed** (includes the 7 new tests).
No regressions from the discovery.py fix.

## Draft issue 1: server.py:986 has no try/except around handler dispatch

**Title:** Handler exceptions bypass the structured error envelope (TOOL-CONTRACT.md)

**Body:** `await handler(dumped)` at server.py:986 is unguarded. Any exception
raised inside a handler (e.g. the #85 `AttributeError`) propagates as a bare
string via whatever wraps `call_tool`, instead of the structured envelope
documented in docs/TOOL-CONTRACT.md. This is why #85 surfaced as a raw
`'dict' object has no attribute 'from_object'` string rather than a
recognizable error code. Fix: wrap the dispatch call in try/except, emit a
TOOL-CONTRACT-compliant error object (with a generic `internal_error` code)
on unhandled exceptions, and log the traceback via `operations_logger`.

## Draft issue 2: find_path_bfs() reconstruction bug (all BFS-fallback queries return found:false)

**Title:** `find_path_bfs()` never finds a path since the Wave 3 parent-tracking rewrite

**Body:** In `discovery.py`, `find_path_bfs()` matches `target == end` and
reconstructs via `parent[]`, but never inserts `parent[end]` first. The
reconstruction loop (`while node in parent`) therefore always exits
immediately, returning `[]` for every match -- direct-edge or multi-hop.
Regression from commit `2053e12`. Effectively the BFS fallback path of
`flextools_get_navigation_path` has been silently non-functional since that
commit; only precomputed `common_paths` entries have ever worked. Fix:
record `parent[end] = (current, via, rel_type)` before reconstructing.
Repro: `tests/test_issue85_navigation_path.py::TestFindPathBfsReconstructionBug`.

## Incident note (repo hygiene)

Mid-session, a stray `git stash pop` (run while investigating baseline
diffs) grabbed an unrelated stash belonging to a concurrent agent session
("Auto stash before merge of main and origin/main"), producing conflict
markers in `.claude/settings.json` and `src/flextoolsmcp/flexicon_analyzer.py`.
No content was lost: both original stash entries remain in `git stash list`
untouched, and I restored both files to their exact pre-pop ("ours", stage 2)
content via `git show :2:<path>` + manual write/edit, then cleared the index
with `git add` + `git reset` (no `checkout`/`reset --hard`). Verified
`git ls-files -u` is empty and `git stash list` still shows both original
entries. Flagging this because this repo has multiple concurrent agents
writing to the same working tree -- future cycles should avoid `git stash`
here entirely in favor of targeted diffs/backups.
