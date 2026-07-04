#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared utility functions for handler modules.

Consolidates common functions to avoid duplication across handlers.
"""


def normalize_object_name(name: str) -> str:
    """Normalize object name to interface format (ILexEntry).

    Removes 'Operations' suffix if present, then ensures 'I' prefix.

    Args:
        name: Object name to normalize (e.g., 'LexEntry', 'ILexEntry', 'LexEntryOperations')

    Returns:
        Normalized interface name with 'I' prefix (e.g., 'ILexEntry')
    """
    name = name.replace("Operations", "")
    if not name.startswith("I"):
        name = f"I{name}"
    return name
