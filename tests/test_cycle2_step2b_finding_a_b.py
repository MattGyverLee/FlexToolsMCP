#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cycle 2 regression tests for the Step 2b write-gate fix (Finding A) and the
sibling binding-form widening (Finding B).

Finding A: Step 2b used to suppress on a LINE-KEYED set built from Steps 1/1c's
un-stripped regex matches (`_resolved_pairs`), and self-added its own key. Two
same-name unresolved calls on one line collapsed to one finding, and ANY
same-name/same-line regex hit -- including one seeded from a comment or string
literal -- silently suppressed a real unresolved-receiver mutation. The fix
(`certify_script_readonly` Step 2b) decides per `ast.Call` node via
`_resolve_receiver_ops_class`, with a TIGHTENED fallback for Step 1's static
`<OpsClass>.Method(...)` form that requires the class name to be a KNOWN
INDEXED Operations class (`_indexed_operations_class_names`), not merely
suffix-shaped.

Finding B: `_collect_assign_call_nodes` only ever collected `ast.Assign`, so
`fx: FLExProject = ...` (AnnAssign), `if (fx := ...):` (NamedExpr),
`for ops in (...):` (For), and `with ... as fx:` (withitem) bound nothing in
`_resolve_alias_maps`/`_resolve_facade_names`. Widened via a third return
value (`bindings`), consumed only by those two resolvers -- never by
`_find_cast_alias_property_writes`, which still gets the unwidened
`ast.Assign`-only list.

See specs/flexicon-project-bridge/reviews/cycle1-qc-step2b-fix-shape.md for
the design decision this locks in.
"""

import ast
import sys
from types import SimpleNamespace

sys.path.insert(0, "src")

from flextoolsmcp.server.validators import (  # noqa: E402
    _collect_assign_call_nodes,
    _indexed_operations_class_names,
    certify_script_readonly,
)


# ---------------------------------------------------------------------------
# A synthetic index: one facade property per Operations class used below, one
# mutating + one read-only method per class. Mirrors test_issue130's shape.
# ---------------------------------------------------------------------------
def make_index():
    flexicon = {
        "entities": {
            "FLExProject": {
                "name": "FLExProject",
                "properties": [
                    {"name": "LexEntry", "return_type": "LexEntryOperations"},
                    {"name": "Senses", "return_type": "LexSenseOperations"},
                ],
                "methods": [
                    {"name": "FromOpenProject", "return_type": "", "is_mutating": False},
                ],
            },
            "LexEntryOperations": {
                "name": "LexEntryOperations",
                "access_path": "project.LexEntry",
                "properties": [],
                "methods": [
                    {"name": "Duplicate", "is_mutating": True},
                    {"name": "GetLexemeForm", "is_mutating": False},
                ],
            },
            "LexSenseOperations": {
                "name": "LexSenseOperations",
                "access_path": "project.Senses",
                "properties": [],
                "methods": [
                    {"name": "Duplicate", "is_mutating": True},
                    {"name": "GetGloss", "is_mutating": False},
                ],
            },
        }
    }
    return SimpleNamespace(flexicon=flexicon)


def unprotected(cert):
    return [(m["class"], m["method"]) for m in cert["mutating_calls"] if m["is_mutating"]]


def protected(cert):
    return [(m["class"], m["method"]) for m in cert["protected_calls"]]


def unknown(cert):
    return [(u["class"], u["method"]) for u in cert["unknown_calls"]]


# ---------------------------------------------------------------------------
# _indexed_operations_class_names -- the tightened fallback's own index
# ---------------------------------------------------------------------------
class TestIndexedOperationsClassNames:
    def test_returns_only_entities_ending_in_operations(self):
        names = _indexed_operations_class_names(make_index())
        assert names == {"LexEntryOperations", "LexSenseOperations"}

    def test_none_index_returns_empty_set(self):
        assert _indexed_operations_class_names(None) == set()

    def test_empty_flexicon_returns_empty_set(self):
        assert _indexed_operations_class_names(SimpleNamespace(flexicon={})) == set()


# ---------------------------------------------------------------------------
# Regression matrix rows 1-9: suppression vectors. Each embeds a decoy that
# matches _PATTERN_OPERATIONS_CALL (`\w+Operations...Method(`) textually --
# comment or string literal -- on the SAME LINE as a genuinely unresolved
# receiver call, or packs two genuine unresolved calls onto one line. All
# must still be caught: the fix reads only ast_calls + the resolution maps,
# never `code` text or line-keyed suppression.
# ---------------------------------------------------------------------------
class TestSuppressionVectorsAllCaught:
    def test_row_1_and_9_semicolon_packing_two_same_line_calls_produce_two_rows(self):
        """Rows 1 (`;` packing) and 9 (Step 2b self-suppression) together:
        before the fix, the second call's key collided with the first's
        self-added key and collapsed to one finding."""
        code = (
            "ops = mystery(project)\n"
            "ops.Duplicate(a); ops.Duplicate(b)\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        rows = [(u["method"], u["line"], u["col"]) for u in cert["unknown_calls"]]
        assert len(rows) == 2
        assert {ln for _, ln, _ in rows} == {2}
        assert len({c for _, _, c in rows}) == 2, "must have distinct col_offset"

    def test_row_2_nested_as_argument_caught(self):
        code = (
            "ops = mystery(project)\n"
            "report.Info(ops.Duplicate(a))  # ZzzOperations.Duplicate(z) decoy\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert ("ops", "Duplicate") in unknown(cert)

    def test_row_3_comprehension_caught(self):
        code = (
            "ops = mystery(project)\n"
            "results = [ops.Duplicate(x) for x in items]  # ZzzOperations.Duplicate(z)\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert ("ops", "Duplicate") in unknown(cert)

    def test_row_4_ternary_both_branches_caught(self):
        code = (
            "ops = mystery(project)\n"
            "y = ops.Duplicate(a) if flag else ops.Duplicate(b)  # ZzzOperations.Duplicate(z)\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        rows = [u["method"] for u in cert["unknown_calls"]]
        assert rows.count("Duplicate") == 2

    def test_row_5_one_line_for_caught(self):
        code = (
            "ops = mystery(project)\n"
            "for x in items: ops.Duplicate(x)  # ZzzOperations.Duplicate(z)\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert ("ops", "Duplicate") in unknown(cert)

    def test_row_6_trailing_comment_decoy_does_not_suppress(self):
        code = (
            "ops = mystery(project)\n"
            "ops.Duplicate(entry)  # ZzzOperations.Duplicate(x) not a real call\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert unknown(cert) == [("ops", "Duplicate")]

    def test_row_7_string_literal_decoy_after_does_not_suppress(self):
        code = (
            "ops = mystery(project)\n"
            'ops.Duplicate(entry); msg = "ZzzOperations.Duplicate(x)"\n'
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert unknown(cert) == [("ops", "Duplicate")]

    def test_row_8_reversed_order_decoy_before_does_not_suppress(self):
        code = (
            "ops = mystery(project)\n"
            'msg = "ZzzOperations.Duplicate(x)"; ops.Duplicate(entry)\n'
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert unknown(cert) == [("ops", "Duplicate")]


# ---------------------------------------------------------------------------
# Rows 10-12: the annotated-bridge widening interacting with Step 2b.
# ---------------------------------------------------------------------------
class TestAnnotatedBridgeInteraction:
    def test_row_10_annotated_bridge_with_usable_index_resolves_silently(self):
        code = (
            "fx: FLExProject = FLExProject.FromOpenProject(project)\n"
            "fx.LexEntry.Duplicate(entry)\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert unprotected(cert) == [("LexEntryOperations", "Duplicate")]
        assert cert["unknown_calls"] == []

    def test_row_11_annotated_bridge_without_usable_index_is_graceful(self):
        code = (
            "fx: FLExProject = FLExProject.FromOpenProject(project)\n"
            "fx.LexEntry.Duplicate(entry)\n"
        )
        cert_none = certify_script_readonly(code, api_index=None)
        assert isinstance(cert_none, dict)
        assert cert_none["is_certified_readonly"] is True

        cert_empty = certify_script_readonly(code, api_index=SimpleNamespace(flexicon={}))
        assert isinstance(cert_empty, dict)
        assert cert_empty["is_certified_readonly"] is True

    def test_row_12_index_absent_method_variant_not_double_reported(self):
        """The class resolves (widened AnnAssign facade binding), but the
        method itself is absent from the index entirely -- Step 2's own
        "method not in index" branch reports it exactly once; Step 2b must
        not ALSO report it (its `_indexed_mutating` gate is never even
        reached because `_cls` resolves)."""
        code = (
            "fx: FLExProject = FLExProject.FromOpenProject(project)\n"
            "fx.LexEntry.SomeNewMethodNotInIndex(entry)\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert len(cert["unknown_calls"]) == 1
        assert cert["unknown_calls"][0]["class"] == "LexEntryOperations"
        assert cert["unknown_calls"][0]["method"] == "SomeNewMethodNotInIndex"


# ---------------------------------------------------------------------------
# Row 13: each sibling binding form Finding B widens collection to.
# ---------------------------------------------------------------------------
class TestSiblingBindingForms:
    def test_walrus_named_expr_binds_the_facade(self):
        code = (
            "if (fx := FLExProject.FromOpenProject(project)):\n"
            "    fx.LexEntry.Duplicate(entry)\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert unprotected(cert) == [("LexEntryOperations", "Duplicate")]

    def test_for_target_binds_an_operations_alias(self):
        """Deliberate over-typing (issue #8): the For target is treated as
        bound to the whole iterable expression, not an element of it."""
        code = (
            "for ops in LexEntryOperations(project):\n"
            "    ops.Duplicate(entry)\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert unprotected(cert) == [("LexEntryOperations", "Duplicate")]

    def test_with_as_binds_the_facade(self):
        code = (
            "with FLExProject.FromOpenProject(project) as fx:\n"
            "    fx.LexEntry.Duplicate(entry)\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert unprotected(cert) == [("LexEntryOperations", "Duplicate")]


# ---------------------------------------------------------------------------
# Tightened fallback: adversarial cases J/K/L (PRE-EXISTING holes, closed by
# the tightening) and legitimate shapes M (anti-over-block), plus N/O.
# ---------------------------------------------------------------------------
class TestTightenedFallback:
    def test_case_j_local_alias_not_matching_index_is_caught(self):
        code = (
            "myOperations = get_agent_ops()\n"
            "myOperations.Duplicate(entry)\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert unknown(cert) == [("myOperations", "Duplicate")]

    def test_case_k_class_absent_from_index_is_caught(self):
        code = "ZzzOperations.Duplicate(entry)\n"
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert unknown(cert) == [("ZzzOperations", "Duplicate")]

    def test_case_l_function_parameter_shaped_like_ops_class_is_caught(self):
        code = (
            "def go(fooOperations):\n"
            "    fooOperations.Duplicate(entry)\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert unknown(cert) == [("fooOperations", "Duplicate")]

    def test_case_m_all_four_legitimate_shapes_stay_silent_from_step_2b(self):
        cases = [
            ("static_class_receiver", "LexSenseOperations.Duplicate(s)\n",
             ("LexSenseOperations", "Duplicate")),
            ("inline_construction", "LexSenseOperations(project).Duplicate(s)\n",
             ("LexSenseOperations", "Duplicate")),
            ("project_accessor", "project.LexEntry.Duplicate(e)\n",
             ("LexEntryOperations", "Duplicate")),
            ("facade_alias", (
                "fx = FLExProject.FromOpenProject(project)\n"
                "fx.LexEntry.Duplicate(e)\n"
             ), ("LexEntryOperations", "Duplicate")),
        ]
        for name, code, expected in cases:
            cert = certify_script_readonly(code, make_index())
            assert unprotected(cert) == [expected], name
            assert cert["unknown_calls"] == [], name

    def test_case_n_non_mutating_method_on_stale_class_stays_silent(self):
        """`GetLexemeForm` is never declared `is_mutating` anywhere in the
        index, so Step 2b's own `_indexed_mutating` gate excludes it before
        the tightened fallback is ever consulted."""
        code = "LexEntryOperations.GetLexemeForm(x)\n"
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is True
        assert unprotected(cert) == []
        assert cert["unknown_calls"] == []

    def test_case_o_guarded_case_k_variant_passes_unprotected_writes_gate(self):
        code = (
            "if modifyAllowed:\n"
            "    ZzzOperations.Duplicate(entry)\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is True
        assert protected(cert) == [("ZzzOperations", "Duplicate")]


# ---------------------------------------------------------------------------
# Finding B structural guarantee: _find_cast_alias_property_writes' input
# list must stay ast.Assign-only even as the sibling forms are collected.
# ---------------------------------------------------------------------------
class TestCollectAssignCallNodesStructuralSplit:
    def test_assigns_list_is_ast_assign_only_bindings_list_is_the_rest(self):
        code = (
            "fx: FLExProject = FLExProject.FromOpenProject(project)\n"
            "if (y := 1):\n"
            "    pass\n"
            "for z in range(3):\n"
            "    pass\n"
            "with open('f') as w:\n"
            "    pass\n"
            "a = 1\n"
        )
        tree = ast.parse(code)
        assigns, calls, bindings = _collect_assign_call_nodes(tree)
        assert all(isinstance(n, ast.Assign) for n in assigns)
        assert len(assigns) == 1  # only `a = 1`
        assert {type(n) for n in bindings} == {
            ast.AnnAssign, ast.NamedExpr, ast.For, ast.withitem
        }
