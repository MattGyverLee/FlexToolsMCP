#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generation-time preflight validator for recipes (issue #52).

Every shipped recipe (``curated_recipes.CURATED_RECIPES``) must pass this
check before it can be served through ``search_by_capability`` /
``find_examples``. It runs the recipe's ``code`` through the same static
validators the live ``run_module`` preflight chain uses
(``server.validators``), so a recipe that would be rejected at run time can
never ship.

This is intentionally a subset of the full ``run_module`` preflight
(``server/handlers/execution.py``): recipes are bare snippets (no ``Main``/
``docs``/``FlexToolsModule`` scaffold), so the module-structure and
session/undiscovered-entity checks (which require a live session_state) do
not apply here. What DOES apply, and is checked:

  - the code parses as valid Python (``ast.parse``)
  - CUD detection (``detect_cud_operations``) agrees with the recipe's
    declared ``requires_write`` flag
  - any write is guarded by ``if modifyAllowed:`` (``certify_script_readonly``)
  - no Operations class is used without being imported
    (``detect_missing_operations_imports``)
  - no import comes from the wrong library for the recipe's API mode
    (``detect_wrong_library_imports``) -- recipes are flexicon-only per
    CLAUDE.md, so ``api_mode`` is always "flexicon" here
  - no obviously-undefined internal/MCP variable names
    (``detect_undefined_variables``)
  - every ``project.<X>`` accessor chain resolves against the real
    FLExProject property list (``detect_invalid_project_chains``)
"""

import ast
from typing import Any, Dict, List

if __package__:
    from .server.validators import (
        detect_cud_operations,
        certify_script_readonly,
        detect_missing_operations_imports,
        detect_wrong_library_imports,
        detect_undefined_variables,
        detect_invalid_project_chains,
    )
else:
    from server.validators import (
        detect_cud_operations,
        certify_script_readonly,
        detect_missing_operations_imports,
        detect_wrong_library_imports,
        detect_undefined_variables,
        detect_invalid_project_chains,
    )


def validate_recipe(recipe: Dict[str, Any], api_index: Any = None) -> Dict[str, Any]:
    """Run the preflight validator chain against one recipe.

    Args:
        recipe: a recipe dict shaped like ``curated_recipes.CURATED_RECIPES``
            values (must have ``code`` and ``requires_write``).
        api_index: loaded ``APIIndex``-like object (needs ``.flexicon`` for
            ``certify_script_readonly`` mutation lookups and
            ``detect_invalid_project_chains`` accessor validation). May be
            ``None`` -- checks that need it degrade to regex-only detection.

    Returns:
        {"passed": bool, "issues": [str, ...]}
    """
    issues: List[str] = []
    code = recipe.get("code", "")

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"passed": False, "issues": [f"SyntaxError: {e}"]}

    requires_write = bool(recipe.get("requires_write", False))

    # detect_cud_operations is regex-based and only recognizes a subset of
    # mutating call shapes (literal .Create(/.Delete(/.Set*( etc.) -- it can
    # miss genuine mutations named e.g. AddSemanticDomain. That's a detection
    # gap, not a safety issue: certify_script_readonly (below) is the
    # authoritative, index-backed check for whether a call actually mutates
    # and whether it's guarded. So we only flag the DANGEROUS direction here:
    # a recipe declaring requires_write=False whose code the regex still
    # recognizes as CUD.
    cud_info = detect_cud_operations(code)
    if cud_info["is_cud"] and not requires_write:
        issues.append(
            f"requires_write=False but detect_cud_operations found "
            f"is_cud=True (operations={cud_info['operations']})"
        )

    cert = certify_script_readonly(code, api_index, tree)
    if not cert["is_certified_readonly"]:
        mutating = [m for m in cert.get("mutating_calls", []) if m.get("is_mutating")]
        unprotected_lcm = cert.get("unprotected_liblcm_calls", []) or []
        issues.append(
            f"unprotected mutation(s): flexicon={[m.get('method') for m in mutating]} "
            f"unprotected_lcm={unprotected_lcm}"
        )

    missing_ops = detect_missing_operations_imports(code, "flexicon")
    if missing_ops["has_missing"]:
        issues.append(f"missing operations imports: {missing_ops['missing_imports']}")

    wrong_imports = detect_wrong_library_imports(code, "flexicon")
    if wrong_imports["has_wrong_imports"]:
        issues.append(f"wrong-library imports: {wrong_imports['wrong_imports']}")

    undefined = detect_undefined_variables(code, tree)
    if undefined["has_undefined"]:
        issues.append(f"undefined variables: {undefined['undefined_vars']}")

    chain_check = detect_invalid_project_chains(tree, api_index)
    if chain_check["has_invalid"]:
        issues.append(f"invalid project.<X> chain(s): {chain_check['issues']}")

    return {"passed": len(issues) == 0, "issues": issues}


def validate_all(recipes: Dict[str, Dict[str, Any]], api_index: Any = None) -> Dict[str, Dict[str, Any]]:
    """Run ``validate_recipe`` over a whole recipes dict.

    Returns a dict of {recipe_id: result} for every recipe that FAILED (the
    happy path -- an empty dict -- means every recipe passed).
    """
    failures: Dict[str, Dict[str, Any]] = {}
    for recipe_id, recipe in recipes.items():
        result = validate_recipe(recipe, api_index)
        if not result["passed"]:
            failures[recipe_id] = result
    return failures
