# WS-focus cycle 2 — dispatch plan

Emitted by `/lex-lead` after synthesizing the four cycle-1 reports. The
coordinator executes the fenced block below verbatim (`subagent_type`,
`description`, `prompt`).

**Lock claim in force:** team `lex-grammar-health-ws`, session
`2b1e527d-eb93-4d1b-9556-02e2839698f7`, expires 2026-09-21T05:33Z, 14 files
(6 from cycle 1, 8 added for cycle 2). New files created by the P0 task carry
no conflict.

**Working-tree note:** the ~17 other modified files are the user's own
uncommitted CP2b work in progress. No parallel session is editing this repo.
They are not contested and not at risk — they simply stay untouched, and every
commit from this campaign stays path-scoped so they are never swept in.

**Sequencing rationale:** group 1 runs alone because its step 6 takes a full
`pytest -q` baseline, which is only interpretable if no other task is mid-edit.
If group 1 comes back RED, hold group 2 and re-invoke the lead — the P0 and doc
work is wasted effort if the seam itself is wrong.

---

```dispatch_plan
cycle: 2
rationale: fire the live-verification gate first and alone so its full-suite baseline is clean, then land the approved execution.py P0 fix and the doc amendments in parallel; row 2 and checks_skipped isolation deliberately held for the next checkpoint
groups:
  - mode: sequential
    tasks:
      - subagent_type: lex-verification
        description: Live read-only grammar-health verification
        prompt: |
          Repo: D:\Github\_Projects\_LEX\FlexToolsMCP (branch main).

          GOAL: prove that the writing-system fix just made to
          src/flextoolsmcp/server/scan/grammar_scan_module.py actually eliminates a
          shipped crash, by running against REAL FieldWorks projects. This is the gate
          the whole campaign turns on. Everything so far has been tested only against
          fake objects.

          BACKGROUND: rows 1/5/6/7a of the grammar scan passed a raw LCM
          IMultiUnicode (IMoForm.Form) straight into a `form in (None, "", "***")`
          predicate and into a JSON-serialized `label` field. A pythonnet multistring is
          never equal to those literals, so the predicate was unconditionally False
          (rows 1 and 6 could only ever report count: 0), and serializing the raw object
          as `label` is a hard crash. A `_ws_handles` / `_read_ws` seam now resolves the
          multistring at the default vernacular writing system before both uses.

          THIS IS READ-ONLY. flextools_grammar_health opens the project with
          write_enabled=False (see handlers/grammar_health.py:262-268). Do NOT write to
          any FLEx project, and do not run any parser.

          TARGETS (both confirmed present under C:/ProgramData/SIL/FieldWorks/Projects):
            - "Sena 3"
            - "Aweti"

          DO ALL OF THE FOLLOWING:

          1. Run the grammar-health scan against each project through the REAL
             subprocess seam (handlers/grammar_health.handle_flextools_grammar_health ->
             run_scan_module), NOT by importing run_grammar_scan directly. The point is
             to exercise the actual JSON serialization path where the crash lived.
             Set FLEXLIBS_REQUIRE_LIVE=1 so silent mock degradation becomes a hard error
             rather than a false pass (PowerShell: $env:FLEXLIBS_REQUIRE_LIVE="1").
             Capture the full response envelope for each project.

          2. Report, per project: did the scan complete? Any runtime_error or
             _scan_failure_response? The full checks_run / checks_skipped lists, and
             every finding's check_id, spec_row, count and the first few objects[]
             entries.

          3. CRITICAL EVIDENCE -- rows 1 and 6 (zero-surface IMoForm, and
             IMoForm.IsComplete). Before the fix these were STRUCTURALLY incapable of a
             nonzero count. Report their counts now. A nonzero count on either row is the
             positive proof the fix works. A zero count is NOT automatically a failure
             (the project may genuinely have no zero-surface forms) but you must say
             which it is and how you can tell the difference.

          4. CRITICAL EVIDENCE -- `label`. Confirm every `label` in every finding's
             objects[] is a plain JSON string, never a CLR repr like
             "SIL.LCModel.DomainImpl.MoStemAllomorph" and never an object. Grep the raw
             response text for "SIL.LCModel" and report any hit -- that would mean a
             multistring leaked through un-resolved somewhere the seam does not cover.

          5. WRITING-SYSTEM INVENTORY, per project. Record the default vernacular WS, the
             default analysis WS, and the FULL list of vernacular writing systems.
             REASON THIS MATTERS: a domain review flagged that on a project with more
             than one vernacular WS, a form recorded ONLY in a secondary vernacular WS
             will now legitimately read as empty under single-WS resolution. That is a
             CORRECT consequence of the fix, not a regression -- but we can only tell the
             two apart if we know the project's WS inventory. If either project is
             multi-vernacular, say so prominently and explain which counts it could
             affect.

          6. Run the FULL test suite (`python -m pytest -q`) and report pass/fail/skip
             counts. The cycle-1 programmer ran only two test files; this checks that the
             new `run_grammar_scan(project, ws=None)` signature and the `_found_object`
             coercion did not break any other caller. Compare against any baseline you
             can find in git history or STATUS.md (a recent baseline is 1437 passed /
             8 skipped, but verify rather than assume -- the tree has moved since).

          7. If the scan FAILS on either project, capture the full traceback verbatim.
             That is the single most valuable artifact you could return.

          ALLOWED FILES -- you may WRITE only:
            specs/parser-check/reviews/ws-focus-cycle2-verification.md
          You may READ anything. You must EDIT no source, test, spec or doc file.
          You are verifying, not fixing. DO NOT COMMIT anything.

          NOTE ON THE WORKING TREE: about 17 other files are modified (CP2b parse work:
          server.py, handlers/parse.py, parse/*, subprocess_helpers.py, CHANGELOG.md,
          docs/TOOL-CONTRACT.md, specs/parser-check-cp2b/*, and six parse test files).
          These are the USER'S OWN uncommitted work in progress. Leave them completely
          alone -- do not revert, stash, restore or commit them, and do not treat them as
          campaign state or as a problem to fix. If the full-suite run in step 6 surfaces
          failures that trace into those files, report that plainly and attribute it
          there rather than to the WS fix; do not attempt to repair it.

          OUTPUT: write your full report to
          specs/parser-check/reviews/ws-focus-cycle2-verification.md
          Return to the lead ONLY a 2-line summary plus that file path. Do not paste the
          report body back.
        expected_artifact: Live verification report at specs/parser-check/reviews/ws-focus-cycle2-verification.md (path + 2-line summary only)
  - mode: parallel
    tasks:
      - subagent_type: lex-programmer
        description: Fix is_empty_multistring P0 in execution.py
        prompt: |
          Repo: D:\Github\_Projects\_LEX\FlexToolsMCP (branch main).

          A P0 was found by a pattern audit. It is the same defect class as one just
          fixed in the grammar scanner, but this one is SHIPPED TO USERS. The user has
          explicitly approved fixing it inside this campaign.

          THE BUG -- src/flextoolsmcp/server/handlers/execution.py:4056-4062:

              FLEX_EMPTY_PLACEHOLDER = "***"

              def is_empty_multistring(text):
                  if text is None:
                      return True
                  if not isinstance(text, str):
                      text = str(text)
                  text = text.strip()
                  return text == "" or text == FLEX_EMPTY_PLACEHOLDER

          This helper is injected into the exec namespace of EVERY generated FLExTools
          module and EVERY bare snippet (see execution.py around line 4152). When handed
          a raw LCM IMultiUnicode / IMultiString / ITsString -- which is exactly what
          `sense.Gloss` or `form.Form` gives you by direct C# field access -- the
          `str(text)` coercion produces a CLR ToString()/repr that never equals "" or
          "***". So it returns **False for a field that is actually empty**. Silently.

          It is documented as returning True "for None, '', or '***'" in at least:
            - docs/FLEXTOOLS-STYLE-GUIDE.md:265-266
            - src/flextoolsmcp/server/tool_definitions.py:295
            - src/flextoolsmcp/server/handlers/admin.py:295
          and the style guide's usage example (`if is_empty_multistring(gloss):`) shows a
          bare variable with no visible `.Text` / `.GetGloss()` extraction -- so a user
          or a generator following the doc verbatim walks straight into the bug.

          RULING FROM THE LEAD, already decided and user-approved -- implement it, do not
          relitigate: this is a BUGFIX, not a contract change. Making the helper
          defensive is a strict superset of its documented behaviour; no caller can be
          intentionally relying on "False for an empty multistring".

          DO THIS:

          1. Make `is_empty_multistring` defensive. Before the string comparison, if the
             input is not a str, attempt to unwrap it in this order, each attempt guarded
             so it can never raise:
               a. `.Text` (an ITsString)
               b. `.BestAnalysisAlternative.Text`, then `.BestVernacularAlternative.Text`
                  (an IMultiUnicode / IMultiString)
             If unwrapping yields a str, test that. If every attempt fails, fall back to
             the current `str(text)` behaviour rather than raising -- this function is
             injected into user scripts and must NEVER be the thing that throws.
             Keep the existing None handling and the `.strip()`.

             IMPORTANT: this code is a string spliced into a generated module and runs
             under IronPython/pythonnet inside the FLExTools subprocess. Keep it
             dependency-free and defensive. Do not add imports it cannot resolve there.

          2. Update its docstring/comment to state plainly that it accepts EITHER an
             already-resolved str OR a raw multistring, and that it resolves the latter
             at the best available alternative.

          3. Fix the docs so they stop teaching the bug:
             - docs/FLEXTOOLS-STYLE-GUIDE.md around lines 265-269: make the usage example
               show where the value came from. Note that lines 150-160 of that SAME file
               already demonstrate the correct idiom
               (`.AnalysisDefaultWritingSystem.Text` resolved BEFORE the "***" compare).
               Make the two sections consistent and cross-reference each other rather
               than quietly contradict.
             - tool_definitions.py:295 and admin.py:295: correct the description to match
               the new behaviour.

          4. Add tests. Put them where execution.py's helper injection is already tested
             -- find the existing test file and use it if there is a natural home; only
             create a new file if there genuinely is not. Creating a new test file is
             explicitly permitted. Cover at minimum:
               - a fake object that is NOT a str, is not equal to "" or "***", and
                 exposes `.Text` returning "" -> must now return True
               - the same via `.BestAnalysisAlternative.Text`
               - an object whose unwrapping RAISES -> must not propagate, must still
                 return a bool
               - the existing str / None / "***" / whitespace cases behaving IDENTICALLY
                 to before (regression guard against over-tightening -- this half matters
                 as much as the new behaviour)

          ALLOWED FILES -- you may edit ONLY these. The lock claim (team
          `lex-grammar-health-ws`) already covers them; you do not need to claim
          anything yourself:
            src/flextoolsmcp/server/handlers/execution.py
            docs/FLEXTOOLS-STYLE-GUIDE.md
            src/flextoolsmcp/server/tool_definitions.py
            src/flextoolsmcp/server/handlers/admin.py
            the ONE test file you choose or create (name it in your report)
            specs/parser-check/reviews/ws-focus-cycle2-programmer-p0.md (your report)

          FORBIDDEN -- do not edit, read-only at most:
            - CHANGELOG.md, docs/TOOL-CONTRACT.md, src/flextoolsmcp/server.py,
              src/flextoolsmcp/server/handlers/parse.py, src/flextoolsmcp/server/parse/*,
              src/flextoolsmcp/server/subprocess_helpers.py, specs/parser-check-cp2b/**
              -- these are the USER'S OWN uncommitted CP2b work in progress. They are not
              broken and not yours to touch. Leave them exactly as they are.
            - src/flextoolsmcp/server/scan/grammar_scan_module.py,
              tests/test_grammar_scan_checks.py,
              specs/parser-check/contracts/flextools_grammar_health.md
              -- this campaign's cycle-1 output, already complete.
            - specs/parser-check/data-model.md, specs/parser-check/SPEC.md,
              specs/parser-check/tasks.md, tests/fixtures/parser_check.py
              -- a lex-doc agent is editing these concurrently in this same cycle. Stay
              out to keep the two tasks file-disjoint.

          Run the tests you added plus the existing suite for the files you touched, and
          report the counts. DO NOT COMMIT -- the lead is scoping a path-limited commit.

          OUTPUT: write your report to
          specs/parser-check/reviews/ws-focus-cycle2-programmer-p0.md
          Return to the lead ONLY a 2-line summary plus that file path.
        expected_artifact: P0 fix report at specs/parser-check/reviews/ws-focus-cycle2-programmer-p0.md (path + 2-line summary only)
      - subagent_type: lex-doc
        description: Amend WS rule in spec and data-model
        prompt: |
          Repo: D:\Github\_Projects\_LEX\FlexToolsMCP (branch main).

          An archivist investigation established that a cross-cutting rule in the spec is
          INCOMPLETE, and that the incompleteness propagated into code that shipped
          broken. Your job is to amend the documentation so the same bug cannot be
          written again. READ specs/parser-check/reviews/ws-focus-cycle1-archivist.md
          FIRST -- it has the full provenance and every restatement site with line
          numbers.

          THE DEFECT IN THE RULE: specs/parser-check/data-model.md, "Cross-cutting rules"
          item 2, lines 158-173, says the emptiness predicate is
          `form in (None, "", "***")`. That is correct about the VALUES and silent about
          the TYPE. `IMoForm.Form` is an `IMultiUnicode` OBJECT, not a str. A pythonnet
          multistring is never `==` to any of those literals, so the predicate was
          unconditionally False and the check could never fire. The archivist's verdict,
          which the lead accepts: AMEND, do not merely clarify.

          MAKE THESE EDITS:

          1. data-model.md rule 2 (lines 158-173): insert a WS-RESOLUTION STEP before the
             existing predicate sentence. The predicate itself is UNCHANGED -- only its
             input contract needs stating. Say explicitly: resolve the multistring to a
             plain `str` at a NAMED writing system BEFORE calling `is_empty_form`.
             Vernacular default for forms/representations; analysis default for
             glosses/names/abbreviations. State that the raw object is never compared
             directly and never serialized directly.
             Cross-reference docs/FLEXTOOLS-STYLE-GUIDE.md:150-160, which already
             demonstrates the correct idiom -- the right pattern existed elsewhere in
             this repo and simply was not carried over.

          2. data-model.md row table (around lines 239-254) and
             specs/parser-check/SPEC.md section 9.5.4 (around lines 1392-1442): these
             tables have no writing-system column. Do NOT add a full column -- only rows
             1, 2, 6 and the label sites in 5/7a touch multistring fields. Add ONE
             cross-cutting note beneath the table: any row reading an
             `IMultiUnicode`/`IMultiString` must resolve it at a named WS before
             comparing or serializing it. The archivist specifically warns that without
             this note, row 11 will reproduce the bug when it is written.

          3. specs/parser-check/contracts/flextools_grammar_health.md: rows 1 and 6 were
             STRUCTURALLY incapable of a nonzero `count` before this fix -- the worked
             example showing `count: 3` was literally unreachable. Add a sentence noting
             the count becomes real only after the WS resolution.
             NOTE: the cycle-1 programmer already added a "`label` is always a plain
             string" section to this file. Read what is there and COMPLEMENT it -- do not
             duplicate or contradict it. This file is already modified in the working
             tree; that is expected, it is this campaign's own cycle-1 output.

          4. specs/parser-check/tasks.md lines 129 (T033) and 142 (T034) quote the old
             predicate. These are a HISTORICAL LOG of completed work -- do NOT rewrite
             them as though they had always been right. Add a brief footnote or
             bracketed note recording that the predicate was later amended to require WS
             resolution first, with a pointer to the amended rule 2.

          5. tests/fixtures/parser_check.py, around lines 150-160: `FakeIMoForm.Form` is
             typed `Optional[str]` -- a plain string. This is WHY the bug survived
             testing: the fixture could not represent the failing input. Add a clearly
             marked `# KNOWN SIMPLIFICATION:` comment stating that this stub models
             `.Form` as an already-resolved str, that a live `IMoForm.Form` is an
             `IMultiUnicode` object, and that tests using this fixture therefore cannot
             catch WS-resolution defects.
             ADD THE COMMENT ONLY. Do not change the fixture's behaviour, its type, or
             any test. Changing it would break the 102 currently passing tests and is
             deliberately scheduled for the next checkpoint.

          CONSTRAINTS:
          - Per SPEC 9.5.3/9.5.7 this scan reports SUSPECTS, never verdicts, and never a
            scalar score. Keep all wording consistent with that -- no severity language,
            no ranking, no score.

          ALLOWED FILES -- you may edit ONLY these. The lock claim (team
          `lex-grammar-health-ws`) already covers them; you do not need to claim
          anything yourself:
            specs/parser-check/data-model.md
            specs/parser-check/SPEC.md
            specs/parser-check/tasks.md
            specs/parser-check/contracts/flextools_grammar_health.md
            tests/fixtures/parser_check.py   (comment only, per item 5)
            specs/parser-check/reviews/ws-focus-cycle2-doc.md   (your report)

          FORBIDDEN -- do not edit:
            - CHANGELOG.md, docs/TOOL-CONTRACT.md, specs/parser-check-cp2b/**,
              src/flextoolsmcp/server.py, handlers/parse.py, parse/*,
              subprocess_helpers.py -- these are the USER'S OWN uncommitted CP2b work in
              progress. Leave them exactly as they are.
            - src/flextoolsmcp/server/scan/grammar_scan_module.py. Its docstrings at
              lines 110-122 and 375-377 ALSO restate the old rule, but that file is
              cycle-1 output and is being held stable while live verification runs
              against it. Report those two as a carried-forward edit for the next
              checkpoint instead of making them.
            - src/flextoolsmcp/server/handlers/execution.py and
              docs/FLEXTOOLS-STYLE-GUIDE.md -- a lex-programmer agent is editing both
              concurrently in this same cycle. You may READ the style guide to
              cross-reference it (item 1), but not edit it.

          DO NOT COMMIT.

          OUTPUT: write your report to
          specs/parser-check/reviews/ws-focus-cycle2-doc.md
          Return to the lead ONLY a 2-line summary plus that file path.
        expected_artifact: Doc amendment report at specs/parser-check/reviews/ws-focus-cycle2-doc.md (path + 2-line summary only)
on_return: re-invoke /lex-lead with each report's FILE PATH + 2-line summary (not the body), noting cycle 2 of the ws-focus campaign. If group 1 (verification) comes back RED, hold group 2 and re-invoke immediately -- the P0 and doc work is wasted if the seam itself is wrong. Do not commit anything; the lead will emit a path-scoped commit list for user confirmation at the checkpoint.
```
