#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #40 (B-1) / issue #97 Bug 2 (B-2 + B-4): the casting gate's
severity-aware decision, and branch-/assignment-aware variable typing.

B-1 (execution.py decision point): a casting issue set is only allowed to
proceed without rejecting when the run is READ-ONLY *and* every issue in
the set is warning-tier (index-derived lookup, never a known-pattern hit
or a genuine attribute typo). Any "error"-severity issue still hard-rejects,
and every WRITE-enabled run still hard-rejects at every severity. This is
GATE-LOCAL to the casting gate -- no other preflight gate is touched.

B-2/B-4 (validators.py variable typing): `if`/`elif`/`else` arms that cast
the SAME variable name to different interfaces must not conflate -- a
usage in one arm must never be attributed to a sibling arm's cast. An
already-cast variable (`wa = IWfiAnalysis(ana)`) must not be re-flagged.
"""

import ast
import asyncio
import json
import unittest

import pytest

from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server import kernel, project_discovery
from server.validators import (
    detect_casting_needs,
    detect_interface_attribute_typos,
    _is_multistring_value_member,
)


# ---------------------------------------------------------------------------
# Execution-level (handle_run_module) severity-decision tests
# ---------------------------------------------------------------------------

def _stub_execution_preflight(monkeypatch, tmp_path, *, detect_casting_needs=None,
                               detect_interface_attribute_typos=None):
    """Wire handle_run_module's dependencies so only the casting-gate
    severity decision under test runs with real logic; every other
    preflight gate and the subprocess launch itself are stubbed to "pass".
    Mirrors test_diagnostic_report_reconstruction.py's `_stub_execution_preflight`,
    extended far enough to reach an actual "proceeds" outcome (not just a
    reject), since B-1's whole point is that some scenarios no longer reject.
    """
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(
        execution_mod, "certify_script_readonly",
        lambda code, api_idx, tree: {
            "is_certified_readonly": True, "confidence": "high",
            "mutating_calls": [], "unprotected_liblcm_calls": [],
        },
    )
    if detect_casting_needs is not None:
        monkeypatch.setattr(execution_mod, "detect_casting_needs", detect_casting_needs)
    if detect_interface_attribute_typos is not None:
        monkeypatch.setattr(
            execution_mod, "detect_interface_attribute_typos", detect_interface_attribute_typos
        )

    async def fake_run_script_async(path, timeout_seconds=None):
        return {
            "stdout": "===FLEXTOOLS_RESULT_JSON===\n" + json.dumps({"success": True, "messages": []}),
            "stderr": "", "timeout": False, "returncode": 0,
        }
    monkeypatch.setattr(execution_mod, "run_script_async", fake_run_script_async)


def _no_typos(code_tree, api_idx):
    return {"has_typos": False, "issues": [], "suggestion": ""}


def _run(args, monkeypatch, tmp_path, **stub_kwargs):
    _stub_execution_preflight(monkeypatch, tmp_path, **stub_kwargs)
    result = asyncio.run(execution_mod.handle_run_module(args))
    return json.loads(result[0].text)


_BASE_ARGS = {
    "code": "print('hi')\n",
    "project_name": "TestProject",
    "auto_fix": False,
    "skip_module_check": True,
    "skip_api_check": True,
}


def _warning_issue():
    return {"property": "Foo", "line": 1, "severity": "warning", "fix": "cast it to IFoo"}


def _error_issue():
    return {"property": "HeadWord", "line": 1, "severity": "error", "fix": "cast it to ILexEntry"}


class TestSeverityDecision:
    def test_warning_tier_readonly_proceeds_with_warnings(self, monkeypatch, tmp_path):
        """All-warning-tier + read-only -> no reject; issues surface as
        non-blocking advisories in the `warnings` list instead."""
        def fake_detect_casting_needs(code, casting_index, code_tree):
            return {
                "has_casting_issues": True,
                "casting_issues": [_warning_issue()],
                "severity": "warning",
            }
        args = {**_BASE_ARGS, "write_enabled": False}
        payload = _run(
            args, monkeypatch, tmp_path,
            detect_casting_needs=fake_detect_casting_needs,
            detect_interface_attribute_typos=_no_typos,
        )
        assert payload.get("success") is True, payload
        assert "error_code" not in payload
        assert any("[casting]" in w for w in payload.get("warnings", [])), payload
        assert any("Foo" in w for w in payload.get("warnings", [])), payload

    def test_warning_tier_write_enabled_rejects(self, monkeypatch, tmp_path):
        """All-warning-tier but WRITE-enabled -> still hard-rejects. Every
        write run rejects at every severity, no exceptions."""
        def fake_detect_casting_needs(code, casting_index, code_tree):
            return {
                "has_casting_issues": True,
                "casting_issues": [_warning_issue()],
                "severity": "warning",
            }
        args = {**_BASE_ARGS, "write_enabled": True}
        payload = _run(
            args, monkeypatch, tmp_path,
            detect_casting_needs=fake_detect_casting_needs,
            detect_interface_attribute_typos=_no_typos,
        )
        assert payload.get("error_code") == "casting_issues_detected", payload

    def test_error_tier_readonly_still_rejects(self, monkeypatch, tmp_path):
        """A known-pattern ("error"-severity) issue still hard-rejects even
        on a read-only run."""
        def fake_detect_casting_needs(code, casting_index, code_tree):
            return {
                "has_casting_issues": True,
                "casting_issues": [_error_issue()],
                "severity": "error",
            }
        args = {**_BASE_ARGS, "write_enabled": False}
        payload = _run(
            args, monkeypatch, tmp_path,
            detect_casting_needs=fake_detect_casting_needs,
            detect_interface_attribute_typos=_no_typos,
        )
        assert payload.get("error_code") == "casting_issues_detected", payload

    def test_typo_issue_readonly_still_rejects(self, monkeypatch, tmp_path):
        """A genuine attribute typo (merged in from detect_interface_attribute_typos,
        forced to severity="error") still hard-rejects on a read-only run --
        it is a real error (the property exists nowhere), not a low-confidence
        guess."""
        def fake_detect_casting_needs(code, casting_index, code_tree):
            return {"has_casting_issues": False, "casting_issues": [], "severity": "none"}

        def fake_typos(code_tree, api_idx):
            return {
                "has_typos": True,
                "issues": [{
                    "kind": "interface_attribute_typo", "property": "EntriesOC",
                    "line": 1, "severity": "error",
                }],
                "suggestion": "did you mean Entries?",
            }
        args = {**_BASE_ARGS, "write_enabled": False}
        payload = _run(
            args, monkeypatch, tmp_path,
            detect_casting_needs=fake_detect_casting_needs,
            detect_interface_attribute_typos=fake_typos,
        )
        assert payload.get("error_code") == "casting_issues_detected", payload
        reported = {ci["property"] for ci in payload.get("casting_issues", [])}
        assert "EntriesOC" in reported, payload

    def test_no_issues_readonly_proceeds_clean(self, monkeypatch, tmp_path):
        """Sanity: no casting issues at all -> proceeds, no casting advisory
        in warnings."""
        def fake_detect_casting_needs(code, casting_index, code_tree):
            return {"has_casting_issues": False, "casting_issues": [], "severity": "none"}
        args = {**_BASE_ARGS, "write_enabled": False}
        payload = _run(
            args, monkeypatch, tmp_path,
            detect_casting_needs=fake_detect_casting_needs,
            detect_interface_attribute_typos=_no_typos,
        )
        assert payload.get("success") is True, payload
        assert not any("[casting]" in w for w in payload.get("warnings", [])), payload


# ---------------------------------------------------------------------------
# Validator-level (B-2 + B-4): branch-/assignment-aware variable typing
# ---------------------------------------------------------------------------

class FakeMSAIndex:
    """Real-shaped stand-in for #97 Bug 2's verbatim MSA repro: four
    concrete MSA interfaces, each with only ITS OWN property."""

    liblcm = {
        "entities": {
            "IMoStemMsa": {
                "properties": [{"name": "InflectionClassRA"}],
                "methods": [], "interfaces": ["IMoMorphSynAnalysis"],
            },
            "IMoInflAffMsa": {
                "properties": [{"name": "SlotsRC"}],
                "methods": [], "interfaces": ["IMoMorphSynAnalysis"],
            },
            "IMoDerivAffMsa": {
                "properties": [{"name": "FromPartOfSpeechRA"}, {"name": "ToPartOfSpeechRA"}],
                "methods": [], "interfaces": ["IMoMorphSynAnalysis"],
            },
            "IMoUnclassifiedAffixMsa": {
                "properties": [], "methods": [], "interfaces": ["IMoMorphSynAnalysis"],
            },
            "IMoMorphSynAnalysis": {"properties": [], "methods": [], "interfaces": []},
        }
    }
    flexicon = {}
    flexlibs_stable = {}


class TestBranchAwareVariableTyping(unittest.TestCase):
    def test_issue97_bug2_if_elif_branches_no_false_positive(self):
        """Verbatim shape from issue #97 Bug 2: four mutually exclusive
        if/elif branches cast the SAME variable name `m` to four different
        MSA interfaces. Each branch accesses a property that is valid ONLY
        on that branch's own cast target. None of the four may be flagged
        as a typo -- the branch-conflation bug attributed every earlier
        branch's usage to the LAST branch's interface (IMoUnclassifiedAffixMsa,
        which has none of these properties)."""
        code = (
            "def f(msa, cn):\n"
            "    if cn == \"MoStemMsa\":\n"
            "        m = IMoStemMsa(msa)\n"
            "        return m.InflectionClassRA\n"
            "    elif cn == \"MoInflAffMsa\":\n"
            "        m = IMoInflAffMsa(msa)\n"
            "        return m.SlotsRC\n"
            "    elif cn == \"MoDerivAffMsa\":\n"
            "        m = IMoDerivAffMsa(msa)\n"
            "        return m.FromPartOfSpeechRA\n"
            "    elif cn == \"MoUnclassifiedAffixMsa\":\n"
            "        m = IMoUnclassifiedAffixMsa(msa)\n"
        )
        tree = ast.parse(code)
        result = detect_interface_attribute_typos(tree, FakeMSAIndex())
        self.assertFalse(
            result["has_typos"],
            f"Branch-conflation false positive: {result['issues']}"
        )

    def test_already_cast_variable_not_reflagged(self):
        """#40 item 3: `wa = IWfiAnalysis(ana); wa.CategoryRA` must not be
        flagged -- the explicit cast on the prior line proves the type."""
        index = {
            "properties": {
                "CategoryRA": {
                    "defined_on": ["IWfiAnalysis"],
                    "requires_cast_from": ["ICmObject"],
                },
            },
            "polymorphic_collections": {},
        }
        code = (
            "from SIL.LCModel import IWfiAnalysis\n"
            "def f(ana):\n"
            "    wa = IWfiAnalysis(ana)\n"
            "    return wa.CategoryRA\n"
        )
        result = detect_casting_needs(code, index)
        flagged = {issue["property"] for issue in result["casting_issues"]}
        self.assertNotIn(
            "CategoryRA", flagged,
            f"CategoryRA must not re-flag after IWfiAnalysis(ana) cast; "
            f"got: {result['casting_issues']}"
        )

    def test_wrong_branch_cast_still_flags(self):
        """Safety guarantee via detect_casting_needs(): a branch whose OWN
        cast does NOT satisfy a property's `defined_on` must still flag --
        branch-awareness must not become a blanket suppression. Only the
        FIRST branch (wrong interface for SlotsRC) should flag; the SECOND
        branch (correct interface) must not."""
        index = {
            "properties": {
                "SlotsRC": {
                    "defined_on": ["IMoInflAffMsa"],
                    "requires_cast_from": ["ICmObject"],
                },
            },
            "polymorphic_collections": {},
        }
        code = (
            "def f(msa, cn):\n"
            "    if cn == \"MoStemMsa\":\n"
            "        m = IMoStemMsa(msa)\n"
            "        x = m.SlotsRC\n"
            "    elif cn == \"MoInflAffMsa\":\n"
            "        m = IMoInflAffMsa(msa)\n"
            "        y = m.SlotsRC\n"
        )
        result = detect_casting_needs(code, index)
        flagged_lines = [issue["line"] for issue in result["casting_issues"]]
        self.assertEqual(
            flagged_lines, [4],
            f"Only the IMoStemMsa (wrong-interface) branch on line 4 should "
            f"flag, not the IMoInflAffMsa (correct-interface) branch on "
            f"line 7; got: {result['casting_issues']}"
        )


class TestWhitelistedMembersNotFlagged(unittest.TestCase):
    """#40: universally-safe members never need a cast, regardless of
    receiver type or branch."""

    INDEX = {
        "properties": {
            "CategoryRA": {
                "defined_on": ["IWfiAnalysis"],
                "requires_cast_from": ["ICmObject"],
            },
        },
        "polymorphic_collections": {},
    }

    def _flagged(self, code):
        result = detect_casting_needs(code, self.INDEX)
        return {issue["property"] for issue in result["casting_issues"]}

    def test_guid(self):
        self.assertNotIn("Guid", self._flagged("def f(obj):\n    return obj.Guid\n"))

    def test_hvo(self):
        self.assertNotIn("Hvo", self._flagged("def f(obj):\n    return obj.Hvo\n"))

    def test_classid(self):
        self.assertNotIn("ClassID", self._flagged("def f(obj):\n    return obj.ClassID\n"))

    def test_classname(self):
        self.assertNotIn("ClassName", self._flagged("def f(obj):\n    return obj.ClassName\n"))

    def test_best_analysis_alternative(self):
        code = "def f(ms):\n    return ms.BestAnalysisAlternative.Text\n"
        self.assertNotIn("BestAnalysisAlternative", self._flagged(code))

    def test_best_vernacular_alternative(self):
        code = "def f(ms):\n    return ms.BestVernacularAlternative.Text\n"
        self.assertNotIn("BestVernacularAlternative", self._flagged(code))

    def test_is_multistring_value_member_helper(self):
        self.assertTrue(_is_multistring_value_member("BestAnalysisAlternative"))
        self.assertFalse(_is_multistring_value_member("CategoryRA"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
