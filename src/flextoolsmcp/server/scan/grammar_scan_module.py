#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CP1 static grammar-health scan (SPEC 9.5.4 / 9.5.5, `flextools_grammar_health`).

Runs in the FLExTools/IronPython... no -- plain-CPython generated-module
SUBPROCESS launched by `run_scan_module` / `_build_scan_script`
(`src/flextoolsmcp/server/handlers/execution.py`, T030; research.md D11).
Per `scan/__init__.py`'s own docstring, this module must NEVER import
``flextoolsmcp.server.*`` -- it can only return plain, JSON-serializable
data (bool/int/str/list/dict). Building the closed
``GrammarHealthFinding``/``FoundObject`` pydantic models (T017,
``server/models.py``) happens later, in the MCP server process, inside
T020's handler -- not here.

Entry point, called by T030's fixed "module code"
(research.md D11, cycle10-programmer-t029.md)::

    from flextoolsmcp.server.scan.grammar_scan_module import run_grammar_scan
    report.Result(run_grammar_scan(project))

``run_grammar_scan(project)`` returns::

    {
        "checks_run": ["representation-variant-product", ...],
        "checks_skipped": [{"check_id": "...", "reason": "lcm_name_unverified"}],
        "findings": [
            {
                "check_id": "...", "spec_row": 2, "count": 4096,
                "measured": "...", "evidence_basis": "...",
                "objects": [{"hvo": 1, "class_name": "PhPhoneme", "label": "p", "goto_url": "..."}],
            },
            ...
        ],
    }

No finding carries any severity/score/grade/rank field of any kind, and no
``measured`` string uses verdict wording ("invalid"/"wrong"/"broken"/etc.)
-- SPEC 9.5.3, 9.5.7, data-model.md's ``GrammarFinding``, D7. ``findings``
order is the SPEC 9.5.4 row order, fixed at authoring time, never sorted
by ``count`` -- see the "structural order guarantee" note on
``run_grammar_scan`` below.

CP1 boundary (SPEC 3.1): this module reads grammar objects only. It never
reads wordform-analysis objects (the ``IWfi*`` family) or wordforms,
constructs no ``HCParser``, loads no grammar into HermitCrab, opens no
``LcmCache`` itself (the T030 seam opens the project and hands this module
a live, already-open ``project``), and parses no word. T026 asserts this
statically/dynamically over ``server/scan/**`` -- and
tests/test_grammar_health.py's own ``TestCP1BoundaryOnTheScanModule``
checks this module's source text does not even mention that forbidden
type by name, so this docstring is careful not to spell it out literally
either.

Implementation table: ``specs/parser-check/data-model.md``, the
"``flextools_grammar_health`` scan implementation table" section (T033).
That table -- not SPEC.md 9.5.4 directly -- is the authority this module
follows for ``check_id`` slugs, cast requirements and ``measured``/
``evidence_basis`` wording, per T033's own instruction that where the two
disagree, its table wins.

Module layout (for T034 -- rows 1, 6, 7a/7b, 10 -- and T035 -- rows
3a/3b, 5, 8 -- landing later; read this before adding a row):

    1. Shared, pure-Python helpers (``is_empty_form``, ``exclude_disabled_
       rules``, ``skipped_check``, ``_found_object``, ``_emit``) -- LCM-free,
       safe to import and unit-test without pythonnet/FieldWorks installed
       (tests/test_grammar_scan_checks.py, T015). Add new *shared*
       predicates here, not inside a row's own ``_scan_*`` function.
    2. One private ``_scan_<check_id_with_underscores>(project)`` function
       per row, each doing its own LOCAL (function-scoped, not
       module-top-level) ``from SIL.LCModel import ...`` -- see "why LCM
       imports are local" below -- and returning a plain
       ``(count, measured, evidence_basis, objects)`` tuple. A gated row
       that T016 did not confirm returns ``None`` instead (see the row's
       own docstring for the exact contract T034/T035 should follow) so
       ``run_grammar_scan`` can emit a ``checks_skipped`` entry instead of
       a finding.
    3. ``run_grammar_scan(project)`` itself, which calls each ``_scan_*``
       function and appends its result via ``_emit`` (or
       ``checks_skipped.append(skipped_check(...))`` for a gated,
       unconfirmed row) IN SPEC 9.5.4 ROW ORDER, marked with one comment
       per row slot. T034/T035 insert their own calls at the marked
       comment for their row, in row-number order among rows 1/2/3a/3b/4/
       5/6/7a/7b/8/9/10 -- inserting a call is the whole integration; no
       other function in this module needs to change.

Why LCM imports are local, not top-of-file: ``SIL.LCModel`` is a pythonnet
binding only resolvable inside the FLExTools/flexicon runtime (FieldWorks
installed, pythonnet bridged). It is NOT importable in the plain
dev/test environment this repo's own test suite runs in ("ModuleNotFoundError:
No module named 'SIL'", confirmed by probe). A top-level
``from SIL.LCModel import ...`` would make importing this module -- and
therefore every pure-Python helper T015's tests exercise -- fail in that
environment. Every ``import SIL.LCModel`` in this file is therefore inside
a ``_scan_*`` function, executed only when ``run_grammar_scan`` actually
runs against a live project in the generated-module subprocess.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


# ---------------------------------------------------------------------------
# Shared, pure-Python helpers. No LCM/pythonnet import anywhere below this
# line until the first ``_scan_*`` function -- these must stay importable
# with no FieldWorks/pythonnet present (tests/test_grammar_scan_checks.py).
# ---------------------------------------------------------------------------

def is_empty_form(form) -> bool:
    """The emptiness predicate data-model.md's cross-cutting rule 2 pins
    verbatim for every row that reads an ``IMultiUnicode``/``IMultiString``
    form directly off LCM (this module's read path gets no Operations-layer
    "***" -> "" normalization -- CLAUDE.md). A real empty field surfaces as
    the literal string "***", not "" or ``None`` alone; testing only
    ``form in (None, "")`` silently undercounts every one of them.

    Not used by T019's own three rows (2, 4, 9 -- none reads a form field),
    but established here for T034 (rows 1, 6, 7a all read ``IMoForm``-family
    multistring fields) so it does not need reinventing per row.
    """
    return form in (None, "", "***")


def is_zero_surface_form(form) -> bool:
    """Row 1 predicate (data-model.md row 1; SPEC 9.5.4 row 1): a zero-surface
    ``IMoForm``, tested via ``is_empty_form`` on the form's own ``.Form``
    ``IMultiUnicode`` field -- the same "***"/""/None emptiness rule, just
    applied to the whole ``IMoForm`` object rather than a bare string so
    callers can pass the LCM object straight through.

    **Unconditional at CP1** (T034/T033, contracts/flextools_grammar_health.md
    "Row 1's `measured` wording is deliberately unconditional at CP1"): this
    signature deliberately takes no slot/position/reachability argument. The
    slot -> ``Affixes`` -> MSA -> owning entry -> ``AlternateFormsOS`` walk
    that would condition this on optional-slot reachability is deferred (the
    allomorph -> owning-entry hop is a known flexicon read gap, research D5,
    tasked flexicon-first under S9) -- every zero-surface ``IMoForm`` is
    counted regardless of where, or whether, it is reachable.
    """
    return is_empty_form(getattr(form, "Form", None))


def is_optional_slot(slot) -> bool:
    """Row 10 predicate half (data-model.md row 10; SPEC 9.5.4 row 10):
    ``IMoInflAffixSlot.Optional`` read directly, no cast. This predicate is
    deliberately just the boolean -- the row's full condition also requires
    ``.Affixes`` to be non-empty (data-model.md: "``Optional == True`` with
    ``.Affixes`` non-empty"), but that second half is a collection-emptiness
    check on the *scan's* enumeration, not a property of "is this slot
    optional" in isolation, so it stays out of this predicate and is applied
    separately in ``_scan_optional_template_slot_branching``.

    **Never** the ``ICmPossibility``-cast ``.Name`` read (cross-cutting rule
    6, research D4): ``IMoInflAffixSlot`` is not ``ICmPossibility`` -- its
    base is ``CmObject`` -- so this predicate touches only ``.Optional`` and
    never ``.Name``.
    """
    return bool(slot.Optional)


def exclude_disabled_rules(rules):
    """data-model.md cross-cutting rule 7: ``IPhSegmentRule.Disabled`` gates
    every rule-based check (rows 3a/3b, 5, 8) and must be excluded BEFORE
    counting, never filtered out of an already-built result afterward -- a
    disabled rule cannot multiply search paths, so counting it manufactures
    a suspect the grammar never runs.

    Not used by T019's own three rows (phonemes and iteration contexts are
    not ``IPhSegmentRule``s), but established here for T035, which owns
    every rule-based row.
    """
    return [rule for rule in rules if not getattr(rule, "Disabled", False)]


def skipped_check(check_id: str) -> Dict[str, str]:
    """One ``checks_skipped`` entry (contracts/flextools_grammar_health.md):
    a check gated on an LCM name T016 has not confirmed is named, never
    silently dropped. Reason is always exactly the literal string
    ``"lcm_name_unverified"`` -- checked as a literal by
    tests/test_grammar_scan_checks.py, not a synonym.

    Not needed by T019's own three rows (none is gated on T016 -- see this
    module's docstring / data-model.md's table), but established here for
    T034's row 7b (``ILexEntry.AlternateFormsOS``) and T035's row 3b
    (``IPhMetathesisRule``) / row 5 (``IMoAffixProcess`` +
    ``IPhMetathesisRule``).
    """
    return {"check_id": check_id, "reason": "lcm_name_unverified"}


# Per-finding objects[] preview cap (data-model.md `GrammarFinding.objects`:
# "Capped preview (SPEC S7: responses summarise, never inline the full
# set)"). `run_grammar_scan(project)` takes no `limit` argument -- T030's
# fixed "module code" calls it with exactly one positional argument, and
# GrammarHealthInput.limit (server/models.py, default 20) is not available
# to this module -- so this is the scan's own summarize-not-inline default,
# matching that same default. `count` always reflects the true number of
# objects found; only the `objects` preview list is capped.
DEFAULT_OBJECT_CAP = 20


def _found_object(project, obj, label: str) -> Dict[str, Any]:
    """Build one ``FoundObject``-shaped plain dict (data-model.md
    `FoundObject`) -- never the pydantic model itself (this module cannot
    import ``server.models``; T020 revalidates through it).

    ``goto_url`` is best-effort: ``project.BuildGotoURL(obj)``
    (data-model.md's own prescribed call) currently only special-cases
    lexicon/wordform/reversal/text objects (`FLExProject.BuildGotoURL`) and
    falls back to the Lexicon Edit tool for anything else, including every
    grammar object this module reads -- so the URL it returns may not land
    the linguist exactly on the phoneme/rule/slot in question. That is a
    known `BuildGotoURL` limitation outside this task's scope, not
    something this module works around. If the call raises for any reason,
    ``goto_url`` is ``None`` (the field is `Optional[str]`) rather than
    failing the whole scan.
    """
    try:
        goto_url = project.BuildGotoURL(obj)
    except Exception:
        goto_url = None
    return {
        "hvo": obj.Hvo,
        "class_name": obj.ClassName,
        "label": label if label not in (None, "***") else "",
        "goto_url": goto_url,
    }


def _emit(
    checks_run: List[str],
    findings: List[Dict[str, Any]],
    check_id: str,
    spec_row: int,
    count: int,
    measured: str,
    evidence_basis,
    objects: List[Dict[str, Any]],
) -> None:
    """Append one finding. The ONLY place a finding dict is built -- keeping
    this in one function is what makes the field set
    (``check_id``/``spec_row``/``count``/``measured``/``evidence_basis``/
    ``objects``, nothing else, no severity field of any kind) a structural
    guarantee rather than something each row has to remember to match.
    """
    checks_run.append(check_id)
    findings.append(
        {
            "check_id": check_id,
            "spec_row": spec_row,
            "count": count,
            "measured": measured,
            "evidence_basis": evidence_basis,
            "objects": objects[:DEFAULT_OBJECT_CAP],
        }
    )


# ---------------------------------------------------------------------------
# Row 1 -- zero-surface-morph-repeatable (T034, check_id
# "zero-surface-morph-repeatable", not gated on T016).
# ---------------------------------------------------------------------------

def _scan_zero_surface_morph_repeatable(project) -> Tuple[int, str, str, List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 1 / data-model.md row 1.

    LCM predicate (T033/data-model.md): ``is_zero_surface_form(form)`` over
    every ``IMoForm`` in the project, **unconditional on position** -- no
    optional-slot reachability walk at CP1 (see ``is_zero_surface_form``'s
    own docstring and contracts/flextools_grammar_health.md's "deliberately
    unconditional at CP1" note). ``measured`` therefore states only what CP1
    actually counted -- every zero-surface form, project-wide -- and must
    not claim slot-conditioning; matches the contract's own corrected
    example wording exactly ("{count} allomorphs have an empty surface
    form"), not data-model.md's older "reachable from an optional slot"
    draft phrasing.

    Enumeration: no flexicon wrapper walks every ``IMoForm`` regardless of
    owner (allomorphs, affix forms, etc. all subtype it), so this uses
    ``FLExProject``'s generic-repository escape hatch,
    ``project.ObjectsIn(IMoFormRepository)`` -- same idiom as row 4's
    ``IPhIterationContext`` walk.

    Cast: none (T033's cast_example) -- ``IMoForm.Form`` is a direct
    property and ``ObjectsIn`` already yields ``IMoForm``-typed objects.
    """
    from SIL.LCModel import IMoFormRepository

    count = 0
    suspects: List[Dict[str, Any]] = []
    for form in project.ObjectsIn(IMoFormRepository):
        if is_zero_surface_form(form):
            count += 1
            # The form is empty by definition here, so its own .Form value
            # is None/""/"***" -- _found_object normalizes all three to ""
            # rather than this row hand-rolling the same check again.
            suspects.append(_found_object(project, form, form.Form))

    measured = "{} allomorphs have an empty surface form".format(count)
    evidence_basis = "425x"  # PanGloss's own measured factor for row 1 (data-model.md row 1).
    return count, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 2 -- representation-variant-product (T019, check_id
# "representation-variant-product", not gated on T016).
# ---------------------------------------------------------------------------

def _scan_representation_variant_product(project) -> Tuple[int, str, str, List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 2 / data-model.md row 2.

    LCM predicate (T033): product of ``IPhPhoneme.CodesOS`` counts
    (``.Count``, not the codes' content), described in data-model.md as
    taken "over a form's segments". CP1 has no way to walk a specific
    word-form's phoneme segmentation without a parse -- that is exactly
    what the CP1 boundary forbids (no ``HCParser``, no parse; SPEC 3.1) --
    so, matching the same "count unconditionally, not yet the fully
    conditioned per-instance claim" posture the contract doc already takes
    for row 1 at CP1 (contracts/flextools_grammar_health.md, "Row 1's
    `measured` wording is deliberately unconditional at CP1"), this
    implementation counts across the WHOLE phoneme inventory rather than
    per form: the product of ``.CodesOS.Count`` over every phoneme that has
    more than one recorded representation code. A phoneme with exactly one
    code (the common case) does not change the product and is not itself a
    suspect; phonemes with more than one code are the multiplicative unit
    PanGloss's "representation-variant product" is about, so they are the
    suspects named in ``objects[]``. Flagged in the T019 programmer report
    as an interpretation decision, not a literal per-form walk.

    Cast: ``IPhPhoneme(obj).CodesOS`` (T033's cast_example), applied
    unconditionally here even though ``project.Phonemes.GetAll()`` already
    yields typed ``IPhPhoneme`` objects -- cheap and correct either way,
    and matches the table's cast pattern literally rather than
    hand-writing an accessor.
    """
    from SIL.LCModel import IPhPhoneme

    product = 1
    suspects: List[Dict[str, Any]] = []
    for phoneme in project.Phonemes.GetAll():
        ph = IPhPhoneme(phoneme)
        codes = ph.CodesOS
        n = codes.Count if codes is not None else 0
        if n > 1:
            product *= n
            label = project.Phonemes.GetRepresentation(ph)
            suspects.append(_found_object(project, ph, label))

    measured = (
        "{} is the representation-variant product across phonemes with "
        "more than one recorded representation code"
    ).format(product)
    evidence_basis = "4096"  # PanGloss's own Aweti-case citation (data-model.md row 2), not this project's number.
    return product, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 4 -- unbounded-quantifier (T019, check_id "unbounded-quantifier",
# not gated on T016).
# ---------------------------------------------------------------------------

def _scan_unbounded_quantifier(project) -> Tuple[int, str, str, List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 4 / data-model.md row 4.

    LCM predicate (T033): ``IPhIterationContext.Maximum == -1``.

    Enumeration: flexicon's ``PhonologicalRuleOperations`` has no
    dedicated wrapper for iteration contexts, so this uses
    ``FLExProject``'s own documented generic-repository escape hatch,
    ``project.ObjectsIn(IPhIterationContextRepository)`` (`FLExProject.py`,
    "Generic Repository Access") rather than hand-resolving
    ``ServiceLocator.GetInstance`` directly.

    Cast: ``IPhIterationContext(obj).Maximum`` (T033's cast_example),
    applied unconditionally -- see the row-2 docstring above for why this
    is harmless even though ``ObjectsIn`` already yields the repository's
    own interface type.
    """
    from SIL.LCModel import IPhIterationContext, IPhIterationContextRepository

    count = 0
    suspects: List[Dict[str, Any]] = []
    for ctx in project.ObjectsIn(IPhIterationContextRepository):
        ic = IPhIterationContext(ctx)
        if ic.Maximum == -1:
            count += 1
            # IPhIterationContext carries no name/representation of its
            # own (data-model.md's table lists no label source for this
            # row) -- "" per FoundObject.label's documented empty spelling.
            suspects.append(_found_object(project, ic, ""))

    measured = "{} pattern/environment positions use an unbounded quantifier".format(count)
    evidence_basis = "fst-health's UnknownUnboundedConstruct"
    return count, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 6 -- partial-morpheme-incomplete-form (T034, check_id
# "partial-morpheme-incomplete-form", not gated on T016).
# ---------------------------------------------------------------------------

def _scan_partial_morpheme_incomplete_form(project) -> Tuple[int, str, str, List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 6 / data-model.md row 6.

    LCM predicate (T033, research D4): ``IMoForm.IsComplete == False`` --
    the predicate research D4 found already exists on LCM rather than
    reimplementing "lacking category" by hand, mirroring 9.3.1's use of
    ``IWfiMorphBundle.IsComplete``.

    Enumeration: same ``project.ObjectsIn(IMoFormRepository)`` walk as row 1
    -- a separate walk per this module's one-function-per-row layout (see
    module docstring), not a shared iteration with row 1's scan.

    Cast: none (T033's cast_example) -- ``IMoForm.IsComplete`` is a direct
    property.
    """
    from SIL.LCModel import IMoFormRepository

    count = 0
    suspects: List[Dict[str, Any]] = []
    for form in project.ObjectsIn(IMoFormRepository):
        if not form.IsComplete:
            count += 1
            suspects.append(_found_object(project, form, form.Form))

    measured = "{} morphs are incomplete".format(count)
    evidence_basis = "hc-partial-morpheme"
    return count, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 7a -- stem-allomorph-stem-name-restriction (T034, check_id
# "stem-allomorph-stem-name-restriction", already verified -- not gated on
# T016 despite sharing row 7 with the gated 7b half below).
# ---------------------------------------------------------------------------

def _scan_stem_allomorph_stem_name_restriction(project) -> Tuple[int, str, str, List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 7 (first half) / data-model.md row 7a.

    LCM predicate (T033, research D4 -- VERIFIED, not part of D9's gate):
    ``IMoStemAllomorph.StemNameRA != null`` (kind ``RA`` -> ``IMoStemName``).

    Enumeration: ``project.ObjectsIn(IMoStemAllomorphRepository)`` -- the
    generic-repository escape hatch, same idiom as rows 1/4/6.

    Cast: ``IMoStemAllomorph(obj).StemNameRA`` (T033's cast_example),
    applied unconditionally even though ``ObjectsIn`` already yields
    ``IMoStemAllomorph``-typed objects -- same reasoning as rows 2/4/9's
    own cast-applied-unconditionally precedent.
    """
    from SIL.LCModel import IMoStemAllomorph, IMoStemAllomorphRepository

    count = 0
    suspects: List[Dict[str, Any]] = []
    for allomorph in project.ObjectsIn(IMoStemAllomorphRepository):
        sa = IMoStemAllomorph(allomorph)
        if sa.StemNameRA is not None:
            count += 1
            suspects.append(_found_object(project, sa, sa.Form))

    measured = "{} stem allomorphs are restricted to a stem name".format(count)
    evidence_basis = None
    return count, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 7b -- multiple-allomorphs-per-entry (T034, check_id
# "multiple-allomorphs-per-entry"). CONFIRMED by research D9: written as a
# normal check, NOT emitted to checks_skipped -- ILexEntry.AlternateFormsOS
# resolved to an exact-spelling, exact-casing index entity with no
# ambiguity (liblcm_api_v11.0.0.json:86250).
# ---------------------------------------------------------------------------

def _scan_multiple_allomorphs_per_entry(project) -> Tuple[int, str, str, List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 7 (second half) / data-model.md row 7b.

    LCM predicate (T033, research D9): ``ILexEntry.AlternateFormsOS.Count >
    1``. ``.Count`` is a collection-level read on the ``ILcmOwningSequence``
    (D9), so no per-element cast is needed here -- this check never inspects
    an individual allomorph's concrete type.

    Enumeration: ``project.LexEntry.GetAll()`` (flexicon's
    ``LexEntryOperations``, already used project-wide in generated FLExTools
    modules per CLAUDE.md's own template) rather than a raw
    ``ILexEntryRepository`` walk -- entries are exactly what this wrapper is
    for, unlike rows 1/6/7a/10 which have no flexicon wrapper at all.

    Cast: none -- ``AlternateFormsOS`` is declared directly on ``ILexEntry``
    (D9), and ``project.LexEntry.GetAll()`` already yields ``ILexEntry``.
    """
    count = 0
    suspects: List[Dict[str, Any]] = []
    for entry in project.LexEntry.GetAll():
        if entry.AlternateFormsOS.Count > 1:
            count += 1
            label = project.LexEntry.GetHeadword(entry)
            suspects.append(_found_object(project, entry, label))

    measured = "{} entries have more than one allomorph".format(count)
    evidence_basis = None
    return count, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 9 -- duplicate-feature-bundle (T019, check_id
# "duplicate-feature-bundle", not gated on T016).
# ---------------------------------------------------------------------------

def _scan_duplicate_feature_bundle(project) -> Tuple[int, str, str, List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 9 / data-model.md row 9.

    LCM predicate (T033): pairwise ``IPhPhoneme.FeaturesOA`` equality
    within one phoneme set. ``IFsFeatStruc`` exposes no pythonnet-visible
    equality operator, so pairs are compared via ``.LongName`` -- a direct
    ``String`` property on ``IFsFeatStruc`` needing no cast
    (`liblcm_api_v11.0.0.json`'s own ``IFsFeatStruc`` entity record) -- on
    the reasoning that two feature structures with the same closed
    feature/value set render the same LongName. Phonemes with no
    ``FeaturesOA`` (``None``) or an empty/placeholder LongName are excluded
    from comparison -- an absent feature bundle cannot duplicate another
    absent one in the sense this check measures.

    ``count`` is the number of phoneme PAIRS sharing an identical feature
    bundle (matching the row's `measured` wording basis exactly);
    ``objects[]`` lists each distinct phoneme that participates in at
    least one such pair once (never once per pair it appears in).

    Cast: ``IPhPhoneme(obj).FeaturesOA`` (T033's cast_example), applied
    unconditionally per the same reasoning as rows 2 and 4 above.
    """
    from SIL.LCModel import IPhPhoneme

    bundles: List[Tuple[str, Any]] = []
    for phoneme in project.Phonemes.GetAll():
        ph = IPhPhoneme(phoneme)
        features = ph.FeaturesOA
        if features is None:
            continue
        long_name = features.LongName
        if is_empty_form(long_name):
            continue
        bundles.append((long_name, ph))

    pair_count = 0
    seen_hvos = set()
    suspects: List[Dict[str, Any]] = []
    for i in range(len(bundles)):
        name_i, ph_i = bundles[i]
        for j in range(i + 1, len(bundles)):
            name_j, ph_j = bundles[j]
            if name_i != name_j:
                continue
            pair_count += 1
            for ph in (ph_i, ph_j):
                if ph.Hvo not in seen_hvos:
                    seen_hvos.add(ph.Hvo)
                    label = project.Phonemes.GetRepresentation(ph)
                    suspects.append(_found_object(project, ph, label))

    measured = "{} phoneme pairs share an identical feature bundle".format(pair_count)
    evidence_basis = "hc-duplicate-feature-bundle"
    return pair_count, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 10 -- optional-template-slot-branching (T034, check_id
# "optional-template-slot-branching", not gated on T016).
# ---------------------------------------------------------------------------

def _scan_optional_template_slot_branching(project) -> Tuple[int, str, str, List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 10 / data-model.md row 10.

    LCM predicate (T033, research D4 cross-cutting rule 6 -- VERIFIED):
    ``IMoInflAffixSlot.Optional == True`` with ``.Affixes`` non-empty.
    ``is_optional_slot`` covers the ``.Optional`` half; the ``.Affixes``
    non-emptiness is applied here, in the scan itself, rather than folded
    into the shared predicate (see ``is_optional_slot``'s own docstring for
    why).

    **Never** the ``ICmPossibility``-cast ``.Name`` read -- ``IMoInflAffixSlot``
    is not ``ICmPossibility`` (cross-cutting rule 6). This function reads
    only ``.Optional`` and ``.Affixes``; it never touches ``.Name`` at all, so no
    cast of either kind appears on this path.

    Enumeration: ``project.ObjectsIn(IMoInflAffixSlotRepository)`` -- the
    generic-repository escape hatch, same idiom as rows 1/4/6/7a.

    Cast: none (T033's cast_example) -- ``.Optional``/``.Affixes`` are
    direct properties.
    """
    from SIL.LCModel import IMoInflAffixSlotRepository

    count = 0
    suspects: List[Dict[str, Any]] = []
    for slot in project.ObjectsIn(IMoInflAffixSlotRepository):
        if is_optional_slot(slot) and slot.Affixes:
            count += 1
            # IMoInflAffixSlot.Name exists (it is its own IMultiUnicode --
            # research D4 cross-cutting rule 6) but is deliberately not read
            # here: this row's suspects are the slots themselves, and no
            # cast_example in the table calls for reading .Name for this
            # row's label. "" per FoundObject.label's documented empty
            # spelling, matching row 4's own no-label precedent.
            suspects.append(_found_object(project, slot, ""))

    measured = "{} optional template slots independently admit or skip an affix".format(count)
    evidence_basis = None
    return count, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Entry point -- called by the T030 subprocess seam as
# report.Result(run_grammar_scan(project)).
# ---------------------------------------------------------------------------

def run_grammar_scan(project) -> Dict[str, Any]:
    """Run every implemented SPEC 9.5.4 check against ``project`` and
    return a plain, JSON-serializable dict -- never a pydantic model (see
    module docstring).

    Structural fixed-order guarantee (data-model.md: "Findings are grouped
    by check_id and never ordered by count"; SPEC S7/D7): ``findings`` is
    built by calling ``_emit`` exactly once per implemented row, in SPEC
    9.5.4 row order (2, 4, 9 at T019). There is no sort step anywhere in
    this function -- order is guaranteed by Python executing these
    statements top-to-bottom, the same way ``checks_run`` accumulates in
    call order, not by any comparator applied after the fact. T034/T035
    preserve the guarantee simply by inserting their own ``_emit(...)``
    call (or, for a row T016 leaves unconfirmed,
    ``checks_skipped.append(skipped_check(...))``) at the row's marked
    comment below, in row-number order -- no restructuring of this
    function, and no change to ``_emit`` itself, is needed to add a row.
    """
    checks_run: List[str] = []
    checks_skipped: List[Dict[str, str]] = []
    findings: List[Dict[str, Any]] = []

    count, measured, evidence_basis, objects = _scan_zero_surface_morph_repeatable(project)
    _emit(checks_run, findings, "zero-surface-morph-repeatable", 1, count, measured, evidence_basis, objects)

    count, measured, evidence_basis, objects = _scan_representation_variant_product(project)
    _emit(checks_run, findings, "representation-variant-product", 2, count, measured, evidence_basis, objects)

    # --- Row 3a ("epenthesis-empty-struc-desc") and 3b ("metathesis-rule-present",
    #     gated on T016) -- T035 -- insert their calls here. ---

    count, measured, evidence_basis, objects = _scan_unbounded_quantifier(project)
    _emit(checks_run, findings, "unbounded-quantifier", 4, count, measured, evidence_basis, objects)

    # --- Row 5 ("rule-product-morph-phon", gated on T016) -- T035 -- inserts its call here. ---

    count, measured, evidence_basis, objects = _scan_partial_morpheme_incomplete_form(project)
    _emit(checks_run, findings, "partial-morpheme-incomplete-form", 6, count, measured, evidence_basis, objects)

    count, measured, evidence_basis, objects = _scan_stem_allomorph_stem_name_restriction(project)
    _emit(checks_run, findings, "stem-allomorph-stem-name-restriction", 7, count, measured, evidence_basis, objects)

    # Row 7b, "multiple-allomorphs-per-entry": CONFIRMED by research D9
    # (ILexEntry.AlternateFormsOS resolved unambiguously) -- written here as
    # a normal check, not routed to checks_skipped.
    count, measured, evidence_basis, objects = _scan_multiple_allomorphs_per_entry(project)
    _emit(checks_run, findings, "multiple-allomorphs-per-entry", 7, count, measured, evidence_basis, objects)

    # --- Row 8 ("unordered-rule-application-stratum-pair") -- T035 -- inserts its call here. ---

    count, measured, evidence_basis, objects = _scan_duplicate_feature_bundle(project)
    _emit(checks_run, findings, "duplicate-feature-bundle", 9, count, measured, evidence_basis, objects)

    count, measured, evidence_basis, objects = _scan_optional_template_slot_branching(project)
    _emit(checks_run, findings, "optional-template-slot-branching", 10, count, measured, evidence_basis, objects)

    return {
        "checks_run": checks_run,
        "checks_skipped": checks_skipped,
        "findings": findings,
    }
