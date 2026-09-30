# QC Report — CP5 design review (research cycle 1)

Reviewer: lex-qc (read-only; written to disk by the main session because the
reviewer had no Write tool). Design under review: `--sandbox` mode of
`server/parse/worker_main.py` with a `_SandboxBackend` (research cycle 1,
option 1).

## 1. test_cp1_boundary.py

Passes mechanically: `_SandboxBackend` lives in `worker_main.py`, the sole
`CP2B_PARSE_OPERATION_ALLOWLIST` entry (tests/test_cp1_boundary.py:743-745), so
any `ParseWord` call there is exempted. Calls to `XmlLanguageLoader.Load` /
`Morpher(...)` are not in `PARSE_OPERATION_NAMES` (:227-234) or
`FORBIDDEN_CONSTRUCTED_TYPES` (:180-185), so the scanner reports nothing either way.

**P0 — gap, not a pass.** `test_the_worker_still_constructs_no_parser_itself`
(:826-841) exists so the worker "reaches the parser through flexicon's facade and
constructs nothing itself" (:735-737). The sandbox backend violates that premise
directly (in-process `Morpher` / `XmlLanguageLoader` construction, no flexicon).
The test is vacuously green only because those names are not in the forbidden
set. Needs an explicit edit: add `Morpher` / `XmlLanguageLoader` to a new CP5
sandbox allowlist (mirroring `CP4_FILING_ALLOWLIST`, :764-766) with its own
pinning test, or the guarantee silently stops meaning what its docstring says.

**P1 — dead/stale code.** `TestHcIdentityProbeNarrowing` (:1767-1781) and the
`HC_IDENTITY_PROBE_ARGS` / `HC_PROBE_MODULE` machinery (:251-271) exist for `hc -h`
discovery in `parser_probe.py`. Once `hc` discovery is retired, this class and the
module docstring's "CP5 NARROWED AGAIN" section (:94-107) describe a mechanism that
no longer exists — edit/remove together with `parser_probe.py`.

## 2. Which message types assume a project

- `preflight()` (:339-348, :986-1013) reads `project.lp.MorphologicalDataOA`.
- `_drain_resolves` (:2236-2317) calls `preflight()` + `lexicon_rows()`.
- `_drain_controls` (:2318-2387) answers `engine_check` / `resolve_scope` /
  `filing_gate` / `filing_preview`, all via `preflight()` / `active_engine()` /
  project reads.
- `_send_baseline_once` / `eligible_entries` (:441-447, :2612-2636) need a live lexicon.
- `_observe_engine` (:2550-2570) reads `active_engine()`.

None has sandbox meaning. `_SandboxBackend` must supply harmless stand-ins
(`preflight()` no-op, `active_engine()` fixed `"HC"` or `None`,
`eligible_entries()` → `{"known": False, "entries": []}`, `lexicon_rows()` → `[]`)
or refuse those messages with a coded error, and the sandbox client must only send
sandbox-level parse requests through `_parse_one`. **Needs an explicit decision.**

## 3. Does `_release_if_idle` release after every word?

**Yes, confirmed.** `runner.py:815-833` awaits `worker.parse_word(...)` one word at
a time; the worker queue (`worker_main.py:2168`) empties between requests,
`_release_if_idle()` fires (:2178, :2224-2234), and `_ensure_project_open()`
reopens and invalidates `_index` / `_load_baseline` (:2197-2222) on the next word.
A real per-word open/close cycle for `_RealBackend` (#223 regression; separate
issue). For the sandbox backend, `release()` must keep the Morpher.

## 4. FR/SC likely broken but not in the amendment list

- **FR-023** (run.json hand-off; MUST NOT scrape console prose): Parse/Test move
  to JSON-over-stdio with the worker. FR-023 needs redrafting to cover Generate
  mode only (or the worker protocol), not silent replacement.
- **FR-025** cache key: `sandbox/engine.py` `remember()` hardcodes
  `parameters=None` (engine.py:128, 227). The design needs parameters persisted in
  `key.json`. (The `.fwdata` mtime already keys the entry, so a parameter edit in
  FLEx changes the key; confirm.)
- **FR-036**: unaffected only if the pre-copy `.fwdata` stream-read engine check
  stays server-side, outside `_SandboxBackend`. Make this explicit.
