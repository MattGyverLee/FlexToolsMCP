#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T022: Engine-gate tests for ``check_active_parser`` (parser-check CP1, US3).

Contract sources: specs/parser-check/SPEC.md 3.2 and 12.7,
specs/parser-check/contracts/error-codes.md (``parser_engine_mismatch``).

Module under test: ``check_active_parser(project, supported_engines=("HC",))``
in ``src/flextoolsmcp/server/parser_probe.py`` -- **does not exist yet**. Per
SPEC.md:1647-1648 it is ``-> None``, raising ``parser_engine_mismatch`` on
mismatch, and lands at T024, strictly after this file (declared tests-first
wave order, tasks.md "Wave 2 (single)"). The detail payload's *shape* is
already pinned (``response_models.ParserEngineMismatchDetail``, landed T003);
what is NOT pinned by any contract doc is how ``check_active_parser`` signals
the refusal to a Python caller. SPEC.md's own wording ("-> None, raising
parser_engine_mismatch") reads as an ordinary Python ``raise``, so this file
assumes T024 raises a dedicated exception, ``ParserEngineMismatchError``,
carrying a ``.detail`` dict shaped exactly like the contract's example
(``{"error_code": "parser_engine_mismatch", "configured_engine", ...}``) --
the same dict shape ``validate_detail()`` already accepts per
tests/test_parser_error_models.py (T006). If T024 lands with a different
signalling mechanism (e.g. a plain-dict return, or a different exception
name/attribute), the fix is a small, mechanical rename in this file, not a
design change -- the same expectation T007's own docstring states for its
own invented seam names.

Following T008's convention (no ``xfail``/skip-guard precedent anywhere in
this suite): every test that touches ``check_active_parser`` does its own
**lazy, per-test import** of ``check_active_parser`` (and
``ParserEngineMismatchError`` where needed) from ``parser_probe``, so a
missing module/name fails that one test with a clear
``ModuleNotFoundError``/``ImportError``, not a whole-file collection error.
Fixture-only tests (e.g. sanity-checking this file's own XML resolver
against ``PARSER_PARAMETERS_XML_CORRUPT``) import nothing from
``parser_probe`` and therefore collect and run today.

Fixtures reused verbatim from tests/fixtures/parser_check.py (T002):
``PARSER_PARAMETERS_XML_HC``, ``PARSER_PARAMETERS_XML_XAMPLE``,
``PARSER_PARAMETERS_XML_CORRUPT``.

Test-only XML resolver (``_resolve_active_parser_from_xml``): SPEC.md:210
names the real property as ``LanguageProject.MorphologicalDataOA.ActiveParser``
-- already a resolved string in production, computed inside FieldWorks' own
C# getter (``OverridesLing_MoClasses.cs:4213``), which
``check_active_parser`` simply reads and compares; it does not parse XML
itself. Since CP1 has no live LCM (READ_ONLY_SAFE, no LcmCache), this file's
``FakeProject``/``_ActiveParserSource`` reproduce just enough of that C#
getter's documented behaviour -- parse ``ParserParameters`` XML, default to
``"XAmple"`` on any parse failure -- to turn the T002 XML fixtures into the
plain string ``project.MorphologicalDataOA.ActiveParser`` would expose live,
matching fixtures/parser_check.py's own docstring: "A test asserting on this
fixture asserts the resolved engine is XAmple, not that parsing raises."
This resolver is test infrastructure only; it makes no claim about
``check_active_parser``'s own implementation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server.response_models import (  # noqa: E402
    validate_detail,
    ParserEngineMismatchDetail,
)

from fixtures.parser_check import (  # noqa: E402
    PARSER_PARAMETERS_XML_HC,
    PARSER_PARAMETERS_XML_XAMPLE,
    PARSER_PARAMETERS_XML_CORRUPT,
)


# ---------------------------------------------------------------------------
# Test-only ActiveParser resolver + fake project (see module docstring)
# ---------------------------------------------------------------------------

def _resolve_active_parser_from_xml(xml: Optional[str]) -> str:
    """Mimic OverridesLing_MoClasses.cs:4213's fail-safe getter: parse
    ``ParserParameters`` XML and return whichever of ``<HC>``/``<XAmple>``
    is the top-level child; default to ``"XAmple"`` on ANY parse failure
    (malformed XML, missing/unrecognised child, or no XML at all) --
    SPEC.md:672-680. Never silently resolves to "HC" on a corrupt input."""
    if not xml:
        return "XAmple"
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return "XAmple"
    for child in root:
        if child.tag in ("HC", "XAmple"):
            return child.tag
    return "XAmple"


class _ActiveParserSource:
    """Stand-in for ``MorphologicalDataOA``: exposes a live ``ActiveParser``
    property, re-computed on every access (never memoized), matching
    SPEC.md:672's "re-read live on every call, never cached per session".

    ``read_count`` lets a test prove ``check_active_parser`` actually
    touched this property on a given call -- a per-session cache that
    returns a stale/memoized verdict without re-reading would leave this
    counter flat, which is exactly what TestLiveRereadNeverCached asserts
    against.

    Two ways to drive the resolved value:
      - ``set_xml(...)`` -- resolved via ``_resolve_active_parser_from_xml``,
        exercising the fail-safe XML behaviour (property 3).
      - ``force_value(...)`` -- returns an arbitrary string verbatim,
        bypassing the resolver entirely. Real FieldWorks only ever yields
        exactly "XAmple" or "HC" (SPEC.md:676); this escape hatch exists
        solely to test ``check_active_parser``'s OWN comparison operator
        in isolation from that closed-set guarantee (property 2) -- e.g.
        proving it does not lower-case or otherwise normalise before
        comparing.
    """

    def __init__(self, xml: Optional[str] = None, *, forced_value: Optional[str] = None):
        self._xml = xml
        self._forced_value = forced_value
        self.read_count = 0

    @property
    def ActiveParser(self) -> str:
        self.read_count += 1
        if self._forced_value is not None:
            return self._forced_value
        return _resolve_active_parser_from_xml(self._xml)

    def set_xml(self, xml: str) -> None:
        self._xml = xml
        self._forced_value = None

    def force_value(self, value: str) -> None:
        self._forced_value = value
        self._xml = None


class FakeProject:
    """Stand-in for the LCM project object, exposing only the one path
    SPEC.md:210 names: ``project.MorphologicalDataOA.ActiveParser``."""

    def __init__(self, xml: Optional[str] = None, *, forced_value: Optional[str] = None):
        self.MorphologicalDataOA = _ActiveParserSource(xml=xml, forced_value=forced_value)


# ---------------------------------------------------------------------------
# Sanity check on this file's own resolver against the T002 fixtures --
# no parser_probe import, so these collect and run regardless of T024.
# ---------------------------------------------------------------------------

class TestOwnXmlResolverSanity:
    def test_hc_fixture_resolves_to_HC(self):
        assert _resolve_active_parser_from_xml(PARSER_PARAMETERS_XML_HC) == "HC"

    def test_xample_fixture_resolves_to_XAmple(self):
        assert _resolve_active_parser_from_xml(PARSER_PARAMETERS_XML_XAMPLE) == "XAmple"

    def test_corrupt_fixture_is_genuinely_unparsable_xml(self):
        with pytest.raises(ET.ParseError):
            ET.fromstring(PARSER_PARAMETERS_XML_CORRUPT)

    def test_corrupt_fixture_resolves_to_XAmple_not_an_error_sentinel(self):
        # fixtures/parser_check.py's own docstring: "A test asserting on
        # this fixture asserts the resolved engine is XAmple, not that
        # parsing raises."
        assert _resolve_active_parser_from_xml(PARSER_PARAMETERS_XML_CORRUPT) == "XAmple"


# ---------------------------------------------------------------------------
# Property 1: refusal, not a parse -- carries the contract's three fields,
# validated through validate_detail() (not the bare model class)
# ---------------------------------------------------------------------------

class TestRefusalCarriesContractFields:
    def test_xample_active_with_hc_only_supported_raises_with_contract_fields(self):
        from flextoolsmcp.server.parser_probe import (
            check_active_parser,
            ParserEngineMismatchError,
        )

        project = FakeProject(xml=PARSER_PARAMETERS_XML_XAMPLE)

        with pytest.raises(ParserEngineMismatchError) as exc_info:
            check_active_parser(project, supported_engines=("HC",))

        # Through the shared discriminated-union validator, matching T006's
        # precedent -- not ParserEngineMismatchDetail(**...) directly, so a
        # detail this function raises but that AnyDetail forgot to union in
        # would be caught here too.
        detail = validate_detail(exc_info.value.detail)
        assert isinstance(detail, ParserEngineMismatchDetail)
        assert detail.error_code == "parser_engine_mismatch"
        assert detail.configured_engine == "XAmple"
        assert detail.supported_engines == ["HC"]
        assert isinstance(detail.hint, str) and detail.hint

    def test_matching_engine_returns_none_and_never_raises(self):
        from flextoolsmcp.server.parser_probe import check_active_parser

        project = FakeProject(xml=PARSER_PARAMETERS_XML_HC)
        assert check_active_parser(project, supported_engines=("HC",)) is None


class TestNoParseAttemptedOnRefusal:
    """CP1 boundary, applied to this specific helper: a refusal must never
    touch a parser/CLR object. Mirrors the LcmCache-spy technique in
    tests/test_parser_probe.py's TestCP1Boundary, so the same style of
    regression guard covers this helper too."""

    def test_refusal_never_touches_lcmcache(self, monkeypatch):
        import types as _types

        from flextoolsmcp.server.parser_probe import (
            check_active_parser,
            ParserEngineMismatchError,
        )

        calls = []

        def _spy(*args, **kwargs):
            calls.append((args, kwargs))
            return object()

        fake_lcmodel_module = _types.ModuleType("SIL.LCModel")
        fake_lcmodel_module.LcmCache = _spy
        fake_sil_module = _types.ModuleType("SIL")
        fake_sil_module.LCModel = fake_lcmodel_module
        monkeypatch.setitem(sys.modules, "SIL", fake_sil_module)
        monkeypatch.setitem(sys.modules, "SIL.LCModel", fake_lcmodel_module)

        project = FakeProject(xml=PARSER_PARAMETERS_XML_XAMPLE)
        with pytest.raises(ParserEngineMismatchError):
            check_active_parser(project, supported_engines=("HC",))

        assert calls == []


# ---------------------------------------------------------------------------
# Property 2: accepted values are exactly "XAmple" and "HC", case-sensitive
# ---------------------------------------------------------------------------

class TestCaseSensitiveClosedSet:
    def test_exact_case_HC_is_accepted(self):
        from flextoolsmcp.server.parser_probe import check_active_parser

        project = FakeProject(forced_value="HC")
        assert check_active_parser(project, supported_engines=("HC",)) is None

    @pytest.mark.parametrize("mis_cased", ["hc", "Hc", "hC"])
    def test_case_variants_of_hc_are_not_silently_accepted(self, mis_cased):
        from flextoolsmcp.server.parser_probe import (
            check_active_parser,
            ParserEngineMismatchError,
        )

        project = FakeProject(forced_value=mis_cased)
        with pytest.raises(ParserEngineMismatchError) as exc_info:
            check_active_parser(project, supported_engines=("HC",))

        detail = validate_detail(exc_info.value.detail)
        assert detail.configured_engine == mis_cased

    @pytest.mark.parametrize("bogus", ["xample", "HERMITCRAB", "hermitcrab", "Xample"])
    def test_other_case_or_out_of_set_values_refuse(self, bogus):
        from flextoolsmcp.server.parser_probe import (
            check_active_parser,
            ParserEngineMismatchError,
        )

        project = FakeProject(forced_value=bogus)
        with pytest.raises(ParserEngineMismatchError) as exc_info:
            check_active_parser(project, supported_engines=("HC",))

        detail = validate_detail(exc_info.value.detail)
        assert detail.configured_engine == bogus


# ---------------------------------------------------------------------------
# Property 3: fail-safe on corruption -- a corrupt ParserParameters XML
# reads as XAmple and refuses; never silently HC.
# ---------------------------------------------------------------------------

class TestFailSafeOnCorruptParserParameters:
    def test_corrupt_xml_refuses_as_xample_when_hc_required(self):
        from flextoolsmcp.server.parser_probe import (
            check_active_parser,
            ParserEngineMismatchError,
        )

        project = FakeProject(xml=PARSER_PARAMETERS_XML_CORRUPT)

        # The critical direction: if a future change inverted the default
        # to silently resolve corruption as "HC", this call would not
        # raise at all (HC is in supported_engines) and pytest.raises
        # itself would fail loudly with "DID NOT RAISE" -- catching the
        # inversion even before the field assertions below run.
        with pytest.raises(ParserEngineMismatchError) as exc_info:
            check_active_parser(project, supported_engines=("HC",))

        detail = validate_detail(exc_info.value.detail)
        assert detail.configured_engine == "XAmple"
        assert detail.configured_engine != "HC"

    def test_corrupt_xml_resolves_as_literal_xample_not_an_error_state(self):
        # Double-confirms the resolution is the literal string "XAmple"
        # (not some third "unknown"/error sentinel that happens to also
        # fail the HC check above): when XAmple IS the supported engine,
        # the corrupt-XML project must be accepted with no refusal at all.
        from flextoolsmcp.server.parser_probe import check_active_parser

        project = FakeProject(xml=PARSER_PARAMETERS_XML_CORRUPT)
        assert check_active_parser(project, supported_engines=("XAmple",)) is None


# ---------------------------------------------------------------------------
# Property 4: ActiveParser is re-read live on every call, never cached per
# session -- constructed so a per-session cache genuinely fails these tests.
# ---------------------------------------------------------------------------

class TestLiveRereadNeverCachedPerSession:
    def test_flip_between_two_calls_on_the_same_project_is_observed(self):
        from flextoolsmcp.server.parser_probe import (
            check_active_parser,
            ParserEngineMismatchError,
        )

        project = FakeProject(xml=PARSER_PARAMETERS_XML_HC)

        # Call 1: HC active, HC supported -> accepted.
        assert check_active_parser(project, supported_engines=("HC",)) is None
        assert project.MorphologicalDataOA.read_count == 1

        # User flips the parser mid-session, same project object, same
        # session (Words > Parser > Choose Parser, SPEC.md:672-675).
        project.MorphologicalDataOA.set_xml(PARSER_PARAMETERS_XML_XAMPLE)

        # Call 2 on the SAME project object must see the NEW value. A
        # per-session cache keyed on the project (memoizing call 1's
        # verdict) would return None again here, and this pytest.raises
        # block would fail with "DID NOT RAISE" -- the cache is genuinely
        # caught, not just plausibly caught.
        with pytest.raises(ParserEngineMismatchError) as exc_info:
            check_active_parser(project, supported_engines=("HC",))

        # Belt-and-suspenders: even a cache subtle enough to still raise
        # correctly (e.g. one that caches only the resolved *string*, not
        # the verdict) is caught here, because the live property itself
        # must have been touched a second time.
        assert project.MorphologicalDataOA.read_count == 2
        detail = validate_detail(exc_info.value.detail)
        assert detail.configured_engine == "XAmple"

    def test_three_consecutive_calls_each_increment_the_live_read_count(self):
        from flextoolsmcp.server.parser_probe import check_active_parser

        project = FakeProject(xml=PARSER_PARAMETERS_XML_HC)
        for expected_count in (1, 2, 3):
            check_active_parser(project, supported_engines=("HC",))
            assert project.MorphologicalDataOA.read_count == expected_count, (
                "check_active_parser must re-read ActiveParser live on "
                "every call -- a per-session cache would stop incrementing "
                "this counter after the first call."
            )

    def test_flip_back_to_supported_engine_mid_session_is_also_observed(self):
        # Symmetric case: XAmple -> HC. A cache that only ever "sticks"
        # in the refusing direction (plausible if someone memoizes just
        # the raised exception) would fail this the other way around.
        from flextoolsmcp.server.parser_probe import (
            check_active_parser,
            ParserEngineMismatchError,
        )

        project = FakeProject(xml=PARSER_PARAMETERS_XML_XAMPLE)

        with pytest.raises(ParserEngineMismatchError):
            check_active_parser(project, supported_engines=("HC",))
        assert project.MorphologicalDataOA.read_count == 1

        project.MorphologicalDataOA.set_xml(PARSER_PARAMETERS_XML_HC)

        assert check_active_parser(project, supported_engines=("HC",)) is None
        assert project.MorphologicalDataOA.read_count == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
