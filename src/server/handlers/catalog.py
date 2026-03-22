#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Catalog handler functions for FlexToolsMCP.

These handlers provide listing and discovery of available APIs:
- list_categories: List all API categories
- list_entities_in_category: List entities within a specific category
"""

import json
from mcp.types import TextContent

# Import shared state from kernel
# During Phase 5 integration, the re-export facade will handle these imports
try:
    from ..kernel import api_index
except ImportError:
    # Fallback for when module isn't fully modularized yet
    from src.server.kernel import api_index

# Type narrowing: handlers assume api_index is loaded by server.py
assert api_index is not None, "api_index must be initialized before handler calls"


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
