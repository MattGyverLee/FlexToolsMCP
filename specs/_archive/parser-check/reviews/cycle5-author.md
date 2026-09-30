# Original Author Review -- parser-check tasks.md, cycle 5

> **Provenance note.** Authored by `lex-author` in cycle 5. The agent has no write tool
> (Read/Grep/Glob only), so the main session persisted this body verbatim to the path
> the dispatch plan specified. Content is lex-author's, unedited.

## 1. CP1 boundary -- 7/10

Everywhere else in the task list the line holds: T009's docstring invariant (`ok=True`
implies no signal), T020's explicit refusal to call `check_active_parser()` or touch an
engine-specific object, T024/T025 confined to `parser_probe.py`, no task instantiates
`HCParser`. But **T026 as phrased is not falsifiable**. "Across every CP1 code path,
`HCParser` is never instantiated ... reflection only" names an unbounded quantifier over
paths with no stated verification mechanism. A single unit test cannot discharge "every
code path" claims by construction. Restate as two concrete, combinable checks: (a) a
static scan (grep/AST) over `src/flextoolsmcp/server/**`, excluding `parser_probe.py`'s
own `Assembly.LoadFile`/`GetMethods` reflection, asserting no literal `HCParser(`
construction call exists anywhere in CP1 source; (b) a dynamic check that runs the full
CP1 test suite with a spy/patch on the CLR construction point and asserts zero
invocations. Static alone misses a construction reached only via computed
strings/`getattr`; dynamic alone misses dead code the test suite never exercises.
Together they're falsifiable; "across every code path" alone is not.

## 2. Story split -- 8/10 (a) / 7/10 (b)

**(a)** Verified by file audit: T017 (`models.py`), T018 (`tool_definitions.py`), T019
(new `grammar_scan_module.py`), T020 (new `handlers/grammar_health.py`), T021
(`dispatch.py`) -- none overlap US1's `parser_probe.py`/`diagnostic_health.py` or US3's
`parser_probe.py`. The claim is correct and matches SPEC 9.5.5's own framing ("decoupled
from the sandbox spine entirely").

**(b)** Sound, given D2: the health handler *structurally* never opens a project, so US3
existing or not literally cannot change what the health block emits -- `agent_probe:
"skipped"` would be identical either way. The "misleading picture" risk is real but
architectural, not sequencing-induced, and it's disclosed rather than hidden (`skipped`
is an explicit, documented state, not a silent omission). One inconsistency worth naming:
`active_engine` rests on the *identical* premise (health never opens a project) but,
unlike `agent_probe`, got no research decision (no "D-note") arguing why it's
unconditionally `null` at CP1 -- T012 just asserts it. Same argument, asymmetric rigor.

## 3. US3 ships with no caller -- 7/10

Correct call: `try_word`/`parse_text`/`parse_sandbox` -- the only legitimate callers of
`check_active_parser` -- don't exist until CP2/CP4/CP5, and T020 is right to keep
`grammar_health` from calling it (it touches no engine-specific object). Shipping
tested-but-uncalled helpers now beats deferring both design and tests to CP2. No cheap
CP1 caller exists without inventing one that violates scope. The one thing worth flagging
upward (not a tasks.md defect): SPEC 15's CP1 row promises "HC-agent probe with
`parser_agent_missing` **refusal**", but nothing at CP1 actually refuses anything live --
only fixture-driven unit tests exercise the refusal in isolation. Tasks.md's own phase-5
goal text is honest about this ("deliberately not wired into a handler that does not
exist"), so the gap is in SPEC 15's wording, not in the task breakdown.

## 4. Intent preservation -- 6/10

No-version-floor (5.4): held -- T007's "unexpected-but-complete version passes and is
reported" is exactly the standing regression test SPEC demands. 3.2/12.7
refuse-rather-than-mislead: held verbatim in T022-T025, including the
read-spine-unaffected clause. 3.1 never-infer-from-database-state: held in T014/T026.

**T013's next_step degradation is the weak point.** The contract it inherits from
(`flextools_health-parser-block.md`) already says the two `flextools_try_word` rows
"degrade to external-action wording with `tool: null`" but never gives that replacement
wording. One of those two rows' *action text* ("use read-only Try A Word; filing
unavailable") names the nonexistent tool by name in prose -- nulling only the `tool` field
while leaving that sentence intact still proposes a tool that isn't there, which doesn't
actually satisfy 10.1's "never propose a tool that does not exist." T013 should spell out
the literal CP1 replacement string for that row, not just "tool: null."

## 5. Readability -- 6/10

T019 is the outlier: one paragraph carrying six rows' LCM predicates, the corrected row-8
rationale, the `cast_example` guidance, and the multistring-normalization reminder -- all
design decisions that already live (or belong) in `data-model.md`/the 9.5.4 table T027
corrects. Every other task is appropriately terse. Shrink T019 to "implement rows 1-10
per data-model.md's corrected 9.5.4 mapping" and move the rest there.

## Prioritized edits

1. Split T026 into a static scan + a dynamic spy-and-run-suite check; drop the
   unfalsifiable "every code path" framing.
2. Add a one-line rationale (research-style) for why `active_engine` is unconditionally
   `null` at CP1 -- same D2 argument, currently unrecorded.
3. Give T013 (or the contract it cites) the literal CP1 replacement action text for the
   "use read-only Try A Word" row, not just `tool: null`.
4. Shrink T019 to a pointer at `data-model.md`; move the corrected-row-8/`cast_example`/
   normalization detail out of the task line.
5. Flag SPEC 15's "refusal" wording to whoever owns SPEC.md -- CP1 ships the refusal
   *logic*, tested, not a live refusal path.
