# after_plan QC gate (lex-qc), 2026-09-30

Verdict: one BLOCKING finding, now fixed in plan.md; non-blocking gaps folded in.

- B1 (fixed): the count 46 -> 47 also lives at `tests/test_parser_error_models.py:503`.
  `tests/evals` preflight-code lists are recorded as not applicable.
- N1 (fixed): scenario-to-test map added. Scenarios 1.3 "not refused" and 1.8 are named.
- N2 (fixed): the `_probe_access` change (`execution.py:5258`) is scheduled
  with a probe-called assertion. `unknown` with and without matches, the guarded
  call on a read-only run, and the detector inputs from all four certifier lists
  are each tested. The FR-040/041 ledger is stated as not automated.
- N3 (fixed): the live evidence shape is required (run_mode, FLEXLIBS_REQUIRE_LIVE,
  pre/post values from LCM, cleanup).
- N4 (fixed): audit candidates listed (`project_discovery.py:398,419`,
  `teardown_recovery.py:180`), plus a sweep-pattern pass on the detector shape.
- N5: the gate seam is confirmed. The "project_locked precedence vs refuse
  before confirmation" concern holds only if the gate fired on every verdict.
  It fires on `open_shared`/`unknown` only, now stated explicitly. Certifier
  wrapper rows may lack a line number, and data-model.md is adjusted for that.
