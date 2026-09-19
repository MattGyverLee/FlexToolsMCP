# Tasks: parser-check CP2a -- the script-library parser surface

**Scope**: CP2a ONLY -- User Story 1 (FR-001..FR-011) plus the grammar-lifetime
clauses it implements (FR-041 flexicon half, FR-042, FR-043).
**Plan**: [`plan.md`](./plan.md) · **Spec**: [`spec.md`](./spec.md) ·
**Contracts**: [`contracts/parser-operations.md`](./contracts/parser-operations.md),
[`contracts/evidence-gate.md`](./contracts/evidence-gate.md)

---

## Where these paths point

CP2a changes **one** file in this repository. Everything else lands in a
different repo.

| Path prefix | Repository root |
|---|---|
| `flexicon/...`, `tests/...`, `CHANGELOG.md`, `history.md`, `RELEASE_NOTES_*` | `D:\Github\_Projects\_LEX\flexicon` |
| `specs/...`, `src/...` | `D:\Github\_Projects\_LEX\FlexToolsMCP` (this repo) |

**Governing constitution**: `D:\Github\_Projects\_LEX\flexicon\.specify\memory\constitution.md`
(Flexicon Constitution v1.0.0).

## Required invocation -- quoted per Constitution Principle II

```
python -m pytest -m "not requires_live_project" -q
```

Tier A3 only, in-place against the installed project:

```
$env:FLEXLIBS_REQUIRE_LIVE = "1"; python -m pytest tests/operations/test_parser_live.py -m requires_live_project -q
```

Bare `pytest` is prohibited. So is `pytest --ignore=tests/contract` -- it
applies no marker filter and executes `requires_live_project` tests against
real projects.

## Not in this task list

Named here so they are not implemented early by association (plan.md, "Scope fence"):

- **CP2a-bridge** -- the `pyflexicon>=4.9.0,<5` floor, refreshed index artifacts,
  the floor/index-equality test. Runs after the tag, before CP2b's first parser task.
- **CP2b** -- `flextools_try_word`, `flextools_parse_status`, the run record,
  stages, priority queue, cancellation (FR-012..FR-040), and the
  `HCParser_DoesNotLoadXCore` / SC-003 standing test.
- **Tier A4** -- the live half of FR-043's stale branch. Requires a live write,
  so Constitution Principle II defers it to CP2b with `needs_human` (escalation E-D).
- **The `v4.9.0` tag push and `gh release create`** -- maintainer acts
  (escalation E-C). CP2a stops at the prepared release commit.

## Refinements to plan.md made here

- **Citations corrected against the live flexicon tree (cycle 5).** tasks.md was
  written in spurt 3; flexicon took commits afterwards. The audit in
  [`reviews/cycle5-explore-taskrefs.md`](./reviews/cycle5-explore-taskrefs.md)
  checked every `path:line` citation here against commit `c08ede4`: 24 of ~30 are
  exact and **every ratchet and registry citation is line-accurate**. The three
  load-bearing errors (T007's template, T009's "net-new" premise, T013's
  justification) and the path omissions in T011/T023 are corrected inline above.

- The plan's single `tests/test_parser_offline.py` is split into two files so the
  behavioural checks and the standing AST ratchets are independently runnable and
  independently ownable: `tests/test_parser_offline.py` (A1.1, A1.4, A1.5, A1.6)
  and `tests/test_parser_structure.py` (A1.2, A1.3, following the
  `tests/test_public_casting_export.py:127-153` template).

---

## Phase 1: Setup

**Wave 1 -- independent (different files):**

- [ ] **T001** [P] Capture the pre-change baseline: run `python -m pytest -m "not requires_live_project" -q`, save the full transcript and its exact invocation, and enumerate every failure as **pre-existing** with an attribution. This is not a smoke check -- with no CI anywhere (no hosted-runner workflow, and the self-hosted `[windows, fieldworks]` pool has zero registered runners), it is the only record that separates a failure CP2a caused from one it inherited, and Principle IV requires that separation in the evidence artifact · `specs/parser-check-cp2/evidence/raw/baseline.md`
- [ ] **T002** [P] Create the new domain package with an empty `__init__.py`. Own package rather than `Lexicon/` or `TextsWords/` because it wraps a different assembly (`ParserCore.dll`) with a different availability lifetime, and the package boundary is what makes "this whole area can be unavailable" expressible (D-A2) · `flexicon/code/Parser/__init__.py`

---

## Phase 2: Foundational -- verify the LCM surface before building on it

Constitution Principle I (NON-NEGOTIABLE). **This phase blocks every facade
task in Phase 3.** No design may assume a member exists; `Reset` and
`IsUpToDate` have never been verified anywhere, in either repository.

**Wave 1 -- single task:**

- [ ] **T003** Write and run tier A2, against the **real installed** `ParserCore.dll`, FieldWorks present and **no project opened** (no LCM cache, therefore no write risk of any kind). Assert A2.1 every member the facade will bind exists -- construction from a cache, update, reset, currency read, plain parse, structured parse, trace; A2.2 the reset and currency members **specifically**, which the shipped MCP-side check does not cover and which this verifies for the first time anywhere; A2.3 same-installation directory equality holds on this machine (FR-004); A2.4 the detected version is read and unused (FR-006) · `tests/test_parser_reflective.py`

**--> Wait for Wave 1 to finish, then:**

- [ ] **T004** Save the A2 transcript with its exact invocation and the observed member list. **Gate:** if A2.2 fails, the facade cannot be built as designed -- halt and return to research rather than working around it. Running this tier before any behaviour exists is the entire point of the ordering · `specs/parser-check-cp2/evidence/raw/tier-a2.md`

---

## Phase 3: User Story 1 -- a generated script can reach the parser safely (P1)

**Goal**: `project.Parser` exists as an ordinary area of the project object; on a
machine where the parser component is missing, relocated or from a different
FieldWorks installation, import still succeeds and the area reports itself
unavailable *with a reason*, raising nothing. Three read gaps close alongside it.

**Independent Test**: Install the built library on a machine with the parser
component's resolution failing, import it, confirm the import succeeds and parser
access reports unavailable with a reason. Then against `IndonesianHC-Complete`,
call each read operation from a plain script and confirm results come back.

### Tests -- write these first, and expect them to fail

**Wave 1 -- independent (different files):**

- [ ] **T005** [P] [US1] Tier A1 behavioural checks, run with FieldWorks present and the parser component's resolution **simulated as failing** (re-tiered per D-A1: `import flexicon` itself requires FieldWorks, because `__init__.py:76` pulls in `FLExInit`, whose module scope calls `InitialiseFWGlobals()` and raises without the registry key -- a genuinely FieldWorks-free run cannot execute these). A1.1 import succeeds and availability reports unavailable with a reason, raising nothing (SC-001); A1.4 the public surface contains no method that records, files or writes a result, asserted by **enumeration** over the surface rather than by inspection (FR-002); A1.5 operations are bound **positionally**, not by parameter name (FR-005); A1.6 a grammar reported stale produces a reload before any word is parsed, against a stubbed change listener (FR-043). Simulate absence -- never assume it; there is no template for this shape anywhere in the package · `tests/test_parser_offline.py`
- [ ] **T006** [P] [US1] The two standing AST ratchets. A1.2: no code path compares a detected parser version against a minimum -- **0 occurrences** (FR-006, SC-002). A1.3: no module-scope parser import exists anywhere; loading is triggered by use only (FR-003). Template: `tests/test_public_casting_export.py:127-153`. Both are controls that fail loudly, not conventions an implementer must remember (Principle III) · `tests/test_parser_structure.py`

### Implementation

**Wave 2 -- the three read gaps, independent of the parser and of each other (different files):**

A machine with no parser component still gets all three.

- [ ] **T007** [P] [US1] FR-007: add `GetGenres(text)` returning **every** genre assigned to a text, empty list when none, reading `GenresRC` as a reference collection. Decorate `@wrap_enumerable` stacked **above** `@OperationsMethod` (order matters -- `BaseOperations.py:172`). Template for the **stacked decorators**: `AllomorphOperations.py:102-104` (or `ReversalIndexOperations.py:81-83`) -- these actually stack the two. `LexSenseOperations.GetSemanticDomains` (`LexSenseOperations.py:1602`) is the shape reference for an **RC read only**; it carries `@OperationsMethod` alone and returns `list(...)`, so copying it faithfully drops the very requirement this task sets (cycle-5 citation audit, discrepancy 1). Leave the existing singular `GetGenre` (`TextOperations.py:665`, with `GenresRC.FirstOrDefault()` at `:699`) **exactly as it is** -- changing its cardinality would be a silent breaking change no structural ratchet would catch (D-A9). Update the matching stub line in the same task · `flexicon/code/TextsWords/TextOperations.py`, `flexicon/code/TextsWords/TextOperations.pyi`
- [ ] **T008** [P] [US1] FR-008: add `GetOwningEntry(allomorph_or_hvo)` returning the owning `ILexEntry` or `None`. Resolve via `OwnerOfClass(LexEntryTags.kClassId)` and **null-guard before casting** -- copy `LexSenseOperations.py:2826`, **not** the three one-hop `.Owner` siblings (Etymology, Pronunciation, Variant) that sit in the same directory and are unguarded: an `IMoForm` can sit under an affix-form chain where one hop lands on the wrong object, and copying a working pattern without re-checking it on the target type is the documented root cause of issues #36, #39 and #40 (D-A8, Principle I). This closes the round trip against the existing `AllomorphOperations.GetAll(entry)` at `:104`. Update the matching stub line · `flexicon/code/Lexicon/AllomorphOperations.py`, `flexicon/code/Lexicon/AllomorphOperations.pyi`
- [ ] **T009** [P] [US1] FR-009: add a read accessor **into the existing, write-capable `MSAOperations`** over `entry.MorphoSyntaxAnalysesOC`. **`flexicon/code/Lexicon/MSAOperations.py` is NOT net-new** -- it already exists at 1230 lines (`class MSAOperations(BaseOperations)` at `:115`) with `CreateStem` / `CreateDerivAff` / `CreateInflAff` / `SetStemMsaPos` / `ChangeAffixVariant` / `RemoveOrphaned` and sync properties, and its `.pyi` exists too; what it has no accessor for is **reading**. Two consequences to settle before writing code: whether the new accessor needs `@wrap_enumerable` alongside its write siblings, and that this deliverable is **not** read-only-by-construction the way `flexicon/code/Parser/` is -- nothing in T010/T011's read-only framing may be inherited by association (cycle-5 citation audit, discrepancy 2). The accessor itself wraps each element in the **existing** `MorphosyntaxAnalysis` (`morphosyntax_analysis.py:74`) and returns the **existing** `MSACollection` (`msa_collection.py:76`). Both are already complete and are instantiated by no code path at all -- this is wiring, not design. Wiring template: `AllomorphOperations.GetAll` (`AllomorphOperations.py:104`), the same two-subtype shape already shipped end to end. Callers must never see `ClassName` or a cast; subtype differences stay inside the wrapper's `is_*` / `as_*` / `pos_*` families (Principle VI). Where a flat property read is needed, use the `ClassName`-keyed dispatch convention (`lcm_casting.py:652`, `:662`, `:665`) consumed as at `LexSenseOperations.py:1177`. Update the matching stub line · `flexicon/code/Lexicon/MSAOperations.py`, `flexicon/code/Lexicon/MSAOperations.pyi`

**--> Wait for Wave 2 and Phase 2 to finish, then (the facade -- same file, strictly ordered):**

- [ ] **T010** [US1] Add `ParserAvailability` (fields `available: bool`, `reason: str`, `version: str | None`) and the probe that resolves it: directory equality against the data model's installation (FR-004), then member inspection of every operation to be called (FR-005), then the version **read and never compared** (FR-006). Constructing the status **never raises, on any machine, in any condition** -- that is SC-001. This is the first degrading-with-reason return in the package: flexicon today has exactly two shapes, raise or silently become `None`, and no precedent for a third (F2, D-A4). The `reason` must state **what was checked and nothing more** -- FR-004's test is directory equality only, so a foreign component copied into the correct directory passes undetected, and the docstring must say so (Principle V). Per SC-016, the docstring also carries the written statement naming what `src/flextoolsmcp/server/parser_probe.py` checks that this does not, and why the two checks are deliberately different (D1) · `flexicon/code/Parser/ParserOperations.py`
- [ ] **T011** [US1] Add the five operations FR-001 requires, on `BaseOperations` (`BaseOperations.py:590`), `__init__` delegating via `super().__init__(project)` and re-documented (template `flexicon/code/Reversal/ReversalIndexOperations.py:70-77` -- `:77` is the `super().__init__(project)` line this points at), `@OperationsMethod` on every public method: plain parse (results carry **live** `IMoForm` / `IMoMorphSynAnalysis` / `ILexEntryInflType` references, not strings -- FR-010); structured parse; trace with an optional caller-supplied analysis restriction (identity here needs a repository lookup to rehydrate -- **do not build a typed object-identity marshaller for the trace**, FR-010 as amended by E5); **reload as reset-then-update, two steps** (D-A5, FR-043 -- `HCParser.Update()` is guarded by `if (m_changeListener.Reset() || m_forceUpdate) LoadParser();`, so a bare update short-circuits on an unchanged model and serves the next parse from the stale grammar the caller believes was discarded, which is the `RollbackToMark` fiction Principle I exists to prevent; FieldWorks' own `ParserWorker.ReloadGrammarAndLexicon()` resets first); and a currency read returning `bool` (FR-043's "confirmed before reuse"). Hold **at most one** loaded grammar, for the project in use, releasing it when another project's is needed (FR-042, SC-014); answer currency by asking the parser, never from a local flag. Bind every operation **positionally** -- interface and implementation disagree on parameter names for two of them, and positional binding is what makes that harmless. **No `_EnsureWriteEnabled`, no `_TransactionCM`, no method that records or files a result** (FR-002); state that absence in the class docstring, because the read-only safety claim of both CP2b tools rests on it · `flexicon/code/Parser/ParserOperations.py`
- [ ] **T012** [US1] Hand-write the matching stub for the class, `ParserAvailability`, and all five operations · `flexicon/code/Parser/ParserOperations.pyi`

**--> Wait for T012, then (registration -- independent, different files):**

- [ ] **T013** [P] [US1] Register the lazy read-only `@property Parser` on `FLExProject` with a **function-local** import and a `__dict__` cache keyed `_parser_ops` -- template `FLExProject.py:2181-2209`. Singular, not plural: the plural-guess block at `_op_aliases.py:79-84` (`LexEntries`->`LexEntry`, `MSAs`->`MSA`, `Etymologies`->`Etymology`, `GramCats`->`GramCat`) plus the shipped singular service facades on `FLExProject.py` -- `:1622 POS`, `:1649 LexEntry`, `:2212 MSA`, `:2787 Discourse`, `:2916 ProjectSettings` -- establish that plural is for collection namespaces and singular for service facades, and a parser is a service (D-A3). **Do not cite `_op_aliases.py:6-8` for this**: that comment says nothing about service facades and names none of those four accessors. The decision is right; only the original citation was wrong, and an implementer who checked it would have found the premise unsupported and reopened a settled naming decision (cycle-5 citation audit, discrepancy 3). The function-local import is what satisfies FR-003 and keeps T006's A1.3 assertion true. Add the accessor to the stub with a return annotation that is the **identical string** on both sides (`tests/test_pyi_return_annotation_ratchet.py:70-101`), so that `>>>` examples naming `project.Parser` are not reported `unknown-accessor` by `tests/test_docstring_example_ratchet.py`; regenerate `tests/docstring_example_baseline.json` if it moves · `flexicon/code/FLExProject.py`, `flexicon/code/FLExProject.pyi`
- [ ] **T014** [P] [US1] Export the class top-level -- `from .code.Parser.ParserOperations import ParserOperations` in **both** files, **and** the `__all__` string in the stub. Three assertions fail without all three edits: `tests/test_297_init_stub_parity.py:170`, `:190`, `:210`. Do **not** touch `CAPABILITIES` or `version` here; both land later and for different reasons · `flexicon/__init__.py`, `flexicon/__init__.pyi`
- [ ] **T015** [P] [US1] Add the class to the test plugin registry: `operations_modules` (`tests/flex_plugin.py:152-222`) **and** `_OPERATIONS_CLASS_DOMAIN` (`:738-808`). The comment at `:736-737` requires the two stay in sync · `tests/flex_plugin.py`

**--> Wait for T013 (the canonical target must exist), then:**

- [ ] **T016** [US1] Add the `"Parsers"` -> `"Parser"` plural guess to the alias table (`:35`, `:79-84`). `install_op_namespace_aliases` raises **at import time** if a listed canonical target does not exist (`:143-149`), which is why this cannot land before the property · `flexicon/code/_op_aliases.py`

**--> Wait for Wave 3 and T016, then:**

- [ ] **T017** [US1] Run tier A1 to green with `python -m pytest -m "not requires_live_project" -q`, iterating on T010/T011 until A1.1-A1.6 pass, and save the transcript with its exact invocation · `specs/parser-check-cp2/evidence/raw/tier-a1.md`

**--> Wait for T017, then (tier A3 live -- same file, strictly ordered):**

Target `IndonesianHC-Complete` (41 entries, 3 phonological rules -- small enough
that a cold grammar load stays fast), opened with `writeEnabled=False`. No write,
no restore, **no human authorisation required.** Must be an *installed* project,
never a `.fwbackup` sandbox: opening a sandbox read-only triggers a modal liblcm
dialog that freezes the suite.

- [ ] **T018** [US1] Create the live read-only tier. A3.1 the parser constructs against a real cache and a real update loads a grammar; A3.2 a word parses and a trace returns; A3.4 FR-010's object-identity claim -- plain-parse results carry live object references, not strings; A3.6 the active parser is confirmed to be the expected engine on both `IndonesianHC-Complete` and `Malay Parsing-20230810withHC`. Mark `requires_live_project` · `tests/operations/test_parser_live.py`
- [ ] **T019** [US1] **A3.3, the gate within the gate.** With no model change between calls, prove the plain update does **not** reload and the reload **does**. Witness: the identity of the parser's internal morpher instance across calls, since `LoadParser()` replaces it (D-A11). This is a private-field read under pythonnet -- acceptable only in a test whose docstring says so, and unacceptable in shipped code. Documented fallback if the private read proves unreliable: observe the rewrite of the `{ProjectName}HCLoadErrors.xml` side file, which CP1 already treats as the load signal. Do **not** assert on elapsed time; that is a correlation, not a witness, and a small grammar on a warm cache makes it flaky. **A reload that cannot be shown to discard has not been proven, and CP2b does not start** · `tests/operations/test_parser_live.py`
- [ ] **T020** [US1] A3.5: across a sequence spanning both live projects, assert at most one grammar is held and switching projects releases the previous one -- 0 grammars retained for a project not in use (SC-014), with 0 parses served from a grammar whose currency was not confirmed immediately before reuse (SC-015) · `tests/operations/test_parser_live.py`
- [ ] **T021** [US1] Run tier A3 with `$env:FLEXLIBS_REQUIRE_LIVE = "1"; python -m pytest tests/operations/test_parser_live.py -m requires_live_project -q`. `FLEXLIBS_REQUIRE_LIVE=1` turns silent mock-degradation into a usage error, so a run that quietly fell back to mocks cannot be mistaken for live evidence -- confirm `tests/live_status.json` shows `"run_mode": "live"` before recording anything. Save the transcript, the run mode, and for A3.3 **which witness produced the result** · `specs/parser-check-cp2/evidence/raw/tier-a3.md`

**--> Wait for T021 (tiers A1-A3 all passing), then:**

- [ ] **T022** [US1] Add the `"parser"` token to `CAPABILITIES` (`flexicon/__init__.py:67-72`), the `#:` doc block above the frozenset (`:17-66`), and `EXPECTED_TOKENS` (`tests/write_path_transactions/test_capabilities.py:36-41`, asserted for set equality at `:54`) -- **three edits in lockstep, in one task, and last**. `test_capabilities.py:12-16` states that a token added without a landed capability behind it is a Principle V violation, and the token is read across the repository boundary by FlexToolsMCP (D-A10). The doc block must preserve the semantics at `:31-33`: a token means *this build implements the surface*, **not** that the parser is reachable on the machine reading it -- that runtime question belongs to `ParserAvailability` alone, and CP2b must probe it rather than infer it from the token · `flexicon/__init__.py`, `tests/write_path_transactions/test_capabilities.py`

**--> Wait for T022, then (the release cut):**

- [ ] **T023** [US1] FR-011: bump `version` `"4.8.0"` -> `"4.9.0"` at `flexicon/__init__.py:15`. **Single source of truth** -- `pyproject.toml:69-72` reads it via `version = { attr = "flexicon.version" }`, and `docs/RELEASING.md:189` says "Do not add a second version constant." The stub declares only the type (`__init__.pyi:12`), so there is no literal to bump there · `flexicon/__init__.py`

**--> Wait for T023, then (release paperwork -- independent, different files):**

- [ ] **T024** [P] [US1] Move `[Unreleased]` to `[4.9.0] - <date>`, covering the parser surface, the three read gaps and the new capability token · `CHANGELOG.md`
- [ ] **T025** [P] [US1] Add the newest-first narrative entry · `history.md`
- [ ] **T026** [P] [US1] Write the release notes, including the CAPABILITIES token semantics and the read-only-by-construction statement · `RELEASE_NOTES_v4.9.0.md`

**--> Wait for Wave 8, then:**

- [ ] **T027** [US1] Prepare the release commit with all four ratchets green -- stub parity, return-annotation agreement, docstring examples, alias stability (the string `flexlibs2` must not appear in any new code, comment, docstring, test or doc: `tests/test_flexlibs2_alias_ratchet.py:150`, `:170`, `:285`, `:310`). **Then stop.** The `v4.9.0` tag push and `gh release create` publish to PyPI and are irreversible -- they are maintainer acts (escalation E-C). The prepared release commit is the last reversible moment for anything in `contracts/parser-operations.md`

**Checkpoint**: `project.Parser` is reachable from a plain FLExTools module, degrades
with a stated reason instead of raising, and all three read gaps are closed --
independently functional and testable without any assistant-side change. Note the
seam CP2b actually depends on is *proven*, not *released* (Decision D4): the tag and
the evidence gate are on separate timelines, which is precisely why FR-011 was
amended in cycle 3.

---

## Phase 4: Polish

**Wave 1 -- independent (different files):**

- [ ] **T028** [P] Run the full suite with `python -m pytest -m "not requires_live_project" -q` and validate against the Success Criteria in scope -- SC-001, SC-002, SC-014, SC-015, SC-016, and the CP2a portion of SC-013. Reconcile every failure against the T001 baseline and name each pre-existing one **as pre-existing, with its attribution**; never round to "green" (Principle IV) · `specs/parser-check-cp2/evidence/raw/final-suite.md`
- [ ] **T029** [P] Assert this checkpoint changed **0 lines** of the capability check already shipped here -- `git diff` must be empty for it (FR-041, SC-016, Decision D1). The two checks are deliberately different, not accidentally divergent · `src/flextoolsmcp/server/parser_probe.py`

**--> Wait for Wave 1 to finish, then:**

- [ ] **T030** Write the evidence artifact -- **the only file CP2a creates in this repository, and CP2b's entry gate.** Per tier A1/A2/A3: the exact invocation that produced the result, full counts including failures with pre-existing ones named as pre-existing, for A3.3 the observed discard result and which witness produced it, and for any tier not run, that it was not run and why. Record A4 as deferred to CP2b with `needs_human` (escalation E-D). This is prose evidence, not a test count: all four flexicon ratchets are structural and **every one of them would have passed a reload bound to a bare update**, which is the defect cycle 1 actually found -- so a green suite cannot discharge the one claim that matters most. A future maintainer asking "how do we know the reload discards?" must find an answer that is not "there is a test named that" (D-A12, Principle IV) · `specs/parser-check-cp2/evidence/cp2a-evidence.md`
- [ ] **T031** Record the handoff state in the evidence artifact's closing section: CP2a-bridge not started (the `pyflexicon>=4.9.0,<5` floor, refreshed index artifacts and the floor/index-equality test remain to be done in this repo before CP2b's first parser task), CP2b not started, and escalations E-C (tag push) and E-D (tier A4 live write) standing and unresolved · `specs/parser-check-cp2/evidence/cp2a-evidence.md`

---

## Dependencies & Execution Order

**Phase order**: Setup (T001-T002) -> Foundational (T003-T004) -> User Story 1
(T005-T027) -> Polish (T028-T031). The order is constrained, not stylistic --
each step's output is the next step's precondition.

| Phase | Waves |
|---|---|
| **1 Setup** | Wave 1: T001, T002 -- fully independent, nothing blocks them. |
| **2 Foundational** | Wave 1: T003 alone. -> Wave 2: T004 (needs T003's run). **Phase 2 blocks every facade task in Phase 3**, per Principle I: no design may assume a member exists, and A2.2 is the first verification of the reset and currency members anywhere. |
| **3 US1** | Wave 1 (tests-first): T005, T006. -> Wave 2 (read gaps, parser-independent): T007, T008, T009 -- these need neither Phase 2 nor the facade, so they may in practice start alongside T003. -> Wave 3 (facade, one file, strictly ordered): T010 -> T011 -> T012, gated on T004. -> Wave 4 (registration): T013, T014, T015. -> Wave 5: T016 alone (the alias table raises at import if `Parser` does not yet exist, so it must follow T013). -> Wave 6: T017 (A1 green). -> Wave 7 (live tier, one file, ordered): T018 -> T019 -> T020 -> T021. -> Wave 8: T022 alone (the CAPABILITIES token lands last, after A1-A3 pass). -> Wave 9: T023 alone (same file as T022). -> Wave 10: T024, T025, T026. -> Wave 11: T027 (stop at the tag). |
| **4 Polish** | Wave 1: T028, T029. -> Wave 2: T030 -> T031 (same file, T031 appends to T030's artifact). |

**The three hard gates**, each of which halts the checkpoint rather than being
worked around:

1. **T003/A2.2** -- if the reset or currency member is absent from the real
   installed component, the facade cannot be built as designed; return to research.
2. **T019/A3.3** -- a reload that cannot be shown to discard has not been proven,
   and CP2b does not start.
3. **T027** -- the crew prepares the release commit and stops; the tag is a
   maintainer act.

**Parallel opportunities**: T001+T002; T005+T006; T007+T008+T009 (and this trio is
independent of the entire parser track, so it can run concurrently with T003-T004);
T013+T014+T015; T024+T025+T026; T028+T029.

**Serialization you cannot avoid**: the facade (T010-T012) and the live tier
(T018-T021) each concentrate in a single file; the alias table (T016) needs the
property (T013) to exist or it raises at import time; and the CAPABILITIES token
(T022) is deliberately last, because a token present without a landed capability
behind it is a Constitution Principle V violation.
