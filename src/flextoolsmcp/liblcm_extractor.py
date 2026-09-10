#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LibLCM Extractor

Extracts API documentation from FieldWorks .NET assemblies using pythonnet.
Produces output in the unified-api-doc/2.0 schema format for consistency
with the Flexicon analyzer output.

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
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

if __package__:
    from .json_utils import sort_json_arrays
    from .flexicon_analyzer import infer_unified_output_behavior
    from .constants import (
        PROPERTY_KIND_OWNING_SEQUENCE,
        PROPERTY_KIND_OWNING_COLLECTION,
        PROPERTY_KIND_REFERENCE_SEQUENCE,
        PROPERTY_KIND_REFERENCE_COLLECTION,
        PROPERTY_KIND_OWNING_ATOMIC,
        PROPERTY_KIND_REFERENCE_ATOMIC,
        PROPERTY_KIND_TO_RELATIONSHIP,
        PROPERTY_KIND_DESCRIPTIONS,
        METHOD_CATEGORY_RETRIEVAL,
        METHOD_CATEGORY_MODIFICATION,
        METHOD_CATEGORY_CREATION,
        METHOD_CATEGORY_DELETION,
        METHOD_CATEGORY_PREDICATE,
        METHOD_CATEGORY_MANIPULATION,
        METHOD_CATEGORY_VALIDATION,
        METHOD_CATEGORY_OPERATION,
        METHOD_CATEGORY_DESCRIPTIONS,
        ENTITY_CATEGORY_SCRIPTURE,
        ENTITY_CATEGORY_TEXT,
        ENTITY_CATEGORY_GENERAL,
        ENTITY_CATEGORY_REPOSITORY,
        ENTITY_CATEGORY_FACTORY,
        ENTITY_CATEGORY_SERVICE,
        ENTITY_CATEGORY_INFRASTRUCTURE,
        ENTITY_PREFIX_TO_CATEGORY,
    )
else:
    from json_utils import sort_json_arrays
    from flexicon_analyzer import infer_unified_output_behavior
    from constants import (
        PROPERTY_KIND_OWNING_SEQUENCE,
        PROPERTY_KIND_OWNING_COLLECTION,
        PROPERTY_KIND_REFERENCE_SEQUENCE,
        PROPERTY_KIND_REFERENCE_COLLECTION,
        PROPERTY_KIND_OWNING_ATOMIC,
        PROPERTY_KIND_REFERENCE_ATOMIC,
        PROPERTY_KIND_TO_RELATIONSHIP,
        PROPERTY_KIND_DESCRIPTIONS,
        METHOD_CATEGORY_RETRIEVAL,
        METHOD_CATEGORY_MODIFICATION,
        METHOD_CATEGORY_CREATION,
        METHOD_CATEGORY_DELETION,
        METHOD_CATEGORY_PREDICATE,
        METHOD_CATEGORY_MANIPULATION,
        METHOD_CATEGORY_VALIDATION,
        METHOD_CATEGORY_OPERATION,
        METHOD_CATEGORY_DESCRIPTIONS,
        ENTITY_CATEGORY_SCRIPTURE,
        ENTITY_CATEGORY_TEXT,
        ENTITY_CATEGORY_GENERAL,
        ENTITY_CATEGORY_REPOSITORY,
        ENTITY_CATEGORY_FACTORY,
        ENTITY_CATEGORY_SERVICE,
        ENTITY_CATEGORY_INFRASTRUCTURE,
        ENTITY_PREFIX_TO_CATEGORY,
    )

# ---- Logging -----------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
log = logging.getLogger("liblcm-extractor")

# ---- Schema Version ----------------------------------------------------------
SCHEMA_VERSION = "unified-api-doc/2.0"

# ---- Default DLL Paths -------------------------------------------------------
def get_default_dll_paths():
    """Build list of default DLL paths from environment and standard locations."""
    paths = []

    # Check FIELDWORKS_DLL_PATH environment variable first
    env_path = os.environ.get("FIELDWORKS_DLL_PATH")
    if env_path:
        paths.append(Path(env_path))

    # Add standard paths
    paths.extend([
        Path(r"D:/Github/Fieldworks/Output/Debug"),
        Path(r"D:/Github/Fieldworks/Output/Release"),
        Path(r"C:/Program Files/SIL/FieldWorks 9"),
        Path(r"C:/Program Files (x86)/SIL/FieldWorks 9"),
    ])

    return paths

DEFAULT_DLL_PATHS = get_default_dll_paths()


# ---- Version Detection -------------------------------------------------------

def get_liblcm_version(assemblies: List[Any]) -> str:
    """Extract LibLCM version from loaded assemblies."""
    if not PYTHONNET_AVAILABLE or not assemblies:
        return "0.0.0"

    try:
        # Try to get version from SIL.LCModel assembly
        for assembly in assemblies:
            try:
                asm_name = assembly.GetName()
                if "SIL.LCModel" in asm_name.Name:
                    version = asm_name.Version
                    return f"{version.Major}.{version.Minor}.{version.Build}"
            except Exception:
                pass

        # Fallback: try first assembly
        if assemblies:
            try:
                version = assemblies[0].GetName().Version
                return f"{version.Major}.{version.Minor}.{version.Build}"
            except Exception:
                pass

    except Exception as e:
        log.warning(f"Could not extract version from assemblies: {e}")

    return "0.0.0"

# ---- Required Assemblies (order matters - dependencies first) ----------------
REQUIRED_ASSEMBLIES = [
    "SIL.Core.dll",
    "SIL.LCModel.Core.dll",
    "SIL.LCModel.dll"
]

# ---- Optional Assemblies (help resolve dependencies) -------------------------
OPTIONAL_ASSEMBLIES = [
    "SIL.LCModel.Utils.dll",
    "SIL.LCModel.Tools.dll",
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

# Namespaces that sit under a target prefix but are not FieldWorks API.
# SIL.LCModel.Tools.dll bundles Malcolm Crowe's CSTools LALR parser generator
# (Nfa, Dfa, Lexer, Parser, Regex, Class_1..Class_12, ...). The DLL is preloaded
# only so SIL.LCModel.Core.dll can bind; its own types are build machinery and
# would otherwise pollute search_by_capability under category "system".
EXCLUDED_NAMESPACES = [
    "SIL.LCModel.Tools"
]

# Namespaces where only a few hand-written types are real API. Everything else in
# them is generated machinery. SIL.LCModel.Core.Phonology is CSTools output for the
# phonological-environment grammar -- Class_1..Class_12, Environment_1..3,
# LeftContext/RightContext/OptionalSegment/TermSequence/Term/Segment variants,
# yyPhonEnvParser, yytokens -- around 56 generated types wrapping two useful ones.
NAMESPACE_TYPE_ALLOWLIST = {
    "SIL.LCModel.Core.Phonology": {"PhonEnvRecognizer", "SyntaxErrType"},
}

# Pre-compile regex for namespace matching (eliminates O(m) list iteration per type)
_TARGET_NS_PATTERN = re.compile(r"^(" + "|".join(re.escape(ns) for ns in TARGET_NAMESPACES) + ")")

# Anchored at a namespace boundary so "SIL.LCModel.ToolsSomething" is not excluded
_EXCLUDED_NS_PATTERN = re.compile(
    r"^(" + "|".join(re.escape(ns) for ns in EXCLUDED_NAMESPACES) + r")(\.|$)"
)


def _is_target_type(t) -> bool:
    """True if a reflected .NET type belongs in the index.

    Keeps types in the target namespaces, dropping excluded namespaces and
    compiler-generated or internal names (those starting with '<' or '_').
    """
    if t is None:
        return False
    ns = t.Namespace or ""
    if not _TARGET_NS_PATTERN.match(ns):
        return False
    if _EXCLUDED_NS_PATTERN.match(ns):
        return False
    allowed = NAMESPACE_TYPE_ALLOWLIST.get(ns)
    if allowed is not None and t.Name not in allowed:
        return False
    return bool(t.Name) and t.Name[0] not in "<_"

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
        import clr  # noqa: F401  # availability probe: raises ImportError if pythonnet is absent
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


def load_assemblies(assembly_paths: List[Path], dll_dir: Path) -> List[Any]:
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
    if prop_name.endswith(PROPERTY_KIND_OWNING_SEQUENCE):
        return PROPERTY_KIND_OWNING_SEQUENCE
    if prop_name.endswith(PROPERTY_KIND_OWNING_COLLECTION):
        return PROPERTY_KIND_OWNING_COLLECTION
    if prop_name.endswith(PROPERTY_KIND_REFERENCE_SEQUENCE):
        return PROPERTY_KIND_REFERENCE_SEQUENCE
    if prop_name.endswith(PROPERTY_KIND_REFERENCE_COLLECTION):
        return PROPERTY_KIND_REFERENCE_COLLECTION
    if prop_name.endswith(PROPERTY_KIND_OWNING_ATOMIC):
        return PROPERTY_KIND_OWNING_ATOMIC
    if prop_name.endswith(PROPERTY_KIND_REFERENCE_ATOMIC):
        return PROPERTY_KIND_REFERENCE_ATOMIC
    return ""


def get_relationship_type(kind: str) -> str:
    """Map property kind to relationship type."""
    return PROPERTY_KIND_TO_RELATIONSHIP.get(kind, "property")


def get_relationship_description(kind: str) -> str:
    """Get human-readable description for relationship type."""
    return PROPERTY_KIND_DESCRIPTIONS.get(kind, "Object property")


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

        # Build result
        result = {
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

        # Add structured output behavior
        result["output_behavior"] = infer_unified_output_behavior(
            method_or_property_name=name,
            return_type=type_name,
            library="liblcm",
            property_kind=kind,
            is_method=False
        )

        # Keep legacy empty_value_behavior for backwards compatibility with multistrings
        if is_ms:
            result["empty_value_behavior"] = {
                "returns_when_empty": "***",
                "warning": "Returns '***' placeholder when empty, not empty string or None",
                "recommended_handling": "Use flexicon wrapper methods or normalize_text() to handle '***'"
            }

        return result
    except Exception as e:
        log.debug(f"Error extracting property {pinfo.Name if hasattr(pinfo, 'Name') else 'unknown'}: {e}")
        return None


# ---- Method Extraction -------------------------------------------------------

# Issue #136: hand-written teaching text for the two ITsString accessors the
# domain review called out by name. Every other recovered get_/set_ accessor
# falls back to generate_method_description()'s generic template -- these two
# are common enough (every run-iteration script touches them) to earn a
# precise, worked description instead of "Retrieves data using get_Properties".
#
# NOTE: the domain review's cycle1-domain.md drafted these against an
# assumed "character offset ich" parameter for both methods. Live reflection
# (confirmed against src/SIL.LCModel.Core/Text/TsStrBase.cs's own doc
# comments in the liblcm checkout) shows both actually take a *run index*
# (parameter irun) -- "Gets the text properties for the specified run." /
# "Gets the text for the specified run." -- which is a different parameter
# than the sibling *At methods (get_RunAt(ich)/get_PropertiesAt(ich)) that
# genuinely take a character offset. Shipping the drafted text verbatim
# would tell script authors to pass a character offset into a run-index
# parameter, silently returning the wrong run's data (or throwing once the
# offset exceeds RunCount). Corrected below to match the real signature
# while preserving the domain review's teaching intent (the
# GetIntPropValues hint and the RunCount/get_MinOfRun/get_LimOfRun
# iteration pattern).
RECOVERED_ACCESSOR_DESCRIPTIONS = {
    "get_Properties": (
        "Returns the ITsTextProps for run number irun (a run index, not a "
        "character offset -- use get_RunAt(ich) to find which run contains "
        "a given character offset, or get_PropertiesAt(ich) to get "
        "properties directly from an offset). Call "
        ".GetIntPropValues(FwTextPropType.ktptWs) on the result to read the "
        "writing-system id for that run."
    ),
    "get_RunText": (
        "Returns the text of run number irun (a run index, not a character "
        "offset). Pair with get_Properties(irun) to read both the run's "
        "text and its properties (e.g. writing system) in one pass; use "
        "RunCount/get_MinOfRun(i)/get_LimOfRun(i) to iterate every run, or "
        "get_RunAt(ich) to find the run containing a given character offset."
    ),
}


def _is_property_backing_accessor(minfo, accessor_name: str, type_properties: List[Any]) -> bool:
    """Gate 2 for #136: True when `minfo` is the compiler-generated get_/set_
    accessor for a PropertyInfo that GetProperties() already surfaced on this
    type (e.g. the managed C# indexer backing IStText.Item, LcmList.Item,
    SmallDictionary.Item, ...). Retaining those too would emit a second,
    method-shaped duplicate of an entry `properties` already documents --
    unlike ITsString's COM case, where GetProperties() never surfaces an
    indexer at all.

    Primary check is MethodInfo identity against
    pinfo.GetGetMethod(True)/GetSetMethod(True) (the real reflection-level
    fact: "is this method literally the getter/setter of that property").
    A base-name string match against known property names is the fallback,
    covering any reflection edge case where two MethodInfo instances that
    describe the same underlying accessor fail an identity comparison.
    """
    base_name = accessor_name[4:] if accessor_name.startswith(("get_", "set_")) else accessor_name

    property_names = set()
    for pinfo in type_properties:
        try:
            property_names.add(clean_type_name(pinfo.Name))
        except Exception:
            pass

        try:
            getter = pinfo.GetGetMethod(True)
            if getter is not None and minfo.Equals(getter):
                return True
        except Exception:
            pass

        try:
            setter = pinfo.GetSetMethod(True)
            if setter is not None and minfo.Equals(setter):
                return True
        except Exception:
            pass

    # Fallback: base-name string comparison against existing property names.
    return base_name in property_names


def extract_method(minfo, type_properties: Optional[List[Any]] = None) -> Optional[Dict[str, Any]]:
    """Extract method metadata in unified format.

    `type_properties` is the declaring type's `GetProperties()` result (as
    reflected by the caller); it is only consulted for get_/set_-named
    methods, to run gate 2 (backing-accessor de-duplication) below.
    """
    if not PYTHONNET_AVAILABLE:
        return None

    try:
        name = clean_type_name(minfo.Name)

        if name in ("Equals", "GetHashCode", "GetType", "ToString", "Finalize", "MemberwiseClone"):
            return None

        # Event accessors carry no arity/indexing semantics -- #136 only
        # concerns indexed property accessors -- so they stay unconditionally
        # filtered, same as before this fix.
        if name.startswith(("add_", "remove_")):
            return None

        is_getter = name.startswith("get_")
        is_setter = name.startswith("set_")

        if is_getter or is_setter:
            arity = len(minfo.GetParameters())

            # Gate 1 (arity): an ordinary zero-arg getter/single-arg setter is
            # already surfaced via GetProperties() -> extract_property(), so
            # only parameterized accessors (indexers, FLID accessors, etc.)
            # are candidates for recovery here.
            if is_getter and arity < 1:
                return None
            if is_setter and arity < 2:
                return None

            # Gate 2 (backing accessor): drop duplicates of a real indexer
            # PropertyInfo already documented in `properties`.
            if _is_property_backing_accessor(minfo, name, type_properties or []):
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

        # Infer output behavior
        output_behavior = infer_unified_output_behavior(
            method_or_property_name=name,
            return_type=return_type,
            library="liblcm",
            property_kind="",
            is_method=True
        )

        description = RECOVERED_ACCESSOR_DESCRIPTIONS.get(name) or generate_method_description(name, category)

        result = {
            "name": name,
            "signature": signature,
            "return_type": return_type,
            "output_behavior": output_behavior,
            "parameters": params,
        }

        if is_getter or is_setter:
            # Mechanical rule (domain review, #136): a single Int32 parameter
            # means the accessor is indexed (e.g. get_Properties(int ich));
            # an enum or any other single-parameter type (e.g.
            # get_IsNormalizedForm(FwNormalizationMode)) is an ordinary
            # parameterized accessor, not an index, so index_param_type is
            # only emitted when indexed is true.
            indexed = len(params) == 1 and params[0]["type"] == "Int32"
            result["indexed"] = indexed
            if indexed:
                result["index_param_type"] = params[0]["type"]

        result.update({
            "category": category,
            "description": description,
            "is_static": minfo.IsStatic,
            "is_virtual": minfo.IsVirtual,
            "is_abstract": minfo.IsAbstract
        })

        return result
    except Exception as e:
        log.debug(f"Error extracting method: {e}")
        return None


def categorize_method(name: str) -> str:
    """Categorize method by naming pattern."""
    # Recovered get_/set_ accessors (#136) use the lowercase compiler-emitted
    # prefix, not the "Get"/"Set" PascalCase convention checked below --
    # match them explicitly so e.g. get_Properties still lands in
    # "retrieval" rather than falling through to the generic "operation".
    if name.startswith("get_"):
        return METHOD_CATEGORY_RETRIEVAL
    if name.startswith("set_"):
        return METHOD_CATEGORY_MODIFICATION
    if name.startswith(("Get", "Find", "Search", "Retrieve", "Load", "Fetch")):
        return METHOD_CATEGORY_RETRIEVAL
    elif name.startswith(("Set", "Update", "Modify", "Change", "Apply")):
        return METHOD_CATEGORY_MODIFICATION
    elif name.startswith(("Create", "New", "Add", "Insert", "Make")):
        return METHOD_CATEGORY_CREATION
    elif name.startswith(("Delete", "Remove", "Clear", "Dispose")):
        return METHOD_CATEGORY_DELETION
    elif name.startswith(("Is", "Has", "Can", "Should", "Check")):
        return METHOD_CATEGORY_PREDICATE
    elif name.startswith(("Merge", "Copy", "Clone", "Move")):
        return METHOD_CATEGORY_MANIPULATION
    elif name.startswith(("Validate", "Verify")):
        return METHOD_CATEGORY_VALIDATION
    else:
        return METHOD_CATEGORY_OPERATION


def generate_method_description(name: str, category: str) -> str:
    """Generate a basic description for a method based on its name."""
    template = METHOD_CATEGORY_DESCRIPTIONS.get(category, f"Method: {name}")
    return template.format(name=name) if "{name}" in template else template


# ---- Type Extraction ---------------------------------------------------------

def categorize_type(name: str, namespace: str) -> str:
    """Categorize a type based on name and namespace."""
    # Repository pattern
    if "Repository" in name:
        return ENTITY_CATEGORY_REPOSITORY
    if "Factory" in name:
        return ENTITY_CATEGORY_FACTORY

    # By namespace
    ns_lower = namespace.lower()
    if "domainservices" in ns_lower:
        return ENTITY_CATEGORY_SERVICE
    if "infrastructure" in ns_lower:
        return ENTITY_CATEGORY_INFRASTRUCTURE

    # By name patterns (check long prefixes first)
    if name.startswith("IScrip") or name.startswith("IScr"):
        return ENTITY_CATEGORY_SCRIPTURE
    if name.startswith("IStText"):
        return ENTITY_CATEGORY_TEXT

    # Check single prefix matches using mapping
    for prefix, category in ENTITY_PREFIX_TO_CATEGORY.items():
        if name.startswith(prefix):
            return category

    return ENTITY_CATEGORY_GENERAL


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


def extract_type(t: Any, fetch_descriptions: bool = False) -> Optional[Dict[str, Any]]:
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
        # Reflected once and reused below for gate 2 of #136's method
        # recovery (identity/name check against backing get_/set_ accessors).
        type_properties: List[Any] = []

        try:
            type_properties = list(t.GetProperties(flags))
            for p in type_properties:
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
                method_info = extract_method(m, type_properties=type_properties)
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
                if _is_target_type(t):
                    types.append(t)

        except Exception as e:
            try:
                asm_name = assembly.GetName().Name
            except Exception:
                asm_name = "<unknown>"
            log.warning(f"Error reflecting types from assembly {asm_name}: {e}")

            # A ReflectionTypeLoadException still exposes every type that DID
            # load in e.Types (with a None entry for each one that did not), so
            # recover those instead of discarding the whole assembly. Without
            # this, a single unresolvable dependency silently dropped all of
            # SIL.LCModel.Core -- ITsString, ITsTextProps, ITsStrBldr,
            # ITsStrFactory, FwTextPropType and TsStringUtils among them -- and
            # left callers with no discoverable API for TsString work at all.
            recovered = 0
            try:
                for t in (getattr(e, 'Types', None) or []):
                    if _is_target_type(t):
                        types.append(t)
                        recovered += 1
            except Exception as recover_error:
                log.debug(f"  Could not recover partial types: {recover_error}")

            if recovered:
                log.info(f"  Recovered {recovered} types from {asm_name} despite load errors")

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

def build_api_documentation(assemblies: List[Any], fetch_descriptions: bool = False) -> Dict[str, Any]:
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


def stamp_document(api_doc: Dict[str, Any], dll_dir: Path, version: str = "0.0.0") -> Dict[str, Any]:
    """Add schema and generation metadata to the document."""
    return {
        "_schema": SCHEMA_VERSION,
        "_source": {
            "type": "liblcm",
            "version": version,
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

        # Detect version
        version = get_liblcm_version(assemblies)
        log.info(f"Detected LibLCM version: {version}")

        # Build documentation
        api_doc = build_api_documentation(assemblies, args.fetch_descriptions)

        # Add metadata
        stamped_doc = stamp_document(api_doc, dll_dir, version)

        # Ensure output directory exists
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write output
        stamped_doc = sort_json_arrays(stamped_doc)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(stamped_doc, f, indent=2, ensure_ascii=False, sort_keys=True)

        log.info(f"API documentation written to: {output_path}")

        # Print summary
        if not args.quiet:
            print("\n[DONE] LibLCM Extraction Complete")
            print(f"  Output: {output_path}")
            print(f"  Types: {api_doc['metadata']['total_types']}")
            print(f"  Interfaces: {api_doc['metadata']['total_interfaces']}")
            print(f"  Classes: {api_doc['metadata']['total_classes']}")
            print(f"  Methods: {api_doc['metadata']['total_methods']}")
            print(f"  Properties: {api_doc['metadata']['total_properties']}")
            print(f"  Relationships: {api_doc['metadata']['total_relationships']}")
            print("\n  Categories:")
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
