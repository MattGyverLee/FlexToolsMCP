#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #45: canonical-intent map surfaces the correct flexicon
method as the top search result for high-frequency intents, instead of the
assistant guessing nonexistent accessor/method names.
"""

import unittest

from server.handlers.api import _match_canonical_intents, CANONICAL_INTENTS


# Minimal fake flexicon index carrying just the methods the map points at.
FAKE_INDEX = {
    "entities": {
        "LexSenseOperations": {
            "namespace": "flexicon.code.Lexicon.LexSenseOperations",
            "category": "lexicon",
            "methods": [
                {"name": "GetPartOfSpeechObject", "signature": "GetPartOfSpeechObject(sense)",
                 "summary": "Get the POS object for a sense."},
                {"name": "GetGloss", "signature": "GetGloss(sense)", "summary": "Get sense gloss."},
                {"name": "GetDefinition", "signature": "GetDefinition(sense)", "summary": "Get definition."},
            ],
        },
        "TextOperations": {
            "namespace": "flexicon.code.TextsWords.TextOperations",
            "category": "texts",
            "methods": [{"name": "GetAll", "signature": "GetAll()", "summary": "All texts."}],
        },
        "LexEntryOperations": {
            "namespace": "flexicon.code.Lexicon.LexEntryOperations",
            "category": "lexicon",
            "methods": [
                {"name": "GetAll", "signature": "GetAll()", "summary": "All entries."},
                {"name": "GetLexemeForm", "signature": "GetLexemeForm(e)", "summary": "Lexeme form."},
                {"name": "GetHeadword", "signature": "GetHeadword(e)", "summary": "Headword."},
            ],
        },
        "WordformOperations": {
            "namespace": "flexicon.code.TextsWords.WordformOperations",
            "category": "texts",
            "methods": [{"name": "GetAll", "signature": "GetAll()", "summary": "All wordforms."}],
        },
        "WfiGlossOperations": {
            "namespace": "flexicon.code.TextsWords.WfiGlossOperations",
            "category": "texts",
            "methods": [{"name": "GetForm", "signature": "GetForm(g)", "summary": "Gloss form."}],
        },
    }
}


class TestCanonicalIntents(unittest.TestCase):
    def _first(self, query):
        rows = _match_canonical_intents(query, FAKE_INDEX)
        return (rows[0]["entity"], rows[0]["name"]) if rows else None

    def test_sense_part_of_speech(self):
        self.assertEqual(
            self._first("how do I get the sense part of speech?"),
            ("LexSenseOperations", "GetPartOfSpeechObject"),
        )

    def test_list_texts(self):
        self.assertEqual(self._first("list all texts"), ("TextOperations", "GetAll"))

    def test_wordform_gloss_distinct_from_sense_gloss(self):
        self.assertEqual(self._first("get the wordform gloss"), ("WfiGlossOperations", "GetForm"))
        self.assertEqual(self._first("get the sense gloss"), ("LexSenseOperations", "GetGloss"))

    def test_rows_are_flagged_and_ready_to_import(self):
        rows = _match_canonical_intents("iterate entries", FAKE_INDEX)
        self.assertTrue(rows)
        row = rows[0]
        self.assertTrue(row["canonical_intent"])
        self.assertEqual(row["import_statement"], "from flexicon import LexEntryOperations")
        self.assertEqual(row["type"], "method")

    def test_no_match_returns_empty(self):
        self.assertEqual(_match_canonical_intents("frobnicate the widgets", FAKE_INDEX), [])

    def test_missing_method_is_skipped(self):
        # Index without the target method must not raise or fabricate a row.
        thin = {"entities": {"LexSenseOperations": {"methods": []}}}
        self.assertEqual(_match_canonical_intents("sense part of speech", thin), [])

    def test_dedup_same_method(self):
        # A query hitting two phrase groups for the same method yields one row.
        rows = _match_canonical_intents("sense part of speech pos of sense", FAKE_INDEX)
        keys = [(r["entity"], r["name"]) for r in rows]
        self.assertEqual(keys.count(("LexSenseOperations", "GetPartOfSpeechObject")), 1)

    def test_all_map_targets_are_well_formed(self):
        # Guard against typos in the map structure itself.
        for phrases, entity, method in CANONICAL_INTENTS:
            self.assertTrue(phrases and all(isinstance(p, str) for p in phrases))
            self.assertTrue(entity.endswith("Operations"))
            self.assertTrue(method and method[0].isupper())


if __name__ == "__main__":
    unittest.main()
