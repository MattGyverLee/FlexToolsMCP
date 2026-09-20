#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The SPEC 16 test groups CP1 deferred (parser-check CP2b, T061, FR-039).

CP1's T028 listed by name the SPEC 16 groups it could and could not cover,
and deferred four. This file closes the ones CP2b can close and says, in
code and in the evidence artifact, why the remaining one still cannot be.

    1. no-user-interface-code guarantee   CLOSED -- tests/test_parser_no_xcore.py
    2. the script-library facade group    CLOSED HERE
    3. the conditional-proposal case      CLOSED HERE
    4. the no-oracle case                 STILL NOT IMPLEMENTABLE -- see below

**Why the no-oracle case is not here.** SPEC 16 asks that "a never-parsed
project reports the oracle as absent, not as all-unreviewed". The oracle is
the record of which analyses a human has approved -- and CP2b ships no
review surface at all: FR-002 says the parser area exposes no way to write,
and `RunStage.FILING` is defined and deliberately unreachable
(`tests/test_parse_stages.py` asserts no CP2b code path reaches it). There
is nothing here that could report an oracle, absent or otherwise, so a test
would have to invent the surface it was testing. Deferred to the checkpoint
that ships one, and recorded as deferred rather than quietly dropped --
which is the failure CP1's own evidence discipline exists to prevent.

Run with:
    python -m pytest tests/test_spec16_deferred_groups.py -q
"""

import ast
import inspect
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.parse import worker_main  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.parse.worker_client import WorkerError  # noqa: E402

from test_try_word_handler import Pool, RecordingWorker  # noqa: E402


# ---------------------------------------------------------------------------
# Group 2 -- the script-library facade
# ---------------------------------------------------------------------------

#: The facade's entire surface, frozen by a set-equality test in the flexicon
#: repository. Reproduced here because THIS repository's claim depends on it:
#: `flextools_try_word` is annotated `READ_ONLY_SAFE`, and the first thing
#: holding that annotation true is that none of these six records, files or
#: writes a parse result.
FACADE_MEMBERS = frozenset(
    {
        "GetAvailability",
        "ParseWord",
        "ParseWordXml",
        "TraceWordXml",
        "Reload",
        "IsUpToDate",
    }
)

#: Members that WOULD write. None of them is on the facade, and none may be
#: bound anywhere under `server/parse/`. `ProcessParse` is the one that files
#: a parse result back into the project; it is what CP1's write spine probes
#: for and what this checkpoint must never reach.
WRITE_MEMBERS = ("ProcessParse", "ParseFiler", "MoveConcAnnotationsToWordform")


def _parser_attribute_names(module, class_name="_RealBackend") -> set:
    """Every facade member bound inside `class_name`.

    SCOPED TO THE CLASS, not the module. The module's `main()` builds an
    `argparse.ArgumentParser` into a local also called `parser`, so a
    module-wide walk reports `add_argument` and `parse_args` as facade
    members -- which is a name collision, not a finding, and exactly the
    kind of false positive that gets a useful test deleted.

    An AST walk rather than a grep, because the docstrings in this module
    discuss these members at length -- precisely because the binding is
    load-bearing -- and a grep would match all of that prose.
    """
    tree = ast.parse(inspect.getsource(module))
    target = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        ),
        None,
    )
    assert target is not None, f"{class_name} not found in {module.__name__}"

    names = set()
    for node in ast.walk(target):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id in ("parser", "facade"):
                names.add(node.attr)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
            if node.value.attr == "Parser":
                names.add(node.attr)
    return names


def test_the_worker_binds_only_members_that_exist_on_the_facade():
    """Every facade member the worker calls is one of the six.

    This is the group CP1 deferred because it had no caller. CP2b is the
    caller, and the check it enables is the one that matters: a binding to
    a member the facade does not have fails at runtime on a live project
    and nowhere else.
    """
    bound = _parser_attribute_names(worker_main)

    unknown = bound - FACADE_MEMBERS
    assert not unknown, (
        f"the worker binds facade members that do not exist: {sorted(unknown)}. "
        f"The facade has exactly six: {sorted(FACADE_MEMBERS)}."
    )


def test_the_worker_binds_no_write_member():
    """The second thing holding `READ_ONLY_SAFE` true.

    The first is that the facade cannot reach a write path; this is that
    nothing under `server/parse/` reaches around it. Checked over the whole
    package, not just the worker, because the point is the absence of a
    path rather than the innocence of one module.
    """
    offenders = []
    package = REPO_ROOT / "src" / "flextoolsmcp" / "server" / "parse"
    for path in sorted(package.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in WRITE_MEMBERS:
                offenders.append(f"{path.name}:{node.lineno} .{node.attr}")
            elif isinstance(node, ast.Name) and node.id in WRITE_MEMBERS:
                offenders.append(f"{path.name}:{node.lineno} {node.id}")

    assert offenders == [], (
        "the parse package binds a write member, which would silently "
        "invalidate flextools_try_word's READ_ONLY_SAFE annotation: "
        + ", ".join(offenders)
    )


def test_the_three_calls_the_worker_makes_are_named_in_the_facade_set():
    """The specific three, so the set test above cannot pass vacuously.

    A worker that bound nothing at all would satisfy "binds only members
    that exist". These are the three FR-012 requires it to reach.
    """
    bound = _parser_attribute_names(worker_main)

    for member in ("ParseWord", "TraceWordXml", "GetAvailability"):
        assert member in bound, (
            f"the worker never binds {member}; FR-012 requires all three "
            f"levels to reach their own operation"
        )


def test_the_held_grammar_members_are_bound_too():
    """`Reload` and `IsUpToDate` -- the currency half of the facade (FR-043).

    Named here because the facade's set-equality test lives in another
    repository: if these were dropped from this side, nothing in THIS
    repository would notice, and the held-grammar contract would quietly
    stop being exercised.
    """
    bound = _parser_attribute_names(worker_main)

    assert "IsUpToDate" in bound, "currency is never confirmed"
    assert "Reload" in bound, "no explicit reload path is bound"


# ---------------------------------------------------------------------------
# Group 3 -- the conditional proposal (SPEC 9.5.5)
# ---------------------------------------------------------------------------


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    instance = ParseRunner(
        pool=Pool(RecordingWorker()), record_dir=tmp_path / "runs", grace_window=30.0
    )
    parse_handler.set_runner(instance)
    try:
        yield instance
    finally:
        parse_handler.set_runner(None)


async def _status(run_id):
    response = await parse_handler.handle_flextools_parse_status({"run_id": run_id})
    return json.loads(response[0].text)


async def test_the_grammar_scan_is_proposed_when_a_run_fails(tmp_path, monkeypatch):
    """CP1 shipped `flextools_grammar_health` with nothing to propose it.

    SPEC 9.5.5 makes the proposal CONDITIONAL, and CP1 deferred the case
    because the condition -- a parse that failed -- could not arise: there
    was no parse. This is the first checkpoint where it can.
    """
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    failing = ParseRunner(
        pool=Pool(RecordingWorker(fail_with=WorkerError("out of memory"))),
        record_dir=tmp_path / "runs",
        grace_window=30.0,
    )
    parse_handler.set_runner(failing)
    try:
        handle = await failing.start_run(project_name="P", wordforms=["makan"])
        payload = await _status(handle.run_id)
    finally:
        parse_handler.set_runner(None)

    proposals = [
        rung for rung in payload["next_step"]
        if rung["tool"] == "flextools_grammar_health"
    ]
    assert proposals, (
        "a failed run did not propose the grammar scan; the commonest cause "
        "of a failure here is a grammar expensive enough to exhaust memory, "
        "which is exactly what that scan names"
    )
    assert proposals[0]["args"]["project_name"] == "P", (
        "the proposal must carry the project, or the caller has to retype it"
    )


async def test_the_grammar_scan_is_NOT_proposed_when_the_run_succeeded(runner):
    """The conditional half, and the one that makes it a condition.

    Proposing a diagnostic after every parse would make it noise: a caller
    who sees the same suggestion on success and on failure learns nothing
    from seeing it on failure.
    """
    handle = await runner.start_run(project_name="P", wordforms=["makan"])
    payload = await _status(handle.run_id)

    assert payload["next_step"] is None, (
        f"a successful run carried guidance: {payload['next_step']}"
    )


async def test_the_scan_is_not_proposed_on_a_still_running_run(tmp_path, monkeypatch):
    """Nor while the run is merely slow.

    A run still in `parsing` has not failed. Proposing a grammar scan there
    would read as "something is wrong", and the caller's reasonable
    response -- cancel and investigate -- would throw away work that was
    about to succeed.
    """
    import asyncio

    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )

    class Slow(RecordingWorker):
        def __init__(self):
            super().__init__()
            self.gate = asyncio.Event()

        async def parse_word(self, **kwargs):
            self.calls.append(kwargs)
            await self.gate.wait()
            return {"parse": {"parsed": True, "analysis_count": 1}, "trace_xml": None}

    slow = Slow()
    instance = ParseRunner(
        pool=Pool(slow), record_dir=tmp_path / "runs", grace_window=0.05
    )
    parse_handler.set_runner(instance)
    try:
        handle = await instance.start_run(
            project_name="P", wordforms=["a", "b", "c"]
        )
        assert not handle.is_terminal
        payload = await _status(handle.run_id)

        tools = [rung["tool"] for rung in payload["next_step"]]
        assert "flextools_grammar_health" not in tools, (
            f"a running run was told its grammar might be the problem: {tools}"
        )
        assert tools == ["flextools_parse_status"], tools
    finally:
        # Release the held word so the run can finish rather than being
        # abandoned mid-flight; a leaked pending task would surface as a
        # warning in some unrelated test.
        slow.gate.set()
        await instance.aclose()
        parse_handler.set_runner(None)


# ---------------------------------------------------------------------------
# Group 4 -- the no-oracle case, and why it is still deferred
# ---------------------------------------------------------------------------


def test_this_checkpoint_has_no_oracle_to_report_on():
    """The deferral, asserted rather than asserted-in-a-comment.

    SPEC 16 asks that a never-parsed project report the oracle as absent.
    CP2b ships no review surface at all, so there is nothing that could
    report it -- and a test written against an invented surface would be
    worse than no test.

    This asserts the PREMISE of the deferral instead: nothing here records,
    files, or reaches the filing stage. When that stops being true, this
    test fails and says to go write the real one.
    """
    from flextoolsmcp.server.parse.stages import ALLOWED_TRANSITIONS, RunStage

    inbound = [
        source
        for source, targets in ALLOWED_TRANSITIONS.items()
        if RunStage.FILING in targets
    ]
    assert inbound == [], (
        "`filing` has become reachable, so this checkpoint now records parse "
        "results -- SPEC 16's no-oracle case is finally implementable. Write "
        "it, and update T061's entry in evidence/cp2b-evidence.md."
    )
