# QC Report -- Cycle 3 (review of cycle-2 implementation)

## 1. Cycle-1 defect closure

- **Instance A (parse.py:465 always-true guard): CLOSED.** New `is_definite_parse_failure` at `src/flextoolsmcp/server/handlers/parse.py:476-482` requires `"parsed" in result` (presence, not truthy-default) AND `result["parsed"] is False` AND `"parse_error" not in result`, restricted to `level in ("plain","explain")`. Verified this actually changes behavior (not just cosmetic) via the parse_error case: old guard fired on any missing key; new guard requires presence.
- **Instance B (`_level_guidance` explain branch): CLOSED.** `parse.py:832-841` -- error case returns `{"next_step": None}` with `explains_failure` omitted entirely; success case (`result.get("parsed")`) mirrors the `plain` branch's `{"explains_failure": False, "next_step": None}`; only falls through to failure guidance otherwise.
- **Instance C (`_result_summary` unconditional `parsed: 0`): CLOSED.** `parse.py:947-985` now counts `hypotheses_held` separately from `parsed` (:973-976), fed by real per-level dicts from `worker_main.py`'s `_RealBackend.parse()` (:724-758) which now calls `_summarize_trace` (:810-865) instead of returning `{"parse": None}` for restricted/explain.

## 2. Test potency

- P2 -- `_RealBackend.parse()`'s renaming step (`worker_main.py:745-749`) and the pythonnet `XDocument`/`XElement` binding it depends on are **not** exercised by any test; `tests/test_summarize_trace.py` uses hand-rolled stand-ins, and handler-level tests (`test_try_word_handler.py`, `test_parse_status_handler.py`) drive a fake `RecordingWorker` that hardcodes per-level dicts rather than calling `_summarize_trace`. This gap is disclosed by the programmer (cycle2-programmer.md "Could not verify without a live FLEx project"), so it's a known, flagged gap rather than a hidden one -- not a blocker, but the live verifier should target exactly this seam.
- Spot-checked for vacuousness: `test_explain_on_a_successful_parse_offers_nothing` (test_try_word_handler.py:527-544) would KeyError on `payload["parsed"]` if the `_inline_response` explain branch (parse.py:584-586) were reverted -- not vacuous. `test_explain_on_a_parser_error_names_neither_outcome` (:547-562) specifically distinguishes the old guard formula from the new one (old guard would wrongly fire on a parse_error explain response because `result.get("parsed", False)` defaults False on a missing key; new guard's presence check correctly excludes it) -- this is the test that actually pins Instance A's fix, not the success-case test, which both guard formulas satisfy once `_inline_response` sets `parsed` for explain. `test_a_completed_explain_runs_summary_reports_nonzero_parsed` / `..._counts_hypotheses_held` (test_parse_status_handler.py:112-187) would KeyError on `hypotheses_held` if `_result_summary` reverted, and would assert `parsed == 0` (defect symptom) if `worker_main.py`'s per-level fix were reverted alone. No vacuous test found among the new additions.

## 3. Narrowing vs deletion

Confirmed narrowed, not deleted, at all four cited sites: `test_try_word_handler.py:508-524` (`test_the_explaining_levels_say_they_explain_on_failure`, self-documented "NARROWED (CP2b)"), `:579-597` (`test_restricted_never_carries_parsed_even_on_a_held_hypothesis`), `:1207-1225` (`test_no_proposal_is_offered_when_the_caller_already_gave_one`), and `test_parse_proposal.py:256-287` (`test_agreement_produces_no_commentary`, "NARROWED (CP2b)" with rationale). Every one keeps its original assertions and adds new ones; none dropped an existing check.

## 4. test_flexicon_index_floor.py

Untouched -- confirmed absent from the git-status M-list and from the diff's file set; programmer's report also states this explicitly. No action needed.

## 5. Absence contract

Actually asserted, not merely unproduced: `test_try_word_handler.py:572-576` (`"hypothesis_held" not in payload`, `"parsed" not in payload` on explain-error), `:595-596` (restricted never carries `parsed`/`analysis_count`), `test_parse_proposal.py:278` (`"parsed" not in payload` on restricted agreement), `test_parse_status_handler.py:184-187` (`parsed == 0` on a completed restricted run). Gate satisfied.

## 6. Rootless-document ruling

Confirmed **not yet applied** -- `worker_main.py:844-850` still returns `{"parsed": False, "analysis_count": 0}` for a rootless document, and `tests/test_summarize_trace.py:184-189` pins exactly that (pre-cycle-4) behavior. Correct per the stated ruling (queued for cycle 4).
No other site in this diff manufactures a definite negative from a missing/unreadable input: the `<Error>`-first check (`worker_main.py:852-857`) is the one place doing exactly the opposite (refusing to assert `parsed: False` on ambiguity), and `_inline_response`/`_level_guidance`/`_result_summary` all key off presence rather than falsy-default gets in the touched regions.

## 7. Pattern-audit gate

Confirmed landed verbatim at `specs/parser-check-cp2b/evidence/cp2b-evidence.md:690-721`, quoting cycle-1's section-3 conclusion and mapping each of the 3 defects to its closing change. T042/tasks.md:139 gate satisfied.

## P0 / P1 / P2

- P0: none.
- P1: none.
- P2: `_RealBackend.parse()`'s real pythonnet wiring (worker_main.py:707-758) is untested end-to-end -- disclosed gap, hand to the live verifier, not a rework request.
- P2: `_level_guidance`'s `restricted` branch (parse.py:852-855) remains hardcoded `explains_failure: True` regardless of outcome -- explicitly out of scope per the programmer's report, consistent with Delta 6's stated boundary, not a new defect, but flag for cycle 4 triage alongside the rootless-document fix so it isn't lost.

## Score: 92/100

## Recommendation: **APPROVE**
