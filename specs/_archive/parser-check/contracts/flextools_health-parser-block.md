# Contract -- `flextools_health`, `parser` block

**Checkpoint:** CP1 | **Annotation:** `READ_ONLY_SAFE` | **Contract version:**
`tool-responses/1.0` (additive; no bump)

Updated 2026-09-27 (issue #167): sandbox components follow the CP5 re-plan; the `hc` tool is retired and replaced with FieldWorks' bundled `fieldworks_hermitcrab` and `GenerateHCConfig.exe`.

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
    "fieldworks_hermitcrab_path": null,
    "generate_hc_config_path": null,
    "fieldworks_hermitcrab_version": null,
    "generate_hc_config_version": null
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

An **array**, not a singular value like `parser_tool_missing` -- the two components fail
independently and a caller must know which one to install:

```json
[{"component": "fieldworks_hermitcrab", "found": false, "expected_path": "..."},
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
- **`detected.parser_core_version` and version fields never decide.** No code path may compare
  them to a floor. Reported because they are the first things worth knowing in a bug report.
- **Sandbox component detection is filesystem-only.** CP5 re-plan: FieldWorks' bundled
  HermitCrab engine (`SIL.Machine.Morphology.HermitCrab.dll`) and `GenerateHCConfig.exe`
  are located via a plain directory check in the resolved FieldWorks install, never
  spawned or loaded; detection is cheap and deterministic. No process is executed and
  no assembly is loaded, so health stays fast.
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
| `sandbox.components[fieldworks_hermitcrab].found=false` | "repair or reinstall FieldWorks (SIL.Machine.Morphology.HermitCrab.dll missing)" | none (external) | n/a |
| `sandbox.components[GenerateHCConfig.exe].found=false` | "repair or reinstall FieldWorks (GenerateHCConfig.exe missing)" | none (external) | n/a |
| `sandbox: unavailable` (either component) | never propose `flextools_parse_sandbox` | -- | -- |
| `write: unavailable`, `signal: parser_agent_missing` | "this project has never run HermitCrab; run it once from FLEx's Parser menu, then retry filing" | `flextools_try_word` | inline |
| `active_engine` mismatch | "project is on {configured_engine}; HC tools refused" | none (external) | n/a |

**CP1 caveat.** Two rows name `flextools_try_word`, which does not exist until CP2.
SPEC 10.1 forbids proposing a tool that does not exist, so at CP1 those rows degrade
to the external-action wording with `tool: null`. The rows land in full at CP2, when
the tool they name is real.

**CP1 degradation, as shipped (T013).** `tool: null` alone is not enough for the
`write: unavailable` / `read: ready` row: its action text still names the tool in
prose, which is the same violation. At CP1 these two rows are emitted as:

| State | CP1 action | CP1 tool | est_cost |
|---|---|---|---|
| `write: unavailable`, `read: ready` | "filing is unavailable on this install; read-only parser diagnosis is unaffected." | `null` | inline |
| `write: unavailable`, `signal: parser_agent_missing` | unchanged (names no tool in prose) | `null` | inline |

The replacement text is literal. It deliberately does **not** say the read spine
confirms the grammar loads -- nothing at CP1 loads a grammar, so `read: ready`
means only that ParserCore's read surface is reachable.

The rungs are emitted as a list at the response's top level, in a
`parser_next_steps` key beside `parser` (each item in SPEC 10.1's
`{action, tool, args, rationale, est_cost}` shape) -- not inside the `parser`
block, whose key set is copied verbatim from SPEC 10.2 and is exactly the five
keys shown above. Every CP1 rung carries `tool: null`: the only rows with a tool
to name name `flextools_try_word`. `flextools_parse_sandbox` is never named while
either sandbox component is missing. The `active_engine` mismatch row never fires from
health at CP1, since health never opens a project and `active_engine` is always
`null`; that gate lives in the per-call preflight.

As of CP5 (FR-004, FR-005), both missing-component rows carry the same repair hint:
`GenerateHCConfig.exe ships with FieldWorks 9; repair or reinstall FieldWorks.`
Both components are located in the resolved FieldWorks directory and are discovered
via filesystem check only -- no process is spawned, no assembly is loaded, and the
discovery never blocks or times out. Whether an engine that is present actually loads
is a sandbox-worker question, not a health-time question (surfaces on the sandbox's
first `parse` instead).
