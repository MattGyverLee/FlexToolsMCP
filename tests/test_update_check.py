#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the proactive update-notice feature (issue #79).

Covers: version comparison, cache freshness/TTL, fail-open on every failure
mode, opt-out env var, dev-install skip, and the once-per-process notice gate.
No network is performed -- the PyPI fetch is always injected.
"""

import json

import pytest

from flextoolsmcp import update_check as uc


@pytest.fixture(autouse=True)
def _reset_process_guards():
    """Each test starts with the once-per-process guards cleared."""
    uc._notice_emitted = False
    uc._refresh_started = False
    yield
    uc._notice_emitted = False
    uc._refresh_started = False


@pytest.fixture
def cache_path(tmp_path):
    """A temp cache path + a path_fn that returns it."""
    p = tmp_path / "update-check.json"
    return p, (lambda: p)


# --------------------------------------------------------------------------
# Version comparison
# --------------------------------------------------------------------------

@pytest.mark.parametrize("latest,installed,expected", [
    ("2.6.2", "2.6.1", True),
    ("2.7.0", "2.6.9", True),
    ("2.6.1", "2.6.1", False),
    ("2.6.0", "2.6.1", False),
    ("2.10.0", "2.9.0", True),   # numeric, not lexical
    ("garbage", "2.6.1", False),  # unparseable -> fail-closed on comparison
])
def test_is_newer(latest, installed, expected):
    assert uc._is_newer(latest, installed) is expected


# --------------------------------------------------------------------------
# Cache freshness / refresh
# --------------------------------------------------------------------------

def test_refresh_fetches_when_cache_missing(cache_path):
    path, path_fn = cache_path
    latest = uc.refresh_cache(
        path_fn=path_fn, fetch_fn=lambda: "9.9.9", now_fn=lambda: 1000.0
    )
    assert latest == "9.9.9"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["latest"] == "9.9.9"
    assert saved["last_checked_epoch"] == 1000.0


def test_refresh_skips_when_cache_fresh(cache_path):
    path, path_fn = cache_path
    path.write_text(json.dumps({"latest": "1.0.0", "last_checked_epoch": 1000.0}),
                    encoding="utf-8")

    def _boom():
        raise AssertionError("network must not be hit when cache is fresh")

    # 100s later, well within the 24h TTL -> no fetch.
    latest = uc.refresh_cache(path_fn=path_fn, fetch_fn=_boom, now_fn=lambda: 1100.0)
    assert latest == "1.0.0"


def test_refresh_refetches_when_cache_stale(cache_path):
    path, path_fn = cache_path
    path.write_text(json.dumps({"latest": "1.0.0", "last_checked_epoch": 1000.0}),
                    encoding="utf-8")
    stale = 1000.0 + uc.CACHE_TTL_SECONDS + 1
    latest = uc.refresh_cache(
        path_fn=path_fn, fetch_fn=lambda: "2.0.0", now_fn=lambda: stale
    )
    assert latest == "2.0.0"


def test_refresh_retains_last_known_on_fetch_failure(cache_path):
    path, path_fn = cache_path
    path.write_text(json.dumps({"latest": "1.0.0", "last_checked_epoch": 1000.0}),
                    encoding="utf-8")
    stale = 1000.0 + uc.CACHE_TTL_SECONDS + 1
    # Fetch returns None (offline). Last-known latest is retained, and the
    # check time is still stamped so we don't hammer PyPI on every call.
    latest = uc.refresh_cache(
        path_fn=path_fn, fetch_fn=lambda: None, now_fn=lambda: stale
    )
    assert latest == "1.0.0"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["last_checked_epoch"] == stale


# --------------------------------------------------------------------------
# get_update_notice
# --------------------------------------------------------------------------

def test_notice_when_update_available(cache_path, monkeypatch):
    path, path_fn = cache_path
    path.write_text(json.dumps({"latest": "2.6.2", "last_checked_epoch": 1e12}),
                    encoding="utf-8")
    monkeypatch.setattr(uc, "get_installed_version", lambda: "2.6.1")
    monkeypatch.setattr(uc, "ensure_background_refresh", lambda **kw: None)

    notice = uc.get_update_notice(path_fn=path_fn)
    assert notice is not None
    assert notice["installed"] == "2.6.1"
    assert notice["latest"] == "2.6.2"
    assert notice["update_available"] is True
    assert notice["upgrade_commands"]["uvx"] == "uvx flextools-mcp@latest"
    assert notice["upgrade_commands"]["pip"] == "pip install -U flextools-mcp"


def test_no_notice_when_up_to_date(cache_path, monkeypatch):
    path, path_fn = cache_path
    path.write_text(json.dumps({"latest": "2.6.1", "last_checked_epoch": 1e12}),
                    encoding="utf-8")
    monkeypatch.setattr(uc, "get_installed_version", lambda: "2.6.1")
    monkeypatch.setattr(uc, "ensure_background_refresh", lambda **kw: None)
    assert uc.get_update_notice(path_fn=path_fn) is None


def test_notice_emitted_at_most_once_per_process(cache_path, monkeypatch):
    path, path_fn = cache_path
    path.write_text(json.dumps({"latest": "2.6.2", "last_checked_epoch": 1e12}),
                    encoding="utf-8")
    monkeypatch.setattr(uc, "get_installed_version", lambda: "2.6.1")
    monkeypatch.setattr(uc, "ensure_background_refresh", lambda **kw: None)

    assert uc.get_update_notice(path_fn=path_fn) is not None
    # Second call in the same process -> suppressed.
    assert uc.get_update_notice(path_fn=path_fn) is None


def test_no_notice_for_dev_install(cache_path, monkeypatch):
    path, path_fn = cache_path
    path.write_text(json.dumps({"latest": "2.6.2", "last_checked_epoch": 1e12}),
                    encoding="utf-8")
    monkeypatch.setattr(uc, "get_installed_version", lambda: None)  # dev/source
    monkeypatch.setattr(uc, "ensure_background_refresh", lambda **kw: None)
    assert uc.get_update_notice(path_fn=path_fn) is None


def test_no_notice_when_cache_empty(cache_path, monkeypatch):
    _, path_fn = cache_path  # file never created
    monkeypatch.setattr(uc, "get_installed_version", lambda: "2.6.1")
    monkeypatch.setattr(uc, "ensure_background_refresh", lambda **kw: None)
    assert uc.get_update_notice(path_fn=path_fn) is None


# --------------------------------------------------------------------------
# Opt-out
# --------------------------------------------------------------------------

@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes"])
def test_opt_out_truthy(monkeypatch, val):
    monkeypatch.setenv(uc._ENV_OPT_OUT, val)
    assert uc.opted_out() is True


@pytest.mark.parametrize("val", ["", "0", "false", "no"])
def test_opt_out_falsey(monkeypatch, val):
    monkeypatch.setenv(uc._ENV_OPT_OUT, val)
    assert uc.opted_out() is False


def test_opt_out_suppresses_notice(cache_path, monkeypatch):
    path, path_fn = cache_path
    path.write_text(json.dumps({"latest": "2.6.2", "last_checked_epoch": 1e12}),
                    encoding="utf-8")
    monkeypatch.setenv(uc._ENV_OPT_OUT, "1")
    monkeypatch.setattr(uc, "get_installed_version", lambda: "2.6.1")
    assert uc.get_update_notice(path_fn=path_fn) is None


def test_opt_out_prevents_background_thread(monkeypatch):
    monkeypatch.setenv(uc._ENV_OPT_OUT, "1")
    started = []
    monkeypatch.setattr(uc.threading, "Thread",
                        lambda *a, **k: started.append(1))
    uc.ensure_background_refresh()
    assert started == []


# --------------------------------------------------------------------------
# Fail-open guarantees
# --------------------------------------------------------------------------

def test_load_cache_failopen_on_corrupt(cache_path):
    path, path_fn = cache_path
    path.write_text("{not valid json", encoding="utf-8")
    assert uc._load_cache(path_fn) == {}


def test_load_cache_failopen_on_bad_path():
    def _boom():
        raise RuntimeError("no home")
    assert uc._load_cache(_boom) == {}


def test_get_notice_never_raises(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(uc, "get_installed_version", lambda: "2.6.1")
    monkeypatch.setattr(uc, "ensure_background_refresh", _boom)
    # Even though a dependency raises, the notice path swallows it.
    assert uc.get_update_notice() is None


def test_fetch_latest_failopen(monkeypatch):
    # Simulate httpx raising; _fetch_latest must return None, not propagate.
    import sys
    import types
    fake = types.ModuleType("httpx")

    def _get(*a, **k):
        raise RuntimeError("network down")

    fake.get = _get
    monkeypatch.setitem(sys.modules, "httpx", fake)
    assert uc._fetch_latest(timeout=0.01) is None
