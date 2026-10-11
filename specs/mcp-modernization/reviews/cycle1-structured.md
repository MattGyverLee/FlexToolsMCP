# Cycle 1 — Structured Output (`outputSchema` / `structuredContent`) Audit

**Role:** lex-structured, FlexToolsMCP issue #369 Phase 2. **READ-ONLY audit** —
no code was changed; this file is the only artifact.
**Base:** worktree `ftmcp-369` at `origin/main` `c1c751f`.
**Scope of Phase 2 (per issue):** wire existing Pydantic response models into
tool `outputSchema`, keep `TextContent` payloads unchanged, structured output
additive, start with the highest-traffic doc-search tools.

## Verdict up front

| Question | Answer |
|---|---|
| Can the 3 modelled tools advertise after plumbing work? | **Yes** — mechanically safe today (see §2 for why "safe" is weaker than it sounds). |
| Does today's validation prove handler dicts conform? | **No.** It proves invented minimal dicts and 2 golden files do not violate two shell models and one mostly-optional model (§2, §3). |
| Where does `structuredContent` attach? | In `mcp_compat.make_call_tool_handler` (2.x) and via the `(content, dict)` tuple return from `server.call_tool` (1.x) — one derivation point, parsing the **final** text payload (§1.3). |
| Does `structuredContent` carry envelope or inner payload? | The **full top-level envelope dict** — there is no inner wrapper; handlers spread everything top-level (§4). |
| Error path? | Attach **nothing** on `status == "error"` payloads in Phase 2 (§6). |
| Batch 1 | `flextools_run_module`, `flextools_search_by_capability`, `flextools_get_object_api` — after 3 preconditions (§5.1). Everything else needs a model authored first (§5.2). |

---

## 1. Return path trace and the attachment point

### 1.1 The path today

```
handlers/*.py  ──build dict──▶  json_response(dict)            response_utils.py
                                  └─ [TextContent(text=json.dumps(dict, indent=2))]
                               ─▶ dispatch.py DISPATCH_ROUTES (name → handler, input_model)
                               ─▶ server.py call_tool(name, arguments) -> list[TextContent]
                                    · session gate / Pydantic arg validation
                                    · await handler(dumped_args)
                                    · post-pass: parses result[0].text, may inject
                                      `_session_note`, re-serializes the text
                               ─▶ mcp_compat.build_server()
                                    · 1.x: srv.call_tool()(call_tool) decorator
                                    · 2.x: make_call_tool_handler() wraps the list in
                                      CallToolResult(content=list(content))
```

Every handler returns `list[TextContent]`; the dict exists only transiently
inside `json_response()` / `error_response()` (`src/flextoolsmcp/response_utils.py`)
and inside a few handlers that build `TextContent` directly (e.g.
`handlers/discovery.py` navigation paths, `handlers/equivalence.py`).

`list_tools()` (`server.py:855-885`) builds `Tool(name, description,
annotations, inputSchema)`; the `outputSchema` lines are commented out with the
#54 follow-up note (advertise only together with returning `structuredContent`
AND after confirming handler dicts validate). That note is accurate and still
describes the current state exactly.

### 1.2 What the wire types allow

- **mcp 2.x (verified locally, mcp 2.3.0):** `mcp.types.CallToolResult` has
  fields `meta, content, structured_content, is_error, result_type`;
  `structured_content` is aliased `structuredContent` and accepts the camelCase
  kwarg (per `specs/_archive/mcp2-compat` dual-support analysis: 2.0 does
  **not** auto-normalize a tuple/dict return into `structuredContent` — the
  shim must do it). `mcp.types.Tool` has `output_schema` / `outputSchema`.
- **mcp 1.x (per `docs/TODO.md` Option B, mcp 1.27.0):** the low-level
  `call_tool` handler may return `(list[ContentBlock], dict)`; the dict
  becomes `structuredContent` and is validated against the advertised schema.

### 1.3 Exact attachment point (recommendation)

Do **not** change the 31 handlers and do **not** change `json_response`.

1. Keep handlers returning `list[TextContent]` — text bytes untouched.
2. In `server.call_tool`, after the existing `_session_note` post-pass (which
   already parses `result[0].text` and may rewrite it), parse the **final**
   text once more and keep the resulting dict as the structured payload.
   Deriving it *before* that post-pass would make `structuredContent` and the
   text disagree on cold-start calls.
3. Return `(content_list, structured_dict_or_None)` from `call_tool`.
   - 1.x decorator normalizes the tuple natively.
   - 2.x: `mcp_compat.make_call_tool_handler` (currently
     `return CallToolResult(content=list(content))`) unpacks the tuple and
     passes `structuredContent=structured_dict`. This is the single 2.x seam;
     `build_server` already routes everything through it.
4. Attach only when the tool has an `output_model` and the payload passes the
   error-path rule in §6. Tools without a model keep returning text-only —
   additive, per-tool, exactly the Phase 2 shape.

**Two implementation traps:**

- **Never use `model_dump()` as the structured payload.** All Success models
  are `extra="ignore"`; a dump drops every real payload key (verified in §2:
  a real search payload dumps to just `status/_contract/op_id`).
  `structuredContent` must be the raw parsed dict, validated — not rebuilt.
- **Cost:** `structuredContent` duplicates the full payload next to its text
  mirror (the spec expects the serialized JSON in `content` too). Doc-search
  payloads (`get_object_api` full entity dumps) are the largest the server
  emits, so wire size roughly doubles for Batch 1 tools. Not a blocker; note
  it for the Phase 2 PR description.

---

## 2. Do the 3 modelled handlers' real dicts validate today?

**Formally yes, substantively barely.** Verified empirically in the venv
(mcp 2.3.0, pydantic 2.14.1) against representative payloads traced key-by-key
from `handlers/api.py` and `handlers/execution.py`:

| Payload (real shape) | `model_validate` | Client-side `jsonschema` vs generated schema |
|---|---|---|
| `get_object_api` found: `{object_type, found, api_mode, flexicon:{…}, session_context}` | ✅ passes | ✅ passes |
| `get_object_api` not-found: `{object_type, found, api_mode, message}` | ✅ passes | ✅ passes |
| `search_by_capability`: `{query, api_mode, api_mode_description, search_method, sources_searched, fallback_used, semantic_available, results_count, canonical_matches, results, worked_examples(_count), recipes(_count/_ambiguous), session_context}` | ✅ passes | ✅ passes |
| `run_module` golden `auto_fix_casting_applied.json` / `auto_fix_typo_applied.json` | ✅ passes (also the existing test) | ✅ passes |

Why this proves so little:

1. **`GetObjectApiSuccess` and `SearchByCapabilitySuccess` are shells.**
   `response_models.py:147-157`: each adds **zero** tool-specific fields to
   `BaseEnvelope` (`status`, `_contract`, `op_id`). With `extra="ignore"`,
   *any* JSON object validates.
2. **The generated JSON Schemas have no `required` fields at all** (every
   field carries a default) and no `additionalProperties` restriction.
   A spec-compliant client will therefore accept essentially any object —
   advertising these two schemas cannot break clients, but also gives them
   almost no usable contract beyond the envelope keys.
3. **`RunModuleSuccess` is the only real model** (11 optional fields:
   `auto_fixes_applied`, `auto_fix_note`, `auto_discovered`,
   `_inline_discovery`, `discovery_note`, `diagnostic_report`, `executed`,
   `discovery_redirect`, `capability_suggestions`, + envelope). Its handler
   path (`handlers/execution.py:185-195`) is also the only one that
   *guarantees* `status` is stamped (`"ok"`/`"error"` derived from the
   payload) before `build_response_with_context`.
4. **The real doc-search payloads carry neither `status` nor `_contract`.**
   `handlers/api.py` defines a **local** `build_response_with_context`
   (api.py:392) that shadows the `response_utils` version and adds only
   `session_context` — no contract stamp. (The `response_utils` version
   stamps `_contract` but still not `status`.) So the two highest-traffic
   tools violate the success-envelope guarantee in `docs/TOOL-CONTRACT.md`
   ("guaranteed keys: `_contract`, `status`, `op_id`") *today*, in text.
   Validation passes anyway only because both fields have model defaults.
   This is a pre-existing contract-vs-code drift that Phase 2 surfaces;
   it does not block advertising (nothing is required in the schema), but
   structured consumers reading `status` per the contract will find nothing.

**Consequence for Phase 2:** "confirm handler dicts validate" (the server.py
note's precondition) is satisfiable in an afternoon, but if Batch 1 ships the
shell models as-is, Phase 2 delivers protocol compliance without contract
value. §5.1 lists the cheap field additions that change that.

---

## 3. Existing validation: what was run, what it enforces

### 3.1 Runs (this audit)

System python has neither `pytest` nor `mcp` (collection impossible). The
throwaway venv was recreated per AGENTS.md
(`python3 -m venv /tmp/ftmcp-venv`, `mcp 2.3.0`, `pydantic 2.14.1`):

```
PYTHONPATH=src /tmp/ftmcp-venv/bin/python -m pytest tests/test_tool_output_model_validation.py -q
→ 6 passed in 5.97s

PYTHONPATH=src /tmp/ftmcp-venv/bin/python scripts/validate_integrity.py success_models
→ "tool output models: golden + minimal success payloads OK [OK]"

PYTHONPATH=src /tmp/ftmcp-venv/bin/python -m pytest tests/test_response_contract.py::TestOutputSchema -q
→ 2 passed   (guards that NO tool currently advertises outputSchema — must be flipped by Phase 2)
```

### 3.2 What the machinery actually enforces

`src/flextoolsmcp/tool_output_validation.py` (#152) + 
...[truncated 13430 chars]