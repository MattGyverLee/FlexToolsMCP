#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Safe Casting Helpers for FLExTools Scripts

Provides utility functions for safe property access with automatic fallback casting.
Works with all 3 API flavors: flexlibs_stable, flexlibs2, liblcm

These helpers can be injected into generated code to handle polymorphic type issues
where base interfaces (like ICmObject) don't expose properties that concrete types have.

Usage:
    from flexlibs2 import FLExInitialize, FLExCleanup, FLExProject
    from casting_helpers import safe_get_property, smart_cast

    # For flexlibs2
    entry = project.LexEntry.GetAll()[0]

    # Safe property access with auto-casting
    headword = safe_get_property(entry, 'HeadWord')

    # Or explicit casting
    from SIL.LCModel import ILexEntry
    entry_concrete = ILexEntry(entry)
    headword = entry_concrete.HeadWord.Text
"""

from typing import Any, Optional, List, Type
import inspect
import textwrap


def safe_get_property(obj: Any, property_name: str, default: Any = None) -> Any:
    """Safely get a property with fallback to None if not accessible.

    Tries to access the property directly first. If that fails (AttributeError),
    returns the default value instead of raising an exception.

    Works across all 3 API flavors without wrapper-specific knowledge.

    Args:
        obj: Object to access property on
        property_name: Name of property to access
        default: Value to return if property not accessible (default: None)

    Returns:
        Property value if accessible, else default value

    Example:
        headword = safe_get_property(sense.Owner, 'HeadWord', 'Unknown')
    """
    try:
        return getattr(obj, property_name, default)
    except (AttributeError, TypeError):
        return default


def smart_cast(obj: Any, target_type: Type) -> Optional[Any]:
    """Attempt to cast an object to a target type using pythonnet casting.

    This is the universal pattern for all 3 API flavors:
        from SIL.LCModel import ILexEntry
        entry = smart_cast(obj, ILexEntry)
        if entry:
            print(entry.HeadWord.Text)

    Args:
        obj: Object to cast
        target_type: Target interface type (e.g., ILexEntry, IMultiString)

    Returns:
        Casted object if successful, None if casting fails

    Example:
        from SIL.LCModel import ILexEntry
        entry = smart_cast(sense.Owner, ILexEntry)
        if entry:
            headword = entry.HeadWord.Text
    """
    try:
        return target_type(obj)
    except (TypeError, AttributeError):
        return None


def cast_or_default(obj: Any, target_type: Type, property_name: str = None, default: Any = None) -> Any:
    """Cast object to target type and optionally get a property, with default fallback.

    Combines casting with property access in one operation. Perfect for chains like:
        sense.Owner.HeadWord -> cast sense.Owner to ILexEntry, then get HeadWord

    Args:
        obj: Object to cast
        target_type: Target interface type to cast to
        property_name: Optional property to access after casting
        default: Value to return if cast fails or property not found

    Returns:
        Property value if cast+property succeeds, else default

    Example:
        # Instead of:
        from SIL.LCModel import ILexEntry
        entry = ILexEntry(sense.Owner)
        headword = entry.HeadWord.Text

        # Can write:
        headword = cast_or_default(sense.Owner, ILexEntry, 'HeadWord', 'Unknown')
    """
    casted = smart_cast(obj, target_type)
    if casted is None:
        return default

    if property_name is None:
        return casted

    return safe_get_property(casted, property_name, default)


def get_headword(entry_or_sense: Any, default: str = "Unknown") -> str:
    """Get headword text from an entry or sense's owner entry.

    Handles the common pattern:
        - If passed an ILexEntry, get its HeadWord
        - If passed an ILexSense, get its Owner's HeadWord

    Works with all 3 API flavors automatically.

    Args:
        entry_or_sense: ILexEntry or ILexSense object
        default: Default value if headword not accessible

    Returns:
        Headword text string

    Example:
        for sense in senses:
            hw = get_headword(sense)
            print(f"Entry: {hw}")
    """
    try:
        # Try direct access (works if already ILexEntry)
        return entry_or_sense.HeadWord.Text
    except (AttributeError, TypeError):
        pass

    # Try casting sense.Owner to ILexEntry
    try:
        from SIL.LCModel import ILexEntry
        if hasattr(entry_or_sense, 'Owner'):
            entry = ILexEntry(entry_or_sense.Owner)
            return entry.HeadWord.Text
    except (TypeError, AttributeError):
        pass

    return default


def get_lexeme_form(entry: Any, default: str = "") -> str:
    """Get lexeme form (headword form) text from a lexical entry.

    Handles polymorphic type issue where entry might be various interface types.

    Args:
        entry: ILexEntry or similar object
        default: Default value if lexeme form not accessible

    Returns:
        Lexeme form text string

    Example:
        for entry in entries:
            form = get_lexeme_form(entry)
            print(f"Form: {form}")
    """
    try:
        return entry.LexemeForm.Form.Text
    except (AttributeError, TypeError):
        pass

    # Try casting
    try:
        from SIL.LCModel import ILexEntry, IMoForm
        lex_entry = ILexEntry(entry)
        form = lex_entry.LexemeForm
        if form:
            concrete_form = IMoForm(form)
            return concrete_form.Form.Text
    except (TypeError, AttributeError):
        pass

    return default


# Map of known polymorphic patterns to their helper functions
# This can be used by code generation to auto-inject the right helper
POLYMORPHIC_HELPERS = {
    "HeadWord": get_headword,
    "LexemeForm": get_lexeme_form,
    "safe_get_property": safe_get_property,
    "smart_cast": smart_cast,
    "cast_or_default": cast_or_default,
}


def _generate_helper_function_defs() -> str:
    """Generate helper function definitions from actual function sources.

    Dynamically extracts source code from the helper functions defined above.
    This eliminates manual duplication and ensures code-injection definitions
    always match the actual implementations.

    Returns:
        Multi-function string suitable for exec() injection into FLExTools scripts.
    """
    functions_to_inject = [
        safe_get_property,
        smart_cast,
        cast_or_default,
        get_headword,
        get_lexeme_form,
    ]

    sources = []
    for func in functions_to_inject:
        # Get the source, strip leading/trailing whitespace, dedent
        source = inspect.getsource(func)
        dedented = textwrap.dedent(source)
        sources.append(dedented)

    return "\n".join(sources)


# Helper function definitions for code injection
# Generated from actual function sources above - never manually edited
HELPER_FUNCTION_DEFS = _generate_helper_function_defs()
