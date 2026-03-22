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
