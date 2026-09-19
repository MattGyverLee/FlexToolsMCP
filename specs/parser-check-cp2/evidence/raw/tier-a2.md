# Tier A2 -- reflective verification of the installed parser surface

**Tasks**: T003 (write and run tier A2), T004 (this transcript).
**Phase 2, Foundational.** Constitution Principle I (NON-NEGOTIABLE).
**Gate status: PASSED.** Phase 3's facade tasks are released.

## Exact invocation

Working directory at the flexicon repository root:

```
python -m pytest tests/test_parser_reflective.py -m "not requires_live_project" -v
```

The file is also collected by the full `python -m pytest -m "not
requires_live_project" -q` invocation from `tasks.md`; it carries no marker
because it opens no project.

## Tree state

| | |
|---|---|
| Repository | `D:\Github\_Projects\_LEX\flexicon` |
| Branch | `feat/parser-check-cp2` |
| Test file | `tests/test_parser_reflective.py` (new at T003) |
| Component under test | `C:\Program Files\SIL\FieldWorks 9\ParserCore.dll` |
| Assembly version | **9.3.10.0** |
| Python / pytest | 3.12.7 / 9.0.2 |
| Date | 2026-09-19 |

**No LcmCache was constructed, no project was opened, no grammar was loaded and
no word was parsed.** The tier is `Assembly.LoadFile` plus
`GetConstructors`/`GetMethods`. There is therefore no write risk of any kind and
nothing to restore -- which is what lets it run unattended.

## Result

```
11 passed in 1.23s
```

| Assertion | Covers | Outcome |
|---|---|---|
| `TestA21BoundMemberSurface` (2) | A2.1 -- every member the facade binds exists | pass |
| `TestA22ResetAndCurrency` (5) | **A2.2 -- reset + currency, specifically** | pass |
| `TestA23SameInstallation` (2) | A2.3 -- directory equality (FR-004) | pass |
| `TestA24VersionReadNeverCompared` (2) | A2.4 -- version read and unused (FR-006) | pass |

## Observed member list

Reflected with `BindingFlags.Public | Instance | DeclaredOnly`. This is the
complete declared instance surface of both types, not an excerpt:

**`HCParser` (class)**

```
ctor  HCParser(LcmCache)
bool         IsUpToDate()
ParseResult  ParseWord(string)
XDocument    ParseWordXml(string)
void         Reset()
XDocument    TraceWordXml(string, IEnumerable<int>)
void         Update()
void         WriteDataIssues(XElement)
```

**`IParser` (interface)**

```
bool         IsUpToDate()
ParseResult  ParseWord(string)
XDocument    ParseWordXml(string)
void         Reset()
XDocument    TraceWordXml(string, IEnumerable<int>)
void         Update()
```

`WriteDataIssues(XElement)` is present on the concrete class only and is **not**
bound by CP2a.

## The gate: A2.2

**`Reset()` and `IsUpToDate()` both exist, and this is their first verification
anywhere in either repository.**

The task list made this a halt-or-proceed gate for a reason. `HCParser.Update()`
is itself conditional --

```csharp
if (m_changeListener.Reset() || m_forceUpdate) LoadParser();
```

-- so FR-043's reload is specified as **reset-then-update, two steps** (D-A5),
mirroring FieldWorks' own `ParserWorker.ReloadGrammarAndLexicon()`. Had `Reset`
been absent, the facade could not have been built as designed and CP2a would
have returned to research rather than binding a reload that silently
short-circuits. It is present, `void`, and on the interface.

Three findings beyond the bare existence check, each of which the facade depends
on:

1. **`IsUpToDate()` returns `bool` and takes no arguments.** FR-043's "currency
   confirmed before reuse" can therefore be answered by *asking the parser*,
   which is what the spec requires -- never from a local flag the facade
   maintains.
2. **`Reset()` returns `void`, not `bool`.** It is the discard, not a query. The
   two-step reload cannot be collapsed into a single call that reports what it
   did; T019/A3.3 must witness the discard some other way.
3. **Both members are on `IParser`, not just on the concrete `HCParser`.** The
   facade binds through the interface, so a member that existed only on the
   concrete type would not have been safe to bind. Both are interface-level.

## A2.3 -- and the limit of what it proves

`ParserCore.dll` and `SIL.LCModel.dll` both resolve from
`C:\Program Files\SIL\FieldWorks 9`, so directory equality holds on this machine.

Recorded explicitly, because T010's docstring must say the same thing
(Principle V): **directory equality does not verify provenance.** A foreign
`ParserCore.dll` copied into the correct directory passes this check. FR-004's
test is directory equality and nothing more, and the `reason` string the facade
produces must state what was checked and no more than that.

## A2.4

The assembly version reads as `9.3.10`. It is reported here and used in no
decision: nothing in this tier's pass/fail outcome depends on its value. The
*standing* control for FR-006 -- "no code path compares a detected parser
version against a minimum, 0 occurrences" -- is T006/A1.2 in
`tests/test_parser_structure.py`, which scans by AST. This file pins only the
local claim.

## Relationship to the shipped MCP-side check (D-02, E3, SC-016)

`src/flextoolsmcp/server/parser_probe.py` is untouched by CP2a and stays that
way (FR-041; T029 asserts a zero-line diff). The two member lists **diverge in
both directions, deliberately**:

| | this A2 tier | `parser_probe.HCPARSER_MEMBERS` |
|---|---|---|
| `HCParser(LcmCache)`, `Update()`, `ParseWord`, `ParseWordXml`, `TraceWordXml` | required | required |
| `Reset()`, `IsUpToDate()` | **required** | absent |
| `ParseFiler.ProcessParse` | not bound | required (write spine) |

Each check probes what its own surface binds. Neither is a superset of the
other, and neither should be reconciled into the other.

## Next

Phase 2 is complete and Phase 3's facade tasks (T010-T012) are unblocked on this
gate. They remain blocked on their own Wave-2 predecessors per the task list's
dependency table.
