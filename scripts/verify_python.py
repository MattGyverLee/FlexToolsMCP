#!/usr/bin/env python3
"""Delegate to validate_integrity.py for backwards compatibility.

This script is kept for pre-commit hooks that reference it directly.
All validation logic has been consolidated into validate_integrity.py.
"""
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(__file__))

from validate_integrity import cmd_all

if __name__ == "__main__":
    class Args:
        command = None
    sys.exit(cmd_all(Args()))
