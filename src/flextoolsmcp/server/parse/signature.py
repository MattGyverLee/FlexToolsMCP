#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The durable analysis signature (parser-check CP3, US4; FR-031, FR-031a,
FR-032, FR-033; D-2).

WHAT A SIGNATURE IS. The host application decides whether a parser analysis
is "the same" as a stored one with `ParseAnalysis.MatchesIWfiAnalysis`
(FieldWorks ParserCore/ParseResult.cs): same number of morphs, and for each
position the same morph-form object, the same morph-syntax-analysis object
and the same inflection-type object. That is ordered object identity. A
comparison runs across two RUNS, and a run on disk holds no live objects, so
the identity has to survive serialization: the signature is that same
predicate expressed as the ordered (form, MSA, inflection type) identifier
triples. The identifiers are object GUIDs (the identity the host's own
`ParseMorph.GetHashCode` uses), not hvos, which liblcm renumbers per cache
load (issue #103).

THE INFLECTION TYPE IS NOT OPTIONAL. A (form, MSA) pair would collapse two
analyses that differ only in inflection type -- an irregularly inflected form
against its regular reading -- and report `unchanged` for analyses that
genuinely differ.

THE HONEST RESIDUE (FR-031a). The host predicate has a fourth clause: where a
parser morph proposes a guessed surface string, that string must also equal
one of the bundle's writing-system alternatives. A serialized signature has
no access to that comparison. So the worker records `has_guessed_form` per
analysis, and any comparison that leans on such an analysis is reported as
PROVISIONAL rather than as asserted identity. Dropping the flag would claim
alignment with a predicate this code does not reproduce.

TWO MODES (FR-033). Identifier mode compares the triples; it is the host's
predicate and is authoritative once identifier stability across sessions has
been confirmed live. Until then the rendered-form fallback is authoritative:
rendered morphs plus category labels. It is weaker -- two distinct morphemes
spelled alike collapse -- and every report produced in it SAYS so. The switch
is `IDENTIFIER_STABILITY`, set by the live verification (T125); nothing
flips it implicitly.

In either mode, identical rendered forms under differing identifiers is an
IDENTITY CHANGE (FR-032): neither a behavioural change nor "unchanged".
Something did change in the lexicon -- an entry was re-created, merged or
re-linked -- and the parser's visible behaviour did not.

Pure server-side: reads `results.jsonl` lines, never a project.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

__all__ = [
    "DurableAnalysisSignature",
    "IDENTIFIER_STABILITY",
    "SignatureMode",
    "signature_mode",
    "FALLBACK_AMBIGUITY_NOTE",
    "PROVISIONAL_NOTE",
    "IDENTITY_CHANGE_NOTE",
    "WordComparison",
    "compare_word",
]

#: The live verdict on whether analysis identifiers are stable across
#: sessions (FR-033). "unverified" until T125 records it from live evidence;
#: then "confirmed" or "disproved". Only "confirmed" enables identifier mode.
#: `FLEXTOOLSMCP_IDENTIFIER_STABILITY` overrides it, for tests and for a
#: maintainer applying the live verdict before a release carries it.
IDENTIFIER_STABILITY = "unverified"

_ENV_STABILITY = "FLEXTOOLSMCP_IDENTIFIER_STABILITY"


class SignatureMode:
    IDENTIFIER = "identifier"
    RENDERED_FALLBACK = "rendered_fallback"


def signature_mode() -> str:
    """The comparison mode in force. Identifier only when stability is confirmed."""
    verdict = os.environ.get(_ENV_STABILITY, IDENTIFIER_STABILITY).strip().lower()
    return SignatureMode.IDENTIFIER if verdict == "confirmed" else SignatureMode.RENDERED_FALLBACK


#: Stated in every report produced in fallback mode (FR-033).
FALLBACK_AMBIGUITY_NOTE = (
    "Analyses were compared by their rendered morph forms and category labels, "
    "not by the lexical objects they were built from, because it has not yet "
    "been confirmed live that those objects' identifiers stay the same between "
    "sessions. This comparison is weaker: two different morphemes spelled the "
    "same way, with the same category, look identical to it. A word reported "
    "unchanged may have changed which entry it is analysed with."
)

#: Stated wherever a comparison leans on a guessed-form analysis (FR-031a).
PROVISIONAL_NOTE = (
    "At least one analysis compared here carries a surface form the parser "
    "guessed. The host application also checks a guessed form against the "
    "stored forms, which a saved run cannot repeat, so this match is "
    "provisional rather than confirmed."
)

#: Stated with every identity change (FR-032).
IDENTITY_CHANGE_NOTE = (
    "The analyses look the same -- the same morph forms and categories -- but "
    "are built from different lexical objects than before. The parser's "
    "behaviour on this word did not visibly change; the lexicon did (an entry "
    "or sense re-created, merged or re-linked). This is neither a change in "
    "how the word parses nor 'unchanged'."
)


@dataclass(frozen=True)
class DurableAnalysisSignature:
    """One analysis, as a run records it (data-model.md section 6)."""

    triples: Tuple[Tuple[Optional[str], Optional[str], Optional[str]], ...]
    rendered_morphs: Tuple[str, ...]
    category_labels: Tuple[str, ...]
    has_guessed_form: bool = False

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "DurableAnalysisSignature":
        triples = []
        for triple in record.get("signature") or ():
            padded = list(triple) + [None] * (3 - len(triple))
            if len(padded) != 3:
                raise ValueError(f"A signature triple has {len(triple)} components: {triple!r}")
            triples.append(tuple(padded))
        return cls(
            triples=tuple(triples),
            rendered_morphs=tuple(str(m) for m in record.get("rendered_morphs") or ()),
            category_labels=tuple(str(c) for c in record.get("category_labels") or ()),
            has_guessed_form=bool(record.get("has_guessed_form")),
        )

    def identifier_key(self) -> tuple:
        """The host predicate, durably: ordered (form, MSA, inflection type)."""
        return self.triples

    def rendered_key(self) -> tuple:
        """The FR-033 fallback: rendered morphs plus category labels."""
        return (self.rendered_morphs, self.category_labels)

    def key(self, mode: str) -> tuple:
        return self.identifier_key() if mode == SignatureMode.IDENTIFIER else self.rendered_key()

    def legible(self) -> str:
        """For a report: 'mem+buat [v+v]' -- rendered without the project."""
        morphs = "+".join(self.rendered_morphs) or "?"
        labels = "+".join(label or "?" for label in self.category_labels)
        return f"{morphs} [{labels}]" if labels else morphs


def signatures_of(line: Optional[Dict[str, Any]]) -> Optional[List[DurableAnalysisSignature]]:
    """The signatures on one result line, or None if the line has no analyses.

    None -- a CP2b single-word line, or a word that errored -- is NOT the
    same as an empty list: an empty list means the word parsed to nothing,
    None means nothing is known about it.
    """
    if not line:
        return None
    parse = line.get("parse")
    if not isinstance(parse, dict) or "analyses" not in parse:
        return None
    return [DurableAnalysisSignature.from_record(a) for a in parse.get("analyses") or ()]


@dataclass(frozen=True)
class WordComparison:
    """How one word compares between two runs."""

    wordform: str
    bucket: Optional[str]          # fixed | broken | changed | unchanged | None
    identity_change: bool
    provisional: bool
    before_count: int
    after_count: int
    added: Tuple[str, ...] = ()
    removed: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "wordform": self.wordform,
            "analyses_before": self.before_count,
            "analyses_after": self.after_count,
        }
        if self.added:
            data["analyses_added"] = list(self.added)
        if self.removed:
            data["analyses_removed"] = list(self.removed)
        if self.provisional:
            data["provisional"] = True
        return data


def _keyset(signatures: Iterable[DurableAnalysisSignature], mode: str) -> FrozenSet[tuple]:
    return frozenset(s.key(mode) for s in signatures)


def compare_word(
    wordform: str,
    before: List[DurableAnalysisSignature],
    after: List[DurableAnalysisSignature],
    mode: str,
) -> WordComparison:
    """Classify one word on SIGNATURE SETS, never on counts (FR-030).

        fixed      no analyses before, some after
        broken     some before, none after
        changed    both non-empty and the signature sets differ
        unchanged  both non-empty and the signature sets are identical

    A word going from one analysis to seven is `changed`: it still parses,
    and the grammar got looser. A count-equality test would call it
    unchanged whenever the counts happened to match and miss it entirely
    when they did not.

    Identity change (FR-032) is decided on the OTHER key: in identifier mode,
    identifier sets differ while rendered sets match; in fallback mode,
    rendered sets match (so the word would be unchanged) while identifier
    sets differ. Either way the word gets no bucket -- it is reported as an
    identity change, never as behavioural change and never as unchanged.
    """
    provisional = any(s.has_guessed_form for s in list(before) + list(after))
    base = dict(wordform=wordform, before_count=len(before), after_count=len(after),
                provisional=provisional)

    if not before and not after:
        # Parsed to nothing in both runs: nothing moved.
        return WordComparison(bucket="unchanged", identity_change=False, **base)
    if not before:
        return WordComparison(bucket="fixed", identity_change=False,
                              added=tuple(s.legible() for s in after), **base)
    if not after:
        return WordComparison(bucket="broken", identity_change=False,
                              removed=tuple(s.legible() for s in before), **base)

    by_ids_same = _keyset(before, SignatureMode.IDENTIFIER) == _keyset(after, SignatureMode.IDENTIFIER)
    by_render_same = _keyset(before, SignatureMode.RENDERED_FALLBACK) == _keyset(
        after, SignatureMode.RENDERED_FALLBACK
    )

    if mode == SignatureMode.IDENTIFIER:
        if by_ids_same:
            return WordComparison(bucket="unchanged", identity_change=False, **base)
        if by_render_same:
            return WordComparison(bucket=None, identity_change=True, **base)
    else:
        if by_render_same:
            if by_ids_same:
                return WordComparison(bucket="unchanged", identity_change=False, **base)
            return WordComparison(bucket=None, identity_change=True, **base)

    before_keys = {s.key(mode): s for s in before}
    after_keys = {s.key(mode): s for s in after}
    added = tuple(after_keys[k].legible() for k in after_keys if k not in before_keys)
    removed = tuple(before_keys[k].legible() for k in before_keys if k not in after_keys)
    return WordComparison(bucket="changed", identity_change=False,
                          added=added, removed=removed, **base)
