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
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone


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
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "_description": "Maps properties to interfaces, identifying pythonnet casting requirements",
        "properties": {},
        "polymorphic_collections": {},
        "interface_hierarchy": {},
    }

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


def main():
    """Build and save the casting index."""
    index_dir = Path(__file__).parent.parent / "index"
    liblcm_path = index_dir / "liblcm" / "liblcm_api.json"

    if not liblcm_path.exists():
        print(f"[ERROR] LibLCM API not found at {liblcm_path}")
        return 1

    print("[INFO] Building casting index...")
    casting_index = build_casting_index(liblcm_path)

    # Save the index
    output_path = index_dir / "casting_index.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(casting_index, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"[OK] Casting index saved to {output_path}")
    print(f"     Properties with casting requirements: {len(casting_index['properties'])}")
    print(f"     Polymorphic collections documented: {len(casting_index['polymorphic_collections'])}")
    print(f"     Interface hierarchies: {len(casting_index['interface_hierarchy'])}")

    return 0


if __name__ == "__main__":
    exit(main())
