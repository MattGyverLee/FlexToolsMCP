#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #130: unguarded mutations reached through the flexicon facade
(`fx = FLExProject.FromOpenProject(project)`) bypassed EVERY write gate.

The receiver resolver typed a call receiver by matching the literal name
`project`, so `fx.LexEntry` never resolved to `LexEntryOperations`, the
mutating call on it was never looked up in the API index, and
`certify_script_readonly` reported `is_certified_readonly=True` on a
DELIBERATELY unguarded write: `unprotected_writes` passed,
`writeability.is_mutating_script` was False, and `would_require.write_enabled`
was False. Refreshing the index did not help -- `FLExProject.FromOpenProject`
carries no return annotation upstream, so its indexed `return_type` is `''`
and there was nothing to resolve `fx` against.

That landed on exactly the shape flexicon 4.7.0 documents as THE portable
module shape (and the shape our own flexicon template teaches).

Two fixes, both exercised here:

  1. `_resolve_receiver_ops_class` now membership-tests the receiver name
     against `_resolve_facade_names()` -- `project` plus every variable bound
     to a FLExProject -- instead of comparing to the literal `"project"`.
     Facade-valued variables are tracked through direct construction, the
     documented `FromOpenProject` bridge (typed off an EMPTY or absent
     `return_type`, deliberately), rebind chains, accessor aliases
     (`lex = fx.LexEntry`) and tuple unpacking
     (`lex, lists = fx.LexEntry, fx.PossibilityLists`).

  2. Fail closed: an UNRESOLVABLE receiver reaching a method name the index
     declares mutating is reported as a suspected mutation
     (`source="unresolved_receiver"`) instead of being silently certified
     read-only. This is what keeps the next un-annotated bridge constructor a
     reporting gap rather than a safety hole.

The scope table in the issue is reproduced verbatim in
`TestIssue130ScopeTable` -- every row that read "no" must now read "yes".
"""

import json
import sys
from functools import lru_cache
from types import SimpleNamespace

import pytest

sys.path.insert(0, "src")

from flextoolsmcp.server.validators import (  # noqa: E402
    _FACADE_INJECTED_NAMES,
    _resolve_alias_maps,
    _resolve_facade_names,
    build_writeability_payload,
    certify_script_readonly,
)

import ast  # noqa: E402


# ---------------------------------------------------------------------------
# A synthetic index, so the shape tests run without a FieldWorks checkout.
# Mirrors the real 4.7.0 records that matter: the FLExProject facade property
# `LexEntry -> LexEntryOperations`, the un-annotated `FromOpenProject`
# (`return_type: ""` -- the root cause), and one mutating + one read-only
# LexEntryOperations method.
# ---------------------------------------------------------------------------
def make_index(from_open_project_return_type=""):
    flexicon = {
        "entities": {
            "FLExProject": {
                "name": "FLExProject",
                "properties": [
                    {"name": "LexEntry", "return_type": "LexEntryOperations"},
                    {"name": "PossibilityLists", "return_type": "PossibilityListOperations"},
                ],
                "methods": [
                    {
                        "name": "FromOpenProject",
                        "return_type": from_open_project_return_type,
                        "is_mutating": False,
                    },
                    {"name": "GetProjectNames", "return_type": "", "is_mutating": False},
                ],
            },
            "LexEntryOperations": {
                "name": "LexEntryOperations",
                "access_path": "project.LexEntry",
                "properties": [],
                "methods": [
                    {"name": "SetLexemeForm", "is_mutating": True},
                    {"name": "AddComplexFormComponent", "is_mutating": True},
                    {"name": "GetLexemeForm", "is_mutating": False},
                    {"name": "Find", "is_mutating": False},
                    {"name": "GetAll", "is_mutating": False},
                ],
            },
            "PossibilityListOperations": {
                "name": "PossibilityListOperations",
                "access_path": "project.PossibilityLists",
                "properties": [],
                "methods": [{"name": "GetAll", "is_mutating": False}],
            },
        }
    }
    return SimpleNamespace(flexicon=flexicon)


def unprotected(cert):
    return [(m["class"], m["method"]) for m in cert["mutating_calls"] if m["is_mutating"]]


def protected(cert):
    return [(m["class"], m["method"]) for m in cert["protected_calls"]]


# ---------------------------------------------------------------------------
# The scope table from the issue. Every shape uses the SAME mutating method;
# the only variable is how the receiver is spelled.
# ---------------------------------------------------------------------------

_SCOPE_TABLE = {
    "operations_class_receiver": (
        'entry = project.LexEntry.Find("x")\n'
        "LexEntryOperations(project).AddComplexFormComponent(entry, entry)\n"
    ),
    "injected_project_accessor": (
        'entry = project.LexEntry.Find("x")\n'
        "project.LexEntry.AddComplexFormComponent(entry, entry)\n"
    ),
    "attached_facade_accessor": (
        "fx = FLExProject.FromOpenProject(project)\n"
        'entry = fx.LexEntry.Find("x")\n'
        "fx.LexEntry.AddComplexFormComponent(entry, entry)\n"
    ),
    "facade_accessor_alias": (
        "fx = FLExProject.FromOpenProject(project)\n"
        "lex = fx.LexEntry\n"
        'entry = lex.Find("x")\n'
        "lex.AddComplexFormComponent(entry, entry)\n"
    ),
    "facade_accessor_tuple_unpack": (
        "fx = FLExProject.FromOpenProject(project)\n"
        "lex, lists = fx.LexEntry, fx.PossibilityLists\n"
        'entry = lex.Find("x")\n'
        "lex.AddComplexFormComponent(entry, entry)\n"
    ),
}


class TestIssue130ScopeTable:
    """Every row of the issue's scope table must now be DETECTED."""

    @pytest.mark.parametrize("shape", sorted(_SCOPE_TABLE))
    def test_unguarded_mutation_is_detected(self, shape):
        cert = certify_script_readonly(_SCOPE_TABLE[shape], make_index())
        assert cert["is_certified_readonly"] is False, shape
        assert unprotected(cert) == [
            ("LexEntryOperations", "AddComplexFormComponent")
        ], shape

    @pytest.mark.parametrize("shape", sorted(_SCOPE_TABLE))
    def test_detected_shapes_resolve_through_the_index(self, shape):
        """Not merely "blocked somehow": resolved against the index, which is
        what makes the row report the real class/method rather than a
        regex-shaped guess."""
        cert = certify_script_readonly(_SCOPE_TABLE[shape], make_index())
        assert [m["source"] for m in cert["mutating_calls"]] == ["index"], shape
        assert cert["confidence"] == "high", shape


class TestIssue130LiveRepro:
    """The verbatim probe from the issue (op-005219846-031)."""

    CODE = (
        "from flexicon import FLExProject\n"
        "\n"
        "def Main(project, report, modifyAllowed):\n"
        "    fx = FLExProject.FromOpenProject(project)\n"
        '    entry = fx.LexEntry.Find("nsanga-nsanga")\n'
        "    # DELIBERATELY UNGUARDED -- no `if modifyAllowed:` anywhere.\n"
        '    fx.LexEntry.SetLexemeForm(entry, "PROBE-SHOULD-BE-BLOCKED")\n'
        '    report.Info("if you can read this, the gate did not fire")\n'
    )

    def test_unprotected_writes_gate_fires(self):
        cert = certify_script_readonly(self.CODE, make_index())
        assert cert["is_certified_readonly"] is False
        assert unprotected(cert) == [("LexEntryOperations", "SetLexemeForm")]

    def test_writeability_payload_names_the_mutation(self):
        """The issue's expected output: `SetLexemeForm` named, write_enabled
        and project_lock both required."""
        payload = build_writeability_payload(self.CODE, make_index())
        assert payload["is_mutating_script"] is True
        assert payload["would_require"] == {"write_enabled": True, "project_lock": True}
        assert [m["call"] for m in payload["mutations_detected"]] == [
            "LexEntryOperations.SetLexemeForm"
        ]


class TestIssue130GuardedFacadeWritesStillPass:
    """The fix must not turn a correctly guarded facade module into a
    violation -- only the SEPARATE unprotected_writes gate cares about the
    guard, while the mutation still needs write_enabled + the lock (#93)."""

    CODE = (
        "def Main(project, report, modifyAllowed):\n"
        "    fx = FLExProject.FromOpenProject(project)\n"
        '    entry = fx.LexEntry.Find("x")\n'
        "    if modifyAllowed:\n"
        '        fx.LexEntry.SetLexemeForm(entry, "new")\n'
    )

    def test_guarded_write_is_certified_readonly(self):
        cert = certify_script_readonly(self.CODE, make_index())
        assert cert["is_certified_readonly"] is True
        assert unprotected(cert) == []
        assert protected(cert) == [("LexEntryOperations", "SetLexemeForm")]

    def test_guarded_write_still_requires_write_enabled_and_lock(self):
        payload = build_writeability_payload(self.CODE, make_index())
        assert payload["is_mutating_script"] is True
        assert payload["would_require"] == {"write_enabled": True, "project_lock": True}

    def test_readonly_facade_module_stays_certified(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    fx = FLExProject.FromOpenProject(project)\n"
            "    for entry in fx.LexEntry.GetAll():\n"
            "        report.Info(fx.LexEntry.GetLexemeForm(entry))\n"
        )
        cert = certify_script_readonly(code, make_index())
        payload = build_writeability_payload(code, make_index())
        assert cert["is_certified_readonly"] is True
        assert payload["is_mutating_script"] is False
        assert payload["would_require"] == {"write_enabled": False, "project_lock": False}


# ---------------------------------------------------------------------------
# Facade-name tracking itself
# ---------------------------------------------------------------------------

def facade_names(code, api_index=None):
    assigns = [n for n in ast.walk(ast.parse(code)) if isinstance(n, ast.Assign)]
    return _resolve_facade_names(assigns, api_index)


class TestFacadeNameResolution:
    def test_injected_project_is_always_a_facade(self):
        assert _FACADE_INJECTED_NAMES <= facade_names("x = 1\n")

    def test_from_open_project_binds_the_target(self):
        """The root cause: `FromOpenProject`'s indexed return_type is ''."""
        assert "fx" in facade_names(
            "fx = FLExProject.FromOpenProject(project)\n", make_index()
        )

    def test_direct_construction_binds_the_target(self):
        assert "p" in facade_names("p = FLExProject()\n", make_index())

    def test_rebind_chain_propagates(self):
        names = facade_names(
            "fx = FLExProject.FromOpenProject(project)\np = fx\nq = p\n", make_index()
        )
        assert {"fx", "p", "q"} <= names

    def test_rebind_declared_before_its_source_still_resolves(self):
        """`_resolve_facade_names` runs to a fixed point, so it does not depend
        on the order ast.walk happened to yield the assignments."""
        code = (
            "def outer(project):\n"
            "    def inner():\n"
            "        p = fx\n"
            "        return p\n"
            "    fx = FLExProject.FromOpenProject(project)\n"
            "    return inner()\n"
        )
        assert {"fx", "p"} <= facade_names(code, make_index())

    def test_annotated_return_type_also_binds(self):
        """Issue #130 suggestion 1 (annotate upstream) must not REGRESS the
        detection: once flexicon declares `-> "FLExProject"`, the same
        assignment still types `fx`."""
        assert "fx" in facade_names(
            "fx = FLExProject.FromOpenProject(project)\n",
            make_index(from_open_project_return_type="FLExProject"),
        )

    def test_readonly_classmethod_result_is_not_a_facade(self):
        """`FLExProject.GetProjectNames()` returns a list of names, not a
        facade -- an unannotated return type must not make everything one."""
        assert "names" not in facade_names(
            "names = FLExProject.GetProjectNames()\n", make_index()
        )

    def test_unrelated_call_is_not_a_facade(self):
        assert "thing" not in facade_names("thing = SomethingElse(project)\n", make_index())

    def test_future_bridge_constructor_absent_from_index_still_binds(self):
        """A newer constructor read against a stale index has no record at
        all; typing it anyway is what stops #130 from recurring on the next
        seam nobody anticipated."""
        assert "fx" in facade_names(
            "fx = FLExProject.AttachTo(project)\n", make_index()
        )


class TestFacadeAccessorAliases:
    def test_single_accessor_alias_resolves_to_its_operations_class(self):
        code = "fx = FLExProject.FromOpenProject(project)\nlex = fx.LexEntry\n"
        assigns = [n for n in ast.walk(ast.parse(code)) if isinstance(n, ast.Assign)]
        ops, _ = _resolve_alias_maps(
            assigns,
            _resolve_facade_names(assigns, make_index()),
            {"LexEntry": "LexEntryOperations"},
        )
        assert ops["lex"] == "LexEntryOperations"

    def test_tuple_unpacking_binds_each_name_to_its_own_accessor(self):
        """Issue #130 scope table row 5: `lex, lists = fx.LexEntry,
        fx.PossibilityLists` bound NEITHER name before the fix."""
        code = (
            "fx = FLExProject.FromOpenProject(project)\n"
            "lex, lists = fx.LexEntry, fx.PossibilityLists\n"
        )
        assigns = [n for n in ast.walk(ast.parse(code)) if isinstance(n, ast.Assign)]
        ops, _ = _resolve_alias_maps(
            assigns,
            _resolve_facade_names(assigns, make_index()),
            {
                "LexEntry": "LexEntryOperations",
                "PossibilityLists": "PossibilityListOperations",
            },
        )
        assert ops == {
            "lex": "LexEntryOperations",
            "lists": "PossibilityListOperations",
        }

    def test_injected_project_accessor_alias_also_resolves(self):
        """The same blindness applied to `lex = project.LexEntry`, which the
        issue's table did not list but which was equally unseen."""
        code = "lex = project.LexEntry\n"
        assigns = [n for n in ast.walk(ast.parse(code)) if isinstance(n, ast.Assign)]
        ops, _ = _resolve_alias_maps(
            assigns, None, {"LexEntry": "LexEntryOperations"}
        )
        assert ops["lex"] == "LexEntryOperations"

    def test_pre_existing_operations_alias_shape_still_works(self):
        """#8's shape must survive the switch to `_iter_assign_pairs`."""
        code = "posOps = POSOperations(project)\ns_typed = ILexSense(sense)\n"
        assigns = [n for n in ast.walk(ast.parse(code)) if isinstance(n, ast.Assign)]
        ops, casts = _resolve_alias_maps(assigns)
        assert ops == {"posOps": "POSOperations"}
        assert casts == {"s_typed": "ILexSense"}


# ---------------------------------------------------------------------------
# Suggestion 3: fail closed on an unresolvable receiver
# ---------------------------------------------------------------------------

class TestUnresolvableReceiverFailsClosed:
    def test_unguarded_mutating_name_on_unknown_receiver_is_blocked(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    ops = mystery(project)\n"
            '    ops.SetLexemeForm(entry, "PROBE")\n'
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is False
        assert unprotected(cert) == [("ops", "SetLexemeForm")]
        assert [m["source"] for m in cert["mutating_calls"]] == ["unresolved_receiver"]

    def test_unresolvable_receiver_degrades_confidence(self):
        """A suspicion, not a certainty -- say so rather than claiming 'high'."""
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    ops = mystery(project)\n"
            '    ops.SetLexemeForm(entry, "PROBE")\n'
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["confidence"] == "low"
        assert [(u["class"], u["method"]) for u in cert["unknown_calls"]] == [
            ("ops", "SetLexemeForm")
        ]

    def test_guarded_mutating_name_on_unknown_receiver_passes_the_gate(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    ops = mystery(project)\n"
            "    if modifyAllowed:\n"
            '        ops.SetLexemeForm(entry, "PROBE")\n'
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is True
        assert protected(cert) == [("ops", "SetLexemeForm")]
        payload = build_writeability_payload(code, make_index())
        assert payload["is_mutating_script"] is True

    def test_readonly_method_on_unknown_receiver_stays_clean(self):
        """Only names the index DECLARES mutating are suspected -- this is not
        a verb-prefix guess, so read-only calls on untyped receivers stay
        silent."""
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    ops = mystery(project)\n"
            "    report.Info(ops.GetLexemeForm(entry))\n"
        )
        cert = certify_script_readonly(code, make_index())
        assert cert["is_certified_readonly"] is True
        assert cert["mutating_calls"] == []
        assert cert["protected_calls"] == []

    def test_resolved_calls_are_not_double_reported(self):
        """A call the index already classified must not also appear as an
        unresolved-receiver suspicion."""
        code = (
            "def Main(project, report, modifyAllowed):\n"
            '    project.LexEntry.SetLexemeForm(entry, "x")\n'
        )
        cert = certify_script_readonly(code, make_index())
        assert unprotected(cert) == [("LexEntryOperations", "SetLexemeForm")]
        assert cert["unknown_calls"] == []


# ---------------------------------------------------------------------------
# The index-independent half: the gate must hold with NO api_index at all.
# A missing index is only a WARNING at gate 2 ("will be loaded on first API
# discovery"), so gate 4 can genuinely run with api_index=None -- and in that
# state the index lookup sees nothing, leaving the line-aware accessor regexes
# as the only thing holding the write gate.
# ---------------------------------------------------------------------------

class TestFacadeWriteGatedWithoutAnIndex:
    def test_unguarded_facade_write_blocked_with_no_index(self):
        code = (
            "fx = FLExProject.FromOpenProject(project)\n"
            'entry = fx.LexEntry.Find("x")\n'
            'fx.LexEntry.SetLexemeForm(entry, "PROBE")\n'
        )
        cert = certify_script_readonly(code, api_index=None)
        assert cert["is_certified_readonly"] is False
        assert [c["method"] for c in cert["unprotected_liblcm_calls"]] == [
            "fx.*.Set/Update"
        ]

    def test_guarded_facade_write_passes_with_no_index(self):
        code = (
            "fx = FLExProject.FromOpenProject(project)\n"
            "if modifyAllowed:\n"
            '    fx.LexEntry.SetLexemeForm(entry, "PROBE")\n'
        )
        cert = certify_script_readonly(code, api_index=None)
        assert cert["is_certified_readonly"] is True
        assert [c["method"] for c in cert["protected_liblcm_calls"]] == [
            "fx.*.Set/Update"
        ]

    def test_readonly_facade_script_stays_clean_with_no_index(self):
        code = (
            "fx = FLExProject.FromOpenProject(project)\n"
            "for entry in fx.LexEntry.GetAll():\n"
            "    report.Info(fx.LexEntry.GetLexemeForm(entry))\n"
        )
        cert = certify_script_readonly(code, api_index=None)
        assert cert["is_certified_readonly"] is True
        assert cert["unprotected_liblcm_calls"] == []

    def test_project_receiver_label_is_unchanged(self):
        """The historical `project.*.Set/Update` label is asserted verbatim
        elsewhere (test_issue49_validate_only), so rebuilding these patterns
        from a template must not rename them."""
        cert = certify_script_readonly(
            'project.LexEntry.SetLexemeForm(entry, "PROBE")\n', api_index=None
        )
        assert [c["method"] for c in cert["unprotected_liblcm_calls"]] == [
            "project.*.Set/Update"
        ]

    def test_facade_create_and_delete_shapes_also_gated(self):
        for call, label in (
            ('fx.LexEntry.Create("x")', "fx.*.Create"),
            ("fx.LexEntry.Delete(entry)", "fx.*.Delete"),
        ):
            code = "fx = FLExProject.FromOpenProject(project)\n" + call + "\n"
            cert = certify_script_readonly(code, api_index=None)
            assert cert["is_certified_readonly"] is False, call
            methods = [c["method"] for c in cert["unprotected_liblcm_calls"]]
            assert label in methods, call


# ---------------------------------------------------------------------------
# End-to-end against the real shipped index (the environment from the issue)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_real_index():
    from flextoolsmcp.server import APIIndex, get_index_dir

    index_dir = get_index_dir() / "python"
    files = sorted(index_dir.glob("flexicon_api_v*.json"))
    if not files:
        raise FileNotFoundError(f"No Flexicon API index found in {index_dir}")
    idx = APIIndex()
    with open(files[-1], encoding="utf-8") as fh:
        idx.flexicon = json.load(fh)
    return idx


@pytest.mark.requires_flex
class TestIssue130AgainstShippedIndex:
    """Same assertions, but against the on-disk index the server actually
    loads -- the configuration in which the probe passed all 11 gates.
    Deselected where the packaged index is absent (Linux CI)."""

    def test_live_probe_is_blocked(self):
        cert = certify_script_readonly(TestIssue130LiveRepro.CODE, load_real_index())
        assert cert["is_certified_readonly"] is False
        assert ("LexEntryOperations", "SetLexemeForm") in unprotected(cert)

    def test_from_open_project_return_type_is_unannotated_or_facade_typed(self):
        """Documents the root cause, and pins the reason the resolver must be
        able to type off an EMPTY return_type: `FromOpenProject` has no return
        annotation upstream, so the generator records `""`.

        Both outcomes are acceptable and the fix covers both -- if flexicon
        later annotates it (issue #130 suggestion 1), the value becomes
        "FLExProject" and `test_annotated_return_type_also_binds` above
        already covers that path. Skipped rather than failed on an index that
        predates the bridge (4.6.0 and earlier have no such method at all),
        since the detection does not depend on the record existing."""
        entities = load_real_index().flexicon["entities"]
        methods = entities["FLExProject"]["methods"]
        found = [m for m in methods if m["name"] == "FromOpenProject"]
        if not found:
            pytest.skip(
                "shipped index predates FLExProject.FromOpenProject "
                "(run `python -m flextoolsmcp.refresh`)"
            )
        assert found[0].get("return_type", "") in ("", "FLExProject")

    @pytest.mark.parametrize("shape", sorted(_SCOPE_TABLE))
    def test_scope_table_against_shipped_index(self, shape):
        cert = certify_script_readonly(_SCOPE_TABLE[shape], load_real_index())
        assert cert["is_certified_readonly"] is False, shape
        assert unprotected(cert) == [
            ("LexEntryOperations", "AddComplexFormComponent")
        ], shape

    def test_shipped_flexicon_template_readonly_body_stays_certified(self):
        """Our own template teaches the `fx = FromOpenProject(project)` shape
        and its example body is read-only -- it must not start tripping the
        write gate now that `fx` is typed."""
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    fx = FLExProject.FromOpenProject(project)\n"
            "    entries = fx.LexEntry.GetAll()\n"
            "    for entry in entries:\n"
            "        form = fx.LexEntry.GetLexemeForm(entry)\n"
            "        senses = fx.LexEntry.GetAllSenses(entry)\n"
            "        report.Info(f'{form} ({len(senses)})')\n"
        )
        cert = certify_script_readonly(code, load_real_index())
        assert cert["is_certified_readonly"] is True
        assert cert["mutating_calls"] == []
