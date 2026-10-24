#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate tool success payloads against declared *Success models (issue #152).

Closes the contract-drift gap noted at server.py: handler dicts were not checked
against ToolDef.output_model.

Phase 2 (#369, ruling R2): the get_object_api / search_by_capability cases
are NO LONGER hand-written "minimal" dicts -- the old ones carried keys the
handlers never emit (``entity``/``methods``/``matches``) and omitted most
keys they always emit, so they validated vacuously against the shell
models. They are now captured from the real handlers
(``handle_get_object_api`` / ``handle_search_by_capability``) driven by a
minimal fake API index; every payload below comes out of a handler code
path. run_module keeps its golden fixtures (captured real responses).
"""

from __future__ import annotations

import asyncio
import copy
import json
from functools import lru_cache
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
except ImportError as _dual_first_exc:
    try:
        from server.response_models import (
            GetObjectApiSuccess,
            RunModuleSuccess,
            SearchByCapabilitySuccess,
        )
        from server.tool_definitions import TOOLS
    except ImportError as _dual_second_exc:
        raise _dual_second_exc from _dual_first_exc

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


# ---------------------------------------------------------------------------
# Real-payload capture (Phase 2): fake index, real handlers
# ---------------------------------------------------------------------------

class _FakeSemanticSearch:
    enabled = False


class _FakeAPIIndex:
    """Minimal APIIndex stand-in: just what the two doc-search handlers read.

    The entity/method/property rows are fake index DATA; the payloads
    validated below are built entirely by the real handler code paths
    (pagination, search scoring, envelope stamping) from that data.
    """

    def __init__(self) -> None:
        self.flexicon = {
            "entities": {
                "FakeWidget": {
                    "category": "test",
                    "summary": "A fake entity used to capture real payloads.",
                    "source_file": "fake_widget.py",
                    "namespace": "",
                    "methods": [
                        {
                            "name": "GetGloss",
                            "signature": "GetGloss() -> str",
                            "summary": "Get the gloss text.",
                            "description": "Get the gloss text.",
                        }
                    ],
                    "properties": [
                        {"name": "Name", "description": "The widget name."}
                    ],
                }
            }
        }
        self.liblcm = None
        self.flexlibs_stable = None
        self.casting_index: Dict[str, Any] = {}
        self.semantic_search = _FakeSemanticSearch()
        self.liblcm_entities_epoch = 0

    def ensure_casting_index_loaded(self) -> None:
        pass

    def ensure_liblcm_loaded(self) -> None:
        pass

    def ensure_flexlibs_stable_loaded(self) -> None:
        pass


async def _capture_payloads_async() -> Dict[str, Dict[str, Any]]:
    try:
        from .server import kernel
        from .server.handlers.api import (
            handle_get_object_api,
            handle_search_by_capability,
        )
    except ImportError as _dual_first_exc:
        try:
            from server import kernel
            from server.handlers.api import (
                handle_get_object_api,
                handle_search_by_capability,
            )
        except ImportError as _dual_second_exc:
            raise _dual_second_exc from _dual_first_exc

    prev_index = kernel.get_api_index()
    prev_session = copy.deepcopy(kernel.session_state.__dict__)
    try:
        kernel.set_api_index(_FakeAPIIndex())  # type: ignore[arg-type]
        kernel.session_state.configure(
            session_id="tool-output-validation", api_mode="flexicon"
        )
        found = await handle_get_object_api({"object_type": "FakeWidget"})
        not_found = await handle_get_object_api({"object_type": "NoSuchWidget"})
        search = await handle_search_by_capability({"query": "gloss"})
    finally:
        kernel.set_api_index(prev_index)  # type: ignore[arg-type]
        kernel.session_state.__dict__.clear()
        kernel.session_state.__dict__.update(prev_session)

    return {
        "get_object_api_found": json.loads(found[0].text),
        "get_object_api_not_found": json.loads(not_found[0].text),
        "search_by_capability": json.loads(search[0].text),
    }


@lru_cache(maxsize=1)
def _captured_payloads_cached() -> Tuple[Tuple[str, str, Dict[str, Any]], ...]:
    payloads = asyncio.run(_capture_payloads_async())
    return (
        ("flextools_get_object_api", "real:found", payloads["get_object_api_found"]),
        (
            "flextools_get_object_api",
            "real:not_found",
            payloads["get_object_api_not_found"],
        ),
        (
            "flextools_search_by_capability",
            "real:keyword_search",
            payloads["search_by_capability"],
        ),
    )


def capture_real_payloads() -> List[Tuple[str, str, Dict[str, Any]]]:
    """(tool_name, case_label, payload) captured from the real handlers.

    Deep-copied per call so a caller mutating a payload cannot poison the
    cache for the next validation run.
    """
    return [
        (tool, label, copy.deepcopy(payload))
        for tool, label, payload in _captured_payloads_cached()
    ]


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
    captured = capture_real_payloads()
    for tool_name, (_model, golden_names) in _STRUCTURED_OUTPUT_TOOLS.items():
        for golden_name in golden_names:
            path = GOLDEN_DIR / golden_name
            with open(path, encoding="utf-8") as f:
                yield tool_name, golden_name, json.load(f)
        for cap_tool, label, payload in captured:
            if cap_tool == tool_name:
                yield cap_tool, label, payload


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
