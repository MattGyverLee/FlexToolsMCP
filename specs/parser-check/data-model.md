# Data Model -- parser-check, CP1

Entities CP1 introduces. Field names and enum values are copied verbatim from
[SPEC.md](./SPEC.md) 10.2 and 14; where a name appears in both, the spec's spelling
wins. Nothing here is a wire contract on its own -- see [`contracts/`](./contracts/)
for what is serialized.

CP1 introduces **no persisted state**. Every entity below is computed per call and
discarded. Run artifacts (SPEC 5.5) belong to CP2's job runner.

---

## `ProbeResult`

The atom of parser detection. One per probed capability. Defined by SPEC 10.2's
"interface seam for the detection agent".

| Field | Type | Notes |
|---|---|---|
| `ok` | bool | Whether this capability is reachable. Never `None` -- a probe that could not run reports `ok=False` with a `signal` saying why, and a *skipped* probe is represented outside this type (see `AgentProbeState`) |
| `signal` | str or null | Closed vocabulary per probe kind; shares `parser_core_missing`'s values for the member probe: `absent`, `foreign_install`, `incompatible_surface`, `load_failed` |
| `expected_path` | str or null | Where we looked. Populated even on success -- it is the first thing worth knowing in a bug report |
| `missing_members` | list[str] | Empty on success. Each entry is a bound member from SPEC 5.4's enumerated surface |
| `detected_version` | str or null | **Reported, never compared.** No code path may test this against a floor |

**Invariant.** `ok=True` implies `missing_members == []` and `signal is None`.
`detected_version` is independent of `ok` in both directions: an unexpected version
that passes the member probe is a pass (SPEC 16's regression test against a version
floor).

---

## `AgentProbeState`

Three-valued, because the HC-agent probe has a third outcome the other probes do not:
it may be unable to run at all. Modelled separately so `skipped` can never be
flattened into `ok=True`.

| Value | Meaning |
|---|---|
| `present` | Agent resolved from `ICmAgentRepository` |
| `absent` | `ActiveParser == "HC"` and `kguidAgentHermitCrabParser` not in the repository |
| `skipped` | No project open, so the probe could not run (D2 -- the normal case for `flextools_health`) |

**Invariant, and the one SPEC 16 tests directly: a `skipped` probe is never reported
as a pass.** When the state is `skipped`, `write`'s status is decided by the member
probe alone and the reason records `agent_probe: "skipped"`.

---

## `ParserDetector` return shape

What `parser_probe.py` hands to `diagnostic_health.py`. The health handler only
reshapes this; no location or reflection logic lives in the handler (SPEC 10.2).

| Field | Type |
|---|---|
| `read_probe` | `ProbeResult` |
| `write_probe` | `ProbeResult` -- additionally requires `ParseFiler.ProcessParse` in its member set |
| `sandbox_probe` | `{hc: ProbeResult, generate_config: ProbeResult}` |
| `agent_probe` | `AgentProbeState` plus `{agent_guid, active_engine}` when `absent` |
| `active_engine` | str or null -- `"XAmple"` \| `"HC"`, echoed only when a project is open |
| `versions` | `{parser_core_version, lcmodel_install_path, hc_tool_version}` |

**Why `read` and `write` are separate probes over one DLL.** They differ by exactly
one member: `write` additionally requires `ParseFiler.ProcessParse`. That makes
`read: ready` / `write: unavailable` representable when only that member is missing
-- a state SPEC 10.2 requires and a single boolean could not express.

**`active_engine` is informational only.** It never decides a status. The mismatch
gate lives in the per-call preflight, because `ActiveParser` is a project property and
health can run session-independent.

---

## `GrammarFinding`

One suspect from the static scan. Emitted by `grammar_scan_module.py`, interpreted by
`grammar_health.py`.

| Field | Type | Notes |
|---|---|---|
| `check_id` | str | Stable slug, e.g. `zero-surface-morph-repeatable`. Maps to a 9.5.4 row or to one of the three 9.5.1 causes PanGloss does not cover |
| `spec_row` | int or null | The 9.5.4 row this implements, or null for the three extras |
| `count` | int | How many objects tripped the check. **Evidence, not severity** |
| `objects` | list[`FoundObject`] | Capped preview (SPEC S7: responses summarise, never inline the full set) |
| `measured` | str | What was measured, in the wording of SPEC 8.4 -- "12 optional slots can host this zero-surface morph", never "this is wrong" |
| `evidence_basis` | str or null | PanGloss's measured factor where one exists (e.g. `"425x"` for row 1), labelled as *their* measurement on *their* corpus |

**What this type deliberately does not have** (D7, SPEC 9.5.3): no `severity`, no
`score`, no `grade`, no `rank`, no `priority`. Findings are grouped by `check_id` and
never ordered by `count`. A client must not be handed a field it could sort on as a
severity proxy -- a 2,044-state network ran ~1300x slower than a 106,365-state one, so
size and count are anti-correlated with cost.

`count` is present because a count is the measurement; what is forbidden is summing
counts into a total or ordering findings by them.

### `FoundObject`

| Field | Type | Notes |
|---|---|---|
| `hvo` | int | LCM object id |
| `class_name` | str | e.g. `MoStemAllomorph` |
| `label` | str | Best human-readable name; `""` when the field is empty, never `"***"` (flexicon normalizes -- `CLAUDE.md`) |
| `goto_url` | str or null | `project.BuildGotoURL(obj)` so the linguist can open it in FLEx |

---

## `flextools_grammar_health` scan implementation table (SPEC 9.5.4)

The per-row specification `T019`/`T034`/`T035` read while writing
`grammar_scan_module.py`. SPEC 9.5.4 states *what* each row maps to in LCM;
this table states *how to write it* -- `check_id`, which task owns it, whether
it is gated, the exact predicate, and whether it needs a pythonnet cast. Row
numbering, evidence and LCM-check wording are copied from SPEC.md 9.5.4 as
corrected by `T027` (row 8) and verified by research D4. Where this table and
SPEC.md 9.5.4 disagree, this table is the one T019/T034/T035 must follow --
flag the disagreement to `/lex-lead` rather than silently picking one.

**Scope.** Only the ten 9.5.4 rows. The three 9.5.1 causes PanGloss does not
cover (short allomorphs, broadly permissive rule environments, overlapping
natural classes) are named in SPEC 9.5.1/9.5.4 but have no LCM mapping and no
task in Phase 4 -- they are not part of this table and not part of CP1.

**`check_id` slugs.** Only row 1's slug (`zero-surface-morph-repeatable`) is
fixed elsewhere (the contract example, `data-model.md`'s `GrammarFinding`).
The other nine are assigned here for the first time and become the stable
identifiers `checks`, `checks_run` and `checks_skipped` use -- T017's
`GrammarHealthInput.checks` filter and T014's tests must use these exact
strings, not invent their own.

### Cross-cutting rules (read before the row table)

**1. Cast guidance.** Research D4: 32 of 37 `IMoStemAllomorph` properties and
31 of 36 `IPhRegularRule` properties require a pythonnet cast, verified against
`casting_index_liblcm-v11.0.0.json`. The rule that decides *which* properties
in this table need one is the index's `requires_cast_from` list for that
property, not the type name alone:

- A property declared only on the **subtype** (e.g. `IMoStemAllomorph.StemNameRA`,
  `requires_cast_from` includes `IMoForm`) needs a cast whenever the receiver in
  hand is typed to the **base** interface -- which it usually is, because
  `ILexEntry.AlternateFormsOS` yields `IMoForm`, not `IMoStemAllomorph`. This is
  the common case and the one the "32 of 37" statistic is mostly counting.
- A property declared on the **base** interface (`IPhSegmentRule.OrderNumber`,
  `.InitialStratumRA`, `.FinalStratumRA`, `.Disabled`, and also `.StrucDescOS`
  -- `requires_cast_from` is `[ICmObject, ICmObjectOrId]` only, no subtype)
  needs a cast **only if the receiver is a bare `ICmObject`/`ICmObjectOrId`**
  (e.g. reached through a generic/reflective walk). A receiver already typed
  `IPhRegularRule` or `IPhMetathesisRule` reads these directly -- C# interface
  inheritance carries them, no cast needed at that call site.

Use `build_property_cast_example()` / the index's own `cast_example` output
(`flextools_get_object_api`, `validators.py:4594`) rather than hand-writing a
cast. Per-row examples below; the pattern is `Interface(receiver).Property`.

**2. The emptiness predicate is `form in (None, "", "***")`.** CLAUDE.md
documents that Flexicon's Operations layer (`sense.GetGloss()`,
`entry.GetLexemeForm()`, etc.) normalizes `"***"` to `""`. **That
normalization does NOT apply here.** Every row in this table reads
`IMoForm.Form` (or another `IMultiUnicode`/`IMultiString`) directly off the
LCM object -- there is no Operations-layer wrapper on this path (research D1:
the scan module is pure LCM, run through the generated-module subprocess, not
through flexicon's Operations classes). So a real empty field surfaces as the
literal string `"***"`, not `""`, and a check that tests only
`form in (None, "")` will silently miss every one of them. **The predicate
every row that reads a form must use is exactly:**

```python
def is_empty_form(form) -> bool:
    return form in (None, "", "***")
```

T015's regression guard exists precisely for this: a stub `IMoForm.Form ==
"***"` must be counted as zero-surface, not skipped. Getting this wrong is the
single most likely way this table's rows ship silently broken -- the check
would run, return a count, and simply undercount every affected project.

**3. `OrderNumber` is comparable only within one stratum-pair grouping.**
`IPhSegmentRule.OrderNumber` (row 8) is not a grammar-wide ordinal. Each rule
references exactly one `InitialStratumRA`/`FinalStratumRA` pair, and
`OrderNumber` is very likely a per-pair counter. **Never sort or compare
`OrderNumber` across two rules that do not share the same
`(InitialStratumRA, FinalStratumRA)` pair.** The correct algorithm groups
rules by that pair first, and only orders/counts within a group. `IMoStratum`
itself has **no** rule collection -- its own properties are exactly
`Abbreviation`, `Description`, `Name`, `PhonemesRA` -- so row 8 is implemented
by walking rules and grouping by their stratum references, never by walking
strata looking for a rule list.

**4. Gated sub-checks and their `checks_skipped` fallback.** Row 5 (entirely),
row 3's metathesis half, and row 7's `AlternateFormsOS` half are gated on
`T016`'s verification of `IMoAffixProcess`, `IPhMetathesisRule` and
`ILexEntry.AlternateFormsOS` against this project's index. `T016` runs
concurrently with this table -- **do not assert its verdict here**; branch on
whatever `T016` records:

- **Confirmed** -> the sub-check is written as a normal row in
  `checks_run` / `findings`, exactly like an ungated row.
- **Not confirmed** -> the sub-check is never silently dropped. It is emitted
  as one entry in `checks_skipped`: `{"check_id": "<slug>", "reason":
  "lcm_name_unverified"}` -- that exact reason string, nothing else.

Row 7's first half, `IMoStemAllomorph.StemNameRA` (kind `RA` ->
`IMoStemName`), is already verified and is **not** gated -- write it
unconditionally regardless of T016's outcome.

**5. The index-inheritance trap.** `Disabled`, `OrderNumber`,
`InitialStratumRA` and `FinalStratumRA` are declared **once**, on the base
`IPhSegmentRule`, and are **not** redeclared in `IPhRegularRule`'s or
`IPhMetathesisRule`'s own `properties` array inside
`liblcm_api_v11.0.0.json` (confirmed: `IMoStemAllomorph`'s own entity record
at `properties` lists only `PhoneEnvRC` and `StemNameRA` -- inherited members
are absent from that array, the same pattern holds for the rule interfaces).
Inheritance makes all four reachable on an `IPhRegularRule` or
`IPhMetathesisRule` instance at runtime, but `flextools_get_object_api` run
against the derived interface **will not show them** in its own-properties
listing. **Absence from that listing is not evidence of absence** -- do not
let an implementer conclude `IPhRegularRule` lacks `OrderNumber` because the
tool's output for `IPhRegularRule` doesn't mention it; check
`IPhSegmentRule` (or the wider casting index, which does list inherited
availability under `available_on`) instead.

**6. `IMoInflAffixSlot` is not `ICmPossibility` (row 10).** Its base is
`CmObject`, not `ICmPossibility` -- unlike `IMoMorphType`, which genuinely is
one. `IMoInflAffixSlot.Name` is its own `IMultiUnicode`; casting with
`ICmPossibility(obj).Name` is wrong here and the index warns explicitly. Use
`slot.Name` / `slot.Optional` / `slot.Affixes` directly.

**7. `Disabled` gates every rule-based check, excluded before counting.**
`IPhSegmentRule.Disabled` (rows 3, 5, 8 -- anything walking `IPhRegularRule` or
`IPhMetathesisRule`) must be checked and the rule skipped **before** it is
counted, not filtered afterward. A disabled rule cannot multiply search paths,
so counting it manufactures a suspect the grammar never runs -- the same
validation rule already stated for `GrammarFinding` above, restated here
because rows 3/5/8 are exactly where it applies.

### The ten rows

| # | `check_id` | Written by | Gated on T016? | `cast_example` (when receiver is the base/generic type) |
|---|---|---|---|---|
| 1 | `zero-surface-morph-repeatable` | T034 | No | none -- `IMoForm.Form` is a direct property |
| 2 | `representation-variant-product` | T019 | No | `IPhPhoneme(obj).CodesOS` (only if the receiver is `ICmObject`; `IPhPhonemeRepository.AllInstances()` is already typed `IPhPhoneme`) |
| 3a | `epenthesis-empty-struc-desc` | T035 | No | `IPhRegularRule(obj).StrucDescOS` (only if the receiver is `ICmObject`; `IPhRegularRuleRepository.AllInstances()` is already typed `IPhRegularRule`, which inherits `StrucDescOS` from `IPhSegmentRule`) |
| 3b | `metathesis-rule-present` | T035 | **Yes** -- `IPhMetathesisRule` | type test only (`IPhMetathesisRuleRepository.AllInstances()`), no property cast |
| 4 | `unbounded-quantifier` | T019 | No | `IPhIterationContext(obj).Maximum` (only if the receiver is `ICmObject`) |
| 5 | `rule-product-morph-phon` | T035 | **Yes** -- `IMoAffixProcess` + `IPhMetathesisRule` | none -- counts via repository `.Count`, no property read |
| 6 | `partial-morpheme-incomplete-form` | T034 | No | none -- `IMoForm.IsComplete` is a direct property (research D4; do not reimplement "lacking category") |
| 7a | `stem-allomorph-stem-name-restriction` | T034 | No -- already verified | `IMoStemAllomorph(obj).StemNameRA` (needed whenever `obj` is typed `IMoForm`, e.g. items from `ILexEntry.AlternateFormsOS` -- this is the common case) |
| 7b | `multiple-allomorphs-per-entry` | T034 | **Yes** -- `ILexEntry.AlternateFormsOS` | none -- `entry.AlternateFormsOS.Count > 1` is a direct property |
| 8 | `unordered-rule-application-stratum-pair` | T035 | No (corrected mapping, T027) | `IPhSegmentRule(obj).OrderNumber` / `.InitialStratumRA` / `.FinalStratumRA` (only if the receiver is `ICmObject`; direct on `IPhRegularRule`/`IPhMetathesisRule` receivers) |
| 9 | `duplicate-feature-bundle` | T019 | No | `IPhPhoneme(obj).FeaturesOA` (only if the receiver is `ICmObject`; `IPhPhonemeRepository.AllInstances()` is already typed `IPhPhoneme`) |
| 10 | `optional-template-slot-branching` | T034 | No | none -- `IMoInflAffixSlot.Optional`/`.Affixes` are direct properties; **never** `ICmPossibility(obj).Name` (cross-cutting rule 6) |

**Per-row predicate and `measured` wording (CP1 scope).** `measured` states a
fact, never a verdict (SPEC 8.4, D7) -- no "invalid"/"wrong"/"broken". Rows are
in this table's order, which mirrors SPEC 9.5.4's PanGloss-yield ranking and
is the fixed `findings` order (SPEC S7/D7: never re-sorted by `count`).

| # | LCM predicate | `measured` wording basis | `evidence_basis` |
|---|---|---|---|
| 1 | `is_empty_form(form.Form)` over every `IMoForm`, **unconditional on position** -- no optional-slot reachability walk at CP1 (that walk needs the flexicon allomorph->owning-entry accessor, a CP2 gap per research D5) | `"{count} morphs have an empty or boundary-only surface form"` -- **must not** say "reachable from an optional slot" at CP1; that claim is only true once the reachability walk lands | `"425x"` |
| 2 | product of `IPhPhoneme.CodesOS` counts (`.Count`, not the codes' content) over a form's segments | `"the representation-variant product for this form is {count}"` | e.g. `"4096"` for the Aweti case |
| 3a | `IPhRegularRule` where `StrucDescOS` is empty, `Disabled == False` | `"{count} phonological rules have an empty structural description"` | -- |
| 3b | `IPhMetathesisRule` count, `Disabled == False` | `"{count} metathesis rules are present in the grammar"` | -- |
| 4 | `IPhIterationContext.Maximum == -1` | `"{count} pattern/environment positions use an unbounded quantifier"` | `fst-health`'s `UnknownUnboundedConstruct` |
| 5 | `IMoAffixProcess` count x (`IPhRegularRule` + `IPhMetathesisRule`, `Disabled == False`) count | `"the morphological x phonological rule product is {count}"` | `"64"` (PanGloss's own placeholder threshold -- report the product, never compare it to 64 as a pass/fail line; D7/9.5.3: "treat their numbers as placeholders") |
| 6 | `IMoForm.IsComplete == False` | `"{count} morphs are incomplete"` | `hc-partial-morpheme` |
| 7a | `IMoStemAllomorph.StemNameRA != null` | `"{count} stem allomorphs are restricted to a stem name"` | -- |
| 7b | `ILexEntry.AlternateFormsOS.Count > 1` | `"{count} entries have more than one allomorph"` | -- |
| 8 | group `IPhSegmentRule` (`Disabled == False`) by `(InitialStratumRA, FinalStratumRA)`; within each group, count members and/or `OrderNumber` spread -- **never** compare `OrderNumber` across groups (cross-cutting rule 3) | `"{count} rules are ordered within the '{stratum_pair}' stratum-pair grouping"` | `"2^N, capped at N=6"` |
| 9 | pairwise `IPhPhoneme.FeaturesOA` equality within one phoneme set | `"{count} phoneme pairs share an identical feature bundle"` | `hc-duplicate-feature-bundle` |
| 10 | `IMoInflAffixSlot.Optional == True` with `.Affixes` non-empty | `"{count} optional template slots independently admit or skip an affix"` | named by PanGloss, never built -- "we would be first" (SPEC 9.5.4) |

**`evidence_basis` is PanGloss's own measured factor, not ours** (SPEC 8.4,
`GrammarFinding.evidence_basis`) -- label it as their measurement on their
corpus, per the existing field note above. Rows with `"--"` have no PanGloss
measurement to cite; leave `evidence_basis` `null` for those findings rather
than inventing one.

---

## Validation rules

- **Closed enums are closed.** `signal`, `component`
  (`"hc"` \| `"GenerateHCConfig.exe"`), and `probe_source`
  (`bootstrap_absent` \| `lookup_failed`) are shared between the error payloads and
  the health block precisely so the two never drift. Adding a value is a contract
  change.
- **Error detail models use `extra="forbid"`**, matching every model from
  `response_models.py:142` onward. A typo'd field fails loudly rather than
  silently vanishing.
- **Empty multistring fields normalize to `""`, never `"***"`** on the flexicon path
  (`CLAUDE.md`). The scan module reads through flexicon where a wrapper exists; where
  it reads raw LCM it must normalize explicitly.
- **Disabled rules are excluded before counting.** `IPhSegmentRule.Disabled` gates
  every rule-based check (D4). A disabled rule cannot multiply paths, so including it
  manufactures a suspect the grammar never runs.

---

## State transitions

None. Every entity is computed per call and discarded; CP1 has no job, no run
artifact, and no cache. The first stateful entity in this feature is CP2's job
(`starting | loading_grammar | parsing | filing | completed | failed | cancelled`),
which is out of scope here.
