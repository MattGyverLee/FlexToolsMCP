# Cycle 8 -- Doc Agent Report

**Trigger:** lead-review finding on cycle 7 -- `docs/TOOL-CONTRACT.md` did not
mark the required fields introduced by the four parser-check detail models,
contradicting line 95 ("optional unless noted").

## Verification against `response_models.py` (line by line)

- `ParserEngineMismatchDetail` (L360-371): `configured_engine: str`,
  `supported_engines: List[str]`, `hint: str` -- no defaults on any. All
  three required. Matches finding.
- `ParserCoreMissingDetail` (L374-389): `signal` (Literal, no default),
  `expected_path: str` (no default), `detected_version: Optional[str] = None`,
  `missing_members: List[str]` (no default), `lcmodel_install_path:
  Optional[str] = None`, `install_hint: str` (no default), `load_error:
  Optional[str] = None`. Required: signal, expected_path, missing_members,
  install_hint. Optional/nullable: detected_version, lcmodel_install_path,
  load_error. Matches finding exactly.
- `ParserAgentMissingDetail` (L392-405): `agent_guid: str`, `agent_name:
  Literal["HermitCrab"]`, `active_engine: str`, `probe_source: Literal[...]`,
  `hint: str` -- no defaults anywhere. All five required. Matches finding.
- `ParserToolMissingDetail` (L408-419): `component: Literal[...]`,
  `expected_path: str`, `install_hint: str` -- no defaults. All three
  required. Matches finding.

No disagreement found; the supplied field lists were confirmed correct.

## Rows as they now read (`docs/TOOL-CONTRACT.md` lines 117-120)

```
| `parser_engine_mismatch` | `configured_engine` (required string), `supported_engines` (required list), `hint` (required string) |
| `parser_core_missing` | `signal` (required; `absent` | `foreign_install` | `incompatible_surface` | `load_failed`), `expected_path` (required string), `detected_version` -- **reported and never compared: there is no version floor**, this is a standing guarantee with a regression test behind it (SPEC 16), `missing_members` (required list), `lcmodel_install_path`, `install_hint` (required string), `load_error` |
| `parser_agent_missing` | `agent_guid` (required string), `agent_name` (required; always `"HermitCrab"`), `active_engine` (required string), `probe_source` (required; `bootstrap_absent` | `lookup_failed`), `hint` (required string) |
| `parser_tool_missing` | `component` (required; `"hc"` | `"GenerateHCConfig.exe"`), `expected_path` (required string), `install_hint` (required string) |
```

Notation follows the existing `project_locked` precedent (`` `guidance`
(required string) ``); no new legend or column added. Unlisted fields in
`parser_core_missing` remain unmarked, consistent with the "optional unless
noted" rule at line 95. Only `docs/TOOL-CONTRACT.md` was edited;
`response_models.py`, the `22` count, and the `tool-responses/1.0` version
string are untouched.
