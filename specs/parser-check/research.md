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
