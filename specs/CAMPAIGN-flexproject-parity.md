# CAMPAIGN -- FlexProject parity

Seven specs from one triage: `user-logs/Kendall/session_{112101,145439,154828}*.log`,
2026-09-09. One root cause, several independent failures it exposed.

## The root cause

FlexTools constructs the project object with **flexlibs**
(`flextoolslib/code/FTModules.py:75,24`). This MCP constructs it with
**flexicon** (`execution.py:3911,3939`). Modules using the flexicon facade
(`project.LexEntry.*`) or direct operations construction
(`LexEntryOperations(project)`) therefore pass here and fail there -- and our
own guidance told users that the flexicon *import* was what made this safe,
which is false. Four distinct broken modules across three sessions, every one
reported `[OK] Operation completed successfully`.

## The specs

| # | spec | repo | depends on |
|---|---|---|---|
| 1 | `flexicon-project-bridge` | flexicon | -- |
| 2 | `modifiesdb-parity` | FlexToolsMCP | -- |
| 3 | `write-authorization-audit` | FlexToolsMCP | -- |
| 4 | `portability-preflight` | FlexToolsMCP | 1 |
| 5 | `flexicon-guidance-correction` | FlexToolsMCP | 1 |
| 6 | `vanilla-flextools-parity` | FlexToolsMCP | 1, 4 |
| 7 | `broken-script-migration` | FlexToolsMCP | 1, 4, 6 |

## Suggested order

**2 and 3 first** -- both standalone, neither waits on flexicon, and 3 is the
one that closes a live safety hole: a destructive write executed with no
record of whether a human authorised it.

**Then 1**, which is the load-bearing fix. Its CP3/T3.2 is the one question
this triage could not settle by reading -- whether a Phase 1 transaction inside
the flexlibs non-undoable envelope commits on the host save. If it does not,
spec 1 section 3a is wrong and needs rework before anything downstream lands.

**Then 4 and 5** together; 5 is a docs sweep that 4 makes self-enforcing
(`flexicon-guidance-correction` CP2 reuses 4's detector to test the
documentation).

**Then 6**, which is the empirical check on all of it, and **7** last, since
migration is only trustworthy once 6 can prove a migrated module runs under the
real host.

## Verified evidence

- `specs/vanilla-flextools-parity/evidence/corpus/` -- all 10 distinct modules
  from the logs, byte-exact (each reproduces its logged `sha256` prefix and
  byte count), plus `MANIFEST.json` and `regenerate.py --check`. Stored as
  `*.py.txt` because a formatter here strips trailing whitespace from `*.py`,
  which two of the modules contain and which the fingerprints include.
- The flexlibs/flexicon contract gap: 57 distinct project attributes over 1011
  call sites; 15 attrs / 841 sites satisfied by a flexlibs donor, 42 attrs /
  170 sites not, 14 of them whole sub-facades. Recomputable; see spec 1
  section 1.
- The confirmation-gate bypass: the verbatim logged code from 154828 op#3 run
  through the real detector yields `is_mutating_script: True` and two
  mutations, identical to 145439 op#3 which *was* gated. See spec 3 section 1.

## What is NOT in these specs

- Renaming `flexicon.FLExProject` to `FlexiconProject`. Considered and
  rejected -- flexicon reaches the flexlibs private `__WSHandle` by its mangled
  name in 51 places, which works only because both classes share the name.
  Reasoning preserved in spec 1 section 1 so it does not get relitigated.
- Patching `flextoolslib` or `flexlibs`. Upstream (cdfarrow); we mirror where
  needed and document the delta (spec 6 section 3b).
- Fixing the logic bugs in the user modules (double `Delete` in a loop, the
  wrong `ILexEntry(c)` cast, dropped variant type). Reported by spec 7, never
  auto-applied.
