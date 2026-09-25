#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The standing no-blocking regression (parser-check CP3; FR-061, SC-020).

"A running parse job blocks a concurrent lexicon edit 0 times, and no
project-wide claim is introduced." A linguist leaving a corpus batch running
must still be able to fix the entry the batch just exposed.

The edit path is `flextools_run_module` with `write_enabled=True`. It can be
held up by exactly two things this server controls: the per-project write
lock (`kernel.get_project_write_lock`), which serializes CUD runs, and the
`.fwdata.lock` file check (`project_discovery.check_project_locked`). A parse
job must take neither. This file asserts both while a batch is genuinely
running in a real (stub) worker, and then asserts structurally that no CP3
module reaches for either -- or for any other process-wide lock.

What this file cannot see offline is whether LCM itself takes a file lock
when the worker opens a project read-only; that is a live fact, and it is
part of the live scenarios (quickstart.md Scenario 7).

Run with:
    python -m pytest tests/test_parse_no_edit_blocking.py -q
"""

import ast
import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SRC = REPO_ROOT / "src" / "flextoolsmcp" / "server"
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server import kernel  # noqa: E402
from flextoolsmcp.server import project_discovery  # noqa: E402
from flextoolsmcp.server.parse.priority import Priority  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.parse.worker_client import WorkerPool  # noqa: E402

CP3_MODULES = sorted(
    list((SRC / "parse").glob("*.py"))
    + list((SRC / "signals").glob("*.py"))
    + [SRC / "handlers" / "parse.py"]
    # CP4 (FR-027, R-11): the filing claim is a per-project dictionary, NOT a
    # lock, and this scan is what proves it takes none of the claims an edit
    # waits on.
    + [SRC / "filing" / "claims.py"]
    # CP5 (T056): the sandbox spine copies the project and runs `hc` on the
    # copy; it must take none of the claims an edit waits on either.
    + list((SRC / "sandbox").glob("*.py"))
)

FINGERPRINT = {
    "scope_kind": "words", "scope_value": None, "text_ids": [], "word_count": 100,
    "limit": None, "truncated": False, "engine": "HC", "vernacular_ws": "id",
}

#: Anything that would amount to a project-wide claim.
_CLAIM_NAMES = {
    "get_project_write_lock", "project_write_locks",
    "check_project_locked", "locking", "flock", "lockf",
}


@pytest.fixture
async def running_batch(tmp_path):
    """A 100-word batch, genuinely mid-run in a real stub worker."""
    runner = ParseRunner(
        pool=WorkerPool(stub=True, parse_delay=0.05),
        record_dir=tmp_path / "runs",
        grace_window=0.1,
    )
    handle = await runner.start_run(
        project_name="P",
        wordforms=[f"w{n}" for n in range(100)],
        level="batch",
        priority=Priority.LOW,
        scope_fingerprint=FINGERPRINT,
        engine_at_submission="HC",
        vernacular_ws="id",
    )
    for _ in range(600):
        if handle.words_completed >= 1:
            break
        await asyncio.sleep(0.05)
    assert handle.words_completed >= 1 and not handle.is_terminal, (
        "the batch is not mid-run, so nothing below would prove anything"
    )
    try:
        yield handle
    finally:
        await runner.cancel_run(handle.run_id)
        await runner.aclose()


async def test_the_write_lock_is_free_while_a_batch_runs(running_batch):
    """The lock a write-enabled run_module takes is acquirable at once."""
    lock = kernel.get_project_write_lock("P")
    assert not lock.locked(), "a parse job is holding the project's write lock"
    await asyncio.wait_for(lock.acquire(), timeout=0.5)
    try:
        assert not running_batch.is_terminal, "the batch ended; the overlap was not tested"
    finally:
        lock.release()


async def test_the_batch_takes_no_lock_file(running_batch, tmp_path, monkeypatch):
    """No `.fwdata.lock` appears for the project because a batch is running."""
    projects = tmp_path / "projects"
    (projects / "P").mkdir(parents=True)
    monkeypatch.setattr(
        project_discovery, "get_projects_directory", lambda: (str(projects), "test")
    )
    assert project_discovery.check_project_locked("P") is None
    assert not running_batch.is_terminal


async def test_an_edit_does_not_wait_for_the_batch(running_batch):
    """Blocks 0 times: a simulated edit, under the write lock, completes while
    the batch is still running -- it does not queue behind the batch."""
    completed_before = running_batch.words_completed
    edits = 0
    for _ in range(5):
        async with kernel.get_project_write_lock("P"):
            edits += 1
        await asyncio.sleep(0)
    assert edits == 5
    assert not running_batch.is_terminal, "the edits waited for the batch to finish"
    assert running_batch.words_completed < 100
    assert running_batch.words_completed >= completed_before


def _docstring_nodes(tree):
    """The ids of the module/class/function docstring constants in `tree`.

    CP5 (T056): the lock-file rule looks for string LITERALS the code could
    use as a path. A docstring is prose, never a path the code opens, and the
    sandbox modules' docstrings name `.fwdata.lock` precisely to say the
    spine never takes it. Only docstrings are exempt; any other string that
    names a lock file is still a hit.
    """
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                ids.add(id(body[0].value))
    return ids


@pytest.mark.parametrize("path", CP3_MODULES, ids=lambda p: p.name)
def test_no_cp3_module_introduces_a_project_wide_claim(path):
    """Structural: CP3 code references none of the claims an edit waits on."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = _docstring_nodes(tree)
    hits = []
    for node in ast.walk(tree):
        name = None
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        elif (isinstance(node, ast.Constant) and isinstance(node.value, str)
              and id(node) not in docstrings):
            if node.value.endswith(".lock") or ".fwdata.lock" in node.value:
                hits.append(f"{path.name}:{node.lineno} names a lock file")
        if name in _CLAIM_NAMES:
            hits.append(f"{path.name}:{node.lineno} references {name}")
    assert hits == [], f"project-wide claim(s) in CP3 code: {hits}"
