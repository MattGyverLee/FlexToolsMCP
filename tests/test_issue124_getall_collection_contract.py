#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #124: GetAll methods carry a structured collection_contract in the index."""

import json
import unittest
from pathlib import Path

from flextoolsmcp.build_getall_contract import (
    KEY_COLLECTION_CONTRACT,
    annotate_getall_contracts,
    infer_getall_collection_contract,
)
from flextoolsmcp.server import APIIndex
from flextoolsmcp.server.handlers.api import paginate_entity
from flextoolsmcp.server.kernel import get_index_dir
from flextoolsmcp.server.response_keys import KEY_COLLECTION_CONTRACT as RK_CONTRACT


class TestInferGetallCollectionContract(unittest.TestCase):
    def test_enumerable_wrapper(self):
        c = infer_getall_collection_contract("EnumerableWrapper[ILexEntry]")
        self.assertEqual(c["shape"], "enumerable_wrapper")
        self.assertEqual(c["element_type"], "ILexEntry")
        self.assertTrue(c["behavioral"])
        self.assertTrue(c["yields_lcm_objects"])

    def test_allomorph_collection_is_wrapper_not_lcm(self):
        c = infer_getall_collection_contract("AllomorphCollection[Allomorph]")
        self.assertEqual(c["shape"], "allomorph_collection")
        self.assertFalse(c["yields_lcm_objects"])
        self.assertIn("note", c)


class TestShippedFlexiconIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api_index = APIIndex.load(get_index_dir())
        cls.flexicon = cls.api_index.flexicon.get("entities") or {}

    def test_every_getall_has_nonempty_return_type_and_contract(self):
        missing_rt = []
        missing_contract = []
        for entity_name, entity in self.flexicon.items():
            for method in entity.get("methods") or []:
                if method.get("name") != "GetAll":
                    continue
                rt = (method.get("return_type") or "").strip()
                if not rt:
                    missing_rt.append(f"{entity_name}.GetAll")
                    continue
                if not method.get(KEY_COLLECTION_CONTRACT):
                    missing_contract.append(f"{entity_name}.GetAll ({rt})")
        self.assertFalse(missing_rt, f"empty return_type: {missing_rt[:5]}")
        self.assertFalse(
            missing_contract,
            f"missing collection_contract: {missing_contract[:5]}",
        )

    def test_known_wrapper_getall_surfaces_note_in_get_object_api(self):
        entity = self.flexicon.get("AllomorphOperations")
        if not entity:
            self.skipTest("AllomorphOperations not in shipped index")
        page = paginate_entity(
            entity,
            summary_only=True,
            method_filter="GetAll",
            limit=5,
            offset=0,
            object_type="AllomorphOperations",
        )
        getall_rows = [m for m in page["methods"] if m.get("name") == "GetAll"]
        self.assertEqual(len(getall_rows), 1)
        contract = getall_rows[0].get(RK_CONTRACT)
        self.assertIsNotNone(contract)
        self.assertFalse(contract["yields_lcm_objects"])


class TestAnnotateGetallContracts(unittest.TestCase):
    def test_annotate_idempotent_on_minimal_fixture(self):
        data = {
            "entities": {
                "LexEntryOperations": {
                    "methods": [
                        {
                            "name": "GetAll",
                            "return_type": "EnumerableWrapper[ILexEntry]",
                        }
                    ]
                }
            }
        }
        stats = annotate_getall_contracts(data)
        self.assertEqual(stats["annotated"], 1)
        method = data["entities"]["LexEntryOperations"]["methods"][0]
        self.assertIn(KEY_COLLECTION_CONTRACT, method)


if __name__ == "__main__":
    unittest.main()
