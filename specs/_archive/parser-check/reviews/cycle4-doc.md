# Cycle 4 -- Doc Agent: applying cycle-3 crew edits to SPEC.md

Source reviews read: cycle3-explore.md, cycle3-domain.md, cycle3-author.md,
cycle3-programmer.md.

| # | Landed under | Status | Notes |
|---|---|---|---|
| 1 | 5.4 "Where the code lives (S9)", the reflection-only sentence | Applied | Replaced with lex-programmer's wording (Assembly.LoadFile + GetMethods precedent, liblcm_extractor.py:332); added static-initializer/heavier-than-file-check sentence tying laziness survival to call-triggered vs import-triggered; added load_failed -> parser_core_missing mapping sentence. |
| 2 | 5.4, "Same install" gate item 1 | Applied | Added `get_resolved_fieldworks_dir()` accessor note (thin wrapper over `locate_liblcm_dll().parent`), no caching / recomputes per call, cheap because filesystem-only. |
| 3 | 5.4, new bullet after the reflection paragraph | Applied | New "MCP-side placement" bullet: detectors live in new `src\flextoolsmcp\server\parser_probe.py`, imported by `diagnostic_health.py` like `versioning.py`/`project_access.py`; explicitly states detection logic does not move into `diagnostic_health.py` (its "pure composition" docstring contract preserved). |
| 4 | 5.6, "Jobs are prioritised..." paragraph, the queue paragraph, and the existing preemption blockquote | Reconciled (not duplicated) | Heading/claim rewritten to interleave-at-next-word-boundary language with explicit "FLEx does not preempt, and neither do we," citing `ConsumerThread.WorkLoop` (`ConsumerThread.cs:434-453`). The queue paragraph's "makes preemption possible" -> "makes interleaving possible... queue-jump, not preemption." The pre-existing blockquote (already covered most of (b), including the uncommitted `ParserScheduler.cs:265-296` mod) was trimmed to avoid re-arguing the now-upfront point and given the explicit "Our guarantee is our own" sentence requested. |
| 5 | 5.6 (new paragraph before "A job must be cancellable") + 5.5 (`run.json` field list) | Applied, collapsed to one branch | Added live-re-read-only paragraph (no session-immutable branch): user-flippable via `OnChooseParser`/`areaConfiguration.xml`; accepted values `"XAmple"`/`"HC"` case-sensitive (`ParserWorker.cs:65-77`); fail-safe default to XAmple on XML parse failure (`OverridesLing_MoClasses.cs:4213`); batch check fires once at submission, `engine_at_submission` recorded in `run.json`, post-completion divergence is a WARNING not a refusal, satisfies 3.2's labelling rule. Added `engine_at_submission` to 5.5's run.json field list. |
| 6 | 12.3 "P0-2: the grammar can shrink silently" | Applied | Inserted new "What FLEx itself does with these errors" paragraph (HCLoader.Load/HCParser.LoadParser/HCTrace/FormatHCTrace.xsl chain, single-word-only UI consumer, batch path has none -> refusal fills a gap). Rewrote gate list: rung 2 now MCP-owned baseline (keyed to `scope_fingerprint`, first-run-has-no-baseline degrades to rung 3), rung 3 flagged as working hypothesis, rungs 1/3/4 marked Validated. Replaced closing "must read the side file; ugly and unavoidable" sentence with the our-own-load-vs-cross-session-baseline distinction. |
| 7 | 14 "Error codes" table | Applied | `parser_core_missing.signal` gains `load_failed`; added `load_error` field. `parser_tool_missing.component` now documented as closed two-value enum shared with 10.2's `sandbox.components[].component`. `grammar_load_unclean` gains `baseline_source` (`this_run` \| `prior_run:<run_id>` \| `absent`). |
| 8 | New "### 10.2 `flextools_health` parser block" (end of section 10, before section 11) | Applied | Lex-author's JSON shape verbatim; two-state-per-spine rule; `write` requires `ParseFiler.ProcessParse`; `sandbox.components` as array; `active_engine`/`detected.parser_core_version` informational-only; `ParserDetector` interface seam; `check_active_parser(project, supported_engines=("HC",))` preflight fired first in the three spine-executing handlers, mutability branch collapsed per edit 5 (always live-read, no immutable-session branch); `next_step` table carried over verbatim. Also updated the section-10 tools table row to cite "(10.2)". |
| 9 | 17 "Open questions" | Applied with one exception noted below | Item 2 rewritten: rung 2 resolved by MCP-owned baseline, rungs 1/3/4 validated, rung 3's benign-hypothesis flagged. Item 1 (GenerateHCConfig.exe) left open, untouched. Appended three new items (7, 8, 9): ParserCore.dll resolution order/SIL.LCModel.dll anchoring; hc detection method + timeout/failure behaviour; concrete detector output shape. |

## Could not apply as literally instructed

**Edit 9's "retire question 4 (ParserPriority)"** -- SPEC.md section 17 has no
ParserPriority question at item 4 or anywhere else; its item 4 is "Non-file-based
backends" and always has been in this rewrite. The ParserPriority question
(verbatim: "FLEx's ParserPriority enum members and their ordering were never
read... Verify at CP2") lives only in `specs/parser-check/.crew-handoff.json`'s
`open_questions[3]` (0-indexed) / item 4 (1-indexed), not in SPEC.md. Section
5.6 already carries a "**Verified** (`ParserScheduler.cs:25-32`)" citation
answering it in-line, so nothing needed retiring in SPEC.md itself. No SPEC.md
edit was made for this sub-item; the stale tracker entry in `.crew-handoff.json`
is a follow-up for whoever next touches that file (out of scope here -- task
scoped this pass to SPEC.md only).

**Residual inconsistency left untouched by design:** the Clarifications log at
SPEC.md line 97 ("a single-word parse **preempts** a background run") still
uses the pre-cycle-3 "preempts" framing. That is a dated historical record of
what was said in the 2026-09-15 session, not current architecture text, so it
was left as-is rather than retroactively edited; flagging here in case the
maintainer wants a footnote correcting it.

## Verification

- Ran a full heading scan before and after editing; section numbers 1-18
  unchanged, only new subsection 10.2 added (no existing 10.2 collided).
  Grep for `preempt` post-edit shows exactly one lingering "preempts" use, in
  the historical Clarifications log noted above.
- No emoji, no Unicode bullets introduced; all new prose is ASCII with `--`
  em-dash substitutes matching the file's existing convention.
- File was being edited concurrently; re-read affected regions before each
  edit and confirmed old_string matches before applying.

---
**Doc Agent:** cycle 4
