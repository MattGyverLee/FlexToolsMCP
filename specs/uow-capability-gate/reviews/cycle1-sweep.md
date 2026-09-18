# Cycle 1 Sweep -- sibling instances of the #144 / #145 bug shapes

Agent: Explore (read-only; transcribed to disk by the main session).

Shapes hunted:
- **A** stale workaround for an upstream defect that has since been fixed
- **B** hardcoded feature flag / version-sniff where `flexicon.CAPABILITIES` is
  the intended probe
- **C** value computed once at startup, replayed as if live in a diagnostic

Severity: **P1** user could get wrong DATA -- **P2** wrong DIAGNOSTICS --
**P3** stale prose / internal debt.

## Key upstream facts (flexicon 4.8.0)

- `undoable=True` is the **default since 4.4.0** and works (per-operation UoW +
  rollback). `__init__.py:15-72`, `code/FLExProject.py:255-330`.
- `ui=None` **defaults to `HeadlessLcmUI()` since flexicon issue #285**;
  `HeadlessLcmUI` is re-exported at top level.
- `RefreshFromDisk()` exists at `FLExProject.py:1182`.
- `CAPABILITIES` has 4 tokens and **zero references anywhere in this repo.**

## Findings

| file:line | shape | what | still valid vs 4.8.0? | sev |
|---|---|---|---|---|
| `src/flextoolsmcp/server/handlers/execution.py:2887-2900` | B | Nested-UoW gate comment + gate assume "CP1 hardcoded undoable=False => one session-long non-undoable UoW; OpenProject only opens a UoW when writeEnabled=True" | **Stale premise.** Under the 4.8.0 default atomicity is per-operation; gate should key off `per-operation-uow` + the actual `undoable=` passed | P1 |
| `src/flextoolsmcp/server/validators.py:448-475` | B | Same assumption as prose + constants for `detect_nested_unit_of_work` (`_NESTED_UOW_HELPER_NAMES`, write-only condition at :468-472) | Same as above; the rejection text sent to users is wrong-by-construction once `undoable=True` | P1 |
| `src/flextoolsmcp/server/handlers/execution.py:226-227` | B | Capability check is `hasattr(flexicon,'version')` or `'__version__'` as a proxy for "flexicon usable" | Version-sniffing where `CAPABILITIES` is the intended probe; **passes on a 4.3.0-floor build that lacks every capability the runner assumes** | P1 |
| `src/flextoolsmcp/server/handlers/execution.py:3878-3899` | A+B | Imports `flexicon.code.headless_ui.HeadlessLcmUI` behind try/ImportError; on failure warns "falls back to WinForms FwLcmUI... can hang (issue #96 / flexicon #238). Upgrade flexicon." | **Stale.** 4.8.0 defaults `ui=None` -> `HeadlessLcmUI`, so the fallback branch's premise (None => FwLcmUI) is false. Also reaches into `code.*` instead of the top-level export, and ImportError-probes instead of `"ui-injection" in CAPABILITIES` | P2 |
| `src/flextoolsmcp/server/session.py:74-81` | A | `nested_unit_of_work` assistance hint: "the runner already has a UnitOfWork open for the whole run" | Stale under the 4.8.0 default | P2 |
| `src/flextoolsmcp/server/tool_definitions.py:112-113` | A | `flextools_start` description: "There is no undo: writes are direct and immediate" | **False** since 4.4.0 -- `per-operation-uow` puts each op in FLEx's Ctrl+Z menu. Model-facing prose, so it shapes behaviour | P2 |
| `src/flextoolsmcp/server/handlers/admin.py:491-510` -> `session.py:283-295` | C | `api_versions` built from `api_index.*_version` (the **index file** versions loaded at startup), stored on the session, replayed as "active API versions" | Misreports installed flexicon when index is `fallback_latest`; no invalidation | P2 |
| `src/flextoolsmcp/server/handlers/api.py:499-509` | C | `_INHERITED_MEMBERS_CACHE` keyed on `id(entities_index)`, no TTL/invalidation, justified by "loaded once per process... never mutated" | Holds today; breaks silently if an overlay/refresh ever reloads the index (id reuse after GC is the real hazard) | P2 |
| `src/flextoolsmcp/response_utils.py:170` + `workspace_check.py:284-289` | C | `get_workspace_notice(once=True)` with process-global `_notice_emitted`, no reset | By design for the envelope; but the flag also suppresses re-detection after a cwd change. `admin.py:563` / `diagnostic_health.py:260` correctly pass `once=False` | P3 |
| `src/flextoolsmcp/server/validators.py:1824-1828` | A | `STABLE_ONE_SHOT_METHODS` allowlist, "Revisit if flexlibs stable ever gains reliable return-type index data" | Unverified; flexlibs-stable scope, not flexicon | P3 |
| `src/flextoolsmcp/server/kernel.py:768` | A | `from server import APIIndex  # Temporary import, will be resolved during modularization` | Internal debt only | P3 |
| `src/flextoolsmcp/server/skeleton_storage.py:207` | A | "for now the single-process MCP makes this acceptable" (unlocked write) | Holds while single-process | P3 |
| `src/flextoolsmcp/server.py:833` | A | "See docs/TODO.md" -- handler dicts not validated against `*Success` models | Contract drift risk, no user-visible data effect | P3 |

## Gap (an omission, not a stale workaround)

`RefreshFromDisk()` / the `refresh-from-disk` capability is **never called
anywhere in `src\`**. One foreign FLEx save wedges auto-save for the remainder
of a run. P1-adjacent.

## Conclusion

13 sibling sites. The dominant cluster is the nested-UoW gate
(`execution.py:2887`, `validators.py:448-475`, `session.py:74`) plus the
`HeadlessLcmUI` ImportError probe (`execution.py:3878`), all resting on
pre-4.4.0 flexicon semantics that 4.8.0 has reversed. Every one of them infers
a flexicon capability by version, import-probe, or hardcoded constant while
`flexicon.CAPABILITIES` goes unread.
