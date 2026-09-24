#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #174: surface session project re-pointing on the response envelope."""

import asyncio
import json
import unittest
from unittest.mock import patch

import flextoolsmcp.server.handlers.execution as exec_mod
import flextoolsmcp.server.project_discovery as pd_mod
from flextoolsmcp.project_adoption import adopt_resolved_project
from flextoolsmcp.response_utils import build_response_with_context, error_response
from flextoolsmcp.server.session import SessionState


_BROKEN_CODE = "def Main(project, report, modifyAllowed):\n    pass"


class TestAdoptResolvedProjectHelper(unittest.TestCase):
    def test_first_adoption_emits_no_notice(self):
        session = SessionState()
        name = adopt_resolved_project(session, "ProjA", log_context="test")
        self.assertEqual(name, "ProjA")
        self.assertEqual(session.project_name, "ProjA")
        self.assertIsNone(session.project_adopted_notice)

    def test_repoint_queues_notice(self):
        session = SessionState(project_name="ProjA")
        with patch(
            "flextoolsmcp.server.kernel.get_operations_logger", return_value=None
        ):
            adopt_resolved_project(session, "ProjB", log_context="test")
        self.assertEqual(session.project_name, "ProjB")
        notice = session.project_adopted_notice
        self.assertIsNotNone(notice)
        self.assertEqual(notice["previous_project"], "ProjA")
        self.assertEqual(notice["project"], "ProjB")
        self.assertIn("ProjB", notice["message"])
        self.assertIn("ProjA", notice["message"])


class TestIssue174RunModuleEnvelope(unittest.TestCase):
    def setUp(self):
        from flextoolsmcp.server.kernel import initialize_kernel, set_api_index, get_index_dir
        from flextoolsmcp.server import APIIndex

        initialize_kernel()
        set_api_index(APIIndex.load(get_index_dir()))
        self._saved = exec_mod.session_state
        self._saved.__dict__.clear()
        self._saved.__dict__.update(SessionState().__dict__)

    def tearDown(self):
        self._saved.__dict__.clear()
        self._saved.__dict__.update(SessionState().__dict__)

    def test_repoint_surfaces_notice_on_error_envelope(self):
        passthrough = lambda name: (name, None)
        with patch.object(pd_mod, "resolve_or_explain", passthrough):
            asyncio.run(
                exec_mod.handle_run_module(
                    dict(code=_BROKEN_CODE, project_name="ProjA")
                )
            )
            self.assertEqual(exec_mod.session_state.project_name, "ProjA")

            second = asyncio.run(
                exec_mod.handle_run_module(
                    dict(code=_BROKEN_CODE, project_name="ProjB")
                )
            )
        data = json.loads(second[0].text)
        self.assertEqual(exec_mod.session_state.project_name, "ProjB")
        notice = data.get("project_adopted_notice")
        self.assertIsNotNone(notice, data.keys())
        self.assertEqual(notice["previous_project"], "ProjA")
        self.assertEqual(notice["project"], "ProjB")

    def test_first_adoption_has_no_notice(self):
        passthrough = lambda name: (name, None)
        with patch.object(pd_mod, "resolve_or_explain", passthrough):
            result = asyncio.run(
                exec_mod.handle_run_module(
                    dict(code=_BROKEN_CODE, project_name="ProjA")
                )
            )
        data = json.loads(result[0].text)
        self.assertNotIn("project_adopted_notice", data)


class TestErrorResponseAttachesNotice(unittest.TestCase):
    def test_envelope_consumes_notice_once(self):
        session = SessionState(project_name="Old", initialized=True)
        session.project_adopted_notice = {
            "previous_project": "Old",
            "project": "New",
            "message": "changed",
        }
        with patch("flextoolsmcp.server.kernel.session_state", session):
            data = build_response_with_context({"status": "ok"})
        self.assertIn("project_adopted_notice", data)
        self.assertIsNone(session.project_adopted_notice)

    def test_error_response_attaches_notice(self):
        session = SessionState(project_name="Old")
        session.project_adopted_notice = {
            "previous_project": "Old",
            "project": "New",
            "message": "changed",
        }
        with patch("flextoolsmcp.server.kernel.session_state", session):
            chunks = error_response("syntax_error", "bad")
        text = chunks[0].text if hasattr(chunks[0], "text") else chunks[0]["text"]
        data = json.loads(text)
        self.assertIn("project_adopted_notice", data)


if __name__ == "__main__":
    unittest.main()
