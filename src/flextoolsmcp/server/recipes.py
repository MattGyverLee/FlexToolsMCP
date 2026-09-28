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

import math
import re
from typing import Any, Callable, Dict, List, Optional

try:
    from ..curated_recipes import CURATED_RECIPES
except ImportError:  # pragma: no cover - script-mode fallback
    from curated_recipes import CURATED_RECIPES

try:
    from ..recipe_files import extract_code_terms as _extract_code_terms
except ImportError:  # pragma: no cover - script-mode fallback
    try:
        from recipe_files import extract_code_terms as _extract_code_terms
    except ImportError:
        _extract_code_terms = None  # type: ignore


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _words(text: str) -> set:
    return set(_normalize(text).split())


# ---------------------------------------------------------------------------
# Unified ranked search (unified-recipes Phase 3, FR-020/FR-021, research R10).
# The old first-match attachment above is kept byte-identical (FR-022); the
# ranker below feeds only the new `recipes` keys.
# ---------------------------------------------------------------------------

STOPWORDS = frozenset({
    "the", "a", "all", "with", "their", "of", "for", "to", "and",
    "my", "in", "on", "which", "what", "how",
})

TASK_WEIGHT = 2.0
CODE_WEIGHT = 1.5
OBJECT_WEIGHT = 0.25
PHRASE_WEIGHT = 4.0
FLOOR_WORD_SCORE = 2.0
CLEAR_MIN_SCORE = 3.0
CLEAR_RATIO = 1.5
SHIPPED_BOOST = 1.0

RECIPES_HINT = (
    "Several recipes match; refine the query or fetch one with "
    "flextools_list_recipes(recipe_id=...)"
)

# Pluggable local-recipe provider (US2: wired to local_recipes store).
# Tests inject records directly via search_recipes(local_recipes=[...]).
_LOCAL_PROVIDER: Optional[Callable[[], List[Dict[str, Any]]]] = None


def set_local_recipe_provider(fn: Optional[Callable[[], List[Dict[str, Any]]]]) -> None:
    global _LOCAL_PROVIDER
    _LOCAL_PROVIDER = fn


def _default_local_records() -> List[Dict[str, Any]]:
    """US2 seam: load local recipes from the store (best-effort)."""
    try:
        try:
            from . import local_recipes as _lr  # type: ignore
        except ImportError:
            from server import local_recipes as _lr  # type: ignore
        try:
            rows = _lr.load_local_recipes()
        except Exception:
            return []
        return rows if isinstance(rows, list) else []
    except Exception:
        return []


def _singularize(word: str) -> str:
    w = word
    if len(w) <= 3:
        return w
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    low = w.lower()
    if low.endswith(("sses", "xes", "zes", "ches", "shes")):
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def tokenize(text: str) -> List[str]:
    out: List[str] = []
    for raw in re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split():
        if not raw or raw in STOPWORDS:
            continue
        out.append(_singularize(raw))
    return out


def tokenize_set(text: str) -> set:
    return set(tokenize(text))


def _split_entity(name: str) -> List[str]:
    parts = str(name).split("_")
    terms: List[str] = []
    for part in parts:
        spaced = re.sub(
            r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", part
        )
        for tok in spaced.split():
            low = tok.lower()
            if low and low not in STOPWORDS:
                terms.append(_singularize(low))
    return terms


def _object_words(recipe: Dict[str, Any]) -> set:
    words: set = set()
    for ent in recipe.get("entities", []) or []:
        words.update(_split_entity(ent))
    for tok in re.sub(r"[^a-z0-9]+", " ", str(recipe.get("id", "")).lower()).split():
        if tok and tok not in STOPWORDS:
            words.add(_singularize(tok))
    return words


def _code_words(recipe: Dict[str, Any]) -> set:
    terms = recipe.get("code_terms")
    if not terms:
        code = recipe.get("code", "") or ""
        if _extract_code_terms is not None:
            try:
                terms = _extract_code_terms(code)
            except Exception:
                terms = []
        else:
            terms = []
    words: set = set()
    for t in terms or []:
        low = str(t).lower()
        if low and low not in STOPWORDS:
            words.add(_singularize(low))
    return words


def _task_words(recipe: Dict[str, Any]) -> set:
    words: set = set()
    intent = recipe.get("intent") or ""
    words.update(tokenize_set(intent))
    for term in recipe.get("match_terms", []) or []:
        words.update(tokenize_set(term))
    return words


def _match_phrases(recipe: Dict[str, Any]) -> List[set]:
    phrases: List[set] = []
    for term in recipe.get("match_terms", []) or []:
        toks = tokenize_set(term)
        if toks:
            phrases.append(toks)
    return phrases


def compute_idf(recipes: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    n = len(recipes)
    if n == 0:
        return {}
    df: Dict[str, int] = {}
    for recipe in recipes.values():
        vocab = _task_words(recipe) | _code_words(recipe) | _object_words(recipe)
        for w in vocab:
            df[w] = df.get(w, 0) + 1
    return {w: math.log(1.0 + n / c) for w, c in df.items()}


def _local_boost(recipe: Dict[str, Any]) -> float:
    try:
        use_count = int(recipe.get("use_count", 0) or 0)
    except Exception:
        use_count = 0
    return min(2.0, 0.5 * math.log2(1.0 + max(0, use_count)))


def _is_shipped(recipe: Dict[str, Any]) -> bool:
    return str(recipe.get("source", "curated")) in ("curated", "shipped")


def _score_one(query_words: set, recipe: Dict[str, Any],
               idf: Dict[str, float]) -> Dict[str, Any]:
    task = _task_words(recipe)
    code = _code_words(recipe)
    objects = _object_words(recipe)
    phrases = _match_phrases(recipe)
    phrase_score = 0.0
    has_phrase = False
    for phrase in phrases:
        if phrase and phrase.issubset(query_words):
            has_phrase = True
            mean_idf = sum(idf.get(w, 0.0) for w in phrase) / len(phrase)
            phrase_score += PHRASE_WEIGHT * mean_idf
    word_score = 0.0
    non_object = False
    for q in query_words:
        if q in task:
            word_score += idf.get(q, 0.0) * TASK_WEIGHT
            non_object = True
        elif q in code:
            word_score += idf.get(q, 0.0) * CODE_WEIGHT
            non_object = True
        elif q in objects:
            word_score += idf.get(q, 0.0) * OBJECT_WEIGHT
    if phrase_score > 0:
        # A phrase hit is itself a non-object (task-text) contribution.
        non_object = True
    total = phrase_score + word_score
    if _is_shipped(recipe):
        total += SHIPPED_BOOST
    else:
        total += _local_boost(recipe)
        intent = recipe.get("intent")
        if intent is None or not str(intent).strip():
            total -= 1.0
    return {
        "total": total,
        "word_score": word_score,
        "has_phrase": has_phrase,
        "non_object": non_object,
    }


def _all_ranked_recipes(local_recipes: Optional[List[Dict[str, Any]]] = None
                        ) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = dict(CURATED_RECIPES)
    locals_list: List[Dict[str, Any]] = []
    if local_recipes is not None:
        locals_list = local_recipes
    elif _LOCAL_PROVIDER is not None:
        try:
            locals_list = _LOCAL_PROVIDER() or []
        except Exception:
            locals_list = []
    for rec in locals_list:
        rid = rec.get("id")
        if rid and rid not in merged:
            merged[rid] = rec
    return merged


def rank_recipes(query: str,
                 recipes: Optional[Dict[str, Dict[str, Any]]] = None,
                 local_recipes: Optional[List[Dict[str, Any]]] = None
                 ) -> List[Dict[str, Any]]:
    if recipes is None:
        recipes = _all_ranked_recipes(local_recipes)
    query_words = set(tokenize(query))
    if not query_words or not recipes:
        return []
    idf = compute_idf(recipes)
    scored: List[Dict[str, Any]] = []
    for rid, recipe in recipes.items():
        s = _score_one(query_words, recipe, idf)
        # Floor (R10): a phrase hit, or a real word match whose boosted total
        # clears the floor. Requiring word_score > 0 keeps boost-only rows
        # (e.g. a high-use local recipe for a nonsense query) out while
        # letting object-word queries like "entry" through via task/code hits.
        if not s["has_phrase"] and not (s["word_score"] > 0 and s["total"] >= FLOOR_WORD_SCORE):
            continue
        scored.append({
            "id": rid,
            "_score": s["total"],
            "_has_phrase": s["has_phrase"],
            "_non_object": s["non_object"],
            "recipe": recipe,
        })
    scored.sort(key=lambda r: (-r["_score"],
                               0 if _is_shipped(r["recipe"]) else 1,
                               r["id"]))
    return scored


def _compact_params(params: Any) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
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


def _shipped_label(recipe: Dict[str, Any]) -> str:
    return "shipped" if _is_shipped(recipe) else "local"


def to_compact_row(recipe_id: str, recipe: Dict[str, Any], score: float,
                   code_at: Optional[str] = None) -> Dict[str, Any]:
    label = _shipped_label(recipe)
    row: Dict[str, Any] = {
        "id": recipe_id,
        "intent": recipe.get("intent") or "",
        "source": label,
        "requires_write": bool(recipe.get("requires_write", False)),
        "params": _compact_params(recipe.get("params", [])),
        "entities": list(recipe.get("entities", []) or []),
        "use_count": None if label == "shipped" else int(recipe.get("use_count", 0) or 0),
        "last_used": None if label == "shipped" else recipe.get("last_used"),
        "score": score,
    }
    if code_at:
        row["code_at"] = code_at
    return row


def to_full_row(recipe_id: str, recipe: Dict[str, Any], score: float,
                code_at: Optional[str] = None) -> Dict[str, Any]:
    row = to_compact_row(recipe_id, recipe, score, code_at=code_at)
    if code_at:
        return row
    row["code"] = recipe.get("code", "")
    row["notes"] = recipe.get("notes", "")
    row["match_terms"] = list(recipe.get("match_terms", []) or [])
    row["operations"] = list(recipe.get("operations", []) or [])
    if recipe.get("origin") is not None:
        row["origin"] = recipe.get("origin")
    if recipe.get("verified_against") is not None:
        row["verified_against"] = recipe.get("verified_against")
    return row


def search_recipes(query: str,
                   local_recipes: Optional[List[Dict[str, Any]]] = None,
                   legacy_recipe_id: Optional[str] = None,
                   limit: int = 3) -> Dict[str, Any]:
    ranked = rank_recipes(query, local_recipes=local_recipes)
    rows_all = ranked[: max(0, limit)]
    if not rows_all:
        return {"recipes": [], "recipes_count": 0, "recipes_ambiguous": False}
    top = rows_all[0]
    second_score = rows_all[1]["_score"] if len(rows_all) > 1 else None
    clear = (
        top["_score"] >= CLEAR_MIN_SCORE
        and top["_non_object"]
        and (second_score is None or top["_score"] >= CLEAR_RATIO * second_score)
    )
    rows: List[Dict[str, Any]] = []
    for i, entry in enumerate(rows_all):
        rid = entry["id"]
        recipe = entry["recipe"]
        score = entry["_score"]
        if i == 0 and clear:
            if legacy_recipe_id is not None and rid == legacy_recipe_id:
                rows.append(to_compact_row(rid, recipe, score,
                                           code_at="results[0].recipe"))
            else:
                rows.append(to_full_row(rid, recipe, score))
        else:
            rows.append(to_compact_row(rid, recipe, score))
    ambiguous = not clear
    result: Dict[str, Any] = {
        "recipes": rows,
        "recipes_count": len(rows),
        "recipes_ambiguous": ambiguous,
    }
    if ambiguous:
        result["recipes_hint"] = RECIPES_HINT
    return result


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
