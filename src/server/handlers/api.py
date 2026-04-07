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

# Import kernel and config (absolute imports work in all modes)
from server.kernel import api_index, session_state
from response_utils import json_response
from server.response_keys import (
    KEY_OBJECT_TYPE, KEY_FOUND, KEY_METHODS, KEY_ENTITY, KEY_NAME, KEY_TYPE,
    KEY_SOURCE, KEY_SIGNATURE, KEY_DESCRIPTION, KEY_CATEGORY, KEY_SCORE,
    KEY_MATCHES, KEY_FLEXLIBS2, KEY_LIBLCM, KEY_FLEXLIBS2_MATCHES,
    KEY_LIBLCM_MATCHES, KEY_DISAMBIGUATION, KEY_QUERY, KEY_RESULTS_COUNT,
    KEY_EXAMPLES, KEY_MESSAGE, KEY_SUMMARY, KEY_METHODS_COUNT
)

# Type note: api_index is initialized by server.py before any handlers are called
KEY_SOURCES_SEARCHED = "sources_searched"
KEY_FALLBACK_USED = "fallback_used"
KEY_API_MODE = "api_mode"
KEY_API_MODE_DESCRIPTION = "api_mode_description"
KEY_SEARCH_METHOD = "search_method"
KEY_SEMANTIC_AVAILABLE = "semantic_available"
KEY_IMPORT_STATEMENT = "import_statement"
KEY_IMPORT_REQUIRED = "import_required"
KEY_TOTAL_METHODS = "total_methods"
KEY_RETURNED_METHODS = "returned_methods"
KEY_HAS_MORE = "has_more"
KEY_NEXT_OFFSET = "next_offset"
KEY_SOURCE_FILE = "source_file"
KEY_SESSION_CONTEXT = "session_context"
KEY_DETECTED = "detected"
KEY_AUTO_RESOLVED = "auto_resolved"
KEY_SELECTED = "selected"
KEY_CONFIDENCE = "confidence"
KEY_REASONING = "reasoning"
KEY_ALTERNATIVES = "alternatives"
KEY_QUESTION = "question"
KEY_METHOD_NAME = "method_name"
KEY_OPERATION_TYPE = "operation_type"
KEY_PYTHONIC_NAME = "pythonic_name"
KEY_KIND = "kind"
KEY_TARGET_TYPE = "target_type"
KEY_IS_MULTISTRING = "is_multistring"
KEY_EMPTY_VALUE_WARNING = "empty_value_warning"
KEY_PROPERTY_NAME = "property_name"
KEY_CONTEXT_ENTITY = "context_entity"
KEY_LIMIT = "limit"
KEY_OFFSET = "offset"
KEY_INCLUDE_CASTING_INFO = "include_casting_info"
KEY_SUFFIX_GUIDE = "suffix_guide"
KEY_USAGE_EXAMPLES = "usage_examples"
KEY_PYTHONNET_CASTING = "pythonnet_casting"
KEY_REQUIRES_CAST = "requires_cast"
KEY_DEFINED_ON = "defined_on"
KEY_NOT_AVAILABLE_ON = "NOT_available_on"
KEY_WARNING = "warning"
KEY_PATTERN = "pattern"
KEY_FLEXLIBS2_HELPER = "flexlibs2_helper"
KEY_AVAILABLE_ON_CONCRETE_TYPES = "available_on_concrete_types"
KEY_POLYMORPHIC_COLLECTION_WARNING = "polymorphic_collection_warning"
KEY_BASE_TYPE = "base_type"
KEY_CONCRETE_TYPES = "concrete_types"
KEY_UNIQUE_PROPERTIES_BY_TYPE = "unique_properties_by_type"
KEY_CASTING_HINT = "casting_hint"
KEY_EXAMPLE = "example"
KEY_PROPERTY_AVAILABILITY_IN_CONTEXT = "property_availability_in_context"
KEY_HAS_PROPERTY_ON = "has_property_on"
KEY_MISSING_FROM = "missing_from"
KEY_GUIDANCE = "guidance"

# Operation type constants
OP_CREATE = "create"
OP_READ = "read"
OP_UPDATE = "update"
OP_DELETE = "delete"
OP_ITERATE = "iterate"
OP_SEARCH = "search"

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
        "fallback": ["liblcm"],
        "description": "FlexLibs Stable with LibLCM fallback"
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
    """Apply pagination and filtering to an entity's methods."""
    try:
        from ..constants import OPERATIONS_CLASSES
    except ImportError:
        from server.constants import OPERATIONS_CLASSES

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

    return result


def resolve_pythonic_property(name: str, context_entity: str | None = None) -> List[Dict[str, Any]]:
    """Resolve a pythonic (suffix-free) property name to its LibLCM equivalent(s)."""
    if not api_index or not api_index.liblcm:
        return []

    suffix_index = api_index.liblcm.get("suffix_index", {})
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
    """Get API documentation for a specific object type."""
    object_type = args[KEY_OBJECT_TYPE]
    mode = session_state.get_mode()
    default_flexlibs2 = mode in ("flexlibs2", "all")
    default_liblcm = mode in ("liblcm", "flexlibs_stable", "all")
    include_flexlibs2 = args.get("include_flexlibs2", default_flexlibs2)
    include_liblcm = args.get("include_liblcm", default_liblcm)
    summary_only = args.get(KEY_SUMMARY, False)
    method_filter = args.get("method_filter", "")
    limit = args.get(KEY_LIMIT, 50)
    offset = args.get(KEY_OFFSET, 0)

    result = {KEY_OBJECT_TYPE: object_type, KEY_FOUND: False}

    # Search in FlexLibs 2.0
    if include_flexlibs2 and api_index.flexlibs2:
        entities = api_index.flexlibs2.get("entities", {})
        if object_type in entities:
            entity = entities[object_type]
            result[KEY_FLEXLIBS2] = paginate_entity(
                entity, summary_only, method_filter, limit, offset,
                object_type=object_type, library="flexlibs2"
            )
            result[KEY_FOUND] = True
        else:
            max_matches = 10
            for name, entity in entities.items():
                if object_type.lower() in name.lower():
                    if KEY_FLEXLIBS2_MATCHES not in result:
                        result[KEY_FLEXLIBS2_MATCHES] = []
                    result[KEY_FLEXLIBS2_MATCHES].append({
                        KEY_NAME: name,
                        KEY_CATEGORY: entity.get(KEY_CATEGORY),
                        KEY_METHODS_COUNT: len(entity.get(KEY_METHODS, []))
                    })
                    result[KEY_FOUND] = True
                    if len(result[KEY_FLEXLIBS2_MATCHES]) >= max_matches:
                        break

    # Search in LibLCM
    if include_liblcm and api_index.liblcm:
        entities = api_index.liblcm.get("entities", {})
        if object_type in entities:
            result[KEY_LIBLCM] = paginate_entity(
                entities[object_type], summary_only, method_filter, limit, offset,
                object_type=object_type, library="liblcm"
            )
            result[KEY_FOUND] = True
        else:
            max_matches = 10
            for name, entity in entities.items():
                if object_type.lower() in name.lower():
                    if KEY_LIBLCM_MATCHES not in result:
                        result[KEY_LIBLCM_MATCHES] = []
                    result[KEY_LIBLCM_MATCHES].append({
                        KEY_NAME: name,
                        KEY_TYPE: entity.get(KEY_TYPE),
                        KEY_CATEGORY: entity.get(KEY_CATEGORY)
                    })
                    result[KEY_FOUND] = True
                    if len(result[KEY_LIBLCM_MATCHES]) >= max_matches:
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
            """Search a single source and return results."""
            source_results = []
            if not index_data:
                return source_results

            for entity_name, entity in index_data.get("entities", {}).items():
                for method in entity.get(KEY_METHODS, []):
                    method_name = method.get(KEY_NAME, '')
                    name_lower = method_name.lower()
                    score = boost

                    has_name_match = any(term in name_lower for term in expanded_terms)
                    if has_name_match:
                        score += 2

                    if score > boost:
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
                        name_lower = prop_name.lower()
                        pythonic_lower = pythonic_name.lower()
                        score = boost

                        for term in expanded_terms:
                            if term == name_lower or term == pythonic_lower:
                                score += 3
                                break

                        if score == boost:
                            desc_lower = prop.get(KEY_DESCRIPTION, '').lower()
                            kind_lower = prop.get(KEY_KIND, '').lower()
                            for term in expanded_terms:
                                if term in desc_lower or term in kind_lower or term in name_lower or term in pythonic_lower:
                                    score += 1

                        if score > boost:
                            result_item = {
                                KEY_SCORE: score,
                                KEY_SOURCE: source_name,
                                KEY_ENTITY: entity_name,
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

    result = {
        KEY_QUERY: query,
        KEY_API_MODE: api_mode,
        KEY_API_MODE_DESCRIPTION: config["description"],
        KEY_SEARCH_METHOD: search_method,
        KEY_SOURCES_SEARCHED: sources_searched,
        KEY_FALLBACK_USED: fallback_used,
        KEY_SEMANTIC_AVAILABLE: api_index.semantic_search.enabled if api_index.semantic_search else False,
        KEY_RESULTS_COUNT: len(results),
        "results": results
    }

    result = build_response_with_context(result, include_session=True)

    return json_response(result)


async def handle_find_examples(args: dict) -> list[TextContent]:
    """Find code examples for methods or operations."""
    method_name = args.get(KEY_METHOD_NAME)
    operation_type = args.get(KEY_OPERATION_TYPE)
    object_type = args.get(KEY_OBJECT_TYPE)
    max_results = args.get("max_results", 5)

    examples = []

    if api_index.flexlibs2:
        for entity_name, entity in api_index.flexlibs2.get("entities", {}).items():
            if object_type and object_type.lower() not in entity_name.lower():
                continue

            for method in entity.get(KEY_METHODS, []):
                method_name_str = method.get(KEY_NAME, "")
                if method_name and method_name.lower() not in method_name_str.lower():
                    continue

                if operation_type:
                    name_lower = method_name_str.lower()
                    if not _matches_operation(name_lower, operation_type):
                        continue

                if method.get(KEY_EXAMPLE):
                    examples.append({
                        "class": entity_name,
                        KEY_METHOD_NAME: method_name_str,
                        KEY_SIGNATURE: method.get(KEY_SIGNATURE),
                        KEY_DESCRIPTION: method.get(KEY_SUMMARY, method.get(KEY_DESCRIPTION, ""))[:150],
                        KEY_EXAMPLE: method.get(KEY_EXAMPLE)
                    })

                    if len(examples) >= max_results:
                        break

            if len(examples) >= max_results:
                break

    return json_response({
        KEY_QUERY: {
            KEY_METHOD_NAME: method_name,
            KEY_OPERATION_TYPE: operation_type,
            KEY_OBJECT_TYPE: object_type
        },
        KEY_RESULTS_COUNT: len(examples),
        KEY_EXAMPLES: examples
    })


async def handle_resolve_property(args: dict) -> list[TextContent]:
    """Resolve pythonic property names to LibLCM equivalents with casting info."""
    property_name = args[KEY_PROPERTY_NAME]
    context_entity = args.get(KEY_CONTEXT_ENTITY)
    include_casting_info = args.get(KEY_INCLUDE_CASTING_INFO, True)

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

        if include_casting_info and api_index.casting_index:
            casting_props = api_index.casting_index.get("properties", {})
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

    if include_casting_info and api_index.casting_index:
        casting_props = api_index.casting_index.get("properties", {})
        poly_collections = api_index.casting_index.get("polymorphic_collections", {})
        prop_to_concrete = api_index.casting_index.get("property_to_concrete_mapping", {})

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
