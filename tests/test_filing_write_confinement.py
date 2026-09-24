#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INVERSE confinement: exactly one module may open a project for writing in the
parser area (parser-check CP4, FR-029, R-09; tasks.md T052).

`test_parse_no_project_writes.py` proves the read spine never writes, over a
FIXED scan set (`parse/`, `signals/`, `handlers/parse.py`). This file proves
the other half: across the whole source tree, a writable open --
`OpenProject(..., writeEnabled=True)` or a `writeEnabled=True` keyword
anywhere -- appears in `server/filing/worker_filing.py` and nowhere else,
apart from `run_module`'s own generated runner (a string template executed in
its own subprocess, which predates CP4 and is its own write spine).

It also holds the filing package's READ modules to the same no-write scan the
read spine is held to: the preview's reads, the projection, the eligibility
port and the gate run in (or feed) the read worker, and must not write.
"""

import ast
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "flextoolsmcp"
FILING = SRC / "server" / "filing"

#: The one module allowed a writable open in the parser area.
ALLOWED_WRITABLE_OPEN = FILING / "worker_filing.py"

#: run_module's generated runner lives in this module as a STRING template
#: (it writes `WRITE_ENABLED = ...` into a script run in a subprocess). It is
#: not parser-area code and predates CP4; the scan below reads the AST, where
#: a template string is a Constant, not a call -- so it is not an exception
#: here at all. Named for the reader.
_TEMPLATE_HOST = SRC / "server" / "handlers" / "execution.py"

#: The same write surface `test_parse_no_project_writes.py` scans for.
_WRITE_CALLS = {
    "UndoableUnitOfWorkHelper", "NonUndoableUnitOfWorkHelper",
    "DoUsingNewOrCurrentUOW", "DoSomehow", "DoUsingNewOrCurrentUow",
    "BeginUndoTask", "EndUndoTask", "BeginNonUndoableTask", "EndNonUndoableTask",
    "SaveChanges", "SaveOnIdle", "Commit",
    "Create", "CreateEntry", "CreateSense", "CreateAnalysis",
    "Delete", "DeleteUnderlyingObject", "DeleteObj",
    "SetAgentOpinion", "SetEvaluation",
    "SetParserParameters", "SetGloss", "SetDefinition", "SetLexemeForm",
    "AddAnalysis", "AppendTo",
}

#: The filing modules that must only READ the project.
_READ_ONLY_FILING_MODULES = [
    "preflight_reads.py", "projection.py", "eligibility.py", "gate.py", "plan.py",
    "claims.py", "paths.py", "wording.py",
]


def _writable_opens(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if (kw.arg == "writeEnabled" and isinstance(kw.value, ast.Constant)
                        and kw.value.value is True):
                    hits.append(f"{path.relative_to(SRC)}:{node.lineno}")
            if (isinstance(node.func, ast.Attribute) and node.func.attr == "OpenProject"
                    and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value is True):
                hits.append(f"{path.relative_to(SRC)}:{node.lineno} (positional)")
    return hits


def test_a_writable_open_appears_only_in_worker_filing():
    hits = {}
    for path in SRC.rglob("*.py"):
        found = _writable_opens(path)
        if found:
            hits[path] = found
    offenders = {p: h for p, h in hits.items() if p != ALLOWED_WRITABLE_OPEN}
    assert offenders == {}, f"writable open outside worker_filing.py: {offenders}"


def test_worker_filing_does_open_writable_exactly_once():
    """Guard the guard: the scan must actually find the one it allows."""
    found = _writable_opens(ALLOWED_WRITABLE_OPEN)
    assert len(found) == 1, found


def test_the_filing_read_modules_make_no_write_call():
    hits = []
    for name in _READ_ONLY_FILING_MODULES:
        path = FILING / name
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
                if called in _WRITE_CALLS:
                    hits.append(f"{name}:{node.lineno} calls {called}")
    assert hits == [], hits


def test_the_read_worker_still_opens_read_only():
    """FR-029: the read tools keep opening the project read-only."""
    text = (SRC / "server" / "parse" / "worker_main.py").read_text(encoding="utf-8")
    assert "writeEnabled=False" in text
    assert _writable_opens(SRC / "server" / "parse" / "worker_main.py") == []
