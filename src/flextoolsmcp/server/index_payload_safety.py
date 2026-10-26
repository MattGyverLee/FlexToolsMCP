#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S-P1-1 (#369 Phase 5): label index-served API text as library documentation
(data), and drop method-level import lines that do not match the known
namespace patterns for each library.

Index JSON is build output from upstream docstrings; it must not be served
in the same undifferentiated channel as server guidance without provenance,
and executable-looking import lines must not advertise arbitrary modules
(for example ``import os`` embedded in a poisoned index entry).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .flexicon_imports import load_surface
from .response_keys import KEY_IMPORT_STATEMENT, KEY_METHODS

# Top-level marker on get_object_api (and nested on each paginated entity).
INDEX_DOCUMENTATION_PROVENANCE: Dict[str, str] = {
    "kind": "library_documentation",
    "origin": "shipped_api_index",
    "trust": "data_not_server_instructions",
}

_FLEXICON_IMPORT_RE = re.compile(
    r"^\s*from\s+flexicon\s+import\s+(.+)\s*$",
    re.IGNORECASE,
)
_FLEXLIBS_IMPORT_RE = re.compile(
    r"^\s*from\s+flexlibs(?:2|_stable)?\s+import\s+(.+)\s*$",
    re.IGNORECASE,
)
_LCM_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+SIL\.|import\s+SIL\.)",
    re.IGNORECASE,
)
_BARE_IMPORT_RE = re.compile(r"^\s*import\s+(\S+)")


def index_data_provenance() -> Dict[str, str]:
    """Shallow copy so callers cannot mutate the module constant."""
    return dict(INDEX_DOCUMENTATION_PROVENANCE)


def _flexicon_import_names(tail: str) -> List[str]:
    names: List[str] = []
    for part in tail.split(","):
        part = part.strip()
        if not part:
            continue
        name = part.split(" as ", 1)[0].strip()
        if name:
            names.append(name)
    return names


def validate_index_import_statement(
    statement: Optional[str],
    library: str,
    api_index: Any = None,
) -> Tuple[bool, Optional[str]]:
    """Return (is_valid, sanitized_statement_or_none).

    When invalid, the second value is None -- callers should omit
    ``import_statement`` and set ``import_statement_valid`` to False.
    """
    if not statement or not str(statement).strip():
        return True, None

    stmt = str(statement).strip()

    # Facade access paths (``project.LexEntry``) and other non-import guidance
    # from the index builder are not Python import lines.
    if not re.match(r"^\s*(from|import)\s+", stmt, re.IGNORECASE):
        return True, stmt

    if library == "flexicon":
        m = _FLEXICON_IMPORT_RE.match(stmt)
        if not m:
            return False, None
        surface = load_surface(api_index)
        if surface is None or surface.root_open:
            return True, stmt
        for name in _flexicon_import_names(m.group(1)):
            if name not in surface.root_names:
                return False, None
        return True, stmt

    if library == "flexlibs_stable":
        if not _FLEXLIBS_IMPORT_RE.match(stmt):
            return False, None
        return True, stmt

    if library == "liblcm":
        if not _LCM_IMPORT_RE.match(stmt):
            return False, None
        return True, stmt

    # Unknown library: reject bare ``import X`` lines; allow explicit from-imports.
    if _BARE_IMPORT_RE.match(stmt) and not stmt.lower().startswith("from "):
        return False, None
    return True, stmt


def sanitize_index_method_row(
    row: Dict[str, Any],
    library: str,
    api_index: Any = None,
) -> None:
    """Mutate a method row in place (S-P1-1 import_statement gate)."""
    if KEY_IMPORT_STATEMENT not in row:
        return
    valid, cleaned = validate_index_import_statement(
        row.get(KEY_IMPORT_STATEMENT), library, api_index
    )
    if not valid:
        row.pop(KEY_IMPORT_STATEMENT, None)
        row["import_statement_valid"] = False
    elif cleaned:
        row[KEY_IMPORT_STATEMENT] = cleaned
        row["import_statement_valid"] = True
    else:
        row.pop(KEY_IMPORT_STATEMENT, None)


def sanitize_index_entity_block(
    block: Dict[str, Any],
    library: str,
    api_index: Any = None,
) -> None:
    """Attach provenance and sanitize method import lines on a paginated entity."""
    block["provenance"] = index_data_provenance()
    entity_import = block.get(KEY_IMPORT_STATEMENT)
    if entity_import is not None:
        valid, cleaned = validate_index_import_statement(
            entity_import, library, api_index
        )
        if not valid:
            block.pop(KEY_IMPORT_STATEMENT, None)
            block["import_statement_valid"] = False
        elif cleaned:
            block[KEY_IMPORT_STATEMENT] = cleaned
            block["import_statement_valid"] = True
    for method in block.get(KEY_METHODS, []) or []:
        if isinstance(method, dict):
            sanitize_index_method_row(method, library, api_index)

