#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #239: the filing worker must hold its one writable open (FR-029) from
startup to `filing_commit`, not idle-release it the way a read worker does.

Regression from #223: `ParseWorker.run()` calls `_release_if_idle()` whenever
the queue is empty. For the filing worker the queue is empty on the very first
loop pass -- `filing_setup` has not arrived yet -- so the project was closed and
`FilingBackend.setup()` then called `ObjectRepository` on None. #235's
`_open_runs` hold starts only once a word is enqueued, too late for this.

Run with:
    python -m pytest tests/test_issue239_filing_holds_project.py -q
"""

import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.filing.worker_filing import (  # noqa: E402
    FilingBackend,
    FilingRefusal,
    FilingWorker,
    StubFilingBackend,
)


class _OpenAtSetupBackend(StubFilingBackend):
    """Records whether the project was still open when each control arrived."""

    def __init__(self):
        super().__init__()
        self.open_at_setup = None
        self.open_at_commit = None

    def setup(self, run_id, setup):
        self.open_at_setup = self.is_open()

    def final_commit(self):
        self.open_at_commit = self.is_open()
        self.release()


def test_filing_worker_holds_project_across_idle_ticks_until_commit(tmp_path):
    backend = _OpenAtSetupBackend()
    messages = []
    worker = FilingWorker("Filing239", backend=backend, idle_timeout=600,
                          emit=messages.append)
    runner = threading.Thread(target=worker.run, daemon=True)
    runner.start()

    # Let the main loop pass its empty-queue branch several times before
    # `filing_setup` lands -- the window #223 released the project in.
    time.sleep(0.3)
    assert backend.is_open(), "idle ticks before filing_setup must not close the project"
    assert backend.release_count == 0

    worker.handle_message({"type": "filing_setup", "request_id": "s", "run_id": "r",
                           "setup": {"record_root": str(tmp_path / "rec" / "r")}})
    time.sleep(0.3)   # idle again between setup and the first word
    assert backend.is_open(), "idle ticks between setup and words must not close it"

    worker.handle_message({"type": "filing_commit", "request_id": "c", "run_id": "r"})
    worker.handle_message({"type": "shutdown"})
    runner.join(timeout=10)
    assert not runner.is_alive()

    assert backend.open_at_setup is True
    assert backend.open_at_commit is True
    assert backend.release_count == 1, "closed once, by final_commit"
    types = [m.get("type") for m in messages]
    assert "filing_ready" in types
    assert any(m.get("type") == "filing_committed" and m.get("ok") for m in messages)


def test_setup_without_open_project_refuses_by_name(tmp_path):
    """A closed project is a named refusal, not AttributeError on None."""
    backend = FilingBackend("Filing239")   # never opened: _project is None
    with pytest.raises(FilingRefusal) as info:
        backend.setup("r", {"record_root": str(tmp_path / "rec" / "r")})
    assert info.value.detail["error_type"] == "ProjectNotOpen"
    assert "not open" in str(info.value)
