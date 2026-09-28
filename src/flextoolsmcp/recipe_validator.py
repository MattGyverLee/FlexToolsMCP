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
  - no curated-deprecated member is used (``detect_deprecated_members``)

With ``shipped=True`` (unified-recipes FR-041/FR-045, used for file recipes
in CI), the validator ALSO checks:

  - the PARAMS block parses (a present-but-broken block fails)
  - every recipe with ``requires_write`` guards writes with
    ``if modifyAllowed:``
  - no recipe uses an index-deprecated member (``detect_deprecated_members``
    with ``api_index``)
  - no recipe contains a GUID literal, a Windows user path, or the
    ``Claude-Swahili``/``Target`` defaults (shared scrub patterns)
  - no recipe calls ``print()`` (``detect_print_calls`` -- report via
    ``report.*`` per FR-051)
  - raw LibLCM use is minimal (``detect_raw_lcm_access`` plus the
    ``raw_lcm_lines`` ratchet)
"""

import ast
from typing import Any, Dict, List

try:
    from .recipe_files import PARAMS_END, PARAMS_START, find_scrub_lines, parse_params
except ImportError:
    from recipe_files import PARAMS_END, PARAMS_START, find_scrub_lines, parse_params

if __package__:
    from .server.validators import (
        detect_cud_operations,
        certify_script_readonly,
        detect_missing_operations_imports,
        detect_wrong_library_imports,
        detect_undefined_variables,
        detect_invalid_project_chains,
        detect_deprecated_members,
        detect_print_calls,
        detect_raw_lcm_access,
    )
else:
    from server.validators import (
        detect_cud_operations,
        certify_script_readonly,
        detect_missing_operations_imports,
        detect_wrong_library_imports,
        detect_undefined_variables,
        detect_invalid_project_chains,
        detect_deprecated_members,
        detect_print_calls,
        detect_raw_lcm_access,
    )


def _check_params_block(code: str) -> List[str]:
    """Fail a present-but-broken PARAMS block (FR-041).

    A missing block is fine (params default to ``[]``); a block that is
    unclosed, misordered, unparsable, or defines no parameters is malformed.
    """
    lines = code.splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == PARAMS_START]
    ends = [i for i, line in enumerate(lines) if line.strip() == PARAMS_END]
    if not starts:
        return []
    if not ends:
        return ["PARAMS block opened with '# --- PARAMS ---' but never closed"]
    if ends[0] <= starts[0]:
        return ["PARAMS block ends before it starts"]
    block_text = "\n".join(lines[starts[0] + 1 : ends[0]])
    try:
        ast.parse(block_text)
    except SyntaxError as e:
        return [f"PARAMS block does not parse: {e}"]
    params = parse_params(code)
    if not params and any(
        stripped and not stripped.startswith("#")
        for stripped in (line.strip() for line in lines[starts[0] + 1 : ends[0]])
    ):
        return ["PARAMS block defines no parameters"]
    return []


def validate_recipe(
    recipe: Dict[str, Any], api_index: Any = None, shipped: bool = False
) -> Dict[str, Any]:
    """Run the preflight validator chain against one recipe.

    Args:
        recipe: a recipe dict shaped like ``curated_recipes.CURATED_RECIPES``
            values (must have ``code`` and ``requires_write``).
        api_index: loaded ``APIIndex``-like object (needs ``.flexicon`` for
            ``certify_script_readonly`` mutation lookups and
            ``detect_invalid_project_chains`` accessor validation). May be
            ``None`` -- checks that need it degrade to regex-only detection.
        shipped: when True, also run the shipped-recipe gate (FR-041/FR-045):
            PARAMS, ``modifyAllowed`` guard, index-driven deprecation, scrub
            patterns, ``print()`` ban, and the raw-LCM gate with the
            ``raw_lcm_lines`` ratchet.

    Returns:
        {"passed": bool, "issues": [str, ...], "notes": [str, ...]} ("notes"
        carries non-failing ratchet advice, e.g. lowering ``raw_lcm_lines``).
    """
    issues: List[str] = []
    notes: List[str] = []
    code = recipe.get("code", "")

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        syntax_issues = [f"SyntaxError: {e}"]
        if shipped:
            # A broken PARAMS block usually breaks the whole-file parse too;
            # name it so the fix location is obvious.
            syntax_issues.extend(_check_params_block(code))
        return {"passed": False, "issues": syntax_issues, "notes": notes}

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

    deprecated = detect_deprecated_members(code, tree, api_index if shipped else None)
    if deprecated["has_deprecated"]:
        issues.append(f"deprecated member(s): {[f['expr'] for f in deprecated['findings']]}")

    print_calls = detect_print_calls(code, tree)
    if shipped and print_calls["has_print"]:
        issues.append(print_calls["suggestion"])

    if shipped:
        if not recipe.get("match_terms"):
            issues.append(
                "match_terms is empty: add query phrases so search can find this recipe"
            )
        notes_text = recipe.get("notes", "")
        if (
            not notes_text
            or not str(notes_text).strip()
            or str(notes_text).strip() == "TODO"
        ):
            issues.append(
                "notes is empty or TODO: describe what the recipe does and its gotchas"
            )
        for params_issue in _check_params_block(code):
            issues.append(params_issue)
        if requires_write and "if modifyAllowed:" not in code:
            issues.append(
                "requires_write=True but code lacks an 'if modifyAllowed:' guard"
            )
        for lineno, line in find_scrub_lines(code):
            issues.append(
                f"scrub line {lineno}: contains a GUID, a Windows user path, "
                f"or a forbidden project name: {line[:120]}"
            )
        raw = detect_raw_lcm_access(code, tree, api_index)
        for finding in raw["findings"]:
            issues.append(finding["message"])
        allowed = recipe.get("raw_lcm_lines", 0)
        if not isinstance(allowed, int) or allowed < 0:
            allowed = 0
        if raw["count"] > allowed:
            issues.append(
                f"raw LCM lines: code has {raw['count']} but the header records "
                f"raw_lcm_lines={recipe.get('raw_lcm_lines', 0)!r}"
            )
        elif raw["count"] < allowed:
            notes.append(f"lower raw_lcm_lines to {raw['count']}")
        if raw["count"] > 0 and "raw_lcm_lines" not in recipe:
            issues.append(
                "raw LCM access present but the header has no raw_lcm_lines count"
            )

    chain_check = detect_invalid_project_chains(tree, api_index)
    if chain_check["has_invalid"]:
        issues.append(f"invalid project.<X> chain(s): {chain_check['issues']}")

    return {"passed": len(issues) == 0, "issues": issues, "notes": notes}


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
