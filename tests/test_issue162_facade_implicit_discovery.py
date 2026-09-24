#!/usr/bin/env python3
"""Issue #162: facade accessors like project.Variants must satisfy discovery.

VariantOperations is only reachable via ``project.Variants`` (not
``VariantsOperations``). Using the facade in code is deliberate API use and
should satisfy the undiscovered_entity gate, parallel to issue #31's
import-based implicit discovery.
"""

import ast
import unittest

from flextoolsmcp.server import APIIndex
from flextoolsmcp.server.kernel import get_index_dir
from flextoolsmcp.server.validators import detect_undiscovered_entities


class _EmptySession:
    validated_apis = set()
    discovered_apis = set()


class TestIssue162FacadeImplicitDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api_index = APIIndex.load(get_index_dir())

    def _detect(self, code: str):
        return detect_undiscovered_entities(
            ast.parse(code), _EmptySession(), self.api_index
        )

    def test_project_variants_satisfies_variant_operations(self):
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    project.Variants.Create(entry, 'form', vtype)\n"
        )
        result = self._detect(code)
        self.assertFalse(
            result["has_undiscovered"],
            msg=f"expected facade use to satisfy discovery; got {result}",
        )

    def test_project_msa_satisfies_msa_operations(self):
        """MSAOperations is another non-{Name}Operations facade mapping."""
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    project.MSA.CreateStem(sense, pos)\n"
        )
        result = self._detect(code)
        self.assertFalse(result["has_undiscovered"])

    def test_direct_operations_class_still_requires_discovery(self):
        """Constructor-style use without import or facade still gated."""
        code = "VariantOperations(project).Create(entry, 'form', vtype)\n"
        result = self._detect(code)
        self.assertTrue(result["has_undiscovered"])
        self.assertIn("VariantOperations", result["undiscovered"])

    def test_import_still_satisfies_direct_constructor(self):
        code = (
            "from flexicon import VariantOperations\n"
            "VariantOperations(project).Create(entry, 'form', vtype)\n"
        )
        result = self._detect(code)
        self.assertFalse(result["has_undiscovered"])


if __name__ == "__main__":
    unittest.main()
