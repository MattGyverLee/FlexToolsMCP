#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LibLCM Extractor

Extracts API documentation from FieldWorks .NET assemblies using pythonnet.
Produces output in the unified-api-doc/2.0 schema format for consistency
with the FlexLibs 2.0 analyzer output.

Usage:
    python src/liblcm_extractor.py --dll-path "D:/path/to/dlls" --output index/liblcm/liblcm_api.json
    python src/liblcm_extractor.py --help

DLL Sources (in order of preference):
    1. --dll-path argument
    2. D:/Github/Fieldworks output directory (for development)
    3. C:/Program Files/SIL/FieldWorks 9 (standard installation)
"""

import argparse
import json
import os
import sys
import re
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

# ---- Logging -----------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
log = logging.getLogger("liblcm-extractor")

# ---- Schema Version ----------------------------------------------------------
SCHEMA_VERSION = "unified-api-doc/2.0"

# ---- Default DLL Paths -------------------------------------------------------
DEFAULT_DLL_PATHS = [
    Path(r"D:/Github/Fieldworks/Output/Debug"),
    Path(r"D:/Github/Fieldworks/Output/Release"),
    Path(r"C:/Program Files/SIL/FieldWorks 9"),
    Path(r"C:/Program Files (x86)/SIL/FieldWorks 9"),
]

# ---- Required Assemblies (order matters - dependencies first) ----------------
REQUIRED_ASSEMBLIES = [
    "SIL.Core.dll",
    "SIL.LCModel.Core.dll",
    "SIL.LCModel.dll"
]

# ---- Optional Assemblies (help resolve dependencies) -------------------------
OPTIONAL_ASSEMBLIES = [
    "SIL.LCModel.Utils.dll",
    "SIL.WritingSystems.dll",
    "icu.net.dll",
    "Newtonsoft.Json.dll",
    "CommonServiceLocator.dll"
]

# ---- Namespace Filters -------------------------------------------------------
TARGET_NAMESPACES = [
    "SIL.LCModel",
    "SIL.LCModel.Core",
    "SIL.LCModel.DomainServices",
    "SIL.LCModel.Infrastructure",
    "SIL.LCModel.Application"
]

# ---- Known MultiString Property Names ----------------------------------------
MULTISTRING_PROPERTY_NAMES = {
    "CitationForm", "Gloss", "Definition", "Abbreviation",
    "Name", "ShortName", "Description", "Comment", "Form",
    "ReversalName", "Title", "VersionNotes", "Explanation"
}

# ---- Python.NET Bootstrap ----------------------------------------------------
PYTHONNET_AVAILABLE = False
Assembly = None
BindingFlags = None
DotNetType = object

def init_pythonnet():
    """Initialize pythonnet and import required .NET types."""
    global PYTHONNET_AVAILABLE, Assembly, BindingFlags, DotNetType

    try:
        import clr
        from System.Reflection import Assembly as Asm, BindingFlags as BF
        from System import Type as DT

        Assembly = Asm
        BindingFlags = BF
        DotNetType = DT
        PYTHONNET_AVAILABLE = True
        log.info("pythonnet initialized successfully")
        return True

    except ImportError as e:
        log.error(f"pythonnet not available: {e}")
        log.error("Install with: pip install pythonnet")
        return False
    except Exception as e:
        log.error(f"Failed to initialize pythonnet: {e}")
        return False


# ---- Assembly Loading --------------------------------------------------------

def find_dll_directory(dll_path: Optional[str] = None) -> Optional[Path]:
    """Find a valid DLL directory containing FieldWorks assemblies."""

    # Check explicit path first
    if dll_path:
        path = Path(dll_path)
        if path.exists():
            log.info(f"Using specified DLL path: {path}")
            return path
        else:
            log.warning(f"Specified DLL path does not exist: {path}")

    # Check default paths
    for path in DEFAULT_DLL_PATHS:
        if path.exists():
            # Verify it has at least one required assembly
            if (path / "SIL.LCModel.dll").exists():
                log.info(f"Found DLL directory: {path}")
                return path

    log.error("No valid DLL directory found")
    log.error("Searched paths:")
    for path in DEFAULT_DLL_PATHS:
        log.error(f"  - {path}")

    return None


def find_assemblies(dll_dir: Path) -> Tuple[List[Path], List[str]]:
    """Find required and optional assemblies in the DLL directory."""
    found = []
    missing = []

    # Find required assemblies
    for assembly_name in REQUIRED_ASSEMBLIES:
        assembly_path = dll_dir / assembly_name
        if assembly_path.exists():
            found.append(assembly_path)
            log.debug(f"Found required: {assembly_name}")
        else:
            missing.append(assembly_name)
            log.warning(f"Missing required: {assembly_name}")

    # Find optional assemblies
    for assembly_name in OPTIONAL_ASSEMBLIES:
        assembly_path = dll_dir / assembly_name
        if assembly_path.exists():
            found.append(assembly_path)
            log.debug(f"Found optional: {assembly_name}")

    return found, missing


def load_assemblies(assembly_paths: List[Path], dll_dir: Path) -> List:
    """Load .NET assemblies using pythonnet."""
    if not PYTHONNET_AVAILABLE:
        raise RuntimeError("pythonnet is not available")

    # Add DLL directory to path for dependency resolution
    dll_dir_str = str(dll_dir.absolute())
    if dll_dir_str not in sys.path:
        sys.path.insert(0, dll_dir_str)

    loaded = []
    for path in assembly_paths:
        try:
            log.debug(f"Loading: {path.name}")
            assembly = Assembly.LoadFile(str(path.absolute()))
            loaded.append(assembly)
            log.info(f"Loaded: {path.name}")
        except Exception as e:
            log.warning(f"Failed to load {path.name}: {e}")

    if not loaded:
        raise RuntimeError("No assemblies could be loaded")

    log.info(f"Successfully loaded {len(loaded)} assemblies")
    return loaded


# ---- Type Reflection ---------------------------------------------------------

def clean_type_name(name: str) -> str:
    """Clean .NET generic type names (remove backtick notation)."""
    if not name:
        return ""
    return re.sub(r'`\d+', '', name)


def get_element_type(t) -> Optional[str]:
    """Extract element type from generic collections (List<T>, IEnumerable<T>, etc.)."""
    if not PYTHONNET_AVAILABLE or t is None:
        return None

    try:
        # Generic types like ILcmOwningSequence<T>
        if t.IsGenericType:
            args = t.GetGenericArguments()
            if args and len(args) == 1:
                return clean_type_name(args[0].Name)
    except Exception:
        pass

    try:
        # Array types
        if t.IsArray:
            elem = t.GetElementType()
            return clean_type_name(elem.Name) if elem else None
    except Exception:
        pass

    try:
        # Check implemented interfaces for IEnumerable<T>
        for iface in t.GetInterfaces():
            if iface.IsGenericType:
                iface_name = clean_type_name(iface.Name)
                if iface_name in ("IEnumerable", "ICollection", "IList"):
                    args = iface.GetGenericArguments()
                    if args and len(args) == 1:
                        return clean_type_name(args[0].Name)
    except Exception:
        pass

    return None


def is_multistring_type(t) -> bool:
    """Detect if a type is a MultiString/MultiUnicode type."""
    if not PYTHONNET_AVAILABLE or t is None:
        return False

    try:
        type_name = clean_type_name(t.Name)
        if type_name in ("IMultiString", "IMultiUnicode", "MultiStringAccessor", "MultiUnicodeAccessor"):
            return True

        # Check for get_String/set_String methods (MultiString pattern)
        methods = {m.Name for m in t.GetMethods(BindingFlags.Public | BindingFlags.Instance)}
        return "get_String" in methods and "set_String" in methods
    except Exception:
        return False


def determine_property_kind(prop_name: str) -> str:
    """Determine FieldWorks property relationship kind from naming convention."""
    if prop_name.endswith("OS"):
        return "OS"  # Owning Sequence
    if prop_name.endswith("OC"):
        return "OC"  # Owning Collection
    if prop_name.endswith("RS"):
        return "RS"  # Reference Sequence
    if prop_name.endswith("RC"):
        return "RC"  # Reference Collection
    if prop_name.endswith("OA"):
        return "OA"  # Owning Atomic
    if prop_name.endswith("RA"):
        return "RA"  # Reference Atomic
    return ""


def get_relationship_type(kind: str) -> str:
    """Map property kind to relationship type."""
    mapping = {
        "OS": "owns_sequence",
        "OC": "owns_collection",
        "RS": "references_sequence",
        "RC": "references_collection",
        "OA": "owns_atomic",
        "RA": "references_atomic"
    }
    return mapping.get(kind, "property")


def get_relationship_description(kind: str) -> str:
    """Get human-readable description for relationship type."""
    descriptions = {
        "OS": "Ordered collection of owned objects (children)",
        "OC": "Unordered collection of owned objects (children)",
        "RS": "Ordered collection of referenced objects",
        "RC": "Unordered collection of referenced objects",
        "OA": "Single owned object reference (child)",
        "RA": "Single referenced object"
    }
    return descriptions.get(kind, "Object property")


# ---- Property Extraction -----------------------------------------------------

def extract_property(pinfo) -> Optional[Dict[str, Any]]:
    """Extract property metadata in unified format."""
    if not PYTHONNET_AVAILABLE:
        return None

    try:
        name = clean_type_name(pinfo.Name)
        prop_type = pinfo.PropertyType
        type_name = clean_type_name(prop_type.Name) if prop_type else "object"

        kind = determine_property_kind(name)
        relationship = get_relationship_type(kind)

        # Compute pythonic_name by stripping 2-char suffix for relationship properties
        pythonic_name = name
        if kind in ("OA", "OS", "OC", "RA", "RS", "RC"):
            pythonic_name = name[:-2]  # Strip suffix like SensesOS -> Senses

        # Determine target type for relationships
        target_type = None
        if kind in ("OS", "OC", "RS", "RC"):
            target_type = get_element_type(prop_type)
        elif kind in ("OA", "RA"):
            target_type = type_name

        # Check for MultiString
        is_ms = is_multistring_type(prop_type) or (name in MULTISTRING_PROPERTY_NAMES)

        # Can read/write?
        can_read = pinfo.CanRead
        can_write = pinfo.CanWrite

        return {
            "name": name,
            "pythonic_name": pythonic_name,
            "type": type_name,
            "kind": kind if kind else "property",
            "relationship": relationship,
            "target_type": target_type,
            "is_multistring": is_ms,
            "can_read": can_read,
            "can_write": can_write,
            "description": f"{get_relationship_description(kind)}" if kind else f"Property of type {type_name}"
        }
    except Exception as e:
        log.debug(f"Error extracting property {pinfo.Name if hasattr(pinfo, 'Name') else 'unknown'}: {e}")
        return None


# ---- Method Extraction -------------------------------------------------------

def extract_method(minfo) -> Optional[Dict[str, Any]]:
    """Extract method metadata in unified format."""
    if not PYTHONNET_AVAILABLE:
        return None

    try:
        name = clean_type_name(minfo.Name)

        # Skip property accessors and common object methods
        if name.startswith(("get_", "set_", "add_", "remove_")):
            return None
        if name in ("Equals", "GetHashCode", "GetType", "ToString", "Finalize", "MemberwiseClone"):
            return None

        # Build parameter list
        params = []
        for p in minfo.GetParameters():
            param_info = {
                "name": p.Name,
                "type": clean_type_name(p.ParameterType.Name) if p.ParameterType else "object",
                "is_optional": p.IsOptional,
                "has_default": p.HasDefaultValue
            }
            if p.HasDefaultValue:
                try:
                    param_info["default"] = str(p.DefaultValue) if p.DefaultValue is not None else "null"
                except Exception:
                    param_info["default"] = "?"
            params.append(param_info)

        # Build signature string
        param_strs = []
        for p in params:
            s = f"{p['type']} {p['name']}"
            if p.get('has_default'):
                s += f" = {p.get('default', '?')}"
            param_strs.append(s)

        signature = f"{name}({', '.join(param_strs)})"

        # Return type
        return_type = "void"
        if minfo.ReturnType:
            return_type = clean_type_name(minfo.ReturnType.Name)

        # Categorize method
        category = categorize_method(name)

        return {
            "name": name,
            "signature": signature,
            "return_type": return_type,
            "parameters": params,
            "category": category,
            "description": generate_method_description(name, category),
            "is_static": minfo.IsStatic,
            "is_virtual": minfo.IsVirtual,
            "is_abstract": minfo.IsAbstract
        }
    except Exception as e:
        log.debug(f"Error extracting method: {e}")
        return None


def categorize_method(name: str) -> str:
    """Categorize method by naming pattern."""
    if name.startswith(("Get", "Find", "Search", "Retrieve", "Load", "Fetch")):
        return "retrieval"
    elif name.startswith(("Set", "Update", "Modify", "Change", "Apply")):
        return "modification"
    elif name.startswith(("Create", "New", "Add", "Insert", "Make")):
        return "creation"
    elif name.startswith(("Delete", "Remove", "Clear", "Dispose")):
        return "deletion"
    elif name.startswith(("Is", "Has", "Can", "Should", "Check")):
        return "predicate"
    elif name.startswith(("Merge", "Copy", "Clone", "Move")):
        return "manipulation"
    elif name.startswith(("Validate", "Verify")):
        return "validation"
    else:
        return "operation"


def generate_method_description(name: str, category: str) -> str:
    """Generate a basic description for a method based on its name."""
    category_descriptions = {
        "retrieval": f"Retrieves data using {name}",
        "modification": f"Modifies data using {name}",
        "creation": f"Creates new objects using {name}",
        "deletion": f"Removes or deletes using {name}",
        "predicate": f"Checks condition using {name}",
        "manipulation": f"Manipulates data using {name}",
        "validation": f"Validates using {name}",
        "operation": f"Performs operation {name}"
    }
    return category_descriptions.get(category, f"Method: {name}")


# ---- Type Extraction ---------------------------------------------------------

def categorize_type(name: str, namespace: str) -> str:
    """Categorize a type based on name and namespace."""
    # Repository pattern
    if "Repository" in name:
        return "repository"
    if "Factory" in name:
        return "factory"

    # By namespace
    ns_lower = namespace.lower()
    if "domainservices" in ns_lower:
        return "service"
    if "infrastructure" in ns_lower:
        return "infrastructure"

    # By name patterns
    if name.startswith("ILex"):
        return "lexicon"
    if name.startswith("IMo"):
        return "morphology"
    if name.startswith("IWfi"):
        return "wordform"
    if name.startswith("IScrip") or name.startswith("IScr"):
        return "scripture"
    if name.startswith("IRn"):
        return "notebook"
    if name.startswith("IText") or name.startswith("IStText"):
        return "text"
    if name.startswith("IFs"):
        return "feature_structure"
    if name.startswith("IPh"):
        return "phonology"
    if name.startswith("ICm"):
        return "core"
    if name.startswith("IDs"):
        return "discourse"
    if name.startswith("IReversal"):
        return "reversal"

    return "general"


def generate_type_tags(name: str, namespace: str, category: str) -> List[str]:
    """Generate tags for a type."""
    tags = [category]

    # Add namespace-based tag
    if namespace:
        ns_parts = namespace.split('.')
        if len(ns_parts) > 2:
            tags.append(ns_parts[-1].lower())

    # Add pattern-based tags
    if name.startswith("I") and len(name) > 1 and name[1].isupper():
        tags.append("interface")
    if "Factory" in name:
        tags.append("factory")
    if "Repository" in name:
        tags.append("repository")
    if name.endswith("Svc") or name.endswith("Service"):
        tags.append("service")

    return list(set(tags))


def generate_usage_hint(name: str, kind: str) -> str:
    """Generate a usage hint for the type."""
    if "Repository" in name:
        base = name.replace("Repository", "").lstrip("I")
        return f"Use to query and access {base} objects from the database"
    if "Factory" in name:
        base = name.replace("Factory", "").lstrip("I")
        return f"Use to create new {base} objects"
    if kind == "interface" and name.startswith("I"):
        base = name[1:]
        return f"Interface for working with {base} objects in FieldWorks"
    if kind == "class":
        return f"Class providing {name} functionality"
    return f"{kind.capitalize()} in the FieldWorks API"


def extract_type(t, fetch_descriptions: bool = False) -> Optional[Dict[str, Any]]:
    """Extract complete type information in unified format."""
    if not PYTHONNET_AVAILABLE:
        return None

    try:
        name = clean_type_name(t.Name)
        namespace = t.Namespace or ""

        # Determine type kind
        kind = "class"
        if t.IsInterface:
            kind = "interface"
        elif t.IsEnum:
            kind = "enum"
        elif t.IsValueType and not t.IsPrimitive:
            kind = "struct"
        elif t.IsAbstract:
            kind = "abstract_class"

        # Get binding flags for public instance members only
        flags = BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly

        # Extract properties
        properties = []
        relationships = []

        try:
            for p in t.GetProperties(flags):
                prop_info = extract_property(p)
                if prop_info:
                    properties.append(prop_info)

                    # Track relationships separately
                    if prop_info.get("kind") in ("OS", "OC", "RS", "RC", "OA", "RA"):
                        relationships.append({
                            "property": prop_info["name"],
                            "type": prop_info["relationship"],
                            "target": prop_info.get("target_type"),
                            "description": prop_info.get("description", "")
                        })
        except Exception as e:
            log.debug(f"Error getting properties for {name}: {e}")

        # Extract methods
        methods = []

        try:
            for m in t.GetMethods(flags):
                method_info = extract_method(m)
                if method_info:
                    methods.append(method_info)
        except Exception as e:
            log.debug(f"Error getting methods for {name}: {e}")

        # Extract base types and interfaces
        base_classes = []
        implemented_interfaces = []

        try:
            if t.BaseType and t.BaseType.Name != "Object":
                base_classes.append(clean_type_name(t.BaseType.Name))

            for iface in t.GetInterfaces():
                iface_name = clean_type_name(iface.Name)
                if iface_name not in ("IDisposable", "IEnumerable", "IComparable"):
                    implemented_interfaces.append(iface_name)
        except Exception as e:
            log.debug(f"Error getting inheritance for {name}: {e}")

        # Categorize and generate metadata
        category = categorize_type(name, namespace)
        tags = generate_type_tags(name, namespace, category)
        usage_hint = generate_usage_hint(name, kind)

        # Generate summary/description
        summary = f"{kind.replace('_', ' ').capitalize()} for {name.lstrip('I')} operations"
        description = f"FieldWorks {kind} in the {namespace} namespace"

        if "Repository" in name:
            target = name.replace("Repository", "").lstrip("I")
            description = f"Repository for managing {target} objects in the FieldWorks database. Provides methods for querying, creating, and managing {target} instances."
        elif "Factory" in name:
            target = name.replace("Factory", "").lstrip("I")
            description = f"Factory for creating {target} objects. Use this to instantiate new {target} instances with proper initialization."

        return {
            "id": name,
            "name": name,
            "type": kind,
            "namespace": namespace,
            "category": category,
            "summary": summary,
            "description": description,
            "usage_hint": usage_hint,
            "base_classes": base_classes,
            "interfaces": implemented_interfaces,
            "properties": sorted(properties, key=lambda x: x["name"]),
            "methods": sorted(methods, key=lambda x: x["name"]),
            "relationships": relationships,
            "tags": tags
        }

    except Exception as e:
        log.debug(f"Error extracting type: {e}")
        return None


# ---- Assembly Analysis -------------------------------------------------------

def reflect_types(assemblies) -> List:
    """Extract all types from loaded assemblies that match our target namespaces."""
    if not PYTHONNET_AVAILABLE:
        return []

    types = []

    for assembly in assemblies:
        try:
            assembly_types = assembly.GetTypes()
            for t in assembly_types:
                ns = t.Namespace or ""

                # Check if namespace matches our targets
                if any(ns.startswith(target) for target in TARGET_NAMESPACES):
                    # Skip compiler-generated and internal types
                    if not t.Name.startswith("<") and not t.Name.startswith("__"):
                        types.append(t)

        except Exception as e:
            log.warning(f"Error reflecting types from assembly: {e}")

            # Try to get LoaderExceptions details
            try:
                if hasattr(e, 'LoaderExceptions'):
                    for lex in e.LoaderExceptions[:5]:  # Show first 5
                        if lex:
                            log.debug(f"  LoaderException: {lex}")
            except Exception:
                pass

    log.info(f"Found {len(types)} types in target namespaces")
    return types


# ---- Main Extraction ---------------------------------------------------------

def build_api_documentation(assemblies, fetch_descriptions: bool = False) -> Dict[str, Any]:
    """Build complete API documentation from loaded assemblies."""
    log.info("Building API documentation...")

    # Reflect all types
    types = reflect_types(assemblies)

    # Initialize output structure
    api_doc = {
        "metadata": {
            "total_types": 0,
            "total_interfaces": 0,
            "total_classes": 0,
            "total_enums": 0,
            "total_methods": 0,
            "total_properties": 0,
            "total_relationships": 0,
            "assemblies": [str(a.FullName) for a in assemblies],
            "namespaces": set(),
            "categories": {}
        },
        "entities": {},
        "categories": {
            "lexicon": {"description": "Lexical entry and sense management", "entities": []},
            "morphology": {"description": "Morphological forms and analysis", "entities": []},
            "phonology": {"description": "Phonological patterns and rules", "entities": []},
            "wordform": {"description": "Word form analysis and glossing", "entities": []},
            "text": {"description": "Text and paragraph management", "entities": []},
            "scripture": {"description": "Scripture translation support", "entities": []},
            "notebook": {"description": "Research notebook entries", "entities": []},
            "discourse": {"description": "Discourse analysis", "entities": []},
            "reversal": {"description": "Reversal index entries", "entities": []},
            "feature_structure": {"description": "Feature structures and values", "entities": []},
            "repository": {"description": "Data access repositories", "entities": []},
            "factory": {"description": "Object creation factories", "entities": []},
            "service": {"description": "Domain services", "entities": []},
            "infrastructure": {"description": "Infrastructure types", "entities": []},
            "core": {"description": "Core FieldWorks types", "entities": []},
            "general": {"description": "General utility types", "entities": []}
        },
        "relationships": [],
        "glossary": {
            "OS": "Owning Sequence - ordered collection of owned child objects",
            "OC": "Owning Collection - unordered collection of owned child objects",
            "RS": "Reference Sequence - ordered collection of referenced objects",
            "RC": "Reference Collection - unordered collection of referenced objects",
            "OA": "Owning Atomic - single owned child object reference",
            "RA": "Reference Atomic - single referenced object",
            "MultiString": "Text with multiple writing system alternatives (e.g., vernacular + analysis)",
            "HVO": "Handle-Value Object - integer identifier for database objects"
        }
    }

    # Process each type
    total_types = len(types)
    processed = 0

    for i, t in enumerate(types):
        if i % 50 == 0:
            log.info(f"Processing type {i+1}/{total_types}...")

        type_info = extract_type(t, fetch_descriptions)
        if type_info:
            entity_id = type_info["id"]
            api_doc["entities"][entity_id] = type_info
            processed += 1

            # Update metadata
            api_doc["metadata"]["total_types"] += 1
            api_doc["metadata"]["namespaces"].add(type_info["namespace"])
            api_doc["metadata"]["total_methods"] += len(type_info.get("methods", []))
            api_doc["metadata"]["total_properties"] += len(type_info.get("properties", []))
            api_doc["metadata"]["total_relationships"] += len(type_info.get("relationships", []))

            # Count by type
            kind = type_info.get("type", "class")
            if kind == "interface":
                api_doc["metadata"]["total_interfaces"] += 1
            elif kind == "enum":
                api_doc["metadata"]["total_enums"] += 1
            else:
                api_doc["metadata"]["total_classes"] += 1

            # Add to category
            category = type_info.get("category", "general")
            if category in api_doc["categories"]:
                api_doc["categories"][category]["entities"].append(entity_id)

            # Track category counts
            if category not in api_doc["metadata"]["categories"]:
                api_doc["metadata"]["categories"][category] = 0
            api_doc["metadata"]["categories"][category] += 1

            # Add relationships to global list
            for rel in type_info.get("relationships", []):
                api_doc["relationships"].append({
                    "source": entity_id,
                    "property": rel["property"],
                    "type": rel["type"],
                    "target": rel.get("target")
                })

    # Convert namespace set to sorted list
    api_doc["metadata"]["namespaces"] = sorted(list(api_doc["metadata"]["namespaces"]))

    # Remove empty categories
    api_doc["categories"] = {
        k: v for k, v in api_doc["categories"].items()
        if v.get("entities")
    }

    # Sort relationships
    api_doc["relationships"].sort(key=lambda r: (r["source"], r["property"]))

    # Build suffix_index for pythonic name lookups
    suffix_index = {
        "by_pythonic_name": {},  # "Senses" -> [{"entity": "ILexEntry", "full_name": "SensesOS", "kind": "OS"}, ...]
        "by_full_name": {}       # "SensesOS" -> {"entity": "ILexEntry", "pythonic_name": "Senses", "kind": "OS"}
    }

    for entity_id, entity_data in api_doc["entities"].items():
        for prop in entity_data.get("properties", []):
            name = prop.get("name", "")
            pythonic_name = prop.get("pythonic_name", name)
            kind = prop.get("kind", "property")

            # Only index properties with suffixes (relationship properties)
            if kind in ("OA", "OS", "OC", "RA", "RS", "RC") and pythonic_name != name:
                # Add to by_pythonic_name index
                if pythonic_name not in suffix_index["by_pythonic_name"]:
                    suffix_index["by_pythonic_name"][pythonic_name] = []
                suffix_index["by_pythonic_name"][pythonic_name].append({
                    "entity": entity_id,
                    "full_name": name,
                    "kind": kind
                })

                # Add to by_full_name index
                key = f"{entity_id}.{name}"
                suffix_index["by_full_name"][key] = {
                    "entity": entity_id,
                    "pythonic_name": pythonic_name,
                    "kind": kind
                }

    # Sort the pythonic name entries by entity for consistent output
    for pythonic_name in suffix_index["by_pythonic_name"]:
        suffix_index["by_pythonic_name"][pythonic_name].sort(key=lambda x: x["entity"])

    api_doc["suffix_index"] = suffix_index
    log.info(f"  Suffix index: {len(suffix_index['by_pythonic_name'])} pythonic names, {len(suffix_index['by_full_name'])} full names")

    log.info(f"Processed {processed}/{total_types} types")
    log.info(f"  Interfaces: {api_doc['metadata']['total_interfaces']}")
    log.info(f"  Classes: {api_doc['metadata']['total_classes']}")
    log.info(f"  Enums: {api_doc['metadata']['total_enums']}")
    log.info(f"  Methods: {api_doc['metadata']['total_methods']}")
    log.info(f"  Properties: {api_doc['metadata']['total_properties']}")
    log.info(f"  Relationships: {api_doc['metadata']['total_relationships']}")

    return api_doc


def stamp_document(api_doc: Dict[str, Any], dll_dir: Path) -> Dict[str, Any]:
    """Add schema and generation metadata to the document."""
    return {
        "_schema": SCHEMA_VERSION,
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "_source": {
            "type": "liblcm",
            "path": str(dll_dir.absolute()),
            "description": "LibLCM - FieldWorks Language and Culture Model (.NET assemblies)",
            "url": "https://github.com/sillsdev/liblcm"
        },
        **api_doc
    }


# ---- Main Entry Point --------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Extract API documentation from FieldWorks .NET assemblies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/liblcm_extractor.py
  python src/liblcm_extractor.py --dll-path "D:/Github/Fieldworks/Output/Debug"
  python src/liblcm_extractor.py --output index/liblcm/liblcm_api.json
  python src/liblcm_extractor.py --dll-path "C:/Program Files/SIL/FieldWorks 9" -v
        """
    )

    parser.add_argument(
        "--dll-path",
        help="Path to directory containing FieldWorks DLLs"
    )
    parser.add_argument(
        "--output", "-o",
        default="index/liblcm/liblcm_api.json",
        help="Output JSON file (default: index/liblcm/liblcm_api.json)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress non-error output"
    )
    parser.add_argument(
        "--fetch-descriptions",
        action="store_true",
        help="Attempt to fetch descriptions from liblcm source (experimental)"
    )

    args = parser.parse_args()

    # Configure logging
    if args.quiet:
        log.setLevel(logging.ERROR)
    elif args.verbose:
        log.setLevel(logging.DEBUG)

    try:
        # Initialize pythonnet
        if not init_pythonnet():
            log.error("Cannot proceed without pythonnet")
            return 1

        # Find DLL directory
        dll_dir = find_dll_directory(args.dll_path)
        if not dll_dir:
            log.error("No valid DLL directory found")
            log.error("Use --dll-path to specify the location of FieldWorks assemblies")
            return 1

        # Find assemblies
        assembly_paths, missing = find_assemblies(dll_dir)
        if missing:
            log.error(f"Missing required assemblies: {missing}")
            return 1

        if not assembly_paths:
            log.error("No assemblies found to load")
            return 1

        # Load assemblies
        assemblies = load_assemblies(assembly_paths, dll_dir)

        # Build documentation
        api_doc = build_api_documentation(assemblies, args.fetch_descriptions)

        # Add metadata
        stamped_doc = stamp_document(api_doc, dll_dir)

        # Ensure output directory exists
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write output
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(stamped_doc, f, indent=2, ensure_ascii=False)

        log.info(f"API documentation written to: {output_path}")

        # Print summary
        if not args.quiet:
            print(f"\n[DONE] LibLCM Extraction Complete")
            print(f"  Output: {output_path}")
            print(f"  Types: {api_doc['metadata']['total_types']}")
            print(f"  Interfaces: {api_doc['metadata']['total_interfaces']}")
            print(f"  Classes: {api_doc['metadata']['total_classes']}")
            print(f"  Methods: {api_doc['metadata']['total_methods']}")
            print(f"  Properties: {api_doc['metadata']['total_properties']}")
            print(f"  Relationships: {api_doc['metadata']['total_relationships']}")
            print(f"\n  Categories:")
            for cat, count in sorted(api_doc['metadata']['categories'].items()):
                print(f"    {cat}: {count} types")

        return 0

    except Exception as e:
        log.error(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
