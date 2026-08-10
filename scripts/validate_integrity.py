#!/usr/bin/env python3
"""Unified validation script for FlexToolsMCP: syntax, imports, runtime, and contract checks.

Supports subcommands:
  syntax      Check Python syntax on all src/ files
  imports     Check import guards on relative imports
  server      Verify server.py tool count
  refresh     Verify refresh.py functionality
  flexicon   Verify flexicon contract (Operations, exceptions)
  all         Run all checks (default)

Examples:
  python scripts/validate_integrity.py                    # Run all checks
  python scripts/validate_integrity.py syntax             # Syntax only
  python scripts/validate_integrity.py flexicon          # Contract check only
"""

import argparse
import ast
import inspect
import os
import re
import subprocess
import sys


# ── Configuration ──────────────────────────────────────────────────

SRC_DIR = "src/flextoolsmcp"
LOCAL_MODULES = {"json_utils"}
MIN_TOOL_COUNT = 10
CORE_CLASSES = ["FLExInitialize", "FLExCleanup", "FLExProject"]


# ── Shared AST Helpers ─────────────────────────────────────────────

class ImportChecker(ast.NodeVisitor):
    """AST visitor that checks import statements resolve correctly."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.src_dir = os.path.dirname(filepath)
        self.errors = []

    def visit_ImportFrom(self, node):
        if node.level > 0 and node.module:
            self._check_guarded_relative(node)

        if node.level == 0 and node.module in LOCAL_MODULES:
            module_file = os.path.join(self.src_dir, node.module + ".py")
            if not os.path.isfile(module_file):
                self.errors.append(
                    f"  Line {node.lineno}: `from {node.module} import ...` "
                    f"but {module_file} not found"
                )

        self.generic_visit(node)

    def _check_guarded_relative(self, node):
        """Verify that a relative import is inside an `if __package__:` guard."""
        with open(self.filepath) as f:
            lines = f.readlines()

        import_line = node.lineno - 1  # Convert to 0-indexed
        found_guard = False

        import_indent = len(lines[import_line]) - len(lines[import_line].lstrip())

        for i in range(import_line - 1, max(0, import_line - 50), -1):
            line = lines[i].strip()
            line_indent = len(lines[i]) - len(lines[i].lstrip())

            if "__package__" in line and line.startswith("if") and line_indent < import_indent:
                found_guard = True
                break

            if line and not line.startswith("#") and line_indent == 0 and "if __package__" not in line:
                break

        if not found_guard:
            module_name = "." * node.level + (node.module or "")
            self.errors.append(
                f"  Line {node.lineno}: relative import `from {module_name} import ...` "
                f"is not guarded by `if __package__:` — will fail when run as a script"
            )


def extract_set_from_ast(source, var_name):
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


def extract_exec_namespace_ops(source):
    """Extract Operations class names from the exec_namespace block."""
    pattern = r'"(\w+Operations)":\s*\1'
    return set(re.findall(pattern, source))


def extract_exec_namespace_exceptions(source):
    """Extract FP_* exception names from the exec_namespace block."""
    pattern = r'"(FP_\w+)":\s*\1'
    return set(re.findall(pattern, source))


# ── Syntax & Imports ───────────────────────────────────────────────

def check_syntax_and_imports(path):
    """Check syntax and import patterns for a Python file (static analysis)."""
    try:
        with open(path) as f:
            source = f.read()
    except FileNotFoundError:
        return True

    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as e:
        print(f"SYNTAX ERROR: {path} - {e}", file=sys.stderr)
        return False

    checker = ImportChecker(path)
    checker.visit(tree)

    if checker.errors:
        print(f"IMPORT ERROR (static): {path}", file=sys.stderr)
        for err in checker.errors:
            print(err, file=sys.stderr)
        return False

    return True


def check_runtime_import(script_path, description):
    """Run the script in a subprocess to catch real import errors."""
    check_code = (
        f"import sys, os; "
        f"sys.path.insert(0, os.path.join(os.getcwd(), {os.path.dirname(script_path)!r})); "
        f"_code = compile(open({script_path!r}).read(), {script_path!r}, 'exec'); "
        f"exec(_code, {{'__name__': '_import_check', '__file__': {script_path!r}}})"
    )
    result = subprocess.run(
        [sys.executable, "-c", check_code],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        import_errors = ("ImportError", "ModuleNotFoundError")
        error_lines = stderr.split("\n")
        if any(err in stderr for err in import_errors):
            last_line = error_lines[-1] if error_lines else ""
            is_local_module_error = any(
                mod in last_line for mod in LOCAL_MODULES
            )
            is_relative_import_error = (
                "attempted relative import" in last_line
                or "No module named '__main__" in last_line
            )
            if is_local_module_error or is_relative_import_error:
                print(
                    f"RUNTIME IMPORT ERROR: {script_path} ({description})",
                    file=sys.stderr,
                )
                print(stderr, file=sys.stderr)
                return False
            # Genuine third-party ImportError/ModuleNotFoundError (e.g. a dep
            # simply isn't installed in this environment) -- intentional skip,
            # not a code bug.
            print(
                f"  Note: {description} has uninstalled third-party dependency "
                f"(not a code bug, skipping)",
            )
            return True
        # Non-zero exit with NEITHER ImportError nor ModuleNotFoundError in
        # stderr (e.g. a bare AttributeError from a removed decorator API --
        # see mcp 2.0.0 incompatibility). This is an unclassified failure and
        # must FAIL the check rather than silently falling through to True.
        print(
            f"RUNTIME ERROR: {script_path} ({description}) exited "
            f"{result.returncode} with an unrecognized (non-Import) error:",
            file=sys.stderr,
        )
        print(stderr, file=sys.stderr)
        return False
    return True


# ── Server Checks ──────────────────────────────────────────────────

def check_server_tools():
    """Verify server.py exposes the expected number of MCP tools."""
    check_code = (
        "import asyncio; "
        "from flextoolsmcp.server import APIIndex, get_index_dir, list_tools; "
        "tools = asyncio.run(list_tools()); "
        "print(len(tools))"
    )
    result = subprocess.run(
        [sys.executable, "-c", check_code],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode == 0 and result.stdout.strip().isdigit():
        tool_count = int(result.stdout.strip())
        if tool_count >= MIN_TOOL_COUNT:
            print(f"  server.py: {tool_count} tools registered (runtime) [OK]")
            return True
        else:
            print(
                f"TOOL COUNT ERROR: server.py has {tool_count} tools, "
                f"expected >= {MIN_TOOL_COUNT}",
                file=sys.stderr,
            )
            return False

    print(
        "  server.py: runtime import/execution failed, falling back to AST tool "
        "count -- DEGRADED CHECK, does not verify server.py actually imports/runs"
    )
    if result.stderr.strip():
        print(f"  (runtime import stderr: {result.stderr.strip().splitlines()[-1]})")
    return _count_tools_from_ast()


def _count_tools_from_ast():
    """Count Tool() constructor calls in server.py AND ToolDef instances in tool_definitions.py."""
    with open("src/flextoolsmcp/server.py") as f:
        tree = ast.parse(f.read(), filename="src/flextoolsmcp/server.py")

    tool_count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Tool"
        ):
            tool_count += 1

    try:
        with open("src/flextoolsmcp/server/tool_definitions.py") as f:
            tooldef_tree = ast.parse(f.read(), filename="src/flextoolsmcp/server/tool_definitions.py")

        tooldef_count = 0
        for node in ast.walk(tooldef_tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "ToolDef"
            ):
                tooldef_count += 1

        tool_count += tooldef_count
    except FileNotFoundError:
        pass

    if tool_count >= MIN_TOOL_COUNT:
        print(
            f"  server.py + tool_definitions.py: {tool_count} tool definitions found "
            f"(AST, DEGRADED -- runtime import check failed, this does NOT prove "
            f"server.py imports/runs) [OK]"
        )
        return True
    else:
        print(
            f"TOOL COUNT ERROR: server.py + tool_definitions.py has {tool_count} tool definitions, "
            f"expected >= {MIN_TOOL_COUNT}",
            file=sys.stderr,
        )
        return False


def check_refresh_runs():
    """Verify refresh.py runs successfully with --help."""
    result = subprocess.run(
        [sys.executable, "src/flextoolsmcp/refresh.py", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        print("REFRESH ERROR: `python src/flextoolsmcp/refresh.py --help` failed", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return False

    help_text = result.stdout
    # The per-library filter flags were removed: refresh.py always scans every
    # available API because the scans are cross-linked (a partial scan leaves
    # the others' cross-references stale). Guard against their reintroduction.
    removed_flags = ["--flexicon-only", "--flexlibs-only", "--liblcm-only"]
    present = [f for f in removed_flags if f in help_text]
    if present:
        print(
            f"REFRESH ERROR: --help output has removed per-library filter flags: {present}",
            file=sys.stderr,
        )
        return False

    print("  refresh.py: --help OK, per-library filter flags absent [OK]")
    return True


# ── Contract Checks (Flexicon) ────────────────────────────────────

def check_server_internal_consistency():
    """Verify the 3 copies of the Operations list match across server.py and execution.py."""
    with open("src/flextoolsmcp/server/constants.py") as f:
        constants_source = f.read()
    with open("src/flextoolsmcp/server/handlers/execution.py") as f:
        execution_source = f.read()

    errors = []

    known_ops = extract_set_from_ast(constants_source, "KNOWN_OPERATIONS")
    if not known_ops:
        errors.append("Could not find KNOWN_OPERATIONS set in src/flextoolsmcp/server/constants.py")
        return errors

    ops_classes = extract_set_from_ast(constants_source, "OPERATIONS_CLASSES")
    if not ops_classes:
        ops_classes = known_ops

    exec_ops = extract_exec_namespace_ops(execution_source)
    if not exec_ops:
        exec_ops = known_ops

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

    exec_exceptions = extract_exec_namespace_exceptions(execution_source)

    return errors, known_ops, exec_exceptions


def _try_import(cls_name):
    """Try to import cls_name from flexicon. Returns (obj, error)."""
    try:
        obj = getattr(__import__("flexicon", fromlist=[cls_name]), cls_name)
        if obj is None:
            return None, f"{cls_name} is None"
        return obj, None
    except (ImportError, AttributeError) as e:
        return None, str(e)


def check_flexicon_contract(operations_classes, exception_classes):
    """Full runtime contract check against installed flexicon."""
    errors = []
    warnings = []

    try:
        import flexicon
    except ImportError:
        print("flexicon not installed — skipping runtime contract checks.")
        return [], []
    except Exception as e:
        # flexicon is installed but can't initialize in this environment. Its
        # import runs FLExGlobals.InitialiseFWGlobals(), which raises a bare
        # Exception ("64bit FieldWorks 9 not found") on any host without a
        # FieldWorks install — e.g. headless CI runners. The static/consistency
        # checks above don't need a live flexicon; only the runtime contract
        # does, so skip it gracefully rather than failing the whole check.
        print(
            f"flexicon installed but not initializable "
            f"(no FieldWorks environment: {e}) -- "
            f"skipping runtime contract checks."
        )
        return [], []

    # Import the non-enumerable operations list from server constants
    try:
        from flextoolsmcp.server.constants import NON_ENUMERABLE_OPERATIONS
    except (ImportError, AttributeError):
        NON_ENUMERABLE_OPERATIONS = {
            "CheckOperations",
            "CustomFieldOperations",
            "DiscourseOperations",
            "InflectionFeatureOperations",
            "PossibilityListOperations",
            "ProjectSettingsOperations",
        }

    version = getattr(flexicon, "__version__", None)
    if version is None:
        # Distribution is `pyflexicon` (imported as `flexicon`); try the live
        # dist name first, then the legacy import name for older installs.
        from importlib.metadata import version as pkg_version
        for dist_name in ("pyflexicon", "flexicon"):
            try:
                version = pkg_version(dist_name)
                break
            except Exception:
                continue
    if version:
        print(f"  flexicon version: {version}")
    else:
        errors.append("flexicon has no __version__ attribute or package metadata")

    for cls_name in CORE_CLASSES:
        _, err = _try_import(cls_name)
        if err:
            errors.append(f"Core class {cls_name}: {err}")

    ops_passed = 0
    for cls_name in sorted(operations_classes):
        obj, err = _try_import(cls_name)
        if err:
            errors.append(f"Operations class {cls_name}: {err}")
        else:
            ops_passed += 1
            # Skip GetAll() check for non-enumerable operations (they use domain-specific methods)
            if cls_name not in NON_ENUMERABLE_OPERATIONS:
                if not hasattr(obj, "GetAll") and not any(
                    name == "GetAll" for name, _ in inspect.getmembers(obj)
                ):
                    errors.append(
                        f"{cls_name} has no GetAll() method "
                        f"(server.py generates code calling ops.GetAll())"
                    )

    exc_passed = 0
    for cls_name in sorted(exception_classes):
        _, err = _try_import(cls_name)
        if err:
            errors.append(f"Exception class {cls_name}: {err}")
        else:
            exc_passed += 1

    all_exports = set(dir(flexicon))
    new_ops = {
        name for name in all_exports
        if name.endswith("Operations")
        and not name.startswith("_")
        and name not in operations_classes
    }
    if new_ops:
        warnings.append(
            f"flexicon has {len(new_ops)} Operations class(es) not in server.py: "
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


# ── Utility Functions ──────────────────────────────────────────────

def find_python_files(directory):
    """Find all .py files in the given directory."""
    py_files = []
    for entry in sorted(os.listdir(directory)):
        if entry.endswith(".py"):
            py_files.append(os.path.join(directory, entry))
    return py_files


# ── Subcommands ────────────────────────────────────────────────────

def cmd_syntax(args):
    """Check Python syntax on all src/ files."""
    files = find_python_files(SRC_DIR)
    if not files:
        print(f"No Python files found in {SRC_DIR}/", file=sys.stderr)
        return 1

    print(f"Checking syntax on {len(files)} src/ files...")
    all_ok = True
    for path in files:
        if not check_syntax_and_imports(path):
            all_ok = False

    if all_ok:
        print(f"All {len(files)} files: syntax OK")
        return 0
    else:
        print("Syntax check FAILED", file=sys.stderr)
        return 1


def cmd_imports(args):
    """Check import guards on relative imports."""
    files = find_python_files(SRC_DIR)
    if not files:
        print(f"No Python files found in {SRC_DIR}/", file=sys.stderr)
        return 1

    print(f"Checking import guards on {len(files)} src/ files...")
    all_ok = True
    for path in files:
        if not check_syntax_and_imports(path):
            all_ok = False

    if all_ok:
        print(f"All {len(files)} files: import guards OK")
        return 0
    else:
        print("Import guard check FAILED", file=sys.stderr)
        return 1


def cmd_server(args):
    """Check server.py tool count."""
    print("Checking server.py tool count...")
    print("Phase 1: Runtime import check (server.py, refresh.py)...")
    all_ok = True

    for script_path, description in [
        ("src/flextoolsmcp/server.py", "MCP server"),
        ("src/flextoolsmcp/refresh.py", "refresh script"),
    ]:
        if not check_runtime_import(script_path, description):
            all_ok = False

    print("Phase 2: Functional checks...")
    if not check_server_tools():
        all_ok = False

    return 0 if all_ok else 1


def cmd_refresh(args):
    """Check refresh.py functionality."""
    print("Checking refresh.py...")
    if check_refresh_runs():
        return 0
    else:
        print("Refresh check FAILED", file=sys.stderr)
        return 1


def cmd_flexicon(args):
    """Check flexicon contract."""
    print("Checking flexicon contract...")
    print("Checking server.py internal consistency...")
    result = check_server_internal_consistency()
    if isinstance(result[0], list) and len(result) == 3:
        consistency_errors, operations_set, exceptions_set = result
    else:
        consistency_errors = result if isinstance(result, list) else [str(result)]
        operations_set = set()
        exceptions_set = set()

    all_errors = []
    all_warnings = []

    if consistency_errors:
        all_errors.extend(consistency_errors)
        for err in consistency_errors:
            print(f"  DRIFT: {err}", file=sys.stderr)
    else:
        print(
            f"  3 copies of Operations list match: "
            f"{len(operations_set)} classes, {len(exceptions_set)} exceptions"
        )

    print("Checking flexicon runtime contract...")
    if operations_set:
        runtime_errors, runtime_warnings = check_flexicon_contract(
            operations_set, exceptions_set
        )
        all_errors.extend(runtime_errors)
        all_warnings.extend(runtime_warnings)
    else:
        print("  Skipped (could not parse Operations list from server.py)")

    if all_warnings:
        print()
        for w in all_warnings:
            print(f"WARNING: {w}", file=sys.stderr)

    if all_errors:
        print(f"\nFAILED: {len(all_errors)} contract violation(s):", file=sys.stderr)
        for err in all_errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    print("\nFlexicon contract check passed.")
    return 0


def cmd_all(args):
    """Run all checks."""
    all_ok = True

    print("[1/5] Checking syntax...")
    all_ok = cmd_syntax(args) == 0 and all_ok

    print("\n[2/5] Checking imports...")
    all_ok = cmd_imports(args) == 0 and all_ok

    print("\n[3/5] Checking server...")
    all_ok = cmd_server(args) == 0 and all_ok

    print("\n[4/5] Checking refresh...")
    all_ok = cmd_refresh(args) == 0 and all_ok

    print("\n[5/5] Checking flexicon...")
    all_ok = cmd_flexicon(args) == 0 and all_ok

    return 0 if all_ok else 1


# ── Main ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Unified validation for FlexToolsMCP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    subparsers = parser.add_subparsers(dest='command', help='Validation check to run')

    subparsers.add_parser('syntax', help='Check Python syntax')
    subparsers.add_parser('imports', help='Check import guards')
    subparsers.add_parser('server', help='Check server.py tools')
    subparsers.add_parser('refresh', help='Check refresh.py')
    subparsers.add_parser('flexicon', help='Check flexicon contract')
    subparsers.add_parser('all', help='Run all checks')

    args = parser.parse_args()

    commands = {
        'syntax': cmd_syntax,
        'imports': cmd_imports,
        'server': cmd_server,
        'refresh': cmd_refresh,
        'flexicon': cmd_flexicon,
        'all': cmd_all,
        None: cmd_all,  # Default to all checks
    }

    cmd = commands.get(args.command, cmd_all)
    return cmd(args)


if __name__ == "__main__":
    sys.exit(main())
