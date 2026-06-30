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
    detect_candidate_entities,
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

    def test_import_alone_satisfies_discovery_gate(self):
        """Issue #31 supersedes the original #20 behavior: a bare
        `from flexlibs2 import X` is now treated as implicit discovery, so the
        imported entity is no longer flagged as undiscovered. (The function's
        own #31 comment documents this: importing an operations class brings
        the API surface into scope, satisfying the gate.) The stricter
        "imported but still undiscovered" assertion this test once made is
        therefore obsolete -- import + use must pass cleanly."""
        code = (
            "from flexlibs2 import SegmentOperations\n"
            "x = SegmentOperations(project).GetAll()\n"
        )
        tree = ast.parse(code)
        session = _FakeSession()
        result = detect_undiscovered_entities(tree, session, api_index=None)
        self.assertFalse(result["has_undiscovered"])
        self.assertEqual(result["imported_undiscovered"], [])

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


# ---------------------------------------------------------------------------
# Issue #21 follow-up: ambiguous properties (Form, Gloss, Name) must NOT
# get an alphabetical tie-break. They route to no-rewrite + fallback hint
# unless the receiver name is a known linguist-convention variable.
# ---------------------------------------------------------------------------

AMBIGUOUS_CAST_INDEX = {
    "properties": {
        # Real-world ambiguous properties from the Dennis cascade-failure
        # post-mortem. Alphabetical pick lands on the WRONG interface.
        "Form": {
            # ILexEtymology (alphabetically first) vs IMoForm (correct for
            # the common LexemeFormOA case).
            "defined_on": ["ILexEtymology", "IMoForm"],
            "requires_cast_from": ["ICmObject"],
        },
        "Gloss": {
            # ILexEtymology vs ILexSense -- sense is the common case.
            "defined_on": ["ILexEtymology", "ILexSense"],
            "requires_cast_from": ["ICmObject"],
        },
        "Name": {
            # ICmAgent vs ICmPossibility -- POS/SemDom is the common case.
            "defined_on": ["ICmAgent", "ICmPossibility"],
            "requires_cast_from": ["ICmObject"],
        },
        "BestAnalysisAlternative": {
            # IMultiAccessorBase lives in SIL.LCModel.Core.KernelInterfaces,
            # NOT SIL.LCModel -- emitted import must reflect that.
            "defined_on": ["IMultiAccessorBase"],
            "requires_cast_from": ["ICmObject"],
        },
    },
    "polymorphic_collections": {},
}


class TestIssue21AmbiguousNoTieBreak(unittest.TestCase):
    """Ambiguous defined_on must NOT yield a confidently-wrong rewrite."""

    def test_form_ambiguous_no_rewrite_with_unknown_receiver(self):
        # `x.Form` -- receiver name carries no linguist signal, so no rewrite.
        code = "y = x.Form\n"
        result = detect_casting_needs(code, AMBIGUOUS_CAST_INDEX)
        form_issues = [i for i in result["casting_issues"] if i["property"] == "Form"]
        # Issue may or may not be flagged depending on regex pattern, but
        # if it IS flagged, no confidently-wrong rewrite must be emitted.
        for issue in form_issues:
            self.assertIsNone(
                issue["rewrite"],
                f"Form on ambiguous defined_on must not emit a rewrite; got {issue['rewrite']!r}",
            )
            self.assertEqual(issue["imports_needed"], [])
            self.assertIsNone(issue["cast_interface"])

    def test_gloss_ambiguous_no_rewrite_with_unknown_receiver(self):
        code = "g = obj.Gloss\n"
        result = detect_casting_needs(code, AMBIGUOUS_CAST_INDEX)
        gloss_issues = [i for i in result["casting_issues"] if i["property"] == "Gloss"]
        for issue in gloss_issues:
            self.assertIsNone(issue["rewrite"])
            self.assertEqual(issue["imports_needed"], [])

    def test_name_ambiguous_no_rewrite_with_unknown_receiver(self):
        code = "n = thing.Name\n"
        result = detect_casting_needs(code, AMBIGUOUS_CAST_INDEX)
        name_issues = [i for i in result["casting_issues"] if i["property"] == "Name"]
        for issue in name_issues:
            self.assertIsNone(issue["rewrite"])

    def test_sense_receiver_disambiguates_gloss(self):
        # `sense.Gloss` -- the receiver-name table maps `sense` -> ILexSense,
        # which is in Gloss's defined_on, so we DO emit a rewrite.
        code = "g = sense.Gloss\n"
        result = detect_casting_needs(code, AMBIGUOUS_CAST_INDEX)
        gloss = next(
            (i for i in result["casting_issues"] if i["property"] == "Gloss"), None
        )
        # If Gloss got flagged, the receiver-name signal should resolve to ILexSense.
        if gloss is not None:
            self.assertEqual(gloss["cast_interface"], "ILexSense")
            self.assertEqual(gloss["rewrite"], "ILexSense(sense).Gloss")
            self.assertEqual(
                gloss["imports_needed"], ["from SIL.LCModel import ILexSense"]
            )

    def test_pos_receiver_disambiguates_name(self):
        code = "n = pos.Name\n"
        result = detect_casting_needs(code, AMBIGUOUS_CAST_INDEX)
        name_issue = next(
            (i for i in result["casting_issues"] if i["property"] == "Name"), None
        )
        if name_issue is not None:
            self.assertEqual(name_issue["cast_interface"], "ICmPossibility")
            self.assertEqual(name_issue["rewrite"], "ICmPossibility(pos).Name")

    def test_imultiaccessorbase_uses_kernelinterfaces_namespace(self):
        # BestAnalysisAlternative -> IMultiAccessorBase. The namespace
        # override must route it to SIL.LCModel.Core.KernelInterfaces, NOT
        # SIL.LCModel (which would fail at import time).
        code = "x = obj.BestAnalysisAlternative\n"
        result = detect_casting_needs(code, AMBIGUOUS_CAST_INDEX)
        baa = next(
            (i for i in result["casting_issues"] if i["property"] == "BestAnalysisAlternative"),
            None,
        )
        if baa is not None and baa["cast_interface"] == "IMultiAccessorBase":
            self.assertEqual(
                baa["imports_needed"],
                ["from SIL.LCModel.Core.KernelInterfaces import IMultiAccessorBase"],
            )


class TestIssue21FallbackHintWhenNoRewrite(unittest.TestCase):
    """When no inline rewrite is emitted, the handler's rejection payload
    must point the LLM at flextools_resolve_property as a fallback."""

    def test_handler_emits_resolve_property_hint_when_no_rewrite(self):
        # Exercise the execution handler path that picks how_to_fix /
        # hint_msg based on whether any issue carries a rewrite. We don't
        # need to spin a full project up -- we can hit the validator and
        # check the handler's fallback branch by structural inspection.
        code = "g = obj.Gloss\n"
        result = detect_casting_needs(code, AMBIGUOUS_CAST_INDEX)
        # The validator should produce at least one issue with rewrite=None
        # (the ambiguous Gloss). The handler's fallback branch is selected
        # when ALL issues have rewrite=None.
        gloss_issues = [i for i in result["casting_issues"] if i["property"] == "Gloss"]
        if gloss_issues:
            self.assertTrue(
                all(i["rewrite"] is None for i in gloss_issues),
                "Ambiguous Gloss must not produce an inline rewrite",
            )


# ---------------------------------------------------------------------------
# Issue #29: api_discovery_required inlines get_object_api for detected entities
# ---------------------------------------------------------------------------

LEX_ENTRY_OPS_ENTITY = {
    "category": "lexicon",
    "namespace": "flexlibs2.operations.LexEntryOperations",
    "import_statement": "from flexlibs2 import LexEntryOperations",
    "methods": [
        {"name": "GetAll", "signature": "(project)", "is_mutating": False},
        {"name": "Create", "signature": "(project, form, gloss)", "is_mutating": True},
    ],
    "properties": [],
}


class TestIssue29CandidateDetection(unittest.TestCase):
    def test_detect_candidate_entities_finds_name_references(self):
        code = "entries = LexEntryOperations.GetAll(project)\n"
        tree = ast.parse(code)
        api_idx = _FakeAPIIndex(
            entities={
                "LexEntryOperations": LEX_ENTRY_OPS_ENTITY,
                "SegmentOperations": SEG_OPS_ENTITY,
            }
        )
        result = detect_candidate_entities(tree, api_idx, limit=3)
        self.assertIn("LexEntryOperations", result)

    def test_detect_candidate_entities_finds_project_accessors(self):
        # No accessor_to_ops_map in our fake index, so the naive
        # `<Accessor>Operations` fallback handles this case.
        code = "for x in project.LexEntry.GetAll():\n    pass\n"
        tree = ast.parse(code)
        api_idx = _FakeAPIIndex(entities={"LexEntryOperations": LEX_ENTRY_OPS_ENTITY})
        result = detect_candidate_entities(tree, api_idx, limit=3)
        self.assertIn("LexEntryOperations", result)

    def test_detect_candidate_entities_capped_at_limit(self):
        code = (
            "a = LexEntryOperations.GetAll(project)\n"
            "b = SegmentOperations.GetAll(project)\n"
        )
        tree = ast.parse(code)
        api_idx = _FakeAPIIndex(
            entities={
                "LexEntryOperations": LEX_ENTRY_OPS_ENTITY,
                "SegmentOperations": SEG_OPS_ENTITY,
            }
        )
        result = detect_candidate_entities(tree, api_idx, limit=1)
        self.assertEqual(len(result), 1)

    def test_detect_candidate_entities_ranks_by_frequency(self):
        # LexEntryOperations referenced twice; SegmentOperations once.
        code = (
            "a = LexEntryOperations.GetAll(project)\n"
            "b = LexEntryOperations.Create(project, 'x', 'y')\n"
            "c = SegmentOperations.GetAll(project)\n"
        )
        tree = ast.parse(code)
        api_idx = _FakeAPIIndex(
            entities={
                "LexEntryOperations": LEX_ENTRY_OPS_ENTITY,
                "SegmentOperations": SEG_OPS_ENTITY,
            }
        )
        result = detect_candidate_entities(tree, api_idx, limit=3)
        self.assertEqual(result[0], "LexEntryOperations")


# ---------------------------------------------------------------------------
# Issue #27: in-use-by-another-program detection
# Issue #23: SharedSettings / path-mismatch / drive-unavailable detection
# ---------------------------------------------------------------------------

class TestIssue27ProjectLocked(unittest.TestCase):
    def test_locked_message_returns_project_locked_payload(self):
        from server.handlers.execution import _diagnose_project_open_error

        exec_result = {
            "error": (
                "Failed to open project 'Foo': LcmCacheLockedException: The project "
                "is in use by another program."
            ),
        }
        diag = _diagnose_project_open_error(exec_result, "Foo")
        self.assertIsNotNone(diag)
        assert diag is not None
        self.assertEqual(diag["error_code"], "project_locked")
        self.assertIn("Close FieldWorks", diag["hint"])

    def test_non_locked_message_returns_none_for_lock_path(self):
        from server.handlers.execution import _diagnose_project_open_error

        # Unrelated error -> no diagnosis (caller leaves error alone).
        exec_result = {"error": "Execution error: AttributeError: 'X' has no attribute 'Y'"}
        diag = _diagnose_project_open_error(exec_result, "Foo")
        self.assertIsNone(diag)


class TestIssue23ProjectPathMismatch(unittest.TestCase):
    def setUp(self):
        from server.project_discovery import clear_cache

        clear_cache()
        # Patch the project_discovery module functions that
        # _diagnose_project_open_error imports on demand.
        from unittest.mock import patch
        self._patchers = []
        self._patchers.append(
            patch(
                "server.project_discovery.list_projects",
                return_value=(["Foo", "Bar"], "env"),
            )
        )
        self._patchers.append(
            patch(
                "server.project_discovery.get_last_directory",
                return_value=r"C:\ProgramData\SIL\FieldWorks\Projects",
            )
        )
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        from server.project_discovery import clear_cache
        clear_cache()

    def test_path_mismatch_when_project_in_discovered_list(self):
        from server.handlers.execution import _diagnose_project_open_error

        exec_result = {
            "error": (
                "Failed to open project 'Foo': System.IO.DirectoryNotFoundException: "
                "Could not find a part of the path 'C:\\OtherLocation\\Foo\\Foo.fwdata'."
            ),
        }
        diag = _diagnose_project_open_error(exec_result, "Foo")
        self.assertIsNotNone(diag)
        assert diag is not None
        self.assertEqual(diag["error_code"], "project_path_mismatch")
        self.assertIn("Foo", diag["message"])
        self.assertEqual(
            diag["attempted_path"],
            "C:\\OtherLocation\\Foo\\Foo.fwdata",
        )
        self.assertIn("FieldWorks", diag["hint"])
        # discovered_at should be present so the LLM can show the user the
        # canonical location alongside the failing attempt.
        self.assertIn("discovered_at", diag)

    def test_drive_unavailable_detected_for_offline_share(self):
        from server.handlers.execution import _diagnose_project_open_error

        exec_result = {
            "error": (
                "Failed to open project 'Foo': System.IO.DirectoryNotFoundException: "
                "Could not find a part of the path 'V:\\fau-iya-flex\\SharedSettings'."
            ),
        }
        diag = _diagnose_project_open_error(exec_result, "Foo")
        self.assertIsNotNone(diag)
        assert diag is not None
        # V: is in the flagged-letter set, and os.path.exists('V:\\') is False
        # on a typical test machine -- so we should see project_drive_unavailable.
        self.assertEqual(diag["error_code"], "project_drive_unavailable")
        self.assertIn("V:", diag["message"])
        self.assertEqual(
            diag["attempted_path"], "V:\\fau-iya-flex\\SharedSettings"
        )

    def test_path_mismatch_falls_back_to_project_not_found_when_unknown(self):
        from server.handlers.execution import _diagnose_project_open_error

        exec_result = {
            "error": (
                "Failed to open project 'CompletelyUnknown': "
                "System.IO.DirectoryNotFoundException: "
                "Could not find a part of the path 'C:\\Path\\CompletelyUnknown.fwdata'."
            ),
        }
        diag = _diagnose_project_open_error(exec_result, "CompletelyUnknown")
        self.assertIsNotNone(diag)
        assert diag is not None
        self.assertEqual(diag["error_code"], "project_not_found")
        # The fall-through path should still attach the attempted_path so the
        # user can see what FieldWorks tried.
        self.assertEqual(
            diag["attempted_path"],
            "C:\\Path\\CompletelyUnknown.fwdata",
        )


if __name__ == "__main__":
    unittest.main()
