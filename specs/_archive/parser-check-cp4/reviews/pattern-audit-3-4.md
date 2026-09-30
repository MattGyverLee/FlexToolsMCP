# Pattern audit, sweeps 3 and 4 (parser-check CP4, T091)

Run 2026-09-24 with the `sweep-pattern` skill: two Explore agents, "very thorough", read-only. Sweep
#3 re-grepped `config_get(` across `src/`; it did not rely on the plan's list, whose line numbers
have drifted. Each sibling below has a disposition:

- **fixed**: fixed in this PR, with a test.
- **cleared**: checked, and it is not the bug class.
- **recorded**: a real sibling outside CP4's write path. It is listed for follow-up.

---

## Pattern audit: a config key that can lower a safety rung (sweep #3, R-08)

Original site: `require_write_confirmation` (`REQUIRE_WRITE_CONFIRMATION_KEY`) for `run_module`, in
`handlers/execution.py`.

Nothing bypasses `config_get`:
- `config.py` is the only code that opens `~/.flextoolsmcp/config.json`.
- `config_list()` is called only by `flextools_manage_config`'s "list" action.
- `manage_config` sets any key. It has no allowlist, and it parses string values as JSON, so the
  string `"false"` becomes the boolean `False`.

The sweep found 13 call sites: 10 direct `config_get` reads, 2 reader pass-throughs, and 1
`config_list` dump.

| Site | Key | Rung? | Is lowering it intended, and what does filing do |
|---|---|---|---|
| `handlers/execution.py:4528` | `require_write_confirmation` | RUNG | Intended for `run_module`, and disclosed (the original site). |
| `handlers/parse.py:1632` | `require_write_confirmation` | no, for filing | Read **only** to disclose it in the plan (`confirmation_setting.effective_for_filing: true`). The confirmation check never reads it (SC-008, `tests/test_filing_bypass_surface.py`). |
| `handlers/execution.py:4535` | `backup_before_write` (pass-through) | no | Predicts `would_run` for run_module's preview. The real read is `backup.py:131`. |
| `backup.py:128-134` | `backup_before_write` | RUNG | Intended: backups are best-effort (Principle I). Filing **honours** it by writing without a backup, but only after the plan says `disabled_by_configuration`, and the result and `meta.json` carry the no-recovery warning (FR-009). |
| `write_ladder.py:259` / `handlers/parse.py:1607` | `backup_before_write` (pass-through) | disclosure | Puts `disabled_by_configuration` in the plan. The backup outcome is part of `plan_id`, so changing the key between preview and confirm forces a fresh preview. |
| `backup.py:152` | `backup_retention` | RUNG, **not intended** | See below. |
| `handlers/execution.py:2820` | `auto_fix_enabled` | no | Read-only runs only. It is forced off whenever `write_enabled`, and filing does not read it. |
| `handlers/diagnostic_report.py:233, 234, 277` | report repo, email, offers | no | Report routing and advisories. |
| `handlers/admin.py:717, 745` | any key; the whole config | no | `manage_config` get and list. |

**`backup_retention`: fixed.**
- **Before:** a value of `0` made the prune step right after a backup delete the backup just
  written, while still returning `created: True` and its path. A non-integer value raised into
  `backup_failed` with the copy already on disk.
- **Why that mattered for filing:** filing backs up before every run and names that backup as the
  recovery point in the result, so it would have named a file that does not exist.
- **Now:** the backup just taken is never pruned, and an unparseable value falls back to the
  default. The fix is in `backup.py`. The test is
  `tests/test_filing_fail_closed.py::test_the_backup_just_taken_survives_any_retention_setting`.
- **What lowering retention still does, by intent:** it keeps fewer older recovery points.

---

## Pattern audit: a fail-open probe (sweep #4, #118)

Original site: #118 / `5612fc2`. An unresolvable projects directory used to give `free`; it now gives
`verdict="unknown"`, `probed=False`. Filing refuses `unknown` with `project_drive_unavailable`. That
is a disclosed divergence from `run_module` (contracts section 1, row 11).

Siblings found:

- `filing/worker_filing.py:376` + `filing/classify.py:127` [MED as reported; HIGH on triage]
  - **Before:** an unreadable default-user opinion (`"unreadable"`) was read as *shielded*.
    `would_delete` left it out, so the R-02 guard passed. FieldWorks' filer, reading the real
    opinion, could then delete an analysis nobody confirmed, with no `pre_deletion` capture.
  - **fixed**: `would_delete` now counts an unreadable opinion as deletable, which is the preview's
    own rule. Tests are in `tests/test_filing_classify.py`.
- `filing/worker_filing.py:187` [MED as reported; HIGH on triage]
  - **Before:** an unreadable `OccurrencesBag` or `AnalysesRS` became an empty set, so every
    analysis read as "in no text". That dropped the in-use disapproval guard and unshielded the
    whole word.
  - **fixed**: the filer-side join returns `None` (unknown). Unknown use shields nothing and guards
    every disapproval. Tests are in `tests/test_filing_classify.py`.
- `filing/preflight_reads.py:134` [HIGH]
  - **Before:** an unreadable analysis list became `[]` ("nothing to delete"), so the plan
    understated the bound.
  - **fixed**: the word now maps to `projection.UNREADABLE`. The plan's `deletion_projection` names
    it in `words_unreadable`, and the confirmation message says the bound does not cover it.
  - Even before the fix the R-02 guard contained it: nothing could be deleted for such a word
    unless the plan named it.
  - Tests are in `tests/test_filing_projection.py`.
- `filing/preflight_reads.py:105` [MED]
  - **Before:** an unreadable wordform form was skipped, so a scope word the index lacked could be
    that very wordform, yet it read as "absent".
  - **fixed**: while any form is unreadable, an absent word is `UNREADABLE`, not `None`. It has the
    same test and the same containment as the site above.
- `handlers/parse.py:1603` [MED]
  - **Before:** a preview answer that omitted words in scope gave an empty projection.
  - **fixed**: it now refuses with `runtime_error` / `IncompletePreview` and starts no worker. The
    test is in `tests/test_filing_fail_closed.py`.
- `filing/gate.py:223` [LOW as reported]
  - **Before:** a missing `morpher_null` read as "built".
  - **fixed**: anything but an explicit `False` refuses as `morpher_null`. The test is in
    `tests/test_filing_fail_closed.py`.
- `handlers/parse.py:1716` [LOW]
  - **Before:** if `acquire` returned None and `lookup` then returned None too, the handler started
    a run without holding the claim.
  - **fixed**: the handler retries, then fails closed with `runtime_error` / `FilingClaimUnavailable`.
  - Within one event loop `acquire` and `lookup` cannot interleave, so this is belt and braces.
- `filing/paths.py:117` [MED] `assert_outside_project` allows any path when the projects directory
  is unresolvable.
  - **recorded, contained**. The handler refuses `unknown` access before any worker exists.
  - The worker-side calls guard artifacts that are written under `~/.flextoolsmcp/`. Because the
    record root is fixed, it cannot be inside a projects directory that could not be found.
- `backup.py:79` [MED] If `disk_usage` raises, `predict_backup_skip` says `will_be_taken`.
  - **recorded**. The plan states intent, and the confirmed call reports the actual outcome.
  - A backup that then fails is reported `backup_failed`, and the no-recovery warning goes into the
    result and `meta.json`.
- `handlers/execution.py:4053`, `filing/worker_filing.py:142`, and `handlers/execution.py:5217`
  [MED/LOW] A `RefreshFromDisk` failure before close is swallowed.
  - **recorded**. This is the #147 capability pattern, shared with run_module.
  - For filing, the interval saves and `filing_commit` have already persisted the run's own writes.
  - Follow-up: report a failed reconcile in the result rather than swallow it.
- `project_access.py:215, 224` [MED/LOW] `_pid_is_alive` reads an unexpected OpenProcess error as
  "dead", which makes the lock `stale_lock`.
  - **recorded**. This predates CP4.
- `handlers/parse.py:2222` + `parse/diff.py:74` [MED] A failed access probe reads as "not shared" in
  CP3's diff.
  - **recorded**. CP3 read-side only.
- `handlers/execution.py:2165` [MED] The preflight report says "not locked" when the lock check
  raises.
  - **recorded**. This is run_module's preflight, outside CP4.
- `filing/gate.py:307` [LOW] An unreadable newer baseline is skipped, so an older baseline, or none,
  is used.
  - **recorded**. With no baseline, errors count as pre-existing. That softer verdict is documented
    and disclosed, as is the working hypothesis (`HYPOTHESIS_NOTE`).
- `project_discovery.py:239` / `:115` / `:337` / `:343` [LOW]
  - **cleared**. The fail-open in name resolution is deliberate and documented. The rest is
    informational only.

Sites cleared as fail-closed:
- `project_access.probe_project_access`, which gives `unknown` for an unresolvable directory and
  `open_exclusive` for an unreadable lock;
- `is_project_sharing_enabled`, which falls to the restrictive side;
- `send_receive_status`, where `unknown` is worded as Send/Receive;
- `probe_filing_surface` and `probe_bound_members`;
- `probe_parser_core` and `probe_hc_agent`;
- `eligible_entries` and `enabled_template_slots`, where None means not judged and the gate refuses
  on unknown;
- `load_error_baseline` and `_capture_load_baseline`;
- `fresh_occurrence`;
- `is_valid` and `checksum_matches`;
- the `MatchesIWfiAnalysis` suppress, which over-captures;
- `take_backup`;
- the reporting-only paths in `claims`.
