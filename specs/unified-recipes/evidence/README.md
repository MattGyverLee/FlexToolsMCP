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
writes"). An unattended run stops with `needs-human`.

Each recipe sets `verified_against:
{"flexicon": "4.11.0", "verified_by": "sena3-read" | "sena3-dryrun" |
"sena3-live"}` once its evidence file exists.

## Deferred recipes (FR-052)

Recipes from the FR-050 batch of 16 that cannot ship yet, with the blocking
flexicon issue. The batch ships when at least 12 of the 16 are verified.

| recipe id | reason deferred | blocking issue |
|---|---|---|
| _(none yet)_ | | |
