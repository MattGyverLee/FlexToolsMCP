# Contract -- `flextools_health`, `parser` block

**Checkpoint:** CP1 | **Annotation:** `READ_ONLY_SAFE` | **Contract version:**
`tool-responses/1.0` (additive; no bump)

A new top-level `parser` key on the existing `flextools_health` response. Every
existing key is unchanged. Shape is copied verbatim from SPEC 10.2.

---

## Shape

```json
"parser": {
  "read":    {"status": "ready|unavailable", "reason": null},
  "write":   {"status": "ready|unavailable", "reason": null},
  "sandbox": {"status": "ready|unavailable", "components": []},
  "active_engine": null,
  "detected": {
    "parser_core_version": null,
    "lcmodel_install_path": null,
    "hc_tool_version": null,
    "hc_path": null,
    "generate_hc_config_path": null
  }
}
```

**Exactly two states per spine** -- `ready` and `unavailable`. There is no third
`degraded` value; degradation lives in `reason` / `components`, reusing the
error-code detail vocabulary so health and error envelopes never drift apart.

**One dead spine must not blank the other two.** Per-spine, not blanket.

## `reason` shape

`read.reason` / `write.reason` carry `parser_core_missing`'s detail shape verbatim:

```
{signal, expected_path, detected_version, missing_members, lcmodel_install_path}
```

`write` additionally carries `agent_probe` (`present` | `absent` | `skipped`) and,
when `absent`, `{agent_guid, active_engine}`.

## `sandbox.components`

An **array**, not a singular value like `parser_tool_missing` -- the two tools fail
independently and a caller must know which one to install:

```json
[{"component": "hc", "found": false, "expected_path": "..."},
 {"component": "GenerateHCConfig.exe", "found": true, "expected_path": "..."}]
```

`component` is a **closed enum** shared with `parser_tool_missing`.

---

## Rules CP1 must honor

- **`read` vs `write` differ by exactly one member.** `write`'s member probe
  additionally requires `ParseFiler.ProcessParse`, making `read: ready` /
  `write: unavailable` representable.
- **The HC-agent probe is always `skipped` here.** `flextools_health` never opens a
  project (research D2), so `write.reason` records `agent_probe: "skipped"` and the
  status is decided by the member probe alone. **A skipped probe is never reported as
  a pass.**
- **`active_engine` is informational only** -- it echoes `ActiveParser` when a project
  is open, else `null`, and is never a status input. The mismatch gate lives in the
  per-call preflight.
- **`detected.parser_core_version` never decides.** No code path may compare it to a
  floor. Reported because it is the first thing worth knowing in a bug report.
- **`hc` detection must be bounded.** `dotnet tool list -g` runs with a timeout; a
  slow or hanging call reports the component as not found with the reason recorded,
  and never blocks the health response. (SPEC open question 8 left this unspecified;
  CP1 specifies it.)
- **No new detection logic in `diagnostic_health.py`.** It composes
  `parser_probe.ParserDetector`'s output and reshapes it. That module's docstring is a
  contract other code and tests rely on.

---

## `next_step` per unhealthy state

Copied from SPEC 10.2. No rung ever names a tool whose spine is `unavailable`.

| State | action | tool | est_cost |
|---|---|---|---|
| `read: unavailable` | "install/repair FieldWorks so ParserCore is reachable" | none (external) | n/a |
| `write: unavailable`, `read: ready` | "use read-only Try A Word; filing unavailable" | `flextools_try_word` | inline |
| `sandbox.components[hc].found=false` | "install the hc dotnet tool" | none (external) | n/a |
| `sandbox: unavailable` (either component) | never propose `flextools_parse_sandbox` | -- | -- |
| `write: unavailable`, `signal: parser_agent_missing` | "this project has never run HermitCrab; run it once from FLEx's Parser menu, then retry filing" | `flextools_try_word` | inline |
| `active_engine` mismatch | "project is on {configured_engine}; HC tools refused" | none (external) | n/a |

**CP1 caveat.** Two rows name `flextools_try_word`, which does not exist until CP2.
SPEC 10.1 forbids proposing a tool that does not exist, so at CP1 those rows degrade
to the external-action wording with `tool: null`. The rows land in full at CP2, when
the tool they name is real.

The install hint for `hc` is literally
`dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool` (SPEC H1). `hc` is a
dotnet **global tool**, located via PATH / `dotnet tool list -g` with a config
override -- *not* `%LOCALAPPDATA%\HermitCrabTool\hc.dll`, which is what the
contributed script wrongly assumed.
