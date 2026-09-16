#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Home for the subprocess-run grammar scan module (parser-check feature,
specs/parser-check/SPEC.md section 9.5.5, `flextools_grammar_health`).

`grammar_scan_module.py` (T019, a later spurt) lives in this package. It is
pure-LCM, static-analysis code -- no export, no `hc` tool, no ParserCore --
so it ships decoupled from the sandbox spine and is available from the
moment a project can be opened.

IMPORTANT: modules in this package are executed in the FLExTools/IronPython
subprocess interpreter via `flextools_run_module` (see
`src/flextoolsmcp/server/subprocess_helpers.py`), the same way any other
run_module script is. They are NOT imported by the MCP server process
itself, and must not import anything from the MCP server's own runtime
(`flextoolsmcp.server.*`) -- only `flexicon` / raw LCM, matching every other
script this project hands to a FieldWorks project.
"""

__all__: list = []
