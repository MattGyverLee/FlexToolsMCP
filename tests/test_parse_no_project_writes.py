#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The standing no-write test (parser-check CP3; FR-063, SC-021).

CP3 IS ENTIRELY READ-ONLY, and that is asserted here rather than discharged
by skipping a verification gate. "No code path shipped by this checkpoint
writes to a FieldWorks project -- 0 occurrences." The checkpoint cannot ship
without this file green.

WHAT IS CHECKED, and why each is the right lever:

  1. THE ONE PROJECT OPEN. Every `OpenProject` call in the parse package
     passes `writeEnabled=False` as a literal. With the project opened
     read-only, an LCM write raises rather than lands -- this is the
     enforcement, the rest is evidence that nothing even tries.

  2. NO WRITE API IS CALLED. Every CP3 module is walked as an AST for the
     LCM write surface: unit-of-work helpers, undo tasks, saves, factory
     creation, deletion, agent opinions. Walking the AST rather than grepping
     text means a comment or a docstring that NAMES a write API -- and this
     code names them often, to say it does not call them -- is not a hit.

  3. NO C#-STYLE PROPERTY IS ASSIGNED. LCM properties are PascalCase
     (`ParserParameters`, `Text`, `Gloss`); this package's own objects use
     snake_case. An assignment to a PascalCase attribute is therefore an LCM
     write in all but name, and there are 0 of them.

  4. THE WIRE CARRIES NO WRITE. The server can send the worker exactly the
     message types enumerated below, none of which writes. A new message type
     has to be added to this list on purpose.

  5. FILING IS UNREACHABLE. The `filing` stage has no inbound edge, so no run
     can enter it -- the write ladder is CP4's and none of it ships here.

Run with:
    python -m pytest tests/test_parse_no_project_writes.py -q
"""

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SRC = REPO_ROOT / "src" / "flextoolsmcp" / "server"
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse.stages import RunStage, can_transition  # noqa: E402

#: Every module this checkpoint's code path runs through: the parse package
#: (runner, worker, scope, record, measurement, comparison), the signals
#: package (the report), and the parse tool handlers. CP5 (T055, FR-043)
#: adds the sandbox spine's package, `server/sandbox/`: it never opens the
#: live project at all, so it must hold to the same no-write rules.
CP3_MODULES = sorted(
    list((SRC / "parse").glob("*.py"))
    + list((SRC / "signals").glob("*.py"))
    + list((SRC / "sandbox").glob("*.py"))
    + [SRC / "handlers" / "parse.py"]
)

#: The LCM / flexicon write surface, by the name that is CALLED.
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

#: What the server may say to a worker. All reads, parses, or lifecycle.
_READ_ONLY_MESSAGE_TYPES = {
    "parse", "cancel", "ping", "shutdown", "resolve", "assemblies",
    "engine_check", "resolve_scope", "parser_parameters",
    # CP4: the filing preflight's three questions to the READ worker. Each is
    # a read -- the agent lookup, this grammar load's errors and eligible
    # forms, the stored analyses and their segment use -- answered from
    # server/filing/preflight_reads.py, which T052's inverse test also holds
    # to no writes. The one message that sets up a WRITE (`filing_setup`) is
    # sent only to the filing worker, from server/filing/client.py, never
    # from this module.
    "agent_probe", "filing_gate", "filing_preview",
    # #235: runner closes a server-paced batch; worker only drops run_id from
    # `_open_runs` so `_release_if_idle` may run. No project write.
    "run_end",
}


def _tree(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _called_name(call):
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def test_the_module_list_covers_what_cp3_ships():
    names = {p.name for p in CP3_MODULES}
    for expected in ("runner.py", "worker_main.py", "measure.py", "scope.py",
                     "diff.py", "record.py", "report.py", "oracle.py",
                     "projections.py"):
        assert expected in names, f"{expected} is not under the no-write scan"
    sandbox = {p.name for p in CP3_MODULES if p.parent.name == "sandbox"}
    for expected in ("cache.py", "engine.py", "paths.py", "script.py", "workdir.py"):
        assert expected in sandbox, f"sandbox/{expected} is not under the no-write scan"


def test_every_project_open_is_read_only():
    opens = []
    for path in CP3_MODULES:
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Call) and _called_name(node) == "OpenProject":
                opens.append((path.name, node))
    assert opens, "the scan found no project open at all; it is looking in the wrong place"
    for name, call in opens:
        flags = {kw.arg: kw.value for kw in call.keywords}
        value = flags.get("writeEnabled")
        assert isinstance(value, ast.Constant) and value.value is False, (
            f"{name}:{call.lineno} opens a project without a literal writeEnabled=False"
        )


@pytest.mark.parametrize("path", CP3_MODULES, ids=lambda p: p.name)
def test_no_cp3_module_calls_a_write_api(path):
    hits = [
        f"{path.name}:{node.lineno} calls {_called_name(node)}"
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.Call) and _called_name(node) in _WRITE_CALLS
    ]
    assert hits == [], f"{len(hits)} write call(s) in CP3 code: {hits}"


#: .NET events a module may subscribe to with `+=` -- a handler added to a
#: process-wide event, never a write to an LCM object. CP5 re-plan (T096):
#: the sandbox worker resolves the bundled HermitCrab's dependencies by
#: simple name from the FieldWorks folder (`AppDomain.AssemblyResolve`).
_ALLOWED_EVENT_SUBSCRIPTIONS = frozenset({"AssemblyResolve"})


def _is_event_subscription(node: ast.AugAssign) -> bool:
    return (
        isinstance(node.op, ast.Add)
        and isinstance(node.target, ast.Attribute)
        and node.target.attr in _ALLOWED_EVENT_SUBSCRIPTIONS
    )


@pytest.mark.parametrize("path", CP3_MODULES, ids=lambda p: p.name)
def test_no_cp3_module_assigns_an_lcm_property(path):
    hits = []
    for node in ast.walk(_tree(path)):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign) and _is_event_subscription(node):
            continue
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for target in targets:
            for sub in ast.walk(target):
                if (
                    isinstance(sub, ast.Attribute)
                    and sub.attr[:1].isupper()
                    # `self.NumWords += 1` is this package's own
                    # `HostCounters`, which carries the host's eight counter
                    # names VERBATIM (contracts/tools.md section 4). No LCM
                    # object is ever `self` in this code.
                    and not (isinstance(sub.value, ast.Name) and sub.value.id == "self")
                ):
                    hits.append(f"{path.name}:{node.lineno} assigns .{sub.attr}")
    assert hits == [], f"{len(hits)} LCM-style property assignment(s): {hits}"


def test_the_server_sends_the_worker_no_write():
    """Every `{"type": ...}` the client can put on the wire is a read."""
    client = SRC / "parse" / "worker_client.py"
    sent = set()
    for node in ast.walk(_tree(client)):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(key, ast.Constant) and key.value == "type"
                    and isinstance(value, ast.Constant)
                ):
                    sent.add(value.value)
    assert sent, "the scan found no outgoing message types"
    unexpected = sent - _READ_ONLY_MESSAGE_TYPES
    assert unexpected == set(), (
        f"the server can send the worker {sorted(unexpected)}; add it to the "
        f"read-only list only if it writes nothing"
    )


def test_filing_is_unreachable_from_every_stage():
    """No READ-ONLY run can reach `filing` (CP4 R-16: the claim is kept, per run).

    `can_transition` without `filing=True` is the read-run table, byte for
    byte what CP3 shipped: `filing` has no inbound edge there.
    """
    reaching = [s.value for s in RunStage if can_transition(s, RunStage.FILING)]
    assert reaching == [], f"filing is reachable from {reaching}"
    reaching = [s.value for s in RunStage
                if can_transition(s, RunStage.FILING, filing=False)]
    assert reaching == [], f"filing is reachable from {reaching} on a read run"


def test_filing_is_reachable_only_for_a_filing_run():
    """CP4 (data-model section 10): the FILING edges exist only on a run
    created with filing=True -- parsing -> filing, and filing -> a terminal
    stage. The read-run table is untouched."""
    assert can_transition(RunStage.PARSING, RunStage.FILING, filing=True)
    for terminal in (RunStage.COMPLETED, RunStage.CANCELLED, RunStage.FAILED):
        assert can_transition(RunStage.FILING, terminal, filing=True)
        assert not can_transition(RunStage.FILING, terminal)
    assert not can_transition(RunStage.PARSING, RunStage.FILING)


def test_try_word_never_files():
    """FR-017 (structural): no try-a-word mode files anything, errored or not.

    `handle_flextools_try_word` starts runs; none of them may be a filing run,
    use the filing worker, or name the `file` level.
    """
    tree = _tree(SRC / "handlers" / "parse.py")
    handler = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "handle_flextools_try_word"
    )
    for node in ast.walk(handler):
        if isinstance(node, ast.keyword):
            assert node.arg not in ("filing", "filing_setup"), (
                f"try_word passes {node.arg}= at line {node.value.lineno}"
            )
        if isinstance(node, ast.Constant) and node.value == "file":
            raise AssertionError(f"try_word names the 'file' level at line {node.lineno}")
        if isinstance(node, ast.Name) and node.id in ("FILING_ROLE", "_handle_filing_request"):
            raise AssertionError(f"try_word reaches {node.id} at line {node.lineno}")


def test_the_measurement_reads_parser_parameters_and_never_assigns_them():
    """FR-055, specifically: the one place CP3 touches the parameters."""
    for path in CP3_MODULES:
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    assert not (
                        isinstance(target, ast.Attribute)
                        and target.attr == "ParserParameters"
                    ), f"{path.name}:{node.lineno} writes ParserParameters"
