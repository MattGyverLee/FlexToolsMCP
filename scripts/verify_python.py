#!/usr/bin/env python3
"""Pre-commit hook: verify key Python files parse and import correctly.

Three levels of checking:
1. AST syntax check — all src/*.py files
2. Import guard check — ensures relative imports have `if __package__:` guards
3. Runtime import check — actually runs `python src/server.py` and
   `python src/refresh.py` in a subprocess to catch real import errors
   (e.g., broken relative imports, missing local modules)

Level 3 is what catches bugs like the .json_utils import that worked
as a package but failed when run as `python src/server.py`.
"""
import ast
import os
import subprocess
import sys


# Directory containing source files to verify
SRC_DIR = "src"

# Modules that live in src/ (intra-package imports we must validate)
LOCAL_MODULES = {"json_utils"}

# Scripts to actually run and verify no import errors
# Each tuple: (script_path, description)
RUNTIME_CHECK_SCRIPTS = [
    ("src/server.py", "MCP server"),
    ("src/refresh.py", "refresh script"),
]


class ImportChecker(ast.NodeVisitor):
    """AST visitor that checks import statements resolve correctly."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.src_dir = os.path.dirname(filepath)
        self.errors = []

    def visit_ImportFrom(self, node):
        # Check relative imports (from .json_utils import ...)
        if node.level > 0 and node.module:
            self._check_guarded_relative(node)

        # Check absolute imports of local modules
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
    """Actually run the script in a subprocess and check for import errors.

    Executes the script but intercepts __name__ == '__main__' so we only
    run the top-level imports and definitions, not the actual main() logic.
    This catches real runtime import failures without starting the server
    or triggering index refreshes.
    """
    # We compile and exec the file with __name__ set to something other than
    # '__main__', so the `if __name__ == "__main__":` block is skipped.
    # This runs all top-level code (imports, class/function defs, constants).
    check_code = f"""\
import sys, os
# Add src/ to path so absolute imports of local modules work
sys.path.insert(0, os.path.join(os.getcwd(), {os.path.dirname(script_path)!r}))
# Compile and exec with __name__ != '__main__' to skip entry point
with open({script_path!r}) as _f:
    _code = compile(_f.read(), {script_path!r}, 'exec')
exec(_code, {{'__name__': '_import_check', '__file__': {script_path!r}}})
"""
    result = subprocess.run(
        [sys.executable, "-c", check_code],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        # Only fail on import-related errors — other runtime errors
        # (missing .env, missing index files, missing third-party packages
        # not installed in this env) are not import bugs we can catch here.
        import_errors = ("ImportError", "ModuleNotFoundError")
        error_lines = stderr.split("\n")
        if any(err in stderr for err in import_errors):
            # Extract the module name from the last error line
            # e.g., "ModuleNotFoundError: No module named 'mcp'"
            last_line = error_lines[-1] if error_lines else ""
            # Check if the missing module is one of our local modules
            # (not a third-party package). Local modules live in src/.
            is_local_module_error = any(
                mod in last_line for mod in LOCAL_MODULES
            )
            # Also catch relative import errors (from . import ...)
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
            # Third-party missing package — not our bug, skip
            print(
                f"  Note: {description} has uninstalled third-party dependency "
                f"(not a code bug, skipping)",
            )
    return True


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

    print(f"Checking {len(files)} src/ files...")
    for path in files:
        if not check_syntax_and_imports(path):
            all_ok = False

    # Phase 2: Runtime import check on critical scripts
    print("Running server.py and refresh.py to verify imports...")
    for script_path, description in RUNTIME_CHECK_SCRIPTS:
        if not check_runtime_import(script_path, description):
            all_ok = False

    if all_ok:
        print(f"All {len(files)} src/ files: syntax OK, imports OK, runtime OK.")
    else:
        print("Pre-commit check FAILED. See errors above.", file=sys.stderr)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
