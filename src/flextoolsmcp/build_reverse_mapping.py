#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build Reverse Mapping: LibLCM -> FlexLibs

Creates a reverse index mapping LibLCM entities/properties/methods to their
FlexLibs Python wrappers. This enables:
- Showing "Python way" when viewing LibLCM docs
- Suggesting FlexLibs alternatives
- Bidirectional code conversion

Usage:
    python src/build_reverse_mapping.py
    python src/build_reverse_mapping.py --output index/reverse_mapping.json
"""

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple, Optional

if __package__:
    from .json_utils import sort_json_arrays
    from .server.versioning import find_latest_versioned_api_file
    from .file_utils import get_project_root, get_index_dir, load_json, save_json
else:
    from json_utils import sort_json_arrays
    from server.versioning import find_latest_versioned_api_file
    from file_utils import get_project_root, get_index_dir, load_json, save_json


# ============================================================
# Constants (avoid stringly-typed code)
# ============================================================
# LibLCM mapping field names
KEY_MAPPING_TYPE = "mapping_type"
KEY_LCM_DEPENDENCIES = "lcm_dependencies"
KEY_METHODS_CALLED = "methods_called"
KEY_PROPERTIES_ACCESSED = "properties_accessed"
KEY_FACTORIES_USED = "factories_used"
KEY_REPOSITORIES_USED = "repositories_used"

# Result structure keys
KEY_PROPERTIES = "properties"
KEY_METHODS = "methods"
KEY_FACTORIES = "factories"
KEY_REPOSITORIES = "repositories"
KEY_BY_FLEXLIBS_CLASS = "by_flexlibs_class"
KEY_BY_LIBLCM_ENTITY = "by_liblcm_entity"
KEY_STATISTICS = "statistics"

# Mapping type constant
MAPPING_TYPE_PURE_PYTHON = "pure_python"


def extract_interface_from_property(prop_str: str) -> str:
    """Extract interface name from property access pattern.

    Examples:
        'SensesOS (OwningSequence)' -> 'SensesOS'
        'Gloss.get_String()' -> 'Gloss'
    """
    # Remove suffix annotations like (OwningSequence), (ReferenceAtomic), etc.
    match = re.match(r'^(\w+)', prop_str)
    return match.group(1) if match else prop_str


def extract_interface_from_method(method_str: str) -> str:
    """Extract method name from method call pattern.

    Examples:
        '.Add()' -> 'Add'
        '.get_String()' -> 'get_String'
    """
    match = re.match(r'^\.?(\w+)', method_str)
    return match.group(1) if match else method_str


def is_interface(name: str) -> bool:
    """Check if a name looks like a LibLCM interface (starts with I and has uppercase letter)."""
    # Exclude utility classes that aren't really interfaces
    utility_classes = {
        "TsStringUtils", "ReflectionHelper", "ServiceLocator",
        "CopyValuesHelper", "UndoableUnitOfWorkHelper"
    }
    if name in utility_classes:
        return False

    # Include I* interfaces, *Factory, *Repository
    return (
        (name.startswith("I") and len(name) > 1 and name[1].isupper()) or
        name.endswith("Factory") or
        name.endswith("Repository")
    )


def is_exception_class(name: str) -> bool:
    """Check if a class is an exception/error class to filter out."""
    return (
        name.startswith("FP_") or
        "Error" in name or
        "Exception" in name
    )


def _index_wrapper_mapping(
    result_dict: Dict,
    items: List[str],
    wrapper_info: Dict,
    extractor_fn,
    stats_key: str,
    statistics: Dict
):
    """Index wrapper info by extracted item names and update statistics.

    DRY helper to eliminate repeated pattern in build_reverse_mapping():
    for each item, extract name, append wrapper_info, increment stats.

    Args:
        result_dict: The result["properties/methods/factories/repositories"] dict
        items: List of items to process
        wrapper_info: The wrapper info dict to append (will be copied per item)
        extractor_fn: Function to extract name from item (e.g., extract_interface_from_property)
        stats_key: Statistics key to increment (e.g., "properties_mapped")
        statistics: The statistics dict to update
    """
    for item in items:
        name = extractor_fn(item)
        result_dict[name].append(wrapper_info.copy())
        statistics[stats_key] += 1


def _add_liblcm_mapping(
    by_liblcm_entity: Dict,
    dep: str,
    wrapper_dict: Dict,
    key: str
):
    """Add or merge FlexLibs wrapper info to LibLCM entity mapping.

    Handles collision when multiple FlexLibs classes wrap the same interface.

    Args:
        by_liblcm_entity: Result["by_liblcm_entity"] dict
        dep: LibLCM entity name
        wrapper_dict: {"class": class_name, "methods": [method_list]}
        key: "flexlibs_2" or "flexlibs_stable"
    """
    if dep not in by_liblcm_entity:
        by_liblcm_entity[dep] = {"flexlibs_stable": None, "flexlibs_2": None}

    existing = by_liblcm_entity[dep][key]
    if existing is None:
        by_liblcm_entity[dep][key] = wrapper_dict
    else:
        # Multiple wrappers: convert to list if needed
        if isinstance(existing, dict):
            by_liblcm_entity[dep][key] = [existing]
        by_liblcm_entity[dep][key].append(wrapper_dict)


def build_reverse_mapping(
    flexicon_path: Path,
    flexlibs_path: Path | None = None,
    liblcm_path: Path | None = None
) -> Dict[str, Any]:
    """Build reverse mapping from LibLCM -> FlexLibs.

    Returns a structure like:
    {
        "properties": {
            "SensesOS": [
                {"class": "LexEntryOperations", "method": "GetSenses", "mapping_type": "direct"}
            ]
        },
        "methods": {
            "Add": [
                {"class": "LexSenseOperations", "method": "AddAnthroCode", "mapping_type": "direct"}
            ]
        },
        "by_class": {
            "LexEntryOperations": {
                "wraps": ["ILexEntry"],
                "methods": {...}
            }
        }
    }
    """

    flexicon = load_json(flexicon_path)
    flexlibs = load_json(flexlibs_path) if flexlibs_path and flexlibs_path.exists() else None
    liblcm = load_json(liblcm_path) if liblcm_path and liblcm_path.exists() else None

    # Initialize result structure
    result = {
        "_schema": "reverse-mapping/1.0",
        KEY_PROPERTIES: defaultdict(list),  # property_name -> [FlexLibs wrappers]
        KEY_METHODS: defaultdict(list),      # method_name -> [FlexLibs wrappers]
        KEY_FACTORIES: defaultdict(list),    # factory_name -> [FlexLibs wrappers]
        KEY_REPOSITORIES: defaultdict(list), # repo_name -> [FlexLibs wrappers]
        KEY_BY_FLEXLIBS_CLASS: {},           # FlexLibs class -> what it wraps
        KEY_BY_LIBLCM_ENTITY: defaultdict(lambda: {"flexlibs_stable": None, "flexlibs_2": None}),
        KEY_STATISTICS: {
            "total_mappings": 0,
            "properties_mapped": 0,
            "methods_mapped": 0,
            "factories_mapped": 0,
            "repositories_mapped": 0
        }
    }

    # Process Flexicon entities
    print("[INFO] Processing Flexicon mappings...")
    for class_name, entity in flexicon.get("entities", {}).items():
        # Skip exception/error classes
        if is_exception_class(class_name):
            continue

        # Filter and deduplicate LCM dependencies - keep only interface-like names
        raw_deps = entity.get(KEY_LCM_DEPENDENCIES, [])
        lcm_deps = [d for d in set(raw_deps) if is_interface(d)]  # Deduplicate via set, filter, then list

        # Track what LibLCM interfaces this class wraps
        class_info = {
            "wraps_interfaces": lcm_deps,
            "category": entity.get("category", "general"),
            "method_count": len(entity.get("methods", [])),
            "methods": {}
        }

        for method in entity.get("methods", []):
            method_name = method.get("name", "")
            lcm_mapping = method.get("lcm_mapping", {})
            mapping_type = lcm_mapping.get(KEY_MAPPING_TYPE, MAPPING_TYPE_PURE_PYTHON)

            if mapping_type == MAPPING_TYPE_PURE_PYTHON:
                continue  # Skip pure Python methods - no LibLCM mapping

            wrapper_info = {
                "class": class_name,
                "method": method_name,
                KEY_MAPPING_TYPE: mapping_type,
                "signature": method.get("signature", ""),
                "description": method.get("summary", "") or method.get("description", "")[:100]
            }

            # Index by properties accessed
            if KEY_PROPERTIES_ACCESSED in lcm_mapping:
                _index_wrapper_mapping(
                    result[KEY_PROPERTIES],
                    lcm_mapping[KEY_PROPERTIES_ACCESSED],
                    wrapper_info,
                    extract_interface_from_property,
                    "properties_mapped",
                    result[KEY_STATISTICS]
                )

            # Index by methods called
            if KEY_METHODS_CALLED in lcm_mapping:
                _index_wrapper_mapping(
                    result[KEY_METHODS],
                    lcm_mapping[KEY_METHODS_CALLED],
                    wrapper_info,
                    extract_interface_from_method,
                    "methods_mapped",
                    result[KEY_STATISTICS]
                )

            # Index by factories used
            if KEY_FACTORIES_USED in lcm_mapping:
                for factory in lcm_mapping[KEY_FACTORIES_USED]:
                    result[KEY_FACTORIES][factory].append(wrapper_info.copy())
                    result[KEY_STATISTICS]["factories_mapped"] += 1

            # Index by repositories used
            if KEY_REPOSITORIES_USED in lcm_mapping:
                for repo in lcm_mapping[KEY_REPOSITORIES_USED]:
                    result[KEY_REPOSITORIES][repo].append(wrapper_info.copy())
                    result[KEY_STATISTICS]["repositories_mapped"] += 1

            # Add to class info
            class_info["methods"][method_name] = {
                KEY_MAPPING_TYPE: mapping_type,
                "lcm_calls": (
                    lcm_mapping.get(KEY_PROPERTIES_ACCESSED, []) +
                    lcm_mapping.get(KEY_METHODS_CALLED, [])
                )
            }

            result[KEY_STATISTICS]["total_mappings"] += 1

        result[KEY_BY_FLEXLIBS_CLASS][class_name] = class_info

        # Link LibLCM entities to this FlexLibs class
        for dep in lcm_deps:
            wrapper_dict = {
                "class": class_name,
                "methods": list(class_info["methods"].keys())
            }
            _add_liblcm_mapping(result[KEY_BY_LIBLCM_ENTITY], dep, wrapper_dict, "flexlibs_2")

    # Process FlexLibs stable if available
    if flexlibs:
        print("[INFO] Processing FlexLibs stable mappings...")
        for class_name, entity in flexlibs.get("entities", {}).items():
            lcm_deps = entity.get(KEY_LCM_DEPENDENCIES, [])

            for dep in lcm_deps:
                wrapper_dict = {
                    "class": class_name,
                    "methods": [m["name"] for m in entity.get("methods", [])]
                }
                _add_liblcm_mapping(result[KEY_BY_LIBLCM_ENTITY], dep, wrapper_dict, "flexlibs_stable")

    # Convert defaultdicts to regular dicts for JSON serialization
    result[KEY_PROPERTIES] = dict(result[KEY_PROPERTIES])
    result[KEY_METHODS] = dict(result[KEY_METHODS])
    result[KEY_FACTORIES] = dict(result[KEY_FACTORIES])
    result[KEY_REPOSITORIES] = dict(result[KEY_REPOSITORIES])
    result[KEY_BY_LIBLCM_ENTITY] = dict(result[KEY_BY_LIBLCM_ENTITY])

    return result


def add_python_wrappers_to_liblcm(
    liblcm_path: Path,
    reverse_mapping: Dict,
    output_path: Path | None = None
):
    """Add python_wrappers field to LibLCM entities."""

    liblcm = load_json(liblcm_path)

    print("[INFO] Adding python_wrappers to LibLCM entities...")

    wrappers_added = 0
    for entity_id, entity in liblcm.get("entities", {}).items():
        if entity_id in reverse_mapping[KEY_BY_LIBLCM_ENTITY]:
            wrapper_info = reverse_mapping[KEY_BY_LIBLCM_ENTITY][entity_id]
            entity["python_wrappers"] = wrapper_info
            wrappers_added += 1

    print(f"[INFO] Added python_wrappers to {wrappers_added} entities")

    # Save
    output = output_path or liblcm_path
    save_json(liblcm, output)

    return liblcm


def print_summary(result: Dict):
    """Print summary statistics."""
    stats = result[KEY_STATISTICS]

    print("\n" + "=" * 50)
    print("Reverse Mapping Summary")
    print("=" * 50)
    print(f"  Total mappings: {stats['total_mappings']}")
    print(f"  Properties mapped: {stats['properties_mapped']}")
    print(f"  Methods mapped: {stats['methods_mapped']}")
    print(f"  Factories mapped: {stats['factories_mapped']}")
    print(f"  Repositories mapped: {stats['repositories_mapped']}")
    print(f"  FlexLibs classes: {len(result[KEY_BY_FLEXLIBS_CLASS])}")
    print(f"  LibLCM entities with wrappers: {len(result[KEY_BY_LIBLCM_ENTITY])}")

    # Top wrapped properties
    print("\nTop 10 wrapped properties:")
    sorted_props = sorted(result[KEY_PROPERTIES].items(), key=lambda x: len(x[1]), reverse=True)[:10]
    for prop, wrappers in sorted_props:
        print(f"  {prop}: {len(wrappers)} wrappers")


def main():
    parser = argparse.ArgumentParser(
        description="Build reverse mapping from LibLCM to FlexLibs"
    )
    parser.add_argument(
        "--output",
        default="index/reverse_mapping.json",
        help="Output path for reverse mapping JSON"
    )
    parser.add_argument(
        "--update-liblcm",
        action="store_true",
        help="Also update LibLCM index with python_wrappers field"
    )

    args = parser.parse_args()

    root = get_project_root()
    index_dir = get_index_dir()
    flexlibs_dir = index_dir / "flexlibs"
    liblcm_dir = index_dir / "liblcm"

    # Find latest versioned API files
    flexicon_path = find_latest_versioned_api_file(flexlibs_dir, "flexicon_api")
    flexlibs_path = find_latest_versioned_api_file(flexlibs_dir, "flexlibs_api")
    liblcm_path = find_latest_versioned_api_file(liblcm_dir, "liblcm_api")

    if not flexicon_path:
        print("[ERROR] Flexicon API file not found")
        return 1
    if not liblcm_path:
        print("[ERROR] LibLCM API file not found")
        return 1

    # Type narrowing: checks above ensure these are not None
    assert flexicon_path is not None
    assert liblcm_path is not None

    # Extract version from liblcm_path for versioned filename
    version_match = re.search(r'liblcm_api_v(\d+\.\d+\.\d+)', str(liblcm_path))
    if version_match:
        liblcm_version = version_match.group(1)
        output_filename = f"reverse_mapping_liblcm-v{liblcm_version}.json"
        output_path = index_dir / output_filename
    else:
        output_path = root / args.output

    # Build reverse mapping
    result = build_reverse_mapping(flexicon_path, flexlibs_path, liblcm_path)

    # Save reverse mapping
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(result, output_path)

    # Print summary
    print_summary(result)

    # Optionally update LibLCM with python_wrappers
    if args.update_liblcm:
        add_python_wrappers_to_liblcm(liblcm_path, result)

    print("\n[DONE] Reverse mapping complete")
    return 0


if __name__ == "__main__":
    exit(main())
