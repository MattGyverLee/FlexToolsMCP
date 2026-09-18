# Cycle 2 -- Archivist filing of cycle-1 sweep findings

Filed 7 issues for findings scoped out of #144, per user approval. Commented on #144 cross-referencing all seven.

| # | Title | Labels |
|---|---|---|
| #146 | Capability check version-sniffs hasattr(flexicon,'version'); passes on builds lacking every capability assumed | bug, P1 |
| #147 | RefreshFromDisk() never called; foreign FLEx save wedges auto-save | bug, P1 |
| #148 | HeadlessLcmUI ImportError probe rests on premise flexicon #285 reversed | bug, P2 |
| #149 | api_versions misreports index-file versions as active under fallback_latest | bug, P2 |
| #150 | _INHERITED_MEMBERS_CACHE keyed on id(entities_index), no invalidation | bug, P2 |
| #151 | get_workspace_notice(once=True) suppresses re-detection after cwd change | bug |
| #152 | Stale-comment / internal-debt cluster (validators, kernel, skeleton_storage, server.py) | dx |

## Label deviations
Repo has no `P3` or `chore` label (`gh label list` checked first). Per instructions to match existing convention rather than create new labels: #151 filed with `bug` only (no P3); #152 filed with `dx` only (no chore, no P3). Noted inline in both issue bodies.

## Declined to file
None declined -- all 11 findings from the sweep table map into the 7 requested issues (the 3-item nested-UoW cluster and the RefreshFromDisk gap were explicitly excluded per the in-scope list for #144, and were not re-filed here).

## Source files touched
None. Filing only, per instructions -- no edits to execution.py, validators.py, response_models.py, make_golden.py, tool_definitions.py, session.py, or any other source file.
