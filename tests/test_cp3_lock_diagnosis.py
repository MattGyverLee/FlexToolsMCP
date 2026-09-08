#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #93 CP3 (T3.1-T3.4): wiring probe_project_access() into
_diagnose_project_open_error() so a live LcmFileLockedException /
FP_FileLockedError gets a verdict-specific diagnosis instead of the generic
"close FieldWorks" hint.

Follows tests/test_rejection_payloads.py's style: bare `server.xxx` imports
(matching how handlers/execution.py resolves its own relative imports when
loaded as `server.handlers.execution`), unittest.mock.patch to stub the
probe so nothing here depends on a real projects directory or a real PID.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from server.project_access import LockHolder, ProjectAccess  # noqa: E402


_LOCKED_ERROR = (
    "Failed to open project 'Foo': LcmFileLockedException: This project is "
    "in use by another program."
)


def _access(verdict, *, pid=68436, process="FieldWorks", sharing=None, holder=True):
    return ProjectAccess(
        project_name="Foo",
        verdict=verdict,
        sharing_enabled=sharing,
        holder=LockHolder(pid=pid, process_name=process, timestamp_ticks=None) if holder else None,
        lock_age_seconds=None,
    )


class TestLockDiagnosisWiring(unittest.TestCase):
    def _diagnose(self, access_or_exc):
        from server.handlers.execution import _diagnose_project_open_error

        exec_result = {"error": _LOCKED_ERROR}
        if isinstance(access_or_exc, Exception):
            probe = _raise(access_or_exc)
        else:
            probe = lambda name: access_or_exc  # noqa: E731

        with patch("server.project_access.probe_project_access", probe):
            return _diagnose_project_open_error(exec_result, "Foo")

    def test_open_exclusive_gives_enable_sharing_remedy(self):
        diag = self._diagnose(_access("open_exclusive", sharing=False))
        assert diag is not None
        self.assertEqual(diag["verdict"], "open_exclusive")
        self.assertEqual(diag["sharing_enabled"], False)
        self.assertEqual(diag["holder_pid"], 68436)
        self.assertEqual(diag["holder_process"], "FieldWorks")
        self.assertIn("Sharing tab", diag["hint"])
        self.assertIn("never writes LexiconSettings.plsx", diag["hint"])
        # remedy mirrors build_access_remedy()'s own (blocking-verdict-only)
        # text, so it should be populated and match the hint here.
        self.assertEqual(diag["remedy"], diag["hint"])

    def test_stale_lock_names_the_dead_pid(self):
        diag = self._diagnose(_access("stale_lock", pid=4242, process="FieldWorks"))
        assert diag is not None
        self.assertEqual(diag["verdict"], "stale_lock")
        self.assertEqual(diag["holder_pid"], 4242)
        self.assertIn("4242", diag["hint"])
        self.assertIn("stale", diag["hint"])
        # build_access_remedy() deliberately has nothing to say for a lock
        # that no longer blocks anything -- remedy stays None even though
        # hint carries informational text.
        self.assertIsNone(diag["remedy"])

    def test_held_by_other_is_a_real_collision(self):
        diag = self._diagnose(
            _access("held_by_other", pid=9999, process="python", sharing=True)
        )
        assert diag is not None
        self.assertEqual(diag["verdict"], "held_by_other")
        self.assertIn("9999", diag["hint"])
        self.assertIn("python", diag["hint"])
        self.assertIn("does not resolve it", diag["hint"])
        self.assertEqual(diag["remedy"], diag["hint"])

    def test_probe_raising_falls_back_to_generic_hint(self):
        def _boom(name):
            raise OSError("registry unreadable")

        exec_result = {"error": _LOCKED_ERROR}
        from server.handlers.execution import _diagnose_project_open_error

        with patch("server.project_access.probe_project_access", _boom):
            diag = _diagnose_project_open_error(exec_result, "Foo")

        assert diag is not None
        self.assertEqual(diag["error_code"], "project_locked")
        self.assertIn("Close FieldWorks", diag["hint"])
        # No probe facts should leak onto the payload when the probe failed.
        self.assertNotIn("verdict", diag)
        self.assertNotIn("remedy", diag)

    def test_non_blocking_verdicts_fall_back_to_generic_hint(self):
        for verdict in ("free", "open_shared"):
            with self.subTest(verdict=verdict):
                diag = self._diagnose(_access(verdict, sharing=True))
                assert diag is not None
                self.assertIn("Close FieldWorks", diag["hint"])
                self.assertNotIn("verdict", diag)

    def test_unrelated_error_still_returns_none(self):
        from server.handlers.execution import _diagnose_project_open_error

        exec_result = {"error": "Execution error: AttributeError: 'X' has no attribute 'Y'"}
        diag = _diagnose_project_open_error(exec_result, "Foo")
        self.assertIsNone(diag)


def _raise(exc):
    def _inner(name):
        raise exc
    return _inner


if __name__ == "__main__":
    unittest.main()
