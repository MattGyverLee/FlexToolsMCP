# FlexToolsMCP — Project TODOs

Open questions and follow-up work, tracked in the repo so they survive between sessions.

---

## P1: Return structuredContent so outputSchema can be re-advertised (issue #54 follow-up / "Option B")

**Status:** done for batch 1; batch 2 is the remaining follow-up  **Added:** 2026-07-08  **Resolved:** 2026-10-11 by issue #369 (MCP modernization)

**What landed (#369):** the server is now `mcp` 2.x-only (`mcp>=2,<3` in
`pyproject.toml` and `requirements.txt`); the `mcp_compat` dual-support shim is
deleted and its 2.x adapter is inlined in `server.py` on the low-level `Server`
(no FastMCP dependency exists in `pyproject.toml` or `requirements.txt`, and
none was introduced). `list_tools()` advertises `outputSchema` for the three
batch-1 tools -- `flextools_run_module`, `flextools_search_by_capability`,
`flextools_get_object_api` -- and the adapter derives `structuredContent` from
the final text payload, validating it against the advertised schema before
attaching it (a payload that does not validate, including every error
payload, is returned text-only). Text payload bytes are unchanged, guarded by
golden-compare tests; `tests/test_structured_output.py` asserts the three
tools advertise a schema and that real responses validate against it.

**Remaining follow-up (batch 2):** author output models and advertise
`outputSchema` for the next tier of tools -- `resolve_property`,
`find_examples`, `get_navigation_path`, `resolve_type` (after fixing its
non-envelope `{error:...}` branch), and the catalog/list_recipes tools. The
parse family, `flextools_start`, and health tools stay deferred (shape-variant
or stateful payloads). Each batch-2 tool needs the same treatment as batch 1:
a model traced from real handler payloads, validate-before-attach, and a
golden byte-compare of the text payload.

---

## P3: Remove legacy log-folder migration in the next major version

**Status:** open  **Added:** 2026-07-20  **Ref:** log-folder naming fix (session_id no longer sliced as a timestamp)

`kernel.migrate_legacy_session_logs()` (plus its helpers `_infer_log_datetime`
and `_unique_migration_target`, and the `_LEGACY_LOG_RE` / `_DATE_DIR_RE`
patterns) is a one-time healer for the malformed `auto*` log folders produced by
pre-fix builds that sliced a semantic `session_id` as if it were a
`YYYYMMDD-HHMMSS` timestamp. It runs best-effort on every startup via
`setup_logging()`.

Once the next major version ships, every active install will have started at
least once under the fixed code, so the malformed folders will already be gone
and the migration is dead weight. Remove:
1. `migrate_legacy_session_logs`, `_infer_log_datetime`, `_unique_migration_target`,
   `_LEGACY_LOG_RE`, `_DATE_DIR_RE` from `src/flextoolsmcp/server/kernel.py`.
2. The best-effort call block inside `setup_logging()`.
3. `test_migrate_legacy_session_logs` in `tests/test_cross_session_logging.py`.

Keep `_build_session_log_path` / `_sanitize_session_id` — those are the
permanent path builders, not migration code.

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

---

## Could the MCP propose analyses the user can accept, as its own agent?

**Status:** open · **Added:** 2026-09-15 · **Origin:** parser-check spec session (not in scope for that spec)

### The idea

Today an analysis is owned by either a parser agent or the human. If the MCP could
propose a `WfiAnalysis` the way a human does -- as a candidate the user reviews and
accepts in FLEx -- that opens a "suggest, don't file" mode: the AI offers a
decomposition, the analyst approves it in the normal FLEx workflow, and nothing is
written on the user's behalf.

### What the model already allows (verified, 2026-09-15)

`ICmAgent` is not a closed set. Agents are created via
`ICmAgentFactory.Create(guid, hvo, human: bool, version: string)` and added to
`LangProject.AnalyzingAgentsOC` (`BootstrapNewLanguageProject.cs:143-163`). Each
`CmAgent` owns exactly one `ApprovesOA` and one `DisapprovesOA` evaluation;
`SetEvaluation` adds/removes that singleton from `WfiAnalysis.EvaluationsRC`, and
"no opinion" is the absence of a reference (`OverridesCellar.cs:491-514`). A new
opinion-owner is therefore purely additive -- no schema change, no migration.

There is already a third agent meaning "machine, but not the parser":
`kguidAgentComputer` (`ConstantAdditions.cs:85`), exposed as `DefaultComputerAgent`
(`OverridesLangProj.cs:263-275`), bootstrapped with `human: false`. Its docstring:
"Get the analyzing agent representing the computer. Do not use this for the parser;
there is a dedicated agent for that purpose." `OpinionAgent` is a three-value enum --
`Computer = -1`, Parser, Human (`AnalysisGuessServices.cs:52-57`) -- and FLEx's own
guess machinery files under it.

### What stays safe

The human-approval oracle is structurally protected: `IsHumanApproved`,
`IsHumanDisapproved` and `IncludeAnalysis` all filter on
`((ICmAgent)ae.Owner).Human` (`AnalysisGuessServices.cs:238-297`), so a non-human
agent is invisible to them and cannot contaminate the G3 signal. `ParserStatusIcon`
reads `DefaultParserAgent` and `ApprovalStatusIcon` reads `DefaultUserAgent`
specifically (`OverridesLing_Wfi.cs:1489,1510`), so neither column is corrupted.
`AgentCount(agent)` is parameterized and works for any agent.

### Three hazards to design around

1. **ParseFiler deletes our analyses.** `ParseFiler.cs:312-315` checks ONLY the
   parser agent and the user agent: if both are `noopinion`, `analysis.Delete()`.
   An MCP-approved analysis with no parser and no human opinion is deleted on the
   next reparse of that wordform -- our evaluation confers no protection. A proposed
   analysis is fragile by construction; it survives only until the next parse touches
   that word. Any "propose" feature must either accept that lifetime or find another
   anchor.
2. **`IsFullyFormed` requires a human evaluation** (`OverridesLing_Wfi.cs:1161-1176`
   returns false when no eval has `.Human` true), so MCP-proposed analyses never read
   as complete without a human. Arguably correct, but it must be stated.
3. **Dissent has an invisible side effect.** `HasConflictingEvaluations` is
   `EvaluationsRC.Select(e => e.Approves).Distinct().Count() > 1`
   (`OverridesLing_Wfi.cs:1091`), and `IsFullyFormed` fails on it. An MCP
   disapproval of a parser-approved analysis silently makes it incomplete with no
   attributable cause in the FLEx UI. This is the one place a new agent genuinely
   distorts the model.

### Leaning

Prefer `DefaultComputerAgent` over minting a dedicated MCP agent: it exists in every
project, is semantically the right slot by its own docstring, and FLEx already has
services that understand it. The cost is losing attribution -- "MCP proposed this"
becomes indistinguishable from "FLEx guessed this." A dedicated GUID with `version`
set to the tool version is fully model-legal if attribution matters, but it is
invisible in every FLEx UI surface. Do NOT propose as the human agent
(`kguidAgentDefUser`) -- that is precisely the G3 oracle.

### Next step

Route to lex-domain for a proper ruling before any design work: confirm the deletion
lifetime in hazard 1 against a live project, and decide whether a transient proposal
is useful enough to build on.

### Incidental findings (worth acting on independently of this item)

- `ParseFiler.cs:309-310` ("ensure that used analyses have a user evaluation") writes
  a HUMAN approval on the user's behalf for any analysis in use in a segment. So
  `HumanApprovedAnalyses` already includes analyses no human assented to -- the G3
  oracle means "a human approved this, OR it was in a text when the parser ran."
  Worth writing into the parser-check oracle section regardless.
- `SetupAgents` bootstraps DefUser, XAmple and Computer but NOT HermitCrab
  (`BootstrapNewLanguageProject.cs:143-163`), yet `DefaultParserAgent` calls
  `GetObject(kguidAgentHermitCrabParser)`, which throws `KeyNotFoundException`. On a
  project that has never run HC that lookup may throw -- a live CP1/CP2 precondition
  for anything filing under the HC agent.
