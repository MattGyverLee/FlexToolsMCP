#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The durable run record (parser-check CP2b, FR-029; data-model.md section 5).

Results accumulate here **as they are produced**, so a run that dies or is
cancelled leaves everything completed so far readable (SC-008). That is the
entire point of the module, and it is what dictates every decision below.

LAYOUT, following `server/skeleton_storage.py` (R-07):

    <record dir>/<run_id>/
        meta.json        # the Run's current state, REWRITTEN on stage change
        results.jsonl    # one line per completed word, APPENDED and flushed
        traces/<n>.xml   # trace payloads, out of line

WHY meta IS REWRITTEN AND results ARE APPENDED. `meta.json` is current
state; `results.jsonl` is history. Folding the two into one appended file
would make "what stage is this run in now" an O(file) read on every status
poll -- and status is polled precisely on the long runs whose files are
largest.

WHY THE FLUSH IS PER WORD AND NOT A DETAIL. A buffered write loses the tail
of a killed run, which is exactly SC-008's case: the worker is killed, and
everything already parsed must still be readable. Buffering would make the
last few results vanish -- the ones most likely to matter, since a run is
usually killed because of what it was doing at the end. So each result line
is written, flushed, and fsync-free but OS-visible before the call returns.

WHY TRACES GO OUT OF LINE. The parent specification calls trace payload size
"a design decision rather than a detail". A full trace is XML measured in
tens or hundreds of kilobytes; inlining one into a tool response makes the
response unreadable and can overflow what the transport will carry. The
record stores the trace as its own file and the result line carries a
pointer.

WHY THERE IS A SIZE CAP FROM DAY ONE. `skeleton_storage`'s own docstring
records unbounded growth as known debt -- acceptable there, where a payload
is a few lines of Python source. A record of parse traces cannot inherit
that omission: the payloads are orders of magnitude larger and a batch
produces one per word. The cap is enforced here rather than deferred (R-07).

WHY `run_id` IS SERVER-ISSUED. It is a path component. A caller-supplied
string would make directory traversal reachable from a tool argument, so
ids are minted here from `secrets` and validated on every use; no caller
string ever reaches the filesystem.

This module is pure server-side: no pythonnet, no project, no FieldWorks.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Iterator, Optional

from .stages import RunStage

__all__ = [
    "RunRecord",
    "RecordSizeExceeded",
    "InvalidRunId",
    "get_record_dir",
    "new_run_id",
    "is_valid_run_id",
    "list_run_ids",
]

_ENV_VAR = "FLEXTOOLSMCP_PARSE_RECORD_DIR"
_DEFAULT_SUBDIR = ".flextoolsmcp"
_RECORDS_SUBDIR = "parse-runs"

_META_FILENAME = "meta.json"
_RESULTS_FILENAME = "results.jsonl"
_TRACES_DIRNAME = "traces"

#: Default cap on a single run's on-disk footprint. Generous enough that a
#: real batch does not trip it, small enough that a runaway run cannot fill
#: a disk. Override per-record for tests, or globally with the env var.
DEFAULT_MAX_RECORD_BYTES = 256 * 1024 * 1024  # 256 MiB
_ENV_MAX_BYTES = "FLEXTOOLSMCP_PARSE_RECORD_MAX_BYTES"

#: A minted run id: 32 lowercase hex characters. Anchored, and checked on
#: every path construction -- this is the guard that keeps a caller string
#: out of the filesystem.
_RUN_ID_RE = re.compile(r"\A[0-9a-f]{32}\Z")

_WRITE_LOCK = Lock()


class RecordSizeExceeded(RuntimeError):
    """A run's record hit its size cap.

    Raised rather than silently truncating: a record that quietly stopped
    accepting results would make a partial run indistinguishable from a
    complete one, which is the opposite of what FR-029 is for.
    """


class InvalidRunId(ValueError):
    """A run id was not a server-minted identifier."""


def get_record_dir() -> Path:
    """Where run records live. Honors the env override."""
    override = os.environ.get(_ENV_VAR)
    if override:
        return Path(override)
    return Path.home() / _DEFAULT_SUBDIR / _RECORDS_SUBDIR


def new_run_id() -> str:
    """Mint an opaque run id. Never derived from caller input."""
    return secrets.token_hex(16)


def is_valid_run_id(run_id: str) -> bool:
    return bool(_RUN_ID_RE.match(run_id or ""))


def _require_valid_run_id(run_id: str) -> str:
    if not is_valid_run_id(run_id):
        raise InvalidRunId(
            f"{run_id!r} is not a server-issued run id. Run ids are minted by "
            f"new_run_id() and are 32 hex characters. A caller-supplied string "
            f"must never become a path component -- that is how traversal "
            f"becomes reachable from a tool argument."
        )
    return run_id


def _max_record_bytes() -> int:
    raw = os.environ.get(_ENV_MAX_BYTES)
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_MAX_RECORD_BYTES


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_run_ids() -> list[str]:
    """Every run id with a record on disk, newest first.

    Backs `parse_run_not_found`'s "and here are the handles that do exist"
    (FR-035), which is why it tolerates a missing directory rather than
    raising -- being asked about a run before any run has happened is a
    perfectly ordinary thing for a caller to do.
    """
    root = get_record_dir()
    if not root.is_dir():
        return []
    entries = [p for p in root.iterdir() if p.is_dir() and is_valid_run_id(p.name)]
    entries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in entries]


@dataclass
class RunMeta:
    """The Run's current state. Rewritten whole on every stage change."""

    run_id: str
    stage: str
    project_name: Optional[str] = None
    words_total: int = 0
    words_completed: int = 0
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    #: Set while a higher-priority word is interleaving, so a caller polling
    #: mid-interleave sees why progress paused instead of a stalled run
    #: (FR-031).
    interleaved_by: Optional[str] = None
    failure: Optional[dict[str, Any]] = None
    stage_at_cancel: Optional[str] = None


class RunRecord:
    """One run's durable record.

    Every write is under the module lock and flushed before returning. The
    lock is module-level rather than per-instance because two RunRecord
    objects can legitimately address the same run_id (a status poll and the
    worker channel), and per-instance locks would not serialize those.
    """

    def __init__(
        self,
        run_id: str,
        *,
        max_bytes: Optional[int] = None,
        record_dir: Optional[Path] = None,
    ) -> None:
        self.run_id = _require_valid_run_id(run_id)
        self._root = (record_dir or get_record_dir()) / self.run_id
        self._max_bytes = max_bytes if max_bytes is not None else _max_record_bytes()

    # -- paths ------------------------------------------------------------

    @property
    def root(self) -> Path:
        return self._root

    @property
    def meta_path(self) -> Path:
        return self._root / _META_FILENAME

    @property
    def results_path(self) -> Path:
        return self._root / _RESULTS_FILENAME

    @property
    def traces_dir(self) -> Path:
        return self._root / _TRACES_DIRNAME

    # -- lifecycle --------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        project_name: Optional[str] = None,
        words_total: int = 0,
        max_bytes: Optional[int] = None,
        record_dir: Optional[Path] = None,
    ) -> "RunRecord":
        """Mint a run id and open its record at stage `starting`."""
        record = cls(new_run_id(), max_bytes=max_bytes, record_dir=record_dir)
        record._root.mkdir(parents=True, exist_ok=True)
        record.write_meta(
            RunMeta(
                run_id=record.run_id,
                stage=RunStage.STARTING.value,
                project_name=project_name,
                words_total=words_total,
            )
        )
        return record

    def exists(self) -> bool:
        return self.meta_path.is_file()

    # -- meta -------------------------------------------------------------

    def write_meta(self, meta: RunMeta) -> None:
        """Rewrite meta.json whole. Written to a temp file then replaced.

        The replace is atomic on both POSIX and Windows, so a status poll
        landing mid-write reads either the old state or the new one, never a
        half-written file. A status tool that could return a truncated
        meta.json would turn a successful query into a spurious failure.
        """
        meta.updated_at = _now_iso()
        payload = json.dumps(asdict(meta), ensure_ascii=False, indent=2)
        with _WRITE_LOCK:
            self._root.mkdir(parents=True, exist_ok=True)
            tmp = self.meta_path.with_suffix(".json.tmp")
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, self.meta_path)

    def read_meta(self) -> Optional[RunMeta]:
        if not self.meta_path.is_file():
            return None
        try:
            data = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        known = {f for f in RunMeta.__dataclass_fields__}
        return RunMeta(**{k: v for k, v in data.items() if k in known})

    def set_stage(self, stage: RunStage, **updates: Any) -> RunMeta:
        """Move the run to a stage and persist immediately."""
        meta = self.read_meta() or RunMeta(
            run_id=self.run_id, stage=RunStage.STARTING.value
        )
        meta.stage = stage.value
        for key, value in updates.items():
            setattr(meta, key, value)
        self.write_meta(meta)
        return meta

    # -- results ----------------------------------------------------------

    def append_result(self, result: dict[str, Any]) -> None:
        """Append one completed word's result and FLUSH before returning.

        The flush is the requirement, not an optimization detail: a buffered
        write loses the tail of a killed run, and the tail is what SC-008 is
        about.
        """
        self._enforce_size_cap()
        line = json.dumps(result, ensure_ascii=False)
        with _WRITE_LOCK:
            self._root.mkdir(parents=True, exist_ok=True)
            with open(self.results_path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())

    def iter_results(self) -> Iterator[dict[str, Any]]:
        """Every result written so far.

        A malformed trailing line is skipped rather than raised on: a run
        killed mid-write can leave a partial final line, and the whole
        promise of this module is that everything BEFORE that stays
        readable. Raising here would throw away the results the record
        exists to preserve.
        """
        if not self.results_path.is_file():
            return
        with open(self.results_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    def result_count(self) -> int:
        return sum(1 for _ in self.iter_results())

    # -- traces -----------------------------------------------------------

    def write_trace(self, index: int, xml: str) -> Path:
        """Store a trace payload out of line. Returns its path.

        `index` is an int supplied by the runner, never a caller string, so
        the filename cannot carry traversal.
        """
        self._enforce_size_cap()
        with _WRITE_LOCK:
            self.traces_dir.mkdir(parents=True, exist_ok=True)
            path = self.traces_dir / f"{int(index)}.xml"
            path.write_text(xml, encoding="utf-8")
        return path

    def read_trace(self, index: int) -> Optional[str]:
        path = self.traces_dir / f"{int(index)}.xml"
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    # -- size cap ---------------------------------------------------------

    def total_bytes(self) -> int:
        if not self._root.is_dir():
            return 0
        return sum(p.stat().st_size for p in self._root.rglob("*") if p.is_file())

    def _enforce_size_cap(self) -> None:
        if self._max_bytes <= 0:
            return
        size = self.total_bytes()
        if size >= self._max_bytes:
            raise RecordSizeExceeded(
                f"Run {self.run_id} has reached its record size cap: "
                f"{size} bytes >= {self._max_bytes}. The run is stopped rather "
                f"than silently truncated -- a record that quietly stopped "
                f"accepting results would make a partial run indistinguishable "
                f"from a complete one. Raise "
                f"{_ENV_MAX_BYTES} if this limit is genuinely too low."
            )
