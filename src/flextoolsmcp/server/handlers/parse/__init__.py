#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
flextools_try_word and flextools_parse_status (parser-check CP2b), and
flextools_parse_text (parser-check CP3, US2).

Authority: specs/parser-check-cp2b/contracts/tools.md (levels, ordering
guarantees, refusal table, the run contract), specs/parser-check-cp2/spec.md
FR-012 .. FR-016 and FR-026 .. FR-036, data-model.md sections 1-4.

WHAT THIS MODULE DOES NOT DO, and why that is the point:

  * It never constructs a parser, opens a project, or loads a grammar. Every
    one of those happens in the parse worker, a separate process addressed
    through `server/parse/worker_client.py`. The MCP server process holding
    an LCM cache is the failure CP1's boundary test exists to prevent, and
    `tests/test_cp1_boundary.py` asserts that no handler reaches the parser
    facade outside `server/parse/` (T060).
  * It never runs the engine gate itself. `check_active_parser(project,
    supported_engines=("HC",))` is the **first statement of the worker's
    request handler** (worker_real_backend.py `_RealBackend.preflight`), which is
    what makes FR-015's "before any parser is constructed" true of the
    process that would do the constructing. Running a second copy here
    would read `ActiveParser` from a project this process does not have
    open -- it would have to open one to do it, which is the thing
    forbidden above. The refusal arrives over the worker channel with its
    `parser_engine_mismatch` detail intact and is re-emitted unchanged.
  * It never starts a parse by any route other than `ParseRunner`. FR-026
    says all parser execution goes through one mechanism and that there is
    no second synchronous path; a "just this once" direct call here is
    exactly how a second one appears.

THE BATCH'S ENGINE CHECK IS DIFFERENT, AND DELIBERATELY SO (FR-024). For
`flextools_parse_text` the gate fires ONCE, at submission, as the handler's
first project-touching statement -- `runner.check_engine`, which asks the
worker to run `check_active_parser` and nothing else -- before the scope is
resolved and before any word is queued. From then on the batch's words
observe the engine rather than gate on it, so a user flipping the active
parser mid-batch gets a warning on the run, not a batch that dies at word
four thousand.

THE GRACE WINDOW IS A REPORTING BOUNDARY, NOT A TIMEOUT (FR-028, SC-010).
`ParseRunner.start_run` returns when the run finishes *or* when the window
closes, whichever comes first. This handler tells the two apart with
`handle.is_terminal` and does nothing else about it: a run still going is
left going, untouched, and the caller gets a handle to poll. Nothing on this
path cancels a run, shortens one, or passes a deadline downstream.

WHERE THE PIECES LIVE (#298). This package was one 4,400-line module; it is
split by responsibility, and this `__init__` re-exports what callers use so
`handlers.parse` imports keep working:

    common.py          the one runner, next_step rungs, morph resolution,
                       project resolution, access probe
    summary.py         run-summary helpers shared by the tools below
    try_word.py        flextools_try_word
    runs.py            flextools_parse_text / _status / _cancel / _release
    filing.py          flextools_parse_text(apply=true) -- filing (CP4)
    run_log.py         flextools_parse_log and flextools_parse_diff
    sandbox_checks.py  flextools_parse_sandbox, check-order steps 1-7
    sandbox.py         flextools_parse_sandbox, step 8 and the handler

To patch a helper in a test, patch the module that owns it (for example
`parse.common._resolve_project`). Helpers used across modules are looked up
at call time as `common.<name>` / `sandbox_checks.<name>`, so one patch
reaches every caller.
"""

from .common import (
    _refusal_from_failure,
    _resolve_project,
    _rung,
    aclose_runner,
    get_runner,
    peek_runner,
    session_state,
    set_runner,
)
from .try_word import (
    handle_flextools_try_word,
)
from .runs import (
    _live_run_not_found,
    handle_flextools_parse_cancel,
    handle_flextools_parse_release,
    handle_flextools_parse_status,
    handle_flextools_parse_text,
)
from .summary import (
    _failure_rungs,
)
from .filing import (
    _PREVIEW_INLINE_GUIDS,
    _PREVIEW_SAMPLE_WORDFORMS,
    filing_paths,
)
from .run_log import (
    _empty_note,
    _log_record,
    _trace_section,
    handle_flextools_parse_diff,
    handle_flextools_parse_log,
    reset_drill_down,
    summarize_trace_xml,
)
from .sandbox_checks import (
    _sandbox_list_rung,
    _sandbox_space_check,
    _tool_missing_rungs,
    split_words,
)
from .sandbox import (
    _sandbox_launch,
    _sandbox_origin,
    handle_flextools_parse_sandbox,
)
