#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #139: early-return ``if not modifyAllowed: ... return`` must gate writes."""

import sys

sys.path.insert(0, "src")

from flextoolsmcp.server.validators import (  # noqa: E402
    certify_script_readonly,
    find_protected_ranges,
)


class TestEarlyReturnGuardRecognized:
    def test_find_protected_ranges_tail_after_early_return(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    if not modifyAllowed:\n"
            "        report.Info('dry run')\n"
            "        return\n"
            "    project.LexEntry.Create('x')\n"
        )
        assert find_protected_ranges(code) == [(5, 5)]

    def test_certify_readonly_with_early_return_guard(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    if not modifyAllowed:\n"
            "        report.Info('dry run')\n"
            "        return\n"
            "    project.LexEntry.Create('x')\n"
        )
        result = certify_script_readonly(code, api_index=None)
        assert result["is_certified_readonly"] is True
        assert result["unprotected_liblcm_calls"] == []
        assert len(result["protected_liblcm_calls"]) == 1

    def test_if_else_form_still_protects(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    if modifyAllowed:\n"
            "        project.LexEntry.Create('x')\n"
            "    else:\n"
            "        report.Info('dry run')\n"
        )
        assert find_protected_ranges(code) == [(2, 3)]

    def test_early_return_without_return_does_not_protect_tail(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    if not modifyAllowed:\n"
            "        report.Info('dry run')\n"
            "    project.LexEntry.Create('x')\n"
        )
        result = certify_script_readonly(code, api_index=None)
        assert result["is_certified_readonly"] is False

    def test_not_project_writeEnabled_early_return(self):
        code = (
            "if not project.writeEnabled:\n"
            "    return\n"
            "project.LexEntry.Create('x')\n"
        )
        assert find_protected_ranges(code) == [(3, 3)]
        result = certify_script_readonly(code, api_index=None)
        assert result["is_certified_readonly"] is True
