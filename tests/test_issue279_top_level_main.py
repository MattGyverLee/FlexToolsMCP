#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #279: module-level Main(...) must not double-invoke with def Main."""

import ast
import sys

sys.path.insert(0, "src")

from flextoolsmcp.server.handlers import execution as execution_mod  # noqa: E402


class TestValidateOnlyTopLevelMainGate:
    def _checks(self, code: str, *, write_enabled: bool):
        tree = ast.parse(code)
        return execution_mod._build_validate_only_checks(
            code=code,
            code_tree=tree,
            syntax_error=None,
            api_idx=None,
            session_state_obj=object(),
            write_enabled=write_enabled,
            api_mode="flexicon",
            skip_api_check=True,
            provenance_existing=False,
            skip_module_check=True,
        )[0]

    def test_write_run_fails_gate(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    pass\n"
            "Main(project, report, modifyAllowed)\n"
        )
        checks = self._checks(code, write_enabled=True)
        gate = next(c for c in checks if c["gate"] == "top_level_main_invocation")
        assert gate["passed"] is False
        assert gate["call_lines"] == [3]

    def test_read_run_passes_with_advisory(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    pass\n"
            "Main(project, report, modifyAllowed)\n"
        )
        checks = self._checks(code, write_enabled=False)
        gate = next(c for c in checks if c["gate"] == "top_level_main_invocation")
        assert gate["passed"] is True
        assert "advisory" in gate
