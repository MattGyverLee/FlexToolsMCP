#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for script certification using API index.

Verifies that certify_script_readonly() correctly identifies mutating operations
using the is_mutating field from the index.
"""

import json
import sys
from functools import lru_cache
from pathlib import Path

from server.validators import certify_script_readonly


@lru_cache(maxsize=1)
def load_api_index():
    """Load the FlexLibs2 API index (latest version available).

    Returns an APIIndex instance matching the shape that production code
    passes to certify_script_readonly (attribute access, not dict access).
    The test previously returned a plain dict, which silently broke when
    the validator switched to attribute access in commit 845927e.

    Result is cached to avoid redundant file I/O across multiple tests.
    """
    from server import APIIndex  # imported here to avoid pulling server.py at module load

    index_dir = Path(__file__).parent.parent / "index" / "flexlibs"

    # Find the latest flexlibs2 API file
    flexlibs2_files = sorted(index_dir.glob("flexlibs2_api_v*.json"))
    if not flexlibs2_files:
        raise FileNotFoundError(f"No FlexLibs2 API index found in {index_dir}")

    index_file = flexlibs2_files[-1]  # Use latest version

    with open(index_file, encoding='utf-8') as f:
        api = json.load(f)

    idx = APIIndex()
    idx.flexlibs2 = api
    return idx


def test_readonly_code():
    """Test that read-only code is certified."""
    api_index = load_api_index()

    code = """
    entries = LexEntryOperations(project).GetAll()
    for entry in entries:
        print(entry.Headword)
    """

    cert = certify_script_readonly(code, api_index)
    assert cert["is_certified_readonly"], f"Should be certified readonly, got: {cert}"
    assert cert["confidence"] == "high", f"Should have high confidence, got: {cert['confidence']}"
    assert len(cert["mutating_calls"]) == 0, f"Should have no mutating calls, got: {cert['mutating_calls']}"

    print("[OK] Read-only code certified correctly")


def test_create_operation():
    """Test that Create operations are detected."""
    api_index = load_api_index()

    code = """
    entry = LexEntryOperations(project).Create(headword="water")
    """

    cert = certify_script_readonly(code, api_index)
    assert not cert["is_certified_readonly"], f"Should NOT be certified readonly, got: {cert}"
    assert len(cert["mutating_calls"]) > 0, f"Should detect mutating calls, got: {cert['mutating_calls']}"

    mutating_call = [m for m in cert["mutating_calls"] if m.get("is_mutating")]
    assert len(mutating_call) > 0, f"Should have is_mutating=True calls, got: {cert['mutating_calls']}"

    print("[OK] Create operation detected correctly")


def test_delete_operation():
    """Test that Delete operations are detected."""
    api_index = load_api_index()

    code = """
    LexEntryOperations(project).Delete(entry_id=123)
    """

    cert = certify_script_readonly(code, api_index)
    assert not cert["is_certified_readonly"], f"Should NOT be certified readonly, got: {cert}"
    assert len(cert["mutating_calls"]) > 0, f"Should detect mutating calls"

    print("[OK] Delete operation detected correctly")


def test_mixed_operations():
    """Test that mixed read and write operations are detected."""
    api_index = load_api_index()

    code = """
    entries = LexEntryOperations(project).GetAll()
    for entry in entries:
        new_sense = LexSenseOperations(project).Create(entry=entry)
    """

    cert = certify_script_readonly(code, api_index)
    assert not cert["is_certified_readonly"], f"Should NOT be certified readonly"

    # Should have readonly calls (GetAll) and mutating calls (Create)
    readonly = [m for m in cert["readonly_calls"] if not m.get("is_mutating")]
    mutating = [m for m in cert["mutating_calls"] if m.get("is_mutating")]

    assert len(readonly) > 0, f"Should detect readonly calls"
    assert len(mutating) > 0, f"Should detect mutating calls"

    print("[OK] Mixed operations detected correctly")


def test_index_lookup_source():
    """Test that lookups use the index as source."""
    api_index = load_api_index()

    code = """
    LexEntryOperations(project).Create(headword="test")
    """

    cert = certify_script_readonly(code, api_index)

    # Check that the source is "index"
    calls_from_index = [m for m in cert["mutating_calls"] if m.get("source") == "index"]
    assert len(calls_from_index) > 0, f"Should use index as source, got sources: {[m.get('source') for m in cert['mutating_calls']]}"

    print("[OK] Index lookup working correctly")


def test_confidence_levels():
    """Test that confidence levels are assigned correctly."""
    api_index = load_api_index()

    # High confidence: all from index
    code1 = "LexEntryOperations(project).GetAll()"
    cert1 = certify_script_readonly(code1, api_index)
    assert cert1["confidence"] == "high", f"Read-only should be high confidence, got: {cert1['confidence']}"

    # No confidence needed for empty code
    code2 = "x = 1 + 2"
    cert2 = certify_script_readonly(code2, api_index)
    assert cert2["confidence"] == "high", f"Empty code should be high confidence"

    print("[OK] Confidence levels assigned correctly")


def test_unprotected_liblcm_calls():
    """Test that unprotected raw LibLCM mutations are detected."""
    api_index = load_api_index()

    code = """
    # Direct LibLCM call without protection
    project._cache.CreateObject(...)
    """

    cert = certify_script_readonly(code, api_index)
    assert not cert["is_certified_readonly"], "Should NOT be certified readonly"
    assert len(cert["unprotected_liblcm_calls"]) > 0, "Should detect unprotected LibLCM call"
    assert any(c["method"] == "CreateObject" for c in cert["unprotected_liblcm_calls"])

    print("[OK] Unprotected LibLCM calls detected correctly")


def test_protected_liblcm_with_modifyenabled():
    """Test that LibLCM mutations protected by modifyEnabled are allowed."""
    api_index = load_api_index()

    code = """
    with project.modifyEnabled:
        project._cache.CreateObject(...)
    """

    cert = certify_script_readonly(code, api_index)
    assert cert["is_certified_readonly"], "Should be certified readonly when protected"
    assert len(cert["unprotected_liblcm_calls"]) == 0, "Should have no unprotected calls"
    assert len(cert["protected_liblcm_calls"]) > 0, "Should detect protected LibLCM call"

    print("[OK] Protected LibLCM calls with modifyEnabled allowed")


def test_protected_liblcm_with_writeenabled():
    """Test that LibLCM mutations protected by writeEnabled check are allowed."""
    api_index = load_api_index()

    code = """
    if project.writeEnabled:
        project._cache.CreateObject(...)
    """

    cert = certify_script_readonly(code, api_index)
    assert cert["is_certified_readonly"], "Should be certified readonly when protected"
    assert len(cert["unprotected_liblcm_calls"]) == 0, "Should have no unprotected calls"
    assert len(cert["protected_liblcm_calls"]) > 0, "Should detect protected LibLCM call"

    print("[OK] Protected LibLCM calls with writeEnabled check allowed")


def test_protected_with_modifyallowed():
    """Test that FlexLibs2 mutations protected by modifyAllowed parameter are allowed."""
    api_index = load_api_index()

    code = """
    def Main(project, report, modifyAllowed):
        entries = LexEntryOperations(project).GetAll()
        for entry in entries:
            if modifyAllowed:
                LexEntryOperations(project).SetLexemeForm(entry, "new_form")
                report.Info("Updated")
            else:
                report.Info("(Would update)")
    """

    cert = certify_script_readonly(code, api_index)
    assert cert["is_certified_readonly"], f"Should be certified readonly when protected by modifyAllowed, got: {cert}"
    # Check that SetLexemeForm was detected but is protected (not in the unprotected list)
    mutating = [m for m in cert["mutating_calls"] if m.get("is_mutating")]
    assert len(mutating) == 0, f"Should have no UNPROTECTED mutations, but got: {mutating}"

    print("[OK] Protected FlexLibs2 mutations with modifyAllowed parameter allowed")


def test_protected_liblcm_with_modifyallowed():
    """Test that raw LibLCM mutations protected by modifyAllowed parameter are allowed."""
    api_index = load_api_index()

    code = """
    def Main(project, report, modifyAllowed):
        if modifyAllowed:
            project._cache.CreateObject(...)
            report.Info("Created")
        else:
            report.Info("(Would create)")
    """

    cert = certify_script_readonly(code, api_index)
    assert cert["is_certified_readonly"], "Should be certified readonly when protected by modifyAllowed"
    assert len(cert["unprotected_liblcm_calls"]) == 0, "Should have no unprotected calls"
    assert len(cert["protected_liblcm_calls"]) > 0, "Should detect protected LibLCM call"

    print("[OK] Protected raw LibLCM calls with modifyAllowed parameter allowed")


def test_modifyallowed_comparison():
    """Test that modifyAllowed == True comparisons are recognized as guards."""
    api_index = load_api_index()

    code = """
    if modifyAllowed == True:
        project._cache.DeleteObject(...)
    """

    cert = certify_script_readonly(code, api_index)
    assert cert["is_certified_readonly"], "Should be certified readonly with modifyAllowed == True guard"
    assert len(cert["unprotected_liblcm_calls"]) == 0, "Should have no unprotected calls"
    assert len(cert["protected_liblcm_calls"]) > 0, "Should detect protected LibLCM call"

    print("[OK] modifyAllowed == True comparison recognized as guard")


def test_mixed_protected_and_unprotected():
    """Test mixed protected and unprotected LibLCM calls."""
    api_index = load_api_index()

    code = """
    # Unprotected call
    project._cache.CreateObject(...)

    # Protected call
    with project.modifyEnabled:
        entry.SensesOS.Add(sense)
    """

    cert = certify_script_readonly(code, api_index)
    assert not cert["is_certified_readonly"], "Should NOT be certified due to unprotected call"
    assert len(cert["unprotected_liblcm_calls"]) > 0, "Should detect unprotected CreateObject"
    assert len(cert["protected_liblcm_calls"]) > 0, "Should detect protected Add"

    print("[OK] Mixed protected/unprotected LibLCM calls detected correctly")


def test_project_accessor_create_unprotected():
    """project.<Accessor>.Create(...) outside a guard must be blocked."""
    api_index = load_api_index()

    code = """
    def Main(project, report, modifyAllowed):
        entry = project.LexEntry.Create(headword="water")
    """

    cert = certify_script_readonly(code, api_index)
    assert not cert["is_certified_readonly"], (
        f"Unguarded project.LexEntry.Create should NOT be certified, got: {cert}"
    )
    assert len(cert["unprotected_liblcm_calls"]) > 0, (
        f"Should flag project.LexEntry.Create as unprotected, got: {cert['unprotected_liblcm_calls']}"
    )

    print("[OK] Unprotected project.<X>.Create() detected correctly")


def test_project_accessor_create_protected():
    """project.<Accessor>.Create(...) inside `if modifyAllowed:` must certify clean.

    Regression for the validator bug where raw_lcm_patterns triggered a hard
    block even when the mutation was correctly guarded, producing the
    contradictory "Found 0 unprotected mutation(s)" + execution-blocked output.
    """
    api_index = load_api_index()

    code = """
    def Main(project, report, modifyAllowed):
        if modifyAllowed:
            entry = project.LexEntry.Create(headword="water")
            report.Info("Created entry")
        else:
            report.Info("(Would create entry)")
    """

    cert = certify_script_readonly(code, api_index)
    assert cert["is_certified_readonly"], (
        f"Guarded project.LexEntry.Create should be certified readonly, got: {cert}"
    )
    assert len(cert["unprotected_liblcm_calls"]) == 0, (
        f"Should have no unprotected calls when guarded, got: {cert['unprotected_liblcm_calls']}"
    )
    assert len(cert["protected_liblcm_calls"]) > 0, (
        f"Should record the guarded mutation in protected_liblcm_calls, got: {cert['protected_liblcm_calls']}"
    )

    print("[OK] Protected project.<X>.Create() certified clean")


def test_collection_mutations():
    """Test detection of collection mutations (Add, Remove, Clear, Insert)."""
    api_index = load_api_index()

    code = """
    entry.SensesOS.Add(sense)
    entry.SensesOS.Remove(old_sense)
    entry.AlternateFormsOS.Clear()
    """

    cert = certify_script_readonly(code, api_index)
    assert not cert["is_certified_readonly"], "Should NOT be certified readonly"
    assert len(cert["unprotected_liblcm_calls"]) >= 3, "Should detect all 3 unprotected mutations"

    print("[OK] Collection mutations detected correctly")


if __name__ == "__main__":
    print("Running script certification tests...\n")

    try:
        test_readonly_code()
        test_create_operation()
        test_delete_operation()
        test_mixed_operations()
        test_index_lookup_source()
        test_confidence_levels()
        test_unprotected_liblcm_calls()
        test_protected_liblcm_with_modifyenabled()
        test_protected_liblcm_with_writeenabled()
        test_protected_with_modifyallowed()
        test_protected_liblcm_with_modifyallowed()
        test_modifyallowed_comparison()
        test_mixed_protected_and_unprotected()
        test_project_accessor_create_unprotected()
        test_project_accessor_create_protected()
        test_collection_mutations()

        print("\n[DONE] All certification tests passed!")
    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
