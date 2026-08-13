#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CP1 / issue #92 end-to-end regression: the write path that was never
actually covered by a test.

Issue #92 found that ``undoable=True`` (the default whenever
``write_enabled=True``, per issue #55 Rung 1) made flexicon's
``OpenProject`` skip ``BeginNonUndoableTask()``, so every mutating call
either raised ``TypeError`` (multi-mutation methods going through
``_begin_undo_fn``) or ``InvalidOperationException`` (simple setters like
``SetGloss``) -- and the module's own ``except Exception`` block then
reported ``result["success"] = True`` anyway. Every unit test in this repo
stubs ``run_script_async``, so nothing ever caught this: 27
``write_enabled: true`` records in operations.jsonl, zero with
``undoable: true``.

CP1 fixed this by hardcoding ``undoable=False`` at the generated
``OpenProject`` call and by demoting ``success`` whenever the run reported
any ``report.Error()``. This test is the one that would have caught the
original regression: it drives the REAL ``flextools_run_module`` handler
(not a stub) against a real FieldWorks project, sets a gloss, closes the
project, reopens it, and asserts the write actually reached disk.

This is a live, mutating test. It is SKIPPED BY DEFAULT (no scratch
project on the machine running the suite has any business being touched
by an automated test run). To actually run it, a human must:

  1. Point FLEXTOOLSMCP_E2E_SCRATCH_PROJECT at a real, disposable FieldWorks
     project name (already open with FLEx closed, or opened in shared mode)
     that has at least one lexical entry with at least one sense.
  2. Run: pytest tests/test_issue92_write_path_e2e.py -m requires_flex -v

Do not wire this into CI or run it unattended against any project whose
state matters.
"""

import asyncio
import json
import os
import re
import uuid

import pytest

pytestmark = pytest.mark.requires_flex

_SCRATCH_PROJECT_ENV = "FLEXTOOLSMCP_E2E_SCRATCH_PROJECT"


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


def _find_marker(messages, prefix):
    """Pull `prefix<value>` back out of a run_module response's messages."""
    for m in messages or []:
        text = m.get("message", "") if isinstance(m, dict) else ""
        match = re.match(re.escape(prefix) + r"(.+)$", text)
        if match:
            return match.group(1)
    return None


def _scratch_project_name():
    name = os.environ.get(_SCRATCH_PROJECT_ENV)
    if not name:
        pytest.skip(
            f"set {_SCRATCH_PROJECT_ENV} to a disposable FieldWorks project "
            "name to run this live write-persistence check -- it is never "
            "run unattended; a human must opt in explicitly."
        )
    return name


def test_setgloss_persists_across_close_and_reopen():
    """flextools_run_module: SetGloss -> CloseProject -> reopen -> persisted.

    This is the exact scenario CP1 fixed: a write (SetGloss) made under the
    real generated-script OpenProject/CloseProject cycle, verified by
    re-opening the project in a SEPARATE subprocess (a second
    flextools_run_module call) and reading the value back.
    """
    pytest.importorskip(
        "flexicon", reason="CP1 e2e write check needs a live flexicon+FieldWorks install"
    )
    project_name = _scratch_project_name()

    from flextoolsmcp.server import APIIndex, kernel, project_discovery
    from flextoolsmcp.server.handlers import execution as execution_mod

    kernel.initialize_kernel()
    kernel.set_api_index(APIIndex.load(kernel.get_index_dir()))
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()

    # Real project resolution (no monkeypatching) -- this must be a real,
    # on-disk FieldWorks project the caller has already picked.
    resolved, err = project_discovery.resolve_or_explain(project_name)
    assert err is None, f"could not resolve scratch project {project_name!r}: {err}"
    project_name = resolved or project_name

    marker = f"cp1-e2e-{uuid.uuid4().hex[:8]}"

    write_code = (
        "if modifyAllowed:\n"
        "    entries = list(project.LexEntry.GetAll())\n"
        "    entry = entries[0]\n"
        "    senses = list(project.LexEntry.GetAllSenses(entry))\n"
        "    sense = senses[0]\n"
        "    ws_handle = project.GetDefaultAnalysisWSHandle()\n"
        "    report.Info('entry_hvo=' + str(entry.Hvo))\n"
        "    report.Info('sense_hvo=' + str(sense.Hvo))\n"
        f"    project.Senses.SetGloss(sense, {marker!r}, ws_handle)\n"
        "    report.Info('wrote gloss')\n"
        "else:\n"
        "    report.Error('modifyAllowed is False -- write_enabled did not propagate')\n"
    )

    write_args = {
        "code": write_code,
        "project_name": project_name,
        "write_enabled": True,
        "confirmed": True,
        "skip_api_check": True,
        "skip_module_check": True,
        "backup_before_write": False,
        "user_intent": "CP1/#92 e2e regression: SetGloss must persist across reopen.",
    }
    write_result = asyncio.run(execution_mod.handle_run_module(write_args))
    write_data = _parse(write_result)

    assert write_data.get("success") is True, (
        "write run_module call did not report success -- this is exactly the "
        f"CP1/#92 regression this test guards against. Response: {write_data}"
    )

    entry_hvo = _find_marker(write_data.get("messages"), "entry_hvo=")
    sense_hvo = _find_marker(write_data.get("messages"), "sense_hvo=")
    assert entry_hvo is not None and sense_hvo is not None, (
        f"could not recover entry/sense hvo from write response: {write_data}"
    )

    read_code = (
        "entries = [e for e in project.LexEntry.GetAll() if str(e.Hvo) == "
        f"{entry_hvo!r}]\n"
        "assert entries, 'entry vanished across CloseProject/reopen'\n"
        "senses = [s for s in project.LexEntry.GetAllSenses(entries[0]) if str(s.Hvo) == "
        f"{sense_hvo!r}]\n"
        "assert senses, 'sense vanished across CloseProject/reopen'\n"
        "ws_handle = project.GetDefaultAnalysisWSHandle()\n"
        "gloss = project.Senses.GetGloss(senses[0], ws_handle)\n"
        "report.Info('persisted_gloss=' + gloss)\n"
    )

    read_args = {
        "code": read_code,
        "project_name": project_name,
        "write_enabled": False,
        "skip_api_check": True,
        "skip_module_check": True,
        "user_intent": "CP1/#92 e2e regression: read back the gloss set by the prior call.",
    }
    read_result = asyncio.run(execution_mod.handle_run_module(read_args))
    read_data = _parse(read_result)

    assert read_data.get("success") is True, (
        f"read-back run_module call failed: {read_data}"
    )
    persisted_gloss = _find_marker(read_data.get("messages"), "persisted_gloss=")
    assert persisted_gloss == marker, (
        f"SetGloss did not persist across CloseProject/reopen: "
        f"expected {marker!r}, got {persisted_gloss!r}"
    )
