# Contract: `--sandbox` mode, the interface between `SandboxClient` and the parse worker

**New in CP5 (design of record, 2026-09-24).** This is the replacement for the Parse/Test half of
`contracts/hcparse.md`, retired the same day (see `HANDOFF.md` and
`reviews/research-cycle1-domain.md` for the decision, and `reviews/research-cycle1-qc.md` for the
open gaps this contract closes). Generate mode is unaffected and still governed by
`contracts/hcparse.md`.

**The one-line version.** Parse and Test no longer shell out to an `hc` console tool. They run
**in the existing parse worker** (`src/flextoolsmcp/server/parse/worker_main.py`), started in a
new `--sandbox` mode: one process per run, no flexicon, no LCM, no project, no files written. It
loads the FieldWorks HermitCrab engine directly through pythonnet and calls
`XmlLanguageLoader.Load` / `Morpher` / `ParseWord`, the same calls Try A Word makes. A
`SandboxClient` spawns this process directly, **outside** the server's `WorkerPool` (the pool that
manages the ordinary, project-bound `--project` workers) — a sandbox worker is not pooled, is not
keyed by project, and is not reused across an unrelated sandbox run.

## 1. Argv (spawn parameters)

```
python -m flextoolsmcp.server.parse.worker_main --sandbox --config <path-to-hc-config.xml>
    [--hc-params <path-to-json>] [--id-map <path-to-lcm-ids.json>] [--engine-dir <dir>] [--project <label>] [--named-sandbox]
```

| Argument | Required | Notes |
|---|---|---|
| `--sandbox` | yes | Selects this mode instead of the ordinary `--project` mode. Mutually exclusive with `--project`'s project-opening behaviour: no `OpenProject()` call, no LCM cache, no flexicon import |
| `--config` | yes | The `hc-config.xml` to load: a cache entry's or a named sandbox's (`data-model.md` sections 3 and 4). Loaded exactly once per process, at first `parse` (lazily, not at spawn — a spawned-but-unused worker holds no engine) |
| `--hc-params` | no | Path to a small JSON file carrying the Morpher parameters (`DelReapps`, `MaxRoots`, `MergeAnalyses`, `GuessRoots`, `MaxAlternatives`) sourced by the **client**, not the worker, per D3 below. Omitted entirely when no source has them, in which case FLEx's own defaults apply |
| `--id-map` | no (**new, D4 reversed, FR-050**) | Path to the config source's validated `lcm-ids.json` sidecar (`data-model.md` section 3), sourced by the **client**, same as `--hc-params`. When present and `valid`, the worker applies Try A Word's shaping rules a-d (section 4 below) against it. Omitted only when the config source predates the sidecar. In practice that is a named sandbox created before FR-050: cache entries cannot be in this state, because the `HCPARSE_VERSION` bump rebuilds them all. When it is omitted, no shaping rule is applied (`meta.sandbox.shaping.id_map: "absent"`, plus the `shaping_not_applied` advisory, `contracts/tools.md` section 5.1). That is disclosed, and it is never a refusal. A sidecar that exists but is invalid is never passed as "absent". The client never spawns a worker against a sidecar recorded `valid: false`; that is the check order's job (`contracts/tools.md` section 3) and it is the primary gate. The worker still re-checks the map before its first `parse` as a backstop (section 5), and fails `id_map_invalid` if the map is invalid or cannot be parsed (spec FR-050, "Who refuses an invalid map") |
| `--engine-dir` | no | The FieldWorks installation directory holding the HermitCrab DLL and its dependencies, for the `AssemblyResolve` handler (`reference/hc_fw_prototype.py`, `Engine.__init__`). Defaults to the path the server's engine-detection step already resolved (D6) |
| `--project` | no | A **label only**, for diagnostics and the run record (`meta.sandbox`, `data-model.md` 6.2) — never a project name to open. A sandbox worker never opens a FieldWorks project; this argument exists so `hc_stdout`-equivalent diagnostics can say which project's grammar a sandbox came from without the worker touching that project |
| `--named-sandbox` | no (**added at implementation, T096**) | Set when `--config` is a named sandbox's (user-editable) config. It is the only thing that switches on rule (a)'s `user_added` exception (section 4); a project-cache run never sets it, so a morph with no `ID` there is skipped as FLEx skips it |

`--sandbox` is checked first: it is a **routing** flag in `main()`, read before `--project` is
required, so a sandbox invocation never needs (and must reject, at argument-parsing time) a bare
`--project <name>` used the ordinary way.

## 2. The `ready` handshake

Identical in shape to the ordinary worker's `ready` message (module docstring, `worker_main.py`
line 94), because both spines share one `main()`:

```json
{"type": "ready", "protocol": 1, "project": "<--project label or null>", "pid": 12345}
```

Emitted **before** the config is loaded (loading is lazy, at first `parse`) and before the reader
thread starts, for the same reason the ordinary worker emits it early: a message already buffered
on the pipe must never race the handshake.

## 3. Accepted and refused messages (D1)

**Accepted**, all on the existing wire shape (module docstring):

- `{"type": "parse", "request_id": str, "run_id": str, "wordform": str, ...}` — see section 4.
  `level` is always effectively `"batch"` for a sandbox run (the sandbox client sends only this
  shape); other levels are not refused, but the sandbox backend answers them exactly as `batch`
  because there is no restricted/explain distinction without LCM morphs to restrict to.
- `{"type": "cancel", "run_id": str}` — cooperative, at the next word boundary, unchanged.
- `{"type": "ping"}` → `{"type": "pong"}`, unchanged.
- `{"type": "shutdown"}` — drains, unchanged.

**Refused**, because each assumes a live, opened FieldWorks project that a sandbox worker never
has (`reviews/research-cycle1-qc.md` section 2 enumerates exactly these): `resolve`,
`engine_check`, `resolve_scope`, `parser_parameters`, `agent_probe`, `filing_gate`,
`filing_preview`, and any `parse` message carrying a non-null `restricted_to`. Each is answered
with the worker's ordinary error line, unchanged in shape from the "unknown message type" branch
(`handle_message`, `worker_main.py` ~line 2061):

```json
{"type": "error", "request_id": "<echoed, or null if absent>", "run_id": "<echoed, or null>",
 "error_code": null, "detail": null, "message": "not available in sandbox mode"}
```

`error_code` stays `null` deliberately: this is not a typed protocol error the server maps to a
tool-response error model (`docs/TOOL-CONTRACT.md`), it is a same-process contract violation — the
`SandboxClient` is the only caller, and it must simply never construct one of these messages
against a sandbox worker. A test pins that `SandboxClient` cannot do so (mirrors the CP1 boundary
discipline: refusal is a second line of defense, not the primary one).

**CP1 boundary note (closes QC finding P0).** `_SandboxBackend`'s in-process
`XmlLanguageLoader.Load` / `Morpher(...)` construction is a deliberate, allowlisted crossing of the
same boundary `test_cp1_boundary.py` polices for the ordinary worker
(`CP2B_PARSE_OPERATION_ALLOWLIST`, currently `{"src/flextoolsmcp/server/parse/worker_main.py"}`).
Because the sandbox backend lives in the same file, the existing allowlist entry already covers
it — no new path is added. What is needed, and is a companion code task rather than a doc change,
is a **new pinning test** (mirroring `CP4_FILING_ALLOWLIST`'s own test) that asserts
`test_the_worker_still_constructs_no_parser_itself`'s premise is now explicitly scoped to
`_RealBackend`, with `_SandboxBackend`'s `Morpher` / `XmlLanguageLoader` construction named and
allowlisted on purpose rather than passing by accident because those names are absent from
`FORBIDDEN_CONSTRUCTED_TYPES`.

## 4. The per-word `result.parse` shape

A `parse` message for a sandbox run gets back the existing `result` envelope
(`{"type": "result", "request_id", "run_id", "wordform", "index_in_run", "parse": {...},
"trace_xml": null}` — `trace_xml` is always null; the sandbox has no `<Trace>` document, HermitCrab
was called directly, not through flexicon's document-producing facade). The `parse` object:

```json
{
  "outcome": "parsed",
  "analyses": [
    {"morphs": [{"form": "meŋ", "gloss": "ACT", "guessed": false, "is_circumfix": false, "user_added": false},
                {"form": "ukul", "gloss": "hit", "guessed": true, "is_circumfix": false, "user_added": false}],
     "guessed": true}
  ],
  "parse_time_ms": 47
}
```

| Field | Type | Notes |
|---|---|---|
| `outcome` | `"parsed" \| "not_parsed" \| "invalid_segment" \| "error"` | Closed enum. `parsed`/`not_parsed` come back from a normal `ParseWord` return (non-empty / empty), **after** FR-050's shaping rules a-d (below) are applied — an analysis that rule (d) drops is simply absent from `analyses`, so a word all of whose analyses are dropped reports `not_parsed`, not `parsed` with an empty list. `invalid_segment` is `InvalidShapeException`, with `position` set (below). `error` is any other exception, with a message (below) |
| `position` | `int \| null` | Present, 0-based, only for `invalid_segment` (`InvalidShapeException.Position`, `HANDOFF.md` "proven facts"). Null otherwise |
| `error_message` | `str \| null` | Present only for `outcome: "error"`: `f"{type(exc).__name__}: {exc}"`, the same shape `_RealBackend`'s own uncaught-exception path already uses elsewhere in this module |
| `analyses` | `list \| null` | A list only for `parsed` (mirrors data-model.md 6.4's existing rule that `not_parsed`/`invalid_segment`/`error` carry no analyses to read); `null` otherwise |
| `analyses[].morphs` | `list[{form, gloss, guessed, is_circumfix, user_added}]` | One entry per **emitted** morph, in order, after FR-050's shaping (below) is applied to the engine's raw morph list; form as FLEx shows it (**corrected at T110, 2026-09-25**, against `HCParser.GetMorphs` and the live SC-003 comparison): the id map's `form` text for the form id the morph was emitted through (the allomorph, e.g. `meŋ`) -- except for a guessed morph, and for a morph whose map entry has no `form` (an older map, or no text in the default vernacular), which keep the surface string: the morph annotation's non-`HCFeatureSystem.Morph` children rendered through `HermitCrabExtensions.ToString` (e.g. `mem`), as `reference/hc_fw_prototype.py`'s `morph_infos` does -- FLEx's own `GuessedString`; `user_added` and unshaped (`id_map: "absent"`) morphs are surface too; gloss from `word.GetAllomorph(morph).Morpheme.Gloss`, with an empty gloss written `"?"` (D4) |
| `morphs[].guessed` | `bool` | Per-morph, `word.GetAllomorph(morph).Guessed` (D5, `reviews/research-cycle1-domain.md` section 3). Reliable signal, not the fragile gloss-equals-form heuristic |
| `morphs[].is_circumfix` | `bool` | **New (D4 reversed, FR-050).** `true` for the second (suffix-portion) occurrence of an `AffixProcessAllomorph`-with-no-`ID2` circumfix pair (shaping rule b/c below), and for a morph emitted through `ID2 > 0` (FLEx's own `MorphInfo.IsCircumfix = formID2 > 0`); `false` otherwise |
| `morphs[].user_added` | `bool` | **New (D4 reversed, FR-050).** `true` only in a named-sandbox run, for a morph whose allomorph `Property` has no `ID` at all (a user hand-edit); `false` otherwise, including for every morph in a project-cache-sourced run |
| `analyses[].guessed` | `bool` | True if **any** morph in the analysis is guessed — a per-analysis roll-up so a caller that does not want per-morph detail still gets the guessed/non-guessed split named in SC-003(b) |
| `parse_time_ms` | `int \| null` | Wall-clock time of the `ParseWord` call itself, measured by the worker (not printed and parsed the way hc's `Parse time:` line was) |

**Shaping to match Try A Word (D4 reversed, maintainer correction 2026-09-24, FR-050, SC-003(d)).**
The worker applies `HCParser.GetMorphs`'s own rules to the engine's raw per-analysis morph list,
using the validated `--id-map` (section 1), in order, per morph:

a. a morph whose allomorph `Property` `ID` (FormID) is absent or `0` is skipped -- **except**, in a
   named-sandbox run, a morph with no `ID` at all (a user hand-edit): it is emitted, flagged
   `user_added: true`, and never skipped by this rule;
b. an `AffixProcessAllomorph` with no `ID2` whose form's morph type is circumfix is recorded and
   emitted on its first occurrence; its second occurrence is emitted too, as the suffix portion (corrected 2026-09-24 against `HCParser.cs:347-374`: FLEx emits **both** occurrences -- the first is recorded *and* emitted, so the circumfix shows before and after what it attaches to),
   flagged `is_circumfix: true`;
c. a morpheme already seen is re-emitted only if it is (b)'s circumfix suffix portion (keyed on
   `ID`) or has `ID2 > 0` (keyed on `ID2`); otherwise it is skipped. "The same morpheme" is keyed
   on the morpheme's MSA `ID` (**corrected at T110**: GenerateHCConfig leaves the engine's own
   `Morpheme.Id` unset, so keying on it made every morph collide and dropped a root after its
   prefix -- live, `memukul` came back as `mem` alone), else on the engine's id, else on the
   morph's position;
d. the whole analysis is dropped -- not just the morph -- if a form ID, the morpheme's MSA `ID`, or
   a positive `InflTypeID` is not present in the validated `--id-map` (a morph flagged `user_added`
   is exempt from this rule, per (a)'s exception).

Then, as `GetMorphs` does last, an emitted infix or infixing interfix is placed before the morph it
interrupts (inserted ahead of the last emitted morph) rather than appended. The id map's
`morph_type_guid` is what tells the worker a form is an infix.

**The load baseline carries the run's engine facts (added at implementation, T096).** Once per run,
before that run's first `result`, the worker sends the existing
`{"type": "load_baseline", "run_id", "baseline"}` line with `baseline = {"captured": true, "source":
<config path>, "errors": [<load callbacks>], "parameters": {...}, "parameters_applied": [...],
"id_map": "valid" | "absent", "engine_version": <FileVersion>}`. That is how `SandboxClient` fills
`meta.sandbox.parameters_applied`, `shaping.id_map`, `engine_version` and
`generation.load_errors` without a second channel.

These are FLEx's own Try A Word display rules, replicated rather than named as gaps against Try A
Word (former D4). The two differences that remain, named rather than hidden (SC-003(d)):

- Glosses come from `Morpheme.Gloss` in the exported grammar, not from live LCM sense glosses; the
  two can differ if the project's senses changed after the config was generated (this is the same
  staleness the `sandbox_predates_project_grammar` advisory already names for Generate mode).
- In a named sandbox, a user-added morph (`user_added: true`) has no analogue in Try A Word at all
  -- it exists only because the user edited the sandbox's XML by hand, which is exactly what the
  sandbox spine is for.

## 5. Load errors (the D7 baseline)

`XmlLanguageLoader.Load(path, Action<Exception,string> errorHandler)` reports each load problem
through the callback rather than throwing (`HANDOFF.md` "proven facts"). The sandbox worker collects
every callback invocation during the first `parse`'s lazy load and:

- if the load **completes** (the callback fired zero or more times, but `Load` returned a usable
  `Language`), proceeds normally; the collected callback messages are folded into
  `meta.sandbox.generation.load_errors` (data-model.md section 6.2, unchanged shape) so a config
  with load errors still gets a `grammar_load_errors` advisory even though the sandbox itself did
  not generate the config;
- if the load **cannot produce a usable `Language`** at all (the FieldWorks engine's
  `XmlLanguageLoader` throws, or is unable to construct a `Morpher` from what it loaded), the first
  `parse` this process ever receives fails: no `result` for that word, instead
  ```json
  {"type": "error", "request_id": "<echoed>", "run_id": "<echoed>", "error_code": "parser_job_failed",
   "detail": {"failure": "engine_unavailable"}, "message": "<the load exception, str()'d>"}
  ```
  This is distinct from D7's **health** check (section 8 below), which never spawns a worker at
  all — this is what happens if a config that health could not have predicted (a hand-broken XML,
  S11) turns out unloadable only once a worker actually tries.

The Morpher, once built, is held for the life of the process (mirrors the ordinary worker's
`_GrammarSlot`, but with no `IsUpToDate()` re-check: a sandbox config file does not change under a
running worker the way a live project's grammar can, and `release()` — see section 7 — keeps the
Morpher across calls rather than tearing it down).

**`id_map_invalid` (new, D4 reversed, FR-050).** Before the first `parse` applies any shaping rule,
the worker reads the `--id-map` file (when given) and trusts its own recorded `valid` flag
(`data-model.md` section 3) rather than re-deriving it. If `--id-map` is given but `valid: false`,
or the file cannot be parsed at all, the first `parse` fails the same way an unloadable config
does, except with a different code:
```json
{"type": "error", "request_id": "<echoed>", "run_id": "<echoed>", "error_code": "parser_job_failed",
 "detail": {"failure": "id_map_invalid"}, "message": "<the invalid_ids list, or the parse error>"}
```
This is a **client-side belt-and-suspenders** case in practice — `contracts/tools.md` section 3's
check order already refuses before spawn when a cache entry's map is invalid — but the worker still
checks it itself rather than trusting the client, exactly as it checks `XmlLanguageLoader.Load`
itself rather than trusting a health check that never loaded the config.

## 6. Parameters (D3): feature-detected, client-sourced

The **worker** never decides where a parameter's value comes from. The **`SandboxClient`**
resolves each of `DelReapps`, `MaxRoots` (→ `MaxStemCount`), `MergeAnalyses`, `GuessRoots`, and
`MaxAlternatives` from, in order: (1) the config source's `key.json` `hc_parameters` if present
(data-model.md section 3, additive); (2) a live `.fwdata` stream read of the project's
`MorphologicalDataOA.ParserParameters/HC` XML, when the sandbox run is against a project-cache
source rather than a user-edited named sandbox; (3) FLEx's own defaults if neither source has a
value: `DelReapps=0`, `MaxRoots=2`, `MergeAnalyses=true`, `GuessRoots=true`, `MaxAlternatives=0`
(`reviews/research-cycle1-domain.md` section 1, `HCParser.cs:145-182`). The resolved values are
serialized to the `--hc-params` JSON file and handed to the worker at spawn; the worker applies
each one **only if the loaded `Morpher` exposes the matching property** —
`MaxAlternatives` is absent from the engine FieldWorks 9.3.11 ships (v3.8.2.0;
`reviews/research-cycle1-domain.md` section 1, `[verified v3.8.2]`) — and silently skips any it
does not have, recording which were actually applied in `meta.sandbox.parameters_applied`
(`data-model.md` section 6.2, revised for CP5).

`ParseWord` is always called as `ParseWord(word, out trace, guessRoot)`, never the one-argument
`ParseWord(word)` overload that hardcodes `guessRoot=false`
(`reviews/research-cycle1-domain.md` section 1), so `GuessRoots` from the resolved parameters
actually takes effect.

## 7. Release, cancellation, and timeout

- `release()` on a sandbox backend is a **no-op with respect to the Morpher**: there is no project
  to close and no `.fwdata` lock to drop, so unlike `_RealBackend` (which reopens a fresh project
  on the next word after every idle-triggered release, `reviews/research-cycle1-qc.md` section 3),
  the sandbox's loaded `Morpher` survives every `_release_if_idle()` call. It is torn down only by
  process exit (idle timeout or `shutdown`).
- **Cancellation** is cooperative, at the same word boundary as the ordinary worker: a `cancel`
  message drops queued words for that `run_id`; a word already handed to `ParseWord` finishes.
  HermitCrab's `ParseWord` has no internal cancellation token, so a single pathological word
  cannot be interrupted mid-call — only queued words behind it.
- **Timeout** is not a worker concept at all: the worker has no `-TimeoutSeconds` of its own. The
  **`SandboxClient`** holds a wall-clock watchdog around the whole run and, on expiry, kills the
  worker's process tree (the same `_kill_process_tree` path `worker_client.py` already uses for
  ordinary teardown). A word in flight at the kill is reported the way `parser_timeout` already
  reports one for the ordinary spine: `words_completed` up to and excluding the in-flight word,
  and the in-flight word named (data-model.md section 6.4's `error_no_output` /
  `not_reached` outcomes apply unchanged to a killed sandbox run).

## 8. Isolation invariants and how they are tested

| Invariant | How it is tested |
|---|---|
| No flexicon import, no LCM cache, no project open | A static scan (mirrors `test_cp1_boundary.py`'s AST scan) over the sandbox code path confirms no `flexicon` import and no `OpenProject`/`FLExProject` construction reachable from `--sandbox`'s branch of `main()` |
| No files written under the sandbox process's own initiative | A test spawns a `--sandbox` worker against a scratch config, in a scratch working directory, parses several words including at least one `invalid_segment` and one triggering a load error, and asserts the working directory's file list is unchanged before/after (mirrors S4's project-hash invariant, generalized to "no directory at all", since the sandbox has no project to hash) |
| D1 refusals never touch a project | Send each refused message type to a running sandbox worker and assert the `error_code: null, message: "not available in sandbox mode"` line, with no `ready`-adjacent side effect (no new file, no second process) |
| Held Morpher survives idle release | Parse two words with an intervening artificial idle (below the process's own `--idle-timeout`) and assert the second word's `parse_time_ms` is in the "warm" range (`HANDOFF.md`'s ~50ms, not the ~190ms first-parse figure), confirming no reload happened |
| Parameters applied only when supported | Against the bundled 3.8.2 engine, assert `meta.sandbox.parameters_applied` omits `MaxAlternatives` even when `MaxAlternatives` was present in the resolved input parameters, and that the run does not fail because of the missing property |
| Engine load failure surfaces once, not per word | Point `--config` at a hand-broken XML (mirrors S11) and assert the **first** `parse` gets `parser_job_failed`/`engine_unavailable` and the process does not attempt to reload on a second `parse` in the same run |
| Guessed flag is the reliable signal, not the heuristic | A corpus word known to need a guessed root (`HANDOFF.md`'s `memukul` example, or equivalent) asserts `guessed: true` on the guessed morph and `false` on the others, independent of whether gloss happens to equal form |
| Shaping rules a-d replicate `HCParser.GetMorphs` (D4 reversed, FR-050) | A synthetic `--id-map` fixture with a `FormID==0` morph, a circumfix pair, a repeated morpheme with `ID2 > 0`, and an id absent from the map: the parsed result skips the zero-id morph, emits the circumfix pair's second occurrence only (flagged `is_circumfix: true`), re-emits the `ID2` repeat, and drops the whole analysis carrying the unresolved id |
| An invalid or absent id map is handled, never silently mis-shaped | `--id-map` pointed at a fixture with `valid: false` fails the first `parse` as `parser_job_failed`/`id_map_invalid`; `--id-map` omitted entirely emits every morph unshaped and records `meta.sandbox.shaping.id_map: "absent"` |
| A named sandbox's user-added morph is emitted, not skipped | A hand-edited sandbox config with one morph whose allomorph has no `ID` parses with that morph present, flagged `user_added: true`, and its analysis is not dropped by rule (d) on its account |
