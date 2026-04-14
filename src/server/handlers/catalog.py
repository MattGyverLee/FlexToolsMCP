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

from ._import_helper import safe_import_api_index
from ..models import ListCategoriesInput, ListEntitiesInCategoryInput
from ..response_keys import (
    KEY_NAME, KEY_TYPE, KEY_DESCRIPTION, KEY_SUMMARY, KEY_CATEGORY,
    KEY_FLEXLIBS2_COUNT, KEY_LIBLCM_COUNT, KEY_METHODS_COUNT,
    KEY_CATEGORIES, KEY_ENTITIES, KEY_COUNTS, KEY_TOTAL_CATEGORIES
)

# Import with fallback support
get_api_index = safe_import_api_index()

# Type note: api_index is initialized by server.py before any handlers are called

# ============================================================
# Constants (avoid stringly-typed code)
# ============================================================
SUMMARY_MAX_LENGTH = 100

# Response field names imported from response_keys module (see imports above)


def _init_category_dict() -> dict:
    """Initialize empty category with zero counts."""
    return {KEY_FLEXLIBS2_COUNT: 0, KEY_LIBLCM_COUNT: 0}


def _get_entity_summary(entity: dict) -> str:
    """Extract and normalize entity summary with fallback to description."""
    summary = entity.get(KEY_SUMMARY) or entity.get(KEY_DESCRIPTION) or ""
    return summary[:SUMMARY_MAX_LENGTH]


async def handle_list_categories(args: ListCategoriesInput) -> list[TextContent]:
    """List all available API categories."""
    # Lazy-load APIs if needed (they're deferred from startup for speed)
    get_api_index().ensure_liblcm_loaded()

    categories = defaultdict(_init_category_dict)

    # From FlexLibs 2.0
    if get_api_index().flexlibs2:
        fl2_cats = get_api_index().flexlibs2.get(KEY_CATEGORIES, {})
        for cat_name, cat_data in fl2_cats.items():
            categories[cat_name][KEY_FLEXLIBS2_COUNT] = len(cat_data.get(KEY_ENTITIES, []))

    # From LibLCM
    if get_api_index().liblcm:
        for entity in get_api_index().liblcm.get(KEY_ENTITIES, {}).values():
            cat = entity.get(KEY_CATEGORY, "uncategorized")
            categories[cat][KEY_LIBLCM_COUNT] += 1

    return [TextContent(type="text", text=json.dumps({
        KEY_CATEGORIES: dict(categories),
        KEY_TOTAL_CATEGORIES: len(categories)
    }, indent=2))]


async def handle_list_entities_in_category(args: dict) -> list[TextContent]:
    """List all entities in a specific category."""
    # Lazy-load APIs if needed (they're deferred from startup for speed)
    get_api_index().ensure_liblcm_loaded()

    category = args.get("category", "").lower()

    entities = {"flexlibs2": [], "liblcm": []}

    # From FlexLibs 2.0
    if get_api_index().flexlibs2:
        fl2_entities = get_api_index().flexlibs2.get(KEY_ENTITIES, {})
        for entity_name, entity in fl2_entities.items():
            # Pre-lowercase category once and cache to avoid repeated .lower() calls per entity
            entity_category_lower = entity.get(KEY_CATEGORY, "").lower()
            if entity_category_lower == category:
                entities["flexlibs2"].append({
                    KEY_NAME: entity_name,
                    KEY_METHODS_COUNT: len(entity.get("methods", [])),
                    KEY_SUMMARY: _get_entity_summary(entity)
                })

    # From LibLCM
    if get_api_index().liblcm:
        liblcm_entities = get_api_index().liblcm.get(KEY_ENTITIES, {})
        for entity_name, entity in liblcm_entities.items():
            # Pre-lowercase category once and cache to avoid repeated .lower() calls per entity
            entity_category_lower = entity.get(KEY_CATEGORY, "").lower()
            if entity_category_lower == category:
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
