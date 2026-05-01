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

try:
    from ..response_keys import (
        KEY_NAME, KEY_TYPE, KEY_DESCRIPTION, KEY_SUMMARY, KEY_CATEGORY,
        KEY_FLEXLIBS2_COUNT, KEY_LIBLCM_COUNT, KEY_FLEXLIBS_STABLE_COUNT,
        KEY_METHODS_COUNT,
        KEY_CATEGORIES, KEY_ENTITIES, KEY_COUNTS, KEY_TOTAL_CATEGORIES,
        KEY_FLEXLIBS2, KEY_LIBLCM, KEY_FLEXLIBS_STABLE, KEY_API_MODE,
    )
except ImportError:
    from server.response_keys import (
        KEY_NAME, KEY_TYPE, KEY_DESCRIPTION, KEY_SUMMARY, KEY_CATEGORY,
        KEY_FLEXLIBS2_COUNT, KEY_LIBLCM_COUNT, KEY_FLEXLIBS_STABLE_COUNT,
        KEY_METHODS_COUNT,
        KEY_CATEGORIES, KEY_ENTITIES, KEY_COUNTS, KEY_TOTAL_CATEGORIES,
        KEY_FLEXLIBS2, KEY_LIBLCM, KEY_FLEXLIBS_STABLE, KEY_API_MODE,
    )

try:
    from ..kernel import session_state
except ImportError:
    from server.kernel import session_state

try:
    from .api import active_sources_for_mode, ensure_active_sources_loaded
except ImportError:
    from server.handlers.api import active_sources_for_mode, ensure_active_sources_loaded

# Import with fallback support
get_api_index = safe_import_api_index()

# Type note: api_index is initialized by server.py before any handlers are called

# ============================================================
# Constants (avoid stringly-typed code)
# ============================================================
SUMMARY_MAX_LENGTH = 100

# Response field names imported from response_keys module (see imports above)

# Maps a source name (as returned by active_sources_for_mode) to the response
# count key emitted in list_categories / list_entities_in_category.
_SOURCE_COUNT_KEY = {
    "flexlibs2": KEY_FLEXLIBS2_COUNT,
    "flexlibs_stable": KEY_FLEXLIBS_STABLE_COUNT,
    "liblcm": KEY_LIBLCM_COUNT,
}


def _get_entity_summary(entity: dict) -> str:
    """Extract and normalize entity summary with fallback to description."""
    summary = entity.get(KEY_SUMMARY) or entity.get(KEY_DESCRIPTION) or ""
    return summary[:SUMMARY_MAX_LENGTH]


async def handle_list_categories(args: ListCategoriesInput) -> list[TextContent]:
    """List all available API categories.

    Source-isolated: only counts the source(s) for the active session mode.
    """
    api_index = get_api_index()
    mode = session_state.get_mode()
    ensure_active_sources_loaded(api_index, mode)

    sources = active_sources_for_mode(mode)
    active_count_keys = [_SOURCE_COUNT_KEY[s[0]] for s in sources if s[0] in _SOURCE_COUNT_KEY]

    def _init_category_dict() -> dict:
        return {key: 0 for key in active_count_keys}

    categories = defaultdict(_init_category_dict)

    for source_name, attr, _key in sources:
        index_data = getattr(api_index, attr, None)
        if not index_data:
            continue
        count_key = _SOURCE_COUNT_KEY.get(source_name)
        if not count_key:
            continue

        if source_name == "flexlibs2":
            # flexlibs2 index has a top-level "categories" map with entity lists
            for cat_name, cat_data in index_data.get(KEY_CATEGORIES, {}).items():
                categories[cat_name][count_key] = len(cat_data.get(KEY_ENTITIES, []))
        else:
            # flexlibs_stable and liblcm: bucket entities by their category field
            for entity in index_data.get(KEY_ENTITIES, {}).values():
                cat = entity.get(KEY_CATEGORY, "uncategorized")
                categories[cat][count_key] += 1

    return [TextContent(type="text", text=json.dumps({
        KEY_API_MODE: mode,
        KEY_CATEGORIES: dict(categories),
        KEY_TOTAL_CATEGORIES: len(categories),
    }, indent=2))]


async def handle_list_entities_in_category(args: dict) -> list[TextContent]:
    """List all entities in a specific category.

    Source-isolated: only emits an entry per active source for the session mode.
    """
    api_index = get_api_index()
    mode = session_state.get_mode()
    ensure_active_sources_loaded(api_index, mode)

    category = args.get("category", "").lower()

    sources = active_sources_for_mode(mode)
    entities: dict = {s[0]: [] for s in sources if s[0] in _SOURCE_COUNT_KEY}

    for source_name, attr, _key in sources:
        if source_name not in entities:
            continue
        index_data = getattr(api_index, attr, None)
        if not index_data:
            continue

        for entity_name, entity in index_data.get(KEY_ENTITIES, {}).items():
            entity_category_lower = entity.get(KEY_CATEGORY, "").lower()
            if entity_category_lower != category:
                continue

            if source_name == "liblcm":
                entities[source_name].append({
                    KEY_NAME: entity_name,
                    KEY_TYPE: entity.get(KEY_TYPE),
                    KEY_SUMMARY: _get_entity_summary(entity),
                })
            else:
                entities[source_name].append({
                    KEY_NAME: entity_name,
                    KEY_METHODS_COUNT: len(entity.get("methods", [])),
                    KEY_SUMMARY: _get_entity_summary(entity),
                })

    return [TextContent(type="text", text=json.dumps({
        KEY_API_MODE: mode,
        KEY_CATEGORY: category,
        KEY_ENTITIES: entities,
        KEY_COUNTS: {name: len(items) for name, items in entities.items()},
    }, indent=2))]
