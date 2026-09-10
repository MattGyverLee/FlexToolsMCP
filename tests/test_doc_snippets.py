#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The gate for code that lives inside text (scripts/check_doc_snippets.py).

Two halves, and the second matters as much as the first:

1. The corpus is clean -- no repo-owned markdown fence, template, recipe,
   worked example or see_also reference names a flexicon API that does not
   exist, refuses, or takes different arguments.

2. The checker still has teeth. A gate that silently stops detecting is worse
   than no gate, because the green run is read as evidence. Each planted
   defect below is one this check has already caught for real:
   `ReversalOperations` (CLAUDE.md), `AddInputSegment` (worked example),
   `SetLeftContext` (same example, and invisible to any existence-only check
   because the name is still there -- it just always raises).

This test is the reason the check runs at all in CI: the failure mode is not
"someone edited a doc", it is "refresh.py pulled a new flexicon and the prose
stayed behind", which no doc-file trigger would ever fire on.
"""

import json
import os
import sys

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import check_doc_snippets as checker  # noqa: E402


@pytest.fixture(scope="module")
def api():
    return checker.Api(checker.find_index())


def _check(code, api, **kwargs):
    return checker.check_snippet(checker.Snippet("md", "test", code, **kwargs), api)


def _kinds(findings):
    return {f["kind"] for f in findings}


# ---------------------------------------------------------------------------
# 1. The corpus is clean
# ---------------------------------------------------------------------------

def test_repo_owned_snippets_have_no_api_findings():
    """Every code claim the MCP teaches from resolves against the index."""
    _api, _snippets, findings = checker.run(include_upstream=False)
    blocking = [f for f in findings if f["surface"] in checker.BLOCKING_SURFACES]
    assert not blocking, "doc snippets reference APIs that do not exist:\n" + "\n".join(
        "  [%s] %s:%s  %s" % (f["kind"], f["where"], f["line"], f["detail"])
        for f in blocking
    )


def test_every_surface_is_actually_being_scanned(api):
    """Guards against a silent collector break emptying a whole surface."""
    snippets = checker.collect_snippets(api)
    counts = {}
    for snippet in snippets:
        counts[snippet.surface] = counts.get(snippet.surface, 0) + 1
    for surface in ("md", "template", "recipe", "worked", "pycode"):
        assert counts.get(surface, 0) > 0, "surface %r collected nothing" % surface


def test_upstream_docstrings_are_not_scanned_by_default(api):
    """flexicon gates its own docstrings at source, against the library
    rather than a generated index. Checking the same text twice here would
    be the weaker of two duplicate checks."""
    default = checker.collect_snippets(api)
    assert not [s for s in default if s.surface == "docstring"]
    on_demand = checker.collect_snippets(api, include_upstream=True)
    assert [s for s in on_demand if s.surface == "docstring"], (
        "the cross-check path must still be able to reach upstream examples"
    )


# ---------------------------------------------------------------------------
# 2. The checker still has teeth
# ---------------------------------------------------------------------------

def test_catches_import_of_removed_symbol(api):
    """The real CLAUDE.md defect: flexicon has ReversalIndexOperations."""
    findings = _check("from flexicon import ReversalOperations\n", api)
    assert "bad-import" in _kinds(findings)


def test_accepts_the_real_symbol(api):
    findings = _check("from flexicon import ReversalIndexOperations\n", api)
    assert not findings


def test_catches_unknown_method(api):
    """The real worked-example defect."""
    findings = _check("project.PhonRules.AddInputSegment(rule, seg)\n", api)
    assert "unknown-method" in _kinds(findings)


def test_catches_method_that_exists_but_always_refuses(api):
    """Existence checking alone cannot see this class of rot.

    SetLeftContext is still on PhonologicalRuleOperations; it raises
    NotImplementedError on every call (flexicon issue #142).
    """
    findings = _check("project.PhonRules.SetLeftContext(rule, ctx)\n", api)
    assert "refusing-method" in _kinds(findings)


def test_catches_unknown_accessor(api):
    findings = _check("project.LexSense.GetGloss(sense)\n", api)
    assert "unknown-accessor" in _kinds(findings)


def test_accepts_the_aliased_accessor(api):
    """project.Senses is the real name behind the LexSense shorthand."""
    findings = _check("project.Senses.GetGloss(sense)\n", api)
    assert not findings


def test_catches_wrong_argument_count(api):
    findings = _check('project.LexEntry.Create()\n', api)
    assert "arity" in _kinds(findings)


def test_catches_unparseable_snippet(api):
    findings = _check("if modifyAllowed\n    pass\n", api)
    assert "syntax" in _kinds(findings)


# ---------------------------------------------------------------------------
# 3. And does not cry wolf
# ---------------------------------------------------------------------------

def test_inherited_members_resolve_through_base_classes(api):
    """Sort/MoveUp live on BaseOperations; without MRO walking these are ~80
    phantom failures across the corpus."""
    findings = _check("project.Senses.MoveUp(entry, sense)\nproject.Senses.Sort(entry)\n", api)
    assert not findings


def test_flavor_is_taken_from_the_snippet(api):
    """project.LexAllEntries is right in flexlibs-stable, wrong in flexicon."""
    code = "entry = project.LexAllEntries()[0]\n"
    assert _kinds(_check(code, api)) == {"unknown-accessor"}
    assert not _check(code, api, flavor="flexlibs_stable")


def test_elided_calls_do_not_trip_arity(api):
    """`Create(...)` in prose is an illustration, not a call with one arg."""
    assert not _check("project.Senses.Create(...)\n", api)


def test_documented_internals_are_not_api_claims(api):
    assert not _check("project._cache.CreateObject(x)\n", api)


def test_worklist_resolves_findings_to_flexicon_source_locations(api, tmp_path):
    """The report is only actionable if it says which file and line to open.

    Findings are keyed by index entity ("FLExProject.Paragraphs"); whoever
    fixes them works in the flexicon repo, so the worklist resolves each one
    to a repo-relative path and the enclosing def's line number.
    """
    _api, _snippets, findings = checker.run(include_upstream=True)
    md_path, json_path, count = checker.write_worklist(
        api, findings, str(tmp_path / "worklist.md")
    )
    assert count > 0
    assert os.path.exists(md_path) and os.path.exists(json_path)

    with open(json_path, encoding="utf-8") as fh:
        payload = json.load(fh)
    rows = payload["findings"]
    assert rows

    located = [r for r in rows if r["file"].startswith("flexicon/") and r["def_line"]]
    if checker._flexicon_source_root() is None:
        pytest.skip("flexicon not installed: source locations cannot be resolved")
    assert located, "no finding resolved to a flexicon source file and line"
    # internal receivers are their own repair, not an accessor rename
    assert any(r["kind"] == "internal-leak" for r in rows)


def test_deprecated_alias_accessors_are_valid(api):
    """flexicon installs 46 singular/plural aliases onto FLExProject at
    import time (issue #200). They are absent from the index property list
    but they are real: `project.Sense.GetGloss(s)` runs. Calling them typos
    is the same false-failure class as the pre-commit degradation."""
    if not api.aliases:
        pytest.skip("alias table unavailable: flexicon not importable")
    assert not _check("project.Sense.GetGloss(sense)\n", api)


def test_member_checking_continues_through_an_alias(api):
    if not api.aliases:
        pytest.skip("alias table unavailable: flexicon not importable")
    assert "unknown-method" in _kinds(_check("project.Sense.GetGlosss(s)\n", api))


def test_prose_claims_in_our_own_comments_are_checked(api):
    """A comment naming a method that does not exist is rot like any other."""
    findings = checker.prose_findings(api)
    assert isinstance(findings, list)  # runs clean today; shape is the contract


def test_prose_ignores_bare_accessor_mentions(api, tmp_path, monkeypatch):
    """`project.LexSense` appears throughout validators.py on purpose -- it is
    the alias they exist to reject. Only two-segment claims are judged."""
    module = tmp_path / "sample.py"
    module.write_text(
        "# project.LexSense is not a real accessor\n"
        "# from flexicon import XOperations means any Operations class\n"
        "# project.Senses.GetGlosss(s) is a genuine typo\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "_pycode_files",
                        lambda: [(str(module), "sample.py")])
    findings = checker.prose_findings(api)
    kinds = [f["kind"] for f in findings]
    assert kinds == ["unknown-method"], findings
    assert "GetGlosss" in findings[0]["detail"]


def test_prose_opt_out_marker_is_honoured(api, tmp_path, monkeypatch):
    module = tmp_path / "sample.py"
    module.write_text(
        "# project.Senses.GetGlosss(s)  # doc-check: ignore\n", encoding="utf-8")
    monkeypatch.setattr(checker, "_pycode_files",
                        lambda: [(str(module), "sample.py")])
    assert not checker.prose_findings(api)


def test_refuses_to_run_with_a_narrowed_ground_truth(monkeypatch):
    """Exit 2 (refuse), never exit 1 (fail), when the check cannot see enough.

    pre-commit's isolated venv has no flextoolsmcp/pyflexicon, so the accessor
    universe collapsed to the index's under-enumerated property list and 13
    perfectly valid names (project.Text, project.Example, ...) were reported
    as typos. A gate that fails on valid code teaches people to bypass it.
    """
    monkeypatch.setitem(sys.modules, "flextoolsmcp.server.constants", None)
    with pytest.raises(checker.DegradedCheck):
        checker.Api(checker.find_index())


def test_helper_imports_are_not_judged_without_a_live_flexicon(api, monkeypatch):
    """Index-only mode must not invent verdicts it has no basis for.

    The index enumerates classes, not module-level helpers, so with no
    flexicon installed `cast_to_concrete` is unverifiable -- and reporting it
    as a bad import (which is what pre-commit's isolated venv produced) is a
    false failure. Operations-class names stay checkable either way.
    """
    monkeypatch.setattr(api, "live", None)
    assert not _check("from flexicon import cast_to_concrete\n", api)
    assert "bad-import" in _kinds(_check("from flexicon import ReversalOperations\n", api))


def test_ignore_marker_skips_the_block(api):
    findings = _check("from flexicon import ReversalOperations\n", api, ignored=True)
    assert not findings
