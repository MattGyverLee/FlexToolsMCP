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

import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import patch


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
# resolve_property wiring (exploring Name on morphology list objects)
# ---------------------------------------------------------------------------

class TestResolvePropertyNotCmPossibilityWarning(unittest.TestCase):
    def _resolve(self, **kwargs):
        from flextoolsmcp.server.handlers.api import handle_resolve_property

        with patch(
            "flextoolsmcp.server.handlers.api.get_api_index",
        ) as mock_index:
            from flextoolsmcp.server import APIIndex
            from flextoolsmcp.server.kernel import get_index_dir

            mock_index.return_value = APIIndex.load(get_index_dir())
            payload = asyncio.run(handle_resolve_property(kwargs))
        return json.loads(payload[0].text)

    def test_curated_context_includes_warning(self):
        result = self._resolve(
            property_name="Name",
            context_entity="IMoInflAffixSlot",
            include_casting_info=True,
        )
        self.assertIn("not_cmpossibility_warning", result)
        self.assertIn("NOT ICmPossibility", result["not_cmpossibility_warning"])

    def test_immo_morph_type_context_omits_warning(self):
        result = self._resolve(
            property_name="Name",
            context_entity="IMoMorphType",
            include_casting_info=True,
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


# ---------------------------------------------------------------------------
# run_module casting validator (preflight) -- issue #101 follow-up
# ---------------------------------------------------------------------------

class TestInvalidICmPossibilityCastPreflight(unittest.TestCase):
    """Reopened #101: discovery tools warn, but detect_casting_needs must
    reject the bad cast before run_module reaches runtime."""

    def _casting(self, code: str):
        from server.validators import detect_casting_needs

        return detect_casting_needs(code, casting_index=None)

    def _invalid_ic_poss_issues(self, result):
        return [
            i
            for i in result.get("casting_issues") or []
            if i.get("kind") == "invalid_icmpossibility_cast"
        ]

    def test_icmpossibility_on_infl_template_cast_alias_flags(self):
        code = (
            "from SIL.LCModel import IMoInflAffixTemplate, ICmPossibility\n"
            "def Main(project, report, modify):\n"
            "    t = IMoInflAffixTemplate(x)\n"
            "    nm = ICmPossibility(t).Name\n"
            "    report.Info(str(nm))\n"
        )
        result = self._casting(code)
        bad = self._invalid_ic_poss_issues(result)
        self.assertEqual(len(bad), 1, bad)
        self.assertEqual(bad[0]["severity"], "error")
        self.assertIn("NOT ICmPossibility", bad[0]["fix"])

    def test_icmpossibility_on_immo_morph_type_not_flagged(self):
        code = (
            "from SIL.LCModel import IMoMorphType, ICmPossibility\n"
            "def Main(project, report, modify):\n"
            "    mt = IMoMorphType(x)\n"
            "    nm = ICmPossibility(mt).Name\n"
            "    report.Info(str(nm))\n"
        )
        result = self._casting(code)
        self.assertEqual(self._invalid_ic_poss_issues(result), [])

    def test_inline_template_cast_to_icmpossibility_flags(self):
        code = (
            "from SIL.LCModel import IMoInflAffixTemplate, ICmPossibility\n"
            "def f(x):\n"
            "    return ICmPossibility(IMoInflAffixTemplate(x)).Name\n"
        )
        result = self._casting(code)
        self.assertEqual(len(self._invalid_ic_poss_issues(result)), 1)


class TestICmPossibilityProvenanceGate(unittest.TestCase):
    """Issue #101 B1: attribute and receiver-name provenance for ICmPossibility."""

    def _run(self, code: str):
        from server.validators import detect_casting_needs

        return detect_casting_needs(code, casting_index=None)

    def _invalid_ic_poss_issues(self, result):
        return [
            i
            for i in result.get("casting_issues") or []
            if i.get("kind") == "invalid_icmpossibility_cast"
        ]

    def test_inflection_class_ra_provenance_flags(self):
        code = "name = ICmPossibility(m.InflectionClassRA).Name\n"
        result = self._run(code)
        self.assertEqual(len(self._invalid_ic_poss_issues(result)), 1)

    def test_slot_receiver_name_flags(self):
        code = "name = ICmPossibility(slot).Name\n"
        result = self._run(code)
        self.assertEqual(len(self._invalid_ic_poss_issues(result)), 1)

    def test_morph_type_not_flagged(self):
        code = "name = ICmPossibility(morphType).Name\n"
        result = self._run(code)
        self.assertEqual(self._invalid_ic_poss_issues(result), [])

    def test_pos_not_flagged(self):
        code = "name = ICmPossibility(pos).Name\n"
        result = self._run(code)
        self.assertEqual(self._invalid_ic_poss_issues(result), [])

    def test_unrelated_attribute_not_flagged(self):
        code = "name = ICmPossibility(obj.Guid).Name\n"
        result = self._run(code)
        self.assertEqual(self._invalid_ic_poss_issues(result), [])

    def test_b1_injection_tier_not_none(self):
        code = (
            "for m in project.MorphRules.GetAllInstances():\n"
            "    name = ICmPossibility(m.InflectionClassRA).Name\n"
        )
        result = self._run(code)
        self.assertTrue(result["has_casting_issues"])
        self.assertNotEqual(result["injection_tier"], "none")


if __name__ == "__main__":
    unittest.main()
