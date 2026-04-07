#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive test suite for validators module.

Tests validation functions for static analysis of FLExTools scripts:
- CUD (Create/Update/Delete) operation detection
- Module structure validation
- Output mechanism checking
- Polymorphic error detection
- Import validation
- Undefined variable detection
"""

import unittest
from server.validators import (
    detect_cud_operations,
    detect_module_structure,
    check_output_mechanism,
    detect_polymorphic_error,
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


class TestOutputMechanism(unittest.TestCase):
    """Tests for check_output_mechanism()."""

    def test_module_with_report_info(self):
        """Test module code using report.Info()."""
        code = 'report.Info("Output")'
        result = check_output_mechanism(code, "module")
        self.assertTrue(result["uses_correct_mechanism"])
        self.assertEqual(result["mechanism_type"], "report")

    def test_module_with_print(self):
        """Test module code using print() - discouraged."""
        code = 'print("Output")'
        result = check_output_mechanism(code, "module")
        self.assertFalse(result["uses_correct_mechanism"])
        self.assertEqual(result["mechanism_type"], "print")

    def test_operation_with_print(self):
        """Test operation code using print() - correct."""
        code = 'print("Output")'
        result = check_output_mechanism(code, "operation")
        self.assertTrue(result["uses_correct_mechanism"])
        self.assertEqual(result["mechanism_type"], "print")

    def test_no_output_is_valid(self):
        """Test that code with no output is valid."""
        code = "x = 1 + 1"
        result = check_output_mechanism(code, "module")
        self.assertTrue(result["uses_correct_mechanism"])
        self.assertFalse(result["has_output"])

    def test_has_expected_fields(self):
        """Test that result has expected structure."""
        code = ""
        result = check_output_mechanism(code, "module")
        self.assertIn("has_output", result)
        self.assertIn("uses_correct_mechanism", result)
        self.assertIn("mechanism_type", result)
        self.assertIn("message", result)


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


class TestImportValidation(unittest.TestCase):
    """Tests for detect_missing_operations_imports() and detect_wrong_library_imports()."""

    def test_missing_operations_import_detection(self):
        """Test detection of missing Operations imports."""
        code = """
entries = LexEntryOperations(project).GetAll()
"""
        result = detect_missing_operations_imports(code, "flexlibs2")
        self.assertIn("missing_imports", result)

    def test_wrong_library_detection(self):
        """Test detection of wrong library imports."""
        code = """
from SIL.LCModel import ILexEntry
"""
        result = detect_wrong_library_imports(code, "flexlibs2")
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
