# parser-check CP3: as built

**Status:** Retired 2026-09-29. Merged to main via PR #185 (merge `822ec10`, 2026-09-23, branch `worktree-parser-check-cp3-tasks`); lint fixup `a672510`. Tasks: 126/126 complete (US1 `07ab1ff` .. US6 `f551601`, polish `5727935`).
**Full docs:** [specs/_archive/parser-check-cp3/](../_archive/parser-check-cp3/) (spec, plan, tasks, research, data-model, quickstart, review-notes, live note, contracts, evidence). Not read by default.
**Pinned (archive):** tests read [`contracts/tools.md`](../_archive/parser-check-cp3/contracts/tools.md) (5 tests), [`contracts/artifact.md`](../_archive/parser-check-cp3/contracts/artifact.md) (`test_parse_batch_artifact.py`) and `evidence/` (`test_parse_signature.py`; `test_parse_live_cp3.py` writes there) from `specs/_archive/parser-check-cp3/`. `artifact.md` is still the live run-artifact contract: CP4 (section 10) and CP5 (section 11) amended it in place.
**Scope:** MCP-side only. Consumes flexicon's CP2a surface (`project.Parser`, `TextOperations.GetGenres`, `AllomorphOperations.GetOwningEntry`, MSA reads); no flexicon code shipped with CP3. Read-only at CP3; CP4 added filing to the same tool.

## What shipped
- Three tools: `flextools_parse_text` (batch over a scope), `flextools_parse_log` (read a run back from disk), `flextools_parse_diff` (compare two runs). `tool_definitions.py:564-705`.
- Scope resolution (all texts / genre / text / word list) to a de-duplicated list, ordered by occurrence then alphabetically, limit applied after ordering (`parse/scope.py`, `parse/resolver.py`), plus an eight-field scope fingerprint (`parse/fingerprint.py`).
- Batches run on CP2b's runner at `Priority.LOW` with per-word enqueue. No second execution model (FR-014). A single word from `flextools_try_word` overtakes a running batch at the next word boundary.
- Run artifact (`parse/record.py`): `meta.json` (rewritten on each stage change), `results.jsonl` (appended), `words.txt` (new at CP3), `traces/<n>.xml`. Retention keeps the newest 20 runs per project (`parse/retention.py`).
- Batch report (`server/signals/`): five corpus signals, each with its false-alarm note; the human-analysis oracle in fixed wording; candidate pairing and promotion-only ranking; clustering; lexicalization attribution; deletion and duplicate projections (reported only, never acted on).
- Bounded single-word measurement (`parse/measure.py`), enforced by killing the worker process tree (D-4), plus next-step proposals on four trigger conditions.
- Five new refusal codes, standing tests `test_parse_no_project_writes.py` and `test_parse_no_edit_blocking.py`, and a correction to parent SPEC section 5.5's file listing.

## Public contracts (checked against this repo at `0715b64`)
- `flextools_parse_text` annotations: `readOnlyHint=False, destructiveHint=True` (`tool_definitions.py:697-698`), unchanged at CP4 by design (D-1).
- The engine check is the handler's first statement and runs once, at submission. `parse_log` and `parse_diff` never call it.
- `parse_log` sections: `summary | config_generation | hc_stdout | hc_output | trace | words | results | deletions`. `deletions` came with CP4. A section that does not apply to the run's spine returns a typed "not applicable" answer, never an empty section. A trace that cannot be parsed comes back raw and labelled raw.
- `parse_diff` buckets: `fixed | broken | changed | unchanged`, decided by which analyses a word gets, not how many; identity changes are reported separately. Refuses with `parse_scope_mismatch` when fingerprints differ; `force=true` compares only the intersection. In shared mode the result carries `staleness: "shared_mode_unverifiable"`, and `no_change` becomes `no_change_unverifiable` (`parse/diff.py:100-102`).
- Refusal codes and detail-field order, as in `contracts/tools.md` section 2: `parse_scope_empty`, `parse_scope_ambiguous`, `parse_scope_mismatch`, `parser_timeout`, `parser_job_failed` (`response_models.py:650-755`, `extra="forbid"`, `Literal` codes). The contract stayed at `tool-responses/1.0`.
- `run_id` = `secrets.token_hex(16)` (`record.py:189`) and carries no timestamp. Retention orders runs by `meta.json` `created_at`, never by name or mtime. It keeps runs it cannot date and never deletes a run in flight.
- Durable analysis signature: an ordered sequence of (form, MSA, inflection-type) GUID triples (`parse/signature.py`). `IDENTIFIER_STABILITY = "confirmed"` (:103); `FLEXTOOLSMCP_IDENTIFIER_STABILITY=disproved` turns the FR-033 fallback back on.
- The oracle's six sentences and its population sentence are verbatim (`signals/oracle.py`). Analyses with no stored opinion are never called `invalid|incorrect|rejected|flagged`. Provenance splits as `{affirmed, indeterminate}`; no analysis is ever labelled `tacit`, `unreviewed` or `auto_approved`.
- The eight host-report counters (`NumWords` .. `TotalUserNoOpinionAnalyses`, `record.py:~248-255`), with `counter_divergences` written into the artifact itself.
- `drill_down_cap` is 10-20 (`models.py:1079-1080`), and up to 3 representatives are picked per cluster (`signals/clustering.py:46`). Nothing is traced automatically.

## Key decisions
- D-1: the batch tool was annotated destructive from its first release, with no filing argument until CP4. Status: not overturned (plan.md, T006).
- D-2: the signature follows the host's match predicate: ordered triples, including inflection type (added after the domain gate). The guessed-form component cannot be serialized and is disclosed rather than dropped (FR-031a).
- D-3: the fingerprint deliberately excludes grammar state, because a grammar edit is what a comparison measures. The load-error baseline travels beside the fingerprint, not inside it.
- D-4: the measurement is bounded at process level and runs alone in its own worker. Concurrent measurements on one project are serialized, so one bound can never kill another's word. Cost is reported as wall-clock time only.
- D-5: clusters key on the shared root entry, falling back to the category pair. Representatives are the words with the most analyses, capped at 3.
- D-6: the artifact keeps CP2b's shipped layout; parent SPEC 5.5 was corrected to match it (T121).

## Gotchas and limits
- Identifiers in the artifact are GUID strings, not hvos: liblcm renumbers hvos on every cache load (#103).
- On IndonesianHC-Complete each text's wordforms exist in only one vernacular WS. A run skips the other text's forms, counts them in `unreadable_wordform_count`, and names `vernacular_ws` in `notes`. It never emits `""` as a word.
- The genre match runs in the default analysis WS only, so a user working in a localized UI may miss (FR-008, disclosed, not fixed).
- `Sena 3` reports XAmple, so CP3's engine gate refuses it. Live projects: `IndonesianHC-Complete` (correctness) and `Malay Parsing-20230810withHC` (scale).
- The three grammar lints stayed deferred (T120): no checker exists in SIL.Machine 3.8.2. CP4 re-probed and deferred them again (parent SPEC ~line 1345).

## Divergences from the spec
- D-1's "filing is not yet reachable" first-line wording is gone: CP4 added `apply=true`, and the description now leads with filing. The annotation is unchanged, as D-1 intended.
- `parse_log` has eight sections, not seven (`deletions`, CP4). The contract doc says so; the code agrees.
- The error-code count rose 25 -> 30 at CP3. `docs/TOOL-CONTRACT.md` now documents 44 codes (CP4/CP5 added more).
- `artifact.md` was reconciled at freeze (T053): GUID identifiers, `results.jsonl` keeps CP2b's line shape with batch fields inside `parse`, and `load_error_baseline` is an object.
- Live verification was narrower than specified:
  - Scale: 262 words, killed at 175, versus "a few thousand, kill at ~4000".
  - No `terminated_at_bound` live (the 1 s bound completed in 0.58 s).
  - No live genre case, because neither project has genres.
  - Needed a human and were never done: SC-009 break-then-revert, SC-010 delete-and-recreate, and FR-034 shared-mode staleness.
- Identifier stability was confirmed on one project with one close/reopen only (T125, 38/38).
- Not verified: FR-001..FR-063 one by one, and the signal, ranking and attribution internals (only the surfaces above were read).

## Follow-ups and open issues
- Upstream: flexicon's `GetGenre` docstring still doesn't point to `GetGenres` (TextOperations.py:824), so the served pattern index still teaches a read that returns only the first genre. No issue was found filed.
- `sorted(versions.keys())[-1]` sorts version strings as text, so "latest" goes wrong once a component reaches two digits: `refresh.py:344`, `build_casting_index.py:244`, `build_navigation_graph.py:389`, `build_element_types.py:425`. The fix is `archive_old_versions.parse_version`. No issue was found filed.
- `worker_main._ws_handle` quietly falls back to the default vernacular WS where `scope._vernacular` refuses. Low risk, left as is.
- There is no `terminated_at_bound` evidence from a slow live grammar; that path is proven only against stub workers.
