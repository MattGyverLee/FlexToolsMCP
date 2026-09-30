# QC Sweep — raw LCM multistring used as `str` (WS-focus cycle 1)

**Summary:** One real sibling found, in the shipped `is_empty_multistring` runner helper
(`execution.py:4056`) — documented as handling `"***"`, silently always-False on a raw
multistring. Everything else checked (worker_main.py, parse.py, casting_helpers.py,
templates) already extracts `.Text` or uses Operations-layer `str` returns correctly.
Task 2: `checks` filtering is post-hoc, so an unrequested row's crash still kills the whole
scan; recommend per-row exception isolation, explicitly flagged as a `checks_skipped`
contract change.

## TASK 1 — Pattern sweep (P0/P1/P2)

**P0 — `src/flextoolsmcp/server/handlers/execution.py:4056-4062`.**
`is_empty_multistring(text)` is injected into every generated module's / bare-snippet's exec
namespace (`execution.py:4152`) and is documented (`docs/FLEXTOOLS-STYLE-GUIDE.md:265-266`,
`tool_definitions.py:295`, `admin.py:295`) as returning True "for None, '', or '***'". But its
body does `if not isinstance(text, str): text = str(text)` then compares to `""`/`"***"` — on a
raw `IMultiUnicode`/`ITsString` this coerces to a CLR `ToString()`/repr, which never equals
those literals, so it silently returns **False for an actually-empty field**.

The style guide's own usage example (`if is_empty_multistring(gloss):`) uses a bare variable
name with no visible `.GetGloss()`/`.Text` call, so a generator — or a user — following the doc
verbatim is one step from the exact bug this audit is about.

Fix: either make the function defensive (unwrap `.BestAnalysisAlternative.Text` / `.Text` when
given a non-str with those attrs), or update the docstring and style-guide example to state
that the input must already be a `str` (from an Operations `Get*` call or `.Text`).

**P1 — none found beyond the above.** Checked and confirmed clean (Operations-layer or
`.Text`-suffixed, so out of scope as false positives):

- `casting_helpers.py:152,177,188` — `get_headword`/`get_lexeme_form` both end in `.Text`.
- `server/parse/worker_main.py:761-773` (`_as_text`) — generic CLR->str coercion for the trace
  channel, not multistring-typed; `_summarize_trace` (810+) walks `XElement.Name.LocalName`
  (System.Xml.Linq), unrelated interface.
- `server/handlers/parse.py:668,677` — both via `project.Senses.GetGloss(...)`.
- `server/worked_examples.py:337,347` — example code, both have `.Text`.
- `templates/3-liblcm-template.py:97-98,122-123,339` — all extract `.Text` before comparing
  to `"***"`.
- `server/handlers/admin.py:209` — docstring only, has `.Text`.
- `grammar_scan_module.py:828` — `is_empty_form(long_name)` where `long_name =
  features.LongName`. `IFsFeatStruc.LongName` is a direct `String` property per its own
  docstring (not `IMultiUnicode`), so this one use of `is_empty_form` on a non-Form field is
  fine, unlike the four excluded call sites.

**P2** — none noteworthy. No other `.BestAnalysisAlternative`/`.BestVernacularAlternative`
without a trailing `.Text` was found anywhere in `src/flextoolsmcp/`.

## TASK 2 — `checks` scoping in `grammar_health.py`

Confirmed the architecture problem as described: `handle_flextools_grammar_health`
(`handlers/grammar_health.py:262-268`) calls `run_scan_module(...)`, which runs
`run_grammar_scan(project)` unconditionally over all 12 rows; `_select_requested` (line 160)
only filters the *already-produced* `checks_run`/`checks_skipped`/`findings` lists afterward.

A `checks=["representation-variant-product"]` caller gets zero protection from a crash in, say,
row 8's `_scan_unordered_rule_application_stratum_pair` — one bad row still takes the whole tool
down via `run_scan_module`'s failure path (`scan_result["success"]=False` ->
`_scan_failure_response`, a `runtime_error`), even though the caller never asked for that row.

**Is it worth addressing:** yes. This is exactly the shape of risk the pattern-audit gate exists
to catch generically (one row's LCM assumption breaks unrelated callers), and `checks` existing
at all implies callers use it to *avoid* a known-bad row — which today it cannot do.

**Recommended fix — per-row exception isolation, not push-down filtering:**

- Wrap each of the 12 `_scan_*(project)` calls inside `run_grammar_scan` in its own
  `try/except Exception`. On failure, append to `checks_skipped` instead of calling `_emit`,
  and skip that row's `checks_run` entry.
- Do **not** change `run_grammar_scan(project)`'s signature to accept `checks` and push
  filtering into the scan. That seam is fixed by T030's generated "module code", which calls it
  with exactly one positional argument (module docstring "Entry point" section, and
  `_select_requested`'s own docstring: "the seam's fixed 'module code' calls it with the project
  and nothing else"). Changing that is more invasive than the bug warrants and would touch
  `execution.py`'s script-builder too.
- Push-down filtering is a legitimate second-order improvement (it would let a caller *skip
  running* a row known to be slow or broken, not just isolate its crash) but should be scoped as
  separate follow-up work, not bundled into the crash fix.

**Contract-change flag (must not be silently absorbed):** `checks_skipped` entries today carry
exactly the fixed literal string `"lcm_name_unverified"` as `reason`, checked literally by
`tests/test_grammar_scan_checks.py`, and documented that way in
`contracts/flextools_grammar_health.md` and `data-model.md`'s cross-cutting rule 4. A
crash-isolated row needs a **new** reason string (e.g. `"check_raised_exception"`) — that is a
contract change, not a pure bugfix, and requires:

1. updating the contract doc's `checks_skipped` semantics section,
2. updating the literal-string test,
3. a decision on whether the exception's type/message is ever surfaced. Recommend: not in the
   finding itself — SPEC 9.5.3/9.5.7 forbid verdict wording, and an exception message could
   smuggle diagnostic or severity-flavored text in. If surfaced at all, put it behind a
   debug-only channel, not `checks_skipped[].reason`.

This isolation does **not** by itself violate 9.5.3/9.5.7 (no score/severity/verdict) —
`checks_skipped` already exists as a structural "this didn't run" signal with no ranking
implication — but the new reason string's wording must be reviewed under the same no-verdict
discipline the fixed one was.

**Recommendation:** implement per-row isolation plus the new `checks_skipped` reason as a small,
explicitly-labelled contract change (spec, contract and test updated together in the same PR);
defer push-down filtering.
