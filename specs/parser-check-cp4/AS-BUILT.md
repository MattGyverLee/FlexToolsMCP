# parser-check CP4: as built

**Status:** Retired 2026-09-29. Merged to main as PR #216 (`b8c5df6`, 2026-09-24; feature commit `a657cfd`, evidence refresh `9099eef`). Tasks: 71/71 complete. Post-merge fixes: `98944ef` (#240, filing worker held its writable open past idle-release, fixes #239), `aca9e79` (#252, compact preview on large scopes).
**Full docs:** [specs/_archive/parser-check-cp4/](../_archive/parser-check-cp4/) (spec, plan, tasks, research, data-model, contracts, reviews, evidence). Not read by default.
**Pinned (archive):** `tests/test_parser_error_models.py` reads `contracts/tools.md`, and the live harnesses (`test_parse_live_cp4.py`, `live_support/cp4_scenarios.py`, `live_support/l0_coexistence.py`) write `evidence/`, all under `specs/_archive/parser-check-cp4/`.
**Scope:** The first checkpoint that writes. `flextools_parse_text(apply=true)` files HermitCrab results into the project through FieldWorks' own `ParseFiler` (what FLEx's *Parse Words in Text* does). Parent requirement text: [../_archive/parser-check/SPEC.md](../_archive/parser-check/SPEC.md) sections 5.2, 12.2-12.7, 14-16.

## What shipped
- `apply`, `confirmed`, `plan_id` on `flextools_parse_text`; annotations unchanged (`destructiveHint=True`). New tool `flextools_parse_cancel` (idempotent, stops at a word boundary, works on read-only runs too).
- `server/write_ladder.py`: the `run_module` ladder extracted, not copied (`probe_write_access`, `backup_intent`, `take_backup`); `handlers/execution.py` and `handlers/parse.py` both call it.
- `server/filing/` package (claims, classify, eligibility, filer, gate, observer, paths, plan, preflight_reads, projection, wording, worker_filing) run by a separate `FILING_ROLE = "filing"` worker (`filing/client.py:31`), the only place a project is opened for writing. The CP3 read worker and its no-write tests are untouched.
- Two additive refusal codes, `parser_filing_in_progress` and `grammar_load_unclean` (`response_models.py:777,799`; `docs/TOOL-CONTRACT.md:151-152`; goldens in `tests/golden/responses/`).

## Public contracts
- Call sequence: `apply=true` -> `confirmation_required {plan, plan_id}`; `apply=true, confirmed=true, plan_id=<id>` -> plan re-computed; same id -> backup + run `{run_id}`, different -> new `confirmation_required` (FR-006).
- `plan_id` = sha256 over the canonical JSON of the bound plan fields, 64 lowercase hex (`filing/plan.py:80`). Proves issuance, not reading.
- Confirmation is unconditional for filing: `require_write_confirmation=false` is ignored here (`handlers/parse.py:1297`). No bypass argument or config key (`tests/test_filing_bypass_surface.py`, SC-008).
- `write_enabled=false` session refuses with `server_state_error` (`server_state: "write_disabled"`); filing never degrades to read-only.
- `grammar_load_unclean.signal`: `morpher_null | new_load_errors | eligible_forms_dropped`. No override: the only escape is a read-only `flextools_parse_text` of the same scope, which re-baselines.
- Artifacts live under `~/.flextoolsmcp/backups` and the record dir, never inside a project folder (`filing/paths.py:103 assert_outside_project`, FR-042).

## Key decisions
- CP3's deletion projection is not an upper bound (R-01: FLEx deletes human-made, never-evaluated, unused analyses). CP4 reuses CP3's join and probe, not its predicate.
- The bound is enforced per word at filing time (R-02): a new `ParseFiler` per word, on a real paused `IdleQueue` pumped by hand (R-03); the filer's would-delete set is checked against the confirmed projection first.
- The gate runs on every reload during the job, because the facade silently reloads a stale grammar before each parse (R-05).
- Load-error diffs miss silent shrinks (D-1): `filing/eligibility.py` ports `HCLoader.IsValidLexEntryForm`/`IsValidRuleForm` and compares eligible counts; a live parity test guards drift (Principle VI exception).
- Backup is best-effort (constitution I), stated in the plan before confirmation; a run without one carries a no-recovery warning. S/R projects (`.hg` present) are told the recovery is discard-and-re-download.
- Filing overwrites human disapprovals by design (D-2, `ParseFiler.SetUnsuccessfulParseEvals`): projected (FR-040) and listed (FR-041).
- Errored parses are filed exactly as FLEx does; try-a-word modes never file.
- M-1 (resolved 2026-09-24): L-0 failed, so FR-027/SC-007 were amended. With sharing off, reads on the project are refused with `parser_filing_in_progress` during filing (`filing/claims.py:74`); with sharing on they are not. Shared-mode filing is allowed with an advisory to stop FLEx's own parser.

## Gotchas and limits
- flexicon's `HeadlessLcmUI.SynchronizeInvoke` is None; `ParseFiler` NREs in `SendPropChangedNotifications`. The filing worker supplies `SingleThreadedSynchronizeInvoke` (`filing/worker_filing.py:105-147`).
- The filing worker must not idle-release (#223 regression, #239): `_release_if_idle` is a no-op (`worker_filing.py:693`); `final_commit` closes the project.
- FLEx's lowercase side-filing is not reproduced (R-06); the plan and record disclose it.
- Large plans are shown compact (>200 GUIDs / >50 unreadable words); the full plan goes to `<record dir>/plans/<plan_id>.json`, and `plan_id` still hashes the full plan (#252).
- Live verification ran only on disposable `CP4-Scratch-` copies of IndonesianHC-Complete and Malay, with pyflexicon 4.9.0 (`evidence/SUMMARY.json`). Nothing runs in CI. Filing does not trigger mid-run grammar reloads (Q3); checksum skip works across processes (Q5).
- Out of scope: gloss-only merge (parent 17.6), unattended filing, undo, coordinating with FLEx's background parser.

## Divergences from the spec
- `docs/TOOL-CONTRACT.md:151` still says read-only parses and single-word tries "are not refused on its account". That is pre-amendment text: the code refuses them on non-shared projects (M-1 / amended FR-027).
- pyflexicon: live evidence at 4.9.0; repo now floors `>=4.11.0,<5` (requirements.txt:21). Not re-verified live.
- Not verified here: FR-001..FR-043 individually, and the live evidence rerun on the current tree. Only the surface above was read.

## Follow-ups and open issues
- M-2 open: issue #165 (closed) still says "Mandatory pre-write backup" (line 29 and an unchecked DoD box). Outward-facing edit awaits authorisation. Parent SPEC 12.4 is already corrected.
