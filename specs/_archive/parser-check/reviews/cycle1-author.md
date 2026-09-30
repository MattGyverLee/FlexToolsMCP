# Original Author Review — cycle1

**Status:** CONCERNS — architecture correction absorbed; below is the redesigned surface.

> Filed by the orchestrator on the reviewing agent's behalf: the subagent was
> provisioned with Read/Grep/Glob only and had no Write tool. Content is the
> agent's verbatim report.

## 1. Tool surface

| Tool | Purpose | Mode(s) | R/W | Key args |
|---|---|---|---|---|
| `flextools_parse` | Run FLEx's in-process parser over a scope | 1 (write) & 2 (read) | **conditional** — see §2 | `project_name`, `scope`, `words`/`text_name`/`genre`, `apply` (bool, default `false`), `limit`, `trace` |
| `flextools_parse_diff` | Before/after comparison of two runs | 1 or 2 (whatever produced the runs) | inherits inputs' mode; itself read-only | `baseline`, `current="parse_now"`, `force`, `include` |
| `flextools_parse_log` | Read run artifacts (results, traces, config-gen log) | any | read-only | `run_id`, `section`, `word`, `filter`, `lines`, `offset` |
| `flextools_parse_test` | Run mode 3 (export + `hc.dll`) — the hardened `hcparse.ps1` spine | 3a (read) & 3b (may write via mode-1 filing) | **conditional**, same rule as `flextools_parse` | `project_name`, `words`/`scope`, `apply`, `config_policy`, `label` |
| `flextools_parse_overgeneration` | Report analyses that over-succeed (G3) | any completed run | read-only | `run_id`, `min_analyses`, `limit`, `filter` |
| `flextools_health` parser block | Preflight for both spines | n/a | read-only | (unchanged from spec 5.4, extended per §5 below) |

**Fewer top-level names than the spec's four (`parse`/`diff`/`log` + health), but two tools instead of one for "run a parse" — `flextools_parse` (in-process, drives FLEx directly) and `flextools_parse_test` (export/CLI, `hc.dll`).** These are genuinely different execution mechanisms with different failure modes (`project_locked` vs. `parser_tool_missing`), so collapsing them into a `mechanism` enum would hide which subsystem a caller is depending on — the same reasoning the repo already applies to keeping `flextools_run_module` separate from `flextools_manage_config` rather than a single `flextools_do` with an action enum. `flextools_parse_diff` and `flextools_parse_log` stay single tools because they are genuinely mode-agnostic consumers of run artifacts.

**Is "mode" an argument or are modes separate tools?** Neither cleanly. Mode 1 vs. mode 2 is **not** a caller-selected mode at all — it is a consequence of `apply` (see §2). Mode 3 is a separate *tool* (`flextools_parse_test`) because it is a separate *mechanism*, matching how the repo puts `write_enabled` inside `flextools_run_module` (one execution path, write is a flag) but keeps `flextools_prepare_report` as its own tool rather than an action on `run_module` (different mechanism, own gates).

## 2. Safety annotation — the concrete rule

Follow the `flextools_run_module` precedent exactly, do not invent a new shape: `readOnlyHint` on the **tool definition** stays `False` whenever a write is *reachable* through that tool, because MCP client UIs gate on the static annotation, not runtime args. So `flextools_parse` and `flextools_parse_test` both get `ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)` — same shape as `run_module` — never `READ_ONLY_SAFE`, even though most calls (`apply=false`) don't write. This is the opposite of "hide the write behind an argument": the *tool* is honestly annotated write-capable; the *argument* (`apply`, default `false`) is what actually gates the write at runtime, mirroring `write_enabled` on `run_module`.

The concrete pre-call rule for an LLM caller: **if the tool's annotation says `readOnlyHint=False`, assume every call *can* write until `apply` is inspected in the response** (`applied: true/false` echoed back, mirroring `executed` in the discovery-redirect shape). `apply=false` is mode 2 (hypothesis testing, LCM never touches disk); `apply=true` is mode 1. Defaulting `apply` to `false` means a caller who never reads the argument gets the safe behavior by construction — argument-gating is fine *because* the tool-level annotation never lies about capability, closing the exact hazard named in the prompt (a tool safe in one mode, destructive in another, with no static signal).

## 3. Where mode 1's write sits relative to existing gates

Mode 1 (`apply=true`) is a write and must pass the **same** ladder as `run_module`: `write_enabled` must be true for the session, `require_write_confirmation` (default `True`, `config.py`) means the first call returns `confirmation_required` with the mutation plan (projected analysis count, words affected) instead of executing, and the resubmit needs `confirmed=True`. Before the first confirmed mutating parse per (session, project), `perform_pre_write_backup` (`src\flextoolsmcp\server\backup.py`) fires exactly as it does for `run_module`, including its 2x-free-space skip/WARN. Mode-1 writes should **also** route through `execution.py`'s existing `needs_lock` / mutating-script machinery rather than a parallel path — a batch of hundreds of `IWfiAnalysis` filings is exactly the profile `unprotected_writes` and the backup gate exist for, and duplicating that logic for parser writes risks exactly the kind of silent bypass `write-authorization-audit`'s SPEC documents. **A "set it and forget it" unattended batch parse must not run**: `require_write_confirmation` defaults on, and nothing in this feature should introduce a bypass flag — that would recreate the audited hole (`confirmed` asserted by the model, never verified as human assent). 3b's DB write is explicitly routed through mode 1's filing path per the correction, so it inherits this same ladder, not a separate one.

## 4. G3 surface (overgeneration — interface only)

New tool, `flextools_parse_overgeneration(run_id, min_analyses=2, limit=20, filter="all"|"ambiguous_growth")`, not a section of the parse response and not a filter mode of `flextools_parse_log`. Rationale: the parse response's `failures_preview` (cap 10) is about words that *didn't* parse; overgeneration is about words that parsed *too well*, a disjoint population that would double the response's payload for a population most calls don't care about — same "never inline the whole set" rule (5.1) applies, so it needs its own capped, on-demand door. It reads from the same `run.json` (no new run artifact), returning `{run_id, overgenerating_count, preview: [{word, analysis_count, top_analyses: [...]}], full_detail_hint: "flextools_parse_log(section='results', word=...)"}` — capped preview, drill-down via the existing log tool, exactly like `failures_preview` today.

## 5. Checkpoint resequence

| CP | Mode | Deliverable | First that writes? |
|---|---|---|---|
| **CP1** | — | Health parser block for *both* spines (in-process FLEx probe + hc.dll/dotnet/GenerateHCConfig detection); no parsing | No |
| **CP2** | 2 | `flextools_parse(apply=false)` in-process, `scope="words"` only — proves FLEx's parser is driveable headless at all | No |
| **CP3** | 1 | `flextools_parse(apply=true)` — write-ladder wiring (confirmation, backup, lock) on top of CP2's plumbing | **Yes, first write** |
| **CP4** | 3a/3b | Hardened `hcparse.ps1` (spec §9) + `flextools_parse_test`, 3b's write routed through CP3's filing path | Yes (via CP3) |
| **CP5** | all | Scope resolution (§6), config cache (§7), `flextools_parse_diff`, `flextools_parse_log`, overgeneration tool, telemetry, contract docs | — |

**If headless FLEx-parser feasibility comes back negative**, CP2/CP3 collapse: mode 1 and mode 2 become unreachable, and the feature degrades to exactly the spec's original shape — CP1 (health), CP4 (hardened script + `flextools_parse_test`, mode 3a only, no filing path since mode 1 doesn't exist), and CP5's scope/diff/log/overgeneration machinery, all of which are mechanism-agnostic and survive untouched. That is the argument for building scope resolution, diff, and log against run-artifact shape rather than against either mechanism directly — it is the one piece of the spec's original architecture worth keeping as-is.

---

## Orchestrator addendum — evidence that lands after this review

Two source facts verified after this report was written bear directly on its CP4 row:

1. **`ParseMorph` holds live LCM object references, not strings** (`ParseResult.cs:154-177`:
   `IMoForm m_form`, `IMoMorphSynAnalysis m_msa`, `ILexEntryInflType m_inflType`,
   `string m_guessedString`). Since `ParseFiler.ProcessParse` takes a typed
   `ParseResult`, a `ParseResult` **cannot** be faithfully reconstructed from the
   CLI tool's text output. **Mode 3b is therefore not buildable over the
   export/CLI path**; 3b must run in-process like mode 1, and the CLI spine
   supports 3a only. CP4's "3b's write routed through CP3's filing path" needs
   rewriting on that basis.
2. **`IsValid` is not a linguistic validity notion.** `ParseMorph.IsValid` is
   `Form.IsValidObject && Msa.IsValidObject && (m_inflType == null || m_inflType.IsValidObject)`
   (`ParseResult.cs:199-202`), and `ParseAnalysis.IsValid` is
   `Morphs.All(morph => morph.IsValid)` (`:86-89`). It is an LCM object-liveness
   / stale-reference guard. It contributes nothing to G3's "invalid parses" half.
