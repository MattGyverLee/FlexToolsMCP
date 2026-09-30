# Implementation Plan -- parser-check, CP1

**Spec:** [`SPEC.md`](./SPEC.md) | **Research:** [`research.md`](./research.md) |
**Data model:** [`data-model.md`](./data-model.md) | **Contracts:** [`contracts/`](./contracts/)

**Scope of this plan: CP1 only.** SPEC section 15 sequences six checkpoints; this
plan covers the first and stops at its boundary. CP2-CP6 get their own plans.

---

## Summary

CP1 makes the MCP able to say, before anything is parsed, whether each of the three
parser spines is actually reachable on this machine and this project -- and it ships
one substantial standalone deliverable, `flextools_grammar_health`, the pure-LCM
static scan for path-multiplying grammar properties. The detection work goes into a
new `src/flextoolsmcp/server/parser_probe.py` that `diagnostic_health.py` composes,
preserving that module's "no new detection logic" contract; `flextools_health` grows
a `parser` block, and four additive error codes join the `tool-responses/1.0`
contract.

The shape of the work is set by one fact about this codebase: **the MCP server
process never opens a FieldWorks project.** Every `OpenProject` lives in the script
text `execution.py` generates and runs in a subprocess. So CP1 splits cleanly in two
-- the ParserCore capability probe is reflection over a DLL and runs in-process,
while the grammar scan reads LCM objects and runs through the existing generated-module
harness. Nothing in CP1 constructs an `HCParser`, loads a grammar, or parses a word;
`HCParser` is touched by reflection only.

No new dependency is introduced. The probe uses `Assembly.LoadFile` exactly as
`versioning.py` and `liblcm_extractor.py` already do, and binds to the same
FieldWorks install through the existing `get_resolved_fieldworks_dir()`.

---

## Project Structure

```
src/flextoolsmcp/server/
  parser_probe.py                      # NEW -- all CP1 detection: same-install check,
                                       #   reflective member probe, hc + GenerateHCConfig
                                       #   discovery, HC-agent probe, check_active_parser
  versioning.py                        # UNCHANGED -- get_resolved_fieldworks_dir() reused as-is
  response_models.py                   # + 4 error detail models (extra="forbid")
  models.py                            # + GrammarHealthInput
  tool_definitions.py                  # + flextools_grammar_health (READ_ONLY_SAFE)
  dispatch.py                          # + TOOL_GRAMMAR_HEALTH, route, ALL_TOOL_NAMES
  handlers/
    diagnostic_health.py               # + _build_parser_block(), composition only
    grammar_health.py                  # NEW -- handler; composes the scan, never reads LCM
  scan/
    grammar_scan_module.py             # NEW -- the LCM checks, run in the subprocess

docs/TOOL-CONTRACT.md                  # + 4 code rows; "18 codes" -> 22
CHANGELOG.md                           # + "Tool contract" entry

tests/
  test_parser_probe.py                 # NEW -- probe unit tests (SPEC 16)
  test_parser_health_block.py          # NEW -- health parser block + agent-probe skip
  test_grammar_health.py               # NEW -- scan checks, no-score, no-parser assertions
```

**Structure Decision.** Detection logic lands in one new module, `parser_probe.py`,
imported by `diagnostic_health.py` the same way `versioning.py` and
`project_access.py` already are. This is SPEC 5.4's explicit instruction and it
protects a contract other code and tests rely on: `diagnostic_health.py`'s docstring
declares it "pure COMPOSITION of existing detectors -- it introduces no new detection
logic". The grammar scan is a separate concern with a separate execution model (D1),
so it gets its own handler plus a scan module the subprocess harness runs.

---

## Constitution Check

No `.specify/memory/constitution.md` exists in this project, so there is no formal
principle set to table. The project's binding rules come from `CLAUDE.md` and the
spec's own "Settled" and anti-requirement sections; CP1 is assessed against those.

| Principle (source) | Assessment |
|---|---|
| Object-centric, indexed API discovery; verify names against the index (`CLAUDE.md`) | **PASS** -- D4 verified every 9.5.4 row against the index before planning the checks; one row refuted rather than carried forward |
| Read-only by default; explicit confirmation for writes (`CLAUDE.md`) | **PASS** -- every CP1 deliverable is `READ_ONLY_SAFE`. CP1 writes nothing (SPEC 15: "Writes? No") |
| No emoji in console/terminal output (`CLAUDE.md`, SPEC H9) | **PASS** -- ASCII only; these strings get parsed |
| Never infer parseability from database state (SPEC 3.1, anti-requirement) | **PASS** -- the scan reads grammar objects (`IMoForm`, `IPhPhoneme`, `IMoInflAffixSlot`), never wordforms or analyses. Asserted by test, not just by intent |
| Never report the wrong engine's results as the project's (SPEC 3.2) | **PASS** -- `check_active_parser()` ships at CP1 and refuses with `parser_engine_mismatch`; fail-safe on a corrupt value, which reads as XAmple |
| No scalar health score; never rank by size or count (SPEC 9.5.3, ANTI-METRIC) | **PASS** -- D7; the response model offers no sortable severity field |
| A G4 finding names a suspect, never a defect (SPEC 9.5.7) | **PASS** -- enforced in the contract's wording rules and by test |
| Capability probe, never a version floor (SPEC 5.4) | **PASS** -- version is reported, never compared. Regression test included |
| CP1 boundary: no parser constructed, no grammar loaded, nothing parsed (SPEC 15) | **PASS** -- `HCParser` reached by reflection only; asserted by test |
| Additive contract changes stay at `tool-responses/1.0` (SPEC 14) | **PASS** -- four codes added, no existing key changed |

No violations, so no Complexity Tracking table.

**One item to carry to the maintainer, not a violation.** SPEC 10.2's HC-agent probe
is specified "with a project open", a state `flextools_health` can never reach under
this architecture (D2). The spec's own fallback -- `agent_probe: "skipped"`, never
reported as a pass -- is what CP1 implements, so CP1 is correct as specified; the
wording is just narrower than it reads. Re-check when CP2 makes the branch reachable.

---

## Phase 0 -- Research

Complete: [`research.md`](./research.md). Seven decisions, D1-D7. The two the rest of
the plan rests on are **D1** (the scan runs in the subprocess, because the server
process never opens a project) and **D4** (the 9.5.4 property names, one of which is
refuted).

---

## Phase 1 -- Design and contracts

- [`data-model.md`](./data-model.md) -- `ProbeResult`, `ParserDetector`'s return
  shape, the `parser` health block, and the grammar-scan finding.
- [`contracts/`](./contracts/) -- the `flextools_grammar_health` tool contract, the
  `flextools_health` parser-block contract, and the four error codes with their exact
  detail fields.

Every identifier in `contracts/` is copied verbatim from SPEC 10.2 and SPEC 14. The
closed enums in particular -- `signal`, `component`, `probe_source` -- are the
contract, and CP1 must not rename, recase or extend them.

---

## Work breakdown

Dependency-ordered. `tasks.md` (next step) expands these; the ordering constraint is
that the probe precedes its consumer, and the contract rows precede the code that
emits them.

1. **`parser_probe.py` -- same-install check + reflective member probe.** Reuses
   `get_resolved_fieldworks_dir()`. Positional binding only (D3). Load failure maps
   to `signal: load_failed`.
2. **`parser_probe.py` -- `hc` and `GenerateHCConfig.exe` discovery.** `hc` is a
   dotnet global tool on PATH / `dotnet tool list -g` (SPEC H1), **not**
   `%LOCALAPPDATA%\HermitCrabTool\hc.dll`. Needs a timeout on the `dotnet` call --
   SPEC open question 8 leaves the hang behavior unspecified, so this task specifies
   it: bounded, and a timeout reports the component as not found with the reason
   recorded, never blocks health.
3. **`parser_probe.py` -- `check_active_parser()` and the HC-agent probe.**
   Re-reads `ActiveParser` live on every call, never caches per session. The agent
   probe is a function here; health reports it `skipped` (D2).
4. **Four error detail models + `TOOL-CONTRACT.md` rows + CHANGELOG.** Before any
   handler emits them.
5. **`diagnostic_health.py` -- `_build_parser_block()`.** Composition only, matching
   `_build_fieldworks_block()`'s shape.
6. **Verify the three still-open LCM names** (D4: `IMoAffixProcess`,
   `IPhMetathesisRule`, `ILexEntry.AlternateFormsOS`) before writing rows 3, 5, 7.
7. **`grammar_scan_module.py` -- the 9.5.4 checks**, highest measured yield first,
   honoring `IPhSegmentRule.Disabled` throughout, and using row 8's *corrected*
   rule-side mapping.
8. **`grammar_health.py` handler + registration** in `models.py`,
   `tool_definitions.py`, `dispatch.py`.
9. **Tests** -- the SPEC 16 items scoped to CP1, listed below.

**Not in CP1, deliberately:** the flexicon facade and the two read gaps (CP2, D5),
the job runner, `try_word`, any `HCParser` construction, filing, and the ten SPEC 14
codes belonging to later checkpoints.

---

## Test obligations for CP1

Drawn from SPEC 16, restricted to what CP1 can honestly assert:

- ParserCore probe: foreign install yields `signal=foreign_install`; a missing bound
  member yields `signal=incompatible_surface` naming it in `missing_members`; an
  unexpected-but-complete version **passes and is reported** -- the regression test
  against reintroducing a version floor; the probe opens no cache and loads no
  grammar.
- HC agent: the `ActiveParser == "HC"` / no-agent fixture yields `write: unavailable`
  with `signal=parser_agent_missing` and **no `KeyNotFoundException` escapes**; the
  same fixture leaves `read: ready`; with no project open, `write.reason` records
  `agent_probe: "skipped"` and the member probe alone decides.
- Engine mismatch produces `parser_engine_mismatch`, never a parse. A corrupt
  `ParserParameters` value reads as XAmple and refuses.
- Grammar health: constructs no `HCParser` and runs no parse; a null allomorph
  reachable from any position is reported as a **suspect** with its count; **no
  scalar score appears anywhere** in the output.
- Parseability is never derived from analysis counts (SPEC 3.1).
- Integration (Windows + FieldWorks, no `hc` tool): sandbox spine reports
  unavailable with the real `dotnet tool install` hint while the in-process spines
  report ready.
