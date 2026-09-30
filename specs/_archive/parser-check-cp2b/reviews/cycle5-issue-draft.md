# Issue draft (cycle 5) -- DRAFT -- NOT FILED. Requires user approval.

## Title
`_as_text` crashes the parse worker on a null-byte or ~5000-char wordform (XML-writer ArgumentException / OutOfMemoryException)

## Reproduction
- Project: `IndonesianHC-Complete` (HC, 41 entries), read-only worker (`writeEnabled=False`).
- Inputs: (1) a wordform containing a NUL byte (`\x00`); (2) a wordform ~5000 characters long.
- Both submitted via `flextools_try_word` at `level="explain"` (or `"restricted"`), which calls `TraceWordXml`.
- Observed: the trace object builds successfully, but converting it to text in
  `_as_text` (`worker_main.py`, via `str(trace)`) throws:
  - NUL byte -> `ArgumentException` from the underlying XML writer (NUL is illegal in XML text).
  - ~5000-char word -> `OutOfMemoryException` while serializing.
- Found live during cycle-4 verification of Delta 6
  (`specs/parser-check-cp2b/reviews/cycle4-verification.md`, "New finding, out of this cycle's scope").

## Code path
- `src/flextoolsmcp/server/parse/worker_main.py`, `_as_text` (~line 761), called from `parse()` at lines 750/754 for `restricted`/`explain` levels.
- No length or content guard exists anywhere upstream: `TryWordInput.word`
  (`src/flextoolsmcp/server/models.py:718-720`) is a bare `str = Field(description=...)`
  with no `min_length`/`max_length`/pattern/validator, and
  `handle_flextools_try_word` (`src/flextoolsmcp/server/handlers/parse.py:361+`)
  passes `word` straight through unchecked. This is an **absent** guard, not
  an existing-but-too-permissive one.

## Why this is not a Delta 6 regression
Delta 6 (this checkpoint) touched only `_summarize_trace`, which reads the
trace's `XDocument` structure directly and runs **before** `_as_text` is
called. The crash is in `_as_text`'s later `str(trace)` call, a separate,
pre-existing code path `_summarize_trace` never reaches. Cycle-4 confirmed
`_summarize_trace` handles the same malformed-phoneme case correctly (step
7, PASS); this defect is orthogonal to that fix.

## Severity
Not yet known whether the exception is caught by the worker's existing
request-level handling (`_report_exception`, `_parse_one`) and returned as
a failed request, or escapes and kills the worker process. If it kills the
worker, every in-flight/queued request for that project is lost and the
grammar must reload -- **P1**. If only the single request fails, it's an
unguarded-input gap -- **P2/P3**. Needs a live check (submit both inputs,
watch whether the worker process survives) before triage sets severity.

Source reading suggests the worse case, and the same open question now
also covers the sibling transport defect
(`cycle6-issue-draft-transport.md`): `worker_client.py`'s `_read_message`
(lines 256-274) catches only `json.JSONDecodeError` around the
`readline()`/`json.loads()` pair. A `ValueError` raised elsewhere in that
window -- e.g. from a malformed/oversized decode -- is not a
`JSONDecodeError` subclass in every raise site and would escape uncaught
into `_read_loop`, which has no surrounding try/except of its own. That
reads as "kills the worker," not "fails the request," pending confirmation.

### Live-check answer (PLACEHOLDER -- fill in this cycle)
- [ ] NUL-byte input: worker survives / worker dies (strike one)
- [ ] ~5000-char input: worker survives / worker dies (strike one)
- [ ] Resulting severity: P1 / P2 / P3 (strike two)
- [ ] Evidence: `<link to this cycle's live-verification log/report>`

## Suggested fix direction
1. **Input validation at the boundary** (`TryWordInput.word`, models.py):
   reject NUL bytes and cap length before the request reaches the worker.
   Cheapest; avoids paying for a parse on input that can't yield a trace.
2. **Defensive handling in `_as_text`**: catch the CLR exceptions there and
   degrade to a structured error, protecting any other caller that reaches
   `TraceWordXml` with bad input.
Recommend (1) as primary, (2) as defense in depth given the worker-crash risk.

## No duplicate found
Searched `MattGyverLee/FlexToolsMCP` issues (open+closed) for: "null byte",
"malformed word", "OutOfMemoryException", "_as_text", "wordform
validation", "ArgumentException", "worker crash", "5000 char", "worker",
"try_word", "input validation", "long word", "crash". No existing issue
covers malformed or oversized wordform input to `flextools_try_word` /
`_as_text`. Nearest hits (unrelated): #164 (api_mode inert), #94
(AddPicture NullReferenceException), #113 (LibLCM template crash).
