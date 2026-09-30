# parser-check CP2 -- cycle 1 planning brief

**Produced by:** lex-lead, synthesising five recon lanes (explore-mcp,
explore-flexicon, domain, archivist, doc).
**Audience:** `/speckit.companion.plan`, and the spec-amendment pass that must run
before it.
**Status of the evidence:** recon is CLOSED. No further broad discovery cycle is
warranted. Every claim below is traceable to a named lane report in this directory.

---

## 0. How to read this document

Three things are in here and they are not interchangeable:

1. **Section 1-4: grounded facts** the plan must build on. These replace
   assumptions the spec currently makes.
2. **Section 5: the decision ledger.** Twenty-one questions, each marked
   `AUTHORITATIVE` (the user's, binding), `DECIDED` (mine, with rationale,
   binding on the plan) or `ESCALATE` (needs the human before the plan can be
   trusted).
3. **Section 6-7: spec amendments and decomposition.** Twelve edits that belong
   in `spec.md` *before* planning, and the split of CP2 into CP2a / CP2b with
   the evidence gate between them.

**Read section 5.0 first.** The user's sequencing constraint -- flexicon is
extended and proven before any MCP-side change -- reorders everything downstream
of it, and section 7.5 defines the gate it implies.

If you are the planner: apply section 6 first, then plan against sections 1-5,
then honour section 7's phasing.

---

## 1. The shape of the work, measured

| Part | Repo | Files | Character |
|---|---|---|---|
| A -- `project.Parser` facade + 3 read gaps + 4.9.0 release | `flexicon` | 10-13 | pattern-matched; one genuinely new mechanism (lazy probe) |
| B1 -- run machinery (FR-026..FR-036) | this repo | net-new | **100% greenfield; nothing to extend** |
| B2 -- `flextools_try_word` + `flextools_parse_status` | this repo | ~8 | mechanical registration over B1 |
| B3 -- morph-spec resolver (US3) | this repo | ~4 | net-new, highest correctness risk |
| C -- carry-overs (FR-037..FR-040) | this repo | ~8 | mechanical, exhaustively enumerated |

The two load-bearing sizing facts:

- **There is no job, queue, worker or durable run-record machinery anywhere in
  this repository.** `SessionState` is in-memory and process-lifetime;
  `run_script_async` is one `create_subprocess_exec` + `wait_for`, with no
  handle, no cancellation token and no progress channel; the only concurrency
  primitive on the request path is `kernel.project_write_locks`, a per-project
  `asyncio.Lock`. US4 extends nothing. (explore-mcp section 4.)
- **`flexicon` has zero parser-adjacent code.** Part A is greenfield but
  strongly pattern-matched: `BaseOperations` subclass + lazy `@property` with a
  `self.__dict__` guard and a function-local import, four sibling
  `GetOwningEntry` templates to copy, and a `CAPABILITIES` frozenset already
  designed to be probed. (explore-flexicon sections 1-3.)

**The only structural precedent worth reusing for the run record** is
`skeleton_storage.py:43-50` -- JSONL append under a `threading.Lock`, with an
env override for its directory. Durable artifact roots that already exist:
`~/.flextoolsmcp/{backups,reports,index}` and `kernel.get_log_dir()`.

---

## 2. What CP1 shipped that CP2 is the first to call

Both live in `src/flextoolsmcp/server/parser_probe.py`, both have **zero
callers today**, both are tested:

- `check_active_parser(project, *, supported_engines=("HC",))` at :714, raising
  `ParserEngineMismatchError` at :698 -- FR-015's engine gate.
- `probe_hc_agent(project, active_engine)` at :773, returning `AgentProbeResult`
  at :641 -- FR-016's agent probe.

FR-015 says the engine check is the **first action** of every handler that
reaches the parser. That is new wiring over shipped logic, not new logic.

The mechanism behind the engine gate is confirmed against source:
`LangProject.MorphologicalDataOA.ActiveParser` is a real string property reading
`/ParserParameters/ActiveParser`, with a hard `"XAmple"` fail-safe on any parse
exception. (domain section 8.)

---

## 3. Facts that contradict the spec as written

These are the four places the plan would go wrong if it trusted `spec.md`.

### 3.1 `Reload()` cannot be `Update()` alone (domain section 5)

`HCParser.Update()` is itself conditional:

```
if (m_changeListener.Reset() || m_forceUpdate) LoadParser();
```

so calling `Update()` on an unchanged model does nothing. FieldWorks' own
force-reload path is `ParserWorker.ReloadGrammarAndLexicon()`, which calls
`m_parser.Reset()` **then** `CheckNeedsUpdate()`. FR-043's "an explicit reload
request MUST discard the held grammar unconditionally" is therefore
**unsatisfiable** by the facade table in CP2-SPEC 3.1, which maps only
`Reload() -> Update()`.

Binding for the plan: `Reload()` = `Reset()` then `Update()`. `IsUpToDate()` is
the currency read FR-043's "confirmed before reuse" clause needs
(`HCParser.IsUpToDate() => !m_changeListener.ModelChanged`).

### 3.2 The bundled-index path in Verbatim Constraints does not exist (explore-mcp section 5)

Spec says `index/python/flexicon_api_v4.9.0.json`. Real root is
`src/flextoolsmcp/index/python/`, currently holding:

```
flexicon_api_v4.8.0.json
flexicon_lcm_bridge_v4.8.0.json
flexlibs_api_v1.2.8.json
flexlibs_lcm_bridge_v1.2.8.json
```

**The sibling bridge file is keyed to the same version and the spec never
mentions it.** Verified independently for this brief: `server.py:665` loads it
as `self._load_lcm_bridge("Flexicon", "flexicon_lcm_bridge", self.flexicon_version)`
and `handlers/equivalence.py:64` consumes `api.flexicon_lcm_bridge`. A 4.9.0
bump that produces only `flexicon_api_v4.9.0.json` leaves the equivalence
handler with **no bridge at all** for 4.9.0 -- a silent capability loss, not an
error. `refresh.py:217` already derives the bridge prefix
(`output_prefix.replace("_api", "_lcm_bridge", 1)`), so a full
`python -m flextoolsmcp.refresh` produces both; the risk is a hand-copied index.

Also: installed wheels read an overlay at `~/.flextoolsmcp/index`
(`file_utils.py:61`). Resolution is by glob
(`versioning.py:386 find_latest_versioned_api_file`), not by literal path.

### 3.3 Identity is object-level only in Mode B (domain section 7)

`HCParser.ParseWord`'s internal `MorphInfo` carries real `IMoForm`,
`IMoMorphSynAnalysis`, `ILexEntryInflType` references -- FR-010 is satisfiable
there. But `ParseWordXml` / `TraceWordXml` return an already-serialised
`XDocument` in which objects survive only as `Hvo` integer attributes
(`XAttribute("id", form.Hvo)`). For Modes A and C, FR-010 is satisfied **via
Hvo requiring a repository lookup to rehydrate**, not by object identity.

Do not plan a typed object-identity marshaller for the trace. Plan it for
`ParseWord` only.

### 3.4 The allomorph gap is a wrapper gap, not an LCM gap (domain section 6b)

LCM already exposes `MoForm.OwningEntry`
(`OverridesLing_MoClasses.cs:3113`, `[VirtualProperty(..., "LexEntry")]`),
inherited by `MoStemAllomorph` and `MoAffixAllomorph`. `AllomorphOperations`
merely never wrapped it, while calling the protected `_GetTypedOwner` internally
at `:350` and `:423`. FR-008 is a ~20-line wrapper with four sibling templates
to copy, not a research task.

The other two read gaps stand:

- **Genres (FR-007)**: real. `TextOperations.GetGenre()` returns
  `GenresRC.FirstOrDefault()`; needs a plural `GetGenres()`.
- **MSA reads (FR-009)**: real and the nontrivial one. `MSAOperations` is
  create/set/repair only; the MSA subtypes (`MoStemMsa`, `MoInflAffMsa`,
  `MoDerivAffMsa`) expose different property sets, so "a readable-properties
  surface" is not one flat wrapper. Raw building blocks exist at
  `lcm_casting.get_pos_from_msa:665` and `get_from_pos_from_msa:990`.

---

## 4. Constraints the plan must not discover the hard way

**Registration is a 6-site mechanical edit plus two test lists.** Declare in
`tool_definitions.py` `TOOLS` (nearest precedent: `flextools_grammar_health` at
:498); input model in `models.py` (`GrammarHealthInput` :564 is the pattern);
in `dispatch.py` add the name constant, the `ALL_TOOL_NAMES` frozenset entry,
the handler import **twice** (relative branch :155-157 AND absolute fallback
:197-199), the returned dict :223, the module-level rebind :249, and the
`DISPATCH_ROUTES` row. Then `tests/test_mcp_tools.py` `EXPECTED_TOOL_NAMES`
and `READ_ONLY_TOOLS` -- **both**, or the derived count test fails.

**`outputSchema` advertisement is deliberately disabled** (`server.py:822-834`).
Do not wire `output_model` expecting it to ship.

**`HCParser_DoesNotLoadXCore` must run in a child process, and the guarantee is
subtler than the spec implies.** `ParserCore.csproj` references
`xCoreInterfaces.dll` / `xCore.dll` / `FwUtils.dll` at assembly level; the
`using XCore;` statements are confined to `ParseFiler.cs`, `ParserScheduler.cs`
and `ParserWorker.cs` -- not `HCParser.cs`/`HCLoader.cs`/`IParser.cs`. All
compile into one assembly, so **the guarantee rests entirely on .NET's lazy
per-type assembly binding, not on the absence of a reference** (domain
section 9). The test must therefore assert on the *loaded-assembly list of the
process after a real `Update()` + `ParseWord()`.

CP1's `tests/test_cp1_boundary.py` is the design model (falsifiability
discipline: `class BoundarySpy` :694, the planted-violation suite :1191) **but
it uses in-process monkeypatched spies**, which cannot see a CLR assembly load.
The real parse must run where parses run -- the `run_scan_module`
(`execution.py:5060`) child via `run_script_async`
(`subprocess_helpers.py:56`) -- returning its loaded-assembly list over the
`===FLEXTOOLS_USER_RESULT===` sentinel. Keep CP1's rule: prove the probe *would*
have caught a planted XCore load.

**flexicon's lazy-load precedent raises; CP2's must not.**
`lcm_casting._ensure_interfaces()` (`:84`) is the right structural model --
module-global cache + loaded flag, optional interfaces caught as `None` rather
than raising (`:130-140`, `:147-153`, `:286`) -- but it still raises
`ImportError` when SIL.LCModel is absent entirely (`:103`). The
"unavailable-with-a-reason return value" that SC-001 demands is genuinely new.
Nearest deferred-load precedent: `clr.AddReference("FwUtils")` inside a function
body at `FLExGlobals.py:154`; every other `AddReference` is module-level.

**Four ratchets gate the 4.9.0 cut**, all in `flexicon/tests/`:
`test_297_init_stub_parity.py` (every public name in `__init__.py` must appear
in `__init__.pyi`'s `__all__` and vice versa),
`test_pyi_return_annotation_ratchet.py`, `test_docstring_example_ratchet.py`
(+ its `docstring_example_baseline.json` refresh), and
`test_flexlibs2_alias_ratchet.py`. Release order is fixed by
`docs/RELEASING.md` section 4: version constant -> CHANGELOG -> history.md ->
`RELEASE_NOTES_v4.9.0.md`, then push `main`, **then** tag -- the tag is what
publishes to PyPI.

**The same-install gate is directory equality only.** A foreign `ParserCore.dll`
copied *into* the correct install directory passes undetected (domain
section 2). Accepted; the alternative (load-and-invoke) is exactly what the
proxy exists to avoid.

**`Sena 3` cannot verify anything here** -- its engine is XAmple, so FR-015's own
gate refuses it. D3's per-project engine facts for `IndonesianHC-Complete` and
`Malay Parsing-20230810withHC` could not be re-confirmed statically and must be
re-read live as the first live task (domain section 8).

**CP1 carry-over work lists are exhaustive and ready to task** (archivist
sections 1-2): FR-038 has five named sites
(`diagnostic_health.py:298-301`, `:352-361`, the two docstrings at `:303-317`
and `:334-336`, `contracts/flextools_health-parser-block.md`'s two-row table
plus its "CP1 caveat" prose, and `tests/test_parser_health_block.py`'s negative
assertion which must **invert**). FR-039's four groups cite
`SPEC.md:2063-2068`, `:2119-2121`, `:2138-2141`, `:2141`, all excluded at
`tasks.md:204`.

---

## 5. Decision ledger

Twenty-one items. `DECIDED` is binding on the plan. `ESCALATE` blocks the item
it names and nothing else.

### 5.0 AUTHORITATIVE -- the user's standing sequencing constraint

**D-00. Part A (flexicon) is extended and PROVEN before any MCP-side change is
made. This is a hard predecessor phase, not interleaved work.**

*Source:* the user, on being shown the FR-043 finding: *"Refuted by LCM reality?
yes, this is exactly why I expected flexicon to be extended before making
changes to the MCP."* This is a standing constraint, not a preference available
for trade against convenience.

*The worked justification -- FR-043 is exactly the class of failure this
ordering exists to catch.* The finding is discoverable **only from the
flexicon/LCM side**, because it lives in the behaviour of
`HCParser.Update()`, not in any MCP-side artifact. Had the MCP tools been built
first against the spec as written, `Reload()` would have been implemented as
`Update()` alone. That does not fail. It does not raise. It does not log. On an
unchanged model `Update()` short-circuits at
`if (m_changeListener.Reset() || m_forceUpdate)` and returns, and the caller --
an MCP handler that believes it has just forced a fresh grammar -- serves the
next parse **from the stale grammar it thought it had discarded**. The user then
gets a confident, wrong answer about whether their word parses, after explicitly
asking for a reload.

That is the same failure class the spec already names as its top correctness
risk for the resolver ("a silently narrowed selection produces a confident wrong
answer about someone's grammar") and the same class D2's currency check exists
to prevent. It would have been caught only by a live test that made the model
stale -- i.e. late, after the MCP surface was built on the wrong assumption.
Settling the facade against LCM reality first turns a late live-integration
surprise into an early one-line binding decision. **One recon lane paid for the
whole ordering.**

*Binding consequences for the plan:*
1. No MCP-side file is touched until Part A's surface is settled and proven per
   section 7.5's evidence gate.
2. The decomposition question (formerly E-A) is **resolved: CP2 splits.** A
   single 55-task checkpoint has no way to express "Part A is done and proven"
   as a gate -- there is no artifact in an undifferentiated task list that says
   *stop here and check*. The seam is defined in section 7.
3. "Proven" is not "written and the ratchets are green". Section 7.5 defines it.

### 5.1 DECIDED -- bind the plan to these

**D-01. `Reload()` binds `Reset()` + `Update()`, not `Update()` alone.**
*Rationale:* FR-043's "unconditionally" is otherwise unsatisfiable --
`Update()` short-circuits on an unchanged model, and FieldWorks' own
force-reload path is `Reset()` then `Update()`. This is a factual correction,
not a preference. *Spec edit required (section 6, E2).*

**D-02. `IsUpToDate()` and `Reset()` join the flexicon-side capability probe's
required-member set; `parser_probe.py` is NOT touched.**
*Rationale:* the domain lane flagged that `HCPARSER_MEMBERS` omits both, and
CP2's whole currency story depends on them -- but FR-041/D1 and SC-016 forbid
changing `parser_probe.py` ("0 lines"). These reconcile cleanly under D1's own
logic: **each check probes what its own surface binds.** The facade binds
`Reset`/`IsUpToDate` (FR-001 requires reload and currency operations), so the
flexicon probe must verify them. The MCP's in-process probe binds neither --
its handlers reach the parser through the facade in a subprocess -- so it needs
neither. D1 is upheld and SC-016 stays green.
*Consequence to record:* after CP2 the two lists diverge **in both directions**
(MCP has the write op; flexicon has `Reset`/`IsUpToDate`). The spec's phrase
"this repository keeps its **larger** check" becomes false and must become
"different, overlapping". FR-041's mandate that each check *state* the
divergence is deliberate now has two directions to state.
*Residual risk, accepted and documented:* the MCP health block could report the
parser capable on an install where the facade will refuse for a missing
`Reset`. Plan a one-line note in each check pointing at the other.
*Spec edit required (section 6, E3).*

**D-03. `parse_morph_unresolved` carries FIVE fields, including
`resolved_to` (`none` | `ambiguous` | `no_msa`).**
*Rationale:* the parent `SPEC.md` section 14 (line ~1987) is the authority and
carries five; `CP2-SPEC.md` section 7 dropped `resolved_to` silently. The three
values are exactly the distinctions 5.1.2 must make, and the spec's own edge
cases list both "matches a headword but that headword carries no usable
analysis" (`no_msa`) and "matches several homographs, or several allomorphs of
one entry" (`ambiguous`) as *separate* cases. Collapsing them into a bare
refusal reproduces the silent-narrowing failure mode FR-023 and SC-005 exist to
prevent. Reconcile **toward the parent spec and the more informative form.**
*Spec edit required (section 6, E7).*

**D-04. `flextools_parse_status` NEVER returns `status:"error"` for a
cancelled or failed run. It returns a success envelope carrying
`state: "cancelled" | "failed"`.**
*Rationale:* asking about a dead run is a successful query, not a failed
request. The requirements are unambiguous once read together: FR-033 says the
status tool reports, on a terminal stage, "the result summary **or the failure
with its guidance**"; FR-034 requires a failed run to *carry* guidance; FR-036
requires a cancelled run to be *reportable* with `words_completed` and
`state_at_cancel`; SC-008 requires partial results to stay readable. An error
envelope by convention carries no result payload -- it would make SC-008
unreportable through the very tool FR-033 provides for it.
*Therefore:* `parse_job_cancelled` fires only from **other** calls that would
*act on* a dead run (a second cancel request; a `try_word` attaching to a run
cancelled elsewhere). The only error `parse_status` emits is
`parse_run_not_found`, which FR-035 explicitly words as a refusal.
*Confidence:* high on the reading; the decision is cheap to reverse at plan
review if the maintainer disagrees, since it changes contract prose and one
handler branch, not architecture.
*Spec edit required (section 6, E8).*

**D-05. The inline-vs-handle discriminator is the presence of `result`.
`run_id` is present in BOTH shapes.**
*Rationale:* FR-026 says all parser execution goes through one run mechanism --
so a run exists even on the fast path, and withholding its id would be a lie
about the architecture. It also matters concretely: D-06 puts the trace payload
in the run artifact, so a Mode C answer that returns inline still needs its
run's artifact pointer. Precedent for one tool emitting materially different
`status:"ok"` shapes keyed on which keys are present is `run_module`'s
`discovery_redirect`. Shape: always `run_id` + `state`; `result` present =
terminal inside the grace window, `result` absent = poll `parse_status`.
Document as a named block in the contract file, the way `RunModuleSuccess`
fields are documented -- not implicitly.

**D-06. The trace payload lives in the run artifact; the response carries a
summary plus a pointer field.**
*Rationale:* already settled by the spec's own Assumptions ("Trace explanations
are persisted to the run's record rather than embedded in responses") and by
CP2-SPEC 5.5. The doc lane's contribution is the precedent -- `diagnostic_report.report_path`
and the 10-line casting-warning cap -- confirming the house style. No spec
change; the plan must name the pointer field and the summary shape explicitly
rather than leaving it to the implementer.

**D-07. FR-040: the three grammar lints are DEFERRED AGAIN, to CP3, and the
deferral is recorded.**
*Rationale:* the premise that motivated folding them in is refuted.
`SIL.Machine.Morphology.HermitCrab.GrammarHealthChecker` is **absent outright**
from the installed assembly (v3.8.2.0) -- a fully-resolved 195-type scan found
no type named `GrammarHealthChecker` and none containing `Grammar`, `Checker`
or `Health` (`research.md:290-324`). "Fold in" therefore means writing three
lints from scratch against LCM/HermitCrab data, with independent correctness
risk, inside a checkpoint already classified OVERSIZED and already carrying
100% net-new run machinery. FR-040 requires only that the decision be *made and
recorded* -- it does not require inclusion. SPEC 9.5.6 already adopts PanGloss
vocabulary for the checks that do ship, so this leaves a **named** gap, not a
silent one.
*Rider:* D10's probe is HermitCrab-version-specific. CP3 must re-probe, not
reuse the cached verdict. *Spec edit required (section 6, E10).*

**D-08. The Verbatim Constraint index path is corrected to
`src/flextoolsmcp/index/python/flexicon_api_v4.9.0.json`, and the constraint is
widened to cover the full refresh output for 4.9.0.**
*Rationale:* the current string is repo-root-relative and does not exist on
disk, and Verbatim Constraints are by definition used as written by downstream
steps -- this one would be copied into a task and fail. Widening matters more
than the path fix: `flexicon_lcm_bridge_v4.9.0.json` is loaded by
`server.py:665` keyed to the flexicon version and consumed by
`handlers/equivalence.py:64`; shipping only the api file silently removes the
bridge for 4.9.0. Phrase the constraint as "the complete output of
`python -m flextoolsmcp.refresh` for 4.9.0, which currently comprises
`flexicon_api_v4.9.0.json` and `flexicon_lcm_bridge_v4.9.0.json`" so it does not
drift as refresh's output set changes. SC-013's "the bundled index" becomes
"every bundled flexicon index artifact". *Spec edit required (section 6, E1, E11.)*

**D-09. FR-010 is amended to state that identity is object-level for
`ParseWord` and Hvo-only inside the XML trace.**
*Rationale:* section 3.3. This is not a weakening of the requirement -- the spec
already assumes "the trace explanation crosses unchanged" -- it is making the
consequence explicit so nobody plans a typed marshaller for an `XDocument`.
*Spec edit required (section 6, E5).*

**D-10. The named-vs-positional edge case names `ParseWordXml` and
`TraceWordXml` specifically; FR-005's positional-binding rule stays universal.**
*Rationale:* `HCParser.ParseWord(string word)` actually **matches** the
interface; only `ParseWordXml(string form)` and `TraceWordXml(string form, ...)`
diverge (`word` vs `form`). Naming them makes the edge case testable. Keeping
FR-005 universal costs nothing and defends against future drift.
*Spec edit required (section 6, E6).*

**D-11. FR-008's framing is corrected to a wrapper gap.**
*Rationale:* section 3.4. Changes the deliverable's cost, so it changes the
plan. *Spec edit required (section 6, E4).*

**D-12. Add a standing test that the documented error-code count cannot drift.**
*Rationale:* the count "22" is currently hand-maintained in at least five places
(`docs/TOOL-CONTRACT.md:69`, `response_models.py:10`/`:423`/`:491`,
`contracts/error-codes.md:3`) and **no test asserts it**;
`tests/test_parser_error_models.py` validates models but not the count. CP1
already had to fix it in three in-file sites it did not expect. CP2 is the
second bump (22 -> 25). Derive the count from the `AnyDetail` union and assert
the doc table matches. Cheap, and it makes the third bump safe.

**D-13. `CLAUDE.md`'s "18 error codes" is stale and is corrected to 25 as part
of CP2's contract work.**
*Rationale:* trivially true (the count has been 22 since CP1); it is a documented
figure an assistant reads. The doc lane found no other `CLAUDE.md` count
reference.

**D-14. The `HCParser_DoesNotLoadXCore` test runs in the `run_scan_module`
child process, not in-process, and its rationale records the lazy-binding
mechanism.**
*Rationale:* section 4. CP1's boundary-test spies are in-process and structurally
cannot observe a CLR assembly load; and the guarantee is *not* "ParserCore does
not reference xCore" (it does) but "the HC parse path touches no xCore type".
Writing the wrong rationale into the test would make a future maintainer
"simplify" it into a class-level check -- exactly what FR-017 forbids.

**D-15. `Sena 3` stays ruled out; both live projects' `ActiveParser` is
re-read live as the first live-verification task.**
*Rationale:* D3's per-project facts are unverifiable without opening the
`.fwdata` files. They are almost certainly right (they were read during
specification), but a live plan should not open with an unre-verified premise
when re-verifying costs one read-only call. Not a blocker, a task ordering.

**D-16. `"parser"` joins flexicon's `CAPABILITIES` frozenset, and this
repository probes it.**
*Rationale:* `flexicon/__init__.py:67` already exists with a documented
`getattr(flexicon, "CAPABILITIES", frozenset())` probe contract
(`docs/FLEXTOOLSMCP_WRITE_CONTRACT.md` section 3). It is the cheapest honest
seam for "is the facade present in the installed version", and it degrades
correctly on 4.8.0 (token absent). Use it; do not invent a version comparison
-- FR-006/SC-002 forbid version floors on the *parser*, and a capability token
is the idiom this pair of repos already agreed on.

### 5.2 ESCALATE -- needs the human

**E-A. RESOLVED by the user -- see D-00.** CP2 splits; Part A is a hard
predecessor phase. Retained here only so the ledger records that the question
was asked and answered, not dropped. No longer blocking.

**E-B. Is the maintainer content that `flextools_parse_status` never returns an
error envelope for a terminal run (D-04)?**
I decided it on the requirement text and I stand behind it, but it is the one
decision where a maintainer preference could reasonably differ from what the
requirements imply, and it is baked into a contract file the moment planning
starts. *Recommendation:* accept D-04; flag at plan review rather than blocking
now. Cost to reverse after planning but before implementation: low. After
implementation: moderate.

**E-C. The flexicon 4.9.0 release is a hard serialisation point. When?**
FR-011 says the library must be released before assistant-side work is tested
against it, and the tag is what publishes to PyPI. Nothing in the crew's control
schedules this. Under D-00 this is now unambiguously **CP2a's exit gate** and
needs no interim workaround -- but the tag push and the `gh release create` are
maintainer acts, not crew acts. *Recommendation:* CP2a ends with the release
commit prepared and the ratchets green; the tag is the human's to push, and the
spurt loop must hand off rather than tag.

**E-D. Proving FR-043's STALE half requires a WRITE to a FLEx project.**
This is the one genuine live-authorisation item and it was not visible until
D-00 forced the question of what "proven" means. FR-043 has two halves:

- *"an explicit reload MUST discard unconditionally"* -- provable read-only
  (section 7.5, gate A3): the no-change case needs no model change by
  construction.
- *"a held grammar MUST be reloaded when it reports stale"* -- **not provable
  read-only.** `IsUpToDate()` returns `!m_changeListener.ModelChanged`, and the
  only thing that sets `ModelChanged` is an actual LCM change under a unit of
  work. Making a grammar stale means editing the project.

*Options:* (a) prove the stale path offline against a stubbed change listener at
CP2a, and defer the live proof to CP2b's live verification on a backed-up or
copied project; (b) authorise a live write on a `-restore`able target now.
*My recommendation:* **(a).** The stale path's logic is a branch on a boolean the
facade reads -- a stub settles the branch honestly, and the live half is worth
running once, later, against a scratch copy where a backup already exists.
CP2a therefore needs **no destructive write and no human authorisation**. When
CP2b reaches the live stale test, the loop must stop with `needs_human` per the
standing rule; do not let it write unattended.

---

## 6. Spec amendments required BEFORE planning

`/speckit.companion.plan` reads `specs/parser-check-cp2/spec.md` as truth. Four
of these eleven edits fix statements that are **factually false** or
**unsatisfiable as written**; planning against them produces tasks that cannot
be completed. Run a single amendment pass first.

| # | Target | Edit | Blocking? |
|---|---|---|---|
| E1 | Verbatim Constraints, "Bundled index file" | `src/flextoolsmcp/index/python/flexicon_api_v4.9.0.json`, widened to the full refresh output incl. `flexicon_lcm_bridge_v4.9.0.json` (D-08) | **YES** -- string is used verbatim |
| E2 | FR-043 + D2 rationale | explicit reload = `Reset()` then `Update()`; currency read = `IsUpToDate()` (D-01) | **YES** -- unsatisfiable as written |
| E3 | FR-041, D1, SC-016, Assumptions | "larger check" -> "different, overlapping"; record that the flexicon list adds `Reset`/`IsUpToDate` while the MCP list keeps the write op; both must state the divergence in both directions (D-02) | **YES** -- SC-016 is measurable |
| E7 | FR-037 + the CP2-SPEC section 7 table | `parse_morph_unresolved` = 5 fields incl. `resolved_to` (`none`\|`ambiguous`\|`no_msa`) (D-03) | **YES** -- contract cannot be drafted otherwise |
| E8 | FR-033, FR-036 | `parse_status` always returns a success envelope on terminal stages; `parse_job_cancelled` fires only from calls that *act on* a dead run (D-04) | **YES** -- same reason |
| E5 | FR-010 | identity is object-level for `ParseWord`, Hvo-only inside the XML trace (D-09) | near-blocking -- drives marshalling design |
| E4 | FR-008 + Key Entities | allomorph->owning-entry is a flexicon wrapper gap; LCM has `MoForm.OwningEntry` (D-11) | no, but changes cost |
| E6 | Edge Cases, 2nd bullet | name `ParseWordXml` and `TraceWordXml` (D-10) | no |
| E9 | FR-004 | one line: the check is directory equality, so a foreign DLL copied into the install dir passes | no |
| E10 | FR-040 + a research note | record the DEFER-AGAIN decision with D10's absence evidence and the re-probe rider (D-07) | no, but FR-040 demands a recorded decision |
| E11 | SC-013 | "the bundled index" -> "every bundled flexicon index artifact" (D-08) | no |
| E12 | new Decision `D4`, plus FR-011 and the Risks "Schedule" bullet | record D-00: Part A is a hard predecessor phase, proven per the A1-A3 evidence gate before any MCP-side parser work; CP2 splits into CP2a / CP2a-bridge / CP2b | **YES** -- it is the ordering the whole plan is built on, and it currently exists nowhere in the spec |

**Recommended executor:** `lex-doc`, one task, all twelve edits, applied to
`specs/parser-check-cp2/spec.md` (and the one table row in
`specs/parser-check/CP2-SPEC.md` section 7 for E7, so the two documents stop
disagreeing).

---

## 7. Decomposition recommendation

**DECIDED (D-00, user-authoritative): CP2 splits into two checkpoints, with the
seam at "Part A proven".** What follows is where the seam goes and why that
placement is the right one.

### Why split, and why this seam

Three independent forces land on the same line, which is why it is the right
seam rather than merely an available one:

1. **The user's sequencing constraint (D-00).** Part A must be proven before any
   MCP-side change. A single 55-task checkpoint cannot express that gate --
   there is no artifact in an undifferentiated task list that says *stop here and
   check*, so the constraint would survive only as a convention, and conventions
   lose to a task list that says a `[P]` pair is parallelisable.
2. **FR-011's release gate.** Nothing on the assistant side can be tested against
   a published dependency until the 4.9.0 tag lands, and the tag is what
   publishes to PyPI. A checkpoint spanning that has a mandatory stall built into
   its own task graph.
3. **US1 is independently deliverable on speckit's own terms.** The spec's "Why
   this priority" says it "is the only slice with standalone value on day one";
   its Independent Test needs no MCP tool; every acceptance scenario is
   library-level.

The FR-043 finding is the worked proof that (1) is load-bearing rather than
stylistic -- see D-00. Note what it implies about the *order of the gates*: the
constraint is "Part A **proven**", not "Part A **released**". Proving comes
first and is the gate that matters; the release is the mechanical consequence.
Placing the seam at "released" alone would let the facade be written, tagged and
published with `Reload()` bound wrong.

### Proposed shape

**CP2a -- the library (`flexicon` 4.9.0), in the `flexicon` repo only.** US1
entirely: `ParserOperations` facade with the lazy capability probe (including
`Reset` and `IsUpToDate` per D-02), `GetGenres()`, `GetOwningEntry()`, the MSA
read surface, the `"parser"` CAPABILITIES token, the four ratchets, and the
release cut. ~13 files. **Exit gate: section 7.5's evidence, then the tag.**

**CP2a-bridge -- the dependency bump, in this repo.** The
`pyflexicon>=4.9.0,<5` floor in `pyproject.toml` and `requirements.txt`, the
refreshed index artifacts (`flexicon_api_v4.9.0.json` **and**
`flexicon_lcm_bridge_v4.9.0.json`, per D-08), and the floor/index-equality test
(`tests/test_dependency_bounds.py:64` is the regex template). ~4 files.

This is deliberately called out as its own slice rather than folded into either
side. It touches this repo, so under a literal reading of D-00 it is "an
MCP-side change" -- but it is a dependency declaration, not parser work, and it
is the mechanical consequence of the release rather than anything built on the
facade. Treat it as CP2a's landing strip: it runs **after** the tag and
**before** CP2b's first parser task, and it changes no handler, no tool and no
contract. Naming it separately is what stops it being quietly used as a
precedent for starting CP2b early.

**CP2b -- the tools (this repo).** US2, US3, US4 and the cross-cutting
carry-overs. ~17 files. **Entry gate: CP2a's evidence is recorded and the
bridge has landed.**

### 7.5 What "proven" means for Part A -- the gate CP2b may not start without

D-00 says *extended and proven*. Ratchets passing is not proof: all four
flexicon ratchets are structural (stub parity, return-annotation agreement,
docstring examples, alias stability) and **every one of them would have passed a
`Reload()` bound to `Update()` alone.** The gate must therefore include
behavioural evidence, and the FR-043 finding sets the bar for what counts.

Four tiers, cheapest first. **A1-A3 are required. A4 is explicitly deferred.**

**A1 -- Offline, no FieldWorks, no project.** Runs anywhere, including CI.
- Import succeeds on a machine with no `ParserCore.dll`; `project.Parser` reports
  unavailable **with a reason** and raises nothing (SC-001). This is the one that
  needs care: flexicon's only lazy-load precedent,
  `lcm_casting._ensure_interfaces()`, **raises** at `:103` rather than
  degrading, so the degrading return value is new code with no template to copy.
  Test it by simulating absence, not by assuming it.
- No code path compares a detected parser version against a minimum -- 0
  occurrences, standing test on the flexicon side (SC-002).
- The facade binds positionally, asserted structurally.
- FR-002's absence claim: no write/record/file method on the surface, asserted by
  enumeration rather than by inspection, because the read-only safety claim of
  both new MCP tools rests on it.
- FR-043's **stale** half against a stubbed change listener (E-D option (a)).

**A2 -- Reflective, FieldWorks installed, no project opened.** No LCM cache, so
no project, so no write risk at all.
- Every member the facade binds exists on the real installed `ParserCore.dll`:
  `HCParser(LcmCache)`, `Update`, `Reset`, `IsUpToDate`, `ParseWord`,
  `ParseWordXml`, `TraceWordXml`. **`Reset` and `IsUpToDate` are the two the
  shipped MCP-side probe does not check** (D-02) -- this is their first
  verification anywhere, and it is the direct remediation of the domain lane's
  finding.
- Same-install directory equality holds on this machine.
- Detected version is reported and unused.

**A3 -- Live, read-only, one project open. The gate that actually settles
FR-043.** Requires a real project, so `IndonesianHC-Complete` (41 entries, 3
rules -- small enough that a cold grammar load stays fast). Read-only: no write,
no `-restore`, **no human authorisation needed.**
- `HCParser(cache)` constructs and a real `Update()` loads a grammar.
- A word parses via `ParseWord`, and a trace returns via `TraceWordXml`.
- **The unconditional-discard proof.** With no model change between calls:
  `Update()` alone must NOT reload, and `Reload()` MUST. The observable witness
  is a fresh morpher: `LoadParser()` replaces the internal morpher instance, so
  compare its identity across each call. That is a private field read under
  pythonnet -- acceptable in a test that documents itself as such, and it is the
  only direct witness. Fall back to the `{ProjectName}HCLoadErrors.xml` side
  file's rewrite (CP1 already treats it as the load signal) if the field read
  proves unreliable. **A `Reload()` that cannot be shown to discard has not been
  proven, and CP2b does not start.**
- FR-010's Mode B claim: `ParseWord`'s results carry live `IMoForm` /
  `IMoMorphSynAnalysis` references, not strings (section 3.3).
- D-15's rider: re-read `ActiveParser` on both live projects and confirm `HC`.

**A4 -- deferred to CP2b, with authorisation.** FR-043's stale half proven
live, which requires editing the project to set `ModelChanged` (E-D). Not part
of this gate. When CP2b reaches it, the loop stops with `needs_human`.

**The recorded artifact.** CP2a ends by writing the A1-A3 results into the
checkpoint's own evidence file -- not into a passing-test count. The reason is
D-00's: the next phase is authorised by *what was observed*, not by a green
suite, and a future maintainer asking "how do we know `Reload()` discards?"
must find an answer that is not "there is a test named that".

### Phasing inside CP2b -- the part that matters most

US4 is numbered P4 by *value* and the planner will be tempted to schedule it
last. **It must be built first.** The spec's own risk section rules out a second
execution model ("Shipping the tool synchronously and adding the machinery later
is explicitly ruled out"), and FR-026 makes the run mechanism the sole path. A
`try_word` built before the runner exists has nowhere to run.

Resolve the tension by **splitting US4 into two things**:

1. **Runner foundation (Phase 2 / Foundational, not a user story):** run record
   + stages + the priority queue + cooperative cancellation + the grace window.
   No user-visible surface. This is the 100% greenfield block.
2. **Lifecycle visibility (stays US4, a real story):** `flextools_parse_status`,
   cancel, interleave, partial-result survival -- the acceptance scenarios a user
   can actually observe.

Then CP2b's sequence is: Foundational (runner) -> US2 (`try_word`, modes B and C)
-> US3 (mode A resolver -- the highest correctness risk, and the one that most
benefits from landing on proven plumbing) -> US4-visible -> carry-overs
(FR-037..FR-040, all mechanical and exhaustively enumerated by the archivist).

### A further split trigger inside CP2b

The CP2a/CP2b split is settled. CP2b may still be too big on its own: name this
trigger in the plan rather than discovering it mid-spurt. **If CP2b's task count
exceeds ~35 after `/speckit.companion.tasks`, split US3 out as CP2c.** US3 is
the cleanest late cut -- it is the only story whose failure mode is a confidently
wrong linguistic answer rather than a missing feature, and modes B and C ship
without it.

### On `lex-simplify`

**Holding it to cycle 2 still holds, but retarget it.** There was nothing to
simplify during recon. There is now exactly one high-value target: **the runner
design**, once `/speckit.companion.plan` has produced it. Ten requirements
(FR-026..FR-036) of net-new infrastructure, in a repository whose only
concurrency primitive is a per-project `asyncio.Lock`, is precisely where an
over-built design would be both easy to write and expensive to carry into CP3
(which "consumes CP2's runner; adds no second execution model"). Dispatch
`lex-simplify` **after** planning, against the runner design specifically --
not before, and not against the spec.

---

## 8. What the next spurt does, in order

1. **Cycle 2:** `lex-doc` applies the twelve section-6 amendments to
   `specs/parser-check-cp2/spec.md` (plus the one table row in
   `specs/parser-check/CP2-SPEC.md` section 7 for E7). One task. E12 is the
   biggest of them -- it writes D-00 and the three-way split into the spec.
2. **Then `/speckit.companion.plan`** against the amended spec, planning
   **CP2a only**. Under D-00 there is no reason to plan CP2b in detail yet:
   its shape depends on what Part A's surface actually turns out to be, and
   planning it now would re-create exactly the "MCP built on unproven
   assumptions" posture the ordering exists to prevent. Plan CP2b after the
   A1-A3 evidence lands.
3. **Cycle 3:** review of the CP2a plan -- `lex-domain` on the facade's LCM
   bindings (the FR-043 lesson says this is where the value is) and `lex-qc` on
   the plan's task structure.
4. **CP2a implementation**, ending at the A1-A3 evidence gate. The tag is the
   maintainer's to push (E-C); the loop hands off rather than tagging.
5. `lex-simplify` enters when CP2b's runner design exists, not before.

Recon is closed. No further discovery dispatch is warranted.

---

## 9. Conflicts between lanes, recorded

Two, both resolved above rather than papered over:

1. **domain vs. the spec's own D1.** The domain lane requires `Reset()` and
   `IsUpToDate()` in "the capability probe's required-member set", naming
   `parser_probe.py`; FR-041 and SC-016 forbid changing that file at all.
   Resolved by D-02 -- each check probes what its own surface binds, so the
   requirement lands on the flexicon-side probe and D1 survives intact. The
   cost is that "larger check" becomes false (spec edit E3).
2. **doc lane vs. `CP2-SPEC.md` section 7.** Field-count drift on
   `parse_morph_unresolved`, 4 vs 5. Resolved by D-03 toward the parent
   `SPEC.md`'s five. Not a conflict between reviewers -- a pre-existing
   contradiction between two spec documents that the doc lane surfaced.

No lane contradicted another on a matter of fact. Where two lanes touched the
same ground -- the error-code count -- they agreed independently at 22
(archivist section 4, doc section 2), which is why D-12's drift test is worth
having rather than a third manual verification.
