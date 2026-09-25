#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #235: the parse worker must not release the project between words of
a batch when the server sends one word at a time (the production path).

Regression from the #223 idle-release fix: `_release_if_idle` ran whenever
the worker queue emptied, but the runner only enqueues the next word after
the previous result returns, so every word looked like idle.

Run with:
    python -m pytest tests/test_issue235_run_end_hold.py -q
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse.priority import Priority  # noqa: E402
from flextoolsmcp.server.parse.worker_main import (  # noqa: E402
    ParseWorker,
    _StubBackend,
)


def _parse_message(run_id, wordform, priority, index, **extra):
    message = {
        "type": "parse",
        "request_id": f"{run_id}:{index}",
        "run_id": run_id,
        "wordform": wordform,
        "level": "plain",
        "restricted_to": None,
        "priority": int(priority),
        "index_in_run": index,
    }
    message.update(extra)
    return message


def test_server_paced_batch_holds_one_grammar_load():
    """Words arrive one at a time, like `ParseRunner._execute_run`."""
    backend = _StubBackend()
    messages = []

    def emit(message):
        messages.append(message)
        if message.get("type") != "result" or message.get("run_id") != "batch":
            return
        index = int(message.get("index_in_run", 0))
        if index + 1 < 4:
            worker.handle_message(
                _parse_message(
                    "batch",
                    f"w{index + 1}",
                    Priority.MEDIUM,
                    index + 1,
                    level="batch",
                    engine_at_submission="HC",
                )
            )
        else:
            worker.handle_message({"type": "run_end", "run_id": "batch"})
            worker.handle_message({"type": "shutdown"})

    worker = ParseWorker("Batch235", backend=backend, idle_timeout=600, emit=emit)
    worker.handle_message(
        _parse_message(
            "batch",
            "w0",
            Priority.MEDIUM,
            0,
            level="batch",
            engine_at_submission="HC",
        )
    )
    worker.run()

    assert backend.load_count == 1, "one grammar load for the whole batch"
    assert backend.release_count == 1, "released once after run_end, not per word"
    assert len([m for m in messages if m.get("type") == "result"]) == 4
