#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Equivalence handler functions for FlexToolsMCP.

These handlers surface the cross-flavor mapping data that lives in the LCM
bridge files (flexicon_lcm_bridge_*.json, flexlibs_lcm_bridge_*.json) and
in reverse_mapping_liblcm-*.json. They are the deliberate, scoped path for
the LLM to do flexlibs <-> flexicon <-> liblcm lookups, replacing the
previous implicit cross-layer leakage.

Tools:
- get_wrapper_dependencies: wrapper method -> LCM internals it touches
- find_wrappers_for_lcm: LCM symbol -> wrapper methods that cover it
"""

import json
from typing import Any, Optional
from mcp.types import TextContent

# Import kernel deps (with fallback for both package and script modes)
try:
    from ..kernel import get_api_index, session_state
    from ..response_keys import (
        KEY_FOUND, KEY_MESSAGE, KEY_HINT, KEY_SUMMARY,
        KEY_LIBRARY, KEY_METHOD, KEY_LCM_INTERNALS, KEY_ADVISORY,
        KEY_LCM_NAME, KEY_COVERAGE, KEY_GAPS, KEY_KIND,
    )
except ImportError:
    from server.kernel import get_api_index, session_state
    from server.response_keys import (
        KEY_FOUND, KEY_MESSAGE, KEY_HINT, KEY_SUMMARY,
        KEY_LIBRARY, KEY_METHOD, KEY_LCM_INTERNALS, KEY_ADVISORY,
        KEY_LCM_NAME, KEY_COVERAGE, KEY_GAPS, KEY_KIND,
    )


# Library label keys used by the reverse_mapping by_liblcm_entity entries.
# (The reverse mapping uses 'flexlibs_2' / 'flexlibs_stable' rather than
# 'flexicon' / 'flexlibs_stable'.)
_REVERSE_LIB_KEYS = {
    "flexicon": "flexlibs_2",
    "flexlibs_stable": "flexlibs_stable",
}

# Heuristic prefixes/suffixes used by kind="auto"
_FACTORY_SUFFIX = "Factory"
_REPOSITORY_SUFFIX = "Repository"


def _text(payload: dict) -> list[TextContent]:
    """Wrap a payload dict in MCP TextContent."""
    return [TextContent(type="text", text=json.dumps(payload, indent=2))]


def _get_bridge(library: str) -> Optional[dict]:
    """Load and return the bridge dict for the requested wrapper library."""
    api = get_api_index()
    if api is None:
        return None

    if library == "flexicon":
        api.ensure_flexicon_bridge_loaded()
        return api.flexicon_lcm_bridge
    if library == "flexlibs_stable":
        api.ensure_flexlibs_stable_bridge_loaded()
        return api.flexlibs_stable_lcm_bridge
    return None


def _get_reverse_mapping() -> Optional[dict]:
    api = get_api_index()
    if api is None:
        return None
    api.ensure_reverse_mapping_loaded()
    return api.reverse_mapping


# ============================================================
# Tool 1: flextools_get_wrapper_dependencies
# ============================================================

async def handle_get_wrapper_dependencies(args: dict) -> list[TextContent]:
    """Look up the LCM internals (factories, repos, properties, methods,
    mapping_type) used by a flexlibs/flexicon wrapper method."""
    method = args.get("method", "")
    library = args.get("library", "flexicon")

    if library not in ("flexicon", "flexlibs_stable"):
        return _text({
            KEY_FOUND: False,
            KEY_LIBRARY: library,
            KEY_METHOD: method,
            KEY_MESSAGE: f"Unknown library: {library!r}. Use 'flexicon' or 'flexlibs_stable'.",
        })

    bridge = _get_bridge(library)
    if not bridge:
        return _text({
            KEY_FOUND: False,
            KEY_LIBRARY: library,
            KEY_METHOD: method,
            KEY_MESSAGE: f"No LCM bridge file is loaded for {library!r}. "
                         f"Run `python src/refresh.py` to regenerate it.",
        })

    by_method = bridge.get("by_method", {})
    entry = by_method.get(method)
    if entry is None:
        # Suggest checking the other library as a hint.
        other = "flexlibs_stable" if library == "flexicon" else "flexicon"
        return _text({
            KEY_FOUND: False,
            KEY_LIBRARY: library,
            KEY_METHOD: method,
            KEY_MESSAGE: f"No bridge entry for {method!r} in {library}.",
            KEY_HINT: (
                f"Check spelling (e.g. 'ClassName.MethodName'), or try "
                f"library='{other}' if this method belongs to the other wrapper."
            ),
        })

    # Surface the current session mode so the caller knows whether the LCM
    # names below are callable on the active surface or just informational.
    api_mode = getattr(session_state, "api_mode", "flexicon")
    advisory = (
        f"These LCM names are bridge metadata, not callable surface in "
        f"{library} mode. To call LCM directly, switch to api_mode='liblcm'."
    )

    return _text({
        KEY_FOUND: True,
        KEY_LIBRARY: library,
        KEY_METHOD: method,
        KEY_LCM_INTERNALS: entry,
        "session_mode": api_mode,
        KEY_ADVISORY: advisory,
    })


# ============================================================
# Tool 2: flextools_find_wrappers_for_lcm
# ============================================================

def _coverage_from_entity_value(value: Any) -> Optional[dict]:
    """Normalize a by_liblcm_entity per-library value into a dict-or-list shape.

    The reverse mapping stores per-library coverage as either:
      - None (no coverage)
      - {"class": str, "methods": [...]}  (single wrapper class)
      - [{"class": str, "methods": [...]}, ...]  (multiple wrapper classes)

    We pass the value through unchanged when present, so callers see the
    real shape; we only convert "absent" to None.
    """
    if value is None:
        return None
    return value


def _entity_summary_for_lib(value: Any) -> str:
    """Build a human-readable phrase describing wrapper coverage for one lib."""
    if value is None:
        return ""
    if isinstance(value, list):
        classes = [v.get("class", "?") for v in value if isinstance(v, dict)]
        total = sum(len(v.get("methods", []) or []) for v in value if isinstance(v, dict))
        return f"{', '.join(classes)} ({total} methods across {len(classes)} classes)"
    if isinstance(value, dict):
        cls = value.get("class", "?")
        methods = value.get("methods", []) or []
        return f"{cls} ({len(methods)} methods)"
    return ""


def _lookup_entity(reverse: dict, lcm_name: str, include: list[str]) -> Optional[dict]:
    """Look up `lcm_name` in by_liblcm_entity. Returns the response payload or None."""
    by_entity = reverse.get("by_liblcm_entity", {})

    # Bare entity name (e.g. "ILexEntry"). Also allow "Foo.bar" by stripping
    # the trailing dotted segment so callers can pass "ILexEntry.HeadWord"
    # and still get entity-level coverage info.
    candidates = [lcm_name]
    if "." in lcm_name:
        candidates.append(lcm_name.split(".", 1)[0])

    info = None
    matched_name = None
    for cand in candidates:
        if cand in by_entity:
            info = by_entity[cand]
            matched_name = cand
            break

    if info is None:
        return None

    coverage: dict = {}
    gaps: list[str] = []
    for lib in include:
        rev_key = _REVERSE_LIB_KEYS.get(lib)
        if rev_key is None:
            continue
        value = info.get(rev_key)
        coverage[lib] = _coverage_from_entity_value(value)
        if coverage[lib] is None:
            gaps.append(lib)

    # Build a human-readable summary
    parts = []
    for lib, value in coverage.items():
        if value is None:
            continue
        phrase = _entity_summary_for_lib(value)
        parts.append(f"{lib}: {phrase}" if phrase else lib)
    if not parts:
        summary = f"No {' or '.join(include)} wrapper coverage for {matched_name}."
    elif gaps:
        summary = f"{matched_name}: covered by {', '.join(parts)}; not wrapped in {', '.join(gaps)}."
    else:
        summary = f"{matched_name}: covered by {', '.join(parts)}."

    return {
        KEY_FOUND: True,
        KEY_LCM_NAME: lcm_name,
        KEY_KIND: "entity",
        KEY_COVERAGE: coverage,
        KEY_GAPS: gaps,
        KEY_SUMMARY: summary,
        KEY_ADVISORY: (
            "Use api_mode='liblcm' if you need to access this LCM type directly."
        ),
    }


def _lookup_flat_kind(
    reverse: dict, lcm_name: str, kind: str, include: list[str]
) -> Optional[dict]:
    """Look up in one of the flat dicts: factories / repositories / methods / properties.

    Each value is a list of {class, method, signature, description, mapping_type}.
    The reverse mapping does not split these by library, so we report the flat
    list as wrapper coverage and surface a gap whenever an `include` library
    is asked for but produced zero hits. (Currently every entry is a
    flexicon method since that is the wrapper layer that maps LCM directly.)
    """
    bucket = reverse.get(kind, {}) if kind != "factory" else reverse.get("factories", {})
    if kind == "factory":
        bucket = reverse.get("factories", {})
    elif kind == "repository":
        bucket = reverse.get("repositories", {})
    elif kind == "method":
        bucket = reverse.get("methods", {})
    elif kind == "property":
        bucket = reverse.get("properties", {})

    entries = bucket.get(lcm_name)
    if not entries:
        return None

    # Split entries by inferred library. The reverse mapping does not encode
    # this directly, so we infer: any entry whose `class` matches a class in
    # the flexicon bridge belongs to flexicon; anything else falls back to
    # flexlibs_stable. To avoid pulling the bridge for a hot path, default
    # to attributing all entries to flexicon (which is where the reverse
    # mapping is generated from in build_reverse_mapping.py).
    coverage = {lib: [] for lib in include}
    if "flexicon" in coverage:
        coverage["flexicon"] = list(entries)

    gaps = [lib for lib, v in coverage.items() if not v]

    # Map our internal kind to a stable response label
    kind_label = {
        "factory": "factory",
        "repository": "repository",
        "method": "method",
        "property": "property",
    }.get(kind, kind)

    parts = []
    for lib, vals in coverage.items():
        if vals:
            parts.append(f"{lib}: {len(vals)} wrapper method(s)")
    summary_core = ", ".join(parts) if parts else "no wrapper coverage"
    if gaps:
        summary = f"{lcm_name} ({kind_label}): {summary_core}; not wrapped in {', '.join(gaps)}."
    else:
        summary = f"{lcm_name} ({kind_label}): {summary_core}."

    return {
        KEY_FOUND: True,
        KEY_LCM_NAME: lcm_name,
        KEY_KIND: kind_label,
        KEY_COVERAGE: coverage,
        KEY_GAPS: gaps,
        KEY_SUMMARY: summary,
        KEY_ADVISORY: (
            "Use api_mode='liblcm' if you need to call this LCM symbol directly."
        ),
    }


def _auto_lookup(reverse: dict, lcm_name: str, include: list[str]) -> Optional[dict]:
    """Dispatch order for kind='auto':
       1. by_liblcm_entity (handles 'Foo' and 'Foo.bar')
       2. factories (if name endswith 'Factory')
       3. repositories (if name endswith 'Repository')
       4. properties
       5. methods
    """
    hit = _lookup_entity(reverse, lcm_name, include)
    if hit:
        return hit

    if lcm_name.endswith(_FACTORY_SUFFIX):
        hit = _lookup_flat_kind(reverse, lcm_name, "factory", include)
        if hit:
            return hit

    if lcm_name.endswith(_REPOSITORY_SUFFIX):
        hit = _lookup_flat_kind(reverse, lcm_name, "repository", include)
        if hit:
            return hit

    hit = _lookup_flat_kind(reverse, lcm_name, "property", include)
    if hit:
        return hit

    hit = _lookup_flat_kind(reverse, lcm_name, "method", include)
    if hit:
        return hit

    return None


async def handle_find_wrappers_for_lcm(args: dict) -> list[TextContent]:
    """Find which wrapper methods cover a given LibLCM symbol, and surface
    libraries with no coverage in the `gaps` field."""
    lcm_name = args.get("lcm_name", "")
    kind = args.get("kind", "auto") or "auto"
    include = args.get("include") or ["flexicon", "flexlibs_stable"]

    # Validate include (silently drop unknown libs)
    include = [lib for lib in include if lib in _REVERSE_LIB_KEYS]
    if not include:
        include = ["flexicon", "flexlibs_stable"]

    reverse = _get_reverse_mapping()
    if not reverse:
        return _text({
            KEY_FOUND: False,
            KEY_LCM_NAME: lcm_name,
            KEY_KIND: kind,
            KEY_MESSAGE: "Reverse mapping (reverse_mapping_liblcm-*.json) not loaded. "
                         "Run `python src/build_reverse_mapping.py` to regenerate it.",
        })

    if kind == "auto":
        hit = _auto_lookup(reverse, lcm_name, include)
    elif kind == "entity":
        hit = _lookup_entity(reverse, lcm_name, include)
    elif kind in ("factory", "repository", "method", "property"):
        hit = _lookup_flat_kind(reverse, lcm_name, kind, include)
    else:
        return _text({
            KEY_FOUND: False,
            KEY_LCM_NAME: lcm_name,
            KEY_KIND: kind,
            KEY_MESSAGE: f"Unknown kind: {kind!r}. "
                         "Use one of: 'entity', 'factory', 'repository', 'method', 'property', 'auto'.",
        })

    if hit is None:
        return _text({
            KEY_FOUND: False,
            KEY_LCM_NAME: lcm_name,
            KEY_KIND: kind,
            KEY_MESSAGE: f"No wrapper coverage found for {lcm_name!r} (kind={kind}).",
            KEY_HINT: (
                "Check the spelling, or try kind='auto' to search across "
                "entity/factory/repository/method/property buckets."
            ),
        })

    return _text(hit)
