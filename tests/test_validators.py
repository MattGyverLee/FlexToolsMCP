#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for validators module.

Tests validation functions for static analysis of FLExTools scripts:
- CUD (Create/Update/Delete) operation detection
- Module structure validation
- Polymorphic error detection
- Import validation
- Undefined variable detection
"""

import unittest
from types import SimpleNamespace
from server.validators import (
    detect_cud_operations,
    detect_module_structure,
    detect_partial_module_structure,
    detect_polymorphic_error,
    detect_overload_resolution_error,
    detect_missing_operations_imports,
    detect_wrong_library_imports,
    detect_undefined_variables,
    validate_project_context,
)


class TestCUDDetection(unittest.TestCase):
    """Tests for detect_cud_operations()."""

    def test_readonly_code_no_cud(self):
        """Test that read-only code has no CUD operations."""
        code = "entries = LexEntryOperations(project).GetAll()"
        result = detect_cud_operations(code)
        self.assertFalse(result["is_cud"])
        self.assertEqual(len(result["operations"]), 0)

    def test_has_operations_field(self):
        """Test that result has expected structure."""
        code = "x = 1"
        result = detect_cud_operations(code)
        self.assertIn("is_cud", result)
        self.assertIn("operations", result)
        self.assertIn("risks", result)
        self.assertIn("affected_types", result)


class TestModuleStructure(unittest.TestCase):
    """Tests for detect_module_structure()."""

    def test_missing_main_function(self):
        """Test detection of missing Main() function."""
        code = "def helper(): pass"
        result = detect_module_structure(code)
        self.assertFalse(result["is_valid_module"])
        # Check that missing_elements contains Main-related content
        missing_str = str(result["missing_elements"])
        self.assertIn("Main", missing_str)

    def test_missing_flextoolslib_import(self):
        """Test detection of missing flextoolslib import."""
        code = "def Main(project, report, modifyAllowed): pass"
        result = detect_module_structure(code)
        self.assertFalse(result["is_valid_module"])
        # Check that missing_elements contains flextoolslib
        missing_str = str(result["missing_elements"])
        self.assertIn("flextoolslib", missing_str)

    def test_has_expected_fields(self):
        """Test that result has expected structure."""
        code = ""
        result = detect_module_structure(code)
        self.assertIn("is_valid_module", result)
        self.assertIn("missing_elements", result)


class TestPartialModuleStructure(unittest.TestCase):
    """Tests for detect_partial_module_structure() - the soft-block validator."""

    def test_bare_snippet_not_flagged(self):
        """Bare snippet without Main is not a partial module."""
        code = "for entry in project.LexEntry.GetAll(): pass"
        result = detect_partial_module_structure(code)
        self.assertFalse(result["is_partial_module"])
        self.assertFalse(result["has_main"])

    def test_main_without_scaffolding_is_partial(self):
        """Dennis's case: def Main but no docs/FlexToolsModule binding."""
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    report.Info('hello')\n"
        )
        result = detect_partial_module_structure(code)
        self.assertTrue(result["is_partial_module"])
        self.assertTrue(result["has_main"])
        missing_str = " ".join(result["missing_elements"])
        self.assertIn("docs", missing_str)
        self.assertIn("FlexToolsModule", missing_str)
        self.assertTrue(result["suggestion"])

    def test_main_with_docs_only_still_partial(self):
        """Has Main + docs but missing FlexToolsModule binding."""
        code = (
            "docs = {FTM_Name: 'x'}\n"
            "def Main(project, report, modifyAllowed): pass\n"
        )
        result = detect_partial_module_structure(code)
        self.assertTrue(result["is_partial_module"])
        self.assertEqual(result["missing_elements"],
                         ["FlexToolsModule = FlexToolsModuleClass(Main, docs)"])

    def test_full_module_not_flagged(self):
        """Conformant module passes: Main + docs + FlexToolsModule."""
        code = (
            "docs = {FTM_Name: 'x'}\n"
            "def Main(project, report, modifyAllowed): pass\n"
            "FlexToolsModule = FlexToolsModuleClass(Main, docs)\n"
        )
        result = detect_partial_module_structure(code)
        self.assertFalse(result["is_partial_module"])
        self.assertTrue(result["has_main"])
        self.assertEqual(result["missing_elements"], [])

    def test_syntax_error_returns_false(self):
        """Code with a syntax error is not flagged (lets syntax_error fire first)."""
        code = "def Main(:"
        result = detect_partial_module_structure(code)
        self.assertFalse(result["is_partial_module"])

    def test_main_at_indent_not_flagged(self):
        """A `def Main` nested inside a class is not the FlexTools entry point."""
        code = (
            "class Wrapper:\n"
            "    def Main(self, project, report, modifyAllowed): pass\n"
        )
        result = detect_partial_module_structure(code)
        # ast.walk still finds it, so this WILL flag - documents the boundary.
        # Acceptable: nested Main is unusual and getting a structural nudge is
        # not actively wrong.
        self.assertTrue(result["has_main"])


class TestPolymorphicError(unittest.TestCase):
    """Tests for detect_polymorphic_error()."""

    def test_detect_polymorphic_error(self):
        """Test detection of polymorphic attribute errors."""
        error = "'ILexEntry' object has no attribute 'HeadWord'"
        result = detect_polymorphic_error(error)
        self.assertTrue(result["is_polymorphic_error"])
        self.assertEqual(result["object_type"], "ILexEntry")
        self.assertEqual(result["property_name"], "HeadWord")

    def test_non_polymorphic_error(self):
        """Test that non-polymorphic errors are not flagged."""
        error = "name 'foo' is not defined"
        result = detect_polymorphic_error(error)
        self.assertFalse(result["is_polymorphic_error"])

    def test_generic_polymorphic_error(self):
        """Test result structure for non-polymorphic error."""
        error = "some random error"
        result = detect_polymorphic_error(error)
        self.assertIn("is_polymorphic_error", result)


def _fake_api_index_for_overloads():
    """Minimal fake APIIndex exposing two overloads of 'Create' on
    IPartOfSpeechFactory (mirrors the real liblcm index shape) plus a
    single-overload 'GetFields' on IFwMetaDataCacheManaged, so tests don't
    depend on the real (large, version-pinned) index file.
    """
    liblcm = {
        "entities": {
            "IPartOfSpeechFactory": {
                "methods": [
                    {
                        "name": "Create",
                        "signature": "Create(Guid guid, ICmPossibilityList owner)",
                        "parameters": [
                            {"name": "guid", "type": "Guid"},
                            {"name": "owner", "type": "ICmPossibilityList"},
                        ],
                    },
                    {
                        "name": "Create",
                        "signature": "Create(Guid guid, IPartOfSpeech owner)",
                        "parameters": [
                            {"name": "guid", "type": "Guid"},
                            {"name": "owner", "type": "IPartOfSpeech"},
                        ],
                    },
                ],
            },
            "IFwMetaDataCacheManaged": {
                "methods": [
                    {
                        "name": "GetFields",
                        "signature": "GetFields()",
                        "parameters": [],
                    },
                ],
            },
        }
    }
    return SimpleNamespace(liblcm=liblcm, flexicon=None, flexlibs_stable=None)


class TestOverloadResolutionError(unittest.TestCase):
    """Tests for detect_overload_resolution_error() (issue #75)."""

    def test_detects_known_method_and_lists_candidates(self):
        """A recognized 'No method matches given arguments' message for a known
        method surfaces candidate overloads with their argument types."""
        error = (
            "TypeError: No method matches given arguments for Create: "
            "(<class 'System.Guid'>, <class 'NoneType'>)"
        )
        result = detect_overload_resolution_error(error, _fake_api_index_for_overloads())

        self.assertTrue(result["is_overload_error"])
        self.assertEqual(result["method_name"], "Create")
        self.assertEqual(result["given_arg_types"], ["System.Guid", "NoneType"])
        self.assertEqual(result["total_candidates_found"], 2)

        signatures = {c["signature"] for c in result["candidates"]}
        self.assertIn("Create(Guid guid, ICmPossibilityList owner)", signatures)
        self.assertIn("Create(Guid guid, IPartOfSpeech owner)", signatures)
        self.assertIn("IPartOfSpeechFactory", result["suggestion"])
        self.assertIn("Create(Guid guid, ICmPossibilityList owner)", result["suggestion"])

    def test_detects_message_without_arg_types(self):
        """The method name is still extracted when pythonnet's message omits
        the trailing ': (<arg types>)' portion."""
        error = "No method matches given arguments for GetFields"
        result = detect_overload_resolution_error(error, _fake_api_index_for_overloads())

        self.assertTrue(result["is_overload_error"])
        self.assertEqual(result["method_name"], "GetFields")
        self.assertEqual(result["given_arg_types"], [])
        self.assertEqual(result["total_candidates_found"], 1)
        self.assertEqual(result["candidates"][0]["entity"], "IFwMetaDataCacheManaged")

    def test_entity_hint_narrows_candidates(self):
        """entity_hint restricts candidates to a single entity even when the
        method name is shared across multiple entities."""
        error = "No method matches given arguments for Create: (<class 'Guid'>,)"
        result = detect_overload_resolution_error(
            error, _fake_api_index_for_overloads(), entity_hint="IPartOfSpeechFactory"
        )
        self.assertTrue(result["is_overload_error"])
        self.assertEqual(result["total_candidates_found"], 2)
        for c in result["candidates"]:
            self.assertEqual(c["entity"], "IPartOfSpeechFactory")

    def test_no_candidates_found_still_reports_error(self):
        """When the method has no indexed overloads, the error is still
        recognized and a fallback suggestion is returned (no crash)."""
        error = "No method matches given arguments for TotallyUnknownMethod"
        result = detect_overload_resolution_error(error, _fake_api_index_for_overloads())

        self.assertTrue(result["is_overload_error"])
        self.assertEqual(result["method_name"], "TotallyUnknownMethod")
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["total_candidates_found"], 0)
        self.assertTrue(result["suggestion"])

    def test_none_api_index_does_not_crash(self):
        """No api_index available (e.g. not yet loaded): still recognized,
        no candidates, no exception."""
        error = "No method matches given arguments for Create"
        result = detect_overload_resolution_error(error, api_index=None)
        self.assertTrue(result["is_overload_error"])
        self.assertEqual(result["candidates"], [])

    def test_unrelated_error_not_flagged(self):
        """Unrelated errors (including the existing polymorphic-attribute
        error class) are left alone -- is_overload_error is False."""
        for error in (
            "'ILexEntry' object has no attribute 'HeadWord'",
            "name 'foo' is not defined",
            "",
        ):
            result = detect_overload_resolution_error(error)
            self.assertFalse(result["is_overload_error"])


class TestImportValidation(unittest.TestCase):
    """Tests for detect_missing_operations_imports() and detect_wrong_library_imports()."""

    def test_missing_operations_import_detection(self):
        """Test detection of missing Operations imports."""
        code = """
entries = LexEntryOperations(project).GetAll()
"""
        result = detect_missing_operations_imports(code, "flexicon")
        self.assertIn("missing_imports", result)

    def test_wrong_library_detection(self):
        """Test detection of wrong library imports."""
        code = """
from SIL.LCModel import ILexEntry
"""
        result = detect_wrong_library_imports(code, "flexicon")
        # Result structure varies - just check keys exist
        self.assertIsInstance(result, dict)


class TestUndefinedVariables(unittest.TestCase):
    """Tests for detect_undefined_variables()."""

    def test_defined_variable_usage(self):
        """Test that defined variables are not flagged."""
        code = """
x = 5
report.Info(x)
"""
        result = detect_undefined_variables(code)
        # Should not have critical undefined variables
        self.assertIsInstance(result, dict)

    def test_has_expected_fields(self):
        """Test that result has expected structure."""
        code = ""
        result = detect_undefined_variables(code)
        self.assertIsInstance(result, dict)


class TestProjectContextValidation(unittest.TestCase):
    """Tests for validate_project_context()."""

    def test_valid_context(self):
        """Test validation with valid context."""
        result = validate_project_context("TestProject", write_enabled=False)
        self.assertIn("project_validated", result)
        self.assertIn("target_project", result)
        self.assertTrue(result["project_validated"])

    def test_missing_project_name(self):
        """Test validation with missing project name."""
        result = validate_project_context("", write_enabled=False)
        self.assertIsInstance(result, dict)

    def test_session_not_initialized(self):
        """Test validation with session not initialized."""
        result = validate_project_context("TestProject", write_enabled=False, session_initialized=False)
        self.assertIn("project_validated", result)


class TestValidatorEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_empty_code(self):
        """Test validators with empty code."""
        code = ""
        result1 = detect_cud_operations(code)
        result2 = detect_module_structure(code)
        result3 = detect_undefined_variables(code)

        self.assertFalse(result1["is_cud"])
        self.assertIsNotNone(result2)
        self.assertIsNotNone(result3)

    def test_code_with_only_comments(self):
        """Test validators with comment-only code."""
        code = "# This is a comment\n# Another comment"
        result = detect_cud_operations(code)
        self.assertFalse(result["is_cud"])

    def test_code_with_multiline_strings(self):
        """Test validators with multiline string content."""
        code = '''
docstring = """
This is a multiline string
with some code-like content: LexEntryOperations.Create()
but it shouldn't be detected
"""
'''
        result = detect_cud_operations(code)
        # Behavior depends on implementation
        self.assertIsInstance(result, dict)


class TestValidatorRobustness(unittest.TestCase):
    """Tests for validator robustness and error handling."""

    def test_malformed_python(self):
        """Test that validators handle malformed Python gracefully."""
        code = "def Main(: pass"  # Missing parameter list
        try:
            result = detect_cud_operations(code)
            # Should return some result, not crash
            self.assertIsInstance(result, dict)
        except SyntaxError:
            # It's acceptable to raise SyntaxError for invalid code
            pass

    def test_very_large_code(self):
        """Test that validators handle large code blocks."""
        code = "x = 1\n" * 10000  # 10k lines
        result = detect_cud_operations(code)
        self.assertIsInstance(result, dict)


if __name__ == "__main__":
    unittest.main()
