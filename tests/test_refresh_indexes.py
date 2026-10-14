"""flextools_refresh_indexes (issue #369, Phase 3 follow-up; R3 option (i)).

The refresh pipeline itself is never executed for real here:

- Handler tests monkeypatch ``flextoolsmcp.refresh.run_refresh`` with a
  scripted fake that fires the on_step callback the way the real pipeline
  does, so the handler's progress bridging, payload shaping, and error
  path are exercised without spawning any builder subprocess.
- Orchestration tests call the real ``refresh.run_refresh`` with the
  individual step functions monkeypatched out, pinning the plan order,
  the fixed total, and the success/skip accounting without any I/O.
"""

import asyncio
import json

import flextoolsmcp.refresh as refresh_mod
from flextoolsmcp.server.dispatch import DISPATCH_ROUTES
from flextoolsmcp.server.handlers import admin
from flextoolsmcp.server.models import RefreshIndexesInput
from flextoolsmcp.server.progress import (
    ProgressReporter,
    reset_progress_reporter,
    set_progress_reporter,
)
from flextoolsmcp.server.tool_definitions import TOOLS

_DESCRIPTIONS = [
    "Refreshing FlexLibs index",
    "Refreshing Flexicon index",
    "Refreshing LibLCM index",
]


def _scripted_result():
    return {
        "success": True,
        "any_refresh_succeeded": True,
        "steps": [
            {"step": "flexlibs", "description": _DESCRIPTIONS[0],
             "status": "ok", "detail": None},
            {"step": "flexicon", "description": _DESCRIPTIONS[1],
             "status": "ok", "detail": None},
            {"step": "liblcm", "description": _DESCRIPTIONS[2],
             "status": "skipped",
             "detail": "FieldWorks DLLs / pythonnet not available"},
        ],
    }


def _install_fake_pipeline(monkeypatch, received):
    def _fake_run_refresh(flexicon_path=None, flexlibs_path=None,
                          dll_path=None, skip_categorization=False,
                          skip_postprocess=False, on_step=None):
        received.update({
            "flexicon_path": flexicon_path,
            "flexlibs_path": flexlibs_path,
            "dll_path": dll_path,
            "skip_categorization": skip_categorization,
            "skip_postprocess": skip_postprocess,
        })
        if on_step is not None:
            for completed, description in enumerate(_DESCRIPTIONS):
                on_step(completed, len(_DESCRIPTIONS), description)
        return _scripted_result()

    monkeypatch.setattr(refresh_mod, "run_refresh", _fake_run_refresh)


def _capturing_reporter(records):
    async def _sink(progress, total=None, message=None):
        records.append((progress, total, message))

    return ProgressReporter(_sink)


# ---------------------------------------------------------------------------
# Handler: payload, args forwarding, error path
# ---------------------------------------------------------------------------


def test_handler_returns_summary_payload_and_forwards_args(monkeypatch):
    received = {}
    _install_fake_pipeline(monkeypatch, received)

    result = asyncio.run(
        admin.handle_refresh_indexes({"flexicon_path": "/opt/flexicon"})
    )
    data = json.loads(result[0].text)

    assert data["status"] == "ok"
    assert data["_contract"]  # stamped by build_response_with_context
    assert data["refreshed"] == ["flexlibs", "flexicon"]
    assert data["skipped"] == ["liblcm"]
    assert data["failed"] == []
    assert [s["step"] for s in data["steps"]] == [
        "flexlibs", "flexicon", "liblcm",
    ]
    # The restart caveat and the embeddings exclusion are part of the
    # payload, not just the description.
    assert "restart" in data["note"]
    assert "embeddings are not rebuilt" in data["note"]
    # Args reach the pipeline with the CLI-shaped names/defaults.
    assert received["flexicon_path"] == "/opt/flexicon"
    assert received["flexlibs_path"] is None
    assert received["skip_categorization"] is False
    assert received["skip_postprocess"] is False


def test_handler_payload_identical_without_progress_token(monkeypatch):
    """R3 invariant: no token => no-op reporter => same payload out.

    Compared as parsed JSON minus the once-per-process advisory keys
    build_response_with_context may attach (update/workspace notices) --
    those are envelope furniture, not refresh output.
    """
    _install_fake_pipeline(monkeypatch, {})

    def _payload(result):
        data = json.loads(result[0].text)
        for key in ("workspace_notice", "update_notice",
                    "project_adopted_notice"):
            data.pop(key, None)
        return data

    bare = _payload(asyncio.run(admin.handle_refresh_indexes({})))
    records = []
    token = set_progress_reporter(_capturing_reporter(records))
    try:
        with_reporter = _payload(asyncio.run(admin.handle_refresh_indexes({})))
    finally:
        reset_progress_reporter(token)
    assert records  # the reporter run really did emit
    assert with_reporter == bare


def test_handler_emits_milestones_in_order(monkeypatch):
    _install_fake_pipeline(monkeypatch, {})
    records = []
    token = set_progress_reporter(_capturing_reporter(records))
    try:
        result = asyncio.run(admin.handle_refresh_indexes({}))
    finally:
        reset_progress_reporter(token)
    assert json.loads(result[0].text)["status"] == "ok"
    assert records == [
        (0, 3, "Refreshing FlexLibs index"),
        (1, 3, "Refreshing Flexicon index"),
        (2, 3, "Refreshing LibLCM index"),
        (3, 3, "Index refresh complete"),
    ]


def test_handler_partial_pipeline_reports_partial_status(monkeypatch):
    def _fake_run_refresh(**_kwargs):
        result = _scripted_result()
        result["success"] = False
        result["steps"][1]["status"] = "failed"
        return result

    monkeypatch.setattr(refresh_mod, "run_refresh", _fake_run_refresh)
    result = asyncio.run(admin.handle_refresh_indexes({}))
    data = json.loads(result[0].text)
    # A failed step is a reported outcome, not a transport error.
    assert data["status"] == "partial"
    assert data["failed"] == ["flexicon"]


def test_handler_pipeline_exception_becomes_error_response(monkeypatch):
    def _boom(**_kwargs):
        raise RuntimeError("analyzer exploded")

    monkeypatch.setattr(refresh_mod, "run_refresh", _boom)
    result = asyncio.run(admin.handle_refresh_indexes({}))
    data = json.loads(result[0].text)
    assert data["status"] == "error"
    assert data["error_code"] == "refresh_failed"
    assert "analyzer exploded" in data["message"]


# ---------------------------------------------------------------------------
# Registration: annotations, route, input-model defaults
# ---------------------------------------------------------------------------


def test_annotations_and_registration():
    tool = TOOLS["flextools_refresh_indexes"]
    a = tool.annotations
    assert (a.read_only_hint, a.destructive_hint,
            a.idempotent_hint, a.open_world_hint) == (False, True, True, False)
    handler, model = DISPATCH_ROUTES["flextools_refresh_indexes"]
    assert handler is admin.handle_refresh_indexes
    assert model is RefreshIndexesInput
    # Defaults mirror the refresh CLI exactly.
    assert RefreshIndexesInput().model_dump() == {
        "flexicon_path": None,
        "flexlibs_path": None,
        "dll_path": None,
        "skip_categorization": False,
        "skip_postprocess": False,
    }
    # It writes index files, so the cold-start gate must not auto-init a
    # read-only session for it (tool_definitions' set is the authority).
    from flextoolsmcp.server.tool_definitions import COLD_START_SAFE_TOOLS

    assert "flextools_refresh_indexes" not in COLD_START_SAFE_TOOLS


# ---------------------------------------------------------------------------
# run_refresh orchestration (real function, step functions faked)
# ---------------------------------------------------------------------------

_STEP_FN_NAMES = [
    "refresh_flexlibs_stable",
    "refresh_flexicon",
    "refresh_liblcm",
    "apply_categorization",
    "run_postprocess_reverse_mapping",
    "run_postprocess_navigation_graph",
    "run_postprocess_patterns",
    "run_postprocess_casting_index",
    "run_postprocess_element_types",
    "run_postprocess_getall_contract",
    "run_archive_old_versions",
]

_PLAN_DESCRIPTIONS = [
    "Refreshing FlexLibs index",
    "Refreshing Flexicon index",
    "Refreshing LibLCM index",
    "Applying semantic categorization to LibLCM",
    "Building reverse mapping (LibLCM -> FlexLibs)",
    "Building navigation graph",
    "Extracting common patterns",
    "Building casting index (pythonnet interface casting)",
    "Annotating element types (collection casting hints)",
    "Annotating GetAll collection contracts",
    "Archiving old API versions",
]


def _fake_steps(monkeypatch, outcomes=None, liblcm_scannable=False):
    """Replace every pipeline step with a recording stub (no subprocesses,
    no file I/O). ``outcomes`` maps a step function name to its bool."""
    outcomes = outcomes or {}
    calls = []
    for name in _STEP_FN_NAMES:
        def _make(name=name):
            def _stub(*_args, **_kwargs):
                calls.append(name)
                return outcomes.get(name, True)
            return _stub
        monkeypatch.setattr(refresh_mod, name, _make())
    monkeypatch.setattr(
        refresh_mod, "liblcm_scannable", lambda dll_path=None: liblcm_scannable
    )
    return calls


def test_run_refresh_plan_order_and_skip_accounting(monkeypatch):
    calls = _fake_steps(monkeypatch, liblcm_scannable=False)
    milestones = []
    result = refresh_mod.run_refresh(
        on_step=lambda c, t, d: milestones.append((c, t, d))
    )

    # Fixed 11-step plan, announced in order with a total that never moves.
    assert milestones == [
        (i, 11, d) for i, d in enumerate(_PLAN_DESCRIPTIONS)
    ]
    assert [s["description"] for s in result["steps"]] == _PLAN_DESCRIPTIONS
    by_step = {s["step"]: s["status"] for s in result["steps"]}
    assert by_step["flexlibs"] == "ok"
    assert by_step["flexicon"] == "ok"
    assert by_step["liblcm"] == "skipped"           # not scannable here
    assert by_step["categorization"] == "skipped"   # follows the LibLCM scan
    assert by_step["archive"] == "ok"
    assert result["success"] is True
    assert result["any_refresh_succeeded"] is True
    # Skipped steps never invoke their functions.
    assert "refresh_liblcm" not in calls
    assert "apply_categorization" not in calls


def test_run_refresh_liblcm_scannable_runs_categorization(monkeypatch):
    _fake_steps(monkeypatch, liblcm_scannable=True)
    result = refresh_mod.run_refresh()
    by_step = {s["step"]: s["status"] for s in result["steps"]}
    assert by_step["liblcm"] == "ok"
    assert by_step["categorization"] == "ok"
    assert result["success"] is True


def test_run_refresh_failed_scans_skip_archive_and_fail(monkeypatch):
    calls = _fake_steps(
        monkeypatch,
        outcomes={"refresh_flexlibs_stable": False,
                  "refresh_flexicon": False},
    )
    result = refresh_mod.run_refresh()
    by_step = {s["step"]: s["status"] for s in result["steps"]}
    assert by_step["flexlibs"] == "failed"
    assert by_step["flexicon"] == "failed"
    assert by_step["archive"] == "skipped"  # nothing succeeded
    assert "run_archive_old_versions" not in calls
    assert result["any_refresh_succeeded"] is False
    assert result["success"] is False


def test_run_refresh_skip_postprocess_records_skips(monkeypatch):
    calls = _fake_steps(monkeypatch)
    result = refresh_mod.run_refresh(skip_postprocess=True)
    by_step = {s["step"]: s["status"] for s in result["steps"]}
    for key in ("reverse_mapping", "navigation_graph", "patterns",
                "casting_index", "element_types", "getall_contract"):
        assert by_step[key] == "skipped", key
    assert "run_postprocess_patterns" not in calls
    assert result["success"] is True


def test_run_refresh_on_step_exception_never_fails_refresh(monkeypatch):
    _fake_steps(monkeypatch)

    def _bad_callback(*_args):
        raise RuntimeError("client channel gone")

    result = refresh_mod.run_refresh(on_step=_bad_callback)
    assert result["success"] is True
    assert len(result["steps"]) == 11
