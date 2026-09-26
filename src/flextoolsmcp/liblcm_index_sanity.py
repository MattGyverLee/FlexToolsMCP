#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Post-build sanity checks for the LibLCM API index (#140).

Catches structurally incomplete indexes (e.g. #135/G14: zero
``SIL.LCModel.Core.KernelInterfaces`` entities) before refresh reports success
with no signal beyond a swallowed per-assembly warning.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Tuple

log = logging.getLogger("liblcm-extractor")

# Namespaces that must never be empty when reflection succeeded. Values are
# minimum *entity* counts (types indexed), not member counts.
MIN_NAMESPACE_ENTITY_COUNTS: Dict[str, int] = {
    "SIL.LCModel.Core.KernelInterfaces": 15,
    "SIL.LCModel.Core.Text": 10,
    "SIL.LCModel": 50,
}

# Anchor types: if present in the index, they must expose at least this many
# combined properties + methods (guards against hollow extractions).
ANCHOR_MIN_MEMBER_COUNTS: Dict[str, int] = {
    "ITsString": 3,
    "ILexEntry": 5,
}

# When live .NET types are available, flag if indexed public surface is far
# below reflection (ratio = indexed / live).
MIN_INDEXED_TO_LIVE_MEMBER_RATIO = 0.25


def _namespace_entity_counts(entities: Mapping[str, Mapping[str, Any]]) -> Counter:
    counts: Counter = Counter()
    for entity in entities.values():
        ns = entity.get("namespace") or ""
        if ns:
            counts[ns] += 1
    return counts


def audit_namespace_coverage(api_doc: Mapping[str, Any]) -> List[str]:
    """Return human-readable warnings for implausibly low namespace coverage."""
    entities = api_doc.get("entities") or {}
    if not entities:
        return ["LibLCM index has zero entities after extraction"]

    counts = _namespace_entity_counts(entities)
    warnings: List[str] = []

    for namespace, minimum in MIN_NAMESPACE_ENTITY_COUNTS.items():
        found = counts.get(namespace, 0)
        if found < minimum:
            warnings.append(
                f"namespace {namespace!r} has {found} indexed entities "
                f"(expected at least {minimum}); index may be incomplete"
            )

    return warnings


def audit_anchor_entities(api_doc: Mapping[str, Any]) -> List[str]:
    """Warn when anchor types are missing or indexed with too few members."""
    entities = api_doc.get("entities") or {}
    warnings: List[str] = []

    for entity_id, minimum_members in ANCHOR_MIN_MEMBER_COUNTS.items():
        entity = entities.get(entity_id)
        if entity is None:
            warnings.append(
                f"anchor type {entity_id!r} is missing from the LibLCM index"
            )
            continue
        member_count = len(entity.get("properties") or []) + len(
            entity.get("methods") or []
        )
        if member_count < minimum_members:
            warnings.append(
                f"anchor type {entity_id!r} has only {member_count} indexed "
                f"members (expected at least {minimum_members})"
            )

    return warnings


def _public_member_names(dotnet_type: Any) -> Tuple[set, set]:
    """Return (property_names, method_names) from a reflected .NET type."""
    props: set = set()
    methods: set = set()
    flags = None
    try:
        from System.Reflection import BindingFlags

        flags = (
            BindingFlags.Public
            | BindingFlags.Instance
            | BindingFlags.DeclaredOnly
        )
    except Exception:
        return props, methods

    try:
        for p in dotnet_type.GetProperties(flags):
            props.add(str(p.Name))
    except Exception:
        pass
    try:
        for m in dotnet_type.GetMethods(flags):
            name = str(m.Name)
            if name.startswith("get_") or name.startswith("set_"):
                continue
            methods.add(name)
    except Exception:
        pass
    return props, methods


def spot_check_live_types(
    api_doc: Mapping[str, Any],
    live_types: Mapping[str, Any],
) -> List[str]:
    """
    Compare indexed members on anchor types against live reflection.

    ``live_types`` maps entity id (e.g. ``ITsString``) to the pythonnet Type.
    """
    entities = api_doc.get("entities") or {}
    warnings: List[str] = []

    for entity_id, dotnet_type in live_types.items():
        entity = entities.get(entity_id)
        if entity is None or dotnet_type is None:
            continue

        indexed_names = {
            p.get("name")
            for p in (entity.get("properties") or [])
            if p.get("name")
        }
        indexed_names.update(
            m.get("name")
            for m in (entity.get("methods") or [])
            if m.get("name")
        )

        live_props, live_methods = _public_member_names(dotnet_type)
        live_names = live_props | live_methods
        if not live_names:
            continue

        overlap = indexed_names & live_names
        ratio = len(overlap) / len(live_names)
        if ratio < MIN_INDEXED_TO_LIVE_MEMBER_RATIO:
            warnings.append(
                f"spot-check {entity_id!r}: indexed surface covers "
                f"{len(overlap)}/{len(live_names)} live public members "
                f"({ratio:.0%}); reflection may have partially failed"
            )

    return warnings


def apply_index_sanity_audit(
    api_doc: MutableMapping[str, Any],
    live_types: Optional[Mapping[str, Any]] = None,
) -> List[str]:
    """
    Run all sanity checks, attach results to ``api_doc['metadata']``, log WARN.

    Returns the combined warning strings (empty if clean).
    """
    warnings: List[str] = []
    warnings.extend(audit_namespace_coverage(api_doc))
    warnings.extend(audit_anchor_entities(api_doc))
    if live_types:
        warnings.extend(spot_check_live_types(api_doc, live_types))

    metadata = api_doc.setdefault("metadata", {})
    if warnings:
        metadata["index_sanity_warnings"] = list(warnings)
        metadata["coverage_gaps"] = [
            w.split(":", 1)[0] if ":" in w else w for w in warnings
        ]
        for msg in warnings:
            log.warning("[index-sanity] %s", msg)
    else:
        metadata.pop("index_sanity_warnings", None)
        metadata.pop("coverage_gaps", None)

    return warnings
