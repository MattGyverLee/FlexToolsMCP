"""
Run-summary helpers shared by the run, filing, try_word and sandbox tools:
the worker-refusal envelope, the batch block, the result summary and the
status next_step ladder.
"""

from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from ...parse.stages import RunStage

try:
    from ....response_utils import error_response
except (ImportError, ValueError):
    from response_utils import error_response

from .common import (
    _grammar_scan_rung,
    _read_run_rung,
    _rung,
    _stuck_loading,
)


def _worker_error_response(exc: Exception) -> List[TextContent]:
    """Re-emit a worker refusal under its own code, detail unchanged (R-03)."""
    error_code = getattr(exc, "error_code", None)
    if error_code:
        detail = dict(getattr(exc, "detail", None) or {})
        detail.pop("error_code", None)
        message = detail.pop("message", None) or detail.get("hint") or str(exc)
        return error_response(error_code, message, **detail)
    return error_response("runtime_error", str(exc), error_type=type(exc).__name__)


def _batch_block(handle) -> Dict[str, Any]:
    """What a batch run adds to a status or submission response."""
    if not getattr(handle, "is_batch", False):
        return {}
    block: Dict[str, Any] = {
        "scope_fingerprint": handle.scope_fingerprint,
        "engine_at_submission": handle.engine_at_submission,
        "engine_changed_midjob": handle.engine_changed_midjob,
    }
    if handle.counters is not None:
        from ...parse.record import COUNTER_DIVERGENCES

        block["counters"] = handle.counters.to_dict()
        block["counter_divergences"] = list(COUNTER_DIVERGENCES)
    warnings: List[str] = []
    if handle.engine_changed_midjob:
        # FR-024: a warning on the summary, never a refusal.
        warnings.append(
            f"The project's active parser changed while this batch was running "
            f"(submitted on {handle.engine_at_submission!r}, now "
            f"{handle.engine_now!r}). The batch carried on and its results are "
            f"labelled with the engine it was submitted on."
        )
    if warnings:
        block["warnings"] = warnings
    return block


def _result_summary(handle) -> Dict[str, Any]:
    """What a completed run produced, summarised rather than inlined.

    Counts and paths, never the traces themselves: a single trace runs to
    tens or hundreds of kilobytes, and a completed batch of four thousand
    words would not fit in a response at all (data-model.md section 5).

    TWO QUESTIONS, TWO COUNTERS. `plain`/`explain` entries carry `parsed`;
    `restricted` entries carry `hypothesis_held` instead, never `parsed`
    (worker_real_backend.py's `BackendFacade.parse()` renames it there, at the one
    place that already knows which question that run's level asked). Before
    this fix, every entry's `parse` was `{}` for `explain`/`restricted`
    (the worker returned `{"parse": None, ...}` for both), so
    `parse.get("parsed")` was always falsy and a poll on ANY completed
    explain/restricted run reported `parsed: 0` unconditionally --
    indistinguishable from "every word failed to parse". Counting each
    question separately, over the entries that actually carry its key,
    is what keeps a `restricted` run's held hypotheses from being
    conflated with -- or silently erased by -- an unrestricted `parsed`
    count that was never asked about them.
    """
    parsed = 0
    hypotheses_held = 0
    traced = 0
    for entry in handle.results:
        parse = entry.get("parse") or {}
        if parse.get("parsed"):
            parsed += 1
        if parse.get("hypothesis_held"):
            hypotheses_held += 1
        if entry.get("trace_path"):
            traced += 1
    return {
        "words": len(handle.results),
        "parsed": parsed,
        "hypotheses_held": hypotheses_held,
        "traces_written": traced,
        "record_dir": str(handle.record.root),
    }


def _failure_rungs(handle) -> List[Dict[str, Any]]:
    """A FAILED run's rungs: the instruments, never a retry (FR-034).

    The static scan comes first (FR-057): it runs no parse, and the
    commonest failure -- memory exhausted while loading the grammar -- is the
    one it speaks to. No rung names `flextools_try_word`: repeating the run
    repeats the step that exhausted it. Words that completed before the
    failure are readable, and CP3 ships the tool that reads them (FR-058).
    """
    rungs = [
        _grammar_scan_rung(handle.project_name),
        _rung(
            action="Check the environment and the project's grammar.",
            tool="flextools_health",
            args={"verbose": True},
            rationale=(
                "A run that died while loading the grammar has usually "
                "exhausted memory. Repeating it repeats the step that "
                "exhausted it; the diagnostics say what the project needs."
            ),
            est_cost="seconds",
        ),
    ]
    if handle.words_completed > 0:
        rungs.append(
            _read_run_rung(
                handle.run_id,
                f"{handle.words_completed} word(s) completed before the "
                f"failure; their results were written as they were produced.",
            )
        )
    return rungs


def _status_next_step(handle) -> Optional[List[Dict[str, Any]]]:
    """What to do next, or nothing when there is nothing useful to say.

    A still-running run gets "poll again" -- plus the static scan when it is
    a batch that entered grammar loading and has stayed there (FR-056). A
    FAILED run gets the diagnostic instruments and never a retry (FR-034).

    FR-058's revisit: a cancelled run with partial results, and a completed
    BATCH, point at `flextools_parse_log` -- rows that had no tool to name
    before CP3 shipped one. A completed single word still gets `None`: its
    answer is already in the response.
    """
    if handle.stage is RunStage.FAILED:
        return _failure_rungs(handle)

    if not handle.is_terminal:
        rungs = [
            _rung(
                action="Poll again for this run.",
                tool="flextools_parse_status",
                args={"run_id": handle.run_id},
                rationale=(
                    f"The run is in {handle.stage.value!r} and is still "
                    f"going. It was not slowed or throttled by being polled."
                ),
                est_cost="instant",
            )
        ]
        if _stuck_loading(handle):
            rungs.append(_grammar_scan_rung(handle.project_name))
        return rungs

    if handle.stage is RunStage.CANCELLED and handle.words_completed > 0:
        return [
            _read_run_rung(
                handle.run_id,
                f"{handle.words_completed} word(s) completed before the cancel "
                f"and are on disk.",
            )
        ]

    if handle.stage is RunStage.COMPLETED and getattr(handle, "is_batch", False):
        return [
            _read_run_rung(
                handle.run_id,
                "The batch report -- signals, the oracle, clusters to trace -- "
                "is in this run's summary section.",
            )
        ]

    return None
