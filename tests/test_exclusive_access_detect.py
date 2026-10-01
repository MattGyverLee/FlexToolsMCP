#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exclusive-access gate: the table and the detector (specs/exclusive-access-gate,
FR-001..FR-003, research R2/R3/R8).

Writing-system and custom-field schema changes are not safe while FieldWorks
holds the project open in shared mode. `EXCLUSIVE_ONLY_OPERATIONS` names them
once; `detect_exclusive_only_operations` finds them in a submitted script by
reusing the read-only certifier's resolved rows (wrapper calls) plus one AST
pass for raw LCM names.

These tests run against the SHIPPED flexicon index (it is git-tracked), so a
flexicon rename of a wrapper method turns CI red instead of silently
un-gating it.
"""

import ast
import json
import sys
from functools import lru_cache
from pathlib import Path

import pytest

sys.path.insert(0, "src")

from flextoolsmcp.server.exclusive_access import (  # noqa: E402
    EXCLUSIVE_ONLY_OPERATIONS,
    ExclusiveOnlyMatch,
    detect_exclusive_only_operations,
)
from flextoolsmcp.server.validators import certify_script_readonly  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
INDEX_DIR = REPO / "src" / "flextoolsmcp" / "index" / "python"


@lru_cache(maxsize=1)
def load_index():
    from flextoolsmcp.server import APIIndex

    files = sorted(INDEX_DIR.glob("flexicon_api_v*.json"))
    if not files:
        pytest.skip(f"no shipped flexicon index in {INDEX_DIR}")
    idx = APIIndex()
    with open(files[-1], encoding="utf-8") as fh:
        idx.flexicon = json.load(fh)
    return idx


def detect(code):
    tree = ast.parse(code)
    cert = certify_script_readonly(code, load_index(), tree=tree)
    return detect_exclusive_only_operations(code, tree, cert)


def keys(matches):
    return [m.key for m in matches]


def main(body):
    """Wrap a body in the module shape (`Main(project, report, modifyAllowed)`)."""
    lines = "".join(f"    {ln}\n" for ln in body.strip("\n").splitlines())
    return "def Main(project, report, modifyAllowed):\n" + lines


# ---------------------------------------------------------------------------
# T003: the table
# ---------------------------------------------------------------------------

VALUE_METHODS = {
    "SetValue",
    "AddListValue",
    "RemoveListValue",
    "SetListFieldSingle",
    "SetListFieldMultiple",
    "ClearValue",
    "Duplicate",
}


class TestTable:
    def test_every_wrapper_method_is_indexed_and_mutating(self):
        entities = load_index().flexicon["entities"]
        for row in EXCLUSIVE_ONLY_OPERATIONS:
            if row.wrapper is None:
                continue
            cls, methods = row.wrapper
            assert cls in entities, (row.key, cls)
            indexed = {m["name"]: m.get("is_mutating") for m in entities[cls]["methods"]}
            for method in methods:
                assert method in indexed, (row.key, cls, method)
                assert indexed[method] is True, (row.key, cls, method)

    def test_no_row_names_a_value_method(self):
        for row in EXCLUSIVE_ONLY_OPERATIONS:
            names = set(row.raw_names) | set(row.raw_assignments)
            if row.wrapper is not None:
                names |= set(row.wrapper[1])
            if row.raw_receiver_methods is not None:
                names |= set(row.raw_receiver_methods[1])
            assert not (names & VALUE_METHODS), (row.key, names & VALUE_METHODS)

    def test_every_row_is_documented(self):
        for row in EXCLUSIVE_ONLY_OPERATIONS:
            assert row.reason.strip(), row.key
            assert row.evidence.strip(), row.key
            assert row.failure_class in {"crashes_holder", "silently_lost"}, row.key
            assert row.category in {"writing_system", "custom_field"}, row.key

    def test_keys_are_unique(self):
        all_keys = [row.key for row in EXCLUSIVE_ONLY_OPERATIONS]
        assert len(all_keys) == len(set(all_keys))

    def test_table_is_ascii(self):
        src = (REPO / "src" / "flextoolsmcp" / "server" / "exclusive_access.py").read_text(
            encoding="utf-8"
        )
        assert src.isascii()


# ---------------------------------------------------------------------------
# T005: the detector
# ---------------------------------------------------------------------------

class TestDetect:
    # --- positives -------------------------------------------------------

    def test_a_project_accessor_wrapper(self):
        m = detect(main('project.WritingSystems.Create("qaa-x-test")'))
        assert keys(m) == ["ws.wrapper"]
        assert m[0].call == "WritingSystemOperations.Create"
        assert m[0].source == "wrapper"
        assert m[0].line == 2
        assert m[0].category == "writing_system"
        assert m[0].failure_class == "crashes_holder"

    def test_b_accessor_alias(self):
        m = detect(main('ws = project.WritingSystems\nws.Ensure("en")'))
        assert keys(m) == ["ws.wrapper"]
        assert m[0].call == "WritingSystemOperations.Ensure"

    def test_c_facade(self):
        m = detect(main(
            "fx = FLExProject.FromOpenProject(project)\n"
            'fx.CustomFields.CreateField("LexEntry", "zz", "String")'
        ))
        assert keys(m) == ["cf.wrapper"]
        assert m[0].call == "CustomFieldOperations.CreateField"
        assert m[0].failure_class == "silently_lost"

    def test_d_operations_constructor(self):
        m = detect(main('WritingSystemOperations(project).Delete("qaa")'))
        assert keys(m) == ["ws.wrapper"]

    def test_e_raw_add_custom_field(self):
        m = detect(main('cache.MetaDataCacheAccessor.AddCustomField("LexEntry", "zz", 13, 0)'))
        assert keys(m) == ["cf.raw"]
        assert m[0].source == "raw"
        assert m[0].call == "cache.MetaDataCacheAccessor.AddCustomField"

    def test_f_raw_manager_alias(self):
        m = detect(main("mgr = cache.ServiceLocator.WritingSystemManager\nmgr.Set(ws)"))
        assert keys(m) == ["ws.raw.manager"]
        assert m[0].line == 3

    def test_f2_raw_manager_direct(self):
        m = detect(main("cache.ServiceLocator.WritingSystemManager.Save()"))
        assert keys(m) == ["ws.raw.manager"]

    def test_g_raw_list(self):
        m = detect(main("lp.CurrentVernacularWritingSystems.Add(ws)"))
        assert keys(m) == ["ws.raw.lists"]

    def test_g2_raw_container_name(self):
        m = detect(main("lp.AddToCurrentAnalysisWritingSystems(ws)"))
        assert keys(m) == ["ws.raw.container"]

    def test_g3_raw_services(self):
        m = detect(main(
            "WritingSystemServices.FindOrCreateWritingSystem(cache, None, 'qaa', True, False)"
        ))
        assert keys(m) == ["ws.raw.services"]

    def test_h_assignments(self):
        m = detect(main("fd.MarkForDeletion = True\nws.DefaultFontSize = 12"))
        assert keys(m) == ["cf.raw", "ws.raw.props"]
        assert [x.line for x in m] == [2, 3]

    def test_h2_field_description_update(self):
        m = detect(main("fd = FieldDescription(cache)\nfd.UpdateCustomField()"))
        assert keys(m) == ["cf.raw"]

    def test_i_guarded_call_still_matches(self):
        code = main('if modifyAllowed:\n    project.WritingSystems.SetFontSize("en", 12)')
        cert = certify_script_readonly(code, load_index())
        assert cert["is_certified_readonly"] is True  # it IS in protected_calls
        m = detect(code)
        assert keys(m) == ["ws.wrapper"]

    def test_j_unknown_call_on_known_class(self):
        """A method the index lacks on an exclusive class does not match by
        class alone -- only the table's named methods count."""
        m = detect(main('project.WritingSystems.Frobnicate("x")'))
        assert m == []

    def test_j_unresolved_receiver(self):
        code = main('ops = mystery(project)\nops.Ensure("en")')
        cert = certify_script_readonly(code, load_index())
        assert [(u["class"], u["method"]) for u in cert["unknown_calls"]] == [
            ("ops", "Ensure")
        ]
        m = detect(code)
        assert keys(m) == ["ws.wrapper"]
        assert m[0].call == "ops.Ensure"

    def test_j_unresolved_receiver_guarded(self):
        code = main('ops = mystery(project)\nif modifyAllowed:\n    ops.CreateField("a", "b", "c")')
        m = detect(code)
        assert keys(m) == ["cf.wrapper"]

    @pytest.mark.parametrize(
        "body",
        [
            'ops = mystery(project)\nops.Create("x")',
            "ops = mystery(project)\nops.Delete(entry)",
            "factory = cache.ServiceLocator.GetService(ILexEntryFactory)\nfactory.Create()",
            "cache.ServiceLocator.GetService(ILexEntryFactory).Create()",
        ],
    )
    def test_j_generic_names_on_untyped_receivers_do_not_match(self, body):
        """`Create`/`Delete` are mutating on ~50 other Operations classes and
        on every raw LCM factory, so an untyped receiver calling them is far
        more likely an ordinary entry/sense write than a writing-system one.
        Matching them by name alone would refuse ordinary edits while FLEx is
        open -- the exact over-refusal US2 forbids."""
        assert detect(main(body)) == []

    def test_k_dead_code_still_matches(self):
        m = detect(main('if False:\n    project.WritingSystems.Delete("qaa")'))
        assert keys(m) == ["ws.wrapper"]

    def test_dedup_and_sort(self):
        m = detect(main(
            'project.CustomFields.DeleteField("LexEntry", "zz")\n'
            'project.WritingSystems.Create("qaa")\n'
            "lp.VernacularWritingSystems.Remove(ws)"
        ))
        assert [(x.key, x.line) for x in m] == [
            ("cf.wrapper", 2),
            ("ws.wrapper", 3),
            ("ws.raw.lists", 4),
        ]

    def test_match_type(self):
        m = detect(main('project.WritingSystems.Create("qaa")'))
        assert isinstance(m[0], ExclusiveOnlyMatch)

    # --- negatives -------------------------------------------------------

    @pytest.mark.parametrize(
        "call",
        [
            'project.CustomFields.SetValue(entry, "zz", "v")',
            'project.CustomFields.AddListValue(entry, "zz", item)',
            'project.CustomFields.RemoveListValue(entry, "zz", item)',
            'project.CustomFields.SetListFieldSingle(entry, "zz", item)',
            'project.CustomFields.SetListFieldMultiple(entry, "zz", [item])',
            'project.CustomFields.ClearValue(entry, "zz")',
        ],
    )
    def test_l_value_setters(self, call):
        assert detect(main(call)) == []

    @pytest.mark.parametrize(
        "call",
        [
            "project.WritingSystems.GetAll()",
            'project.WritingSystems.Exists("en")',
            'project.WritingSystems.GetDisplayName("en")',
            "project.CustomFields.GetAllFields('LexEntry')",
        ],
    )
    def test_m_reads(self, call):
        assert detect(main(call)) == []

    @pytest.mark.parametrize(
        "body",
        [
            'some_dict.Set("k", 1)',
            "items.Add(x)",
            "other.Save()",
            "mgr = make_manager()\nmgr.Set(ws)",
            "wsList = [1, 2]\nwsList.Add(3)",
        ],
    )
    def test_n_generic_names_on_unrelated_receivers(self, body):
        assert detect(main(body)) == []

    def test_o_comments_and_strings(self):
        code = main(
            '# project.WritingSystems.Create("qaa")\n'
            's = "project.CustomFields.CreateField(a, b, c)"\n'
            "t = 'cache.MetaDataCacheAccessor.AddCustomField(x)'\n"
            'report.Info("fd.MarkForDeletion = True")'
        )
        assert detect(code) == []

    def test_reading_a_ws_property_is_not_an_assignment(self):
        assert detect(main("size = ws.DefaultFontSize\nreport.Info(str(size))")) == []

    def test_iterating_a_ws_list_is_not_a_mutation(self):
        code = main(
            "for ws in lp.CurrentVernacularWritingSystems:\n"
            "    report.Info(ws.Id)"
        )
        assert detect(code) == []

    def test_p_filing_path_is_clean(self):
        """Research R8: parse filing never touches writing systems or custom
        fields, so the gate must never fire on it."""
        filing = REPO / "src" / "flextoolsmcp" / "server" / "filing"
        sources = sorted(filing.glob("*.py"))
        assert sources
        for path in sources:
            code = path.read_text(encoding="utf-8")
            assert detect(code) == [], path.name

    def test_syntax_error_tree_none(self):
        assert detect_exclusive_only_operations("def (:\n", None, {}) == []
