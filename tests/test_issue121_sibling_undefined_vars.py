#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #121 sibling bug (pattern-audit finding, bug 2 of 2):
`detect_undefined_variables` hard-blocks valid code.

Same bug *class* as #121: a conclusion about user code drawn from syntax
alone, with no dataflow. `NameCollector` only recognized a handful of
binding forms (FunctionDef/ClassDef/bare-Name Assign/Import/ImportFrom) and
had no `visit_For`, no tuple/list/starred unpacking, no comprehension
targets, no `with ... as`, no walrus, no except-as, and no full parameter
list (posonlyargs/kwonlyargs/vararg/kwarg). Any of these binding a
CAPITALIZED name (FLExTools convention: `for POS in ...`, `for K, V2 in
...`) got hard-rejected with error_code="undefined_variables" even though
the name is perfectly well-defined.

Fix: NameCollector now recognizes every Python binding-statement shape via
one shared recursive `_bind_target` helper (Name/Tuple/List/Starred) plus
a `_bind_args` helper for parameter lists.

This gate is purely additive by construction here -- every added visitor
only grows `defined_names`, which can only reduce rejections. The risk is
precision loss, not breakage, so each positive case below is paired with a
negative-control assertion that a genuinely undefined name is still caught.
"""

import ast
import sys

sys.path.insert(0, "src")

from flextoolsmcp.server.validators import detect_undefined_variables  # noqa: E402


def _check(code: str) -> dict:
    return detect_undefined_variables(ast.parse(code))


class TestPreviouslyRejectedValidCode:
    """Verbatim audit inputs -- each must now report has_undefined: False."""

    def test_for_loop_target(self):
        code = (
            "for POS in project.POS.GetAll():\n"
            "    print(POS)\n"
        )
        result = _check(code)
        assert result["has_undefined"] is False
        assert result["undefined_vars"] == []

    def test_list_comprehension_target(self):
        code = "result = [POS for POS in project.POS.GetAll()]\n"
        result = _check(code)
        assert result["has_undefined"] is False

    def test_with_as_target(self):
        code = (
            "with open(\"p\") as FH:\n"
            "    print(FH)\n"
        )
        result = _check(code)
        assert result["has_undefined"] is False

    def test_walrus_target(self):
        code = (
            "if (N := 5) > 1:\n"
            "    print(N)\n"
        )
        result = _check(code)
        assert result["has_undefined"] is False

    def test_tuple_unpacking_for_target(self):
        code = (
            "d = {}\n"
            "for K, V2 in d.items():\n"
            "    print(K, V2)\n"
        )
        result = _check(code)
        assert result["has_undefined"] is False


class TestAdditionalBindingShapes:
    """Binding forms named in the fix requirements but not in the audit's
    verbatim repro list -- each is a distinct AST shape the old collector
    missed."""

    def test_async_for_target(self):
        code = (
            "async def f():\n"
            "    async for ROW in gen():\n"
            "        print(ROW)\n"
        )
        result = _check(code)
        assert result["has_undefined"] is False

    def test_async_with_target(self):
        code = (
            "async def f():\n"
            "    async with ctx() as SESSION:\n"
            "        print(SESSION)\n"
        )
        result = _check(code)
        assert result["has_undefined"] is False

    def test_set_comprehension_target(self):
        code = "s = {X for X in range(3)}\n" "print(s)\n"
        result = _check(code)
        assert result["has_undefined"] is False

    def test_dict_comprehension_target(self):
        code = "d = {K: K for K in range(3)}\n" "print(d)\n"
        result = _check(code)
        assert result["has_undefined"] is False

    def test_generator_expression_target(self):
        code = "g = (X for X in range(3))\n" "print(list(g))\n"
        result = _check(code)
        assert result["has_undefined"] is False

    def test_starred_assignment_target(self):
        code = "a, *REST = [1, 2, 3]\n" "print(a, REST)\n"
        result = _check(code)
        assert result["has_undefined"] is False

    def test_list_unpacking_assignment_target(self):
        code = "[A, B] = [1, 2]\n" "print(A, B)\n"
        result = _check(code)
        assert result["has_undefined"] is False

    def test_annotated_assignment_target(self):
        code = "X: int = 5\n" "print(X)\n"
        result = _check(code)
        assert result["has_undefined"] is False

    def test_augmented_assignment_target(self):
        code = "Y = 0\n" "Y += 1\n" "print(Y)\n"
        result = _check(code)
        assert result["has_undefined"] is False

    def test_except_as_target(self):
        code = (
            "try:\n"
            "    pass\n"
            "except Exception as E:\n"
            "    print(E)\n"
        )
        result = _check(code)
        assert result["has_undefined"] is False

    def test_lambda_parameter(self):
        code = "f = lambda Q: Q + 1\n" "print(f(1))\n"
        result = _check(code)
        assert result["has_undefined"] is False

    def test_function_full_parameter_list(self):
        code = (
            "def g(POS, /, MID=1, *ARGS, KW=2, **KWARGS):\n"
            "    print(POS, MID, ARGS, KW, KWARGS)\n"
        )
        result = _check(code)
        assert result["has_undefined"] is False

    def test_global_and_nonlocal_names(self):
        code = (
            "COUNTER = 0\n"
            "\n"
            "def outer():\n"
            "    LOCAL = 1\n"
            "\n"
            "    def inner():\n"
            "        global COUNTER\n"
            "        nonlocal LOCAL\n"
            "        COUNTER += 1\n"
            "        LOCAL += 1\n"
            "    inner()\n"
        )
        result = _check(code)
        assert result["has_undefined"] is False


class TestNegativeControlStillCaught:
    """The gate must still catch genuinely undefined names -- this fix is
    additive to `defined_names` only, so precision loss (not breakage) is
    the risk to guard against."""

    def test_plain_undefined_name_still_flagged(self):
        result = _check("print(UNDEFINED_THING)\n")
        assert result["has_undefined"] is True
        assert "UNDEFINED_THING" in result["undefined_vars"]

    def test_undefined_name_alongside_valid_for_loop_binding(self):
        """A for-loop target is now recognized, but a *different* undefined
        name used nearby must still be caught."""
        code = (
            "for POS in project.POS.GetAll():\n"
            "    print(POS, TOTALLY_UNDEFINED)\n"
        )
        result = _check(code)
        assert result["has_undefined"] is True
        assert "TOTALLY_UNDEFINED" in result["undefined_vars"]
        assert "POS" not in result["undefined_vars"]
