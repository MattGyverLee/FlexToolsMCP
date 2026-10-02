#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #352: `if modifyAllowed and <cond>:` is a write guard; `or` is not.

Also covers the sibling found by the pattern audit: the Compare branch of
`_is_write_enabled_check` accepted ANY comparison mentioning `modifyAllowed`
or `project.writeEnabled`, so `if modifyAllowed == False:` certified the
write in its body as protected.
"""

import pytest

from flextoolsmcp.server.validators import (
    certify_script_readonly,
    find_protected_ranges,
)

_CREATE = "    project.LexEntry.Create('x', 'stem')\n"


def _certified(code):
    return certify_script_readonly(code, api_index=None)["is_certified_readonly"]


class TestCompoundAndGuardProtects:
    @pytest.mark.parametrize(
        "test",
        [
            "modifyAllowed and existing is None",
            "existing is None and modifyAllowed",
            "a and modifyAllowed and b",
            "project.writeEnabled and existing is None",
            "(modifyAllowed and a) and b",
            "modifyAllowed == True and a",
            "a and (modifyAllowed or modifyAllowed)",
        ],
    )
    def test_and_with_write_operand_protects_body(self, test):
        code = "existing = project.LexEntry.Find('x')\nif " + test + ":\n" + _CREATE
        assert _certified(code), test

    def test_issue_repro(self):
        code = (
            "existing = project.LexEntry.Find('x')\n"
            "if modifyAllowed and existing is None:\n"
            "    project.LexEntry.Create('x', 'stem')\n"
        )
        cert = certify_script_readonly(code, api_index=None)
        assert cert["is_certified_readonly"] is True
        assert cert["unprotected_liblcm_calls"] == []
        assert cert["protected_liblcm_calls"]

    def test_nested_form_still_protects(self):
        code = (
            "if modifyAllowed:\n"
            "    if existing is None:\n"
            "        project.LexEntry.Create('x', 'stem')\n"
        )
        assert _certified(code)

    def test_mutation_in_test_before_guard_operand_is_not_protected(self):
        # `x.Add(s)` runs before modifyAllowed is evaluated.
        code = (
            "if entry.SensesOS.Add(s) and\\\n"
            "        modifyAllowed:\n"
            "    pass\n"
        )
        assert not _certified(code)

    def test_else_branch_not_protected(self):
        code = (
            "if modifyAllowed and a:\n"
            "    pass\n"
            "else:\n" + _CREATE
        )
        assert not _certified(code)


class TestNonGuardsRejected:
    @pytest.mark.parametrize(
        "test",
        [
            "modifyAllowed or existing is None",
            "existing is None or modifyAllowed",
            "not (modifyAllowed and a)",
            "a and not modifyAllowed",
            "modifyAllowed == False",
            "modifyAllowed is False",
            "modifyAllowed != True",
            "modifyAllowed is not True",
            "False == modifyAllowed",
            "project.writeEnabled == False",
            "project.writeEnabled != True",
            "modifyAllowed == other",
            "modifyAllowed < 1",
        ],
    )
    def test_body_not_protected(self, test):
        code = "if " + test + ":\n" + _CREATE
        assert not _certified(code), test

    def test_true_comparisons_still_protect(self):
        for test in (
            "modifyAllowed == True",
            "modifyAllowed is True",
            "True == modifyAllowed",
            "modifyAllowed != False",
            "project.writeEnabled == True",
        ):
            assert _certified("if " + test + ":\n" + _CREATE), test


class TestEarlyReturnIdiomStillWorks:
    def _main(self, guard):
        return (
            "def Main(project, report, modifyAllowed):\n"
            f"    if {guard}:\n"
            "        return\n"
            "    project.LexEntry.Create('x')\n"
        )

    @pytest.mark.parametrize(
        "guard",
        [
            "not modifyAllowed",
            "modifyAllowed == False",
            "not project.writeEnabled",
            "not modifyAllowed or existing is not None",
            "existing is not None or not modifyAllowed",
            "not (modifyAllowed and existing is None)",
        ],
    )
    def test_tail_protected(self, guard):
        assert _certified(self._main(guard)), guard

    @pytest.mark.parametrize(
        "guard",
        [
            "not modifyAllowed and existing is not None",
            "not (modifyAllowed or existing is None)",
            "modifyAllowed",
        ],
    )
    def test_tail_not_protected(self, guard):
        assert not _certified(self._main(guard)), guard

    def test_issue139_range_unchanged(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    if not modifyAllowed:\n"
            "        report.Info('dry run')\n"
            "        return\n"
            "    project.LexEntry.Create('x')\n"
        )
        assert find_protected_ranges(code) == [(5, 5)]


def test_scaffold_marks_compound_guard_as_modifying():
    from flextoolsmcp.server.validators import _MODIFY_GUARD_RE

    assert _MODIFY_GUARD_RE.search("    if existing is None and modifyAllowed:\n")
    assert _MODIFY_GUARD_RE.search("    if not modifyAllowed:\n")
    assert not _MODIFY_GUARD_RE.search("    report.Info(modifyAllowed)\n")
