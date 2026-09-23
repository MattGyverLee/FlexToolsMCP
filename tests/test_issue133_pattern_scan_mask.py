#!/usr/bin/env python3
"""Regression tests for issue #133: regex scans ignore comments and strings."""

import pytest

from server.validators import (
    _code_for_pattern_scan,
    _mask_comments_and_strings,
    certify_script_readonly,
    detect_missing_operations_imports,
    detect_wrong_library_imports,
)

pytestmark = pytest.mark.requires_flex


@pytest.fixture(scope="module")
def api_index():
    from server import APIIndex, get_index_dir

    index_dir = get_index_dir() / "python"
    flexicon_files = sorted(index_dir.glob("flexicon_api_v*.json"))
    if not flexicon_files:
        pytest.skip("flexicon index not available")
    return APIIndex.load(index_dir)


def test_mask_does_not_treat_string_contents_as_code():
    code = 'msg = "tag#1"; x = 1\n'
    masked = _code_for_pattern_scan(code)
    assert "tag#1" not in masked
    assert "project.LexEntry.Create" not in masked


def test_mask_blanks_comment_operations_mention():
    code = "# AgentOperations.Create(x)\nfor e in project.LexEntry.GetAll():\n    pass\n"
    masked = _code_for_pattern_scan(code)
    assert "AgentOperations" not in masked.split("\n")[0].strip()


def test_certify_readonly_ignores_comment_decoy(api_index):
    code = """
# LexSenseOperations.Duplicate(s) would mutate
for entry in project.LexEntry.GetAll():
    project.LexEntry.GetLexemeForm(entry)
"""
    cert = certify_script_readonly(code, api_index)
    assert cert["is_certified_readonly"] is True
    assert not cert.get("mutating_calls")


def test_certify_readonly_ignores_string_decoy(api_index):
    code = '''
note = "project.Agents.Create(x)"
for entry in project.LexEntry.GetAll():
    project.LexEntry.GetLexemeForm(entry)
'''
    cert = certify_script_readonly(code, api_index)
    assert cert["is_certified_readonly"] is True


def test_real_mutation_still_detected_with_masked_scan(api_index):
    code = "project.Agents.Create(agent)\n"
    cert = certify_script_readonly(code, api_index)
    assert cert["is_certified_readonly"] is False
    assert cert.get("unprotected_liblcm_calls")


def test_missing_import_detector_ignores_comment():
    code = "# maybe use MorphRuleOperations.Foo(x)\nfor e in project.LexEntry.GetAll():\n    pass\n"
    result = detect_missing_operations_imports(code, "flexicon")
    assert result["has_missing"] is False


def test_wrong_library_detector_ignores_comment():
    code = "# from flexlibs import FLExProject\nfor e in project.LexEntry.GetAll():\n    pass\n"
    result = detect_wrong_library_imports(code, "flexicon")
    assert result["has_wrong_imports"] is False

