#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the workspace sanity check.

Covers: repo fingerprinting for every known signature, ancestor walk + depth
bound, nearest-match-wins, the no-false-positive case (an ordinary user folder),
the opt-out env var, the once-per-process gate, fail-open on a broken cwd, and
the three wiring surfaces (start warnings, health warnings, response envelope).
"""

import json

import pytest

from flextoolsmcp import workspace_check as wc


@pytest.fixture(autouse=True)
def _reset_process_guard(monkeypatch):
    """Clear the once-per-process gate and any inherited opt-out."""
    monkeypatch.delenv(wc._ENV_OPT_OUT, raising=False)
    wc._notice_emitted = False
    yield
    wc._notice_emitted = False


def _make_repo(root, signature_key):
    """Materialize the marker files for one signature under ``root``."""
    sig = next(s for s in wc._REPO_SIGNATURES if s["key"] == signature_key)
    for rel in sig["markers"]:
        target = root / rel
        # Markers are a mix of files (pyproject.toml, LCM.sln) and directories
        # (src, Src, FlexTools); exists() accepts either, so a directory is the
        # safe universal stand-in except where the name obviously carries an
        # extension.
        if target.suffix:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
        else:
            target.mkdir(parents=True, exist_ok=True)
    return root


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "key", [s["key"] for s in wc._REPO_SIGNATURES]
)
def test_every_signature_is_detected(tmp_path, key):
    repo = _make_repo(tmp_path / "repo", key)
    found = wc.detect_source_checkout(cwd_fn=lambda: repo)
    assert found is not None
    assert found["key"] == key
    assert found["repo_root"] == str(repo.resolve())


def test_plain_user_folder_is_not_flagged(tmp_path):
    """The healthy case: an empty working folder, or one with only scripts."""
    work = tmp_path / "flex-scripts"
    work.mkdir()
    (work / "clean_glosses.py").write_text("# my script\n", encoding="utf-8")
    assert wc.detect_source_checkout(cwd_fn=lambda: work) is None


def test_single_marker_is_not_enough(tmp_path):
    """A lone pyproject.toml must not fingerprint as the MCP repo."""
    work = tmp_path / "my-project"
    work.mkdir()
    (work / "pyproject.toml").write_text("", encoding="utf-8")
    assert wc.detect_source_checkout(cwd_fn=lambda: work) is None


def test_detects_from_a_subdirectory(tmp_path):
    """Opening src/flextoolsmcp inside the clone still counts as the clone."""
    repo = _make_repo(tmp_path / "FlexToolsMCP", "flextools-mcp")
    deep = repo / "src" / "flextoolsmcp"
    found = wc.detect_source_checkout(cwd_fn=lambda: deep)
    assert found is not None
    assert found["key"] == "flextools-mcp"
    assert found["repo_root"] == str(repo.resolve())
    assert found["cwd"] == str(deep.resolve())


def test_ancestor_walk_is_depth_bounded(tmp_path):
    """Beyond MAX_ANCESTOR_DEPTH the walk stops rather than climbing to root."""
    repo = _make_repo(tmp_path / "FlexToolsMCP", "flextools-mcp")
    deep = repo
    for i in range(wc.MAX_ANCESTOR_DEPTH + 2):
        deep = deep / f"d{i}"
    deep.mkdir(parents=True)
    assert wc.detect_source_checkout(cwd_fn=lambda: deep) is None


def test_nearest_checkout_wins(tmp_path):
    """A nested checkout reports the inner repo, not the outer one."""
    outer = _make_repo(tmp_path / "liblcm", "liblcm")
    inner = _make_repo(outer / "vendor" / "flexicon", "flexicon")
    found = wc.detect_source_checkout(cwd_fn=lambda: inner)
    assert found["key"] == "flexicon"
    assert found["repo_root"] == str(inner.resolve())


def test_fail_open_when_cwd_is_unresolvable():
    def boom():
        raise OSError("cwd was deleted")

    assert wc.detect_source_checkout(cwd_fn=boom) is None
    assert wc.get_workspace_notice(cwd_fn=boom) is None


def test_running_from_this_checkout_is_false_for_an_unrelated_clone(tmp_path):
    """A clone the user downloaded for reference is not the running code."""
    repo = _make_repo(tmp_path / "FlexToolsMCP", "flextools-mcp")
    found = wc.detect_source_checkout(cwd_fn=lambda: repo)
    assert found["running_from_this_checkout"] is False


def test_running_from_this_checkout_is_true_for_the_real_source_tree():
    """Detected against the actual repo this test file lives in."""
    from pathlib import Path

    real_root = Path(wc.__file__).resolve().parents[2]
    found = wc.detect_source_checkout(cwd_fn=lambda: real_root)
    assert found is not None
    assert found["key"] == "flextools-mcp"
    assert found["running_from_this_checkout"] is True


# --------------------------------------------------------------------------
# Notice payload
# --------------------------------------------------------------------------

def test_notice_names_the_repo_and_an_alternative(tmp_path):
    repo = _make_repo(tmp_path / "FlexToolsMCP", "flextools-mcp")
    notice = wc.get_workspace_notice(cwd_fn=lambda: repo)
    assert notice["detected_repo"] == "flextools-mcp"
    assert notice["repo_root"] == str(repo.resolve())
    assert "empty folder" in notice["message"]
    assert notice["suggested_workspace"]
    assert notice["opt_out_env_var"] == wc._ENV_OPT_OUT
    # The directive is what actually changes assistant behaviour; keep it here.
    directive = " ".join(notice["assistant_directive"])
    assert "flextools_search_by_capability" in directive
    assert ".fwdata" in directive


def test_notice_mentions_the_opt_out_when_it_is_the_running_source():
    from pathlib import Path

    real_root = Path(wc.__file__).resolve().parents[2]
    notice = wc.get_workspace_notice(cwd_fn=lambda: real_root)
    assert notice["running_from_this_checkout"] is True
    assert wc._ENV_OPT_OUT in notice["message"]


def test_warning_line_is_single_line_and_actionable(tmp_path):
    repo = _make_repo(tmp_path / "liblcm", "liblcm")
    notice = wc.get_workspace_notice(cwd_fn=lambda: repo)
    line = wc.warning_line(notice)
    assert "\n" not in line
    assert line.startswith("WORKSPACE:")
    assert "liblcm" in line


# --------------------------------------------------------------------------
# Opt-out and the once-per-process gate
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "anything"])
def test_opt_out_suppresses_the_notice(tmp_path, monkeypatch, value):
    monkeypatch.setenv(wc._ENV_OPT_OUT, value)
    repo = _make_repo(tmp_path / "FlexToolsMCP", "flextools-mcp")
    assert wc.opted_out() is True
    assert wc.get_workspace_notice(cwd_fn=lambda: repo) is None


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_falsey_env_values_do_not_opt_out(tmp_path, monkeypatch, value):
    monkeypatch.setenv(wc._ENV_OPT_OUT, value)
    repo = _make_repo(tmp_path / "FlexToolsMCP", "flextools-mcp")
    assert wc.opted_out() is False
    assert wc.get_workspace_notice(cwd_fn=lambda: repo) is not None


def test_once_gate_emits_a_single_time(tmp_path):
    repo = _make_repo(tmp_path / "FlexToolsMCP", "flextools-mcp")
    first = wc.get_workspace_notice(once=True, cwd_fn=lambda: repo)
    second = wc.get_workspace_notice(once=True, cwd_fn=lambda: repo)
    assert first is not None
    assert second is None


def test_ungated_calls_always_emit(tmp_path):
    """start / health must report every time, independent of the once gate."""
    repo = _make_repo(tmp_path / "FlexToolsMCP", "flextools-mcp")
    assert wc.get_workspace_notice(cwd_fn=lambda: repo) is not None
    assert wc.get_workspace_notice(cwd_fn=lambda: repo) is not None


def test_once_gate_is_not_consumed_when_workspace_is_clean(tmp_path):
    """A clean cwd must not burn the gate for a later dirty check."""
    work = tmp_path / "clean"
    work.mkdir()
    assert wc.get_workspace_notice(once=True, cwd_fn=lambda: work) is None
    assert wc._notice_emitted is False


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------

def test_response_envelope_attaches_the_notice_once(tmp_path, monkeypatch):
    from flextoolsmcp import response_utils

    repo = _make_repo(tmp_path / "FlexToolsMCP", "flextools-mcp")
    monkeypatch.chdir(repo)

    first = response_utils.build_response_with_context({}, include_session=False)
    second = response_utils.build_response_with_context({}, include_session=False)
    assert "workspace_notice" in first
    assert "workspace_notice" not in second


def test_response_envelope_survives_a_broken_check(monkeypatch):
    """The notice must never be why a tool response fails."""
    from flextoolsmcp import response_utils

    def boom(**_kwargs):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(wc, "get_workspace_notice", boom)
    data = response_utils.build_response_with_context(
        {"status": "ok"}, include_session=False
    )
    assert data["status"] == "ok"
    assert "workspace_notice" not in data


@pytest.mark.asyncio
async def test_start_warns_when_cwd_is_a_checkout(tmp_path, monkeypatch):
    from flextoolsmcp.server.handlers import admin

    repo = _make_repo(tmp_path / "FlexToolsMCP", "flextools-mcp")
    monkeypatch.chdir(repo)

    result = json.loads((await admin.handle_start({}))[0].text)
    assert "workspace_notice" in result
    assert any(w.startswith("WORKSPACE:") for w in result["warnings"])


@pytest.mark.asyncio
async def test_start_is_quiet_in_a_normal_folder(tmp_path, monkeypatch):
    from flextoolsmcp.server.handlers import admin

    work = tmp_path / "flex-scripts"
    work.mkdir()
    monkeypatch.chdir(work)

    result = json.loads((await admin.handle_start({}))[0].text)
    assert "workspace_notice" not in result
    assert not any(w.startswith("WORKSPACE:") for w in result.get("warnings", []))


@pytest.mark.asyncio
async def test_health_reports_the_workspace_warning(tmp_path, monkeypatch):
    from flextoolsmcp.server.handlers import diagnostic_health

    repo = _make_repo(tmp_path / "FlexToolsMCP", "flextools-mcp")
    monkeypatch.chdir(repo)

    result = json.loads(
        (await diagnostic_health.handle_flextools_health({}))[0].text
    )
    assert any(w.startswith("WORKSPACE:") for w in result["warnings"])
