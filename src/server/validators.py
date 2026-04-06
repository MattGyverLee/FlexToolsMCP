#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validation and detection functions for FlexToolsMCP.

Provides checks for code structure, safety, and correctness:
- Detect CUD operations (Create/Update/Delete)
- Detect module structure validity
- Check output mechanisms
- Detect errors and undefined variables
- Validate project context
"""

import re
import ast
import textwrap
from typing import Dict, List, Set, Optional, Any


def detect_cud_operations(code: str) -> dict:
    """Detect Create, Update, Delete operations in code that modify the FLEx database.

    Only detects actual FlexLibs2/LCM database modifications, not:
    - Local Python list operations (results.append(), etc.)
    - Variable assignments to local variables
    - Comments containing keywords

    Returns dict with:
      - is_cud: bool - whether CUD operations detected
      - operations: list - detected operation types
      - risks: list - specific risks identified
      - affected_types: list - data types that may be affected
    """
    operations = []
    risks = []
    affected = set()

    # Remove comments to avoid false positives
    code_no_comments = re.sub(r'#.*$', '', code, flags=re.MULTILINE)

    # === CREATE operations (actual database writes) ===
    create_patterns = [
        # FlexLibs2/LCM .Create() methods (factory or operations)
        (r'\.Create\s*\(', 'Create()'),
        # .Add() on LCM collections (OC, OS, RC suffixes indicate LCM collections)
        (r'\.(AnalysesOC|SensesOS|MorphBundlesOS|MeaningsOC|EntriesOC|'
         r'SubentriesOS|AllomorphsOS|ExamplesOS|ReversalEntriesOC|'
         r'EvaluationsRC|PossibilitiesOS|SubPossibilitiesOS|'
         r'PronunciationsOS|LexEntryRefsOS|ComponentLexemesRS)\s*\.\s*Add\s*\(', 'collection.Add()'),
        # Generic .Add() with LCM object context (be more conservative)
        (r'(entry|sense|wordform|analysis|bundle|gloss)\w*\.\w+\.\s*Add\s*\(', 'Add()'),
        # .Insert() on LCM sequences
        (r'\.(SensesOS|MorphBundlesOS|SubentriesOS|AllomorphsOS|ExamplesOS|'
         r'PossibilitiesOS|SubPossibilitiesOS|PronunciationsOS)\s*\.\s*Insert\s*\(', 'Insert()'),
        # project.*.Create (FlexLibs2 operations Create methods)
        (r'project\.\w+\.Create\s*\(', 'project.*.Create()'),
    ]

    for pattern, label in create_patterns:
        if re.search(pattern, code_no_comments, re.IGNORECASE):
            operations.append(f"CREATE ({label})")
            risks.append("New data will be added to the database")
            break

    # === UPDATE operations (actual database writes) ===
    update_patterns = [
        # .set_String() - multistring value setting
        (r'\.set_String\s*\(', 'set_String()'),
        # .SetOccurrences, .SetForm, etc.
        (r'\.Set(Occurrences|Form|Gloss|Definition|Category|Analysis)\s*\(', 'Set*()'),
        # .CopyAlternatives() - copying multistring values
        (r'\.CopyAlternatives\s*\(', 'CopyAlternatives()'),
        # Direct property assignment to LCM object properties
        # Matches: entry.Foo = ..., sense.BarRA = ..., etc.
        (r'(entry|sense|wordform|analysis|bundle|morph|gloss|allomorph|pos)\w*\s*\.\s*'
         r'(LexemeFormOA|MorphoSyntaxAnalysisRA|SenseRA|MsaRA|MorphRA|CategoryRA|'
         r'InflectionClassRA|EntryRefsOS|ComponentLexemesRS|PrimaryLexemesRS|'
         r'MorphTypeRA|Gloss|Definition|Form|LiteralMeaning|SummaryDefinition|'
         r'Bibliography|Etymology|Comment|Note)\s*=', 'property assignment'),
        # project.*.Set* or project.*.Update* methods
        (r'project\.\w+\.(Set|Update|Modify|Change|Edit|Replace)\w*\s*\(', 'project.*.Set/Update()'),
        # Approve/Reject analysis (changes approval status)
        (r'\.(Approve|Reject|SetApprovalStatus)\s*\(', 'approval change'),
    ]

    for pattern, label in update_patterns:
        if re.search(pattern, code_no_comments, re.IGNORECASE):
            operations.append(f"UPDATE ({label})")
            risks.append("Existing data will be modified")
            break

    # === DELETE operations (actual database writes) ===
    delete_patterns = [
        # .Delete() methods
        (r'\.Delete\s*\(', 'Delete()'),
        # .Remove() on LCM collections
        (r'\.(AnalysesOC|SensesOS|MorphBundlesOS|MeaningsOC|EntriesOC|'
         r'SubentriesOS|AllomorphsOS|ExamplesOS|ReversalEntriesOC|'
         r'EvaluationsRC|PossibilitiesOS|SubPossibilitiesOS)\s*\.\s*Remove\s*\(', 'collection.Remove()'),
        # .Clear() on LCM collections
        (r'\.(AnalysesOC|SensesOS|MorphBundlesOS|MeaningsOC|EntriesOC)\s*\.\s*Clear\s*\(', 'collection.Clear()'),
        # project.*.Delete methods
        (r'project\.\w+\.Delete\s*\(', 'project.*.Delete()'),
    ]

    for pattern, label in delete_patterns:
        if re.search(pattern, code_no_comments, re.IGNORECASE):
            operations.append(f"DELETE ({label})")
            risks.append("Data will be permanently removed")
            break

    # Identify affected data types (only if CUD operations detected)
    if operations:
        type_patterns = {
            r'\bentry\b': 'Lexicon entries',
            r'\bsense\b': 'Senses',
            r'\bexample\b': 'Example sentences',
            r'\bgloss\b': 'Glosses',
            r'\bdefinition\b': 'Definitions',
            r'\bpos\b': 'Parts of speech',
            r'\ballomorph\b': 'Allomorphs',
            r'\breversal\b': 'Reversal entries',
            r'\btext\b': 'Texts',
            r'\bwordform\b': 'Wordforms',
            r'\banalysis\b': 'Analyses',
            r'\bmorph\s*bundle\b': 'Morph bundles',
        }

        for pattern, label in type_patterns.items():
            if re.search(pattern, code_no_comments, re.IGNORECASE):
                affected.add(label)

    return {
        "is_cud": len(operations) > 0,
        "operations": operations,
        "risks": risks,
        "affected_types": list(affected) if affected else ["Unknown - review code carefully"]
    }


def detect_module_structure(code: str) -> dict:
    """Check if code is in valid FlexTools module format.

    A valid FlexTools module must have:
    - from flextoolslib import statement
    - def Main(project, report, modifyAllowed): function
    - FlexToolsModuleClass(...) instantiation
    - docs = {...} dictionary with FTM_* keys

    Returns dict with:
      - is_valid_module: bool - whether all required elements are present
      - missing_elements: list - what's missing (for error messaging)
    """
    missing = []

    # Check for flextoolslib import
    if "from flextoolslib import" not in code:
        missing.append("from flextoolslib import *")

    # Check for Main function with correct signature
    if not re.search(r'^\s*def Main\s*\(', code, re.MULTILINE):
        missing.append("def Main(project, report, modifyAllowed):")

    # Check for FlexToolsModuleClass instantiation
    if "FlexToolsModuleClass(" not in code:
        missing.append("FlexToolsModule = FlexToolsModuleClass(Main, docs)")

    # Check for docs dictionary
    if not re.search(r'^\s*docs\s*=\s*\{', code, re.MULTILINE):
        missing.append("docs = {FTM_Name: ..., FTM_Version: ..., ...}")

    return {
        "is_valid_module": len(missing) == 0,
        "missing_elements": missing
    }


def check_output_mechanism(code: str, tool_type: str) -> dict:
    """Check that code uses correct output mechanism IF it produces output.

    For run_operation (raw operations code): IF outputting, use print()
    For run_module (FlexTools modules): IF outputting, use report.Info() (or report.*)

    Code with NO output is always valid.

    Returns dict with:
      - has_output: bool - whether code produces output
      - uses_correct_mechanism: bool - uses tool-appropriate output (if outputting)
      - mechanism_type: str - detected mechanism (print, report, none)
      - message: str - guidance if incorrect
    """
    code_no_comments = re.sub(r'#.*$', '', code, flags=re.MULTILINE)

    has_print = 'print(' in code_no_comments
    has_report_info = re.search(r'report\.(Info|Warning|Error|Blank|FileURL)\s*\(', code_no_comments)
    has_report_direct = re.search(r'report\s*\(', code_no_comments) and not re.search(r'report\.(Info|Warning|Error|Blank|FileURL)\s*\(', code_no_comments)

    if tool_type == "operation":
        # run_operation: if outputting, use print(); if not outputting, that's fine
        if has_print:
            return {
                "has_output": True,
                "uses_correct_mechanism": True,
                "mechanism_type": "print",
                "message": None
            }
        elif has_report_direct:
            return {
                "has_output": True,
                "uses_correct_mechanism": False,
                "mechanism_type": "report",
                "message": "Operations code calls report() directly, but report is not available. Only modules have access to report. Use print() instead for output."
            }
        elif has_report_info:
            return {
                "has_output": True,
                "uses_correct_mechanism": False,
                "mechanism_type": "report",
                "message": "Operations code uses report.Info(), but only modules have access to report. Use print() instead for output."
            }
        else:
            # No output: this is valid
            return {
                "has_output": False,
                "uses_correct_mechanism": True,
                "mechanism_type": "none",
                "message": None
            }

    elif tool_type == "module":
        # run_module: if outputting, use report.Info(); if not outputting, that's fine
        if has_report_info:
            return {
                "has_output": True,
                "uses_correct_mechanism": True,
                "mechanism_type": "report",
                "message": None
            }
        elif has_report_direct:
            return {
                "has_output": True,
                "uses_correct_mechanism": False,
                "mechanism_type": "report",
                "message": "Module code calls report() directly, but the report object must be accessed with a method like report.Info(message). Use report.Info(), report.Warning(), or report.Error() instead."
            }
        elif has_print:
            return {
                "has_output": True,
                "uses_correct_mechanism": False,
                "mechanism_type": "print",
                "message": "Module code uses print(), but output should use report.Info() to be captured in the FlexTools result format."
            }
        else:
            # No output: this is valid
            return {
                "has_output": False,
                "uses_correct_mechanism": True,
                "mechanism_type": "none",
                "message": None
            }

    return {"has_output": False, "uses_correct_mechanism": True, "mechanism_type": "unknown"}


def detect_polymorphic_error(error_msg: str) -> dict:
    """Detect polymorphic attribute errors and suggest resolve_property.

    Identifies errors like "'IPhSegmentRule' object has no attribute 'RightHandSidesOS'"
    and suggests using resolve_property to find the correct property and casting.

    Returns dict with:
      - is_polymorphic_error: bool - whether this looks like a polymorphic issue
      - object_type: str - the object type from the error (e.g., 'IPhSegmentRule')
      - property_name: str - the missing property (e.g., 'RightHandSidesOS')
      - suggestion: str - suggested resolve_property call
    """
    # Match pattern: 'ObjectType' object has no attribute 'PropertyName'
    pattern = r"'(\w+)'\s+object\s+has\s+no\s+attribute\s+'(\w+)'"
    match = re.search(pattern, error_msg)

    if match:
        object_type, property_name = match.groups()
        return {
            "is_polymorphic_error": True,
            "object_type": object_type,
            "property_name": property_name,
            "suggestion": f"Call resolve_property(property_name='{property_name}', context_entity='{object_type}') to find the correct property and required casting."
        }

    return {"is_polymorphic_error": False}


def detect_missing_operations_imports(code: str, api_mode: str) -> dict:
    """Detect Operations classes used without imports and suggest what to add.

    Args:
        code: User's module/operation code
        api_mode: Selected API mode ('flexlibs_stable', 'flexlibs2', 'liblcm')

    Returns:
        dict with 'missing_imports', 'has_missing', and 'suggestion'
    """
    # Known Operations classes in flexlibs2
    KNOWN_OPERATIONS = {
        # Grammar
        "POSOperations", "PhonemeOperations", "NaturalClassOperations",
        "EnvironmentOperations", "MorphRuleOperations", "InflectionFeatureOperations",
        "GramCatOperations", "PhonologicalRuleOperations",
        # Lexicon
        "LexEntryOperations", "LexSenseOperations", "ExampleOperations",
        "LexReferenceOperations", "VariantOperations", "PronunciationOperations",
        "SemanticDomainOperations", "ReversalOperations", "EtymologyOperations",
        "AllomorphOperations",
        # TextsWords
        "TextOperations", "WordformOperations", "WfiAnalysisOperations",
        "ParagraphOperations", "SegmentOperations", "WfiGlossOperations",
        "WfiMorphBundleOperations", "MediaOperations", "FilterOperations",
        "DiscourseOperations",
        # Notebook
        "NoteOperations", "PersonOperations", "LocationOperations",
        "AnthropologyOperations", "DataNotebookOperations",
        # Lists
        "PublicationOperations", "AgentOperations", "ConfidenceOperations",
        "OverlayOperations", "TranslationTypeOperations", "PossibilityListOperations",
        # System
        "WritingSystemOperations", "ProjectSettingsOperations",
        "AnnotationDefOperations", "CheckOperations", "CustomFieldOperations",
    }

    result = {
        "missing_imports": [],
        "has_missing": False,
        "suggestion": ""
    }

    # Find all words that match Operations class names
    pattern = r'\b(' + '|'.join(KNOWN_OPERATIONS) + r')\b'
    matches = re.findall(pattern, code)

    if not matches:
        return result

    # Check which are imported
    import_pattern = r'from\s+\w+\s+import\s+([^#\n]+)'
    import_lines = re.findall(import_pattern, code)
    imported = set()
    for line in import_lines:
        # Parse comma-separated imports
        parts = [p.strip() for p in line.split(',')]
        imported.update(parts)

    # Find missing imports
    used = set(matches)
    missing = used - imported

    if missing:
        result["has_missing"] = True
        result["missing_imports"] = sorted(list(missing))

        library = "flexlibs2" if api_mode == "flexlibs2" else "flexlibs"
        import_stmt = f"from {library} import {', '.join(sorted(missing))}"

        result["suggestion"] = (
            f"Code uses {len(missing)} Operations class(es) without importing: {', '.join(sorted(missing))}. "
            f"Add this import at the top:\n\n    {import_stmt}\n"
        )

    return result


def detect_wrong_library_imports(code: str, api_mode: str) -> dict:
    """Gate #2: Detect if user code imports from the wrong library for the selected API mode.

    Args:
        code: User's module/operation code
        api_mode: Selected API mode ('flexlibs_stable', 'flexlibs2', 'liblcm')

    Returns:
        dict with 'has_wrong_imports', 'wrong_imports', and 'suggestion'
    """
    result = {
        "has_wrong_imports": False,
        "wrong_imports": [],
        "suggestion": ""
    }

    # Extract all import statements
    import_pattern = r'(?:from|import)\s+([\w.]+)'
    imports = re.findall(import_pattern, code)

    if api_mode == "flexlibs2":
        # In flexlibs2 mode, flag imports from stable flexlibs
        wrong_libs = [imp for imp in imports if imp.startswith('flexlibs') and not imp.startswith('flexlibs2')]
        if wrong_libs:
            result["has_wrong_imports"] = True
            result["wrong_imports"] = wrong_libs
            result["suggestion"] = (
                f"Code in flexlibs2 mode is importing from flexlibs (stable). "
                f"Detected: {', '.join(set(wrong_libs))}. "
                f"Use 'from flexlibs2 import ...' instead for API consistency."
            )

    elif api_mode == "flexlibs_stable":
        # In stable mode, warn about flexlibs2 imports that might not work
        wrong_libs = [imp for imp in imports if imp.startswith('flexlibs2')]
        if wrong_libs:
            result["has_wrong_imports"] = True
            result["wrong_imports"] = wrong_libs
            result["suggestion"] = (
                f"Code in flexlibs (stable) mode is importing from flexlibs2. "
                f"Detected: {', '.join(set(wrong_libs))}. "
                f"Use 'from flexlibs import ...' for API consistency."
            )

    return result


def detect_undefined_variables(code: str) -> dict:
    """Detect likely undefined variables in code using static analysis.

    Looks for variable usage patterns that suggest undefined names:
    - CapitalizedName(...) - likely undeclared class/function (e.g., API_MODE_IMPORTS, SomeOperations)
    - UPPERCASE_VAR - likely internal variable or constant
    - References to MCP internals

    Returns dict with:
      - has_undefined: bool - whether undefined variables detected
      - undefined_vars: list - variable names that appear undefined
      - suggestion: str - guidance for fixing
    """
    try:
        # Parse to AST to find actual undefined variables
        tree = ast.parse(code)
        defined_names = set()
        used_names = set()

        class NameCollector(ast.NodeVisitor):
            def visit_FunctionDef(self, node):
                defined_names.add(node.name)
                # Add function parameters
                for arg in node.args.args:
                    defined_names.add(arg.arg)
                self.generic_visit(node)

            def visit_ClassDef(self, node):
                defined_names.add(node.name)
                self.generic_visit(node)

            def visit_Assign(self, node):
                # Track assignments (x = value)
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined_names.add(target.id)
                self.generic_visit(node)

            def visit_ImportFrom(self, node):
                # Track imports
                for alias in node.names:
                    defined_names.add(alias.asname or alias.name)
                self.generic_visit(node)

            def visit_Import(self, node):
                # Track imports
                for alias in node.names:
                    defined_names.add(alias.asname or alias.name)
                self.generic_visit(node)

            def visit_Name(self, node):
                # Track name usage
                if isinstance(node.ctx, ast.Load):  # Reading, not writing
                    used_names.add(node.id)
                self.generic_visit(node)

        collector = NameCollector()
        collector.visit(tree)

        # Add built-in names
        builtins = {
            "print", "len", "range", "list", "dict", "str", "int", "float", "bool",
            "True", "False", "None", "Exception", "ValueError", "TypeError",
            "for", "if", "else", "elif", "while", "def", "class",
            "project", "report", "modifyAllowed", "FLExProject"  # FlexTools/module context
        }
        defined_names.update(builtins)

        # Find undefined variables
        undefined = used_names - defined_names

        # Filter out likely false positives (imported in patterns, etc)
        suspicious = []
        for var in undefined:
            # Flag internal-looking names and MCP variables
            if (var.startswith("API_") or var.isupper() or
                var[0].isupper() and "Operations" in var or
                "API_MODE" in var):
                suspicious.append(var)

        if suspicious:
            return {
                "has_undefined": True,
                "undefined_vars": sorted(suspicious),
                "suggestion": f"Undefined variables detected: {', '.join(suspicious)}. Make sure all classes and modules are imported (e.g., 'from flexlibs2 import ...'). Do not use internal MCP variables like API_MODE_IMPORTS."
            }

        return {"has_undefined": False, "undefined_vars": []}

    except SyntaxError:
        # Can't parse code, skip check
        return {"has_undefined": False, "undefined_vars": []}


def validate_project_context(project_name: str, write_enabled: bool, session_initialized: bool = False) -> dict:
    """Validate project context and show what will be affected."""

    if not project_name:
        return {
            "error": "project_name_required",
            "message": "Project name must be set before running operations",
            "how_to_set": [
                "Option 1: Set in start(project_name='MyProject')",
                "Option 2: Set in this call with project_name='MyProject' parameter"
            ],
        }

    return {
        "project_validated": True,
        "target_project": project_name,
        "write_mode": "ENABLED - will modify project" if write_enabled else "READ-ONLY - safe exploration",
        "ready_to_execute": True
    }


def format_cud_warning(cud_info: dict, write_enabled: bool, confirmed: bool = False) -> dict:
    """Format enhanced warning with staged confirmation for data-affecting operations.

    Args:
        cud_info: Dict with 'operations', 'risks', 'affected_types'
        write_enabled: Whether write mode is enabled
        confirmed: Whether user has confirmed code review

    Shows clear progression through safety stages.
    """
    if not confirmed:
        # Stage 1: Code review
        return {
            "confirmation_required": True,
            "stage": "code_review",
            "reason": "This operation involves Create/Update/Delete actions",
            "detected_operations": cud_info["operations"],
            "potential_risks": cud_info["risks"],
            "affected_data": cud_info["affected_types"],
            "current_state": {
                "write_mode": "ENABLED" if write_enabled else "DISABLED (dry-run)",
                "confirmed": False
            },
            "progress": "1/3 - YOU ARE HERE: Review the code",
            "what_happens_next": (
                "Set confirmed=True to proceed to dry-run mode (RECOMMENDED: write_enabled will remain False)"
                if not write_enabled
                else "DANGER: Write mode is enabled. STRONGLY recommend setting write_enabled=False first"
            ),
            "safe_progression": [
                "1. Review the code carefully (YOU ARE HERE)",
                "2. Set confirmed=True with write_enabled=False to dry-run",
                "3. Review dry-run output",
                "4. Backup your project",
                "5. Set confirmed=True with write_enabled=True to execute"
            ]
        }

    if confirmed and not write_enabled:
        # Stage 2: Dry-run
        return {
            "executing": "dry_run",
            "stage": "dry_run",
            "confirmed": True,
            "write_mode": "DISABLED",
            "progress": "2/3 - DRY-RUN: Showing what WOULD happen",
            "will_modify_database": False,
            "note": "This shows exactly what would happen if write_enabled=True",
            "next_steps": [
                "1. Review the dry-run output above carefully",
                "2. Backup your project (if output looks good)",
                "3. Run again with write_enabled=True to execute"
            ]
        }

    if confirmed and write_enabled:
        # Stage 3: Execute
        return {
            "executing": "live",
            "stage": "execute",
            "confirmed": True,
            "write_mode": "ENABLED",
            "progress": "3/3 - EXECUTING: Making changes to database",
            "will_modify_database": True,
            "operations_that_will_execute": cud_info["operations"],
            "affected_data": cud_info["affected_types"],
            "warning": "DATABASE WILL BE MODIFIED - MAKE SURE YOU HAVE A BACKUP!",
            "final_check": "Backup complete? Ready to proceed?"
        }

    # Unreachable - covers all cases (confirmed: bool, write_enabled: bool)
    return {}


def find_liblcm_mutations(code: str) -> List[Dict[str, Any]]:
    """Find raw LibLCM calls that mutate state.

    Detects patterns like:
    - _cache.CreateObject(...)
    - _cache.DeleteObject(...)
    - _cache.BeginNonUndoableTask()
    - obj.Add(...), obj.Remove(...), obj.Clear(...)
    - obj.MoveTo(...), obj.Insert(...)

    Returns list of mutations with their line numbers for protection context checking.
    """
    mutations = []
    liblcm_mutable_patterns = [
        (r'_cache\s*\.\s*CreateObject\s*\(', 'CreateObject', 'Create'),
        (r'_cache\s*\.\s*DeleteObject\s*\(', 'DeleteObject', 'Delete'),
        (r'_cache\s*\.\s*BeginNonUndoableTask\s*\(', 'BeginNonUndoableTask', 'BeginNonUndoableTask'),
        (r'\.Add\s*\(', 'Add', 'Mutate'),
        (r'\.Remove\s*\(', 'Remove', 'Mutate'),
        (r'\.Clear\s*\(', 'Clear', 'Mutate'),
        (r'\.MoveTo\s*\(', 'MoveTo', 'Reorder'),
        (r'\.Insert\s*\(', 'Insert', 'Mutate'),
    ]

    for line_num, line in enumerate(code.split('\n'), 1):
        # Skip comments
        line_content = re.sub(r'#.*$', '', line)

        for pattern, method_name, category in liblcm_mutable_patterns:
            if re.search(pattern, line_content):
                mutations.append({
                    'method': method_name,
                    'line': line_num,
                    'category': category,
                    'context': line_content.strip()[:60]  # First 60 chars for display
                })

    return mutations


def find_protected_ranges(code: str) -> List[tuple]:
    """Find line ranges protected by modifyAllowed or modifyEnabled/writeEnabled guards.

    Detects:
    - if modifyAllowed: blocks (FLExTools standard parameter)
    - with project.modifyEnabled: blocks
    - with self.project.modifyEnabled: blocks
    - if project.writeEnabled: blocks
    - if self.project.writeEnabled: blocks
    - if project.writeEnabled == True: blocks

    Returns list of (start_line, end_line) tuples for protected ranges.
    """
    protected = []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return protected  # Can't parse, assume no protection

    class ProtectionFinder(ast.NodeVisitor):
        def visit_With(self, node):
            """Find 'with project.modifyEnabled:' blocks."""
            for item in node.items:
                ctx_expr = item.context_expr
                # Match: project.modifyEnabled or self.project.modifyEnabled
                if self._is_modify_enabled(ctx_expr):
                    start_line = node.lineno
                    end_line = node.end_lineno or start_line + 1000
                    protected.append((start_line, end_line))
                    break

            self.generic_visit(node)

        def visit_If(self, node):
            """Find 'if modifyAllowed:' or 'if project.writeEnabled:' blocks."""
            if self._is_write_enabled_check(node.test):
                start_line = node.lineno
                # end_lineno includes the if line, body starts after
                if node.body:
                    end_line = node.body[-1].end_lineno or start_line + 1000
                else:
                    end_line = node.end_lineno or start_line + 1

                protected.append((start_line, end_line))

            self.generic_visit(node)

        def _is_modify_enabled(self, node):
            """Check if expression is 'project.modifyEnabled' or similar."""
            if isinstance(node, ast.Attribute):
                if node.attr == 'modifyEnabled':
                    return True
            return False

        def _is_write_enabled_check(self, node):
            """Check if condition checks 'modifyAllowed', 'writeEnabled', etc."""
            # Pattern: modifyAllowed (name - FLExTools standard parameter)
            if isinstance(node, ast.Name):
                return node.id == 'modifyAllowed'

            # Pattern: project.writeEnabled (attribute)
            if isinstance(node, ast.Attribute):
                return node.attr == 'writeEnabled'

            # Pattern: project.writeEnabled == True (compare)
            if isinstance(node, ast.Compare):
                # Check left side
                if isinstance(node.left, ast.Attribute):
                    if node.left.attr == 'writeEnabled':
                        return True
                if isinstance(node.left, ast.Name):
                    if node.left.id == 'modifyAllowed':
                        return True
                # Check comparators
                for comp in node.comparators:
                    if isinstance(comp, ast.Attribute):
                        if comp.attr == 'writeEnabled':
                            return True
                    if isinstance(comp, ast.Name):
                        if comp.id == 'modifyAllowed':
                            return True
            return False

    finder = ProtectionFinder()
    finder.visit(tree)
    return protected


def certify_script_readonly(code: str, api_index) -> dict:
    """Certify whether a script makes any FlexLibs2 mutating calls using API index.

    Uses the is_mutating flag from the API index to identify write operations with
    high confidence. Falls back to regex-based detection for code not in the index
    (raw LCM, custom logic, etc.).

    Also detects raw LibLCM mutations and checks if they're protected by
    modifyEnabled or writeEnabled guards.

    Args:
        code: Python code to analyze
        api_index: Loaded API index with is_mutating field per method

    Returns:
        {
          "is_certified_readonly": bool,           # True = no unprotected mutations
          "confidence": str,                       # "high" | "medium" | "low"
          "mutating_calls": [                      # Detected FlexLibs2 mutations
              {"class": str, "method": str, "is_mutating": bool, "source": str}
          ],
          "unprotected_liblcm_calls": [            # Raw LCM calls without guard
              {"method": str, "line": int, "context": str}
          ],
          "protected_liblcm_calls": [              # Raw LCM calls with guard
              {"method": str, "line": int, "context": str}
          ],
          "unknown_calls": [...],                  # Calls not found in index
          "raw_lcm_patterns": [...],               # Regex-detected raw LCM writes
        }
    """
    # Normalize code by removing leading indentation (important for test strings)
    code = textwrap.dedent(code)

    mutating_calls = []
    unknown_calls = []
    raw_lcm_patterns = []
    unprotected_liblcm_calls = []
    protected_liblcm_calls = []
    confidence_sources = {"index": 0, "regex": 0, "unknown": 0}

    # Get protected ranges once for both FlexLibs2 and LibLCM checks
    protected_ranges = find_protected_ranges(code)

    # Step 1: Extract FlexLibs2 Operations method calls with line numbers
    # Pattern: ClassName(project).MethodName( or ClassName.MethodName( (static)
    operations_call_pattern = r'(\w+Operations)\s*(?:\(\s*\w+\s*\))?\s*\.\s*(\w+)\s*\('
    operations_calls_with_lines = []

    for match in re.finditer(operations_call_pattern, code):
        class_name, method_name = match.groups()
        # Calculate line number from character position
        line_num = code[:match.start()].count('\n') + 1
        operations_calls_with_lines.append((class_name, method_name, line_num))

    # Step 2: Look up each call in the API index and check if protected
    if api_index and api_index.get("flexlibs2"):
        entities = api_index["flexlibs2"].get("entities", {})

        for class_name, method_name, line_num in operations_calls_with_lines:
            # Check if this call is protected by a guard
            is_protected = any(
                start <= line_num <= end
                for start, end in protected_ranges
            )

            if class_name in entities:
                class_entity = entities[class_name]
                methods = class_entity.get("methods", [])

                # Search for method in class
                method_found = False
                for method in methods:
                    if method.get("name") == method_name:
                        method_found = True
                        is_mutating = method.get("is_mutating", False)

                        # Only add as unprotected mutation if it's actually mutating and not protected
                        if is_mutating and not is_protected:
                            mutating_calls.append({
                                "class": class_name,
                                "method": method_name,
                                "is_mutating": True,
                                "source": "index",
                                "line": line_num,
                                "protected": False
                            })
                            confidence_sources["index"] += 1
                        elif is_mutating and is_protected:
                            # Protected mutation - don't add to mutating_calls
                            pass
                        else:
                            # Read-only call - still track it
                            mutating_calls.append({
                                "class": class_name,
                                "method": method_name,
                                "is_mutating": False,
                                "source": "index",
                                "line": line_num,
                                "protected": True
                            })
                        break

                if not method_found:
                    # Class found but method not in index - conservative: treat as mutating
                    if not is_protected:
                        unknown_calls.append({
                            "class": class_name,
                            "method": method_name,
                            "reason": "method not in index",
                            "line": line_num
                        })
                        mutating_calls.append({
                            "class": class_name,
                            "method": method_name,
                            "is_mutating": True,
                            "source": "unknown",
                            "line": line_num,
                            "protected": False
                        })
                        confidence_sources["unknown"] += 1
            else:
                # Class not in index - fall through to regex
                pass

    # Step 3: Regex-based detection for patterns not in index
    # Use existing detect_cud_operations() for raw LCM patterns
    cud_info = detect_cud_operations(code)
    if cud_info["is_cud"]:
        raw_lcm_patterns.extend(cud_info["operations"])
        confidence_sources["regex"] += 1

    # Step 4: Detect raw LibLCM mutations and check if they're protected
    liblcm_mutations = find_liblcm_mutations(code)
    # protected_ranges already calculated above in Step 2

    for mutation in liblcm_mutations:
        line_num = mutation['line']
        is_protected = any(
            start <= line_num <= end
            for start, end in protected_ranges
        )

        if is_protected:
            protected_liblcm_calls.append({
                'method': mutation['method'],
                'line': line_num,
                'category': mutation['category'],
                'context': mutation['context']
            })
        else:
            unprotected_liblcm_calls.append({
                'method': mutation['method'],
                'line': line_num,
                'category': mutation['category'],
                'context': mutation['context'],
                'is_mutating': True
            })

    # Step 6: Determine confidence level
    total_calls = len(mutating_calls) + len(unknown_calls) + len(unprotected_liblcm_calls)
    if total_calls == 0 and not raw_lcm_patterns:
        confidence = "high"
    elif confidence_sources["unknown"] == 0 and confidence_sources["regex"] == 0 and not unprotected_liblcm_calls:
        confidence = "high"
    elif confidence_sources["unknown"] == 0 and not unprotected_liblcm_calls:
        confidence = "medium"
    else:
        confidence = "low"

    # Step 7: Build certification result
    # Script is read-only certified if:
    # 1. No FlexLibs2 mutating calls
    # 2. No unprotected raw LibLCM mutations
    # 3. No raw LCM patterns detected
    is_certified_readonly = (
        not any(m.get("is_mutating") for m in mutating_calls)
        and not unprotected_liblcm_calls
        and not raw_lcm_patterns
    )

    return {
        "is_certified_readonly": is_certified_readonly,
        "confidence": confidence,
        "mutating_calls": [m for m in mutating_calls if m.get("is_mutating")],
        "readonly_calls": [m for m in mutating_calls if not m.get("is_mutating")],
        "unprotected_liblcm_calls": unprotected_liblcm_calls,
        "protected_liblcm_calls": protected_liblcm_calls,
        "unknown_calls": unknown_calls,
        "raw_lcm_patterns": raw_lcm_patterns,
    }


def get_unprotected_write_guidance(cert: dict) -> dict:
    """Generate detailed guidance for fixing unprotected mutations.

    Args:
        cert: Result from certify_script_readonly() with unprotected mutations

    Returns:
        Guidance dict with examples and step-by-step instructions
    """
    mutating = cert.get("mutating_calls", [])
    unprotected_liblcm = cert.get("unprotected_liblcm_calls", [])

    # Build list of unprotected mutations found
    mutations_found = []
    if mutating:
        mutations_found.extend([f"{m['class']}.{m['method']}()" for m in mutating if m.get("is_mutating")])
    if unprotected_liblcm:
        mutations_found.extend([m['method'] + "()" for m in unprotected_liblcm])

    return {
        "error": "unprotected_mutations_detected",
        "message": f"Found {len(mutations_found)} unprotected mutation(s). Code cannot run until protected.",
        "mutations_found": mutations_found,
        "why": "All write operations must be guarded with 'if modifyAllowed:' to prevent accidental data loss.",
        "fix_pattern": {
            "before": "project.LexEntry.SetLexemeForm(entry, 'new_form')",
            "after": "if modifyAllowed:\n    project.LexEntry.SetLexemeForm(entry, 'new_form')\n    report.Info('Updated entry')\nelse:\n    report.Info('(Would update entry to: new_form)')"
        },
        "templates_to_review": [
            "templates/2-flexlibs2-template.py (recommended - best documented)",
            "templates/1-flexlibs-stable-template.py (for FieldWorks < 9.0)",
            "templates/3-liblcm-template.py (for advanced use cases)"
        ],
        "next_steps": [
            "1. Open a template above to see the if modifyAllowed: pattern in context",
            "2. Update your code to wrap all mutations with: if modifyAllowed:",
            "3. Move read-only logic before the if block",
            "4. Add else block to preview what would be changed",
            "5. Re-run with the updated code"
        ]
    }
