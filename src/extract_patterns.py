#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract Common Patterns from FlexLibs Docstrings

Extracts code examples from FlexLibs2 docstrings and categorizes them
by operation type (create, read, update, delete, iterate).

Usage:
    python src/extract_patterns.py
    python src/extract_patterns.py --output index/common_patterns.json
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


def classify_operation(method_name: str, example: str) -> str:
    """Classify operation type from method name and example."""
    name_lower = method_name.lower()
    example_lower = example.lower()

    # Creation patterns
    if any(p in name_lower for p in ["create", "add", "new"]):
        return "create"

    # Deletion patterns
    if any(p in name_lower for p in ["delete", "remove"]):
        return "delete"

    # Update/modification patterns
    if any(p in name_lower for p in ["set", "update", "modify", "change"]):
        return "update"

    # Retrieval patterns
    if any(p in name_lower for p in ["get", "find", "lookup", "search"]):
        return "read"

    # Iteration patterns
    if "for " in example_lower and " in " in example_lower:
        return "iterate"

    # Move/reorder patterns
    if any(p in name_lower for p in ["move", "reorder"]):
        return "reorder"

    # Merge patterns
    if "merge" in name_lower:
        return "merge"

    return "general"


def clean_example(example: str) -> str:
    """Clean up docstring example formatting."""
    lines = example.split('\n')
    cleaned = []

    for line in lines:
        # Remove doctest prompts
        line = re.sub(r'^\s*>>>\s?', '', line)
        line = re.sub(r'^\s*\.\.\.\s?', '', line)
        # Remove excessive indentation (keep relative)
        cleaned.append(line.rstrip())

    # Remove leading/trailing blank lines
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    return '\n'.join(cleaned)


def extract_object_type(class_name: str, example: str) -> str:
    """Try to determine what object type this pattern applies to."""
    # From class name
    if "Entry" in class_name:
        return "ILexEntry"
    elif "Sense" in class_name:
        return "ILexSense"
    elif "Example" in class_name:
        return "ILexExampleSentence"
    elif "Allomorph" in class_name:
        return "IMoForm"
    elif "Reversal" in class_name:
        return "IReversalIndexEntry"
    elif "Text" in class_name:
        return "IText"
    elif "Etymology" in class_name:
        return "ILexEtymology"
    elif "Reference" in class_name:
        return "ILexReference"
    elif "Pronunciation" in class_name:
        return "ILexPronunciation"

    return "general"


def extract_patterns(flexlibs2_path: Path) -> Dict[str, Any]:
    """Extract patterns from FlexLibs2 docstrings."""

    flexlibs2 = load_json(flexlibs2_path)

    patterns_by_object = defaultdict(list)
    patterns_by_operation = defaultdict(list)
    all_patterns = []

    print("[INFO] Extracting patterns from FlexLibs2 examples...")

    for class_name, entity in flexlibs2.get("entities", {}).items():
        for method in entity.get("methods", []):
            example = method.get("example", "").strip()

            if not example or len(example) < 20:
                continue

            cleaned = clean_example(example)
            if len(cleaned) < 10:
                continue

            operation = classify_operation(method["name"], example)
            object_type = extract_object_type(class_name, example)

            pattern = {
                "description": method.get("summary", "") or f"{method['name']} operation",
                "operation": operation,
                "object_type": object_type,
                "code": cleaned,
                "source": "docstring",
                "class": class_name,
                "method": method["name"]
            }

            all_patterns.append(pattern)
            patterns_by_object[object_type].append(pattern)
            patterns_by_operation[operation].append(pattern)

    # Deduplicate patterns by similarity
    print("[INFO] Deduplicating patterns...")
    unique_patterns_by_object = {}
    for obj_type, patterns in patterns_by_object.items():
        seen_codes = set()
        unique = []
        for p in patterns:
            # Simple dedup by first 50 chars of code
            code_key = p["code"][:50]
            if code_key not in seen_codes:
                seen_codes.add(code_key)
                unique.append(p)
        unique_patterns_by_object[obj_type] = unique[:20]  # Limit per object

    result = {
        "_schema": "common-patterns/1.0",
        "_generated_at": datetime.now(timezone.utc).isoformat(),
        "by_object": unique_patterns_by_object,
        "by_operation": {
            op: patterns[:30] for op, patterns in patterns_by_operation.items()
        },
        "statistics": {
            "total_patterns": len(all_patterns),
            "unique_patterns": sum(len(p) for p in unique_patterns_by_object.values()),
            "objects_covered": len(unique_patterns_by_object),
            "operations": list(patterns_by_operation.keys())
        }
    }

    return result


def add_patterns_to_flexlibs(flexlibs2_path: Path, patterns: Dict):
    """Add common_patterns field to FlexLibs entities."""

    flexlibs2 = load_json(flexlibs2_path)

    print("[INFO] Adding common_patterns to FlexLibs2 entities...")

    # Map object types to FlexLibs class names
    object_to_class = {
        "ILexEntry": ["LexEntryOperations"],
        "ILexSense": ["LexSenseOperations"],
        "ILexExampleSentence": ["ExampleOperations"],
        "IMoForm": ["AllomorphOperations"],
        "IReversalIndexEntry": ["ReversalOperations", "ReversalIndexEntryOperations"],
        "IText": ["TextOperations"],
        "ILexEtymology": ["EtymologyOperations"],
        "ILexReference": ["LexReferenceOperations"],
        "ILexPronunciation": ["PronunciationOperations"],
    }

    updated = 0
    for obj_type, class_names in object_to_class.items():
        if obj_type not in patterns["by_object"]:
            continue

        obj_patterns = patterns["by_object"][obj_type][:10]  # Limit to 10

        for class_name in class_names:
            if class_name in flexlibs2["entities"]:
                flexlibs2["entities"][class_name]["common_patterns"] = [
                    {
                        "description": p["description"],
                        "operation": p["operation"],
                        "code": p["code"],
                        "source": p["source"]
                    }
                    for p in obj_patterns
                ]
                updated += 1

    print(f"[INFO] Added patterns to {updated} entities")

    flexlibs2["_patterns_added"] = datetime.now(timezone.utc).isoformat()
    save_json(flexlibs2, flexlibs2_path)


def print_summary(result: Dict):
    """Print summary statistics."""
    stats = result["statistics"]

    print("\n" + "=" * 50)
    print("Pattern Extraction Summary")
    print("=" * 50)
    print(f"  Total patterns extracted: {stats['total_patterns']}")
    print(f"  Unique patterns (deduplicated): {stats['unique_patterns']}")
    print(f"  Object types covered: {stats['objects_covered']}")
    print(f"  Operation types: {', '.join(stats['operations'])}")

    print("\nPatterns by object:")
    for obj, patterns in result["by_object"].items():
        print(f"  {obj}: {len(patterns)} patterns")


def main():
    parser = argparse.ArgumentParser(
        description="Extract common patterns from FlexLibs docstrings"
    )
    parser.add_argument(
        "--output",
        default="index/common_patterns.json",
        help="Output path for patterns JSON"
    )
    parser.add_argument(
        "--update-flexlibs",
        action="store_true",
        help="Also update FlexLibs2 index with common_patterns field"
    )

    args = parser.parse_args()

    root = get_project_root()
    flexlibs2_path = root / "index" / "flexlibs" / "flexlibs2_api.json"
    output_path = root / args.output

    # Extract patterns
    result = extract_patterns(flexlibs2_path)

    # Save patterns
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(result, output_path)

    # Print summary
    print_summary(result)

    # Optionally update FlexLibs
    if args.update_flexlibs:
        add_patterns_to_flexlibs(flexlibs2_path, result)

    print("\n[DONE] Pattern extraction complete")
    return 0


if __name__ == "__main__":
    exit(main())
