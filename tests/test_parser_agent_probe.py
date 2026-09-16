#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T023: Agent-probe tests for the HC-agent probe (SPEC 12.7, data-model.md
"AgentProbeState").

Module under test: ``src/flextoolsmcp/server/parser_probe.py`` -- at the
time this file is written the module **does not exist at all** (T009-T011,
which land ``probe_parser_core``, have not landed either; ``ls
src/flextoolsmcp/server/`` shows no ``parser_probe.py``). ``AgentProbeState``
and the HC-agent probe specifically land at **T025**, strictly after this
file, once T024 (``check_active_parser``, same file) lands first. That is
the declared tests-first wave order (tasks.md "US3" row: "W1 tests: T022,
T023 -> W2: T024 -> W3: T025").

Sibling task T008 (``tests/test_parser_health_block.py``) set this cycle's
convention -- confirmed by grep, no ``xfail``/skip-guard precedent exists
anywhere in this suite for "test written ahead of its implementation" --
and it is a **plain, undecorated test module with per-test lazy imports**,
not a single top-level import (contrast T007's ``tests/test_parser_probe.py``,
which does one module-level import and therefore fails the *entire file* at
collection time). This file follows T008, not T007: every test that needs
``parser_probe`` imports it lazily, inside its own body, via
``_import_parser_probe()`` below, so a missing module fails only that one
test with a clear ``ModuleNotFoundError``, not a whole-file collection error.

Contract sources:
    - specs/parser-check/contracts/error-codes.md ("parser_agent_missing")
    - specs/parser-check/data-model.md ("AgentProbeState", "ParserDetector
      return shape")
    - specs/parser-check/SPEC.md 12.7
    - tasks.md T023 / T025

Pinned verbatim (task text, "Pin these names exactly"):
    - ``AgentProbeState``: ``present`` | ``absent`` | ``skipped``,
      case-sensitive, closed.
    - ``probe_source``: ``bootstrap_absent`` | ``lookup_failed``,
      case-sensitive, closed.
    - ``agent_name`` is literally ``"HermitCrab"``.
    - The agent GUID constant is ``kguidAgentHermitCrabParser``, resolved
      from ``ICmAgentRepository``.

CONTRACT AMBIGUITY 1 (documented, not resolved here): the entry-point
function's name is **not** pinned anywhere in data-model.md,
contracts/error-codes.md or tasks.md -- only ``AgentProbeState`` and the
``probe_source``/``agent_name`` vocabularies are. This file invents
``probe_hc_agent(project, active_engine)`` as the seam, parallel to T007's
own invented ``probe_parser_core(required_members, *, search_paths=None)``,
because SPEC 12.7 is scoped to exactly one agent (HermitCrab), not a
generic "any agent" probe. ``project`` is ``None`` when no project is open
(the ``skipped`` case, D2); ``active_engine`` is the already-resolved
``ActiveParser`` value (T024's job to produce it -- this function does not
re-derive it, avoiding a redundant XML re-parse). Only the function's
*attributes on its returned object* (``.state``, ``.agent_guid``,
``.agent_name``, ``.active_engine``, ``.probe_source``, ``.hint``) are
asserted below; the returned object's own class name is deliberately never
imported or asserted, to minimise invented-name surface. If T025 lands with
a different function name, only the ``_import_parser_probe()`` /
``_call_probe`` seam here needs a rename -- every attribute-shape assertion
is independent of that choice.

CONTRACT AMBIGUITY 2: ``probe_source`` has two closed values
(``bootstrap_absent`` | ``lookup_failed``) but neither
contracts/error-codes.md nor SPEC 12.7 states which of the two the
canonical "agent never bootstrapped, lookup raises KeyNotFoundException"
scenario maps to -- both readings are plausible (a proactive
repository-membership check reporting the semantic cause vs. a reactive
catch of the failed lookup reporting the mechanism). Rather than guess,
this file asserts **closed-set membership** (``probe_source in
{"bootstrap_absent", "lookup_failed"}``) for that scenario instead of
pinning one specific value. Whoever lands T025 should tighten this
assertion once the real mapping is decided.

Fidelity choice for simulating ``KeyNotFoundException``: T025's own task
text commits to "catching KeyNotFoundException" **by name**, and
SPEC 12.7 cites ``LangProject.DefaultParserAgent``'s own XML doc comment
declaring ``<exception cref="KeyNotFoundException"/>`` as documented
.NET behaviour -- so a plain Python stand-in class named
``KeyNotFoundException`` would risk a **false RED**: a correct T025
implementation that narrowly catches the real CLR type
(``System.Collections.Generic.KeyNotFoundException``) would not catch an
unrelated Python class of the same name, since pythonnet CLR exception
types do not participate in ordinary Python class hierarchies. This file
therefore raises the **real** CLR type, obtained via
``clr.AddReference("mscorlib")`` -- this needs pythonnet (an existing hard
dependency, ``requirements.txt: pythonnet>=3.0.0``) and a CLR runtime, but
**not** FieldWorks or any ``.fwdata`` file; it is gated behind
``pytest.importorskip("clr")`` so it skips cleanly (not errors) on a
machine without a CLR runtime, rather than being marked
``requires_flex`` (mscorlib needs no FieldWorks install).

``agent_guid`` value precedent: T008 (``tests/test_parser_health_block.py``,
same cycle) already commits to the literal string
``"kguidAgentHermitCrabParser"`` (the C# *symbol name*, not a raw UUID) as
the ``agent_guid`` value its fixtures carry and assert on. This file
matches that precedent for consistency within the cycle, rather than
inventing a different convention.

CP1 boundary: nothing here constructs an ``HCParser``, opens an
``LcmCache``, loads a grammar, parses a word, or writes to a project. The
fake ``project``/``LangProject`` objects below are plain Python stand-ins;
the only live dependency is pythonnet's CLR bridge to mscorlib for the
exception type, never FieldWorks.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional, Set

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ---------------------------------------------------------------------------
# Closed vocabularies, defined locally (not imported -- parser_probe.py does
# not exist yet; mirrors tests/test_parser_probe.py's own local redefinition
# of the signal vocabulary for the same reason).
# ---------------------------------------------------------------------------

AGENT_STATE_PRESENT = "present"
AGENT_STATE_ABSENT = "absent"
AGENT_STATE_SKIPPED = "skipped"
CLOSED_AGENT_STATES = frozenset({AGENT_STATE_PRESENT, AGENT_STATE_ABSENT, AGENT_STATE_SKIPPED})

PROBE_SOURCE_BOOTSTRAP_ABSENT = "bootstrap_absent"
PROBE_SOURCE_LOOKUP_FAILED = "lookup_failed"
CLOSED_PROBE_SOURCES = frozenset({PROBE_SOURCE_BOOTSTRAP_ABSENT, PROBE_SOURCE_LOOKUP_FAILED})

# T008's precedent value (see module docstring).
HC_AGENT_GUID = "kguidAgentHermitCrabParser"
HC_AGENT_NAME = "HermitCrab"


# ---------------------------------------------------------------------------
# Lazy import seam (T008's convention)
# ---------------------------------------------------------------------------

def _import_parser_probe():
    """Import ``flextoolsmcp.server.parser_probe`` lazily so a missing
    module fails only the calling test, not the whole file at collection
    time (T008's convention; see module docstring)."""
    import flextoolsmcp.server.parser_probe as parser_probe  # noqa: F401
    return parser_probe


def _import_validate_detail():
    """response_models.py already exists (T003/T006) -- this import cannot
    fail for module-existence reasons, but is kept lazy anyway for
    consistency with the rest of this file's style."""
    from flextoolsmcp.server.response_models import validate_detail, ParserAgentMissingDetail
    return validate_detail, ParserAgentMissingDetail


def _get_real_key_not_found_exception_type():
    """Return the real .NET ``System.Collections.Generic.KeyNotFoundException``
    type via pythonnet, skipping (not erroring) if no CLR runtime is
    available. See module docstring's "Fidelity choice" note for why a
    plain Python stand-in is not used instead."""
    clr = pytest.importorskip(
        "clr", reason="requires pythonnet's CLR bridge to construct the real .NET KeyNotFoundException"
    )
    try:
        clr.AddReference("mscorlib")
        from System.Collections.Generic import KeyNotFoundException
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"CLR runtime unavailable for mscorlib: {exc}")
    return KeyNotFoundException


def _agent_probe_state_values(agent_probe_state: Any) -> Set[str]:
    """Extract the closed set of string values ``AgentProbeState`` exposes,
    tolerating either an ``enum.Enum`` (``__members__``) or a
    ``typing.Literal`` alias representation -- the data model does not pin
    which Python construct backs the type (see CONTRACT AMBIGUITY 1 in
    tests/test_parser_health_block.py's own precedent for this kind of
    tolerant handling)."""
    if hasattr(agent_probe_state, "__members__"):
        return {member.value for member in agent_probe_state}
    import typing

    args = typing.get_args(agent_probe_state)
    if args:
        return set(args)
    raise AssertionError(
        "AgentProbeState exposes no way to enumerate its closed values "
        "(neither Enum __members__ nor typing.Literal args)"
    )


# ---------------------------------------------------------------------------
# Fake LCM surface: project.LangProject.DefaultParserAgent
# (SPEC 12.7: "LangProject.DefaultParserAgent ... resolves
# ICmAgentRepository.GetObject(CmAgentTags.kguidAgentHermitCrabParser) when
# MorphologicalDataOA.ActiveParser == 'HC'. Its own XML doc comment ...
# declares <exception cref="KeyNotFoundException"/>")
# ---------------------------------------------------------------------------

class _FakeLangProject:
    """Stand-in for ``LangProject``. Accessing ``.DefaultParserAgent``
    either returns a fake agent object or raises the exception it was
    constructed with -- mirroring the real property's documented throw."""

    def __init__(self, *, agent: Optional[object] = None, raise_exc: Optional[BaseException] = None):
        self._agent = agent
        self._raise_exc = raise_exc

    @property
    def DefaultParserAgent(self):
        if self._raise_exc is not None:
            raise self._raise_exc
        return self._agent


class _FakeProject:
    """Stand-in for the project/cache object a real handler would hold --
    only the one attribute path SPEC 12.7 names (``.LangProject``) is
    modelled; nothing else is present, so a probe that reads anything else
    off this fake fails loudly with ``AttributeError``."""

    def __init__(self, lang_project: _FakeLangProject):
        self.LangProject = lang_project


def _missing_agent_project(raise_exc: BaseException) -> _FakeProject:
    return _FakeProject(_FakeLangProject(raise_exc=raise_exc))


def _present_agent_project(agent: object = "fake-hc-agent") -> _FakeProject:
    return _FakeProject(_FakeLangProject(agent=agent))


# ---------------------------------------------------------------------------
# AgentProbeState: closed, three-valued, case-sensitive
# ---------------------------------------------------------------------------

class TestAgentProbeStateClosedEnum:
    def test_exactly_three_closed_values(self):
        pp = _import_parser_probe()
        values = _agent_probe_state_values(pp.AgentProbeState)
        assert values == CLOSED_AGENT_STATES

    def test_case_sensitive_closed_vocabulary(self):
        """``AgentProbeState`` is a ``typing.Literal``, so there is no
        constructor that could reject a mis-cased value -- an Enum-shaped
        assertion would simply not apply here, and skipping it would leave
        case-sensitivity untested, which is the one thing a probe vocabulary
        must not be. So assert the property where the value actually crosses
        a boundary: no recased spelling is a member of the declared set, and
        the shared discriminated-union validator that every error payload
        goes through rejects a recased ``probe_source``."""
        pp = _import_parser_probe()
        values = _agent_probe_state_values(pp.AgentProbeState)
        assert values == CLOSED_AGENT_STATES
        for recased in ("Skipped", "PRESENT", "Absent", "skipped "):
            assert recased not in values

        validate_detail, _ = _import_validate_detail()
        import pydantic

        payload = {
            "error_code": "parser_agent_missing",
            "agent_guid": HC_AGENT_GUID,
            "agent_name": HC_AGENT_NAME,
            "active_engine": "HC",
            "probe_source": "Bootstrap_Absent",  # recased -- must be rejected
            "hint": "install the HermitCrab parser agent",
        }
        with pytest.raises(pydantic.ValidationError):
            validate_detail(payload)


# ---------------------------------------------------------------------------
# No KeyNotFoundException escapes (the whole point of T023/T025)
# ---------------------------------------------------------------------------

class TestNoKeyNotFoundExceptionEscapes:
    def test_missing_agent_does_not_raise_out_of_the_probe(self):
        pp = _import_parser_probe()
        KeyNotFoundException = _get_real_key_not_found_exception_type()
        project = _missing_agent_project(
            KeyNotFoundException(f"key not found: {HC_AGENT_GUID}")
        )

        # No try/except: an escaping exception fails this test with its own
        # traceback, matching tests/test_parser_probe.py's own
        # "does_not_raise_out_of_the_probe" pattern.
        result = pp.probe_hc_agent(project, "HC")

        assert result is not None

    def test_missing_agent_state_is_absent(self):
        pp = _import_parser_probe()
        KeyNotFoundException = _get_real_key_not_found_exception_type()
        project = _missing_agent_project(
            KeyNotFoundException(f"key not found: {HC_AGENT_GUID}")
        )

        result = pp.probe_hc_agent(project, "HC")

        assert str(result.state) == AGENT_STATE_ABSENT or result.state == AGENT_STATE_ABSENT


# ---------------------------------------------------------------------------
# parser_agent_missing: agent_guid, agent_name, active_engine, probe_source,
# hint -- validated through the shared discriminated-union validator, not
# just the bare model class (matching tests/test_parser_error_models.py's
# own precedent for every other error code).
# ---------------------------------------------------------------------------

class TestParserAgentMissingDetailFields:
    def _absent_result(self):
        pp = _import_parser_probe()
        KeyNotFoundException = _get_real_key_not_found_exception_type()
        project = _missing_agent_project(
            KeyNotFoundException(f"key not found: {HC_AGENT_GUID}")
        )
        return pp.probe_hc_agent(project, "HC")

    def test_agent_name_is_literally_hermitcrab(self):
        result = self._absent_result()
        assert result.agent_name == HC_AGENT_NAME

    def test_active_engine_echoes_what_was_passed(self):
        result = self._absent_result()
        assert result.active_engine == "HC"

    def test_agent_guid_is_populated(self):
        result = self._absent_result()
        assert result.agent_guid
        # T008's precedent value (module docstring) -- matched for
        # cross-file consistency within this cycle.
        assert result.agent_guid == HC_AGENT_GUID

    def test_probe_source_is_populated_from_the_closed_vocabulary(self):
        # CONTRACT AMBIGUITY 2 (module docstring): membership only, not a
        # pinned specific value.
        result = self._absent_result()
        assert result.probe_source in CLOSED_PROBE_SOURCES

    def test_hint_is_a_nonempty_string(self):
        result = self._absent_result()
        assert isinstance(result.hint, str)
        assert result.hint

    def test_full_payload_validates_through_validate_detail(self):
        validate_detail, ParserAgentMissingDetail = _import_validate_detail()
        result = self._absent_result()

        payload = {
            "error_code": "parser_agent_missing",
            "agent_guid": result.agent_guid,
            "agent_name": result.agent_name,
            "active_engine": result.active_engine,
            "probe_source": result.probe_source,
            "hint": result.hint,
        }
        detail = validate_detail(payload)

        assert isinstance(detail, ParserAgentMissingDetail)
        assert detail.agent_name == HC_AGENT_NAME
        assert detail.active_engine == "HC"
        assert detail.probe_source in CLOSED_PROBE_SOURCES


# ---------------------------------------------------------------------------
# The read spine is unaffected: try_word neither files nor resolves an
# agent, so a missing HC agent must never touch or degrade the read probe.
# ---------------------------------------------------------------------------

class TestReadSpineUnaffectedByMissingAgent:
    def test_probe_hc_agent_never_invokes_probe_parser_core(self, monkeypatch):
        pp = _import_parser_probe()
        KeyNotFoundException = _get_real_key_not_found_exception_type()

        calls = []

        def _spy(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("probe_hc_agent must never call probe_parser_core")

        # raising=False: probe_parser_core may not exist yet on this module
        # either (it lands at T009-T011, a different wave); the patch must
        # still install cleanly so this test exercises probe_hc_agent alone.
        monkeypatch.setattr(pp, "probe_parser_core", _spy, raising=False)

        project = _missing_agent_project(
            KeyNotFoundException(f"key not found: {HC_AGENT_GUID}")
        )
        pp.probe_hc_agent(project, "HC")

        assert calls == [], (
            "resolving the HC agent must never touch the ParserCore member "
            "probe that decides read/write spine status -- SPEC 12.7: "
            "'flextools_try_word neither files nor resolves an agent'"
        )


# ---------------------------------------------------------------------------
# skipped is never reported as a pass (the invariant SPEC 16 tests directly)
# ---------------------------------------------------------------------------

class TestSkippedNeverAPass:
    def test_no_project_open_yields_skipped(self):
        pp = _import_parser_probe()
        result = pp.probe_hc_agent(None, None)
        assert str(result.state) == AGENT_STATE_SKIPPED or result.state == AGENT_STATE_SKIPPED

    def test_skipped_is_not_present_and_not_absent(self):
        pp = _import_parser_probe()
        result = pp.probe_hc_agent(None, None)
        assert result.state != AGENT_STATE_PRESENT
        assert str(result.state) != AGENT_STATE_PRESENT
        assert result.state != AGENT_STATE_ABSENT
        assert str(result.state) != AGENT_STATE_ABSENT

    def test_skipped_result_carries_no_ok_field(self):
        """data-model.md: 'Modelled separately from ProbeResult precisely
        so skipped can never be flattened into ok=True.' ProbeResult (T007)
        has an .ok bool; the agent-probe result must not, or a caller could
        read a skipped probe as a pass by checking .ok truthiness."""
        pp = _import_parser_probe()
        result = pp.probe_hc_agent(None, None)
        assert not hasattr(result, "ok"), (
            "the agent-probe result must carry no .ok field -- its "
            "presence would let a skipped probe be misread as a pass, "
            "exactly the flattening data-model.md rules out"
        )

    def test_skipped_result_never_equals_a_pass_shaped_value(self):
        pp = _import_parser_probe()
        result = pp.probe_hc_agent(None, None)
        assert result.state is not True
        assert result.state != "present"
        assert bool(result.state) is not False or str(result.state) == AGENT_STATE_SKIPPED

    def test_skipped_result_does_not_validate_as_parser_agent_missing(self):
        """A skipped probe carries no meaningful agent_guid/probe_source/
        hint -- attempting to build a parser_agent_missing payload from it
        must fail validation, confirming skipped can never be silently
        promoted into a reportable error either."""
        validate_detail, _ = _import_validate_detail()
        pp = _import_parser_probe()
        result = pp.probe_hc_agent(None, None)

        payload = {
            "error_code": "parser_agent_missing",
            "agent_guid": getattr(result, "agent_guid", None),
            "agent_name": HC_AGENT_NAME,
            "active_engine": getattr(result, "active_engine", None),
            "probe_source": getattr(result, "probe_source", None),
            "hint": getattr(result, "hint", None),
        }
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            validate_detail(payload)


# ---------------------------------------------------------------------------
# Light positive-path sanity: the agent resolves cleanly when present.
# Not required by T023's task text, but rounds out AgentProbeState's third
# member with the same no-exception-escapes discipline as the other two.
# ---------------------------------------------------------------------------

class TestAgentPresentSanity:
    def test_present_agent_does_not_raise_and_reports_present(self):
        pp = _import_parser_probe()
        project = _present_agent_project()
        result = pp.probe_hc_agent(project, "HC")
        assert str(result.state) == AGENT_STATE_PRESENT or result.state == AGENT_STATE_PRESENT


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
