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

Module layout (rows 2/4/9 landed at T019, rows 1/6/7a/7b/10 at T034 and
rows 3a/3b/5/8 at T035; read this before adding a row):

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
       per row slot, in row-number order among rows 1/2/3a/3b/4/5/6/7a/
       7b/8/9/10 -- adding a call is the whole integration; no other
       function in this module needs to change.

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

from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Shared, pure-Python helpers. This module must stay IMPORTABLE with no
# FieldWorks/pythonnet present (tests/test_grammar_scan_checks.py) -- no
# ``from SIL.LCModel...`` at module top level anywhere below this line.
# Two helpers below (``_resolve_multistring_best_effort``, ``_read_ws``) do
# take a live multistring object and, on that branch only, a
# function-scoped ``from SIL.LCModel...`` -- exactly the same "local, not
# top-of-file" discipline every ``_scan_*`` function already follows (see
# "why LCM imports are local" in the module docstring), each wrapped in its
# own ``try/except`` so a missing pythonnet install falls back rather than
# raising. Calling either helper with a plain ``str``/``None`` -- what
# every existing test in this file passes -- never touches that import at
# all.
# ---------------------------------------------------------------------------

def is_empty_form(form) -> bool:
    """The emptiness predicate data-model.md's cross-cutting rule 2 pins
    verbatim for every row that reads an ``IMultiUnicode``/``IMultiString``
    form directly off LCM (this module's read path gets no Operations-layer
    "***" -> "" normalization -- CLAUDE.md). A real empty field surfaces as
    the literal string "***", not "" or ``None`` alone; testing only
    ``form in (None, "")`` silently undercounts every one of them.

    This predicate takes a plain ``str`` (or ``None``) -- it is NEVER handed
    a raw ``IMultiUnicode``/``IMultiString`` directly. "A real empty field
    surfaces as the literal string '***'" is true only of a string already
    read AT A SPECIFIC WRITING SYSTEM (``ITsString(field.get_String(ws)).Text``)
    -- a live multistring object itself is never ``in (None, "", "***")``
    under Python's ``in``/``==``. That resolution step is ``_read_ws``'s job
    (below); every caller of this predicate passes it an already-resolved
    string.

    Not used by T019's own three rows (2, 4, 9 -- none reads a form field),
    but established here for T034 (rows 1, 6, 7a all read ``IMoForm``-family
    multistring fields) so it does not need reinventing per row.
    """
    return form in (None, "", "***")


def _resolve_multistring_best_effort(value):
    """The no-context fallback ``is_zero_surface_form`` uses when it is
    called with no ``resolve`` callable (every existing caller, including
    every T015 test -- see that predicate's own docstring).

    - Already a ``str`` (or ``None``): returned as-is. T002's fixtures model
      ``.Form`` this way, so this keeps every existing predicate test
      passing unchanged, with no LCM import touched at all.
    - A live LCM multistring: resolved via ``.BestVernacularAnalysisAlternative``,
      the one multistring read that needs no explicit WS handle
      (flexicon's own ``FLExProject.py`` precedent, e.g. its
      ``BuildGotoURL``-adjacent text helpers) -- "best-effort" precisely
      because it is LCM's own generic pick, not the project's actual default
      vernacular/analysis. A ``_scan_*`` function that HAS a project instead
      passes an explicit ``resolve`` bound to ``_read_ws`` and never falls
      through to this helper.
    - Anything else, or any exception along the way: ``""`` -- this helper
      must never raise, and the ``from SIL.LCModel...`` import below is
      function-scoped so importing this module stays safe with no
      pythonnet/FieldWorks present (this module's own "why LCM imports are
      local" note).
    """
    if value is None or isinstance(value, str):
        return value if value is not None else ""
    try:
        from SIL.LCModel.Core.KernelInterfaces import ITsString

        text = ITsString(value.BestVernacularAnalysisAlternative).Text
        return text if text is not None else ""
    except Exception:
        return ""


def _ws_handles(project, override=None):
    """Resolve ``(vernacular_handle, analysis_handle)`` once per scan --
    the seam that closes the CP1 "focus by default on default analysis and
    default vernacular, as these are the ones the parser uses" directive.

    ``override``, when given, is returned verbatim instead of resolving the
    project's own defaults: ``run_grammar_scan``'s own ``ws`` parameter
    threads through to here, so a future caller can pin non-default writing
    systems without this module growing a second resolution path.

    Never raises: either handle that cannot be resolved (fresh/blank
    project, WS factory not yet warmed, etc.) comes back ``None`` instead,
    and ``_read_ws`` treats a ``None`` handle as "fall back to
    ``project.BestStr``", never as a crash.
    """
    if override is not None:
        return override
    try:
        vernacular = project.GetDefaultVernacularWSHandle()
    except Exception:
        vernacular = None
    try:
        analysis = project.GetDefaultAnalysisWSHandle()
    except Exception:
        analysis = None
    return vernacular, analysis


def _read_ws(project, field, ws_handle) -> str:
    """Resolve one multistring ``field`` to a plain ``str`` at
    ``ws_handle``, the one seam every multistring read in this module goes
    through before comparison or before reaching ``_found_object``.

    Never raises and never returns a non-``str``:

    - ``field`` is ``None`` -> ``""``.
    - ``field`` is already a ``str`` (T002's fixtures, or any caller that
      already resolved it) -> returned as-is.
    - Otherwise, a live ``IMultiUnicode``/``IMultiString``: read at
      ``ws_handle`` via ``ITsString(field.get_String(ws_handle)).Text``
      (flexicon's own ``FLExProject.py`` idiom, e.g. its stem-form and
      audio-path readers) -- ``None``/failure maps to ``""``.
    - ``ws_handle`` is ``None``, or the read above fails for any reason
      (including no pythonnet present -- exercised by this module's own
      unit tests, which run with no ``SIL.LCModel``): fall back to
      ``project.BestStr(field)``.
    - If even that fails or returns a non-``str``: ``""``.

    The ``from SIL.LCModel...`` import is function-scoped, taken only on
    the live-multistring branch, so importing this module (and calling this
    function on ``None``/``str`` input) stays safe with no pythonnet/
    FieldWorks present.
    """
    if field is None:
        return ""
    if isinstance(field, str):
        return field
    if ws_handle is not None:
        try:
            from SIL.LCModel.Core.KernelInterfaces import ITsString

            text = ITsString(field.get_String(ws_handle)).Text
            if text is not None:
                return text
        except Exception:
            pass
    try:
        best = project.BestStr(field)
        if isinstance(best, str):
            return best
    except Exception:
        pass
    return ""


def is_zero_surface_form(form, resolve=None) -> bool:
    """Row 1 predicate (data-model.md row 1; SPEC 9.5.4 row 1): a zero-surface
    ``IMoForm``, tested via ``is_empty_form`` on the form's own ``.Form``
    field, RESOLVED TO A STRING FIRST -- the same "***"/""/None emptiness
    rule, just applied after the writing-system read a live ``.Form`` needs
    (see ``is_empty_form``'s own docstring: a raw multistring object is
    never ``in (None, "", "***")``, so skipping this resolution step is
    exactly how a genuinely empty form went uncounted before this seam
    existed).

    ``resolve``, an optional ``(multistring_field) -> str`` callable, is the
    no-signature-change escape hatch: every existing caller (including
    every T015 test, which calls this with one positional argument against
    T002's plain-``str``-``.Form`` fixtures) keeps working via
    ``_resolve_multistring_best_effort`` as the default. A ``_scan_*``
    function that HAS a project passes ``resolve=lambda f: _read_ws(project,
    f, vernacular_handle)`` instead, so it reads at the project's own
    default vernacular WS rather than LCM's generic "best" pick.

    **Unconditional at CP1** (T034/T033, contracts/flextools_grammar_health.md
    "Row 1's `measured` wording is deliberately unconditional at CP1"): this
    signature deliberately takes no slot/position/reachability argument. The
    slot -> ``Affixes`` -> MSA -> owning entry -> ``AlternateFormsOS`` walk
    that would condition this on optional-slot reachability is deferred (the
    allomorph -> owning-entry hop is a known flexicon read gap, research D5,
    tasked flexicon-first under S9) -- every zero-surface ``IMoForm`` is
    counted regardless of where, or whether, it is reachable.
    """
    resolver = resolve if resolve is not None else _resolve_multistring_best_effort
    return is_empty_form(resolver(getattr(form, "Form", None)))


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


def _found_object(project, obj, label) -> Dict[str, Any]:
    """Build one ``FoundObject``-shaped plain dict (data-model.md
    `FoundObject`) -- never the pydantic model itself (this module cannot
    import ``server.models``; T020 revalidates through it).

    DEFENSE IN DEPTH (the crash this seam exists to make structurally
    impossible): every ``_scan_*`` row is expected to hand this a
    ``label`` already resolved to a ``str`` via ``_read_ws``, but if a
    future row -- or a bug in an existing one -- passes a raw
    ``IMultiUnicode``/``IMultiString`` instead, that object is never
    ``in (None, "", "***")`` and would otherwise sail straight into the
    finding dict and detonate at ``json.dumps`` (the exact shipped bug).
    So a non-``str`` ``label`` is coerced here, one last time, via
    ``project.BestStr`` -- and, failing that, ``""`` -- before it ever
    reaches the returned dict. After this, no non-``str`` label can leave
    this function under any circumstances.

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
    if not isinstance(label, str):
        try:
            resolved = project.BestStr(label)
        except Exception:
            resolved = None
        label = resolved if isinstance(resolved, str) else ""
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

def _scan_zero_surface_morph_repeatable(project, ws=None) -> Tuple[int, str, Optional[str], List[Dict[str, Any]]]:
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

    ``.Form`` is an ``IMultiUnicode``, resolved at the project's default
    VERNACULAR writing system (the user's own directive: "focus by default
    on default analysis and default vernacular, as these are the ones the
    parser uses") via the ``_ws_handles``/``_read_ws`` seam -- never
    compared or handed to ``_found_object`` while still a raw multistring
    object.
    """
    from SIL.LCModel import IMoFormRepository

    vernacular_handle, _ = _ws_handles(project, ws)
    resolve = lambda field: _read_ws(project, field, vernacular_handle)  # noqa: E731

    count = 0
    suspects: List[Dict[str, Any]] = []
    for form in project.ObjectsIn(IMoFormRepository):
        if is_zero_surface_form(form, resolve=resolve):
            count += 1
            # The form is empty by definition here, so its resolved .Form
            # value is None/""/"***" -- _found_object normalizes all three
            # to "" rather than this row hand-rolling the same check again.
            suspects.append(_found_object(project, form, resolve(form.Form)))

    measured = "{} allomorphs have an empty surface form".format(count)
    evidence_basis = "425x"  # PanGloss's own measured factor for row 1 (data-model.md row 1).
    return count, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 2 -- representation-variant-product (T019, check_id
# "representation-variant-product", not gated on T016).
# ---------------------------------------------------------------------------

def _scan_representation_variant_product(project) -> Tuple[int, str, Optional[str], List[Dict[str, Any]]]:
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
# Row 3a -- epenthesis-empty-struc-desc (T035, check_id
# "epenthesis-empty-struc-desc", NOT gated on T016 -- the epenthesis half of
# SPEC 9.5.4 row 3 reads only `IPhRegularRule`, a name research D4 already
# verified).
# ---------------------------------------------------------------------------

def _scan_epenthesis_empty_struc_desc(project) -> Tuple[int, str, Optional[str], List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 3 (first half) / data-model.md row 3a.

    LCM predicate (T033): ``IPhRegularRule`` where ``StrucDescOS`` is empty,
    with ``Disabled == False``. An empty structural description is how an
    epenthesis rule is spelled in LCM -- nothing on the left-hand side, so
    the rule can insert material anywhere its environment admits.

    ``StrucDescOS`` is an ``ILcmOwningSequence`` of ``IPhSimpleContext``, so
    its emptiness is a collection-level ``.Count == 0`` read -- deliberately
    NOT ``is_empty_form`` (data-model.md cross-cutting rule 2), which is the
    ``IMultiUnicode``/``IMultiString`` "***" predicate and does not apply to
    a collection.

    ``Disabled`` gating (data-model.md cross-cutting rule 7): applied via
    ``exclude_disabled_rules`` over the repository walk BEFORE anything is
    counted, never as a filter over an already-built result.

    The index-inheritance trap (cross-cutting rule 5): ``StrucDescOS`` and
    ``Disabled`` are declared once on the base ``IPhSegmentRule`` and are
    absent from ``IPhRegularRule``'s own ``properties`` array in
    ``liblcm_api_v11.0.0.json`` -- verified directly against that file.
    Their absence from ``flextools_get_object_api``'s own-properties listing
    for ``IPhRegularRule`` is not evidence of absence; C# interface
    inheritance carries both onto every ``IPhRegularRule`` receiver.

    Enumeration: ``project.ObjectsIn(IPhRegularRuleRepository)`` -- the
    generic-repository escape hatch, same idiom as rows 1/4/6/7a/10.

    Cast: ``IPhRegularRule(obj).StrucDescOS`` (T033's cast_example), applied
    unconditionally even though the repository already yields
    ``IPhRegularRule``-typed objects -- same
    cast-applied-unconditionally precedent rows 2/4/7a/9 set.
    """
    from SIL.LCModel import IPhRegularRule, IPhRegularRuleRepository

    count = 0
    suspects: List[Dict[str, Any]] = []
    for rule in exclude_disabled_rules(project.ObjectsIn(IPhRegularRuleRepository)):
        rr = IPhRegularRule(rule)
        struc_desc = rr.StrucDescOS
        if struc_desc is None or struc_desc.Count == 0:
            count += 1
            # IPhSegmentRule.Name is an IMultiUnicode, but T033's table names
            # no label source for this row -- "" per FoundObject.label's
            # documented empty spelling, matching rows 4/10's precedent.
            suspects.append(_found_object(project, rr, ""))

    measured = "{} phonological rules have an empty structural description".format(count)
    # data-model.md row 3a lists "--": PanGloss publishes no measured factor
    # for this row, so nothing is invented here (SPEC 8.4).
    evidence_basis = None
    return count, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 3b -- metathesis-rule-present (T035, check_id "metathesis-rule-present").
# GATED on T016 -- and research D9 records `IPhMetathesisRule` as CONFIRMED
# ("WRITTEN"): entity present at liblcm_api_v11.0.0.json:108341, interfaces
# [ICmObject, ICmObjectOrId, IPhSegmentRule], class-name map
# "PhMetathesisRule" -> "IPhMetathesisRule". So this half is written as a
# normal check and is NOT routed to checks_skipped.
# ---------------------------------------------------------------------------

def _scan_metathesis_rule_present(project) -> Tuple[int, str, Optional[str], List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 3 (second half) / data-model.md row 3b.

    LCM predicate (T033): ``IPhMetathesisRule`` count, with
    ``Disabled == False``. This is a type test only -- the mere presence of
    an enabled metathesis rule is the whole-grammar cost class SPEC 9.5.4
    row 3 names; no property of the rule is inspected.

    ``Disabled`` gating (cross-cutting rule 7): ``exclude_disabled_rules``
    over the repository walk, before counting. ``Disabled`` reaches an
    ``IPhMetathesisRule`` receiver by inheritance from ``IPhSegmentRule``
    (cross-cutting rule 5) -- research D9 checked this directly rather than
    assuming it, and confirmed the property is correctly absent from
    ``IPhMetathesisRule``'s own ``properties`` array.

    Enumeration: ``project.ObjectsIn(IPhMetathesisRuleRepository)``.

    Cast: none (T033's cast_example: "type test only ... no property cast").
    """
    from SIL.LCModel import IPhMetathesisRuleRepository

    count = 0
    suspects: List[Dict[str, Any]] = []
    for rule in exclude_disabled_rules(project.ObjectsIn(IPhMetathesisRuleRepository)):
        count += 1
        # No label source in T033's table for this row -- "" as with row 3a.
        suspects.append(_found_object(project, rule, ""))

    measured = "{} metathesis rules are present in the grammar".format(count)
    evidence_basis = None  # data-model.md row 3b lists "--" -- no PanGloss factor.
    return count, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 4 -- unbounded-quantifier (T019, check_id "unbounded-quantifier",
# not gated on T016).
# ---------------------------------------------------------------------------

def _scan_unbounded_quantifier(project) -> Tuple[int, str, Optional[str], List[Dict[str, Any]]]:
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
# Row 5 -- rule-product-morph-phon (T035, check_id "rule-product-morph-phon").
# GATED on T016 for BOTH its multiplicands -- and research D9 records
# `IMoAffixProcess` as CONFIRMED ("WRITTEN": entity present at
# liblcm_api_v11.0.0.json:94897, interfaces [ICmObject, ICmObjectOrId,
# IMoAffixForm, IMoForm], class-name map "MoAffixProcess" ->
# "IMoAffixProcess") and `IPhMetathesisRule` likewise CONFIRMED (see row 3b
# above). Both gates open, so this row is written as a normal check and is
# NOT routed to checks_skipped.
# ---------------------------------------------------------------------------

def _scan_rule_product_morph_phon(project, ws=None) -> Tuple[int, str, Optional[str], List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 5 / data-model.md row 5.

    LCM predicate (T033): ``IMoAffixProcess`` count x (``IPhRegularRule`` +
    ``IPhMetathesisRule``, ``Disabled == False``) count -- the morphological
    multiplicand times the phonological one.

    ``Disabled`` gating (cross-cutting rule 7) applies to the phonological
    multiplicand only: ``Disabled`` is an ``IPhSegmentRule`` property, and
    ``IMoAffixProcess`` is an ``IMoForm``, not a segment rule, so it has no
    ``Disabled`` to gate on. Both rule repositories are filtered through
    ``exclude_disabled_rules`` BEFORE either count is taken, never after the
    product is formed.

    ``count`` is the product itself (matching the row's own `measured`
    wording basis), reported as a number and never compared against
    PanGloss's placeholder threshold of 64 as a pass/fail line -- D7 / SPEC
    9.5.3: "treat their numbers as placeholders". That threshold is carried
    in ``evidence_basis`` as *their* measurement, which is the only place a
    number of theirs belongs.

    ``objects[]`` names both multiplicands' members -- the affix processes
    first, then the enabled phonological rules -- in repository enumeration
    order, never magnitude-ordered, capped by ``_emit``'s own preview cap.

    Enumeration: ``project.ObjectsIn(...)`` over the three repositories.
    T033's table says "counts via repository ``.Count``"; this walks them
    instead because the phonological multiplicand must have its disabled
    rules excluded before counting (a repository-level ``.Count`` cannot),
    and because ``objects[]`` needs the members themselves.

    Cast: none (T033's cast_example) -- no property is read off a rule here,
    and each repository already yields its own interface type.
    """
    from SIL.LCModel import (
        IMoAffixProcessRepository,
        IPhMetathesisRuleRepository,
        IPhRegularRuleRepository,
    )

    vernacular_handle, _ = _ws_handles(project, ws)

    suspects: List[Dict[str, Any]] = []

    affix_process_count = 0
    for affix_process in project.ObjectsIn(IMoAffixProcessRepository):
        affix_process_count += 1
        # IMoAffixProcess is an IMoForm, so .Form is its label source --
        # same read rows 1/6 use, resolved at the default vernacular WS via
        # _read_ws before it ever reaches _found_object.
        suspects.append(
            _found_object(project, affix_process, _read_ws(project, affix_process.Form, vernacular_handle))
        )

    phonological_rule_count = 0
    for repository in (IPhRegularRuleRepository, IPhMetathesisRuleRepository):
        for rule in exclude_disabled_rules(project.ObjectsIn(repository)):
            phonological_rule_count += 1
            suspects.append(_found_object(project, rule, ""))

    product = affix_process_count * phonological_rule_count

    measured = "{} is the morphological x phonological rule product".format(product)
    evidence_basis = "64"  # PanGloss's own placeholder threshold (data-model.md row 5), never a pass/fail line here.
    return product, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 6 -- partial-morpheme-incomplete-form (T034, check_id
# "partial-morpheme-incomplete-form", not gated on T016).
# ---------------------------------------------------------------------------

def _scan_partial_morpheme_incomplete_form(project, ws=None) -> Tuple[int, str, Optional[str], List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 6 / data-model.md row 6.

    LCM predicate (T033, research D4): ``IMoForm.IsComplete == False`` --
    the predicate research D4 found already exists on LCM rather than
    reimplementing "lacking category" by hand, mirroring 9.3.1's use of
    ``IWfiMorphBundle.IsComplete``.

    Enumeration: same ``project.ObjectsIn(IMoFormRepository)`` walk as row 1
    -- a separate walk per this module's one-function-per-row layout (see
    module docstring), not a shared iteration with row 1's scan.

    Cast: none (T033's cast_example) -- ``IMoForm.IsComplete`` is a direct
    property. ``.Form`` (the label source) is resolved at the default
    vernacular WS via ``_read_ws`` -- same seam as row 1.
    """
    from SIL.LCModel import IMoFormRepository

    vernacular_handle, _ = _ws_handles(project, ws)

    count = 0
    suspects: List[Dict[str, Any]] = []
    for form in project.ObjectsIn(IMoFormRepository):
        if not form.IsComplete:
            count += 1
            suspects.append(_found_object(project, form, _read_ws(project, form.Form, vernacular_handle)))

    measured = "{} morphs are incomplete".format(count)
    evidence_basis = "hc-partial-morpheme"
    return count, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 7a -- stem-allomorph-stem-name-restriction (T034, check_id
# "stem-allomorph-stem-name-restriction", already verified -- not gated on
# T016 despite sharing row 7 with the gated 7b half below).
# ---------------------------------------------------------------------------

def _scan_stem_allomorph_stem_name_restriction(project, ws=None) -> Tuple[int, str, Optional[str], List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 7 (first half) / data-model.md row 7a.

    LCM predicate (T033, research D4 -- VERIFIED, not part of D9's gate):
    ``IMoStemAllomorph.StemNameRA != null`` (kind ``RA`` -> ``IMoStemName``).

    Enumeration: ``project.ObjectsIn(IMoStemAllomorphRepository)`` -- the
    generic-repository escape hatch, same idiom as rows 1/4/6.

    Cast: ``IMoStemAllomorph(obj).StemNameRA`` (T033's cast_example),
    applied unconditionally even though ``ObjectsIn`` already yields
    ``IMoStemAllomorph``-typed objects -- same reasoning as rows 2/4/9's
    own cast-applied-unconditionally precedent. ``.Form`` (the label
    source) is resolved at the default vernacular WS via ``_read_ws`` --
    same seam as rows 1/5/6.
    """
    from SIL.LCModel import IMoStemAllomorph, IMoStemAllomorphRepository

    vernacular_handle, _ = _ws_handles(project, ws)

    count = 0
    suspects: List[Dict[str, Any]] = []
    for allomorph in project.ObjectsIn(IMoStemAllomorphRepository):
        sa = IMoStemAllomorph(allomorph)
        if sa.StemNameRA is not None:
            count += 1
            suspects.append(_found_object(project, sa, _read_ws(project, sa.Form, vernacular_handle)))

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

def _scan_multiple_allomorphs_per_entry(project) -> Tuple[int, str, Optional[str], List[Dict[str, Any]]]:
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
# Row 8 -- unordered-rule-application-stratum-pair (T035, check_id
# "unordered-rule-application-stratum-pair", not gated on T016 -- this is
# T027's CORRECTED mapping).
# ---------------------------------------------------------------------------

def _scan_unordered_rule_application_stratum_pair(project) -> Tuple[int, str, Optional[str], List[Dict[str, Any]]]:
    """SPEC 9.5.4 row 8 (as corrected by T027) / data-model.md row 8.

    LCM predicate (T033): group ``IPhSegmentRule`` (``Disabled == False``)
    by its own ``(InitialStratumRA, FinalStratumRA)`` pair; within each
    group, count members and/or ``OrderNumber`` spread.

    **Where ordering lives.** On the rule: ``IPhSegmentRule.OrderNumber``,
    with the stratum pair referenced from the rule via ``InitialStratumRA``
    / ``FinalStratumRA``. ``IMoStratum`` has NO rule collection -- its own
    properties are exactly ``Abbreviation``, ``Description``, ``Name``,
    ``PhonemesRA`` (verified against ``liblcm_api_v11.0.0.json``) -- so this
    function walks rules and groups by their stratum references, and never
    walks strata looking for a rule list. SPEC 9.5.4's own note: the
    linguist's mental model ("this rule belongs to this stratum") and LCM's
    storage direction agree; only the direction of the reference differs,
    and the absence of a collection on ``IMoStratum`` is not evidence that
    strata are unordered or unassigned. ``measured`` below therefore speaks
    the user's direction -- rules assigned to a stratum pair -- and never
    "a stratum owns rules".

    **``OrderNumber`` is comparable only within one stratum-pair grouping**
    (data-model.md cross-cutting rule 3): it is a per-pair counter, not a
    grammar-wide ordinal. Every ``OrderNumber`` read below happens inside a
    single group's own member list, and two rules' ``OrderNumber``s are
    compared only when they already share the same
    ``(InitialStratumRA, FinalStratumRA)`` key. Nothing here sorts by
    ``OrderNumber`` -- not across pairs, not within one either: groups and
    their members stay in repository enumeration order, so this function
    adds no sort step to a module whose fixed-order guarantee depends on
    there being none.

    Grouping key: the two strata's ``Hvo``s (``None`` when the reference is
    null), not their names. An ``Hvo`` is an identity that is already a
    plain int, so it needs no ``IMultiUnicode`` read and cannot collide the
    way two same-named strata could.

    ``count`` is the number of enabled rules that sit in a stratum-pair
    grouping holding more than one rule -- the ``N`` PanGloss's "2^N, capped
    at N=6" factor is about. A grouping holding exactly one rule contributes
    nothing: a single rule has no other rule to be ordered against.
    ``measured`` additionally reports how many of those rules share an
    ``OrderNumber`` with another rule *in the same grouping* -- the
    ``OrderNumber``-spread arm of T033's "and/or", computed strictly
    within-group. Neither number is summed with any other row's count.

    Enumeration: ``project.ObjectsIn(IPhSegmentRuleRepository)`` -- the base
    interface's own repository, which yields both concrete rule types
    (``IPhRegularRule`` and ``IPhMetathesisRule``) in one walk.

    Cast: ``IPhSegmentRule(obj).OrderNumber`` / ``.InitialStratumRA`` /
    ``.FinalStratumRA`` (T033's cast_example), applied unconditionally per
    rows 2/4/7a/9's precedent. Cross-cutting rule 5 again: all four of
    ``OrderNumber``/``InitialStratumRA``/``FinalStratumRA``/``Disabled`` are
    declared once on ``IPhSegmentRule`` and are invisible in
    ``flextools_get_object_api``'s own-properties listing for either derived
    interface -- that absence is not evidence of absence.
    """
    from SIL.LCModel import IPhSegmentRule, IPhSegmentRuleRepository

    # Insertion-ordered: dicts preserve insertion order, so groups and their
    # members stay in repository enumeration order end to end.
    groups: Dict[Tuple[Any, Any], List[Any]] = {}
    for rule in exclude_disabled_rules(project.ObjectsIn(IPhSegmentRuleRepository)):
        sr = IPhSegmentRule(rule)
        initial_stratum = sr.InitialStratumRA
        final_stratum = sr.FinalStratumRA
        key = (
            getattr(initial_stratum, "Hvo", None),
            getattr(final_stratum, "Hvo", None),
        )
        groups.setdefault(key, []).append(sr)

    count = 0
    shared_order_number_count = 0
    suspects: List[Dict[str, Any]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        # Every OrderNumber read and comparison below is confined to this
        # one group -- i.e. to rules that already share a stratum pair.
        order_numbers = [member.OrderNumber for member in members]
        # Indexed rather than zip()ed: order_numbers is built from members by
        # comprehension, so the two are the same length by construction, and
        # indexing avoids both a second CLR read of OrderNumber per member and
        # any dependence on zip(strict=) in the subprocess interpreter.
        for index, member in enumerate(members):
            order_number = order_numbers[index]
            count += 1
            if order_numbers.count(order_number) > 1:
                shared_order_number_count += 1
            # T033's table names no label source for this row -- "" per
            # FoundObject.label's documented empty spelling (rows 4/10).
            suspects.append(_found_object(project, member, ""))

    measured = (
        "{} rules are ordered within a stratum-pair grouping that holds more "
        "than one rule, and {} of those rules share an OrderNumber with "
        "another rule assigned to the same stratum pair"
    ).format(count, shared_order_number_count)
    evidence_basis = "2^N, capped at N=6"  # PanGloss's own factor (data-model.md row 8).
    return count, measured, evidence_basis, suspects


# ---------------------------------------------------------------------------
# Row 9 -- duplicate-feature-bundle (T019, check_id
# "duplicate-feature-bundle", not gated on T016).
# ---------------------------------------------------------------------------

def _scan_duplicate_feature_bundle(project) -> Tuple[int, str, Optional[str], List[Dict[str, Any]]]:
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

def _scan_optional_template_slot_branching(project) -> Tuple[int, str, Optional[str], List[Dict[str, Any]]]:
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

def run_grammar_scan(project, ws=None) -> Dict[str, Any]:
    """Run every implemented SPEC 9.5.4 check against ``project`` and
    return a plain, JSON-serializable dict -- never a pydantic model (see
    module docstring).

    ``ws``, an optional ``(vernacular_handle, analysis_handle)`` pair,
    overrides the default writing systems every multistring read in rows
    1/5/6/7a resolves at (via ``_ws_handles``/``_read_ws``). ``None`` (the
    default) means "use the project's own default vernacular/analysis" --
    the user's own directive that these are the two writing systems the
    parser uses. This module's callable-with-one-argument contract holds
    unchanged: T030's fixed "module code" calls
    ``run_grammar_scan(project)``, and this parameter is not wired to any
    tool-level input this cycle -- it exists so a future caller can pin
    non-default writing systems without a second resolution path.

    Structural fixed-order guarantee (data-model.md: "Findings are grouped
    by check_id and never ordered by count"; SPEC S7/D7): ``findings`` is
    built by calling ``_emit`` exactly once per implemented row, in SPEC
    9.5.4 row order -- all twelve check slots (rows 1, 2, 3a, 3b, 4, 5, 6,
    7a, 7b, 8, 9, 10) are now present, T019 having contributed 2/4/9, T034
    1/6/7a/7b/10 and T035 3a/3b/5/8. There is no sort step anywhere in this
    function -- order is guaranteed by Python executing these statements
    top-to-bottom, the same way ``checks_run`` accumulates in call order,
    not by any comparator applied after the fact. A later row is added the
    same way each of these was: one ``_emit(...)`` call (or, for a row T016
    leaves unconfirmed, ``checks_skipped.append(skipped_check(...))``) in
    row-number order -- no restructuring of this function, and no change to
    ``_emit`` itself.

    ``checks_skipped`` is empty as shipped: every T016-gated sub-check
    (rows 3b, 5, 7b) was recorded CONFIRMED by research D9, so each is
    written as a normal check. The list and ``skipped_check`` stay in place
    as the declared fallback, per data-model.md cross-cutting rule 4's rule
    that a gated sub-check is never silently dropped either way.
    """
    checks_run: List[str] = []
    checks_skipped: List[Dict[str, str]] = []
    findings: List[Dict[str, Any]] = []

    count, measured, evidence_basis, objects = _scan_zero_surface_morph_repeatable(project, ws=ws)
    _emit(checks_run, findings, "zero-surface-morph-repeatable", 1, count, measured, evidence_basis, objects)

    count, measured, evidence_basis, objects = _scan_representation_variant_product(project)
    _emit(checks_run, findings, "representation-variant-product", 2, count, measured, evidence_basis, objects)

    count, measured, evidence_basis, objects = _scan_epenthesis_empty_struc_desc(project)
    _emit(checks_run, findings, "epenthesis-empty-struc-desc", 3, count, measured, evidence_basis, objects)

    # Row 3b, "metathesis-rule-present": gated on T016, and research D9
    # records IPhMetathesisRule as CONFIRMED -- written here as a normal
    # check, not routed to checks_skipped.
    count, measured, evidence_basis, objects = _scan_metathesis_rule_present(project)
    _emit(checks_run, findings, "metathesis-rule-present", 3, count, measured, evidence_basis, objects)

    count, measured, evidence_basis, objects = _scan_unbounded_quantifier(project)
    _emit(checks_run, findings, "unbounded-quantifier", 4, count, measured, evidence_basis, objects)

    # Row 5, "rule-product-morph-phon": gated on T016 for both multiplicands,
    # and research D9 records IMoAffixProcess and IPhMetathesisRule as
    # CONFIRMED -- written here as a normal check, not routed to
    # checks_skipped.
    count, measured, evidence_basis, objects = _scan_rule_product_morph_phon(project, ws=ws)
    _emit(checks_run, findings, "rule-product-morph-phon", 5, count, measured, evidence_basis, objects)

    count, measured, evidence_basis, objects = _scan_partial_morpheme_incomplete_form(project, ws=ws)
    _emit(checks_run, findings, "partial-morpheme-incomplete-form", 6, count, measured, evidence_basis, objects)

    count, measured, evidence_basis, objects = _scan_stem_allomorph_stem_name_restriction(project, ws=ws)
    _emit(checks_run, findings, "stem-allomorph-stem-name-restriction", 7, count, measured, evidence_basis, objects)

    # Row 7b, "multiple-allomorphs-per-entry": CONFIRMED by research D9
    # (ILexEntry.AlternateFormsOS resolved unambiguously) -- written here as
    # a normal check, not routed to checks_skipped.
    count, measured, evidence_basis, objects = _scan_multiple_allomorphs_per_entry(project)
    _emit(checks_run, findings, "multiple-allomorphs-per-entry", 7, count, measured, evidence_basis, objects)

    count, measured, evidence_basis, objects = _scan_unordered_rule_application_stratum_pair(project)
    _emit(
        checks_run,
        findings,
        "unordered-rule-application-stratum-pair",
        8,
        count,
        measured,
        evidence_basis,
        objects,
    )

    count, measured, evidence_basis, objects = _scan_duplicate_feature_bundle(project)
    _emit(checks_run, findings, "duplicate-feature-bundle", 9, count, measured, evidence_basis, objects)

    count, measured, evidence_basis, objects = _scan_optional_template_slot_branching(project)
    _emit(checks_run, findings, "optional-template-slot-branching", 10, count, measured, evidence_basis, objects)

    return {
        "checks_run": checks_run,
        "checks_skipped": checks_skipped,
        "findings": findings,
    }
