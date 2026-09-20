#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T007: Probe tests for the CP1 ParserCore capability probe (SPEC 5.4).

Module under test: ``src/flextoolsmcp/server/parser_probe.py`` -- this file
does **not exist yet**. It is written by T009/T010/T011, which land after
this test file per the declared tests-first wave order in
``specs/parser-check/tasks.md``. No repo precedent for pre-implementation
tests was found (no ``xfail``/``importorskip``/skip-guard convention turned
up across ``tests/*.py``), so this file is a **plain, undecorated test
module**: it fails loudly (a collection-time ``ModuleNotFoundError`` on the
top-level import below) until T009 lands, rather than reporting green via
``xfail`` or invisible via a skip guard. See cycle9-programmer-t007.md for
the exact failing/passing counts this produced.

Contract pinned verbatim from specs/parser-check/data-model.md (shared with
the parallel tests/test_parser_health_block.py agent -- do not rename):

    - ``ProbeResult`` fields: ``ok: bool``, ``signal: str | None``,
      ``expected_path: str | None``, ``missing_members: list[str]``,
      ``detected_version: str | None``, plus ``load_error`` (T009, asserted
      by that name for the ``load_failed`` case).
    - ``signal`` closed vocabulary, case-sensitive:
      ``absent`` | ``foreign_install`` | ``incompatible_surface`` |
      ``load_failed``.
    - Invariant: ``ok=True`` implies ``missing_members == []`` and
      ``signal is None``.
    - ``detected_version`` is reported, never compared -- no version floor
      anywhere.

Everything else below this line -- the ``probe_parser_core(...)`` entry
point's name/signature and the ``_load_parser_core_members`` /
``get_resolved_fieldworks_dir`` / ``locate_liblcm_dll`` seams it is assumed
to call -- is **not** pinned by data-model.md or contracts/error-codes.md;
T007's own task text only fixes ``ProbeResult`` and the signal vocabulary.
Those names are this file's own design choice, made because CP1's probe is
reflection-only over the CLR (``Assembly.LoadFile`` / ``GetMembers``,
SPEC 5.4) and this suite must run without a live FieldWorks/pythonnet
install (T008's SPEC 16 integration bullet is the one place that requires
real Windows + FieldWorks, and it is explicitly out of scope for T007).
Rationale for each invented name:

    - ``probe_parser_core(required_members, *, search_paths=None)`` --
      called once per spine (``read`` with ``HCPARSER_MEMBERS``, ``write``
      with ``COMPLETE_PARSER_CORE_MEMBERS``, per data-model.md's
      "read_probe"/"write_probe differ by exactly one member" note).
    - ``get_resolved_fieldworks_dir`` / ``locate_liblcm_dll`` -- reused
      verbatim from ``versioning.py`` (T009's own task text commits to
      reusing ``get_resolved_fieldworks_dir()`` by this exact name;
      ``locate_liblcm_dll`` is already generic over ``dll_name``, the
      obvious existing helper for locating ``ParserCore.dll`` the same
      way). Patched in **two** places (on ``parser_probe`` itself and on
      ``versioning`` directly, both with ``raising=False``) so the patch
      takes effect regardless of whether T009 imports these by name
      (``from .versioning import get_resolved_fieldworks_dir``) or calls
      them module-qualified (``versioning.get_resolved_fieldworks_dir()``).
    - ``_load_parser_core_members(dll_path) -> (frozenset[str], version)``
      -- the reflective load-and-inspect seam SPEC 5.4 describes as
      combining the ``Assembly.LoadFile`` precedent (``versioning.py``:262)
      with the ``GetMembers``/generic-unwrapping precedent
      (``liblcm_extractor.py``:~330); a throw here is what "an
      Assembly.LoadFile throw maps to signal=load_failed" tests against.

If T009 lands with different internal names, these tests may need a small
rename pass to match -- that is expected in a tests-first workflow (the
test file establishes the contract T009 must satisfy; it is not a
prediction of T009's private implementation details).

Note on ``tests/fixtures/parser_check.py``'s ``FakeParserCoreLocation``:
``.parser_core_dir`` and ``.lcmodel_dir`` hold full DLL *file* paths (e.g.
``...\\FieldWorks 9\\SIL.LCModel.dll``), not bare directories, despite the
field names. Its ``same_install`` property does a raw string equality
between these two values, which -- because the two paths always end in
different filenames (``ParserCore.dll`` vs ``SIL.LCModel.dll``) -- is
``False`` for *every* fixture instance, including
``COMPLETE_SAME_INSTALL_PARSER_CORE``. That looks like a latent bug in the
property (probably meant to compare ``Path(...).parent`` on each side).
This file does not rely on ``.same_install`` anywhere; it derives
directory identity itself via ``Path(...).parent``, sidestepping the bug
without touching another agent's fixture file. Flagged here for whoever
next touches ``fixtures/parser_check.py``.
"""

import sys
from pathlib import Path
from typing import FrozenSet, Optional

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server import parser_probe  # noqa: E402
from flextoolsmcp.server import versioning  # noqa: E402
from flextoolsmcp.server.parser_probe import ProbeResult, probe_parser_core  # noqa: E402

from fixtures.parser_check import (  # noqa: E402
    COMPLETE_PARSER_CORE_MEMBERS,
    COMPLETE_SAME_INSTALL_PARSER_CORE,
    FOREIGN_DIRECTORY_PARSER_CORE,
    FakeParserCoreLocation,
    HCPARSER_MEMBERS,
    MISSING_PROCESS_PARSE_PARSER_CORE,
)


# ---------------------------------------------------------------------------
# Closed signal vocabulary (data-model.md / contracts/error-codes.md) --
# defined here, not imported, since parser_probe.py does not exist yet.
# ---------------------------------------------------------------------------

SIGNAL_ABSENT = "absent"
SIGNAL_FOREIGN_INSTALL = "foreign_install"
SIGNAL_INCOMPATIBLE_SURFACE = "incompatible_surface"
SIGNAL_LOAD_FAILED = "load_failed"
CLOSED_SIGNALS = frozenset(
    {SIGNAL_ABSENT, SIGNAL_FOREIGN_INSTALL, SIGNAL_INCOMPATIBLE_SURFACE, SIGNAL_LOAD_FAILED}
)


# ---------------------------------------------------------------------------
# Seam installer
# ---------------------------------------------------------------------------

def _install_fake_probe_location(
    monkeypatch,
    location: FakeParserCoreLocation,
    *,
    detected_version: Optional[str] = "1.0.0.0",
    found_members: Optional[FrozenSet[str]] = None,
    raise_on_load: Optional[Exception] = None,
) -> None:
    """Wire parser_probe's filesystem/reflection seams to a fake location.

    See the module docstring for why each seam name was chosen and why
    each is patched in two places.
    """
    parser_core_path = Path(location.parser_core_dir)
    lcmodel_path = Path(location.lcmodel_dir)
    members = found_members if found_members is not None else location.members

    def fake_get_resolved_fieldworks_dir(search_paths=None):
        return lcmodel_path.parent

    def fake_locate_liblcm_dll(dll_name="SIL.LCModel.dll", search_paths=None):
        if dll_name == "ParserCore.dll":
            return parser_core_path
        return lcmodel_path

    def fake_load_parser_core_members(dll_path):
        if raise_on_load is not None:
            raise raise_on_load
        return (members, detected_version)

    for target in (parser_probe, versioning):
        monkeypatch.setattr(
            target, "get_resolved_fieldworks_dir", fake_get_resolved_fieldworks_dir, raising=False
        )
        monkeypatch.setattr(
            target, "locate_liblcm_dll", fake_locate_liblcm_dll, raising=False
        )
    monkeypatch.setattr(
        parser_probe, "_load_parser_core_members", fake_load_parser_core_members, raising=False
    )


# ---------------------------------------------------------------------------
# ProbeResult shape / invariant
# ---------------------------------------------------------------------------

class TestProbeResultInvariant:
    """data-model.md: ok=True implies missing_members == [] and signal is None."""

    @pytest.mark.parametrize(
        "location,required_members",
        [
            (COMPLETE_SAME_INSTALL_PARSER_CORE, COMPLETE_PARSER_CORE_MEMBERS),
            (MISSING_PROCESS_PARSE_PARSER_CORE, COMPLETE_PARSER_CORE_MEMBERS),
            (FOREIGN_DIRECTORY_PARSER_CORE, COMPLETE_PARSER_CORE_MEMBERS),
        ],
    )
    def test_ok_true_implies_empty_missing_members_and_null_signal(
        self, monkeypatch, location, required_members
    ):
        _install_fake_probe_location(monkeypatch, location)
        result = probe_parser_core(required_members)
        assert isinstance(result, ProbeResult)
        if result.ok:
            assert result.missing_members == []
            assert result.signal is None

    def test_signal_is_from_the_closed_vocabulary_or_none(self, monkeypatch):
        _install_fake_probe_location(monkeypatch, COMPLETE_SAME_INSTALL_PARSER_CORE)
        result = probe_parser_core(COMPLETE_PARSER_CORE_MEMBERS)
        assert result.signal is None or result.signal in CLOSED_SIGNALS


# ---------------------------------------------------------------------------
# foreign_install
# ---------------------------------------------------------------------------

class TestForeignInstallSignal:
    """ParserCore resolved from a directory other than the one supplying
    SIL.LCModel.dll -- FOREIGN_DIRECTORY_PARSER_CORE carries a *complete*
    member set specifically so this test isolates the directory-mismatch
    branch from the member-completeness branch (T002's own design)."""

    def test_foreign_install_yields_signal(self, monkeypatch):
        assert Path(FOREIGN_DIRECTORY_PARSER_CORE.parser_core_dir).parent != Path(
            FOREIGN_DIRECTORY_PARSER_CORE.lcmodel_dir
        ).parent
        _install_fake_probe_location(monkeypatch, FOREIGN_DIRECTORY_PARSER_CORE)

        result = probe_parser_core(COMPLETE_PARSER_CORE_MEMBERS)

        assert result.ok is False
        assert result.signal == SIGNAL_FOREIGN_INSTALL
        assert result.expected_path is not None

    def test_same_install_does_not_yield_foreign_install(self, monkeypatch):
        assert Path(COMPLETE_SAME_INSTALL_PARSER_CORE.parser_core_dir).parent == Path(
            COMPLETE_SAME_INSTALL_PARSER_CORE.lcmodel_dir
        ).parent
        _install_fake_probe_location(monkeypatch, COMPLETE_SAME_INSTALL_PARSER_CORE)

        result = probe_parser_core(COMPLETE_PARSER_CORE_MEMBERS)

        assert result.signal != SIGNAL_FOREIGN_INSTALL
        assert result.ok is True


# ---------------------------------------------------------------------------
# incompatible_surface
# ---------------------------------------------------------------------------

class TestIncompatibleSurfaceSignal:
    """A missing bound member (here, the write-only ParseFiler.ProcessParse)
    yields signal=incompatible_surface naming it in missing_members."""

    def test_missing_bound_member_yields_signal_and_names_it(self, monkeypatch):
        _install_fake_probe_location(monkeypatch, MISSING_PROCESS_PARSE_PARSER_CORE)

        result = probe_parser_core(COMPLETE_PARSER_CORE_MEMBERS)

        assert result.ok is False
        assert result.signal == SIGNAL_INCOMPATIBLE_SURFACE
        assert "ParseFiler.ProcessParse" in result.missing_members

    def test_read_only_required_set_is_unaffected_by_the_write_only_gap(self, monkeypatch):
        # The same location satisfies the *read* probe (HCPARSER_MEMBERS
        # only) even though it fails the *write* probe above -- this is
        # data-model.md's "read: ready, write: unavailable" state.
        _install_fake_probe_location(monkeypatch, MISSING_PROCESS_PARSE_PARSER_CORE)

        result = probe_parser_core(HCPARSER_MEMBERS)

        assert result.ok is True
        assert result.missing_members == []
        assert result.signal is None


# ---------------------------------------------------------------------------
# Standing regression guard: detected_version is reported, never compared
# ---------------------------------------------------------------------------

class TestDetectedVersionNeverCompared:
    """SPEC 16's standing regression test against reintroducing a version
    floor. No code path may compare detected_version against anything --
    so an unexpected version, however implausible, must still pass and be
    reported verbatim, never gated on."""

    @pytest.mark.parametrize(
        "unexpected_version",
        [
            "0.0.1",  # suspiciously low -- what a reintroduced floor would refuse
            "999.999.999",  # suspiciously high
            "not-a-real-version-string",  # malformed -- would break any parse-based floor
        ],
    )
    def test_unexpected_but_complete_version_passes_and_is_reported(
        self, monkeypatch, unexpected_version
    ):
        _install_fake_probe_location(
            monkeypatch,
            COMPLETE_SAME_INSTALL_PARSER_CORE,
            detected_version=unexpected_version,
        )

        result = probe_parser_core(COMPLETE_PARSER_CORE_MEMBERS)

        assert result.ok is True
        assert result.signal is None
        assert result.missing_members == []
        assert result.detected_version == unexpected_version


# ---------------------------------------------------------------------------
# load_failed
# ---------------------------------------------------------------------------

class TestLoadFailedSignal:
    """An Assembly.LoadFile throw (a mismatched transitive dependency, per
    SPEC 5.4) is caught before any member can be inspected and mapped to
    signal=load_failed with load_error carrying the throw."""

    def test_load_file_throw_maps_to_load_failed_with_load_error(self, monkeypatch):
        thrown = RuntimeError(
            "mismatched transitive dependency: SIL.Machine.Morphology.dll not found"
        )
        _install_fake_probe_location(
            monkeypatch, COMPLETE_SAME_INSTALL_PARSER_CORE, raise_on_load=thrown
        )

        result = probe_parser_core(COMPLETE_PARSER_CORE_MEMBERS)

        assert result.ok is False
        assert result.signal == SIGNAL_LOAD_FAILED
        assert result.missing_members == []
        assert result.detected_version is None
        # load_error is T009's addition beyond data-model.md's four pinned
        # fields (see module docstring); asserted by that exact name.
        assert result.load_error is not None
        assert "mismatched transitive dependency" in result.load_error

    def test_load_failed_does_not_raise_out_of_the_probe(self, monkeypatch):
        # The throw must be caught inside probe_parser_core, never
        # propagated -- a probe that dies mid-call tells the caller
        # nothing (contracts/error-codes.md's parser_agent_missing
        # section states this principle for a sibling probe; it applies
        # here too).
        _install_fake_probe_location(
            monkeypatch,
            COMPLETE_SAME_INSTALL_PARSER_CORE,
            raise_on_load=OSError("access denied"),
        )
        result = probe_parser_core(COMPLETE_PARSER_CORE_MEMBERS)
        assert result.signal == SIGNAL_LOAD_FAILED


# ---------------------------------------------------------------------------
# CP1 boundary: no LcmCache, no grammar, no parse
# ---------------------------------------------------------------------------

class TestCP1Boundary:
    """SPEC 5.4 / CP1 scope: the probe is reflection-only. It never opens
    an LcmCache, never loads a grammar, never parses a word. This is the
    T007-local instance of the guarantee tests/test_cp1_boundary.py (T026)
    polices suite-wide with a dynamic spy/patch on the CLR construction
    point plus a static scan; this test is the probe's own dynamic half,
    exercised through the *real* probe_parser_core (only the filesystem
    location is faked, via search_paths pointing at an empty directory --
    the reflection seam is left untouched so the real "no DLL found"
    short-circuit is what's under test)."""

    def test_probe_on_absent_dll_never_touches_lcmcache(self, monkeypatch, tmp_path):
        import types as _types

        lcm_cache_calls = []

        def _spy(*args, **kwargs):
            lcm_cache_calls.append((args, kwargs))
            return object()

        fake_lcmodel_module = _types.ModuleType("SIL.LCModel")
        fake_lcmodel_module.LcmCache = _spy
        fake_sil_module = _types.ModuleType("SIL")
        fake_sil_module.LCModel = fake_lcmodel_module
        monkeypatch.setitem(sys.modules, "SIL", fake_sil_module)
        monkeypatch.setitem(sys.modules, "SIL.LCModel", fake_lcmodel_module)

        # No DLLs exist under tmp_path: locate_liblcm_dll's plain
        # filesystem check (no pythonnet required) finds nothing, so the
        # probe must fail on that cheap check alone -- never reaching a
        # grammar or cache path -- regardless of what internal signal it
        # reports for "not found".
        result = probe_parser_core(COMPLETE_PARSER_CORE_MEMBERS, search_paths=[tmp_path])

        assert result.ok is False
        assert lcm_cache_calls == []

    def test_probe_across_all_signals_never_touches_lcmcache(self, monkeypatch):
        import types as _types

        lcm_cache_calls = []

        def _spy(*args, **kwargs):
            lcm_cache_calls.append((args, kwargs))
            return object()

        fake_lcmodel_module = _types.ModuleType("SIL.LCModel")
        fake_lcmodel_module.LcmCache = _spy
        fake_sil_module = _types.ModuleType("SIL")
        fake_sil_module.LCModel = fake_lcmodel_module
        monkeypatch.setitem(sys.modules, "SIL", fake_sil_module)
        monkeypatch.setitem(sys.modules, "SIL.LCModel", fake_lcmodel_module)

        for location in (
            COMPLETE_SAME_INSTALL_PARSER_CORE,
            MISSING_PROCESS_PARSE_PARSER_CORE,
            FOREIGN_DIRECTORY_PARSER_CORE,
        ):
            _install_fake_probe_location(monkeypatch, location)
            probe_parser_core(COMPLETE_PARSER_CORE_MEMBERS)

        assert lcm_cache_calls == []


# ---------------------------------------------------------------------------
# FR-041 -- the two capability checks diverge ON PURPOSE
# ---------------------------------------------------------------------------
#
# Added at CP2b. The member lists were used by several tests and pinned by
# none, so the specific mistake FR-041 exists to prevent -- "these two lists
# disagree, let me make them match" -- would have passed the whole suite.
#
# These tests do NOT modify the check (FR-041 forbids that, and CP2b did
# not): they pin what it already is, and they pin the divergence itself as
# intentional.


class TestCapabilityCheckDivergenceIsIntentional:
    """The read/write member sets, and what flexicon's check does not share."""

    def test_the_read_spine_member_set_is_exactly_these_five(self):
        # Imported from the module under test, NOT from the fixtures module
        # this file also imports a `HCPARSER_MEMBERS` from -- that one is a
        # tuple mirror kept for the fake DLL surfaces, and asserting against
        # it would pin the fixture rather than the probe.
        from flextoolsmcp.server.parser_probe import HCPARSER_MEMBERS

        assert HCPARSER_MEMBERS == frozenset(
            {
                "HCParser(LcmCache)",
                "Update()",
                "ParseWord(string)",
                "TraceWordXml(string, IEnumerable<int>)",
                "ParseWordXml(string)",
            }
        ), (
            "the read spine's member set changed. If you are syncing it with "
            "flexicon's GetAvailability() list, stop: the two probe different "
            "surfaces on purpose (FR-041, and the note above these lists)."
        )

    def test_the_write_spine_adds_exactly_the_filer(self):
        from flextoolsmcp.server.parser_probe import (
            HCPARSER_MEMBERS,
            PARSE_FILER_MEMBERS,
            WRITE_REQUIRED_MEMBERS,
        )

        assert PARSE_FILER_MEMBERS == frozenset({"ParseFiler.ProcessParse"})
        assert WRITE_REQUIRED_MEMBERS == HCPARSER_MEMBERS | PARSE_FILER_MEMBERS
        assert WRITE_REQUIRED_MEMBERS - HCPARSER_MEMBERS == frozenset(
            {"ParseFiler.ProcessParse"}
        ), "the two spines must differ by exactly one member (SPEC 5.2)"

    def test_the_filing_member_is_gated_here_and_nowhere_else(self):
        """The one thing this check has that flexicon's cannot.

        flexicon never wraps the write path, so its capability check has
        nothing to say about filing. If this member were dropped from here,
        the write spine would be ungated on both sides at once.
        """
        from flextoolsmcp.server.parser_probe import WRITE_REQUIRED_MEMBERS

        assert any("ProcessParse" in m for m in WRITE_REQUIRED_MEMBERS), (
            "ParseFiler.ProcessParse is no longer required by the write "
            "spine; nothing else in either repository gates filing"
        )

    def test_the_currency_members_are_deliberately_absent_here(self):
        """The one thing flexicon's check has that this one does not.

        `IsUpToDate()` and `Reset()` belong to the held-grammar contract,
        which lives entirely on flexicon's facade -- this probe has no
        caller that binds either, so demanding them here would refuse an
        install over a member nothing in this repository uses.

        Asserted as an ABSENCE so that adding them is a deliberate act with
        a failing test to answer, rather than a tidy-up.
        """
        from flextoolsmcp.server.parser_probe import WRITE_REQUIRED_MEMBERS

        for member in ("IsUpToDate", "Reset()"):
            assert not any(member in m for m in WRITE_REQUIRED_MEMBERS), (
                f"{member} was added to this probe's member set. It is "
                f"flexicon's to check -- see the FR-041 note above the lists."
            )

    def test_the_divergence_is_documented_where_the_lists_are_edited(self):
        """FR-041's last sentence, asserted rather than assumed.

        The note has to be next to the lists, because that is what a
        contributor is looking at when they are tempted to sync them.
        """
        import inspect

        from flextoolsmcp.server import parser_probe

        source = inspect.getsource(parser_probe)
        head = source[: source.index("class ProbeResult")]

        assert "GetAvailability" in head, (
            "parser_probe no longer names the other capability check; FR-041 "
            "requires each to state what the other has that it lacks"
        )
        assert "IsUpToDate" in head and "ProcessParse" in head, (
            "the note no longer names the members that actually differ, "
            "which is the only part of it that is checkable"
        )
