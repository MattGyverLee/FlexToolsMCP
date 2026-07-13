#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for version-mismatch handling in ``_load_library_api_index``.

The server ships indexes for specific library versions, but a user's installed
LibLCM / Flexicon / FlexLibs may be newer or older. These tests pin the
behaviour of the loader when the installed version does not exactly match a
shipped index:

- exact match           -> load it, never refresh
- no exact match        -> try refresh-to-match once; if that regenerates the
                           installed version, serve it
- refresh can't match   -> serve the nearest (latest) shipped index and warn,
                           naming the direction (older/newer) of the mismatch
- nothing shipped at all -> refresh
- refresh guard         -> at most one refresh attempt per library per process
"""
import json

import pytest


@pytest.fixture
def server_mod():
    """The legacy ``server.py`` module (lazily loaded via the ``server``
    package), with the refresh guard and file-discovery cache reset so each
    test runs in isolation."""
    import server as server_pkg

    _ = server_pkg.APIIndex  # trigger lazy load into _server_module_cache
    mod = server_pkg._server_module_cache
    mod._REFRESH_ATTEMPTED.clear()
    mod.clear_file_discovery_cache()
    yield mod
    mod._REFRESH_ATTEMPTED.clear()
    mod.clear_file_discovery_cache()


def _write_api(lib_dir, version, entities):
    lib_dir.mkdir(parents=True, exist_ok=True)
    path = lib_dir / f"liblcm_api_v{version}.json"
    path.write_text(json.dumps({"entities": entities}), encoding="utf-8")
    return path


def _load(mod, index_dir, installed_version, monkeypatch, refresh=None):
    """Run the loader for a liblcm-style library.

    ``refresh`` optionally replaces ``auto_refresh_missing_api_file``. Warnings
    are captured. Returns ``(index, refresh_calls, warnings)``.
    """
    calls = []

    def default_refresh(*args, **kwargs):
        calls.append(args)
        return False

    monkeypatch.setattr(mod, "auto_refresh_missing_api_file", refresh or default_refresh)

    warnings = []
    monkeypatch.setattr(mod, "_log_warning", lambda m: warnings.append(m))

    idx = mod.APIIndex()
    mod._load_library_api_index(
        idx, index_dir, "LibLCM", "liblcm_api",
        lambda: installed_version, "liblcm", "liblcm_version",
    )
    return idx, calls, warnings


def test_exact_match_no_refresh(server_mod, tmp_path, monkeypatch):
    _write_api(tmp_path / "liblcm", "11.0.0", {"X": {}})
    idx, calls, warnings = _load(server_mod, tmp_path, "11.0.0", monkeypatch)
    assert idx.liblcm_version == "11.0.0"
    assert idx.liblcm == {"entities": {"X": {}}}
    assert calls == []       # never refresh when an exact match exists
    assert warnings == []


def test_no_match_refresh_regenerates_installed_version(server_mod, tmp_path, monkeypatch):
    # Shipped 11.0.0; installed 11.2.0. Refresh regenerates the exact match.
    _write_api(tmp_path / "liblcm", "11.0.0", {"OLD": {}})

    def refresh(library_key, prefix, lib_dir):
        _write_api(lib_dir, "11.2.0", {"NEW": {}})
        return True

    idx, _calls, warnings = _load(server_mod, tmp_path, "11.2.0", monkeypatch, refresh=refresh)
    assert idx.liblcm_version == "11.2.0"            # served the regenerated match
    assert idx.liblcm == {"entities": {"NEW": {}}}
    assert warnings == []                            # exact match, so no warning


def test_installed_newer_than_shipped_warns_older(server_mod, tmp_path, monkeypatch):
    # Installed 11.2.0, only 11.0.0 shipped, refresh fails -> serve 11.0.0, which
    # is OLDER than the installed library.
    _write_api(tmp_path / "liblcm", "11.0.0", {"X": {}})
    idx, calls, warnings = _load(server_mod, tmp_path, "11.2.0", monkeypatch)
    assert idx.liblcm_version == "11.0.0"            # nearest shipped
    assert len(calls) == 1                           # one refresh attempt
    assert len(warnings) == 1
    assert "11.2.0" in warnings[0] and "older" in warnings[0].lower()


def test_installed_older_than_shipped_warns_newer(server_mod, tmp_path, monkeypatch):
    # Installed 10.5.0, only 11.0.0 shipped, refresh fails -> serve 11.0.0, which
    # is NEWER than the installed library.
    _write_api(tmp_path / "liblcm", "11.0.0", {"X": {}})
    idx, calls, warnings = _load(server_mod, tmp_path, "10.5.0", monkeypatch)
    assert idx.liblcm_version == "11.0.0"
    assert len(calls) == 1
    assert len(warnings) == 1
    assert "10.5.0" in warnings[0] and "newer" in warnings[0].lower()


def test_missing_entirely_refreshes(server_mod, tmp_path, monkeypatch):
    def refresh(library_key, prefix, lib_dir):
        _write_api(lib_dir, "11.0.0", {"X": {}})
        return True

    idx, _calls, warnings = _load(server_mod, tmp_path, "11.0.0", monkeypatch, refresh=refresh)
    assert idx.liblcm_version == "11.0.0"
    assert warnings == []                            # exact match produced by refresh


def test_refresh_attempted_once_per_process(server_mod, tmp_path, monkeypatch):
    # Empty index dir, installed version known, refresh always fails: the loader
    # must attempt refresh exactly once for this library across repeated loads.
    calls = []

    def refresh(*args, **kwargs):
        calls.append(args)
        return False

    monkeypatch.setattr(server_mod, "auto_refresh_missing_api_file", refresh)
    monkeypatch.setattr(server_mod, "_log_warning", lambda m: None)

    for _ in range(3):
        idx = server_mod.APIIndex()
        server_mod._load_library_api_index(
            idx, tmp_path, "LibLCM", "liblcm_api",
            lambda: "11.0.0", "liblcm", "liblcm_version",
        )
    assert len(calls) == 1                           # guard holds across loads


def test_version_tuple_is_crash_proof(server_mod):
    # Malformed / partial versions must never raise during comparison.
    assert server_mod._version_tuple("11.0.0") == (11, 0, 0)
    assert server_mod._version_tuple("11.2") < server_mod._version_tuple("11.2.1")
    assert server_mod._version_tuple(None) == ()
    assert server_mod._version_tuple("11.0.0-beta") == (11, 0, 0)  # non-numeric tail ignored
    server_mod._version_tuple("garbage")             # does not raise
