#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #48: inline casting metadata into get_object_api responses.

Casting knowledge used to live only in flextools_resolve_property, a tool the
model rarely called (#22). #48 joins per-property casting requirements straight
into the get_object_api / discovery response so the model writes cast-correct
code on the first draft. The guidance MUST be byte-identical to what a preflight
rejection would emit -- both paths route through the same rewrite generator.

Coverage:
  - property with a casting-index entry -> annotated (requires_cast/cast_to/cast_example)
  - polymorphic collection -> annotated (polymorphic/iteration_note)
  - property with NO entry -> returned byte-for-byte unchanged (golden)
  - summary_only -> only the top-level counter, no per-item fields (#11)
  - cast_example == detect_casting_needs rewrite for the same access pattern
  - flow-independent safe members (Hvo/Guid/...) skipped, matching the rejection
    path (#40) so the two code paths never diverge
  - paginate_entity wiring: casting_notes added iff something was annotated
"""

import copy
import unittest

from server.validators import (
    annotate_properties_with_casting,
    build_property_cast_example,
    build_casting_notes,
    detect_casting_needs,
)
from server.handlers.api import paginate_entity


# Controlled stand-in for the real (986-entry) casting index. Only the shapes
# the join reads are populated: `properties` (receiver-cast) and
# `polymorphic_collections` (per-item cast on iteration).
FAKE_CASTING_INDEX = {
    "properties": {
        # Single defined_on -> _pick_cast_interface resolves -> cast_example emitted.
        "MorphoSyntaxAnalysisRA": {
            "defined_on": ["ILexSense"],
            "requires_cast_from": ["ICmObject", "ICmObjectOrId"],
        },
        # Multiple defined_on with no receiver signal -> requires_cast still set,
        # but no confidently-wrong cast_example.
        "SensesOS": {
            "defined_on": ["ILexEntry", "ILexSense"],
            "requires_cast_from": ["ICmObject"],
        },
        # A universally-safe member that lives on ICmObject; the rejection path
        # skips it (#40) so the annotation must too.
        "Hvo": {
            "defined_on": ["ICmObject"],
            "requires_cast_from": [],
        },
    },
    "polymorphic_collections": {
        "AllomorphsOS": {
            "base_type": "IMoForm",
            "concrete_types": ["IMoStemAllomorph", "IMoAffixAllomorph"],
            "casting_hint": "Cast to concrete type.",
        },
    },
}


class TestAnnotateProperties(unittest.TestCase):
    def test_receiver_cast_property_annotated(self):
        props = [{"name": "MorphoSyntaxAnalysisRA", "description": "the MSA"}]
        out, count = annotate_properties_with_casting(props, FAKE_CASTING_INDEX)
        self.assertEqual(count, 1)
        p = out[0]
        self.assertTrue(p["requires_cast"])
        self.assertEqual(p["cast_to"], ["ILexSense"])
        self.assertEqual(p["cast_example"], "ILexSense(obj).MorphoSyntaxAnalysisRA")

    def test_ambiguous_property_flagged_without_example(self):
        """Multiple defined_on + no receiver signal: flag but emit no rewrite."""
        props = [{"name": "SensesOS", "description": "senses"}]
        out, count = annotate_properties_with_casting(props, FAKE_CASTING_INDEX)
        self.assertEqual(count, 1)
        self.assertTrue(out[0]["requires_cast"])
        self.assertEqual(out[0]["cast_to"], ["ILexEntry", "ILexSense"])
        self.assertNotIn("cast_example", out[0])

    def test_polymorphic_collection_annotated(self):
        props = [{"name": "AllomorphsOS", "description": "allomorphs"}]
        out, count = annotate_properties_with_casting(props, FAKE_CASTING_INDEX)
        self.assertEqual(count, 1)
        self.assertTrue(out[0]["polymorphic"])
        self.assertIn("cast_to_concrete", out[0]["iteration_note"])
        # Not a receiver-cast property -> no requires_cast key.
        self.assertNotIn("requires_cast", out[0])

    def test_property_with_no_entry_is_byte_identical(self):
        """Golden: entity whose properties are absent from the index is untouched."""
        props = [
            {"name": "SomeRandomProp", "description": "no casting", "return_type": "str"},
            {"name": "AnotherProp", "description": "also fine"},
        ]
        original = copy.deepcopy(props)
        out, count = annotate_properties_with_casting(props, FAKE_CASTING_INDEX)
        self.assertEqual(count, 0)
        self.assertEqual(out, original)
        # Original dict objects reused (no shallow-copy churn).
        self.assertIs(out[0], props[0])

    def test_summary_only_suppresses_per_item_fields(self):
        """#11: summary mode returns only the counter, no per-item annotations."""
        props = [
            {"name": "MorphoSyntaxAnalysisRA", "description": "msa"},
            {"name": "AllomorphsOS", "description": "forms"},
        ]
        original = copy.deepcopy(props)
        out, count = annotate_properties_with_casting(
            props, FAKE_CASTING_INDEX, summary_only=True
        )
        self.assertEqual(count, 2)  # counter still populated
        self.assertEqual(out, original)  # but items untouched
        for p in out:
            self.assertNotIn("requires_cast", p)
            self.assertNotIn("polymorphic", p)

    def test_safe_members_skipped_matching_rejection_path(self):
        """#40 parity: Hvo/Guid/ClassID/ClassName never get flagged."""
        props = [{"name": "Hvo", "description": "id"}]
        out, count = annotate_properties_with_casting(props, FAKE_CASTING_INDEX)
        self.assertEqual(count, 0)
        self.assertNotIn("requires_cast", out[0])
        # And the rejection path agrees.
        rej = detect_casting_needs("x = obj.Hvo\n", FAKE_CASTING_INDEX)
        self.assertFalse(any(i["property"] == "Hvo" for i in rej["casting_issues"]))

    def test_no_casting_index_returns_unchanged(self):
        props = [{"name": "MorphoSyntaxAnalysisRA"}]
        out, count = annotate_properties_with_casting(props, None)
        self.assertEqual(count, 0)
        self.assertIs(out, props)


class TestCastExampleConsistency(unittest.TestCase):
    """cast_example must be byte-identical to casting_issues[*].rewrite."""

    def test_cast_example_matches_rejection_rewrite(self):
        prop = "MorphoSyntaxAnalysisRA"
        example = build_property_cast_example(prop, FAKE_CASTING_INDEX, receiver_name="obj")
        result = detect_casting_needs(f"x = obj.{prop}\n", FAKE_CASTING_INDEX)
        rewrites = [i.get("rewrite") for i in result["casting_issues"] if i["property"] == prop]
        self.assertIn(example, rewrites)
        self.assertEqual(example, "ILexSense(obj).MorphoSyntaxAnalysisRA")

    def test_ambiguous_property_yields_no_example(self):
        self.assertIsNone(build_property_cast_example("SensesOS", FAKE_CASTING_INDEX))

    def test_unknown_property_yields_no_example(self):
        self.assertIsNone(build_property_cast_example("Nope", FAKE_CASTING_INDEX))


class TestBuildCastingNotes(unittest.TestCase):
    def test_zero_returns_none(self):
        self.assertIsNone(build_casting_notes(0))

    def test_singular_and_plural(self):
        self.assertIn("1 property requires", build_casting_notes(1))
        self.assertIn("3 properties require", build_casting_notes(3))


class TestPaginateEntityWiring(unittest.TestCase):
    """paginate_entity joins the metadata and sets the top-level counter."""

    def _entity(self):
        return {
            "category": "lexicon",
            "summary": "A lexical sense.",
            "methods": [],
            "properties": [
                {"name": "MorphoSyntaxAnalysisRA", "description": "msa"},
                {"name": "PlainProp", "description": "nothing special"},
            ],
        }

    def test_casting_index_annotates_and_sets_notes(self):
        result = paginate_entity(
            self._entity(), summary_only=False, method_filter="", limit=50, offset=0,
            object_type="ILexSense", library="liblcm", casting_index=FAKE_CASTING_INDEX,
        )
        props = {p["name"]: p for p in result["properties"]}
        self.assertTrue(props["MorphoSyntaxAnalysisRA"]["requires_cast"])
        self.assertNotIn("requires_cast", props["PlainProp"])
        self.assertIn("casting_notes", result)
        self.assertIn("1 property requires", result["casting_notes"])

    def test_no_casting_index_leaves_response_clean(self):
        result = paginate_entity(
            self._entity(), summary_only=False, method_filter="", limit=50, offset=0,
            object_type="ILexSense", library="liblcm", casting_index=None,
        )
        self.assertNotIn("casting_notes", result)
        for p in result["properties"]:
            self.assertNotIn("requires_cast", p)

    def test_entity_with_no_matching_props_has_no_notes(self):
        entity = {
            "category": "lexicon", "summary": "x", "methods": [],
            "properties": [{"name": "PlainProp", "description": "nothing"}],
        }
        result = paginate_entity(
            entity, summary_only=False, method_filter="", limit=50, offset=0,
            object_type="Whatever", library="liblcm", casting_index=FAKE_CASTING_INDEX,
        )
        self.assertNotIn("casting_notes", result)

    def test_summary_only_sets_notes_without_per_item_fields(self):
        result = paginate_entity(
            self._entity(), summary_only=True, method_filter="", limit=50, offset=0,
            object_type="ILexSense", library="liblcm", casting_index=FAKE_CASTING_INDEX,
        )
        self.assertIn("casting_notes", result)
        for p in result["properties"]:
            self.assertNotIn("requires_cast", p)
            self.assertNotIn("cast_example", p)


if __name__ == "__main__":
    unittest.main()
