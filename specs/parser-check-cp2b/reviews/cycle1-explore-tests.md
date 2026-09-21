# Cycle 1 -- test reconnaissance for the CP2b `try_word` shape change

**Key finding up front.** The fake worker at `tests/test_try_word_handler.py:152-155`
returns `{"parse": None, ...}` for every non-plain level. `_inline_response` does
`parse = entry.get("parse") or {}`, so once `explain`/`restricted` start reading
`parsed`, every fake-worker test will see `parsed=False` / `analysis_count=0`
**unconditionally**. Result: almost nothing breaks on day one, and the new
conditional gets zero coverage. The breakage arrives only when the fake is
updated to carry a real `parse` block -- which it must be, or the change ships
untested.

## 1. WILL BREAK

| file:line | test | why |
|---|---|---|
| tests/test_try_word_handler.py:472-479 | `test_the_explaining_levels_say_they_explain` | Asserts `explains_failure is True` for *both* `explain` and `restricted`, with no success/failure distinction. Breaks the moment the fake returns `parsed=True` at explain. Must be split into a failure case and a success case. |
| tests/test_try_word_handler.py:532-535 | `test_explain_steers_back_toward_restricted` | Indexes `payload["next_step"][0]` unguarded. If explain-on-success drops rungs (mirroring the plain-success branch at parse.py:757-759), this raises `TypeError`. |
| tests/test_try_word_handler.py:1085-1091 | `test_no_proposal_is_offered_when_the_caller_already_gave_one` | Conditional break: only passes today because of the `level != "restricted"` half of the guard at parse.py:465. If that half is dropped in favour of a pure success test, restricted+`parse: None` yields `parsed=False` and a proposal appears. |
| tests/test_parse_proposal.py:256-277 | `test_agreement_produces_no_commentary` | Same exposure as above (`"proposed_decomposition" not in payload` at :272), plus `next_step is None` at :268. |
| tests/test_parse_live.py:514-520 | `test_scenario_3_the_same_word_at_explain_carries_the_trace` | Live-gated. Uses `FAILING_WORD`, so `explains_failure is True` survives -- but only by luck of the fixture word. Flag for review, not a certain break. |

## 2. GOES VACUOUS (passes, tests nothing)

| file:line | test | what it stops covering |
|---|---|---|
| tests/test_try_word_handler.py:472-479 | `test_the_explaining_levels_say_they_explain` | If the fake keeps `parse: None`, `explains_failure is True` becomes tautological -- the new success branch is never reached. |
| tests/test_try_word_handler.py:1023-1043 | `test_every_emitted_rung_names_a_tool_that_exists` | `payload.get("next_step") or []` swallows a `None` next_step; an explain response that wrongly drops all rungs passes silently. |
| tests/test_try_word_handler.py:451-469, :1066-1082 | `..._successful_plain_parse_offers_nothing`, `no_proposal_..._when_the_word_parsed` | Both hand-roll a *plain-shaped* success (`:461`, `:1076`). They never exercise success at explain/restricted, which is exactly the new branch. |
| tests/test_try_word_handler.py:538-542 | `test_restricted_steers_nowhere` | Asserts `next_step is None` for restricted; unchanged by the edit, so it certifies nothing about the conditional. |
| tests/test_try_word_handler.py:482-489, :1163-1180 | trace-path / trace-bytes tests | Unaffected, but now cover a strictly smaller fraction of the explain payload. |
| tests/test_parse_proposal.py:249-253, :279-292 | `no_confidence_figure`, `no_alternatives_block` | Key-absence sweeps; `analysis_count` matches neither `_JUDGEMENT_KEYS` nor the alternatives list, so they neither break nor notice. |

**Uncovered today, and still uncovered after the change unless a test is added:**
the guard at parse.py:465 currently *always* calls `_propose_decomposition` for
`explain` (because `parsed` is absent there). No test asserts a proposal at
explain, in either direction.

## 3. Other parse-path tests

Fake-worker (not gated): `tests/test_parse_proposal.py` (imports `Pool`,
`RecordingWorker` from the handler test at :56; `call` at :114-123),
`tests/test_parse_status_handler.py:47,67`, `tests/test_spec16_deferred_groups.py:46,280`
(each hand-rolls a plain-shaped `analysis_count` success). Name-only / structural,
unaffected: `tests/test_mcp_tools.py:94,121`, `tests/test_parser_health_block.py:486-546`,
`tests/test_parser_agent_probe.py:369-397`, `tests/test_cp1_boundary.py:213-215,817-818`,
`tests/test_parser_probe.py:435-437`, `tests/fixtures/parser_check.py:60-62`,
`tests/test_parse_resolver.py:9-22`, `tests/test_response_contract.py:244`.

Live-gated (`pytestmark = pytest.mark.requires_flex`): **all of**
`tests/test_parse_live.py` (:80) and `tests/test_parser_no_xcore.py` (:92, asserts
`analysis_count` is an int at :198). Live assertions on shape:
`:339` (`analysis_count >= 1`, plain success), `:476-477` (plain failure),
`:519-520` (explain failure), `:681`, `:757` (restricted `trace_available`).
No live test asserts explain-on-a-word-that-parses.

## 4. `tests/test_flexicon_index_floor.py` -- verdict

**NO.** It compares three things only: the declared pyflexicon floor in
`pyproject.toml`/`requirements.txt`, the version `server/versioning.py` resolves,
and the version embedded in bundled `index/**` artifact filenames (tests at
:154, :178, :206, :216, :234, :259). The planned change edits response assembly
in `handlers/parse.py` alone; it adds no flexicon API dependency (`ParseWord` /
`TraceWordXml` already ship at the 4.9.0 floor) and touches no index artifact or
version string. Nothing in it needs weakening, skipping or re-generating.

## 5. Baseline command and counts

CI (`.github/workflows/test.yml:50-59`):

    pytest -m "not requires_flex" --continue-on-collection-errors \
      --cov=src/flextoolsmcp --cov=server --cov-fail-under=25 \
      --cov-report=term-missing -q

Local equivalent (`pytest.ini`: `asyncio_mode = auto`, `testpaths = tests`,
marker `requires_flex` registered): `python -m pytest -q -m "not requires_flex"`.

`tests/test_try_word_handler.py` alone, measured on this tree at `main` (clean):

    python -m pytest tests/test_try_word_handler.py -q
    40 passed in 2.07s        # 40 passed, 0 skipped, 0 failed
