#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #350: a loop over a list of LCM collections must not hide `.Add`.

`_collect_local_container_names` used to treat a `for` target as a local
container when its iterable was a list literal or a local list. The loop
variable is an ELEMENT of that list -- possibly a real LCM collection such as
`e.SensesOS` -- so an unguarded `coll.Add(s)` was dropped from
`find_liblcm_mutations` and the script certified read-only.

The suppression was also keyed by LINE, so a local `tmp.Add(x)` sharing a
line with a real `entry.SensesOS.Add(s)` hid the real one. It is now keyed by
the call node itself.
"""

from flextoolsmcp.server.validators import (
    certify_script_readonly,
    find_liblcm_mutations,
)


def _adds(code):
    return [m for m in find_liblcm_mutations(code) if m["method"] == "Add"]


def _assert_flagged(code):
    cert = certify_script_readonly(code, api_index=None)
    assert cert["is_certified_readonly"] is False, cert
    assert any(m["method"] == "Add" for m in cert["unprotected_liblcm_calls"]), cert


class TestLoopElementIsNotALocalContainer:
    def test_loop_over_list_literal_of_lcm_collections(self):
        code = (
            "e = project.LexEntry.Find('a'); f = project.LexEntry.Find('b')\n"
            "for coll in [e.SensesOS, f.SensesOS]:\n"
            "    coll.Add(s)\n"
        )
        _assert_flagged(code)

    def test_loop_over_local_list_comprehension(self):
        code = (
            "colls = [e.SensesOS for e in project.LexEntry.GetAll()]\n"
            "for coll in colls:\n"
            "    coll.Add(s)\n"
        )
        _assert_flagged(code)

    def test_loop_over_tuple_with_unpacking_target(self):
        code = (
            "pairs = [(e.SensesOS, s) for e in project.LexEntry.GetAll()]\n"
            "for coll, s in pairs:\n"
            "    coll.Add(s)\n"
        )
        _assert_flagged(code)

    def test_loop_rebinding_a_previously_local_name(self):
        # `coll` is a local list first, then rebound per-iteration to an
        # element; the earlier local binding must not whitelist it.
        code = (
            "coll = []\n"
            "for coll in [entry.SensesOS]:\n"
            "    coll.Add(s)\n"
        )
        _assert_flagged(code)

    def test_later_local_rebinding_does_not_whitelist_earlier_lcm_use(self):
        # Flow-insensitive "last binding wins" used to leave `x` local.
        code = (
            "x = entry.SensesOS\n"
            "x.Add(s)\n"
            "x = []\n"
        )
        _assert_flagged(code)

    def test_guarded_loop_add_is_protected(self):
        code = (
            "for coll in [entry.SensesOS]:\n"
            "    if modifyAllowed:\n"
            "        coll.Add(s)\n"
        )
        cert = certify_script_readonly(code, api_index=None)
        assert cert["is_certified_readonly"] is True, cert
        assert any(m["method"] == "Add" for m in cert["protected_liblcm_calls"])


class TestSuppressionIsNodeKeyed:
    def test_local_add_and_lcm_add_on_one_line(self):
        code = (
            "tmp = set()\n"
            "tmp.Add(x); entry.SensesOS.Add(s)\n"
        )
        adds = _adds(code)
        assert len(adds) == 1, adds
        assert adds[0]["line"] == 2
        _assert_flagged(code)

    def test_lcm_add_before_local_add_on_one_line(self):
        code = (
            "tmp = set()\n"
            "entry.SensesOS.Add(s); tmp.Add(x)\n"
        )
        assert len(_adds(code)) == 1
        _assert_flagged(code)

    def test_two_local_adds_on_one_line_stay_suppressed(self):
        code = (
            "a = set(); b = set()\n"
            "a.Add(1); b.Add(2)\n"
        )
        assert _adds(code) == []


class TestGenuinelyLocalContainersStillSkipped:
    def test_python_list_append_not_flagged(self):
        code = (
            "results = []\n"
            "for e in project.LexEntry.GetAll():\n"
            "    results.append(e)\n"
        )
        cert = certify_script_readonly(code, api_index=None)
        assert cert["is_certified_readonly"] is True, cert

    def test_local_set_add_not_flagged(self):
        code = (
            "seen = set()\n"
            "for e in project.LexEntry.GetAll():\n"
            "    seen.Add(e)\n"
        )
        assert _adds(code) == []
        assert certify_script_readonly(code, api_index=None)["is_certified_readonly"]

    def test_alias_of_local_container_not_flagged(self):
        code = (
            "seen = set()\n"
            "alias = seen\n"
            "alias.Add(1)\n"
        )
        assert _adds(code) == []

    def test_walrus_and_annotated_local_containers_not_flagged(self):
        code = (
            "acc: set = set()\n"
            "acc.Add(1)\n"
            "if (bag := set()) is not None:\n"
            "    bag.Add(2)\n"
        )
        assert _adds(code) == []

    def test_augassign_with_local_value_keeps_name_local(self):
        code = (
            "seen = set()\n"
            "seen |= {1}\n"
            "seen.Add(2)\n"
        )
        assert _adds(code) == []


class TestNonNameBindingsDisqualify:
    """Pattern audit sibling: bindings that are not `ast.Name` stores."""

    def test_helper_parameter_named_like_a_local_list(self):
        code = (
            "def helper(senses, s):\n"
            "    senses.Add(s)\n"
            "def Main(project, report, modifyAllowed):\n"
            "    senses = []\n"
            "    for e in project.LexiconAllEntries():\n"
            "        helper(e.SensesOS, None)\n"
        )
        _assert_flagged(code)

    def test_lambda_parameter(self):
        code = (
            "tmp = []\n"
            "f = lambda tmp, s: tmp.Add(s)\n"
            "f(e.SensesOS, None)\n"
        )
        _assert_flagged(code)

    def test_import_alias(self):
        code = (
            "def a():\n"
            "    tmp = []\n"
            "def b():\n"
            "    from x import y as tmp\n"
            "    tmp.Add(s)\n"
        )
        _assert_flagged(code)

    def test_except_and_match_names(self):
        code = (
            "tmp = []\n"
            "try:\n"
            "    pass\n"
            "except Exception as tmp:\n"
            "    tmp.Add(s)\n"
        )
        _assert_flagged(code)
        code = (
            "tmp = []\n"
            "match e:\n"
            "    case [*tmp]:\n"
            "        tmp.Add(s)\n"
        )
        _assert_flagged(code)

    def test_plain_local_list_still_not_flagged(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    results = []\n"
            "    results.Add(1)\n"
        )
        assert _adds(code) == []
