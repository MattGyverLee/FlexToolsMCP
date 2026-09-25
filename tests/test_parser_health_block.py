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
import uuid
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

#: parser.sandbox.components[*] keys at CP5 (data-model section 7).
SANDBOX_COMPONENT_KEYS = {
    "component", "found", "expected_path", "starts", "signal", "source", "reason",
}


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
class FakeHcDiscovery(FakeProbeResult):
    """Stand-in for parser_probe.HcToolDiscovery (CP5, T024/T030): a
    ProbeResult plus the discovery fields. ``ok`` is kept equal to
    ``found and starts is True`` by ``_hc()`` below, the invariant the
    real class carries."""

    found: bool = False
    starts: Optional[bool] = None
    source: Optional[str] = None
    path: Optional[str] = None
    reason: Optional[str] = None
    invoke_argv: Optional[List[str]] = None


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
    # CP5 (FR-005, T031): reported, never compared to a floor.
    fieldworks_hermitcrab_version: Optional[str] = None
    generate_hc_config_version: Optional[str] = None
    hc_engine_version_skew: bool = False


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


HC_FOUND_PATH = r"C:\Users\u\.dotnet\tools\hc.exe"


def _hc(found, starts=None, signal=None, source=None, reason=None, path=None):
    """A FakeHcDiscovery with ``ok == (found and starts is True)``.

    A found hc reports its real path as ``expected_path`` (data-model
    section 7's example); an unfound one reports the search description."""
    if found and path is None:
        path = HC_FOUND_PATH
    return FakeHcDiscovery(
        ok=bool(found and starts is True),
        signal=signal,
        expected_path=path if found else HC_EXPECTED_PATH,
        found=found,
        starts=starts,
        source=source,
        path=path if found else None,
        reason=reason,
        invoke_argv=[path] if found else None,
    )


def _hc_ready(source="path"):
    return _hc(True, starts=True, source=source)


def _hc_not_found():
    return _hc(
        False, signal="not_found",
        reason="hc was not found on PATH, in the dotnet tools folder or in `dotnet tool list -g`",
    )


def _sandbox(hc_ok=True, generate_config_ok=True, hc=None):
    if hc is None:
        hc = _hc_ready() if hc_ok else _hc_not_found()
    return FakeSandboxProbe(
        hc=hc,
        generate_config=_probe(
            generate_config_ok,
            expected_path=GENERATE_CONFIG_EXPECTED_PATH,
            signal=None if generate_config_ok else "not_found",
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
    hc=None,
):
    return FakeParserDetector(
        read_probe=_probe(read_ok, signal=read_signal),
        write_probe=_probe(write_ok, signal=write_signal, missing_members=write_missing_members),
        sandbox_probe=_sandbox(sandbox_hc_ok, sandbox_generate_config_ok, hc=hc),
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
# next_step: the two rows that name flextools_try_word LAND IN FULL at CP2b;
# no rung names a tool whose spine is unavailable; flextools_parse_sandbox
# is still never proposed
# ---------------------------------------------------------------------------
#
# AMENDED AT CP2b (FR-038), NOT WEAKENED. CP1 degraded two rows to
# `tool: null` with replacement action prose, because SPEC 10.1 forbids
# proposing a tool that does not exist and `flextools_try_word` did not.
# The CP1 caveat said in as many words that they "land in full at CP2, when
# the tool they name is real". They do, and the tests below now assert the
# landed state.
#
# The underlying rule is UNCHANGED and is now asserted more strongly than
# before, by a registry sweep over every emitted rung rather than by a
# hardcoded "must be null": a rung may name a tool if and only if that tool
# is registered. That is what kept `flextools_try_word` out at CP1 and what
# still keeps `flextools_parse_sandbox` out now.

class TestNextStepRowsThatNameTryWord:
    def test_flextools_try_word_is_still_never_named_when_read_is_unavailable(self, monkeypatch, tmp_path):
        """The rule that held at CP1 and still holds: never name a tool whose
        spine is unavailable.

        This row is UNCHANGED by CP2b. `flextools_try_word` existing does
        not make it usable on an install where ParserCore's read surface
        cannot be resolved -- pointing a caller at it here would send them
        to a tool that cannot run.
        """
        detector = _detector(read_ok=False, read_signal="absent", write_ok=False, write_signal="absent")
        data = _run_health(monkeypatch, tmp_path, detector)
        assert "flextools_try_word" not in json.dumps(data)

    def test_the_write_unavailable_read_ready_row_lands_in_full(self, monkeypatch, tmp_path):
        """CP2b: the row names the tool, in the field AND in the contract's
        own action wording.

        Filing is what is unavailable. A caller should be told the read
        spine is fully usable and by what -- which is the whole substance
        of this row, and the part CP1 had to withhold.
        """
        detector = _detector(
            read_ok=True,
            write_ok=False, write_signal="incompatible_surface",
            write_missing_members=["ParseFiler.ProcessParse"],
        )
        data = _run_health(monkeypatch, tmp_path, detector)

        rows = [
            rung
            for rung in data["parser_next_steps"]
            if rung["tool"] == "flextools_try_word"
        ]
        assert rows, f"the row did not land: {data['parser_next_steps']}"

        # The contract's own wording (SPEC 10.2, copied to
        # contracts/flextools_health-parser-block.md:91).
        assert rows[0]["action"] == "use read-only Try A Word; filing unavailable"

        # And CP1's replacement text is gone -- it existed only to avoid
        # naming a tool that did not exist.
        assert "read-only parser diagnosis is unaffected" not in json.dumps(data)

    def test_the_agent_missing_row_lands_in_full(self, monkeypatch, tmp_path):
        """A missing recording agent does NOT make reading unavailable.

        FR-016. Reading neither records nor needs an agent, so this row
        names the read tool -- which is precisely the boundary CP1 shipped
        the agent probe to protect and had no caller to demonstrate.
        """
        detector = _detector(
            read_ok=True,
            write_ok=False, write_signal="parser_agent_missing",
            agent_state="absent", agent_guid="kguidAgentHermitCrabParser", active_engine="HC",
        )
        data = _run_health(monkeypatch, tmp_path, detector)

        rows = [
            rung
            for rung in data["parser_next_steps"]
            if rung["tool"] == "flextools_try_word"
        ]
        assert rows, f"the row did not land: {data['parser_next_steps']}"
        assert "HermitCrab" in rows[0]["action"]
        assert data["parser"]["read"]["status"] == "ready", (
            "a missing recording agent marked READING unavailable; FR-016 "
            "says it must not"
        )

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
            {"write_ok": False, "write_signal": "parser_agent_missing", "agent_state": "absent"},
            {"sandbox_hc_ok": False},
            {"sandbox_generate_config_ok": False},
        ],
    )
    def test_no_rung_anywhere_names_a_tool_that_does_not_exist(self, monkeypatch, tmp_path, kwargs):
        """SC-011: 0 next_step references to tools that do not exist.

        THIS REPLACES CP1's "every tool value must be null", and is the
        stronger form of the same rule. The old assertion was true only
        because no proposable tool existed yet; it would have had to be
        deleted the moment one did, taking the guarantee with it. Checking
        against the REGISTRY instead means the rule survives every tool this
        project ever adds. (At CP5 `flextools_parse_sandbox` became
        registered; whether it may be named is now FR-006's spine rule,
        asserted in TestSandboxSpineCp5 below.)

        Swept over every unhealthy combination, because a rung reachable
        from only one of them would otherwise escape.
        """
        from flextoolsmcp.server.dispatch import get_all_tool_names

        registered = set(get_all_tool_names())
        detector = _detector(**kwargs)
        data = _run_health(monkeypatch, tmp_path, detector)

        for tool_value in _find_all(data, "tool"):
            assert tool_value is None or tool_value in registered, (
                f"guidance names {tool_value!r}, which is not a registered "
                f"tool (SC-011)"
            )

    def test_the_sweep_would_catch_a_nonexistent_tool(self, monkeypatch, tmp_path):
        """The sweep above, shown to detect something.

        A guarantee asserted only over passing data has not been shown to
        work. This injects a rung naming a tool that does not exist and
        confirms the same check rejects it -- so the sweep is known to be
        load-bearing rather than merely green.

        CP5 (T027): the example used to be `flextools_parse_sandbox`, which
        is now registered (FR-034). The example is now a name that cannot be
        registered, and the test checks that before relying on it.
        """
        from flextoolsmcp.server.dispatch import get_all_tool_names

        registered = set(get_all_tool_names())
        bogus = "flextools_no_such_tool_" + uuid.uuid4().hex
        assert bogus not in registered
        detector = _detector(sandbox_hc_ok=False)
        data = _run_health(monkeypatch, tmp_path, detector)
        data["parser_next_steps"].append(
            {"action": "x", "tool": bogus, "args": None,
             "rationale": "y", "est_cost": "z"}
        )

        offenders = [
            t for t in _find_all(data, "tool")
            if t is not None and t not in registered
        ]
        assert offenders == [bogus], offenders


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

        # CP5 (data-model section 7): additive keys on every component.
        for c in components:
            assert set(c.keys()) == SANDBOX_COMPONENT_KEYS

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
            # CP5 additions (data-model section 7, FR-005)
            "fieldworks_hermitcrab_version",
            "generate_hc_config_version",
            "hc_source",
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
# CP5 (T027): the sandbox spine -- additive keys, two-state status decided by
# found+starts, one rung per cause, FR-006's naming rule
# (specs/parser-check-cp5/contracts/tools.md section 6, data-model section 7)
# ---------------------------------------------------------------------------

SANDBOX_TOOL = "flextools_parse_sandbox"
RUNG_INSTALL_HC = "install the hc dotnet tool"
RUNG_INSTALL_RUNTIME = "install the .NET runtime hc needs"
RUNG_REPAIR_FIELDWORKS = "repair or reinstall FieldWorks (GenerateHCConfig.exe missing)"
RUNG_REHEARSE = "rehearse a grammar change on an exported copy"
READY_ARGS = {"action": "parse", "words": []}

RUNTIME_REASON = (
    "hc needs the .NET runtime Microsoft.NETCore.App 10.0, which is not installed"
)

#: Every unavailable variant FR-004/SC-002 names, as (id, hc discovery,
#: GenerateHCConfig found, the rung action this state must produce).
UNAVAILABLE_VARIANTS = [
    ("no_hc", lambda: _hc_not_found(), True, RUNG_INSTALL_HC),
    (
        "runtime_missing",
        lambda: _hc(True, starts=False, signal="runtime_missing",
                    source="dotnet_tools_dir", reason=RUNTIME_REASON),
        True,
        RUNG_INSTALL_RUNTIME,
    ),
    (
        # FR-003: anything that is not the HermitCrab tool counts as not found.
        "not_hermitcrab",
        lambda: _hc(False, signal="not_hermitcrab",
                    reason="the hc on PATH is not the HermitCrab tool"),
        True,
        RUNG_INSTALL_HC,
    ),
    (
        # probe_hc: a -h probe that times out is found=True, starts=False.
        # contracts/tools.md section 6 keys the rung on found/starts alone.
        "timeout",
        lambda: _hc(True, starts=False, signal="timeout", source="path",
                    reason="hc did not answer `hc -h` within 5 seconds"),
        True,
        RUNG_INSTALL_RUNTIME,
    ),
    ("generate_hc_config_missing", lambda: _hc_ready(), False, RUNG_REPAIR_FIELDWORKS),
]


def _components_by_name(data):
    return {c["component"]: c for c in data["parser"]["sandbox"]["components"]}


def _rungs(data, action):
    return [r for r in data["parser_next_steps"] if r["action"] == action]


class TestSandboxSpineCp5:
    # -- additive keys ------------------------------------------------------

    def test_sandbox_block_keys(self, monkeypatch, tmp_path):
        data = _run_health(monkeypatch, tmp_path, _detector())
        sandbox = data["parser"]["sandbox"]
        assert set(sandbox.keys()) == {"status", "components", "advisories"}
        assert isinstance(sandbox["advisories"], list)
        for c in sandbox["components"]:
            assert set(c.keys()) == SANDBOX_COMPONENT_KEYS

    def test_hc_component_carries_discovery_fields(self, monkeypatch, tmp_path):
        hc = _hc(True, starts=False, signal="runtime_missing",
                 source="dotnet_tools_dir", reason=RUNTIME_REASON)
        data = _run_health(monkeypatch, tmp_path, _detector(hc=hc))
        c = _components_by_name(data)["hc"]
        assert c["found"] is True, "a found-but-cannot-start hc must not read as absent (FR-004)"
        assert c["starts"] is False
        assert c["signal"] == "runtime_missing"
        assert c["source"] == "dotnet_tools_dir"
        assert c["reason"] == RUNTIME_REASON
        assert c["expected_path"] == HC_FOUND_PATH

    def test_hc_component_when_not_found(self, monkeypatch, tmp_path):
        data = _run_health(monkeypatch, tmp_path, _detector(hc=_hc_not_found()))
        c = _components_by_name(data)["hc"]
        assert c["found"] is False
        assert c["starts"] is None
        assert c["signal"] == "not_found"
        assert c["source"] is None

    def test_ready_hc_component(self, monkeypatch, tmp_path):
        data = _run_health(monkeypatch, tmp_path, _detector(hc=_hc_ready(source="path")))
        c = _components_by_name(data)["hc"]
        assert (c["found"], c["starts"], c["signal"], c["source"]) == (True, True, None, "path")

    @pytest.mark.parametrize("gc_ok", [True, False])
    def test_generate_hc_config_component_is_never_executed(self, monkeypatch, tmp_path, gc_ok):
        """Health does not run GenerateHCConfig, so its `starts` is null."""
        data = _run_health(monkeypatch, tmp_path, _detector(sandbox_generate_config_ok=gc_ok))
        c = _components_by_name(data)["GenerateHCConfig.exe"]
        assert c["found"] is gc_ok
        assert c["starts"] is None
        assert c["expected_path"] == GENERATE_CONFIG_EXPECTED_PATH
        if gc_ok:
            assert c["signal"] is None
            assert c["source"] == "fieldworks_dir"
        else:
            assert c["signal"] == "not_found"

    def test_detected_additions(self, monkeypatch, tmp_path):
        detector = _detector(hc=_hc_ready(source="dotnet_tool_list"))
        detector.versions.hc_tool_version = "1.2.3"
        detector.versions.fieldworks_hermitcrab_version = "3.8.2.0"
        detector.versions.generate_hc_config_version = "9.3.11.1"
        detected = _run_health(monkeypatch, tmp_path, detector)["parser"]["detected"]
        assert detected["hc_tool_version"] == "1.2.3"
        assert detected["fieldworks_hermitcrab_version"] == "3.8.2.0"
        assert detected["generate_hc_config_version"] == "9.3.11.1"
        assert detected["hc_source"] == "dotnet_tool_list"

    def test_hc_source_reported_even_when_hc_cannot_start(self, monkeypatch, tmp_path):
        hc = _hc(True, starts=False, signal="runtime_missing",
                 source="dotnet_tools_dir", reason=RUNTIME_REASON)
        detected = _run_health(monkeypatch, tmp_path, _detector(hc=hc))["parser"]["detected"]
        assert detected["hc_source"] == "dotnet_tools_dir"

    # -- advisories (FR-005: a skew warns, never refuses) --------------------

    def test_version_skew_is_an_advisory_and_still_ready(self, monkeypatch, tmp_path):
        detector = _detector()
        detector.versions.fieldworks_hermitcrab_version = "3.8.2.0"
        detector.versions.hc_tool_version = "3.9.0"
        detector.versions.hc_engine_version_skew = True
        sandbox = _run_health(monkeypatch, tmp_path, detector)["parser"]["sandbox"]
        assert sandbox["status"] == "ready"
        assert sandbox["advisories"] == ["hc_engine_version_skew"]

    def test_no_skew_no_advisory(self, monkeypatch, tmp_path):
        sandbox = _run_health(monkeypatch, tmp_path, _detector())["parser"]["sandbox"]
        assert sandbox["advisories"] == []

    # -- status: ready only if hc.found and hc.starts and generate.found ------

    @pytest.mark.parametrize(
        "found,starts,gc_ok,expected",
        [
            (True, True, True, "ready"),
            (True, False, True, "unavailable"),
            (True, None, True, "unavailable"),  # dotnet-tool-list-only hit: never probed
            (False, None, True, "unavailable"),
            (True, True, False, "unavailable"),
            (True, False, False, "unavailable"),
            (False, None, False, "unavailable"),
        ],
    )
    def test_status_rule(self, monkeypatch, tmp_path, found, starts, gc_ok, expected):
        if not found:
            signal = "not_found"
        elif starts is False:
            signal = "runtime_missing"
        else:
            signal = None
        hc = _hc(found, starts=starts, signal=signal, source="path" if found else None)
        data = _run_health(monkeypatch, tmp_path, _detector(hc=hc, sandbox_generate_config_ok=gc_ok))
        assert data["parser"]["sandbox"]["status"] == expected

    def test_found_but_unprobed_hc_never_names_the_tool(self, monkeypatch, tmp_path):
        """A `dotnet tool list` row alone (starts=None) is not a start."""
        hc = _hc(True, starts=None, source="dotnet_tool_list")
        data = _run_health(monkeypatch, tmp_path, _detector(hc=hc))
        assert data["parser"]["sandbox"]["status"] == "unavailable"
        assert SANDBOX_TOOL not in json.dumps(data)

    # -- unavailable: never names the tool; the right rung ------------------

    @pytest.mark.parametrize(
        "make_hc,gc_ok,action",
        [v[1:] for v in UNAVAILABLE_VARIANTS],
        ids=[v[0] for v in UNAVAILABLE_VARIANTS],
    )
    def test_unavailable_never_names_the_sandbox_tool(self, monkeypatch, tmp_path, make_hc, gc_ok, action):
        """FR-006 / SC-002: not in any field, not in any prose, anywhere."""
        data = _run_health(monkeypatch, tmp_path, _detector(hc=make_hc(), sandbox_generate_config_ok=gc_ok))
        assert data["parser"]["sandbox"]["status"] == "unavailable"
        assert SANDBOX_TOOL not in json.dumps(data)
        assert not _rungs(data, RUNG_REHEARSE)

    @pytest.mark.parametrize(
        "make_hc,gc_ok,action",
        [v[1:] for v in UNAVAILABLE_VARIANTS],
        ids=[v[0] for v in UNAVAILABLE_VARIANTS],
    )
    def test_unavailable_has_the_rung_for_its_cause(self, monkeypatch, tmp_path, make_hc, gc_ok, action):
        data = _run_health(monkeypatch, tmp_path, _detector(hc=make_hc(), sandbox_generate_config_ok=gc_ok))
        rows = _rungs(data, action)
        assert len(rows) == 1, data["parser_next_steps"]
        assert rows[0]["tool"] is None
        assert rows[0]["args"] is None

    def test_hc_not_found_rung_carries_the_full_hint(self, monkeypatch, tmp_path):
        data = _run_health(monkeypatch, tmp_path, _detector(hc=_hc_not_found()))
        (row,) = _rungs(data, RUNG_INSTALL_HC)
        assert HC_INSTALL_HINT in row["rationale"]
        assert row["est_cost"] == "n/a"
        assert not _rungs(data, RUNG_INSTALL_RUNTIME)

    def test_cannot_start_rung_names_the_runtime_not_absence(self, monkeypatch, tmp_path):
        """FR-004 / US1 scenario 3: the reason names the missing runtime
        rather than reporting hc as absent."""
        hc = _hc(True, starts=False, signal="runtime_missing",
                 source="dotnet_tools_dir", reason=RUNTIME_REASON)
        data = _run_health(monkeypatch, tmp_path, _detector(hc=hc))
        (row,) = _rungs(data, RUNG_INSTALL_RUNTIME)
        assert row["tool"] is None
        assert row["est_cost"] == "n/a"
        assert "Microsoft.NETCore.App 10.0" in row["rationale"]
        assert not _rungs(data, RUNG_INSTALL_HC), (
            "a found-but-cannot-start hc must not be told to install hc"
        )

    def test_both_components_missing_gives_both_rungs(self, monkeypatch, tmp_path):
        data = _run_health(monkeypatch, tmp_path, _detector(hc=_hc_not_found(), sandbox_generate_config_ok=False))
        assert len(_rungs(data, RUNG_INSTALL_HC)) == 1
        assert len(_rungs(data, RUNG_REPAIR_FIELDWORKS)) == 1
        assert SANDBOX_TOOL not in json.dumps(data)

    # -- ready: names the tool with usable args ------------------------------

    def test_ready_names_the_sandbox_tool(self, monkeypatch, tmp_path):
        data = _run_health(monkeypatch, tmp_path, _detector())
        assert data["parser"]["sandbox"]["status"] == "ready"
        rows = [r for r in data["parser_next_steps"] if r["tool"] == SANDBOX_TOOL]
        assert len(rows) == 1, data["parser_next_steps"]
        row = rows[0]
        assert row["action"] == RUNG_REHEARSE
        assert row["args"] == READY_ARGS
        assert row["est_cost"] == "minutes"

    def test_ready_rung_args_validate_against_the_input_model(self, monkeypatch, tmp_path):
        from flextoolsmcp.server.models import ParseSandboxInput

        data = _run_health(monkeypatch, tmp_path, _detector())
        (row,) = [r for r in data["parser_next_steps"] if r["tool"] == SANDBOX_TOOL]
        ParseSandboxInput(**row["args"])  # raises on unusable args

    def test_ready_rung_names_a_registered_tool(self, monkeypatch, tmp_path):
        from flextoolsmcp.server.dispatch import get_all_tool_names

        assert SANDBOX_TOOL in set(get_all_tool_names())

    def test_ready_emits_no_sandbox_repair_rungs(self, monkeypatch, tmp_path):
        data = _run_health(monkeypatch, tmp_path, _detector())
        for action in (RUNG_INSTALL_HC, RUNG_INSTALL_RUNTIME, RUNG_REPAIR_FIELDWORKS):
            assert not _rungs(data, action)

    def test_sandbox_rung_independent_of_in_process_spines(self, monkeypatch, tmp_path):
        """One dead spine must not blank the others: a dead read/write spine
        does not withdraw the sandbox rung."""
        detector = _detector(read_ok=False, read_signal="absent", write_ok=False, write_signal="absent")
        data = _run_health(monkeypatch, tmp_path, detector)
        assert [r for r in data["parser_next_steps"] if r["tool"] == SANDBOX_TOOL]


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
