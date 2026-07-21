#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression tests for the worked-examples matching layer (Phase A of #12).
"""

from server.worked_examples import find_worked_examples, WORKED_EXAMPLES


def test_phonrule_query_returns_phonrule_example():
    hits = find_worked_examples(query="create a phonological rule")
    assert hits, "Expected at least one hit for phonological rule query"
    assert hits[0]["id"] == "phonological-rule-with-context"


def test_phoneme_query_returns_phoneme_example():
    hits = find_worked_examples(query="how do I create a phoneme")
    assert hits, "Expected at least one hit for phoneme query"
    assert hits[0]["id"] == "phoneme-creation-and-wiring"


def test_factory_query_returns_servicelocator_example():
    hits = find_worked_examples(query="factory")
    assert hits, "Expected at least one hit for 'factory'"
    assert hits[0]["id"] == "servicelocator-factory-pattern"


def test_sense_query_returns_nothing():
    """No worked example covers senses -- must not false-positive."""
    hits = find_worked_examples(query="how do I create a sense")
    assert hits == [], f"Expected no hits for sense query, got: {[h['id'] for h in hits]}"


def test_generic_verb_alone_returns_nothing():
    """'create' alone shouldn't pull in any example -- noun terms drive matching."""
    hits = find_worked_examples(query="create")
    assert hits == [], f"'create' alone should not match, got: {[h['id'] for h in hits]}"


def test_voicing_assimilation_returns_phonrule():
    """Specific tag terms drive exact matches."""
    hits = find_worked_examples(query="voicing assimilation")
    assert hits, "Expected hit for voicing assimilation"
    assert hits[0]["id"] == "phonological-rule-with-context"


def test_empty_query_returns_nothing():
    assert find_worked_examples(query="") == []
    assert find_worked_examples() == []


def test_wordform_query_returns_analysis_subtype_example():
    """#12 seth-logs sub-gap: distinguishing analysis subtypes."""
    hits = find_worked_examples(query="distinguish wordform analysis gloss")
    assert hits, "Expected a hit for analysis-subtype query"
    assert hits[0]["id"] == "analysis-subtype-disambiguation"


def test_kclsid_query_returns_analysis_subtype_example():
    """A user reaching for kclsid* constants should be steered to the example."""
    hits = find_worked_examples(query="kclsid class id constant IWfiGloss")
    assert hits, "Expected a hit for kclsid query"
    assert hits[0]["id"] == "analysis-subtype-disambiguation"


def test_object_type_drives_match():
    """find_examples passes object_type, not free-text query -- verify that path."""
    hits = find_worked_examples(object_type="phoneme")
    assert hits and hits[0]["id"] == "phoneme-creation-and-wiring"


def test_all_examples_have_required_fields():
    """Schema check -- every example must have these fields populated."""
    required = ["id", "title", "summary", "tags", "library", "code", "see_also"]
    for ex in WORKED_EXAMPLES:
        for field in required:
            assert field in ex, f"{ex.get('id', '?')} missing field: {field}"
            assert ex[field], f"{ex['id']} has empty field: {field}"


def test_all_example_code_parses_as_python():
    """Worked-example code must be valid Python so users can copy-paste."""
    import ast
    for ex in WORKED_EXAMPLES:
        try:
            ast.parse(ex["code"])
        except SyntaxError as e:
            raise AssertionError(f"{ex['id']} code does not parse: {e}") from e


if __name__ == "__main__":
    for name in [n for n in dir() if n.startswith("test_")]:
        try:
            globals()[name]()
            print(f"[PASS] {name}")
        except AssertionError as e:
            print(f"[FAIL] {name}: {e}")
