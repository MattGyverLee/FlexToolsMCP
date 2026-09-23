#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scope resolution (parser-check CP3, US1; T015-T019).

Each test here is written so the WRONG implementation fails, not merely so
the right one passes:

  T015  two-genre regression -- a first-genre-only read (`GetGenre`) misses
        a text found by its second genre. The double's `GetGenre` returns the
        first genre, exactly as the library does, so reaching for it fails.
  T016  order-then-truncate -- truncating in source order and then sorting
        yields a different list for a differently ordered corpus.
  T017  never-tokenized -- a text with paragraphs but no unique wordforms
        must not be reported as having no words, and must not borrow
        `parse_scope_empty`'s wording.
  T018  the genre read's empty-collection contract (FR-013) -- CP3 is that
        read's first consumer, so it is pinned here as if it were the
        library's own test.
  T019  ambiguity -- every candidate is named, not the first two.

Plus the live finding from `specs/parser-check-cp3/live-note-fr001-fr003.md`:
wordforms read at a writing system they are not stored in come back as the
empty string, and must be skipped-and-recorded rather than collapsing into a
single empty "word".

Everything runs offline against doubles; no FieldWorks install is involved.
"""

import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server.models import ParseScope  # noqa: E402
from flextoolsmcp.server.parse import scope as scope_mod  # noqa: E402
from flextoolsmcp.server.parse.scope import (  # noqa: E402
    NEVER_TOKENIZED_NOTE,
    ScopeRefusal,
    genres_of,
    resolve_scope,
)
from flextoolsmcp.server.response_models import (  # noqa: E402
    ParseScopeAmbiguousDetail,
    ParseScopeEmptyDetail,
)


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------

VERN = 101      # default vernacular WS handle
IPA = 102       # a second vernacular WS
ANALYSIS = 201  # default analysis WS handle

WS_TAGS = {"id": VERN, "id-fonipa": IPA, "en": ANALYSIS}


class ProjectWriteAttempted(AssertionError):
    """A scope resolution tried to write. CP3 ships no write path (FR-063)."""


class _ReadOnly:
    """Raise on any name a scope read has no business calling."""

    _WRITE_PREFIXES = ("Set", "Add", "Create", "Delete", "Remove", "Move")

    def __getattr__(self, name):
        if name.startswith(self._WRITE_PREFIXES):
            raise ProjectWriteAttempted(name)
        raise AttributeError(name)


class FakeGenre:
    def __init__(self, hvo, name, abbr=""):
        self.Hvo = hvo
        self.name = name
        self.abbr = abbr


class FakeWordform:
    def __init__(self, hvo, form, occurrences=1, ws=VERN):
        self.Hvo = hvo
        self.forms = {ws: form}
        self.occurrences = occurrences


class FakeContents:
    def __init__(self, wordforms):
        self._wordforms = list(wordforms)

    def UniqueWordforms(self):
        # A set in LCM (HashSet[IWfiWordform]); iteration order is not a
        # contract, so the double deliberately returns it reversed.
        return list(reversed(self._wordforms))


class FakeText:
    def __init__(self, hvo, name, genres=(), wordforms=(), paragraphs=None):
        self.Hvo = hvo
        self.name = name
        self.genres = list(genres)
        self.paragraphs = (1 if wordforms else 0) if paragraphs is None else paragraphs
        self.ContentsOA = FakeContents(wordforms) if self.paragraphs else None


class FakeTexts(_ReadOnly):
    def __init__(self, texts):
        self._texts = texts

    def GetAll(self):
        return list(self._texts)

    def GetGenres(self, text):
        return list(text.genres)

    def GetGenre(self, text):
        # The library's singular read: FIRST genre only. Present so that an
        # implementation reaching for it fails T015 instead of erroring.
        return text.genres[0] if text.genres else None

    def GetName(self, text, wsHandle=None):
        return text.name

    def GetParagraphCount(self, text):
        return text.paragraphs


class FakeWordforms(_ReadOnly):
    def GetForm(self, wf, wsHandle=None):
        if wsHandle is None:
            raise AssertionError(
                "GetForm called without an explicit writing system. The "
                "implicit default silently reads '' for wordforms stored in "
                "another vernacular WS (live-note-fr001-fr003.md)."
            )
        return wf.forms.get(wsHandle, "")

    def GetOccurrenceCount(self, wf):
        return wf.occurrences


class FakePossibilityLists(_ReadOnly):
    def GetItemName(self, item, wsHandle=None):
        assert wsHandle == ANALYSIS, "genre names are read at the analysis WS"
        return item.name

    def GetItemAbbreviation(self, item, wsHandle=None):
        assert wsHandle == ANALYSIS, "genre abbreviations are read at the analysis WS"
        return item.abbr


class FakeProject(_ReadOnly):
    def __init__(self, texts):
        self.Texts = FakeTexts(texts)
        self.Wordforms = FakeWordforms()
        self.PossibilityLists = FakePossibilityLists()

    def GetDefaultVernacularWSHandle(self):
        return VERN

    def GetDefaultVernacularWS(self):
        return ("id", "Indonesian")

    def GetDefaultAnalysisWSHandle(self):
        return ANALYSIS

    def GetDefaultAnalysisWS(self):
        return ("en", "English")

    def WSHandle(self, tag):
        return WS_TAGS.get(tag)


def _wfs(*pairs, start=1000):
    """Wordforms from (form, occurrences) pairs, with distinct hvos."""
    return [FakeWordform(start + i, form, occ) for i, (form, occ) in enumerate(pairs)]


NARRATIVE = FakeGenre(1, "Narrative", "Narr")
FOLKLORE = FakeGenre(2, "Folklore", "Folk")
PROCEDURAL = FakeGenre(3, "Procedural", "Proc")


# ---------------------------------------------------------------------------
# T015 -- two-genre regression (FR-006, SC-001)
# ---------------------------------------------------------------------------

def test_text_with_two_genres_is_found_by_its_second_genre():
    tagged_twice = FakeText(10, "Tale", genres=[NARRATIVE, FOLKLORE],
                            wordforms=_wfs(("rumah", 3)))
    other = FakeText(11, "Recipe", genres=[PROCEDURAL], wordforms=_wfs(("masak", 1), start=2000))
    project = FakeProject([tagged_twice, other])

    resolved = resolve_scope(project, ParseScope(kind="genre", value="Folklore"))

    assert resolved.text_ids == [10], (
        "A text tagged [Narrative, Folklore] must be found by 'Folklore'. "
        "A first-genre-only read (GetGenre) misses it."
    )
    assert resolved.words == ["rumah"]


def test_text_with_two_genres_is_found_by_its_first_genre_too():
    tagged_twice = FakeText(10, "Tale", genres=[NARRATIVE, FOLKLORE],
                            wordforms=_wfs(("rumah", 3)))
    project = FakeProject([tagged_twice])

    resolved = resolve_scope(project, ParseScope(kind="genre", value="Narrative"))

    assert resolved.text_ids == [10]


def test_genre_matching_is_case_insensitive_on_name_and_abbreviation():
    text = FakeText(10, "Tale", genres=[NARRATIVE, FOLKLORE], wordforms=_wfs(("rumah", 1)))
    project = FakeProject([text])

    for requested in ("folklore", "FOLKLORE", "folk", "FoLk"):
        resolved = resolve_scope(project, ParseScope(kind="genre", value=requested))
        assert resolved.text_ids == [10], requested


# ---------------------------------------------------------------------------
# T016 -- order-then-truncate (FR-009, SC-002)
# ---------------------------------------------------------------------------

def _corpus(order):
    """The same three texts, in a caller-chosen source order."""
    a = FakeText(10, "A", wordforms=_wfs(("zebra", 1), ("apel", 5), start=1000))
    b = FakeText(11, "B", wordforms=_wfs(("mangga", 5), ("buku", 2), start=2000))
    c = FakeText(12, "C", wordforms=_wfs(("cicak", 9), ("durian", 1), start=3000))
    by_id = {10: a, 11: b, 12: c}
    return FakeProject([by_id[i] for i in order])


def test_ordering_is_descending_occurrence_then_alphabetical():
    resolved = resolve_scope(_corpus([10, 11, 12]), ParseScope(kind="all_texts"))

    assert resolved.words == ["cicak", "apel", "mangga", "buku", "durian", "zebra"]
    assert resolved.count_before_limit == 6
    assert resolved.truncated is False


def test_limit_truncates_after_ordering_and_is_recorded():
    forward = resolve_scope(_corpus([10, 11, 12]), ParseScope(kind="all_texts", limit=3))
    backward = resolve_scope(_corpus([12, 11, 10]), ParseScope(kind="all_texts", limit=3))

    # Truncate-then-order would keep the first three words the SOURCE order
    # happened to yield, which differs between the two corpora.
    assert forward.words == ["cicak", "apel", "mangga"]
    assert backward.words == forward.words
    assert forward.truncated is True
    assert forward.count_before_limit == 6
    assert forward.limit == 3


def test_same_corpus_in_two_orders_yields_identical_fingerprint():
    from flextoolsmcp.server.parse.fingerprint import build_fingerprint

    forward = resolve_scope(_corpus([10, 11, 12]), ParseScope(kind="all_texts", limit=4))
    backward = resolve_scope(_corpus([11, 12, 10]), ParseScope(kind="all_texts", limit=4))

    assert forward.words == backward.words
    assert build_fingerprint(forward, engine="HermitCrab") == \
        build_fingerprint(backward, engine="HermitCrab")


def test_limit_larger_than_list_is_not_truncation():
    resolved = resolve_scope(_corpus([10, 11, 12]), ParseScope(kind="all_texts", limit=50))

    assert len(resolved.words) == 6
    assert resolved.truncated is False


def test_words_are_nfc_deduplicated_across_texts():
    decomposed = unicodedata.normalize("NFD", "café")
    composed = unicodedata.normalize("NFC", "café")
    assert decomposed != composed
    a = FakeText(10, "A", wordforms=[FakeWordform(1, decomposed, 2)])
    b = FakeText(11, "B", wordforms=[FakeWordform(2, composed, 2)])

    resolved = resolve_scope(FakeProject([a, b]), ParseScope(kind="all_texts"))

    assert resolved.words == [composed]
    assert resolved.count_before_limit == 1


def test_same_wordform_in_two_texts_is_counted_once():
    shared = FakeWordform(1, "rumah", 4)
    a = FakeText(10, "A", wordforms=[shared])
    b = FakeText(11, "B", wordforms=[shared])

    resolved = resolve_scope(FakeProject([a, b]), ParseScope(kind="all_texts"))

    assert resolved.words == ["rumah"]
    assert resolved.text_ids == [10, 11]


# ---------------------------------------------------------------------------
# T017 -- never-tokenized (FR-002, SC-003)
# ---------------------------------------------------------------------------

_EMPTY_WORDING = (
    "no words", "has no words", "contains no words", "is empty", "empty text",
)


def _all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _all_strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _all_strings(v)


def test_never_tokenized_text_is_not_asserted_to_have_no_words():
    untokenized = FakeText(10, "Fresh", genres=[NARRATIVE], wordforms=(), paragraphs=4)
    project = FakeProject([untokenized])

    # Not a parse_scope_empty refusal: the scope DID match a text.
    resolved = resolve_scope(project, ParseScope(kind="genre", value="Narrative"))

    assert resolved.words == []
    assert resolved.text_ids == [10]
    assert resolved.never_tokenized_text_ids == [10]

    emitted = " ".join(_all_strings(resolved.model_dump())).lower()
    for phrase in _EMPTY_WORDING:
        assert phrase not in emitted, (
            f"{phrase!r}: a text with structure but no unique wordforms has "
            f"not been shown to contain no words (FR-002)."
        )


def test_never_tokenized_wording_is_not_parse_scope_empty_wording():
    untokenized = FakeText(10, "Fresh", genres=[NARRATIVE], wordforms=(), paragraphs=4)
    resolved = resolve_scope(FakeProject([untokenized]), ParseScope(kind="genre", value="Narrative"))

    assert NEVER_TOKENIZED_NOTE in resolved.notes
    with pytest.raises(ScopeRefusal) as empty:
        resolve_scope(FakeProject([untokenized]), ParseScope(kind="genre", value="Nonexistent"))
    assert empty.value.detail["error_code"] == "parse_scope_empty"
    assert NEVER_TOKENIZED_NOTE != empty.value.detail["hint"]
    assert "parse_scope_empty" not in " ".join(_all_strings(resolved.model_dump()))


def test_never_tokenized_text_beside_tokenized_one_keeps_the_others_words():
    untokenized = FakeText(10, "Fresh", wordforms=(), paragraphs=2)
    tokenized = FakeText(11, "Done", wordforms=_wfs(("rumah", 1)))

    resolved = resolve_scope(FakeProject([untokenized, tokenized]), ParseScope(kind="all_texts"))

    assert resolved.words == ["rumah"]
    assert resolved.never_tokenized_text_ids == [10]


def test_text_with_no_structure_is_not_called_never_tokenized():
    # No paragraphs at all: there is no structure to have tokenized, so the
    # distinguishing read (structure present, no words) does not fire.
    bare = FakeText(10, "Blank", wordforms=(), paragraphs=0)
    resolved = resolve_scope(FakeProject([bare]), ParseScope(kind="all_texts"))

    assert resolved.never_tokenized_text_ids == []
    assert resolved.words == []


# ---------------------------------------------------------------------------
# T018 -- the genre read's empty-collection contract (FR-013)
# ---------------------------------------------------------------------------

def test_genres_of_a_text_with_no_genres_is_an_empty_collection():
    ungenred = FakeText(10, "Untagged", genres=[], wordforms=_wfs(("rumah", 1)))
    project = FakeProject([ungenred])

    result = genres_of(project, ungenred)

    assert result == []
    assert project.Texts.GetGenres(ungenred) == [], (
        "The library contract CP3 consumes: GetGenres returns an EMPTY "
        "collection, never None, for a text with no genres."
    )


def test_genres_of_tolerates_none_from_the_read():
    class NoneGenres(FakeTexts):
        def GetGenres(self, text):
            return None

    project = FakeProject([])
    project.Texts = NoneGenres([])

    assert genres_of(project, FakeText(10, "X")) == []


def test_genre_scope_over_ungenred_texts_refuses_as_empty_and_raises_nothing_else():
    ungenred = FakeText(10, "Untagged", genres=[], wordforms=_wfs(("rumah", 1)))

    with pytest.raises(ScopeRefusal) as refusal:
        resolve_scope(FakeProject([ungenred]), ParseScope(kind="genre", value="Narrative"))

    ParseScopeEmptyDetail.model_validate(refusal.value.detail)
    assert refusal.value.detail["matched_texts"] == []


def test_no_match_discloses_the_default_analysis_writing_system():
    text = FakeText(10, "Tale", genres=[NARRATIVE], wordforms=_wfs(("rumah", 1)))

    with pytest.raises(ScopeRefusal) as refusal:
        resolve_scope(FakeProject([text]), ParseScope(kind="genre", value="Cerita"))

    hint = refusal.value.detail["hint"]
    assert "default analysis writing system" in hint, (
        "FR-008: a localized-interface user needs the plausible reason, not "
        "a bare assertion that no such genre exists."
    )
    assert "en" in hint


# ---------------------------------------------------------------------------
# T019 -- ambiguity (FR-007)
# ---------------------------------------------------------------------------

def test_genre_matching_two_genres_refuses_with_every_candidate():
    # 'Folk' is one genre's abbreviation and another genre's name.
    folklore = FakeGenre(2, "Folklore", "Folk")
    folk = FakeGenre(4, "Folk", "Fk")
    folk_song = FakeGenre(5, "Folk Song", "folk")
    texts = [
        FakeText(10, "A", genres=[folklore], wordforms=_wfs(("a", 1), start=1)),
        FakeText(11, "B", genres=[folk], wordforms=_wfs(("b", 1), start=2)),
        FakeText(12, "C", genres=[folk_song, NARRATIVE], wordforms=_wfs(("c", 1), start=3)),
    ]

    with pytest.raises(ScopeRefusal) as refusal:
        resolve_scope(FakeProject(texts), ParseScope(kind="genre", value="folk"))

    detail = ParseScopeAmbiguousDetail.model_validate(refusal.value.detail)
    assert detail.requested == "folk"
    assert len(detail.candidates) == 3, "EVERY candidate, not the first two"
    joined = " | ".join(detail.candidates)
    for name in ("Folklore", "Folk Song"):
        assert name in joined
    assert list(refusal.value.detail) == ["error_code", "scope", "requested", "candidates"]


def test_same_genre_on_many_texts_is_not_ambiguous():
    texts = [
        FakeText(10, "A", genres=[FOLKLORE], wordforms=_wfs(("a", 1), start=1)),
        FakeText(11, "B", genres=[FOLKLORE], wordforms=_wfs(("b", 1), start=2)),
    ]

    resolved = resolve_scope(FakeProject(texts), ParseScope(kind="genre", value="Folklore"))

    assert resolved.text_ids == [10, 11]


# ---------------------------------------------------------------------------
# Writing system (live-note-fr001-fr003.md, "vernacular_ws is load-bearing")
# ---------------------------------------------------------------------------

def test_wordforms_absent_at_the_writing_system_are_skipped_and_recorded():
    # The Ortho case: wordforms present and countable, stored at another WS.
    ortho = FakeText(10, "Ortho", wordforms=[
        FakeWordform(1, "membuat", 2, ws=IPA),
        FakeWordform(2, "mendalam", 1, ws=IPA),
    ])

    resolved = resolve_scope(FakeProject([ortho]), ParseScope(kind="all_texts"))

    assert resolved.words == [], "never a single empty-string 'word'"
    assert "" not in resolved.words
    assert resolved.unreadable_wordform_count == 2
    assert resolved.vernacular_ws == "id"
    assert any("id" in note and "writing system" in note for note in resolved.notes)


def test_explicit_vernacular_ws_reads_the_other_writing_system():
    ortho = FakeText(10, "Ortho", wordforms=[
        FakeWordform(1, "membuat", 2, ws=IPA),
        FakeWordform(2, "mendalam", 1, ws=IPA),
    ])

    resolved = resolve_scope(FakeProject([ortho]),
                             ParseScope(kind="all_texts", vernacular_ws="id-fonipa"))

    assert resolved.words == ["membuat", "mendalam"]
    assert resolved.vernacular_ws == "id-fonipa"
    assert resolved.unreadable_wordform_count == 0


def test_unknown_vernacular_ws_is_a_usage_error_not_a_silent_default():
    text = FakeText(10, "A", wordforms=_wfs(("rumah", 1)))

    with pytest.raises(ValueError, match="writing system"):
        resolve_scope(FakeProject([text]), ParseScope(kind="all_texts", vernacular_ws="xx-nope"))


# ---------------------------------------------------------------------------
# Other scope kinds
# ---------------------------------------------------------------------------

def test_text_scope_by_name_and_by_id():
    a = FakeText(10, "Tale", wordforms=_wfs(("rumah", 1)))
    b = FakeText(11, "Recipe", wordforms=_wfs(("masak", 1), start=2000))
    project = FakeProject([a, b])

    assert resolve_scope(project, ParseScope(kind="text", value="recipe")).text_ids == [11]
    assert resolve_scope(project, ParseScope(kind="text", value="10")).text_ids == [10]


def test_text_scope_that_matches_nothing_refuses_as_empty():
    project = FakeProject([FakeText(10, "Tale", wordforms=_wfs(("rumah", 1)))])

    with pytest.raises(ScopeRefusal) as refusal:
        resolve_scope(project, ParseScope(kind="text", value="Missing"))

    ParseScopeEmptyDetail.model_validate(refusal.value.detail)
    assert list(refusal.value.detail) == ["error_code", "scope", "matched_texts", "hint"]


def test_all_texts_on_a_project_with_no_texts_refuses_as_empty():
    with pytest.raises(ScopeRefusal) as refusal:
        resolve_scope(FakeProject([]), ParseScope(kind="all_texts"))
    assert refusal.value.detail["error_code"] == "parse_scope_empty"


def test_explicit_word_list_is_deduplicated_and_ordered():
    resolved = resolve_scope(
        FakeProject([]),
        ParseScope(kind="words", value=["b", "a", "b", unicodedata.normalize("NFD", "é"), "é"]),
    )

    # Occurrence here is repetition in the caller's list: b x2, e-acute x2
    # (once NFD, once NFC), a x1. The tie breaks on code point.
    assert resolved.words == ["b", "é", "a"]
    assert resolved.text_ids == []


def test_scope_input_validation():
    with pytest.raises(ValueError):
        ParseScope(kind="genre")
    with pytest.raises(ValueError):
        ParseScope(kind="words", value=[])
    with pytest.raises(ValueError):
        ParseScope(kind="all_texts", value="x")
    with pytest.raises(ValueError):
        ParseScope(kind="all_texts", limit=0)


def test_resolution_never_writes():
    # FakeProject raises ProjectWriteAttempted on any Set*/Add*/Create*/...
    text = FakeText(10, "Tale", genres=[NARRATIVE, FOLKLORE], wordforms=_wfs(("rumah", 1)))
    resolve_scope(FakeProject([text]), ParseScope(kind="genre", value="Folk", limit=1))


def test_scope_module_does_not_call_the_first_genre_only_read():
    source = Path(scope_mod.__file__).read_text(encoding="utf-8")
    assert "GetGenre(" not in source, (
        "GetGenre returns only the FIRST genre (FR-006). Use GetGenres."
    )


def test_a_texts_durable_id_is_its_guid_and_never_its_session_hvo():
    """What the fingerprint records for a text (issue #103)."""
    from flextoolsmcp.server.parse.scope import _durable_id

    class WithGuid:
        Hvo = 5
        Guid = "ABCD-1234"

    class WithoutGuid:
        Hvo = 5

    assert _durable_id(WithGuid()) == "abcd-1234"
    assert _durable_id(WithoutGuid()) == "5"
