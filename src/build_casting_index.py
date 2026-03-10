#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build Casting Index for FlexToolsMCP

Generates an index that maps properties to their defining interfaces,
with information about which base interfaces DON'T have the property.
This helps detect when pythonnet casting is required.

Usage:
    python src/build_casting_index.py
"""

import json
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

from .json_utils import sort_json_arrays


def build_casting_index(liblcm_path: Path) -> dict:
    """
    Build a casting index from the LibLCM API data.

    The index maps property names to:
    - Which interfaces define that property
    - Which base interfaces DON'T have it (requiring casting)
    - Collections that return base-typed objects
    """

    with open(liblcm_path, "r", encoding="utf-8") as f:
        liblcm = json.load(f)

    entities = liblcm.get("entities", {})

    # Build interface hierarchy (child -> parents)
    interface_parents = {}  # interface -> list of interfaces it extends
    interface_children = defaultdict(list)  # interface -> list of interfaces that extend it

    # Build property ownership map
    property_to_interfaces = defaultdict(set)  # property_name -> set of interfaces that have it
    interface_properties = {}  # interface -> set of its own properties (not inherited)

    # Known polymorphic collections (collection property -> base type returned)
    polymorphic_collections = {
        "MorphoSyntaxAnalysesOC": "IMoMorphSynAnalysis",
        "AlternateFormsOS": "IMoForm",
        "LexemeFormOA": "IMoForm",
        "AllomorphsOS": "IMoForm",
        "FormOS": "IMoForm",
        "AnalysesOC": "IWfiAnalysis",
        "MorphBundlesOS": "IWfiMorphBundle",
        "MeaningsOC": "IWfiGloss",
    }

    # First pass: build hierarchy and collect properties
    for entity_name, entity_data in entities.items():
        if entity_data.get("type") != "interface":
            continue

        # Get parent interfaces
        interfaces = entity_data.get("interfaces", [])
        interface_parents[entity_name] = interfaces

        for parent in interfaces:
            interface_children[parent].append(entity_name)

        # Collect properties defined on this interface
        props = set()
        for prop in entity_data.get("properties", []):
            prop_name = prop.get("name", "")
            if prop_name:
                props.add(prop_name)
                property_to_interfaces[prop_name].add(entity_name)

        interface_properties[entity_name] = props

    # Build the casting index
    casting_index = {
        "_schema": "casting-index/1.0",
        "_description": "Maps properties to interfaces, identifying pythonnet casting requirements",
        "properties": {},
        "property_to_concrete_mapping": {},
        "class_name_mapping": {},
        "polymorphic_collections": {},
        "interface_hierarchy": {},
    }

    # Build class name -> interface mapping
    # ClassName is typically the interface name without the "I" prefix and with proper casing
    for entity_name, entity_data in entities.items():
        if entity_data.get("type") == "interface":
            # Convert interface name to ClassName (IMoStemMsa -> MoStemMsa)
            if entity_name.startswith("I"):
                class_name = entity_name[1:]
                casting_index["class_name_mapping"][class_name] = entity_name

    # For each property, determine if it requires casting
    for prop_name, defining_interfaces in property_to_interfaces.items():
        # Skip very common properties that are on base interfaces
        if len(defining_interfaces) > 50:
            continue

        # Find common base interfaces that DON'T have this property
        base_interfaces_without = set()

        for interface in defining_interfaces:
            # Check if any parent interface has this property
            parents = interface_parents.get(interface, [])
            for parent in parents:
                if parent not in defining_interfaces:
                    # Parent doesn't have this property - casting needed
                    base_interfaces_without.add(parent)

        if base_interfaces_without:
            casting_index["properties"][prop_name] = {
                "defined_on": sorted(defining_interfaces),
                "requires_cast_from": sorted(base_interfaces_without),
                "pythonnet_warning": True,
            }

    # Build reverse mapping: property -> concrete types that have it
    # This is built from polymorphic collections and interface hierarchies
    for prop_name, defining_interfaces in property_to_interfaces.items():
        # For each defined interface, find all concrete subtypes
        concrete_types_with_prop = set()

        for interface in defining_interfaces:
            # Add the interface itself (concrete type)
            concrete_types_with_prop.add(interface)
            # Add all descendants (they inherit the property)
            def get_all_descendants(iface):
                descendants = set()
                for child in interface_children.get(iface, []):
                    descendants.add(child)
                    descendants.update(get_all_descendants(child))
                return descendants
            concrete_types_with_prop.update(get_all_descendants(interface))

        if concrete_types_with_prop and len(concrete_types_with_prop) <= 20:
            # Only include if not too many (avoid noise)
            casting_index["property_to_concrete_mapping"][prop_name] = {
                "available_on": sorted(concrete_types_with_prop),
                "note": "Property is available on these concrete types and their descendants"
            }

    # Add polymorphic collections info
    for collection_name, base_type in polymorphic_collections.items():
        children = interface_children.get(base_type, [])

        # Get properties unique to each child
        child_unique_props = {}
        base_props = interface_properties.get(base_type, set())

        for child in children:
            child_props = interface_properties.get(child, set())
            unique = child_props - base_props
            if unique:
                child_unique_props[child] = sorted(unique)

        if child_unique_props:
            casting_index["polymorphic_collections"][collection_name] = {
                "base_type": base_type,
                "concrete_types": children,
                "unique_properties_by_type": child_unique_props,
                "casting_hint": f"Elements are typed as {base_type}. Cast to concrete type to access derived properties.",
            }

    # Add interface hierarchy for key base types
    key_base_types = [
        "IMoMorphSynAnalysis", "IMoForm", "ICmPossibility",
        "IWfiAnalysis", "ICmAnnotation"
    ]

    for base_type in key_base_types:
        if base_type in interface_children:
            casting_index["interface_hierarchy"][base_type] = {
                "derived_interfaces": sorted(interface_children[base_type]),
                "common_pattern": f"Check obj.ClassName then cast: Interface(obj)",
            }

    return casting_index


def find_latest_liblcm(liblcm_dir: Path) -> tuple[Path, str]:
    """Find the latest LibLCM API file and extract its version."""
    pattern = re.compile(r"liblcm_api_v(\d+\.\d+\.\d+)\.json$")
    versions = {}

    for file in liblcm_dir.glob("liblcm_api_v*.json"):
        match = pattern.match(file.name)
        if match:
            version = match.group(1)
            versions[version] = file

    if not versions:
        return None, None

    latest = sorted(versions.keys())[-1]
    return versions[latest], latest


def main():
    """Build and save the casting index."""
    index_dir = Path(__file__).parent.parent / "index"
    liblcm_dir = index_dir / "liblcm"

    # Find latest LibLCM version
    liblcm_path, liblcm_version = find_latest_liblcm(liblcm_dir)

    if not liblcm_path:
        print(f"[ERROR] No LibLCM API files found in {liblcm_dir}")
        return 1

    print("[INFO] Building casting index...")
    casting_index = build_casting_index(liblcm_path)

    # Save with version suffix
    output_filename = f"casting_index_liblcm-v{liblcm_version}.json"
    output_path = index_dir / output_filename
    casting_index = sort_json_arrays(casting_index)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(casting_index, f, indent=2, ensure_ascii=False, sort_keys=True)

    # Print summary
    print(f"[OK] Casting index saved to {output_path}")
    print(f"     Properties with casting requirements: {len(casting_index['properties'])}")
    print(f"     Property-to-concrete mappings: {len(casting_index['property_to_concrete_mapping'])}")
    print(f"     ClassName-to-interface mappings: {len(casting_index['class_name_mapping'])}")
    print(f"     Polymorphic collections documented: {len(casting_index['polymorphic_collections'])}")
    print(f"     Interface hierarchies: {len(casting_index['interface_hierarchy'])}")

    return 0


if __name__ == "__main__":
    exit(main())
