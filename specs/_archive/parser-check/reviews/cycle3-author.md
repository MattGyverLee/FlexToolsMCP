# Cycle 3 -- Original Author Review: parser-check health contract

## 1. `flextools_health` parser block

Per-spine, not blanket -- one dead spine must not blank the other two.

```json
"parser": {
  "read":    {"status": "ready|unavailable", "reason": null},
  "write":   {"status": "ready|unavailable", "reason": null},
  "sandbox": {"status": "ready|unavailable", "components": []},
  "active_engine": null,
  "detected": {
    "parser_core_version": null, "lcmodel_install_path": null,
    "hc_tool_version": null, "hc_path": null, "generate_hc_config_path": null
  }
}
```

Two states per spine (`ready`/`unavailable`) -- no third "degraded" value; degrade lives in `reason`/`components`, reusing error-code detail vocabulary so health and error envelopes never drift apart:
- `read.reason` / `write.reason`: `{signal: "absent"|"foreign_install"|"incompatible_surface", expected_path, detected_version, missing_members, lcmodel_install_path}` -- `parser_core_missing`'s shape verbatim. `write` additionally requires `ParseFiler.ProcessParse` in its member probe; `write.status="unavailable"` even if `read.status="ready"` when only that member is missing.
- `sandbox.components`: array of `{component: "hc"|"GenerateHCConfig.exe", found, expected_path}` -- **not** singular like `parser_tool_missing`, because the two tools fail independently and a caller must know which one to install.

Licenses: `read: ready` -> `flextools_try_word` callable. `write: ready` -> `flextools_parse_text` callable (still walks the write ladder). `sandbox: ready` -> `flextools_parse_sandbox` callable. `active_engine` is informational only (echoes `ActiveParser` when a project is open, else `null`) -- never a status input; the mismatch gate lives in the per-call helper (#2), not here, since `ActiveParser` is a project property and health can run session-independent.

**Interface seam for the detection agent:** supply a `ParserDetector` returning `{read_probe: ProbeResult, write_probe: ProbeResult, sandbox_probe: {hc: ProbeResult, generate_config: ProbeResult}, active_engine: str|None, versions: {...}}` where `ProbeResult = {ok: bool, signal, expected_path, missing_members, detected_version}`. This handler only reshapes that into the block above -- no location/reflection logic here.

## 2. Shared preflight helper for `parser_engine_mismatch`

`check_active_parser(project, supported_engines=("HC",)) -> None`, raising the error dict on mismatch. Called as the **first statement** in each of the three spine-executing handlers (`try_word`, `parse_text`, `parse_sandbox`) -- before any `HCParser`/config-export construction. `parse_diff`/`parse_log`/`parse_status` never call it; they read prior artifacts and never touch the engine.

**Both mutability answers, designed for:**
- If `ActiveParser` is session-immutable: cache it once at project-open in `session_state`; helper and health's `active_engine` both read the cache -- cheap, no per-call LCM hit.
- If it can change mid-session: the helper must re-read live on every call (no caching), and `active_engine` in health is likewise a live read, documented as "true at call time only." For `parse_text`, the check still fires once at job submission (12.4's ladder is walked before the job starts, not per-word) -- a flip mid-job is out of scope, matching the per-result (not per-run) staleness posture already set for filing.

## 3. Reported-but-never-decides placement

`parser_core_version` lives only in `detected` (sibling of the status blocks) and in `run.json`'s metadata. Gating reads `read.status`/`write.status` (boolean member-probe results) exclusively. No code path may compare `detected.parser_core_version` to a floor -- this is a straight prohibition, not a threshold left at "TBD."

## 4. `next_step` per unhealthy state

| State | action | tool | args | est_cost |
|---|---|---|---|---|
| `read: unavailable` | "install/repair FieldWorks so ParserCore is reachable" | none (external) | -- | n/a |
| `write: unavailable`, `read: ready` | "use read-only Try A Word; filing unavailable" | `flextools_try_word` | `{}` | inline |
| `sandbox.components[hc].found=false` | "install the hc dotnet tool" | none (external) | -- | n/a |
| `sandbox: unavailable` (either component missing) | never propose `flextools_parse_sandbox` | -- | -- | -- |
| `active_engine` mismatch | "project is on {configured_engine}; HC tools refused" | none (external, switch engine in FLEx) | -- | n/a |

No rung ever names a tool whose spine is `unavailable` -- satisfies 10.1's "never propose a rung the project cannot reach."

## 5. Error-envelope field check

- `parser_core_missing`: fields (`signal`, `expected_path`, `detected_version`, `missing_members`, `lcmodel_install_path`, `install_hint`) fully cover `read`/`write.reason` -- no gap.
- `parser_engine_mismatch`: (`configured_engine`, `supported_engines`, `hint`) matches the helper exactly -- no gap.
- `parser_tool_missing`: (`component`, `expected_path`, `install_hint`) covers one `sandbox.components[]` entry, but **flag**: the code fires singular (one component per error), while health must report both `hc` and `GenerateHCConfig.exe` independently in one snapshot. Not a missing field, but confirm `component` is a closed two-value enum (`"hc"|"GenerateHCConfig.exe"`) so health's array and the error's single value stay in lockstep -- an open-ended string would let the two vocabularies drift.

**Recommendation:** APPROVE the shape above pending the `component` enum confirmation in #5.

---
**Reviewed By:** Original Author Agent (cycle 3)
