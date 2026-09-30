"""
flextools_parse_log (CP3, US3) and flextools_parse_diff (CP3, US4): both read
the run artifact on disk, never the engine.
"""

from typing import Any, Dict, List, Optional

from mcp.types import TextContent

from ...parse.record import MetaUnreadable
from ...filing import paths as filing_paths

try:
    from ....response_utils import build_response_with_context, error_response
except (ImportError, ValueError):
    from response_utils import build_response_with_context, error_response

from . import common
from .common import (
    _rung,
    json_response,
)


# ---------------------------------------------------------------------------
# flextools_parse_log (CP3, US3)
# ---------------------------------------------------------------------------
#
# READS THE ARTIFACT, NEVER THE ENGINE (FR-024). Nothing in this section
# reaches a worker, a project or a parser: every section is served from the
# run directory on disk. That is also what makes a run from an earlier server
# process as readable as a live one -- the artifact is the thing CP4 and CP5
# read, so it is the thing this tool reads too.
#
# NO SECTION IS EVER EMPTY (FR-028, SC-007). An empty section reads as
# "nothing happened", which for a sandbox-spine section is false (it was
# never run) and for a real section may be false too (the run died before
# its first word). Every response therefore says what it is: real content,
# a typed not-applicable naming the spine and the checkpoint that fills it,
# or an explicit statement of why there is nothing to show.
# ---------------------------------------------------------------------------

#: The spine this checkpoint runs. Named in every not-applicable response.
IN_PROCESS_SPINE = "in_process"

#: The three sandbox-spine sections: what each would hold, and who fills it.
_SANDBOX_SECTIONS: Dict[str, str] = {
    "config_generation": "the HermitCrab configuration generated from the project for a sandboxed run",
    # Kept verbatim: the in-process not-applicable response is pinned
    # byte-identical (CP5 contracts/tools.md section 7), even though a
    # sandbox run now fills these from its parse worker (FR-038).
    "hc_stdout": "the standard output of a sandboxed HermitCrab process",
    "hc_output": "the output file a sandboxed HermitCrab process writes",
}
SANDBOX_SPINE = "sandbox"
SANDBOX_CHECKPOINT = "CP5"


def _not_applicable(section: str, run_id: str) -> Dict[str, Any]:
    """The typed not-applicable response for a sandbox section (FR-028)."""
    return {
        "status": "ok",
        "run_id": run_id,
        "section": section,
        "applicable": False,
        "reason": "not_applicable_for_this_spine",
        "run_spine": IN_PROCESS_SPINE,
        "section_spine": SANDBOX_SPINE,
        "filled_by": SANDBOX_CHECKPOINT,
        "note": (
            f"This section holds {_SANDBOX_SECTIONS[section]}. This run used "
            f"the {IN_PROCESS_SPINE} spine, where the parser runs inside the "
            f"worker and no such file exists, so the section is not "
            f"applicable -- it is not empty. The {SANDBOX_SPINE} spine that "
            f"produces it arrives at {SANDBOX_CHECKPOINT}."
        ),
    }


#: CP5 (FR-038): each sandbox section's file under `<run>/sandbox/`, and what
#: its empty note calls the missing lines.
_SANDBOX_SECTION_FILES: Dict[str, str] = {
    "config_generation": "generate-config.log",
    "hc_stdout": "worker-stderr.txt",
    "hc_output": "hc-output.txt",
}
_SANDBOX_SECTION_WHAT: Dict[str, str] = {
    "config_generation": "configuration-generation log lines",
    "hc_stdout": "sandbox worker diagnostic lines",
    "hc_output": "rendered sandbox results",
}

#: The most characters of one sandbox file served inline, like a trace's
#: `max_trace_chars` default. A longer file is served from its start, marked
#: truncated, with the file's path for the rest.
SANDBOX_LOG_MAX_CHARS = 200_000


def _sandbox_log_section(record, meta, section: str) -> Dict[str, Any]:
    """One sandbox section, served verbatim from the run's `sandbox/` file.

    An empty or never-written file is an explained absence (`_empty_note`),
    never an empty section. `config_generation` also carries the generation
    facts from `meta.sandbox.generation`.
    """
    name = _SANDBOX_SECTION_FILES[section]
    result: Dict[str, Any] = {
        "status": "ok",
        "run_id": record.run_id,
        "section": section,
        "applicable": True,
        "run_spine": SANDBOX_SPINE,
        "source": f"sandbox/{name}",
    }
    text = record.read_sandbox_file(name)
    if text:
        if len(text) > SANDBOX_LOG_MAX_CHARS:
            result["content"] = text[:SANDBOX_LOG_MAX_CHARS]
            result["content_truncated"] = True
            result["content_chars"] = len(text)
            result["source_path"] = str(record.sandbox_path(name))
        else:
            result["content"] = text
    else:
        result["note"] = _empty_note(meta, _SANDBOX_SECTION_WHAT[section])
    if section == "config_generation":
        sandbox = meta.sandbox if isinstance(meta.sandbox, dict) else {}
        generation = sandbox.get("generation") if isinstance(sandbox.get("generation"), dict) else {}
        load_errors = list(generation.get("load_errors") or [])
        result["reused_cache"] = generation.get("reused_cache")
        result["load_error_count"] = int(generation.get("load_error_count") or len(load_errors))
        result["load_errors"] = load_errors
    return result


def _log_record(run_id: str):
    """The run's on-disk record, or None if no such run exists."""
    from ...parse.record import RunRecord, is_valid_run_id

    if not is_valid_run_id(run_id):
        return None
    runner = common._runner
    record_dir = runner.record_dir if runner is not None else None
    record = RunRecord(run_id, record_dir=record_dir)
    return record if record.exists() else None


def _run_not_found(run_id: str) -> List[TextContent]:
    from ...parse.record import list_run_ids

    runner = common._runner
    known = list(runner.known_run_ids()) if runner is not None else []
    record_dir = runner.record_dir if runner is not None else None
    on_disk = [r for r in list_run_ids(record_dir) if r not in known]
    available = known + on_disk[:20]
    return error_response(
        "parse_run_not_found",
        f"No parse run with handle {run_id!r}.",
        run_id=run_id,
        available_runs=available,
        hint=(
            "Run handles are issued by flextools_parse_text and "
            "flextools_try_word, and their records stay on disk (the newest 20 "
            "per project). "
            + (f"Runs with records: {', '.join(available)}." if available
               else "No run records exist yet.")
        ),
    )


#: `server_state` for a run record whose meta.json exists but stays
#: unreadable (pattern audit sweep 6): transient, never "not found".
RUN_RECORD_UNREADABLE = "run_record_unreadable"


def _run_record_unreadable(
    run_id: str, exc: BaseException, *, tool: str, args: Dict[str, Any]
) -> List[TextContent]:
    """A run record that exists but could not be read: retry, not absence.

    `RunRecord.read_meta_strict` already retried briefly before raising
    `MetaUnreadable`; on Windows this is usually a virus scanner or indexer
    holding meta.json. The record is intact, so the answer is the same call
    again in a moment -- never `parse_run_not_found` or "not applicable".
    """
    return error_response(
        "server_state_error",
        f"Run {run_id}'s record exists but could not be read just now. "
        "Nothing was changed.",
        server_state=RUN_RECORD_UNREADABLE,
        component="parse_record",
        state_description=str(exc),
        hint=(
            "Another process (often a virus scanner or search indexer) is holding "
            "the run's meta.json. The record is intact; retry in a moment."
        ),
        next_step=[
            _rung(
                action="Retry the same call in a moment.",
                tool=tool,
                args=args,
                rationale="The record exists; the read failure is transient.",
                est_cost="instant",
            )
        ],
    )


def _page(items: List[Any], offset: int, limit: int) -> Dict[str, Any]:
    page = items[offset:offset + limit]
    return {
        "total": len(items),
        "offset": offset,
        "returned": len(page),
        "items": page,
        "next_offset": offset + len(page) if offset + len(page) < len(items) else None,
    }


def _empty_note(meta, what: str) -> str:
    """Why a real section has nothing to show -- never left unexplained."""
    if meta is None:
        return f"No {what} are recorded for this run."
    stage = meta.stage
    if meta.failure:
        where = (meta.failure or {}).get("stage_at_failure") or stage
        return (
            f"No {what} are recorded: the run failed during {where!r} before "
            f"completing a word."
        )
    if stage in ("starting", "loading_grammar"):
        return f"No {what} yet: the run is still in {stage!r}."
    return f"No {what} are recorded for this run (stage {stage!r})."


# The session's drill-down budget (FR-047, SC-016). A user-chosen figure in
# 10-20, set once by the first report request that names one; later requests
# read the same budget, so a session cannot be walked past its cap by asking
# again. Nothing traces automatically -- the budget bounds what the report
# RECOMMENDS, and every trace remains one flextools_try_word call for one word.
_drill_down: Optional["DrillDownBudget"] = None  # noqa: F821


def _drill_down_budget(cap: Optional[int]):
    """The session's budget, created on the first request that names a cap."""
    global _drill_down
    if _drill_down is None and cap is not None:
        from ...signals.clustering import DrillDownBudget

        _drill_down = DrillDownBudget(int(cap))
    return _drill_down


def reset_drill_down() -> None:
    """Forget the session's drill-down budget (tests; a new session)."""
    global _drill_down
    _drill_down = None


async def handle_flextools_parse_log(args: dict) -> List[TextContent]:
    """Serve one section of a run's artifact (FR-028, FR-029).

    Read-only. Starts nothing and never calls the engine check (FR-024).
    """
    run_id = str(args.get("run_id") or "")
    section = str(args.get("section") or "summary")
    offset = int(args.get("offset") or 0)
    limit = int(args.get("limit") or 50)

    if section in _SANDBOX_SECTIONS:
        # Answered for any existing run: whether the section applies is a
        # fact about the RECORDED spine (never the section name, never the
        # presence of a file), not about how far the run got.
        record = _log_record(run_id)
        if record is None:
            return _run_not_found(run_id)
        try:
            meta = record.read_meta_strict()
        except MetaUnreadable as exc:
            return _run_record_unreadable(run_id, exc, tool="flextools_parse_log", args=dict(args))
        if meta is not None and meta.effective_spine == SANDBOX_SPINE:
            return json_response(build_response_with_context(
                _sandbox_log_section(record, meta, section)
            ))
        return json_response(build_response_with_context(_not_applicable(section, run_id)))

    record = _log_record(run_id)
    if record is None:
        return _run_not_found(run_id)
    try:
        meta = record.read_meta_strict()
    except MetaUnreadable as exc:
        return _run_record_unreadable(run_id, exc, tool="flextools_parse_log", args=dict(args))

    result: Dict[str, Any] = {"status": "ok", "run_id": run_id, "section": section,
                              "applicable": True}

    if section == "summary":
        from dataclasses import asdict

        summary = asdict(meta) if meta is not None else {}
        summary["results_recorded"] = record.result_count()
        summary["traces_recorded"] = sorted(_trace_indices(record))
        summary["run_spine"] = meta.effective_spine if meta is not None else IN_PROCESS_SPINE
        if meta is not None and meta.words_path is not None:
            # A batch run: the US5 report, computed from the artifact alone.
            from ...signals.report import build_report

            summary["report"] = build_report(
                record.iter_results(),
                meta.project_state,
                budget=_drill_down_budget(args.get("drill_down_cap")),
                offset=offset,
                limit=limit,
            )
        if summary.get("engine_changed_midjob"):
            summary["warnings"] = [
                "The project's active parser changed while this run was going. "
                "Its results are labelled with the engine it was submitted on."
            ]
        result["content"] = summary

    elif section == "words":
        words = record.read_words()
        source = "words.txt"
        if words is None:
            # A single-word run writes no word list (an empty one would read
            # as "resolved to nothing"); its words are its result lines.
            words = [line.get("wordform") for line in record.iter_results()]
            source = "results.jsonl (this run has no resolved word list)"
        result["source"] = source
        result.update(_page(words, offset, limit))
        if not words:
            result["note"] = _empty_note(meta, "words")

    elif section == "results":
        lines = list(record.iter_results())
        result.update(_page(lines, offset, limit))
        if not lines:
            result["note"] = _empty_note(meta, "results")

    elif section == "deletions":
        # CP4 (FR-031, FR-041): a filing run's captures, read from disk like
        # every other section. A read-only run has none to have: it is
        # reported not applicable -- never as an empty section (FR-028).
        if meta is None or not meta.filing:
            result = {
                "status": "ok", "run_id": run_id, "section": section,
                "applicable": False, "reason": "not_applicable_for_this_run",
                "note": (
                    "This section holds a filing run's pre-deletion captures -- "
                    "filing runs only. This run was read-only: it filed nothing, so "
                    "nothing was captured. It is not applicable, not empty."
                ),
            }
        else:
            lines = list(record.iter_jsonl(filing_paths.DELETIONS_RELPATH))
            result.update(_page(lines, offset, limit))
            if not lines:
                result["note"] = (
                    "No analysis was captured: this filing run deleted nothing and "
                    "overwrote no human disapproval (or stopped before its first "
                    "word -- see the summary's filing block)."
                )

    else:  # trace
        result.update(_trace_section(record, args, meta))

    return json_response(build_response_with_context(result))


def _trace_indices(record) -> List[int]:
    if not record.traces_dir.is_dir():
        return []
    indices = []
    for path in record.traces_dir.glob("*.xml"):
        if path.stem.isdigit():
            indices.append(int(path.stem))
    return indices


def _trace_section(record, args: dict, meta) -> Dict[str, Any]:
    """One trace: a one-line reading if it parses, the raw slice if not (FR-029)."""
    available = sorted(_trace_indices(record))
    if not available:
        return {
            "available_traces": [],
            "note": (
                "No trace was recorded for this run. Traces are written only "
                "where a drill-down was taken; a batch is never traced in bulk."
            ),
        }
    index = args.get("trace_index")
    if index is None:
        index = available[0]
    index = int(index)
    if index not in available:
        return {
            "available_traces": available,
            "trace_index": index,
            "note": f"No trace was recorded for word {index}. Traces exist for: {available}.",
        }
    xml = record.read_trace(index) or ""
    cap = int(args.get("max_trace_chars") or 20000)
    out: Dict[str, Any] = {"available_traces": available, "trace_index": index,
                           "trace_path": f"traces/{index}.xml",
                           "trace_chars": len(xml)}
    reading = summarize_trace_xml(xml)
    if reading is None:
        # FR-029: returned raw, labelled raw, nothing invented about it.
        out["format"] = "raw"
        out["raw"] = xml[:cap]
        out["raw_truncated"] = len(xml) > cap
        out["note"] = (
            "This trace could not be read as a parser trace document, so it is "
            "returned exactly as recorded and labelled raw. No explanation is "
            "offered for output this tool could not read."
        )
    else:
        out["format"] = "parsed"
        out.update(reading)
    return out


def summarize_trace_xml(xml: str) -> Optional[Dict[str, Any]]:
    """A one-line reading of a HermitCrab trace, or None if it is unreadable.

    Reads only what the trace states (FwXmlTraceManager.cs): `FailureReason`
    elements and their `type`, the rule element beside each one, and the
    `ParseCompleteTrace` successes. It names the most frequent rejection and
    where it first occurred; it does not guess at a cause the trace does not
    record. A document that is not XML, or not a trace, returns None and the
    caller labels it raw (FR-029).
    """
    import xml.etree.ElementTree as ET
    from collections import Counter

    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    traces = [e for e in root.iter() if e.tag.endswith("Trace")]
    if not traces and root.tag != "Wordform":
        return None

    parent = {child: node for node in root.iter() for child in node}
    reasons = []
    for element in root.iter("FailureReason"):
        owner = parent.get(element)
        rule = None
        if owner is not None:
            for sibling in owner:
                if sibling.tag.endswith("Rule") and (sibling.text or "").strip():
                    rule = sibling.text.strip()
                    break
        reasons.append({
            "type": element.get("type") or "unspecified",
            "stage": owner.tag if owner is not None else None,
            "rule": rule,
        })
    successes = sum(
        1 for e in root.iter("ParseCompleteTrace") if (e.get("success") or "").lower() == "true"
    )
    analyses = sum(1 for e in root if e.tag == "Analysis")

    if not reasons:
        line = (
            f"The trace records {successes} successful parse path(s) and no "
            f"rejection reason."
        )
        return {"summary_line": line, "rejections": 0, "successful_paths": successes,
                "analyses": analyses, "rejections_by_type": {}}

    counts = Counter(r["type"] for r in reasons)
    top_type, top_count = counts.most_common(1)[0]
    first = next(r for r in reasons if r["type"] == top_type)
    where = []
    if first["rule"]:
        where.append(f"rule {first['rule']!r}")
    if first["stage"]:
        where.append(first["stage"])
    line = (
        f"The trace records {len(reasons)} rejection(s); the most frequent is "
        f"'{top_type}' ({top_count})"
        + (f", first at {' in '.join(where)}" if where else "")
        + "."
    )
    return {
        "summary_line": line,
        "rejections": len(reasons),
        "rejections_by_type": dict(counts),
        "first_of_most_frequent": first,
        "successful_paths": successes,
        "analyses": analyses,
    }


# ---------------------------------------------------------------------------
# flextools_parse_diff (CP3, US4)
# ---------------------------------------------------------------------------


async def handle_flextools_parse_diff(args: dict) -> List[TextContent]:
    """Compare two runs: fixed, broken, changed, unchanged (FR-030).

    Read-only. Reads two run records; never reaches a worker or the engine
    check (FR-024).
    """
    from ...parse.diff import RunNotComparable, compare_runs
    from ...parse.fingerprint import ScopeMismatch

    baseline_id = str(args.get("baseline_run_id") or "")
    current_id = str(args.get("current_run_id") or "")
    force = bool(args.get("force"))

    baseline = _log_record(baseline_id)
    if baseline is None:
        return _run_not_found(baseline_id)
    current = _log_record(current_id)
    if current is None:
        return _run_not_found(current_id)

    current_meta = current.read_meta()
    access = common._probe_access(current_meta.project_name if current_meta else None)

    try:
        comparison = compare_runs(baseline, current, force=force, access=access)
    except ScopeMismatch as refused:
        detail = dict(refused.detail)
        detail.pop("error_code", None)
        return error_response("parse_scope_mismatch", detail.get("hint") or str(refused), **detail)
    except RunNotComparable as exc:
        return error_response("runtime_error", str(exc), reason="not_a_batch_run")

    result: Dict[str, Any] = {"status": "ok"}
    result.update(comparison.to_dict())
    return json_response(build_response_with_context(result))
