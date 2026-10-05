#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #322: an unreadable `hcparse.ps1` is a `sandbox_unavailable` envelope,
never a HANDLER EXCEPTION.

The packaged script is read from two places: `_sandbox_create` awaits
`cache.ensure_entry` directly in the handler (the logged incident's path --
`key_inputs` -> `script.read_hcparse_version` raised `HcparseVersionError`
straight into the dispatch wrapper), and `SandboxClient._resolve_config`
reads it for the parse/run_corpus run path. Both now convert the
unreadable-script case into the named `sandbox_unavailable` failure; the
create path returns the envelope with next_steps, the run path raises
`SandboxRunError(error_code="sandbox_unavailable")` so the runner records a
named terminal failure instead of an unhandled exception.

Offline; the script is never executed. The unreadable state is emulated by
raising `HcparseVersionError` at the seams (the real error when the file is
missing is `HcparseVersionError("Cannot read ...: [Errno 2] ...")`).
"""

import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.handlers.parse import sandbox as sandbox_handler  # noqa: E402
from flextoolsmcp.server.handlers.parse import sandbox_checks  # noqa: E402
from flextoolsmcp.server.handlers.parse.sandbox_checks import _SANDBOX_FAILURE_CODES  # noqa: E402
from flextoolsmcp.server.models import ParseSandboxInput  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.sandbox import cache as sandbox_cache  # noqa: E402
from flextoolsmcp.server.sandbox import script as sandbox_script  # noqa: E402
from flextoolsmcp.server.sandbox import workdir as sandbox_workdir  # noqa: E402
from flextoolsmcp.server.sandbox.client import (  # noqa: E402
    SandboxClient,
    SandboxRunError,
)

MISSING = (
    "Cannot read C:\\Github\\FlexToolsMCP\\src\\flextoolsmcp\\scripts\\hcparse.ps1: "
    "[Errno 2] No such file or directory"
)


def _plan(project="FakeProj", name="tighten-env"):
    request = ParseSandboxInput(
        action="create_sandbox", project_name=project, sandbox=name
    )
    plan = sandbox_checks._SandboxPlan(request=request, project_name=project)
    plan.generator = types.SimpleNamespace(expected_path="C:\\FW\\GenerateHCConfig.exe")
    return plan


@pytest.fixture
def broken_create(monkeypatch, tmp_path):
    """`_sandbox_create` with `ensure_entry` raising the logged error."""
    fwdata = tmp_path / "FakeProj.fwdata"
    fwdata.write_bytes(b"fake")
    monkeypatch.setattr(
        sandbox_checks, "_sandbox_fwdata_path", lambda project: fwdata
    )
    monkeypatch.setattr(sandbox_workdir, "create", lambda op_id, **kw: tmp_path / "work")
    monkeypatch.setattr(
        sandbox_workdir, "delete", lambda target: None
    )

    async def ensure_entry(*args, **kwargs):
        raise sandbox_script.HcparseVersionError(MISSING)

    monkeypatch.setattr(sandbox_cache, "ensure_entry", ensure_entry)
    return _plan()


class TestCreateSandboxUnavailable:
    async def test_returns_sandbox_unavailable_envelope(self, broken_create):
        # Regression: this used to escape as HANDLER EXCEPTION -> internal_error.
        payload = json.loads((await sandbox_handler._sandbox_create(broken_create))[0].text)
        assert payload["status"] == "error", payload
        assert payload["error_code"] == "sandbox_unavailable", payload

    async def test_envelope_carries_script_path_hint_and_null_run_id(
        self, broken_create
    ):
        payload = json.loads((await sandbox_handler._sandbox_create(broken_create))[0].text)
        assert payload["script_path"].endswith("hcparse.ps1"), payload
        assert payload["hint"], payload
        assert "reinstall" in payload["hint"].lower() or "repair" in payload["hint"].lower()
        assert payload["run_id"] is None, "create_sandbox issues no run id"

    async def test_envelope_carries_next_steps(self, broken_create):
        payload = json.loads((await sandbox_handler._sandbox_create(broken_create))[0].text)
        steps = payload.get("next_step")
        assert isinstance(steps, list) and steps, payload
        for step in steps:
            assert step.get("est_cost"), f"rung without est_cost: {step}"
        assert any(s.get("tool") == "flextools_health" for s in steps), steps


class TestResolveConfigUnavailable:
    async def test_converts_to_named_run_error(self, monkeypatch):
        async def boom(self):
            raise sandbox_script.HcparseVersionError(MISSING)

        monkeypatch.setattr(SandboxClient, "_resolve_config_inner", boom)
        client = SandboxClient.__new__(SandboxClient)
        client.run_id = "run-xyz"
        with pytest.raises(SandboxRunError) as exc_info:
            await client._resolve_config()
        err = exc_info.value
        assert err.error_code == "sandbox_unavailable"
        assert err.detail["error_code"] == "sandbox_unavailable"
        assert err.detail["script_path"].endswith("hcparse.ps1")
        assert err.detail["run_id"] == "run-xyz"
        assert err.detail["hint"]

    async def test_key_inputs_raise_site_is_covered(self, monkeypatch):
        # The direct `cache.key_inputs(...)` call in `_resolve_config_inner`
        # (not just `ensure_entry`) raises the same error; the wrapper must
        # convert it too. Patch key_inputs to raise and give the inner method
        # a just-enough launch object.
        monkeypatch.setattr(
            sandbox_cache, "key_inputs",
            lambda *a, **k: (_ for _ in ()).throw(
                sandbox_script.HcparseVersionError(MISSING)
            ),
        )

        async def fake_inner(self):
            sandbox_cache.key_inputs("fwdata", "gen")

        monkeypatch.setattr(SandboxClient, "_resolve_config_inner", fake_inner)
        client = SandboxClient.__new__(SandboxClient)
        client.run_id = "run-xyz"
        with pytest.raises(SandboxRunError) as exc_info:
            await client._resolve_config()
        assert exc_info.value.error_code == "sandbox_unavailable"


class TestRunFailurePlumbing:
    def test_code_is_an_envelope_code(self):
        assert "sandbox_unavailable" in _SANDBOX_FAILURE_CODES

    def test_runner_passes_the_client_detail_through(self):
        handle = types.SimpleNamespace(run_id="run-xyz")
        exc = SandboxRunError(
            "The sandbox engine is unavailable.",
            error_code="sandbox_unavailable",
            detail={
                "error_code": "sandbox_unavailable",
                "script_path": "C:\\x\\hcparse.ps1",
                "run_id": None,
                "hint": "reinstall the package",
            },
        )
        detail = ParseRunner._sandbox_failure_detail(handle, exc)
        assert detail["error_code"] == "sandbox_unavailable"
        assert detail["run_id"] == "run-xyz", "the runner fills the run id"
        assert detail["hint"] == "reinstall the package"


class TestScriptShipsAsPackageData:
    def test_script_path_resolves_inside_the_package(self):
        path = sandbox_script.script_path()
        assert path.name == "hcparse.ps1"
        assert path.is_file(), f"packaged script missing at {path}"

    def test_version_reads_from_the_packaged_file(self):
        assert sandbox_script.read_hcparse_version()

    def test_wheel_includes_the_script(self):
        # pyproject's package-data must keep covering the script (the "confirm
        # it ships" half of the issue); the exclusion list must not sweep it.
        import tomllib

        data = tomllib.load(open(REPO_ROOT / "pyproject.toml", "rb"))
        included = data["tool"]["setuptools"]["package-data"]["flextoolsmcp"]
        assert any("ps1" in pattern for pattern in included), included
