#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Execution handler functions for FlexToolsMCP.

These handlers manage module and operation execution:
- start_module: Interactive wizard to create FlexTools modules
- run_module: Execute a complete FlexTools module
- run_operation: Execute ad-hoc operations directly
- get_operation_logs: View execution logs and pattern recommendations
"""

import json
import asyncio
import sys
import subprocess
import tempfile
import os
import ast
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from mcp.types import TextContent

from ._import_helper import (
    safe_import_kernel_deps,
    safe_import_session_state,
    safe_import_logging_helpers,
)

# Import async subprocess helper with fallback
try:
    from ..subprocess_helpers import run_script_async
except ImportError:
    from server.subprocess_helpers import run_script_async

# Import kernel dependencies with fallback
json_response, session_state, get_log_dir, get_api_index = safe_import_kernel_deps()
_, get_operations_logger = safe_import_logging_helpers()
SessionState = safe_import_session_state()

try:
    from ..kernel import get_pattern_tracker, get_project_write_lock
except ImportError:
    from server.kernel import get_pattern_tracker, get_project_write_lock

# Import validators with fallback
try:
    from ..validators import (
        detect_cud_operations, detect_polymorphic_error, detect_undefined_variables,
        detect_missing_operations_imports, detect_wrong_library_imports, format_cud_warning,
        certify_script_readonly, get_unprotected_write_guidance, detect_casting_needs, validate_server_state,
        detect_unknown_attribute_error, detect_invalid_project_chains,
    )
except ImportError:
    from server.validators import (
        detect_cud_operations, detect_polymorphic_error, detect_undefined_variables,
        detect_missing_operations_imports, detect_wrong_library_imports, format_cud_warning,
        certify_script_readonly, get_unprotected_write_guidance, detect_casting_needs, validate_server_state,
        detect_unknown_attribute_error, detect_invalid_project_chains,
    )

# Import response utilities and HeadlessReport with fallback
try:
    from ...response_utils import build_response_with_context, error_response
    from ..headless_report import HeadlessReport
except (ImportError, ValueError):
    from response_utils import build_response_with_context, error_response
    from server.headless_report import HeadlessReport

# Import response field constants
from ..response_keys import (
    KEY_STATUS, KEY_ERROR, KEY_MESSAGE, KEY_NEEDS_INPUT, KEY_COMPLETE,
    KEY_MODULE_NAME, KEY_SYNOPSIS, KEY_API_TARGET, KEY_INCLUDE_DRY_RUN,
    KEY_MODIFIES_DB, KEY_QUESTIONS, KEY_QUESTION, KEY_EXAMPLE, KEY_PROVIDED,
    KEY_SESSION, KEY_SUMMARY, KEY_WARNINGS, KEY_RAW_OUTPUT, KEY_STDERR,
    KEY_EXIT_CODE, KEY_WRITE_CERTIFICATION, KEY_IS_CERTIFIED_READONLY,
    KEY_MUTATING_CALLS_DETECTED, KEY_CASTING_ISSUES, KEY_SEVERITY,
    KEY_HAS_CASTING_ISSUES, KEY_WHY, KEY_APPLIES_TO, KEY_HOW_TO_FIX,
    KEY_SUGGESTIONS, KEY_SUCCESS, KEY_PROJECT, KEY_WRITE_ENABLED,
    KEY_MESSAGES, KEY_TEMPLATE, KEY_CONFIDENCE, KEY_NEXT_STEPS
)

# ============================================================
# Constants (avoid stringly-typed code)
# ============================================================
# Error codes (execution-specific)
ERROR_PROJECT_NAME_REQUIRED = "project_name_required"
ERROR_CASTING_ISSUES = "casting_issues_detected"
ERROR_API_DISCOVERY_REQUIRED = "api_discovery_required"
ERROR_UNDEFINED_VARIABLES = "undefined_variables"
ERROR_MISSING_IMPORTS = "missing_imports"
ERROR_WRONG_LIBRARY = "wrong_library_imports"
ERROR_UNPROTECTED_CODE = "unprotected_code"


def _validate_api_mode(api_mode: str) -> Tuple[bool, str]:
    """Validate that the requested API mode libraries are properly installed.

    Args:
        api_mode: One of 'flexlibs_stable', 'flexlibs2', 'liblcm'

    Returns:
        (is_valid, error_message)
    """
    if api_mode == "flexlibs2":
        try:
            import flexlibs2  # type: ignore
            # Check version is available (flexlibs2 uses 'version' not '__version__')
            if not hasattr(flexlibs2, 'version') and not hasattr(flexlibs2, '__version__'):
                return False, "flexlibs2 missing version info"
            return True, ""
        except ImportError as e:
            return False, f"flexlibs2 not found: {e}"

    elif api_mode == "flexlibs_stable":
        try:
            import flexlibs  # type: ignore
            return True, ""
        except ImportError as e:
            return False, f"flexlibs not found: {e}"

    elif api_mode == "liblcm":
        # LibLCM is optional, validated at runtime
        return True, ""

    return False, f"Unknown API mode: {api_mode}"


def _get_casting_helpers_code(injection_tier: str = "full", helpers_needed: Optional[set] = None) -> str:
    """Generate casting helpers code based on injection tier.

    Uses HELPER_FUNCTION_DEFS from constants to avoid duplication.

    Args:
        injection_tier: 'none' | 'minimal' | 'full'
        helpers_needed: Set of helper names for 'minimal' tier

    Returns:
        Python code string with helper definitions (or empty if tier='none')
    """
    try:
        from ...casting_helpers import HELPER_FUNCTION_DEFS
    except ImportError:
        from casting_helpers import HELPER_FUNCTION_DEFS

    if injection_tier == "none":
        return ""

    if injection_tier == "minimal" and helpers_needed:
        # Only import what's needed
        helper_names = ", ".join(sorted(helpers_needed))
        return f"""
# Auto-injected: Minimal casting helpers for polymorphic types (three-tier strategy, tier 2)
try:
    from casting_helpers import {helper_names}
except ImportError:
    # Fallback: Define only needed helpers if module not available
{HELPER_FUNCTION_DEFS}
"""

    # Full injection (tier='full' or defensive fallback)
    return f"""
# Auto-injected: Safe casting helpers for polymorphic types (three-tier strategy, tier 3 - full)
try:
    from casting_helpers import safe_get_property, smart_cast, cast_or_default, get_headword, get_lexeme_form
except ImportError:
    # Fallback: Define all helpers if module not available
{HELPER_FUNCTION_DEFS}
"""


def _get_api_mode_imports(api_mode: str, helpers_needed: Optional[set] = None, injection_tier: str = "full") -> str:
    """Generate imports and namespace dict for a given API mode.

    Args:
        api_mode: One of 'flexlibs_stable', 'flexlibs2', 'liblcm'
        helpers_needed: Optional set of specific helper names to inject (e.g., {'get_headword'})
        injection_tier: 'none' | 'minimal' | 'full'
            - none: Don't inject casting helpers (code pre-flighted, safe)
            - minimal: Only inject helpers in helpers_needed set
            - full: Inject full suite of helpers (defensive mode)

    Returns:
        imports_code: Python code string with imports and helpers

    Raises:
        ValueError: If API mode is invalid or required libraries are not installed
    """
    if helpers_needed is None:
        helpers_needed = set()

    # Gate #1: Validate API mode is valid
    is_valid, error_msg = _validate_api_mode(api_mode)
    if not is_valid:
        raise ValueError(f"API mode validation failed: {error_msg}")

    # Base imports per API mode
    BASE_IMPORTS = {
        "flexlibs_stable": "from flexlibs import FLExInitialize, FLExCleanup, FLExProject",
        "flexlibs2": "from flexlibs2 import FLExInitialize, FLExCleanup, FLExProject",
        "liblcm": """import clr
clr.AddReference('SIL.LCModel')
from SIL.LCModel import *
from SIL.LCModel.Core.WritingSystems import *

def FLExInitialize():
    \"\"\"Initialize LibLCM backend.\"\"\"
    pass

def FLExCleanup():
    \"\"\"Cleanup LibLCM backend.\"\"\"
    pass

class FLExProject:
    \"\"\"Wrapper for direct LibLCM project access.\"\"\"
    def __init__(self):
        self._backend = None
        self._cache = None

    def OpenProject(self, projectName, writeEnabled=False):
        \"\"\"Open project using LibLCM directly.\"\"\"
        try:
            from SIL.LCModel import LcmCache
            self._cache = LcmCache.CreateCacheForNewLcmProject(projectName, "en", "en", "en",
                                                               writeSystemType=LcmWriteSystemType.kDefault)
            self._backend = self._cache.ServiceLocator
        except Exception as e:
            raise RuntimeError(f"Failed to open LibLCM project: {e}")

    def CloseProject(self):
        \"\"\"Close project.\"\"\"
        if self._cache:
            self._cache.Dispose()

    def __getattr__(self, name):
        \"\"\"Delegate unknown attributes to backend.\"\"\"
        if self._backend:
            return getattr(self._backend, name)
        raise AttributeError(f"Project not initialized: {name}")
""",
    }

    if api_mode not in BASE_IMPORTS:
        raise ValueError(f"Unknown API mode: {api_mode}")

    # Get base imports and append casting helpers (single shared logic)
    imports = BASE_IMPORTS[api_mode]
    casting_helpers = _get_casting_helpers_code(injection_tier, helpers_needed)
    imports += casting_helpers

    return imports


def _log_operation_failure(
    error: Optional[str] = None,
    error_type: Optional[str] = None,
    stderr: Optional[str] = None,
    info_count: int = 0,
    warning_count: int = 0,
    error_count: int = 0,
) -> None:
    """Emit the [FAIL] / Messages / Operation End log block with diagnostic detail.

    Centralizes the failure-logging shape so the actual cause (error text,
    error_type, stderr) reaches the log instead of just "0 errors".
    """
    logger = get_operations_logger()
    logger.info("[FAIL] Operation failed")
    if error_type:
        logger.info(f"Error type: {error_type}")
    if error:
        first_line = error.strip().splitlines()[0] if error.strip() else ""
        if len(first_line) > 500:
            first_line = first_line[:500] + "..."
        logger.info(f"Error: {first_line}")
    if stderr:
        for line in stderr.strip().splitlines()[:10]:
            logger.debug(f"stderr: {line}")
    logger.info(f"Messages: {info_count} info, {warning_count} warnings, {error_count} errors")
    logger.info("=== Operation End ===")


def _run_validator(validator_func, code: str, check_key: str, error_code: str, **validator_kwargs) -> Optional[list[TextContent]]:
    """Run a single validator and return error response if validation fails.

    Reduces code duplication in handle_run_module by centralizing validator pattern.

    Args:
        validator_func: The validator function to call (e.g., detect_cud_operations)
        code: The code to validate
        check_key: The key in validator result to check (e.g., 'has_cud_operations')
        error_code: The error code to return if validation fails
        **validator_kwargs: Additional keyword args to pass to validator_func

    Returns:
        Error response list if validation fails, None if validation passes
    """
    check_result = validator_func(code, **validator_kwargs)
    if check_result.get(check_key):
        return error_response(
            error_code,
            check_result.get("suggestion", "Validation failed"),
            **check_result.get("extras", {})
        )
    return None


async def handle_start_module(args: dict) -> list[TextContent]:
    """Interactive wizard to start creating a new FlexTools module."""
    import platform

    # Gather environment info
    env_info = {
        "python_version": "{}.{}.{}".format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro),
        "python_implementation": platform.python_implementation(),
        "platform": platform.system(),
        "can_use_modern_python": sys.version_info >= (3, 6),
    }

    # Check what parameters were provided
    provided = {k: v for k, v in args.items() if v is not None}

    # Define required and optional questions
    required_questions = []
    optional_questions = []

    if "module_name" not in provided:
        required_questions.append({
            "field": "module_name",
            "question": "What should the module be named?",
            "type": "string",
            "example": "Export Custom Data"
        })

    if "synopsis" not in provided:
        required_questions.append({
            "field": "synopsis",
            "question": "Provide a short description of what the module does:",
            "type": "string",
            "example": "Exports custom field data to a file"
        })

    if "api_target" not in provided:
        required_questions.append({
            "field": "api_target",
            "question": "Which API should the module target?",
            "type": "choice",
            "options": [
                {
                    "value": "flexlibs2",
                    "label": "FlexLibs 2.0 (Recommended)",
                    "description": "Modern Python wrappers with 99% documentation coverage and examples. Best for new modules. Use api_mode='flexlibs2' in searches."
                },
                {
                    "value": "flexlibs_stable",
                    "label": "FlexLibs Stable + LibLCM fallback",
                    "description": "Legacy Python wrappers (~40 functions) with LibLCM fallback for advanced features. Use api_mode='flexlibs_stable' in searches."
                },
                {
                    "value": "liblcm",
                    "label": "Pure LibLCM",
                    "description": "Direct C# API access via pythonnet. Maximum flexibility but requires .NET knowledge. Use api_mode='liblcm' in searches."
                }
            ],
            "recommended": "flexlibs2"
        })

    if "modifies_db" not in provided:
        required_questions.append({
            "field": "modifies_db",
            "question": "Will this module modify the FieldWorks database?",
            "type": "boolean",
            "hint": "Set to True if the module creates, updates, or deletes entries, senses, or other data."
        })

    if "domain" not in provided:
        required_questions.append({
            "field": "domain",
            "question": "What is the primary domain this module works with?",
            "type": "choice",
            "options": [
                {"value": "lexicon", "label": "Lexicon", "description": "Entries, senses, definitions, glosses"},
                {"value": "grammar", "label": "Grammar", "description": "Parts of speech, morphology, inflection"},
                {"value": "texts", "label": "Texts", "description": "Interlinear texts, discourse analysis"},
                {"value": "media", "label": "Media", "description": "Pictures, audio files, linked files"},
                {"value": "general", "label": "General", "description": "Project-wide operations, multiple domains"}
            ]
        })

    if args.get("modifies_db") and "include_dry_run" not in provided:
        required_questions.append({
            "field": "include_dry_run",
            "question": "Include a DRY_RUN safety mode? (Recommended for write operations)",
            "type": "boolean",
            "hint": "DRY_RUN mode shows what would happen without making changes. Useful for testing.",
            "recommended": True
        })

    # Optional question - only ask if no required questions remain
    if "test_project" not in provided:
        optional_questions.append({
            "field": "test_project",
            "question": "Do you have a FieldWorks test project to verify the script against?",
            "type": "string",
            "hint": "Provide the project name (e.g., 'Sena 3') or path. This helps verify the script works before running on production data.",
            "optional": True,
            "example": "Sena 3"
        })

    # If we have required questions, return them along with optional ones
    if required_questions:
        questions = required_questions + optional_questions
        return json_response({
            KEY_STATUS: KEY_NEEDS_INPUT,
            "environment": env_info,
            KEY_PROVIDED: provided,
            "required_questions": required_questions,
            "optional_questions": optional_questions,
            KEY_QUESTIONS: questions,
            "instructions": "Please ask the user these questions and call start_module again with the answers. Optional questions can be skipped."
        })

    # All questions answered - generate the template
    module_name = args["module_name"]
    synopsis = args["synopsis"]
    api_target = args["api_target"]
    modifies_db = args["modifies_db"]
    domain = args.get("domain", "general")
    include_dry_run = args.get("include_dry_run", False)
    test_project = args.get("test_project")

    # Build imports
    imports = ["from flextoolslib import *"]

    # Build helper code
    helpers = []
    if include_dry_run:
        helpers.append("""
#----------------------------------------------------------------
# Configuration

DRY_RUN = True  # Set to False to actually make changes
""")

    # Build main function body
    main_body_lines = []

    if modifies_db and include_dry_run:
        main_body_lines.append("""    if not modifyAllowed and not DRY_RUN:
        report.Error("This module requires write access.")
        return

    if DRY_RUN:
        report.Warning("DRY RUN mode - no changes will be made")
""")
    elif modifies_db:
        main_body_lines.append("""    if not modifyAllowed:
        report.Error("This module requires write access.")
        return
""")

    main_body_lines.append("""
    report.Info("Starting...")

    # TODO: Implement module logic

    report.Info("Done.")
""")

    # Combine main body
    main_body = "".join(main_body_lines)

    # Generate final template
    template = """#
#   {module_name}
#    - A FlexTools Module -
#
#   {synopsis}
#
#   API Target: {api_target}
#   Platforms: Python .NET and IronPython
#

{imports}
{helpers}
#----------------------------------------------------------------
# Documentation that the user sees:

docs = {{FTM_Name        : "{module_name}",
        FTM_Version     : 1,
        FTM_ModifiesDB  : {modifies_db},
        FTM_Synopsis    : "{synopsis}",
        FTM_Description :
\"\"\"
{synopsis}

<additional details here>
\"\"\" }}

#----------------------------------------------------------------
# The main processing function

def Main(project, report, modifyAllowed):
    \"\"\"
    Main entry point for the FlexTools module.

    Args:
        project: FLExProject instance providing access to the FieldWorks database
        report: Reporter object for logging (report.Info, report.Warning, report.Error)
        modifyAllowed: Boolean indicating if database modifications are permitted
    \"\"\"
{main_body}

#----------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(Main, docs)

#----------------------------------------------------------------
if __name__ == '__main__':
    print(FlexToolsModule.Help())
""".format(
        module_name=module_name,
        synopsis=synopsis,
        api_target=api_target,
        imports="\n".join(imports),
        helpers="".join(helpers),
        modifies_db=modifies_db,
        main_body=main_body
    )

    # API-specific notes and search guidance
    api_notes = {
        "flexlibs2": {
            "search_mode": "flexlibs2",
            "tips": [
                "Use project.Senses.GetAll() to iterate senses",
                "Use project.CustomFields.GetValue/SetValue for custom fields",
                "Use project.Media.* for file operations",
                "Full documentation at 99% coverage with examples"
            ],
            "search_reminder": "Use api_mode='flexlibs2' when calling search_by_capability"
        },
        "flexlibs_stable": {
            "search_mode": "flexlibs_stable",
            "tips": [
                "Use project.LexiconAllEntries() to iterate entries",
                "More limited API (~40 functions)",
                "LibLCM fallback available for advanced features",
                "Compatible with older FlexTools installations"
            ],
            "search_reminder": "Use api_mode='flexlibs_stable' when calling search_by_capability (includes LibLCM fallback)"
        },
        "liblcm": {
            "search_mode": "liblcm",
            "tips": [
                "Direct access to C# LibLCM API via pythonnet",
                "Requires understanding of .NET and LibLCM architecture",
                "Most powerful but also most complex",
                "Use ILexEntry, ILexSense, etc. interface types"
            ],
            "search_reminder": "Use api_mode='liblcm' when calling search_by_capability"
        }
    }

    # Build next steps based on configuration
    next_steps = [
        "Save the template to your FlexTools Modules folder",
        "Replace TODO comments with your implementation",
    ]

    if include_dry_run:
        next_steps.append("Test with DRY_RUN=True first to verify behavior without making changes")

    if test_project:
        next_steps.append("Run the module against '{}' to verify it works correctly".format(test_project))
        next_steps.append("Check the FlexTools report output for any errors or warnings")
    else:
        next_steps.append("IMPORTANT: Test on a backup/sample project before running on production data")

    next_steps.append("Use search_by_capability to find specific API methods you need")

    # Build configuration output
    config = {
        "module_name": module_name,
        "synopsis": synopsis,
        "api_target": api_target,
        "modifies_db": modifies_db,
        "domain": domain,
        "include_dry_run": include_dry_run
    }
    if test_project:
        config["test_project"] = test_project

    api_info = api_notes.get(api_target, {})

    return json_response({
        KEY_STATUS: KEY_COMPLETE,
        "environment": env_info,
        "configuration": config,
        KEY_TEMPLATE: template,
        "api_guidance": {
            "mode": api_target,
            "search_mode": api_info.get("search_mode", api_target),
            "search_reminder": api_info.get("search_reminder", ""),
            "tips": api_info.get("tips", [])
        },
        KEY_NEXT_STEPS: next_steps,
        "testing_reminder": "Always test FlexTools modules on a backup or sample project first!" if not test_project else None
    })


async def handle_run_module(args: dict) -> list[TextContent]:
    """Execute code (snippet or full module) against a FieldWorks project.

    Accepts:
    - Minimal snippets: entries = project.LexEntry.GetAll()
    - Full modules: def Main(project, report, modifyAllowed): ...
    - Anything in between

    If code defines Main(), it will be called. Otherwise, code runs as-is.
    """
    # Get code from parameter (unified interface)
    code = args.get("code")
    if not code:
        # Fallback for backwards compatibility (shouldn't happen)
        code = args.get("module_code") or args.get("operations", "")

    # Use session state as fallback for project and write settings
    project_name = args.get("project_name", session_state.get_project())
    write_enabled = args.get("write_enabled", session_state.is_write_enabled())
    api_mode = session_state.get_mode()

    # Validate project_name is available
    if not project_name:
        return error_response(
            "project_name_required",
            "No project specified. Either set project_name in start() or provide it directly.",
            session=session_state.summary()
        )

    # === PREFLIGHT: Validate server state before attempting execution ===
    server_health = validate_server_state()
    if not server_health["is_healthy"]:
        error_details = []
        for severity, message in server_health["issues"]:
            if severity == "error":
                error_details.append(f"[{severity.upper()}] {message}")
        return error_response(
            "server_state_error",
            "Server initialization incomplete. Cannot execute code:\n" + "\n".join(error_details),
            server_state=server_health,
            hint="The server may not have started correctly. Check the server logs and try restarting."
        )

    # Parse AST early for reuse across all validators (avoid redundant parsing)
    try:
        code_tree = ast.parse(code)
    except SyntaxError as e:
        return error_response(
            "syntax_error",
            f"Invalid Python syntax at line {e.lineno}: {e.msg}",
            line_number=e.lineno,
            guidance="Check your Python code for syntax errors (missing colons, unmatched parentheses, etc.)"
        )

    # Check for unprotected mutations - HARD BLOCK if found
    cud_info = detect_cud_operations(code)
    cert = certify_script_readonly(code, get_api_index(), code_tree)

    # CRITICAL: Refuse unprotected code unconditionally
    if not cert["is_certified_readonly"]:
        guidance = get_unprotected_write_guidance(cert)
        return [TextContent(type="text", text=json.dumps(guidance, indent=2))]

    # Check for polymorphic casting issues - detect and suggest fixes BEFORE running
    # This catches errors like: sense.Owner.HeadWord (ICmObject doesn't have HeadWord)
    api_idx = get_api_index()
    casting_index = api_idx.casting_index if api_idx else None
    casting_check = detect_casting_needs(code, casting_index)
    if casting_check["has_casting_issues"]:
        # Format issues with clear fixes for all 3 API flavors
        issues = casting_check["casting_issues"]
        return error_response(
            "casting_issues_detected",
            f"Found {len(issues)} polymorphic property access issue(s) that require casting.",
            severity=casting_check["severity"],
            issues=issues,
            general_guidance={
                "why": "In C# (LibLCM), base interface types like ICmObject don't expose all properties. You must cast to concrete types (ILexEntry, IMultiString, etc.) to access them.",
                "applies_to": "All 3 API flavors (flexlibs_stable, flexlibs2, liblcm) - this is a C# type system issue, not wrapper-specific",
                "how_to_fix": [
                    "1. Call flextools_resolve_property(property_name='{}', context_entity='{}') to get the exact casting solution".format(
                        issues[0]["property"],
                        issues[0].get("context_entity", "ICmObject")
                    ),
                    "2. Apply the suggested cast from the tool response",
                    "3. Re-run your code"
                ]
            },
            tool_to_call="flextools_resolve_property",
            next_steps="Use flextools_resolve_property to resolve the casting issue, then update your code"
        )

    # Require API discovery before executing code
    skip_api_check = args.get("skip_api_check", False)
    if not skip_api_check and len(session_state.get_discovered_apis()) == 0:
        return error_response(
            "api_discovery_required",
            "No APIs have been discovered yet. Before running code, you MUST use one of these tools first:\n"
            "1. start(task='...') - discovers relevant APIs automatically\n"
            "2. get_object_api(object_type='...') - get API for specific object\n"
            "3. search_by_capability(query='...') - search for APIs by description\n\n"
            "This prevents using incorrect/hallucinated method names.",
            hint="Call get_object_api() for each object/operation you use (FLExProject, LexEntryOperations, etc.), then write code using those discovered APIs.",
            session=session_state.summary()
        )

    # Note: Output mechanism check removed - both print() and report.Info() work in unified runner
    # The SimpleReporter provides both mechanisms transparently

    # Check for undefined variables that indicate hallucinated/internal names
    # Pass pre-parsed AST to avoid re-parsing
    undefined_check = detect_undefined_variables(code, code_tree)
    if undefined_check["has_undefined"]:
        return error_response(
            "undefined_variables",
            undefined_check["suggestion"],
            undefined_vars=undefined_check["undefined_vars"],
            guidance="All variables must be either: (1) imported from a module, (2) defined in your code, or (3) provided by FlexTools (project, report, modifyAllowed). Do not use internal MCP variable names."
        )

    # Check for missing Operations class imports
    missing_ops_check = detect_missing_operations_imports(code, api_mode)
    if missing_ops_check["has_missing"]:
        return error_response(
            "missing_imports",
            missing_ops_check["suggestion"],
            missing_imports=missing_ops_check["missing_imports"],
            api_mode=api_mode,
            guidance="Add the import statement shown above to the top of your code."
        )

    # Check for wrong library imports
    wrong_imports_check = detect_wrong_library_imports(code, api_mode)
    if wrong_imports_check["has_wrong_imports"]:
        return error_response(
            "wrong_library_imports",
            wrong_imports_check["suggestion"],
            wrong_imports=wrong_imports_check["wrong_imports"],
            api_mode=api_mode,
            guidance=f"Ensure all imports match your selected API mode. You selected '{api_mode}' mode."
        )

    # Pre-flight: catch project.<accessor>/<method> typos before subprocess launch.
    # Conservative: only rejects when difflib finds a high-confidence match
    # (cutoff 0.7) -- unrecognized names with no close match are passed through
    # to runtime so we don't block valid direct-project methods we don't index.
    chain_check = detect_invalid_project_chains(code_tree, api_idx)
    if chain_check["has_invalid"]:
        return error_response(
            "invalid_api_chain",
            chain_check["suggestion"],
            issues=chain_check["issues"],
            guidance="Replace each flagged expression with the suggested correct name and re-run."
        )

    timeout_seconds = args.get("timeout_seconds", 300)

    # Determine three-tier injection strategy based on pre-flight results
    # Tier 1 (none): No casting issues → Skip helper injection (lightweight)
    # Tier 2 (minimal): Issues found but handled → Inject only needed helpers (balanced)
    # Tier 3 (full): Defensive mode → Inject full suite (heavy but safest)
    injection_tier = casting_check.get("injection_tier", "full")  # Default to full for safety
    helpers_needed = casting_check.get("helpers_needed", set())  # Set of specific helpers

    # Telemetry: Track injection strategy
    get_operations_logger().debug(f"Three-tier injection: tier={injection_tier}, helpers_needed={helpers_needed}")

    # Log module start with rich formatting
    get_operations_logger().info(f"=== Operation Start ===")
    get_operations_logger().info(f"Project: {project_name}")
    get_operations_logger().info(f"Write enabled: {write_enabled}")
    get_operations_logger().debug(f"Code:")
    # Log the full code, each line with proper indentation
    for code_line in code.split('\n'):
        get_operations_logger().debug(code_line)

    # Build warnings
    warnings = []
    if write_enabled:
        warnings.extend([
            "*** WRITE MODE ENABLED ***",
            "Changes WILL be made to the database!",
            "Make sure you have a backup of your project!",
            ""
        ])
    else:
        warnings.extend([
            "Running in READ-ONLY mode (dry-run)",
            "No changes will be made to the database.",
            "Set write_enabled=True to enable modifications.",
            ""
        ])

    # Create the runner script that will be executed in a subprocess
    # (Large script template - hardcoded imports to avoid placeholder/indentation issues)
    runner_script = '''# -*- coding: utf-8 -*-
"""FlexTools Module Runner - Generated by FlexToolsMCP"""
import sys
import json
import os
import traceback
import types

# Create fake flextoolslib module
flextoolslib = types.ModuleType('flextoolslib')

# FlexTools module documentation keys
flextoolslib.FTM_Name = "FTM_Name"
flextoolslib.FTM_Version = "FTM_Version"
flextoolslib.FTM_ModifiesDB = "FTM_ModifiesDB"
flextoolslib.FTM_Synopsis = "FTM_Synopsis"
flextoolslib.FTM_Description = "FTM_Description"
flextoolslib.FTM_Help = "FTM_Help"

# Minimal FlexToolsModuleClass
class FlexToolsModuleClass:
    def __init__(self, runFunction=None, docs=None, configuration=None):
        self.runFunction = runFunction
        self.docs = docs or {}
        self.configuration = configuration or []

    def Run(self, project, report, modifyAllowed=False):
        if self.runFunction:
            self.runFunction(project, report, modifyAllowed)

    def Help(self):
        return self.docs.get(flextoolslib.FTM_Description, "")

flextoolslib.FlexToolsModuleClass = FlexToolsModuleClass
sys.modules['flextoolslib'] = flextoolslib

# Simple Reporter Class - mimics FLExTools FTReporter
# Outputs to console AND collects messages for structured response
class SimpleReporter:
    INFO = 0
    WARNING = 1
    ERROR = 2
    BLANK = 3
    TYPE_NAMES = ["INFO", "WARNING", "ERROR", "BLANK"]
    MAX_MESSAGES = 10000  # Prevent unbounded memory growth from verbose operations

    def __init__(self, max_messages=None):
        self.messages = []
        self.messageCounts = [0, 0, 0, 0]
        self.max_messages = max_messages or self.MAX_MESSAGES
        self.dropped_message_count = 0

    def _report(self, msg_type, msg, ref=None):
        if msg is not None and not isinstance(msg, str):
            msg = repr(msg)

        # Enforce message buffer limit (keep most recent messages)
        if len(self.messages) < self.max_messages:
            self.messages.append({
                "type": self.TYPE_NAMES[msg_type],
                "message": msg,
                "ref": ref
            })
        else:
            # Buffer full - drop oldest message and track it
            self.messages.pop(0)
            self.messages.append({
                "type": self.TYPE_NAMES[msg_type],
                "message": msg,
                "ref": ref
            })
            self.dropped_message_count += 1

        self.messageCounts[msg_type] += 1

        # Print to console for immediate feedback (transparent reporting)
        if msg_type == self.INFO:
            print("[INFO] {}".format(msg))
        elif msg_type == self.WARNING:
            print("[WARN] {}".format(msg))
        elif msg_type == self.ERROR:
            print("[ERROR] {}".format(msg))
        elif msg_type == self.BLANK:
            print()

        # Print reference if provided
        if ref:
            print("       {}".format(ref))

    def Info(self, msg, ref=None):
        self._report(self.INFO, msg, ref)

    def Warning(self, msg, ref=None):
        self._report(self.WARNING, msg, ref)

    def Error(self, msg, ref=None):
        self._report(self.ERROR, msg, ref)

    def Blank(self):
        self._report(self.BLANK, "", None)

    def Debug(self, msg, ref=None):
        """Debug messages (only printed if DEBUG env var set)"""
        if msg is not None and not isinstance(msg, str):
            msg = repr(msg)

        # Enforce message buffer limit for debug messages too
        if len(self.messages) < self.max_messages:
            self.messages.append({
                "type": "DEBUG",
                "message": msg,
                "ref": ref
            })
        else:
            # Buffer full - drop oldest message
            self.messages.pop(0)
            self.messages.append({
                "type": "DEBUG",
                "message": msg,
                "ref": ref
            })
            self.dropped_message_count += 1

        import os
        if os.getenv("DEBUG"):
            print("[DEBUG] {}".format(msg))
            if ref:
                print("        {}".format(ref))

    def ProgressStart(self, max_val, msg=None):
        pass

    def ProgressUpdate(self, value):
        pass

    def ProgressStop(self):
        pass

    def FileURL(self, fname):
        import pathlib
        return pathlib.Path(os.path.abspath(fname)).as_uri()


def run_module():
    result = {
        "success": False,
        "project": PROJECT_NAME,
        "write_enabled": WRITE_ENABLED,
        "messages": [],
        "summary": {},
        "error": None
    }

    project = None

    try:
        # API Mode-specific imports
        from flexlibs2 import FLExInitialize, FLExCleanup, FLExProject

        FLExInitialize()

        # Open project
        project = FLExProject()
        try:
            project.OpenProject(projectName=PROJECT_NAME, writeEnabled=WRITE_ENABLED)
        except Exception as e:
            result["error"] = "Failed to open project '{}': {}".format(PROJECT_NAME, str(e))
            return result

        # Create reporter
        report = SimpleReporter()

        # FLEx uses '***' as placeholder for empty/unset multilingual string values
        FLEX_EMPTY_PLACEHOLDER = "***"

        def is_empty_multistring(text):
            if text is None:
                return True
            if not isinstance(text, str):
                text = str(text)
            text = text.strip()
            return text == "" or text == FLEX_EMPTY_PLACEHOLDER

        def find_writing_system(project, query):
            """
            Find a writing system by name, tag, or partial match.

            Args:
                project: FLExProject instance
                query: String to search for (e.g., "pyn", "Pinyin", "zh-CN")

            Returns:
                Writing system handle if found, None otherwise
                Also searches display names and language tags

            Usage:
                ws_handle = find_writing_system(project, "pyn")
                if ws_handle:
                    text = project.WritingSystems.GetDisplayName(ws_handle)
                    print(f"Found: {text}")
            """
            try:
                query_lower = query.lower()
                all_ws = list(project.WritingSystems.GetAll())

                # Search for exact match first
                for ws in all_ws:
                    try:
                        display_name = project.WritingSystems.GetDisplayName(ws)
                        language_tag = project.WritingSystems.GetLanguageTag(ws)

                        if (query_lower == display_name.lower() or
                            query_lower == language_tag.lower()):
                            return ws
                    except:
                        pass

                # Then search for substring match
                for ws in all_ws:
                    try:
                        display_name = project.WritingSystems.GetDisplayName(ws)
                        language_tag = project.WritingSystems.GetLanguageTag(ws)

                        if (query_lower in display_name.lower() or
                            query_lower in language_tag.lower()):
                            return ws
                    except:
                        pass

                return None
            except Exception as e:
                return None

        def list_writing_systems(project):
            """
            List all available writing systems with their names and tags.

            Returns:
                List of dicts with 'name' and 'tag' keys

            Usage:
                for ws_info in list_writing_systems(project):
                    print(f"{ws_info['name']} ({ws_info['tag']})")
            """
            try:
                all_ws = list(project.WritingSystems.GetAll())
                result = []

                for ws in all_ws:
                    try:
                        display_name = project.WritingSystems.GetDisplayName(ws)
                        language_tag = project.WritingSystems.GetLanguageTag(ws)
                        result.append({
                            'name': display_name,
                            'tag': language_tag
                        })
                    except:
                        pass

                return result
            except Exception as e:
                return []

        # Execute the module code in a namespace
        module_namespace = {
            "__name__": "__flextools_module__",
            "__file__": "module.py",
            "is_empty_multistring": is_empty_multistring,
            "FLEX_EMPTY_PLACEHOLDER": FLEX_EMPTY_PLACEHOLDER,
            "find_writing_system": find_writing_system,
            "list_writing_systems": list_writing_systems,
            # Add project and report so bare code can use them directly
            "project": project,
            "report": report,
        }

        # Execute the module code to define Main and FlexToolsModule, or run bare code
        exec(MODULE_CODE, module_namespace)

        # Find and call Main function, or accept bare code
        if "Main" in module_namespace:
            module_namespace["Main"](project, report, WRITE_ENABLED)
        elif "FlexToolsModule" in module_namespace:
            module_namespace["FlexToolsModule"].Run(project, report, WRITE_ENABLED)
        # else: bare code already executed at line 978 during exec(MODULE_CODE, module_namespace)

        # Collect results
        result["success"] = True
        result["messages"] = report.messages
        result["summary"] = {
            "info_count": report.messageCounts[SimpleReporter.INFO],
            "warning_count": report.messageCounts[SimpleReporter.WARNING],
            "error_count": report.messageCounts[SimpleReporter.ERROR],
            "total_messages": len(report.messages)
        }
        # Include buffer overflow warning if messages were dropped
        if report.dropped_message_count > 0:
            result["summary"]["dropped_messages"] = report.dropped_message_count
            result["summary"]["note"] = "Output exceeded maximum buffer size. Most recent {} messages retained.".format(report.max_messages)

    except Exception as e:
        error_msg = str(e)
        if error_msg.startswith("RESULTS:"):
            result["success"] = True
            result["output"] = error_msg[8:].strip()
        else:
            result["error"] = "Execution error: {}\\n{}".format(error_msg, traceback.format_exc())

    finally:
        if project:
            try:
                project.CloseProject()
            except:
                pass
        try:
            FLExCleanup()
        except:
            pass

    return result


if __name__ == "__main__":
    result = run_module()
    print("===FLEXTOOLS_RESULT_JSON===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
'''

    # Escape the code for embedding in the script
    escaped_code = repr(code)

    # Note: API mode imports are now hardcoded in the template (flexlibs2)

    # Create the complete script with configuration
    full_script = '''# Configuration
PROJECT_NAME = {project_name}
WRITE_ENABLED = {write_enabled}
MODULE_CODE = {code}

{runner_script}
'''.format(
        project_name=repr(project_name),
        write_enabled=repr(write_enabled),
        code=escaped_code,
        runner_script=runner_script
    )

    # Write to temporary file
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(full_script)
            temp_script_path = f.name
    except Exception as e:
        err_msg = "Failed to create temporary script: {}".format(str(e))
        _log_operation_failure(error=err_msg, error_type=type(e).__name__)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": err_msg,
            "warnings": warnings
        }, indent=2))]

    try:
        # Determine if we need the write lock
        # Use index-based certification as primary, regex-based as fallback
        # Only lock if: write_enabled=True AND script is NOT certified readonly
        is_mutating_script = (not cert["is_certified_readonly"]) or cud_info["is_cud"]
        needs_lock = write_enabled and is_mutating_script

        if needs_lock:
            # Serialize CUD operations on same project to prevent database corruption
            write_lock = get_project_write_lock(project_name)
            async with write_lock:
                result = await run_script_async(
                    temp_script_path,
                    timeout_seconds=timeout_seconds
                )
        else:
            # No lock needed: read-only or metadata-only operations
            result = await run_script_async(
                temp_script_path,
                timeout_seconds=timeout_seconds
            )

        stdout = result["stdout"]
        stderr = result["stderr"]

        # Handle timeout case
        if result["timeout"]:
            err_msg = f"Execution timeout: script exceeded {timeout_seconds} seconds"
            _log_operation_failure(error=err_msg, error_type="Timeout", stderr=stderr)
            return [TextContent(type="text", text=json.dumps({
                "success": False,
                "error": err_msg,
                "warnings": warnings
            }, indent=2))]

        # Parse the JSON result from stdout
        if "===FLEXTOOLS_RESULT_JSON===" in stdout:
            json_start = stdout.index("===FLEXTOOLS_RESULT_JSON===") + len("===FLEXTOOLS_RESULT_JSON===")
            json_str = stdout[json_start:].strip()
            try:
                execution_result = json.loads(json_str)
            except json.JSONDecodeError as e:
                execution_result = {
                    "success": False,
                    "error": "Failed to parse result JSON: {}".format(str(e)),
                    "error_type": "JSONDecodeError",
                    "raw_output": stdout
                }
        else:
            execution_result = {
                "success": False,
                "error": "No result marker found in output",
                "error_type": "NoResultMarker",
                "raw_output": stdout,
                "stderr": stderr
            }

        # Add warnings, metadata, and optionally the full module code for learning
        execution_result["warnings"] = warnings
        execution_result["exit_code"] = result["returncode"]
        if stderr and not execution_result.get("error"):
            execution_result["stderr"] = stderr
        if args.get("show_code", True):
            execution_result["code"] = code

        # Include write certification result
        execution_result["write_certification"] = {
            "is_certified_readonly": cert["is_certified_readonly"],
            "confidence": cert["confidence"],
            "mutating_calls_detected": [m for m in cert["mutating_calls"] if m.get("is_mutating")],
        }

        # Detect polymorphic attribute errors and suggest resolve_property
        if execution_result.get("error") and "has no attribute" in execution_result.get("error", ""):
            polymorphic_info = detect_polymorphic_error(execution_result["error"])
            if polymorphic_info["is_polymorphic_error"]:
                execution_result["polymorphic_error_detected"] = True
                execution_result["error_type"] = "PolymorphicAttributeError"
                execution_result["object_type"] = polymorphic_info["object_type"]
                execution_result["property_name"] = polymorphic_info["property_name"]
                execution_result["help"] = polymorphic_info["suggestion"]
            else:
                # Try wrapper-API name suggestions (project.LexEntries -> project.LexEntry,
                # GetPOS -> GetPartOfSpeech, etc.)
                hint = detect_unknown_attribute_error(execution_result["error"], get_api_index())
                if hint.get("has_suggestion"):
                    execution_result["did_you_mean"] = hint["did_you_mean"]
                    execution_result["help"] = hint["suggestion"]

        # Record API usage patterns for learning
        from ..kernel import get_pattern_tracker
        tracker = get_pattern_tracker()
        if tracker:
            error_msg = execution_result.get("error")
            error_type = execution_result.get("error_type")
            tracker.record_operation(code, execution_result.get("success", False), error_msg, error_type)

        # Extract message counts from execution result
        summary = execution_result.get("summary", {})
        info_count = summary.get("info_count", 0)
        warning_count = summary.get("warning_count", 0)
        error_count = summary.get("error_count", 0)

        # Log operation completion with rich formatting
        if execution_result.get("success"):
            get_operations_logger().info("[OK] Operation completed successfully")
            get_operations_logger().info(
                f"Messages: {info_count} info, {warning_count} warnings, {error_count} errors"
            )
            get_operations_logger().info("=== Operation End ===")
        else:
            _log_operation_failure(
                error=execution_result.get("error"),
                error_type=execution_result.get("error_type"),
                stderr=execution_result.get("stderr") or stderr,
                info_count=info_count,
                warning_count=warning_count,
                error_count=error_count,
            )

        return [TextContent(type="text", text=json.dumps(execution_result, indent=2, ensure_ascii=False))]

    except subprocess.TimeoutExpired:
        err_msg = "Execution timed out after {} seconds".format(timeout_seconds)
        _log_operation_failure(error=err_msg, error_type="TimeoutExpired")
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": err_msg,
            "warnings": warnings
        }, indent=2))]

    except Exception as e:
        err_msg = "Subprocess execution error: {}".format(str(e))
        _log_operation_failure(error=err_msg, error_type=type(e).__name__)
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": err_msg,
            "warnings": warnings
        }, indent=2))]

    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_script_path)
        except:
            pass


async def handle_get_operation_logs(args: dict) -> list[TextContent]:
    """View operation logs and pattern recommendations."""
    log_lines = args.get("log_lines", 50)
    include_patterns = args.get("include_patterns", True)
    errors_only = args.get("errors_only", False)

    result = {
        "log_file": str(get_log_dir() / "operations.log"),
        "patterns_file": str(get_log_dir() / "patterns.json"),
        "recent_logs": [],
        "recommendations": None
    }

    # Read recent log entries
    log_file = get_log_dir() / "operations.log"
    if log_file.exists():
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Filter to errors only if requested
            if errors_only:
                lines = [l for l in lines if '| ERROR' in l or '| FAIL' in l or '[FAIL]' in l]

            # Get last N lines
            recent = lines[-log_lines:] if len(lines) > log_lines else lines
            result["recent_logs"] = [line.rstrip() for line in recent]
            result["total_log_lines"] = len(lines)
        except Exception as e:
            result["log_error"] = str(e)
    else:
        result["recent_logs"] = ["(No logs yet - run some operations first)"]

    # Include pattern analysis
    if include_patterns:
        tracker = get_pattern_tracker()
        if tracker:
            tracker.load()
            recommendations = tracker.get_recommendations()

            result["recommendations"] = {
                "preferred_patterns": recommendations.get("preferred_patterns", [])[:10],
                "patterns_to_avoid": recommendations.get("patterns_to_avoid", [])[:10],
                "common_errors_needing_fix": recommendations.get("common_errors_needing_fix", [])[:10]
            }

            # Add summary statistics
            api_patterns = tracker.patterns.get("api_patterns", {})
            total_operations = sum(
                p["success_count"] + p["failure_count"]
                for p in api_patterns.values()
            )
            total_successes = sum(p["success_count"] for p in api_patterns.values())
            total_failures = sum(p["failure_count"] for p in api_patterns.values())

            result["statistics"] = {
                "total_operations": total_operations,
                "total_successes": total_successes,
                "total_failures": total_failures,
                "success_rate": round(total_successes / total_operations * 100, 1) if total_operations > 0 else 0,
                "unique_api_patterns": len(api_patterns),
                "unique_error_patterns": len(tracker.patterns.get("error_patterns", {}))
            }
        else:
            result["recommendations"] = {}
            result["statistics"] = {}

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
