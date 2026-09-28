#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Catalog handler functions for FlexToolsMCP.

These handlers provide listing and discovery of available APIs:
- list_categories: List all API categories
- list_entities_in_category: List entities within a specific category
"""

import difflib
import json
from collections import defaultdict
from mcp.types import TextContent

from ._import_helper import safe_import_api_index
from ..models import (
    ListCategoriesInput,
    ListSkeletonsInput,
)

try:
    from .. import local_recipes
except ImportError:
    from server import local_recipes

try:
    from ..response_keys import (
        KEY_NAME, KEY_TYPE, KEY_DESCRIPTION, KEY_SUMMARY, KEY_CATEGORY,
        KEY_FLEXICON_COUNT, KEY_LIBLCM_COUNT, KEY_FLEXLIBS_STABLE_COUNT,
        KEY_METHODS_COUNT,
        KEY_CATEGORIES, KEY_ENTITIES, KEY_COUNTS, KEY_TOTAL_CATEGORIES,
        KEY_API_MODE,
    )
except ImportError:
    from server.response_keys import (
        KEY_NAME, KEY_TYPE, KEY_DESCRIPTION, KEY_SUMMARY, KEY_CATEGORY,
        KEY_FLEXICON_COUNT, KEY_LIBLCM_COUNT, KEY_FLEXLIBS_STABLE_COUNT,
        KEY_METHODS_COUNT,
        KEY_CATEGORIES, KEY_ENTITIES, KEY_COUNTS, KEY_TOTAL_CATEGORIES,
        KEY_API_MODE,
    )

try:
    from ..kernel import session_state
except ImportError:
    from server.kernel import session_state

try:
    from .api import active_sources_for_mode, ensure_active_sources_loaded
except ImportError:
    from server.handlers.api import active_sources_for_mode, ensure_active_sources_loaded

try:
    from ...response_utils import build_response_with_context, error_response, json_response
except ImportError:
    try:
        from response_utils import build_response_with_context, error_response, json_response
    except ImportError:
        from server.response_utils import build_response_with_context, error_response, json_response

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
    """List local recipes in the legacy skeleton row shape (US2, deprecated alias).

    Read-only: enumerates recipes.jsonl on disk, most-recent-first, no
    filtering beyond ``limit``.
    """
    # Support both Pydantic model and dict (legacy dispatch paths).
    limit = args.limit if hasattr(args, "limit") else (args or {}).get("limit", 100)
    try:
        rows = local_recipes.list_local_recipes(limit=limit)
        entries = [{
            "name": r.get("id"),
            "source": r.get("code"),
            "entities": r.get("entities", []),
            "user_intent": r.get("intent"),
            "captured_at": r.get("last_used", ""),
            "op_id": (r.get("op_ids", [""])[-1] if r.get("op_ids") else ""),
            "session_id": "",
            "duration_ms": 0,
        } for r in rows]
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
        "storage_path": str(local_recipes.get_recipe_path()),
        "skeletons": entries,
        "deprecation": {
            "deprecated": "flextools_list_skeletons",
            "replacement": "flextools_list_recipes(source=\"local\")",
            "removal": "tool-responses/2.0",
        },
    }, indent=2))]


# ============================================================
# flextools_list_recipes (unified-recipes Phase 6, FR-024/FR-026)
# ============================================================

def _list_compact_params(params):
    rows = []
    for p in params or []:
        if not isinstance(p, dict):
            continue
        default = str(p.get("default", ""))
        if len(default) > 60:
            default = default[:60] + "..."
        rows.append({
            "name": str(p.get("name", "")),
            "default": default,
            "description": str(p.get("description", "")),
        })
    return rows


def _list_shipped_label(recipe: dict) -> str:
    return "shipped" if str(recipe.get("source", "curated")) in ("curated", "shipped") else "local"


def _list_compact_row(recipe_id: str, recipe: dict) -> dict:
    label = _list_shipped_label(recipe)
    return {
        "id": recipe_id,
        "intent": recipe.get("intent") or "",
        "source": label,
        "requires_write": bool(recipe.get("requires_write", False)),
        "params": _list_compact_params(recipe.get("params", [])),
        "entities": list(recipe.get("entities", []) or []),
        "use_count": None if label == "shipped" else int(recipe.get("use_count", 0) or 0),
        "last_used": None if label == "shipped" else recipe.get("last_used"),
    }


def _list_full_row(recipe_id: str, recipe: dict) -> dict:
    row = _list_compact_row(recipe_id, recipe)
    row["code"] = recipe.get("code", "")
    row["notes"] = recipe.get("notes", "")
    row["match_terms"] = list(recipe.get("match_terms", []) or [])
    row["operations"] = list(recipe.get("operations", []) or [])
    if recipe.get("origin") is not None:
        row["origin"] = recipe.get("origin")
    if recipe.get("verified_against") is not None:
        row["verified_against"] = recipe.get("verified_against")
    return row


def _list_all_merged() -> dict:
    """All recipes keyed by id: shipped first, then local (no overwrite)."""
    try:
        try:
            from ...curated_recipes import CURATED_RECIPES as _shipped
        except ImportError:
            from curated_recipes import CURATED_RECIPES as _shipped
    except ImportError:
        _shipped = {}
    merged = dict(_shipped or {})
    try:
        local_rows = local_recipes.load_local_recipes()
    except Exception:
        local_rows = []
    for rec in local_rows or []:
        rid = (rec or {}).get("id")
        if rid and rid not in merged:
            merged[rid] = rec
    return merged


async def handle_list_recipes(args) -> list[TextContent]:
    """Browse shipped and local recipes (FR-024); one full recipe by id (FR-026).

    Read-only: compact rows carry no `code` unless `recipe_id` is given.
    Serving a full recipe records its entities as validated discovery.
    Unknown ids give `recipe_not_found` with `closest_matches` + hint.
    """
    get_arg = (lambda k, d=None: getattr(args, k, d)) if hasattr(args, "query") or hasattr(args, "recipe_id") else (lambda k, d=None: (args or {}).get(k, d))
    query = get_arg("query", None)
    source = get_arg("source", None) or "all"
    requires_write = get_arg("requires_write", None)
    limit = get_arg("limit", None)
    recipe_id = get_arg("recipe_id", None)
    if limit is None:
        limit = 50
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 50
    limit = max(1, min(200, limit))

    merged = _list_all_merged()

    if recipe_id:
        recipe = merged.get(recipe_id)
        if recipe is None:
            ids = list(merged.keys())
            closest = difflib.get_close_matches(str(recipe_id), ids, n=3, cutoff=0.3)
            hint = (
                f"No recipe '{recipe_id}'. "
                "Try flextools_list_recipes(query=...) to find one, "
                "or list all ids without filters."
            )
            return error_response(
                "recipe_not_found",
                f"Unknown recipe_id '{recipe_id}'.",
                recipe_id=str(recipe_id),
                closest_matches=closest,
                hint=hint,
            )
        for entity in recipe.get("entities", []) or []:
            try:
                session_state.record_validated_api(entity)
            except Exception:
                pass
        return json_response(build_response_with_context(
            {"recipe": _list_full_row(str(recipe_id), recipe)}))

    if query:
        try:
            try:
                from ..recipes import rank_recipes as _rank
            except ImportError:
                from server.recipes import rank_recipes as _rank
            ranked = _rank(str(query), recipes=dict(merged))
            ordered_ids = [r["id"] for r in ranked]
        except Exception:
            ordered_ids = []
        # Ranked order; unknown ids (should not happen) appended in default order.
        seen = set(ordered_ids)
        for rid in merged:
            if rid not in seen:
                ordered_ids.append(rid)
    else:
        shipped_ids = sorted(rid for rid, r in merged.items()
                             if _list_shipped_label(r) == "shipped")
        try:
            local_rows = local_recipes.load_local_recipes()
        except Exception:
            local_rows = []
        local_by_id = {r.get("id"): r for r in local_rows or [] if (r or {}).get("id")}
        local_ids = sorted(
            (rid for rid in merged if _list_shipped_label(merged[rid]) == "local"),
            key=lambda rid: str((local_by_id.get(rid) or {}).get("last_used", "")),
            reverse=True,
        )
        ordered_ids = shipped_ids + local_ids

    rows = []
    for rid in ordered_ids:
        recipe = merged.get(rid)
        if recipe is None:
            continue
        if source != "all" and _list_shipped_label(recipe) != source:
            continue
        if requires_write is not None and bool(recipe.get("requires_write", False)) != bool(requires_write):
            continue
        rows.append((rid, recipe))

    total = len(rows)
    page = rows[:limit]
    compact = [_list_compact_row(rid, recipe) for rid, recipe in page]
    try:
        storage_path = str(local_recipes.get_recipe_path())
    except Exception:
        storage_path = ""
    return json_response(build_response_with_context({
        "recipes": compact,
        "recipes_count": len(compact),
        "total": total,
        "source": source,
        "storage_path": storage_path,
    }))
