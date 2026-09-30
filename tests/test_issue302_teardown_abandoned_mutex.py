#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #302 -- teardown AbandonedMutexException (GlobalWritingSystemRepository).

A process that died holding SIL's global writing-system store mutex made
every later ``LcmCache.Dispose`` fail with ``AbandonedMutexException``;
the runner reported "writes may not have been committed" with no advice,
and weaker callers re-ran the same write 20 times. Covered here, all
live-FLEx-free:

- ``teardown_recovery`` pure logic: phase / ``writes_committed``
  classification, the abandoned-mutex detection, the message, and the
  ``next_steps`` list.
- The generated runner (executed against a fake ``flexicon``): an
  abandoned-mutex failure inside ``LcmCache.Dispose`` is retried once; a
  successful retry keeps the run successful with a ``teardown_warning``,
  a failed retry is a ``TeardownError`` that says the writes WERE
  committed.
- The tool envelope: a ``TeardownError`` result carries ``next_steps``
  and ``writes_committed``.
- The scan runner embeds the same helpers and still parses.
"""

import asyncio
import ast
import json
import textwrap

from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.handlers import teardown_recovery as tr

from test_issue96_teardown_visibility import (  # noqa: E402
    _capture_generated_script,
    _parse,
    _run_script,
    _stub_env,
    _FAKE_FLEXICON_HEADLESS,
)


class AbandonedMutexException(Exception):
    """Stands in for System.Threading.AbandonedMutexException (pythonnet
    exposes .NET exceptions under their .NET type name)."""


_DISPOSE_TRACE = (
    "The wait completed due to an abandoned mutex.\n"
    "   at SIL.Threading.GlobalMutex.Lock()\n"
    "   at SIL.WritingSystems.GlobalWritingSystemRepository`1.TryGet(String id, T& ws)\n"
    "   at SIL.WritingSystems.LdmlInFolderWritingSystemRepository`1.Save()\n"
    "   at SIL.LCModel.LcmCache.Dispose()\n"
)


# ---------------------------------------------------------------------------
# Pure classification logic
# ---------------------------------------------------------------------------

class TestClassify:
    def test_abandoned_mutex_in_dispose_means_committed(self):
        info = tr.classify_teardown_failure(AbandonedMutexException(_DISPOSE_TRACE))
        assert info == {"phase": "dispose", "writes_committed": True, "abandoned_mutex": True}

    def test_python_frame_dispose_marker_counts(self):
        tb = 'File "FLExProject.py", line 736, in CloseProject\n    self.project.Dispose()\n'
        info = tr.classify_teardown_failure(RuntimeError("boom"), tb)
        assert info["phase"] == "dispose"
        assert info["writes_committed"] is True
        assert info["abandoned_mutex"] is False

    def test_save_failure_means_not_committed(self):
        e = RuntimeError("disk full\n   at SIL.LCModel.Infrastructure.Impl.UndoStackManager.Save()")
        info = tr.classify_teardown_failure(e)
        assert info["phase"] == "save"
        assert info["writes_committed"] is False

    def test_save_failure_in_context_wins_over_dispose(self):
        """usm.Save() raised, then Dispose() in the finally raised too: the
        Dispose exception carries the Save failure as __context__."""
        try:
            try:
                raise RuntimeError("save failed\n   at UnitOfWorkService.Save()")
            finally:
                raise AbandonedMutexException(_DISPOSE_TRACE)
        except AbandonedMutexException as e:
            info = tr.classify_teardown_failure(e)
        assert info["phase"] == "save"
        assert info["writes_committed"] is False
        assert info["abandoned_mutex"] is True

    def test_net_inner_exception_is_walked(self):
        class Outer(Exception):
            pass
        outer = Outer("wrapper")
        outer.InnerException = AbandonedMutexException("abandoned")
        assert tr.is_abandoned_mutex_error(outer) is True

    def test_read_only_run_is_not_applicable(self):
        info = tr.classify_teardown_failure(
            AbandonedMutexException(_DISPOSE_TRACE), write_enabled=False
        )
        assert info["writes_committed"] is None
        assert info["phase"] == "dispose"

    def test_pre_close_failure_is_not_committed(self):
        info = tr.classify_teardown_failure(
            RuntimeError("refresh failed"), close_started=False
        )
        assert info["phase"] == "pre_close"
        assert info["writes_committed"] is False

    def test_unknown_phase_is_unknown(self):
        info = tr.classify_teardown_failure(RuntimeError("simulated ConflictingSave"))
        assert info["phase"] == "unknown"
        assert info["writes_committed"] is None


class TestMessageAndNextSteps:
    def test_message_states_committed(self):
        msg = tr.teardown_error_message(
            {"writes_committed": True, "abandoned_mutex": True}
        )
        assert "WERE committed" in msg
        assert "may not have been" not in msg
        assert "AbandonedMutexException" in msg

    def test_message_unknown_keeps_hedge(self):
        assert "may not have been committed" in tr.teardown_error_message(
            {"writes_committed": None}
        )

    def test_message_read_only(self):
        assert "read-only" in tr.teardown_error_message({}, write_enabled=False)

    def test_next_steps_committed_abandoned(self):
        steps = tr.teardown_next_steps(
            {"writes_committed": True, "abandoned_mutex": True}
        )
        joined = " ".join(steps)
        assert "Do NOT re-run" in joined
        assert "read-only query" in joined
        assert "Close FieldWorks" in joined
        assert "clears a stale" in joined

    def test_next_steps_unknown_warns_against_blind_retry(self):
        steps = tr.teardown_next_steps({"writes_committed": None})
        joined = " ".join(steps)
        assert "Do NOT blindly re-run" in joined
        assert "Do not retry in a loop" in joined

    def test_next_steps_not_committed(self):
        steps = tr.teardown_next_steps({"writes_committed": False})
        assert "were not committed" in steps[0]

    def test_next_steps_read_only_has_no_rerun_warning(self):
        steps = tr.teardown_next_steps({"writes_committed": None}, write_enabled=False)
        assert not any("re-run" in s for s in steps)
        assert steps


class TestDotNetHelpersDegrade:
    def test_helpers_never_raise_without_clr(self):
        out = tr.clear_stale_ws_mutex(["no_such_mutex_issue302"])
        assert set(out) == {"names", "cleared", "held_by_other", "errors"}
        assert out["cleared"] is False
        assert tr.release_owned_ws_mutex(["no_such_mutex_issue302"]) == 0

    def test_mutex_names_include_fallback(self):
        names = tr.ws_repo_mutex_names()
        assert any(n.endswith("_SIL_WritingSystemRepository_3") for n in names)
        assert all("\\" not in n for n in names)

    def test_retry_without_cache_is_safe(self):
        class P:
            pass
        out = tr.retry_dispose_after_abandoned_mutex(P(), names=["no_such_mutex_issue302"])
        assert out["retried"] is False and out["retry_error"] is None

    def test_embedded_source_is_server_free(self):
        src = tr.RUNNER_HELPER_SOURCE
        assert "def classify_teardown_failure" in src
        assert "def _tr_load_source" not in src
        assert "RUNNER_HELPER_SOURCE" not in src.split('"""', 2)[2]
        ast.parse(src)


# ---------------------------------------------------------------------------
# Generated runner, executed against a fake flexicon
# ---------------------------------------------------------------------------

_FAKE_FLEXICON_ABANDONED = textwrap.dedent(
    '''
    import os


    def FLExInitialize():
        pass


    def FLExCleanup():
        pass


    class AbandonedMutexException(Exception):
        pass


    class _FakeCache:
        IsDisposed = False

        def Dispose(self):
            if os.environ.get("FAKE_CACHE_RETRY_RAISES"):
                raise RuntimeError("retry dispose failed")


    class FLExProject:
        def OpenProject(self, projectName=None, writeEnabled=False, undoable=True, ui=None):
            self.project = _FakeCache()

        def CloseProject(self):
            raise AbandonedMutexException(
                "The wait completed due to an abandoned mutex.\\n"
                "   at SIL.Threading.GlobalMutex.Lock()\\n"
                "   at SIL.LCModel.LcmCache.Dispose()"
            )
    '''
)


def _abandoned_runner(monkeypatch, tmp_path, *, retry_raises=False):
    script = _capture_generated_script(monkeypatch, tmp_path)
    assert "WRITE_ENABLED = False" in script
    script = script.replace("WRITE_ENABLED = False", "WRITE_ENABLED = True", 1)
    script_path = tmp_path / "runner.py"
    script_path.write_text(script, encoding="utf-8")
    pkg = tmp_path / "fake_pkgs" / "flexicon"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(
        _FAKE_FLEXICON_ABANDONED + _FAKE_FLEXICON_HEADLESS, encoding="utf-8"
    )
    if retry_raises:
        monkeypatch.setenv("FAKE_CACHE_RETRY_RAISES", "1")
    else:
        monkeypatch.delenv("FAKE_CACHE_RETRY_RAISES", raising=False)
    return _run_script(script_path, tmp_path / "fake_pkgs")


class TestRunnerRecovery:
    def test_runner_clears_stale_mutex_before_open(self, monkeypatch, tmp_path):
        script = _capture_generated_script(monkeypatch, tmp_path)
        assert script.index("clear_stale_ws_mutex()") < script.index(
            "project.OpenProject(projectName=PROJECT_NAME"
        )
        assert "def classify_teardown_failure" in script

    def test_successful_retry_keeps_success_with_warning(self, monkeypatch, tmp_path):
        payload = _abandoned_runner(monkeypatch, tmp_path)
        assert payload["success"] is True, payload.get("error")
        assert payload.get("error_type") in (None, "")
        assert payload["writes_committed"] is True
        warn = payload["teardown_warning"]
        assert warn["abandoned_mutex"] is True
        assert warn["phase"] == "dispose"
        assert warn["recovery"]["retry_ok"] is True
        assert "stale_ws_mutex_cleared" in payload

    def test_failed_retry_is_teardown_error_with_commit_status(self, monkeypatch, tmp_path):
        payload = _abandoned_runner(monkeypatch, tmp_path, retry_raises=True)
        assert payload["success"] is False
        assert payload["error_type"] == "TeardownError"
        assert payload["writes_committed"] is True
        assert "WERE committed" in payload["error"]
        assert "may not have been committed" not in payload["error"]
        td = payload["teardown_error"]
        assert td["abandoned_mutex"] is True
        assert td["recovery"]["retry_ok"] is False
        assert "retry dispose failed" in td["recovery"]["retry_error"]


# ---------------------------------------------------------------------------
# Tool envelope
# ---------------------------------------------------------------------------

def test_envelope_carries_next_steps_for_teardown_error(monkeypatch, tmp_path):
    _stub_env(monkeypatch, tmp_path)
    runner_payload = {
        "success": False,
        "error": "Project teardown failed after script execution (...)",
        "error_type": "TeardownError",
        "writes_committed": True,
        "teardown_error": {
            "type": "AbandonedMutexException",
            "message": "abandoned",
            "phase": "dispose",
            "writes_committed": True,
            "abandoned_mutex": True,
        },
        "summary": {"info_count": 0, "warning_count": 0, "error_count": 0},
        "messages": [],
    }

    async def _fake_run(path, timeout_seconds):
        return {
            "stdout": "===FLEXTOOLS_RESULT_JSON===" + json.dumps(runner_payload),
            "stderr": "",
            "timeout": False,
            "returncode": 0,
        }

    monkeypatch.setattr(execution_mod, "run_script_async", _fake_run)
    resp = _parse(asyncio.run(execution_mod.handle_run_module({
        "code": "report.Info('hi')\n",
        "project_name": "TestProj_302",
        "write_enabled": False,
        "skip_api_check": True,
        "skip_module_check": True,
    })))
    assert resp["error_type"] == "TeardownError"
    assert resp["writes_committed"] is True
    joined = " ".join(resp["next_steps"])
    assert "Close FieldWorks" in joined
    assert "clears a stale" in joined


def test_scan_script_embeds_helpers_and_parses():
    script = execution_mod._build_scan_script(
        module_import_path="x.y", function_name="scan",
        project_name="P", write_enabled=False,
    )
    ast.parse(script)
    assert "clear_stale_ws_mutex()" in script
    assert "retry_dispose_after_abandoned_mutex(project)" in script
