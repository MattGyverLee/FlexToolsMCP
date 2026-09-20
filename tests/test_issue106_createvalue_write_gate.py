#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #106: `CreateValue` must stay behind the write gate anywhere the object
API index marks it `is_mutating: true`.

The live report isolated this to a per-method drift: `Create` and
`CreateValue` were called through the same receiver shapes, but only `Create`
was classified as mutating. These regressions lock the two relevant families
back together:

- `InflectionFeatureOperations.CreateValue` (the reported bug)
- `PhonFeatureOperations.CreateValue` (same name/docstring family, audited in
  the same pass)
"""

from functools import lru_cache

import pytest

from flextoolsmcp.server import APIIndex, get_index_dir
from flextoolsmcp.server.validators import build_writeability_payload, certify_script_readonly


@lru_cache(maxsize=1)
def _api_index():
    return APIIndex.load(get_index_dir())


@lru_cache(maxsize=1)
def _mutating_methods_by_class():
    entities = (_api_index().flexicon or {}).get("entities", {})
    return {
        class_name: {
            method["name"]
            for method in entity.get("methods", []) or []
            if method.get("is_mutating") and method.get("name")
        }
        for class_name, entity in entities.items()
    }


@pytest.mark.parametrize(
    ("ops_class", "method_name"),
    [
        ("InflectionFeatureOperations", "CreateValue"),
        ("PhonFeatureOperations", "CreateValue"),
    ],
)
def test_real_index_marks_createvalue_mutating(ops_class, method_name):
    assert method_name in _mutating_methods_by_class()[ops_class]


@pytest.mark.parametrize(
    ("code", "expected_call"),
    [
        (
            'infl = project.InflectionFeatures\n'
            'infl.CreateValue(feat, "NC 14", "14")\n',
            "InflectionFeatureOperations.CreateValue",
        ),
        (
            'project.InflectionFeatures.CreateValue(feat, "NC 14", "14")\n',
            "InflectionFeatureOperations.CreateValue",
        ),
        (
            'phon = project.PhonFeatures\n'
            'phon.CreateValue(feat, "+voice", "+")\n',
            "PhonFeatureOperations.CreateValue",
        ),
        (
            'project.PhonFeatures.CreateValue(feat, "+voice", "+")\n',
            "PhonFeatureOperations.CreateValue",
        ),
    ],
)
def test_createvalue_is_classified_mutating_through_issue_shapes(code, expected_call):
    cert = certify_script_readonly(code, _api_index())

    assert cert["is_certified_readonly"] is False
    assert [
        f"{m['class']}.{m['method']}"
        for m in cert["mutating_calls"]
        if m.get("is_mutating")
    ] == [expected_call]

    payload = build_writeability_payload(code, _api_index(), cert=cert)
    assert payload["is_mutating_script"] is True
    assert [m["call"] for m in payload["mutations_detected"]] == [expected_call]
