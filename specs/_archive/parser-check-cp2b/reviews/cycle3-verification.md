# Live verification -- cycle 3, `_summarize_trace` XName binding

**Project used:** `IndonesianHC-Complete` (HC, 41 entries), already present
at `C:\ProgramData\SIL\FieldWorks\Projects\IndonesianHC-Complete`. Read-only
throughout: worker opened `writeEnabled=False`; no module run, nothing written.

## Step results

**Step 2 -- explain on a parsing word (`pukul`): FAIL.**
Raised before returning any `analysis_count`: `status: error`,
`error_code: runtime_error`, `message: "TypeError: No method matches given
arguments for XContainer.Element: (<class 'str'>)"`. No non-zero count was
ever produced -- the call never completed.

**Step 3 -- explain on a non-parsing word (`meŋ`): FAIL, same defect.**
Identical `TypeError`/`runtime_error`. Could not observe `parsed`,
`analysis_count`, or the assist/guidance path at `explain` -- the call dies
before any response body is built. (The unrelated `plain`-level failing-word
test, which does not call `_summarize_trace`, passed independently, isolating
the defect to trace-summarizing code.)

**Step 4 -- restricted, resolvable decomposition (`pukul`): FAIL, same defect.**
Same `TypeError`. `hypothesis_held`/`restricted_analysis_count` never
appeared.

**Step 5 -- cross-check plain vs. explain `analysis_count`: BLOCKED.**
`plain` returned `analysis_count: 1` for `pukul` (cold and warm). `explain`
never returned any count -- it raised every time. The claim under test
(`<Analysis>` count == `ParseResult.Analyses.Count`) could not be checked;
the code that would compute it never runs to completion.

**Step 6 -- XName string binding: RAISED, every time, unconditionally.**
Captured from the worker's own stderr (full traceback via `_report_exception`):

```
System.ArgumentException: 'str' value cannot be converted to System.Xml.Linq.XName
  in method System.Xml.Linq.XElement Element(System.Xml.Linq.XName)
Traceback (most recent call last):
  File ".../worker_main.py", line 1272, in _parse_one
    outcome = self._backend.parse(...)
  File ".../worker_main.py", line 754, in parse
    return {"parse": _summarize_trace(trace), ...}
  File ".../worker_main.py", line 852, in _summarize_trace
    error_element = root.Element("Error")
TypeError: No method matches given arguments for XContainer.Element: (<class 'str'>)
```

pythonnet does **not** apply implicit `str -> XName` conversion for this
overload in this environment. The very first XName call (`root.Element
("Error")`) fails -- `root.Elements("Analysis")` is never reached, on any
input. Reproduced identically on every `explain`/`restricted` call made,
against both a parsing and a non-parsing word.

**Step 7 -- inducing an `<Error>` document: NOT REACHABLE FROM HERE.**
Every call fails at `root.Element("Error")` regardless of the trace's actual
content -- the crash precedes any inspection. Cannot be tested; stated
plainly rather than contrived.

## Mock suite (regression, supplementary)
Command: `python -m pytest -m "not requires_flex" --continue-on-collection-errors -q`
Result: 2016 passed, 6 skipped, 71 deselected, 0 failed -- matches cycle 2's
reported baseline exactly. No pre-existing failures.

## VERDICT: FAIL

`_summarize_trace`'s XName string-conversion assumption does not hold live.
Every `explain`/`restricted` call raises `TypeError` and fails the whole
parse, exactly as the briefing warned. `plain` is unaffected (uses
`_summarize_plain`, verified `analysis_count: 1` for `pukul`, live). The
shipped claim -- `explain`/`restricted` deriving counts from the trace -- is
false in this environment: both levels return only `runtime_error`. This is
a live-verified regression in the two levels the change specifically
targeted.

Fix needed: bind `root.Element("Error")` / `root.Elements("Analysis")`
through an explicit `XName` (e.g. `from System.Xml.Linq import XName;
XName.Get("Error")`) rather than relying on implicit string conversion,
which this pythonnet build does not perform for this overload.
