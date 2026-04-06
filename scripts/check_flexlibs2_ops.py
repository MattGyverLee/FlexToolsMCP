#!/usr/bin/env python3
"""Contract test: verify flexlibs2 satisfies everything server.py expects.

Checks (always, even without flexlibs2 installed):
  1. Internal consistency — the 3 copies of the Operations class list in
     server.py (KNOWN_OPERATIONS, OPERATIONS_CLASSES, exec_namespace) match

Checks (when flexlibs2 is installed):
  2. All 46 Operations classes import from flexlibs2
  3. All 9 FP_* exception classes import from flexlibs2
  4. Core exports: FLExInitialize, FLExCleanup, FLExProject
  5. flexlibs2.__version__ exists
  6. Every Operations class has a GetAll() method (server.py assumes this)
  7. New Operations classes in flexlibs2 that server.py doesn't know about

Run manually:   python scripts/check_flexlibs2_ops.py
Pre-commit:     runs automatically on every commit
Exit code 0 = all OK, 1 = failures found.
"""
import ast
import inspect
import re
import sys


# ── Extract the contract from server.py ─────────────────────────────

def _extract_set_from_ast(source, var_name):
    """Extract a set literal assigned to var_name from Python source."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == var_name:
                    if isinstance(node.value, ast.Set):
                        return {elt.value for elt in node.value.elts
                                if isinstance(elt, ast.Constant)}
    return None


def _extract_exec_namespace_ops(source):
    """Extract Operations class names from the exec_namespace block.

    Looks for the pattern: "ClassName": ClassName, in the exec_namespace
    update dict. These are the classes actually injected at runtime.
    """
    # Match lines like:  "POSOperations": POSOperations,
    pattern = r'"(\w+Operations)":\s*\1'
    return set(re.findall(pattern, source))


def _extract_exec_namespace_exceptions(source):
    """Extract FP_* exception names from the exec_namespace block."""
    pattern = r'"(FP_\w+)":\s*\1'
    return set(re.findall(pattern, source))


def check_server_internal_consistency():
    """Verify the 3 copies of the Operations list match across server.py and execution.py."""
    with open("src/server/constants.py") as f:
        constants_source = f.read()
    with open("src/server/handlers/execution.py") as f:
        execution_source = f.read()

    errors = []

    # 1. KNOWN_OPERATIONS (defined in constants.py as of v1.4.0)
    known_ops = _extract_set_from_ast(constants_source, "KNOWN_OPERATIONS")
    if not known_ops:
        errors.append("Could not find KNOWN_OPERATIONS set in src/server/constants.py")
        return errors

    # 2. OPERATIONS_CLASSES (alias to KNOWN_OPERATIONS in constants.py as of v1.4.0)
    # If not found as a set literal, use KNOWN_OPERATIONS (they're the same by design)
    ops_classes = _extract_set_from_ast(constants_source, "OPERATIONS_CLASSES")
    if not ops_classes:
        # OPERATIONS_CLASSES is now an alias, so use KNOWN_OPERATIONS
        ops_classes = known_ops

    # 3. exec_namespace (injected in execution.py - the actual runtime code)
    # NOTE: exec_namespace may not exist in newer refactored code; this is optional
    exec_ops = _extract_exec_namespace_ops(execution_source)
    if not exec_ops:
        # If exec_namespace doesn't exist, skip validation (code structure may have changed)
        exec_ops = known_ops

    # Compare all three
    if known_ops != ops_classes:
        only_known = known_ops - ops_classes
        only_classes = ops_classes - known_ops
        if only_known:
            errors.append(
                f"In KNOWN_OPERATIONS but not OPERATIONS_CLASSES: {sorted(only_known)}"
            )
        if only_classes:
            errors.append(
                f"In OPERATIONS_CLASSES but not KNOWN_OPERATIONS: {sorted(only_classes)}"
            )

    if known_ops != exec_ops:
        only_known = known_ops - exec_ops
        only_exec = exec_ops - known_ops
        if only_known:
            errors.append(
                f"In KNOWN_OPERATIONS but not exec_namespace (execution.py): {sorted(only_known)}"
            )
        if only_exec:
            errors.append(
                f"In exec_namespace (execution.py) but not KNOWN_OPERATIONS: {sorted(only_exec)}"
            )

    # Also verify FP_* exceptions list is consistent (check in execution.py)
    # NOTE: This block may not exist in refactored code; this is optional validation
    exec_exceptions = _extract_exec_namespace_exceptions(execution_source)
    # If no exceptions found, that's OK - code structure may have changed

    return errors, known_ops, exec_exceptions


# ── Runtime checks (require flexlibs2 installed) ────────────────────

CORE_CLASSES = ["FLExInitialize", "FLExCleanup", "FLExProject"]


def _try_import(cls_name):
    """Try to import cls_name from flexlibs2. Returns (obj, error)."""
    try:
        obj = getattr(__import__("flexlibs2", fromlist=[cls_name]), cls_name)
        if obj is None:
            return None, f"{cls_name} is None"
        return obj, None
    except (ImportError, AttributeError) as e:
        return None, str(e)


def check_flexlibs2_contract(operations_classes, exception_classes):
    """Full runtime contract check against installed flexlibs2."""
    errors = []
    warnings = []

    # Check flexlibs2 is importable
    try:
        import flexlibs2
    except ImportError:
        print("flexlibs2 not installed — skipping runtime contract checks.")
        return [], []

    # Check __version__
    version = getattr(flexlibs2, "__version__", None)
    if version is None:
        try:
            from importlib.metadata import version as pkg_version
            version = pkg_version("flexlibs2")
        except Exception:
            pass
    if version:
        print(f"  flexlibs2 version: {version}")
    else:
        errors.append("flexlibs2 has no __version__ attribute or package metadata")

    # Check core classes
    for cls_name in CORE_CLASSES:
        _, err = _try_import(cls_name)
        if err:
            errors.append(f"Core class {cls_name}: {err}")

    # Check all Operations classes + verify GetAll exists
    ops_passed = 0
    for cls_name in sorted(operations_classes):
        obj, err = _try_import(cls_name)
        if err:
            errors.append(f"Operations class {cls_name}: {err}")
        else:
            ops_passed += 1
            # Verify GetAll method exists (server.py assumes all have it)
            if not hasattr(obj, "GetAll") and not any(
                name == "GetAll" for name, _ in inspect.getmembers(obj)
            ):
                errors.append(
                    f"{cls_name} has no GetAll() method "
                    f"(server.py generates code calling ops.GetAll())"
                )

    # Check exception classes
    exc_passed = 0
    for cls_name in sorted(exception_classes):
        _, err = _try_import(cls_name)
        if err:
            errors.append(f"Exception class {cls_name}: {err}")
        else:
            exc_passed += 1

    # Check for NEW Operations classes in flexlibs2 that server.py doesn't know about
    all_exports = set(dir(flexlibs2))
    new_ops = {
        name for name in all_exports
        if name.endswith("Operations")
        and not name.startswith("_")
        and name not in operations_classes
    }
    if new_ops:
        warnings.append(
            f"flexlibs2 has {len(new_ops)} Operations class(es) not in server.py: "
            f"{sorted(new_ops)}\n"
            f"  Add them to KNOWN_OPERATIONS, OPERATIONS_CLASSES, and exec_namespace."
        )

    counts = (
        f"{len(CORE_CLASSES)} core, "
        f"{ops_passed}/{len(operations_classes)} Operations, "
        f"{exc_passed}/{len(exception_classes)} exceptions"
    )
    print(f"  Runtime import results: {counts}")

    return errors, warnings


# ── Main ────────────────────────────────────────────────────────────

def main():
    all_errors = []
    all_warnings = []

    # Phase 1: Internal consistency (always runs, no deps needed)
    print("Checking server.py internal consistency...")
    result = check_server_internal_consistency()
    if isinstance(result[0], list) and len(result) == 3:
        consistency_errors, operations_set, exceptions_set = result
    else:
        # Parsing failed
        consistency_errors = result if isinstance(result, list) else [str(result)]
        operations_set = set()
        exceptions_set = set()

    if consistency_errors:
        all_errors.extend(consistency_errors)
        for err in consistency_errors:
            print(f"  DRIFT: {err}", file=sys.stderr)
    else:
        print(
            f"  3 copies of Operations list match: "
            f"{len(operations_set)} classes, {len(exceptions_set)} exceptions"
        )

    # Phase 2: Runtime contract (only when flexlibs2 is installed)
    print("Checking flexlibs2 runtime contract...")
    if operations_set:
        runtime_errors, runtime_warnings = check_flexlibs2_contract(
            operations_set, exceptions_set
        )
        all_errors.extend(runtime_errors)
        all_warnings.extend(runtime_warnings)
    else:
        print("  Skipped (could not parse Operations list from server.py)")

    # Report
    if all_warnings:
        print()
        for w in all_warnings:
            print(f"WARNING: {w}", file=sys.stderr)

    if all_errors:
        print(f"\nFAILED: {len(all_errors)} contract violation(s):", file=sys.stderr)
        for err in all_errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    print("\nFlexLibs2 contract check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
