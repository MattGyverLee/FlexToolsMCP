#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression tests for issue #10: "Session not initialized" between
consecutive run_module calls.

Root cause (found by direct experimentation, since static analysis alone
-- per the issue's own investigation comment -- could not find an in-memory
reset of session_state.initialized):

    src/flextoolsmcp/server.py physically lives at src/flextoolsmcp/server.py,
    a SIBLING of the src/flextoolsmcp/server/ package. flextoolsmcp/server/
    __init__.py lazily loads server.py (for backward-compat symbols like
    `run`, `main`, `APIIndex`) via importlib.util.spec_from_file_location
    under the dotless name "_server_module". A dotless module name gives
    __package__ == "" (falsy), so server.py's own `if __package__: ... else:
    ...` branches all took the SCRIPT-MODE path (`from server.kernel import
    ...`), which imports the top-level `server` package (resolved via
    sys.path, NOT `flextoolsmcp.server`) and re-executes server/kernel.py
    under sys.modules key "server.kernel" -- a SECOND, disconnected
    `SessionState()` singleton from the one flextoolsmcp.server.kernel
    already created when `flextoolsmcp.server` (the real package) was first
    imported.

    Depending on which tree a given code path ends up touching, a session
    configured via one singleton is invisible to reads against the other --
    this is the split-brain behind #10.

Fix: flextoolsmcp/server/__init__.py's lazy loader now sets
`_server_module.__package__ = "flextoolsmcp"` before exec (matching
server.py's real on-disk location, a sibling of the server/ package). This
makes server.py's own `if __package__:` branches take the RELATIVE-import
path, which resolves `.server.kernel` to the REAL `flextoolsmcp.server.kernel`
-- collapsing back to a single singleton.

These tests do NOT require a live FieldWorks installation.
"""

import asyncio
import importlib
import json

import pytest


def _flextoolsmcp_server_package():
    """Import flextoolsmcp.server (reusing whatever pytest's collection of
    other test modules already cached in sys.modules -- deliberately NOT
    deleting/reimporting the package tree here, since that would create a
    second generation of module objects that diverge from references other
    test files already bound at their own import time, reintroducing the
    exact split-brain this suite guards against).
    """
    return importlib.import_module("flextoolsmcp.server")


class TestSingletonCollapse:
    """Direct regression test for the dual-SessionState-singleton bug."""

    def test_lazy_loaded_server_module_reuses_package_session_state(self):
        """Accessing flextoolsmcp.server.run (or .main, .APIIndex, ...)
        triggers the lazy loader in server/__init__.py's __getattr__. The
        resulting module's session_state must be IDENTICAL (is, not ==) to
        flextoolsmcp.server.kernel.session_state -- not a second object.
        """
        pkg = _flextoolsmcp_server_package()
        pkg_session_state_before = pkg.session_state

        # Trigger the lazy loader (this used to create a second singleton).
        _run = pkg.run
        _main = pkg.main

        import flextoolsmcp.server.handlers.admin as pkg_admin
        import flextoolsmcp.server.handlers.execution as pkg_exec

        assert pkg.session_state is pkg_session_state_before, (
            "flextoolsmcp.server.session_state was rebound by the lazy load "
            "-- the package-mode singleton itself must never change identity."
        )
        assert pkg_admin.session_state is pkg.session_state, (
            "admin.py's session_state diverged from the package singleton "
            "after the lazy legacy-server load -- this is the #10 split-brain."
        )
        assert pkg_exec.session_state is pkg.session_state, (
            "execution.py's session_state diverged from the package "
            "singleton after the lazy legacy-server load -- this is the "
            "#10 split-brain."
        )

    def test_legacy_module_package_is_flextoolsmcp(self):
        """The dynamically-loaded server.py module must carry
        __package__ == 'flextoolsmcp' -- matching its real on-disk location
        as a sibling of the server/ package -- so its own conditional
        imports resolve against the real package instead of a synthetic
        top-level 'server' name."""
        pkg = _flextoolsmcp_server_package()
        _ = pkg.run  # trigger lazy load
        legacy_mod = pkg._server_module_cache
        assert legacy_mod is not None
        assert legacy_mod.__package__ == "flextoolsmcp"

    def test_repeated_attribute_access_reuses_cached_module(self):
        """The lazy loader must not re-exec server.py (and therefore not
        recreate the collapsed singleton) on every attribute access."""
        pkg = _flextoolsmcp_server_package()
        _ = pkg.run
        first_cache = pkg._server_module_cache
        _ = pkg.main
        _ = pkg.APIIndex
        assert pkg._server_module_cache is first_cache


class TestConsecutiveRunModuleCalls:
    """End-to-end regression: two run_module calls back-to-back, no
    flextools_start between them, must not resurface 'Session not
    initialized' -- the exact symptom reported in #10.
    """

    @pytest.fixture(autouse=True)
    def _bypass_project_resolution(self, monkeypatch):
        """Synthetic project names don't exist on the test host; bypass the
        fuzzy resolver so any name is accepted (mirrors test_undo_wiring.py).
        """
        def _passthrough(project_name):
            return project_name, None

        import flextoolsmcp.server.handlers.execution as exec_mod
        import flextoolsmcp.server.handlers.admin as admin_mod
        monkeypatch.setattr(exec_mod, "resolve_or_explain", _passthrough, raising=False)
        monkeypatch.setattr(admin_mod, "resolve_or_explain", _passthrough, raising=False)

    @pytest.fixture(autouse=True)
    def _isolate_session_state(self):
        """This class mutates the process-wide flextoolsmcp.server.kernel
        session_state singleton (by design -- that's what it's testing).
        Save and restore it so other test files in the same pytest run don't
        see a leaked project/write_enabled/initialized state afterward."""
        import flextoolsmcp.server.handlers.execution as exec_mod
        from flextoolsmcp.server.session import SessionState

        saved = exec_mod.session_state
        try:
            yield
        finally:
            # Restore in place (same object identity other modules hold a
            # reference to) rather than rebinding the module attribute --
            # rebinding would NOT propagate to admin.py/server.py's own
            # already-imported references to the same object.
            saved.__dict__.clear()
            saved.__dict__.update(SessionState().__dict__)

    def test_second_run_module_survives_a_failed_first_run(self):
        """Open a session, run a script that fails preflight (syntax error --
        the cheapest reliable way to fail without needing live FieldWorks),
        then run a second (also-preflight-only) script. The second call must
        NOT see 'Session not initialized' -- the session survives the first
        call's failure, exactly as #10's suggested test describes."""
        import flextoolsmcp.server.handlers.admin as admin_mod
        import flextoolsmcp.server.handlers.execution as exec_mod
        from flextoolsmcp.server.kernel import (
            initialize_kernel, set_api_index, get_index_dir,
        )
        from flextoolsmcp.server import APIIndex

        initialize_kernel()
        set_api_index(APIIndex.load(get_index_dir()))

        start_args = {
            "api_mode": "flexicon",
            "project_name": "Issue10TestProject",
            "output_type": "auto",
            "write_enabled": False,
            "undoable": False,
            "_user_provided_keys": {"project_name", "write_enabled", "undoable"},
        }
        start_result = asyncio.run(admin_mod.handle_start(start_args))
        start_data = json.loads(start_result[0].text)
        assert start_data.get("session", {}).get("initialized") is True or \
            exec_mod.session_state.initialized is True

        # First call: deliberately broken syntax -- fails at the earliest
        # preflight gate (ast.parse), never touches a subprocess/live FLEx.
        first = asyncio.run(exec_mod.handle_run_module({
            "code": "def Main(project, report, modifyAllowed:\n    pass",  # SyntaxError
            "project_name": "Issue10TestProject",
        }))
        first_data = json.loads(first[0].text)
        assert first_data.get("error_code") == "syntax_error" or "error" in first_data

        # Session must still be initialized after the failed first call.
        assert exec_mod.session_state.initialized is True, (
            "session_state.initialized flipped to False after a failing "
            "run_module call -- this is exactly the #10 symptom."
        )

        # Second call: also preflight-only (validate_only=True), but the key
        # assertion is simply that it does not get the generic
        # 'Session not initialized' rejection that #10 describes.
        second = asyncio.run(exec_mod.handle_run_module({
            "code": "report.Info('hello')",
            "project_name": "Issue10TestProject",
            "validate_only": True,
        }))
        second_data = json.loads(second[0].text)
        assert second_data.get("error") != "Session not initialized"
        assert second_data.get("error_code") != "session_not_initialized"
        assert exec_mod.session_state.initialized is True
