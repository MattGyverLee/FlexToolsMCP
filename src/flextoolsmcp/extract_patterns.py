#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract Common Patterns from FlexLibs Docstrings

Extracts code examples from Flexicon docstrings and categorizes them
by operation type (create, read, update, delete, iterate).

Usage:
    python src/extract_patterns.py
    python src/extract_patterns.py --output index/common_patterns.json
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any

if __package__:
    from .server.versioning import find_latest_versioned_api_file
    from .file_utils import get_project_root, get_index_dir, load_json, save_json
    from .curated_recipes import CURATED_RECIPES
else:
    from server.versioning import find_latest_versioned_api_file
    from file_utils import get_project_root, get_index_dir, load_json, save_json
    from curated_recipes import CURATED_RECIPES


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


def extract_patterns(flexicon_path: Path) -> Dict[str, Any]:
    """Extract patterns from Flexicon docstrings."""
    # Configuration limits
    MIN_EXAMPLE_LENGTH = 20  # Minimum example text length to include
    MIN_CLEANED_EXAMPLE_LENGTH = 10  # Minimum length after cleanup
    MAX_PATTERNS_PER_OBJECT = 20  # Maximum patterns to keep per object type
    MAX_PATTERNS_PER_OPERATION = 30  # Maximum patterns per operation type

    flexicon = load_json(flexicon_path)

    patterns_by_object = defaultdict(list)
    patterns_by_operation = defaultdict(list)
    all_patterns = []

    print("[INFO] Extracting patterns from Flexicon examples...")

    for class_name, entity in flexicon.get("entities", {}).items():
        for method in entity.get("methods", []):
            example = method.get("example", "").strip()

            if not example or len(example) < MIN_EXAMPLE_LENGTH:
                continue

            cleaned = clean_example(example)
            if len(cleaned) < MIN_CLEANED_EXAMPLE_LENGTH:
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
        unique_patterns_by_object[obj_type] = unique[:MAX_PATTERNS_PER_OBJECT]

    result = {
        # Issue #52: bumped from common-patterns/1.0. The 2.0 schema adds a
        # top-level "recipes" section (intent-keyed, runnable, bare-snippet
        # code) served through search_by_capability / find_examples. The
        # by_object/by_operation aggregate sections are unchanged -- 2.0 is
        # additive, not a breaking rewrite.
        "_schema": "common-patterns/2.0",
        "by_object": unique_patterns_by_object,
        "by_operation": {
            op: patterns[:MAX_PATTERNS_PER_OPERATION] for op, patterns in patterns_by_operation.items()
        },
        "statistics": {
            "total_patterns": len(all_patterns),
            "unique_patterns": sum(len(p) for p in unique_patterns_by_object.values()),
            "objects_covered": len(unique_patterns_by_object),
            "operations": list(patterns_by_operation.keys())
        },
        # Curated seed recipes (source of truth: curated_recipes.py). Mined
        # candidates (--mine-operations-log) are NEVER merged in here
        # automatically -- they land in a separate review file and only
        # join CURATED_RECIPES (and thus this section) after a human flips
        # their `source` to "curated".
        "recipes": CURATED_RECIPES,
    }

    return result


def add_patterns_to_flexlibs(flexicon_path: Path, patterns: Dict):
    """Add common_patterns field to FlexLibs entities."""

    flexicon = load_json(flexicon_path)

    print("[INFO] Adding common_patterns to Flexicon entities...")

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
            if class_name in flexicon["entities"]:
                flexicon["entities"][class_name]["common_patterns"] = [
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

    save_json(flexicon, flexicon_path)


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


def _normalize_intent(intent: str) -> str:
    """Lowercase + collapsed-whitespace form used to cluster user_intent strings."""
    return re.sub(r"\s+", " ", intent.strip().lower())


def mine_operations_log(log_dir: Path) -> Dict[str, Any]:
    """Cluster successful, intent-tagged operations into mined recipe candidates.

    Reads ``operations.jsonl`` (+ rotated ``.1``) for records with
    ``outcome == "ok"`` and a non-empty ``user_intent``, clusters them by
    normalized intent text, and returns a review payload -- never a
    ship-ready recipe. ``operations.jsonl`` intentionally does not retain
    the executed code (only ``code_sha256``/``code_bytes``, for privacy and
    size reasons), so each cluster carries the evidence (count, op_ids,
    sha256 samples) a human reviewer needs to go find the real code (e.g.
    via the session log or the skeleton closet) and hand-author or bless a
    recipe -- it does NOT fabricate a ``code`` field.

    Every emitted entry has ``source: "mined"`` and ``requires_human_review:
    True``. Promoting a cluster to a shipped recipe means hand-writing (or
    verifying) a ``curated_recipes.CURATED_RECIPES`` entry and flipping
    ``source`` to ``"curated"`` -- this function never writes to that file.
    """
    if __package__:
        from .server.handlers.op_telemetry import _load_jsonl_records
    else:
        from server.handlers.op_telemetry import _load_jsonl_records

    records = _load_jsonl_records(log_dir)

    clusters: Dict[str, Dict[str, Any]] = {}
    for record in records:
        if record.get("outcome") != "ok":
            continue
        intent = (record.get("user_intent") or "").strip()
        if not intent:
            continue
        key = _normalize_intent(intent)
        cluster = clusters.setdefault(key, {
            "intent": intent,
            "count": 0,
            "op_ids": [],
            "code_sha256_samples": [],
        })
        cluster["count"] += 1
        if len(cluster["op_ids"]) < 10:
            cluster["op_ids"].append(record.get("op_id", ""))
        sha = record.get("code_sha256", "")
        if sha and sha not in cluster["code_sha256_samples"] and len(cluster["code_sha256_samples"]) < 10:
            cluster["code_sha256_samples"].append(sha)

    # Sort clusters by frequency -- the busiest intents are the best mining
    # candidates for a human to turn into a curated recipe next.
    ordered = sorted(clusters.values(), key=lambda c: -c["count"])

    candidates = {}
    for i, cluster in enumerate(ordered):
        candidate_id = f"mined-{i + 1:03d}"
        candidates[candidate_id] = {
            "intent": cluster["intent"],
            "match_terms": [],
            "entities": [],
            "operations": [],
            "requires_write": None,  # unknown until a human inspects the code
            "code": None,  # NOT retained in operations.jsonl -- see docstring
            "notes": (
                f"Mined from {cluster['count']} outcome=ok operation(s) sharing this "
                "user_intent. Code was NOT retained in telemetry (only "
                "code_sha256/code_bytes) -- cross-reference op_ids against the "
                "session log or skeleton closet to recover the actual code before "
                "authoring a recipe."
            ),
            "source": "mined",
            "requires_human_review": True,
            "evidence": {
                "occurrence_count": cluster["count"],
                "op_ids": cluster["op_ids"],
                "code_sha256_samples": cluster["code_sha256_samples"],
            },
        }

    return {
        "_schema": "mined-recipe-candidates/1.0",
        "generated_from": str(log_dir),
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


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
        help="Also update Flexicon index with common_patterns field"
    )
    parser.add_argument(
        "--mine-operations-log",
        action="store_true",
        help=(
            "Instead of extracting docstring patterns, read operations.jsonl "
            "telemetry for outcome=ok ops with a user_intent, cluster by "
            "intent, and write candidate recipes (source: mined) to a review "
            "file. Never ships automatically -- see --mined-output."
        ),
    )
    parser.add_argument(
        "--mined-output",
        default="mined_recipes_review.json",
        help="Output path for --mine-operations-log's review file (relative to index dir unless absolute)",
    )

    args = parser.parse_args()

    if args.mine_operations_log:
        if __package__:
            from .server.kernel import get_log_dir
        else:
            from server.kernel import get_log_dir

        log_dir = get_log_dir()
        mined = mine_operations_log(log_dir)

        mined_output_path = Path(args.mined_output)
        if not mined_output_path.is_absolute():
            mined_output_path = get_index_dir() / mined_output_path
        mined_output_path.parent.mkdir(parents=True, exist_ok=True)
        save_json(mined, mined_output_path)

        print(f"[INFO] Mined {mined['candidate_count']} candidate intent cluster(s) from {log_dir}")
        print(f"[INFO] Review file written to: {mined_output_path}")
        print("[INFO] NONE of these ship automatically -- human review required before adding to curated_recipes.py")
        return 0

    root = get_project_root()
    python_dir = get_index_dir() / "python"

    # Find latest Flexicon API file
    flexicon_path = find_latest_versioned_api_file(python_dir, "flexicon_api")
    if not flexicon_path:
        print("[ERROR] Flexicon API file not found")
        return 1

    output_path = root / args.output

    # Extract patterns
    result = extract_patterns(flexicon_path)

    # Extract version from flexicon_path for versioned filename
    version_match = re.search(r'flexicon_api_v(\d+\.\d+\.\d+)', str(flexicon_path))
    if version_match:
        flexicon_version = version_match.group(1)
        output_filename = f"common_patterns_flexicon-v{flexicon_version}.json"
        output_path = get_index_dir() / output_filename

    # Save patterns
    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_json(result, output_path)

    # Print summary
    print_summary(result)

    # Optionally update FlexLibs
    if args.update_flexlibs:
        add_patterns_to_flexlibs(flexicon_path, result)

    print("\n[DONE] Pattern extraction complete")
    return 0


if __name__ == "__main__":
    exit(main())
