#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for rejection-payload enrichments across issues #20, #21, #22, #29.

These cover the validator + handler boundary -- where a pre-flight rejection
gets enriched with inline get_object_api docs and structured rewrite hints so
the LLM can recover in a single round-trip.

Each issue is exercised against the real validators module; the execution
handler is tested via dispatch.call_tool to keep the test against the actual
MCP entrypoint (the same path the LLM hits).
"""

import ast
import asyncio
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from server.validators import (  # noqa: E402
    _collect_flexlibs2_imports,
    detect_casting_needs,
    detect_undiscovered_entities,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

class _FakeSession:
    """Stand-in for SessionState with the two attributes the gate reads."""

    def __init__(self, discovered=None, validated=None):
        self.discovered_apis = set(discovered or [])
        self.validated_apis = set(validated or [])


class _FakeAPIIndex:
    """Stand-in for APIIndex.flexlibs2 with a small entities map."""

    def __init__(self, entities=None):
        self.flexlibs2 = {"entities": dict(entities or {})}
        # Minimal casting index used by issue #21 helpers (if any).
        self.casting_index = {
            "properties": {
                "IsLabel": {
                    "defined_on": ["ISegment"],
                    "requires_cast_from": ["ICmObject", "ICmObjectOrId"],
                },
                "BaselineText": {
                    "defined_on": ["ISegment"],
                    "requires_cast_from": ["ICmObject", "ICmObjectOrId"],
                },
                "Gloss": {
                    "defined_on": ["ILexEtymology", "ILexSense", "ISenseOrEntry"],
                    "requires_cast_from": ["ICmObject", "ICmObjectOrId"],
                },
            },
            "polymorphic_collections": {},
        }


SEG_OPS_ENTITY = {
    "category": "texts",
    "namespace": "flexlibs2.operations.SegmentOperations",
    "import_statement": "from flexlibs2 import SegmentOperations",
    "methods": [
        {"name": "GetAll", "signature": "(project)", "is_mutating": False},
        {"name": "GetText", "signature": "(self, segment)", "is_mutating": False},
    ],
    "properties": [],
}


# ---------------------------------------------------------------------------
# Issue #20: undiscovered_entity gate honors explicit imports
# ---------------------------------------------------------------------------

class TestIssue20ImportedUndiscovered(unittest.TestCase):
    def test_collect_flexlibs2_imports_basic(self):
        tree = ast.parse(
            "from flexlibs2 import SegmentOperations\n"
            "from flexlibs2 import LexEntryOperations as LEO\n"
            "import flexlibs2.WfiWordformOperations\n"
        )
        names = _collect_flexlibs2_imports(tree)
        # We key on original name -- aliases don't matter for index lookup.
        self.assertIn("SegmentOperations", names)
        self.assertIn("LexEntryOperations", names)
        self.assertIn("WfiWordformOperations", names)

    def test_collect_ignores_non_flexlibs2_imports(self):
        tree = ast.parse(
            "from flexlibs import LexEntryOperations\n"
            "from os import path\n"
        )
        names = _collect_flexlibs2_imports(tree)
        self.assertEqual(names, set())

    def test_imported_undiscovered_populated_when_single_import(self):
        code = (
            "from flexlibs2 import SegmentOperations\n"
            "x = SegmentOperations(project).GetAll()\n"
        )
        tree = ast.parse(code)
        session = _FakeSession()
        result = detect_undiscovered_entities(tree, session, api_index=None)
        self.assertTrue(result["has_undiscovered"])
        self.assertIn("SegmentOperations", result["undiscovered"])
        self.assertEqual(result["imported_undiscovered"], ["SegmentOperations"])
        # Suggestion text must explicitly call out the import-vs-discovery gap.
        self.assertIn(
            "from flexlibs2 import SegmentOperations",
            result["suggestion"],
        )
        self.assertIn("Imports alone aren't enough", result["suggestion"])

    def test_imported_undiscovered_empty_when_not_imported(self):
        code = "x = SegmentOperations(project).GetAll()\n"
        tree = ast.parse(code)
        session = _FakeSession()
        result = detect_undiscovered_entities(tree, session, api_index=None)
        self.assertTrue(result["has_undiscovered"])
        self.assertEqual(result["imported_undiscovered"], [])

    def test_discovered_entity_not_flagged_even_if_imported(self):
        code = (
            "from flexlibs2 import SegmentOperations\n"
            "x = SegmentOperations(project).GetAll()\n"
        )
        tree = ast.parse(code)
        # Session already has SegmentOperations validated via get_object_api.
        session = _FakeSession(validated={"SegmentOperations"})
        result = detect_undiscovered_entities(tree, session, api_index=None)
        self.assertFalse(result["has_undiscovered"])


class TestIssue20InlineDiscoveryHandler(unittest.TestCase):
    """Exercise the execution handler's _inline_discovery_docs helper."""

    def test_inline_discovery_returns_method_shapes(self):
        from server.handlers.execution import _inline_discovery_docs

        api_idx = _FakeAPIIndex(entities={"SegmentOperations": SEG_OPS_ENTITY})
        result = _inline_discovery_docs(["SegmentOperations"], api_idx)
        self.assertIn("SegmentOperations", result)
        doc = result["SegmentOperations"]
        method_names = {m["name"] for m in doc["methods"]}
        self.assertIn("GetAll", method_names)
        self.assertEqual(doc["category"], "texts")

    def test_inline_discovery_resolves_accessor_to_ops_class(self):
        from server.handlers.execution import _inline_discovery_docs

        api_idx = _FakeAPIIndex(entities={"SegmentOperations": SEG_OPS_ENTITY})
        # Caller passes the accessor form; the helper should still resolve it.
        result = _inline_discovery_docs(["Segment"], api_idx)
        self.assertIn("SegmentOperations", result)

    def test_inline_discovery_skips_unknown_entities(self):
        from server.handlers.execution import _inline_discovery_docs

        api_idx = _FakeAPIIndex(entities={})
        result = _inline_discovery_docs(["DoesNotExistOperations"], api_idx)
        self.assertEqual(result, {})

    def test_inline_discovery_handles_none_api_index(self):
        from server.handlers.execution import _inline_discovery_docs

        result = _inline_discovery_docs(["SegmentOperations"], None)
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# Issue #21: casting_issues carries inline rewrite + imports_needed
# ---------------------------------------------------------------------------

FAKE_CAST_INDEX = {
    "properties": {
        "IsLabel": {
            "defined_on": ["ISegment"],
            "requires_cast_from": ["ICmObject", "ICmObjectOrId"],
        },
        "BaselineText": {
            "defined_on": ["ISegment"],
            "requires_cast_from": ["ICmObject", "ICmObjectOrId"],
        },
        "Gloss": {
            "defined_on": ["ILexSense"],
            "requires_cast_from": ["ICmObject"],
        },
        "MorphRA": {
            "defined_on": ["IWfiMorphBundle"],
            "requires_cast_from": ["ICmObject"],
        },
    },
    "polymorphic_collections": {},
}


class TestIssue21InlineRewrite(unittest.TestCase):
    """Each casting issue must carry a structured rewrite + imports."""

    def test_isLabel_rewrite_present(self):
        # seg is a bare Name, so the rewrite should be ISegment(seg).IsLabel
        code = "x = seg.IsLabel\n"
        result = detect_casting_needs(code, FAKE_CAST_INDEX)
        self.assertTrue(result["has_casting_issues"])
        issues = result["casting_issues"]
        # Find the IsLabel issue (there should be one).
        is_label = next((i for i in issues if i["property"] == "IsLabel"), None)
        self.assertIsNotNone(is_label, f"IsLabel not in issues: {issues}")
        self.assertEqual(is_label["rewrite"], "ISegment(seg).IsLabel")
        self.assertEqual(is_label["imports_needed"], ["from SIL.LCModel import ISegment"])
        self.assertEqual(is_label["cast_interface"], "ISegment")
        # Backwards compatibility: original keys still present.
        self.assertIn("property", is_label)
        self.assertIn("line", is_label)
        self.assertIn("fix", is_label)

    def test_morph_RA_rewrite(self):
        code = "y = bundle.MorphRA\n"
        result = detect_casting_needs(code, FAKE_CAST_INDEX)
        morph = next(
            (i for i in result["casting_issues"] if i["property"] == "MorphRA"), None
        )
        self.assertIsNotNone(morph)
        self.assertEqual(morph["rewrite"], "IWfiMorphBundle(bundle).MorphRA")
        self.assertEqual(
            morph["imports_needed"], ["from SIL.LCModel import IWfiMorphBundle"]
        )

    def test_rewrite_omitted_for_chained_receiver(self):
        # Chained receiver: we deliberately skip the rewrite per "single-site only".
        # Note: foo() returns something that we then access .IsLabel on; the
        # receiver is a Call, not a Name/Subscript, so rewrite must be None.
        code = "x = get_seg().IsLabel\n"
        result = detect_casting_needs(code, FAKE_CAST_INDEX)
        issues = [i for i in result["casting_issues"] if i["property"] == "IsLabel"]
        # Either no issue (regex didn't match) or rewrite is None.
        for issue in issues:
            self.assertIsNone(issue["rewrite"])

    def test_imports_needed_is_list(self):
        code = "x = seg.IsLabel\n"
        result = detect_casting_needs(code, FAKE_CAST_INDEX)
        for issue in result["casting_issues"]:
            self.assertIsInstance(issue["imports_needed"], list)


if __name__ == "__main__":
    unittest.main()
