"""
Reducing parser results to plain channel data: the plain/trace summaries
(CP2b) and the typed structured analysis (CP3, FR-021/FR-035).

Worker-process only: imported by `worker_main.py` (the parse worker) and the
filing worker, never by the MCP server process -- see `worker_main.py`'s
header for why.
"""

from __future__ import annotations

from typing import Any, Optional



def _as_text(value: Any) -> Optional[str]:
    """Coerce a facade return to a plain string for the channel.

    The trace comes back as a serialized document, but "serialized" does
    not guarantee `str` across the CLR boundary. Everything crossing this
    channel is JSON, so it is coerced here rather than at the far end where
    the original object is no longer available to inspect.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _summarize_plain(result: Any) -> dict[str, Any]:
    """Reduce `ParseWord`'s live objects to something JSON can carry.

    `ParseWord` returns live LCM object references, which cannot cross a
    JSON channel and must not be smuggled across it either -- they belong
    to the worker's LCM cache and mean nothing in the server process.

    What the plain level actually owes its caller is narrow: FR-013 says it
    reports only **that** nothing parsed and points at the explaining
    levels; it must never present itself as an explanation. So this
    deliberately extracts a count and nothing more. Enriching it here would
    be the first step toward the plain level explaining itself, which is
    the thing the requirement forbids.
    """
    analyses = getattr(result, "Analyses", None)
    count = 0
    if analyses is not None:
        # A CLR ReadOnlyCollection[ParseAnalysis]. `Count` is its own
        # property and is tried first; `len()` works through pythonnet's
        # ICollection mapping and is the fallback. Both are tried because
        # this is the one number the whole plain level rests on, and a
        # silent 0 here would report "nothing parsed" for a word that
        # parsed perfectly well -- the exact silent-wrong-answer shape
        # CP2a shipped for a whole checkpoint.
        count = getattr(analyses, "Count", None)
        if count is None:
            try:
                count = len(analyses)
            except TypeError:
                count = sum(1 for _ in analyses)

    return {"parsed": int(count) > 0, "analysis_count": int(count)}


def _summarize_trace(trace: Any) -> dict[str, Any]:
    """Derive the same parsed/analysis_count facts `_summarize_plain`
    reports, straight from the trace `XDocument` -- BEFORE `_as_text`
    discards its structure.

    DERIVE, DO NOT RE-PARSE. `TraceWordXml` and `ParseWordXml` are the same
    C# method underneath (`HCParser.cs:120-131`): both build one
    `<Wordform>` document (root, `:207`) and append an `<Analysis>` child
    per surviving analysis (`:213-215`) *independently of the tracing
    flag*. The `<Trace>` sibling (`:217-218`) that `tracing=True` adds holds
    only explored/rejected paths -- they are never promoted into
    `<Analysis>`. So `len(root.Elements("Analysis"))` is not an estimate of
    what `ParseWord`'s own `Analyses.Count` would report; it is the same
    count, because `:104-113` applies the identical `GetMorphs` filter to
    build both. Counting it here is therefore never a second parse.

    THE <Error> CASE IS BLOCKING, and is checked FIRST. `ParseToXml` catches
    an exception and appends an `<Error>` child to `<Wordform>` *instead of*
    any `<Analysis>` (`HCParser.cs:219-222`). Zero `<Analysis>` is therefore
    ambiguous on its own: it means either "genuinely did not parse" or "the
    parse threw", and those are not the same fact. Reporting `parsed: False`
    for a document that actually holds `<Error>` would assert something
    false -- a worse defect than the silence it replaces, because today
    explain reports nothing about a thrown parse; a derived `False` would
    report a definite negative that never happened. So this returns
    `{"parse_error": str}` alone, with neither `parsed` nor `analysis_count`
    riding along -- the caller must not be able to mistake "the parse threw"
    for "the parse failed".

    ONE NO-ARGUMENT `Elements()` PASS, MATCHED BY `.Name.LocalName`.
    `XContainer.Element(XName)` / `.Elements(XName)` do not accept a bare
    `str` under pythonnet in this environment -- there is no implicit
    `str -> XName` conversion for that overload, so `root.Element("Error")`
    raised `TypeError: No method matches given arguments for
    XContainer.Element: (<class 'str'>)` on every live call (cycle 3
    verification). The no-arg `Elements()` overload (`IEnumerable<XElement>
    Elements()`) has no such binding problem, so this walks the children
    once, comparing each child's `.Name.LocalName` to the two names this
    function cares about, and counts/detects both in that single pass.
    Neither `XName` nor `System.Xml.Linq` needs importing into the worker
    for this, and no bare string is left behind for the next call site to
    reintroduce. <Error> still wins over <Analysis> when both are somehow
    present -- checked after the full walk, so the order children arrive in
    cannot flip the precedence.

    Returns:
        `{"parsed": bool, "analysis_count": int}` when the document has no
        `<Error>` (whether or not it has any `<Analysis>`), or
        `{"parse_error": str}` alone when it does, or when the document has
        no root at all (see below).
    """
    root = getattr(trace, "Root", None)
    if root is None:
        # A document we could not read is not a word that did not parse --
        # that is Delta 6's own stated principle, applied here. Silently
        # reporting `parsed: False` would invent the very fact absence was
        # supposed to avoid inventing: it would tell the caller the word
        # was tried and failed, when in truth nothing was ever established
        # about it at all. An unreadable document is indeterminate, and
        # `parse_error` is the outcome this function already has for "this
        # response asserts nothing about whether the word parses".
        return {"parse_error": "the trace document has no root element"}

    error_element = None
    analysis_count = 0
    for child in root.Elements():
        name = getattr(getattr(child, "Name", None), "LocalName", None)
        if name == "Error":
            if error_element is None:
                error_element = child
        elif name == "Analysis":
            analysis_count += 1

    if error_element is not None:
        text = getattr(error_element, "Value", None)
        if not text:
            text = str(error_element)
        return {"parse_error": str(text)}

    return {"parsed": analysis_count > 0, "analysis_count": analysis_count}


# ---------------------------------------------------------------------------
# CP3: reducing the typed structured result to plain data (FR-021, FR-035)
# ---------------------------------------------------------------------------


def _clr_list(collection: Any) -> list:
    """A CLR collection (or None) as a Python list. Never raises."""
    if collection is None:
        return []
    try:
        return list(collection)
    except TypeError:
        return []


def _guid(obj: Any) -> Optional[str]:
    """An LCM object's GUID as a lowercase string, or None for a null ref.

    The durable identity (see `_RealBackend._batch_parse`). A null reference
    stays None rather than becoming "" -- a triple whose inflection type is
    absent is a different triple from one whose inflection type is unknown.
    """
    if obj is None:
        return None
    guid = getattr(obj, "Guid", None)
    if guid is None:
        return None
    return str(guid).lower()


def _multi_text(multi: Any, ws: int) -> str:
    """One alternative of a multistring at an EXPLICIT writing system.

    Never `BestVernacularAlternative` and never the default: the live note
    for US1 records a whole text whose forms read back empty at the default
    writing system (the #36/#39/#40 class). Missing is "", not "***".
    """
    if multi is None:
        return ""
    try:
        text = multi.get_String(ws).Text
    except Exception:  # noqa: BLE001
        return ""
    if not text or text == "***":
        return ""
    return str(text)


def _msa_label(msa: Any) -> str:
    """A short category label for a morph's MSA, best-effort.

    Rendered text only, carried so a report is legible without reopening the
    project (FR-031). Nothing compares on it except the FR-033 fallback, and
    that fallback states its own ambiguity.
    """
    if msa is None:
        return ""
    for name in ("InterlinearAbbr", "ShortName"):
        try:
            value = getattr(msa, name, None)
        except Exception:  # noqa: BLE001
            value = None
        if value:
            text = getattr(value, "Text", value)
            if text and str(text) != "***":
                return str(text)
    return ""


def _morph_kind(form: Any) -> str:
    """'stem', 'affix' or 'unknown', from the form's morph type flags."""
    morph_type = getattr(form, "MorphTypeRA", None)
    if morph_type is None:
        return "unknown"
    try:
        if bool(getattr(morph_type, "IsAffixType", False)):
            return "affix"
        if bool(getattr(morph_type, "IsStemType", False)):
            return "stem"
    except Exception:  # noqa: BLE001
        pass
    return "unknown"


def _sense_gloss(entry: Any, msa: Any, analysis_ws: Optional[int]) -> str:
    """The gloss of the entry's sense that carries this MSA, best-effort.

    What a composed gloss is built from (SPEC 9.3.2). The entry arrives as
    the form's `Owner`, typed as base `ICmObject` -- `AllSenses` is not on
    that interface, so it is cast to `ILexEntry` first (the #32/#97/#98
    class: an unguarded member read on a base-typed `.Owner`).
    """
    if entry is None or msa is None or analysis_ws is None:
        return ""
    try:
        from SIL.LCModel import ILexEntry  # type: ignore[import-not-found]

        entry = ILexEntry(entry)
    except Exception:  # noqa: BLE001 -- not an entry, or no CLR (a test double)
        pass
    msa_guid = _guid(msa)
    for sense in _clr_list(getattr(entry, "AllSenses", None)):
        if _guid(getattr(sense, "MorphoSyntaxAnalysisRA", None)) == msa_guid:
            return _multi_text(getattr(sense, "Gloss", None), analysis_ws)
    return ""


def _structured_analysis(
    analysis: Any, ws: int, analysis_ws: Optional[int] = None
) -> dict[str, Any]:
    """One `ParseAnalysis` as an AnalysisRecord (data-model.md section 6).

    `signature` is the ordered (form, MSA, inflection type) GUID triples --
    the host's `MatchesIWfiAnalysis` predicate made durable (D-2). The
    inflection type is the third component, not an optional extra: without
    it two analyses differing only in inflection type collapse into one.

    `has_guessed_form` is the honest residue (FR-031a): where a morph carries
    a guessed surface string, the host predicate also requires that string to
    match one of the bundle's writing-system alternatives, and a serialized
    signature cannot reproduce that comparison.
    """
    signature = []
    rendered = []
    labels = []
    entries = []
    kinds = []
    glosses = []
    guessed = False
    for morph in _clr_list(getattr(analysis, "Morphs", None)):
        form = getattr(morph, "Form", None)
        msa = getattr(morph, "Msa", None)
        infl = getattr(morph, "InflType", None)
        guess = getattr(morph, "GuessedString", None)
        signature.append([_guid(form), _guid(msa), _guid(infl)])
        if guess is not None:
            guessed = True
            rendered.append(str(guess))
        else:
            rendered.append(_multi_text(getattr(form, "Form", None), ws))
        labels.append(_msa_label(msa))
        # CP3 US5 additions (additive to the frozen line shape): what the
        # batch signals need without reopening the project -- the owning
        # entry (root-entry disagreement), the morph kind (a root analysed
        # as affixes) and the sense gloss (the composed gloss, SPEC 9.3.2).
        owner = getattr(form, "Owner", None)
        entries.append(_guid(owner))
        kinds.append(_morph_kind(form))
        glosses.append(_sense_gloss(owner, msa, analysis_ws))
    return {
        "signature": signature,
        "rendered_morphs": rendered,
        "category_labels": labels,
        "has_guessed_form": guessed,
        "entry_guids": entries,
        "morph_kinds": kinds,
        "morph_glosses": glosses,
    }


class _SpecView:
    """A `MorphSpec` as it arrives over the channel: a plain dict.

    `resolver.resolve_spec` reads `headword` / `sense` / `msa_hvo` /
    `position` by attribute, and the server-side model supplies them that
    way. Rather than import the pydantic model into the worker -- which
    would drag the whole `server.models` import graph into a process whose
    job is to hold a grammar -- this gives the dict the same four
    attributes. The resolver stays indifferent to which side called it,
    which is what lets one implementation serve both.
    """

    __slots__ = ("headword", "sense", "msa_hvo", "position")

    def __init__(self, raw: dict[str, Any]) -> None:
        self.headword = raw.get("headword")
        self.sense = raw.get("sense")
        self.msa_hvo = raw.get("msa_hvo")
        self.position = raw.get("position")

    @property
    def morph(self) -> Any:
        return self.headword if self.headword is not None else self.msa_hvo
