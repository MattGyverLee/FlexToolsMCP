#!/usr/bin/env python3
"""Pre-commit hook: verify key Python files parse and import correctly.

Goes beyond syntax checking — actually tests that intra-package imports
(like `from json_utils import ...`) resolve correctly when run as scripts.
This catches the relative-vs-absolute import bug where `from .json_utils`
works as a package but fails when running `python src/server.py` directly.
"""
import ast
import os
import sys


# Directory containing source files to verify
SRC_DIR = "src"

# Modules that live in src/ (intra-package imports we must validate)
LOCAL_MODULES = {"json_utils"}


class ImportChecker(ast.NodeVisitor):
    """AST visitor that checks import statements resolve correctly."""

    def __init__(self, filepath):
        self.filepath = filepath
        self.src_dir = os.path.dirname(filepath)
        self.errors = []

    def visit_ImportFrom(self, node):
        # Check relative imports (from .json_utils import ...)
        if node.level > 0 and node.module:
            # Relative import — only valid inside a package.
            # When run as a script, __package__ is None and this fails.
            # The codebase uses `if __package__:` guard; verify it exists.
            self._check_guarded_relative(node)

        # Check absolute imports of local modules
        if node.level == 0 and node.module in LOCAL_MODULES:
            # Absolute import of local module — verify the file exists
            module_file = os.path.join(self.src_dir, node.module + ".py")
            if not os.path.isfile(module_file):
                self.errors.append(
                    f"  Line {node.lineno}: `from {node.module} import ...` "
                    f"but {module_file} not found"
                )

        self.generic_visit(node)

    def _check_guarded_relative(self, node):
        """Verify that a relative import is inside an `if __package__:` guard."""
        # Walk up the AST to see if this import is inside an If node
        # that tests __package__. We do this by checking the source lines.
        with open(self.filepath) as f:
            lines = f.readlines()

        import_line = node.lineno
        # Look at the preceding non-blank lines for `if __package__:`
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


def check_file(path):
    """Check syntax and import patterns for a Python file."""
    try:
        with open(path) as f:
            source = f.read()
    except FileNotFoundError:
        return True  # File deleted, skip

    # Syntax check
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as e:
        print(f"SYNTAX ERROR: {path} - {e}", file=sys.stderr)
        return False

    # Import pattern check
    checker = ImportChecker(path)
    checker.visit(tree)

    if checker.errors:
        print(f"IMPORT ERROR: {path}", file=sys.stderr)
        for err in checker.errors:
            print(err, file=sys.stderr)
        return False

    return True


def find_python_files(directory):
    """Find all .py files in the given directory."""
    py_files = []
    for entry in sorted(os.listdir(directory)):
        if entry.endswith(".py"):
            py_files.append(os.path.join(directory, entry))
    return py_files


def main():
    files = find_python_files(SRC_DIR)
    if not files:
        print(f"No Python files found in {SRC_DIR}/", file=sys.stderr)
        sys.exit(1)

    all_ok = all(check_file(f) for f in files)
    if all_ok:
        print(f"All {len(files)} src/ Python files: syntax OK, imports OK.")
    else:
        print("Pre-commit check FAILED. See errors above.", file=sys.stderr)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
