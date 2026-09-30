# Phase 0 Research: parser-check CP2a

Decisions taken before design, each with the alternative rejected. Every
claim about the `flexicon` codebase below carries a `file:line` citation,
per Constitution Principle I -- no design here assumes a member exists.

Citations are relative to `D:\Github\_Projects\_LEX\flexicon` unless the
path says otherwise.

---

## Findings that changed the plan's shape

Four things turned out differently from the cycle-1 brief's assumptions.
They are recorded first because the decisions below depend on them.

### F1 -- `import flexicon` requires FieldWorks (contradicts tier A1 as briefed)

`flexicon/__init__.py:76` imports from `.code.FLExInit`. `FLExInit.py:45`
calls `FLExGlobals.InitialiseFWGlobals()` **at module scope**, which
resolves the FieldWorks registry key and raises a bare `Exception` at
`FLExGlobals.py:82` (`"%s FieldWorks %s not found"`) when it is absent.

So on a machine with no FieldWorks, `import flexicon` fails outright. The
cycle-1 brief's tier A1 -- *"Offline, no FieldWorks, no project. Runs
anywhere, including CI"*, whose first check is *"Import succeeds on a
machine with no ParserCore.dll; project.Parser reports unavailable"* --
cannot be executed as written, because the import it depends on is the
thing that fails.

Note the package asserts the opposite of itself. The comment at
`flexicon/__init__.py:395-399` reads *"`import flexicon` still works on a
machine with no FieldWorks installed"*. That is true of `lcm_casting` in
isolation (it imports only `logging` at module scope, `lcm_casting.py:80-81`)
and false of the package that imports it. **This is a pre-existing
documentation defect in flexicon, not something CP2a introduces or is
obliged to fix.** It is recorded here so the next person does not trust it.

**SC-001 survives intact.** Its text is *"On a machine where the parser
component is absent, relocated or from a different installation"* -- the
parser component, not FieldWorks. That scenario is real, reachable and
testable. Only the brief's tier framing was wrong.

### F2 -- there is no "unavailable with reason" template anywhere

Confirmed by exhaustive search. flexicon has exactly two shapes for a
missing CLR type:

- **Raise.** `BaseOperations.py:1938-1948` resolves an interface by name and
  raises `FP_ParameterError` when absent, with the comment at `:1950-1953`
  stating the intent: *"must raise TypeError loudly ... silently falling
  back ... would defeat the entire point"*. Roughly sixty further
  function-scoped `from SIL.LCModel import ...` sites are bare and raise.
- **Silently become `None`.** `lcm_casting.py:130-141`, `:147-153`,
  `:450-468` degrade per type into `X = Y = None`, and `:483-484` simply
  omits the cache entry. No reason is recorded and no log line is emitted.

There is no `is_available` property, no health check and no feature probe
carrying a reason in the package. The one capability construct,
`CAPABILITIES` (`flexicon/__init__.py:67-72`), is a static *build*
manifest, and `:31-33` warns explicitly that a token means "this build
implements it", **not** "active in your session". It cannot answer a
runtime question.

The degrading return is therefore genuinely new code. It must be tested by
simulating absence, not by assuming it.

### F3 -- the MSA read surface is already written and never used

`MorphosyntaxAnalysis` (`flexicon/code/Lexicon/morphosyntax_analysis.py:74`)
is complete: `is_stem_msa` / `is_deriv_aff_msa` / `is_infl_aff_msa` /
`is_unclassified_aff_msa` (`:114`, `:130`, `:147`, `:163`), a common
`pos_main` (`:181`), subtype-conditional `has_from_pos` / `pos_from` /
`pos_to` (`:205`, `:235`, `:264`), the narrowing family `as_*_msa`
(`:293`, `:321`, `:346`, `:371`) and an escape hatch `concrete` (`:397`).
Its collection `MSACollection` (`flexicon/code/Lexicon/msa_collection.py:76`)
is equally complete, with `stem_msas` / `deriv_aff_msas` / `infl_aff_msas`
/ `unclassified_aff_msas` (`:220`, `:244`, `:268`, `:292`).

Neither is ever instantiated. `MSAOperations` (`MSAOperations.py:115`) is
write and lifecycle only -- `CreateStem:158`, `CreateDerivAff:197`,
`CreateInflAff:246`, `CreateUnclassifiedAffix:303`, `SetStemMsaPos:335`,
`RemoveOrphaned:676` -- with **no `GetAll` and no per-property reader**.
`MSACollection` appears in the package exactly once, in a docstring at
`MSAOperations.py:151`.

The cycle-1 brief called MSA reads *"the nontrivial one, since the MSA
subtypes expose different property sets, so it is not one flat wrapper"*.
That reasoning is correct about the shape and wrong about the cost: the
polymorphic wrapper it implies already exists. FR-009 is wiring.

### F4 -- FR-007 fixes a literal `FirstOrDefault()`

`TextOperations.GetGenre` (`flexicon/code/TextsWords/TextOperations.py:660`)
reads `text_obj.GenresRC.FirstOrDefault()` and returns `None` when the
collection is empty. FR-007 -- *"read all genres assigned to a text, not
only the first"* -- is therefore not an abstract gap; it names this call.
`GenresRC` occurs only on `IText` in LCM; there is no entry-level or
sense-level genre field to expose.

---

## Decisions

### D-A1 -- Re-tier the evidence gate: A1 runs with FieldWorks present, parser component absence simulated

**Decision.** Tier A1 keeps its content and loses its "no FieldWorks,
runs anywhere including CI" framing. It runs on a developer machine with
FieldWorks installed, and simulates the parser component's absence by
monkeypatching the facade's own resolution cache. Tier names and the
A1/A2/A3-required, A4-deferred structure are unchanged.

**Rationale.** F1 makes the briefed framing unexecutable. The framing was
also doubly wrong: no CI workflow runs pytest on a hosted runner at all,
and the self-hosted `[windows, fieldworks]` pool that `upstream-compatibility-check.yml:167`
targets has zero registered runners, so nothing in A1 was ever going to run
in CI regardless. The template to copy is
`tests/test_public_casting_export.py:98-117`, which monkeypatches
`lcm_casting._interfaces_loaded` and `_interface_cache` to simulate a
failing CLR cast without FieldWorks, paired with `:127-153`, which
AST-asserts that no module-scope `SIL` import exists. Mirroring both gives
the simulation *and* a standing control that the laziness cannot regress
(Principle III).

**Alternatives considered.**
- *Make `import flexicon` work without FieldWorks so A1 runs as briefed.*
  Rejected: that is a package-wide refactor of the import chain, entirely
  outside US1, and it would put a large unrelated change inside the
  checkpoint whose whole purpose is proving one small surface.
- *Drop the offline tier and fold its checks into A2.* Rejected: the
  checks differ in kind. A2 asks "does this member exist on the real
  DLL"; A1 asks "what happens when it does not". Losing A1 loses SC-001's
  only direct test.

### D-A2 -- `ParserOperations` gets its own domain package

**Decision.** `flexicon/code/Parser/ParserOperations.py`, with
`flexicon/code/Parser/__init__.py`, rather than placing the class in
`Lexicon/` or `TextsWords/`.

**Rationale.** Every other Operations class wraps the data model, which is
present whenever the package imports. This one wraps a different assembly
(`ParserCore.dll`) with an independent availability lifetime. The package
boundary is what makes "this entire area can be unavailable" a structural
fact rather than a convention. Precedent for a per-domain package is
uniform: `Grammar/`, `Lexicon/`, `Lists/`, `Notebook/`, `Reversal/`,
`Scripture/`, `Shared/`, `System/`, `TextsWords/`.

**Alternatives considered.** *Put it in `Grammar/`, since parsing uses the
grammar.* Rejected: `Grammar/` wraps grammar *data* (`IMoStratum`,
`IPhPhoneme`), which lives in the same assembly as everything else. Co-locating
a differently-available surface there would invite a future contributor to
assume it is equally available.

### D-A3 -- The accessor is singular: `project.Parser`

**Decision.** `project.Parser`, not `project.Parsers`.

**Rationale.** `_op_aliases.py:6-8` states the rule: plural for collection
namespaces, singular where the namespace is a service or facade rather than
a collection. The singular precedents are exactly the service-shaped ones --
`POS` (`FLExProject.py:1622`), `MSA` (`:2212`), `Discourse` (`:2787`),
`ProjectSettings` (`:2916`). A parser is a service; there is no collection
of parsers. `_op_aliases.py:79-84` already carries a plural-guess section,
so `Parsers -> Parser` is registered there for discoverability.

**Alternatives considered.** *Plural for consistency with the 45 plural
accessors.* Rejected: that majority is a majority of collections, not a
naming style, and the alias table exists precisely to absorb the wrong
guess.

### D-A4 -- Unavailability is a returned status object with a reason, not an exception and not `None`

**Decision.** The parser area always constructs. Availability is answered
by a status value carrying a boolean and a human-readable reason string.
Operations called on an unavailable parser raise a flexicon exception whose
message is that same reason; asking *whether* it is available never raises.

**Rationale.** SC-001 requires import to succeed and access to "report
unavailable with a reason instead of raising", so the probe cannot raise.
It cannot return bare `None` either: Principle VI holds that behaviour
changing what happens to a user's data must surface in return values rather
than be smoothed away, and a bare `None` is precisely the smoothing that
`lcm_casting.py:483-484` already does without recording a reason. F2
establishes there is no third shape in the package today, so this is new
code with no template -- which is itself the argument for making the shape
explicit and testable rather than implicit.

The reason string must state *what was checked*, not imply more. FR-004
accepts that a foreign component copied into the correct installation
directory passes undetected; per Principle V the docstring says so, so the
API does not imply a validation it does not perform.

**Alternatives considered.**
- *Raise on access, matching `BaseOperations.py:1938-1948`.* Rejected:
  contradicts SC-001 directly.
- *Return `None` silently, matching `lcm_casting`.* Rejected: loses the
  reason, which is the part SC-001 actually requires, and violates
  Principle VI.

### D-A5 -- Reload binds as reset-then-reload, two steps, never a bare update

**Decision.** The reload operation performs the reset of the change
listener and *then* requests the grammar update. The currency question
binds to the parser's own up-to-date read.

**Rationale.** This is cycle 1's central finding and the spec's amended
FR-043. `HCParser.Update()` is guarded by
`if (m_changeListener.Reset() || m_forceUpdate) LoadParser();`, so on an
unchanged model it short-circuits and does nothing. Binding an
unconditional-discard promise to it would produce exactly the fiction
Principle I exists to prevent: the call returns successfully, the caller
believes the grammar was discarded, and the next parse is served from the
stale one. FieldWorks' own force-reload path,
`ParserWorker.ReloadGrammarAndLexicon()`, does the reset first and then
checks whether an update is needed.

**Alternatives considered.** *Bind `Reload()` to `Update()` and document
the conditionality.* Rejected: the requirement is an unconditional discard.
Documenting that the guarantee does not hold is a Principle V violation
dressed as candour.

### D-A6 -- FR-009 wires the existing MSA wrapper; it designs nothing new

**Decision.** Add a read surface to `MSAOperations` that iterates
`entry.MorphoSyntaxAnalysesOC`, wraps each element in the existing
`MorphosyntaxAnalysis`, and returns the existing `MSACollection`. Copy the
wiring from `AllomorphOperations.GetAll` (`AllomorphOperations.py:104`),
which is the same two-subtype shape already shipped end to end.

**Rationale.** F3. The polymorphic wrapper the requirement implies exists
and is complete; only the accessor that hands it out is missing. Building a
second one would duplicate a tested surface. Where flat property reads are
needed, the established convention is a `ClassName`-keyed dispatch table --
`lcm_casting.py:652` (`_MSA_POS_PROPERTY`), `:662`
(`POS_BEARING_MSA_CLASSES`), `:665` (`get_pos_from_msa`) -- consumed as in
`LexSenseOperations.py:1177`, which checks membership, logs a warning and
returns `None` for an unknown subtype.

**Alternatives considered.** *Design a fresh flat MSA reader.* Rejected on
both counts: it duplicates `morphosyntax_analysis.py`, and a flat reader is
wrong for a hierarchy whose subtypes expose different property sets.

### D-A7 -- The ratchet edits are enumerated up front, not discovered one failure at a time

**Decision.** A new Operations class requires these edits, all of which are
tasks rather than incidental fixes:

| Ratchet / registry | File | What it requires |
|---|---|---|
| Stub parity | `flexicon/__init__.py` + `flexicon/__init__.pyi` | The `from .code.Parser.ParserOperations import ParserOperations` line in both, **and** the `__all__` string in the stub. Three assertions fail otherwise: `tests/test_297_init_stub_parity.py:170`, `:190`, `:210`. |
| Return-annotation agreement | `FLExProject.py` + `FLExProject.pyi` | The accessor's return annotation must be the identical string on both sides (`tests/test_pyi_return_annotation_ratchet.py:70-101`). |
| Docstring examples | `ParserOperations.py`, `FLExProject.pyi` | Every `>>>` example may name only real members; a new `project.Parser` accessor must be typed in `FLExProject.pyi` or carry a `Returns:` docstring line, or every example using it is reported `unknown-accessor` (`tests/test_docstring_example_ratchet.py`, baseline `tests/docstring_example_baseline.json`). |
| Alias stability | all new files | The string `flexlibs2` must not appear in code, comments, docstrings, tests or docs (`tests/test_flexlibs2_alias_ratchet.py:150`, `:170`, `:285`, `:310`). |
| CAPABILITIES | `tests/write_path_transactions/test_capabilities.py:36-41` | `EXPECTED_TOKENS` is a frozen literal asserted for set equality at `:54`. |
| Test plugin registry | `tests/flex_plugin.py:152-222`, `:738-808` | `operations_modules` and `_OPERATIONS_CLASS_DOMAIN` must both gain the class; the comment at `:736-737` requires they stay in sync. |
| Alias table | `flexicon/code/_op_aliases.py:35`, `:79-84` | `install_op_namespace_aliases` raises at import time if a listed canonical target does not exist (`:143-149`). |

**Rationale.** Principle III: these are controls that fail loudly, which is
their value -- but a control discovered mid-implementation costs a rerun
each time. Enumerating them converts seven surprise failures into seven
known edits.

**Alternatives considered.** *Let the suite find them.* Rejected: with no
CI, every discovery is a manual local rerun.

### D-A8 -- Allomorph owner copies the `OwnerOfClass` template, not the one-hop `.Owner` siblings

**Decision.** Copy `LexSenseOperations.GetOwningEntry`
(`LexSenseOperations.py:2826`): resolve via
`OwnerOfClass(LexEntryTags.kClassId)`, null-guard, return the cast entry.

**Rationale.** Four `GetOwningEntry` siblings exist. Three --
`EtymologyOperations.py:1150`, `PronunciationOperations.py:946`,
`VariantOperations.py:1011` -- take a single `.Owner` hop and are
**unguarded**, so a null owner would throw inside the cast. Only the
`LexSense` one walks the ownership chain and guards. Allomorphs need the
walking form: `LexemeFormOA` and `AlternateFormsOS` members sit one hop
from their entry, but an `IMoForm` can also sit under an affix-form chain,
where one hop lands on the wrong object. The template's own comment states
the rationale: *"OwnerOfClass walks the ownership chain directly to the
nearest ancestor with the given class ID, regardless of nesting depth."*

**Alternatives considered.** *Copy the nearest sibling by file proximity
(`AllomorphOperations` sits in `Lexicon/` beside the Variant and
Pronunciation ones).* Rejected -- and worth naming, because proximity is
exactly how the wrong template gets chosen. Constitution Principle I cites
copying a working pattern without re-checking it on the target type as the
documented root cause of issues #36, #39 and #40.

### D-A9 -- Add a plural `GetGenres`; leave `GetGenre` in place

**Decision.** Add `TextOperations.GetGenres(text)` returning every genre.
Do not modify or deprecate the existing singular `GetGenre`.

**Rationale.** F4: the singular exists and returns `FirstOrDefault()`.
Changing its return type from an object to a collection would be a silent
breaking change for existing callers -- the kind that passes every
structural ratchet, since the ratchets check names and annotations rather
than cardinality. The read template is
`LexSenseOperations.GetSemanticDomains` (`LexSenseOperations.py:1602`):
validate, resolve, return the reference collection as a list, empty list
when unset.

**Alternatives considered.** *Change `GetGenre` to return all genres.*
Rejected as above. *Deprecate `GetGenre`.* Rejected as out of scope: FR-007
asks for the plural read, not a deprecation cycle.

### D-A10 -- The `"parser"` CAPABILITIES token lands last

**Decision.** The token is added in the final task before the release cut,
after the facade is proven by tiers A1-A3.

**Rationale.** `tests/write_path_transactions/test_capabilities.py:12-16`
states that a token added without a landed capability behind it is a
Constitution Principle V violation, and `:52` repeats it: *"No token may
appear before its capability is real."* The token is a public claim read by
FlexToolsMCP through the mandated probe
`getattr(flexicon, "CAPABILITIES", frozenset())`
(`docs/FLEXTOOLSMCP_WRITE_CONTRACT.md:183-232`). Adding it early would
advertise a capability across the repository boundary before the evidence
gate has been satisfied -- which is D-00's failure mode in miniature.

Three places change in lockstep: the frozenset
(`flexicon/__init__.py:67-72`), the `#:` documentation block above it
(`:17-66`), and `EXPECTED_TOKENS`.

### D-A11 -- The discard proof witnesses a replaced morpher, with a documented fallback

**Decision.** Tier A3 proves the unconditional discard by comparing the
identity of the parser's internal morpher instance across calls: with no
model change between them, the plain update must **not** replace it and the
reload **must**. If the private-field read proves unreliable, fall back to
observing the rewrite of the `{ProjectName}HCLoadErrors.xml` side file,
which CP1 already treats as the load signal.

**Rationale.** `LoadParser()` replaces the morpher, so its identity is the
only direct witness that a load actually happened. This is a private-field
read under pythonnet, which is acceptable in a test that documents itself
as such and unacceptable in shipped code -- the test carries that statement
in its docstring. The fallback is weaker (it observes a side effect rather
than the state change) but is already established in this codebase.

**Alternatives considered.** *Assert on elapsed time -- a real load is
slower.* Rejected: timing is not a witness, it is a correlation, and a
small grammar on a warm cache would make it a flaky one.

### D-A12 -- Evidence is a written artifact in this repository, not a test count

**Decision.** CP2a ends by writing
`specs/parser-check-cp2/evidence/cp2a-evidence.md` in the `FlexToolsMCP`
repository -- the one file CP2a touches here -- recording per tier: the
exact invocation, the full counts including failures, pre-existing failures
named as pre-existing, and for A3 the observed discard result.

**Rationale.** Decision D4 authorises the next phase by what was
*observed*, and Principle IV requires the measurement with its invocation
rather than the impression. All four flexicon ratchets are structural --
stub parity, return annotations, docstring examples, alias stability -- and
every one of them would have passed a reload bound to a bare update. A
green suite is therefore not evidence for the one claim that matters most.

It lives in `FlexToolsMCP` rather than `flexicon` because it is CP2b's
entry gate, and CP2b is planned and executed here.

**Alternatives considered.** *Record it in the flexicon release notes.*
Rejected: release notes describe what shipped, and this artifact exists to
authorise work in a different repository.

---

## Open escalations carried into plan review

- **E-B (now due).** Is the maintainer content that the status tool never
  returns an error envelope for a terminal run? This is CP2b surface, so it
  does not gate CP2a planning, but it is cheap to reverse now and expensive
  after the runner exists.
- **E-C.** The `v4.9.0` tag push and `gh release create` are maintainer
  acts. The tag publishes to PyPI and is irreversible. CP2a ends with the
  release commit prepared and the ratchets green; the crew does not tag.
- **E-D.** Proving FR-043's *stale* half requires a write to set the model
  as changed. Deferred to CP2b as tier A4, where the loop must stop with
  `needs_human`. CP2a needs no write and no authorisation.
