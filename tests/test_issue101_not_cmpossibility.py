#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #101: IMoInflAffixSlot / IMoInflAffixTemplate / IMoInflClass
are not ICmPossibility despite having Name.

All three declare base="CmObject" (MasterLCModel.xml:3310/3351/3458) and are
NOT ICmPossibility. Their `Name` (MultiUnicode) is each type's OWN attribute
-- a pure name collision with CmPossibility.Name, not inheritance. Code that
reasonably guesses "looks like a possibility list, cast to ICmPossibility to
read .Name" throws `TypeError: object does not implement ICmPossibility` at
runtime.

Issue #87's proposed `interpretation`/`caveats` index field does not exist
yet (grepped clean across src/ -- only unrelated hits in tool_definitions.py
prose and the diagnostic reconstruct/render modules), so this fix does NOT
reuse it. Instead it's a read-path fix in server.handlers.api: a curated,
hard-coded set (NOT a structural heuristic) checked purely against the
requested `object_type` string, needing no index regeneration and no new
index field.

Deliberately NOT a structural rule ("declares an own Name property and
doesn't implement ICmPossibility"): that heuristic matches ~76 other
liblcm entities (CmAgent, CmFile, LangProject, ...) that were never mistaken
for possibility lists. IMoMorphType is the critical contrast case -- it DOES
inherit base="CmPossibility", so ICmPossibility(morphType).Name is correct
there, and the regression test for that is the one that matters most.

Coverage:
  - All 3 named types (interface AND concrete-class forms) are flagged.
  - IMoMorphType (interface AND concrete-class forms) is explicitly NOT
    flagged -- the over-broadening regression test.
  - An unrelated type is not flagged.
  - paginate_entity (get_object_api's response builder) surfaces the
    warning for the curated types, in both summary and full mode, and
    omits it for everything else.
  - Cross-check against the real shipped liblcm index: the 3 types
    genuinely lack "ICmPossibility" in `interfaces`, and IMoMorphType
    genuinely has it -- locking in the premise this fix depends on.
"""

import json
import unittest
from pathlib import Path


# ---------------------------------------------------------------------------
# server.handlers.api._not_cmpossibility_warning / curated set
# ---------------------------------------------------------------------------

class TestNotCmPossibilityWarning(unittest.TestCase):
    def test_all_three_interfaces_flagged(self):
        from server.handlers.api import _not_cmpossibility_warning

        for name in ("IMoInflAffixSlot", "IMoInflAffixTemplate", "IMoInflClass"):
            with self.subTest(name=name):
                warning = _not_cmpossibility_warning(name)
                self.assertIsNotNone(warning)
                self.assertIn("ICmPossibility", warning)
                self.assertIn(name, warning)

    def test_concrete_class_forms_also_flagged(self):
        """Same real-world objects, reachable under the class entity too
        (e.g. "MoInflAffixSlot" alongside "IMoInflAffixSlot")."""
        from server.handlers.api import _not_cmpossibility_warning

        for name in ("MoInflAffixSlot", "MoInflAffixTemplate", "MoInflClass"):
            with self.subTest(name=name):
                self.assertIsNotNone(_not_cmpossibility_warning(name))

    def test_immo_morph_type_not_flagged(self):
        """THE over-broadening regression test. IMoMorphType genuinely IS
        ICmPossibility (base=CmPossibility in MasterLCModel.xml), so
        ICmPossibility(morphType).Name is correct there. If a future edit
        turns the curated set into a structural heuristic, this is the
        test that should catch it."""
        from server.handlers.api import _not_cmpossibility_warning

        self.assertIsNone(_not_cmpossibility_warning("IMoMorphType"))
        self.assertIsNone(_not_cmpossibility_warning("MoMorphType"))

    def test_unrelated_type_not_flagged(self):
        from server.handlers.api import _not_cmpossibility_warning

        self.assertIsNone(_not_cmpossibility_warning("ILexEntry"))
        self.assertIsNone(_not_cmpossibility_warning("ICmPossibility"))

    def test_curated_set_contains_exactly_the_named_types(self):
        """Pin the set itself -- catches accidental broadening/narrowing."""
        from server.handlers.api import NOT_CMPOSSIBILITY_NAME_COLLISION

        self.assertEqual(
            NOT_CMPOSSIBILITY_NAME_COLLISION,
            frozenset({
                "IMoInflAffixSlot", "MoInflAffixSlot",
                "IMoInflAffixTemplate", "MoInflAffixTemplate",
                "IMoInflClass", "MoInflClass",
            }),
        )


# ---------------------------------------------------------------------------
# paginate_entity wiring (get_object_api's response builder)
# ---------------------------------------------------------------------------

class TestPaginateEntityNotCmPossibilityWarning(unittest.TestCase):
    def _entity(self, **overrides):
        base = {
            "category": "grammar",
            "summary": "Test entity",
            "source_file": "",
            "methods": [],
            "properties": [{"name": "Name", "description": "own Name field"}],
        }
        base.update(overrides)
        return base

    def test_curated_type_flagged_full_mode(self):
        from server.handlers.api import paginate_entity

        result = paginate_entity(
            self._entity(), summary_only=False, method_filter="", limit=50, offset=0,
            object_type="IMoInflAffixSlot", library="liblcm",
        )
        self.assertIn("not_cmpossibility_warning", result)
        self.assertIn("ICmPossibility", result["not_cmpossibility_warning"])

    def test_curated_type_flagged_summary_mode(self):
        from server.handlers.api import paginate_entity

        result = paginate_entity(
            self._entity(), summary_only=True, method_filter="", limit=50, offset=0,
            object_type="IMoInflAffixTemplate", library="liblcm",
        )
        self.assertIn("not_cmpossibility_warning", result)

    def test_immo_morph_type_not_flagged_via_paginate_entity(self):
        from server.handlers.api import paginate_entity

        result = paginate_entity(
            self._entity(), summary_only=False, method_filter="", limit=50, offset=0,
            object_type="IMoMorphType", library="liblcm",
        )
        self.assertNotIn("not_cmpossibility_warning", result)

    def test_unrelated_type_not_flagged_via_paginate_entity(self):
        from server.handlers.api import paginate_entity

        result = paginate_entity(
            self._entity(), summary_only=False, method_filter="", limit=50, offset=0,
            object_type="ILexEntry", library="liblcm",
        )
        self.assertNotIn("not_cmpossibility_warning", result)


# ---------------------------------------------------------------------------
# Real shipped liblcm index: locks in the premise
# ---------------------------------------------------------------------------

class TestRealIndexPremise(unittest.TestCase):
    """Confirms the facts this fix depends on against the actual shipped
    liblcm index, so index drift on a future refresh would break these
    tests rather than silently invalidating the fix."""

    @classmethod
    def setUpClass(cls):
        idx_path = (
            Path(__file__).parent.parent
            / "src" / "flextoolsmcp" / "index" / "liblcm" / "liblcm_api_v11.0.0.json"
        )
        if not idx_path.exists():
            cls.entities = None
            return
        with open(idx_path, encoding="utf-8") as f:
            data = json.load(f)
        cls.entities = data.get("entities", {})

    def test_three_types_lack_icmpossibility_interface(self):
        if self.entities is None:
            self.skipTest("shipped liblcm index not found")
        for name in ("IMoInflAffixSlot", "IMoInflAffixTemplate", "IMoInflClass"):
            with self.subTest(name=name):
                entity = self.entities.get(name)
                self.assertIsNotNone(entity, f"{name} missing from shipped index")
                self.assertNotIn("ICmPossibility", entity.get("interfaces", []))

    def test_three_types_have_own_name_property(self):
        if self.entities is None:
            self.skipTest("shipped liblcm index not found")
        for name in ("IMoInflAffixSlot", "IMoInflAffixTemplate", "IMoInflClass"):
            with self.subTest(name=name):
                entity = self.entities[name]
                prop_names = {p.get("name") for p in entity.get("properties", [])}
                self.assertIn("Name", prop_names)

    def test_immo_morph_type_genuinely_has_icmpossibility(self):
        """The contrast case: confirms the fix's exclusion is correct, not
        just convenient."""
        if self.entities is None:
            self.skipTest("shipped liblcm index not found")
        entity = self.entities.get("IMoMorphType")
        self.assertIsNotNone(entity, "IMoMorphType missing from shipped index")
        self.assertIn("ICmPossibility", entity.get("interfaces", []))


if __name__ == "__main__":
    unittest.main()
