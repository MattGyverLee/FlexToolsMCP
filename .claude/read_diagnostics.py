#!/usr/bin/env python3
"""Read and display Pylance diagnostics from .vscode/diagnostics.json"""

import json
import sys
from pathlib import Path

def read_diagnostics():
    """Read diagnostics from .vscode/diagnostics.json and display them."""
    diag_file = Path(".vscode/diagnostics.json")

    if not diag_file.exists():
        print("[INFO] No diagnostics file yet. Run a code change to trigger diagnostic export.")
        return

    try:
        with open(diag_file) as f:
            content = f.read()
        # Skip any non-JSON lines (e.g., warnings from pyright)
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if line.strip().startswith('{'):
                content = '\n'.join(lines[i:])
                break
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[ERROR] Diagnostics file is invalid JSON: {e}")
        return

    diagnostics = data.get("generalDiagnostics", [])

    if not diagnostics:
        print("[OK] No Pylance errors found!")
        return

    # Group by file
    by_file = {}
    for diag in diagnostics:
        file_path = diag.get("file", "unknown")
        if file_path not in by_file:
            by_file[file_path] = []
        by_file[file_path].append(diag)

    # Print summary
    print(f"\n{'='*80}")
    print(f"PYLANCE DIAGNOSTICS: {len(diagnostics)} error(s) in {len(by_file)} file(s)")
    print(f"{'='*80}\n")

    for file_path in sorted(by_file.keys()):
        errors = by_file[file_path]
        # Shorten path for display
        display_path = file_path.replace("d:\\Github\\_Projects\\_LEX\\FlexToolsMCP\\", "")
        print(f"\n{display_path} ({len(errors)} error{'s' if len(errors) > 1 else ''})")
        print("-" * 80)

        for diag in sorted(errors, key=lambda d: d.get("range", {}).get("start", {}).get("line", 0)):
            line = diag.get("range", {}).get("start", {}).get("line", 0)
            severity = diag.get("severity", "error").upper()
            message = diag.get("message", "").split("\n")[0]
            rule = diag.get("rule", "")

            print(f"  Line {line+1}: [{severity}] {message}")
            if rule:
                print(f"    Rule: {rule}")

if __name__ == "__main__":
    read_diagnostics()
