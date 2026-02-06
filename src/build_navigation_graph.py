#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build Navigation Graph from LibLCM Relationships

Extracts parent/child/reference relationships from LibLCM properties and
builds a navigation graph for pathfinding between object types.

Usage:
    python src/build_navigation_graph.py
    python src/build_navigation_graph.py --output index/navigation_graph.json
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Set, Tuple, Optional


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


def extract_relationships(liblcm: Dict) -> Dict[str, Any]:
    """Extract relationships from LibLCM properties.

    Returns a structure with:
    - entities: dict of entity_id -> relationships
    - graph: adjacency list for pathfinding
    """

    # Relationship type mapping
    REL_TYPES = {
        "owns_atomic": {"direction": "child", "cardinality": "one"},
        "owns_sequence": {"direction": "child", "cardinality": "many", "ordered": True},
        "owns_collection": {"direction": "child", "cardinality": "many", "ordered": False},
        "references_atomic": {"direction": "reference", "cardinality": "one"},
        "references_sequence": {"direction": "reference", "cardinality": "many", "ordered": True},
        "references_collection": {"direction": "reference", "cardinality": "many", "ordered": False},
    }

    entities = {}
    graph = defaultdict(list)  # entity_id -> [(target_id, via, relationship_type)]
    reverse_graph = defaultdict(list)  # For building parent relationships

    print("[INFO] Extracting relationships from LibLCM properties...")

    for entity_id, entity in liblcm.get("entities", {}).items():
        relationships = {
            "children": [],
            "parents": [],
            "references": [],
            "referenced_by": []
        }

        for prop in entity.get("properties", []):
            rel_type = prop.get("relationship", "")
            target_type = prop.get("target_type")
            prop_name = prop.get("name", "")
            kind = prop.get("kind", "")

            if rel_type not in REL_TYPES or not target_type:
                continue

            rel_info = REL_TYPES[rel_type]

            # Build access pattern
            access_pattern = f"{entity_id.lower().replace('i', '', 1)}.{prop_name}"

            relationship = {
                "target": target_type,
                "via": prop_name,
                "access_pattern": access_pattern,
                "cardinality": rel_info["cardinality"],
                "kind": kind
            }
            if rel_info.get("ordered"):
                relationship["ordered"] = True

            if rel_info["direction"] == "child":
                relationships["children"].append(relationship)
                # Add to graph
                graph[entity_id].append((target_type, prop_name, "owns"))
                # Build reverse relationship
                reverse_graph[target_type].append((entity_id, prop_name, "owned_by"))
            else:
                relationships["references"].append(relationship)
                graph[entity_id].append((target_type, prop_name, "references"))
                reverse_graph[target_type].append((entity_id, prop_name, "referenced_by"))

        entities[entity_id] = relationships

    # Add parent relationships from reverse graph
    for entity_id in entities:
        if entity_id in reverse_graph:
            for parent_id, via, rel_type in reverse_graph[entity_id]:
                if rel_type == "owned_by":
                    entities[entity_id]["parents"].append({
                        "target": parent_id,
                        "via": via,
                        "relationship": "owned_by"
                    })
                else:
                    entities[entity_id]["referenced_by"].append({
                        "target": parent_id,
                        "via": via,
                        "relationship": "referenced_by"
                    })

    return {
        "entities": entities,
        "graph": dict(graph),
        "reverse_graph": dict(reverse_graph)
    }


def find_path(
    graph: Dict[str, List],
    start: str,
    end: str,
    max_depth: int = 5
) -> Optional[List[Dict]]:
    """Find path between two entity types using BFS.

    Returns list of steps: [{"from": X, "to": Y, "via": prop, "type": owns/references}]
    """
    if start == end:
        return []

    # Normalize names (handle with/without I prefix)
    def normalize(name: str) -> str:
        if not name.startswith("I"):
            name = "I" + name
        return name

    start = normalize(start)
    end = normalize(end)

    # BFS
    from collections import deque
    queue = deque([(start, [])])
    visited = {start}

    while queue:
        current, path = queue.popleft()

        if len(path) >= max_depth:
            continue

        for target, via, rel_type in graph.get(current, []):
            if target == end:
                return path + [{"from": current, "to": target, "via": via, "type": rel_type}]

            if target not in visited:
                visited.add(target)
                queue.append((target, path + [{"from": current, "to": target, "via": via, "type": rel_type}]))

    return None


def precompute_common_paths(graph: Dict[str, List]) -> Dict[str, Any]:
    """Precompute paths for common object pairs."""

    common_pairs = [
        # === Lexicon Navigation (Core) ===
        ("ILexEntry", "ILexSense"),
        ("ILexEntry", "ILexExampleSentence"),
        ("ILexEntry", "IMoForm"),
        ("ILexSense", "ILexExampleSentence"),
        ("ILexSense", "ICmSemanticDomain"),
        ("ILexDb", "ILexEntry"),

        # === Lexicon Navigation (Extended) ===
        ("ILexEntry", "ILexEtymology"),
        ("ILexEntry", "ILexPronunciation"),
        ("ILexEntry", "ILexReference"),
        ("ILexEntry", "ILexEntryRef"),
        ("ILexSense", "ICmPicture"),
        ("ILexSense", "ILexEntryRef"),
        ("IMoForm", "IMoMorphType"),

        # === Text/Interlinear Navigation ===
        ("IText", "IStText"),
        ("IStText", "IStTxtPara"),
        ("IStTxtPara", "ISegment"),
        ("ISegment", "IAnalysis"),
        ("IText", "ISegment"),  # Full path for convenience

        # === Wordform Analysis Navigation ===
        ("IWfiWordform", "IWfiAnalysis"),
        ("IWfiAnalysis", "IWfiGloss"),
        ("IWfiAnalysis", "IWfiMorphBundle"),
        ("IWfiMorphBundle", "IMoForm"),
        ("IWfiMorphBundle", "ILexSense"),
        ("IWfiWordform", "IWfiGloss"),  # Full path

        # === Grammar/Morphology Navigation ===
        ("IMoInflAffixSlot", "IMoInflAffMsa"),
        ("IMoMorphData", "IMoMorphType"),
        ("IMoStemMsa", "IPartOfSpeech"),
        ("IMoInflAffMsa", "IPartOfSpeech"),

        # === Reversal Index Navigation ===
        ("IReversalIndex", "IReversalIndexEntry"),
        ("IReversalIndexEntry", "ILexSense"),

        # === Lists/Possibility Navigation ===
        ("ICmPossibilityList", "ICmPossibility"),
        ("ICmSemanticDomainList", "ICmSemanticDomain"),
        ("ICmAnthroList", "ICmAnthroItem"),

        # === Scripture Navigation ===
        ("IScrBook", "IScrSection"),
        ("IScrSection", "IStText"),
        ("IScrBook", "IStTxtPara"),
    ]

    paths = {}
    for start, end in common_pairs:
        path = find_path(graph, start, end)
        if path:
            key = f"{start} -> {end}"
            paths[key] = {
                "steps": path,
                "code_pattern": generate_code_pattern(path)
            }

    return paths


def generate_code_pattern(path: List[Dict]) -> str:
    """Generate code pattern from path."""
    if not path:
        return ""

    lines = []
    indent = ""

    # Start with first entity (lowercase, remove I prefix)
    current_var = path[0]["from"].lower().replace("i", "", 1)

    for i, step in enumerate(path):
        prop = step["via"]
        is_collection = prop.endswith("OS") or prop.endswith("OC") or prop.endswith("RC") or prop.endswith("RS")

        if is_collection:
            # Generate iteration
            item_var = step["to"].lower().replace("i", "", 1)
            lines.append(f"{indent}for {item_var} in {current_var}.{prop}:")
            indent += "    "
            current_var = item_var
        else:
            # Single property access
            lines.append(f"{indent}{step['to'].lower().replace('i', '', 1)} = {current_var}.{prop}")
            current_var = step["to"].lower().replace("i", "", 1)

    # Add placeholder for final action
    lines.append(f"{indent}# work with {current_var}")

    return "\n".join(lines)


def build_navigation_graph(liblcm_path: Path) -> Dict[str, Any]:
    """Build complete navigation graph."""

    liblcm = load_json(liblcm_path)

    # Extract relationships
    rel_data = extract_relationships(liblcm)

    # Precompute common paths
    common_paths = precompute_common_paths(rel_data["graph"])

    result = {
        "_schema": "navigation-graph/1.0",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "entities": rel_data["entities"],
        "graph": rel_data["graph"],
        "common_paths": common_paths,
        "statistics": {
            "entities_with_children": sum(1 for e in rel_data["entities"].values() if e["children"]),
            "entities_with_parents": sum(1 for e in rel_data["entities"].values() if e["parents"]),
            "total_relationships": sum(
                len(e["children"]) + len(e["references"])
                for e in rel_data["entities"].values()
            ),
            "common_paths_computed": len(common_paths)
        }
    }

    return result


def update_liblcm_with_relationships(liblcm_path: Path, nav_graph: Dict):
    """Update LibLCM entities with structured relationships field."""

    liblcm = load_json(liblcm_path)

    print("[INFO] Adding relationships to LibLCM entities...")

    updated = 0
    for entity_id, entity in liblcm.get("entities", {}).items():
        if entity_id in nav_graph["entities"]:
            rels = nav_graph["entities"][entity_id]
            # Only add if there are actual relationships
            if rels["children"] or rels["parents"] or rels["references"]:
                entity["relationships"] = {
                    "children": rels["children"],
                    "parents": rels["parents"],
                    "references": rels["references"][:10],  # Limit references to avoid bloat
                }
                updated += 1

    print(f"[INFO] Updated relationships for {updated} entities")

    liblcm["_relationships_added"] = datetime.now(timezone.utc).isoformat()
    save_json(liblcm, liblcm_path)


def print_summary(result: Dict):
    """Print summary statistics."""
    stats = result["statistics"]

    print("\n" + "=" * 50)
    print("Navigation Graph Summary")
    print("=" * 50)
    print(f"  Entities with children: {stats['entities_with_children']}")
    print(f"  Entities with parents: {stats['entities_with_parents']}")
    print(f"  Total relationships: {stats['total_relationships']}")
    print(f"  Common paths computed: {stats['common_paths_computed']}")

    print("\nCommon paths:")
    for path_key, path_info in result["common_paths"].items():
        steps = " -> ".join(s["via"] for s in path_info["steps"])
        print(f"  {path_key}: {steps}")


def main():
    parser = argparse.ArgumentParser(
        description="Build navigation graph from LibLCM relationships"
    )
    parser.add_argument(
        "--output",
        default="index/navigation_graph.json",
        help="Output path for navigation graph JSON"
    )
    parser.add_argument(
        "--update-liblcm",
        action="store_true",
        help="Also update LibLCM index with relationships field"
    )

    args = parser.parse_args()

    root = get_project_root()
    liblcm_path = root / "index" / "liblcm" / "flex-api-enhanced.json"
    output_path = root / args.output

    # Build navigation graph
    result = build_navigation_graph(liblcm_path)

    # Save navigation graph
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(result, output_path)

    # Print summary
    print_summary(result)

    # Optionally update LibLCM
    if args.update_liblcm:
        update_liblcm_with_relationships(liblcm_path, result)

    print("\n[DONE] Navigation graph complete")
    return 0


if __name__ == "__main__":
    exit(main())
