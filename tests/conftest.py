#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pytest configuration and shared fixtures."""

import sys
from pathlib import Path

# Add src to path (shared across all tests)
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)
