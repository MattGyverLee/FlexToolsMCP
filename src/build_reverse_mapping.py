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
from typing import Dict, List, Any, Set


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def load_json(path: Path) -> Dict:
    """Load a JSON file with UTF-8 encoding."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(data: Dict, path: Path):
    """Save a JSON file with UTF-8 encoding."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[INFO] Saved: {path}")


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


def build_reverse_mapping(
    flexlibs2_path: Path,
    flexlibs_path: Path = None,
    liblcm_path: Path = None
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

    flexlibs2 = load_json(flexlibs2_path)
    flexlibs = load_json(flexlibs_path) if flexlibs_path and flexlibs_path.exists() else None
    liblcm = load_json(liblcm_path) if liblcm_path and liblcm_path.exists() else None

    # Initialize result structure
    result = {
        "_schema": "reverse-mapping/1.0",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "properties": defaultdict(list),  # property_name -> [FlexLibs wrappers]
        "methods": defaultdict(list),      # method_name -> [FlexLibs wrappers]
        "factories": defaultdict(list),    # factory_name -> [FlexLibs wrappers]
        "repositories": defaultdict(list), # repo_name -> [FlexLibs wrappers]
        "by_flexlibs_class": {},           # FlexLibs class -> what it wraps
        "by_liblcm_entity": defaultdict(lambda: {"flexlibs_stable": None, "flexlibs_2": None}),
        "statistics": {
            "total_mappings": 0,
            "properties_mapped": 0,
            "methods_mapped": 0,
            "factories_mapped": 0,
            "repositories_mapped": 0
        }
    }

    # Process FlexLibs 2.0 entities
    print("[INFO] Processing FlexLibs 2.0 mappings...")
    for class_name, entity in flexlibs2.get("entities", {}).items():
        # Skip exception/error classes
        if is_exception_class(class_name):
            continue

        # Filter and deduplicate LCM dependencies - keep only interface-like names
        raw_deps = entity.get("lcm_dependencies", [])
        lcm_deps = list(set(d for d in raw_deps if is_interface(d)))

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
            mapping_type = lcm_mapping.get("mapping_type", "pure_python")

            if mapping_type == "pure_python":
                continue  # Skip pure Python methods - no LibLCM mapping

            wrapper_info = {
                "class": class_name,
                "method": method_name,
                "mapping_type": mapping_type,
                "signature": method.get("signature", ""),
                "description": method.get("summary", "") or method.get("description", "")[:100]
            }

            # Index by properties accessed
            for prop in lcm_mapping.get("properties_accessed", []):
                prop_name = extract_interface_from_property(prop)
                result["properties"][prop_name].append(wrapper_info.copy())
                result["statistics"]["properties_mapped"] += 1

            # Index by methods called
            for meth in lcm_mapping.get("methods_called", []):
                meth_name = extract_interface_from_method(meth)
                result["methods"][meth_name].append(wrapper_info.copy())
                result["statistics"]["methods_mapped"] += 1

            # Index by factories used
            for factory in lcm_mapping.get("factories_used", []):
                result["factories"][factory].append(wrapper_info.copy())
                result["statistics"]["factories_mapped"] += 1

            # Index by repositories used
            for repo in lcm_mapping.get("repositories_used", []):
                result["repositories"][repo].append(wrapper_info.copy())
                result["statistics"]["repositories_mapped"] += 1

            # Add to class info
            class_info["methods"][method_name] = {
                "mapping_type": mapping_type,
                "lcm_calls": (
                    lcm_mapping.get("properties_accessed", []) +
                    lcm_mapping.get("methods_called", [])
                )
            }

            result["statistics"]["total_mappings"] += 1

        result["by_flexlibs_class"][class_name] = class_info

        # Link LibLCM entities to this FlexLibs class
        for dep in lcm_deps:
            if dep not in result["by_liblcm_entity"]:
                result["by_liblcm_entity"][dep] = {"flexlibs_stable": None, "flexlibs_2": None}

            if result["by_liblcm_entity"][dep]["flexlibs_2"] is None:
                result["by_liblcm_entity"][dep]["flexlibs_2"] = {
                    "class": class_name,
                    "methods": list(class_info["methods"].keys())
                }
            else:
                # Multiple FlexLibs classes wrap the same interface
                existing = result["by_liblcm_entity"][dep]["flexlibs_2"]
                if isinstance(existing, dict):
                    # Convert to list
                    result["by_liblcm_entity"][dep]["flexlibs_2"] = [existing]
                result["by_liblcm_entity"][dep]["flexlibs_2"].append({
                    "class": class_name,
                    "methods": list(class_info["methods"].keys())
                })

    # Process FlexLibs stable if available
    if flexlibs:
        print("[INFO] Processing FlexLibs stable mappings...")
        for class_name, entity in flexlibs.get("entities", {}).items():
            lcm_deps = entity.get("lcm_dependencies", [])

            for dep in lcm_deps:
                if dep not in result["by_liblcm_entity"]:
                    result["by_liblcm_entity"][dep] = {"flexlibs_stable": None, "flexlibs_2": None}

                if result["by_liblcm_entity"][dep]["flexlibs_stable"] is None:
                    result["by_liblcm_entity"][dep]["flexlibs_stable"] = {
                        "class": class_name,
                        "methods": [m["name"] for m in entity.get("methods", [])]
                    }

    # Convert defaultdicts to regular dicts for JSON serialization
    result["properties"] = dict(result["properties"])
    result["methods"] = dict(result["methods"])
    result["factories"] = dict(result["factories"])
    result["repositories"] = dict(result["repositories"])
    result["by_liblcm_entity"] = dict(result["by_liblcm_entity"])

    return result


def add_python_wrappers_to_liblcm(
    liblcm_path: Path,
    reverse_mapping: Dict,
    output_path: Path = None
):
    """Add python_wrappers field to LibLCM entities."""

    liblcm = load_json(liblcm_path)

    print("[INFO] Adding python_wrappers to LibLCM entities...")

    wrappers_added = 0
    for entity_id, entity in liblcm.get("entities", {}).items():
        if entity_id in reverse_mapping["by_liblcm_entity"]:
            wrapper_info = reverse_mapping["by_liblcm_entity"][entity_id]
            entity["python_wrappers"] = wrapper_info
            wrappers_added += 1

    print(f"[INFO] Added python_wrappers to {wrappers_added} entities")

    # Update metadata
    liblcm["_python_wrappers_added"] = datetime.now(timezone.utc).isoformat()

    # Save
    output = output_path or liblcm_path
    save_json(liblcm, output)

    return liblcm


def print_summary(result: Dict):
    """Print summary statistics."""
    stats = result["statistics"]

    print("\n" + "=" * 50)
    print("Reverse Mapping Summary")
    print("=" * 50)
    print(f"  Total mappings: {stats['total_mappings']}")
    print(f"  Properties mapped: {stats['properties_mapped']}")
    print(f"  Methods mapped: {stats['methods_mapped']}")
    print(f"  Factories mapped: {stats['factories_mapped']}")
    print(f"  Repositories mapped: {stats['repositories_mapped']}")
    print(f"  FlexLibs classes: {len(result['by_flexlibs_class'])}")
    print(f"  LibLCM entities with wrappers: {len(result['by_liblcm_entity'])}")

    # Top wrapped properties
    print("\nTop 10 wrapped properties:")
    sorted_props = sorted(result["properties"].items(), key=lambda x: len(x[1]), reverse=True)[:10]
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

    flexlibs2_path = root / "index" / "flexlibs" / "flexlibs2_api.json"
    flexlibs_path = root / "index" / "flexlibs" / "flexlibs_api.json"
    liblcm_path = root / "index" / "liblcm" / "flex-api-enhanced.json"
    output_path = root / args.output

    # Build reverse mapping
    result = build_reverse_mapping(flexlibs2_path, flexlibs_path, liblcm_path)

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
