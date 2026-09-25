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
        words.txt        # the resolved word list (CP3) -- written once, at creation
        traces/<n>.xml   # trace payloads, out of line

This is the frozen artifact contract CP4 and CP5 read
(specs/parser-check-cp3/contracts/artifact.md). `words.txt` is the only file
CP3 added; nothing else is created, and in particular no sandbox-spine file is
written or created empty (FR-015) -- that spine is CP5's.

CP5 (additive, contracts/artifact.md section 9): a sandbox run adds a
`sandbox/` subdirectory holding the files named in `SANDBOX_FILES`
(CP5 data-model.md section 6.3), and two `RunMeta` fields, `spine` and
`sandbox`. An in-process run creates neither the directory nor the
section, so a CP4 reader sees the record it always did.

WHY THE HOST COUNTERS LIVE HERE. `HostCounters` is computed from nothing but
the result lines this module already holds, so a run's counters are a pure
function of its own record: a reader that recomputes them from
`results.jsonl` gets the same numbers the run wrote, with no project open.
The two counters whose meaning deliberately differs from the host
application's are stated in `meta.json` itself (`counter_divergences`), not
only in the specification -- a reader of the artifact never sees the spec.

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
import logging
import os
import re
import secrets
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Iterable, Iterator, Literal, Optional

from .stages import RunStage

_log = logging.getLogger(__name__)

__all__ = [
    "RunRecord",
    "RunMeta",
    "HostCounters",
    "HOST_COUNTER_NAMES",
    "COUNTER_DIVERGENCES",
    "RecordSizeExceeded",
    "InvalidRunId",
    "MetaUnreadable",
    "META_READ_ATTEMPTS",
    "META_RETRY_DELAY_SECONDS",
    "get_record_dir",
    "new_run_id",
    "is_valid_run_id",
    "list_run_ids",
    "SPINE_IN_PROCESS",
    "SPINE_SANDBOX",
    "SANDBOX_DIRNAME",
    "SANDBOX_FILES",
]

_ENV_VAR = "FLEXTOOLSMCP_PARSE_RECORD_DIR"
_DEFAULT_SUBDIR = ".flextoolsmcp"
_RECORDS_SUBDIR = "parse-runs"

_META_FILENAME = "meta.json"
_RESULTS_FILENAME = "results.jsonl"
_WORDS_FILENAME = "words.txt"
_TRACES_DIRNAME = "traces"

#: CP5: the two spines a run can take (data-model.md section 6.1).
SPINE_IN_PROCESS = "in_process"
SPINE_SANDBOX = "sandbox"
Spine = Literal["in_process", "sandbox"]

#: CP5: the sandbox run's own files, all under `sandbox/` in the run
#: directory (data-model.md section 6.3). A closed set: a name outside it is
#: refused, so a typo cannot quietly invent an artifact no reader knows.
SANDBOX_DIRNAME = "sandbox"
SANDBOX_FILES: tuple[str, ...] = (
    "generate-config.log",
    "hc-script.txt",
    "dispatch.json",
    "hc-stdout.txt",
    "hc-stderr.txt",
    "hc-output.txt",
    "run.json",
)

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


#: `read_meta`'s bounded retry for a meta.json that exists but cannot be
#: read (a transient sharing violation under load): 4 x 50 ms.
META_READ_ATTEMPTS = 4
META_RETRY_DELAY_SECONDS = 0.05


class MetaUnreadable(OSError):
    """meta.json exists but could not be read or parsed, even after retrying."""


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


def list_run_ids(record_dir: Optional[Path] = None) -> list[str]:
    """Every run id with a record on disk, newest first.

    Backs `parse_run_not_found`'s "and here are the handles that do exist"
    (FR-035), which is why it tolerates a missing directory rather than
    raising -- being asked about a run before any run has happened is a
    perfectly ordinary thing for a caller to do.

    Ordered by mtime, which is right for naming handles and WRONG for
    retention -- see `retention.py`, which orders by recorded creation time.
    """
    root = record_dir or get_record_dir()
    if not root.is_dir():
        return []
    entries = [p for p in root.iterdir() if p.is_dir() and is_valid_run_id(p.name)]
    entries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in entries]


# ---------------------------------------------------------------------------
# The host application's parser-report counters (CP3, FR-017..FR-019)
# ---------------------------------------------------------------------------

#: The eight names, VERBATIM from the host application's `ParserReport`
#: (FieldWorks `ParserCore/ParserReport.cs`) and from contracts/tools.md
#: section 4. Transcribed, not re-derived.
HOST_COUNTER_NAMES: tuple[str, ...] = (
    "NumWords",
    "NumParseErrors",
    "NumZeroParses",
    "TotalParseTime",
    "TotalAnalyses",
    "TotalUserApprovedAnalysesMissing",
    "TotalUserDisapprovedAnalyses",
    "TotalUserNoOpinionAnalyses",
)

#: The two deliberate divergences from the host's semantics, stated IN THE
#: ARTIFACT (FR-017). Each line names the counter it qualifies first, so a
#: reader can find the qualification from the name.
COUNTER_DIVERGENCES: tuple[str, ...] = (
    "TotalUserApprovedAnalysesMissing: counts only FULLY LINKED human-approved "
    "analyses (every morph bundle present and complete) that the parser did "
    "not produce. The host application counts every human-approved analysis; "
    "an analysis that records a meaning but no decomposition, or one whose "
    "morphs are not all linked, has no morphology the parser could have "
    "produced, so counting it as 'missing' would report a gap in the human "
    "record as a parser failure.",
    "TotalUserNoOpinionAnalyses: the number of parser analyses that match no "
    "stored human opinion. It is NOT a count of unreviewed analyses: a human "
    "may have seen an analysis and recorded nothing, and approval is recorded "
    "for anything left in use in a text, so absence of an opinion says nothing "
    "about whether a person looked. What human review established is reported "
    "as the affirmed/indeterminate split of human approvals, never by this "
    "counter.",
)


@dataclass
class HostCounters:
    """The host's eight counters, computed from a run's own result lines.

    SEMANTICS FOLLOW `ParseReport(IWfiWordform, ParseResult)` exactly, word
    by word, with the two stated divergences:

      * NumParseErrors -- words whose parse reported an error message.
      * NumZeroParses  -- words with zero analyses (an error word counts here
                          too, as it does in the host: its analysis list is
                          empty).
      * TotalParseTime -- milliseconds, summed.
      * TotalUserDisapprovedAnalyses -- parser analyses matching a human
        analysis the human disapproved. Matching is signature equality, the
        durable form of the host's `MatchesIWfiAnalysis`.
      * TotalUserApprovedAnalysesMissing -- see COUNTER_DIVERGENCES[0].
      * TotalUserNoOpinionAnalyses -- see COUNTER_DIVERGENCES[1].

    Result lines that carry no `analyses` key -- a CP2b single-word run, or a
    word the run recorded as a per-word error -- contribute to NumWords and
    NumParseErrors only. Nothing about them is guessed.
    """

    NumWords: int = 0
    NumParseErrors: int = 0
    NumZeroParses: int = 0
    TotalParseTime: int = 0
    TotalAnalyses: int = 0
    TotalUserApprovedAnalysesMissing: int = 0
    TotalUserDisapprovedAnalyses: int = 0
    TotalUserNoOpinionAnalyses: int = 0

    def to_dict(self) -> dict[str, int]:
        return {name: getattr(self, name) for name in HOST_COUNTER_NAMES}

    @classmethod
    def from_results(cls, results: Iterable[dict[str, Any]]) -> "HostCounters":
        counters = cls()
        for line in results:
            counters._add(line)
        return counters

    def _add(self, line: dict[str, Any]) -> None:
        self.NumWords += 1
        parse = line.get("parse") or {}
        if line.get("error") is not None or parse.get("error_message"):
            self.NumParseErrors += 1
        analyses = parse.get("analyses")
        if analyses is None:
            return
        self.TotalParseTime += int(parse.get("parse_time_ms") or 0)
        self.TotalAnalyses += len(analyses)
        if not analyses:
            self.NumZeroParses += 1

        human = parse.get("human_analyses") or []
        produced = {_signature_key(a) for a in analyses}

        for record in human:
            if (
                record.get("opinion") == "approves"
                and _fully_linked(record)
                and _signature_key(record) not in produced
            ):
                self.TotalUserApprovedAnalysesMissing += 1

        for analysis in analyses:
            key = _signature_key(analysis)
            opinion = "noopinion"
            for record in human:
                if _signature_key(record) != key:
                    continue
                if record.get("opinion") == "disapproves":
                    opinion = "disapproves"
                elif record.get("opinion") == "approves" and opinion != "disapproves":
                    opinion = "approves"
            if opinion == "disapproves":
                self.TotalUserDisapprovedAnalyses += 1
            elif opinion == "noopinion":
                self.TotalUserNoOpinionAnalyses += 1


def _signature_key(analysis: dict[str, Any]) -> tuple:
    """The durable signature as a hashable key: ordered identifier triples."""
    return tuple(tuple(triple) for triple in analysis.get("signature") or ())


def _fully_linked(record: dict[str, Any]) -> bool:
    """A human analysis the parser could have produced (FR-018).

    From the public per-bundle completeness flag plus the bundle count, as
    the worker recorded them -- never a reimplemented predicate (FR-038).
    """
    count = int(record.get("bundle_count") or 0)
    return count > 0 and int(record.get("complete_bundle_count") or 0) == count


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

    # -- CP3 additions (contracts/artifact.md section 3). Additive only:
    # every field above is unchanged, and a CP2b record reads back with
    # these at their defaults.

    #: The eight-field `ScopeFingerprint.to_dict()`. None for a single-word
    #: run, which has no scope.
    scope_fingerprint: Optional[dict[str, Any]] = None
    #: The engine recorded when the run was submitted. Results are labelled
    #: with this one even if the project's active parser changes later.
    engine_at_submission: Optional[str] = None
    #: A WARNING, never a refusal (FR-024): the active parser changed while
    #: the run was going.
    engine_changed_midjob: bool = False
    #: Captured at this server's own grammar load, keyed to the fingerprint
    #: and stored BESIDE it, never inside it (FR-023, D-3).
    #:
    #: CP4 (additive, FR-039): a batch's baseline also carries
    #: `eligible_entries` -- `[{"entry_guid", "headword"}]`, the entries whose
    #: forms could reach that grammar -- so a read-only run re-baselines both
    #: halves of the refuse-to-file gate. A baseline written before CP4 has no
    #: such key; the gate then compares load errors only and says so.
    load_error_baseline: Optional[dict[str, Any]] = None
    #: `HostCounters.to_dict()`, refreshed as the run progresses.
    counters: Optional[dict[str, int]] = None
    #: The divergence statements, in the artifact itself (FR-017).
    counter_divergences: Optional[list[str]] = None
    #: Relative path of the word list inside the run directory.
    words_path: Optional[str] = None
    #: `ProjectParseState.to_dict()` from the ONE probe (FR-004), read at
    #: submission. The oracle's precondition (FR-041): a batch report on a
    #: project the parser has never run against reports the oracle absent.
    #: Added after the T053 freeze, additively (contracts/artifact.md s.9).
    project_state: Optional[dict[str, Any]] = None

    # -- CP4 addition (contracts/artifact.md, CP4 amendment). Additive only.

    #: The filing section (CP4 data-model.md section 7). Present only on a run
    #: created with `apply=true`; None on every read-only run, so a CP3 reader
    #: sees the record it always did. Carries the confirmed plan, the backup
    #: outcome or the no-recovery warning, the per-outcome counts, projected
    #: beside actual deletions, and the filing `state`.
    filing: Optional[dict[str, Any]] = None

    # -- CP5 additions (CP5 data-model.md section 6.1). Additive only. They
    # MUST be declared fields: `read_meta` drops any undeclared key, and every
    # stage change rewrites the meta, so a bare dict key would vanish at the
    # first `set_stage` (research F-12) -- the same reason CP4 declared
    # `filing`.

    #: Which spine produced the run. None on every pre-CP5 record and read as
    #: "in_process" -- use `effective_spine`, never this raw value, to branch.
    spine: Optional[Spine] = None
    #: The sandbox section (data-model.md section 6.2): mode, config source,
    #: versions, generation, copy, hc outcome, advisories. Present only on a
    #: sandbox run.
    sandbox: Optional[dict[str, Any]] = None

    @property
    def effective_spine(self) -> str:
        """The run's spine, with a pre-CP5 None read as in-process (FR-037)."""
        return self.spine or SPINE_IN_PROCESS


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

    @property
    def words_path(self) -> Path:
        return self._root / _WORDS_FILENAME

    # -- lifecycle --------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        project_name: Optional[str] = None,
        words_total: int = 0,
        max_bytes: Optional[int] = None,
        record_dir: Optional[Path] = None,
        words: Optional[list[str]] = None,
        scope_fingerprint: Optional[dict[str, Any]] = None,
        engine_at_submission: Optional[str] = None,
        project_state: Optional[dict[str, Any]] = None,
        filing: Optional[dict[str, Any]] = None,
        guard: Optional[Callable[[Path], Any]] = None,
        spine: Optional[Spine] = None,
        sandbox: Optional[dict[str, Any]] = None,
    ) -> "RunRecord":
        """Mint a run id and open its record at stage `starting`.

        `words` -- a batch's resolved word list -- is written to `words.txt`
        BEFORE the first `meta.json`, so a record whose meta names a word list
        always has one. A single-word run passes none and gets no file: an
        empty `words.txt` would read as "this run resolved to no words".

        CP4: `filing` is a filing run's initial section; `guard` (see
        `append_jsonl`) vets the record's own directory before anything is
        created in it.

        CP5: `spine` and `sandbox` are a sandbox run's spine marker and
        initial section; an in-process run passes neither.
        """
        record = cls(new_run_id(), max_bytes=max_bytes, record_dir=record_dir)
        if guard is not None:
            guard(record._root)
        record._root.mkdir(parents=True, exist_ok=True)
        words_path = None
        if words is not None:
            record.write_words(words)
            words_path = _WORDS_FILENAME
        batch = scope_fingerprint is not None
        record.write_meta(
            RunMeta(
                run_id=record.run_id,
                stage=RunStage.STARTING.value,
                project_name=project_name,
                words_total=words_total,
                scope_fingerprint=scope_fingerprint,
                engine_at_submission=engine_at_submission,
                counters=HostCounters().to_dict() if batch else None,
                counter_divergences=list(COUNTER_DIVERGENCES) if batch else None,
                words_path=words_path,
                project_state=project_state,
                filing=filing,
                spine=spine,
                sandbox=sandbox,
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
        """The run's meta, or None.

        None means meta.json is missing, or it exists but still could not be
        read after a short bounded retry (`META_READ_ATTEMPTS` x
        `META_RETRY_DELAY_SECONDS`). The retry absorbs the transient sharing
        violation a virus scanner or indexer causes on Windows under load, so
        a caller that reads None as "no such run" or "pre-CP5" no longer
        misreads a briefly-locked file. A caller that must tell the two apart
        uses `read_meta_strict`.
        """
        try:
            return self.read_meta_strict()
        except MetaUnreadable:
            return None

    def read_meta_strict(self) -> Optional[RunMeta]:
        """The run's meta; None ONLY when meta.json does not exist.

        A meta.json that exists but cannot be read or parsed is retried
        briefly, then raises `MetaUnreadable`. The writers (`set_stage`,
        `set_section`) use this so an unreadable moment can never make them
        rewrite the record from a blank `RunMeta`, which would erase its
        fingerprint, sandbox and filing sections.
        """
        last_error: Optional[BaseException] = None
        for attempt in range(META_READ_ATTEMPTS):
            if not self.meta_path.is_file():
                return None
            try:
                data = json.loads(self.meta_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("meta.json does not hold a JSON object")
            except (OSError, ValueError) as exc:  # JSONDecodeError, UnicodeDecodeError
                last_error = exc
                if attempt + 1 < META_READ_ATTEMPTS:
                    time.sleep(META_RETRY_DELAY_SECONDS)
                continue
            known = {f for f in RunMeta.__dataclass_fields__}
            return RunMeta(**{k: v for k, v in data.items() if k in known})
        raise MetaUnreadable(
            f"Run {self.run_id}: meta.json exists but could not be read "
            f"after {META_READ_ATTEMPTS} attempts: {last_error}"
        ) from last_error

    def set_stage(self, stage: RunStage, **updates: Any) -> RunMeta:
        """Move the run to a stage and persist immediately."""
        meta = self.read_meta_strict() or RunMeta(
            run_id=self.run_id, stage=RunStage.STARTING.value
        )
        meta.stage = stage.value
        # `write_meta` serialises declared fields only, so an undeclared key
        # would vanish without a trace (research F-12's shape, CP5 pattern
        # audit sweep 5). Name it instead of dropping it silently.
        unknown = sorted(k for k in updates if k not in RunMeta.__dataclass_fields__)
        if unknown:
            _log.warning(
                "Run %s: meta update key(s) %s are not RunMeta fields and are "
                "not persisted; declare them on RunMeta.", self.run_id, unknown,
            )
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

    # -- CP4: a filing run's section and captures -------------------------
    #
    # Generic on purpose. The filing package owns what its artifacts are
    # called (`filing/paths.py`: `DELETIONS_RELPATH`) and passes a `guard`, a
    # callable handed a path, which raises if the path must not be written --
    # `filing.paths.assert_outside_project`, so no filing artifact ever lands
    # inside a project folder (FR-042). This module, which a standing test
    # proves never writes to a project, never imports the write spine.

    def set_section(self, **sections: Any) -> RunMeta:
        """Rewrite named meta.json sections in place (CP4: the filing section)."""
        meta = self.read_meta_strict() or RunMeta(run_id=self.run_id, stage=RunStage.STARTING.value)
        for key, value in sections.items():
            setattr(meta, key, value)
        self.write_meta(meta)
        return meta

    def _child(self, relpath: str) -> Path:
        """A path inside this run's directory, from a caller-fixed relative path."""
        rel = Path(relpath)
        # `anchor`, not only `is_absolute()`: on Windows "/etc/x" is rooted
        # but not absolute, and `root / "/etc/x"` would land on the drive root.
        if rel.is_absolute() or rel.anchor or ".." in rel.parts:
            raise ValueError(f"{relpath!r} is not a path inside the run record")
        return self._root / rel

    def append_jsonl(
        self, relpath: str, line: dict[str, Any], *,
        guard: Optional[Callable[[Path], Any]] = None,
    ) -> None:
        """Append one JSON line to a file in the record and FSYNC it.

        CP4's pre-deletion captures (FR-031) are written BEFORE the filer
        deletes the analysis they describe and are the only record of it
        afterwards -- so each line is durable before this returns, like
        `append_result`.
        """
        path = self._child(relpath)
        if guard is not None:
            guard(path)
        self._enforce_size_cap()
        payload = json.dumps(line, ensure_ascii=False)
        with _WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(payload + "\n")
                handle.flush()
                os.fsync(handle.fileno())

    def iter_jsonl(self, relpath: str) -> Iterator[dict[str, Any]]:
        """Every line of a record JSONL file; a torn trailing line is skipped."""
        path = self._child(relpath)
        if not path.is_file():
            return
        with open(path, "r", encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    yield json.loads(raw)
                except json.JSONDecodeError:
                    continue

    # -- CP5: the sandbox files ---------------------------------------------
    #
    # Every sandbox file goes through `_child` (no absolute path, no `..`)
    # and must be one of `SANDBOX_FILES`. The directory is created on first
    # write, never up front: an in-process run has no `sandbox/` at all.

    def sandbox_path(self, name: str) -> Path:
        """The path of one of `SANDBOX_FILES` inside this run's `sandbox/`."""
        if name not in SANDBOX_FILES:
            raise ValueError(
                f"{name!r} is not a sandbox run file; expected one of "
                f"{', '.join(SANDBOX_FILES)}"
            )
        return self._child(f"{SANDBOX_DIRNAME}/{name}")

    def write_sandbox_file(
        self, name: str, text: str, *,
        guard: Optional[Callable[[Path], Any]] = None,
    ) -> Path:
        """Write a sandbox file whole (UTF-8, no BOM, LF kept) and fsync it."""
        path = self.sandbox_path(name)
        if guard is not None:
            guard(path)
        self._enforce_size_cap()
        with _WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        return path

    def append_sandbox_line(
        self, name: str, line: str, *,
        guard: Optional[Callable[[Path], Any]] = None,
    ) -> None:
        """Append one line to a sandbox file and flush it (hc's streams).

        Flushed per line for the same reason results are: a killed hc run
        must leave everything it printed readable.
        """
        path = self.sandbox_path(name)
        if guard is not None:
            guard(path)
        self._enforce_size_cap()
        text = line if line.endswith("\n") else line + "\n"
        with _WRITE_LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8", newline="") as handle:
                handle.write(text)
                handle.flush()

    def read_sandbox_file(self, name: str) -> Optional[str]:
        """A sandbox file's text, or None when the run never wrote it."""
        path = self.sandbox_path(name)
        if not path.is_file():
            return None
        with open(path, "r", encoding="utf-8", newline="") as handle:
            return handle.read()

    # -- the word list ----------------------------------------------------

    def write_words(self, words: Iterable[str]) -> None:
        """Write `words.txt`: UTF-8, NFC, one word per line, in given order.

        Order is the resolved order (descending occurrence, then
        alphabetical, truncated after ordering -- scope.py), and it is kept
        exactly: a reader comparing two runs by position relies on it.
        A word containing a line break would silently become two words, so
        it is refused rather than written.
        """
        lines = []
        for word in words:
            text = unicodedata.normalize("NFC", str(word))
            if "\n" in text or "\r" in text:
                raise ValueError(f"A word may not contain a line break: {text!r}")
            lines.append(text)
        payload = "".join(line + "\n" for line in lines)
        with _WRITE_LOCK:
            self._root.mkdir(parents=True, exist_ok=True)
            with open(self.words_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())

    def read_words(self) -> Optional[list[str]]:
        """The word list, or None when this run has none (a single word)."""
        if not self.words_path.is_file():
            return None
        text = self.words_path.read_text(encoding="utf-8")
        return [line for line in text.split("\n") if line]

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
