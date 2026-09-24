#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #175: module-level parse runner must not leak across tests."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402

from test_try_word_handler import Pool, RecordingWorker  # noqa: E402


@pytest.fixture
def runner(tmp_path, monkeypatch):
    monkeypatch.setattr(
        parse_handler, "_resolve_project", lambda name: (name or "P", None)
    )
    instance = ParseRunner(
        pool=Pool(RecordingWorker()), record_dir=tmp_path / "runs", grace_window=30.0
    )
    parse_handler.set_runner(instance)
    yield instance


def test_deliberately_leaves_a_custom_runner_installed(tmp_path):
    """Simulates the leak pattern reported in #175 (no local teardown)."""
    parse_handler.set_runner(
        ParseRunner(pool=Pool(RecordingWorker()), record_dir=tmp_path / "leak")
    )


async def test_parse_status_still_sees_the_fixture_runner(runner):
    """Would fail if the prior test's runner leaked into this one."""
    handle = await runner.start_run(project_name="P", wordforms=["makan"])
    response = await parse_handler.handle_flextools_parse_status(
        {"run_id": handle.run_id}
    )
    payload = json.loads(response[0].text)
    assert payload["status"] == "ok"
    assert payload["stage"] == "completed"
