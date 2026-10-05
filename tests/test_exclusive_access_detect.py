#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exclusive-access gate: the table and the detector (specs/_archive/exclusive-access-gate,
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
        assert keys(m) == ["ws.ensure"]
        assert m[0].call == "WritingSystemOperations.Ensure"
        assert m[0].conditional is True

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

    def test_j_unresolved_receiver_ensure_needs_evidence(self):
        """An `Ensure()` on an unknown receiver is NOT matched by method name
        alone (review finding on #343): without receiver evidence it is an
        ordinary cache call, not a writing-system change. The runtime peer
        guard stays the backstop if it really is WritingSystems.Ensure."""
        code = main('ops = mystery(project)\nops.Ensure("en")')
        cert = certify_script_readonly(code, load_index())
        assert [(u["class"], u["method"]) for u in cert["unknown_calls"]] == [
            ("ops", "Ensure")
        ]
        assert detect(code) == []

    def test_j_unrelated_cache_ensure_is_not_refused(self):
        """The finding's example: `cache.Ensure()` on a user-defined cache
        must run while FieldWorks is open, not refuse as `ws.ensure`."""
        code = main('cache = make_cache()\nif modifyAllowed:\n    cache.Ensure()')
        assert detect(code) == []

    @pytest.mark.parametrize(
        "body",
        [
            'def f(p):\n    p.WritingSystems.Ensure("en", "x")',
            'def f(p):\n    w = p.WritingSystems\n    w.Ensure("en", "x")',
        ],
    )
    def test_j_unresolved_receiver_ensure_with_facade_evidence(self, body):
        """...but a `.WritingSystems` facade on an untyped receiver IS the
        evidence the bare name lacks, so it still takes the conditional
        Ensure() path (plan_conditional decides it)."""
        m = detect(main(body))
        assert keys(m) == ["ws.ensure"]
        assert m[0].conditional is True
        assert m[0].call == "WritingSystemOperations.Ensure"

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

    @pytest.mark.parametrize(
        "code",
        [
            'def f(p):\n    p.WritingSystems.Delete("fr")\nf(project)',
            'def f(p):\n    w = p.WritingSystems\n    w.Create("fr", "F")',
            'def f(p):\n    w = p.WritingSystems\n    w2 = w\n    w2.Create("fr", "F")',
            'for w in [project.WritingSystems]:\n    w.Create("fr", "F")',
            'w = project.WritingSystems\ndef f():\n    w.Delete("fr")',
        ],
    )
    def test_j_generic_names_on_a_facade_attribute_match(self, code):
        """The certifier cannot type a helper's `p` parameter, so its row is
        `unresolved_receiver` and the generic-name exclusion would drop it.
        The `.WritingSystems` attribute (direct or via a local alias) is the
        evidence the bare name lacks, so these are refused like the typed
        `project.WritingSystems.Delete` (review finding on #343)."""
        m = detect(code)
        assert keys(m) == ["ws.wrapper"]
        assert m[0].source == "wrapper"
        assert m[0].call.startswith("WritingSystemOperations.")

    @pytest.mark.parametrize(
        "code",
        [
            'def f(p):\n    p.LexEntry.Create("x")',
            "def f(p):\n    e = p.LexEntry\n    e.Delete(x)",
            'def f(p):\n    c = p.CustomFields\n    c.Create("x")',
            "def f(p):\n    ws = p.WritingSystems.GetAll()\n    ws.Delete(x)",
        ],
    )
    def test_j_generic_names_off_the_facade_attribute_do_not_match(self, code):
        assert detect(code) == []

    def test_j_rebound_facade_alias_does_not_match(self):
        """`w` rebound from `.WritingSystems` to `.LexEntry`: the later
        `w.Create()` is an ordinary entry edit, not a writing-system change
        (review finding on #343)."""
        code = main(
            "w = project.WritingSystems\n"
            "w = project.LexEntry\n"
            "if modifyAllowed:\n"
            '    w.Create("cat", "stem")'
        )
        assert detect(code) == []

    def test_j_facade_alias_before_rebinding_still_matches(self):
        """The rebinding only affects later calls: the `w.Delete()` before
        `w` is rebound still refuses while FieldWorks is open."""
        code = main(
            "w = project.WritingSystems\n"
            'w.Delete("en")\n'
            "w = project.LexEntry\n"
            'w.Create("cat", "stem")'
        )
        m = detect(code)
        assert keys(m) == ["ws.wrapper"]
        assert m[0].call == "WritingSystemOperations.Delete"

    def test_j_shadowing_parameter_hides_the_module_alias(self):
        """A function parameter shadows a module-level facade alias: the AST
        pass must not classify the parameter's calls (review finding on
        #343)."""
        from flextoolsmcp.server.exclusive_access import _facade_generic_matches

        code = "w = project.WritingSystems\ndef f(w):\n    w.Create('x')\n"
        assert _facade_generic_matches(ast.parse(code)) == []

    def test_facade_attrs_match_the_index_access_paths(self):
        from flextoolsmcp.server.exclusive_access import _FACADE_ATTRS

        entities = load_index().flexicon["entities"]
        for cls, attr in _FACADE_ATTRS.items():
            assert entities[cls]["access_path"] == f"project.{attr}"

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


# ---------------------------------------------------------------------------
# Conditional Ensure(): argument reading, the .fwdata read, the plan, the
# order warning
# ---------------------------------------------------------------------------

from flextoolsmcp.server.exclusive_access import (  # noqa: E402
    conditional_after_writes,
    ensure_call_args,
    plan_conditional,
    read_active_writing_systems,
)

# Sena 3's real lists; its .ldml store also holds grc and hbo, inactive.
ACTIVE = {"vernacular": ["seh", "seh-fonipa-x-etic"], "analysis": ["pt", "en"]}


def plan(body, active=ACTIVE, guard=True):
    code = main(body)
    tree = ast.parse(code)
    matches = detect(code)
    return plan_conditional(matches, ensure_call_args(tree), active, guard), matches


# The LangProject fragment as FieldWorks 9 writes it (Sena 3, 2026-10-01),
# with the inactive store-only tags in AnalysisWss / VernWss for contrast.
FWDATA_FRAGMENT = """<?xml version="1.0" encoding="utf-8"?>
<languageproject version="7000072">
<rt class="LangProject" guid="00000000-0000-0000-0000-000000000001">
<AnalysisWss>
<Uni>en pt grc</Uni>
</AnalysisWss>
<CurAnalysisWss>
<Uni>pt en</Uni>
</CurAnalysisWss>
<CurVernWss>
<Uni>seh seh-fonipa-x-etic</Uni>
</CurVernWss>
<VernWss>
<Uni>seh seh-fonipa-x-etic hbo</Uni>
</VernWss>
</rt>
</languageproject>
"""


class TestReadActiveWritingSystems:
    def test_reads_only_the_current_lists(self, tmp_path):
        f = tmp_path / "P.fwdata"
        f.write_text(FWDATA_FRAGMENT, encoding="utf-8")
        assert read_active_writing_systems(f) == {
            "analysis": ["pt", "en"],
            "vernacular": ["seh", "seh-fonipa-x-etic"],
        }

    def test_same_line_and_empty_uni(self, tmp_path):
        f = tmp_path / "P.fwdata"
        f.write_text(
            "<CurVernWss><Uni>seh</Uni></CurVernWss>\n<CurAnalysisWss><Uni/></CurAnalysisWss>\n",
            encoding="utf-8",
        )
        assert read_active_writing_systems(f) == {"vernacular": ["seh"], "analysis": []}

    def test_missing_element_is_none(self, tmp_path):
        f = tmp_path / "P.fwdata"
        f.write_text("<CurVernWss>\n<Uni>seh</Uni>\n</CurVernWss>\n", encoding="utf-8")
        assert read_active_writing_systems(f) is None

    def test_missing_file_is_none(self, tmp_path):
        assert read_active_writing_systems(tmp_path / "absent.fwdata") is None

    def test_store_only_tag_is_not_active(self, tmp_path):
        """Why the .ldml store is not enough: `grc` is in the store and in
        AnalysisWss, but not current -- Ensure('grc', analysis) would write."""
        f = tmp_path / "P.fwdata"
        f.write_text(FWDATA_FRAGMENT, encoding="utf-8")
        active = read_active_writing_systems(f)
        p, _ = plan("project.WritingSystems.Ensure('grc', 'Greek', False)", active=active)
        assert not p.allowed


class TestEnsureCallArgs:
    def test_positional_keyword_and_default(self):
        tree = ast.parse(
            "a.Ensure('en', 'English', False)\n"
            "b.Ensure(language_tag='seh', name='Sena', is_vernacular=True)\n"
            "c.Ensure('pt', 'Portuguese')\n"
        )
        assert ensure_call_args(tree) == {
            1: [("en", False)], 2: [("seh", True)], 3: [("pt", True)],
        }

    @pytest.mark.parametrize("call", [
        "a.Ensure(tag, 'x')",
        "a.Ensure('en', 'x', flag)",
        "a.Ensure(f'{x}', 'x')",
        "a.Ensure('', 'x')",
    ])
    def test_non_literal_is_none(self, call):
        assert ensure_call_args(ast.parse(call)) == {1: [None]}

    @pytest.mark.parametrize("call", [
        "a.Ensure('en', 'English', **{'is_vernacular': False})",
        "a.Ensure('en', 'English', **kw)",
        "a.Ensure('en', 'English', is_vernacular=False, **kw)",
        "a.Ensure(*args)",
        "a.Ensure('en', *rest)",
    ])
    def test_unpacked_arguments_are_none(self, call):
        """`**kwargs` may carry `is_vernacular` and `*args` shifts the
        positional slots, so the effective arguments cannot be proven from
        the source (review finding on #343). The call defers to the runtime
        peer guard instead of being judged with a defaulted category."""
        assert ensure_call_args(ast.parse(call)) == {1: [None]}


class TestPlanConditional:
    def test_active_analysis_tag_is_satisfied(self):
        p, _ = plan("project.WritingSystems.Ensure('en', 'English', is_vernacular=False)")
        assert p.allowed
        assert [m.key for m in p.satisfied] == ["ws.ensure"]
        assert p.deferred == ()

    def test_tag_compare_is_case_and_separator_blind(self):
        p, _ = plan("project.WritingSystems.Ensure('SEH_FONIPA_X_ETIC', 'x')")
        assert p.allowed

    def test_default_is_vernacular_so_analysis_tag_would_write(self):
        """`en` is analysis-only: Ensure('en', ...) ADDS it as vernacular."""
        p, _ = plan("project.WritingSystems.Ensure('en', 'English')")
        assert not p.allowed
        assert "would add a vernacular writing system" in p.notes[0]

    def test_kwargs_unpacking_defers_instead_of_misjudging(self):
        """The finding's example: `en` is analysis-only and the call passes
        `is_vernacular=False` through `**kwargs`. The old reader defaulted it
        to True and refused a no-op as a vernacular add; now the call defers
        to the runtime guard, which runs the real arguments."""
        p, _ = plan(
            "project.WritingSystems.Ensure('en', 'English', **{'is_vernacular': False})"
        )
        assert p.allowed
        assert [m.key for m in p.deferred] == ["ws.ensure"]
        assert p.refuse == ()

    def test_absent_tag_refuses_with_note(self):
        p, _ = plan("project.WritingSystems.Ensure('qaa-x-new', 'New')")
        assert [m.key for m in p.refuse] == ["ws.ensure"]
        assert "'qaa-x-new' is not active as vernacular" in p.notes[0]

    def test_non_literal_is_deferred_to_runtime(self):
        p, _ = plan("tag = pick()\nproject.WritingSystems.Ensure(tag, 'x')")
        assert p.allowed
        assert [m.key for m in p.deferred] == ["ws.ensure"]

    def test_any_unconditional_match_refuses_everything(self):
        p, matches = plan(
            "project.WritingSystems.Ensure('en', 'English', False)\n"
            "project.WritingSystems.SetFontSize('en', 12)"
        )
        assert set(p.refuse) == set(matches)

    def test_unreadable_file_defers_to_the_guard(self):
        p, _ = plan("project.WritingSystems.Ensure('qaa-x-new', 'New')", active=None)
        assert p.allowed
        assert [m.key for m in p.deferred] == ["ws.ensure"]

    def test_no_runtime_guard_refuses(self):
        p, _ = plan("project.WritingSystems.Ensure('en', 'English', False)", guard=False)
        assert not p.allowed
        assert "peer-schema-guard" in p.notes[0]


class TestConditionalAfterWrites:
    def test_ensure_after_a_write_is_flagged(self):
        code = main(
            "if modifyAllowed:\n"
            "    project.LexEntry.Create('zz', 'stem')\n"
            "    project.WritingSystems.Ensure('en', 'English', False)"
        )
        tree = ast.parse(code)
        cert = certify_script_readonly(code, load_index(), tree=tree)
        late = conditional_after_writes(detect(code), cert)
        assert [m.key for m in late] == ["ws.ensure"]

    def test_ensure_first_is_not_flagged(self):
        code = main(
            "if modifyAllowed:\n"
            "    project.WritingSystems.Ensure('en', 'English', False)\n"
            "    project.LexEntry.Create('zz', 'stem')"
        )
        tree = ast.parse(code)
        cert = certify_script_readonly(code, load_index(), tree=tree)
        assert conditional_after_writes(detect(code), cert) == []
