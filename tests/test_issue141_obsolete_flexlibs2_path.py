#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #141: dead FLEXLIBS2_PATH in .env must warn, not silently no-op."""

import os
import unittest
from pathlib import Path

from flextoolsmcp.env_config import (
    collect_obsolete_env_warnings,
    load_project_env,
)


class TestIssue141ObsoleteFlexlibs2Path(unittest.TestCase):
    def test_flexlibs2_path_in_env_is_not_applied_from_dotenv(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_name:
            tmp = Path(tmp_name)
            env = tmp / ".env"
            env.write_text(
                "FLEXLIBS2_PATH=/nonexistent/flexlibs2\nFLEXICON_PATH=/ok/flexicon\n",
                encoding="utf-8",
            )
            os.environ.pop("FLEXLIBS2_PATH", None)
            os.environ.pop("FLEXICON_PATH", None)
            for key in list(os.environ):
                if key.startswith("_FLEXTOOLSMCP_OBSOLETE_"):
                    os.environ.pop(key)

            load_project_env(tmp)

            self.assertNotIn("FLEXLIBS2_PATH", os.environ)
            self.assertEqual(os.environ.get("FLEXICON_PATH"), "/ok/flexicon")
            warnings = collect_obsolete_env_warnings()
            self.assertTrue(any("FLEXLIBS2_PATH" in w for w in warnings), warnings)

    def test_flexlibs2_path_already_in_process_env_warns(self):
        os.environ["FLEXLIBS2_PATH"] = "/still/here"
        try:
            warnings = collect_obsolete_env_warnings()
            self.assertTrue(any("obsolete" in w.lower() for w in warnings), warnings)
        finally:
            os.environ.pop("FLEXLIBS2_PATH", None)

if __name__ == "__main__":
    unittest.main()
