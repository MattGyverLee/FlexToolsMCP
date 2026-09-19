# Tier A3 -- the live evidence, against real projects with a real grammar

**Tasks**: T018 (A3.1/A3.2/A3.4/A3.6), T019 (A3.3, the gate), T020 (A3.5), T021 (this transcript).
**Status: GREEN, and it caught a wrong-answer defect.**
**Hard gate 2 (A3.3): PASSED.** CP2b is released on this evidence.

## Exact invocation

Quoted verbatim from `tasks.md`. Working directory is the flexicon
repository root:

```
$env:FLEXLIBS_REQUIRE_LIVE = "1"; python -m pytest tests/operations/test_parser_live.py -m requires_live_project -q
```

## Run mode -- confirmed live, not degraded

`FLEXLIBS_REQUIRE_LIVE=1` turns silent mock degradation into a usage error,
so a run that quietly fell back to mocks cannot be mistaken for live
evidence. Checked before anything below was recorded:

```
tests/live_status.json  ->  "run_mode": "live"
```

**A mock fallback would have been a FAIL, not a pass.** It did not occur.

## Tree state

| | |
|---|---|
| Repository | `D:\Github\_Projects\_LEX\flexicon` |
| Branch | `feat/parser-check-cp2` |
| Test file | `tests/operations/test_parser_live.py` (new at T018-T020) |
| Primary project | `IndonesianHC-Complete` -- 41 entries, 3 phonological rules, engine HC |
| Secondary project | `Malay Parsing-20230810withHC` -- engine HC |
| Component | `ParserCore.dll` 9.3.10, `C:\Program Files\SIL\FieldWorks 9` |
| Date | 2026-09-19 |

Both projects were opened **in place, with `writeEnabled=False`**. Nothing was
written and nothing needed restoring, which is what made the tier safe to
run unattended. Neither is a `.fwbackup` sandbox -- opening one read-only
triggers a modal liblcm dialog that freezes the suite.

## Result

```
17 passed in 6.18s
```

**Zero failures, zero skips.** Every assertion in the tier executed against a
real grammar.

Full offline suite after the tier's fixes: **1920 passed, 0 failed**.

| Group | Covers | Outcome |
|---|---|---|
| `TestA31ConstructsAndLoads` (2) | A3.1 -- real cache, real grammar | pass |
| `TestA32ParseAndTrace` (5) | A3.2 -- parse and trace round trips | pass |
| `TestA34ObjectIdentityIsPreserved` (1) | **A3.4 -- FR-010 object identity** | pass |
| `TestA36ExpectedEngine` (2) | A3.6 -- engine HC on both projects | pass |
| `TestA33ReloadDiscardsUnconditionally` (3) | **A3.3 -- THE GATE** | pass |
| `TestA35OneGrammarHeldAndCurrencyConfirmed` (4) | A3.5 -- SC-014, SC-015 | pass |

---

## A3.3 -- the gate, and which witness produced the result

**Witness used: the morpher-identity read (D-A11). The documented fallback
was not needed.**

`HCParser.LoadParser()` replaces the private `m_morpher` instance, so the
identity of that instance across two calls is a direct witness of whether the
grammar was actually reloaded. The field was reflected out of the real
component first, rather than assumed:

```
m_cache :: LcmCache          m_morpher :: Morpher
m_language :: Language       m_traceManager :: FwXmlTraceManager
m_outputDirectory :: String  m_changeListener :: ParserModelChangeListener
m_forceUpdate :: Boolean     m_guessRoots :: Boolean
m_mergeAnalyses :: Boolean
```

Identity is compared with `RuntimeHelpers.GetHashCode`, which is reference
identity -- two distinct `Morpher` objects built from the same model would
compare equal under any value-based comparison.

Both halves of the claim were observed under **identical conditions, with no
model change between them**:

| Call | Morpher replaced? | Meaning |
|---|---|---|
| bare `Update()` | **no** | short-circuited; nothing discarded |
| `Reload()` (reset, then update) | **yes** | the grammar was discarded |

This is the whole of D-A5, verified rather than argued. `HCParser.Update()` is
guarded by `if (m_changeListener.Reset() || m_forceUpdate) LoadParser();`, so
with nothing changed it does nothing -- and a `Reload()` bound to a bare
update would have returned having discarded nothing while the caller believed
otherwise. That is the `RollbackToMark` shape Principle I exists to prevent.

**The first row matters as much as the second.** It is the control: had the
bare update also reloaded, D-A5's premise would have been wrong and the
two-step reload should have been revisited rather than kept out of habit. It
did not.

**Why not elapsed time.** Timing is a correlation, not a witness. A small
grammar on a warm cache reloads fast enough that any threshold either passes
a no-op or fails a real reload depending on the machine. The documented
fallback -- the rewrite of `{ProjectName}HCLoadErrors.xml`, which CP1 already
treats as the load signal -- is implemented in the test and used only if the
field read fails. It did not fail. Had **neither** witness been available the
test would have FAILED, not skipped: an absent witness is absent evidence.

---

## What this tier CAUGHT: a silent wrong-answer defect in the facade

This is the part of the tier that justifies it existing. **Tier A1 was green,
all four structural ratchets were green, and the facade was still returning
wrong answers.**

### The symptom

A3.4 skipped on its first run: the probe word produced no analyses. Chasing
that produced a reproducible sequence on `IndonesianHC-Complete`:

```
baseline                          ParseWord -> 1 analysis
after TraceWordXml(word, [])      ParseWord -> 0 analyses
parse again                       ParseWord -> 0 analyses     (persistent)
after ParseWordXml(word)          ParseWord -> 1 analysis     (recovered)
```

No exception. No warning. Just a word that used to parse and now does not.

### The cause -- read out of the component's source, not guessed

`ParserCore/HCParser.cs`, `ParseToXml(form, tracing, selectTraceMorphs)`:

```csharp
if (selectTraceMorphs != null) { /* narrow LexEntrySelector / RuleSelector */ }
else { m_morpher.LexEntrySelector = entry => true;
       m_morpher.RuleSelector     = rule  => true; }
```

Three facts follow, and together they are the defect:

1. The selectors are set at the **start of every `ParseToXml` call** and
   **outlive it**.
2. Plain `ParseWord` calls the morpher directly and **never touches them**.
3. The branch is on `!= null`. So **null means "no restriction" and an EMPTY
   sequence means "admit nothing"** -- the two are near-opposites.

The facade's `_AsIdentifierSequence` was converting `analyses=None` into an
**empty** `Int32[]`. Every "unrestricted" trace was therefore restricting the
parser to nothing, and leaving it that way for every later plain parse.

**This was the facade's bug, not the component's.** It is precisely the
failure Principle I names: a parameter's semantics were assumed rather than
verified. Tier A2 confirmed `TraceWordXml(string, IEnumerable<int>)` exists;
existence was never the question, and no amount of reflection would have
surfaced it. Only running it against a real grammar did.

### The fix

- `analyses=None` now passes **null**, which is what the component reads as
  "no restriction".
- An **empty** sequence is **refused** with `FP_ParameterError` naming why,
  rather than silently widened to an unrestricted search. Restricting to no
  analyses can only return nothing, so it is a caller error; quietly
  reinterpreting it would answer a different question than the one asked.
- A **non-empty** restriction still narrows the component and still outlives
  the call, so the facade now records that and **undoes it before the next
  plain parse**, through the component's own reset path. The cost is one
  extra parse, paid only when a restricted trace is actually followed by a
  plain parse -- never on the common unrestricted route.

### Pinned so it cannot come back

- `tests/operations/test_parser_live.py::TestA32ParseAndTrace::test_a_restricted_trace_does_not_truncate_the_next_plain_parse`
  -- the live regression pin: parse, restricted trace, parse again, assert
  the count is unchanged.
- `...::test_an_empty_restriction_is_refused` -- live.
- `tests/test_parser_offline.py::...::test_an_empty_analysis_restriction_is_refused`
  -- and asserts the refusal happens **before** the component is called, so
  a rejected request never installs the restriction anyway.
- `...::test_an_unrestricted_trace_passes_null_not_an_empty_sequence` --
  offline, asserts null reaches the component. A machine with no parser
  still catches a regression here.

---

## A3.4 -- FR-010, object identity

Now runs rather than skipping, and passes. A plain-parse analysis carries a
live `Form` reference exposing `Hvo` -- a real data-model object, not a
string rendering. That is the whole of FR-010: a caller can go from a parse
back to the entry that produced it without a lookup.

**Why it skipped at first, and what that revealed about the data.**
`IndonesianHC-Complete` stores lexeme forms in **IPA, not orthography**, so
the orthographic probe word matched nothing. The probe word is now the form
the project actually uses, written as a `\u0251` escape so the test file
stays pure ASCII. Chosen by enumerating all 41 entries and parsing each:
**all 41 parse, each with exactly one analysis**, so it is representative
rather than a lucky pick.

---

## A3.5 -- SC-014 and SC-015

- **One grammar per area.** Repeated parses reuse one handle; a second parse
  does not build a second parser.
- **A project switch releases the previous grammar.** Tested two ways: two
  areas on two projects each holding a handle bound to their own cache and
  never each other's, and -- the stronger one -- a single area re-pointed at
  the second project's cache, which must produce a new handle and drop the
  old one rather than serve the new project from the old project's grammar.
- **Currency is confirmed before every reuse.** The held parser's currency
  read is wrapped and counted across three parses by three different routes
  (`ParseWord`, `ParseWordXml`, `TraceWordXml`): **3 parses, 3
  confirmations**. A cached answer or an exempt route would show up here as
  a count that does not match. SC-015 is "0 parses served from a grammar
  whose currency was not confirmed immediately before reuse", and a count is
  how that is made checkable rather than asserted in the abstract.

## A3.6 -- engine

Both projects report `ActiveParser == "HC"`, read off
`MorphologicalDataOA` exactly as the shipped MCP-side check reads it.
Recorded because **this evidence speaks only for HermitCrab**: a project
configured for XAmple exercises a different component and nothing here
transfers to it. Sena 3 is XAmple with 0 phonological rules and was ruled
out as a verification target for that reason.

## Tiers not run, and why

**Tier A4 -- the live half of FR-043's stale branch -- was NOT run.**
Making a grammar stale on purpose requires changing the model, which is a
write. CP2a is read-only throughout, so Principle II defers it to CP2b with
`needs_human` (escalation E-D). What A3.3 proves is that `Reload()` discards
unconditionally; what remains unproven live is the *automatic* reload path
firing when the model genuinely changes underneath a held grammar. That path
is covered offline, against a stubbed currency read, by A1.6.

## Next

Tiers A1, A2 and A3 are all green and the two hard gates are passed, so the
CAPABILITIES token (T022) and the release cut are released.
