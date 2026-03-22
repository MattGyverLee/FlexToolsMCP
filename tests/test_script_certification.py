#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for script certification using API index.

Verifies that certify_script_readonly() correctly identifies mutating operations
using the is_mutating field from the index.
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from server.validators import certify_script_readonly


def load_api_index():
    """Load the FlexLibs2 API index."""
    index_file = Path(__file__).parent.parent / "index" / "flexlibs" / "flexlibs2_api_v2.3.2.json"
    if not index_file.exists():
        raise FileNotFoundError(f"API index not found: {index_file}")

    with open(index_file, encoding='utf-8') as f:
        api = json.load(f)

    return {"flexlibs2": api}


def test_readonly_code():
    """Test that read-only code is certified."""
    api_index = load_api_index()

    code = """
    entries = LexEntryOperations(project).GetAll()
    for entry in entries:
        print(entry.Headword)
    """

    cert = certify_script_readonly(code, api_index)
    assert cert["is_certified_readonly"] == True, f"Should be certified readonly, got: {cert}"
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
    assert cert["is_certified_readonly"] == False, f"Should NOT be certified readonly, got: {cert}"
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
    assert cert["is_certified_readonly"] == False, f"Should NOT be certified readonly, got: {cert}"
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
    assert cert["is_certified_readonly"] == False, f"Should NOT be certified readonly"

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


if __name__ == "__main__":
    print("Running script certification tests...\n")

    try:
        test_readonly_code()
        test_create_operation()
        test_delete_operation()
        test_mixed_operations()
        test_index_lookup_source()
        test_confidence_levels()

        print("\n[DONE] All certification tests passed!")
    except AssertionError as e:
        print(f"\n[FAIL] {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
