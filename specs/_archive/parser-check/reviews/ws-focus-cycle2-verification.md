# Live verification -- ws-focus cycle 2 (grammar_scan_module writing-system fix)

**Verdict: [PASS]**
**Live run: yes | Project: Sena 3, Aweti | Repository: D:\Github\_Projects\_LEX\FlexToolsMCP (branch main, working tree, commit 25961f8 + uncommitted grammar_scan_module.py WS fix)**
**Date:** 2026-09-20

## Claim under test

Rows 1/5/6/7a of flextools_grammar_health's static grammar scan
(src/flextoolsmcp/server/scan/grammar_scan_module.py) used to pass a raw
LCM IMultiUnicode (IMoForm.Form) straight into a
form in (None, "", "***") predicate and into a JSON-serialized label
field. A pythonnet multistring is never equal to those literals, so:

- rows 1 (zero-surface-morph-repeatable) and 6
  (partial-morpheme-incomplete-form) could only ever report count: 0
  (structurally, not because the data was clean), and
- serializing the raw multistring object as label is a hard crash at
  json.dumps.

The fix adds a _ws_handles / _read_ws seam that resolves the multistring
to a plain str at the projects default vernacular WS before both uses.

## Method -- real subprocess seam, not a direct call

Per instructions, run_grammar_scan was NOT imported directly. The scan
was driven through
flextoolsmcp.server.handlers.grammar_health.handle_flextools_grammar_health
(async), which calls handlers.execution.run_scan_module, which launches the
real generated-runner subprocess via subprocess_helpers.run_script_async
(sys.executable, the same interpreter that has pythonnet/flexicon
installed) -- exactly the path a live MCP tool call takes, including the
json.dumps(...) serialization step where the crash lived.

    export FLEXLIBS_REQUIRE_LIVE=1

Set per instructions; this repos own code has no such env var and no mock
fallback path for this tool at all -- confirmed by grep (no hit in src/ or
tests/conftest.py) and by the fact that tests/live_status.json does not
exist anywhere in this repo. There is nothing here that could silently
degrade to a mock; the only way handle_flextools_grammar_health produces a
result is by actually opening the named FieldWorks project.

Driver: a standalone async script (not pytest) that imports
handle_flextools_grammar_health from src/ and calls
await handle_flextools_grammar_health({"project_name": "Sena 3"}) and
{"project_name": "Aweti"}, dumping the full TextContent envelope to a file.

Both calls opened the project read-only (write_enabled=False, hard-coded
inside handle_flextools_grammar_health's own call to run_scan_module) and
returned the full JSON envelope. Both runs are DEFINITIVELY LIVE: the
returned hvos, GUIDs (goto_url), and label text are real project data (see
the Aweti orthography labels below -- the ENG phoneme character U+014B,
and superscript-P/T diacritics -- values no mock/fixture in this repo
contains). This repository has no requires_live_project pytest marker and
no tests/live_status.json; that machinery belongs to a different repo
(flexicon/FlexLibs2) referenced by the generic verification-agent
template. For FlexToolsMCP, "live" is established by the fact that
handle_flextools_grammar_health has exactly one code path -- open the
named project via flexicon.FLExProject/FLExInitialize in a real subprocess
-- and no seam anywhere in execution.py or grammar_health.py substitutes a
mock.

## Per-project result: did the scan complete?

| Project | success | runtime_error / _scan_failure_response? | checks_run (12) | checks_skipped |
|---|---|---|---|---|
| Sena 3 | yes (status: ok) | none | all 12 rows present | [] |
| Aweti | yes (status: ok) | none | all 12 rows present | [] |

checks_run for both projects, in order: zero-surface-morph-repeatable,
representation-variant-product, epenthesis-empty-struc-desc,
metathesis-rule-present, unbounded-quantifier, rule-product-morph-phon,
partial-morpheme-incomplete-form, stem-allomorph-stem-name-restriction,
multiple-allomorphs-per-entry, unordered-rule-application-stratum-pair,
duplicate-feature-bundle, optional-template-slot-branching.

### Sena 3 -- every finding

| check_id | spec_row | count | first objects (hvo / class / label) |
|---|---|---|---|
| zero-surface-morph-repeatable | 1 | 1 (nonzero) | 24793 / MoAffixAllomorph / (empty) |
| representation-variant-product | 2 | 2 | 10195 / PhPhoneme / N |
| epenthesis-empty-struc-desc | 3 | 0 | -- |
| metathesis-rule-present | 3 | 0 | -- |
| unbounded-quantifier | 4 | 0 | -- |
| rule-product-morph-phon | 5 | 0 | -- (affix-process count times enabled-rule count = 0) |
| partial-morpheme-incomplete-form | 6 | 1633 (nonzero) | 191 / MoStemAllomorph / pang; 273 / nzako; 519 / futhul; more (20 shown, capped) |
| stem-allomorph-stem-name-restriction | 7 | 0 | -- |
| multiple-allomorphs-per-entry | 7 | 14 | 15 / LexEntry / cibubu; 4522 / im2; more |
| unordered-rule-application-stratum-pair | 8 | 0 | -- |
| duplicate-feature-bundle | 9 | 0 | -- |
| optional-template-slot-branching | 10 | 7 | 21653 / MoInflAffixSlot / (empty); more |

### Aweti -- every finding

| check_id | spec_row | count | first objects (hvo / class / label) |
|---|---|---|---|
| zero-surface-morph-repeatable | 1 | 2 (nonzero) | 1014 / MoAffixProcess / (empty); 7498 / MoAffixProcess / (empty) |
| representation-variant-product | 2 | 2 | 19519 / PhPhoneme / eng-character U+014B |
| epenthesis-empty-struc-desc | 3 | 0 | -- |
| metathesis-rule-present | 3 | 0 | -- |
| unbounded-quantifier | 4 | 0 | -- |
| rule-product-morph-phon | 5 | 1600 | 458 / MoAffixProcess / to; 674 / a-superscriptP; 928 / ti; 1014 / (empty); 1420 / pej; more (20 shown, capped) |
| partial-morpheme-incomplete-form | 6 | 2 (nonzero) | 1014 / MoAffixProcess / (empty); 7498 / MoAffixProcess / (empty) |
| stem-allomorph-stem-name-restriction | 7 | 9 | 953 / MoStemAllomorph / ma-superscriptP; 3970 / pa-superscriptP; more |
| multiple-allomorphs-per-entry | 7 | 29 | 126 / LexEntry / affix with a glottal-stop mark; 1259 / t-...-at; more |
| unordered-rule-application-stratum-pair | 8 | 20 | 1730 / PhRegularRule / (empty); more |
| duplicate-feature-bundle | 9 | 0 | -- |
| optional-template-slot-branching | 10 | 9 | 1685 / MoInflAffixSlot / (empty); more |

Non-ASCII Aweti orthography characters are described rather than
reproduced literally in this table to avoid a console-encoding detour; the
raw JSON captures contain the exact UTF-8 text and were verified
byte-for-byte during the run (label U+014B for the ENG phoneme, and
superscript P/T diacritics on several affix-process forms).

## CRITICAL EVIDENCE -- rows 1 and 6

Before the fix, is_zero_surface_form / IMoForm.IsComplete's label read
compared a raw IMultiUnicode against (None, "", "***"), which is never
True under pythonnet -- these two rows were STRUCTURALLY INCAPABLE of a
nonzero count regardless of the data.

| Project | Row 1 count | Row 6 count | Verdict |
|---|---|---|---|
| Sena 3 | 1 | 1633 | Both nonzero -- positive proof the fix works |
| Aweti | 2 | 2 | Both nonzero -- positive proof the fix works |

Both projects independently produced a nonzero count on both rows, so this
is not one lucky data point. The objects entries backing these counts are
typed, real objects (MoAffixAllomorph hvo 24793 on Sena 3; MoAffixProcess
hvo 1014 and 7498 on Aweti) reachable via their goto_urls -- not
synthetic. Since both counts are nonzero here, there is no "zero could
mean clean OR could mean still broken" ambiguity to resolve for this run;
had either count come back zero, the WS inventory below is exactly the
tool that would be needed to tell a genuinely-clean project from a
resolution failure.

## CRITICAL EVIDENCE -- label

Grepped both raw response JSON captures for the literal string SIL.LCModel:

    grep -c "SIL.LCModel" sena3_out2.json aweti_out2.json
    sena3_out2.json:0
    aweti_out2.json:0

Zero hits in both. Every label observed across both responses is a plain
JSON string -- either genuine vernacular text (pang, nzako, the ENG
phoneme, several superscript-marked Aweti affix forms, cibubu, and so on)
or the documented empty spelling "" for rows with no label source in the
implementation table (rows 3a/3b/4/8/10, and rows 1/6 whose suspects are
themselves the empty form). No CLR repr (for example
SIL.LCModel.DomainImpl.MoStemAllomorph) and no raw object leaked through
anywhere. handle_flextools_grammar_health also round-tripped every
finding through the closed, extra=forbid GrammarHealthFinding/FoundObject
pydantic models (_assemble_findings) with no ValidationError for either
project -- confirming every label was already a str by the time it
reached that validation layer, consistent with _found_object's
defense-in-depth coercion never having to fire.

## WRITING-SYSTEM INVENTORY

Read directly (read-only FLExProject.OpenProject(writeEnabled=False),
opened and closed via the same flexicon.FLExInitialize/FLExCleanup the
real subprocess runner uses) to determine whether either project's
zero/nonzero counts above could be affected by secondary-vernacular-WS
forms reading as empty under single-WS resolution.

| Project | Default vernacular | Default analysis | ALL vernacular WSes |
|---|---|---|---|
| Sena 3 | seh "Sena" (handle 999000005) | pt "Portuguese" (handle 999000004) | seh "Sena", AND seh-fonipa-x-etic "Sena (Phonetic)" |
| Aweti | awe "Aweti" (handle 999000001) | en "English" (handle 999000002) | awe "Aweti" (only one) |

SENA 3 IS MULTI-VERNACULAR (2 vernacular WSes); AWETI IS SINGLE-VERNACULAR
(1). This is exactly the scenario the domain review flagged: on Sena 3, a
form recorded ONLY in seh-fonipa-x-etic ("Sena (Phonetic)") and left blank
in the default seh ("Sena") alternative will now legitimately read as
empty under this fix's single-WS (_read_ws at
GetDefaultVernacularWSHandle()) resolution. That is the fix behaving
correctly per the projects own directive ("focus by default on default
analysis and default vernacular"), not a regression -- but it means Sena
3's row 1/6/7a counts specifically (not row 2/9, which read
phoneme/feature data unrelated to .Form) could differ from a hypothetical
scan that also checked the phonetic WS. This is disclosed rather than
resolved -- CP1's scope, per the module's own docstring, is unconditional
on WS beyond "default vernacular", and this verification is not the place
to relitigate that scope decision. Aweti has only one vernacular WS, so no
such ambiguity exists there: Aweti's row 1/6 counts of 2 are unambiguous.

## Full test suite (regression, supplementary)

Command: python -m pytest -q (bare, no marker filter -- confirmed safe for
this repo: grep found no requires_live_project marker and no
tests/live_status.json anywhere in FlexToolsMCP; this repo's suite is
entirely offline/fixture-based, so unlike the flexicon repo, bare pytest
here does not risk touching a real project).

Result: 1 failed, 2094 passed, 8 skipped, 23 warnings, 36 subtests passed
in 395.50s

Comparison against the STATUS.md baseline (1437 passed / 8 skipped,
recorded mid-campaign, explicitly flagged in the task as needing
re-verification since the tree has moved): skip count matches exactly
(8/8, same pinned skip set); passed count is up +657, consistent with the
large amount of parse/CP2b work landed in this working tree since that
baseline was recorded (17 modified files: server.py, handlers/parse.py,
parse/*, subprocess_helpers.py, six parse test files, and so on -- all
listed in the task's own "NOTE ON THE WORKING TREE").

The one failure is NOT caused by the WS fix:

    FAILED tests/test_parse_status_handler.py::test_parse_job_cancelled_is_not_reachable_from_the_status_handler
    AssertionError: assert stage_at_cancel in "word = str(result.get(word) or )\n..."

This test imports only flextoolsmcp.server.handlers.parse (as
parse_handler), server.parse.runner, server.parse.stages,
server.parse.worker_client, and test_try_word_handler -- confirmed by
reading its import block; it has zero import of, and makes zero mention
of, grammar_scan_module or handlers.grammar_health. It is a structural
AST-scan test over handle_flextools_parse_status (server/handlers/parse.py),
one of the 17 files the task's own note identifies as the user's own
uncommitted CP2b parse work-in-progress, which this agent was explicitly
told to leave alone and merely attribute correctly. Per that instruction:
ATTRIBUTED TO THE IN-PROGRESS CP2b PARSE WORK, NOT TO THE GRAMMAR-SCAN WS
FIX. No source file was touched to investigate or repair this.

## Cleanup

Both projects were opened writeEnabled=False throughout (grammar-health
tool call) or opened/closed read-only with no BeginUndoTask (the
WS-inventory probe). No write of any kind was issued to either project;
nothing to restore. git status confirms grammar_scan_module.py is the
only scan-module file with pending changes and it was not modified by
this verification pass.

## Result

[PASS] -- the WS fix is live-verified on two independently-populated,
real FieldWorks projects. Rows 1 and 6, previously structurally incapable
of a nonzero count, now report real nonzero counts (Sena 3: 1 / 1633;
Aweti: 2 / 2) backed by real hvo/goto_url pairs. No label in either
response leaked a CLR repr or raw object (SIL.LCModel grep: 0 hits both
projects); every finding validated through the closed pydantic models
with no coercion needed. Sena 3 is multi-vernacular (seh plus
seh-fonipa-x-etic) and Aweti is single-vernacular -- flagged prominently
above, not as a defect but as a scoping caveat on how Sena 3's row 1/6/7a
counts should be read. The full suite's one failure is pre-existing,
uncommitted CP2b parse work unrelated to this fix, not a regression it
introduced.
