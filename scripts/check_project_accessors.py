#!/usr/bin/env python3
"""Check the FLExProject accessor allowlist against a live flexicon install.

Issue #84 background
--------------------
``validators._project_accessors()`` builds part of its allowlist by stripping
``"Operations"`` off every entry in ``KNOWN_OPERATIONS``
(``LexEntryOperations`` -> ``project.LexEntry``). That heuristic is right for
41 of the 43 classes but invents two accessors FLExProject does not have --
``LexSense`` (real: ``Senses``) and ``PhonologicalRule`` (real: ``PhonRules``).
A phantom in the allowlist is worse than a missing one: the pre-flight gate
*approves* code that raises AttributeError at runtime, which is how the
shipped flexicon template came to teach ``project.LexSense``.

``PROJECT_ACCESSOR_ALIASES`` records the known exceptions. This script is the
drift check for that table -- run it after a flexicon upgrade.

Why the live class and not the index
------------------------------------
The flexicon index's FLExProject ``properties`` list enumerates only 58 names,
while the live class exposes considerably more (both singular and plural
aliases). 29 of the 43 shorthands are real accessors that the index does NOT
list -- ``project.Example``, ``project.WritingSystem``, ``project.Text`` and
friends. Judging phantom-ness from the index therefore flags 29 false
positives and is exactly the wrong tool for this job. ``dir(FLExProject)`` on
an installed flexicon is the authority, so this check needs a real install and
skips (exit 0) when flexicon is unavailable, e.g. headless CI.

Usage:
    python scripts/check_project_accessors.py

Exit codes:
    0 = allowlist agrees with the live class (or flexicon not installed)
    1 = drift detected -- update PROJECT_ACCESSOR_ALIASES in
        src/flextoolsmcp/server/constants.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def main():
    try:
        from flexicon import FLExProject
    except ImportError as exc:
        print(f"[SKIP] flexicon not importable ({exc}); accessor drift check needs a live install.")
        return 0

    from flextoolsmcp.server.constants import KNOWN_OPERATIONS, PROJECT_ACCESSOR_ALIASES

    live = {n for n in dir(FLExProject) if not n.startswith("_")}
    shorthands = sorted(
        op[: -len("Operations")] for op in KNOWN_OPERATIONS if op.endswith("Operations")
    )

    phantoms = {n for n in shorthands if n not in live}
    declared = set(PROJECT_ACCESSOR_ALIASES)

    failures = []

    # 1. A phantom nobody declared -- the gate is currently blessing broken code.
    for name in sorted(phantoms - declared):
        failures.append(
            f"project.{name} does not exist on FLExProject but is NOT in "
            f"PROJECT_ACCESSOR_ALIASES -- the pre-flight gate will approve code that "
            f"raises AttributeError. Add it, mapped to the real accessor."
        )

    # 2. A declared alias that flexicon has since made real -- the entry now
    #    rejects working code, so drop it.
    for name in sorted(declared - phantoms):
        failures.append(
            f"project.{name} DOES exist on FLExProject now, but is still listed in "
            f"PROJECT_ACCESSOR_ALIASES -- the gate will reject valid code. Remove it."
        )

    # 3. An alias pointing at another name that isn't real just moves the bug.
    for name, target in sorted(PROJECT_ACCESSOR_ALIASES.items()):
        if target not in live:
            failures.append(
                f"PROJECT_ACCESSOR_ALIASES maps {name} -> {target}, but "
                f"project.{target} does not exist on FLExProject either."
            )

    print(f"Checked {len(shorthands)} Operations shorthands against live FLExProject.")
    print(f"  phantom (absent from the live class): {sorted(phantoms) or 'none'}")
    print(f"  declared in PROJECT_ACCESSOR_ALIASES: {sorted(declared) or 'none'}")

    if failures:
        print("\n[FAIL] Accessor allowlist has drifted from the installed flexicon:")
        for line in failures:
            print(f"  - {line}")
        print("\nFix: update PROJECT_ACCESSOR_ALIASES in src/flextoolsmcp/server/constants.py")
        return 1

    print("\n[OK] Allowlist matches the installed flexicon.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
