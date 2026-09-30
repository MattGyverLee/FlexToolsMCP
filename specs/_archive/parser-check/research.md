# Research -- parser-check, CP1

Phase 0 for [`plan.md`](./plan.md). Scope is **CP1 only**: preflight/health for
all three spines, the two refusals, and `flextools_grammar_health`. Decisions
that CP2+ inherits are marked as such.

Everything in [SPEC.md](./SPEC.md) section 2 ("Settled -- do not revisit") and the
cycle-4 carry-forward in `.crew-handoff.json` is an input here, not a question.
This file records only what the spec left genuinely open.

---

## D1. Where `flextools_grammar_health` executes

**Decision.** `flextools_grammar_health` runs its LCM scan **in the generated-module
subprocess**, through the existing `execution.py` harness, not in the MCP server
process.

**Rationale.** The MCP server process never opens a FieldWorks project, and this is
structural rather than incidental. Every `OpenProject` call in the codebase lives in
the *script text* `execution.py` builds (`execution.py:3946`) and hands to
`run_script_async` (`subprocess_helpers.py:57`); the server process itself touches
FieldWorks only through filesystem checks (`versioning.py:178` `locate_liblcm_dll`)
and `Assembly.LoadFile` reflection (`versioning.py:262`). `probe_project_access()` is
documented as "filesystem + stdlib only, never opens the project", and
`session_state` holds a project *name*, never a handle.

That boundary is load-bearing for lock safety: `run_script_async` kills the whole
process tree on timeout (`subprocess_helpers.py:112`) specifically so a wedged
pythonnet child cannot hold the `.fwdata` lock open. Opening a project in the server
process would put an unkillable lock holder in the one process that outlives every
operation, and defeat it.

**Alternatives considered.**

- *Open an `LcmCache` in the server process for the scan.* Rejected: introduces the
  first in-process `.fwdata` lock holder, and would need its own lifecycle and
  lock-release policy.
- *A third execution path just for read-only scans.* Rejected: a second harness to
  keep in sync with the validator/preflight chain, for no capability the existing
  one lacks.

**Consequence for the plan.** The scan's checks are authored as a module the harness
runs, so they are covered by the existing preflight/casting validators. The handler
composes and interprets; it does not read LCM itself.

---

## D2. `flextools_health`'s parser block never opens a project

**Decision.** In `flextools_health`, the HC-agent probe of SPEC 12.7 always reports
`agent_probe: "skipped"`. The probe *itself* ships at CP1 as a reusable function in
`parser_probe.py`, called from the spine-executing paths (which already run in the
subprocess), not from the health handler.

**Rationale.** SPEC 10.2 conditions the agent probe on "with a project open", and per
D1 nothing is ever open in the health handler's process. `diagnostic_health.py`'s
module contract is explicit -- "pure COMPOSITION of existing detectors -- it
introduces no new detection logic" -- and `handle_flextools_health`'s docstring
promises "never opens a FieldWorks project". Spawning a project-opening subprocess
from a diagnostic snapshot would break both, and would turn a fast read-only call
into a multi-second one that acquires a project lock.

The spec already anticipates this state and rules it safe: *"when health runs
session-independent it is **skipped, not failed**: `write` status stays driven by the
member probe alone ... A skipped probe is never reported as a pass."* So the
architecture and the spec agree; what CP1 must not do is let `skipped` read as
`ready`.

**This is a spec-wording friction point, not a spec gap.** 10.2's "with a project
open" branch is unreachable from `flextools_health` under the current architecture.
It becomes reachable at CP2+, where `try_word` / `parse_text` run in the subprocess
with a project genuinely open. Flagged for the maintainer; no spec change is required
for CP1 to be correct.

**Alternatives considered.**

- *Have health spawn the subprocess when a session project is set.* Rejected: breaks
  the no-side-effects contract and the `diagnostic_health` composition rule.
- *Report `write: unavailable` when the probe cannot run.* Rejected: that reports a
  skipped probe as a failure, the mirror of the error the spec's own test forbids.

---

## D3. The ParserCore capability probe runs in-process

**Decision.** The same-install check and the reflective member probe run **in the MCP
server process**, in the new `parser_probe.py`.

**Rationale.** SPEC 5.4 requires the probe to never open an `LcmCache`, load a
grammar, or parse a word, which places it inside CP1's boundary and outside the
subprocess's reason for existing. Mechanically it is a pattern already in the tree:
`Assembly.LoadFile` plus member inspection, exactly as `versioning.py:262` reads the
LCM version and `liblcm_extractor.py:332` enumerates members. It reuses
`get_resolved_fieldworks_dir()` (`versioning.py:204`), which already exists and whose
docstring names "a future parser probe that must bind to the same install" as its
reason for being a shared accessor.

CP1 therefore has a clean two-process split: **reflection in-process, LCM reads in
the subprocess.** They share nothing but `parser_probe.py`'s pure functions.

**Cost gate.** A CLR load runs static initializers and resolves manifest
dependencies, so it is heavier than a file check. Per SPEC 5.4 it is gated behind
`verbose=True` or memoized at the call site. Call-site memoization is chosen:
`flextools_health` already recomputes detection per call by design, and a
module-level cache in `parser_probe.py` would need an invalidation policy that
`versioning.py` deliberately avoids. A load that throws before any member is
inspected maps to `parser_core_missing` with `signal: load_failed`.

**Binding is positional, never by keyword.** SPEC 5.4: `IParser` names these
parameters `word` while `HCParser` implements them as `form`, so keyword binding
through pythonnet breaks on the interface/impl mismatch.

---

## D4. Plan-time research task (a): the 9.5.4 LCM property names

The handoff required these verified before any 9.5.4 row is written. Checked against
this project's own index via `flextools_get_object_api`. **Row 8's mapping is wrong
as written.**

| Row | Pathology | Spec's proposed mapping | Verdict |
|---|---|---|---|
| 1 | Zero-surface morph in repeatable position | `IMoForm` form empty / boundary-only | **VERIFIED** -- `IMoForm.Form` is `IMultiUnicode`. Repeatable position resolves via row 10 |
| 2 | Representation-variant product | `IPhPhoneme.CodesOS` | verified previously |
| 3 | Epenthesis / metathesis | `IPhRegularRule` with empty structural description | **VERIFIED** -- `StrucDescOS` (ordered, inherited from `IPhSegmentRule`); empty = epenthesis. RHS is `RightHandSidesOS` |
| 4 | Unbounded quantifier | `IPhIterationContext.Maximum == -1` | verified previously |
| 5 | Morph x phon rule product | affix-process count x (`IPhRegularRule` + `IPhMetathesisRule`) | **PARTIAL** -- `IPhRegularRule` confirmed; `IMoAffixProcess` and `IPhMetathesisRule` not yet confirmed as index types |
| 6 | Partial morphemes | entries / affix rules lacking category or template | **VERIFIED, better predicate found** -- `IMoForm.IsComplete` (Boolean) already exists; use it rather than reimplementing "lacking category". Mirrors 9.3.1's use of `IWfiMorphBundle.IsComplete` |
| 7 | Multiple allomorphs; stem-name restriction | `ILexEntry.AlternateFormsOS.Count > 1`; `IMoStemAllomorph.StemNameRA != null` | **PARTIAL** -- `StemNameRA` VERIFIED (single referenced object); `AlternateFormsOS` not yet confirmed |
| 8 | Unordered rule application; derivation depth | "rule ordering within `IMoStratum`" | **REFUTED** -- see below |
| 9 | Identical feature bundles | `IPhPhoneme.FeaturesOA` | verified previously |
| 10 | Optional template slots | independent apply/skip across `IMoInflAffixSlot`s | **VERIFIED** -- `IMoInflAffixSlot.Optional` (Boolean) and `.Affixes` (IEnumerable) |

**Row 8 is refuted and needs a spec correction.** `IMoStratum` exposes exactly four
own properties -- `Abbreviation`, `Description`, `Name`, `PhonemesRA` -- and **no rule
collection at all**. Rule ordering is not a property of the stratum. It lives on the
*rule*: `IPhSegmentRule.OrderNumber` (Int32), with `InitialStratumRA` /
`FinalStratumRA` pointing from rule to stratum. The correct check walks rules and
groups by stratum reference -- the reverse of what the table says. An implementer
following row 8 literally would look for a collection that does not exist.

**Two casting traps found while verifying, neither in the spec:**

- **`IMoInflAffixSlot` is NOT `ICmPossibility`** (base is `CmObject` in
  `MasterLCModel.xml`). Its `Name` is its own `IMultiUnicode`, so
  `ICmPossibility(obj).Name` is wrong here -- the index warns explicitly. Contrast
  `IMoMorphType`, which genuinely is `ICmPossibility`.
- The casting load is heavier than 9.5.4's note suggests: 32 of 37 properties on
  `IMoStemAllomorph` and 31 of 36 on `IPhRegularRule` require a cast. Use the index's
  `cast_example` output per SPEC 9.5.4, and expect the preflight validator to reject
  uncast access.

**`IPhSegmentRule.Disabled` (Boolean) must gate every rule-based check.** Not
mentioned anywhere in 9.5.4. A disabled rule contributes nothing to path
multiplication, so counting it inflates rows 3, 5 and 8 and would report a suspect
the grammar never runs -- precisely the false positive 9.5.7's "suspect, never
defect" rule exists to keep honest.

**Still to verify before their rows are written** (carried into `tasks.md`, not
blocking the rest): `IMoAffixProcess` and `IPhMetathesisRule` as index types (row 5,
and row 3's metathesis half), and `ILexEntry.AlternateFormsOS` (row 7).

---

## D5. Plan-time research task (b): the flexicon read gaps

**Decision.** The two gaps are **out of CP1's scope** and are tasked at CP2, where the
spec already places the flexicon change. CP1 neither needs nor may add them.

**Rationale.** Both gaps -- no allomorph -> owning-entry accessor, and
`MSAOperations` exposing no read surface at all (`MSAOperations.pyi:14-20`) -- sit on
**mode A's** critical path, because 5.1.1's resolver must terminate in MSA HVOs. Mode
A is `flextools_try_word`, which is CP2. Nothing in CP1 resolves a morph to an MSA:
the capability probe is reflection, and the grammar scan reads `IMoForm` /
`IPhPhoneme` / `IMoInflAffixSlot` directly and never needs an entry from an allomorph.

Recorded here rather than dropped: S9 makes flexicon-first the build order, so these
ship in the flexicon change *before* the MCP consumes them at CP2. CP1 must not grow
a temporary MCP-side MSA accessor to be retired later -- SPEC 5.4's "the MCP does not
grow a temporary parser path of its own" applies to the read gaps too.

---

## D6. Where the new error codes live

**Decision.** Four codes land at CP1 -- `parser_core_missing`,
`parser_engine_mismatch`, `parser_agent_missing`, `parser_tool_missing` -- as
`extra="forbid"` detail models in `server/response_models.py`, with a row each in
`docs/TOOL-CONTRACT.md` and one CHANGELOG entry under "Tool contract".

**Rationale.** This is the established pattern: `response_models.py:142` onward
already defines per-code detail models with `model_config = ConfigDict(extra="forbid")`
and a `Literal` discriminator, and `TOOL-CONTRACT.md` carries the code table. The
additions are purely additive, so the contract stays at `tool-responses/1.0` per SPEC
14 -- no version bump, which is why the CHANGELOG entry is the only contract-facing
obligation.

The remaining ten codes in SPEC 14 belong to later checkpoints and are deliberately
not stubbed now; an unreachable code in the table is a claim the server does not
honor.

**Note for whoever writes the table row.** `TOOL-CONTRACT.md` currently says "one of
the 18 codes below". That count is hand-maintained and becomes 22 at CP1.

---

## D7. No scalar score, and what that means for the output shape

**Decision.** `flextools_grammar_health`'s response has **no score, no grade, no
ranking, and no ordering by magnitude**. Findings are grouped by check id and each
carries its own count.

**Rationale.** This is a carried-forward constraint, not a fresh choice, and it is
measured rather than asserted: PanGloss found a 2,044-state network running ~1300x
slower than a 106,365-state one, so "any metric monotone in states, arcs, or total
proposal count picks the wrong candidate". A single number would also collide with
9.5.7's "a G4 finding names a suspect, never a defect".

The design consequence is concrete: the response model must offer no field a client
could sort on as a severity proxy. Counts are per finding and reported as evidence
("this null morph is reachable from 12 optional slots"), never summed into a total.

**Alternative considered.** *A severity enum per finding.* Rejected -- it is a scalar
score with a small domain, and an implementer would sort by it.

---

## D8. `active_engine` is unconditionally `null` at CP1

**Decision.** In `flextools_health`, `parser.active_engine` is unconditionally
`null` at CP1. This is asserted by `_build_parser_block()` (T012), which had no
recorded decision behind it until now.

**Rationale.** It rests on precisely the same premise as `agent_probe: "skipped"`
(D2): `flextools_health` never opens a project, and `ActiveParser` can only be
read from an open project (`data-model.md` §`ParserDetector` return shape:
"`active_engine` is informational only. It never decides a status";
`contracts/flextools_health-parser-block.md`: "`active_engine` is informational
only -- it echoes `ActiveParser` when a project is open, else `null`"). There is
nothing to echo, so `null` is the only truthful value here -- not a placeholder,
not a TODO.

**`active_engine` is informational only and never a status input.** The
engine-mismatch gate lives in the per-call preflight (`check_active_parser`,
T024), not in health. So a `null` here costs no diagnostic power: no status field
is derived from it, and no client can sort or gate on it either way.

**What it gates.** T012's assertion of `active_engine is null` in
`_build_parser_block()` previously had no recorded decision behind it. This note
is that decision.

**When it changes.** At CP2, once a spine-executing handler holds an open
project, `active_engine` echoes `ActiveParser` (`"XAmple"` | `"HC"`,
case-sensitive) -- still informational, still never a status input. The `null`
at CP1 is a consequence of the session-independent boundary, not a permanent
shape.

---

## D9. The three outstanding 9.5.4 LCM names, gated for T035/T034

**Decision.** All three names D4 left unverified are **confirmed** against this
project's LibLCM index (`liblcm_api_v11.0.0.json`) and its companion
`casting_index_liblcm-v11.0.0.json`. Each becomes a **written** sub-check, not a
`checks_skipped` entry.

| Sub-check | Index evidence | Verdict | Consumer |
|---|---|---|---|
| `IMoAffixProcess` (row 5) | Entity present as its own interface (`liblcm_api_v11.0.0.json:94897`), `interfaces: [ICmObject, ICmObjectOrId, IMoAffixForm, IMoForm]`, own properties `FeatureConstraints`, `InputOS` (OS), `OutputOS` (OS). Listed as a `concrete_types` member of every `IMoForm`-based polymorphic collection (`AlternateFormsOS`, `AllomorphsOS`, `FormOS`, `LexemeFormOA`) in the casting index, class-name map `"MoAffixProcess": "IMoAffixProcess"` (casting_index line 301). Reading it from a polymorphic `IMoForm` slot requires `IMoAffixProcess(form)` after an `obj.ClassName` check. | **WRITTEN** | T035 |
| `IPhMetathesisRule` (row 3, metathesis half) | Entity present (`liblcm_api_v11.0.0.json:108341`), `interfaces: [ICmObject, ICmObjectOrId, IPhSegmentRule]`, own properties `IsMiddleWithLeftSwitch`, `LeftEnvIndex`, `RightEnvIndex`, `StrucChangeOS`, etc. Per the known caveat, `Disabled`, `OrderNumber`, `InitialStratumRA`, `FinalStratumRA` are inherited from base `IPhSegmentRule` and correctly absent from this entity's own `properties` array -- checked directly, not assumed. It is one of the two concrete rule types owned by `IPhPhonData.PhonRulesOS` (`target_type: "IPhSegmentRule"`, `liblcm_api_v11.0.0.json:109579`), and its class-name mapping (`"PhMetathesisRule": "IPhMetathesisRule"`, casting_index line 450) confirms the cast target. Note: `PhonRulesOS` itself is **not** enumerated in the casting index's `polymorphic_collections` table (only `IMoForm`- and `IMoMorphSynAnalysis`-rooted collections are) -- a documentation gap worth flagging separately, not a reason to doubt the entity's existence. | **WRITTEN** | T035 |
| `ILexEntry.AlternateFormsOS` (row 7, second half) | Declared directly on `ILexEntry` (`liblcm_api_v11.0.0.json:86250`, inside the `ILexEntry` block starting at line 85667), `kind: "OS"`, `relationship: "owns_sequence"`, `target_type: "IMoForm"`, `pythonic_name: "AlternateForms"`. `.Count` is a collection-level read (`ILcmOwningSequence`), so `AlternateFormsOS.Count > 1` needs no per-element cast -- casting only enters if a caller inspects an individual allomorph's concrete type, which row 7 does not require. | **WRITTEN** | T034 |

**Rationale.** All three names resolve to exact-spelling, exact-casing index
entities with no ambiguity, so none falls back to `checks_skipped` /
`lcm_name_unverified`. Per the task's own rule that a sub-check is never
silently dropped either way: had any of the three failed to resolve, this note
would instead record, per failed sub-check, `checks_skipped` with reason
`lcm_name_unverified` and name the same downstream consumer (T035 for rows 3/5,
T034 for row 7) so the consuming task knows to omit rather than guess at that
row's check.

**`IMoStemAllomorph.StemNameRA` (row 7's first half) is unaffected** -- already
verified in D4 and not re-litigated here.

---

## D10. `GrammarHealthChecker` is absent from the installed HermitCrab assembly -- the three PanGloss lints defer to CP2

**Decision.** `SIL.Machine.Morphology.HermitCrab.GrammarHealthChecker` does not exist
in the HermitCrab assembly installed on this machine (`SIL.Machine.Morphology.HermitCrab.dll`,
assembly version `3.8.2.0`, resolved via `get_resolved_fieldworks_dir()` --
`versioning.py:204` -- to `C:\Program Files\SIL\FieldWorks 9\`). The three
PanGloss-ported lints -- `hc-undeclared-segment`, `hc-duplicate-feature-bundle`,
`hc-partial-morpheme` -- do **not** come free and **defer to CP2**.

**Rationale.** Probed by reflection only, following `parser_probe.py`'s own
`Assembly.LoadFile` + `GetTypes()`/`GetMembers()` idiom (T009), reused rather than
duplicated. Nothing was instantiated, no grammar was loaded, no parser was
constructed -- consistent with this module's own CP1-boundary note that T026 asserts
no `HCParser(` construction anywhere under `src/flextoolsmcp/server/**`.

A bare `Assembly.LoadFile("SIL.Machine.Morphology.HermitCrab.dll")` followed by
`GetTypes()` throws `System.Reflection.ReflectionTypeLoadException` on this machine --
the same failure mode `probe_parser_core(HCPARSER_MEMBERS)` itself hits for
`ParserCore.dll` here (independently reproduced: both return `signal="load_failed"`
with an identical exception shape). `LoaderExceptions` name the cause:
`Assembly.LoadFile` does not probe the loaded file's own directory for dependencies
on this .NET Framework runtime (confirmed by the CLR's Fusion-log warning in the
exception trace), so the CLR could not resolve `SIL.Machine, Version=3.8.2.0` or
`SIL.Core, Version=17.0.0.0` even though both DLLs sit next to the target assembly.
Pre-loading `SIL.Core.dll` (found on disk as `18.0.0.0`) and `SIL.Machine.dll`
(`3.8.2.0`) from the same directory via `Assembly.LoadFile` before loading the
HermitCrab assembly resolved this: `GetTypes()` then returned all 195 types with no
partial-load exception, i.e. a complete, unambiguous type table -- not merely a
partial scan that might be hiding the target behind another failed dependency.

**Evidence.** Scanning the full, successfully-resolved 195-type table: no type named
`GrammarHealthChecker` exists, and no type whose name contains `Grammar`, `Checker`,
or `Health` exists anywhere in the assembly. This is a stronger finding than "present
but not public" -- the type is absent outright from the assembly whose namespace
(`SIL.Machine.Morphology.HermitCrab`) is exactly where PanGloss's grammar-health
checks would be expected to live. A secondary check of the sibling `SIL.Machine.dll`
(28 MB, evidently bundling further third-party dependencies) for the same exact type
name could not be completed -- its own `GetTypes()` call throws past what pre-loading
`SIL.Core.dll`/`SIL.Machine.dll` alone resolves -- so that assembly's absence is not
independently confirmed, only the HermitCrab-specific one is. Given the
fully-qualified name at stake names the HermitCrab assembly specifically, this is
treated as sufficient rather than pursued further.

**Consequence for the plan.** This confirms rather than overrides the task brief's
strong prior: CP1's grammar health scan stays pure LCM (D1), executed in the
generated-module subprocess, and touches no HermitCrab type. The three lints do not
fold into T034/T035's scope at CP1 -- there is no free capability to fold in, since
the type does not exist on this installed toolchain at all. Independent of that
absence, folding them in would still couple CP1's LCM-only scan to the HermitCrab
assembly and cross the CP1 boundary D1 establishes, so the deferral to CP2 holds even
under a future SIL.Machine/HermitCrab release that adds this type.

**Undetermined, not asserted, for other installs.** This verdict is scoped to the
DLL version installed on this machine (HermitCrab `3.8.2.0`). No claim is made about
any other FieldWorks/SIL.Machine version; a future CP2 task revisiting this should
re-probe rather than assume this note still holds.

---

## D11. The generated-module subprocess CAN import `flextoolsmcp.server.scan.*` directly -- D1's "covered by the existing preflight/casting validators" claim is corrected

**Decision.** Import works. `handle_run_module`'s subprocess is a plain CPython
process running `sys.executable` -- the exact same interpreter that runs the MCP
server itself, not IronPython and not a sandboxed environment. `import
flextoolsmcp.server.scan.<anything>` succeeds in it, unconditionally, with no
extra `PYTHONPATH`/`env` wiring needed. T030 should build the **import path**,
not the splice path: a new, minimal script template that imports the scan
module by name and returns findings via `report.Result(...)`, read back through
the `===FLEXTOOLS_USER_RESULT===` sentinel -- exactly the mechanism the task
brief names as preferred.

**This verdict comes from an executed probe, not a code-read.** Code-reading
supplied the hypothesis; the probe is what confirms it. Two things were run:

1. `run_script_async` (`src/flextoolsmcp/server/subprocess_helpers.py:56-95`)
   launches the child via `asyncio.create_subprocess_exec(sys.executable,
   script_path, ...)`. Both of its two call sites in `execution.py` (lines 4452
   and 4458, inside `handle_run_module`) pass no `env=` kwarg, so `env=None`
   flows through to `create_subprocess_exec`, meaning the child inherits this
   process's environment verbatim -- no explicit `PYTHONPATH` is ever set for
   it anywhere in the file.
2. A scratch probe (kept out of the repo, in the session scratchpad, deleted
   after the run) reproduced `run_script_async` line-for-line -- same
   `sys.executable`, same `env=None`, same `asyncio.create_subprocess_exec`
   shape -- and pointed it at a temp script containing only:
   `import flextoolsmcp.server.scan as scan_pkg`, then printing
   `===FLEXTOOLS_USER_RESULT===` followed by a JSON blob (mirroring
   `SimpleReporter.Result`, `execution.py:3871-3888`), then
   `===FLEXTOOLS_RESULT_JSON===`. Run twice, once from the repo root and once
   from an unrelated directory (`D:\tmp`) to rule out a cwd-dependent result.
   Both runs: `returncode 0`, empty stderr, stdout
   `{"imported_from": "D:\\Github\\_Projects\\_LEX\\FlexToolsMCP\\src\\flextoolsmcp\\server\\scan\\__init__.py", "ok": true}`
   between the two sentinels, and the sentinel-parsing logic copied from
   `execution.py:4481-4490` round-tripped it back into a dict successfully.

**Why the import is available with no extra wiring.** `python -c "import
sys; print(sys.executable)"` in this environment resolves to
`D:\Apps\anaconda3\python.exe`. `pip show` reports no top-level `flextoolsmcp`
metadata, but `D:\Apps\anaconda3\Lib\site-packages\__editable__.flextools_mcp-2.11.0.pth`
exists and contains exactly one line: `D:\Github\_Projects\_LEX\FlexToolsMCP\src`.
That `.pth` is processed by every fresh CPython process started with this same
`python.exe` -- including a subprocess spawned via `sys.executable`, regardless
of the parent's in-memory `sys.path` or working directory -- which is exactly
why the cwd-independence check above matters: it rules out the alternative
explanation that the import only "worked" because the probe happened to run
from inside the repo. `flextoolsmcp.server.scan.__init__` (landed as T001,
confirmed present at `src/flextoolsmcp/server/scan/__init__.py`) is therefore on
`sys.path` in the generated-module subprocess by construction, for any
deployment where `flextoolsmcp` is installed (editable or not) into the same
interpreter that runs the MCP server -- which every real deployment is, since
`run_script_async` always uses `sys.executable`, never a hardcoded or
externally-configured interpreter path.

**D1 correction.** D1 (`research.md:13-45`) states: "The scan's checks are
authored as a module the harness runs, so they are covered by the existing
preflight/casting validators." That is **not achievable as scoped** and is
corrected here rather than reworded in place (D1 is left untouched per the
append-only rule). `handle_run_module`'s preflight/casting gates (the AST-parse,
casting-injection, and CUD-detection chain) run exclusively over the
caller-supplied `code` **string** that gets spliced into `MODULE_CODE = {code}`
(`execution.py:4181`) -- there is no code path by which a module already living
on disk at `server/scan/grammar_scan_module.py` and merely `import`-ed ever
passes through that string-based validator chain. What actually covers
`grammar_scan_module.py` is what covers every other first-party file under
`src/`: the repo's own test suite and lint, not the runtime validators built for
LLM-generated `code` text. T019/T034/T035 should not expect casting-preflight
protection on that module and must get their own casting correctness from
tests, the same way any other hand-written file in this codebase does.

**Consequence for the plan / what T030 must build.** T030 builds a new, small
script-template function alongside (not inside) `handle_run_module` in
`src/flextoolsmcp/server/handlers/execution.py`. It reuses the pieces that
generalize -- `SimpleReporter` (`execution.py:3767+`) for `report.Result(...)`,
the `OpenProject(...)` call needed to hand the scan module a live `project`
handle, `run_script_async` for the launch, and the existing
`===FLEXTOOLS_USER_RESULT===` / `===FLEXTOOLS_RESULT_JSON===` sentinel-pair
convention for the return channel (same sentinels, same parsing logic,
`execution.py:4481-4490`) -- but its "module code" is a fixed, literal one-liner
import (`from flextoolsmcp.server.scan.grammar_scan_module import
run_grammar_scan` or equivalent) followed by `report.Result(run_grammar_scan(project))`,
never caller-supplied text, so none of the AST-parse/casting-injection/CUD
preflight chain applies or is needed.

**T030 is NOT forced to refactor `handle_run_module`.** The import path needs
none of that function's ~1800 lines (write-lock negotiation, backup, casting
injection, size-oscillation detection all exist to make arbitrary LLM-authored
`code` text safe to run; a fixed first-party import has none of that risk
surface). T030 adds a parallel, much smaller function and wires a new handler
(T020) to it; `handle_run_module` itself is untouched.

**Scope note.** This probe deliberately opened no FieldWorks project (CP1
boundary): it only proves the import/sentinel seam in isolation. Confirming
that `report.Result(...)` still round-trips correctly with a *real* open
project and a *real* `grammar_scan_module.run_grammar_scan(project)` return
value is T019/T030's job, not this task's.
