#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Q3 and Q5 (parser-check CP4, T004), live, on a disposable copy.

  Q3 staleness: does filing a word make `IsUpToDate()` false, so that the
     filing worker reloads the grammar before the next word (R-05)? Counted
     from the worker's own "grammar reloaded mid-run" lines over a 5-word run.
  Q5 checksum: file the same scope twice with the grammar unchanged. Does the
     second run -- a NEW filing worker process -- report every word
     `unchanged`? (`Wordform.Checksum == ParseResult.GetHashCode()` compared
     across processes; US2 AS-6.)

WRITES ONLY TO A `CP4-Scratch-` COPY, deleted at the end with its backups.

    python tests/live_support/q3_q5_filing.py [--source P] [--words 5] [--keep]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2] / "src"))
sys.path.insert(0, str(_HERE.parent))

from l0_coexistence import EVIDENCE, Recorder, _capture_worker_stderr, _text  # noqa: E402
from make_disposable import delete_disposable, make_disposable, require_disposable  # noqa: E402


async def _file_once(parse_handler, runner, scope) -> dict:
    preview = _text(await parse_handler.handle_flextools_parse_text(dict(scope, apply=True)))
    if preview.get("error_code") != "confirmation_required":
        return {"stopped_at": "preview", "response": preview}
    started = _text(await parse_handler.handle_flextools_parse_text(
        dict(scope, apply=True, confirmed=True, plan_id=preview["plan_id"])))
    if not started.get("run_id"):
        return {"stopped_at": "confirm", "response": started}
    await asyncio.wait_for(runner.get(started["run_id"]).done.wait(), timeout=1800)
    summary = _text(await parse_handler.handle_flextools_parse_log(
        {"run_id": started["run_id"], "section": "summary"}))
    filing = (summary.get("content") or {}).get("filing") or {}
    plan = preview.get("plan") or {}
    return {"run_id": started["run_id"],
            "upper_bound": (plan.get("deletion_projection") or {}).get("upper_bound"),
            **{k: filing.get(k) for k in ("state", "persisted", "counts", "filed_words",
                                          "actual_deletions", "error")}}


async def _run(name: str, fwdata: Path, record_dir: Path, n_words: int, stderr: list) -> dict:
    from flextoolsmcp.server.filing import claims
    from flextoolsmcp.server.handlers import parse as parse_handler
    from flextoolsmcp.server.parse.runner import ParseRunner

    claims.clear()
    session = parse_handler.session_state
    session.write_enabled = True
    session.filing_plans = {}
    session.filing_backed_up_projects = set()
    rec = Recorder(name, fwdata)
    rec.mark("copy")
    runner = ParseRunner(record_dir=record_dir)
    parse_handler.set_runner(runner)
    out: dict = {"project": name}
    try:
        resolved = await runner.resolve_scope(name, {"kind": "all_texts", "limit": n_words})
        words = list(resolved["words"])
        out["words"] = words
        scope = {"project_name": name, "scope_kind": "words", "scope_value": words}
        baseline = _text(await parse_handler.handle_flextools_parse_text(dict(scope)))
        await asyncio.wait_for(runner.get(baseline["run_id"]).done.wait(), timeout=1800)

        mark = len(stderr)
        out["run1"] = await _file_once(parse_handler, runner, scope)
        out["run1_reload_lines"] = [ln for ln in stderr[mark:] if "grammar reloaded mid-run" in ln]
        rec.mark("after_run1")

        mark = len(stderr)
        out["run2"] = await _file_once(parse_handler, runner, scope)
        out["run2_reload_lines"] = [ln for ln in stderr[mark:] if "grammar reloaded mid-run" in ln]
        rec.mark("after_run2")
    finally:
        parse_handler.set_runner(None)
        await runner.aclose()

    run1, run2 = out.get("run1") or {}, out.get("run2") or {}
    counts2 = run2.get("counts") or {}
    by = {s["step"]: s for s in rec.steps}
    out["verdicts"] = {
        "q3_filing_marks_grammar_stale": bool(out.get("run1_reload_lines")),
        "q3_reloads_in_run1": len(out.get("run1_reload_lines") or []),
        "q5_second_run_all_unchanged": (counts2.get("unchanged") == len(out["words"])
                                        if counts2 else None),
        "q5_second_run_unchanged": counts2.get("unchanged"),
        "run1_state": run1.get("state"),
        "run2_state": run2.get("state"),
        "run2_changed_file": (by["after_run1"]["fwdata"]["sha256"] != by["after_run2"]["fwdata"]["sha256"]
                              if "after_run2" in by else None),
    }
    out["steps"] = rec.steps
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="IndonesianHC-Complete")
    ap.add_argument("--words", type=int, default=5)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)
    evidence: dict = {"recorded_at": datetime.now(timezone.utc).isoformat()}
    record_dir = Path(tempfile.mkdtemp(prefix="cp4-q3q5-runs-"))
    stderr = _capture_worker_stderr()
    copy = None
    try:
        copy = make_disposable(args.source)
        require_disposable(copy.name)
        evidence["result"] = asyncio.run(_run(copy.name, copy.fwdata, record_dir, args.words, stderr))
    except Exception as exc:  # noqa: BLE001
        import traceback

        evidence["error"] = f"{type(exc).__name__}: {exc}"
        evidence["traceback"] = traceback.format_exc()[-4000:]
    finally:
        evidence["worker_stderr_tail"] = stderr[-40:]
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "q3-q5-raw.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"[Q3/Q5] evidence -> {EVIDENCE / 'q3-q5-raw.json'}", flush=True)
        if copy is not None and not args.keep:
            delete_disposable(copy.name)
            shutil.rmtree(Path.home() / ".flextoolsmcp" / "backups" / copy.name, ignore_errors=True)
        shutil.rmtree(record_dir, ignore_errors=True)
    return 0 if "error" not in evidence else 1


if __name__ == "__main__":
    sys.exit(main())
