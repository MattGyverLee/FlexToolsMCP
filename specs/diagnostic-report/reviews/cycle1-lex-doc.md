# Doc Agent Report — cycle 1

**Date:** 2026-07-13
**Trigger:** diagnostic-report SPEC.md §11.5 (Q5), issue #71

## Q5 answer: fits tool-responses/1.0 as-is — no bump needed

**`diagnostic_report` advisory block:** Additive, backward-compatible. It is a
new *optional* field on `RunModuleSuccess` (`response_models.py`), null/absent
when no reportable error fired — structurally identical to the precedent
already shipped in the same contract version: `auto_fixes_applied` /
`auto_fix_note` (issue #46) and `auto_discovered` / `inline_discovery` /
`discovery_note` (issue #47), documented in TOOL-CONTRACT.md's "RunModuleSuccess
envelope" section (lines 132-146). `BaseEnvelope` uses `extra="ignore"` and
existing consumers already tolerate unknown top-level keys. The contract's own
stability promise ("`error_code` strings and all existing keys are append-only
within a major version" — TOOL-CONTRACT.md line 97-98) explicitly covers this:
adding a new optional key is append-only, not a removal/rename, so it does not
trigger the "bump major version + CHANGELOG under 'Tool contract'" rule.
`CONTRACT_VERSION = "tool-responses/1.0"` (response_utils.py:19) is a single
literal constant with no `.1`/`.2` minor-tick precedent anywhere in the repo —
prior additive fields landed under the same `1.0` string. **Recommend the same
here: no version-label change at all**, just a new documented block in
TOOL-CONTRACT.md's RunModuleSuccess section (fields: `signature`, `title`,
`summary`, `report_path`, `transports`), added when the field itself ships.

**`user_request` passthrough arg:** Not a contract change under this document
at all. TOOL-CONTRACT.md governs the *response envelope* (success/error
shapes, error codes, the nested-`error` deprecation) — it says nothing about
tool *input* schemas. An optional input argument on `flextools_start` /
`run_module` that existing callers can omit (falling back to `user_intent`,
per SPEC §4) is a tool-input-surface addition, versioned (if at all) by
whatever governs MCP tool schemas elsewhere in this repo — out of scope for
TOOL-CONTRACT.md. No entry needed there.

**Net:** ship both under `tool-responses/1.0`. Add a "diagnostic_report"
subsection to TOOL-CONTRACT.md's existing RunModuleSuccess table (same style
as the issue #47 table) when the field lands; no `_contract` value change,
no CHANGELOG "Tool contract" heading (that's reserved for removals/renames).

## Open follow-ups
- When the field ships, patch TOOL-CONTRACT.md RunModuleSuccess section
  (mechanical, Doc Agent can do this in the same pass as the code PR).
- SPEC §4 already flags `user_request` as "a small, additive contract change"
  — that phrasing should be corrected to "additive *input* change" to avoid
  conflating it with the response-envelope contract this doc governs.

---
**Doc Agent:** /lex-doc
