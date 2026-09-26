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
from unittest.mock import MagicMock, patch


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
        # Import via the package-relative path used by the rest of this file
        # (server.handlers.api) so we never load server.py / mcp.Server -- the
        # installed mcp SDK no longer exposes Server.list_tools, which breaks
        # `from flextoolsmcp.server import APIIndex` in this environment.
        from server.handlers.api import handle_resolve_property

        mock_api = MagicMock()
        mock_api.liblcm = {"suffix_index": {"by_pythonic_name": {}}}
        mock_api.casting_index = {"properties": {}}
        with patch("server.handlers.api.get_api_index", return_value=mock_api), patch(
            "server.handlers.api.resolve_pythonic_property", return_value=[]
        ):
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
# Run-time cast gate (validators.detect_casting_needs static check)
# ---------------------------------------------------------------------------

class TestWrongICmPossibilityCastIssues(unittest.TestCase):
    """Issue #101 (run-time half): static detection of ICmPossibility(<expr>)
    where <expr> is provably a NOT_CMPOSSIBILITY type.

    All positive cases must have severity='error' and produce injection_tier
    != 'none' on the full detect_casting_needs result.

    A-series NOTE (out of scope for static checking):
    ``IMoInflAffixTemplate(t)`` where ``t`` came from
    ``MorphRuleOperations.GetAllAffixTemplates()`` / ``GetAllAffixTemplatesForPOS()``
    is NOT flagged here.  The cast TARGET matches the declared collection element
    type; the runtime failure is a wrapper/collection impurity (some FLEx versions
    return heterogeneous internal objects), NOT a statically wrong-target cast.
    We cannot prove statically that GetAllAffixTemplates returns a non-template
    object without runtime evidence -- flagging it would produce false positives
    on correct-looking casts to the very type the collection claims to hold.
    These cases are documented in _wrong_icmpossibility_cast_issues' docstring
    and left to runtime diagnostics.
    """

    def _run(self, code: str) -> dict:
        from server.validators import detect_casting_needs
        return detect_casting_needs(code, None)

    # --- Attribute provenance (Hit B1 shapes) ---

    def test_b1_inflectionclassra_flagged(self):
        """Hit B1: ICmPossibility(m.InflectionClassRA) -- InflectionClassRA
        returns IMoInflClass, which is NOT ICmPossibility."""
        code = "name = ICmPossibility(m.InflectionClassRA).Name\n"
        result = self._run(code)
        self.assertTrue(result["has_casting_issues"])
        issues = result["casting_issues"]
        self.assertTrue(
            any(i["severity"] == "error" and "ICmPossibility" in i["property"]
                for i in issues),
            f"Expected error-level ICmPossibility issue; got: {issues}",
        )

    def test_b1_defaultinflectionclassra_flagged(self):
        code = "name = ICmPossibility(pos.DefaultInflectionClassRA).Name\n"
        result = self._run(code)
        self.assertTrue(result["has_casting_issues"])
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertTrue(issues)
        self.assertEqual(issues[0]["severity"], "error")

    def test_b1_affixslotsoc_flagged(self):
        """AffixSlotsOC returns IMoInflAffixSlot -- NOT ICmPossibility."""
        code = "name = ICmPossibility(pos.AffixSlotsOC).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertTrue(issues, "AffixSlotsOC provenance should be flagged")
        self.assertEqual(issues[0]["severity"], "error")

    def test_b1_affixtemplates_os_flagged(self):
        """AffixTemplatesOS returns IMoInflAffixTemplate -- NOT ICmPossibility."""
        code = "name = ICmPossibility(pos.AffixTemplatesOS).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertTrue(issues, "AffixTemplatesOS provenance should be flagged")
        self.assertEqual(issues[0]["severity"], "error")

    def test_b1_slotsrc_flagged(self):
        code = "s = ICmPossibility(msa.SlotsRC).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertTrue(issues, "SlotsRC provenance should be flagged")

    def test_b1_templatera_flagged(self):
        code = "t = ICmPossibility(app.TemplateRA).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertTrue(issues, "TemplateRA provenance should be flagged")

    def test_b1_slotother_prefixslotsrs_flagged(self):
        code = "s = ICmPossibility(tmpl.PrefixSlotsRS).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertTrue(issues, "PrefixSlotsRS provenance should be flagged")

    # --- Receiver-name provenance ---

    def test_receiver_slot_flagged(self):
        code = "name = ICmPossibility(slot).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertTrue(issues, "'slot' receiver name should be flagged")
        self.assertEqual(issues[0]["severity"], "error")

    def test_receiver_template_flagged(self):
        code = "name = ICmPossibility(template).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertTrue(issues, "'template' receiver name should be flagged")

    def test_receiver_infl_class_flagged(self):
        code = "name = ICmPossibility(infl_class).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertTrue(issues, "'infl_class' receiver name should be flagged")

    def test_receiver_inflClass_flagged(self):
        code = "name = ICmPossibility(inflClass).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertTrue(issues, "'inflClass' receiver name should be flagged")

    def test_receiver_tmpl_flagged(self):
        code = "name = ICmPossibility(tmpl).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertTrue(issues, "'tmpl' receiver name should be flagged")

    # --- Negative cases ---

    def test_morph_type_not_flagged(self):
        """IMoMorphType IS ICmPossibility -- ICmPossibility(morphType) is correct."""
        code = "name = ICmPossibility(morphType).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertFalse(issues, "morphType is a valid ICmPossibility target; must not flag")

    def test_pos_not_flagged(self):
        """ICmPossibility(pos) is legitimate -- pos IS a possibility-list item."""
        code = "name = ICmPossibility(pos).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertFalse(issues, "pos is a legitimate ICmPossibility receiver; must not flag")

    def test_generic_variable_not_flagged(self):
        """A plain variable like 'obj' or 'item' is not in the heuristic list."""
        for var in ("obj", "item", "x", "entry", "sense"):
            with self.subTest(var=var):
                code = f"name = ICmPossibility({var}).Name\n"
                result = self._run(code)
                issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
                self.assertFalse(issues, f"'{var}' should not trigger ICmPossibility gate")

    def test_unrelated_attribute_not_flagged(self):
        """ICmPossibility(obj.Guid) -- Guid is not a NOT_CMPOSSIBILITY provenance attr."""
        code = "name = ICmPossibility(obj.Guid).Name\n"
        result = self._run(code)
        issues = [i for i in result["casting_issues"] if "ICmPossibility" in i["property"]]
        self.assertFalse(issues, "Guid provenance must not trigger the #101 gate")

    # --- injection_tier check ---

    def test_b1_injection_tier_not_none(self):
        """B1 hit must drive injection_tier != 'none'.

        The recurrence pattern from op-021047475-032 used a helper
        ``def nm(o): return ICmPossibility(o).Name`` called on InflectionClassRA.
        The DIRECT call form ``ICmPossibility(m.InflectionClassRA)`` is the
        statically catchable equivalent -- nm() wrapping is interprocedural
        and out of scope for static analysis.
        """
        code = (
            "for m in project.MorphRules.GetAllInstances():\n"
            "    name = ICmPossibility(m.InflectionClassRA).Name\n"
        )
        result = self._run(code)
        self.assertTrue(result["has_casting_issues"])
        self.assertNotEqual(
            result["injection_tier"], "none",
            "B1 hit must elevate injection_tier above 'none'",
        )

    # --- Provenance constant is shared (not copied) ---

    def test_provenance_set_imported_from_server_constants(self):
        """NOT_CMPOSSIBILITY_NAME_COLLISION in api.py and the provenance attrs
        in validators.py both come from server.constants -- not copied."""
        from server.constants import NOT_CMPOSSIBILITY_NAME_COLLISION as from_constants
        from server.handlers.api import NOT_CMPOSSIBILITY_NAME_COLLISION as from_api
        self.assertIs(from_constants, from_api,
                      "api.py must re-export from server.constants, not define its own copy")

    def test_receiver_map_has_correct_entries_for_slot_template_inflclass(self):
        """_RECEIVER_NAME_TO_INTERFACE maps slot/template/inflclass names to
        their correct interfaces, never to ICmPossibility."""
        from server.validators import _RECEIVER_NAME_TO_INTERFACE
        for name, iface in _RECEIVER_NAME_TO_INTERFACE.items():
            if name in ("slot", "affix_slot", "infl_slot", "slot_obj",
                        "template", "tmpl", "templ", "affix_template", "template_obj",
                        "infl_class", "inflection_class", "infl_cls", "inflClass",
                        "infl_class_obj"):
                self.assertNotEqual(
                    iface, "ICmPossibility",
                    f"Receiver '{name}' must not map to ICmPossibility (issue #101 b)",
                )
                self.assertIn(
                    iface, ("IMoInflAffixSlot", "IMoInflAffixTemplate", "IMoInflClass"),
                    f"Receiver '{name}' must map to a NOT_CMPOSSIBILITY type",
                )


if __name__ == "__main__":
    unittest.main()
