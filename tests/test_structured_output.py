#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 2 structured output tests (issue #369, ruling R2).

Covers, for the batch-1 tools (flextools_run_module,
flextools_search_by_capability, flextools_get_object_api):

- list_tools() advertises outputSchema for exactly the batch-1 set.
- The 2.x call adapter attaches structuredContent derived by parsing the
  FINAL text payload, and the text payload is byte-identical to what the
  handler/call_tool produced (golden comparison, success AND error).
- Error payloads (status="error" / error_code present) attach NO
  structuredContent.
- Client-side conformance: the emitted structuredContent validates
  against the advertised outputSchema the way the mcp 2.x SDK client
  does (ClientSession.validate_tool_result: hard-fail when structured
  content is missing for an advertised tool, jsonschema-validate it
  otherwise, with the validator built the same way).

Success payloads are real: captured from the actual handlers for the two
doc-search tools (fake index data, real handler code paths) and the
golden captured responses for run_module. Error payloads come from the
production error_response() envelope builder.

Async work is driven via asyncio.run (repo pattern from test_mcp_compat).
"""

import asyncio
import json
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.types import TextContent

REPO_ROOT = Path(__file__).parent.parent
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from flextoolsmcp.response_utils import error_response, json_response  # noqa: E402
from flextoolsmcp.tool_output_validation import capture_real_payloads  # noqa: E402

BATCH_1 = {
    "flextools_run_module",
    "flextools_search_by_capability",
    "flextools_get_object_api",
}


@lru_cache(maxsize=1)
def _get_srv():
    """Load src/flextoolsmcp/server.py directly (pattern: test_mcp_compat)."""
    import importlib.util

    server_py = SRC_DIR / "flextoolsmcp" / "server.py"
    spec = importlib.util.spec_from_file_location("_srv_structured", str(server_py))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec from {server_py}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _success_payloads():
    """{tool_name: real success payload dict} for all three batch-1 tools."""
    payloads = {}
    for tool, _label, payload in capture_real_payloads():
        payloads.setdefault(tool, payload)
    golden = REPO_ROOT / "tests" / "golden" / "responses" / "auto_fix_casting_applied.json"
    payloads["flextools_run_module"] = json.loads(golden.read_text(encoding="utf-8"))
    assert set(payloads) == BATCH_1
    return payloads


def _run_adapter(name, content_list):
    """Drive the real 2.x call adapter with a stub call_tool_fn."""
    srv = _get_srv()

    async def _fake_call_tool(_name, _arguments):
        return content_list

    handler = srv.make_call_tool_handler(_fake_call_tool)
    params = SimpleNamespace(name=name, arguments={})
    return asyncio.run(handler(None, params))


def _client_validate(name, output_schema, result):
    """Validate like mcp 2.x ClientSession.validate_tool_result does.

    (mcp/client/session.py in mcp 2.3.0: a tool with an output schema MUST
    return structured content, and that content is jsonschema-validated
    with a validator built by validator_for + an empty referencing
    Registry; any mismatch raises and the client hard-fails the call.)
    """
    from jsonschema import exceptions as jsonschema_exceptions
    from jsonschema.validators import validator_for
    from referencing import Registry

    assert output_schema is not None, f"{name}: no advertised outputSchema"
    if result.structured_content is None and "structured_content" not in result.model_fields_set:
        raise RuntimeError(
            f"Tool {name} has an output schema but did not return structured content"
        )
    validator_cls = validator_for(output_schema)
    validator_cls.check_schema(output_schema)
    validator = validator_cls(output_schema, registry=Registry())
    error = jsonschema_exceptions.best_match(validator.iter_errors(result.structured_content))
    if error is not None:
        raise RuntimeError(f"Invalid structured content returned by tool {name}: {error}")


# ---------------------------------------------------------------------------
# Advertisement: exactly the batch-1 set
# ---------------------------------------------------------------------------

class TestAdvertisement:
    def test_only_batch1_advertises_output_schema(self):
        srv = _get_srv()
        tools = asyncio.run(srv.list_tools())
        advertised = {
            t.name for t in tools if getattr(t, "output_schema", None) is not None
        }
        assert advertised == BATCH_1

    def test_gate_is_the_explicit_batch1_set(self):
        srv = _get_srv()
        assert set(srv.STRUCTURED_OUTPUT_TOOLS) == BATCH_1
        # Every batch-1 tool also carries an output_model (both conditions
        # of the list_tools gate), and no other tool is in the gate set.
        from flextoolsmcp.server.tool_definitions import TOOLS

        for name in BATCH_1:
            assert TOOLS[name].output_model is not None


# ---------------------------------------------------------------------------
# Golden byte-identity + structured derivation (success and error)
# ---------------------------------------------------------------------------

class TestGoldenByteIdentity:
    @pytest.mark.parametrize("tool_name", sorted(BATCH_1))
    def test_success_text_byte_identical_and_structured_attached(self, tool_name):
        payload = _success_payloads()[tool_name]
        content = json_response(payload)
        golden_text = content[0].text

        result = _run_adapter(tool_name, content)

        assert not result.is_error
        # Golden comparison: text bytes unchanged by the structured plumbing.
        assert len(result.content) == 1
        assert result.content[0].text == golden_text
        assert result.structured_content == payload

    @pytest.mark.parametrize("tool_name", sorted(BATCH_1))
    def test_error_text_byte_identical_and_no_structured(self, tool_name):
        content = error_response("runtime_error", "boom", tool=tool_name)
        golden_text = content[0].text
        parsed = json.loads(golden_text)
        assert parsed["status"] == "error" and parsed["error_code"] == "runtime_error"

        result = _run_adapter(tool_name, content)

        assert result.content[0].text == golden_text
        assert result.structured_content is None

    def test_noncanonical_text_bytes_preserved_verbatim(self):
        # A payload whose text is NOT json.dumps(indent=2) output: if the
        # adapter re-serialized anything, these bytes would change.
        raw = '{"status":  "ok", "_contract": "tool-responses/1.0",   "success": true}'
        content = [TextContent(type="text", text=raw)]
        result = _run_adapter("flextools_run_module", content)
        assert result.content[0].text == raw
        assert result.structured_content == {
            "status": "ok", "_contract": "tool-responses/1.0", "success": True,
        }

    def test_session_note_in_final_text_reaches_structured_content(self):
        # call_tool rewrites the text to inject _session_note BEFORE the
        # adapter runs; deriving from the final text means the structured
        # payload carries the note too (deriving earlier would diverge).
        payload = dict(_success_payloads()["flextools_search_by_capability"])
        payload["_session_note"] = "Session auto-initialized (flexicon, read-only)."
        content = json_response(payload)
        result = _run_adapter("flextools_search_by_capability", content)
        assert result.structured_content == payload
        assert result.structured_content["_session_note"].startswith("Session auto-")

    def test_status_error_without_error_code_attaches_nothing(self):
        content = json_response({"status": "error", "message": "nope"})
        result = _run_adapter("flextools_get_object_api", content)
        assert result.structured_content is None
        assert result.content[0].text == content[0].text

    def test_non_batch1_tool_attaches_nothing(self):
        payload = {"status": "ok", "_contract": "tool-responses/1.0", "projects": []}
        content = json_response(payload)
        result = _run_adapter("flextools_list_projects", content)
        assert result.structured_content is None
        assert result.content[0].text == content[0].text


# ---------------------------------------------------------------------------
# Client-side conformance against the advertised schemas
# ---------------------------------------------------------------------------

class TestClientConformance:
    def test_structured_content_validates_against_advertised_schema(self):
        srv = _get_srv()
        tools = {t.name: t for t in asyncio.run(srv.list_tools())}
        payloads = _success_payloads()
        for tool_name in sorted(BATCH_1):
            content = json_response(payloads[tool_name])
            result = _run_adapter(tool_name, content)
            schema = getattr(tools[tool_name], "output_schema", None)
            # Raises RuntimeError exactly where the SDK client would.
            _client_validate(tool_name, schema, result)

    def test_advertised_schema_requires_traced_keys(self):
        # The tightened doc-search schemas must actually REQUIRE the
        # always-present keys -- a shell schema with no required fields
        # was the pre-Phase-2 vacuity.
        srv = _get_srv()
        tools = {t.name: t for t in asyncio.run(srv.list_tools())}
        get_required = set(tools["flextools_get_object_api"].output_schema["required"])
        assert {"status", "_contract", "object_type", "found", "api_mode"} <= get_required
        search_required = set(
            tools["flextools_search_by_capability"].output_schema["required"]
        )
        assert {
            "status", "_contract", "query", "api_mode", "results",
            "results_count", "recipes",
        } <= search_required


# ---------------------------------------------------------------------------
# Cycle-2 QC P0: off-schema SUCCESS payloads must attach NOTHING.
#
# run_module's validate_only mode (issue #49) returns status "validated" /
# "validation_failed" with no error_code -- a success-shaped payload the
# advertised RunModuleSuccess schema rejects (status is Literal["ok",
# "error"]). Before the fix, derive_structured_content attached it anyway
# and a spec-compliant client hard-failed an otherwise successful call.
# The fix validates the derived dict against the advertised outputSchema
# inside derive_structured_content and attaches nothing on mismatch; the
# derivation is also fully exception-safe (it must never fail a call).
# ---------------------------------------------------------------------------


def _real_validate_only_content(monkeypatch, tmp_path, code):
    """Drive the REAL handle_run_module(validate_only=True) path and return
    its TextContent list -- the exact shape _handle_validate_only emits
    (payload capture pattern: tests/test_issue49_validate_only.py)."""
    from test_issue49_validate_only import _stub_agreement_env

    from flextoolsmcp.server.handlers import execution as execution_mod

    _stub_agreement_env(monkeypatch, tmp_path)
    args = {
        "code": code,
        "project_name": "TestProj",
        "write_enabled": False,
        "skip_api_check": True,
        "skip_module_check": True,
        "validate_only": True,
    }
    return asyncio.run(execution_mod.handle_run_module(args))


class TestOffSchemaSuccessPayloadsAttachNothing:
    @pytest.mark.parametrize(
        "code,expected_status",
        [
            # All gates pass -> "validated" (test_issue49 agreement fixture).
            ("def f(ana):\n    return ana.CategoryRA\n", "validated"),
            # A genuine typo gate failure -> "validation_failed".
            ("d = ILexDb(project)\nx = d.EntriesOC\n", "validation_failed"),
        ],
    )
    def test_real_validate_only_payload_attaches_no_structured_content(
        self, monkeypatch, tmp_path, code, expected_status
    ):
        content = _real_validate_only_content(monkeypatch, tmp_path, code)
        payload = json.loads(content[0].text)
        # The fixture really is the P0 shape: a non-error status the
        # advertised schema does not admit, and no error_code key.
        assert payload["status"] == expected_status
        assert "error_code" not in payload

        srv = _get_srv()
        tools = {t.name: t for t in asyncio.run(srv.list_tools())}
        schema = tools["flextools_run_module"].output_schema
        # ...and it genuinely fails the advertised schema (the client trap).
        from jsonschema.validators import validator_for
        from referencing import Registry

        validator = validator_for(schema)(schema, registry=Registry())
        assert list(validator.iter_errors(payload)), (
            "fixture no longer off-schema -- this test has gone vacuous"
        )

        result = _run_adapter("flextools_run_module", content)
        assert result.structured_content is None
        # Text payload untouched, byte for byte.
        assert result.content[0].text == content[0].text

    def test_payload_failing_advertised_schema_attaches_nothing(self):
        # A batch-1 success payload mutated off-schema (here: a required
        # key's value no longer matches the advertised model) must degrade
        # to text-only, never attach off-schema structuredContent.
        payload = dict(_success_payloads()["flextools_get_object_api"])
        payload["found"] = "not-a-bool"
        content = json_response(payload)
        result = _run_adapter("flextools_get_object_api", content)
        assert result.structured_content is None
        assert result.content[0].text == content[0].text

    def test_derive_never_raises_on_malformed_content(self):
        # Cycle-2 QC P2: content[0] was indexed before any type check, so
        # dict/int content raised out of the derivation seam. Derivation
        # must return None for ANY malformed input instead of propagating.
        srv = _get_srv()
        assert srv.derive_structured_content("flextools_run_module", {"0": "x"}) is None
        assert srv.derive_structured_content("flextools_run_module", [123]) is None
        assert srv.derive_structured_content("flextools_run_module", "text") is None
        assert srv.derive_structured_content("flextools_run_module", []) is None
        assert srv.derive_structured_content("flextools_run_module", None) is None
