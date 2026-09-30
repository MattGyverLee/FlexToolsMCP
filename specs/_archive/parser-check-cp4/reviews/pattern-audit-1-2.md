# Pattern audit, sweeps 1 and 2 (parser-check CP4, T090)

Run 2026-09-24 using the `sweep-pattern` skill: two Explore agents, "very thorough", read-only over
`src/flextoolsmcp/server/**`. Each sibling below has a disposition:

- **fixed**: fixed in this PR, with a test.
- **cleared**: checked, and it is not the bug class.
- **recorded**: a real sibling outside CP4's write path, or one the R-02 guard already contains. It is
  listed here for a follow-up and is not fixed in this PR.

---

## Pattern audit: a proxy predicate that under- or over-counts a C# predicate (sweep #1, R-01)

Original sites:
- `signals/projections.py` and `signals/oracle.is_human_record`. This is CP3's "human record" test,
  standing in for "deletable by ParseFiler" (R-01, which CP4 replaced with FR-011's two conjuncts in
  `filing/projection.py`).
- `filing/eligibility.py`. **Found live by T081** and treated as a second original site:
  - The first port counted 280 eligible entries on `Malay Parsing-20230810withHC` where `HCLoader`
    loads 277, with no load error logged.
  - The port missed three silent drops:
    1. an infix with no position;
    2. an inflectional affix whose slots lie only in a disabled template;
    3. an entry whose MSAs route no morpheme.
  - **fixed**: the port now models all three. `tests/test_filing_eligibility.py` covers them offline.
    `tests/test_parse_live_cp4.py::test_t081_*` holds parity live at 41 = 41 and 277 = 277, with set
    equality.
  - **Residual**: whether a *present* environment or position validates is not ported. That needs
    the loader's natural-class tables. This is named in the module docstring and recorded as a
    concern.

Siblings found:

- `parse/worker_main.py:1359` [HIGH as reported] `_evaluation_facts` reads `Human` off the
  evaluation, not its owning agent.
  - **recorded**. It predates CP4 (it is on `main`), and CP4's bound does not use
    `parser_evaluated` (the FR-011 truth table in `filing/projection.py` has no such column).
  - Whether `ICmAgentEvaluation.Human` exists on the installed LCM needs a read-only live check. It
    is a CP3 follow-up.
- `parse/worker_main.py:1275` [MED] The CP3 oracle's `opinion` comes from `GetApprovalStatus` (any
  human agent), not `GetAgentOpinion(DefaultUserAgent)`.
  - **recorded**. It is CP3 read-side only.
  - Filing reads the default user agent itself: `preflight_reads.user_agent_opinion` on the preview
    side, and `FilingBackend.user_opinion` on the filer side.
- `filing/preflight_reads.py:89` [MED] `user_agent_opinion` falls back to `GetApprovalStatus`.
  - **cleared as contained**. That fallback is reached only when `DefaultUserAgent` cannot be read,
    and then FieldWorks' own filer (which binds the same agent) cannot run either.
  - Any disagreement it causes is caught by the R-02 guard on the filer side. That guard now counts
    an unreadable opinion as deletable (sweep #4 below).
- `parse/project_state.py:108` [MED] `_has_human_opinion` falls back to `IsHumanApproved`, so a human
  disapproval reads as "no opinion".
  - **recorded**. The value is carried as context beside the bound (`parser_created_present`).
    It never sets the number (`test_the_project_state_is_carried_never_used_to_force_the_number`).
- `parse/project_state.py:213` [MED] `parser_has_ever_run = parser_created > 0`.
  - **recorded**, for the same reason: context only, never used to force the bound.
- `signals/oracle.py:191` [MED] The claim was that the preview counts gloss-referenced analyses as in
  use while the filer does not.
  - **cleared**. `ParseFiler.SetUnsuccessfulParseEvals` (`ParseFiler.cs:302-318`) does test
    `analysis.MeaningsOC.Any(gloss => segmentAnalyses.Contains(gloss))`.
  - The filer-side join mirrors it: `filing/worker_filing.py` `existing()`, `glosses & refs`.
- `filing/paths.py:132` [MED] `send_receive_status` looks only at `<project>/.hg`; LIFT Send/Receive
  lives in `OtherRepositories/<P>_LIFT/.hg`.
  - **recorded**. For CP4 this is disclosure only: it words the recovery route and does not gate
    filing.
  - A LIFT-only Send/Receive project gets the local-restore wording instead of the re-download route.
  - Follow-up: widen the probe to `OtherRepositories/*/.hg`.
- `project_access.py:371` [LOW] The `held_by_other` verdict depends on `ProcessName == "FieldWorks"`.
  - **recorded**. This behaviour predates CP4.
- `scan/grammar_scan_module.py:140` [LOW] The literal `"***"` is treated as empty.
  - **cleared**. It is the documented FLEx convention (CLAUDE.md), and scan is read-only.

Sites cleared: `worker_filing.checksum_matches`, `_resolve_hc_agent`, `parser_probe.check_active_parser`,
the `IsUpToDate()` gate, `signals/tiers.py`, `is_optional_slot`, and the truth table in
`filing/projection.project`.

---

## Pattern audit: a worker- or session-lifetime cache consulted for a safety decision (sweep #2, R-02)

Original site: the read worker's cached segment and wordform join, which CP4 replaced with a fresh
read per preview (`filing/projection.fresh_occurrence`, `preflight_reads._fresh_wordform_index`).

**The backstop that bounds this whole class.** On the filer side, every word's would-delete set and
in-use disapprovals are recomputed from the filing worker's own fresh open. Filing skips any word
whose set is not inside the confirmed projection (`outside_projection`, `filing/classify.py`).

A stale preview therefore costs skipped words, never an unconfirmed deletion. The dispositions below
use that fact.

Siblings found:

- `filing/observer.py:166` [HIGH] `after_terminal` skipped recycling the read worker whenever a
  shared-role run was live, so the next preview read a pre-filing cache.
  - **fixed**. A busy worker is now marked stale (`ParseRunner.mark_read_worker_stale`), and every
    filing preflight read (`probe_agent`, `filing_gate`, `filing_preview`) recycles it first once
    nothing is running on it.
  - Tests are in `tests/test_filing_fail_closed.py`.
- `filing/worker_filing.py:437` [HIGH as reported] `_wordforms` is built once per filing worker.
  - **cleared as contained**. The filing worker lives for one run.
  - A wordform a peer deletes mid-run fails `is_valid()` and is skipped as `invalid_object`.
  - Every decision about *analyses* is read live off the wordform object, not off the map.
  - The residual is a wordform a peer creates mid-run in shared mode. Filing would not see it for
    that run's words. That is the same stance as FLEx's own parser.
- `parse/worker_main.py:1494` [MED] The preview walks the read worker's LCM cache, which never
  reloads from disk, so it can be stale against run_module subprocesses or a FLEx save.
  - **recorded, contained by the backstop**.
  - The fix above recycles the worker after *filing*. Staleness against *other* writers is the
    general CP3 read-worker property. It is listed for a follow-up: a RefreshFromDisk (issue #147
    capability) before the preview.
- `parse/worker_main.py:2432` [MED] The gate reports the held `_load_baseline` as current when
  `gate_probe` says no load happened.
  - **recorded, contained**. R-05 re-runs the gate in the filing worker on every grammar load,
    against that worker's own load (`this_run`). A reload the read worker missed is therefore seen
    at filing time.
- `parse/worker_main.py:2474` [MED] `eligible_entries` is cached per grammar load in the baseline.
  - **cleared**. A baseline is supposed to be a snapshot. The *current* eligible set is read fresh by
    `filing_gate` on every preview.
- `parse/worker_main.py:969` [LOW] `_availability_checked` is cached per worker.
  - **cleared**. The `morpher_null` probe re-checks on every gate. It now also refuses on a missing
    answer (sweep #4).
- `write_ladder.py:268` [MED] run_module's once-per-session backup set is never re-checked.
  - **recorded**. This is run_module behaviour, unchanged by the extraction (T006/T008).
  - Filing uses `once_per_session=False` and backs up before every run.
- `handlers/parse.py:1711` [LOW] The access decision is reused across awaits within one request.
  - **cleared**. It is a within-request snapshot. The claim (FR-026) and the worker's own open are
    the authorities.
- `handlers/parse.py:1624` [LOW] `duplicate_disclosure` reads the newest prior read-only run.
  - **cleared**. It is disclosure only and is bound into `plan_id`.
- `parse/worker_main.py:1263` [LOW] The residual `_wordform_index` feeds CP3 batch records.
  - **cleared**. This is the read-side half of the original site, and filing does not read it.
- `project_discovery.py:241` [LOW] The name resolution cache lasts 10 s.
  - **recorded**. It predates CP4. Filing's access probe and the worker's open act on the resolved
    name, which is re-read at open.
- `filing/worker_filing.py:373` [LOW] `_user_agent` is cached per worker.
  - **cleared**. The agent object is stable for the life of a run.
- `parse/worker_main.py:2137` [LOW] `self._index` affects try_word refusals.
  - **cleared**. It is a read path, not a write decision.

Sites cleared: `check_active_parser`/`preflight`, `_gated_parse`, the `session.filing_plans` binding
(which is recomputed and compared at confirm), `filing_backed_up_projects`, `versioning`'s discovery
cache, the doc and schema caches, `kernel.project_write_locks`, `measure._MEASURING`, `filing/claims`
(the authoritative registry), and the discovered-API gate sets.
