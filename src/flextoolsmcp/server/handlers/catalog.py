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
from ..models import (
    ListCategoriesInput,
    ListEntitiesInCategoryInput,
    ListProjectsInput,
    ListSkeletonsInput,
)

try:
    from .. import skeleton_storage
except ImportError:
    from server import skeleton_storage

try:
    from ..response_keys import (
        KEY_NAME, KEY_TYPE, KEY_DESCRIPTION, KEY_SUMMARY, KEY_CATEGORY,
        KEY_FLEXICON_COUNT, KEY_LIBLCM_COUNT, KEY_FLEXLIBS_STABLE_COUNT,
        KEY_METHODS_COUNT,
        KEY_CATEGORIES, KEY_ENTITIES, KEY_COUNTS, KEY_TOTAL_CATEGORIES,
        KEY_FLEXICON, KEY_LIBLCM, KEY_FLEXLIBS_STABLE, KEY_API_MODE,
    )
except ImportError:
    from server.response_keys import (
        KEY_NAME, KEY_TYPE, KEY_DESCRIPTION, KEY_SUMMARY, KEY_CATEGORY,
        KEY_FLEXICON_COUNT, KEY_LIBLCM_COUNT, KEY_FLEXLIBS_STABLE_COUNT,
        KEY_METHODS_COUNT,
        KEY_CATEGORIES, KEY_ENTITIES, KEY_COUNTS, KEY_TOTAL_CATEGORIES,
        KEY_FLEXICON, KEY_LIBLCM, KEY_FLEXLIBS_STABLE, KEY_API_MODE,
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
    "flexicon": KEY_FLEXICON_COUNT,
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

        if source_name == "flexicon":
            # flexicon index has a top-level "categories" map with entity lists
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


async def handle_list_projects(args: dict) -> list[TextContent]:
    """List FieldWorks projects without opening them.

    Safe by construction: scans the projects directory and checks for
    <name>/<name>.fwdata file existence only. Never loads the LCM cache,
    so .fwdata mtimes are not modified (see P10-Export-FLEx issue #13).
    """
    try:
        from ..project_discovery import list_projects, get_last_directory
    except ImportError:
        from server.project_discovery import list_projects, get_last_directory

    # Dispatch may pass a Pydantic model or a dict — handle both.
    raw_filter = args.get("name_contains") if isinstance(args, dict) else getattr(args, "name_contains", None)
    name_contains = (raw_filter or "").strip()

    names, source = list_projects()
    if name_contains:
        needle = name_contains.casefold()
        names = [n for n in names if needle in n.casefold()]

    return [TextContent(type="text", text=json.dumps({
        "projects": names,
        "count": len(names),
        "source": source,
        "projects_directory": get_last_directory(),
        "safety_note": (
            "Listing is read-only: only directory entries and .fwdata file "
            "existence are checked. No project files are opened, so .fwdata "
            "modification times are not affected."
        ),
    }, indent=2))]


async def handle_list_skeletons(
    args: ListSkeletonsInput | dict,
) -> list[TextContent]:
    """List captured skeleton helpers from the storage closet (issue #24).

    Read-only: enumerates JSONL entries on disk, most-recent-first, no
    filtering beyond ``limit``. For entity-aware retrieval, see
    ``flextools_find_examples`` -- it weaves skeletons into normal examples.
    """
    # Support both Pydantic model and dict (legacy dispatch paths).
    limit = args.limit if hasattr(args, "limit") else (args or {}).get("limit", 100)
    try:
        entries = skeleton_storage.list_all_skeletons(limit=limit)
    except Exception as exc:
        # Log before returning -- otherwise the .log has no trace of the
        # failure and the only signal is the error JSON in the MCP response.
        try:
            from ..kernel import get_operations_logger
        except (ImportError, ValueError):
            from server.kernel import get_operations_logger
        op_logger = get_operations_logger()
        if op_logger:
            op_logger.error(
                f"handle_list_skeletons: list_all_skeletons(limit={limit}) failed: {exc}",
                exc_info=True,
            )
        return [TextContent(type="text", text=json.dumps({
            "error": f"Failed to load skeletons: {exc}",
            "skeletons": [],
            "count": 0,
        }, indent=2))]

    return [TextContent(type="text", text=json.dumps({
        "count": len(entries),
        "limit": limit,
        "storage_path": str(skeleton_storage.get_skeleton_path()),
        "skeletons": entries,
    }, indent=2))]
