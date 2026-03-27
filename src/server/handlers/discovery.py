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
from typing import List, Dict
from mcp.types import TextContent

# Import shared state from kernel
try:
    from ..kernel import api_index
except ImportError:
    from server.kernel import api_index

# Type note: api_index is initialized by server.py before any handlers are called


def normalize_object_name(name: str) -> str:
    """Normalize object name to interface format (ILexEntry)."""
    name = name.replace("Operations", "")
    if not name.startswith("I"):
        name = f"I{name}"
    return name


def find_path_bfs(graph: dict, start: str, end: str, max_depth: int = 5) -> list:
    """Find path between two entities using BFS."""
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

    return []


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


def _add_polymorphic_warnings(result: dict, steps: list) -> None:
    """Add casting warnings for polymorphic collections in the navigation path."""
    if not api_index or not api_index.casting_index or not steps:
        return

    poly_collections = api_index.casting_index.get("polymorphic_collections", {})
    warnings = []

    for step in steps:
        # Check if this step is a polymorphic collection
        property_name = step.get("property") or step.get("via", "").split(".")[-1]
        if property_name in poly_collections:
            poly_info = poly_collections[property_name]
            warning = {
                "property": property_name,
                "base_type": poly_info.get("base_type", ""),
                "concrete_types": poly_info.get("concrete_types", []),
                "message": f"The {property_name} property returns {poly_info.get('base_type', 'a base type')}. "
                           f"You may need to cast to a concrete type: {', '.join(poly_info.get('concrete_types', []))}",
                "suggestion": f"Use CastingOperations.cast_to_concrete(obj) to cast to the concrete type."
            }
            warnings.append(warning)

    if warnings:
        result["casting_warnings"] = warnings
        result["casting_hint"] = "This path accesses polymorphic collections. Use CastingOperations from FlexLibs2 to access type-specific properties."


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
    if not api_index or not api_index.navigation_graph:
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
        _add_polymorphic_warnings(result, path_info["steps"])
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Fall back to BFS pathfinding
    steps = find_path_bfs(graph, from_normalized, to_normalized)
    if steps:
        result["found"] = True
        result["source"] = "computed"
        result["steps"] = steps
        result["code"] = generate_code_from_path(steps)
        result["description"] = f"Path found via BFS ({len(steps)} step{'s' if len(steps) != 1 else ''})"
        _add_polymorphic_warnings(result, steps)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # No path found
    result["message"] = f"No navigation path found from {from_normalized} to {to_normalized}."
    result["hint"] = "Try using get_object_api to explore the properties and relationships of these objects."

    # Suggest nearby objects if available
    if api_index.navigation_graph and from_normalized in nav_graph.get("entities", {}):
        entity_rels = nav_graph["entities"][from_normalized]
        children = [c["target"] for c in entity_rels.get("children", [])[:5]]
        if children:
            result["reachable_from_source"] = children

    return [TextContent(type="text", text=json.dumps(result, indent=2))]
