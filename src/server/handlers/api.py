"""
API Discovery Handler Module

Provides read-only API discovery tools:
- get_object_api: Get API documentation for specific object types
- search_by_capability: Search for methods by natural language capability
- find_examples: Find code examples for methods
- resolve_property: Resolve pythonic property names to LibLCM equivalents
"""

import json
from mcp.types import TextContent
from typing import List, Dict, Any

# Import kernel and config with dual-mode support
try:
    from ..kernel import api_index, session_state
except ImportError:
    from src.server.kernel import api_index, session_state


# ============================================================
# Helper Functions
# ============================================================

def rank_object_matches(partial_name: str, matches: list, api_mode: str) -> dict:
    """Rank partial object type matches by relevance and confidence."""

    if not matches:
        return {"matches": [], "auto_resolved": False}

    for match in matches:
        score = 0
        reasons = []

        # Exact match gets highest score
        if match.get("name", "").lower() == partial_name.lower():
            score = 100
            reasons.append("Exact match")

        # Source preference matches session mode
        if match.get("source") == api_mode:
            score += 30
            reasons.append(f"Matches session API mode ({api_mode})")

        # Operations classes preferred for FlexLibs2
        if "Operations" in match.get("name", "") and api_mode == "flexlibs2":
            score += 20
            reasons.append("Operations class (FlexLibs2 pattern)")

        # Lexicon domain is most common
        if match.get("category") == "lexicon":
            score += 10
            reasons.append("Lexicon is most common domain")

        # Substring position matters (earlier = better)
        pos = match.get("name", "").lower().find(partial_name.lower())
        if pos == 0:  # Starts with search term
            score += 15
            reasons.append("Name starts with search term")

        match["score"] = score
        match["reasoning"] = "; ".join(reasons) if reasons else "Default ranking"
        match["confidence"] = "high" if score >= 60 else "medium" if score >= 30 else "low"

    matches.sort(key=lambda x: x.get("score", 0), reverse=True)

    if not matches:
        return {"matches": [], "auto_resolved": False}

    top = matches[0]
    # Auto-resolve if clear winner (30+ point gap)
    auto_resolve = len(matches) == 1 or (top.get("score", 0) - matches[1].get("score", 0) >= 30)

    return {
        "auto_resolved": auto_resolve,
        "selected": top.get("name") if auto_resolve else None,
        "confidence": top.get("confidence"),
        "reasoning": top.get("reasoning"),
        "all_matches": matches[:5],  # Top 5 matches
        "needs_clarification": not auto_resolve
    }


def build_response_with_context(data: dict, include_session: bool = True) -> dict:
    """Add session context to tool response."""

    if include_session and session_state.initialized:
        data["session_context"] = {
            "api_mode": session_state.api_mode,
            "write_enabled": session_state.write_enabled,
            "project": session_state.project_name or "(not set)"
        }

    return data


def paginate_entity(entity: dict, summary_only: bool, method_filter: str, limit: int, offset: int, object_type: str = "", library: str = "flexlibs2") -> dict:
    """Apply pagination and filtering to an entity's methods.

    Args:
        entity: The entity dict from API index
        summary_only: If True, only return method signatures
        method_filter: Filter methods by name pattern
        limit: Max methods to return
        offset: Starting offset for pagination
        object_type: The class/object name (used to generate import statement)
        library: Library name (flexlibs2 or flexlibs)
    """
    result = {
        "category": entity.get("category"),
        "summary": entity.get("summary", ""),
        "source_file": entity.get("source_file", ""),
    }

    # Add import statement for Operations classes
    OPERATIONS_CLASSES = {
        "POSOperations", "PhonemeOperations", "NaturalClassOperations",
        "EnvironmentOperations", "MorphRuleOperations", "InflectionFeatureOperations",
        "GramCatOperations", "PhonologicalRuleOperations",
        "LexEntryOperations", "LexSenseOperations", "ExampleOperations",
        "LexReferenceOperations", "VariantOperations", "PronunciationOperations",
        "SemanticDomainOperations", "ReversalOperations", "EtymologyOperations",
        "AllomorphOperations",
        "TextOperations", "WordformOperations", "WfiAnalysisOperations",
        "ParagraphOperations", "SegmentOperations", "WfiGlossOperations",
        "WfiMorphBundleOperations", "MediaOperations", "FilterOperations",
        "DiscourseOperations",
        "NoteOperations", "PersonOperations", "LocationOperations",
        "AnthropologyOperations", "DataNotebookOperations",
        "PublicationOperations", "AgentOperations", "ConfidenceOperations",
        "OverlayOperations", "TranslationTypeOperations", "PossibilityListOperations",
        "WritingSystemOperations", "ProjectSettingsOperations",
        "AnnotationDefOperations", "CheckOperations", "CustomFieldOperations",
    }

    if object_type in OPERATIONS_CLASSES:
        result["import_statement"] = f"from {library} import {object_type}"
        result["import_required"] = True

    methods = entity.get("methods", [])

    # Apply method filter
    if method_filter:
        filter_lower = method_filter.lower()
        methods = [m for m in methods if filter_lower in m.get("name", "").lower()]

    total_methods = len(methods)
    result["total_methods"] = total_methods

    # Apply pagination
    methods = methods[offset:offset + limit]

    if summary_only:
        # Return just names and signatures
        result["methods"] = [
            {"name": m.get("name"), "signature": m.get("signature", "")}
            for m in methods
        ]
    else:
        result["methods"] = methods

    result["returned_methods"] = len(result["methods"])
    result["has_more"] = (offset + limit) < total_methods
    if result["has_more"]:
        result["next_offset"] = offset + limit

    return result


def normalize_object_name(name: str) -> str:
    """Normalize object name to interface format (ILexEntry)."""
    name = name.replace("Operations", "")
    if not name.startswith("I"):
        name = f"I{name}"
    return name


def resolve_pythonic_property(name: str, context_entity: str = None) -> List[Dict]:
    """
    Resolve a pythonic (suffix-free) property name to its LibLCM equivalent(s).

    Args:
        name: Property name (e.g., 'Senses' or 'SensesOS')
        context_entity: Optional entity context (e.g., 'ILexEntry')

    Returns:
        List of matching properties with their full names and kinds
    """
    if not api_index or not api_index.liblcm:
        return []

    suffix_index = api_index.liblcm.get("suffix_index", {})
    if not suffix_index:
        return []

    results = []

    # Check if it's a pythonic name (suffix-free)
    by_pythonic = suffix_index.get("by_pythonic_name", {})
    if name in by_pythonic:
        matches = by_pythonic[name]
        if context_entity:
            # Filter to matching entity
            results = [m for m in matches if m["entity"] == context_entity]
        else:
            results = matches

    # Check if it's a full name (with suffix)
    if not results:
        by_full = suffix_index.get("by_full_name", {})
        if context_entity:
            key = f"{context_entity}.{name}"
            if key in by_full:
                match = by_full[key]
                results = [{
                    "entity": match["entity"],
                    "full_name": name,
                    "pythonic_name": match["pythonic_name"],
                    "kind": match["kind"]
                }]
        else:
            # Search all entities for this full name
            for key, match in by_full.items():
                if key.endswith(f".{name}"):
                    results.append({
                        "entity": match["entity"],
                        "full_name": name,
                        "pythonic_name": match["pythonic_name"],
                        "kind": match["kind"]
                    })

    return results


# ============================================================
# Handler Functions
# ============================================================

async def handle_get_object_api(args: dict) -> list[TextContent]:
    """Get API documentation for a specific object type."""
    object_type = args["object_type"]
    # Default include flags based on session mode (user can override)
    mode = session_state.get_mode()
    default_flexlibs2 = mode in ("flexlibs2", "all")
    default_liblcm = mode in ("liblcm", "flexlibs_stable", "all")
    include_flexlibs2 = args.get("include_flexlibs2", default_flexlibs2)
    include_liblcm = args.get("include_liblcm", default_liblcm)
    summary_only = args.get("summary_only", False)
    method_filter = args.get("method_filter", "")
    limit = args.get("limit", 50)
    offset = args.get("offset", 0)

    result = {"object_type": object_type, "found": False}

    # Search in FlexLibs 2.0
    if include_flexlibs2 and api_index.flexlibs2:
        entities = api_index.flexlibs2.get("entities", {})
        # Try exact match first
        if object_type in entities:
            entity = entities[object_type]
            result["flexlibs2"] = paginate_entity(
                entity, summary_only, method_filter, limit, offset,
                object_type=object_type, library="flexlibs2"
            )
            result["found"] = True
        else:
            # Try partial match (e.g., "LexEntry" matches "LexEntryOperations")
            for name, entity in entities.items():
                if object_type.lower() in name.lower():
                    if "flexlibs2_matches" not in result:
                        result["flexlibs2_matches"] = []
                    result["flexlibs2_matches"].append({
                        "name": name,
                        "category": entity.get("category"),
                        "methods_count": len(entity.get("methods", []))
                    })
                    result["found"] = True

    # Search in LibLCM
    if include_liblcm and api_index.liblcm:
        entities = api_index.liblcm.get("entities", {})
        if object_type in entities:
            result["liblcm"] = paginate_entity(
                entities[object_type], summary_only, method_filter, limit, offset,
                object_type=object_type, library="liblcm"
            )
            result["found"] = True
        else:
            # Try partial match
            for name, entity in entities.items():
                if object_type.lower() in name.lower():
                    if "liblcm_matches" not in result:
                        result["liblcm_matches"] = []
                    result["liblcm_matches"].append({
                        "name": name,
                        "type": entity.get("type"),
                        "category": entity.get("category")
                    })
                    if len(result.get("liblcm_matches", [])) >= 10:
                        break
                    result["found"] = True

    if not result["found"]:
        result["message"] = f"No API documentation found for '{object_type}'. Try searching with search_by_capability or list_categories to explore available APIs."
    else:
        # Add disambiguation ranking to partial matches
        if "flexlibs2_matches" in result:
            matches_with_source = [
                {**m, "source": "flexlibs2"} for m in result["flexlibs2_matches"]
            ]
            ranked = rank_object_matches(object_type, matches_with_source, mode)
            if ranked.get("auto_resolved"):
                result["disambiguation"] = {
                    "detected": True,
                    "auto_resolved": True,
                    "selected": ranked["selected"],
                    "confidence": ranked["confidence"],
                    "reasoning": ranked["reasoning"]
                }
            elif ranked.get("needs_clarification"):
                result["disambiguation"] = {
                    "detected": True,
                    "auto_resolved": False,
                    "alternatives": ranked.get("all_matches", []),
                    "question": "Multiple matches found. Which did you mean?"
                }
            # Update matches with ranking info
            for match, ranked_match in zip(result["flexlibs2_matches"], ranked.get("all_matches", [])):
                match["score"] = ranked_match.get("score")
                match["confidence"] = ranked_match.get("confidence")
                match["reasoning"] = ranked_match.get("reasoning")

        if "liblcm_matches" in result:
            matches_with_source = [
                {**m, "source": "liblcm"} for m in result["liblcm_matches"]
            ]
            ranked = rank_object_matches(object_type, matches_with_source, mode)
            if ranked.get("auto_resolved"):
                if "disambiguation" not in result:  # Don't override flexlibs2 result
                    result["disambiguation"] = {
                        "detected": True,
                        "auto_resolved": True,
                        "selected": ranked["selected"],
                        "confidence": ranked["confidence"],
                        "reasoning": ranked["reasoning"]
                    }
            # Update matches with ranking info
            for match, ranked_match in zip(result["liblcm_matches"], ranked.get("all_matches", [])):
                match["score"] = ranked_match.get("score")
                match["confidence"] = ranked_match.get("confidence")
                match["reasoning"] = ranked_match.get("reasoning")

        # Record discovered APIs for validation in run_operation
        if "flexlibs2" in result:
            entity_name = result["flexlibs2"].get("name", object_type)
            for method in result["flexlibs2"].get("methods", []):
                method_name = method.get("name", "")
                if method_name:
                    session_state.record_discovered_api(entity_name, method_name)
        if "liblcm" in result:
            entity_name = result["liblcm"].get("name", object_type)
            for prop in result["liblcm"].get("properties", []):
                prop_name = prop.get("name", "")
                if prop_name:
                    session_state.record_discovered_api(entity_name, prop_name)
            for method in result["liblcm"].get("methods", []):
                method_name = method.get("name", "")
                if method_name:
                    session_state.record_discovered_api(entity_name, method_name)

        # Add session context to response
        result = build_response_with_context(result, include_session=True)

    # Record this API as validated (can now be used in run_operation/run_module)
    if result.get("found"):
        session_state.record_validated_api(object_type)

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def handle_search_by_capability(args: dict) -> list[TextContent]:
    """Search for methods by capability description with API mode support."""
    query = args["query"]
    max_results = args.get("max_results", 10)
    # Use session mode if not explicitly specified
    api_mode = args.get("api_mode", session_state.get_mode())
    use_semantic = args.get("semantic", True)

    # Domain-specific synonyms: map linguistics terms to API terms
    domain_synonyms = {
        # Parts of speech -> API terms
        "noun": "part of speech POS grammatical category",
        "verb": "part of speech POS grammatical category",
        "adjective": "part of speech POS grammatical category",
        "adverb": "part of speech POS grammatical category",
        "pronoun": "part of speech POS grammatical category",
        "preposition": "part of speech POS grammatical category",
        # Common linguistics terms
        "pos": "part of speech grammatical category",
        "category": "grammatical category part of speech",
        "lemma": "headword citation form lexeme entry",
        "morpheme": "morph allomorph form",
        "affix": "prefix suffix infix circumfix",
        "stem": "root base form",
        "inflection": "inflectional paradigm conjugation declension",
        "derivation": "derivational affix",
        # Data terms
        "translation": "gloss definition meaning",
        "meaning": "gloss definition sense",
        "example": "sentence illustration",
        "pronunciation": "phonetic phonology",
        "etymology": "origin history borrowed",
        "domain": "semantic domain category field",
        "usage": "register style sociolinguistic",
    }

    # Expand query with domain synonyms
    query_lower = query.lower()
    expanded_query = query
    for term, expansion in domain_synonyms.items():
        if term in query_lower:
            expanded_query = f"{query} {expansion}"
            break  # Apply first match only to avoid over-expansion

    results = []
    search_method = "keyword"
    sources_searched = []
    fallback_used = False

    # Define which sources to search based on api_mode
    mode_config = {
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

    config = mode_config.get(api_mode, mode_config["all"])

    # Try semantic search first if available
    if use_semantic and api_index.semantic_search and api_index.semantic_search.enabled:
        semantic_source = api_mode if api_mode in ["flexlibs2", "liblcm"] else "all"
        semantic_results = api_index.semantic_search.search(expanded_query, max_results, semantic_source)
        if semantic_results:
            results = semantic_results
            search_method = "semantic"
            sources_searched = [api_mode]

    # Fall back to keyword search
    if not results:
        query_lower = query.lower()

        synonyms = {
            # Operations
            "add": ["add", "set", "create", "insert", "append"],
            "set": ["set", "add", "update", "modify", "assign"],
            "get": ["get", "fetch", "retrieve", "find", "read"],
            "delete": ["delete", "remove", "clear", "erase"],
            "remove": ["remove", "delete", "clear"],
            "create": ["create", "add", "new", "make"],
            "update": ["update", "set", "modify", "change"],
            "find": ["find", "search", "get", "lookup", "query"],
            "list": ["list", "getall", "all", "iterate", "enumerate"],
            # Lexicon terms
            "gloss": ["gloss", "translation", "meaning"],
            "definition": ["definition", "meaning", "description"],
            "sense": ["sense", "meaning", "definition"],
            "entry": ["entry", "headword", "lexeme", "word"],
            # Parts of speech
            "noun": ["noun", "pos", "partofspeech", "grammatical", "category"],
            "verb": ["verb", "pos", "partofspeech", "grammatical", "category"],
            "adjective": ["adjective", "pos", "partofspeech", "grammatical", "category"],
            "adverb": ["adverb", "pos", "partofspeech", "grammatical", "category"],
            "pos": ["pos", "partofspeech", "grammatical", "category", "speech"],
            # Other linguistics terms
            "lemma": ["lemma", "headword", "citation", "lexeme"],
            "morpheme": ["morpheme", "morph", "allomorph", "form"],
            "stem": ["stem", "root", "base"],
            "affix": ["affix", "prefix", "suffix", "infix"],
        }

        # Expand query terms with synonyms
        query_terms = query_lower.split()
        expanded_terms = set(query_terms)
        for term in query_terms:
            if term in synonyms:
                expanded_terms.update(synonyms[term])

        # Expand pythonic names to suffixed equivalents
        suffix_index = api_index.liblcm.get("suffix_index", {}) if api_index.liblcm else {}
        by_pythonic = suffix_index.get("by_pythonic_name", {})
        pythonic_expansions = set()
        for term in list(expanded_terms):
            for pythonic_name, matches in by_pythonic.items():
                if pythonic_name.lower() == term:
                    for match in matches:
                        pythonic_expansions.add(match["full_name"].lower())
        expanded_terms.update(pythonic_expansions)

        def search_source(source_name, index_data, boost=0):
            """Search a single source and return results."""
            source_results = []
            if not index_data:
                return source_results

            for entity_name, entity in index_data.get("entities", {}).items():
                # Search methods
                for method in entity.get("methods", []):
                    score = boost
                    text_to_search = "{} {} {}".format(
                        method.get('name', ''),
                        method.get('description', ''),
                        method.get('summary', '')
                    ).lower()

                    for term in expanded_terms:
                        if term in text_to_search:
                            score += 1
                        if term in method.get('name', '').lower():
                            score += 2

                    if score > boost:
                        source_results.append({
                            "score": score,
                            "source": source_name,
                            "entity": entity_name,
                            "name": method.get("name"),
                            "type": "method",
                            "signature": method.get("signature"),
                            "description": method.get("summary", method.get("description", ""))[:150],
                            "category": entity.get("category", "general"),
                        })

                # Search properties (LibLCM only)
                if source_name == "liblcm":
                    for prop in entity.get("properties", []):
                        score = boost
                        prop_name = prop.get('name', '')
                        pythonic_name = prop.get('pythonic_name', prop_name)
                        text_to_search = "{} {} {} {}".format(
                            prop_name,
                            pythonic_name,
                            prop.get('description', ''),
                            prop.get('kind', '')
                        ).lower()

                        for term in expanded_terms:
                            if term in text_to_search:
                                score += 1
                            if term == prop_name.lower() or term == pythonic_name.lower():
                                score += 3

                        if score > boost:
                            result_item = {
                                "score": score,
                                "source": source_name,
                                "entity": entity_name,
                                "name": prop_name,
                                "pythonic_name": pythonic_name if pythonic_name != prop_name else None,
                                "type": "property",
                                "kind": prop.get("kind"),
                                "target_type": prop.get("target_type"),
                                "description": prop.get("description", "")[:150],
                                "category": entity.get("category", "general"),
                            }
                            if prop.get("is_multistring"):
                                result_item["is_multistring"] = True
                                result_item["empty_value_warning"] = "Returns '***' when empty - use flexlibs2 wrapper or normalize_text()"
                            source_results.append(result_item)
            return source_results

        # Search primary sources with boost
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

        # If not enough results, try fallback sources
        if len(results) < max_results and config["fallback"]:
            for source in config["fallback"]:
                if source == "liblcm" and api_index.liblcm and "liblcm" not in sources_searched:
                    fallback_results = search_source("liblcm", api_index.liblcm, boost=0)
                    results.extend(fallback_results)
                    if fallback_results:
                        sources_searched.append("liblcm (fallback)")
                        fallback_used = True

        # Sort by score and limit results
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:max_results]

    # Record discovered APIs for validation
    for r in results:
        entity = r.get("entity", "")
        method = r.get("name", "")
        if entity and method:
            session_state.record_discovered_api(entity, method)

    result = {
        "query": query,
        "api_mode": api_mode,
        "api_mode_description": config["description"],
        "search_method": search_method,
        "sources_searched": sources_searched,
        "fallback_used": fallback_used,
        "semantic_available": api_index.semantic_search.enabled if api_index.semantic_search else False,
        "results_count": len(results),
        "results": results
    }

    # Add session context
    result = build_response_with_context(result, include_session=True)

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_find_examples(args: dict) -> list[TextContent]:
    """Find code examples for methods or operations."""
    method_name = args.get("method_name")
    operation_type = args.get("operation_type")
    object_type = args.get("object_type")
    max_results = args.get("max_results", 5)

    examples = []

    # Search FlexLibs 2.0 for examples (it has 82% example coverage)
    if api_index.flexlibs2:
        for entity_name, entity in api_index.flexlibs2.get("entities", {}).items():
            # Filter by object type if specified
            if object_type and object_type.lower() not in entity_name.lower():
                continue

            for method in entity.get("methods", []):
                # Filter by method name if specified
                if method_name and method_name.lower() not in method.get("name", "").lower():
                    continue

                # Filter by operation type if specified
                if operation_type:
                    name_lower = method.get("name", "").lower()
                    matches_op = False
                    if operation_type == "create" and any(x in name_lower for x in ["create", "add", "new"]):
                        matches_op = True
                    elif operation_type == "read" and any(x in name_lower for x in ["get", "find", "fetch"]):
                        matches_op = True
                    elif operation_type == "update" and any(x in name_lower for x in ["set", "update", "modify"]):
                        matches_op = True
                    elif operation_type == "delete" and any(x in name_lower for x in ["delete", "remove"]):
                        matches_op = True
                    elif operation_type == "iterate" and any(x in name_lower for x in ["getall", "list", "iterate"]):
                        matches_op = True
                    elif operation_type == "search" and any(x in name_lower for x in ["find", "search", "query"]):
                        matches_op = True

                    if not matches_op:
                        continue

                # Check if method has an example
                if method.get("example"):
                    examples.append({
                        "class": entity_name,
                        "method": method.get("name"),
                        "signature": method.get("signature"),
                        "description": method.get("summary", method.get("description", ""))[:150],
                        "example": method.get("example")
                    })

                    if len(examples) >= max_results:
                        break

            if len(examples) >= max_results:
                break

    return [TextContent(type="text", text=json.dumps({
        "query": {
            "method_name": method_name,
            "operation_type": operation_type,
            "object_type": object_type
        },
        "results_count": len(examples),
        "examples": examples
    }, indent=2))]


async def handle_resolve_property(args: dict) -> list[TextContent]:
    """Resolve pythonic property names to LibLCM equivalents with casting info."""
    property_name = args["property_name"]
    context_entity = args.get("context_entity")
    include_casting_info = args.get("include_casting_info", True)

    # Use the helper function
    matches = resolve_pythonic_property(property_name, context_entity)

    if not matches:
        # Try to provide helpful suggestions
        result = {
            "property_name": property_name,
            "context_entity": context_entity,
            "found": False,
            "message": f"No property '{property_name}' found",
            "suggestions": []
        }

        # Check if this might be a typo
        suffix_index = api_index.liblcm.get("suffix_index", {}) if api_index.liblcm else {}
        by_pythonic = suffix_index.get("by_pythonic_name", {})

        # Find similar pythonic names
        property_lower = property_name.lower()
        for pythonic_name in by_pythonic.keys():
            if property_lower in pythonic_name.lower() or pythonic_name.lower() in property_lower:
                result["suggestions"].append(pythonic_name)
            elif abs(len(property_name) - len(pythonic_name)) <= 2:
                # Check edit distance for close matches
                if sum(a != b for a, b in zip(property_lower, pythonic_name.lower())) <= 2:
                    result["suggestions"].append(pythonic_name)

        result["suggestions"] = list(set(result["suggestions"]))[:10]

        # Check casting index even if no suffix match found
        if include_casting_info and api_index.casting_index:
            casting_props = api_index.casting_index.get("properties", {})
            if property_name in casting_props:
                result["found"] = True
                result["message"] = f"Property '{property_name}' found in casting index"
                result["casting_info"] = casting_props[property_name]
    else:
        result = {
            "property_name": property_name,
            "context_entity": context_entity,
            "found": True,
            "matches": matches,
            "suffix_guide": {
                "OA": "Owning Atomic - single owned child object",
                "OS": "Owning Sequence - ordered collection of owned objects",
                "OC": "Owning Collection - unordered collection of owned objects",
                "RA": "Reference Atomic - single referenced object",
                "RS": "Reference Sequence - ordered collection of references",
                "RC": "Reference Collection - unordered collection of references"
            }
        }

        # Add usage examples if we found matches
        if matches:
            result["usage_examples"] = []
            for match in matches[:3]:  # Limit to first 3
                entity = match.get("entity", "")
                full_name = match.get("full_name", property_name)
                kind = match.get("kind", "property")

                if kind in ("OS", "OC", "RS", "RC"):
                    result["usage_examples"].append(
                        f"for item in obj.{full_name}:  # Iterate {kind} collection"
                    )
                elif kind in ("OA", "RA"):
                    result["usage_examples"].append(
                        f"ref = obj.{full_name}  # Get single {kind} reference"
                    )

    # Add pythonnet casting information if available
    if include_casting_info and api_index.casting_index:
        casting_props = api_index.casting_index.get("properties", {})
        poly_collections = api_index.casting_index.get("polymorphic_collections", {})
        prop_to_concrete = api_index.casting_index.get("property_to_concrete_mapping", {})

        # Check if property requires casting
        if property_name in casting_props:
            casting_info = casting_props[property_name]
            result["pythonnet_casting"] = {
                "requires_cast": True,
                "defined_on": casting_info.get("defined_on", []),
                "NOT_available_on": casting_info.get("requires_cast_from", []),
                "warning": f"Property '{property_name}' is NOT available on base interfaces: {', '.join(casting_info.get('requires_cast_from', []))}. You must cast to a concrete interface first.",
                "pattern": "concrete = InterfaceType(obj)  # Cast based on obj.ClassName",
                "flexlibs2_helper": "Use CastingOperations.cast_to_concrete(obj) from flexlibs2"
            }

            # Add concrete type information from property mapping
            if property_name in prop_to_concrete:
                result["pythonnet_casting"]["available_on_concrete_types"] = prop_to_concrete[property_name].get("available_on", [])

        # Check if context_entity is a polymorphic collection
        if context_entity:
            for coll_name, coll_info in poly_collections.items():
                if context_entity == coll_info.get("base_type"):
                    result["polymorphic_collection_warning"] = {
                        "collection": coll_name,
                        "base_type": coll_info.get("base_type"),
                        "concrete_types": coll_info.get("concrete_types", []),
                        "unique_properties_by_type": coll_info.get("unique_properties_by_type", {}),
                        "casting_hint": coll_info.get("casting_hint", ""),
                        "example": f"for item in obj.{coll_name}:\n    concrete = CastingOperations.cast_to_concrete(item)\n    # Now access derived properties"
                    }
                    break

        # If property is in the polymorphic collection, show which concrete types have it
        if property_name in prop_to_concrete and context_entity:
            prop_info = prop_to_concrete[property_name]
            available_types = prop_info.get("available_on", [])
            # Filter to just the types relevant to the context polymorphic collection
            if context_entity in poly_collections:
                poly_info = poly_collections[context_entity]
                relevant_types = [t for t in available_types if t in poly_info.get("concrete_types", [])]
                if relevant_types:
                    result["property_availability_in_context"] = {
                        "property": property_name,
                        "polymorphic_collection": context_entity,
                        "has_property_on": relevant_types,
                        "missing_from": [t for t in poly_info.get("concrete_types", []) if t not in relevant_types],
                        "guidance": f"'{property_name}' is only available on {', '.join(relevant_types)}. Check the concrete type with obj.ClassName == '{relevant_types[0][1:]}' before accessing."
                    }

    # Add session context
    result = build_response_with_context(result, include_session=True)

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
