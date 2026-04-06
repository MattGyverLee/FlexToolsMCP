#!/usr/bin/env python3
"""Test casting detection system with Dennis's HeadWord error case."""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from server.validators import detect_casting_needs

# Test Case 1: Dennis's actual error - accessing HeadWord on sense.Owner
print("[TEST 1] Dennis's HeadWord Error Case")
print("=" * 60)

dennis_code = """
for sense in senses:
    entry = sense.Owner
    hw = entry.HeadWord.Text  # ICmObject doesn't have HeadWord
    report.Info(f'Entry: {hw}')
"""

result = detect_casting_needs(dennis_code)
print(f"Casting issues detected: {result['has_casting_issues']}")
print(f"Severity: {result['severity']}")

if result['casting_issues']:
    for issue in result['casting_issues']:
        print(f"\n  Issue at line {issue['line']}:")
        print(f"    Property: {issue['property']}")
        print(f"    Pattern: {issue['pattern']}")
        print(f"    Missing on: {issue['missing_on']}")
        print(f"    Available on: {issue['available_on']}")
        print(f"\n    Suggested fix:")
        print("    " + "\n    ".join(issue['fix'].split("\n")))

# Test Case 2: ReversalEntriesRC access (flexlibs2 wrapping issue)
print("\n\n[TEST 2] ReversalEntriesRC Issue (flexlibs2 wrapped object)")
print("=" * 60)

reversals_code = """
sense = senses[0]
reversals = sense.ReversalEntriesRC  # May not exist on flexlibs2 wrapped ILexSense
for rev in reversals:
    report.Info(rev.Form)
"""

result = detect_casting_needs(reversals_code)
print(f"Casting issues detected: {result['has_casting_issues']}")

if result['casting_issues']:
    for issue in result['casting_issues']:
        print(f"\n  Issue at line {issue['line']}:")
        print(f"    Property: {issue['property']}")
        print(f"    Suggested helper: {issue['flexlibs2_helper']}")

# Test Case 3: Clean code with no issues
print("\n\n[TEST 3] Clean Code (no casting issues)")
print("=" * 60)

clean_code = """
from SIL.LCModel import ILexEntry

for sense in senses:
    entry = ILexEntry(sense.Owner)  # Explicit casting - correct!
    hw = entry.HeadWord.Text
    report.Info(f'Entry: {hw}')
"""

result = detect_casting_needs(clean_code)
print(f"Casting issues detected: {result['has_casting_issues']}")
print(f"Severity: {result['severity']}")

print("\n" + "=" * 60)
print("Test Summary: All 3 test cases executed successfully")
print("=" * 60)
