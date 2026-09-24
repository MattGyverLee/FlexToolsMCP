#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Which lexical entries can reach the HermitCrab grammar (parser-check CP4,
FR-039; research R-12; spec D-1).

THE SILENT DROP. `HCLoader` loads an entry's forms only when they pass two
predicates, `IsValidLexEntryForm` (`HCLoader.cs:579-589`) and `IsValidRuleForm`
(`:536-569`) -- and a form that fails is simply skipped. NOTHING is logged. An
entry whose only lexeme form was emptied, or marked abstract, vanishes from the
parser's view and leaves no line in `HCLoadErrors.xml`. Filing against that
grammar deletes every analysis the entry used to license. A gate that compares
load errors alone passes that case; this module is how the gate sees it.

THIS IS A PORT, AND A JUSTIFIED VIOLATION OF CONSTITUTION PRINCIPLE VI. The two
predicates are PRIVATE INSTANCE methods of `HCLoader` and depend on mid-load
state (`IsValidEnvironment` needs the loader's phoneme and natural-class
tables), so they cannot be called by reflection. Reflecting on the loaded
`Language` could COUNT entries but not NAME the dropped ones, which FR-039
requires. So the logic is copied, line for line, with the C# line each rule
mirrors named beside it -- and pinned: the live parity test
(`tests/test_parse_live_cp4.py`, parity group, T081) fails the suite if this
port and the loader FieldWorks actually runs disagree on the count.

WHAT THE PORT COVERS, AND WHAT IT CANNOT. The parity test found the first
version too generous (T081, on `Malay Parsing-20230810withHC`: 280 entries
by the port, 277 by the loader, no load error logged). Three more silent
drops are now ported:

  * an infix with NO position, and a bracketed prefix/suffix with NO
    environment: `IsValidRuleForm` (`:558-564`) requires one that validates,
    so an empty list rejects the form before anything is logged;
  * an entry whose MSAs route nowhere: the stem side loads one `LexEntry` per
    stem MSA (`LoadLexEntries`), the rule side one rule per affix MSA
    (`LoadMorphologicalRule`) -- an entry with no MSA of the right kind
    reaches neither (a variant with no senses borrows its components' MSAs);
  * an inflectional affix whose every slot lies outside an ENABLED template:
    a slotted rule joins no stratum (`s = null` in `LoadMorphologicalRule`)
    and reaches the grammar only through a template the loader keeps
    (`:295-300`). Disabling a template drops its affixes without a word.

The one residual: WHETHER a present environment or position validates is not
ported. `IsValidEnvironment` needs the loader's phoneme and natural-class
tables, so an affix whose every environment is present but invalid is still
counted eligible -- and the loader drops it silently. Editing an environment
into an invalid one is therefore the one D-1 path this gate does not see.

TWO LAYERS. `entry_facts` reads an LCM entry into plain facts (read only, in
the worker that has the project open); the predicates below run on those
facts, so each branch is testable offline against a plain dict.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

__all__ = [
    "MORPH_TYPES",
    "is_valid_lex_entry_form",
    "is_valid_rule_form",
    "has_valid_rule_form",
    "is_eligible",
    "entry_facts",
    "eligible_from_facts",
    "eligible_entries",
    "enabled_template_slots",
]

#: `MoMorphTypeTags.kguidMorph*`, lowercase (FieldWorks'
#: `FwAvalonia/Detail/MorphTypeSwapLogic.cs` mirrors the same model GUIDs).
MORPH_TYPES: Dict[str, str] = {
    "root": "d7f713e5-e8cf-11d3-9764-00c04f186933",
    "stem": "d7f713e8-e8cf-11d3-9764-00c04f186933",
    "bound_root": "d7f713e4-e8cf-11d3-9764-00c04f186933",
    "bound_stem": "d7f713e7-e8cf-11d3-9764-00c04f186933",
    "particle": "56db04bf-3d58-44cc-b292-4c8aa68538f4",
    "clitic": "c2d140e5-7ca9-41f4-a69a-22fc7049dd2c",
    "proclitic": "d7f713e2-e8cf-11d3-9764-00c04f186933",
    "enclitic": "d7f713e1-e8cf-11d3-9764-00c04f186933",
    "phrase": "a23b6faa-1052-4f4d-984b-4b338bdaf95f",
    "discontiguous_phrase": "0cc8c35a-cee9-434d-be58-5d29130fba5b",
    "prefix": "d7f713db-e8cf-11d3-9764-00c04f186933",
    "suffix": "d7f713dd-e8cf-11d3-9764-00c04f186933",
    "infix": "d7f713da-e8cf-11d3-9764-00c04f186933",
    "simulfix": "d7f713dc-e8cf-11d3-9764-00c04f186933",
    "suprafix": "d7f713de-e8cf-11d3-9764-00c04f186933",
    "circumfix": "d7f713df-e8cf-11d3-9764-00c04f186933",
    "prefixing_interfix": "af6537b0-7175-4387-ba6a-36547d37fb13",
    "infixing_interfix": "18d9b1c3-b5b6-4c07-b92c-2fe1d2281bd4",
    "suffixing_interfix": "3433683d-08a9-4bae-ae53-2a7798f64068",
}
_BY_GUID = {guid: name for name, guid in MORPH_TYPES.items()}

#: `HCLoader.IsStemType` (`:590-603`).
_STEM_TYPES = frozenset({"root", "stem", "bound_root", "bound_stem", "phrase"})
#: `HCLoader.IsCliticType` (`:605-619`).
_CLITIC_TYPES = frozenset({"clitic", "enclitic", "proclitic", "particle"})

_DOTTED_CIRCLE = "◌"


def _type_name(facts: Optional[Dict[str, Any]]) -> Optional[str]:
    guid = (facts or {}).get("morph_type")
    return _BY_GUID.get(str(guid).lower()) if guid else None


def _form_text(facts: Dict[str, Any]) -> str:
    # `RemoveDottedCircles` (`:153`): placeholder circles are not content.
    return str(facts.get("form") or "").replace(_DOTTED_CIRCLE, "")


def is_valid_lex_entry_form(facts: Optional[Dict[str, Any]]) -> bool:
    """`HCLoader.IsValidLexEntryForm` (`:579-589`)."""
    if not facts or facts.get("class_name") != "MoStemAllomorph":   # :581-582
        return False
    if facts.get("is_abstract") or not _form_text(facts):           # :584-586
        return False
    return _type_name(facts) in _STEM_TYPES | _CLITIC_TYPES         # :588


def is_valid_rule_form(facts: Optional[Dict[str, Any]]) -> bool:
    """`HCLoader.IsValidRuleForm` (`:536-569`); a present environment is taken as valid."""
    if not facts:
        return False
    if facts.get("class_name") == "MoAffixProcess":                 # :538-540
        return int(facts.get("input_count") or 0) > 1 or int(facts.get("output_count") or 0) > 1
    if facts.get("is_abstract") or not _form_text(facts):           # :542-544
        return False
    kind = _type_name(facts)
    if kind in ("proclitic", "enclitic"):                            # :550-552
        return True
    if kind in ("prefix", "prefixing_interfix", "suffix", "suffixing_interfix"):  # :554-560
        text = _form_text(facts)
        if "[" in text and "[...]" not in text:                      # :558-559
            # Needs an environment that validates. Presence is ported;
            # validity is not (the module docstring's residual).
            return int(facts.get("env_count") or 0) > 0
        return True
    if kind in ("infix", "infixing_interfix"):                       # :562-564
        # Needs a position that validates: no position, no rule form.
        return int(facts.get("position_count") or 0) > 0
    return False                                                     # :568


def _all_forms(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    forms = list(entry.get("alternates") or [])
    if entry.get("lexeme"):
        forms.append(entry["lexeme"])
    return forms


def has_valid_rule_form(entry: Dict[str, Any]) -> bool:
    """`HCLoader.HasValidRuleForm` (`:517-534`), incl. the circumfix branch."""
    lexeme = entry.get("lexeme") or {}
    is_circumfix = _type_name(lexeme) == "circumfix"
    if is_circumfix and lexeme.get("class_name") == "MoAffixAllomorph":   # :519
        has_prefix = has_suffix = False
        for alternate in entry.get("alternates") or []:
            if not is_valid_rule_form(alternate):
                continue
            kind = _type_name(alternate)
            if kind == "prefix":
                has_prefix = True
            elif kind == "suffix":
                has_suffix = True
            if has_prefix and has_suffix:
                return True
        return False
    return any(is_valid_rule_form(f) for f in _all_forms(entry))    # :533


#: MSA kinds `LoadMorphologicalRule` builds a rule for; any other kind yields
#: none. `infl` routes only if slotless, or slotted in an enabled template.
_RULE_MSA_KINDS = frozenset({"deriv", "infl", "unclassified", "stem"})


def _msas_for(entry: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """The MSAs the loader consults: the entry's own, plus -- for an entry
    with no senses -- its variant components' (`LoadLexEntries`,
    `LoadMorphologicalRules`). None when the reader could not tell; routing
    is then not judged."""
    own = entry.get("msas")
    if own is None:
        return None
    msas = list(own)
    if int(entry.get("sense_count") or 0) == 0:
        msas.extend(entry.get("variant_msas") or [])
    return msas


def _routes_a_rule(msa: Dict[str, Any], template_slots: Optional[frozenset]) -> bool:
    kind = msa.get("kind")
    if kind not in _RULE_MSA_KINDS:
        return False
    slots = msa.get("slots") or []
    if kind != "infl" or not slots:
        return True                                   # joins the stratum
    if template_slots is None:
        return True                                   # templates unread: not judged
    return any(str(slot).lower() in template_slots for slot in slots)   # :295-300


def is_eligible(entry: Dict[str, Any], template_slots: Optional[frozenset] = None) -> bool:
    """Would the loader take any of this entry's forms? (`HCLoader.cs:256-293`).

    Stem side: some form passes `IsValidLexEntryForm`, and a stem MSA builds a
    `LexEntry` from it. Rule side: some form passes `IsValidRuleForm`, the
    entry passes `HasValidRuleForm` (`:849-850`), and some MSA routes a rule
    into the grammar. `template_slots` is the set of slot GUIDs in enabled
    templates (`enabled_template_slots`); None means unread, and slotted
    inflectional MSAs are then not judged.
    """
    forms = _all_forms(entry)
    msas = _msas_for(entry)
    if any(is_valid_lex_entry_form(f) for f in forms):
        if msas is None or any(m.get("kind") == "stem" for m in msas):
            return True
    if any(is_valid_rule_form(f) for f in forms) and has_valid_rule_form(entry):
        if msas is None or any(_routes_a_rule(m, template_slots) for m in msas):
            return True
    return False


def eligible_from_facts(
    entries: Iterable[Dict[str, Any]], template_slots: Optional[Iterable[str]] = None
) -> List[Dict[str, str]]:
    """`[{entry_guid, headword}]` for every eligible entry, in the given order."""
    slots = None if template_slots is None else frozenset(str(x).lower() for x in template_slots)
    return [
        {"entry_guid": e["entry_guid"], "headword": e.get("headword") or ""}
        for e in entries if e.get("entry_guid") and is_eligible(e, slots)
    ]


# ---------------------------------------------------------------------------
# The reader: LCM objects -> plain facts. Reads only.
# ---------------------------------------------------------------------------


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = getattr(value, "Text", value)
    text = "" if text is None else str(text)
    return "" if text == "***" else text


def _form_facts(form: Any) -> Optional[Dict[str, Any]]:
    if form is None:
        return None
    class_name = str(getattr(form, "ClassName", "") or "")
    facts: Dict[str, Any] = {
        "class_name": class_name,
        "morph_type": None,
        "is_abstract": False,
        "form": "",
        "input_count": 0,
        "output_count": 0,
        "env_count": 0,
        "position_count": 0,
    }
    try:
        morph_type = getattr(form, "MorphTypeRA", None)
        guid = getattr(morph_type, "Guid", None) if morph_type is not None else None
        facts["morph_type"] = str(guid).lower() if guid is not None else None
    except Exception:  # noqa: BLE001 -- an unreadable type is no type
        pass
    try:
        facts["is_abstract"] = bool(getattr(form, "IsAbstract", False))
    except Exception:  # noqa: BLE001
        pass
    try:
        facts["form"] = _text(getattr(getattr(form, "Form", None),
                                      "VernacularDefaultWritingSystem", None))
    except Exception:  # noqa: BLE001
        pass
    if class_name == "MoAffixAllomorph":
        allomorph = form
        try:
            from SIL.LCModel import IMoAffixAllomorph  # type: ignore[import-not-found]

            allomorph = IMoAffixAllomorph(form)
        except Exception:  # noqa: BLE001 -- no CLR (a test double), or already typed
            pass
        for key, attr in (("env_count", "PhoneEnvRC"), ("position_count", "PositionRS")):
            try:
                facts[key] = int(getattr(getattr(allomorph, attr, None), "Count", 0) or 0)
            except Exception:  # noqa: BLE001
                facts[key] = 0
    if class_name == "MoAffixProcess":
        process = form
        try:
            from SIL.LCModel import IMoAffixProcess  # type: ignore[import-not-found]

            process = IMoAffixProcess(form)
        except Exception:  # noqa: BLE001 -- no CLR (a test double), or already typed
            pass
        for key, attr in (("input_count", "InputOS"), ("output_count", "OutputOS")):
            try:
                facts[key] = int(getattr(getattr(process, attr, None), "Count", 0) or 0)
            except Exception:  # noqa: BLE001
                facts[key] = 0
    return facts


_MSA_KINDS = {
    "MoStemMsa": "stem",
    "MoDerivAffMsa": "deriv",
    "MoInflAffMsa": "infl",
    "MoUnclassifiedAffixMsa": "unclassified",
}


def _msa_facts(msa: Any) -> Dict[str, Any]:
    kind = _MSA_KINDS.get(str(getattr(msa, "ClassName", "") or ""), "other")
    slots: List[str] = []
    if kind == "infl":
        typed = msa
        try:
            from SIL.LCModel import IMoInflAffMsa  # type: ignore[import-not-found]

            typed = IMoInflAffMsa(msa)
        except Exception:  # noqa: BLE001 -- no CLR (a test double), or already typed
            pass
        slots = [str(slot.Guid).lower() for slot in list(getattr(typed, "SlotsRC", None) or [])]
    return {"kind": kind, "slots": slots}


def _variant_msas(entry: Any) -> List[Dict[str, Any]]:
    """The MSAs a sense-less variant borrows from its components."""
    out: List[Dict[str, Any]] = []
    for ref in list(getattr(entry, "EntryRefsOS", None) or []):
        for component in list(getattr(ref, "ComponentLexemesRS", None) or []):
            owned = getattr(component, "MorphoSyntaxAnalysesOC", None)
            if owned is not None:                                     # a main entry
                out.extend(_msa_facts(m) for m in list(owned))
                continue
            msa = getattr(component, "MorphoSyntaxAnalysisRA", None)  # a sense
            if msa is None:
                try:
                    from SIL.LCModel import ILexSense  # type: ignore[import-not-found]

                    msa = ILexSense(component).MorphoSyntaxAnalysisRA
                except Exception:  # noqa: BLE001
                    msa = None
            if msa is not None:
                out.append(_msa_facts(msa))
    return out


def entry_facts(entry: Any) -> Dict[str, Any]:
    """One LCM `ILexEntry` as the facts the predicates read."""
    guid = getattr(entry, "Guid", None)
    alternates = []
    try:
        alternates = [f for f in (_form_facts(a) for a in list(entry.AlternateFormsOS)) if f]
    except Exception:  # noqa: BLE001
        alternates = []
    try:
        headword = _text(getattr(entry, "HeadWord", None))
    except Exception:  # noqa: BLE001
        headword = ""
    msas: Optional[List[Dict[str, Any]]]
    try:
        msas = [_msa_facts(m) for m in list(entry.MorphoSyntaxAnalysesOC)]
        sense_count = int(entry.SensesOS.Count)
        variant_msas = _variant_msas(entry) if sense_count == 0 else []
    except Exception:  # noqa: BLE001 -- unread routing is not judged, never "routes nowhere"
        msas, sense_count, variant_msas = None, 0, []
    return {
        "entry_guid": str(guid).lower() if guid is not None else None,
        "headword": headword,
        "lexeme": _form_facts(getattr(entry, "LexemeFormOA", None)),
        "alternates": alternates,
        "msas": msas,
        "sense_count": sense_count,
        "variant_msas": variant_msas,
    }


def enabled_template_slots(flex_project: Any) -> Optional[frozenset]:
    """Slot GUIDs of every ENABLED affix template (`HCLoader.cs:295-300`).

    Templates are owned by parts of speech, so walking the category tree
    reaches every one. None when it cannot be read: slotted inflectional
    affixes are then not judged, rather than all counted dropped.
    """
    try:
        from SIL.LCModel import IPartOfSpeech  # type: ignore[import-not-found]

        lp = flex_project.project.LanguageProject
        slots = set()
        for possibility in list(lp.PartsOfSpeechOA.ReallyReallyAllPossibilities):
            for template in list(IPartOfSpeech(possibility).AffixTemplatesOS):
                if template.Disabled:
                    continue
                for slot in list(template.PrefixSlotsRS) + list(template.SuffixSlotsRS):
                    slots.add(str(slot.Guid).lower())
        return frozenset(slots)
    except Exception:  # noqa: BLE001
        return None


def eligible_entries(flex_project: Any) -> List[Dict[str, str]]:
    """Every entry of an open project that can reach the grammar. Reads only."""
    return eligible_from_facts(
        (entry_facts(e) for e in flex_project.LexEntry.GetAll()),
        enabled_template_slots(flex_project),
    )
