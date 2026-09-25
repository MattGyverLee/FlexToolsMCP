#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Annotate flexicon ``GetAll`` methods with a per-method collection contract (issue #124).

The docs promise a uniform "behavioral collection" for every ``GetAll``, but the
index only recorded heterogeneous ``return_type`` strings. This post-process
step adds a structured ``collection_contract`` beside each ``GetAll`` so
``get_object_api`` can surface the contract where callers look up methods.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

if __package__:
    from .file_utils import get_index_dir, load_json, save_json
    from .server.versioning import find_latest_versioned_api_file
else:
    from file_utils import get_index_dir, load_json, save_json
    from server.versioning import find_latest_versioned_api_file

KEY_COLLECTION_CONTRACT = "collection_contract"

_RETURN_TYPE_PATTERNS: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^EnumerableWrapper\[(.+)\]$"), "enumerable_wrapper"),
    (re.compile(r"^list\[(.+)\]$"), "python_list"),
    (re.compile(r"^AllomorphCollection\[(.+)\]$"), "allomorph_collection"),
    (re.compile(r"^RuleCollection\[(.+)\]$"), "rule_collection"),
    (re.compile(r"^MSACollection\[(.+)\]$"), "msa_collection"),
)

_DOMAIN_WRAPPER_NOTES = {
    "allomorph_collection": (
        "Yields flexicon Allomorph wrapper objects (`.form`, `.class_type`), "
        "not raw LCM interfaces."
    ),
    "rule_collection": (
        "Yields flexicon PhonologicalRule wrapper objects, not raw LCM interfaces."
    ),
    "msa_collection": (
        "Yields flexicon MorphosyntaxAnalysis wrapper objects, not raw LCM interfaces."
    ),
}


def _parse_return_type(return_type: str) -> Optional[Tuple[str, str]]:
    rt = (return_type or "").strip()
    if not rt:
        return None
    for pattern, shape in _RETURN_TYPE_PATTERNS:
        match = pattern.match(rt)
        if match:
            return shape, match.group(1).strip()
    return None


def _yields_lcm_objects(shape: str, element: str) -> bool:
    if shape in ("allomorph_collection", "rule_collection", "msa_collection"):
        return False
    if element == "dict":
        return False
    if element.startswith("I") and element[1:2].isupper():
        return True
    return False


def infer_getall_collection_contract(return_type: str) -> Optional[Dict[str, Any]]:
    """Derive collection_contract from a GetAll return_type string."""
    parsed = _parse_return_type(return_type)
    if not parsed:
        return None
    shape, element = parsed
    contract: Dict[str, Any] = {
        "shape": shape,
        "return_type": return_type.strip(),
        "element_type": element,
        "behavioral": True,
        "yields_lcm_objects": _yields_lcm_objects(shape, element),
    }
    note = _DOMAIN_WRAPPER_NOTES.get(shape)
    if note:
        contract["note"] = note
    return contract


def annotate_getall_contracts(flexicon_data: Dict[str, Any]) -> Dict[str, int]:
    """Walk every entity and annotate GetAll methods in place."""
    stats = {
        "getall_total": 0,
        "annotated": 0,
        "missing_return_type": 0,
        "unrecognized_return_type": 0,
    }
    entities = flexicon_data.get("entities") or {}
    for entity in entities.values():
        for method in entity.get("methods") or []:
            if method.get("name") != "GetAll":
                continue
            stats["getall_total"] += 1
            rt = (method.get("return_type") or "").strip()
            if not rt:
                stats["missing_return_type"] += 1
                continue
            contract = infer_getall_collection_contract(rt)
            if not contract:
                stats["unrecognized_return_type"] += 1
                continue
            method[KEY_COLLECTION_CONTRACT] = contract
            stats["annotated"] += 1
    return stats


def main() -> int:
    index_dir = get_index_dir()
    python_dir = index_dir / "python"
    flexicon_path = find_latest_versioned_api_file(python_dir, "flexicon_api")
    if not flexicon_path:
        print("[ERROR] Flexicon API file not found")
        return 1

    flexicon_data = load_json(flexicon_path)
    print(f"[INFO] Annotating GetAll collection contracts in {flexicon_path.name}")
    stats = annotate_getall_contracts(flexicon_data)
    save_json(flexicon_data, flexicon_path)

    print("[OK] GetAll collection-contract annotation complete")
    for key, value in stats.items():
        print(f"     {key}: {value}")
    if stats["missing_return_type"] or stats["unrecognized_return_type"]:
        print("[WARN] Some GetAll methods lack a contract -- see counts above")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
