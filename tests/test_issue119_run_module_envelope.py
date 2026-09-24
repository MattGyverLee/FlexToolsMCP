#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #119: run_module execution responses carry the tool-response envelope."""

from flextoolsmcp.response_utils import CONTRACT_VERSION
from flextoolsmcp.server.handlers.execution import _finalize_run_module_response


class TestIssue119RunModuleEnvelope:
    def test_success_payload_stamped(self):
        data = _finalize_run_module_response(
            {"success": True, "op_id": "op-test-1", "summary": {}}
        )
        assert data["_contract"] == CONTRACT_VERSION
        assert data["status"] == "ok"
        assert data["op_id"] == "op-test-1"

    def test_runtime_failure_payload_stamped(self):
        data = _finalize_run_module_response(
            {
                "success": False,
                "op_id": "op-test-2",
                "error": "Execution error: boom",
            }
        )
        assert data["_contract"] == CONTRACT_VERSION
        assert data["status"] == "error"
        assert data["op_id"] == "op-test-2"

    def test_existing_status_not_overwritten(self):
        data = _finalize_run_module_response({"status": "ok", "executed": False})
        assert data["status"] == "ok"
        assert data["_contract"] == CONTRACT_VERSION
