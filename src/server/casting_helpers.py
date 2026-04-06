#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Casting helpers for polymorphic type handling in FlexTools module execution.

These helpers provide three-tier injection strategy:
- Tier 0 (none): No helpers injected
- Tier 1 (minimal): Only needed helpers injected
- Tier 2 (full): Full suite of helpers injected

The helpers support safe casting and property access in polymorphic type systems.
"""


def safe_get_property(obj, prop, default=None):
    """Safely get a property from an object with fallback.

    Args:
        obj: Object to access property on
        prop: Property name
        default: Default value if property doesn't exist or access fails

    Returns:
        Property value or default
    """
    try:
        return getattr(obj, prop, default)
    except Exception:
        return default


def smart_cast(obj, target_type):
    """Attempt to cast an object to a target type.

    Args:
        obj: Object to cast
        target_type: Target type or interface

    Returns:
        Casted object or None if cast fails
    """
    try:
        return target_type(obj)
    except Exception:
        return None


def cast_or_default(obj, target_type, prop=None, default=None):
    """Cast an object and optionally get a property, with fallback.

    Args:
        obj: Object to cast
        target_type: Target type or interface
        prop: Optional property to get after casting
        default: Default value if cast or property access fails

    Returns:
        Property value, casted object, or default
    """
    casted = smart_cast(obj, target_type)
    if casted is None:
        return default
    if prop:
        return safe_get_property(casted, prop, default)
    return casted


def get_headword(entry, default="Unknown"):
    """Get headword text from a lexicon entry.

    Args:
        entry: ILexEntry object
        default: Default value if headword is not accessible

    Returns:
        Headword text or default
    """
    try:
        return entry.HeadWord.Text
    except Exception:
        return default


def get_lexeme_form(entry, default=""):
    """Get lexeme form text from a lexicon entry.

    Args:
        entry: ILexEntry object
        default: Default value if lexeme form is not accessible

    Returns:
        Lexeme form text or default
    """
    try:
        return entry.LexemeForm.Form.Text
    except Exception:
        return default


# Helper function definitions as a single source of truth
# Used for code injection in module execution
HELPER_FUNCTION_DEFS = """
def safe_get_property(obj, prop, default=None):
    try: return getattr(obj, prop, default)
    except: return default

def smart_cast(obj, target_type):
    try: return target_type(obj)
    except: return None

def cast_or_default(obj, target_type, prop=None, default=None):
    casted = smart_cast(obj, target_type)
    return default if casted is None else (safe_get_property(casted, prop, default) if prop else casted)

def get_headword(entry, default="Unknown"):
    try: return entry.HeadWord.Text
    except: return default

def get_lexeme_form(entry, default=""):
    try: return entry.LexemeForm.Form.Text
    except: return default
"""
