#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlexLibs 2.0 Analyzer

Analyzes the FlexLibs 2.0 Python source code to extract API structure,
including all operations classes, their methods, and mappings to LibLCM.

Output follows the unified-api-doc/2.0 schema for consistency with
existing FLExTools-Generator extractions.
"""

import ast
import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple


def extract_docstring(node) -> str:
    """Extract docstring from a node if it exists."""
    if (hasattr(node, 'body') and node.body and
        isinstance(node.body[0], ast.Expr) and
        isinstance(node.body[0].value, ast.Constant) and
        isinstance(node.body[0].value.value, str)):
        return node.body[0].value.value.strip()
    elif (hasattr(node, 'body') and node.body and
          isinstance(node.body[0], ast.Expr) and
          isinstance(node.body[0].value, ast.Str)):
        return node.body[0].value.s.strip()
    return ""


def parse_docstring(docstring: str) -> Dict[str, Any]:
    """Parse a docstring to extract Args, Returns, Raises, Example sections."""
    result = {
        "summary": "",
        "description": "",
        "args": {},
        "returns": "",
        "return_type": "",
        "raises": [],
        "example": ""
    }

    if not docstring:
        return result

    lines = docstring.split('\n')
    current_section = "description"
    current_arg = None

    for line in lines:
        stripped = line.strip()

        # Check for section headers
        if stripped.startswith("Args:"):
            current_section = "args"
            continue
        elif stripped.startswith("Returns:") or stripped.startswith("Yields:"):
            current_section = "returns"
            continue
        elif stripped.startswith("Raises:"):
            current_section = "raises"
            continue
        elif stripped.startswith("Example:"):
            current_section = "example"
            continue
        elif stripped.startswith("Note:") or stripped.startswith("Notes:"):
            current_section = "notes"
            continue

        # Process content based on section
        if current_section == "description":
            if result["description"]:
                result["description"] += "\n" + stripped
            else:
                result["description"] = stripped
        elif current_section == "args":
            # Parse argument: "arg_name (type): description" or "arg_name: description"
            arg_match = re.match(r'^(\w+)(?:\s*\(([^)]+)\))?:\s*(.*)$', stripped)
            if arg_match:
                arg_name = arg_match.group(1)
                arg_type = arg_match.group(2) or ""
                arg_desc = arg_match.group(3)
                result["args"][arg_name] = {"type": arg_type, "description": arg_desc}
                current_arg = arg_name
            elif current_arg and stripped:
                # Continuation of previous arg description
                result["args"][current_arg]["description"] += " " + stripped
        elif current_section == "returns":
            if result["returns"]:
                result["returns"] += " " + stripped
            else:
                result["returns"] = stripped
                # Extract return type from "TypeName: description" pattern
                # Handles: "ILexEntry: description", "bool: description", "List[str]: desc"
                type_match = re.match(r'^([A-Za-z_][\w\[\], ]*?):\s+', stripped)
                if type_match:
                    result["return_type"] = type_match.group(1).strip()
        elif current_section == "raises":
            if stripped:
                result["raises"].append(stripped)
        elif current_section == "example":
            if result["example"]:
                result["example"] += "\n" + line  # Preserve indentation
            else:
                result["example"] = line

    # Extract summary (first line of description)
    if result["description"]:
        first_para = result["description"].split('\n\n')[0]
        result["summary"] = first_para.split('.')[0] + '.' if '.' in first_para else first_para

    return result


def generate_method_usage_hint(method_name: str, return_type: str = "") -> str:
    """Generate usage_hint for a method based on name pattern and return type."""
    name_lower = method_name.lower()

    # Check name prefixes for common patterns
    if method_name.startswith("Get") or method_name.startswith("Find"):
        return "retrieval"
    elif method_name.startswith("Set") or method_name.startswith("Update"):
        return "modification"
    elif method_name.startswith("Create") or method_name.startswith("Add") or method_name.startswith("New"):
        return "creation"
    elif method_name.startswith("Delete") or method_name.startswith("Remove"):
        return "deletion"
    elif method_name.startswith("Is") or method_name.startswith("Has") or method_name.startswith("Can"):
        return "validation"
    elif method_name.startswith("Convert") or method_name.startswith("Parse") or method_name.startswith("Format"):
        return "conversion"
    elif method_name.startswith("Move") or method_name.startswith("Copy"):
        return "manipulation"
    elif method_name.startswith("Load") or method_name.startswith("Read"):
        return "retrieval"
    elif method_name.startswith("Save") or method_name.startswith("Write"):
        return "persistence"
    elif "list" in name_lower or "all" in name_lower:
        return "enumeration"

    # Fallback based on return type
    if return_type:
        if return_type.lower() in ("bool", "boolean"):
            return "validation"
        elif return_type.lower() in ("list", "iterator", "iterable") or return_type.startswith("List["):
            return "enumeration"

    return "general"


def generate_entity_usage_hint(name: str, category: str, entity_type: str = "class") -> str:
    """Generate usage_hint for an entity based on name and category."""
    if "Operations" in name:
        return f"Provides operations for working with {category} data in FieldWorks"
    elif "Repository" in name:
        return f"Repository for accessing {category} objects"
    elif "Factory" in name:
        return f"Factory for creating {category} objects"
    elif "Service" in name:
        return f"Service for {category} operations"
    elif name.startswith("I") and name[1].isupper():
        # Interface
        return f"Interface defining {category} object structure and behavior"
    else:
        return f"Class for working with {category} data in FieldWorks"


def generate_method_description(method_name: str, params: List[str], return_type: str = "") -> str:
    """Generate a description for methods without docstrings based on naming patterns.

    This helps fill in documentation gaps for simple methods.
    """
    name = method_name

    # Common pattern mappings
    patterns = {
        # Get patterns
        "GetAll": "Returns all objects of this type",
        "GetCount": "Returns the count of objects",
        "GetGuid": "Returns the unique identifier (GUID) of the object",
        "GetOwner": "Returns the owning object",
        "GetOwning": "Returns the owning object",
        "GetParent": "Returns the parent object",
        "GetForm": "Returns the form (text representation) of the object",
        "GetName": "Returns the name of the object",
        "GetDate": "Returns the date",
        "GetDateModified": "Returns when the object was last modified",
        "GetDateCreated": "Returns when the object was created",

        # Set patterns
        "SetForm": "Sets the form (text representation) of the object",
        "SetName": "Sets the name of the object",

        # List/collection patterns
        "NumberOf": "Returns the count of",
        "AllEntries": "Returns all entries",
        "AllSenses": "Returns all senses",

        # Action patterns
        "Create": "Creates a new object",
        "Delete": "Deletes the object",
        "Add": "Adds an item",
        "Remove": "Removes an item",
        "Find": "Finds objects matching the criteria",
        "Lookup": "Looks up an object by identifier",
        "Move": "Moves the object",
        "Merge": "Merges objects together",
        "Duplicate": "Creates a copy of the object",
    }

    # Try exact prefix matches first
    for pattern, desc in patterns.items():
        if name.startswith(pattern) or pattern in name:
            # Try to make it more specific
            suffix = name.replace(pattern, "").strip()
            if suffix:
                # CamelCase to words
                words = re.sub('([A-Z])', r' \1', suffix).strip().lower()
                return f"{desc} {words}".rstrip()
            return desc

    # Fall back to generic patterns based on prefix
    if name.startswith("Get"):
        target = name[3:]  # Remove "Get"
        words = re.sub('([A-Z])', r' \1', target).strip().lower()
        return f"Returns the {words}"

    if name.startswith("Set"):
        target = name[3:]  # Remove "Set"
        words = re.sub('([A-Z])', r' \1', target).strip().lower()
        return f"Sets the {words}"

    if name.startswith("Is") or name.startswith("Has") or name.startswith("Can"):
        target = name[2:] if name.startswith("Is") else name[3:]
        words = re.sub('([A-Z])', r' \1', target).strip().lower()
        return f"Checks if {words}"

    # If we have parameters, try to describe based on them
    if params:
        param_str = ", ".join(params[:2])  # First 2 params
        return f"Performs {method_name} operation with {param_str}"

    # Last resort - just describe it generically
    words = re.sub('([A-Z])', r' \1', name).strip()
    return f"{words} operation"


def get_function_signature(node) -> Tuple[List[str], List[Dict]]:
    """Extract function signature and parameter details."""
    params = []
    param_details = []

    # Regular arguments
    defaults_start = len(node.args.args) - len(node.args.defaults)

    for i, arg in enumerate(node.args.args):
        if arg.arg == 'self':
            continue

        param_info = {"name": arg.arg, "type": "", "default": None}
        param_str = arg.arg

        # Type annotation
        if hasattr(arg, 'annotation') and arg.annotation:
            if isinstance(arg.annotation, ast.Name):
                param_info["type"] = arg.annotation.id
                param_str += f": {arg.annotation.id}"
            elif isinstance(arg.annotation, ast.Constant):
                param_info["type"] = str(arg.annotation.value)
                param_str += f": {arg.annotation.value}"
            elif isinstance(arg.annotation, ast.Subscript):
                # Handle Optional[X], List[X], etc.
                param_info["type"] = ast.unparse(arg.annotation) if hasattr(ast, 'unparse') else "complex"

        # Default value
        default_idx = i - defaults_start
        if default_idx >= 0 and default_idx < len(node.args.defaults):
            default = node.args.defaults[default_idx]
            if isinstance(default, ast.Constant):
                param_info["default"] = default.value
                param_str += f"={repr(default.value)}"
            elif isinstance(default, ast.Name):
                param_info["default"] = default.id
                param_str += f"={default.id}"

        params.append(param_str)
        param_details.append(param_info)

    return params, param_details


def extract_lcm_imports(tree) -> List[Dict[str, str]]:
    """Extract all SIL.LCModel imports from a module."""
    imports = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("SIL"):
                for alias in node.names:
                    imports.append({
                        "module": module,
                        "name": alias.name,
                        "alias": alias.asname
                    })

    return imports


# Known LibLCM property suffixes and their meanings
LCM_PROPERTY_SUFFIXES = {
    "OA": "OwningAtomic",      # Single owned object
    "OS": "OwningSequence",    # Ordered list of owned objects
    "OC": "OwningCollection",  # Unordered set of owned objects
    "RA": "ReferenceAtomic",   # Single reference to another object
    "RS": "ReferenceSequence", # Ordered list of references
    "RC": "ReferenceCollection", # Unordered set of references
}

# Known LibLCM factory/repository patterns
LCM_FACTORY_PATTERN = re.compile(r'I\w+Factory')
LCM_REPOSITORY_PATTERN = re.compile(r'I\w+Repository')

# Known LibLCM utility classes and methods
LCM_UTILITIES = {
    "TsStringUtils": ["MakeString", "MakeTss", "NormalizeToNFC"],
    "ITsString": ["Text", "Length", "get_RunCount"],
    "ITsTextProps": ["GetIntProp", "GetStrProp"],
}

# Common transformation patterns in FlexLibs2
TRANSFORMATION_PATTERNS = {
    "hvo_resolution": ["GetObject", "__GetObject", "ObjectOrId", "GetLexEntry", "GetSense"],
    "ws_default": ["WSHandle", "__WSHandle", "DefaultVernacularWs", "DefaultAnalysisWs"],
    "null_coalesce": ["or ''", "or \"\"", "or None", "if .* else", "?."],
    "type_conversion": ["int(", "str(", "bool(", "list(", "ITsString("],
}


def _extract_default_transformations(node) -> List[Dict[str, str]]:
    """Extract transformation info from parameter defaults."""
    transformations = []

    if not hasattr(node, 'args') or not node.args:
        return transformations

    args = node.args
    defaults = args.defaults
    kw_defaults = args.kw_defaults if hasattr(args, 'kw_defaults') else []

    # Calculate offset for defaults (defaults align to end of args)
    num_args = len(args.args)
    num_defaults = len(defaults)
    offset = num_args - num_defaults

    for i, default in enumerate(defaults):
        if default is not None:
            arg_index = offset + i
            if arg_index < len(args.args):
                param_name = args.args[arg_index].arg
                if param_name != 'self':
                    default_val = _get_default_value_str(default)
                    if default_val:
                        transformations.append({
                            "type": "default_value",
                            "param": param_name,
                            "default": default_val
                        })

    return transformations


def _get_default_value_str(node) -> str:
    """Get string representation of a default value."""
    if isinstance(node, ast.Constant):
        if node.value is None:
            return "None"
        elif isinstance(node.value, bool):
            return str(node.value)
        elif isinstance(node.value, str):
            return f'"{node.value}"'
        else:
            return str(node.value)
    elif isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.NameConstant):  # Python < 3.8
        return str(node.value)
    elif hasattr(ast, 'unparse'):
        try:
            return ast.unparse(node)
        except Exception:
            pass
    return ""


def _track_param_usage(child, param_names: set, param_usage: dict):
    """Track how parameters are used in LibLCM calls."""
    if not isinstance(child, ast.Call):
        return

    # Get the call target (method name)
    call_target = ""
    if isinstance(child.func, ast.Attribute):
        call_target = child.func.attr
    elif isinstance(child.func, ast.Name):
        call_target = child.func.id

    if not call_target:
        return

    # Check arguments for parameter usage
    for i, arg in enumerate(child.args):
        if isinstance(arg, ast.Name) and arg.id in param_names:
            param_name = arg.id
            usage = f"arg[{i}] of {call_target}()"
            if param_name not in param_usage:
                param_usage[param_name] = []
            if usage not in param_usage[param_name]:
                param_usage[param_name].append(usage)

    # Check keyword arguments
    for kw in child.keywords:
        if isinstance(kw.value, ast.Name) and kw.value.id in param_names:
            param_name = kw.value.id
            usage = f"{kw.arg}= of {call_target}()"
            if param_name not in param_usage:
                param_usage[param_name] = []
            if usage not in param_usage[param_name]:
                param_usage[param_name].append(usage)


def _detect_code_transformations(node) -> List[Dict[str, str]]:
    """Detect transformation patterns in method body."""
    transformations = []

    try:
        if hasattr(ast, 'unparse'):
            source = ast.unparse(node)
        else:
            source = ""
    except Exception:
        source = ""

    if not source:
        return transformations

    # Check for HVO/object resolution
    for pattern in TRANSFORMATION_PATTERNS["hvo_resolution"]:
        if pattern in source:
            transformations.append({
                "type": "hvo_resolution",
                "pattern": pattern,
                "description": "Resolves HVO (integer) to object if needed"
            })
            break

    # Check for writing system default
    for pattern in TRANSFORMATION_PATTERNS["ws_default"]:
        if pattern in source:
            transformations.append({
                "type": "ws_default",
                "pattern": pattern,
                "description": "Applies default writing system if not specified"
            })
            break

    # Check for null coalescing
    if " or ''" in source or ' or ""' in source:
        transformations.append({
            "type": "null_coalesce",
            "pattern": "or ''",
            "description": "Returns empty string instead of None"
        })
    elif " or None" in source or " if " in source and " else " in source:
        transformations.append({
            "type": "conditional",
            "description": "Conditional logic for handling special cases"
        })

    # Check for type conversions
    for pattern in TRANSFORMATION_PATTERNS["type_conversion"]:
        if pattern in source:
            transformations.append({
                "type": "type_conversion",
                "pattern": pattern.rstrip("("),
                "description": f"Converts to {pattern.rstrip('(')}"
            })

    return transformations


def extract_lcm_calls(node, lcm_imports: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Extract LibLCM method calls and property accesses from a method body.

    Returns a dictionary with:
    - factories_used: List of factory interfaces used (e.g., ILexEntryFactory)
    - repositories_used: List of repository interfaces used
    - properties_accessed: List of LibLCM properties accessed (with suffix type)
    - methods_called: List of specific LibLCM methods called
    - utilities_used: List of utility classes/methods used (e.g., TsStringUtils)
    - mapping_type: Classification of the mapping (direct, convenience, composite, pure_python)
    - param_usage: Dict mapping FlexLibs2 params to their LibLCM usage
    - transformations: List of detected transformations (defaults, conversions, etc.)
    """
    result = {
        "factories_used": [],
        "repositories_used": [],
        "properties_accessed": [],
        "methods_called": [],
        "utilities_used": [],
        "mapping_type": "pure_python",  # Default, will be updated
        "param_usage": {},  # Maps param name -> list of LCM usages
        "transformations": [],  # List of detected transformations
    }

    # Extract parameter names from the function definition
    param_names = set()
    if hasattr(node, 'args') and node.args:
        for arg in node.args.args:
            if arg.arg != 'self':
                param_names.add(arg.arg)

    # Track parameter defaults for transformation detection
    defaults_info = _extract_default_transformations(node)
    if defaults_info:
        result["transformations"].extend(defaults_info)

    # Build set of imported LCM names for faster lookup
    imported_lcm_names = {imp["name"] for imp in lcm_imports}

    # Walk the method body AST
    for child in ast.walk(node):
        # Track parameter usage in calls
        if isinstance(child, ast.Call) and param_names:
            _track_param_usage(child, param_names, result["param_usage"])

        # Look for GetService calls (factory/repository pattern)
        if isinstance(child, ast.Call):
            call_str = _get_call_string(child)

            # Check for ServiceLocator.GetService(IFactory)
            if "GetService" in call_str or "GetInstance" in call_str:
                for arg in child.args:
                    if isinstance(arg, ast.Name):
                        if LCM_FACTORY_PATTERN.match(arg.id):
                            if arg.id not in result["factories_used"]:
                                result["factories_used"].append(arg.id)
                        elif LCM_REPOSITORY_PATTERN.match(arg.id):
                            if arg.id not in result["repositories_used"]:
                                result["repositories_used"].append(arg.id)

            # Check for ObjectsIn(Repository) pattern
            if "ObjectsIn" in call_str:
                for arg in child.args:
                    if isinstance(arg, ast.Name) and LCM_REPOSITORY_PATTERN.match(arg.id):
                        if arg.id not in result["repositories_used"]:
                            result["repositories_used"].append(arg.id)

            # Check for utility class calls (TsStringUtils.MakeString, etc.)
            if isinstance(child.func, ast.Attribute):
                if isinstance(child.func.value, ast.Name):
                    class_name = child.func.value.id
                    method_name = child.func.attr
                    if class_name in LCM_UTILITIES:
                        util_str = f"{class_name}.{method_name}"
                        if util_str not in result["utilities_used"]:
                            result["utilities_used"].append(util_str)

            # Check for .Create(), .Add(), .Delete() calls on LCM objects
            if isinstance(child.func, ast.Attribute):
                method_name = child.func.attr
                if method_name in ["Create", "Add", "Delete", "Remove", "Insert", "Clear", "MoveTo"]:
                    method_str = f".{method_name}()"
                    if method_str not in result["methods_called"]:
                        result["methods_called"].append(method_str)

        # Look for property accesses with LCM suffixes
        if isinstance(child, ast.Attribute):
            attr_name = child.attr
            # Check if property ends with known LCM suffix
            for suffix, suffix_type in LCM_PROPERTY_SUFFIXES.items():
                if attr_name.endswith(suffix) and len(attr_name) > len(suffix):
                    prop_info = f"{attr_name} ({suffix_type})"
                    if prop_info not in result["properties_accessed"]:
                        result["properties_accessed"].append(prop_info)
                    break

            # Check for common LCM property patterns
            if attr_name in ["Form", "Gloss", "Definition", "Comment", "CitationForm",
                            "LexemeFormOA", "MorphTypeRA", "PartOfSpeechRA", "Guid", "Hvo",
                            "Owner", "OwningFlid", "ClassID", "ClassName"]:
                if attr_name not in result["properties_accessed"]:
                    result["properties_accessed"].append(attr_name)

            # Check for MultiString operations
            if attr_name in ["get_String", "set_String", "BestAnalysisAlternative",
                            "BestVernacularAlternative", "CopyAlternatives"]:
                method_str = f".{attr_name}()"
                if method_str not in result["methods_called"]:
                    result["methods_called"].append(method_str)

    # Detect code-level transformations
    code_transforms = _detect_code_transformations(node)
    if code_transforms:
        result["transformations"].extend(code_transforms)

    # Classify the mapping type based on what we found
    result["mapping_type"] = _classify_mapping_type(result)

    return result


def _get_call_string(node: ast.Call) -> str:
    """Get a string representation of a call for pattern matching."""
    try:
        if hasattr(ast, 'unparse'):
            return ast.unparse(node.func)
        elif isinstance(node.func, ast.Attribute):
            return node.func.attr
        elif isinstance(node.func, ast.Name):
            return node.func.id
    except Exception:
        pass
    return ""


def _classify_mapping_type(lcm_data: Dict[str, Any]) -> str:
    """
    Classify the type of FlexLibs2 -> LibLCM mapping.

    Types:
    - direct: 1:1 mapping to a single LibLCM call or property access
    - convenience: Adds validation, defaults, type conversion, or chains properties
    - composite: Combines multiple distinct LibLCM operations (e.g., create + configure)
    - pure_python: No LibLCM calls (computation, validation, etc.)
    """
    num_factories = len(lcm_data["factories_used"])
    num_repos = len(lcm_data["repositories_used"])
    num_props = len(lcm_data["properties_accessed"])
    num_methods = len(lcm_data["methods_called"])
    num_utils = len(lcm_data["utilities_used"])

    # Count unique base properties (strip the suffix info for deduplication)
    unique_props = set()
    for prop in lcm_data["properties_accessed"]:
        # Extract just the property name (before " (" if present)
        base_prop = prop.split(" (")[0]
        unique_props.add(base_prop)
    num_unique_props = len(unique_props)

    total_lcm_usage = num_factories + num_repos + num_unique_props + num_methods + num_utils

    if total_lcm_usage == 0:
        return "pure_python"

    # Composite: Multiple factories OR factory + multiple other operations
    if num_factories > 1:
        return "composite"
    if num_factories == 1 and (num_unique_props > 2 or num_methods > 1):
        return "composite"

    # Composite: Using repos + significant property access (iteration + modification)
    if num_repos > 0 and num_unique_props > 2:
        return "composite"

    # Direct: Single property access or single method call
    if total_lcm_usage == 1:
        return "direct"
    if num_unique_props == 1 and num_methods <= 1 and num_factories == 0 and num_repos == 0:
        return "direct"

    # Direct: Simple property chain (e.g., entry.LexemeFormOA.Form)
    # These are counted as multiple accesses but are really one logical access
    if num_unique_props <= 2 and num_methods == 0 and num_factories == 0 and num_repos == 0 and num_utils == 0:
        return "direct"

    # Convenience: Everything else (property access + method call, validation, etc.)
    return "convenience"


def analyze_method(node, class_name: str, lcm_imports: List[Dict] = None) -> Optional[Dict[str, Any]]:
    """Analyze a method definition and extract its API information."""
    if node.name.startswith('_') and node.name != '__init__':
        return None  # Skip private methods except __init__

    params, param_details = get_function_signature(node)
    docstring = extract_docstring(node)
    parsed_doc = parse_docstring(docstring)

    # Extract LibLCM calls from method body
    lcm_calls = extract_lcm_calls(node, lcm_imports or [])

    # Merge docstring arg info with parameter details
    for param in param_details:
        if param["name"] in parsed_doc["args"]:
            doc_arg = parsed_doc["args"][param["name"]]
            if doc_arg["type"] and not param["type"]:
                param["type"] = doc_arg["type"]
            param["description"] = doc_arg["description"]

    # Check for decorators
    is_property = False
    is_classmethod = False
    is_staticmethod = False

    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name):
            if decorator.id == "property":
                is_property = True
            elif decorator.id == "classmethod":
                is_classmethod = True
            elif decorator.id == "staticmethod":
                is_staticmethod = True

    # Extract return type: prefer type annotation, fallback to docstring
    return_type = ""
    if hasattr(node, 'returns') and node.returns:
        # Python type hint: def foo() -> Type:
        if isinstance(node.returns, ast.Name):
            return_type = node.returns.id
        elif isinstance(node.returns, ast.Constant):
            return_type = str(node.returns.value)
        elif isinstance(node.returns, ast.Subscript):
            # Handle Optional[X], List[X], Iterator[X], etc.
            return_type = ast.unparse(node.returns) if hasattr(ast, 'unparse') else "complex"
        elif hasattr(ast, 'unparse'):
            return_type = ast.unparse(node.returns)

    # Fallback to docstring-extracted return type
    if not return_type and parsed_doc["return_type"]:
        return_type = parsed_doc["return_type"]

    # Generate fallback description if none from docstring
    summary = parsed_doc["summary"]
    description = parsed_doc["description"]
    if not description or len(description) < 10:
        generated_desc = generate_method_description(node.name, params, return_type)
        if not description:
            description = generated_desc
        if not summary:
            summary = generated_desc

    method_info = {
        "name": node.name,
        "signature": f"{node.name}({', '.join(params)})",
        "summary": summary,
        "description": description,
        "usage_hint": generate_method_usage_hint(node.name, return_type),
        "parameters": param_details,
        "returns": parsed_doc["returns"],
        "return_type": return_type,
        "raises": parsed_doc["raises"],
        "example": parsed_doc["example"],
        "is_property": is_property,
        "is_classmethod": is_classmethod,
        "is_staticmethod": is_staticmethod,
        "lcm_mapping": lcm_calls
    }

    return method_info


def analyze_class(node, module_path: str, lcm_imports: List[Dict]) -> Dict[str, Any]:
    """Analyze a class definition and extract its API information."""
    docstring = extract_docstring(node)
    parsed_doc = parse_docstring(docstring)

    # Extract base classes
    base_classes = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            base_classes.append(base.id)
        elif isinstance(base, ast.Attribute):
            base_classes.append(f"{ast.unparse(base)}" if hasattr(ast, 'unparse') else base.attr)

    methods = []
    properties = []

    for item in node.body:
        if isinstance(item, ast.FunctionDef):
            method_info = analyze_method(item, node.name, lcm_imports)
            if method_info:
                if method_info["is_property"]:
                    properties.append(method_info)
                else:
                    methods.append(method_info)

    # Determine category from module path
    category = "general"
    if "Lexicon" in module_path:
        category = "lexicon"
    elif "Grammar" in module_path:
        category = "grammar"
    elif "TextsWords" in module_path:
        category = "texts"
    elif "Notebook" in module_path:
        category = "notebook"
    elif "Lists" in module_path:
        category = "lists"
    elif "System" in module_path:
        category = "system"
    elif "Scripture" in module_path:
        category = "scripture"
    elif "Discourse" in module_path:
        category = "discourse"
    elif "Reversal" in module_path:
        category = "reversal"
    elif "Wordform" in module_path:
        category = "wordform"

    # Build real Python namespace (flexlibs.code.Lexicon.LexEntryOperations)
    namespace = f"flexlibs.code.{module_path.replace('/', '.')}"

    return {
        "id": node.name,  # Alias for compatibility with LibLCM schema
        "name": node.name,
        "type": "class",
        "namespace": namespace,
        "source_file": module_path,
        "category": category,
        "summary": parsed_doc["summary"],
        "description": parsed_doc["description"],
        "usage_hint": generate_entity_usage_hint(node.name, category),
        "example": parsed_doc["example"],
        "base_classes": base_classes,
        "methods": sorted(methods, key=lambda m: m["name"]),
        "properties": properties,
        "lcm_dependencies": [imp["name"] for imp in lcm_imports if imp["module"].startswith("SIL.LCModel")],
        "tags": [category, "operations"] if "Operations" in node.name else [category]
    }


def analyze_python_file(file_path: Path, base_path: Path) -> Optional[Dict[str, Any]]:
    """Analyze a single Python file and extract its API structure."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        tree = ast.parse(content)

        # Get relative path for module identification
        rel_path = file_path.relative_to(base_path)
        module_path = str(rel_path.with_suffix('')).replace('\\', '/')

        lcm_imports = extract_lcm_imports(tree)

        file_info = {
            "file": str(rel_path),
            "module_path": module_path,
            "docstring": extract_docstring(tree),
            "classes": [],
            "lcm_imports": lcm_imports
        }

        # Find top-level classes
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_info = analyze_class(node, module_path, lcm_imports)
                file_info["classes"].append(class_info)

        return file_info

    except Exception as e:
        print(f"[WARN] Error analyzing {file_path}: {e}")
        return None


def analyze_flexlibs2(flexlibs2_path: str) -> Dict[str, Any]:
    """Analyze the entire FlexLibs 2.0 codebase."""
    base_path = Path(flexlibs2_path) / "flexlibs" / "code"

    if not base_path.exists():
        raise FileNotFoundError(f"FlexLibs 2.0 code directory not found: {base_path}")

    print(f"[INFO] Analyzing FlexLibs 2.0 at: {base_path}")

    result = {
        "_schema": "unified-api-doc/2.0",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "_source": {
            "type": "flexlibs2",
            "path": str(flexlibs2_path),
            "description": "FlexLibs 2.0 - Deep Python wrapper for LibLCM (~90% coverage)"
        },
        "metadata": {
            "total_classes": 0,
            "total_methods": 0,
            "total_properties": 0,
            "methods_with_return_type": 0,
            "files_analyzed": 0,
            "categories": {},
            "lcm_interfaces_used": set(),
            "mapping_types": {
                "direct": 0,
                "convenience": 0,
                "composite": 0,
                "pure_python": 0
            }
        },
        "entities": {},
        "categories": {},
        "lcm_mapping": {}  # Maps FlexLibs2 methods to LibLCM interfaces
    }

    # Analyze all Python files recursively
    for py_file in base_path.rglob("*.py"):
        if py_file.name.startswith("__"):
            continue

        file_info = analyze_python_file(py_file, base_path)
        if file_info and file_info["classes"]:
            result["metadata"]["files_analyzed"] += 1

            for class_info in file_info["classes"]:
                entity_id = class_info["name"]
                result["entities"][entity_id] = class_info
                result["metadata"]["total_classes"] += 1
                result["metadata"]["total_methods"] += len(class_info["methods"])
                result["metadata"]["total_properties"] += len(class_info["properties"])
                # Count methods with return types and mapping types
                for method in class_info["methods"]:
                    if method.get("return_type"):
                        result["metadata"]["methods_with_return_type"] += 1
                    # Count mapping types
                    mapping_type = method.get("lcm_mapping", {}).get("mapping_type", "pure_python")
                    if mapping_type in result["metadata"]["mapping_types"]:
                        result["metadata"]["mapping_types"][mapping_type] += 1

                # Track categories
                cat = class_info["category"]
                if cat not in result["metadata"]["categories"]:
                    result["metadata"]["categories"][cat] = 0
                result["metadata"]["categories"][cat] += 1

                # Track LCM dependencies
                for dep in class_info["lcm_dependencies"]:
                    result["metadata"]["lcm_interfaces_used"].add(dep)

                # Build LCM mapping with detailed method-level info
                for method in class_info["methods"]:
                    method_key = f"{entity_id}.{method['name']}"
                    lcm_info = method.get("lcm_mapping", {})
                    result["lcm_mapping"][method_key] = {
                        "class": entity_id,
                        "method": method["name"],
                        "mapping_type": lcm_info.get("mapping_type", "pure_python"),
                        "factories_used": lcm_info.get("factories_used", []),
                        "repositories_used": lcm_info.get("repositories_used", []),
                        "properties_accessed": lcm_info.get("properties_accessed", []),
                        "methods_called": lcm_info.get("methods_called", []),
                        "utilities_used": lcm_info.get("utilities_used", []),
                        "lcm_deps": class_info["lcm_dependencies"]
                    }

    # Convert set to list for JSON serialization
    result["metadata"]["lcm_interfaces_used"] = sorted(list(result["metadata"]["lcm_interfaces_used"]))

    # Build category index
    for entity_id, entity in result["entities"].items():
        cat = entity["category"]
        if cat not in result["categories"]:
            result["categories"][cat] = {
                "description": f"Operations related to {cat}",
                "entities": []
            }
        result["categories"][cat]["entities"].append(entity_id)

    return result


def get_category_from_method_name(method_name: str) -> str:
    """
    Determine category from FlexLibs stable method name prefix.

    FlexLibs stable uses method prefixes like Lexicon*, Text*, Reversal*, etc.
    """
    prefixes = {
        "Lexicon": "lexicon",
        "Text": "texts",
        "Reversal": "reversal",
        "Wordform": "wordform",
        "WS": "system",        # Writing system methods
        "Object": "system",    # Generic object methods
        "Get": "general",      # Generic getters (GetAllSemanticDomains, etc.)
        "Build": "general",    # Utility methods
        "Unpack": "general",   # Utility methods
    }

    for prefix, category in prefixes.items():
        if method_name.startswith(prefix):
            return category

    # Check for specific patterns
    if "WritingSystem" in method_name or "WS" in method_name:
        return "system"
    if "SemanticDomain" in method_name or "PartsOfSpeech" in method_name:
        return "lists"
    if "Project" in method_name:
        return "system"

    return "general"


def analyze_flexlibs_stable(flexlibs_path: str) -> Dict[str, Any]:
    """Analyze the FlexLibs stable codebase (single FLExProject class)."""
    code_path = Path(flexlibs_path) / "flexlibs" / "code"

    if not code_path.exists():
        raise FileNotFoundError(f"FlexLibs stable code directory not found: {code_path}")

    print(f"[INFO] Analyzing FlexLibs stable at: {code_path}")

    result = {
        "_schema": "unified-api-doc/2.0",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "_source": {
            "type": "flexlibs",
            "path": str(flexlibs_path),
            "description": "FlexLibs stable - Shallow Python wrapper for LibLCM (~40 functions)"
        },
        "metadata": {
            "total_classes": 0,
            "total_methods": 0,
            "total_properties": 0,
            "total_functions": 0,
            "methods_with_return_type": 0,
            "files_analyzed": 0,
            "categories": {},
            "lcm_interfaces_used": set(),
            "mapping_types": {
                "direct": 0,
                "convenience": 0,
                "composite": 0,
                "pure_python": 0
            }
        },
        "entities": {},
        "categories": {},
        "lcm_mapping": {},
        "functions": []  # Top-level functions
    }

    # Analyze Python files in code directory (non-recursive for stable)
    for py_file in code_path.glob("*.py"):
        if py_file.name.startswith("__"):
            continue

        file_info = analyze_python_file(py_file, code_path)
        if not file_info:
            continue

        result["metadata"]["files_analyzed"] += 1

        # Extract top-level functions
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                tree = ast.parse(f.read())

            lcm_imports = extract_lcm_imports(tree)

            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                    func_info = analyze_method(node, "", lcm_imports)
                    if func_info:
                        func_info["source_file"] = py_file.name
                        func_info["category"] = get_category_from_method_name(node.name)
                        result["functions"].append(func_info)
                        result["metadata"]["total_functions"] += 1
        except Exception as e:
            print(f"[WARN] Error extracting functions from {py_file}: {e}")

        # Process classes
        for class_info in file_info.get("classes", []):
            entity_id = class_info["name"]

            # Skip exception classes (they're not API)
            if ("Error" in entity_id or "Exception" in entity_id or
                entity_id.startswith("FP_")):
                continue

            # For FlexLibs stable, categorize methods by their name prefix
            method_categories = {}
            for method in class_info["methods"]:
                cat = get_category_from_method_name(method["name"])
                method["category"] = cat
                if cat not in method_categories:
                    method_categories[cat] = 0
                method_categories[cat] += 1

            # Set class category based on most common method category
            if method_categories:
                class_info["category"] = max(method_categories, key=method_categories.get)
            else:
                class_info["category"] = "general"

            result["entities"][entity_id] = class_info
            result["metadata"]["total_classes"] += 1
            result["metadata"]["total_methods"] += len(class_info["methods"])
            result["metadata"]["total_properties"] += len(class_info.get("properties", []))

            # Count methods with return types and mapping types
            for method in class_info["methods"]:
                if method.get("return_type"):
                    result["metadata"]["methods_with_return_type"] += 1
                mapping_type = method.get("lcm_mapping", {}).get("mapping_type", "pure_python")
                if mapping_type in result["metadata"]["mapping_types"]:
                    result["metadata"]["mapping_types"][mapping_type] += 1

            # Track categories
            cat = class_info["category"]
            if cat not in result["metadata"]["categories"]:
                result["metadata"]["categories"][cat] = 0
            result["metadata"]["categories"][cat] += 1

            # Track LCM dependencies
            for dep in class_info.get("lcm_dependencies", []):
                result["metadata"]["lcm_interfaces_used"].add(dep)

            # Build LCM mapping
            for method in class_info["methods"]:
                method_key = f"{entity_id}.{method['name']}"
                lcm_info = method.get("lcm_mapping", {})
                result["lcm_mapping"][method_key] = {
                    "class": entity_id,
                    "method": method["name"],
                    "mapping_type": lcm_info.get("mapping_type", "pure_python"),
                    "factories_used": lcm_info.get("factories_used", []),
                    "repositories_used": lcm_info.get("repositories_used", []),
                    "properties_accessed": lcm_info.get("properties_accessed", []),
                    "methods_called": lcm_info.get("methods_called", []),
                    "utilities_used": lcm_info.get("utilities_used", []),
                    "lcm_deps": class_info.get("lcm_dependencies", [])
                }

    # Convert set to list for JSON serialization
    result["metadata"]["lcm_interfaces_used"] = sorted(list(result["metadata"]["lcm_interfaces_used"]))

    # Build category index
    for entity_id, entity in result["entities"].items():
        cat = entity["category"]
        if cat not in result["categories"]:
            result["categories"][cat] = {
                "description": f"Operations related to {cat}",
                "entities": []
            }
        result["categories"][cat]["entities"].append(entity_id)

    return result


def cross_reference_liblcm(flexlibs_data: Dict[str, Any], liblcm_path: str = None) -> Dict[str, Any]:
    """
    Cross-reference FlexLibs lcm_mapping with LibLCM index to validate references.

    Args:
        flexlibs_data: FlexLibs API data with lcm_mapping
        liblcm_path: Path to LibLCM index JSON (defaults to index/liblcm/flex-api-enhanced.json)

    Returns:
        Validation report with found/missing entities
    """
    if liblcm_path is None:
        # Try default path
        default_path = Path(__file__).parent.parent / "index" / "liblcm" / "flex-api-enhanced.json"
        if default_path.exists():
            liblcm_path = str(default_path)
        else:
            return {"error": "LibLCM index not found", "validated": False}

    try:
        with open(liblcm_path, 'r', encoding='utf-8') as f:
            liblcm_data = json.load(f)
    except Exception as e:
        return {"error": f"Failed to load LibLCM index: {e}", "validated": False}

    liblcm_entities = set(liblcm_data.get("entities", {}).keys())

    report = {
        "validated": True,
        "factories": {"found": [], "missing": []},
        "repositories": {"found": [], "missing": []},
        "interfaces": {"found": [], "missing": []},
        "coverage": {}
    }

    # Collect all referenced LCM entities
    all_factories = set()
    all_repos = set()
    all_interfaces = set()

    for entity_name, entity in flexlibs_data.get("entities", {}).items():
        for method in entity.get("methods", []):
            lcm_map = method.get("lcm_mapping", {})
            all_factories.update(lcm_map.get("factories_used", []))
            all_repos.update(lcm_map.get("repositories_used", []))

            # Extract interface names from properties
            for prop in lcm_map.get("properties_accessed", []):
                # Properties like "SensesOS (OwningSequence)" - extract the base
                base_prop = prop.split(" (")[0]
                # Infer interface from property patterns
                if base_prop.endswith(("OA", "OS", "OC", "RA", "RS", "RC")):
                    # This is a relationship property - we'd need type info to know the target
                    pass

    # Validate factories
    for factory in all_factories:
        if factory in liblcm_entities:
            report["factories"]["found"].append(factory)
        else:
            report["factories"]["missing"].append(factory)

    # Validate repositories
    for repo in all_repos:
        if repo in liblcm_entities:
            report["repositories"]["found"].append(repo)
        else:
            report["repositories"]["missing"].append(repo)

    # Check interfaces from lcm_interfaces_used
    for iface in flexlibs_data.get("metadata", {}).get("lcm_interfaces_used", []):
        if iface in liblcm_entities:
            report["interfaces"]["found"].append(iface)
        else:
            report["interfaces"]["missing"].append(iface)

    # Calculate coverage
    total_refs = len(all_factories) + len(all_repos) + len(flexlibs_data.get("metadata", {}).get("lcm_interfaces_used", []))
    found_refs = len(report["factories"]["found"]) + len(report["repositories"]["found"]) + len(report["interfaces"]["found"])
    report["coverage"] = {
        "total_references": total_refs,
        "found_in_liblcm": found_refs,
        "coverage_pct": round(found_refs / total_refs * 100, 1) if total_refs > 0 else 100.0
    }

    return report


def print_summary(api_data: Dict[str, Any], version: str):
    """Print analysis summary."""
    print(f"\n[DONE] FlexLibs {version} Analysis Complete")
    print(f"  Classes: {api_data['metadata']['total_classes']}")
    print(f"  Methods: {api_data['metadata']['total_methods']}")
    if api_data['metadata'].get('total_functions', 0) > 0:
        print(f"  Functions: {api_data['metadata']['total_functions']}")
    print(f"  Methods with return_type: {api_data['metadata']['methods_with_return_type']}")
    print(f"  Properties: {api_data['metadata']['total_properties']}")
    print(f"  Files analyzed: {api_data['metadata']['files_analyzed']}")
    print(f"  LCM interfaces referenced: {len(api_data['metadata']['lcm_interfaces_used'])}")
    print(f"\n  LibLCM Mapping Types:")
    total = api_data['metadata']['total_methods']
    for mtype, count in sorted(api_data['metadata']['mapping_types'].items()):
        pct = (count / total * 100) if total else 0
        print(f"    {mtype}: {count} ({pct:.1f}%)")
    print(f"\n  Categories:")
    for cat, count in sorted(api_data['metadata']['categories'].items()):
        print(f"    {cat}: {count} classes")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Analyze FlexLibs Python API")
    parser.add_argument("--flexlibs2-path",
                        default=None,
                        help="Path to FlexLibs 2.0 repository")
    parser.add_argument("--flexlibs-path",
                        default=None,
                        help="Path to FlexLibs stable repository")
    parser.add_argument("--output", "-o",
                        default=None,
                        help="Output JSON file")

    args = parser.parse_args()

    # Determine which version to analyze
    if args.flexlibs_path:
        # Analyze FlexLibs stable
        try:
            api_data = analyze_flexlibs_stable(args.flexlibs_path)
            output_file = args.output or "flexlibs_api.json"

            print(f"[INFO] Writing results to: {output_file}")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(api_data, f, indent=2, ensure_ascii=False)

            print_summary(api_data, "stable")

        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    elif args.flexlibs2_path:
        # Analyze FlexLibs 2.0
        try:
            api_data = analyze_flexlibs2(args.flexlibs2_path)
            output_file = args.output or "flexlibs2_api.json"

            print(f"[INFO] Writing results to: {output_file}")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(api_data, f, indent=2, ensure_ascii=False)

            print_summary(api_data, "2.0")

        except Exception as e:
            print(f"[ERROR] {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    else:
        # Default: analyze both if paths exist
        default_flexlibs2 = r"D:\Github\flexlibs2"
        default_flexlibs = r"D:\Github\flexlibs"

        if Path(default_flexlibs2).exists():
            try:
                api_data = analyze_flexlibs2(default_flexlibs2)
                output_file = args.output or "flexlibs2_api.json"
                print(f"[INFO] Writing results to: {output_file}")
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(api_data, f, indent=2, ensure_ascii=False)
                print_summary(api_data, "2.0")
            except Exception as e:
                print(f"[ERROR] FlexLibs 2.0: {e}")

        if Path(default_flexlibs).exists():
            try:
                api_data = analyze_flexlibs_stable(default_flexlibs)
                output_file = "flexlibs_api.json"
                print(f"\n[INFO] Writing results to: {output_file}")
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(api_data, f, indent=2, ensure_ascii=False)
                print_summary(api_data, "stable")
            except Exception as e:
                print(f"[ERROR] FlexLibs stable: {e}")


if __name__ == "__main__":
    main()
