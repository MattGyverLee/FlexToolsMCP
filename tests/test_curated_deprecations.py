#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Curated API deprecations (curated_deprecations.py).

ILexEntry.DoNotUseForParsing (and flexicon's LexEntryOperations.Get/
SetDoNotUseForParsing) has no effect on either FLEx parser: HermitCrab's
HCLoader.cs skips only forms whose IsAbstract is set (:543 affixes, :585
stems) and XAmple's FxtM3ParserToXAmpleLex.xsl filters only on @IsAbstract.
The MCP treats it as deprecated: never taught, never run. The redirect is
IsAbstract on the entry's FORMS (LexemeFormOA / AlternateFormsOS), which is
on IMoForm, not ILexEntry.

Covers:
  - the index overlay (build-time hooks, load-time re-apply, checked-in JSON)
  - the redirect wording (names the forms, never a bare ILexEntry.IsAbstract)
  - the preflight detector (reads, writes, calls; no false positives on
    comments/strings/unrelated names) and the run_module hard block
  - the misplaced-member hint for `entry.IsAbstract`
  - rendering in get_object_api / search_by_capability / find_examples /
    resolve_property / find_wrappers_for_lcm / get_wrapper_dependencies
"""

import ast
import asyncio
import copy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from flextoolsmcp import curated_deprecations as cd
from flextoolsmcp.curated_recipes import CURATED_RECIPES
from flextoolsmcp.recipe_validator import validate_recipe
from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import (
    build_deprecated_member_rejection,
    detect_deprecated_members,
    detect_interface_attribute_typos,
)

DEP_ID = "lexentry-donotuseforparsing"
INDEX_DIR = Path(__file__).parent.parent / "src" / "flextoolsmcp" / "index"


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


def _assert_redirects_to_forms(text: str):
    """(d) Every redirect must name the forms, not just 'IsAbstract'."""
    assert "LexemeFormOA" in text, text
    assert "AlternateFormsOS" in text, text
    assert "IsAbstract" in text, text


# ---------------------------------------------------------------------------
# Curated data / redirect wording
# ---------------------------------------------------------------------------

class TestCuratedData:
    def test_note_names_the_forms_and_cites_hcloader(self):
        dep = cd.deprecation_record(DEP_ID)
        _assert_redirects_to_forms(dep["note"])
        assert "no parser effect" in dep["note"].lower()
        assert "HCLoader.cs:543" in dep["note"]
        assert ":585" in dep["note"]
        assert "IMoForm" in dep["note"]
        assert "every form is abstract" in dep["note"]

    def test_replacement_is_a_path_never_a_bare_member(self):
        """(c) No bare 'IsAbstract' replacement on ILexEntry anywhere."""
        dep = cd.deprecation_record(DEP_ID)
        assert dep["replacement_owner"] == "IMoForm"
        paths = dep["replacement_paths"]
        assert "ILexEntry.LexemeFormOA.IsAbstract" in paths
        assert "ILexEntry.AlternateFormsOS[*].IsAbstract" in paths
        for p in paths:
            assert p != "IsAbstract" and p != "ILexEntry.IsAbstract"
        for info in cd.MISPLACED_MEMBERS.values():
            for p in info["correct_paths"]:
                assert p != "ILexEntry.IsAbstract"

    def test_example_walks_entry_to_forms_and_guards(self):
        """(b) Runnable example: entry -> forms, guards LexemeFormOA and the write."""
        ex = cd.deprecation_record(DEP_ID)["example"]
        ast.parse(ex)
        _assert_redirects_to_forms(ex)
        assert "LexemeFormOA is not None" in ex
        assert "if modifyAllowed:" in ex
        assert "form.IsAbstract = True" in ex
        # the example itself must never use the deprecated member...
        assert detect_deprecated_members(ex)["has_deprecated"] is False
        # ...nor touch IsAbstract on the entry itself (only on its forms).
        on_entry = [
            n for n in ast.walk(ast.parse(ex))
            if isinstance(n, ast.Attribute) and n.attr == "IsAbstract"
            and isinstance(n.value, ast.Name) and n.value.id == "entry"
        ]
        assert on_entry == []

    def test_example_passes_recipe_preflight(self):
        recipe = CURATED_RECIPES["hide-entry-from-parser"]
        assert recipe["code"] == cd.deprecation_record(DEP_ID)["example"]
        result = validate_recipe(recipe, None)
        assert result["passed"], result["issues"]

    def test_lookup_member(self):
        assert cd.lookup_member("DoNotUseForParsing", "ILexEntry", "liblcm")["id"] == DEP_ID
        assert cd.lookup_member("ILexEntry.DoNotUseForParsing")["id"] == DEP_ID
        assert cd.lookup_member("LexEntryOperations.SetDoNotUseForParsing")["id"] == DEP_ID
        assert cd.lookup_member("GetDoNotUseForParsing")["id"] == DEP_ID
        assert cd.lookup_member("DoNotUseForParsing", "ILexSense") is None
        assert cd.lookup_member("IsAbstract") is None
        assert cd.lookup_member("") is None

    def test_match_intent(self):
        assert [d["id"] for d in cd.match_intent("hide entry from parser")] == [DEP_ID]
        assert [d["id"] for d in cd.match_intent("set DoNotUseForParsing")] == [DEP_ID]
        assert [d["id"] for d in cd.match_intent("do_not_use_for_parsing")] == [DEP_ID]
        assert cd.match_intent("list entries with glosses") == []
        assert cd.match_intent(None) == []


# ---------------------------------------------------------------------------
# Index overlay
# ---------------------------------------------------------------------------

def _fake_liblcm():
    prop = {"name": "DoNotUseForParsing", "kind": "property", "description": "Property of type Boolean"}
    other = {"name": "LexemeFormOA", "kind": "OA", "description": "x"}
    return {"entities": {
        "ILexEntry": {"properties": [copy.deepcopy(prop), copy.deepcopy(other)], "methods": []},
        "LexEntry": {"properties": [copy.deepcopy(prop)], "methods": []},
        "ILexSense": {"properties": [copy.deepcopy(prop)], "methods": []},  # not a target
    }}


class TestOverlay:
    def test_apply_to_api_index_marks_only_targets(self):
        data = _fake_liblcm()
        assert cd.apply_to_api_index(data, "liblcm") == 2
        ile = data["entities"]["ILexEntry"]["properties"]
        assert ile[0]["deprecated"] is True
        assert ile[0]["deprecation"]["id"] == DEP_ID
        assert "deprecated" not in ile[1]
        assert data["entities"]["LexEntry"]["properties"][0]["deprecated"] is True
        assert "deprecated" not in data["entities"]["ILexSense"]["properties"][0]
        # a different library key leaves liblcm rows alone
        fresh = _fake_liblcm()
        assert cd.apply_to_api_index(fresh, "flexicon") == 0

    def test_apply_is_idempotent(self):
        data = _fake_liblcm()
        cd.apply_to_api_index(data, "liblcm")
        once = copy.deepcopy(data)
        cd.apply_to_api_index(data, "liblcm")
        assert data == once

    def test_bridge_and_casting(self):
        bridge = {"by_method": {"LexEntryOperations.SetDoNotUseForParsing": {"method": "SetDoNotUseForParsing"}}}
        assert cd.apply_to_bridge(bridge, "flexicon") == 1
        assert bridge["by_method"]["LexEntryOperations.SetDoNotUseForParsing"]["deprecated"] is True
        casting = {"properties": {"DoNotUseForParsing": {"defined_on": ["ILexEntry"]}, "IsAbstract": {}}}
        assert cd.apply_to_casting_index(casting) == 1
        assert casting["properties"]["DoNotUseForParsing"]["deprecated"] is True
        assert "deprecated" not in casting["properties"]["IsAbstract"]

    def test_malformed_input_is_safe(self):
        assert cd.apply_to_api_index(None, "liblcm") == 0
        assert cd.apply_to_api_index({"entities": []}, "liblcm") == 0
        assert cd.apply_to_bridge(None, "flexicon") == 0
        assert cd.apply_to_casting_index({}) == 0

    @pytest.mark.parametrize("pattern,kind,library", [
        ("liblcm/liblcm_api_v*.json", "api", "liblcm"),
        ("python/flexicon_api_v*.json", "api", "flexicon"),
        ("python/flexicon_lcm_bridge_v*.json", "bridge", "flexicon"),
        ("casting_index_liblcm-v*.json", "casting", "liblcm"),
    ])
    def test_checked_in_indexes_carry_the_annotation(self, pattern, kind, library):
        """The shipped JSON is already overlaid (python -m
        flextoolsmcp.curated_deprecations --apply is a no-op on it)."""
        files = sorted(INDEX_DIR.glob(pattern))
        assert files, f"no index file matches {pattern}"
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            before = copy.deepcopy(data)
            if kind == "api":
                n = cd.apply_to_api_index(data, library)
            elif kind == "bridge":
                n = cd.apply_to_bridge(data, library)
            else:
                n = cd.apply_to_casting_index(data)
            assert n > 0, f"{path.name}: no DoNotUseForParsing member found"
            assert data == before, (
                f"{path.name} is missing the curated deprecation overlay -- run "
                f"`python -m flextoolsmcp.curated_deprecations --apply`"
            )

    def test_load_time_overlay_on_an_unannotated_index(self, tmp_path):
        """An index generated before the overlay existed is annotated on load."""
        from flextoolsmcp.server import APIIndex

        lib_dir = tmp_path / "liblcm"
        lib_dir.mkdir()
        (lib_dir / "liblcm_api_v99.0.0.json").write_text(json.dumps(_fake_liblcm()), encoding="utf-8")
        loader = APIIndex.load.__func__.__globals__["_load_library_api_index"]
        idx = APIIndex()
        loader(idx, tmp_path, "LibLCM", "liblcm_api", lambda: None, "liblcm", "liblcm_version")
        prop = idx.liblcm["entities"]["ILexEntry"]["properties"][0]
        assert prop["deprecated"] is True
        assert prop["deprecation"]["id"] == DEP_ID

    def test_builders_apply_the_overlay(self):
        """Regeneration keeps the annotation: each builder calls the overlay."""
        src = Path(cd.__file__).parent
        assert "apply_curated_deprecations(stamped_doc, \"liblcm\")" in (src / "liblcm_extractor.py").read_text(encoding="utf-8")
        analyzer = (src / "flexicon_analyzer.py").read_text(encoding="utf-8")
        assert "apply_to_api_index(api_data, library_key)" in analyzer
        assert "apply_to_bridge(bridge_data, library_key)" in analyzer
        assert "apply_to_casting_index(casting_index)" in (src / "build_casting_index.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Preflight detector
# ---------------------------------------------------------------------------

class TestDetectDeprecatedMembers:
    @pytest.mark.parametrize("code,member,access", [
        ("x = entry.DoNotUseForParsing\n", "DoNotUseForParsing", "read"),
        ("entry.DoNotUseForParsing = True\n", "DoNotUseForParsing", "write"),
        ("if modifyAllowed:\n    ILexEntry(e).DoNotUseForParsing = False\n", "DoNotUseForParsing", "write"),
        ("v = project.LexEntry.GetDoNotUseForParsing(entry)\n", "GetDoNotUseForParsing", "read"),
        ("if modifyAllowed:\n    project.LexEntry.SetDoNotUseForParsing(entry, True)\n", "SetDoNotUseForParsing", "read"),
        ("from flexicon import LexEntryOperations\nLexEntryOperations(project).SetDoNotUseForParsing(e, 1)\n", "SetDoNotUseForParsing", "read"),
        ("f = project.LexEntry.GetDoNotUseForParsing\n", "GetDoNotUseForParsing", "read"),
        ("setattr(entry, 'DoNotUseForParsing', True)\n", "DoNotUseForParsing", "write"),
        ("getattr(entry, \"DoNotUseForParsing\")\n", "DoNotUseForParsing", "read"),
    ])
    def test_flags_every_use(self, code, member, access):
        result = detect_deprecated_members(code)
        assert result["has_deprecated"] is True
        assert result["findings"][0]["member"] == member
        assert result["findings"][0]["access"] == access
        assert DEP_ID in result["deprecations"]
        _assert_redirects_to_forms(result["suggestion"])

    @pytest.mark.parametrize("code", [
        "# entry.DoNotUseForParsing = True\nx = 1\n",
        "s = 'entry.DoNotUseForParsing = True'\n",
        "s = \"project.LexEntry.SetDoNotUseForParsing(e, True)\"\n",
        '"""Docstring mentioning DoNotUseForParsing and SetDoNotUseForParsing."""\n',
        "report.Info(f'DoNotUseForParsing is deprecated')\n",
        "x = entry.DoNotUseForParsingX\n",
        "do_not_use_for_parsing = True\n",
        "DoNotUseForParsing = 3\nprint(DoNotUseForParsing)\n",
        "entry.LexemeFormOA.IsAbstract = True\n",
        "getattr(entry, name)\n",
    ])
    def test_no_false_positives(self, code):
        assert detect_deprecated_members(code)["has_deprecated"] is False

    def test_syntax_error_is_clean(self):
        assert detect_deprecated_members("def (:\n")["has_deprecated"] is False

    def test_accepts_preparsed_tree_and_reports_lines(self):
        code = "a = 1\nb = entry.DoNotUseForParsing\nproject.LexEntry.SetDoNotUseForParsing(entry, b)\n"
        result = detect_deprecated_members(code, ast.parse(code))
        assert [(f["member"], f["line"]) for f in result["findings"]] == [
            ("DoNotUseForParsing", 2), ("SetDoNotUseForParsing", 3),
        ]

    def test_names_come_from_curated_data(self):
        """Driven by CURATED_DEPRECATIONS, not a hard-coded string."""
        names = cd.deprecated_code_names()
        assert set(names) == {"DoNotUseForParsing", "GetDoNotUseForParsing", "SetDoNotUseForParsing"}


class TestRejectionMessage:
    def test_message_and_next_steps_redirect_to_the_forms(self):
        """(b)+(d): message and next_steps both carry the entry->forms example."""
        check = detect_deprecated_members("entry.DoNotUseForParsing = True\n")
        rej = build_deprecated_member_rejection(check)
        _assert_redirects_to_forms(rej["message"])
        assert "no parser effect" in rej["message"].lower()
        assert "LexemeFormOA is not None" in rej["message"]
        joined = "\n".join(rej["next_steps"])
        _assert_redirects_to_forms(joined)
        assert "LexemeFormOA is not None" in joined
        assert rej["replacement_example"] in rej["message"]
        assert any(rej["replacement_example"] in s for s in rej["next_steps"])
        assert rej["next_steps"][-1].endswith("Re-run flextools_run_module().")


# ---------------------------------------------------------------------------
# run_module hard block
# ---------------------------------------------------------------------------

def _boom(*a, **k):
    raise AssertionError("must not get past preflight")


def _stub_env(monkeypatch, tmp_path):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "check_project_locked", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(execution_mod, "get_project_write_lock", _boom)
    monkeypatch.setattr(execution_mod, "run_script_async", _boom)


class TestRunModuleRefuses:
    @pytest.mark.parametrize("write_enabled", [False, True])
    @pytest.mark.parametrize("code", [
        "for entry in project.LexEntry.GetAll():\n    report.Info(str(entry.DoNotUseForParsing))\n",
        "for entry in project.LexEntry.GetAll():\n    report.Info(str(project.LexEntry.GetDoNotUseForParsing(entry)))\n",
        # unguarded write: told "deprecated", not "unprotected_writes"
        "for entry in project.LexEntry.GetAll():\n    project.LexEntry.SetDoNotUseForParsing(entry, True)\n",
        "for entry in project.LexEntry.GetAll():\n    if modifyAllowed:\n        entry.DoNotUseForParsing = True\n",
    ])
    def test_refused_read_and_write(self, monkeypatch, tmp_path, code, write_enabled):
        _stub_env(monkeypatch, tmp_path)
        args = {
            "code": code,
            "project_name": "TestProj_dnufp",
            "write_enabled": write_enabled,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
            "source": "existing",
        }
        data = _parse(run_async(execution_mod.handle_run_module(args)))
        assert data["status"] == "error"
        assert data["error_code"] == "deprecated_member"
        _assert_redirects_to_forms(data["message"])
        _assert_redirects_to_forms("\n".join(data["next_steps"]))
        assert data["findings"]
        assert data["deprecations"][0]["id"] == DEP_ID
        assert "LexemeFormOA is not None" in data["replacement_example"]

    def test_comment_only_mention_is_not_refused_by_this_gate(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        seen = {}

        async def _fake_run(path, timeout_seconds):
            seen["ran"] = True
            payload = {"success": True, "summary": {"info_count": 0, "warning_count": 0, "error_count": 0}, "messages": []}
            return {"stdout": "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload), "stderr": "", "timeout": False, "returncode": 0}

        monkeypatch.setattr(execution_mod, "run_script_async", _fake_run)
        args = {
            "code": "# DoNotUseForParsing is deprecated; see IsAbstract\nx = 'SetDoNotUseForParsing'\nreport.Info(x)\n",
            "project_name": "TestProj_dnufp2",
            "write_enabled": False,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        data = _parse(run_async(execution_mod.handle_run_module(args)))
        assert data.get("error_code") != "deprecated_member", data


# ---------------------------------------------------------------------------
# Misplaced member: entry.IsAbstract
# ---------------------------------------------------------------------------

class _FakeIndex:
    liblcm = {"entities": {
        "ILexEntry": {"properties": [{"name": "LexemeFormOA"}, {"name": "AlternateFormsOS"},
                                     {"name": "DoNotUseForParsing"}], "methods": []},
        "IMoForm": {"properties": [{"name": "IsAbstract"}, {"name": "Form"}], "methods": []},
    }}
    flexicon = {"entities": {}}
    flexlibs_stable = None


class TestMisplacedIsAbstract:
    def test_entry_isabstract_points_to_the_forms(self):
        """(e) `entry.IsAbstract` on an ILexEntry receiver -> hint names the forms."""
        code = "e = ILexEntry(obj)\nif modifyAllowed:\n    e.IsAbstract = True\n"
        result = detect_interface_attribute_typos(ast.parse(code), _FakeIndex())
        assert result["has_typos"] is True
        issue = result["issues"][0]
        assert issue["kind"] == "misplaced_member"
        assert issue["severity"] == "error"
        assert issue["correct_owner"] == "IMoForm"
        _assert_redirects_to_forms(issue["suggestion"])
        # (c) the suggestion is a path on the forms, never a bare member
        assert issue["did_you_mean"] == ["e.LexemeFormOA.IsAbstract", "e.AlternateFormsOS[*].IsAbstract"]
        assert issue["rewrite"] is None
        assert issue["cast_interface"] is None

    def test_form_isabstract_is_fine(self):
        code = "f = IMoForm(obj)\nf.IsAbstract = True\n"
        assert detect_interface_attribute_typos(ast.parse(code), _FakeIndex())["has_typos"] is False


# ---------------------------------------------------------------------------
# Rendering in discovery tools (real shipped index)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_index():
    from flextoolsmcp.server import APIIndex, get_index_dir
    kernel.initialize_kernel()
    idx = APIIndex.load(get_index_dir())
    idx.ensure_liblcm_loaded()
    idx.ensure_casting_index_loaded()
    return idx


@pytest.fixture
def api_session(real_index):
    from flextoolsmcp.server.handlers import api as api_handlers
    kernel.set_api_index(real_index)
    kernel.session_state.configure(session_id="test-deprecations", api_mode="all")
    previous = api_handlers.session_state.api_mode
    api_handlers.session_state.api_mode = "all"
    yield real_index
    api_handlers.session_state.api_mode = previous


class TestRendering:
    def test_loaded_index_is_annotated(self, real_index):
        props = {p["name"]: p for p in real_index.liblcm["entities"]["ILexEntry"]["properties"]}
        assert props["DoNotUseForParsing"]["deprecated"] is True
        methods = {m["name"]: m for m in real_index.flexicon["entities"]["LexEntryOperations"]["methods"]}
        assert methods["SetDoNotUseForParsing"]["deprecated"] is True
        assert methods["GetDoNotUseForParsing"]["deprecated"] is True
        assert real_index.casting_index["properties"]["DoNotUseForParsing"]["deprecated"] is True

    @pytest.mark.parametrize("summary_only", [True, False])
    def test_get_object_api_liblcm(self, api_session, summary_only):
        from flextoolsmcp.server.handlers.api import handle_get_object_api
        payload = _parse(run_async(handle_get_object_api({
            "object_type": "ILexEntry", "summary_only": summary_only,
            "method_filter": "DoNotUseForParsing", "limit": 50, "offset": 0,
        })))
        lib = payload["liblcm"]
        row = {p["name"]: p for p in lib["properties"]}["DoNotUseForParsing"]
        assert row["deprecated"] is True
        assert row["description"].startswith("DEPRECATED")
        _assert_redirects_to_forms(row["deprecation"]["note"])
        assert [m["name"] for m in lib["deprecated_members"]] == ["DoNotUseForParsing"]
        assert "IsAbstract" not in {p["name"] for p in lib["properties"]}

    def test_get_object_api_summary_lists_deprecations_beyond_the_page(self, api_session):
        from flextoolsmcp.server.handlers.api import handle_get_object_api
        payload = _parse(run_async(handle_get_object_api({
            "object_type": "LexEntryOperations", "limit": 1, "offset": 0,
        })))
        names = {m["name"] for m in payload["flexicon"]["deprecated_members"]}
        assert names == {"GetDoNotUseForParsing", "SetDoNotUseForParsing"}

    def test_get_object_api_thin_operations_index(self, api_session):
        from flextoolsmcp.server.handlers.api import handle_get_object_api
        payload = _parse(run_async(handle_get_object_api({
            "object_type": "LexEntryOperations", "limit": 500, "offset": 0,
        })))
        rows = {m["name"]: m for m in payload["flexicon"]["methods"]}
        assert rows["SetDoNotUseForParsing"]["deprecated"] is True
        assert rows["SetDoNotUseForParsing"]["description"].startswith("DEPRECATED")
        assert "deprecated" not in rows.get("GetAll", {})

    def test_search_demotes_and_redirects(self, api_session):
        from flextoolsmcp.server.handlers.api import handle_search_by_capability
        payload = _parse(run_async(handle_search_by_capability({
            "query": "DoNotUseForParsing", "semantic": False, "max_results": 10, "api_mode": "all",
        })))
        results = payload["results"]
        flags = [bool(r.get("deprecated")) for r in results]
        assert any(flags), results
        # every deprecated row sits below every live row
        assert flags == sorted(flags)
        assert payload["deprecation_redirects"][0]["id"] == DEP_ID
        _assert_redirects_to_forms(payload["deprecation_redirects"][0]["note"])

    def test_hide_from_parser_query_leads_to_isabstract(self, api_session):
        from flextoolsmcp.server.handlers.api import handle_search_by_capability
        payload = _parse(run_async(handle_search_by_capability({
            "query": "hide entry from parser", "semantic": False, "max_results": 10, "api_mode": "all",
        })))
        assert payload["deprecation_redirects"][0]["id"] == DEP_ID
        if payload["results"]:
            top = payload["results"][0]
            assert not top.get("deprecated")
            assert top.get("recipe", {}).get("id") == "hide-entry-from-parser"
            _assert_redirects_to_forms(top["recipe"]["code"])

    def test_find_examples_redirect(self, api_session):
        from flextoolsmcp.server.handlers.api import handle_find_examples
        payload = _parse(run_async(handle_find_examples({"method_name": "SetDoNotUseForParsing"})))
        assert all("DoNotUseForParsing" not in e["method_name"] for e in payload["examples"])
        assert payload["deprecation_redirects"][0]["id"] == DEP_ID

    def test_resolve_property_deprecated(self, api_session):
        from flextoolsmcp.server.handlers.api import handle_resolve_property
        payload = _parse(run_async(handle_resolve_property({
            "property_name": "DoNotUseForParsing", "context_entity": "ILexEntry",
        })))
        assert payload["deprecated"] is True
        _assert_redirects_to_forms(payload["warning"])

    def test_resolve_property_misplaced_isabstract(self, api_session):
        from flextoolsmcp.server.handlers.api import handle_resolve_property
        payload = _parse(run_async(handle_resolve_property({
            "property_name": "IsAbstract", "context_entity": "ILexEntry",
        })))
        assert payload["misplaced_member"]["correct_owner"] == "IMoForm"
        _assert_redirects_to_forms(payload["warning"])

    def test_find_wrappers_for_lcm(self):
        from flextoolsmcp.server.handlers.equivalence import handle_find_wrappers_for_lcm
        empty_reverse = {"by_liblcm_entity": {}, "properties": {}, "methods": {}, "factories": {}, "repositories": {}}
        with patch("flextoolsmcp.server.handlers.equivalence._get_reverse_mapping", return_value=empty_reverse):
            payload = _parse(asyncio.run(handle_find_wrappers_for_lcm({"lcm_name": "ILexEntry.DoNotUseForParsing"})))
        assert payload["deprecated"] is True
        _assert_redirects_to_forms(payload["advisory"])

    def test_get_wrapper_dependencies(self):
        from flextoolsmcp.server.handlers.equivalence import handle_get_wrapper_dependencies
        bridge = {"by_method": {"LexEntryOperations.SetDoNotUseForParsing": {"method": "SetDoNotUseForParsing"}}}
        with patch("flextoolsmcp.server.handlers.equivalence._get_bridge", return_value=bridge):
            payload = _parse(asyncio.run(handle_get_wrapper_dependencies({
                "method": "LexEntryOperations.SetDoNotUseForParsing", "library": "flexicon",
            })))
        assert payload["found"] is True
        assert payload["deprecated"] is True
        _assert_redirects_to_forms(payload["advisory"])
