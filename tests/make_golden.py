#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regenerate golden fixtures for test_response_contract.py.

Usage:
    python tests/make_golden.py [--regen]

Without --regen the script prints a diff of what would change and exits 1
if any fixture is stale (useful in CI).  With --regen it writes the files.

Golden fixtures live at:  tests/golden/responses/<error_code>.json
"""

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root or from tests/
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.response_utils import error_response, CONTRACT_VERSION

GOLDEN_DIR = Path(__file__).parent / "golden" / "responses"

# ---------------------------------------------------------------------------
# Issue #46: Auto-fix golden fixtures (success-shape, not error_response shape)
# ---------------------------------------------------------------------------

AUTO_FIX_GOLDEN_FIXTURES: dict[str, dict] = {
    # (a) successful casting auto-fix applied (one concrete target)
    "auto_fix_casting_applied": {
        "status": "ok",
        "_contract": CONTRACT_VERSION,
        "success": True,
        "messages": [],
        "auto_fixes_applied": [
            {
                "kind": "casting",
                "line": 3,
                "original": "owner.HeadWord",
                "replacement": "ILexEntry(owner).HeadWord",
                "cast_interface": "ILexEntry",
            }
        ],
        "auto_fix_note": (
            "[AUTO-FIX] 1 safe rewrite(s) were applied to the in-memory copy of your code "
            "before execution:\n\n"
            "  Line 3 [CASTING]: 'owner.HeadWord' -> 'ILexEntry(owner).HeadWord' (cast to ILexEntry)\n\n"
            "[ACTION REQUIRED] The fixes were applied only to the executed copy.\n"
            "  Source: <submitted code>\n"
            "  Update your source file at the line numbers listed above or you will\n"
            "  see this auto-fix note every time you run this code."
        ),
    },
    # (b) successful typo auto-fix applied (ratio>=0.9, single candidate)
    "auto_fix_typo_applied": {
        "status": "ok",
        "_contract": CONTRACT_VERSION,
        "success": True,
        "messages": [],
        "auto_fixes_applied": [
            {
                "kind": "typo",
                "line": 2,
                "col": 12,
                "original": "LexEntries",
                "replacement": "LexEntry",
                "match_ratio": 0.92,
            }
        ],
        "auto_fix_note": (
            "[AUTO-FIX] 1 safe rewrite(s) were applied to the in-memory copy of your code "
            "before execution:\n\n"
            "  Line 2 [TYPO]: 'LexEntries' -> 'LexEntry' (92% match)\n\n"
            "[ACTION REQUIRED] The fixes were applied only to the executed copy.\n"
            "  Source: <submitted code>\n"
            "  Update your source file at the line numbers listed above or you will\n"
            "  see this auto-fix note every time you run this code."
        ),
    },
    # (c) ambiguous casting correctly NOT auto-fixed (stays rejected, original payload)
    "auto_fix_ambiguous_not_applied": {
        "status": "error",
        "_contract": CONTRACT_VERSION,
        "error_code": "casting_issues_detected",
        "message": "Found 1 polymorphic property access issue(s) that require casting.",
        "casting_issues": [
            {
                "line": 5,
                "property": "SenseRA",
                "cast_interface": None,  # ambiguous -> not auto-fixed
                "rewrite": None,
                "severity": "error",
            }
        ],
        # NO auto_fixes_applied or auto_fix_note key -- ambiguous stays rejected
    },
}

# Canonical minimal payload for each of the 16 known error codes.
# Keys must NOT overlap with canonical envelope keys (status, error_code,
# message, _contract, error) -- those are injected by error_response().
GOLDEN_FIXTURES: dict[str, dict] = {
    "syntax_error": {
        "message": "Invalid Python syntax at line 1: invalid syntax",
    },
    "server_state_error": {
        "message": "Server is not in a valid state",
        "server_state": {"is_healthy": False, "issues": []},
    },
    "partial_module_structure": {
        "message": "Module is missing required structural elements",
        "missing_elements": ["docs"],
    },
    "unprotected_writes": {
        "message": "Code contains unprotected write operations",
        "mutating_calls": [],
    },
    "casting_issues_detected": {
        "message": "LibLCM casting issues detected in code",
        "casting_issues": [],
    },
    "api_discovery_required": {
        "message": "API discovery required before running",
        "detected_candidates": [],
    },
    "undiscovered_entity": {
        "message": "Undiscovered entity referenced in code",
        "undiscovered": [],
    },
    "undefined_variables": {
        "message": "Undefined variables detected",
        "undefined_vars": [],
    },
    "missing_imports": {
        "message": "Required imports are missing",
        "missing_imports": [],
        "api_mode": "flexicon",
    },
    "wrong_library_imports": {
        "message": "Imports are from the wrong library",
        "wrong_imports": [],
        "api_mode": "flexicon",
    },
    "invalid_api_chain": {
        "message": "Invalid API method chain detected",
        "issues": [],
    },
    "project_locked": {
        "message": "FieldWorks project is locked by another process",
        "guidance": "Close FieldWorks and try again",
    },
    "project_drive_unavailable": {
        "message": "Project drive is not available",
    },
    "project_path_mismatch": {
        "message": "Project path does not match expected location",
    },
    "project_not_found": {
        "message": "FieldWorks project not found",
    },
    "runtime_error": {
        "message": "Code raised an exception at runtime",
    },
}


def _build_fixture(code: str, extras: dict) -> dict:
    """Generate a fixture dict by calling error_response() and parsing the result."""
    message = extras.pop("message")
    resp_list = error_response(code, message, **extras)
    item = resp_list[0]
    if isinstance(item, dict):
        return json.loads(item["text"])
    return json.loads(item.text)


def _build_auto_fix_fixture(data: dict) -> dict:
    """Auto-fix fixtures are pre-built dicts (not through error_response)."""
    return dict(data)


def _load_existing(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--regen",
        action="store_true",
        help="Write fixture files (default: dry-run, exits 1 if stale)",
    )
    args = parser.parse_args(argv)

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    stale: list[str] = []
    for code, raw_extras in GOLDEN_FIXTURES.items():
        # Work on a copy so we can pop 'message' without mutating the original.
        extras = dict(raw_extras)
        fixture = _build_fixture(code, extras)
        path = GOLDEN_DIR / f"{code}.json"
        existing = _load_existing(path)

        if existing != fixture:
            stale.append(code)
            if args.regen:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(fixture, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                print(f"[REGEN] {path.name}")
            else:
                print(f"[STALE] {path.name}")
        else:
            print(f"[OK]    {path.name}")

    # Issue #46: auto-fix scenario fixtures
    for fixture_name, fixture_data in AUTO_FIX_GOLDEN_FIXTURES.items():
        fixture = _build_auto_fix_fixture(fixture_data)
        path = GOLDEN_DIR / f"{fixture_name}.json"
        existing = _load_existing(path)

        if existing != fixture:
            stale.append(fixture_name)
            if args.regen:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(fixture, f, indent=2, ensure_ascii=False)
                    f.write("\n")
                print(f"[REGEN] {path.name}")
            else:
                print(f"[STALE] {path.name}")
        else:
            print(f"[OK]    {path.name}")

    if stale and not args.regen:
        print(
            f"\n{len(stale)} fixture(s) are stale. "
            "Run: python tests/make_golden.py --regen"
        )
        sys.exit(1)
    elif stale and args.regen:
        print(f"\n[DONE] Regenerated {len(stale)} fixture(s).")
    else:
        print("\n[OK] All golden fixtures are up to date.")


if __name__ == "__main__":
    main()
