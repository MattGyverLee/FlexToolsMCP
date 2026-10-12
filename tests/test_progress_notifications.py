"""Phase 3 (issue #369, ruling R3): progress notifications.

Seam tests per cycle1-longops section 5 -- no live client needed:

- reporter unit behavior (no-op default, capture, raising sink);
- the adapter seam: a FakeCtx whose session.report_progress records
  calls, params carrying meta progressToken => notifications flow;
  ctx=None / no token => nothing emitted and results identical;
- semantic-search milestone sequence with a capturing reporter;
- heartbeat wrapper around a fake long-running coroutine;
- grammar-scan reuse of the heartbeat wrapper;
- sandbox seed milestones with a fake store.
"""

import asyncio
import sys
import types as _types
from types import SimpleNamespace

import pytest
from mcp.types import TextContent

from flextoolsmcp.server import progress as progress_mod
from flextoolsmcp.server.progress import (
    ProgressReporter,
    build_progress_reporter,
    get_progress_reporter,
    progress_heartbeat,
    reset_progress_reporter,
    set_progress_reporter,
)


def _get_srv():
    """Load src/flextoolsmcp/server.py the way test_mcp_compat does."""
    import importlib.util
    from pathlib import Path

    server_py = Path(__file__).parent.parent / "src" / "flextoolsmcp" / "server.py"
    spec = importlib.util.spec_from_file_location("_server_module_p3", str(server_py))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _RecordingSession:
    """Fake ServerSession: records report_progress calls."""

    def __init__(self):
        self.calls = []

    async def report_progress(self, progress, total=None, message=None):
        self.calls.append((progress, total, message))


class _RaisingSession:
    async def report_progress(self, progress, total=None, message=None):
        raise RuntimeError("client channel gone")


def _fake_ctx(session):
    return SimpleNamespace(session=session)


def _params_with_token(token="tok-1"):
    return SimpleNamespace(
        name="probe", arguments={}, meta={"progress_token": token}
    )


def _capturing_reporter(records):
    async def _sink(progress, total=None, message=None):
        records.append((progress, total, message))

    return ProgressReporter(_sink)


@pytest.fixture
def capturing():
    """Install a capturing reporter in the ContextVar for one test."""
    records = []
    token = set_progress_reporter(_capturing_reporter(records))
    try:
        yield records
    finally:
        reset_progress_reporter(token)


# ---------------------------------------------------------------------------
# Reporter unit behavior
# ---------------------------------------------------------------------------


def test_noop_reporter_drops_everything():
    reporter = ProgressReporter()
    assert not reporter.enabled
    asyncio.run(reporter.report(1, total=2, message="x"))
    reporter.report_nowait(1, total=2, message="x")  # must not raise


def test_default_context_reporter_is_noop():
    assert not get_progress_reporter().enabled


async def test_capturing_reporter_records_in_order():
    records = []
    reporter = _capturing_reporter(records)
    assert reporter.enabled
    await reporter.report(0, total=3, message="a")
    await reporter.report(1, total=3, message="b")
    assert records == [(0, 3, "a"), (1, 3, "b")]


async def test_raising_sink_never_propagates():
    async def _boom(progress, total=None, message=None):
        raise RuntimeError("sink exploded")

    reporter = ProgressReporter(_boom)
    await reporter.report(1, total=None, message="x")  # no raise
    reporter.report_nowait(1, total=None, message="x")
    await asyncio.sleep(0.05)  # scheduled task also swallows


# ---------------------------------------------------------------------------
# build_progress_reporter: token / ctx matrix
# ---------------------------------------------------------------------------


def test_build_reporter_binds_session_when_token_present():
    session = _RecordingSession()
    reporter = build_progress_reporter(_fake_ctx(session), _params_with_token())
    assert reporter.enabled
    asyncio.run(reporter.report(5, total=None, message="half"))
    assert session.calls == [(5, None, "half")]


def test_build_reporter_accepts_wire_spelling_and_object_meta():
    session = _RecordingSession()
    params = SimpleNamespace(
        name="probe", arguments={}, meta={"progressToken": "tok-9"}
    )
    assert build_progress_reporter(_fake_ctx(session), params).enabled
    params2 = SimpleNamespace(
        name="probe",
        arguments={},
        meta=SimpleNamespace(progress_token="tok-9"),
    )
    assert build_progress_reporter(_fake_ctx(session), params2).enabled


def test_build_reporter_noop_without_token_or_ctx():
    session = _RecordingSession()
    bare = SimpleNamespace(name="probe", arguments={})
    assert not build_progress_reporter(_fake_ctx(session), bare).enabled
    assert not build_progress_reporter(None, _params_with_token()).enabled
    assert not build_progress_reporter(None, bare).enabled
    # A bool "token" is not a token (SDK dispatcher rule).
    bool_params = SimpleNamespace(
        name="probe", arguments={}, meta={"progress_token": True}
    )
    assert not build_progress_reporter(_fake_ctx(session), bool_params).enabled


def test_build_reporter_noop_when_session_cannot_report():
    ctx = SimpleNamespace(session=SimpleNamespace())
    assert not build_progress_reporter(ctx, _params_with_token()).enabled


# ---------------------------------------------------------------------------
# Adapter seam: _on_call_tool installs the reporter around dispatch
# ---------------------------------------------------------------------------


def _make_emitting_call_tool(srv):
    """A call_tool stub emitting via the loaded server module's OWN
    reporter accessor -- server.py loaded bare (importlib, no package)
    resolves its progress module through the dual-path fallback, so the
    seam must be driven through srv's namespace, as in test_mcp_compat."""

    async def _emitting(name, arguments):
        reporter = srv.get_progress_reporter()
        await reporter.report(0, total=2, message="start")
        await reporter.report(1, total=2, message="middle")
        return [TextContent(type="text", text=f"ok:{name}")]

    return _emitting


def test_adapter_with_token_emits_progress_and_returns_result():
    srv = _get_srv()
    handler = srv.make_call_tool_handler(_make_emitting_call_tool(srv))
    session = _RecordingSession()
    result = asyncio.run(
        handler(_fake_ctx(session), _params_with_token("tok-1"))
    )
    assert not result.is_error
    assert [c.text for c in result.content] == ["ok:probe"]
    assert session.calls == [(0, 2, "start"), (1, 2, "middle")]
    # Reporter does not leak past the call.
    assert not srv.get_progress_reporter().enabled


def test_adapter_without_token_emits_nothing_same_result():
    srv = _get_srv()
    handler = srv.make_call_tool_handler(_make_emitting_call_tool(srv))
    session = _RecordingSession()
    params = SimpleNamespace(name="probe", arguments={})
    result = asyncio.run(handler(_fake_ctx(session), params))
    assert not result.is_error
    assert [c.text for c in result.content] == ["ok:probe"]
    assert session.calls == []


def test_adapter_ctx_none_emits_nothing_same_result():
    srv = _get_srv()
    handler = srv.make_call_tool_handler(_make_emitting_call_tool(srv))
    result = asyncio.run(handler(None, _params_with_token()))
    assert not result.is_error
    assert [c.text for c in result.content] == ["ok:probe"]


def test_adapter_raising_sink_leaves_result_unaffected():
    srv = _get_srv()
    handler = srv.make_call_tool_handler(_make_emitting_call_tool(srv))
    result = asyncio.run(
        handler(_fake_ctx(_RaisingSession()), _params_with_token())
    )
    assert not result.is_error
    assert [c.text for c in result.content] == ["ok:probe"]


# ---------------------------------------------------------------------------
# Semantic-search milestones (server.py SemanticSearch)
# ---------------------------------------------------------------------------


def test_semantic_search_model_load_milestone_sequence(monkeypatch):
    """First-search model load emits the 2 -> 3 rungs of the 0..3 ladder
    with the same strings the _log_info sites narrate. The capturing
    reporter is installed through srv's own ContextVar (see the adapter
    seam note above)."""
    srv = _get_srv()
    capturing = []
    token = srv.set_progress_reporter(_capturing_reporter(capturing))

    fake_st = _types.ModuleType("sentence_transformers")

    class _FakeModel:
        def encode(self, texts, convert_to_numpy=True):
            return [[0.0] * 4 for _ in texts]

    fake_st.SentenceTransformer = lambda name: _FakeModel()
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_st)
    # Force the faiss-absent branch of SemanticSearch.search explicitly:
    # a None sys.modules entry makes `import faiss` raise ImportError,
    # which is exactly what the production guard catches. Without this,
    # the test's outcome depends on the ambient environment -- with real
    # faiss installed (CI installs the full requirements), search would
    # proceed past the milestones and faiss.normalize_L2 would touch
    # .shape on the fake model's list return.
    monkeypatch.setitem(sys.modules, "faiss", None)

    search = srv.SemanticSearch(
        enabled=True,
        index=SimpleNamespace(search=lambda q, k: ([[0.0]], [[-1]])),
        items=[{"source": "flexlibs", "entity": "E", "name": "N"}],
    )

    async def _drive():
        # search() is synchronous and blocks the loop; report_nowait
        # queues the notifications, flushed by the sleeps after it returns.
        # (faiss is forced absent above via sys.modules, so search stops
        # right after the "model ready" milestone -- both load milestones
        # precede it.)
        search.search("gloss")
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    try:
        asyncio.run(_drive())
    finally:
        srv.reset_progress_reporter(token)
    messages = [m for (_p, _t, m) in capturing]
    assert messages == [
        "Downloading embedding model 'all-MiniLM-L6-v2' "
        "(~50MB, cached for future runs)...",
        "Model ready, search in progress...",
    ] or messages == [
        "Loading embedding model 'all-MiniLM-L6-v2' from cache...",
        "Model ready, search in progress...",
    ]
    assert [p for (p, _t, _m) in capturing] == [2, 3]
    assert all(t == 3 for (_p, t, _m) in capturing)


# ---------------------------------------------------------------------------
# Heartbeat wrapper
# ---------------------------------------------------------------------------


async def test_heartbeat_emits_elapsed_progress():
    capturing = []
    reporter = _capturing_reporter(capturing)
    async with progress_heartbeat("test-op", interval=0.05, reporter=reporter):
        await asyncio.sleep(0.23)
    assert len(capturing) >= 3
    values = [p for (p, _t, _m) in capturing]
    assert values == sorted(values)  # monotonic elapsed
    assert all(t is None for (_p, t, _m) in capturing)
    assert all("elapsed" in m for (_p, _t, m) in capturing)
    count_after = len(capturing)
    await asyncio.sleep(0.12)
    assert len(capturing) == count_after  # cancelled in finally, no leak


async def test_heartbeat_noop_reporter_spawns_nothing():
    # Cycle-2 QC P2: this previously had no assertion (it failed only if
    # the wrapper raised). Pin the actual invariant: with the default
    # no-op reporter the wrapper spawns NO background task at all.
    before = asyncio.all_tasks()
    async with progress_heartbeat("test-op", interval=0.01):
        await asyncio.sleep(0.05)  # default reporter: disabled, bare await
        assert asyncio.all_tasks() == before
    assert asyncio.all_tasks() == before


async def test_heartbeat_raising_sink_does_not_affect_run():
    async def _boom(progress, total=None, message=None):
        raise RuntimeError("sink exploded")

    reporter = ProgressReporter(_boom)
    async with progress_heartbeat("test-op", interval=0.02, reporter=reporter):
        await asyncio.sleep(0.07)
    # Reaching here at all is the assertion: the run completed normally.


# ---------------------------------------------------------------------------
# Grammar-health scan reuses the heartbeat wrapper (handlers/execution.py)
# ---------------------------------------------------------------------------


def test_run_scan_module_heartbeats_while_subprocess_runs(
    capturing, monkeypatch
):
    from flextoolsmcp.server.handlers import execution

    monkeypatch.setattr(
        progress_mod, "DEFAULT_HEARTBEAT_INTERVAL_SECONDS", 0.05
    )

    async def _fake_run_script(path, timeout_seconds=None):
        await asyncio.sleep(0.16)
        return {
            "stdout": "",
            "stderr": "",
            "timeout": True,
            "returncode": None,
        }

    monkeypatch.setattr(execution, "run_script_async", _fake_run_script)

    result = asyncio.run(
        execution.run_scan_module(
            "flextoolsmcp.server.scan.grammar_scan_module",
            "scan_project",
            "NoSuchProject",
            timeout_seconds=5,
        )
    )
    assert result["ran"] is False
    assert result["error_type"] == "Timeout"
    assert len(capturing) >= 2
    assert all(
        m.startswith("grammar scan: still running")
        for (_p, _t, m) in capturing
    )


def test_run_scan_module_no_reporter_no_heartbeats(monkeypatch):
    """Invariant: without a token the scan behaves exactly as before."""
    from flextoolsmcp.server.handlers import execution

    async def _fake_run_script(path, timeout_seconds=None):
        return {"stdout": "", "stderr": "", "timeout": True, "returncode": None}

    monkeypatch.setattr(execution, "run_script_async", _fake_run_script)
    result = asyncio.run(
        execution.run_scan_module("m", "f", "NoSuchProject", timeout_seconds=5)
    )
    assert result["error_type"] == "Timeout"


# ---------------------------------------------------------------------------
# Sandbox seed milestones (handlers/parse/sandbox.py)
# ---------------------------------------------------------------------------


def test_sandbox_seed_emits_step_milestones(capturing, monkeypatch):
    from flextoolsmcp.server.handlers.parse import sandbox as sandbox_mod
    from flextoolsmcp.server.models import ParseSandboxInput

    class _FakeStore:
        CorpusNotFound = type("CorpusNotFound", (Exception,), {})
        RunNotFound = type("RunNotFound", (Exception,), {})
        RunNotSeedable = type("RunNotSeedable", (Exception,), {})
        CorpusExists = type("CorpusExists", (Exception,), {})

        def seed_corpus(self, project_name, name, record):
            return {
                "name": name,
                "path": "/tmp/corpus.json",
                "assertion_count": 3,
                "no_parse_count": 0,
                "excluded": [],
                "from_run_id": "run-1",
            }

    monkeypatch.setattr(sandbox_mod, "_sandbox_store", lambda: _FakeStore())
    monkeypatch.setattr(
        "flextoolsmcp.server.parse.record.RunRecord",
        lambda run_id, record_dir=None: SimpleNamespace(run_id=run_id),
    )

    request = ParseSandboxInput(
        action="seed_corpus",
        project_name="Proj",
        corpus="c1",
        from_run_id="a" * 32,
    )
    plan = sandbox_mod._SandboxPlan(request=request, project_name="Proj")

    async def _drive():
        sandbox_mod._sandbox_seed(plan)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(_drive())
    assert capturing == [
        (0, 1, "Seeding corpus from the completed parse run..."),
        (1, 1, "Corpus seeded."),
    ]


# ---------------------------------------------------------------------------
# Cycle-2 QC P2: run_module heartbeat + sandbox CREATE milestones.
# Both were shipped untested in Phase 3; these drive the real call sites
# with the same fake pattern as the grammar-scan / seed tests above.
# ---------------------------------------------------------------------------


def test_run_module_heartbeats_while_script_runs(capturing, monkeypatch, tmp_path):
    """execution.py's two progress_heartbeat("run_module") wrappers around
    run_script_async: a slow script must produce elapsed heartbeats."""
    import json as _json

    from test_issue49_validate_only import _stub_agreement_env

    from flextoolsmcp.server.handlers import execution

    _stub_agreement_env(monkeypatch, tmp_path)
    monkeypatch.setattr(
        progress_mod, "DEFAULT_HEARTBEAT_INTERVAL_SECONDS", 0.05
    )

    async def _slow_run_script(path, timeout_seconds=None):
        await asyncio.sleep(0.16)
        return {
            "stdout": "===FLEXTOOLS_RESULT_JSON===\n"
            + _json.dumps({"success": True, "messages": []}),
            "stderr": "",
            "timeout": False,
            "returncode": 0,
        }

    monkeypatch.setattr(execution, "run_script_async", _slow_run_script)

    args = {
        "code": "def f(ana):\n    return ana.CategoryRA\n",
        "project_name": "TestProj",
        "write_enabled": False,
        "skip_api_check": True,
        "skip_module_check": True,
    }
    result = asyncio.run(execution.handle_run_module(args))
    data = _json.loads(result[0].text)
    assert data.get("success") is True, data
    assert len(capturing) >= 2
    assert all(t is None for (_p, t, _m) in capturing)
    assert all(
        m.startswith("run_module: still running")
        for (_p, _t, m) in capturing
    )


def test_sandbox_create_emits_step_milestones(capturing, monkeypatch):
    """sandbox.py _sandbox_create: milestones 0/1/2 of total=2 around the
    cache export and store create, with fake cache/workdir/store."""
    from pathlib import Path as _Path

    from flextoolsmcp.server.handlers.parse import sandbox as sandbox_mod
    from flextoolsmcp.server.models import ParseSandboxInput
    from flextoolsmcp.server.sandbox import cache as sandbox_cache
    from flextoolsmcp.server.sandbox import workdir as sandbox_workdir

    monkeypatch.setattr(
        sandbox_mod.sandbox_checks,
        "_sandbox_fwdata_path",
        lambda name: _Path("/tmp/Proj.fwdata"),
    )
    monkeypatch.setattr(
        sandbox_workdir, "create", lambda op_id, source_fwdata=None: object()
    )
    monkeypatch.setattr(sandbox_workdir, "delete", lambda work: None)

    async def _fake_ensure_entry(*args, **kwargs):
        return SimpleNamespace(built=True, load_error_count=0)

    monkeypatch.setattr(sandbox_cache, "ensure_entry", _fake_ensure_entry)

    class _FakeStore:
        def create_sandbox(self, project_name, name, entry):
            return {"name": name, "path": "/tmp/sb", "origin": {}}

    monkeypatch.setattr(sandbox_mod, "_sandbox_store", lambda: _FakeStore())

    request = ParseSandboxInput(
        action="create_sandbox", project_name="Proj", sandbox="sb1"
    )
    plan = sandbox_mod._SandboxPlan(request=request, project_name="Proj")
    result = asyncio.run(sandbox_mod._sandbox_create(plan))
    import json as _json2
    data = _json2.loads(result[0].text)
    assert data["status"] == "ok", data
    assert capturing == [
        (0, 2, "Exporting project grammar for the sandbox..."),
        (1, 2, "Creating sandbox from the exported grammar..."),
        (2, 2, "Sandbox created."),
    ]


async def test_report_nowait_task_is_referenced_until_done():
    """Cycle-2 QC P2: report_nowait must hold a strong reference to its
    task (a bare create_task can be GC'd mid-flight)."""
    records = []
    reporter = _capturing_reporter(records)

    async def _drive():
        reporter.report_nowait(1, total=2, message="m")
        # In flight: the task is tracked, not orphaned.
        assert progress_mod._NOWAIT_TASKS, "report_nowait task unreferenced"
        await asyncio.sleep(0.05)

    await _drive()
    assert records == [(1, 2, "m")]
    # Completed: the reference is released again.
    assert not progress_mod._NOWAIT_TASKS
