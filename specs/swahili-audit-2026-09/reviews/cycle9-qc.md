# Cycle 9 -- QC narrow re-gate: CP-D cycle-9 delta (97bd304 / c6cbd25 / 4b43688)

Scope: cycle-9 delta only. The four CP-D commits were not re-reviewed.

## P0 verdict: **CLOSED -- YES**

`docs/TOOL-CONTRACT.md:207-211` -- both false halves gone (no `defined_on[0]`
attribution, no "not yet repaired"). The replacement (`:213-235`) was checked
against the CODE, not the report:

- Resolved -> `fix_msg = f"Cast {obj_var} to {cast_iface}"` (validators.py:4128)
  and `"cast_interface": cast_iface` (:4200). Doc's "available_on / casting
  index / receiver-name tie-break" matches `_pick_cast_interface` steps 1-4
  (:3431-3495). [OK]
- Ambiguous -> two tiers (:4152-4185), `cast_interface` None. [OK]
- No usable candidate -> `"Cast {obj} to concrete type"` (:4188). [OK]
  (Latent only: 0/986 index properties reach it -- P3-3.)
- `:233-235` explicitly states #97 itself is **not** closed. [OK]

## Verbatim rendered `fix` strings (extracted by running the real detector)

`>6` tier -- `morph_type.Name`, 36 candidates, `cast_interface=None`:
> `Cast morph_type to the concrete interface it actually is. 36 interfaces declare 'Name' -- too many to guess. Determine it from where morph_type came from (the wrapper method's return type that produced it), or dispatch at runtime on morph_type.ClassName.`

`2..6` tier -- `unrecognized_receiver_zz.Gloss`, 3 candidates:
> `Cast unrecognized_receiver_zz to one of: ILexEtymology, ILexSense, ISenseOrEntry -- this list is ALPHABETICAL, NOT ranked by likelihood; do not just pick the first. Determine the correct one from where unrecognized_receiver_zz came from (the wrapper method's return type that produced it), or dispatch at runtime on unrecognized_receiver_zz.ClassName.`

Sweep of all 136 ambiguous properties: `>6` tier emits **zero** I-names (0
leaks); `2..6` tier carries the not-ranked warning in **125/125**; 0 bare
`context_entity=...`; `Name` never leads with `ICmAgent`. Split 126 named /
10 count-only / 0 placeholder -- matches the claim exactly. Judged as an LLM
instruction: actionable, and the `>6` tier structurally cannot invite a
first-pick guess. Dennis mode addressed.

## Findings

**P1-1** `STATUS.md:76-78` -- "**#97 IS NOT CLOSED.** Bug 1 ... is
deliberately deferred." Bug 1 *is* repaired. Same drift class as the P0, in
the file the lead/loop reads. Programmer disclosed it as out-of-lock-set.
**P1-2** `specs/swahili-audit-2026-09/.crew-handoff.json:42` -- `next_entry`
still says "Start B-3 ... #97 MUST stay marked not-closed until this lands."
It has landed; a loop re-entry would re-dispatch finished work.
**P1-3** (pre-existing, not CP-D) `handlers/api.py:1621,1636`,
`handlers/discovery.py:163,169`, `validators.py:3642` advertise
`CastingOperations.cast_to_concrete(obj)`. Verified at runtime: no
`CastingOperations` exists in flexicon 4.5.2 (`ImportError`; no class
anywhere in the package). Live #103 class in 5 places; introduced ffa3c0b.
The cycle-9 messages correctly advertise **nothing** (item 4 [OK]).

**P2-1** `validators.py:3449-3450`, `:3491-3493` -- still claim the ambiguous
path "routes to the existing fallback hint (call flextools_resolve_property
to resolve manually)". Cycle 9 deleted exactly that from `fix`.
**P2-2** `tests/test_issue100_access_path.py:399` -- CONFIRMED: `facade` is
assigned and never read; `hazardous` is built purely from `hasattr`. Dead
code that implies a facade cross-check it does not perform, and a needless
raise surface (swallowed into a skip at :443-450). NOT weaker than its
docstring -- that says "(hasattr-based)", and I verified hasattr alone yields
exactly the 21 (= 13 facade-only + 8 unreachable, split reproduced with the
discarded extractor).
**P2-3** `:392-395` reads the **untracked** `flexicon_api_v4.5.2.json`; on a
clean checkout the widened tripwire silently degrades to skip.
**P2-4** `:398` `Path(flexicon.__file__)` (`str | None`) -- harmless at
runtime, but worth guarding: a None would disable the tripwire via skip
rather than error.

**P3-1** `Human`/`Version` still render `one of: ICmAgent, ...` -- mitigated
by the not-ranked label, not eliminated. **P3-2** `>6` tier does not show how
to map a `ClassName` string to an interface. **P3-3** no-candidate tier has
no live-data coverage.

## Item verdicts

- **7 -- versioning.py:** `git diff 250469c..HEAD` is **byte-empty**. [OK]
- **2 -- sweep:** only P1-1/P1-2 above (+ `tasks-bugfix-campaign.md:584`
  unchecked B-3 box, P3). `TOOL-CONTRACT.md:215`, `CHANGELOG.md:587`,
  `test_issue97_*` docstrings, `INNOVATIONS.md:38` all accurate/historical.
- **5 -- behavior:** `severity`/`cast_interface`/`rewrite`/`imports_needed`/
  `available_on` untouched (probe-confirmed both tiers).
  `_RECEIVER_NAME_TO_INTERFACE` and `_build_cast_candidate_set`: **0**
  occurrences in the cycle-9 diff. No ranking added. Gate matrix passes:
  read-only+warning RUNS, read-only+error / write+warning / read-only+typo
  REJECT (`test_issue40_casting_severity.py::TestSeverityDecision`, 4/4).
- **6 -- normalizer:** genuinely shared (`_clean_interface_head` called at
  :3456 and :3515). Equivalence **re-derived independently** against
  transcribed pre-97bd304 inline logic: 986 properties x 27 receivers =
  **26,622 combos, 0 mismatches**; `_casting_candidates_for_fix` 0/986; plus
  14 adversarial inputs (empty, None, `(ILexSense)`, `iLexSense`, double
  parens) 0 mismatches. Behavior-preserving. [OK]
- **8 -- figures:** `test_flextools_health.py:46-62` -- 5/40 (12.5%), 1/40
  (2.5%), 40/300 (13.3%), 58/200 (29%), each cited to its report. All four
  trace to real runs; "~15-25%" gone. [OK]
- **9 -- tripwire:** api.py:689+ logic unchanged (comment-only). The 13/8-of-64
  figure is **independently confirmed** (13 facade-only, 8 unreachable,
  exact name lists reproduced). **Real tripwire, not a tautology**: enrolling
  each of the 21 hazardous classes in `KNOWN_OPERATIONS` (in-memory
  monkeypatch) failed **21/21** on *both* tests; a benign importable control
  passed both.
- **10 -- assertions:** `git diff 250469c..HEAD -- tests/` has **zero**
  removed assert/fail/raise lines. Three reports TRACKED per `git ls-files`:
  `cycle7-programmer-p2.md`, `cycle8-verification.md`, `cycle8-qc.md`. [OK]
- **11 -- suite:** `pytest -q` -> **1133 passed, 4 skipped, 12 subtests** in
  49.21s. `tests/evals/test_corpus.py` -> **35 passed, 2 skipped**. Both
  match the claim exactly. Casting/health/access-path subset: 86 passed.

`git status --porcelain` unchanged from the pre-existing set. No tracked file
edited by QC. No index refresh, no live-LCM access.

## Gate

**No P0 remains. CP-D may close on the code**, conditional on the lead
clearing **P1-1** and **P1-2** -- both are current-state assertions that #97
Bug 1 is unrepaired, i.e. the exact drift the P0 was, in the two files the
lead and the Ralph loop actually read. Neither was in the programmer's
editable set; both were disclosed. P1-3 is pre-existing and belongs in a new
issue, not CP-D.
