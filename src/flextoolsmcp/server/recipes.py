#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recipe serving helpers (issue #52).

Recipes are curated, runnable, bare-snippet starting points for the ~20
dominant search intents (see ``curated_recipes.CURATED_RECIPES``, the
single source of truth). This module answers two questions for the
handlers in ``server.handlers.api``:

  1. ``search_by_capability``: does the query match a recipe closely enough
     to attach the FULL recipe to the top hit? (one recipe max per response)
  2. ``find_examples``: do the ``operation_type``/``object_type`` filters
     match any recipes? (returned as a list, thinner rows -- callers
     already filtered by shape)

Matching is deliberately simple (substring / token overlap over
``match_terms``, ``entities``, ``operations``) -- the same style as
``worked_examples.py`` -- rather than another synonym-expansion pass,
since recipes are a much smaller, curated set than the full method index.
"""

import re
from typing import Any, Dict, List, Optional

try:
    from ..curated_recipes import CURATED_RECIPES
except ImportError:  # pragma: no cover - script-mode fallback
    from curated_recipes import CURATED_RECIPES


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _words(text: str) -> set:
    return set(_normalize(text).split())


def _recipe_matches_query(recipe: Dict[str, Any], query_words: set) -> bool:
    """True if all the (non-trivial) words of some match_term appear
    somewhere in the query's word set.

    Word-set containment rather than a raw substring test: match_terms are
    written as short canonical phrases ("list entries"), but real queries
    interpose other words ("list ALL entries WITH their glosses") -- a
    substring test would miss that. Order/adjacency doesn't matter, only
    that every word the term contributes is present in the query.
    """
    for term in recipe.get("match_terms", []):
        term_words = _words(term)
        if term_words and term_words.issubset(query_words):
            return True
    return False


def find_recipe_for_search(query: str) -> Optional[Dict[str, Any]]:
    """Return the single best-matching recipe for a search_by_capability query.

    Matches when some recipe's ``match_terms`` overlap the (normalized)
    query text. The curated recipe set's match_terms are written to cover
    the same high-frequency phrases as ``CANONICAL_INTENTS`` (list entries,
    list texts, list wordforms, sense gloss, ...), so a query that lands in
    the canonical-intent tier will, in practice, also match a recipe here --
    satisfying the spec's "canonical-intent tier OR match_terms overlap"
    condition without needing a second, entity-based lookup path.

    Returns None when no recipe matches. Only ever returns one recipe (the
    first match in declaration order) -- callers attach it to the TOP hit
    only, per the spec ("one recipe max per response").
    """
    query_words = _words(query)
    if not query_words:
        return None

    for recipe_id, recipe in CURATED_RECIPES.items():
        if _recipe_matches_query(recipe, query_words):
            return {"id": recipe_id, **recipe}

    return None


def find_recipes_for_examples(
    operation_type: str = "",
    object_type: str = "",
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """Return recipes matching find_examples' operation_type/object_type filters.

    Both filters are optional; an empty filter matches everything for that
    dimension. object_type is matched case-insensitively against the
    recipe's ``entities`` list (substring both ways, e.g. "Sense" matches
    "LexSense"). operation_type is matched against the recipe's
    ``operations`` list the same way.
    """
    object_type_lower = object_type.lower() if object_type else None
    operation_type_lower = operation_type.lower() if operation_type else None

    if not object_type_lower and not operation_type_lower:
        return []

    matches: List[Dict[str, Any]] = []
    for recipe_id, recipe in CURATED_RECIPES.items():
        if object_type_lower:
            entities_lower = [e.lower() for e in recipe.get("entities", [])]
            if not any(object_type_lower in e or e in object_type_lower for e in entities_lower):
                continue
        if operation_type_lower:
            operations_lower = [o.lower() for o in recipe.get("operations", [])]
            if not any(operation_type_lower in o or o in operation_type_lower for o in operations_lower):
                continue
        matches.append({"id": recipe_id, **recipe})
        if len(matches) >= max_results:
            break

    return matches
