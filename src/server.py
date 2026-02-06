#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlexTools MCP Server

An MCP server that provides AI assistants with searchable documentation
of the LibLCM and FlexLibs APIs for generating FlexTools scripts.
"""

import json
import asyncio
import sys
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Any, Optional, List, Dict
from dataclasses import dataclass, field

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
)

# Optional imports for semantic search
try:
    import numpy as np
    import faiss
    from sentence_transformers import SentenceTransformer
    SEMANTIC_SEARCH_AVAILABLE = True
except ImportError:
    SEMANTIC_SEARCH_AVAILABLE = False


@dataclass
class SemanticSearch:
    """Handles semantic search using sentence-transformers and FAISS."""
    model: Any = None
    index: Any = None
    items: List[Dict] = field(default_factory=list)
    enabled: bool = False

    @classmethod
    def load(cls, index_dir: Path) -> "SemanticSearch":
        """Load semantic search index from disk."""
        search = cls()

        if not SEMANTIC_SEARCH_AVAILABLE:
            return search

        embeddings_dir = index_dir / "embeddings"
        embeddings_path = embeddings_dir / "embeddings.npy"
        metadata_path = embeddings_dir / "metadata.json"
        faiss_path = embeddings_dir / "faiss.index"

        if not all(p.exists() for p in [embeddings_path, metadata_path, faiss_path]):
            return search

        try:
            # Load metadata
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            search.items = metadata.get("items", [])

            # Load FAISS index
            search.index = faiss.read_index(str(faiss_path))

            # Load model (lazy - only when needed)
            model_name = metadata.get("_model", "all-MiniLM-L6-v2")
            search.model = SentenceTransformer(model_name)

            search.enabled = True
        except Exception as e:
            print(f"[WARN] Failed to load semantic search: {e}")

        return search

    def search(self, query: str, max_results: int = 10, source_filter: str = "all") -> List[Dict]:
        """Perform semantic search on the query."""
        if not self.enabled or not self.model or not self.index:
            return []

        # Encode query
        query_embedding = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_embedding)

        # Search
        k = min(max_results * 3, len(self.items))  # Get more results for filtering
        scores, indices = self.index.search(query_embedding, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.items):
                continue

            item = self.items[idx]

            # Filter by source
            if source_filter != "all" and item.get("source") != source_filter:
                continue

            results.append({
                "score": float(score),
                "source": item.get("source"),
                "entity": item.get("entity"),
                "name": item.get("name"),
                "type": item.get("type"),
                "description": item.get("description", "")[:150],
                "category": item.get("category"),
                "signature": item.get("signature", ""),
            })

            if len(results) >= max_results:
                break

        return results


@dataclass
class APIIndex:
    """Holds the loaded API documentation indexes."""
    liblcm: dict = None
    flexlibs2: dict = None
    flexlibs_stable: dict = None
    navigation_graph: dict = None
    semantic_search: SemanticSearch = None

    @classmethod
    def load(cls, index_dir: Path) -> "APIIndex":
        """Load all API indexes from the index directory."""
        index = cls()

        # Load LibLCM
        liblcm_path = index_dir / "liblcm" / "flex-api-enhanced.json"
        if liblcm_path.exists():
            with open(liblcm_path, "r", encoding="utf-8") as f:
                index.liblcm = json.load(f)

        # Load FlexLibs 2.0
        flexlibs2_path = index_dir / "flexlibs" / "flexlibs2_api.json"
        if flexlibs2_path.exists():
            with open(flexlibs2_path, "r", encoding="utf-8") as f:
                index.flexlibs2 = json.load(f)

        # Load FlexLibs Stable
        flexlibs_stable_path = index_dir / "flexlibs" / "flexlibs_api.json"
        if flexlibs_stable_path.exists():
            with open(flexlibs_stable_path, "r", encoding="utf-8") as f:
                index.flexlibs_stable = json.load(f)

        # Load navigation graph
        nav_graph_path = index_dir / "navigation_graph.json"
        if nav_graph_path.exists():
            with open(nav_graph_path, "r", encoding="utf-8") as f:
                index.navigation_graph = json.load(f)

        # Load semantic search (optional)
        index.semantic_search = SemanticSearch.load(index_dir)

        return index


# Initialize the MCP server
server = Server("flextools-mcp")

# Global index (loaded on startup)
api_index: Optional[APIIndex] = None


def get_index_dir() -> Path:
    """Get the index directory path."""
    return Path(__file__).parent.parent / "index"


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="get_object_api",
            description="Get methods and properties for a FlexTools/LibLCM object like ILexEntry, LexSenseOperations, etc. Use summary_only=true first to see available methods, then request specific methods by name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_type": {
                        "type": "string",
                        "description": "The object type to look up (e.g., 'ILexEntry', 'LexEntryOperations', 'ILexSense')"
                    },
                    "include_flexlibs2": {
                        "type": "boolean",
                        "description": "Include FlexLibs 2.0 wrapper methods (default: true)",
                        "default": True
                    },
                    "include_liblcm": {
                        "type": "boolean",
                        "description": "Include raw LibLCM interface info (default: true)",
                        "default": True
                    },
                    "summary_only": {
                        "type": "boolean",
                        "description": "Return only method/property names without full details (default: false). Use this first to explore large objects.",
                        "default": False
                    },
                    "method_filter": {
                        "type": "string",
                        "description": "Filter to methods containing this substring (case-insensitive)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of methods to return (default: 50)",
                        "default": 50
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Number of methods to skip for pagination (default: 0)",
                        "default": 0
                    }
                },
                "required": ["object_type"]
            }
        ),
        Tool(
            name="search_by_capability",
            description="Search for methods/functions by what they do. Use natural language queries like 'add gloss to sense', 'create new entry', 'get all entries'. Supports different API modes with fallback behavior.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language description of what you want to do"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)",
                        "default": 10
                    },
                    "api_mode": {
                        "type": "string",
                        "enum": ["flexlibs2", "flexlibs_stable", "liblcm", "all"],
                        "description": "API mode: 'flexlibs2' (recommended, searches FlexLibs 2.0 primarily), 'flexlibs_stable' (searches stable API with LibLCM fallback), 'liblcm' (raw C# API only), 'all' (search everything). Default: 'all'",
                        "default": "all"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_navigation_path",
            description="Find how to navigate from one object type to another in the FieldWorks data model. For example, how to get from ILexEntry to ILexExampleSentence.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_object": {
                        "type": "string",
                        "description": "Starting object type (e.g., 'ILexEntry')"
                    },
                    "to_object": {
                        "type": "string",
                        "description": "Target object type (e.g., 'ILexExampleSentence')"
                    }
                },
                "required": ["from_object", "to_object"]
            }
        ),
        Tool(
            name="find_examples",
            description="Find code examples for a specific method or operation type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "method_name": {
                        "type": "string",
                        "description": "Specific method name to find examples for"
                    },
                    "operation_type": {
                        "type": "string",
                        "enum": ["create", "read", "update", "delete", "iterate", "search"],
                        "description": "Type of operation to find examples for"
                    },
                    "object_type": {
                        "type": "string",
                        "description": "Object type to filter examples (e.g., 'LexEntry', 'Sense')"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of examples to return (default: 5)",
                        "default": 5
                    }
                }
            }
        ),
        Tool(
            name="list_categories",
            description="List all available API categories (lexicon, grammar, texts, etc.) with their entity counts.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="list_entities_in_category",
            description="List all entities (classes/interfaces) in a specific category.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Category name (e.g., 'lexicon', 'grammar', 'texts')"
                    }
                },
                "required": ["category"]
            }
        ),
        Tool(
            name="get_module_template",
            description="Get the official FlexTools module template for creating new FlexTools scripts. Returns a ready-to-use Python template with the correct structure, imports, and documentation format.",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_name": {
                        "type": "string",
                        "description": "Name for the new module (e.g., 'Export Custom Data')"
                    },
                    "synopsis": {
                        "type": "string",
                        "description": "Short description of what the module does"
                    },
                    "modifies_db": {
                        "type": "boolean",
                        "description": "Whether the module modifies the database (default: false)",
                        "default": False
                    }
                }
            }
        ),
        Tool(
            name="start_module",
            description="Interactive wizard to start creating a new FlexTools module. Checks Python version, gathers requirements, and generates a customized template with appropriate boilerplate code. Call with no arguments to get the list of questions, or provide answers to generate the template.",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_name": {
                        "type": "string",
                        "description": "Name for the new module"
                    },
                    "synopsis": {
                        "type": "string",
                        "description": "Short description of what the module does"
                    },
                    "api_target": {
                        "type": "string",
                        "enum": ["flexlibs2", "flexlibs_stable", "liblcm"],
                        "description": "Target API: 'flexlibs2' (recommended, Python wrappers), 'flexlibs_stable' (legacy wrappers), or 'liblcm' (raw C# via pythonnet)"
                    },
                    "modifies_db": {
                        "type": "boolean",
                        "description": "Whether the module modifies the database"
                    },
                    "domain": {
                        "type": "string",
                        "enum": ["lexicon", "grammar", "texts", "media", "general"],
                        "description": "Primary domain the module works with"
                    },
                    "include_dry_run": {
                        "type": "boolean",
                        "description": "Include DRY_RUN safety mode for write operations"
                    }
                }
            }
        ),
        Tool(
            name="run_module",
            description="Execute a FlexTools module against a FieldWorks project using FlexLibs directly. Returns the execution log. Defaults to DRY_RUN mode (read-only) for safety. IMPORTANT: Always backup your project before running with write_enabled=True.",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_code": {
                        "type": "string",
                        "description": "The complete FlexTools module Python code to execute"
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Name of the FieldWorks project to open (e.g., 'Sena 3')"
                    },
                    "write_enabled": {
                        "type": "boolean",
                        "description": "Enable write access to the database. Default is False (read-only/dry-run mode). WARNING: Set to True only after testing!",
                        "default": False
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Maximum execution time in seconds (default: 300)",
                        "default": 300
                    }
                },
                "required": ["module_code", "project_name"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    global api_index

    if api_index is None:
        api_index = APIIndex.load(get_index_dir())

    if name == "get_object_api":
        return await handle_get_object_api(arguments)
    elif name == "search_by_capability":
        return await handle_search_by_capability(arguments)
    elif name == "get_navigation_path":
        return await handle_get_navigation_path(arguments)
    elif name == "find_examples":
        return await handle_find_examples(arguments)
    elif name == "list_categories":
        return await handle_list_categories(arguments)
    elif name == "list_entities_in_category":
        return await handle_list_entities_in_category(arguments)
    elif name == "get_module_template":
        return await handle_get_module_template(arguments)
    elif name == "start_module":
        return await handle_start_module(arguments)
    elif name == "run_module":
        return await handle_run_module(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


def paginate_entity(entity: dict, summary_only: bool, method_filter: str, limit: int, offset: int) -> dict:
    """Apply pagination and filtering to an entity's methods."""
    result = {
        "category": entity.get("category"),
        "summary": entity.get("summary", ""),
        "source_file": entity.get("source_file", ""),
    }

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


async def handle_get_object_api(args: dict) -> list[TextContent]:
    """Get API documentation for a specific object type."""
    object_type = args["object_type"]
    include_flexlibs2 = args.get("include_flexlibs2", True)
    include_liblcm = args.get("include_liblcm", True)
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
            result["flexlibs2"] = paginate_entity(
                entities[object_type], summary_only, method_filter, limit, offset
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
                entities[object_type], summary_only, method_filter, limit, offset
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

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def handle_search_by_capability(args: dict) -> list[TextContent]:
    """Search for methods by capability description with API mode support."""
    query = args["query"]
    max_results = args.get("max_results", 10)
    api_mode = args.get("api_mode", "all")
    use_semantic = args.get("semantic", True)

    results = []
    search_method = "keyword"
    sources_searched = []
    fallback_used = False

    # Define which sources to search based on api_mode
    # Each mode has primary sources and optional fallback sources
    mode_config = {
        "flexlibs2": {
            "primary": ["flexlibs2"],
            "fallback": [],  # FlexLibs 2.0 is comprehensive, rarely needs fallback
            "description": "FlexLibs 2.0 (recommended)"
        },
        "flexlibs_stable": {
            "primary": ["flexlibs_stable"],
            "fallback": ["liblcm"],  # Fall back to LibLCM for uncovered functionality
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
        # For semantic search, map api_mode to source filter
        semantic_source = api_mode if api_mode in ["flexlibs2", "liblcm"] else "all"
        semantic_results = api_index.semantic_search.search(query, max_results, semantic_source)
        if semantic_results:
            results = semantic_results
            search_method = "semantic"
            sources_searched = [api_mode]

    # Fall back to keyword search
    if not results:
        query_lower = query.lower()

        # Synonym expansion for common operations
        synonyms = {
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
        }

        # Expand query terms with synonyms
        query_terms = query_lower.split()
        expanded_terms = set(query_terms)
        for term in query_terms:
            if term in synonyms:
                expanded_terms.update(synonyms[term])

        def search_source(source_name, index_data, boost=0):
            """Search a single source and return results."""
            source_results = []
            if not index_data:
                return source_results

            for entity_name, entity in index_data.get("entities", {}).items():
                for method in entity.get("methods", []):
                    score = boost  # Mode-based boost
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

                    if score > boost:  # Only include if actual matches found
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

    return [TextContent(type="text", text=json.dumps({
        "query": query,
        "api_mode": api_mode,
        "api_mode_description": config["description"],
        "search_method": search_method,
        "sources_searched": sources_searched,
        "fallback_used": fallback_used,
        "semantic_available": api_index.semantic_search.enabled if api_index.semantic_search else False,
        "results_count": len(results),
        "results": results
    }, indent=2))]


def normalize_object_name(name: str) -> str:
    """Normalize object name to interface format (ILexEntry)."""
    name = name.replace("Operations", "")
    if not name.startswith("I"):
        name = f"I{name}"
    return name


def find_path_bfs(graph: dict, start: str, end: str, max_depth: int = 5) -> list:
    """Find path between two entities using BFS."""
    from collections import deque

    if start == end:
        return []

    queue = deque([(start, [])])
    visited = {start}

    while queue:
        current, path = queue.popleft()
        if len(path) >= max_depth:
            continue

        for edge in graph.get(current, []):
            target, via, rel_type = edge[0], edge[1], edge[2]

            if target == end:
                return path + [{"from": current, "to": target, "via": via, "type": rel_type}]

            if target not in visited:
                visited.add(target)
                queue.append((target, path + [{"from": current, "to": target, "via": via, "type": rel_type}]))

    return None


def generate_code_from_path(steps: list) -> str:
    """Generate Python code pattern from navigation steps."""
    if not steps:
        return ""

    lines = []
    indent = ""
    current_var = steps[0]["from"].lower().replace("i", "", 1)

    for step in steps:
        prop = step["via"]
        is_collection = prop.endswith("OS") or prop.endswith("OC") or prop.endswith("RC") or prop.endswith("RS")

        if is_collection:
            item_var = step["to"].lower().replace("i", "", 1)
            lines.append(f"{indent}for {item_var} in {current_var}.{prop}:")
            indent += "    "
            current_var = item_var
        else:
            new_var = step["to"].lower().replace("i", "", 1)
            lines.append(f"{indent}{new_var} = {current_var}.{prop}")
            current_var = new_var

    lines.append(f"{indent}# work with {current_var}")
    return "\n".join(lines)


async def handle_get_navigation_path(args: dict) -> list[TextContent]:
    """Find navigation path between two object types using precomputed graph."""
    from_obj = args["from_object"]
    to_obj = args["to_object"]

    from_normalized = normalize_object_name(from_obj)
    to_normalized = normalize_object_name(to_obj)

    result = {
        "from": from_obj,
        "to": to_obj,
        "from_normalized": from_normalized,
        "to_normalized": to_normalized,
        "found": False
    }

    # Check if navigation graph is loaded
    if not api_index.navigation_graph:
        result["message"] = "Navigation graph not loaded. Run refresh.py to generate it."
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    nav_graph = api_index.navigation_graph
    common_paths = nav_graph.get("common_paths", {})
    graph = nav_graph.get("graph", {})

    # Try precomputed common paths first
    path_key = f"{from_normalized} -> {to_normalized}"
    if path_key in common_paths:
        path_info = common_paths[path_key]
        result["found"] = True
        result["source"] = "precomputed"
        result["steps"] = path_info["steps"]
        result["code"] = path_info.get("code_pattern", "")
        result["description"] = f"Navigate from {from_normalized} to {to_normalized}"
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Fall back to BFS pathfinding
    steps = find_path_bfs(graph, from_normalized, to_normalized)
    if steps:
        result["found"] = True
        result["source"] = "computed"
        result["steps"] = steps
        result["code"] = generate_code_from_path(steps)
        result["description"] = f"Path found via BFS ({len(steps)} step{'s' if len(steps) != 1 else ''})"
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # No path found
    result["message"] = f"No navigation path found from {from_normalized} to {to_normalized}."
    result["hint"] = "Try using get_object_api to explore the properties and relationships of these objects."

    # Suggest nearby objects if available
    if from_normalized in nav_graph.get("entities", {}):
        entity_rels = nav_graph["entities"][from_normalized]
        children = [c["target"] for c in entity_rels.get("children", [])[:5]]
        if children:
            result["reachable_from_source"] = children

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


async def handle_list_categories(args: dict) -> list[TextContent]:
    """List all available API categories."""
    categories = {}

    # From FlexLibs 2.0
    if api_index.flexlibs2:
        fl2_cats = api_index.flexlibs2.get("categories", {})
        for cat_name, cat_data in fl2_cats.items():
            if cat_name not in categories:
                categories[cat_name] = {"flexlibs2_count": 0, "liblcm_count": 0}
            categories[cat_name]["flexlibs2_count"] = len(cat_data.get("entities", []))

    # From LibLCM
    if api_index.liblcm:
        for entity in api_index.liblcm.get("entities", {}).values():
            cat = entity.get("category", "uncategorized")
            if cat not in categories:
                categories[cat] = {"flexlibs2_count": 0, "liblcm_count": 0}
            categories[cat]["liblcm_count"] += 1

    return [TextContent(type="text", text=json.dumps({
        "categories": categories,
        "total_categories": len(categories)
    }, indent=2))]


async def handle_list_entities_in_category(args: dict) -> list[TextContent]:
    """List all entities in a specific category."""
    category = args["category"].lower()

    entities = {"flexlibs2": [], "liblcm": []}

    # From FlexLibs 2.0
    if api_index.flexlibs2:
        for entity_name, entity in api_index.flexlibs2.get("entities", {}).items():
            if entity.get("category", "").lower() == category:
                entities["flexlibs2"].append({
                    "name": entity_name,
                    "methods_count": len(entity.get("methods", [])),
                    "summary": entity.get("summary", "")[:100]
                })

    # From LibLCM
    if api_index.liblcm:
        for entity_name, entity in api_index.liblcm.get("entities", {}).items():
            if entity.get("category", "").lower() == category:
                entities["liblcm"].append({
                    "name": entity_name,
                    "type": entity.get("type"),
                    "summary": entity.get("summary", entity.get("description", ""))[:100]
                })

    return [TextContent(type="text", text=json.dumps({
        "category": category,
        "entities": entities,
        "counts": {
            "flexlibs2": len(entities["flexlibs2"]),
            "liblcm": len(entities["liblcm"])
        }
    }, indent=2))]


async def handle_get_module_template(args: dict) -> list[TextContent]:
    """Return the official FlexTools module template."""
    module_name = args.get("module_name", "<Module name>")
    synopsis = args.get("synopsis", "<description>")
    modifies_db = args.get("modifies_db", False)

    template = '''#
#   {module_name}
#    - A FlexTools Module -
#
#   {synopsis}
#
#   Platforms: Python .NET and IronPython
#

from flextoolslib import *

#----------------------------------------------------------------
# Documentation that the user sees:

docs = {{FTM_Name        : "{module_name}",
        FTM_Version     : 1,
        FTM_ModifiesDB  : {modifies_db},
        FTM_Synopsis    : "{synopsis}",
        FTM_Description :
"""
<detailed description here>
""" }}

#----------------------------------------------------------------
# The main processing function

def Main(project, report, modifyAllowed):
    """
    Main entry point for the FlexTools module.

    Args:
        project: FLExProject instance providing access to the FieldWorks database
        report: Reporter object for logging (report.Info, report.Warning, report.Error)
        modifyAllowed: Boolean indicating if database modifications are permitted
    """
    report.Info("Starting...")

    # Example: iterate all entries
    # for entry in project.LexiconAllEntries():
    #     headword = project.LexiconGetHeadword(entry)
    #     report.Info("Entry: {{}}".format(headword))

    report.Info("Done.")

#----------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(Main, docs)

#----------------------------------------------------------------
if __name__ == '__main__':
    print(FlexToolsModule.Help())
'''.format(
        module_name=module_name,
        synopsis=synopsis,
        modifies_db=modifies_db
    )

    result = {
        "template": template,
        "notes": [
            "FTM_Version should be an integer (1, 2, 3...), not a string",
            "Main function must be named 'Main' (not 'MainFunction')",
            "Use .format() for string formatting (IronPython compatible), not f-strings",
            "Do not use type hints (IronPython does not support them)",
            "Do not use pathlib (use os.path instead for IronPython compatibility)",
            "FlexToolsModule = FlexToolsModuleClass(Main, docs) uses positional args"
        ],
        "report_methods": [
            "report.Info(message) - Informational message",
            "report.Warning(message) - Warning message",
            "report.Error(message) - Error message",
            "report.Blank() - Blank line",
            "report.FileURL(path) - Create clickable file link"
        ]
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_start_module(args: dict) -> list[TextContent]:
    """Interactive wizard to start creating a new FlexTools module."""
    import sys
    import platform

    # Gather environment info
    env_info = {
        "python_version": "{}.{}.{}".format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro),
        "python_implementation": platform.python_implementation(),
        "platform": platform.system(),
        "can_use_modern_python": sys.version_info >= (3, 6),
    }

    # Check what parameters were provided
    provided = {k: v for k, v in args.items() if v is not None}

    # Define required and optional questions
    required_questions = []
    optional_questions = []

    if "module_name" not in provided:
        required_questions.append({
            "field": "module_name",
            "question": "What should the module be named?",
            "type": "string",
            "example": "Export Custom Data"
        })

    if "synopsis" not in provided:
        required_questions.append({
            "field": "synopsis",
            "question": "Provide a short description of what the module does:",
            "type": "string",
            "example": "Exports custom field data to a file"
        })

    if "api_target" not in provided:
        required_questions.append({
            "field": "api_target",
            "question": "Which API should the module target?",
            "type": "choice",
            "options": [
                {
                    "value": "flexlibs2",
                    "label": "FlexLibs 2.0 (Recommended)",
                    "description": "Modern Python wrappers with 99% documentation coverage and examples. Best for new modules. Use api_mode='flexlibs2' in searches."
                },
                {
                    "value": "flexlibs_stable",
                    "label": "FlexLibs Stable + LibLCM fallback",
                    "description": "Legacy Python wrappers (~40 functions) with LibLCM fallback for advanced features. Use api_mode='flexlibs_stable' in searches."
                },
                {
                    "value": "liblcm",
                    "label": "Pure LibLCM",
                    "description": "Direct C# API access via pythonnet. Maximum flexibility but requires .NET knowledge. Use api_mode='liblcm' in searches."
                }
            ],
            "recommended": "flexlibs2"
        })

    if "modifies_db" not in provided:
        required_questions.append({
            "field": "modifies_db",
            "question": "Will this module modify the FieldWorks database?",
            "type": "boolean",
            "hint": "Set to True if the module creates, updates, or deletes entries, senses, or other data."
        })

    if "domain" not in provided:
        required_questions.append({
            "field": "domain",
            "question": "What is the primary domain this module works with?",
            "type": "choice",
            "options": [
                {"value": "lexicon", "label": "Lexicon", "description": "Entries, senses, definitions, glosses"},
                {"value": "grammar", "label": "Grammar", "description": "Parts of speech, morphology, inflection"},
                {"value": "texts", "label": "Texts", "description": "Interlinear texts, discourse analysis"},
                {"value": "media", "label": "Media", "description": "Pictures, audio files, linked files"},
                {"value": "general", "label": "General", "description": "Project-wide operations, multiple domains"}
            ]
        })

    if args.get("modifies_db") and "include_dry_run" not in provided:
        required_questions.append({
            "field": "include_dry_run",
            "question": "Include a DRY_RUN safety mode? (Recommended for write operations)",
            "type": "boolean",
            "hint": "DRY_RUN mode shows what would happen without making changes. Useful for testing.",
            "recommended": True
        })

    # Optional question - only ask if no required questions remain
    if "test_project" not in provided:
        optional_questions.append({
            "field": "test_project",
            "question": "Do you have a FieldWorks test project to verify the script against?",
            "type": "string",
            "hint": "Provide the project name (e.g., 'Sena 3') or path. This helps verify the script works before running on production data.",
            "optional": True,
            "example": "Sena 3"
        })

    # If we have required questions, return them along with optional ones
    if required_questions:
        questions = required_questions + optional_questions
        return [TextContent(type="text", text=json.dumps({
            "status": "needs_input",
            "environment": env_info,
            "provided": provided,
            "required_questions": required_questions,
            "optional_questions": optional_questions,
            "questions": questions,  # Combined for convenience
            "instructions": "Please ask the user these questions and call start_module again with the answers. Optional questions can be skipped."
        }, indent=2))]

    # All questions answered - generate the template
    module_name = args["module_name"]
    synopsis = args["synopsis"]
    api_target = args["api_target"]
    modifies_db = args["modifies_db"]
    domain = args.get("domain", "general")
    include_dry_run = args.get("include_dry_run", False)
    test_project = args.get("test_project")

    # Build imports
    imports = ["from flextoolslib import *"]

    # Build helper code
    helpers = []
    if include_dry_run:
        helpers.append("""
#----------------------------------------------------------------
# Configuration

DRY_RUN = True  # Set to False to actually make changes
""")

    # Build main function body
    main_body_lines = []

    if modifies_db and include_dry_run:
        main_body_lines.append("""    if not modifyAllowed and not DRY_RUN:
        report.Error("This module requires write access.")
        return

    if DRY_RUN:
        report.Warning("DRY RUN mode - no changes will be made")
""")
    elif modifies_db:
        main_body_lines.append("""    if not modifyAllowed:
        report.Error("This module requires write access.")
        return
""")

    main_body_lines.append("""
    report.Info("Starting...")

    # TODO: Implement module logic

    report.Info("Done.")
""")

    # Combine main body
    main_body = "".join(main_body_lines)

    # Generate final template
    template = """#
#   {module_name}
#    - A FlexTools Module -
#
#   {synopsis}
#
#   API Target: {api_target}
#   Platforms: Python .NET and IronPython
#

{imports}
{helpers}
#----------------------------------------------------------------
# Documentation that the user sees:

docs = {{FTM_Name        : "{module_name}",
        FTM_Version     : 1,
        FTM_ModifiesDB  : {modifies_db},
        FTM_Synopsis    : "{synopsis}",
        FTM_Description :
\"\"\"
{synopsis}

<additional details here>
\"\"\" }}

#----------------------------------------------------------------
# The main processing function

def Main(project, report, modifyAllowed):
    \"\"\"
    Main entry point for the FlexTools module.

    Args:
        project: FLExProject instance providing access to the FieldWorks database
        report: Reporter object for logging (report.Info, report.Warning, report.Error)
        modifyAllowed: Boolean indicating if database modifications are permitted
    \"\"\"
{main_body}

#----------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(Main, docs)

#----------------------------------------------------------------
if __name__ == '__main__':
    print(FlexToolsModule.Help())
""".format(
        module_name=module_name,
        synopsis=synopsis,
        api_target=api_target,
        imports="\n".join(imports),
        helpers="".join(helpers),
        modifies_db=modifies_db,
        main_body=main_body
    )

    # API-specific notes and search guidance
    api_notes = {
        "flexlibs2": {
            "search_mode": "flexlibs2",
            "tips": [
                "Use project.Senses.GetAll() to iterate senses",
                "Use project.CustomFields.GetValue/SetValue for custom fields",
                "Use project.Media.* for file operations",
                "Full documentation at 99% coverage with examples"
            ],
            "search_reminder": "Use api_mode='flexlibs2' when calling search_by_capability"
        },
        "flexlibs_stable": {
            "search_mode": "flexlibs_stable",
            "tips": [
                "Use project.LexiconAllEntries() to iterate entries",
                "More limited API (~40 functions)",
                "LibLCM fallback available for advanced features",
                "Compatible with older FlexTools installations"
            ],
            "search_reminder": "Use api_mode='flexlibs_stable' when calling search_by_capability (includes LibLCM fallback)"
        },
        "liblcm": {
            "search_mode": "liblcm",
            "tips": [
                "Direct access to C# LibLCM API via pythonnet",
                "Requires understanding of .NET and LibLCM architecture",
                "Most powerful but also most complex",
                "Use ILexEntry, ILexSense, etc. interface types"
            ],
            "search_reminder": "Use api_mode='liblcm' when calling search_by_capability"
        }
    }

    # Build next steps based on configuration
    next_steps = [
        "Save the template to your FlexTools Modules folder",
        "Replace TODO comments with your implementation",
    ]

    if include_dry_run:
        next_steps.append("Test with DRY_RUN=True first to verify behavior without making changes")

    if test_project:
        next_steps.append("Run the module against '{}' to verify it works correctly".format(test_project))
        next_steps.append("Check the FlexTools report output for any errors or warnings")
    else:
        next_steps.append("IMPORTANT: Test on a backup/sample project before running on production data")

    next_steps.append("Use search_by_capability to find specific API methods you need")

    # Build configuration output
    config = {
        "module_name": module_name,
        "synopsis": synopsis,
        "api_target": api_target,
        "modifies_db": modifies_db,
        "domain": domain,
        "include_dry_run": include_dry_run
    }
    if test_project:
        config["test_project"] = test_project

    api_info = api_notes.get(api_target, {})

    return [TextContent(type="text", text=json.dumps({
        "status": "complete",
        "environment": env_info,
        "configuration": config,
        "template": template,
        "api_guidance": {
            "mode": api_target,
            "search_mode": api_info.get("search_mode", api_target),
            "search_reminder": api_info.get("search_reminder", ""),
            "tips": api_info.get("tips", [])
        },
        "next_steps": next_steps,
        "testing_reminder": "Always test FlexTools modules on a backup or sample project first!" if not test_project else None
    }, indent=2))]


async def handle_run_module(args: dict) -> list[TextContent]:
    """Execute a FlexTools module against a FieldWorks project using FlexLibs directly."""
    module_code = args["module_code"]
    project_name = args["project_name"]
    write_enabled = args.get("write_enabled", False)
    timeout_seconds = args.get("timeout_seconds", 300)

    # Build warnings
    warnings = []
    if write_enabled:
        warnings.extend([
            "*** WRITE MODE ENABLED ***",
            "Changes WILL be made to the database!",
            "Make sure you have a backup of your project!",
            ""
        ])
    else:
        warnings.extend([
            "Running in READ-ONLY mode (dry-run)",
            "No changes will be made to the database.",
            "Set write_enabled=True to enable modifications.",
            ""
        ])

    # Create the runner script that will be executed in a subprocess
    runner_script = '''# -*- coding: utf-8 -*-
"""FlexTools Module Runner - Generated by FlexToolsMCP"""
import sys
import json
import os
import traceback

# ============================================================
# Mock flextoolslib module (so module code can import from it)
# ============================================================
import types

# Create fake flextoolslib module
flextoolslib = types.ModuleType('flextoolslib')

# FlexTools module documentation keys
flextoolslib.FTM_Name = "FTM_Name"
flextoolslib.FTM_Version = "FTM_Version"
flextoolslib.FTM_ModifiesDB = "FTM_ModifiesDB"
flextoolslib.FTM_Synopsis = "FTM_Synopsis"
flextoolslib.FTM_Description = "FTM_Description"
flextoolslib.FTM_Help = "FTM_Help"

# Minimal FlexToolsModuleClass
class FlexToolsModuleClass:
    def __init__(self, runFunction=None, docs=None, configuration=None):
        self.runFunction = runFunction
        self.docs = docs or {}
        self.configuration = configuration or []

    def Run(self, project, report, modifyAllowed=False):
        if self.runFunction:
            self.runFunction(project, report, modifyAllowed)

    def Help(self):
        return self.docs.get(flextoolslib.FTM_Description, "")

flextoolslib.FlexToolsModuleClass = FlexToolsModuleClass

# Register the mock module
sys.modules['flextoolslib'] = flextoolslib

# ============================================================
# Simple Reporter Class (mimics FTReporter interface)
# ============================================================
class SimpleReporter:
    INFO = 0
    WARNING = 1
    ERROR = 2
    BLANK = 3
    TYPE_NAMES = ["INFO", "WARNING", "ERROR", "BLANK"]

    def __init__(self):
        self.messages = []
        self.messageCounts = [0, 0, 0, 0]

    def _report(self, msg_type, msg, ref=None):
        if msg is not None and not isinstance(msg, str):
            msg = repr(msg)
        self.messages.append({
            "type": self.TYPE_NAMES[msg_type],
            "message": msg,
            "ref": ref
        })
        self.messageCounts[msg_type] += 1

    def Info(self, msg, ref=None):
        self._report(self.INFO, msg, ref)

    def Warning(self, msg, ref=None):
        self._report(self.WARNING, msg, ref)

    def Error(self, msg, ref=None):
        self._report(self.ERROR, msg, ref)

    def Blank(self):
        self._report(self.BLANK, "", None)

    def ProgressStart(self, max_val, msg=None):
        pass  # Progress not captured in non-GUI mode

    def ProgressUpdate(self, value):
        pass

    def ProgressStop(self):
        pass

    def FileURL(self, fname):
        import pathlib
        return pathlib.Path(os.path.abspath(fname)).as_uri()


# ============================================================
# Main Execution
# ============================================================
def run_module():
    result = {
        "success": False,
        "project": PROJECT_NAME,
        "write_enabled": WRITE_ENABLED,
        "messages": [],
        "summary": {},
        "error": None
    }

    project = None

    try:
        # Initialize FlexLibs
        from flexlibs import FLExInitialize, FLExCleanup, FLExProject

        FLExInitialize()

        # Open project
        project = FLExProject()
        try:
            project.OpenProject(projectName=PROJECT_NAME, writeEnabled=WRITE_ENABLED)
        except Exception as e:
            result["error"] = "Failed to open project '{}': {}".format(PROJECT_NAME, str(e))
            return result

        # Create reporter
        report = SimpleReporter()

        # Execute the module code in a namespace
        module_namespace = {
            "__name__": "__flextools_module__",
            "__file__": "module.py",
        }

        # Execute the module code to define Main and FlexToolsModule
        exec(MODULE_CODE, module_namespace)

        # Find and call Main function
        if "Main" in module_namespace:
            module_namespace["Main"](project, report, WRITE_ENABLED)
        elif "FlexToolsModule" in module_namespace:
            module_namespace["FlexToolsModule"].Run(project, report, WRITE_ENABLED)
        else:
            result["error"] = "Module code must define either 'Main' function or 'FlexToolsModule'"
            return result

        # Collect results
        result["success"] = True
        result["messages"] = report.messages
        result["summary"] = {
            "info_count": report.messageCounts[SimpleReporter.INFO],
            "warning_count": report.messageCounts[SimpleReporter.WARNING],
            "error_count": report.messageCounts[SimpleReporter.ERROR],
            "total_messages": len(report.messages)
        }

    except Exception as e:
        result["error"] = "Execution error: {}\\n{}".format(str(e), traceback.format_exc())

    finally:
        # Clean up
        if project:
            try:
                project.CloseProject()
            except:
                pass
        try:
            FLExCleanup()
        except:
            pass

    return result


if __name__ == "__main__":
    result = run_module()
    print("===FLEXTOOLS_RESULT_JSON===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
'''

    # Escape the module code for embedding in the script
    # We use repr() to safely escape all special characters
    escaped_module_code = repr(module_code)

    # Create the complete script with configuration
    full_script = '''# Configuration
PROJECT_NAME = {project_name}
WRITE_ENABLED = {write_enabled}
MODULE_CODE = {module_code}

{runner_script}
'''.format(
        project_name=repr(project_name),
        write_enabled=repr(write_enabled),
        module_code=escaped_module_code,
        runner_script=runner_script
    )

    # Write to temporary file
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(full_script)
            temp_script_path = f.name
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Failed to create temporary script: {}".format(str(e)),
            "warnings": warnings
        }, indent=2))]

    try:
        # Run the script in a subprocess
        # Use the same Python interpreter
        result = subprocess.run(
            [sys.executable, temp_script_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding='utf-8'
        )

        stdout = result.stdout
        stderr = result.stderr

        # Parse the JSON result from stdout
        if "===FLEXTOOLS_RESULT_JSON===" in stdout:
            json_start = stdout.index("===FLEXTOOLS_RESULT_JSON===") + len("===FLEXTOOLS_RESULT_JSON===")
            json_str = stdout[json_start:].strip()
            try:
                execution_result = json.loads(json_str)
            except json.JSONDecodeError as e:
                execution_result = {
                    "success": False,
                    "error": "Failed to parse result JSON: {}".format(str(e)),
                    "raw_output": stdout
                }
        else:
            execution_result = {
                "success": False,
                "error": "No result marker found in output",
                "raw_output": stdout,
                "stderr": stderr
            }

        # Add warnings and metadata
        execution_result["warnings"] = warnings
        execution_result["exit_code"] = result.returncode
        if stderr and not execution_result.get("error"):
            execution_result["stderr"] = stderr

        return [TextContent(type="text", text=json.dumps(execution_result, indent=2, ensure_ascii=False))]

    except subprocess.TimeoutExpired:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Execution timed out after {} seconds".format(timeout_seconds),
            "warnings": warnings
        }, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Subprocess execution error: {}".format(str(e)),
            "warnings": warnings
        }, indent=2))]

    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_script_path)
        except:
            pass


async def main():
    """Run the MCP server."""
    global api_index

    # Pre-load indexes
    print("[INFO] Loading API indexes...", file=__import__("sys").stderr)
    api_index = APIIndex.load(get_index_dir())

    if api_index.liblcm:
        print(f"[OK] LibLCM: {len(api_index.liblcm.get('entities', {}))} entities", file=__import__("sys").stderr)
    else:
        print("[WARN] LibLCM index not found", file=__import__("sys").stderr)

    if api_index.flexlibs2:
        print(f"[OK] FlexLibs 2.0: {len(api_index.flexlibs2.get('entities', {}))} entities", file=__import__("sys").stderr)
    else:
        print("[WARN] FlexLibs 2.0 index not found", file=__import__("sys").stderr)

    if api_index.flexlibs_stable:
        print(f"[OK] FlexLibs Stable: {len(api_index.flexlibs_stable.get('entities', {}))} entities", file=__import__("sys").stderr)
    else:
        print("[WARN] FlexLibs Stable index not found", file=__import__("sys").stderr)

    print("[INFO] Starting MCP server...", file=__import__("sys").stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
