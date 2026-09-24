#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L-0: can two processes hold one NON-SHARED project -- the read worker's
read-only open and the filing worker's writable open? (parser-check CP4,
T003; research R-10; quickstart "L-0".)

WRITES, BUT ONLY TO A DISPOSABLE COPY. The copy is made here, named
`CP4-Scratch-...`, and deleted at the end (keep it with --keep). The filing
backup this run takes goes to `~/.flextoolsmcp/backups/<copy>/` and is
removed with the copy.

The probe drives the REAL handler, runner and worker processes. Coexistence
is asked directly, below every MCP gate: with the read worker holding the
project, a second process tries `OpenProject(writeEnabled=True)`
(`_raw_writable_open`), and again after the release as a control. Filing
then runs on the production path, which releases the read worker first.

Steps (quickstart L-0), with a .fwdata snapshot (sha256, mtime, size) and
an access probe (lock file, holder PID, verdict) at every one:

  1. copy; snapshot                                   "copy"
  2. try_word -> the read worker opens read-only      "read_open"
  3. a read-only batch of the scope (the gate's baseline)
  4. preview, then confirm: the filing worker opens writable ALONGSIDE the
     live read worker, files one word, commits, closes    "filed"
     (the read worker is asked a word again while/after filing, to show it
     still answers)
  5. release the read worker                          "read_released"
     -> did the release rewrite the file? (hash/mtime vs "filed")
  6. a FRESH read worker reads the word's stored analyses: are the analyses
     filing created still there?                      "reread"
  7. (--xample SOURCE) the XAmple-refusal path on a scratch copy of an
     XAmple project: try_word is refused; does releasing the worker rewrite
     the file? (memory `parse-worker-saves-xample-project`)

    python tests/live_support/l0_coexistence.py [--source P] [--xample "Sena 3"] [--keep]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(_HERE.parent))

from make_disposable import delete_disposable, make_disposable, require_disposable  # noqa: E402

EVIDENCE = REPO / "specs" / "parser-check-cp4" / "evidence"


def _snapshot(fwdata: Path) -> dict:
    data = fwdata.read_bytes()
    stat = fwdata.stat()
    return {"sha256": hashlib.sha256(data).hexdigest(), "mtime": stat.st_mtime,
            "size": stat.st_size}


def _access(name: str) -> dict:
    from flextoolsmcp.server import project_access

    from make_disposable import projects_dir

    lock = project_access._lock_path_for(projects_dir(), name)
    result = {"lock_path": str(lock) if lock else None,
              "lock_exists": bool(lock and Path(lock).exists())}
    if result["lock_exists"]:
        try:
            result["lock_text"] = Path(lock).read_text(encoding="utf-8", errors="replace")[:400]
        except OSError as exc:
            result["lock_text"] = f"unreadable: {exc}"
    try:
        access = project_access.probe_project_access(name)
        result["verdict"] = access.verdict
        holder = access.holder
        result["holder"] = None if holder is None else {
            "pid": holder.pid, "process_name": holder.process_name}
    except Exception as exc:  # noqa: BLE001 -- recorded, not fatal
        result["verdict"] = f"probe failed: {type(exc).__name__}: {exc}"
    return result


_RAW_OPEN = r"""
import json, sys
sys.path.insert(0, sys.argv[2])
from flexicon import FLExInitialize, FLExCleanup, FLExProject
from flextoolsmcp.server.parse.worker_main import headless_ui_kwargs
FLExInitialize()
p = FLExProject()
out = {}
try:
    p.OpenProject(projectName=sys.argv[1], writeEnabled=True, undoable=False, **headless_ui_kwargs(FLExProject))
    out["opened"] = True
    try:
        p.CloseProject()
        out["closed"] = True
    except Exception as exc:
        out["close_error"] = f"{type(exc).__name__}: {exc}"
except Exception as exc:
    out["opened"] = False
    out["open_error"] = f"{type(exc).__name__}: {exc}"[:1500]
finally:
    FLExCleanup()
print("RAW " + json.dumps(out))
"""


def _raw_writable_open(name: str) -> dict:
    """A second process opens the project WRITABLE, then closes. The L-0 core."""
    import subprocess

    require_disposable(name)
    done = subprocess.run([sys.executable, "-c", _RAW_OPEN, name, str(REPO / "src")],
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    lines = [ln[4:] for ln in done.stdout.splitlines() if ln.startswith("RAW ")]
    result = json.loads(lines[-1]) if lines else {"opened": None}
    result["rc"] = done.returncode
    if done.returncode and not lines:
        result["stderr_tail"] = done.stderr[-2000:]
    return result


def _text(response) -> dict:
    return json.loads(response[0].text)


class Recorder:
    def __init__(self, name: str, fwdata: Path):
        self.name, self.fwdata = name, fwdata
        self.steps: list = []

    def mark(self, label: str, **extra) -> dict:
        step = {"step": label, "at": datetime.now(timezone.utc).isoformat(),
                "fwdata": _snapshot(self.fwdata), "access": _access(self.name), **extra}
        self.steps.append(step)
        print(f"[L-0] {label}: sha={step['fwdata']['sha256'][:12]} "
              f"lock={step['access'].get('lock_exists')} verdict={step['access'].get('verdict')}",
              flush=True)
        return step


async def _coexistence(name: str, fwdata: Path, record_dir: Path) -> dict:
    from flextoolsmcp.server.filing import claims
    from flextoolsmcp.server.handlers import parse as parse_handler
    from flextoolsmcp.server.parse.runner import ParseRunner
    from flextoolsmcp.server.parse.worker_client import SHARED_ROLE

    # The PRODUCTION path: the flag stays at its default, so the handler
    # releases the read worker before the writable open. Coexistence itself is
    # answered below every gate by `_raw_writable_open`.
    claims.clear()
    session = parse_handler.session_state
    session.write_enabled = True
    session.filing_plans = {}
    session.filing_backed_up_projects = set()

    rec = Recorder(name, fwdata)
    rec.mark("copy")
    out: dict = {"project": name}

    runner = ParseRunner(record_dir=record_dir)
    parse_handler.set_runner(runner)
    try:
        resolved = await runner.resolve_scope(name, {"kind": "all_texts", "limit": 1})
        word = resolved["words"][0]
        out["word"] = word
        tried = _text(await parse_handler.handle_flextools_try_word(
            {"project_name": name, "word": word, "level": "plain"}))
        out["try_word_before"] = {k: tried.get(k) for k in ("status", "error_code", "analysis_count")}
        rec.mark("read_open", read_worker_pid=getattr(runner._pool.peek(name), "pid", None))

        # L-0's core question, below every MCP gate: with the read worker
        # holding the project, can a second process open it WRITABLE?
        out["raw_writable_open_while_read_worker_holds"] = _raw_writable_open(name)
        rec.mark("raw_writable_open_during")

        scope = {"project_name": name, "scope_kind": "words", "scope_value": [word]}
        baseline = _text(await parse_handler.handle_flextools_parse_text(dict(scope)))
        await asyncio.wait_for(runner.get(baseline["run_id"]).done.wait(), timeout=900)
        out["baseline_run"] = baseline.get("run_id")

        preview = _text(await parse_handler.handle_flextools_parse_text(dict(scope, apply=True)))
        out["preview"] = {k: preview.get(k) for k in ("status", "error_code", "message", "plan_id")}
        if preview.get("error_code") != "confirmation_required":
            out["stopped"] = "preview did not return confirmation_required"
            out["preview_full"] = preview
            return {"steps": rec.steps, **out}
        out["plan_deletion"] = (preview.get("plan") or {}).get("deletion_projection")
        started = _text(await parse_handler.handle_flextools_parse_text(
            dict(scope, apply=True, confirmed=True, plan_id=preview["plan_id"])))
        out["confirmed"] = {k: started.get(k) for k in ("status", "error_code", "message", "run_id", "backup")}
        if not started.get("run_id"):
            out["stopped"] = "confirmed call did not start a run"
            out["confirmed_full"] = started
            await runner.release_worker(name, role=SHARED_ROLE)
            rec.mark("read_released")
            out["raw_writable_open_after_release"] = _raw_writable_open(name)
            rec.mark("raw_writable_open_after")
            return {"steps": rec.steps, **out}
        handle = runner.get(started["run_id"])
        during = None
        for _ in range(600):
            if handle.is_terminal:
                break
            if during is None and handle.stage.value not in ("queued", "starting"):
                during = rec.mark("filing_open", stage=handle.stage.value)
            await asyncio.sleep(0.1)
        await asyncio.wait_for(handle.done.wait(), timeout=900)
        summary = _text(await parse_handler.handle_flextools_parse_log(
            {"run_id": started["run_id"], "section": "summary"}))
        filing = (summary.get("content") or {}).get("filing") or {}
        out["filing"] = {k: filing.get(k) for k in (
            "state", "persisted", "counts", "filed_words", "actual_deletions",
            "projected_deletions", "backup", "error")}
        out["filing_results"] = filing.get("words") or filing.get("results")
        still = _text(await parse_handler.handle_flextools_try_word(
            {"project_name": name, "word": word, "level": "plain"}))
        out["try_word_after_filing"] = {k: still.get(k) for k in ("status", "error_code", "analysis_count")}
        rec.mark("filed", read_worker_alive=runner._pool.peek(name) is not None)

        await runner.release_worker(name, role=SHARED_ROLE)
        rec.mark("read_released")
        # Control: the same writable open with no read worker.
        out["raw_writable_open_after_release"] = _raw_writable_open(name)
        rec.mark("raw_writable_open_after")
    finally:
        parse_handler.set_runner(None)
        await runner.aclose()

    # A FRESH read worker: is what filing wrote still on disk?
    runner2 = ParseRunner(record_dir=record_dir)
    try:
        facts = await runner2.filing_preview(name, words=[out["word"]], vernacular_ws=None)
        out["reread"] = facts.get("words", {}).get(out["word"])
        await runner2.release_worker(name, role=SHARED_ROLE)
    finally:
        await runner2.aclose()
    rec.mark("reread")
    return {"steps": rec.steps, **out}


async def _xample(name: str, fwdata: Path, record_dir: Path) -> dict:
    from flextoolsmcp.server.handlers import parse as parse_handler
    from flextoolsmcp.server.parse.runner import ParseRunner
    from flextoolsmcp.server.parse.worker_client import SHARED_ROLE

    from flextoolsmcp.server import project_discovery

    # The copy was made after discovery last listed projects; its 10 s name
    # cache would report the new copy as not found.
    for key in list(project_discovery._cache):
        project_discovery._cache[key] = None if not isinstance(project_discovery._cache[key], (int, float)) else 0
    rec = Recorder(name, fwdata)
    rec.mark("copy")
    runner = ParseRunner(record_dir=record_dir)
    parse_handler.set_runner(runner)
    out: dict = {"project": name}
    try:
        tried = _text(await parse_handler.handle_flextools_try_word(
            {"project_name": name, "word": "a", "level": "plain"}))
        out["try_word"] = {k: tried.get(k) for k in ("status", "error_code", "message")}
        rec.mark("refused_open")
        await runner.release_worker(name, role=SHARED_ROLE)
        rec.mark("released")
    finally:
        parse_handler.set_runner(None)
        await runner.aclose()
    time.sleep(1)
    rec.mark("settled")
    return {"steps": rec.steps, **out}


def _verdicts(result: dict) -> dict:
    by = {s["step"]: s for s in result.get("steps", [])}
    v: dict = {}
    if "filed" in by and "read_released" in by:
        v["release_rewrote_file"] = by["filed"]["fwdata"] != by["read_released"]["fwdata"]
    if "copy" in by and "filed" in by:
        v["filing_changed_file"] = by["copy"]["fwdata"]["sha256"] != by["filed"]["fwdata"]["sha256"]
    return v


def _capture_worker_stderr() -> list:
    """Worker stderr is forwarded to the client logger at DEBUG; keep it."""
    import logging

    lines: list = []

    class _Keep(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage()[:2000])

    logger = logging.getLogger("flextoolsmcp.server.parse.worker_client")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(_Keep())
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="IndonesianHC-Complete")
    ap.add_argument("--xample", default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)

    evidence: dict = {"question": "L-0 (T003): can a writable open coexist with the read "
                                  "worker's read-only open on a NON-shared project?",
                      "recorded_at": datetime.now(timezone.utc).isoformat()}
    record_dir = Path(tempfile.mkdtemp(prefix="cp4-l0-runs-"))
    stderr_lines = _capture_worker_stderr()
    copies = []
    try:
        copy = make_disposable(args.source)
        copies.append(copy)
        require_disposable(copy.name)
        result = asyncio.run(_coexistence(copy.name, copy.fwdata, record_dir))
        result["verdicts"] = _verdicts(result)
        evidence["coexistence"] = result
        if args.xample:
            xcopy = make_disposable(args.xample)
            copies.append(xcopy)
            xres = asyncio.run(_xample(xcopy.name, xcopy.fwdata, record_dir))
            by = {s["step"]: s for s in xres["steps"]}
            xres["verdicts"] = {"release_rewrote_file":
                                by["copy"]["fwdata"] != by["settled"]["fwdata"]}
            evidence["xample_refusal"] = xres
    except Exception as exc:  # noqa: BLE001 -- the evidence says what broke
        import traceback

        evidence["error"] = f"{type(exc).__name__}: {exc}"
        evidence["traceback"] = traceback.format_exc()[-4000:]
    finally:
        evidence["worker_stderr_tail"] = stderr_lines[-60:]
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        (EVIDENCE / "l0-coexistence.json").write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"[L-0] evidence -> {EVIDENCE / 'l0-coexistence.json'}", flush=True)
        if not args.keep:
            for c in copies:
                delete_disposable(c.name)
                shutil.rmtree(Path.home() / ".flextoolsmcp" / "backups" / c.name,
                              ignore_errors=True)
        shutil.rmtree(record_dir, ignore_errors=True)
    return 0 if "error" not in evidence else 1


if __name__ == "__main__":
    sys.exit(main())
