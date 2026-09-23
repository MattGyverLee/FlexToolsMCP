#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #95: unprotected mutating code must return a structured rejection."""

import asyncio
import json

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.handlers import execution as execution_mod


def _parse(resp_list):
    item = resp_list[0]
    text = item["text"] if isinstance(item, dict) else item.text
    return json.loads(text)


class _FakeIndex:
    flexicon = {
        "entities": {
            "LexEntryOperations": {
                "category": "lexicon",
                "methods": [
                    {"name": "Create", "signature": "(self, form)", "is_mutating": True},
                ],
                "properties": [],
            }
        }
    }


def _stub_env(monkeypatch, tmp_path):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(project_discovery, "check_project_locked", lambda name: None)
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: _FakeIndex())
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})


class TestUnprotectedWritesEnvelope:
    def test_unprotected_create_returns_structured_rejection(self, monkeypatch, tmp_path):
        _stub_env(monkeypatch, tmp_path)
        code = (
            "from flexicon import LexEntryOperations\n"
            "ops = LexEntryOperations(project)\n"
            'ops.Create("probe", create_blank_sense=True)\n'
        )
        args = {
            "code": code,
            "project_name": "TestProj_95",
            "write_enabled": True,
            "confirmed": True,
            "skip_api_check": True,
            "skip_module_check": True,
        }
        data = _parse(asyncio.run(execution_mod.handle_run_module(args)))

        assert data["status"] == "error"
        assert data["error_code"] == "unprotected_writes"
        assert data["_contract"] == CONTRACT_VERSION
        assert "modifyAllowed" in data["message"] or "modifyAllowed" in data.get("why", "")
        assert data.get("next_steps")
        assert data["error"]["code"] == "unprotected_writes"
