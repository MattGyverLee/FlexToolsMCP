#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #69 -- Suggestion quality for both surfaces:
  - detect_unknown_attribute_error (runtime AttributeError path)
  - detect_invalid_project_chains  (preflight path)

Requirements exercised
----------------------
* LangProject -> suggests project.lp; NEVER PossibilityList(s) or ProjectSettings
* LexEntries -> LexEntry still caught (genuine typo)
* ReversalEntrie -> ReversalEntries still caught
* GetPOS on an Operations class -> GetPartOfSpeech (acronym still works)
* Random unrelated name -> no accessor named; points to discovery tools
* Property test: every suggestion has similarity >= _MIN_SUGGESTION_RATIO OR is alias-table
* Preflight must NOT reject the hasattr-fallback line from the issue
* Raw-handle aliases emit advisory (non-blocking) not a hard rejection
"""

import ast
import difflib
import unittest
from typing import List, Optional

import pytest

from server.constants import PROJECT_ACCESSOR_ALIASES, PROJECT_RAW_HANDLE_ALIASES
from server.validators import (
    _MIN_SUGGESTION_RATIO,
    _project_accessors,
    _suggest_attribute_matches,
    detect_invalid_project_chains,
    detect_unknown_attribute_error,
)


# ---------------------------------------------------------------------------
# Synthetic index (no real index file needed)
# ---------------------------------------------------------------------------

class _FakeIndex:
    """Minimal stand-in for APIIndex."""

    def __init__(self, accessors: List[str], ops_methods: Optional[dict] = None):
        entities = {
            "FLExProject": {
                "properties": [{"name": a} for a in accessors],
                "methods": [],
            }
        }
        for ops_class, methods in (ops_methods or {}).items():
            entities[ops_class] = {"methods": [{"name": m} for m in methods]}
        self.flexicon = {"entities": entities}


# An index that mirrors the original bug report conditions:
# PossibilityList(s) are present so the acronym fallback can fire, yet
# lp/lexDB are also there as real accessors.
_ISSUE_INDEX = _FakeIndex(
    accessors=[
        "lp", "lexDB", "project",
        "LexEntry", "Senses", "Example", "WritingSystem",
        "PossibilityLists", "PossibilityList",
        "PhonRules", "ReversalEntries", "POS",
    ],
    ops_methods={
        "LexEntryOperations": ["GetGloss", "GetLexemeForm", "GetAll", "GetAllSenses"],
        "POSOperations": ["GetAll", "GetPartOfSpeech", "GetName"],
    },
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _chain(code: str, idx=_ISSUE_INDEX) -> dict:
    return detect_invalid_project_chains(ast.parse(code), idx)


def _runtime_hint(attr: str, obj_type: str = "FLExProject", idx=_ISSUE_INDEX) -> dict:
    msg = f"'FLExProject' object has no attribute '{attr}'"
    if obj_type != "FLExProject":
        msg = f"'{obj_type}' object has no attribute '{attr}'"
    return detect_unknown_attribute_error(msg, idx)


# ---------------------------------------------------------------------------
# Table-driven: preflight surface
# ---------------------------------------------------------------------------

class TestPreflightSuggestionQuality(unittest.TestCase):
    """detect_invalid_project_chains must not surface wrong suggestions."""

    # --- LangProject / raw-handle aliases ---

    def test_langproject_hasattr_fallback_not_hard_rejected(self):
        """The exact line from the issue report must not cause has_invalid=True."""
        code = 'lp = project.lp if hasattr(project, "lp") else project.LangProject\n'
        result = _chain(code)
        self.assertFalse(
            result["has_invalid"],
            f"hasattr-guarded LangProject must not be a hard rejection; got {result}",
        )

    def test_langproject_bare_not_hard_rejected(self):
        """A standalone project.LangProject is NOT a hard rejection (advisory only)."""
        result = _chain("x = project.LangProject\n")
        self.assertFalse(result["has_invalid"])

    def test_langproject_advisory_emitted(self):
        """project.LangProject should emit an advisory pointing at 'lp'."""
        result = _chain("x = project.LangProject\n")
        advisory_issues = [i for i in result.get("issues", []) if i.get("kind") == "advisory"]
        self.assertEqual(len(advisory_issues), 1, result)
        self.assertIn("lp", advisory_issues[0]["did_you_mean"])

    def test_langproject_advisory_not_possibilitylist(self):
        """The advisory must NEVER suggest PossibilityList(s)."""
        result = _chain("x = project.LangProject\n")
        for issue in result.get("issues", []):
            for m in issue.get("did_you_mean", []):
                self.assertNotIn("PossibilityList", m,
                                 f"Advisory wrongly named {m}")

    def test_langproject_advisory_match_ratio_below_autorewrite(self):
        """Advisory match_ratio must be < 0.9 so auto-fix never rewrites it."""
        result = _chain("x = project.LangProject\n")
        for issue in result.get("issues", []):
            if issue.get("kind") == "advisory":
                self.assertLess(
                    issue["match_ratio"], 0.9,
                    "Raw-handle advisory must not trigger the >=0.9 auto-fix",
                )

    def test_lexdb_alias_advisory(self):
        """LexDb -> lexDB emits an advisory, not a hard rejection."""
        result = _chain("db = project.LexDb\n")
        self.assertFalse(result["has_invalid"])
        advisory_issues = [i for i in result.get("issues", []) if i.get("kind") == "advisory"]
        self.assertEqual(len(advisory_issues), 1)
        self.assertIn("lexDB", advisory_issues[0]["did_you_mean"])

    def test_lexdboa_alias_advisory(self):
        result = _chain("db = project.LexDbOA\n")
        self.assertFalse(result["has_invalid"])
        issues = [i for i in result.get("issues", []) if i.get("kind") == "advisory"]
        self.assertEqual(len(issues), 1)
        self.assertIn("lexDB", issues[0]["did_you_mean"])

    # --- Genuine typos still caught ---

    def test_lexentries_still_caught(self):
        """LexEntries -> LexEntry is a genuine high-confidence typo."""
        result = _chain("x = project.LexEntries\n")
        self.assertTrue(result["has_invalid"], result)
        self.assertIn("LexEntry", result["issues"][0]["did_you_mean"])

    def test_reversalentrie_still_caught(self):
        """ReversalEntrie -> ReversalEntries typo must be caught."""
        result = _chain("x = project.ReversalEntrie\n")
        self.assertTrue(result["has_invalid"], result)
        self.assertIn("ReversalEntries", result["issues"][0]["did_you_mean"])

    # --- Ratio floor on emitted issues ---

    def test_emitted_issues_meet_ratio_floor(self):
        """Every blocking issue that IS emitted must carry ratio >= _MIN_SUGGESTION_RATIO."""
        for code in (
            "x = project.LexEntries\n",
            "x = project.ReversalEntrie\n",
        ):
            result = _chain(code)
            for issue in result.get("issues", []):
                if issue.get("kind") != "advisory":
                    self.assertGreaterEqual(
                        issue.get("match_ratio", 0.0), _MIN_SUGGESTION_RATIO,
                        f"Issue in {code!r} has ratio below floor: {issue}",
                    )


# ---------------------------------------------------------------------------
# Table-driven: runtime surface (detect_unknown_attribute_error)
# ---------------------------------------------------------------------------

class TestRuntimeSuggestionQuality(unittest.TestCase):
    """detect_unknown_attribute_error must use alias tables first."""

    # --- LangProject handled by alias table ---

    def test_langproject_suggests_lp(self):
        result = _runtime_hint("LangProject")
        self.assertTrue(result["has_suggestion"])
        self.assertEqual(result["did_you_mean"], ["lp"])

    def test_langproject_never_possibilitylist(self):
        result = _runtime_hint("LangProject")
        for m in result.get("did_you_mean", []):
            self.assertNotIn("PossibilityList", m)

    def test_langproject_suggestion_text_mentions_lp(self):
        result = _runtime_hint("LangProject")
        self.assertIn("lp", result["suggestion"])

    def test_languageproject_suggests_lp(self):
        result = _runtime_hint("LanguageProject")
        self.assertTrue(result["has_suggestion"])
        self.assertEqual(result["did_you_mean"], ["lp"])

    def test_langproj_suggests_lp(self):
        result = _runtime_hint("LangProj")
        self.assertTrue(result["has_suggestion"])
        self.assertEqual(result["did_you_mean"], ["lp"])

    def test_lexdb_suggests_lexdb_accessor(self):
        result = _runtime_hint("LexDb")
        self.assertTrue(result["has_suggestion"])
        self.assertEqual(result["did_you_mean"], ["lexDB"])

    def test_lexdboa_suggests_lexdb_accessor(self):
        result = _runtime_hint("LexDbOA")
        self.assertTrue(result["has_suggestion"])
        self.assertEqual(result["did_you_mean"], ["lexDB"])

    # --- Genuine typos still resolved ---

    def test_lexentries_resolved_to_lexentry(self):
        result = _runtime_hint("LexEntries")
        self.assertTrue(result["has_suggestion"])
        self.assertIn("LexEntry", result["did_you_mean"])

    def test_reversalentrie_resolved(self):
        result = _runtime_hint("ReversalEntrie")
        self.assertTrue(result["has_suggestion"])
        self.assertIn("ReversalEntries", result["did_you_mean"])

    # --- Acronym fallback still works on Operations methods ---

    def test_getpos_on_operations_class_resolved(self):
        """GetPOS -> GetPartOfSpeech must still work via the acronym fallback."""
        msg = "'POSOperations' object has no attribute 'GetPOS'"
        result = detect_unknown_attribute_error(msg, _ISSUE_INDEX)
        self.assertTrue(result["has_suggestion"], result)
        self.assertIn("GetPartOfSpeech", result["did_you_mean"])

    # --- Completely random name -> discovery pointer, not a specific name ---

    def test_random_unrelated_name_points_to_discovery(self):
        """A completely unrelated name must not name a specific accessor."""
        result = _runtime_hint("XyzFooBarQux")
        # has_suggestion is True (we always have something to say)
        self.assertTrue(result["has_suggestion"])
        # But did_you_mean should be empty (no confident match)
        self.assertEqual(
            result.get("did_you_mean", []), [],
            "No confident match should name a specific accessor",
        )
        # The suggestion should point at discovery tools
        self.assertIn("flextools_get_object_api", result["suggestion"])

    # --- Floor property: every named suggestion is >= _MIN_SUGGESTION_RATIO
    #     OR comes from an alias table ---

    def test_every_named_suggestion_clears_floor_or_is_alias(self):
        """Property test: every project-accessor suggestion clears the floor.

        The floor applies only to project-scope suggestions (where the
        LangProject -> PossibilityLists false match occurred).  Operations
        method suggestions from the acronym path (GetPOS -> GetPartOfSpeech)
        legitimately score below the floor and are exempt.
        """
        all_aliases = set(PROJECT_ACCESSOR_ALIASES) | set(PROJECT_RAW_HANDLE_ALIASES)
        project_scope_attrs = [
            "LangProject", "LexEntries", "ReversalEntrie", "XyzFooBarQux",
            "LanguageProject", "LangProj", "LexDb", "LexDbOA",
            "LexSense", "PhonologicalRule",
        ]
        for attr in project_scope_attrs:
            result = _runtime_hint(attr)  # FLExProject scope
            if attr in all_aliases:
                continue  # alias-table results are always authoritative
            for m in result.get("did_you_mean", []):
                ratio = difflib.SequenceMatcher(None, attr.lower(), m.lower()).ratio()
                self.assertGreaterEqual(
                    ratio, _MIN_SUGGESTION_RATIO,
                    f"Project accessor suggestion {m!r} for {attr!r} has ratio "
                    f"{ratio:.3f} < {_MIN_SUGGESTION_RATIO}",
                )


# ---------------------------------------------------------------------------
# Preflight must NOT reject the hasattr-fallback from the issue report
# ---------------------------------------------------------------------------

class TestPreflightDoesNotBlockSafeHasattrGuard(unittest.TestCase):
    """The exact sample from the issue must pass preflight cleanly."""

    ISSUE_LINE = 'lp = project.lp if hasattr(project, "lp") else project.LangProject\n'

    def test_hasattr_fallback_has_invalid_false(self):
        result = _chain(self.ISSUE_LINE)
        self.assertFalse(result["has_invalid"],
                         f"Expected has_invalid=False, got: {result}")

    def test_lp_accessor_itself_is_valid(self):
        """project.lp must be accepted as a known accessor."""
        result = _chain("x = project.lp\n")
        self.assertFalse(result["has_invalid"], result)

    def test_lexdb_accessor_itself_is_valid(self):
        """project.lexDB must be accepted as a known accessor."""
        result = _chain("x = project.lexDB\n")
        self.assertFalse(result["has_invalid"], result)


# ---------------------------------------------------------------------------
# _suggest_attribute_matches acronym fix
# ---------------------------------------------------------------------------

class TestAcronymFallbackFixed(unittest.TestCase):
    """Direct unit tests for _suggest_attribute_matches fixing the LP/PLPL bug."""

    def test_langproject_upper_letters_not_in_possibilitylist(self):
        """The fixed acronym path must NOT match LangProject -> PossibilityList."""
        candidates = ["PossibilityLists", "PossibilityList", "LexEntry"]
        matches = _suggest_attribute_matches("LangProject", candidates, cutoff=0.7)
        for m in matches:
            self.assertNotIn("PossibilityList", m,
                             f"Acronym fallback wrongly matched {m}")

    def test_getpos_to_getpartofspeech_still_works(self):
        """GetPOS -> GetPartOfSpeech must still resolve via camelCase initials."""
        candidates = ["GetPartOfSpeech", "GetName", "GetAll"]
        matches = _suggest_attribute_matches("GetPOS", candidates, cutoff=0.7)
        self.assertIn("GetPartOfSpeech", matches,
                      "Acronym fallback must still resolve GetPOS -> GetPartOfSpeech")


# ---------------------------------------------------------------------------
# _project_accessors includes lp / project / lexDB even without an index
# ---------------------------------------------------------------------------

class TestProjectAccessorsFallbackIncludesPins(unittest.TestCase):
    """The no-index legacy fallback must include lp, project, and lexDB."""

    def test_lp_in_legacy_accessors(self):
        accessors = set(_project_accessors(None))
        self.assertIn("lp", accessors)

    def test_project_in_legacy_accessors(self):
        accessors = set(_project_accessors(None))
        self.assertIn("project", accessors)

    def test_lexdb_in_legacy_accessors(self):
        accessors = set(_project_accessors(None))
        self.assertIn("lexDB", accessors)

    def test_phantom_accessors_still_excluded(self):
        """Existing exclusions from issue #84 must still hold."""
        accessors = set(_project_accessors(None))
        for phantom in PROJECT_ACCESSOR_ALIASES:
            self.assertNotIn(phantom, accessors)


# ---------------------------------------------------------------------------
# Real shipped index smoke tests (skipped when index unavailable)
# ---------------------------------------------------------------------------

try:
    from flextoolsmcp.server import APIIndex, get_index_dir
    _REAL_INDEX = APIIndex.load(get_index_dir())
    _HAS_REAL_INDEX = True
except Exception:
    _REAL_INDEX = None
    _HAS_REAL_INDEX = False


@pytest.mark.skipif(not _HAS_REAL_INDEX, reason="real index not available")
class TestRealIndexSuggestionQuality:
    """Repeat key checks against the real shipped index."""

    def test_langproject_preflight_not_blocked(self):
        code = 'lp = project.lp if hasattr(project, "lp") else project.LangProject\n'
        result = detect_invalid_project_chains(ast.parse(code), _REAL_INDEX)
        assert not result["has_invalid"], result

    def test_langproject_runtime_suggests_lp(self):
        msg = "'FLExProject' object has no attribute 'LangProject'"
        result = detect_unknown_attribute_error(msg, _REAL_INDEX)
        assert result["has_suggestion"]
        assert "lp" in result["did_you_mean"]

    def test_lexentries_typo_caught(self):
        msg = "'FLExProject' object has no attribute 'LexEntries'"
        result = detect_unknown_attribute_error(msg, _REAL_INDEX)
        assert result["has_suggestion"]
        assert "LexEntry" in result["did_you_mean"]

    def test_all_named_suggestions_clear_floor(self):
        """Property: every suggestion from the real index meets the floor."""
        all_aliases = set(PROJECT_ACCESSOR_ALIASES) | set(PROJECT_RAW_HANDLE_ALIASES)
        for attr in ["LangProject", "LexEntries", "ReversalEntrie", "LexDb"]:
            msg = f"'FLExProject' object has no attribute '{attr}'"
            result = detect_unknown_attribute_error(msg, _REAL_INDEX)
            if attr in all_aliases:
                continue
            for m in result.get("did_you_mean", []):
                ratio = difflib.SequenceMatcher(None, attr.lower(), m.lower()).ratio()
                assert ratio >= _MIN_SUGGESTION_RATIO, (
                    f"Suggestion {m!r} for {attr!r} has ratio {ratio:.3f} < {_MIN_SUGGESTION_RATIO}"
                )


if __name__ == "__main__":
    unittest.main()
