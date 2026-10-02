#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #347 -- run_module dropped report messages when the script raised.

The generated runner's ``except Exception`` branch after
``exec(MODULE_CODE, ...)`` set only ``result["error"]``; everything the
script reported before the exception was lost. The fix mirrors run_scan's
error path: ``messages`` and ``summary`` ride alongside ``error``.

Runs the real generated runner against the fake ``flexicon`` package used
by the #96 teardown tests -- no FieldWorks, no live project.
"""

from test_issue96_teardown_visibility import (  # noqa: E402
    _capture_generated_script,
    _run_script,
    _write_fake_flexicon,
)


def _run(monkeypatch, tmp_path, code):
    script = _capture_generated_script(monkeypatch, tmp_path, code=code)
    script_path = tmp_path / "runner.py"
    script_path.write_text(script, encoding="utf-8")
    _write_fake_flexicon(tmp_path / "fake_pkgs", with_headless_ui=True)
    return _run_script(script_path, tmp_path / "fake_pkgs")


def test_messages_before_raise_are_returned(monkeypatch, tmp_path):
    payload = _run(
        monkeypatch, tmp_path,
        "report.Info('before Ensure: exists in store = False')\n"
        "report.Warning('about to fail')\n"
        "raise RuntimeError('refused call')\n",
    )
    assert payload["success"] is False
    assert "refused call" in payload["error"]
    texts = [m.get("message") or m.get("text") or str(m) for m in payload["messages"]]
    assert any("before Ensure: exists in store = False" in t for t in texts), texts
    assert any("about to fail" in t for t in texts), texts
    summary = payload["summary"]
    # The fake flexicon lacks 'per-operation-uow', so the runner adds its
    # own setup warning -- count the script's messages as a lower bound.
    assert summary["info_count"] == 1
    assert summary["warning_count"] >= 1
    assert summary["total_messages"] == len(payload["messages"])


def test_main_wrapped_raise_keeps_messages(monkeypatch, tmp_path):
    payload = _run(
        monkeypatch, tmp_path,
        "def Main(project, report, modifyAllowed):\n"
        "    report.Info('step 1 done')\n"
        "    raise ValueError('step 2 broke')\n",
    )
    assert payload["success"] is False
    assert "step 2 broke" in payload["error"]
    texts = [m.get("message") or m.get("text") or str(m) for m in payload["messages"]]
    assert any("step 1 done" in t for t in texts), texts
    assert payload["summary"]["info_count"] == 1
