"""
API Discovery Handler Module

Provides read-only API discovery tools:
- get_object_api: Get API documentation for specific object types
- search_by_capability: Search for methods by natural language capability
- find_examples: Find code examples for methods
- resolve_property: Resolve pythonic property names to LibLCM equivalents
"""

import json
import heapq
from mcp.types import TextContent
from typing import List, Dict, Any, cast

# Import kernel and config (with fallback for both package and script modes)
try:
    from ..kernel import get_api_index, session_state
    from ...response_utils import json_response
    from ..response_keys import (
        # Basic fields
        KEY_OBJECT_TYPE, KEY_FOUND, KEY_METHODS, KEY_ENTITY, KEY_NAME, KEY_TYPE,
        KEY_SOURCE, KEY_SIGNATURE, KEY_DESCRIPTION, KEY_CATEGORY, KEY_SCORE,
        KEY_MATCHES, KEY_FLEXLIBS2, KEY_LIBLCM, KEY_FLEXLIBS_STABLE, KEY_FLEXLIBS2_MATCHES,
        KEY_LIBLCM_MATCHES, KEY_FLEXLIBS_STABLE_MATCHES, KEY_DISAMBIGUATION, KEY_QUERY, KEY_RESULTS_COUNT,
        KEY_EXAMPLES, KEY_MESSAGE, KEY_SUMMARY, KEY_METHODS_COUNT, KEY_EXAMPLE,
        # Handler-specific discovery fields
        KEY_SOURCES_SEARCHED, KEY_FALLBACK_USED, KEY_API_MODE, KEY_API_MODE_DESCRIPTION,
        KEY_SEARCH_METHOD, KEY_SEMANTIC_AVAILABLE, KEY_IMPORT_STATEMENT, KEY_IMPORT_REQUIRED,
        KEY_TOTAL_METHODS, KEY_RETURNED_METHODS, KEY_PROPERTIES, KEY_TOTAL_PROPERTIES, KEY_RETURNED_PROPERTIES, KEY_HAS_MORE, KEY_NEXT_OFFSET,
        KEY_SOURCE_FILE, KEY_SESSION_CONTEXT, KEY_DETECTED, KEY_AUTO_RESOLVED,
        KEY_SELECTED, KEY_CONFIDENCE, KEY_REASONING, KEY_ALTERNATIVES, KEY_QUESTION,
        KEY_METHOD_NAME, KEY_OPERATION_TYPE, KEY_PYTHONIC_NAME, KEY_KIND, KEY_TARGET_TYPE,
        KEY_IS_MULTISTRING, KEY_EMPTY_VALUE_WARNING, KEY_PROPERTY_NAME, KEY_CONTEXT_ENTITY,
        KEY_LIMIT, KEY_OFFSET, KEY_SUMMARY_ONLY, KEY_INCLUDE_CASTING_INFO, KEY_SUFFIX_GUIDE,
        KEY_USAGE_EXAMPLES, KEY_PYTHONNET_CASTING, KEY_REQUIRES_CAST, KEY_DEFINED_ON,
        KEY_NOT_AVAILABLE_ON, KEY_WARNING, KEY_PATTERN, KEY_FLEXLIBS2_HELPER,
        KEY_AVAILABLE_ON_CONCRETE_TYPES, KEY_POLYMORPHIC_COLLECTION_WARNING,
        KEY_BASE_TYPE, KEY_CONCRETE_TYPES, KEY_UNIQUE_PROPERTIES_BY_TYPE, KEY_CASTING_HINT,
        KEY_PROPERTY_AVAILABILITY_IN_CONTEXT, KEY_HAS_PROPERTY_ON, KEY_MISSING_FROM, KEY_GUIDANCE,
        KEY_ERROR, KEY_HINT,
        # Operation types
        OP_CREATE, OP_READ, OP_UPDATE, OP_DELETE, OP_ITERATE, OP_SEARCH,
    )
except ImportError:
    from server.kernel import get_api_index, session_state
    from response_utils import json_response
    from server.response_keys import (
        # Basic fields
        KEY_OBJECT_TYPE, KEY_FOUND, KEY_METHODS, KEY_ENTITY, KEY_NAME, KEY_TYPE,
        KEY_SOURCE, KEY_SIGNATURE, KEY_DESCRIPTION, KEY_CATEGORY, KEY_SCORE,
        KEY_MATCHES, KEY_FLEXLIBS2, KEY_LIBLCM, KEY_FLEXLIBS_STABLE, KEY_FLEXLIBS2_MATCHES,
        KEY_LIBLCM_MATCHES, KEY_FLEXLIBS_STABLE_MATCHES, KEY_DISAMBIGUATION, KEY_QUERY, KEY_RESULTS_COUNT,
        KEY_EXAMPLES, KEY_MESSAGE, KEY_SUMMARY, KEY_METHODS_COUNT, KEY_EXAMPLE,
        # Handler-specific discovery fields
        KEY_SOURCES_SEARCHED, KEY_FALLBACK_USED, KEY_API_MODE, KEY_API_MODE_DESCRIPTION,
        KEY_SEARCH_METHOD, KEY_SEMANTIC_AVAILABLE, KEY_IMPORT_STATEMENT, KEY_IMPORT_REQUIRED,
        KEY_TOTAL_METHODS, KEY_RETURNED_METHODS, KEY_PROPERTIES, KEY_TOTAL_PROPERTIES, KEY_RETURNED_PROPERTIES, KEY_HAS_MORE, KEY_NEXT_OFFSET,
        KEY_SOURCE_FILE, KEY_SESSION_CONTEXT, KEY_DETECTED, KEY_AUTO_RESOLVED,
        KEY_SELECTED, KEY_CONFIDENCE, KEY_REASONING, KEY_ALTERNATIVES, KEY_QUESTION,
        KEY_METHOD_NAME, KEY_OPERATION_TYPE, KEY_PYTHONIC_NAME, KEY_KIND, KEY_TARGET_TYPE,
        KEY_IS_MULTISTRING, KEY_EMPTY_VALUE_WARNING, KEY_PROPERTY_NAME, KEY_CONTEXT_ENTITY,
        KEY_LIMIT, KEY_OFFSET, KEY_SUMMARY_ONLY, KEY_INCLUDE_CASTING_INFO, KEY_SUFFIX_GUIDE,
        KEY_USAGE_EXAMPLES, KEY_PYTHONNET_CASTING, KEY_REQUIRES_CAST, KEY_DEFINED_ON,
        KEY_NOT_AVAILABLE_ON, KEY_WARNING, KEY_PATTERN, KEY_FLEXLIBS2_HELPER,
        KEY_AVAILABLE_ON_CONCRETE_TYPES, KEY_POLYMORPHIC_COLLECTION_WARNING,
        KEY_BASE_TYPE, KEY_CONCRETE_TYPES, KEY_UNIQUE_PROPERTIES_BY_TYPE, KEY_CASTING_HINT,
        KEY_PROPERTY_AVAILABILITY_IN_CONTEXT, KEY_HAS_PROPERTY_ON, KEY_MISSING_FROM, KEY_GUIDANCE,
        KEY_ERROR, KEY_HINT,
        # Operation types
        OP_CREATE, OP_READ, OP_UPDATE, OP_DELETE, OP_ITERATE, OP_SEARCH,
    )

# Type note: api_index is initialized by server.py before any handlers are called

# Operation type keyword patterns
OPERATION_PATTERNS = {
    OP_CREATE: ["create", "add", "new", "make"],
    OP_READ: ["get", "fetch", "retrieve", "find", "read"],
    OP_UPDATE: ["set", "update", "modify", "change"],
    OP_DELETE: ["delete", "remove", "clear", "erase"],
    OP_ITERATE: ["getall", "list", "iterate", "enumerate"],
    OP_SEARCH: ["find", "search", "query"],
}

# Suffix kind guide (LibLCM property suffixes)
SUFFIX_KIND_GUIDE = {
    "OA": "Owning Atomic - single owned child object",
    "OS": "Owning Sequence - ordered collection of owned objects",
    "OC": "Owning Collection - unordered collection of owned objects",
    "RA": "Reference Atomic - single referenced object",
    "RS": "Reference Sequence - ordered collection of references",
    "RC": "Reference Collection - unordered collection of references"
}

# API mode configuration
API_MODE_CONFIG = {
    "flexlibs2": {
        "primary": ["flexlibs2"],
        "fallback": [],
        "description": "FlexLibs 2.0 (recommended)"
    },
    "flexlibs_stable": {
        "primary": ["flexlibs_stable"],
        "fallback": [],
        "description": "FlexLibs Stable (no auto-fallback; switch to api_mode='all' to also see LibLCM)"
    },
    "liblcm": {
        "primary": ["liblcm"],
        "fallback": [],
        "description": "Pure LibLCM"
    },
    "all": {
        "primary": ["flexlibs2", "flexlibs_stable", "liblcm"],
        "fallback": [],
        "description": "All sources"
    }
}

# Map of session-mode -> ordered list of (source_name, attr_name, response_key) tuples.
# Used by every read-only handler so a single mode never bleeds another source's
# entities/methods into the response. The "all" mode is the explicit opt-out.
_MODE_SOURCES: Dict[str, list] = {
    "flexlibs2": [("flexlibs2", "flexlibs2", KEY_FLEXLIBS2)],
    "flexlibs_stable": [("flexlibs_stable", "flexlibs_stable", KEY_FLEXLIBS_STABLE)],
    "liblcm": [("liblcm", "liblcm", KEY_LIBLCM)],
    "all": [
        ("flexlibs2", "flexlibs2", KEY_FLEXLIBS2),
        ("flexlibs_stable", "flexlibs_stable", KEY_FLEXLIBS_STABLE),
        ("liblcm", "liblcm", KEY_LIBLCM),
    ],
}


def active_sources_for_mode(mode: str) -> list:
    """Return the source tuples that should be visible for a given session mode.

    Each tuple is (source_name, APIIndex attribute, response key). Single-mode
    sessions return one tuple; "all" returns all three. Unknown modes default
    to flexlibs2 to keep wrappers as the safe default surface.
    """
    return _MODE_SOURCES.get(mode, _MODE_SOURCES["flexlibs2"])


def ensure_active_sources_loaded(api_index, mode: str) -> None:
    """Lazy-load only the index files needed for the active mode."""
    for source_name, _attr, _key in active_sources_for_mode(mode):
        if source_name == "liblcm":
            api_index.ensure_liblcm_loaded()
        elif source_name == "flexlibs_stable":
            api_index.ensure_flexlibs_stable_loaded()


# Domain-specific synonyms for query expansion (linguistics terminology)
DOMAIN_SYNONYMS = {
    "noun": "part of speech POS grammatical category",
    "verb": "part of speech POS grammatical category",
    "adjective": "part of speech POS grammatical category",
    "adverb": "part of speech POS grammatical category",
    "pronoun": "part of speech POS grammatical category",
    "preposition": "part of speech POS grammatical category",
    "pos": "part of speech grammatical category",
    "category": "grammatical category part of speech",
    "lemma": "headword citation form lexeme entry",
    "morpheme": "morph allomorph form",
    "affix": "prefix suffix infix circumfix",
    "stem": "root base form",
    "inflection": "inflectional paradigm conjugation declension",
    "derivation": "derivational affix",
    "translation": "gloss definition meaning",
    "meaning": "gloss definition sense",
    "example": "sentence illustration",
    "pronunciation": "phonetic phonology",
    "etymology": "origin history borrowed",
    "domain": "semantic domain category field",
    "usage": "register style sociolinguistic",
}

# Search synonyms for keyword matching
SEARCH_SYNONYMS = {
    "add": ["add", "set", "create", "insert", "append"],
    "set": ["set", "add", "update", "modify", "assign"],
    "get": ["get", "fetch", "retrieve", "find", "read"],
    "delete": ["delete", "remove", "clear", "erase"],
    "remove": ["remove", "delete", "clear"],
    "create": ["create", "add", "new", "make"],
    "update": ["update", "set", "modify", "change"],
    "find": ["find", "search", "get", "lookup", "query"],
    "list": ["list", "getall", "all", "iterate", "enumerate"],
    "gloss": ["gloss", "translation", "meaning"],
    "definition": ["definition", "meaning", "description"],
    "sense": ["sense", "meaning", "definition"],
    "entry": ["entry", "headword", "lexeme", "word"],
    "noun": ["noun", "pos", "partofspeech", "grammatical", "category"],
    "verb": ["verb", "pos", "partofspeech", "grammatical", "category"],
    "adjective": ["adjective", "pos", "partofspeech", "grammatical", "category"],
    "adverb": ["adverb", "pos", "partofspeech", "grammatical", "category"],
    "pos": ["pos", "partofspeech", "grammatical", "category", "speech"],
    "lemma": ["lemma", "headword", "citation", "lexeme"],
    "morpheme": ["morpheme", "morph", "allomorph", "form"],
    "stem": ["stem", "root", "base"],
    "affix": ["affix", "prefix", "suffix", "infix"],
}


# ============================================================
# Imports for helpers (after constants)
# ============================================================
try:
    from .utils import normalize_object_name
except ImportError:
    from utils import normalize_object_name


# ============================================================
# Helper Functions
# ============================================================

def _matches_operation(name_lower: str, operation_type: str) -> bool:
    """Check if method name matches operation type pattern."""
    if operation_type not in OPERATION_PATTERNS:
        return False
    return any(x in name_lower for x in OPERATION_PATTERNS[operation_type])




def rank_object_matches(partial_name: str, matches: list, api_mode: str) -> dict:
    """Rank partial object type matches by relevance and confidence."""

    if not matches:
        return {KEY_MATCHES: [], KEY_AUTO_RESOLVED: False}

    for match in matches:
        score = 0
        reasons = []

        if match.get(KEY_NAME, "").lower() == partial_name.lower():
            score = 100
            reasons.append("Exact match")

        if match.get(KEY_SOURCE) == api_mode:
            score += 30
            reasons.append(f"Matches session API mode ({api_mode})")

        if "Operations" in match.get(KEY_NAME, "") and api_mode == "flexlibs2":
            score += 20
            reasons.append("Operations class (FlexLibs2 pattern)")

        if match.get(KEY_CATEGORY) == "lexicon":
            score += 10
            reasons.append("Lexicon is most common domain")

        pos = match.get(KEY_NAME, "").lower().find(partial_name.lower())
        if pos == 0:
            score += 15
            reasons.append("Name starts with search term")

        match[KEY_SCORE] = score
        match[KEY_REASONING] = "; ".join(reasons) if reasons else "Default ranking"
        match[KEY_CONFIDENCE] = "high" if score >= 60 else "medium" if score >= 30 else "low"

    matches.sort(key=lambda x: x.get(KEY_SCORE, 0), reverse=True)

    if not matches:
        return {KEY_MATCHES: [], KEY_AUTO_RESOLVED: False}

    top = matches[0]
    auto_resolve = len(matches) == 1 or (top.get(KEY_SCORE, 0) - matches[1].get(KEY_SCORE, 0) >= 30)

    return {
        KEY_AUTO_RESOLVED: auto_resolve,
        KEY_SELECTED: top.get(KEY_NAME) if auto_resolve else None,
        KEY_CONFIDENCE: top.get(KEY_CONFIDENCE),
        KEY_REASONING: top.get(KEY_REASONING),
        KEY_MATCHES: matches[:5],
        "needs_clarification": not auto_resolve
    }


def build_response_with_context(data: dict, include_session: bool = True) -> dict:
    """Add session context to tool response."""

    if include_session and session_state.initialized:
        data[KEY_SESSION_CONTEXT] = {
            KEY_API_MODE: session_state.api_mode,
            "write_enabled": session_state.write_enabled,
            "project": session_state.project_name or "(not set)"
        }

    return data


def paginate_entity(entity: dict, summary_only: bool, method_filter: str, limit: int, offset: int, object_type: str = "", library: str = "flexlibs2") -> dict:
    """Apply pagination and filtering to an entity's methods and properties."""
    try:
        from ..constants import OPERATIONS_CLASSES, KNOWN_OPERATIONS
    except ImportError:
        from server.constants import OPERATIONS_CLASSES, KNOWN_OPERATIONS

    result = {
        KEY_CATEGORY: entity.get(KEY_CATEGORY),
        KEY_SUMMARY: entity.get(KEY_SUMMARY, ""),
        KEY_SOURCE_FILE: entity.get(KEY_SOURCE_FILE, ""),
    }

    if object_type in OPERATIONS_CLASSES:
        result[KEY_IMPORT_STATEMENT] = f"from {library} import {object_type}"
        result[KEY_IMPORT_REQUIRED] = True

    methods = entity.get(KEY_METHODS, [])

    if method_filter:
        filter_lower = method_filter.lower()
        methods = [m for m in methods if filter_lower in m.get(KEY_NAME, "").lower()]

    total_methods = len(methods)
    result[KEY_TOTAL_METHODS] = total_methods

    methods = methods[offset:offset + limit]

    if summary_only:
        result[KEY_METHODS] = [
            {KEY_NAME: m.get(KEY_NAME), KEY_SIGNATURE: m.get(KEY_SIGNATURE, "")}
            for m in methods
        ]
    else:
        result[KEY_METHODS] = methods

    result[KEY_RETURNED_METHODS] = len(result[KEY_METHODS])
    result[KEY_HAS_MORE] = (offset + limit) < total_methods
    if result[KEY_HAS_MORE]:
        result[KEY_NEXT_OFFSET] = offset + limit

    properties = list(entity.get(KEY_PROPERTIES, []))

    if object_type == "FLExProject":
        existing = {p.get(KEY_NAME) for p in properties if p.get(KEY_NAME)}
        for op in KNOWN_OPERATIONS:
            if not op.endswith("Operations"):
                continue
            accessor = op[: -len("Operations")]
            if accessor in existing:
                continue
            properties.append({
                KEY_NAME: accessor,
                KEY_DESCRIPTION: f"Access to {op} (legacy accessor; prefer real FLExProject property if one exists).",
                KEY_TARGET_TYPE: op,
                "is_property": True,
            })
            existing.add(accessor)

    if method_filter:
        filter_lower = method_filter.lower()
        properties = [p for p in properties if filter_lower in p.get(KEY_NAME, "").lower()]

    total_properties = len(properties)
    result[KEY_TOTAL_PROPERTIES] = total_properties

    properties = properties[offset:offset + limit]

    if summary_only:
        result[KEY_PROPERTIES] = [
            {
                KEY_NAME: p.get(KEY_NAME),
                KEY_DESCRIPTION: (p.get(KEY_DESCRIPTION, "") or "")[:120],
            }
            for p in properties
        ]
    else:
        result[KEY_PROPERTIES] = properties

    result[KEY_RETURNED_PROPERTIES] = len(result[KEY_PROPERTIES])

    return result


def resolve_pythonic_property(name: str, context_entity: str | None = None) -> List[Dict[str, Any]]:
    """Resolve a pythonic (suffix-free) property name to its LibLCM equivalent(s)."""
    if not get_api_index() or not get_api_index().liblcm:
        return []

    suffix_index = get_api_index().liblcm.get("suffix_index", {})
    if not suffix_index:
        return []

    results = []

    by_pythonic = suffix_index.get("by_pythonic_name", {})
    if name in by_pythonic:
        matches = by_pythonic[name]
        if context_entity:
            results = [m for m in matches if m[KEY_ENTITY] == context_entity]
        else:
            results = matches

    if not results:
        by_full = suffix_index.get("by_full_name", {})
        if context_entity:
            key = f"{context_entity}.{name}"
            if key in by_full:
                match = by_full[key]
                results = [{
                    KEY_ENTITY: match[KEY_ENTITY],
                    "full_name": name,
                    KEY_PYTHONIC_NAME: match[KEY_PYTHONIC_NAME],
                    KEY_KIND: match[KEY_KIND]
                }]
        else:
            for key, match in by_full.items():
                if key.endswith(f".{name}"):
                    results.append({
                        KEY_ENTITY: match[KEY_ENTITY],
                        "full_name": name,
                        KEY_PYTHONIC_NAME: match[KEY_PYTHONIC_NAME],
                        KEY_KIND: match[KEY_KIND]
                    })

    return results


# ============================================================
# Handler Functions
# ============================================================

async def handle_get_object_api(args: dict) -> list[TextContent]:
    """Get API documentation for a specific object type.

    Source isolation: only the source(s) for the session mode are surfaced.
    flexlibs2 mode shows flexlibs2; flexlibs_stable shows flexlibs_stable;
    liblcm shows liblcm; "all" shows all three. The legacy include_flexlibs2/
    include_liblcm overrides still work but only widen the active source set.
    """
    object_type = args[KEY_OBJECT_TYPE]
    mode = session_state.get_mode()
    summary_only = args.get(KEY_SUMMARY_ONLY, False)
    method_filter = args.get("method_filter", "")
    limit = args.get(KEY_LIMIT, 50)
    offset = args.get(KEY_OFFSET, 0)

    api_index = get_api_index()
    ensure_active_sources_loaded(api_index, mode)

    sources = list(active_sources_for_mode(mode))
    # Legacy explicit opt-ins widen the surface (back-compat) but never bleed
    # other modes' content unless the caller asks for it.
    if args.get("include_flexlibs2") and not any(s[0] == "flexlibs2" for s in sources):
        api_index.ensure_liblcm_loaded()  # no-op for flexlibs2 but cheap
        sources.append(("flexlibs2", "flexlibs2", KEY_FLEXLIBS2))
    if args.get("include_liblcm") and not any(s[0] == "liblcm" for s in sources):
        api_index.ensure_liblcm_loaded()
        sources.append(("liblcm", "liblcm", KEY_LIBLCM))

    result = {KEY_OBJECT_TYPE: object_type, KEY_FOUND: False, KEY_API_MODE: mode}
    object_type_lower = object_type.lower()

    matches_key_for = {
        "flexlibs2": KEY_FLEXLIBS2_MATCHES,
        "flexlibs_stable": KEY_FLEXLIBS_STABLE_MATCHES,
        "liblcm": KEY_LIBLCM_MATCHES,
    }

    for source_name, attr, source_key in sources:
        index_data = getattr(api_index, attr, None)
        if not index_data:
            continue
        entities = index_data.get("entities", {})
        if object_type in entities:
            result[source_key] = paginate_entity(
                entities[object_type], summary_only, method_filter, limit, offset,
                object_type=object_type, library=source_name,
            )
            result[KEY_FOUND] = True
            continue
        # Substring match fallback (capped at 10 per source)
        max_matches = 10
        matches_key = matches_key_for[source_name]
        for name, entity in entities.items():
            if object_type_lower not in name.lower():
                continue
            if matches_key not in result:
                result[matches_key] = []
            entry = {KEY_NAME: name, KEY_CATEGORY: entity.get(KEY_CATEGORY)}
            if source_name == "liblcm":
                entry[KEY_TYPE] = entity.get(KEY_TYPE)
            else:
                entry[KEY_METHODS_COUNT] = len(entity.get(KEY_METHODS, []))
            result[matches_key].append(entry)
            result[KEY_FOUND] = True
            if len(result[matches_key]) >= max_matches:
                break

    if not result[KEY_FOUND]:
        result[KEY_MESSAGE] = f"No API documentation found for '{object_type}'. Try searching with search_by_capability or list_categories to explore available APIs."
    else:
        if KEY_FLEXLIBS2_MATCHES in result:
            matches_with_source = [
                {**m, KEY_SOURCE: "flexlibs2"} for m in result[KEY_FLEXLIBS2_MATCHES]
            ]
            ranked = rank_object_matches(object_type, matches_with_source, mode)
            if ranked.get(KEY_AUTO_RESOLVED):
                result[KEY_DISAMBIGUATION] = {
                    KEY_DETECTED: True,
                    KEY_AUTO_RESOLVED: True,
                    KEY_SELECTED: ranked[KEY_SELECTED],
                    KEY_CONFIDENCE: ranked[KEY_CONFIDENCE],
                    KEY_REASONING: ranked[KEY_REASONING]
                }
            elif ranked.get("needs_clarification"):
                result[KEY_DISAMBIGUATION] = {
                    KEY_DETECTED: True,
                    KEY_AUTO_RESOLVED: False,
                    KEY_ALTERNATIVES: ranked.get(KEY_MATCHES, []),
                    KEY_QUESTION: "Multiple matches found. Which did you mean?"
                }
            for match, ranked_match in zip(result[KEY_FLEXLIBS2_MATCHES], ranked.get(KEY_MATCHES, [])):
                match[KEY_SCORE] = ranked_match.get(KEY_SCORE)
                match[KEY_CONFIDENCE] = ranked_match.get(KEY_CONFIDENCE)
                match[KEY_REASONING] = ranked_match.get(KEY_REASONING)

        if KEY_LIBLCM_MATCHES in result:
            matches_with_source = [
                {**m, KEY_SOURCE: "liblcm"} for m in result[KEY_LIBLCM_MATCHES]
            ]
            ranked = rank_object_matches(object_type, matches_with_source, mode)
            if ranked.get(KEY_AUTO_RESOLVED):
                if KEY_DISAMBIGUATION not in result:
                    result[KEY_DISAMBIGUATION] = {
                        KEY_DETECTED: True,
                        KEY_AUTO_RESOLVED: True,
                        KEY_SELECTED: ranked[KEY_SELECTED],
                        KEY_CONFIDENCE: ranked[KEY_CONFIDENCE],
                        KEY_REASONING: ranked[KEY_REASONING]
                    }
            for match, ranked_match in zip(result[KEY_LIBLCM_MATCHES], ranked.get(KEY_MATCHES, [])):
                match[KEY_SCORE] = ranked_match.get(KEY_SCORE)
                match[KEY_CONFIDENCE] = ranked_match.get(KEY_CONFIDENCE)
                match[KEY_REASONING] = ranked_match.get(KEY_REASONING)

        if KEY_FLEXLIBS_STABLE_MATCHES in result:
            matches_with_source = [
                {**m, KEY_SOURCE: "flexlibs_stable"} for m in result[KEY_FLEXLIBS_STABLE_MATCHES]
            ]
            ranked = rank_object_matches(object_type, matches_with_source, mode)
            if ranked.get(KEY_AUTO_RESOLVED) and KEY_DISAMBIGUATION not in result:
                result[KEY_DISAMBIGUATION] = {
                    KEY_DETECTED: True,
                    KEY_AUTO_RESOLVED: True,
                    KEY_SELECTED: ranked[KEY_SELECTED],
                    KEY_CONFIDENCE: ranked[KEY_CONFIDENCE],
                    KEY_REASONING: ranked[KEY_REASONING]
                }
            for match, ranked_match in zip(result[KEY_FLEXLIBS_STABLE_MATCHES], ranked.get(KEY_MATCHES, [])):
                match[KEY_SCORE] = ranked_match.get(KEY_SCORE)
                match[KEY_CONFIDENCE] = ranked_match.get(KEY_CONFIDENCE)
                match[KEY_REASONING] = ranked_match.get(KEY_REASONING)

        if KEY_FLEXLIBS2 in result:
            entity_name = result[KEY_FLEXLIBS2].get(KEY_NAME, object_type)
            for method in result[KEY_FLEXLIBS2].get(KEY_METHODS, []):
                method_name = method.get(KEY_NAME, "")
                if method_name:
                    session_state.record_discovered_api(entity_name, method_name)
        if KEY_LIBLCM in result:
            entity_name = result[KEY_LIBLCM].get(KEY_NAME, object_type)
            for prop in result[KEY_LIBLCM].get("properties", []):
                prop_name = prop.get(KEY_NAME, "")
                if prop_name:
                    session_state.record_discovered_api(entity_name, prop_name)
            for method in result[KEY_LIBLCM].get(KEY_METHODS, []):
                method_name = method.get(KEY_NAME, "")
                if method_name:
                    session_state.record_discovered_api(entity_name, method_name)
        if KEY_FLEXLIBS_STABLE in result:
            entity_name = result[KEY_FLEXLIBS_STABLE].get(KEY_NAME, object_type)
            for method in result[KEY_FLEXLIBS_STABLE].get(KEY_METHODS, []):
                method_name = method.get(KEY_NAME, "")
                if method_name:
                    session_state.record_discovered_api(entity_name, method_name)

        result = build_response_with_context(result, include_session=True)

    if result.get(KEY_FOUND):
        session_state.record_validated_api(object_type)

    return json_response(result)


async def handle_search_by_capability(args: dict) -> list[TextContent]:
    """Search for methods by capability description with API mode support."""
    query = args[KEY_QUERY]
    max_results = args.get("max_results", 10)
    api_mode = args.get(KEY_API_MODE, session_state.get_mode())
    use_semantic = args.get("semantic", True)

    # Cache API index to avoid redundant lookups in search loops
    api_index = get_api_index()

    # Lazy-load APIs if needed (they're deferred from startup for speed)
    if api_mode in ["all", "liblcm"]:
        api_index.ensure_liblcm_loaded()
    if api_mode in ["all", "flexlibs_stable"]:
        api_index.ensure_flexlibs_stable_loaded()

    query_lower = query.lower()
    expanded_query = query
    for term, expansion in DOMAIN_SYNONYMS.items():
        if term in query_lower:
            expanded_query = f"{query} {expansion}"
            break

    results = []
    search_method = "keyword"
    sources_searched = []
    fallback_used = False

    config = API_MODE_CONFIG.get(api_mode, API_MODE_CONFIG["all"])

    if use_semantic and api_index.semantic_search and api_index.semantic_search.enabled:
        semantic_source = api_mode if api_mode in ["flexlibs2", "liblcm"] else "all"
        semantic_results = api_index.semantic_search.search(expanded_query, max_results, semantic_source)
        if semantic_results:
            results = semantic_results
            search_method = "semantic"
            sources_searched = [api_mode]

    if not results:
        query_terms = query_lower.split()
        expanded_terms = set(query_terms)
        for term in query_terms:
            if term in SEARCH_SYNONYMS:
                expanded_terms.update(SEARCH_SYNONYMS[term])

        # Pre-build pythonic name lookup (efficiency: O(N) instead of O(N*M))
        suffix_index = api_index.liblcm.get("suffix_index", {}) if api_index.liblcm else {}
        by_pythonic = suffix_index.get("by_pythonic_name", {})
        pythonic_lower = {k.lower(): k for k in by_pythonic.keys()}

        pythonic_expansions = set()
        for term in expanded_terms:
            if term in pythonic_lower:
                for match in by_pythonic[pythonic_lower[term]]:
                    pythonic_expansions.add(match["full_name"].lower())
        expanded_terms.update(pythonic_expansions)

        def search_source(source_name, index_data, boost=0):
            """Search a single source and return results.

            Optimization: Pre-lowercase all entity/method names once instead of
            per-term (eliminates 1000+ .lower() calls per large API search).
            """
            source_results = []
            if not index_data:
                return source_results

            for entity_name, entity in index_data.get("entities", {}).items():
                # Cache lowercased entity name for reuse in properties loop
                entity_name_lower = entity_name.lower()
                # Cache namespace + import_statement so every hit on this entity
                # carries them out -- without this, the assistant gets an entity
                # name but no way to import it, which was the root cause of #12.
                entity_namespace = entity.get("namespace", "") or ""
                if source_name == "liblcm":
                    entity_import = (
                        f"from {entity_namespace} import {entity_name}"
                        if entity_namespace
                        else ""
                    )
                else:
                    entity_import = f"from {source_name} import {entity_name}"

                for method in entity.get(KEY_METHODS, []):
                    method_name = method.get(KEY_NAME, '')
                    name_lower = method_name.lower()
                    score = boost

                    has_name_match = any(term in name_lower for term in expanded_terms)
                    if has_name_match:
                        score += 2

                    if score > boost:
                        # Pre-cache lowercased description and summary
                        desc_lower = method.get(KEY_DESCRIPTION, '').lower()
                        summary_lower = method.get(KEY_SUMMARY, '').lower()
                        for term in expanded_terms:
                            if term in desc_lower or term in summary_lower:
                                score += 1

                        if score > boost:
                            source_results.append({
                                KEY_SCORE: score,
                                KEY_SOURCE: source_name,
                                KEY_ENTITY: entity_name,
                                "namespace": entity_namespace,
                                KEY_IMPORT_STATEMENT: entity_import,
                                KEY_NAME: method_name,
                                KEY_TYPE: "method",
                                KEY_SIGNATURE: method.get(KEY_SIGNATURE),
                                KEY_DESCRIPTION: method.get(KEY_SUMMARY, method.get(KEY_DESCRIPTION, ""))[:150],
                                KEY_CATEGORY: entity.get(KEY_CATEGORY, "general"),
                            })

                if source_name == "liblcm":
                    for prop in entity.get("properties", []):
                        prop_name = prop.get(KEY_NAME, '')
                        pythonic_name = prop.get(KEY_PYTHONIC_NAME, prop_name)
                        # Pre-lowercase property names once (O(1) reuse)
                        name_lower = prop_name.lower()
                        pythonic_lower_name = pythonic_name.lower()
                        score = boost

                        for term in expanded_terms:
                            if term == name_lower or term == pythonic_lower_name:
                                score += 3
                                break

                        if score == boost:
                            # Pre-lowercase description and kind once
                            desc_lower = prop.get(KEY_DESCRIPTION, '').lower()
                            kind_lower = prop.get(KEY_KIND, '').lower()
                            for term in expanded_terms:
                                if term in desc_lower or term in kind_lower or term in name_lower or term in pythonic_lower_name:
                                    score += 1

                        if score > boost:
                            result_item = {
                                KEY_SCORE: score,
                                KEY_SOURCE: source_name,
                                KEY_ENTITY: entity_name,
                                "namespace": entity_namespace,
                                KEY_IMPORT_STATEMENT: entity_import,
                                KEY_NAME: prop_name,
                                KEY_PYTHONIC_NAME: pythonic_name if pythonic_name != prop_name else None,
                                KEY_TYPE: "property",
                                KEY_KIND: prop.get(KEY_KIND),
                                KEY_TARGET_TYPE: prop.get(KEY_TARGET_TYPE),
                                KEY_DESCRIPTION: prop.get(KEY_DESCRIPTION, "")[:150],
                                KEY_CATEGORY: entity.get(KEY_CATEGORY, "general"),
                            }
                            if prop.get(KEY_IS_MULTISTRING):
                                result_item[KEY_IS_MULTISTRING] = True
                                result_item[KEY_EMPTY_VALUE_WARNING] = "Returns '***' when empty - use flexlibs2 wrapper or normalize_text()"
                            source_results.append(result_item)
            return source_results

        for source in config["primary"]:
            if source == "flexlibs2" and api_index.flexlibs2:
                results.extend(search_source("flexlibs2", api_index.flexlibs2, boost=5))
                sources_searched.append("flexlibs2")
            elif source == "flexlibs_stable" and api_index.flexlibs_stable:
                results.extend(search_source("flexlibs_stable", api_index.flexlibs_stable, boost=3))
                sources_searched.append("flexlibs_stable")
            elif source == "liblcm" and api_index.liblcm:
                results.extend(search_source("liblcm", api_index.liblcm, boost=0))
                sources_searched.append("liblcm")

        if len(results) < max_results and config["fallback"]:
            for source in config["fallback"]:
                if source == "liblcm" and api_index.liblcm and "liblcm" not in sources_searched:
                    fallback_results = search_source("liblcm", api_index.liblcm, boost=0)
                    results.extend(fallback_results)
                    if fallback_results:
                        sources_searched.append("liblcm (fallback)")
                        fallback_used = True

        # Use heapq.nlargest for efficiency (don't sort all, just get top N)
        results = heapq.nlargest(max_results, results, key=lambda x: x[KEY_SCORE])

    for r in results:
        entity = r.get(KEY_ENTITY, "")
        method = r.get(KEY_NAME, "")
        if entity and method:
            session_state.record_discovered_api(entity, method)

    # Augment with multi-step worked examples (Phase A of #12). These are
    # patterns that span multiple methods, surfaced by tag/title match
    # against the free-text query. The original #12 pain point: 9
    # search_by_capability calls couldn't find MSA wiring / phonology
    # patterns because no single method docstring contained the full recipe.
    try:
        from ..worked_examples import find_worked_examples
    except ImportError:
        from server.worked_examples import find_worked_examples

    matched_patterns = find_worked_examples(query=query, max_results=3)

    result = {
        KEY_QUERY: query,
        KEY_API_MODE: api_mode,
        KEY_API_MODE_DESCRIPTION: config["description"],
        KEY_SEARCH_METHOD: search_method,
        KEY_SOURCES_SEARCHED: sources_searched,
        KEY_FALLBACK_USED: fallback_used,
        KEY_SEMANTIC_AVAILABLE: get_api_index().semantic_search.enabled if get_api_index().semantic_search else False,
        KEY_RESULTS_COUNT: len(results),
        "results": results,
        # Multi-step worked-example recipes matching the same query.
        "worked_examples": matched_patterns,
        "worked_examples_count": len(matched_patterns),
    }

    result = build_response_with_context(result, include_session=True)

    return json_response(result)


async def handle_find_examples(args: dict) -> list[TextContent]:
    """Find code examples for methods or operations."""
    method_name = args.get(KEY_METHOD_NAME)
    operation_type = args.get(KEY_OPERATION_TYPE)
    object_type = args.get(KEY_OBJECT_TYPE)
    max_results = args.get("max_results", 5)

    api_index = get_api_index()
    mode = session_state.get_mode()
    ensure_active_sources_loaded(api_index, mode)

    examples = []
    object_type_lower = object_type.lower() if object_type else None
    method_name_lower = method_name.lower() if method_name else None

    for source_name, attr, _key in active_sources_for_mode(mode):
        if len(examples) >= max_results:
            break
        index_data = getattr(api_index, attr, None)
        if not index_data:
            continue

        for entity_name, entity in index_data.get("entities", {}).items():
            if object_type_lower and object_type_lower not in entity_name.lower():
                continue

            # Cache namespace + import_statement once per entity (same fix as
            # search_by_capability for #12 -- examples must carry import path).
            entity_namespace = entity.get("namespace", "") or ""
            if source_name == "liblcm":
                entity_import = (
                    f"from {entity_namespace} import {entity_name}"
                    if entity_namespace
                    else ""
                )
            else:
                entity_import = f"from {source_name} import {entity_name}"

            for method in entity.get(KEY_METHODS, []):
                method_name_str = method.get(KEY_NAME, "")
                if method_name_lower and method_name_lower not in method_name_str.lower():
                    continue

                if operation_type:
                    if not _matches_operation(method_name_str.lower(), operation_type):
                        continue

                if method.get(KEY_EXAMPLE):
                    examples.append({
                        "class": entity_name,
                        "namespace": entity_namespace,
                        KEY_IMPORT_STATEMENT: entity_import,
                        KEY_METHOD_NAME: method_name_str,
                        KEY_SIGNATURE: method.get(KEY_SIGNATURE),
                        KEY_DESCRIPTION: method.get(KEY_SUMMARY, method.get(KEY_DESCRIPTION, ""))[:150],
                        KEY_EXAMPLE: method.get(KEY_EXAMPLE),
                        KEY_SOURCE: source_name,
                    })

                    if len(examples) >= max_results:
                        break

            if len(examples) >= max_results:
                break

    # Augment with multi-step worked examples (Phase A of #12 -- patterns
    # that span multiple methods, not individual docstring snippets).
    try:
        from ..worked_examples import find_worked_examples
    except ImportError:
        from server.worked_examples import find_worked_examples

    matched_patterns = find_worked_examples(
        query="",  # find_examples doesn't take a free-text query yet
        operation_type=operation_type or "",
        object_type=object_type or "",
        max_results=max_results,
    )

    return json_response({
        KEY_QUERY: {
            KEY_METHOD_NAME: method_name,
            KEY_OPERATION_TYPE: operation_type,
            KEY_OBJECT_TYPE: object_type
        },
        KEY_API_MODE: mode,
        KEY_RESULTS_COUNT: len(examples),
        KEY_EXAMPLES: examples,
        # Multi-step worked-example recipes that match the same query inputs.
        # Distinct from per-method docstring examples above.
        "worked_examples": matched_patterns,
        "worked_examples_count": len(matched_patterns),
    })


async def handle_resolve_property(args: dict) -> list[TextContent]:
    """Resolve pythonic property names to LibLCM equivalents with casting info."""
    property_name = args[KEY_PROPERTY_NAME]
    context_entity = args.get(KEY_CONTEXT_ENTITY)
    include_casting_info = args.get(KEY_INCLUDE_CASTING_INFO, True)

    # Cache API index to avoid redundant lookups
    api_index = get_api_index()

    # Lazy-load APIs if needed (they're deferred from startup for speed)
    api_index.ensure_liblcm_loaded()
    if include_casting_info:
        api_index.ensure_casting_index_loaded()

    matches = resolve_pythonic_property(property_name, context_entity)

    if not matches:
        result = {
            KEY_PROPERTY_NAME: property_name,
            KEY_CONTEXT_ENTITY: context_entity,
            KEY_FOUND: False,
            KEY_MESSAGE: f"No property '{property_name}' found",
            "suggestions": []
        }

        suffix_index = api_index.liblcm.get("suffix_index", {}) if api_index.liblcm else {}
        by_pythonic = suffix_index.get("by_pythonic_name", {})

        property_lower = property_name.lower()
        for pythonic_name in by_pythonic.keys():
            if property_lower in pythonic_name.lower() or pythonic_name.lower() in property_lower:
                result["suggestions"].append(pythonic_name)
            elif abs(len(property_name) - len(pythonic_name)) <= 2:
                if sum(a != b for a, b in zip(property_lower, pythonic_name.lower())) <= 2:
                    result["suggestions"].append(pythonic_name)

        result["suggestions"] = list(set(result["suggestions"]))[:10]

        if include_casting_info and get_api_index().casting_index:
            casting_props = get_api_index().casting_index.get("properties", {})
            if property_name in casting_props:
                result[KEY_FOUND] = True
                result[KEY_MESSAGE] = f"Property '{property_name}' found in casting index"
                result["casting_info"] = casting_props[property_name]
    else:
        result = {
            KEY_PROPERTY_NAME: property_name,
            KEY_CONTEXT_ENTITY: context_entity,
            KEY_FOUND: True,
            KEY_MATCHES: matches,
            KEY_SUFFIX_GUIDE: SUFFIX_KIND_GUIDE
        }

        if matches:
            result[KEY_USAGE_EXAMPLES] = []
            for match in matches[:3]:
                full_name = match.get("full_name", property_name)
                kind = match.get(KEY_KIND, "property")

                if kind in ("OS", "OC", "RS", "RC"):
                    result[KEY_USAGE_EXAMPLES].append(
                        f"for item in obj.{full_name}:  # Iterate {kind} collection"
                    )
                elif kind in ("OA", "RA"):
                    result[KEY_USAGE_EXAMPLES].append(
                        f"ref = obj.{full_name}  # Get single {kind} reference"
                    )

    if include_casting_info and get_api_index().casting_index:
        casting_props = get_api_index().casting_index.get("properties", {})
        poly_collections = get_api_index().casting_index.get("polymorphic_collections", {})
        prop_to_concrete = get_api_index().casting_index.get("property_to_concrete_mapping", {})

        if property_name in casting_props:
            casting_info = casting_props[property_name]
            result[KEY_PYTHONNET_CASTING] = {
                KEY_REQUIRES_CAST: True,
                KEY_DEFINED_ON: casting_info.get(KEY_DEFINED_ON, []),
                KEY_NOT_AVAILABLE_ON: casting_info.get(KEY_REQUIRES_CAST, []),
                KEY_WARNING: f"Property '{property_name}' is NOT available on base interfaces: {', '.join(casting_info.get(KEY_REQUIRES_CAST, []))}. You must cast to a concrete interface first.",
                KEY_PATTERN: "concrete = InterfaceType(obj)  # Cast based on obj.ClassName",
                KEY_FLEXLIBS2_HELPER: "Use CastingOperations.cast_to_concrete(obj) from flexlibs2"
            }

            if property_name in prop_to_concrete:
                result[KEY_PYTHONNET_CASTING][KEY_AVAILABLE_ON_CONCRETE_TYPES] = prop_to_concrete[property_name].get("available_on", [])

        if context_entity:
            for coll_name, coll_info in poly_collections.items():
                if context_entity == coll_info.get(KEY_BASE_TYPE):
                    result[KEY_POLYMORPHIC_COLLECTION_WARNING] = {
                        "collection": coll_name,
                        KEY_BASE_TYPE: coll_info.get(KEY_BASE_TYPE),
                        KEY_CONCRETE_TYPES: coll_info.get(KEY_CONCRETE_TYPES, []),
                        KEY_UNIQUE_PROPERTIES_BY_TYPE: coll_info.get(KEY_UNIQUE_PROPERTIES_BY_TYPE, {}),
                        KEY_CASTING_HINT: coll_info.get(KEY_CASTING_HINT, ""),
                        KEY_EXAMPLE: f"for item in obj.{coll_name}:\n    concrete = CastingOperations.cast_to_concrete(item)\n    # Now access derived properties"
                    }
                    break

        if property_name in prop_to_concrete and context_entity:
            prop_info = prop_to_concrete[property_name]
            available_types = prop_info.get("available_on", [])
            if context_entity in poly_collections:
                poly_info = poly_collections[context_entity]
                relevant_types = [t for t in available_types if t in poly_info.get(KEY_CONCRETE_TYPES, [])]
                if relevant_types:
                    result[KEY_PROPERTY_AVAILABILITY_IN_CONTEXT] = {
                        KEY_PROPERTY_NAME: property_name,
                        "polymorphic_collection": context_entity,
                        KEY_HAS_PROPERTY_ON: relevant_types,
                        KEY_MISSING_FROM: [t for t in poly_info.get(KEY_CONCRETE_TYPES, []) if t not in relevant_types],
                        KEY_GUIDANCE: f"'{property_name}' is only available on {', '.join(relevant_types)}. Check the concrete type with obj.ClassName == '{relevant_types[0][1:]}' before accessing."
                    }

    result = build_response_with_context(result, include_session=True)

    return json_response(result)


# ============================================================
# resolve_type (#12): single-purpose authoritative lookup for an LCM/wrapper type.
# Cheaper than get_object_api when you only need the canonical import path.
# ============================================================

def _lcm_namespace_to_assembly(namespace: str) -> str:
    """Map an LCM namespace to its DLL. Returns '' for unknown namespaces."""
    if not namespace:
        return ""
    if namespace.startswith("SIL.LCModel.Utils"):
        return "SIL.LCModel.Utils.dll"
    if namespace.startswith("SIL.LCModel.Core"):
        return "SIL.LCModel.Core.dll"
    if namespace.startswith("SIL.LCModel"):
        return "SIL.LCModel.dll"
    return ""


def _infer_lcm_kind(type_name: str) -> str:
    """Heuristic: 'I' + uppercase => interface, else class."""
    if len(type_name) >= 2 and type_name[0] == 'I' and type_name[1].isupper():
        return "interface"
    return "class"


async def handle_resolve_type(args: dict) -> list[TextContent]:
    """Resolve a type name to its canonical namespace and import statement.

    Single-purpose lookup for #12 -- cheaper than get_object_api when you only
    need the import path. Searches liblcm first by default (most common case),
    then flexlibs2 / flexlibs_stable.
    """
    type_name = args["type_name"]
    library_filter = args.get("library", "auto")

    api_index = get_api_index()
    if not api_index:
        return json_response({KEY_ERROR: "API index not loaded"})

    if library_filter == "auto":
        search_order = ["liblcm", "flexlibs2", "flexlibs_stable"]
    else:
        search_order = [library_filter]

    if "liblcm" in search_order:
        api_index.ensure_liblcm_loaded()

    found_in = []
    canonical = None

    for lib in search_order:
        lib_data = getattr(api_index, lib, None)
        if not lib_data:
            continue
        entities = lib_data.get("entities", {})
        if type_name not in entities:
            continue

        found_in.append(lib)
        if canonical is not None:
            continue  # First hit is the canonical answer

        entity = entities[type_name]
        namespace = entity.get("namespace", "") or ""
        kind = entity.get("kind") or _infer_lcm_kind(type_name)
        category = entity.get("category")

        if lib == "liblcm":
            assembly = _lcm_namespace_to_assembly(namespace)
            import_statement = (
                f"from {namespace} import {type_name}" if namespace else ""
            )
        else:
            assembly = None
            import_statement = f"from {lib} import {type_name}"

        canonical = {
            KEY_NAME: type_name,
            "kind": kind,
            "namespace": namespace,
            "assembly": assembly,
            "import_statement": import_statement,
            KEY_CATEGORY: category,
        }

    if canonical is not None:
        return json_response({
            KEY_FOUND: True,
            "found_in": found_in,
            **canonical,
        })

    # Not found - offer substring suggestions to help recover from typos.
    suggestions = []
    type_lower = type_name.lower()
    seen = set()
    for lib in search_order:
        lib_data = getattr(api_index, lib, None)
        if not lib_data:
            continue
        for ent_name in lib_data.get("entities", {}):
            if ent_name in seen or ent_name == type_name:
                continue
            if type_lower in ent_name.lower():
                suggestions.append({KEY_NAME: ent_name, "library": lib})
                seen.add(ent_name)
                if len(suggestions) >= 5:
                    break
        if len(suggestions) >= 5:
            break

    return json_response({
        KEY_FOUND: False,
        "type_name": type_name,
        "suggestions": suggestions,
        KEY_HINT: (
            f"Type '{type_name}' not found in {search_order}. "
            "Try a substring suggestion above, or use flextools_search_by_capability "
            "for natural-language search."
        ),
    })
