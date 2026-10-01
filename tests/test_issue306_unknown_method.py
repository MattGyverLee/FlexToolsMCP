#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #306: a method its Operations class does not have is unknown_method.

Field report (run_module preflight):

    writeability: class=ParserOperations method=TryWord source=unknown
    mutating_calls=['TryWord']

ParserOperations has no TryWord (real: ParseWord, ParseWordXml,
TraceWordXml). certify_script_readonly() reported a name absent from a KNOWN
class as a suspected mutation, so run_module refused it as unprotected_writes
and the model looped adding guards to a call that could never run.

Now:
  * a name that is on neither the class nor any indexed base is reported in
    ``cert["unknown_methods"]`` (with did-you-mean), NOT as a mutation;
  * run_module rejects it as ``unknown_method``;
  * every receiver shape (project.Parser.X, alias, inline construction,
    attached facade) and guarded/unguarded code get the same verdict;
  * real indexed mutating methods are still unprotected writes, real
    read-only methods still pass, inherited base-class methods are not
    "unknown", and an unindexed class keeps its old behavior.
"""

import asyncio
import json
from functools import lru_cache

import pytest

from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.validators import (
    build_unknown_method_rejection,
    certify_script_readonly,
    suggest_ops_methods,
)


class _FakeIndex:
    casting_index = {}
    flexicon = {
        "entities": {
            "FLExProject": {
                "properties": [
                    {"name": "Parser", "return_type": "ParserOperations"},
                    {"name": "LexEntry", "return_type": "LexEntryOperations"},
                ],
                "methods": [{"name": "FromOpenProject", "return_type": ""}],
            },
            "BaseOperations": {
                "base_classes": [],
                "methods": [
                    {"name": "MoveUp", "is_mutating": True},
                    {"name": "CompareTo", "is_mutating": False},
                ],
            },
            "ParserOperations": {
                "access_path": "project.Parser",
                "base_classes": ["BaseOperations"],
                "methods": [
                    {"name": "ParseWord", "is_mutating": False},
                    {"name": "ParseWordXml", "is_mutating": False},
                    {"name": "TraceWordXml", "is_mutating": False},
                    {"name": "Reload", "is_mutating": False},
                ],
            },
            "LexEntryOperations": {
                "access_path": "project.LexEntry",
                "base_classes": ["BaseOperations"],
                "methods": [
                    {"name": "GetAll", "is_mutating": False},
                    {"name": "GetLexemeForm", "is_mutating": False},
                    {"name": "SetLexemeForm", "is_mutating": True},
                    {"name": "Create", "is_mutating": True},
                ],
            },
            # Base chain names a class the index does not have: the member
            # list is incomplete, so the pre-#306 path must apply.
            "MysteryOperations": {
                "base_classes": ["NotIndexedBase"],
                "methods": [{"name": "Known", "is_mutating": False}],
            },
        }
    }


IDX = _FakeIndex()

DIRECT = 'result = project.Parser.TryWord("kitabu")\n'
ALIAS = 'parser_ops = project.Parser\nresult = parser_ops.TryWord("kitabu")\n'
INLINE = (
    "from flexicon import ParserOperations\n"
    'result = ParserOperations(project).TryWord("kitabu")\n'
)
FACADE = (
    "from flexicon import FLExProject\n"
    "fx = FLExProject.FromOpenProject(project)\n"
    'result = fx.Parser.TryWord("kitabu")\n'
)
GUARDED = 'if modifyAllowed:\n    result = project.Parser.TryWord("kitabu")\n'


def _verdict(cert):
    """The parts of a cert that decide the run_module verdict."""
    return (
        cert["is_certified_readonly"],
        tuple((c["class"], c["method"]) for c in cert["mutating_calls"]),
        tuple((f["class"], f["method"], tuple(f["did_you_mean"])) for f in cert["unknown_methods"]),
    )


class TestCertifyUnknownMethod:
    @pytest.mark.parametrize("code", [DIRECT, ALIAS, INLINE, FACADE, GUARDED],
                             ids=["direct", "alias", "inline", "facade", "guarded"])
    def test_unknown_method_is_not_a_mutation(self, code):
        cert = certify_script_readonly(code, IDX)
        assert cert["is_certified_readonly"] is True
        assert cert["mutating_calls"] == []
        assert [(f["class"], f["method"]) for f in cert["unknown_methods"]] == [
            ("ParserOperations", "TryWord")
        ]
        assert cert["unknown_calls"][0]["reason"] == "unknown_method"

    def test_all_receiver_shapes_get_the_same_verdict(self):
        verdicts = {_verdict(certify_script_readonly(c, IDX))
                    for c in (DIRECT, ALIAS, INLINE, FACADE, GUARDED)}
        assert len(verdicts) == 1, verdicts

    def test_did_you_mean_names_the_real_parser_methods(self):
        cert = certify_script_readonly(DIRECT, IDX)
        finding = cert["unknown_methods"][0]
        assert finding["did_you_mean"][:3] == ["ParseWord", "ParseWordXml", "TraceWordXml"]
        # available_methods includes inherited base-class methods.
        assert "MoveUp" in finding["available_methods"]
        assert "ParseWord" in finding["available_methods"]

    def test_real_indexed_mutating_method_still_unprotected(self):
        cert = certify_script_readonly('project.LexEntry.SetLexemeForm(e, "x")\n', IDX)
        assert cert["is_certified_readonly"] is False
        assert [(c["class"], c["method"], c["source"]) for c in cert["mutating_calls"]] == [
            ("LexEntryOperations", "SetLexemeForm", "index")
        ]
        assert cert["unknown_methods"] == []

    def test_aliased_real_mutating_method_still_unprotected(self):
        code = 'ops = project.LexEntry\nops.SetLexemeForm(e, "x")\n'
        cert = certify_script_readonly(code, IDX)
        assert cert["is_certified_readonly"] is False
        assert cert["unknown_methods"] == []

    def test_real_readonly_method_passes(self):
        cert = certify_script_readonly('r = project.Parser.ParseWord("kitabu")\n', IDX)
        assert cert["is_certified_readonly"] is True
        assert cert["unknown_methods"] == []
        assert cert["unknown_calls"] == []

    def test_inherited_base_method_is_not_unknown(self):
        """MoveUp lives on BaseOperations; it must not be an unknown_method,
        and (unguarded) keeps the conservative pre-#306 mutating verdict."""
        cert = certify_script_readonly("project.LexEntry.MoveUp(e)\n", IDX)
        assert cert["unknown_methods"] == []
        assert cert["is_certified_readonly"] is False

    def test_unindexed_class_behavior_unchanged(self):
        cert = certify_script_readonly(
            "from flexicon import ZzzOperations\nZzzOperations(project).TryWord(x)\n", IDX
        )
        assert cert["unknown_methods"] == []
        assert cert["is_certified_readonly"] is True

    def test_incomplete_base_chain_keeps_old_conservative_path(self):
        code = "from flexicon import MysteryOperations\nMysteryOperations(project).Frobnicate(x)\n"
        cert = certify_script_readonly(code, IDX)
        assert cert["unknown_methods"] == []
        assert [(c["class"], c["method"], c["source"]) for c in cert["mutating_calls"]] == [
            ("MysteryOperations", "Frobnicate", "unknown")
        ]

    def test_issue32_unindexed_getter_still_tolerated(self):
        """A Get* name with no confident close match is still let through
        as read-only (issue #32: getter added before the index refresh)."""
        cert = certify_script_readonly("x = project.LexEntry.GetHeadwordAndCategory()\n", IDX)
        assert cert["is_certified_readonly"] is True
        assert cert["unknown_methods"] == []

    def test_getter_typo_is_unknown_in_alias_form_too(self):
        """GetLexemForm is a confident typo of GetLexemeForm: the direct form
        was already caught by invalid_api_chain; the alias form now matches."""
        for code in ("x = project.LexEntry.GetLexemForm(e)\n",
                     "ops = project.LexEntry\nx = ops.GetLexemForm(e)\n"):
            cert = certify_script_readonly(code, IDX)
            assert [f["did_you_mean"][0] for f in cert["unknown_methods"]] == ["GetLexemeForm"], code


class TestSuggestions:
    def test_typo_ranks_first(self):
        assert suggest_ops_methods("SetLexemForm", ["Create", "SetLexemeForm", "GetLexemeForm"])[0] == "SetLexemeForm"

    def test_shared_noun_beats_unrelated(self):
        assert suggest_ops_methods("TryWord", ["Reload", "ParseWord", "TraceWordXml", "ParseWordXml"]) == [
            "ParseWord", "ParseWordXml", "TraceWordXml"
        ]

    def test_rejection_payload(self):
        rej = build_unknown_method_rejection(certify_script_readonly(ALIAS, IDX))
        assert rej is not None
        assert "ParserOperations.TryWord" in rej["message"]
        assert "does not exist" in rej["message"]
        assert "not a write-safety problem" in rej["message"]
        assert rej["did_you_mean"][:3] == ["ParseWord", "ParseWordXml", "TraceWordXml"]
        assert rej["next_steps"]
        assert build_unknown_method_rejection(
            certify_script_readonly('project.Parser.ParseWord("x")\n', IDX)
        ) is None


# ---------------------------------------------------------------------------
# run_module end to end (preflight only; never reaches the subprocess)
# ---------------------------------------------------------------------------

def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


def _stub_env(monkeypatch, tmp_path):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "find_lock_file", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: IDX)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(
        execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []}
    )


def _run(code, write_enabled=False, **extra):
    args = {
        "code": code,
        "project_name": "TestProj_306",
        "write_enabled": write_enabled,
        "skip_api_check": True,
        "skip_module_check": True,
        "auto_fix": False,
        **extra,
    }
    if write_enabled:
        args["confirmed"] = True
    return _parse(asyncio.run(execution_mod.handle_run_module(args)))


class TestRunModule:
    @pytest.mark.parametrize("code", [DIRECT, ALIAS, GUARDED], ids=["direct", "alias", "guarded"])
    @pytest.mark.parametrize("write_enabled", [False, True], ids=["ro", "rw"])
    def test_rejects_as_unknown_method(self, monkeypatch, tmp_path, code, write_enabled):
        _stub_env(monkeypatch, tmp_path)
        data = _run(code, write_enabled=write_enabled)
        assert data["status"] == "error"
        assert data["error_code"] == "unknown_method", data.get("message")
        assert data["error"]["code"] == "unknown_method"
        assert data["did_you_mean"][:3] == ["ParseWord", "ParseWordXml", "TraceWordXml"]
        assert data["unknown_methods"][0]["class"] == "ParserOperations"
        assert data["unknown_methods"][0]["method"] == "TryWord"
        assert data.get("next_steps")

    def test_direct_and_alias_same_payload(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        a, b = _run(DIRECT), _run(ALIAS)
        assert (a["error_code"], a["did_you_mean"]) == (b["error_code"], b["did_you_mean"])

    def test_real_mutating_method_still_unprotected_writes(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        data = _run('project.LexEntry.SetLexemeForm(e, "x")\n', write_enabled=True)
        assert data["error_code"] == "unprotected_writes"

    def test_validate_only_reports_unknown_method_once(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        data = _run(DIRECT, validate_only=True)
        by_gate = {c["gate"]: c for c in data["checks"]}
        assert by_gate["unknown_method"]["passed"] is False
        assert by_gate["unknown_method"]["did_you_mean"][0] == "ParseWord"
        assert by_gate["unprotected_writes"]["passed"] is True
        # Not double-listed by the chain gate.
        assert by_gate["invalid_api_chain"]["passed"] is True


# ---------------------------------------------------------------------------
# Against the shipped index (the issue's environment)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _real_index():
    from flextoolsmcp.server import APIIndex, get_index_dir

    return APIIndex.load(get_index_dir())


class TestShippedIndex:
    def test_trywords_on_shipped_index(self):
        try:
            idx = _real_index()
        except Exception as exc:  # pragma: no cover - packaging-dependent
            pytest.skip(f"shipped index unavailable: {exc}")
        if "ParserOperations" not in (idx.flexicon or {}).get("entities", {}):
            pytest.skip("shipped index has no ParserOperations")
        verdicts = set()
        for code in (DIRECT, ALIAS):
            cert = certify_script_readonly(code, idx)
            assert cert["mutating_calls"] == [], code
            [finding] = cert["unknown_methods"]
            assert {"ParseWord", "ParseWordXml", "TraceWordXml"} <= set(finding["did_you_mean"])
            verdicts.add(_verdict(cert))
        assert len(verdicts) == 1
