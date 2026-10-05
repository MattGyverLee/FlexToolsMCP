#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #319: reflection_bypass false positive on hasattr of flexicon wrappers.

Residual false positive of #277: ``hasattr(project.Texts, "GetGuid")`` was
refused because ``project.Texts`` is an attribute receiver, which the
#277 gate assumed could reach LCM. ``project.Texts`` is a flexicon
Operations wrapper (FLExProject facade property), not an LCM object, so the
gate now exempts receivers resolved to flexicon Operations-wrapper facade
properties -- and still refuses genuine LCM reflection.
"""

import pytest

from flextoolsmcp.server import validators
from flextoolsmcp.server.validators import (
    _flexicon_operations_facade_attrs,
    detect_reflection_bypass,
)


@pytest.fixture(scope="module")
def facade_attrs():
    attrs = _flexicon_operations_facade_attrs()
    if "Texts" not in attrs:
        pytest.skip("installed flexicon has no Texts facade property")
    return attrs


class TestIssue319FacadeExemption:
    def test_hasattr_project_texts_getguid_not_flagged(self, facade_attrs):
        # The exact false positive from the runtime log (issue #319).
        code = 'if hasattr(project.Texts, "GetGuid"):\n    report.Info("ok")\n'
        result = detect_reflection_bypass(code)
        assert not result["has_reflection_bypass"], result["findings"]

    def test_getattr_project_wordforms_lcm_member_not_flagged(self, facade_attrs):
        code = 'x = getattr(project.Wordforms, "Guid")\n'
        result = detect_reflection_bypass(code)
        assert not result["has_reflection_bypass"], result["findings"]

    def test_setattr_project_lexentry_not_flagged(self, facade_attrs):
        code = 'if modifyAllowed:\n    setattr(project.LexEntry, "Guid", g)\n'
        result = detect_reflection_bypass(code)
        assert not result["has_reflection_bypass"], result["findings"]

    def test_alias_property_exempt(self, facade_attrs):
        # project.Features is an alias of self.InflectionFeatures (an
        # Operations wrapper); the alias chain must resolve to the exemption.
        assert "Features" in facade_attrs
        code = 'x = hasattr(project.Features, "Find")\n'
        result = detect_reflection_bypass(code)
        assert not result["has_reflection_bypass"], result["findings"]

    def test_cache_not_exempt(self):
        # project.Cache returns the raw LcmCache escape hatch -- reflection
        # on it can genuinely reach LCM and must keep being flagged.
        assert "Cache" not in _flexicon_operations_facade_attrs()
        code = 'x = hasattr(project.Cache, "ServiceLocator")\n'
        result = detect_reflection_bypass(code)
        assert result["has_reflection_bypass"]
        assert any("ServiceLocator" in f.get("expr", "") for f in result["findings"])

    def test_unknown_facade_property_still_flagged(self):
        # A facade property the scanner did not classify (or a future one)
        # stays conservative: flagged, as before #319.
        code = 'x = hasattr(project.SomeFutureFacade, "GetGuid")\n'
        result = detect_reflection_bypass(code)
        assert result["has_reflection_bypass"]

    def test_two_hop_receiver_still_flagged(self):
        # Deeper chains than one hop (wrapper methods can return raw LCM
        # objects) are not exempt.
        code = 'x = hasattr(project.Texts.Foo, "GetGuid")\n'
        result = detect_reflection_bypass(code)
        assert result["has_reflection_bypass"]

    def test_bare_project_receiver_still_flagged(self):
        # The FLExProject instance itself can reach project.Cache, so the
        # bare `project` name keeps its pre-#319 conservative treatment.
        code = 'x = getattr(project, "Cache")\n'
        result = detect_reflection_bypass(code)
        assert result["has_reflection_bypass"]


class TestIssue319GenuineLCMStillRefused:
    def test_hasattr_lcm_object_still_flagged(self):
        code = 'if hasattr(text, "GetGuid"):\n    report.Info("ok")\n'
        result = detect_reflection_bypass(code)
        assert result["has_reflection_bypass"]

    def test_getattr_set_string_still_flagged(self):
        code = 'if modifyAllowed:\n    getattr(ms, "set_String")(ws, value)\n'
        result = detect_reflection_bypass(code)
        assert result["has_reflection_bypass"]


class TestIssue319ScanRobustness:
    def test_scan_never_raises(self):
        # The scan must be total: flexicon missing or FLExProject.py
        # unparsable yields an empty (conservative) set, never an error.
        assert isinstance(_flexicon_operations_facade_attrs(), frozenset)

    def test_missing_flexicon_falls_back_to_old_behavior(self, monkeypatch):
        import importlib.util

        monkeypatch.setattr(importlib.util, "find_spec", lambda *a, **k: None)
        validators._FLEXICON_OPERATIONS_FACADE_ATTRS = None
        try:
            assert _flexicon_operations_facade_attrs() == frozenset()
            code = 'x = hasattr(project.Texts, "GetGuid")\n'
            result = detect_reflection_bypass(code)
            assert result["has_reflection_bypass"]
        finally:
            validators._FLEXICON_OPERATIONS_FACADE_ATTRS = None
