# Recipe verification evidence

Per-recipe evidence for the shipped batch lives in `evidence/<recipe-id>.md`
(research R14, plan "Live-LCM verification obligation").

## Evidence protocol (R14)

Every verification run -- read, dry run, or live write -- records:

- `op_id` of the `run_module` call
- flexicon version (batch target: `4.11.0`)
- parameter values used
- report-line excerpt
- Sena 3 `.fwdata` mtime and SHA-256 **before and after** (the parse worker
  is known to rewrite `.fwdata` on nominally read-only work, so the hash is
  recorded on every run, not only writes)

Before any run, resolve the project path through `flextools_list_projects`
and assert the name is `Sena 3`. No verification run ever targets
Claude-Swahili.

Live writes (recipes that create or delete objects) additionally record:

- pre/post object values
- cleanup in the same session, using objects prefixed `zzRecipeTest`
- the cleanup's own pre/post hash

Live writes need a human present (constitution I, "no unattended destructive
writes"), except the Sena 3 test-project exception used by this batch:
tasks.md's live-write rule lets unattended runs perform live writes on Sena 3
only (assert `Sena 3`, dry-run first, `zzRecipeTest` objects, same-session
cleanup, pre/post evidence through `flextools_run_module`). Any other project
stops with `needs-human`.

Each recipe sets `verified_against:
{"flexicon": "4.11.0", "verified_by": "sena3-read" | "sena3-dryrun" |
"sena3-live"}` once its evidence file exists.

## Deferred recipes (FR-052)

Recipes from the FR-050 batch of 16 that cannot ship yet, with the blocking
flexicon issue. The batch ships when at least 12 of the 16 are verified.

| recipe id | reason deferred | blocking issue |
|---|---|---|
| _(none — 16 of 16 ship; T051 join 2026-09-28)_ | | |

Batch join (T051): all 16 FR-050 ids load via `load_recipe_library()` with
no errors, pass `validate_recipe(..., shipped=True)`, and carry Sena 3
evidence (`sena3-read` for read recipes, `sena3-dryrun` for
`set-allomorph-environments`, `sena3-live` for the 7 object-creating write
recipes). 0 deferred, 12-required threshold exceeded.

## SC-004 one-off (T073)

Date: 2026-09-28. Machine: developer Windows box
(`C:\Users\thoua\.flextoolsmcp\`).

- Legacy store: `skeletons.jsonl`, 319 rows (valid JSON).
- Developer store: `recipes.jsonl`, 183 rows, all with `migrated: true`
  (one-time migration output; zero post-migration captures on this machine).
- Reduction: (319 − 183) / 319 = **42.6%** — below the 50% SC-004 bar on
  the live store. Note the legacy file kept growing after the migration
  (`skeletons.jsonl` mtime 2026-09-28 10:03 is newer than `recipes.jsonl`
  mtime 00:25; spec corpus was 309 rows on 2026-09-25), so the live ratio
  understates the migration itself.
- No-short-entries clause: min non-blank non-comment code lines across the
  183 migrated rows is 5; **0 rows under 5 lines** — passes.
- Normative proof: `tests/test_local_recipes.py::test_migration_shrinks_fixture`
  (309-row-shaped fixture, asserts ≥ 50% smaller) plus the `test_cap_2000*`
  and `test_legacy_migration_*` tests all pass in the T073 lean-suite run.

Verdict: MIXED — size clause 42.6% on the live developer store (< 50%),
no-short-entries clause passes, automated fixture/cap/migration tests green.
