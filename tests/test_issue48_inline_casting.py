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
import re
import unittest
from pathlib import Path

from server.validators import (
    annotate_properties_with_casting,
    build_property_cast_example,
    build_casting_notes,
    detect_casting_needs,
)
from server.handlers.api import paginate_entity

# Templates directory shipped to users via flextools_get_module_template.
_TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "flextoolsmcp" / "templates"


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
        # Bare substring "cast_to_concrete" passes both before and after the
        # #103-class phantom fix (the broken text was
        # "CastingOperations.cast_to_concrete(item)" -- a substring match
        # can't tell that apart from the real call). Pin the FULL, real call
        # form instead: `flexicon.code.lcm_casting.cast_to_concrete` is a
        # bare module-level function, not a `CastingOperations` method
        # (that class does not exist anywhere in pyflexicon).
        self.assertIn("concrete = cast_to_concrete(item)", out[0]["iteration_note"])
        self.assertNotIn("CastingOperations", out[0]["iteration_note"])
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


class TestShippedLiblcmTemplateCastingArity(unittest.TestCase):
    """Regression coverage for the Symbol-B half of the cast_to_concrete
    phantom (specs/swahili-audit-2026-09/reviews/cycle10-phantom.md):

      1. flexicon.code.lcm_casting.cast_to_concrete(obj) takes exactly ONE
         argument, but every shipped call site in 3-liblcm-template.py
         (live code AND prose "examples") passed TWO. Two args would raise
         TypeError the moment a user ran the generated module.
      2. ILexEntry is function-local inside flexicon's internal
         _ensure_interfaces() and is never exported from
         flexicon.code.lcm_casting, so `from flexicon.code.lcm_casting
         import ILexEntry` raises ImportError before Main() ever runs.

    This template is served verbatim to users by
    flextools_get_module_template(flavor='liblcm'/'advanced'), so a wrong
    call form here is code users actually run, not just documentation.
    """

    _CAST_CALL_RE = re.compile(r"cast_to_concrete\(([^()]*)\)")
    _BAD_IMPORT_RE = re.compile(
        r"from\s+flexicon\.code\.lcm_casting\s+import\s+([^\n]+)"
    )

    def _liblcm_template_text(self):
        path = _TEMPLATES_DIR / "3-liblcm-template.py"
        self.assertTrue(path.exists(), f"shipped template missing: {path}")
        return path.read_text(encoding="utf-8")

    def test_every_cast_to_concrete_call_site_takes_one_argument(self):
        """Every cast_to_concrete(...) call in the shipped liblcm template --
        live code and prose examples alike -- must pass exactly one
        positional argument. flexicon's cast_to_concrete resolves the
        concrete interface itself from the object's C# ClassName; a second
        argument is not part of its signature and raises TypeError."""
        text = self._liblcm_template_text()
        calls = self._CAST_CALL_RE.findall(text)
        self.assertTrue(calls, "expected at least one cast_to_concrete(...) call in the template")

        bad_sites = []
        for raw_args in calls:
            args = [a for a in (p.strip() for p in raw_args.split(",")) if a]
            if len(args) != 1:
                bad_sites.append((raw_args, len(args)))

        self.assertEqual(
            bad_sites, [],
            f"cast_to_concrete call(s) with wrong arity (expected 1 arg): {bad_sites}",
        )

    def test_no_template_imports_ilexentry_from_lcm_casting(self):
        """flexicon.code.lcm_casting never re-exports ILexEntry (it is
        function-local inside the package's internal _ensure_interfaces()).
        `from flexicon.code.lcm_casting import ILexEntry` is an ImportError
        that kills the module before Main() runs. ILexEntry must come from
        `SIL.LCModel` instead (see the already-correct import block at the
        top of 3-liblcm-template.py)."""
        text = self._liblcm_template_text()
        for match in self._BAD_IMPORT_RE.finditer(text):
            imported_names = [n.strip() for n in match.group(1).split(",")]
            self.assertNotIn(
                "ILexEntry", imported_names,
                f"template imports ILexEntry from flexicon.code.lcm_casting: {match.group(0)!r}",
            )

    def test_live_flexicon_cast_to_concrete_signature_is_single_arg(self):
        """Ground truth check against the actual installed flexicon package
        (not just the template text) so this test cannot drift from
        reality the way the phantom template text did."""
        try:
            import inspect

            from flexicon.code.lcm_casting import cast_to_concrete
        except Exception as exc:
            self.skipTest(f"flexicon not importable in this environment ({exc})")
            return

        sig = inspect.signature(cast_to_concrete)
        params = [
            p for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]
        self.assertEqual(
            len(params), 1,
            f"cast_to_concrete signature changed -- expected 1 positional param, got {sig}",
        )


if __name__ == "__main__":
    unittest.main()
