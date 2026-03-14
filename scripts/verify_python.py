#!/usr/bin/env python3
"""Pre-commit hook: verify key Python files parse, import, and run correctly.

Four levels of checking:
1. AST syntax check — all src/*.py files
2. Import guard check — ensures relative imports have `if __package__:` guards
3. Runtime import check — runs scripts in subprocess to catch real import errors
4. Functional check — server.py reports tool count, refresh.py runs --help

When full dependencies are installed (desktop), level 4 actually loads the
API index and counts registered tools. When deps are missing (CI), it falls
back to counting Tool() instances in the AST.
"""
import ast
import os
import subprocess
import sys


# Directory containing source files to verify
SRC_DIR = "src"

# Modules that live in src/ (intra-package imports we must validate)
LOCAL_MODULES = {"json_utils"}

# Expected minimum tool count for server.py (update if tools are added/removed)
MIN_TOOL_COUNT = 10


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

        import_line = node.lineno
        found_guard = False
        for i in range(import_line - 2, max(import_line - 5, -1), -1):
            if i < 0:
                break
            line = lines[i].strip()
            if "__package__" in line and line.startswith("if"):
                found_guard = True
                break

        if not found_guard:
            module_name = "." * node.level + (node.module or "")
            self.errors.append(
                f"  Line {node.lineno}: relative import `from {module_name} import ...` "
                f"is not guarded by `if __package__:` — will fail when run as a script"
            )


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
            print(
                f"  Note: {description} has uninstalled third-party dependency "
                f"(not a code bug, skipping)",
            )
    return True


# ── Functional checks ──────────────────────────────────────────────


def check_server_tools():
    """Verify server.py exposes the expected number of MCP tools.

    With full deps: imports server module and counts tools from list_tools().
    Without deps: counts Tool() constructor calls in the AST.
    """
    # Try the real thing first — actually load the server and count tools
    check_code = (
        "import asyncio; "
        "from src.server import APIIndex, get_index_dir, list_tools; "
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
            print(f"  server.py: {tool_count} tools registered (runtime) ✓")
            return True
        else:
            print(
                f"TOOL COUNT ERROR: server.py has {tool_count} tools, "
                f"expected >= {MIN_TOOL_COUNT}",
                file=sys.stderr,
            )
            return False

    # Fallback: count Tool() instances in the AST
    print("  server.py: deps not installed, falling back to AST tool count")
    return _count_tools_from_ast()


def _count_tools_from_ast():
    """Count Tool() constructor calls in server.py via AST."""
    with open("src/server.py") as f:
        tree = ast.parse(f.read(), filename="src/server.py")

    tool_count = 0
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Tool"
        ):
            tool_count += 1

    if tool_count >= MIN_TOOL_COUNT:
        print(f"  server.py: {tool_count} Tool() definitions found (AST) ✓")
        return True
    else:
        print(
            f"TOOL COUNT ERROR: server.py has {tool_count} Tool() calls, "
            f"expected >= {MIN_TOOL_COUNT}",
            file=sys.stderr,
        )
        return False


def check_refresh_runs():
    """Verify refresh.py runs successfully with --help.

    This exercises the full import chain and argparse setup without
    actually refreshing any indexes.
    """
    result = subprocess.run(
        [sys.executable, "src/refresh.py", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        print("REFRESH ERROR: `python src/refresh.py --help` failed", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return False

    # Verify key options are present in help output
    help_text = result.stdout
    expected_flags = ["--flexlibs2-only", "--flexlibs-only", "--liblcm-only"]
    missing = [f for f in expected_flags if f not in help_text]
    if missing:
        print(
            f"REFRESH ERROR: --help output missing expected flags: {missing}",
            file=sys.stderr,
        )
        return False

    print(f"  refresh.py: --help OK, all {len(expected_flags)} flags present ✓")
    return True


# ── Main ────────────────────────────────────────────────────────────


def find_python_files(directory):
    """Find all .py files in the given directory."""
    py_files = []
    for entry in sorted(os.listdir(directory)):
        if entry.endswith(".py"):
            py_files.append(os.path.join(directory, entry))
    return py_files


def main():
    all_ok = True

    # Phase 1: Static analysis on all src/ files
    files = find_python_files(SRC_DIR)
    if not files:
        print(f"No Python files found in {SRC_DIR}/", file=sys.stderr)
        sys.exit(1)

    print(f"Phase 1: Checking {len(files)} src/ files (syntax + import guards)...")
    for path in files:
        if not check_syntax_and_imports(path):
            all_ok = False

    # Phase 2: Runtime import check on critical scripts
    print("Phase 2: Runtime import check (server.py, refresh.py)...")
    for script_path, description in [
        ("src/server.py", "MCP server"),
        ("src/refresh.py", "refresh script"),
    ]:
        if not check_runtime_import(script_path, description):
            all_ok = False

    # Phase 3: Functional checks
    print("Phase 3: Functional checks...")
    if not check_server_tools():
        all_ok = False
    if not check_refresh_runs():
        all_ok = False

    if all_ok:
        print(f"\nAll {len(files)} src/ files: syntax OK, imports OK, runtime OK.")
    else:
        print("\nPre-commit check FAILED. See errors above.", file=sys.stderr)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
