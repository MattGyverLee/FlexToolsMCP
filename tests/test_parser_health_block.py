#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for T008 (parser-check CP1): the `parser` block on `flextools_health`.

Authority: specs/parser-check/contracts/flextools_health-parser-block.md and
specs/parser-check/data-model.md ("ParserDetector return shape"). See
tasks.md T008.

STATUS AT WRITE TIME: RED BY DESIGN. `_build_parser_block()`
(src/flextoolsmcp/server/handlers/diagnostic_health.py) and
`parser_probe.ParserDetector` (src/flextoolsmcp/server/parser_probe.py) land
at T009-T013, strictly after this file. Every test below either fails an
assertion against the *current* (parser-less) response, or fails at
monkeypatch time with AttributeError because `diagnostic_health.py` does not
yet import a name called `ParserDetector`. That is the declared tests-first
wave order (tasks.md "US1 wave" table), not a defect.

No `pytest.mark.xfail` / skip-guard precedent exists in this repo for
"test written ahead of its implementation" (grepped the suite before
writing this file). These are therefore plain, ordinary tests that are
expected to fail until T012/T013 land -- each one imports/patches lazily
inside its own test body (matching TestHandleFlexToolsHealth._run's
existing local-import style in test_flextools_health.py) so a missing name
fails that one test with a clear AttributeError/KeyError, not a
whole-file collection error.

CONTRACT AMBIGUITY (documented, not resolved here): the contract and
data-model docs pin the *shape* `_build_parser_block()` must emit, and pin
`ParserDetector`'s field names, but do not pin how `diagnostic_health.py`
obtains a `ParserDetector` instance (constructor signature, eager vs. lazy
detection). This file assumes -- mirroring the existing precedent of
`dh.get_index_dir` / `dh.detect_installed_library_version` being patched as
names already imported into `diagnostic_health`'s own namespace -- that
T012 will do `from ..parser_probe import ParserDetector` and construct it
with no required positional args, exposing `read_probe`, `write_probe`,
`sandbox_probe` (`{hc, generate_config}`), `agent_probe`, `active_engine`,
`versions` as attributes immediately (eager detection). Tests patch
`dh.ParserDetector` to a zero-arg-tolerant factory returning a fully
controlled fake. If T012 instead calls a bare module-level function, only
the `_patch_detector()` helper below needs to change -- every shape
assertion is independent of this choice.

Where the exact JSON *location* of `next_step` content is not nailed down
by the contract (nested per-spine vs. a new top-level `next_step(s)` key),
tests search the whole response recursively (`_find_all`) rather than
asserting a specific path -- this is also literally how the task describes
the invariant ("assert that no next_step anywhere contains the substring
flextools_try_word").
"""

from __future__ import annotations

import asyncio
import itertools
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, List, Optional

import pytest

from fixtures.parser_check import (
    COMPLETE_SAME_INSTALL_PARSER_CORE,
    MISSING_PROCESS_PARSE_PARSER_CORE,
    FOREIGN_DIRECTORY_PARSER_CORE,
)


# ---------------------------------------------------------------------------
# Fakes for parser_probe.ParserDetector's pinned return shape
# (data-model.md "ParserDetector return shape" / "ProbeResult" / "AgentProbeState")
# ---------------------------------------------------------------------------

HC_EXPECTED_PATH = "hc (dotnet global tool, PATH / `dotnet tool list -g`)"
GENERATE_CONFIG_EXPECTED_PATH = (
    r"C:\Program Files\SIL\FieldWorks 9\GenerateHCConfig.exe"
)
HC_INSTALL_HINT = "dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool"


@dataclass
class FakeProbeResult:
    """Stand-in for parser_probe.ProbeResult (data-model.md)."""

    ok: bool
    signal: Optional[str] = None
    expected_path: Optional[str] = None
    missing_members: List[str] = field(default_factory=list)
    detected_version: Optional[str] = None
    load_error: Optional[str] = None


@dataclass
class FakeSandboxProbe:
    hc: FakeProbeResult
    generate_config: FakeProbeResult


@dataclass
class FakeAgentProbe:
    """Stand-in for AgentProbeState plus its {agent_guid, active_engine}
    companions, bundled the way data-model.md's ParserDetector table
    describes ("agent_probe: AgentProbeState plus {agent_guid,
    active_engine} when absent")."""

    state: str  # "present" | "absent" | "skipped"
    agent_guid: Optional[str] = None
    active_engine: Optional[str] = None


@dataclass
class FakeVersions:
    parser_core_version: Optional[str] = None
    lcmodel_install_path: Optional[str] = None
    hc_tool_version: Optional[str] = None


@dataclass
class FakeParserDetector:
    read_probe: FakeProbeResult
    write_probe: FakeProbeResult
    sandbox_probe: FakeSandboxProbe
    agent_probe: FakeAgentProbe
    active_engine: Optional[str] = None
    versions: FakeVersions = field(default_factory=FakeVersions)


def _probe(ok, signal=None, expected_path="C:\\fake\\ParserCore.dll",
           missing_members=None, detected_version=None, load_error=None):
    return FakeProbeResult(
        ok=ok,
        signal=signal,
        expected_path=expected_path,
        missing_members=list(missing_members or []),
        detected_version=detected_version,
        load_error=load_error,
    )


def _sandbox(hc_ok=True, generate_config_ok=True):
    return FakeSandboxProbe(
        hc=_probe(hc_ok, expected_path=HC_EXPECTED_PATH, signal=None if hc_ok else "absent"),
        generate_config=_probe(
            generate_config_ok,
            expected_path=GENERATE_CONFIG_EXPECTED_PATH,
            signal=None if generate_config_ok else "absent",
        ),
    )


def _detector(
    read_ok=True,
    write_ok=True,
    read_signal=None,
    write_signal=None,
    write_missing_members=None,
    sandbox_hc_ok=True,
    sandbox_generate_config_ok=True,
    agent_state="skipped",
    agent_guid=None,
    active_engine=None,
):
    return FakeParserDetector(
        read_probe=_probe(read_ok, signal=read_signal),
        write_probe=_probe(write_ok, signal=write_signal, missing_members=write_missing_members),
        sandbox_probe=_sandbox(sandbox_hc_ok, sandbox_generate_config_ok),
        agent_probe=FakeAgentProbe(state=agent_state, agent_guid=agent_guid, active_engine=active_engine),
        active_engine=active_engine,
        versions=FakeVersions(),
    )


def _patch_detector(monkeypatch, dh, detector):
    """See module docstring's "CONTRACT AMBIGUITY" note for the assumption
    this encodes: dh.ParserDetector, called with no required args, returns
    an object exposing the ParserDetector return shape as attributes."""
    monkeypatch.setattr(dh, "ParserDetector", lambda *a, **kw: detector)


_STUB_INDEX_SEQ = itertools.count()


def _stub_index_dir(tmp_path):
    """An empty, per-call stub index dir whose PATH STRING cannot contain a
    tool name.

    pytest derives tmp_path's own name from the test function's name, so
    e.g. test_flextools_try_word_never_appears_* gets a tmp_path literally
    containing "flextools_try_word" -- and flextools_health echoes its
    index dir back at indexes.index_dir. Feeding tmp_path straight in would
    make the whole-response substring assertions below ("flextools_try_word
    not in json.dumps(data)") fail on the fixture's own directory name
    rather than on anything the handler said, i.e. unpassable regardless of
    the implementation. Using a sibling directory under tmp_path.parent
    keeps the per-call isolation (nothing is ever written here; the handler
    only scans it) while dropping the test name from the string.
    """
    return tmp_path.parent / "stub-index-{}".format(next(_STUB_INDEX_SEQ))


def _run_health(monkeypatch, tmp_path, detector, args=None):
    import server.handlers.diagnostic_health as dh

    index_dir = _stub_index_dir(tmp_path)
    monkeypatch.setattr(dh, "get_index_dir", lambda: index_dir)
    monkeypatch.setattr(dh, "detect_installed_library_version", lambda *a, **kw: None)
    _patch_detector(monkeypatch, dh, detector)

    result = asyncio.run(dh.handle_flextools_health(args or {"verbose": False}))
    return json.loads(result[0].text)


def _find_all(obj: Any, key: str) -> List[Any]:
    """Recursively collect every value found anywhere under dict key `key`,
    regardless of nesting depth or which parent object holds it -- used so
    "next_step never names X" assertions don't depend on guessing where in
    the response next_step content ends up (contract does not pin this)."""
    found: List[Any] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                found.append(v)
            found.extend(_find_all(v, key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_all(item, key))
    return found


# ---------------------------------------------------------------------------
# Exactly two states per spine -- never a third "degraded" value
# ---------------------------------------------------------------------------

class TestExactlyTwoStatesPerSpine:
    @pytest.mark.parametrize(
        "read_ok,write_ok,hc_ok,gc_ok",
        [
            (True, True, True, True),
            (False, False, True, True),
            (True, False, True, True),
            (True, True, False, True),
            (True, True, True, False),
            (True, True, False, False),
            (False, False, False, False),
        ],
    )
    def test_only_ready_or_unavailable(self, monkeypatch, tmp_path, read_ok, write_ok, hc_ok, gc_ok):
        detector = _detector(
            read_ok=read_ok, write_ok=write_ok,
            read_signal=None if read_ok else "absent",
            write_signal=None if write_ok else "absent",
            sandbox_hc_ok=hc_ok, sandbox_generate_config_ok=gc_ok,
        )
        data = _run_health(monkeypatch, tmp_path, detector)
        parser = data["parser"]

        assert parser["read"]["status"] in ("ready", "unavailable")
        assert parser["write"]["status"] in ("ready", "unavailable")
        assert parser["sandbox"]["status"] in ("ready", "unavailable")

        # Belt-and-suspenders literal check: "degraded" must never appear
        # anywhere in the serialized parser block.
        assert "degraded" not in json.dumps(parser)

    def test_sandbox_ready_only_when_both_components_found(self, monkeypatch, tmp_path):
        detector = _detector(sandbox_hc_ok=True, sandbox_generate_config_ok=False)
        data = _run_health(monkeypatch, tmp_path, detector)
        assert data["parser"]["sandbox"]["status"] == "unavailable"

        detector = _detector(sandbox_hc_ok=True, sandbox_generate_config_ok=True)
        data = _run_health(monkeypatch, tmp_path, detector)
        assert data["parser"]["sandbox"]["status"] == "ready"


# ---------------------------------------------------------------------------
# One dead spine must not blank the other two
# ---------------------------------------------------------------------------

class TestOneDeadSpineDoesNotBlankOthers:
    def test_sandbox_unavailable_leaves_read_and_write_ready(self, monkeypatch, tmp_path):
        detector = _detector(
            read_ok=True, write_ok=True,
            sandbox_hc_ok=False, sandbox_generate_config_ok=False,
        )
        data = _run_health(monkeypatch, tmp_path, detector)
        parser = data["parser"]
        assert parser["sandbox"]["status"] == "unavailable"
        assert parser["read"]["status"] == "ready"
        assert parser["write"]["status"] == "ready"

    def test_read_unavailable_leaves_write_and_sandbox_untouched(self, monkeypatch, tmp_path):
        # Independently-controlled fakes: this composition-level test checks
        # that _build_parser_block() reports each spine from its own probe,
        # not that a real detector would ever produce this exact
        # combination (that invariant belongs to parser_probe's own tests).
        detector = _detector(
            read_ok=False, read_signal="absent",
            write_ok=True,
            sandbox_hc_ok=True, sandbox_generate_config_ok=True,
        )
        data = _run_health(monkeypatch, tmp_path, detector)
        parser = data["parser"]
        assert parser["read"]["status"] == "unavailable"
        assert parser["write"]["status"] == "ready"
        assert parser["sandbox"]["status"] == "ready"

    def test_write_unavailable_leaves_read_and_sandbox_ready(self, monkeypatch, tmp_path):
        detector = _detector(
            read_ok=True,
            write_ok=False, write_signal="incompatible_surface",
            write_missing_members=["ParseFiler.ProcessParse"],
            sandbox_hc_ok=True, sandbox_generate_config_ok=True,
        )
        data = _run_health(monkeypatch, tmp_path, detector)
        parser = data["parser"]
        assert parser["write"]["status"] == "unavailable"
        assert parser["read"]["status"] == "ready"
        assert parser["sandbox"]["status"] == "ready"


# ---------------------------------------------------------------------------
# read: ready / write: unavailable exactly when ParseFiler.ProcessParse is
# the only missing member (uses the T002 fixtures)
# ---------------------------------------------------------------------------

class TestReadReadyWriteUnavailableOnMissingProcessParse:
    def test_missing_process_parse_only(self, monkeypatch, tmp_path):
        # COMPLETE_SAME_INSTALL_PARSER_CORE / MISSING_PROCESS_PARSE_PARSER_CORE
        # (tests/fixtures/parser_check.py) model exactly this: full HCParser
        # surface present in both, ParseFiler.ProcessParse present only in
        # the "complete" one.
        assert COMPLETE_SAME_INSTALL_PARSER_CORE.members - MISSING_PROCESS_PARSE_PARSER_CORE.members == {
            "ParseFiler.ProcessParse"
        }

        detector = _detector(
            read_ok=True,
            write_ok=False,
            write_signal="incompatible_surface",
            write_missing_members=["ParseFiler.ProcessParse"],
        )
        data = _run_health(monkeypatch, tmp_path, detector)
        parser = data["parser"]

        assert parser["read"]["status"] == "ready"
        assert parser["read"]["reason"] is None

        assert parser["write"]["status"] == "unavailable"
        write_reason = parser["write"]["reason"]
        assert write_reason is not None
        assert write_reason["signal"] == "incompatible_surface"
        assert write_reason["missing_members"] == ["ParseFiler.ProcessParse"]

    def test_foreign_install_signal_round_trips(self, monkeypatch, tmp_path):
        # FOREIGN_DIRECTORY_PARSER_CORE: full surface, resolved from a
        # different FieldWorks install than SIL.LCModel.dll.
        assert not FOREIGN_DIRECTORY_PARSER_CORE.same_install

        detector = _detector(read_ok=False, read_signal="foreign_install", write_ok=False, write_signal="foreign_install")
        data = _run_health(monkeypatch, tmp_path, detector)
        parser = data["parser"]
        assert parser["read"]["status"] == "unavailable"
        assert parser["read"]["reason"]["signal"] == "foreign_install"


# ---------------------------------------------------------------------------
# reason shape: read/write's base fields, write's extra agent_probe fields
# ---------------------------------------------------------------------------

class TestReasonShape:
    _BASE_REASON_KEYS = {"signal", "expected_path", "detected_version", "missing_members", "lcmodel_install_path"}

    def test_read_reason_keys_when_unavailable(self, monkeypatch, tmp_path):
        detector = _detector(read_ok=False, read_signal="absent")
        data = _run_health(monkeypatch, tmp_path, detector)
        reason = data["parser"]["read"]["reason"]
        assert set(reason.keys()) == self._BASE_REASON_KEYS

    def test_write_reason_carries_agent_probe_skipped(self, monkeypatch, tmp_path):
        detector = _detector(write_ok=False, write_signal="absent", agent_state="skipped")
        data = _run_health(monkeypatch, tmp_path, detector)
        reason = data["parser"]["write"]["reason"]
        assert reason is not None
        assert reason["agent_probe"] == "skipped"
        assert set(reason.keys()) >= self._BASE_REASON_KEYS | {"agent_probe"}

    def test_write_reason_carries_agent_guid_and_active_engine_when_absent(self, monkeypatch, tmp_path):
        detector = _detector(
            write_ok=False, write_signal="parser_agent_missing",
            agent_state="absent", agent_guid="kguidAgentHermitCrabParser", active_engine="HC",
        )
        data = _run_health(monkeypatch, tmp_path, detector)
        reason = data["parser"]["write"]["reason"]
        assert reason["agent_probe"] == "absent"
        assert reason["agent_guid"] == "kguidAgentHermitCrabParser"
        assert reason["active_engine"] == "HC"


# ---------------------------------------------------------------------------
# agent_probe: "skipped" is never reported as a pass
# ---------------------------------------------------------------------------

class TestAgentProbeSkippedNeverAPass:
    def test_skipped_agent_does_not_block_a_healthy_write(self, monkeypatch, tmp_path):
        """D2: flextools_health never opens a project, so agent_probe is
        always "skipped" here. write's status is decided by the member
        probe ALONE -- a skipped agent probe must not force write
        unavailable."""
        detector = _detector(write_ok=True, agent_state="skipped")
        data = _run_health(monkeypatch, tmp_path, detector)
        write = data["parser"]["write"]
        assert write["status"] == "ready"

    def test_skipped_agent_is_always_visible_in_the_reason_never_silently_a_pass(self, monkeypatch, tmp_path):
        """The invariant SPEC 16 tests directly: a skipped probe is never
        REPORTED as a pass. Even though write is "ready" (member probe
        alone decided that), the reason must still literally say
        agent_probe: "skipped" -- not be omitted, not be coerced to a
        pass-shaped value like true/"present"."""
        detector = _detector(write_ok=True, agent_state="skipped")
        data = _run_health(monkeypatch, tmp_path, detector)
        write = data["parser"]["write"]
        assert write["reason"] is not None, (
            "write.reason must not be null even when write is ready: "
            "agent_probe is always skipped at CP1 (D2) and that fact must "
            "stay visible, never silently folded into a bare 'ready'."
        )
        assert write["reason"]["agent_probe"] == "skipped"
        assert write["reason"]["agent_probe"] != "present"
        assert write["reason"]["agent_probe"] is not True

    def test_skipped_agent_with_failing_member_probe_is_unavailable(self, monkeypatch, tmp_path):
        detector = _detector(write_ok=False, write_signal="absent", agent_state="skipped")
        data = _run_health(monkeypatch, tmp_path, detector)
        write = data["parser"]["write"]
        assert write["status"] == "unavailable"
        assert write["reason"]["agent_probe"] == "skipped"


# ---------------------------------------------------------------------------
# active_engine never decides a status
# ---------------------------------------------------------------------------

class TestActiveEngineNeverDecidesStatus:
    @pytest.mark.parametrize("active_engine", [None, "XAmple", "HC"])
    def test_status_unaffected_by_active_engine_value(self, monkeypatch, tmp_path, active_engine):
        detector = _detector(read_ok=True, write_ok=True, sandbox_hc_ok=True, sandbox_generate_config_ok=True, active_engine=active_engine)
        data = _run_health(monkeypatch, tmp_path, detector)
        parser = data["parser"]
        assert parser["read"]["status"] == "ready"
        assert parser["write"]["status"] == "ready"
        assert parser["sandbox"]["status"] == "ready"

    def test_active_engine_null_by_default_at_cp1(self, monkeypatch, tmp_path):
        """T032's D-note: flextools_health never opens a project (D2), so
        active_engine is unconditionally null at CP1 in the real detection
        path. This is the shape the contract's example literally shows."""
        detector = _detector(active_engine=None)
        data = _run_health(monkeypatch, tmp_path, detector)
        assert data["parser"]["active_engine"] is None


# ---------------------------------------------------------------------------
# next_step: never names flextools_try_word, never names a tool whose
# spine is unavailable, never proposes flextools_parse_sandbox when a
# sandbox component is missing; CP1's literal degraded-action-text row
# ---------------------------------------------------------------------------

class TestNextStepCP1Degradation:
    def test_flextools_try_word_never_appears_anywhere_read_unavailable(self, monkeypatch, tmp_path):
        detector = _detector(read_ok=False, read_signal="absent", write_ok=False, write_signal="absent")
        data = _run_health(monkeypatch, tmp_path, detector)
        assert "flextools_try_word" not in json.dumps(data)

    def test_flextools_try_word_never_appears_write_unavailable_read_ready(self, monkeypatch, tmp_path):
        detector = _detector(
            read_ok=True,
            write_ok=False, write_signal="incompatible_surface",
            write_missing_members=["ParseFiler.ProcessParse"],
        )
        data = _run_health(monkeypatch, tmp_path, detector)
        blob = json.dumps(data)
        assert "flextools_try_word" not in blob

        # CP1's literal replacement action text for this exact row
        # (contracts/flextools_health-parser-block.md, "next_step per
        # unhealthy state"; tasks.md T013). Names no tool.
        assert (
            "filing is unavailable on this install; read-only parser "
            "diagnosis is unaffected."
        ) in blob

    def test_flextools_try_word_never_appears_agent_missing_row(self, monkeypatch, tmp_path):
        detector = _detector(
            read_ok=True,
            write_ok=False, write_signal="parser_agent_missing",
            agent_state="absent", agent_guid="kguidAgentHermitCrabParser", active_engine="HC",
        )
        data = _run_health(monkeypatch, tmp_path, detector)
        assert "flextools_try_word" not in json.dumps(data)

    def test_flextools_parse_sandbox_never_proposed_when_hc_missing(self, monkeypatch, tmp_path):
        detector = _detector(sandbox_hc_ok=False, sandbox_generate_config_ok=True)
        data = _run_health(monkeypatch, tmp_path, detector)
        assert "flextools_parse_sandbox" not in json.dumps(data)

    def test_flextools_parse_sandbox_never_proposed_when_generate_config_missing(self, monkeypatch, tmp_path):
        detector = _detector(sandbox_hc_ok=True, sandbox_generate_config_ok=False)
        data = _run_health(monkeypatch, tmp_path, detector)
        assert "flextools_parse_sandbox" not in json.dumps(data)

    def test_hc_install_hint_is_the_literal_string(self, monkeypatch, tmp_path):
        detector = _detector(sandbox_hc_ok=False, sandbox_generate_config_ok=True)
        data = _run_health(monkeypatch, tmp_path, detector)
        assert HC_INSTALL_HINT in json.dumps(data)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"read_ok": False, "read_signal": "absent", "write_ok": False, "write_signal": "absent"},
            {"write_ok": False, "write_signal": "incompatible_surface", "write_missing_members": ["ParseFiler.ProcessParse"]},
            {"sandbox_hc_ok": False},
            {"sandbox_generate_config_ok": False},
        ],
    )
    def test_no_tool_key_anywhere_names_a_real_tool_at_cp1(self, monkeypatch, tmp_path, kwargs):
        """At CP1 no next_step row has a real tool to propose (both rows
        that would name one degrade to tool: null per the contract's CP1
        caveat) -- so every "tool" value found anywhere in the response
        must be null, for every degraded combination."""
        detector = _detector(**kwargs)
        data = _run_health(monkeypatch, tmp_path, detector)
        for tool_value in _find_all(data, "tool"):
            assert tool_value is None


# ---------------------------------------------------------------------------
# sandbox.components: closed enum, array shape
# ---------------------------------------------------------------------------

class TestSandboxComponentsShape:
    def test_components_is_an_array_of_closed_enum_entries(self, monkeypatch, tmp_path):
        detector = _detector(sandbox_hc_ok=False, sandbox_generate_config_ok=True)
        data = _run_health(monkeypatch, tmp_path, detector)
        components = data["parser"]["sandbox"]["components"]

        assert isinstance(components, list)
        assert len(components) == 2

        names = {c["component"] for c in components}
        assert names == {"hc", "GenerateHCConfig.exe"}

        for c in components:
            assert set(c.keys()) == {"component", "found", "expected_path"}

        by_name = {c["component"]: c for c in components}
        assert by_name["hc"]["found"] is False
        assert by_name["GenerateHCConfig.exe"]["found"] is True


# ---------------------------------------------------------------------------
# Full "detected" block shape (contract Shape section, literal)
# ---------------------------------------------------------------------------

class TestParserBlockFullShape:
    def test_top_level_parser_keys(self, monkeypatch, tmp_path):
        detector = _detector()
        data = _run_health(monkeypatch, tmp_path, detector)
        parser = data["parser"]
        assert set(parser.keys()) == {"read", "write", "sandbox", "active_engine", "detected"}
        assert set(parser["detected"].keys()) == {
            "parser_core_version",
            "lcmodel_install_path",
            "hc_tool_version",
            "hc_path",
            "generate_hc_config_path",
        }

    def test_detected_never_decides_a_status(self, monkeypatch, tmp_path):
        """detected.parser_core_version is reported, never compared against
        a floor -- an "unexpected" version string must not flip read/write
        to unavailable on its own."""
        detector = _detector(read_ok=True, write_ok=True)
        detector.versions.parser_core_version = "0.0.1-totally-unexpected"
        data = _run_health(monkeypatch, tmp_path, detector)
        parser = data["parser"]
        assert parser["read"]["status"] == "ready"
        assert parser["write"]["status"] == "ready"
        assert parser["detected"]["parser_core_version"] == "0.0.1-totally-unexpected"


# ---------------------------------------------------------------------------
# SPEC 16 "Integration (Windows + FieldWorks, no `hc` tool)" -- named
# integration test, skipped automatically off Windows / without FieldWorks
# / when hc happens to be installed on this machine (the scenario requires
# its absence to hold).
# ---------------------------------------------------------------------------

def _fieldworks_installed() -> bool:
    try:
        from server.versioning import get_resolved_fieldworks_dir
    except Exception:
        return False
    try:
        return get_resolved_fieldworks_dir() is not None
    except Exception:
        return False


def _hc_tool_installed() -> bool:
    """Best-effort local check (not the production detector -- T010 owns
    that): `hc` is a dotnet global tool, so look for it via `dotnet tool
    list -g`. Any failure (dotnet itself missing, timeout) is treated as
    "not installed", which is the condition this integration test wants."""
    dotnet = shutil.which("dotnet")
    if dotnet is None:
        return False
    try:
        proc = subprocess.run(
            [dotnet, "tool", "list", "-g"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        return False
    return "hermitcrab" in proc.stdout.lower()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only per SPEC 16")
@pytest.mark.skipif(not _fieldworks_installed(), reason="requires a real FieldWorks install on this machine")
@pytest.mark.skipif(_hc_tool_installed(), reason="scenario requires the hc dotnet tool to be ABSENT")
class TestIntegrationWindowsFieldWorksNoHcTool:
    """SPEC 16, "Integration (Windows + FieldWorks, no `hc` tool)": on a
    real machine with FieldWorks installed and no `hc` dotnet tool, the
    sandbox spine reports unavailable with the real `dotnet tool install`
    hint while the in-process spines (read, write) report ready.

    READ-ONLY: this is exactly a flextools_health call -- no HCParser
    constructed, no LcmCache opened, no project written to (CP1's
    READ_ONLY_SAFE annotation, same as every other health call)."""

    def test_sandbox_unavailable_in_process_spines_ready(self):
        import server.handlers.diagnostic_health as dh

        result = asyncio.run(dh.handle_flextools_health({"verbose": False}))
        data = json.loads(result[0].text)
        parser = data["parser"]

        assert parser["sandbox"]["status"] == "unavailable"
        assert parser["read"]["status"] == "ready"
        assert parser["write"]["status"] == "ready"
        assert HC_INSTALL_HINT in json.dumps(data)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
