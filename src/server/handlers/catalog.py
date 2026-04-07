#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Catalog handler functions for FlexToolsMCP.

These handlers provide listing and discovery of available APIs:
- list_categories: List all API categories
- list_entities_in_category: List entities within a specific category
"""

import json
from collections import defaultdict
from mcp.types import TextContent

# Import shared state and response constants
try:
    from ..kernel import api_index
    from ..models import ListCategoriesInput, ListEntitiesInCategoryInput
    from ..response_keys import KEY_NAME, KEY_TYPE, KEY_DESCRIPTION, KEY_SUMMARY, KEY_CATEGORY
except ImportError:
    # Fallback for when module isn't fully modularized yet
    from server.kernel import api_index
    from server.models import ListCategoriesInput, ListEntitiesInCategoryInput
    from server.response_keys import KEY_NAME, KEY_TYPE, KEY_DESCRIPTION, KEY_SUMMARY, KEY_CATEGORY

# Type note: api_index is initialized by server.py before any handlers are called

# ============================================================
# Constants (avoid stringly-typed code)
# ============================================================
SUMMARY_MAX_LENGTH = 100

# Response field names
# Shared constants imported from response_keys:
# - KEY_NAME, KEY_TYPE, KEY_DESCRIPTION, KEY_SUMMARY, KEY_CATEGORY (above)

# Catalog-specific constants
KEY_FLEXLIBS2_COUNT = "flexlibs2_count"
KEY_LIBLCM_COUNT = "liblcm_count"
KEY_METHODS_COUNT = "methods_count"
KEY_CATEGORIES = "categories"
KEY_ENTITIES = "entities"
KEY_COUNTS = "counts"
KEY_TOTAL_CATEGORIES = "total_categories"


def _init_category_dict() -> dict:
    """Initialize empty category with zero counts."""
    return {KEY_FLEXLIBS2_COUNT: 0, KEY_LIBLCM_COUNT: 0}


def _get_entity_summary(entity: dict) -> str:
    """Extract and normalize entity summary with fallback to description."""
    summary = entity.get(KEY_SUMMARY) or entity.get(KEY_DESCRIPTION) or ""
    return summary[:SUMMARY_MAX_LENGTH]


async def handle_list_categories(args: ListCategoriesInput) -> list[TextContent]:
    """List all available API categories."""
    categories = defaultdict(_init_category_dict)

    # From FlexLibs 2.0
    if api_index.flexlibs2:
        fl2_cats = api_index.flexlibs2.get(KEY_CATEGORIES, {})
        for cat_name, cat_data in fl2_cats.items():
            categories[cat_name][KEY_FLEXLIBS2_COUNT] = len(cat_data.get(KEY_ENTITIES, []))

    # From LibLCM
    if api_index.liblcm:
        for entity in api_index.liblcm.get(KEY_ENTITIES, {}).values():
            cat = entity.get(KEY_CATEGORY, "uncategorized")
            categories[cat][KEY_LIBLCM_COUNT] += 1

    return [TextContent(type="text", text=json.dumps({
        KEY_CATEGORIES: dict(categories),
        KEY_TOTAL_CATEGORIES: len(categories)
    }, indent=2))]


async def handle_list_entities_in_category(args: ListEntitiesInCategoryInput) -> list[TextContent]:
    """List all entities in a specific category."""
    category = args.category.lower()

    entities = {"flexlibs2": [], "liblcm": []}

    # From FlexLibs 2.0
    if api_index.flexlibs2:
        for entity_name, entity in api_index.flexlibs2.get(KEY_ENTITIES, {}).items():
            if entity.get(KEY_CATEGORY, "").lower() == category:
                entities["flexlibs2"].append({
                    KEY_NAME: entity_name,
                    KEY_METHODS_COUNT: len(entity.get("methods", [])),
                    KEY_SUMMARY: _get_entity_summary(entity)
                })

    # From LibLCM
    if api_index.liblcm:
        for entity_name, entity in api_index.liblcm.get(KEY_ENTITIES, {}).items():
            if entity.get(KEY_CATEGORY, "").lower() == category:
                entities["liblcm"].append({
                    KEY_NAME: entity_name,
                    KEY_TYPE: entity.get(KEY_TYPE),
                    KEY_SUMMARY: _get_entity_summary(entity)
                })

    return [TextContent(type="text", text=json.dumps({
        KEY_CATEGORY: category,
        KEY_ENTITIES: entities,
        KEY_COUNTS: {
            "flexlibs2": len(entities["flexlibs2"]),
            "liblcm": len(entities["liblcm"])
        }
    }, indent=2))]
