#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate tool success payloads against declared *Success models (issue #152).

Closes the contract-drift gap noted at server.py: handler dicts were not checked
against ToolDef.output_model. Golden run_module fixtures and minimal smoke payloads
for the other structured tools are validated here and from validate_integrity.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple, Type

from pydantic import BaseModel

try:
    from .server.response_models import (
        GetObjectApiSuccess,
        RunModuleSuccess,
        SearchByCapabilitySuccess,
    )
    from .server.tool_definitions import TOOLS
except ImportError:
    from server.response_models import (
        GetObjectApiSuccess,
        RunModuleSuccess,
        SearchByCapabilitySuccess,
    )
    from server.tool_definitions import TOOLS

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "tests" / "golden" / "responses"

# Tool name -> (Success model, optional golden JSON filenames under GOLDEN_DIR)
_STRUCTURED_OUTPUT_TOOLS: Dict[str, Tuple[Type[BaseModel], Tuple[str, ...]]] = {
    "flextools_run_module": (
        RunModuleSuccess,
        (
            "auto_fix_casting_applied.json",
            "auto_fix_typo_applied.json",
        ),
    ),
    "flextools_get_object_api": (GetObjectApiSuccess, ()),
    "flextools_search_by_capability": (SearchByCapabilitySuccess, ()),
}

# Minimal payloads when no golden file exists (BaseEnvelope fields only).
_MINIMAL_SUCCESS_PAYLOADS: Dict[str, Dict[str, Any]] = {
    "flextools_get_object_api": {
        "status": "ok",
        "_contract": "tool-responses/1.0",
        "entity": "ILexEntry",
        "methods": [],
    },
    "flextools_search_by_capability": {
        "status": "ok",
        "_contract": "tool-responses/1.0",
        "query": "gloss",
        "matches": [],
    },
}


def tools_with_output_models() -> List[str]:
    """Tool names that declare output_model on ToolDef (must stay in sync)."""
    return sorted(
        name for name, tool_def in TOOLS.items() if tool_def.output_model is not None
    )


def _expected_tool_names() -> List[str]:
    return sorted(_STRUCTURED_OUTPUT_TOOLS.keys())


def validate_success_payload(model: Type[BaseModel], data: Dict[str, Any]) -> None:
    """Raise pydantic.ValidationError if data does not conform."""
    model.model_validate(data, by_alias=True)


def iter_validation_cases() -> Iterable[Tuple[str, str, Dict[str, Any]]]:
    """Yield (tool_name, case_label, payload_dict) for every check."""
    for tool_name, (model, golden_names) in _STRUCTURED_OUTPUT_TOOLS.items():
        for golden_name in golden_names:
            path = GOLDEN_DIR / golden_name
            with open(path, encoding="utf-8") as f:
                yield tool_name, golden_name, json.load(f)
        if not golden_names:
            yield tool_name, "minimal", _MINIMAL_SUCCESS_PAYLOADS[tool_name]


def run_output_model_validation() -> Tuple[bool, List[str]]:
    """Return (ok, error_lines). Used by tests and validate_integrity.py."""
    errors: List[str] = []

    declared = set(tools_with_output_models())
    expected = set(_expected_tool_names())
    if declared != expected:
        missing = sorted(expected - declared)
        extra = sorted(declared - expected)
        if missing:
            errors.append(
                f"tool_output_validation: missing output_model on tools: {', '.join(missing)}"
            )
        if extra:
            errors.append(
                f"tool_output_validation: undeclared in validator registry: {', '.join(extra)}"
            )

    for tool_name, (model, _golden_names) in _STRUCTURED_OUTPUT_TOOLS.items():
        tool_def = TOOLS.get(tool_name)
        if tool_def is None:
            errors.append(f"tool_output_validation: unknown tool {tool_name!r}")
            continue
        if tool_def.output_model.__name__ != model.__name__:
            errors.append(
                f"tool_output_validation: {tool_name} output_model mismatch "
                f"(expected {model.__name__}, got {tool_def.output_model.__name__})"
            )

    for tool_name, case_label, payload in iter_validation_cases():
        model = _STRUCTURED_OUTPUT_TOOLS[tool_name][0]
        try:
            validate_success_payload(model, payload)
        except Exception as exc:
            errors.append(
                f"tool_output_validation: {tool_name} case {case_label}: {exc}"
            )

    return (not errors, errors)
