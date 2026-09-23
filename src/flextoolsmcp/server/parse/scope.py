#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scope resolution: from "parse this genre" to a definite word list
(parser-check CP3, US1; FR-002, FR-005..FR-009).

WHAT THIS MODULE DOES. It turns a `ParseScope` into a `ResolvedScope` -- an
ordered, NFC-de-duplicated list of words plus the identifiers of the texts
they came from. No parse starts here. A linguist can ask "how many distinct
words are in this genre, and in what order" and get an answer with no grammar
loaded, which is why US1 stands on its own.

FOUR THINGS THIS MODULE REFUSES TO DO, each one a failure mode that produces
a plausible-looking wrong answer rather than an error:

  1. BUILD ITS OWN CORPUS WALK (FR-005). The word list is the data model's own
     unique-wordform enumeration -- `IStText.UniqueWordforms()` on each text's
     contents -- unioned across the selected texts, exactly as the host
     application's ParserListener does. A hand-rolled segment walk would
     disagree with the host at the edges (punctuation, wordforms with no
     occurrence yet), and the disagreement would surface as "the MCP parsed
     different words than FLEx did".

  2. READ ONLY THE FIRST GENRE (FR-006). `TextOperations.GetGenre` returns the
     first genre on a text and is deliberately unchanged in the library; a
     text tagged [Narrative, Folklore] is invisible to "Folklore" through it.
     Every genre read here goes through `genres_of`, which reads the full
     collection via `GetGenres`. A test asserts the singular read is never called from
     this file.

  3. READ WORDFORMS AT AN IMPLICIT WRITING SYSTEM. Every `GetForm` call names
     its writing system. On IndonesianHC-Complete one text's 38 wordforms all
     read back as "" at the default vernacular WS while being present in
     another -- and after NFC de-duplication that is ONE empty "word", a
     silently wrong list indistinguishable from a real one-word text
     (specs/parser-check-cp3/live-note-fr001-fr003.md). Empty forms are
     skipped and counted, never emitted.

  4. CALL A TEXT WITH NO WORDS EMPTY (FR-002). A text with paragraphs but no
     unique wordforms may simply never have been opened for interlinear work.
     FR-001 -- whether those two states are distinguishable -- is still open,
     so the response says what was observed and stops there. It does not
     reuse `parse_scope_empty`, whose wording asserts nothing matched.

READ-ONLY. Only `Get*` reads and the raw `UniqueWordforms()` enumeration
appear below (FR-063).
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..models import ParseScope, ResolvedScope
from ..response_models import ParseScopeAmbiguousDetail, ParseScopeEmptyDetail


#: FR-002's conservative wording for texts with structure but no unique
#: wordforms. Written against T010's recorded answer: FR-001 is NOT settled,
#: so this sentence claims neither that the text is empty nor that it was
#: never tokenized. It says what was observed and what would change it.
NEVER_TOKENIZED_NOTE = (
    "Some selected texts have paragraphs but no wordforms were found for "
    "them. This can mean the text has not yet been opened for interlinear "
    "work in FieldWorks; opening it there makes its wordforms available. "
    "Their ids are listed in never_tokenized_text_ids."
)


class ScopeRefusal(Exception):
    """A scope that cannot be resolved as asked.

    ``detail`` is the refusal payload, already validated against its detail
    model and in the contract's field order, with ``error_code`` first --
    the same shape `resolver.refusal_detail` produces for
    `parse_morph_unresolved`.
    """

    def __init__(self, detail: Dict[str, Any]):
        super().__init__(detail.get("hint") or detail.get("error_code"))
        self.detail = detail


# ---------------------------------------------------------------------------
# Small reads, each one the only place its read happens
# ---------------------------------------------------------------------------

def genres_of(project: Any, text: Any) -> List[Any]:
    """Every genre on ``text`` -- the full collection, never the first (FR-006).

    The library contract, pinned by `tests/test_parse_scope.py` as its first
    consumer (FR-013): `GetGenres` returns an empty collection, never None,
    for a text with no genres. `None` is still tolerated here, because a
    scope over one mis-shaped text should not fail the other texts.
    """
    genres = project.Texts.GetGenres(text)
    return list(genres) if genres is not None else []


def _hvo(obj: Any) -> int:
    return int(obj.Hvo)


def _durable_id(obj: Any) -> str:
    """A text's GUID, lowercased; its hvo as text only if it has no GUID.

    The GUID is what the fingerprint records: hvos are renumbered on every
    cache load (issue #103), so an hvo-keyed fingerprint would make a
    baseline from yesterday's session refuse to compare with today's. The
    hvo fallback exists for objects that carry no GUID (test doubles); it is
    never mixed with GUIDs from a real project, which always has them.
    """
    guid = getattr(obj, "Guid", None)
    return str(guid).lower() if guid is not None else str(_hvo(obj))


def _ws_tag(pair: Any, fallback: str) -> str:
    """First element of a flexicon ``(language-tag, name)`` pair."""
    try:
        tag = pair[0]
    except Exception:
        return fallback
    return str(tag) if tag else fallback


def _vernacular(project: Any, requested: Optional[str]) -> Tuple[str, int]:
    """The (tag, handle) the words are read in. Always explicit.

    An unknown tag is a usage error, not a quiet fall back to the default:
    falling back would read the words in a writing system the caller did not
    ask for and record the one they did in the fingerprint.
    """
    if requested is not None:
        handle = project.WSHandle(requested)
        if handle is None:
            raise ValueError(
                f"No writing system with language tag {requested!r} in this "
                f"project. Omit vernacular_ws to use the default vernacular "
                f"writing system."
            )
        return requested, int(handle)
    tag = _ws_tag(project.GetDefaultVernacularWS(), "default-vernacular")
    return tag, int(project.GetDefaultVernacularWSHandle())


def _analysis(project: Any) -> Tuple[str, int]:
    """The (tag, handle) genre and text names are matched in (FR-008)."""
    try:
        tag = _ws_tag(project.GetDefaultAnalysisWS(), "default-analysis")
    except Exception:
        tag = "default-analysis"
    return tag, int(project.GetDefaultAnalysisWSHandle())


def _nfc(text: Any) -> str:
    return unicodedata.normalize("NFC", str(text or "")).strip()


def _order_and_limit(
    counts: Dict[str, int], limit: Optional[int],
) -> Tuple[List[str], int, bool]:
    """Order by descending occurrence then code point, THEN truncate (FR-009).

    Truncating first would keep whichever words the source order happened to
    yield first, so two runs over one corpus stored in a different order
    would resolve to different words and fail to compare.
    """
    ordered = sorted(counts, key=lambda word: (-counts[word], word))
    total = len(ordered)
    if limit is not None and total > limit:
        return ordered[:limit], total, True
    return ordered, total, False


def _scope_dict(scope: ParseScope) -> Dict[str, Any]:
    return scope.model_dump()


def _empty(scope: ParseScope, hint: str, matched: Iterable[str] = ()) -> ScopeRefusal:
    detail = ParseScopeEmptyDetail(
        scope=_scope_dict(scope), matched_texts=list(matched), hint=hint,
    )
    return ScopeRefusal(detail.model_dump())


def _ambiguous(scope: ParseScope, candidates: List[str]) -> ScopeRefusal:
    detail = ParseScopeAmbiguousDetail(
        scope=_scope_dict(scope), requested=str(scope.value), candidates=candidates,
    )
    return ScopeRefusal(detail.model_dump())


# ---------------------------------------------------------------------------
# Text selection
# ---------------------------------------------------------------------------

def _select_by_genre(project: Any, scope: ParseScope) -> Tuple[List[Any], str]:
    """Texts carrying the requested genre, and the genre's canonical name.

    Case-insensitive against BOTH name and abbreviation, at the default
    analysis writing system (FR-007, FR-008). Matching is per GENRE, not per
    text: a genre on ten texts is one candidate, two genres answering to one
    string are two, and the second case refuses with every candidate named.
    """
    wanted = scope.value.casefold()
    ws_tag, ws = _analysis(project)
    lists = project.PossibilityLists

    matched: Dict[int, Tuple[str, str]] = {}   # genre hvo -> (name, abbr)
    texts_by_genre: Dict[int, List[Any]] = defaultdict(list)
    for text in project.Texts.GetAll():
        for genre in genres_of(project, text):
            name = _nfc(lists.GetItemName(genre, ws))
            abbr = _nfc(lists.GetItemAbbreviation(genre, ws))
            if wanted in (name.casefold(), abbr.casefold()):
                matched[_hvo(genre)] = (name, abbr)
                texts_by_genre[_hvo(genre)].append(text)

    if not matched:
        raise _empty(
            scope,
            f"No genre on any text matches {scope.value!r} by name or "
            f"abbreviation. Matching ran against the default analysis writing "
            f"system ({ws_tag}); if genre names are entered in another "
            f"writing system -- for example because FieldWorks runs in a "
            f"localized interface -- they will not match here. A genre that "
            f"exists but is assigned to no text also does not match.",
        )
    if len(matched) > 1:
        candidates = [
            f"{name} ({abbr})" if abbr else name
            for _, (name, abbr) in sorted(matched.items())
        ]
        raise _ambiguous(scope, candidates)

    (genre_hvo, (name, _abbr)), = matched.items()
    return texts_by_genre[genre_hvo], name


def _select_by_text(project: Any, scope: ParseScope) -> List[Any]:
    """One text, by id or by name (case-insensitive, analysis WS)."""
    value = scope.value
    texts = list(project.Texts.GetAll())
    if value.isdigit():
        by_id = [t for t in texts if _hvo(t) == int(value)]
        if by_id:
            return by_id

    ws_tag, ws = _analysis(project)
    wanted = value.casefold()
    named = [t for t in texts if _nfc(project.Texts.GetName(t, ws)).casefold() == wanted]
    if len(named) > 1:
        raise _ambiguous(
            scope, [f"{_nfc(project.Texts.GetName(t, ws))} (id {_hvo(t)})" for t in named],
        )
    if not named:
        raise _empty(
            scope,
            f"No text has id or name {value!r}. Names are matched "
            f"case-insensitively in the default analysis writing system "
            f"({ws_tag}).",
        )
    return named


# ---------------------------------------------------------------------------
# Word collection
# ---------------------------------------------------------------------------

def _unique_wordforms(text: Any) -> List[Any]:
    """The data model's own enumeration for one text (FR-005).

    Raw LCM: `IText.ContentsOA` is the `IStText`, and `UniqueWordforms()` is
    what the host unions. A text with no contents object contributes nothing.
    """
    contents = getattr(text, "ContentsOA", None)
    if contents is None:
        return []
    return list(contents.UniqueWordforms())


def _paragraph_count(project: Any, text: Any) -> int:
    try:
        return int(project.Texts.GetParagraphCount(text) or 0)
    except Exception:
        return 0


def _occurrences(project: Any, wordform: Any) -> int:
    """The wordform's occurrence count, as the library reports it.

    Project-wide, not per selected text: counting within the selection would
    need the corpus walk FR-005 forbids. Ordering is the only thing it drives,
    and the tie-break keeps that deterministic regardless.
    """
    try:
        return int(project.Wordforms.GetOccurrenceCount(wordform) or 0)
    except Exception:
        return 0


def _collect(project: Any, texts: List[Any], ws: int):
    """Union the texts' unique wordforms and read each at ``ws``.

    Returns (counts by NFC word, never-tokenized text ids, unreadable count).
    """
    seen: Dict[int, Any] = {}
    never_tokenized: List[int] = []
    for text in texts:
        wordforms = _unique_wordforms(text)
        if not wordforms and _paragraph_count(project, text) > 0:
            never_tokenized.append(_hvo(text))
        for wordform in wordforms:
            seen.setdefault(_hvo(wordform), wordform)

    counts: Dict[str, int] = defaultdict(int)
    unreadable = 0
    for _, wordform in sorted(seen.items()):
        try:
            form = _nfc(project.Wordforms.GetForm(wordform, ws))
        except Exception:
            form = ""
        if not form:
            unreadable += 1
            continue
        # Two wordform objects can share an NFC form (one stored decomposed);
        # they are one word, and both sets of occurrences are its occurrences.
        counts[form] += _occurrences(project, wordform)
    return counts, sorted(never_tokenized), unreadable


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def resolve_scope(project: Any, scope: ParseScope) -> ResolvedScope:
    """Resolve ``scope`` against an open project. Starts no parse.

    Raises:
        ScopeRefusal: ``parse_scope_empty`` when nothing matched, or
            ``parse_scope_ambiguous`` when a string matched more than one
            genre (or text name), with every candidate.
        ValueError: ``vernacular_ws`` names no writing system in the project.
    """
    ws_tag, ws = _vernacular(project, scope.vernacular_ws)

    if scope.kind == "words":
        counts: Dict[str, int] = defaultdict(int)
        for word in scope.value:
            form = _nfc(word)
            if form:
                counts[form] += 1
        words, total, truncated = _order_and_limit(counts, scope.limit)
        return ResolvedScope(
            scope_kind=scope.kind,
            scope_value=sorted(counts),
            words=words,
            count_before_limit=total,
            limit=scope.limit,
            truncated=truncated,
            vernacular_ws=ws_tag,
        )

    scope_value: Optional[Any] = scope.value
    if scope.kind == "all_texts":
        texts = list(project.Texts.GetAll())
        if not texts:
            raise _empty(scope, "This project has no texts.")
    elif scope.kind == "genre":
        texts, scope_value = _select_by_genre(project, scope)
    else:
        texts = _select_by_text(project, scope)

    texts = sorted(texts, key=_hvo)
    counts, never_tokenized, unreadable = _collect(project, texts, ws)
    words, total, truncated = _order_and_limit(counts, scope.limit)

    notes: List[str] = []
    if never_tokenized:
        notes.append(NEVER_TOKENIZED_NOTE)
    if unreadable:
        notes.append(
            f"{unreadable} wordform(s) in the selected texts have no form in "
            f"the writing system {ws_tag!r} and were left out rather than "
            f"read as empty. If the texts are written in another vernacular "
            f"writing system, pass its language tag as vernacular_ws."
        )

    return ResolvedScope(
        scope_kind=scope.kind,
        scope_value=scope_value,
        text_ids=[_hvo(t) for t in texts],
        text_guids=[_durable_id(t) for t in texts],
        words=words,
        count_before_limit=total,
        limit=scope.limit,
        truncated=truncated,
        vernacular_ws=ws_tag,
        never_tokenized_text_ids=never_tokenized,
        unreadable_wordform_count=unreadable,
        notes=notes,
    )
