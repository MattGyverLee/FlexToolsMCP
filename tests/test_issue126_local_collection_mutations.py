#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #126: local container .Add() must not count as raw LCM mutation."""

from flextoolsmcp.server.validators import (
    certify_script_readonly,
    find_liblcm_mutations,
)

_HASHSET_DEDUP = """
from System.Collections.Generic import HashSet
seen = HashSet[str]()
for e in project.LexEntry.GetAll():
    seen.Add(project.LexEntry.GetHeadword(e))
"""

_LCM_COLLECTION_ADD = """
for entry in project.LexEntry.GetAll():
    entry.ComponentLexemesRS.Add(other)
"""


def test_hashset_add_is_not_an_lcm_mutation():
    mutations = find_liblcm_mutations(_HASHSET_DEDUP)
    assert not any(m["method"] == "Add" for m in mutations), mutations


def test_lcm_collection_add_still_detected():
    mutations = find_liblcm_mutations(_LCM_COLLECTION_ADD)
    assert any(m["method"] == "Add" for m in mutations), mutations


def test_hashset_dedup_script_is_certified_readonly():
    cert = certify_script_readonly(_HASHSET_DEDUP, api_index=None)
    assert cert["is_certified_readonly"] is True
    assert cert["unprotected_liblcm_calls"] == []


def test_lcm_collection_add_is_not_certified_readonly():
    cert = certify_script_readonly(_LCM_COLLECTION_ADD, api_index=None)
    assert cert["is_certified_readonly"] is False
    assert cert["unprotected_liblcm_calls"]

