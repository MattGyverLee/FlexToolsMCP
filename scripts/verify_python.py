#!/usr/bin/env python3
"""Pre-commit hook: verify key Python files parse correctly."""
import ast
import sys

CRITICAL_FILES = [
    "src/server.py",
    "src/refresh.py",
]


def check_file(path):
    try:
        with open(path) as f:
            ast.parse(f.read(), filename=path)
        return True
    except SyntaxError as e:
        print(f"FAIL: {path} - {e}", file=sys.stderr)
        return False
    except FileNotFoundError:
        # File not in repo (e.g., deleted), skip
        return True


def main():
    ok = all(check_file(f) for f in CRITICAL_FILES)
    if ok:
        print("All critical Python files parse OK.")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
