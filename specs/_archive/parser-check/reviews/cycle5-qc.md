# QC Report -- parser-check tasks.md audit (pre-code, cycle 5)

> **Provenance note.** Authored by `lex-qc` in cycle 5. The agent has no write tool
> (Read/Grep/Glob only), so the main session persisted this body verbatim to the path
> the dispatch plan specified. Content is lex-qc's, unedited.

## 1. CP1-deliverable -> task coverage table

| SPEC 15 CP1 deliverable | Task(s) | Status |
|---|---|---|
| ParserCore located + capability-probed (5.4) | T003, T006, T007, T009, T011 | OK |
| ActiveParser read + `parser_engine_mismatch` refusal | T003, T006, T022, T024 | OK |
| HC-agent probe + `parser_agent_missing` refusal (12.7) | T003, T006, T012, T023, T025 | OK |
| `hc` via `dotnet tool list -g` | T010 | OK |
| `GenerateHCConfig.exe` discovery | T010 | OK |
| Health-block assembly (`parser` key, per-spine states, `next_step`) | T008, T012, T013 | OK |
| `flextools_grammar_health` (9.5.5) | T014-T021 | OK |
| Four additive error codes / contract rows / CHANGELOG | T003, T004, T005, T006 | OK |
| CP1 boundary invariant (no HCParser instantiated, no grammar loaded) | T026, T028 | OK |
| **PanGloss `GrammarHealthChecker` public-in-installed-dll check** (handoff open question) | **none** | **UNCOVERED** |

No CP1 deliverable is fully uncovered except the GrammarHealthChecker question (see #5).

## 2. Reverse coverage

No scope creep found. All 28 tasks trace to a CP1 deliverable or the coverage map.
T022-T025 (US3 helpers) look like CP2 material by their framing ("first caller arrives
at CP2") but SPEC 15's CP1 row explicitly names both refusals as CP1 deliverables --
building the tested helper without a caller is correct, not creep. T016 (research.md
write) and T027 (SPEC self-correction) are process tasks, both traceable to SPEC-9.5.4
in the coverage map.

## 3. SPEC 16 -> T006/T007/T008

- "ParserCore capability probe (5.4)" group (4 bullets: `foreign_install`,
  `incompatible_surface`, version-passes-and-is-reported, no-cache-opened) -> all four
  map 1:1 into **T007**. OK.
- Envelope bullet ("Error envelopes validate against their detail models,
  `extra=forbid`") -> **T006**. OK.
- **Gap:** SPEC 16's "Integration (Windows + FieldWorks, no `hc` tool)" bullet --
  "`flextools_health` reports the sandbox spine unavailable with the real
  `dotnet tool install` hint, while the in-process spines report ready" -- has no task
  ID. It only survives as Phase 3's prose "Independent test," not a `tests/...` file
  target. T008 covers the *general* two-state/no-blanking invariants (sourced from
  10.2/contract, not a section-16 bullet) but not this specific real-machine
  integration scenario. **P2: add a task** (or fold into T008's scope explicitly) for
  this integration bullet.

## 4. T014's denylist -- insufficient as the sole guard (P0)

A string denylist bans literal words but not renamed proxies. A conforming
implementation could still smuggle severity via a field named `impact`, `tier`,
`weight`, `urgency`, or `significance` -- none banned -- and a client could sort on it.
Likewise the "no verdict wording" list (`invalid/incorrect/wrong/error/defect/broken`)
misses synonyms (`faulty`, `flawed`, `problematic`, `malformed`, `bug`).

**Recommend T014 additionally assert:**

1. The `Finding`/response models are Pydantic with `extra="forbid"` and an explicit
   **allowlist** of keys (`check_id, spec_row, count, measured, evidence_basis,
   objects`) -- structural closure beats a denylist of names.
2. **Order-invariance test:** run the same checks with two different count magnitudes
   (e.g. permuted) and assert `findings` order is byte-identical both times -- proves
   order is fixed at authoring time, not derived from this run's counts, closing the
   "first finding is worst" smuggling path.
3. `objects[]` item order is also asserted non-magnitude-sorted (same vector, one level
   down).
4. Anchor `measured` on a positive vocabulary/template check (factual, count-based
   phrasing) in addition to the negative denylist, since the denylist alone is trivially
   bypassed by synonym.

## 5. Open questions vs. tasks

- **"CHECK AT CP1: is `SIL.Machine.Morphology.HermitCrab.GrammarHealthChecker` public
  in the INSTALLED dll?"** -- no task anywhere in tasks.md references
  `GrammarHealthChecker` or the three PanGloss-ported lints. **P1 gap**: this is
  explicitly CP1-scoped in `.crew-handoff.json` and, if answered yes, is described as
  "free" checks for the grammar scan (T019's scope). Recommend a `[P]` research task in
  Phase 4 Wave 2 alongside T016.
- Other handoff open questions (17.10 HC-agent lazy creation, 17.11 `UniqueWordforms()`,
  17.12 segment-without-human-act, GenerateHCConfig-vs-copied-project) are all explicitly
  marked "does not block CP1" / "verify before CP3" in the handoff -- correctly absent
  from tasks.md.

## 6. Ordering smells

- **T027 in Polish, T019 in Phase 4 (P2):** T019 already implements the corrected row 8
  directly (the corrected fact is inlined in T019's own description and was resolved
  during planning per `.spec-context.json`'s decisions), so there's no functional
  blocking dependency. But SPEC.md remains factually wrong for the entire Phase 3-5
  window, risking drift if anyone reads section 9.5.4 as canonical mid-build. Recommend
  moving T027 to Wave 2 of Phase 4 (paired with T016), not Polish.
- **T016 under "Implementation" heading (P2, cosmetic):** it writes only to
  `research.md`, no source. Wave ordering (W2 before W3) already enforces correctness,
  so this is a labeling issue only -- re-head it "Research (gates implementation)" for
  clarity.

## 7. Independent verifiability

Most tasks name exact files/fields and are checkable standalone. One vague exception:

- **T028 (P1):** "confirming the SPEC 16 items scoped to CP1 all pass" has no enumerated
  checklist -- a reviewer must independently decide which of section 16's ~15 groups are
  CP1-scoped (the same exercise this QC review had to do). Recommend T028 embed or
  reference an explicit itemized list of the CP1-scoped SPEC 16 bullets rather than
  leaving scope to reviewer judgment.

---

**Recommendation: FIX ISSUES** -- primarily #4 (P0, T014 denylist insufficiency) and #5
(P1, missing GrammarHealthChecker task), plus #7 (P1, T028 vagueness). Items #3 and #6
are P2 and can be folded in without re-planning.
