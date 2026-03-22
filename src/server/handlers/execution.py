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
from pathlib import Path
from typing import List, Dict, Any, Tuple
from mcp.types import TextContent

# Import shared state from kernel
try:
    from ..kernel import session_state, get_log_dir, api_index, operations_logger, pattern_tracker
    from ..session import SessionState
    if not isinstance(session_state, SessionState):
        session_state = SessionState()
except ImportError:
    from src.server.kernel import session_state, get_log_dir, api_index, operations_logger, pattern_tracker
    from src.server.session import SessionState

# Import helper functions from validators module
try:
    from ..validators import (
        detect_cud_operations,
        detect_module_structure,
        detect_polymorphic_error,
        detect_undefined_variables,
        detect_missing_operations_imports,
        detect_wrong_library_imports,
        check_output_mechanism,
        format_cud_warning
    )
except ImportError:
    from src.server.validators import (
        detect_cud_operations,
        detect_module_structure,
        detect_polymorphic_error,
        detect_undefined_variables,
        detect_missing_operations_imports,
        detect_wrong_library_imports,
        check_output_mechanism,
        format_cud_warning
    )

# Import response utilities
try:
    from ...response_utils import build_response_with_context
except (ImportError, ValueError):
    # Fallback for different import contexts
    from src.response_utils import build_response_with_context


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
            # Check version is reasonable
            if not hasattr(flexlibs2, '__version__'):
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


def _get_api_mode_imports(api_mode: str) -> Tuple[str, dict]:
    """Generate imports and namespace dict for a given API mode.

    Args:
        api_mode: One of 'flexlibs_stable', 'flexlibs2', 'liblcm'

    Returns:
        (imports_code, namespace_dict_entries)

    Raises:
        ValueError: If API mode is invalid or required libraries are not installed
    """
    # Gate #1: Validate API mode is valid
    is_valid, error_msg = _validate_api_mode(api_mode)
    if not is_valid:
        raise ValueError(f"API mode validation failed: {error_msg}")
    if api_mode == "flexlibs_stable":
        imports = """from flexlibs import FLExInitialize, FLExCleanup, FLExProject"""
        namespace_entries = {}

    elif api_mode == "flexlibs2":
        imports = """from flexlibs2 import FLExInitialize, FLExCleanup, FLExProject"""
        namespace_entries = {}

    elif api_mode == "liblcm":
        imports = """import clr
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
"""
        namespace_entries = {}

    else:
        raise ValueError(f"Unknown API mode: {api_mode}")

    return imports, namespace_entries


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
        return [TextContent(type="text", text=json.dumps({
            "status": "needs_input",
            "environment": env_info,
            "provided": provided,
            "required_questions": required_questions,
            "optional_questions": optional_questions,
            "questions": questions,  # Combined for convenience
            "instructions": "Please ask the user these questions and call start_module again with the answers. Optional questions can be skipped."
        }, indent=2))]

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

    return [TextContent(type="text", text=json.dumps({
        "status": "complete",
        "environment": env_info,
        "configuration": config,
        "template": template,
        "api_guidance": {
            "mode": api_target,
            "search_mode": api_info.get("search_mode", api_target),
            "search_reminder": api_info.get("search_reminder", ""),
            "tips": api_info.get("tips", [])
        },
        "next_steps": next_steps,
        "testing_reminder": "Always test FlexTools modules on a backup or sample project first!" if not test_project else None
    }, indent=2))]


async def handle_run_module(args: dict) -> list[TextContent]:
    """Execute a FlexTools module against a FieldWorks project."""
    module_code = args["module_code"]
    # Use session state as fallback for project and write settings
    project_name = args.get("project_name", session_state.get_project())
    write_enabled = args.get("write_enabled", session_state.is_write_enabled())
    api_mode = session_state.get_mode()

    # Validate project_name is available
    if not project_name:
        return [TextContent(type="text", text=json.dumps({
            "error": "project_name required",
            "message": "No project specified. Either set project_name in start() or provide it directly.",
            "session": session_state.summary()
        }, indent=2))]

    # Check for CUD operations requiring confirmation
    confirmed = args.get("confirmed", False)
    cud_info = detect_cud_operations(module_code)

    if cud_info["is_cud"] and not confirmed:
        return [TextContent(type="text", text=json.dumps(
            format_cud_warning(cud_info, write_enabled), indent=2
        ))]

    # Validate module structure - must be proper FlexTools module format
    structure_check = detect_module_structure(module_code)
    if not structure_check["is_valid_module"]:
        return [TextContent(type="text", text=json.dumps({
            "error": "invalid_module_format",
            "message": "Code is not in FlexTools module format. Call get_module_template first to get the correct boilerplate.",
            "missing_elements": structure_check["missing_elements"],
            "next_step": "Call get_module_template with module_name and synopsis to get the proper template, then fill in your logic inside the Main() function."
        }, indent=2))]

    # Require API discovery before executing module code
    skip_api_check = args.get("skip_api_check", False)
    if not skip_api_check and len(session_state.get_discovered_apis()) == 0:
        return [TextContent(type="text", text=json.dumps({
            "error": "API discovery required",
            "message": "No APIs have been discovered yet. Before running modules, you MUST use one of these tools first:\n"
                      "1. start(task='...') - discovers relevant APIs automatically\n"
                      "2. get_object_api(object_type='...') - get API for specific object\n"
                      "3. search_by_capability(query='...') - search for APIs by description\n\n"
                      "This prevents using incorrect/hallucinated method names like 'project.Wordforms' or 'report.add()'.",
            "hint": "Call get_object_api() for each object/operation you use in your module (FLExProject, LexEntryOperations, etc.), then write code using those discovered APIs.",
            "session": session_state.summary()
        }, indent=2))]

    # Check output mechanism - modules must use report.Info(), not print()
    output_check = check_output_mechanism(module_code, "module")
    if not output_check["uses_correct_mechanism"]:
        return [TextContent(type="text", text=json.dumps({
            "error": "invalid_output_mechanism",
            "message": output_check["message"],
            "has_output": output_check["has_output"],
            "detected_mechanism": output_check["mechanism_type"],
            "guidance": "In FlexTools modules, use report.Info(message) to output results. The report object is provided to Main() for this purpose."
        }, indent=2))]

    # Check for undefined variables that indicate hallucinated/internal names
    undefined_check = detect_undefined_variables(module_code)
    if undefined_check["has_undefined"]:
        return [TextContent(type="text", text=json.dumps({
            "error": "undefined_variables",
            "message": undefined_check["suggestion"],
            "undefined_vars": undefined_check["undefined_vars"],
            "guidance": "All variables must be either: (1) imported from a module, (2) defined in your code, or (3) provided by FlexTools (project, report, modifyAllowed). Do not use internal MCP variable names."
        }, indent=2))]

    # Check for missing Operations class imports
    missing_ops_check = detect_missing_operations_imports(module_code, api_mode)
    if missing_ops_check["has_missing"]:
        return [TextContent(type="text", text=json.dumps({
            "error": "missing_imports",
            "message": missing_ops_check["suggestion"],
            "missing_imports": missing_ops_check["missing_imports"],
            "api_mode": api_mode,
            "guidance": "Add the import statement shown above to the top of your code."
        }, indent=2))]

    # Check for wrong library imports
    wrong_imports_check = detect_wrong_library_imports(module_code, api_mode)
    if wrong_imports_check["has_wrong_imports"]:
        return [TextContent(type="text", text=json.dumps({
            "error": "wrong_library_imports",
            "message": wrong_imports_check["suggestion"],
            "wrong_imports": wrong_imports_check["wrong_imports"],
            "api_mode": api_mode,
            "guidance": f"Ensure all imports match your selected API mode. You selected '{api_mode}' mode."
        }, indent=2))]

    timeout_seconds = args.get("timeout_seconds", 300)

    # Get API mode-specific imports
    api_imports, _ = _get_api_mode_imports(api_mode)
    # Add indentation for embedding in runner_script (uses .replace(), not .format())
    import textwrap
    api_imports_indented = textwrap.indent(api_imports, '        ')

    # Log module start
    operations_logger.info(f"=== Module Start ===")
    operations_logger.info(f"Project: {project_name}")
    operations_logger.info(f"Write enabled: {write_enabled}")
    operations_logger.info(f"API mode: {api_mode}")
    operations_logger.debug(f"Module code length: {len(module_code)} bytes")

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
    # (Large script template - see original server.py lines 3766-3966 for full details)
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

# Simple Reporter Class
class SimpleReporter:
    INFO = 0
    WARNING = 1
    ERROR = 2
    BLANK = 3
    TYPE_NAMES = ["INFO", "WARNING", "ERROR", "BLANK"]

    def __init__(self):
        self.messages = []
        self.messageCounts = [0, 0, 0, 0]

    def _report(self, msg_type, msg, ref=None):
        if msg is not None and not isinstance(msg, str):
            msg = repr(msg)
        self.messages.append({
            "type": self.TYPE_NAMES[msg_type],
            "message": msg,
            "ref": ref
        })
        self.messageCounts[msg_type] += 1

    def Info(self, msg, ref=None):
        self._report(self.INFO, msg, ref)

    def Warning(self, msg, ref=None):
        self._report(self.WARNING, msg, ref)

    def Error(self, msg, ref=None):
        self._report(self.ERROR, msg, ref)

    def Blank(self):
        self._report(self.BLANK, "", None)

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
        {{API_MODE_IMPORTS}}

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

        # Execute the module code in a namespace
        module_namespace = {
            "__name__": "__flextools_module__",
            "__file__": "module.py",
            "is_empty_multistring": is_empty_multistring,
            "FLEX_EMPTY_PLACEHOLDER": FLEX_EMPTY_PLACEHOLDER,
        }

        # Execute the module code to define Main and FlexToolsModule
        exec(MODULE_CODE, module_namespace)

        # Find and call Main function
        if "Main" in module_namespace:
            module_namespace["Main"](project, report, WRITE_ENABLED)
        elif "FlexToolsModule" in module_namespace:
            module_namespace["FlexToolsModule"].Run(project, report, WRITE_ENABLED)
        else:
            result["error"] = "Module code must define either 'Main' function or 'FlexToolsModule'"
            return result

        # Collect results
        result["success"] = True
        result["messages"] = report.messages
        result["summary"] = {
            "info_count": report.messageCounts[SimpleReporter.INFO],
            "warning_count": report.messageCounts[SimpleReporter.WARNING],
            "error_count": report.messageCounts[SimpleReporter.ERROR],
            "total_messages": len(report.messages)
        }

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

    # Escape the module code for embedding in the script
    escaped_module_code = repr(module_code)

    # Replace API mode imports in the runner script
    runner_script = runner_script.replace('{{API_MODE_IMPORTS}}', api_imports_indented)

    # Create the complete script with configuration
    full_script = '''# Configuration
PROJECT_NAME = {project_name}
WRITE_ENABLED = {write_enabled}
MODULE_CODE = {module_code}

{runner_script}
'''.format(
        project_name=repr(project_name),
        write_enabled=repr(write_enabled),
        module_code=escaped_module_code,
        runner_script=runner_script
    )

    # Write to temporary file
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(full_script)
            temp_script_path = f.name
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Failed to create temporary script: {}".format(str(e)),
            "warnings": warnings
        }, indent=2))]

    try:
        # Run the script in a subprocess
        result = subprocess.run(
            [sys.executable, temp_script_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding='utf-8',
            stdin=subprocess.DEVNULL
        )

        stdout = result.stdout
        stderr = result.stderr

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
                    "raw_output": stdout
                }
        else:
            execution_result = {
                "success": False,
                "error": "No result marker found in output",
                "raw_output": stdout,
                "stderr": stderr
            }

        # Add warnings, metadata, and optionally the full module code for learning
        execution_result["warnings"] = warnings
        execution_result["exit_code"] = result.returncode
        if stderr and not execution_result.get("error"):
            execution_result["stderr"] = stderr
        if args.get("show_code", True):
            execution_result["module_code"] = module_code

        # Detect polymorphic attribute errors and suggest resolve_property
        if execution_result.get("error") and "has no attribute" in execution_result.get("error", ""):
            polymorphic_info = detect_polymorphic_error(execution_result["error"])
            if polymorphic_info["is_polymorphic_error"]:
                execution_result["polymorphic_error_detected"] = True
                execution_result["error_type"] = "PolymorphicAttributeError"
                execution_result["object_type"] = polymorphic_info["object_type"]
                execution_result["property_name"] = polymorphic_info["property_name"]
                execution_result["help"] = polymorphic_info["suggestion"]

        return [TextContent(type="text", text=json.dumps(execution_result, indent=2, ensure_ascii=False))]

    except subprocess.TimeoutExpired:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Execution timed out after {} seconds".format(timeout_seconds),
            "warnings": warnings
        }, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Subprocess execution error: {}".format(str(e)),
            "warnings": warnings
        }, indent=2))]

    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_script_path)
        except:
            pass


async def handle_run_operation(args: dict) -> list[TextContent]:
    """Execute FlexLibs2 operations directly without module boilerplate."""
    operations = args["operations"]
    # Use session state as fallback for project and write settings
    project_name = args.get("project_name", session_state.get_project())
    write_enabled = args.get("write_enabled", session_state.is_write_enabled())

    # Validate project_name is available
    if not project_name:
        return [TextContent(type="text", text=json.dumps({
            "error": "project_name required",
            "message": "No project specified. Either set project_name in start() or provide it directly.",
            "session": session_state.summary()
        }, indent=2))]

    # Check if API discovery was performed
    skip_api_check = args.get("skip_api_check", False)
    if not skip_api_check and len(session_state.get_discovered_apis()) == 0:
        return [TextContent(type="text", text=json.dumps({
            "error": "API discovery required",
            "message": "No APIs have been discovered yet. Before running operations, you MUST use one of these tools first:\n"
                      "1. start(task='...') - discovers relevant APIs automatically\n"
                      "2. get_object_api(object_type='...') - get API for specific object\n"
                      "3. search_by_capability(query='...') - search for APIs by description\n\n"
                      "This prevents using incorrect/hallucinated method names.",
            "hint": "Call start() or search_by_capability() first, then use the discovered methods in your code.",
            "session": session_state.summary()
        }, indent=2))]

    # Check for CUD operations requiring confirmation
    confirmed = args.get("confirmed", False)
    cud_info = detect_cud_operations(operations)

    if cud_info["is_cud"] and not confirmed:
        return [TextContent(type="text", text=json.dumps(
            format_cud_warning(cud_info, write_enabled), indent=2
        ))]

    # Get API mode early for validation
    api_mode = session_state.get_mode()

    # Check output mechanism - operations must use print(), not report.Info()
    output_check = check_output_mechanism(operations, "operation")
    if not output_check["uses_correct_mechanism"]:
        return [TextContent(type="text", text=json.dumps({
            "error": "invalid_output_mechanism",
            "message": output_check["message"],
            "has_output": output_check["has_output"],
            "detected_mechanism": output_check["mechanism_type"],
            "guidance": "In operations code, use print(message) to output results. The report object is only available in FlexTools modules."
        }, indent=2))]

    # Check for undefined variables that indicate hallucinated/internal names
    undefined_check = detect_undefined_variables(operations)
    if undefined_check["has_undefined"]:
        return [TextContent(type="text", text=json.dumps({
            "error": "undefined_variables",
            "message": undefined_check["suggestion"],
            "undefined_vars": undefined_check["undefined_vars"],
            "guidance": "All classes/modules must be imported first. Use 'from flexlibs2 import ClassName' or 'import module'. Do not use internal MCP variable names like API_MODE_IMPORTS."
        }, indent=2))]

    # Check for missing Operations class imports
    missing_ops_check = detect_missing_operations_imports(operations, api_mode)
    if missing_ops_check["has_missing"]:
        return [TextContent(type="text", text=json.dumps({
            "error": "missing_imports",
            "message": missing_ops_check["suggestion"],
            "missing_imports": missing_ops_check["missing_imports"],
            "api_mode": api_mode,
            "guidance": "Add the import statement shown above to the top of your code."
        }, indent=2))]

    # Check for wrong library imports
    wrong_imports_check = detect_wrong_library_imports(operations, api_mode)
    if wrong_imports_check["has_wrong_imports"]:
        return [TextContent(type="text", text=json.dumps({
            "error": "wrong_library_imports",
            "message": wrong_imports_check["suggestion"],
            "wrong_imports": wrong_imports_check["wrong_imports"],
            "api_mode": api_mode,
            "guidance": f"Ensure all imports match your selected API mode. You selected '{api_mode}' mode."
        }, indent=2))]

    timeout_seconds = args.get("timeout_seconds", 120)

    # Log operation start
    operations_logger.info(f"=== Operation Start ===")
    operations_logger.info(f"Project: {project_name}")
    operations_logger.info(f"Write enabled: {write_enabled}")
    operations_logger.info(f"API mode: {api_mode}")
    operations_logger.debug(f"Code:\n{operations}")

    # Build warnings
    warnings = []
    if write_enabled:
        warnings.extend([
            "*** WRITE MODE ENABLED ***",
            "Changes WILL be made to the database!",
            ""
        ])
    else:
        warnings.extend([
            "Running in READ-ONLY mode (dry-run)",
            "No changes will be made to the database.",
            ""
        ])

    # Get API mode-specific imports
    api_imports, api_namespace = _get_api_mode_imports(api_mode)

    # Create the runner script template
    runner_script = '''# -*- coding: utf-8 -*-
"""FlexTools Operation Runner - Generated by FlexToolsMCP"""
import sys
import json
import traceback
import io

# Force UTF-8 stdout on Windows
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def safe_str(obj):
    """Safely convert .NET or Python object to UTF-8 string."""
    if obj is None:
        return ""
    try:
        s = str(obj)
        return s.encode('utf-8', errors='replace').decode('utf-8')
    except Exception:
        try:
            return repr(obj)
        except Exception:
            return "(encoding error)"


# FLEx uses '***' as placeholder for empty/unset multilingual string values
FLEX_EMPTY_PLACEHOLDER = "***"


def is_empty_multistring(text):
    """Check if a FLEx multilingual string value is empty."""
    if text is None:
        return True
    if not isinstance(text, str):
        text = str(text)
    text = text.strip()
    return text == "" or text == FLEX_EMPTY_PLACEHOLDER

# Configuration
PROJECT_NAME = {project_name}
WRITE_ENABLED = {write_enabled}
OPERATIONS = {operations}

# Simple Reporter Class
class SimpleReporter:
    INFO = 0
    WARNING = 1
    ERROR = 2
    BLANK = 3
    TYPE_NAMES = ["INFO", "WARNING", "ERROR", "BLANK"]

    def __init__(self):
        self.messages = []
        self.messageCounts = [0, 0, 0, 0]

    def _report(self, msg_type, msg, ref=None):
        if msg is not None and not isinstance(msg, str):
            msg = repr(msg)
        self.messages.append({{
            "type": self.TYPE_NAMES[msg_type],
            "message": msg,
            "ref": ref
        }})
        self.messageCounts[msg_type] += 1

    def Info(self, msg, ref=None):
        self._report(self.INFO, msg, ref)

    def Warning(self, msg, ref=None):
        self._report(self.WARNING, msg, ref)

    def Error(self, msg, ref=None):
        self._report(self.ERROR, msg, ref)

    def Blank(self):
        self._report(self.BLANK, "", None)


# API Mode-specific imports
{API_MODE_IMPORTS}


def run_operation():
    result = {{
        "success": False,
        "project": PROJECT_NAME,
        "write_enabled": WRITE_ENABLED,
        "messages": [],
        "summary": {{}},
        "error": None
    }}

    project = None
    report = SimpleReporter()

    try:
        FLExInitialize()

        # Open project
        project = FLExProject()
        try:
            project.OpenProject(projectName=PROJECT_NAME, writeEnabled=WRITE_ENABLED)
        except Exception as e:
            result["error"] = "Failed to open project '{{}}': {{}}".format(PROJECT_NAME, str(e))
            return result

        # Make variables available to the operations code
        write_enabled = WRITE_ENABLED

        # Build execution namespace
        exec_namespace = {{
            "project": project,
            "report": report,
            "write_enabled": write_enabled,
            "safe_str": safe_str,
            "is_empty_multistring": is_empty_multistring,
            "FLEX_EMPTY_PLACEHOLDER": FLEX_EMPTY_PLACEHOLDER,
        }}

        # Add API-specific classes if available (FlexLibs2 mode)
        try:
            exec_namespace.update({{
                "FP_FileLockedError": FP_FileLockedError,
                "FP_FileNotFoundError": FP_FileNotFoundError,
                "FP_MigrationRequired": FP_MigrationRequired,
                "FP_NullParameterError": FP_NullParameterError,
                "FP_ParameterError": FP_ParameterError,
                "FP_ProjectError": FP_ProjectError,
                "FP_ReadOnlyError": FP_ReadOnlyError,
                "FP_RuntimeError": FP_RuntimeError,
                "FP_WritingSystemError": FP_WritingSystemError,
                "FP_AccessViolationException": FP_AccessViolationException,
                "FP_ArgumentException": FP_ArgumentException,
                "FP_IndexOutOfRangeException": FP_IndexOutOfRangeException,
                "FP_InvalidOperationException": FP_InvalidOperationException,
                "FP_InvalidCastException": FP_InvalidCastException,
                "FP_KeyNotFoundException": FP_KeyNotFoundException,
                "FP_NullReferenceException": FP_NullReferenceException,
                "FP_OperationCanceledException": FP_OperationCanceledException,
                "FP_TimeoutException": FP_TimeoutException,
                "POSOperations": POSOperations,
                "PhonemeOperations": PhonemeOperations,
                "NaturalClassOperations": NaturalClassOperations,
                "EnvironmentOperations": EnvironmentOperations,
                "MorphRuleOperations": MorphRuleOperations,
                "InflectionFeatureOperations": InflectionFeatureOperations,
                "GramCatOperations": GramCatOperations,
                "PhonologicalRuleOperations": PhonologicalRuleOperations,
                "LexEntryOperations": LexEntryOperations,
                "LexSenseOperations": LexSenseOperations,
                "ExampleOperations": ExampleOperations,
                "LexReferenceOperations": LexReferenceOperations,
                "VariantOperations": VariantOperations,
                "PronunciationOperations": PronunciationOperations,
                "SemanticDomainOperations": SemanticDomainOperations,
                "ReversalOperations": ReversalOperations,
                "EtymologyOperations": EtymologyOperations,
                "AllomorphOperations": AllomorphOperations,
                "TextOperations": TextOperations,
                "WordformOperations": WordformOperations,
                "WfiAnalysisOperations": WfiAnalysisOperations,
                "ParagraphOperations": ParagraphOperations,
                "SegmentOperations": SegmentOperations,
                "WfiGlossOperations": WfiGlossOperations,
                "WfiMorphBundleOperations": WfiMorphBundleOperations,
                "MediaOperations": MediaOperations,
                "FilterOperations": FilterOperations,
                "DiscourseOperations": DiscourseOperations,
                "NoteOperations": NoteOperations,
                "PersonOperations": PersonOperations,
                "LocationOperations": LocationOperations,
                "AnthropologyOperations": AnthropologyOperations,
                "DataNotebookOperations": DataNotebookOperations,
                "PublicationOperations": PublicationOperations,
                "AgentOperations": AgentOperations,
                "ConfidenceOperations": ConfidenceOperations,
                "OverlayOperations": OverlayOperations,
                "TranslationTypeOperations": TranslationTypeOperations,
                "PossibilityListOperations": PossibilityListOperations,
                "WritingSystemOperations": WritingSystemOperations,
                "ProjectSettingsOperations": ProjectSettingsOperations,
                "AnnotationDefOperations": AnnotationDefOperations,
                "CheckOperations": CheckOperations,
                "CustomFieldOperations": CustomFieldOperations,
            }})
        except NameError:
            pass

        # Execute the operations
        exec(OPERATIONS, exec_namespace)

        # Collect results
        result["success"] = True
        result["messages"] = report.messages
        result["summary"] = {{
            "info_count": report.messageCounts[SimpleReporter.INFO],
            "warning_count": report.messageCounts[SimpleReporter.WARNING],
            "error_count": report.messageCounts[SimpleReporter.ERROR],
            "total_messages": len(report.messages)
        }}

    except Exception as e:
        result["error"] = "Execution error: {{}}\\n{{}}".format(str(e), traceback.format_exc())
        result["messages"] = report.messages

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
    result = run_operation()
    print("===FLEXTOOLS_RESULT_JSON===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
'''.format(
        project_name=repr(project_name),
        write_enabled=repr(write_enabled),
        operations=repr(operations),
        API_MODE_IMPORTS=api_imports
    )

    # Write to temporary file
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(runner_script)
            temp_script_path = f.name
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Failed to create temporary script: {}".format(str(e)),
            "warnings": warnings
        }, indent=2))]

    try:
        # Create environment with UTF-8 encoding for Windows compatibility
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'

        # Run the script in a subprocess
        result = subprocess.run(
            [sys.executable, temp_script_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding='utf-8',
            errors='replace',
            stdin=subprocess.DEVNULL,
            env=env
        )

        stdout = result.stdout
        stderr = result.stderr

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
                    "raw_output": stdout
                }
        else:
            execution_result = {
                "success": False,
                "error": "No result marker found in output",
                "stdout": stdout,
                "stderr": stderr
            }

        # Add warnings, return code, and optionally the executed code for learning
        execution_result["warnings"] = warnings
        execution_result["exit_code"] = result.returncode
        if args.get("show_code", True):
            execution_result["code_executed"] = operations

        # Detect polymorphic attribute errors and suggest resolve_property
        if execution_result.get("error") and "has no attribute" in execution_result.get("error", ""):
            polymorphic_info = detect_polymorphic_error(execution_result["error"])
            if polymorphic_info["is_polymorphic_error"]:
                execution_result["polymorphic_error_detected"] = True
                execution_result["error_type"] = "PolymorphicAttributeError"
                execution_result["object_type"] = polymorphic_info["object_type"]
                execution_result["property_name"] = polymorphic_info["property_name"]
                execution_result["help"] = polymorphic_info["suggestion"]

        # Log operation result
        if execution_result.get("success"):
            operations_logger.info(f"[OK] Operation completed successfully")
            summary = execution_result.get("summary", {})
            operations_logger.info(f"Messages: {summary.get('info_count', 0)} info, {summary.get('warning_count', 0)} warnings, {summary.get('error_count', 0)} errors")
            pattern_tracker.record_operation(operations, success=True)
        else:
            error_msg = execution_result.get("error", "Unknown error")
            operations_logger.error(f"[FAIL] Operation failed: {error_msg}")
            pattern_tracker.record_operation(operations, success=False, error_msg=error_msg)

        operations_logger.info(f"=== Operation End ===\n")

        # Include pattern recommendations
        recommendations = pattern_tracker.get_recommendations()
        if recommendations.get("patterns_to_avoid"):
            execution_result["pattern_warnings"] = [
                p for p in recommendations["patterns_to_avoid"]
                if any(api in operations for api in [p["pattern"].split(".")[-1]])
            ][:2]

        # Add session context
        execution_result = build_response_with_context(execution_result, include_session=True)

        return [TextContent(type="text", text=json.dumps(execution_result, indent=2, default=str))]

    except subprocess.TimeoutExpired:
        operations_logger.error(f"[FAIL] Operation timed out after {timeout_seconds} seconds")
        pattern_tracker.record_operation(operations, success=False, error_msg="Timeout")
        operations_logger.info(f"=== Operation End ===\n")
        timeout_result = {
            "success": False,
            "error": "Execution timed out after {} seconds".format(timeout_seconds),
            "warnings": warnings
        }
        timeout_result = build_response_with_context(timeout_result, include_session=True)
        return [TextContent(type="text", text=json.dumps(timeout_result, indent=2))]

    except Exception as e:
        error_msg = str(e)
        operations_logger.error(f"[FAIL] Subprocess error: {error_msg}")
        pattern_tracker.record_operation(operations, success=False, error_msg=error_msg)
        operations_logger.info(f"=== Operation End ===\n")
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Subprocess execution error: {}".format(error_msg),
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
        pattern_tracker.load()
        recommendations = pattern_tracker.get_recommendations()

        result["recommendations"] = {
            "preferred_patterns": recommendations.get("preferred_patterns", [])[:10],
            "patterns_to_avoid": recommendations.get("patterns_to_avoid", [])[:10],
            "common_errors_needing_fix": recommendations.get("common_errors_needing_fix", [])[:10]
        }

        # Add summary statistics
        api_patterns = pattern_tracker.patterns.get("api_patterns", {})
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
            "unique_error_patterns": len(pattern_tracker.patterns.get("error_patterns", {}))
        }

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
