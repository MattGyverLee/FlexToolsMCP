# Data Model -- parser-check, CP1

Entities CP1 introduces. Field names and enum values are copied verbatim from
[SPEC.md](./SPEC.md) 10.2 and 14; where a name appears in both, the spec's spelling
wins. Nothing here is a wire contract on its own -- see [`contracts/`](./contracts/)
for what is serialized.

CP1 introduces **no persisted state**. Every entity below is computed per call and
discarded. Run artifacts (SPEC 5.5) belong to CP2's job runner.

---

## `ProbeResult`

The atom of parser detection. One per probed capability. Defined by SPEC 10.2's
"interface seam for the detection agent".

| Field | Type | Notes |
|---|---|---|
| `ok` | bool | Whether this capability is reachable. Never `None` -- a probe that could not run reports `ok=False` with a `signal` saying why, and a *skipped* probe is represented outside this type (see `AgentProbeState`) |
| `signal` | str or null | Closed vocabulary per probe kind; shares `parser_core_missing`'s values for the member probe: `absent`, `foreign_install`, `incompatible_surface`, `load_failed` |
| `expected_path` | str or null | Where we looked. Populated even on success -- it is the first thing worth knowing in a bug report |
| `missing_members` | list[str] | Empty on success. Each entry is a bound member from SPEC 5.4's enumerated surface |
| `detected_version` | str or null | **Reported, never compared.** No code path may test this against a floor |

**Invariant.** `ok=True` implies `missing_members == []` and `signal is None`.
`detected_version` is independent of `ok` in both directions: an unexpected version
that passes the member probe is a pass (SPEC 16's regression test against a version
floor).

---

## `AgentProbeState`

Three-valued, because the HC-agent probe has a third outcome the other probes do not:
it may be unable to run at all. Modelled separately so `skipped` can never be
flattened into `ok=True`.

| Value | Meaning |
|---|---|
| `present` | Agent resolved from `ICmAgentRepository` |
| `absent` | `ActiveParser == "HC"` and `kguidAgentHermitCrabParser` not in the repository |
| `skipped` | No project open, so the probe could not run (D2 -- the normal case for `flextools_health`) |

**Invariant, and the one SPEC 16 tests directly: a `skipped` probe is never reported
as a pass.** When the state is `skipped`, `write`'s status is decided by the member
probe alone and the reason records `agent_probe: "skipped"`.

---

## `ParserDetector` return shape

What `parser_probe.py` hands to `diagnostic_health.py`. The health handler only
reshapes this; no location or reflection logic lives in the handler (SPEC 10.2).

| Field | Type |
|---|---|
| `read_probe` | `ProbeResult` |
| `write_probe` | `ProbeResult` -- additionally requires `ParseFiler.ProcessParse` in its member set |
| `sandbox_probe` | `{hc: ProbeResult, generate_config: ProbeResult}` |
| `agent_probe` | `AgentProbeState` plus `{agent_guid, active_engine}` when `absent` |
| `active_engine` | str or null -- `"XAmple"` \| `"HC"`, echoed only when a project is open |
| `versions` | `{parser_core_version, lcmodel_install_path, hc_tool_version}` |

**Why `read` and `write` are separate probes over one DLL.** They differ by exactly
one member: `write` additionally requires `ParseFiler.ProcessParse`. That makes
`read: ready` / `write: unavailable` representable when only that member is missing
-- a state SPEC 10.2 requires and a single boolean could not express.

**`active_engine` is informational only.** It never decides a status. The mismatch
gate lives in the per-call preflight, because `ActiveParser` is a project property and
health can run session-independent.

---

## `GrammarFinding`

One suspect from the static scan. Emitted by `grammar_scan_module.py`, interpreted by
`grammar_health.py`.

| Field | Type | Notes |
|---|---|---|
| `check_id` | str | Stable slug, e.g. `zero-surface-morph-repeatable`. Maps to a 9.5.4 row or to one of the three 9.5.1 causes PanGloss does not cover |
| `spec_row` | int or null | The 9.5.4 row this implements, or null for the three extras |
| `count` | int | How many objects tripped the check. **Evidence, not severity** |
| `objects` | list[`FoundObject`] | Capped preview (SPEC S7: responses summarise, never inline the full set) |
| `measured` | str | What was measured, in the wording of SPEC 8.4 -- "12 optional slots can host this zero-surface morph", never "this is wrong" |
| `evidence_basis` | str or null | PanGloss's measured factor where one exists (e.g. `"425x"` for row 1), labelled as *their* measurement on *their* corpus |

**What this type deliberately does not have** (D7, SPEC 9.5.3): no `severity`, no
`score`, no `grade`, no `rank`, no `priority`. Findings are grouped by `check_id` and
never ordered by `count`. A client must not be handed a field it could sort on as a
severity proxy -- a 2,044-state network ran ~1300x slower than a 106,365-state one, so
size and count are anti-correlated with cost.

`count` is present because a count is the measurement; what is forbidden is summing
counts into a total or ordering findings by them.

### `FoundObject`

| Field | Type | Notes |
|---|---|---|
| `hvo` | int | LCM object id |
| `class_name` | str | e.g. `MoStemAllomorph` |
| `label` | str | Best human-readable name; `""` when the field is empty, never `"***"` (flexicon normalizes -- `CLAUDE.md`) |
| `goto_url` | str or null | `project.BuildGotoURL(obj)` so the linguist can open it in FLEx |

---

## Validation rules

- **Closed enums are closed.** `signal`, `component`
  (`"hc"` \| `"GenerateHCConfig.exe"`), and `probe_source`
  (`bootstrap_absent` \| `lookup_failed`) are shared between the error payloads and
  the health block precisely so the two never drift. Adding a value is a contract
  change.
- **Error detail models use `extra="forbid"`**, matching every model from
  `response_models.py:142` onward. A typo'd field fails loudly rather than
  silently vanishing.
- **Empty multistring fields normalize to `""`, never `"***"`** on the flexicon path
  (`CLAUDE.md`). The scan module reads through flexicon where a wrapper exists; where
  it reads raw LCM it must normalize explicitly.
- **Disabled rules are excluded before counting.** `IPhSegmentRule.Disabled` gates
  every rule-based check (D4). A disabled rule cannot multiply paths, so including it
  manufactures a suspect the grammar never runs.

---

## State transitions

None. Every entity is computed per call and discarded; CP1 has no job, no run
artifact, and no cache. The first stateful entity in this feature is CP2's job
(`starting | loading_grammar | parsing | filing | completed | failed | cancelled`),
which is out of scope here.
