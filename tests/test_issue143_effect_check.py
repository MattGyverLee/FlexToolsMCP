#!/usr/bin/env python3
"""Issue #143: mutating write runs with zero LCM actions surface effect_check."""

import unittest

from flextoolsmcp.server.handlers.execution import build_effect_check_payload


class TestBuildEffectCheckPayload(unittest.TestCase):
    def test_mutating_write_zero_actions(self):
        payload = build_effect_check_payload(
            {"success": True, "lcm_undoable_action_count": 0},
            write_enabled=True,
            is_mutating_script=True,
        )
        self.assertIsNotNone(payload)
        self.assertEqual(payload["verdict"], "no_observable_effect")
        self.assertEqual(payload["lcm_undoable_action_count"], 0)

    def test_read_only_run_omits(self):
        self.assertIsNone(
            build_effect_check_payload(
                {"success": True, "lcm_undoable_action_count": 0},
                write_enabled=False,
                is_mutating_script=True,
            )
        )

    def test_non_mutating_preflight_zero_actions_omits(self):
        self.assertIsNone(
            build_effect_check_payload(
                {"success": True, "lcm_undoable_action_count": 0},
                write_enabled=True,
                is_mutating_script=False,
            )
        )

    def test_positive_action_count_omits(self):
        self.assertIsNone(
            build_effect_check_payload(
                {"success": True, "lcm_undoable_action_count": 3},
                write_enabled=True,
                is_mutating_script=True,
            )
        )

    def test_failed_run_omits(self):
        self.assertIsNone(
            build_effect_check_payload(
                {"success": False, "lcm_undoable_action_count": 0},
                write_enabled=True,
                is_mutating_script=True,
            )
        )

    def test_missing_count_omits(self):
        self.assertIsNone(
            build_effect_check_payload(
                {"success": True},
                write_enabled=True,
                is_mutating_script=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
