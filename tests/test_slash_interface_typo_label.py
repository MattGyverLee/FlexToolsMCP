"""Swahili audit P2-2: interface typo labels must not slash-join interfaces."""

import ast
import unittest

from flextoolsmcp.server.validators import detect_interface_attribute_typos


class _TwoInterfaceIndex:
    liblcm = {
        "entities": {
            "ILexEntry": {
                "properties": [{"name": "LexemeFormOA"}],
                "methods": [],
                "interfaces": [],
            },
            "ILexSense": {
                "properties": [{"name": "Gloss"}],
                "methods": [],
                "interfaces": [],
            },
        }
    }
    flexicon = {"entities": {}}
    flexlibs_stable = {"entities": {}}


class TestSlashInterfaceTypoLabel(unittest.TestCase):
    def test_multi_cast_union_uses_real_interface_names(self):
        """Mutually exclusive casts -> union check; labels stay index-real."""
        code = (
            "from SIL.LCModel import ILexEntry, ILexSense\n"
            "def f(p, flag):\n"
            "    if flag:\n"
            "        obj = ILexEntry(p)\n"
            "    else:\n"
            "        obj = ILexSense(p)\n"
            "    return obj.Glosss\n"
        )
        result = detect_interface_attribute_typos(ast.parse(code), _TwoInterfaceIndex())
        self.assertTrue(result["has_typos"], result)
        issue = result["issues"][0]
        self.assertEqual(issue["object_type"], "ILexEntry")
        self.assertEqual(issue["missing_on"], ["ILexEntry", "ILexSense"])
        self.assertNotIn("/", issue["suggestion"])
        self.assertIn("'ILexEntry' or 'ILexSense'", issue["suggestion"])
        self.assertEqual(issue["expr"], "obj.Glosss")

    def test_single_interface_unchanged_shape(self):
        code = (
            "from SIL.LCModel import ILexSense\n"
            "def f(p):\n"
            "    s = ILexSense(p)\n"
            "    return s.Glosss\n"
        )
        result = detect_interface_attribute_typos(ast.parse(code), _TwoInterfaceIndex())
        self.assertTrue(result["has_typos"], result)
        issue = result["issues"][0]
        self.assertEqual(issue["object_type"], "ILexSense")
        self.assertEqual(issue["missing_on"], ["ILexSense"])
        self.assertIn("'ILexSense'", issue["suggestion"])


if __name__ == "__main__":
    unittest.main()
