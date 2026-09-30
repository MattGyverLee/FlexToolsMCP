# Contract -- CP1 error codes

Four of SPEC 14's fourteen codes land at CP1. All are **additive**, so the contract
stays at `tool-responses/1.0`; the obligation is a row each in
`docs/TOOL-CONTRACT.md` and one CHANGELOG entry under **"Tool contract"** (SPEC 14).

Detail models go in `server/response_models.py` with
`model_config = ConfigDict(extra="forbid", populate_by_name=True)` and a `Literal`
discriminator, matching every model from `response_models.py:142` onward.

Field names below are **verbatim from SPEC 14**. Do not rename, recase or pluralize.

---

## `parser_engine_mismatch`

| Field | Type |
|---|---|
| `configured_engine` | str |
| `supported_engines` | list[str] |
| `hint` | str |

Raised by `check_active_parser(project, supported_engines=("HC",))`, called as the
**first statement** of each spine-executing handler, before any `HCParser` or
config-export construction. At CP1 no such handler exists yet, so the helper ships
with its tests and its first caller arrives at CP2.

`ActiveParser` is re-read **live on every call**, never cached per session -- it is
user-flippable mid-session via Words > Parser > Choose Parser. Accepted values are
exactly `"XAmple"` and `"HC"`, case-sensitive. **The getter defaults to `"XAmple"` on
any `ParserParameters` XML parse failure, so a corrupt value reads as XAmple and we
refuse -- fail-safe, never silently HC.**

`flextools_grammar_health` does **not** call this helper: it runs no parser and reads
no engine-specific object.

---

## `parser_core_missing`

| Field | Type |
|---|---|
| `signal` | `absent` \| `foreign_install` \| `incompatible_surface` \| `load_failed` |
| `expected_path` | str |
| `detected_version` | str or null |
| `missing_members` | list[str] |
| `lcmodel_install_path` | str or null |
| `install_hint` | str |
| `load_error` | str or null |

`signal` is a **closed enum shared with the health block's `read.reason` /
`write.reason`**, which is what keeps health and error envelopes from drifting.

- `foreign_install` -- ParserCore resolved from a directory other than the one
  supplying `SIL.LCModel.dll`. Mixing two FieldWorks versions across an in-process
  boundary is the failure no version floor would have caught.
- `incompatible_surface` -- a bound member from SPEC 5.4's enumerated set is absent;
  `missing_members` names it.
- `load_failed` -- a mismatched transitive dependency threw during `Assembly.LoadFile`
  before any member could be inspected. `load_error` carries the throw.

**`detected_version` is reported and never compared.** No code path may test it
against a floor; SPEC 16 carries the regression test for exactly this.

---

## `parser_agent_missing`

| Field | Type |
|---|---|
| `agent_guid` | str |
| `agent_name` | `"HermitCrab"` |
| `active_engine` | str |
| `probe_source` | `bootstrap_absent` \| `lookup_failed` |
| `hint` | str |

`BootstrapNewLanguageProject.SetupAgents` creates three agents and **not**
`kguidAgentHermitCrabParser`, while `LangProject.DefaultParserAgent` resolves it when
`ActiveParser == "HC"` -- with `KeyNotFoundException` as *documented* behaviour.

**Any handler that would resolve the agent raises this code instead of propagating
`KeyNotFoundException`.** That escape is the specific failure SPEC 16's test exists to
catch: a handler that dies mid-call tells the user nothing.

**The read spine is unaffected.** `flextools_try_word` neither files nor resolves an
agent, so a missing HC agent must never mark `read` unavailable -- the diagnosis this
feature exists to deliver stays available on exactly the projects most likely to lack
the agent.

**Open, and it does not block CP1** (SPEC 17.10): if a data migration or lazy path
materialises the agent elsewhere, this refusal downgrades to a warning. The probe
ships either way; only its verdict wording depends on the answer.

---

## `parser_tool_missing`

| Field | Type |
|---|---|
| `component` | `"hc"` \| `"GenerateHCConfig.exe"` (closed enum) |
| `expected_path` | str |
| `install_hint` | str |

`component` is **shared with `flextools_health`'s `sandbox.components[].component`**.

`install_hint` for `hc` is literally
`dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool`.

The two components fail independently, which is why health reports an array while the
error names one.

---

## Not at CP1

The remaining ten SPEC 14 codes belong to later checkpoints and are **not** stubbed
now -- an unreachable code in the contract table is a claim the server does not honor:

`grammar_load_unclean`, `parser_config_failed`, `parser_timeout`, `parser_job_failed`,
`parse_scope_empty`, `parse_scope_ambiguous`, `parse_scope_mismatch`,
`parse_run_not_found`, `parser_filing_in_progress`, `parse_morph_unresolved`.

---

## Documentation obligation

`docs/TOOL-CONTRACT.md` says "one of the **18** codes below". CP1 makes it **22**.
That count is hand-maintained; update it in the same change that adds the rows.
