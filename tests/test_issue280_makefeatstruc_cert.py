#!/usr/bin/env python3
"""Issue #280: MakeFeatStruc must classify as mutating for write certification."""

import unittest

from flextoolsmcp.server import APIIndex, get_index_dir
from flextoolsmcp.server.handlers.execution import build_effect_check_payload
from flextoolsmcp.server.validators import (
    build_write_certification_payload,
    certify_script_readonly,
    compute_is_mutating_script,
    detect_cud_operations,
)


class TestMakeFeatStrucWriteCertification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api_index = APIIndex.load(get_index_dir())

    def test_inflection_features_makefeatstruc_index_is_mutating(self):
        entity = self.api_index.flexicon["entities"]["InflectionFeatureOperations"]
        methods = {m["name"]: m for m in entity["methods"]}
        self.assertTrue(methods["MakeFeatStruc"]["is_mutating"])

    def test_guarded_makefeatstruc_preflight_mutating(self):
        code = """
from flexicon import FLExProject

def Main(project, report, modify):
    if modifyAllowed:
        project.InflectionFeatures.MakeFeatStruc([], owner=msa)
"""
        cert = certify_script_readonly(code, self.api_index)
        cud = detect_cud_operations(code)
        self.assertTrue(compute_is_mutating_script(cert, cud))
        payload = build_write_certification_payload(cert, cud)
        self.assertTrue(payload["performs_writes"])


class TestEffectCheckCertificationUnderreported(unittest.TestCase):
    def test_lcm_actions_with_performs_writes_false(self):
        payload = build_effect_check_payload(
            {
                "success": True,
                "lcm_undoable_action_count": 97,
                "write_certification": {"performs_writes": False},
            },
            write_enabled=True,
            is_mutating_script=False,
        )
        self.assertIsNotNone(payload)
        self.assertEqual(payload["verdict"], "certification_underreported")
        self.assertEqual(payload["lcm_undoable_action_count"], 97)

    def test_aligned_certification_omits(self):
        self.assertIsNone(
            build_effect_check_payload(
                {
                    "success": True,
                    "lcm_undoable_action_count": 3,
                    "write_certification": {"performs_writes": True},
                },
                write_enabled=True,
                is_mutating_script=True,
            )
        )


if __name__ == "__main__":
    unittest.main()
