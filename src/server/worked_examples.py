#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Worked-example snippets for multi-step wiring patterns (Phase A of #12).

These are full recipes -- not docstring examples on individual methods --
showing the complete sequence to accomplish a task. They're surfaced via
`flextools_find_examples` when the caller asks about the relevant topic,
filling the gap where semantic search over per-method docstrings couldn't
find "how to wire up X" patterns.

Each entry:
- id              short slug
- title           one-line description
- summary         when to use this
- tags            keywords for matching (lowercase)
- library         "flexlibs2" or "liblcm" (which surface this targets)
- code            the recipe itself, ready to run inside a FlexTools Main()
- see_also        method/class names worth reading next
"""

import re
from typing import Dict, List, Tuple


# Common English stop-words we filter out of free-text queries before matching.
# Keeps "how do I create a phoneme" from collapsing into noise terms.
_STOP_WORDS = frozenset({
    "a", "an", "the", "to", "for", "of", "in", "on", "at", "by", "is", "are",
    "be", "do", "does", "did", "i", "me", "my", "you", "we", "us", "how",
    "what", "where", "when", "why", "which", "who", "and", "or", "but",
    "this", "that", "with", "from", "into", "via",
})

# Generic verbs that appear in many tags/titles and would over-match if
# weighted normally. We tokenize them but contribute zero to the score,
# so the noun terms drive matching. Means "how do I create a sense"
# requires "sense" to match -- "create" alone won't pull in unrelated
# examples that happen to have "create" in their title.
_GENERIC_VERBS = frozenset({
    "add", "set", "get", "use", "make", "run", "see", "put", "try",
    "create", "delete", "remove", "update", "find", "modify", "change",
    "build", "fetch", "show", "list", "read", "write",
})


def _terms(*inputs: str) -> List[str]:
    """Split free-text into matchable tokens (lowercase, 3+ chars, non-stopword)."""
    raw = " ".join(s or "" for s in inputs).lower()
    tokens = re.split(r"[^a-z0-9]+", raw)
    return [t for t in tokens if len(t) >= 3 and t not in _STOP_WORDS]


WORKED_EXAMPLES: List[Dict] = [
    {
        "id": "servicelocator-factory-pattern",
        "title": "Get an LCM factory or service via ServiceLocator",
        "summary": (
            "Use project.GetService(IFooFactory) when no Operations class "
            "exposes the LCM functionality you need. Common for factory "
            "lookups (IPhPhonemeFactory, ILexEntryFactory, IFsClosedFeatureFactory)."
        ),
        "tags": [
            "servicelocator", "service", "factory", "lcm", "discovery",
            "getservice", "getclrtype", "ilookup",
        ],
        "library": "flexlibs2",
        "code": '''from flexlibs2 import FLExProject
# Resolve any LCM factory or service interface by type.
# project.GetService is a discoverable wrapper around
# project.Cache.ServiceLocator.GetService(...) -- you do NOT need
# clr.GetClrType() when going through this wrapper.
from SIL.LCModel import IPhPhonemeFactory

def Main(project, report, modifyAllowed):
    phoneme_factory = project.GetService(IPhPhonemeFactory)
    report.Info(f"Got factory: {type(phoneme_factory).__name__}")

    if modifyAllowed:
        # Factories create unowned objects -- always Add to the owning
        # collection before setting properties (see flexlibs2 Phase 2
        # 'orphan-NPE' notes).
        new_phoneme = phoneme_factory.Create()
        project.Cache.LangProject.PhonologicalDataOA.PhonemeSetsOS[0].PhonemesOC.Add(new_phoneme)
        # Now safe to mutate.
        report.Info(f"Created phoneme with class id {new_phoneme.ClassID}")
''',
        "see_also": ["FLExProject.GetService", "FLExProject.Cache"],
    },
    {
        "id": "phoneme-creation-and-wiring",
        "title": "Create a phoneme and add it to the default phoneme set",
        "summary": (
            "End-to-end recipe for adding a new phoneme: use project.Phonemes "
            "wrapper to create + describe + verify. Avoids the raw "
            "factory/ownership wiring that bites users going through LCM directly."
        ),
        "tags": [
            "phoneme", "phonemes", "phoneme set", "ipa", "phonology",
            "create phoneme", "add phoneme",
        ],
        "library": "flexlibs2",
        "code": '''from flexlibs2 import FLExProject

def Main(project, report, modifyAllowed):
    # Check the phoneme doesn't already exist (Find returns None if absent).
    existing = project.Phonemes.Find("/p/")
    if existing is not None:
        report.Info("/p/ already exists; skipping create")
        return

    if modifyAllowed:
        # Create attaches the phoneme to the default phoneme set automatically.
        phoneme = project.Phonemes.Create("/p/")
        project.Phonemes.SetDescription(phoneme, "voiceless bilabial stop")
        report.Info(f"Created /p/ -- repr={project.Phonemes.GetRepresentation(phoneme)}")
    else:
        report.Info("(Would create /p/: voiceless bilabial stop)")

    # Iterate the full phoneme inventory afterwards
    for ph in project.Phonemes.GetAll():
        rep = project.Phonemes.GetRepresentation(ph)
        desc = project.Phonemes.GetDescription(ph)
        report.Info(f"  {rep}: {desc}")
''',
        "see_also": [
            "PhonemeOperations.Create",
            "PhonemeOperations.Find",
            "PhonemeOperations.SetDescription",
        ],
    },
    {
        "id": "phonological-rule-with-context",
        "title": "Create a phonological rule with input, output, and context",
        "summary": (
            "Build a complete phonological rule (Voicing Assimilation: /t/ -> /d/ "
            "intervocalically) showing input/output segment wiring plus left "
            "and right natural-class contexts. Demonstrates the full PhonRules "
            "Operations surface, not just Create."
        ),
        "tags": [
            "phonological rule", "phonrule", "phonrules", "rewrite rule",
            "phonology", "natural class", "input segment", "output segment",
            "context", "voicing", "assimilation",
        ],
        "library": "flexlibs2",
        "code": '''from flexlibs2 import FLExProject

def Main(project, report, modifyAllowed):
    # Look up the phonemes and natural class we'll wire into the rule.
    phoneme_t = project.Phonemes.Find("/t/")
    phoneme_d = project.Phonemes.Find("/d/")
    vowels   = project.NaturalClasses.Find("Vowels")

    if not (phoneme_t and phoneme_d and vowels):
        report.Error("Missing prerequisites: need /t/, /d/, and 'Vowels' natural class")
        return

    if modifyAllowed:
        # 1. Create the rule shell
        rule = project.PhonRules.Create(
            "Voicing Assimilation",
            "Voiceless stops become voiced between vowels",
        )
        # 2. Set input (what the rule rewrites) and output (what it becomes)
        project.PhonRules.AddInputSegment(rule, phoneme_t)
        project.PhonRules.AddOutputSegment(rule, phoneme_d)
        # 3. Set the environment: V_V
        project.PhonRules.SetLeftContext(rule, vowels)
        project.PhonRules.SetRightContext(rule, vowels)
        report.Info("Created rule: /t/ -> /d/ / V_V")
    else:
        report.Info("(Would create rule: /t/ -> /d/ / V_V)")
''',
        "see_also": [
            "PhonologicalRuleOperations.Create",
            "PhonologicalRuleOperations.AddInputSegment",
            "PhonologicalRuleOperations.AddOutputSegment",
            "PhonologicalRuleOperations.SetLeftContext",
            "PhonologicalRuleOperations.SetRightContext",
            "NaturalClassOperations.Find",
        ],
    },
]


def _tokenize_to_words(text: str) -> set:
    """Lowercase + non-alphanumeric split, returning a word set."""
    words = set(re.split(r"[^a-z0-9]+", text.lower()))
    words.discard("")
    return words


def _build_example_index() -> List[Tuple[Dict, frozenset, frozenset]]:
    """Precompute (example, tag_words, text_words) once at module load.

    Without this, find_worked_examples re-tokenized every example's tags +
    title + summary + see_also on every call -- harmless at N=3 but a
    waste once the list grows.
    """
    indexed: List[Tuple[Dict, frozenset, frozenset]] = []
    for example in WORKED_EXAMPLES:
        tag_words: set = set()
        for t in example.get("tags", []):
            tag_words |= _tokenize_to_words(t)

        text_words: set = set()
        text_words |= _tokenize_to_words(example["title"])
        text_words |= _tokenize_to_words(example["summary"])
        for s in example.get("see_also", []):
            text_words |= _tokenize_to_words(s)
        text_words -= tag_words  # don't double-count

        indexed.append((example, frozenset(tag_words), frozenset(text_words)))
    return indexed


_EXAMPLE_INDEX: List[Tuple[Dict, frozenset, frozenset]] = _build_example_index()


def find_worked_examples(
    query: str = "",
    operation_type: str = "",
    object_type: str = "",
    max_results: int = 5,
) -> List[Dict]:
    """Return worked-example entries that match the input terms.

    Tokenizes all inputs into 3+ char non-stopword words, then scores each
    example by:
        score = 2 * (terms hitting tags) + 1 * (terms hitting title/summary/see_also)
    Returns entries with score > 0, sorted highest-first, truncated to
    max_results. Tag matches outweigh title/summary matches so the
    high-signal "this snippet is about X" tags drive ranking.

    Generic verbs (create, add, get, ...) are tokenized but contribute zero
    score so noun terms drive ranking; this prevents queries like
    "create a sense" from false-matching examples that just share the verb.
    """
    terms = _terms(query, operation_type, object_type)
    scoring_terms = [t for t in terms if t not in _GENERIC_VERBS]
    if not scoring_terms:
        return []

    scored = []
    for example, tag_words, text_words in _EXAMPLE_INDEX:
        tag_hits = sum(1 for term in scoring_terms if term in tag_words)
        text_hits = sum(1 for term in scoring_terms if term in text_words)
        score = tag_hits * 2 + text_hits
        if score > 0:
            scored.append((score, example))

    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:max_results]]
