#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Discovery handler functions for FlexToolsMCP.

These handlers provide navigation and discovery of API relationships:
- get_navigation_path: Find navigation paths between object types
- resolve_property: Resolve pythonic property names to LibLCM equivalents
"""

import json
from collections import deque
from mcp.types import TextContent

from ._import_helper import safe_import_kernel_deps
from ..models import GetNavigationPathInput
from ..response_keys import (
    KEY_MESSAGE, KEY_DESCRIPTION, KEY_TYPE, KEY_FOUND, KEY_SOURCE,
    KEY_FROM, KEY_TO, KEY_VIA, KEY_PROPERTY, KEY_STEPS, KEY_CODE, KEY_HINT,
    KEY_COMMON_PATHS, KEY_GRAPH, KEY_ENTITIES, KEY_CHILDREN, KEY_TARGET,
    KEY_POLYMORPHIC_COLLECTIONS, KEY_BASE_TYPE, KEY_CONCRETE_TYPES,
    KEY_CASTING_WARNINGS, KEY_CASTING_HINT,
    KEY_REACHABLE_FROM_SOURCE
)
from .utils import normalize_object_name

# Import with fallback support
json_response, session_state, _, get_api_index = safe_import_kernel_deps()

# Type note: api_index is initialized by server.py before any handlers are called

# ============================================================
# Constants (avoid stringly-typed code)
# ============================================================
# Collection property suffixes (OS=Sequence, OC=Collection, RC=References, RS=ReferencesSeq)
COLLECTION_SUFFIXES = ("OS", "OC", "RC", "RS")

# Constants for fallbacks
MAX_SUGGESTED_ENTITIES = 5


def find_path_bfs(graph: dict, start: str, end: str, max_depth: int = 5) -> list:
    """Find path between two entities using BFS.

    Args:
        graph: Adjacency list where graph[entity] = [(target, via, rel_type), ...]
        start: Starting entity name
        end: Target entity name
        max_depth: Maximum path depth to search

    Returns:
        List of steps [{from, to, via, type}, ...] or empty list if no path found
    """
    if start == end:
        return []

    # Parent tracking approach: avoid O(n) list concatenation per iteration
    # Instead of: queue = [(node, path)], we track: queue = [node], parent[node] = (parent_node, edge)
    # This eliminates O(n) list copying on every queue append (major optimization for large graphs)
    queue = deque([start])
    visited = {start}
    parent = {}  # Maps node -> (parent_node, via, rel_type)

    def get_depth(node: str) -> int:
        """Get depth by following parent chain."""
        depth = 0
        while node in parent:
            node = parent[node][0]
            depth += 1
        return depth

    while queue:
        current = queue.popleft()

        for edge in graph.get(current, []):
            target, via, rel_type = edge[0], edge[1], edge[2]

            if target == end:
                # Reconstruct path using parent pointers (linear reconstruction, not exponential)
                path = []
                node = target
                while node in parent:
                    parent_node, via_prop, rel_t = parent[node]
                    path.append({KEY_FROM: parent_node, KEY_TO: node, KEY_VIA: via_prop, KEY_TYPE: rel_t})
                    node = parent_node
                return list(reversed(path))

            if target not in visited:
                visited.add(target)
                parent[target] = (current, via, rel_type)
                # Only enqueue if we haven't hit max depth
                if get_depth(target) < max_depth:
                    queue.append(target)

    return []


def generate_code_from_path(steps: list) -> str:
    """Generate Python code pattern from navigation steps.

    Converts path steps into executable Python code skeleton showing:
    - Direct property access (single navigation)
    - Collection iteration (accessing sequences/collections)
    """
    if not steps:
        return ""

    def entity_to_var(entity_name: str) -> str:
        """Convert entity name (ILexEntry) to variable name (lexEntry)."""
        return entity_name[1:].lower() if entity_name.startswith("I") else entity_name.lower()

    lines = []
    indent = ""
    current_var = entity_to_var(steps[0][KEY_FROM])

    for step in steps:
        prop = step[KEY_VIA]
        is_collection = prop.endswith(COLLECTION_SUFFIXES)

        if is_collection:
            item_var = entity_to_var(step[KEY_TO])
            lines.append(f"{indent}for {item_var} in {current_var}.{prop}:")
            indent += "    "
            current_var = item_var
        else:
            new_var = entity_to_var(step[KEY_TO])
            lines.append(f"{indent}{new_var} = {current_var}.{prop}")
            current_var = new_var

    lines.append(f"{indent}# work with {current_var}")
    return "\n".join(lines)


def _add_polymorphic_warnings(result: dict, steps: list) -> None:
    """Add casting warnings for polymorphic collections in the navigation path.

    Checks each step property against casting index to identify collections
    that require explicit casting to access type-specific properties.
    """
    if not get_api_index() or not get_api_index().casting_index or not steps:
        return

    casting_index = get_api_index().casting_index
    poly_collections = casting_index.get(KEY_POLYMORPHIC_COLLECTIONS, {})
    warnings = []

    for step in steps:
        # Extract property name from step (try 'property' key, fallback to 'via' field)
        property_name = step.get(KEY_PROPERTY) or step.get(KEY_VIA, "").split(".")[-1]
        if property_name in poly_collections:
            poly_info = poly_collections[property_name]
            base_type = poly_info.get(KEY_BASE_TYPE, "a base type")
            concrete_types = poly_info.get(KEY_CONCRETE_TYPES, [])
            warning = {
                KEY_PROPERTY: property_name,
                KEY_BASE_TYPE: base_type,
                KEY_CONCRETE_TYPES: concrete_types,
                KEY_MESSAGE: f"The {property_name} property returns {base_type}. "
                             f"You may need to cast to a concrete type: {', '.join(concrete_types)}",
                "suggestion": "Use CastingOperations.cast_to_concrete(obj) to cast to the concrete type."
            }
            warnings.append(warning)

    if warnings:
        result[KEY_CASTING_WARNINGS] = warnings
        result[KEY_CASTING_HINT] = "This path accesses polymorphic collections. Use CastingOperations from Flexicon to access type-specific properties."


async def handle_get_navigation_path(args: GetNavigationPathInput) -> list[TextContent]:
    """Find navigation path between two object types using precomputed graph.

    Tries precomputed common paths first, then falls back to BFS search.
    Includes polymorphic collection warnings for paths that require casting."""
    from_obj = args.from_object
    to_obj = args.to_object

    from_normalized = normalize_object_name(from_obj)
    to_normalized = normalize_object_name(to_obj)

    result = {
        "from": from_obj,
        "to": to_obj,
        "from_normalized": from_normalized,
        "to_normalized": to_normalized,
        KEY_FOUND: False
    }

    # Check if navigation graph is loaded
    if not get_api_index() or not get_api_index().navigation_graph:
        result[KEY_MESSAGE] = "Navigation graph not loaded. Run refresh.py to generate it."
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    nav_graph = get_api_index().navigation_graph
    common_paths = nav_graph.get(KEY_COMMON_PATHS, {})
    graph = nav_graph.get(KEY_GRAPH, {})

    # Try precomputed common paths first
    path_key = f"{from_normalized} -> {to_normalized}"
    if path_key in common_paths:
        path_info = common_paths[path_key]
        result[KEY_FOUND] = True
        result[KEY_SOURCE] = "precomputed"
        result[KEY_STEPS] = path_info[KEY_STEPS]
        result[KEY_CODE] = path_info.get("code_pattern", "")
        result[KEY_DESCRIPTION] = f"Navigate from {from_normalized} to {to_normalized}"
        _add_polymorphic_warnings(result, path_info[KEY_STEPS])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Fall back to BFS pathfinding
    steps = find_path_bfs(graph, from_normalized, to_normalized)
    if steps:
        result[KEY_FOUND] = True
        result[KEY_SOURCE] = "computed"
        result[KEY_STEPS] = steps
        result[KEY_CODE] = generate_code_from_path(steps)
        result[KEY_DESCRIPTION] = f"Path found via BFS ({len(steps)} step{'s' if len(steps) != 1 else ''})"
        _add_polymorphic_warnings(result, steps)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # No path found
    result[KEY_MESSAGE] = f"No navigation path found from {from_normalized} to {to_normalized}."
    result[KEY_HINT] = "Try using get_object_api to explore the properties and relationships of these objects."

    # Suggest nearby objects if available
    entities = nav_graph.get(KEY_ENTITIES, {})
    if entities and from_normalized in entities:
        entity_rels = entities[from_normalized]
        children = [c[KEY_TARGET] for c in entity_rels.get(KEY_CHILDREN, [])[:MAX_SUGGESTED_ENTITIES]]
        if children:
            result[KEY_REACHABLE_FROM_SOURCE] = children

    return [TextContent(type="text", text=json.dumps(result, indent=2))]
