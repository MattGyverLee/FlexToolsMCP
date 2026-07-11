# FlexToolsMCP — Project TODOs

Open questions and follow-up work, tracked in the repo so they survive between sessions.

---

## P1: Return structuredContent so outputSchema can be re-advertised (issue #54 follow-up / "Option B")

**Status:** open  **Added:** 2026-07-08  **Ref:** issue #54, blocks re-enabling outputSchema

**Background:** The tool-responses/1.0 work (ce98e51) wired `list_tools()` to advertise
`outputSchema` for the three tools with an `output_model` (run_module, get_object_api,
search_by_capability). But per MCP spec 2025-06-18, a tool advertising `outputSchema` MUST
return `structuredContent` matching it, and spec-compliant clients (e.g. Claude Code)
validate — and REJECT responses that advertise a schema but return text only. This server's
`call_tool()` returns text-only (`json_response()` -> `[TextContent]`), so the three tools
were broken for such clients.

**Applied as immediate hotfix ("Option A"):** the `outputSchema` advertisement in
`server.py list_tools()` is commented out (the `output_model` metadata on `ToolDef` is
retained). `tests/test_response_contract.py::TestOutputSchema` now guards that NO tool
advertises `outputSchema` until structured content is returned, and that the three tools
keep their `output_model` metadata for this follow-up. Requires an MCP server restart to
take effect (running process does not hot-reload).

**Option B (this TODO):** return structured content so the schemas can be re-advertised.
`mcp` 1.27.0's low-level `call_tool` accepts a handler returning `(list[ContentBlock], dict)`
where the dict becomes `structuredContent` and is validated against the advertised schema.
Handlers already build the response dict before JSON-dumping it, so return both. Work:
1. Change `call_tool()` return type and the three structured handlers to return the tuple.
2. **Critically**, confirm each handler's dict actually validates against
   `GetObjectApiSuccess` / `SearchByCapabilitySuccess` / `RunModuleSuccess` — the #54
   verification only checked the schema was EXPOSED, never that real responses conform.
   Missing required fields / type mismatches would just move the breakage client-side.
3. Re-enable the advertisement in `list_tools()` and flip `TestOutputSchema` back to
   asserting the three tools expose a non-null `outputSchema` PLUS a new test that a real
   handler response validates against its model.

**Do NOT migrate to FastMCP for this.** FastMCP's high-level `@mcp.tool` would populate
`structuredContent` automatically, but FastMCP was previously evaluated and found NOT a good
fit for this server (per maintainer). Option B is deliberately scoped to the low-level `mcp`
API's `(list[ContentBlock], dict)` tuple return, which requires no framework change. The
unused FastMCP 2.14 dependency is incidental and should not be treated as the intended path.

---

## P3: auto_fix_note source_hint — surface originating filename (issue #46 follow-up)

**Status:** open  **Added:** 2026-07-07  **Ref:** issue #46, deferred

`auto_fix_note` currently always reports "<submitted code>" as the source and
never names the originating file. Add a `source_hint` field that surfaces the
filename (or a short label) so log readers and UI callers can trace which file
the auto-fix was applied to without re-reading the full payload.

---

## Register TOOL-CONTRACT.md in docs/MANIFEST.md (issue #54 follow-up)

**Status:** open  **Added:** 2026-07-07  **Ref:** closes #54

`docs/TOOL-CONTRACT.md` was introduced in the tool-responses/1.0 contract commit but
`docs/MANIFEST.md` does not exist in this repo, so the file is not registered
in a manifest. Follow-up: either create `docs/MANIFEST.md` and register all
significant docs files, or confirm the project does not use a manifest
convention and close this item.

---

## Re-evaluate: does `flextools_start_module` still earn its slot?

**Status:** open · **Added:** 2026-05-01

### The question

`flextools_start_module` is an interactive wizard that asks 5 required + 1 conditional + 1 optional question, then synthesizes a module template. Meanwhile `flextools_get_module_template` returns the same authoritative template directly, and `flextools_start`'s runtime primer already pushes the invariants the wizard is gesturing at. Is the wizard still pulling its weight, or is it ceremony the AI can route around with one `get_module_template` call?

### What to evaluate

- **Usage in real sessions.** How often is `start_module` actually called vs. `get_module_template`? If it's rarely called, that's signal.
- **Output divergence.** When `start_module` IS called, how does its generated template differ from what `get_module_template` would have returned plus a normal authoring step? Is there scaffolding only the wizard produces?
- **Conversational redundancy.** The wizard's questions (module_name, synopsis, api_target, modifies_db, domain) are almost always already answered in the user's request before the AI ever calls a tool. Asking them again may be friction, not safety.
- **Auto-injected guard overlap.** The wizard's headline safety feature is auto-injecting `if modifyAllowed:` on writes — but the runtime primer + gate 4 already enforce this independently. The wizard's contribution is making the guard *visible in the source* rather than enforced at validation. That has value, but it's not unique to the wizard if `get_module_template` produces the same scaffold.
- **Maintenance cost.** Two tools generating templates means two places to keep style-guide-aligned. Drift is a real risk.

### Possible outcomes

1. **Keep it** — usage data shows it adds value (e.g. when the AI doesn't know the user's intent yet, the structured Q&A surfaces requirements faster than free-form conversation).
2. **Fold it into `get_module_template`** — make the template tool accept the wizard's inputs as optional parameters and emit the same scaffold. One tool, no Q&A round-trip.
3. **Deprecate it** — runtime primer + `get_module_template` + gate 4 already cover the safety surface. Remove the wizard, keep the template.

### Next step

Pull operation logs and count `start_module` vs. `get_module_template` invocations across recent sessions. If the ratio is heavily skewed toward `get_module_template`, that's the answer — propose folding or deprecating in a follow-up plan doc.
