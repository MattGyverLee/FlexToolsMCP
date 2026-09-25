#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The sandbox spine's per-run client (parser-check CP5; re-plan T102;
contracts/sandbox-worker.md; data-model 6.2-6.6; FR-011, FR-016..FR-020,
FR-023, FR-035, FR-046..FR-050).

`SandboxClient` implements the worker-client interface `ParseRunner` already
drives (`start`, `parse_word`, `cancel_run`, `is_running`, `listen_to_run`,
`stop_listening`, `terminate`, `aclose`), so a sandbox run goes through the
ONE execution path (FR-035): same record, stages, fast path, cancellation
and retention. The runner builds a FRESH client per run under
`SANDBOX_ROLE` instead of asking `WorkerPool` (F-13: the pool keys by
`(project, role)`, and two concurrent sandbox jobs need separate copies).

WHAT ONE RUN DOES

  start()       stage `loading_grammar`; for the project cache: the engine
                check (memoised in engine.py), then the cache lookup, and on
                a miss a marked copy dir `work/<run_id>/` and generation
                (`cache.ensure_entry`, logging into the run's `sandbox/`);
                on a hit the entry's log is copied with one reuse line in
                front. Then the id-map gate (an invalid sidecar is refused
                BEFORE anything is spawned), the Morpher parameters (D3), and
                one `--sandbox` parse worker for the run
                (`ParseWorkerClient` with a `SandboxSpawn`; never pooled).
  parse_word()  one word to the worker, one structured result back
                (contracts/sandbox-worker.md section 4), turned into the
                `results.jsonl` line (`classify`). A worker that dies
                mid-list without a code gives the word in flight
                `error_no_output` and every later word `not_reached`
                (FR-018): the run completes, and no word is `not_parsed`.
  finalize()    before any terminal stage (the runner calls it): stop the
                worker, keep its stderr as `worker-stderr.txt` (the
                `hc_stdout` log section) and the recorded lines rendered
                for reading as `hc-output.txt` (`hc_output`, FR-038), write
                `run.json`, fold the outcome into `meta.sandbox.worker`,
                reconcile the running tally, delete the copy. Idempotent.
  cancel_run()  kills the worker's tree; results already recorded stay.

THE WATCHDOG (FR-020). The worker has no timeout of its own: this client
holds a wall-clock watchdog of `timeout_seconds` around the run and, on
expiry, kills the worker's process tree. The word in flight is named
(`in_flight_index`) and the run ends as `parser_timeout`; every word
completed before the kill is already recorded.

THREE-WAY DELETION (R-11). Generation's script deletes its copy in
`finally`, but a tree kill skips that; so this client deletes
`work/<run_id>/` itself, right after generation and again (idempotently) in
`finalize` / `aclose`. The startup sweep is the third way.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple, Union

from ..parse.worker_client import (
    ParseWorkerClient,
    SandboxSpawn,
    WorkerError,
    WorkerStartupError,
)
from . import cache, classify, engine, lcm_ids, script, workdir

__all__ = [
    "SANDBOX_ROLE",
    "DEFAULT_TIMEOUT_SECONDS",
    "COUNTERS_OK",
    "COUNTERS_UNAVAILABLE",
    "COUNTERS_UNAVAILABLE_TIMEOUT",
    "PARAMETERS_SOURCES",
    "SandboxLaunch",
    "SandboxRunError",
    "SandboxClient",
    "render_results",
]

_log = logging.getLogger(__name__)

#: The runner's worker role for this spine (R-07). Never a pool key.
SANDBOX_ROLE = "sandbox"

DEFAULT_TIMEOUT_SECONDS = 600

#: `meta.sandbox.worker.counters` (data-model 6.2). `unavailable` is for a
#: run that ended before its tally could be reconciled (a crash, a cancel).
COUNTERS_OK = "ok"
COUNTERS_UNAVAILABLE_TIMEOUT = "unavailable_timeout"
COUNTERS_UNAVAILABLE = "unavailable"

MODE_PARSE = "parse"
MODE_TEST = "test"

ADVISORY_GRAMMAR_LOAD_ERRORS = "grammar_load_errors"
#: contracts/tools.md section 5.1: a config source older than the sidecar.
ADVISORY_SHAPING_NOT_APPLIED = "shaping_not_applied"

#: FR-047's three parameter sources, in priority order.
PARAMETERS_CACHE = "cache"
PARAMETERS_LIVE_PROJECT = "live_project"
PARAMETERS_FLEX_DEFAULTS = "flex_defaults"
PARAMETERS_SOURCES = (PARAMETERS_CACHE, PARAMETERS_LIVE_PROJECT, PARAMETERS_FLEX_DEFAULTS)

_GEN_LOG = cache.LOG_NAME
_STDERR = "worker-stderr.txt"
_OUTPUT = "hc-output.txt"
#: How long a worker whose channel failed gets to exit before it is judged
#: alive (one word refused) rather than dead (the rest not reached).
_EXIT_GRACE_SECONDS = 2.0
_PARAMS = "hc-params.json"

PathLike = Union[str, Path]


# ---------------------------------------------------------------------------
# Inputs and errors
# ---------------------------------------------------------------------------


#: Keys `SandboxLaunch.from_value` accepts beyond its fields.
_LAUNCH_ALIASES = frozenset({"corpus_path"})


@dataclass
class SandboxLaunch:
    """What the client needs to run: everything the handler resolved.

    `config_path` None means the project cache (engine check, generation on
    a miss); a path is a named sandbox's `hc-config.xml`, used as it is.
    `engine_dir` is the FieldWorks folder holding the bundled HermitCrab DLL
    (D6/D7); None lets the worker find the standard install itself.
    `worker_stub` starts the worker as `--stub --sandbox` (tests only).
    """

    fwdata_path: str
    generate_hc_config_path: Optional[str] = None
    config_path: Optional[str] = None
    #: A named sandbox's name (the store's key for its sidecar and origin).
    sandbox_name: Optional[str] = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    generate_timeout_seconds: int = cache.DEFAULT_GENERATE_TIMEOUT_SECONDS
    check_engine: bool = True
    active_parser: Optional[str] = "HC"
    versions: Optional[Dict[str, Any]] = None
    engine_dir: Optional[str] = None
    #: Test mode (US4): the corpus JSON (data-model section 5), already
    #: validated by the handler. `corpus_path` is accepted as an alias.
    assertion_file: Optional[str] = None
    #: FR-047 source 2 for a named sandbox (T115): the project `origin.json`
    #: records, and its `.fwdata` when that project still resolves. Either
    #: None -> FLEx's defaults, with a note saying which.
    origin_project: Optional[str] = None
    origin_fwdata_path: Optional[str] = None
    worker_stub: bool = False
    worker_parse_delay: float = 0.0

    @property
    def mode(self) -> str:
        return MODE_TEST if self.assertion_file else MODE_PARSE

    @property
    def named(self) -> bool:
        return bool(self.config_path)

    @classmethod
    def from_value(cls, value: Union["SandboxLaunch", Mapping[str, Any]]) -> "SandboxLaunch":
        """A `SandboxLaunch` from itself or the handler's dict.

        Unknown keys are ignored, and named in a WARNING so a key the
        handler adds but this class does not declare is not dropped
        silently (pattern audit sweep 5); a None value takes the default.
        """
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise TypeError("sandbox_launch must be a SandboxLaunch or a mapping")
        names = {f.name for f in fields(cls)}
        unknown = sorted(str(k) for k in value if k not in names and k not in _LAUNCH_ALIASES)
        if unknown:
            _log.warning("sandbox_launch: ignoring undeclared keys: %s", ", ".join(unknown))
        kwargs = {k: v for k, v in value.items() if k in names and v is not None}
        if "assertion_file" not in kwargs and value.get("corpus_path"):
            kwargs["assertion_file"] = value["corpus_path"]
        if not kwargs.get("fwdata_path"):
            raise ValueError("sandbox_launch lacks fwdata_path")
        return cls(**kwargs)


class SandboxRunError(WorkerError):
    """A terminal sandbox failure, for the runner to map (T051).

    `error_code` is `parser_timeout`, `parser_job_failed`,
    `parser_config_failed`, `parser_engine_mismatch`, or None for a stop the
    runner already asked for (a cancel). `facts` carries what the runner
    needs to build the detail (`timeout_seconds`, `in_flight_index`,
    `failure`, `log_path`); `detail`, when set, is already the response
    model's dict.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: Optional[str] = None,
        facts: Optional[Dict[str, Any]] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.facts = dict(facts or {})
        if detail is not None:
            self.detail = detail


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------


class SandboxClient:
    """One sandbox run: one config, one `--sandbox` worker process."""

    def __init__(
        self,
        project_name: str,
        *,
        run_id: str,
        record: Any,
        wordforms: List[str],
        launch: Union[SandboxLaunch, Mapping[str, Any]],
    ) -> None:
        self.project_name = project_name
        self.run_id = run_id
        self._record = record
        self._wordforms = list(wordforms)
        self._launch = SandboxLaunch.from_value(launch)
        self._sandbox_dir = Path(record.sandbox_path(script.RUN_JSON)).parent
        self._listeners: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._mode = self._launch.mode

        self._worker: Optional[ParseWorkerClient] = None
        self._stderr_lines: List[str] = []
        self._launched_at: Optional[float] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._gen_task: Optional[asyncio.Future] = None
        self._work_dir: Optional[Path] = None
        self._copy_bytes = 0
        self._copy_result: Optional[workdir.CleanupResult] = None
        self._entry: Optional[cache.CacheEntry] = None

        #: Each recorded line, in order (parse or assertion lines).
        self._results: List[Dict[str, Any]] = []
        #: The running tally, kept as words are classified and reconciled
        #: against the recorded lines at the end (data-model 6.6).
        self._running: Dict[str, int] = {}
        #: Test mode: each assertion's `expected`, by assertion index.
        self._expected: List[Any] = []
        #: The worker's `load_baseline` for this run (sandbox-worker.md 5).
        self._baseline: Optional[Dict[str, Any]] = None
        self._id_map_state = "absent"

        self._started = False
        self._cancelled = False
        self._killed = False
        self._watchdog_fired = False
        self._finalized = False
        self._closed = False
        #: The worker died mid-list with no code (FR-018): later words are
        #: answered `not_reached` without a worker.
        self._crashed = False
        self._in_flight_index: Optional[int] = None

    # -- the worker-client interface ----------------------------------------

    @property
    def pid(self) -> Optional[int]:
        return self._worker.pid if self._worker is not None else None

    @property
    def worker_pid(self) -> Optional[int]:
        return self._worker.worker_pid if self._worker is not None else None

    @property
    def launch(self) -> SandboxLaunch:
        return self._launch

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.is_running()

    def listen_to_run(self, run_id: str, listener: Callable[[Dict[str, Any]], None]) -> None:
        self._listeners[run_id] = listener

    def stop_listening(self, run_id: str) -> None:
        self._listeners.pop(run_id, None)

    def _emit(self, message: Dict[str, Any]) -> None:
        listener = self._listeners.get(self.run_id)
        if listener is not None:
            with contextlib.suppress(Exception):
                listener(message)

    async def start(self) -> None:
        """Resolve the config (generating it on a miss) and start the worker."""
        if self._started:
            return
        self._started = True
        self._emit({"type": "stage", "stage": "loading_grammar"})
        self._sandbox_dir.mkdir(parents=True, exist_ok=True)
        if self._mode == MODE_TEST:
            self._expected = self._load_expected()

        config = await self._resolve_config()
        if self._cancelled:
            raise SandboxRunError("The sandbox run was cancelled before the parser started.")

        # The check order's id-map gate (contracts/tools.md section 3): an
        # invalid sidecar is refused here, before any worker exists.
        id_map = self._resolve_id_map()
        parameters, source, note = self._resolve_parameters()
        params_path = self._record.write_sandbox_file(
            _PARAMS, json.dumps(parameters, indent=2, sort_keys=True) + "\n")
        self._update_sandbox(
            parser_parameters=parameters,
            parameters_source=source,
            parameters_note=note,
            shaping={"applied": id_map is not None, "id_map": self._id_map_state},
            advisories=[] if id_map is not None else [ADVISORY_SHAPING_NOT_APPLIED],
        )

        spawn = SandboxSpawn(
            config=str(config),
            hc_params=str(params_path),
            id_map=str(id_map) if id_map is not None else None,
            engine_dir=self._launch.engine_dir,
            project=self.project_name,
            named_sandbox=self._launch.named,
        )
        worker = ParseWorkerClient(
            self.project_name,
            stub=self._launch.worker_stub,
            parse_delay=self._launch.worker_parse_delay,
            sandbox=spawn,
            stderr_sink=self._stderr_lines.append,
        )
        worker.listen_to_run(self.run_id, self._on_worker_message)
        try:
            await worker.start()
        except WorkerStartupError as exc:
            raise SandboxRunError(
                f"The sandbox parse worker did not start: {exc}",
                error_code="parser_job_failed",
                facts={"failure": "crashed", "log_path": str(self._sandbox_dir / _STDERR)},
            ) from exc
        self._worker = worker
        self._launched_at = time.monotonic()
        self._watchdog_task = asyncio.ensure_future(self._watchdog())

    async def parse_word(
        self,
        *,
        request_id: str = "",
        run_id: str = "",
        wordform: str,
        index_in_run: int = 0,
        **_ignored: Any,
    ) -> Dict[str, Any]:
        """This word's `results.jsonl` parse section (data-model 6.4/6.5)."""
        index = int(index_in_run)
        if self._crashed:
            return self._placeholder(index, wordform, classify.OUTCOME_NOT_REACHED)
        if self._worker is None:
            raise SandboxRunError("The sandbox parse worker is not running.",
                                  error_code="parser_job_failed",
                                  facts={"failure": "crashed",
                                         "log_path": str(self._sandbox_dir / _STDERR)})
        if self._watchdog_fired:
            raise self._timeout_error(index)
        self._in_flight_index = index
        try:
            result = await self._worker.parse_word(
                request_id=request_id or f"{self.run_id}:{index}",
                run_id=self.run_id,
                wordform=wordform,
                level="batch",
                index_in_run=index,
            )
        except (WorkerError, ConnectionError, EOFError) as exc:
            # A worker that dies mid-word surfaces as a closed channel or a
            # lost pipe, often before its process is reaped: give it a
            # moment to exit, so "died" and "refused one word" differ.
            await self._settle()
            failure = self._word_failure(exc, index)
            if failure is not None:
                raise failure from exc
            # No code: this word got no output, whether the worker died or
            # threw on it; a dead worker also leaves the rest unreached.
            self._crashed = self._worker_lost(exc)
            return self._placeholder(index, wordform, classify.OUTCOME_ERROR_NO_OUTPUT)
        self._in_flight_index = None

        parse = result.get("parse")
        if self._mode == MODE_TEST:
            expected = self._expected[index] if index < len(self._expected) else []
            line = classify.assertion_to_line(index, wordform, expected, parse)
            self._count(line["assertion"]["classification"],
                        line["assertion"].get("error_reason"))
            self._results.append(line)
            return {"parse": line["parse"], "assertion": line["assertion"]}
        line = classify.worker_parse_to_line(index, wordform, parse)
        self._count(line["parse"]["outcome"])
        self._results.append(line)
        return {"parse": line["parse"]}

    def _placeholder(self, index: int, wordform: str, outcome: str) -> Dict[str, Any]:
        """A recorded line for a word the engine never answered (FR-018)."""
        if self._mode == MODE_TEST:
            expected = self._expected[index] if index < len(self._expected) else []
            line = classify.assertion_to_line(index, wordform, expected, None, outcome=outcome)
            self._count(line["assertion"]["classification"],
                        line["assertion"].get("error_reason"))
            self._results.append(line)
            return {"parse": line["parse"], "assertion": line["assertion"]}
        line = classify.placeholder_line(index, wordform, outcome)
        self._count(line["parse"]["outcome"])
        self._results.append(line)
        return {"parse": line["parse"]}

    def _count(self, key: str, reason: Optional[str] = None) -> None:
        self._running[key] = self._running.get(key, 0) + 1
        if reason == classify.OUTCOME_INVALID_SEGMENT:
            self._running[reason] = self._running.get(reason, 0) + 1

    def _word_failure(self, exc: Exception, index: int) -> Optional[Exception]:
        """What a failed word means for the run: a terminal error, or None.

        None is a word with no output (FR-018): the worker threw on it or
        died under it with no code; `parse_word` records the placeholder.
        """
        if self._watchdog_fired:
            return self._timeout_error(index)
        if self._cancelled:
            return SandboxRunError("The sandbox run was cancelled; the parser was stopped.")
        self._in_flight_index = None
        detail = getattr(exc, "detail", None)
        if getattr(exc, "error_code", None) == "parser_job_failed":
            failure = (detail or {}).get("failure") or "crashed"
            # The load exception's text belongs in the diagnostics the
            # `hc_stdout` section serves (contracts/tools.md section 7).
            self._stderr_lines.append("Sandbox job failed (%s): %s" % (failure, exc))
            if failure == "id_map_invalid":
                self._id_map_state = "invalid"
                self._update_sandbox(shaping={"applied": False, "id_map": "invalid"})
            return SandboxRunError(
                str(exc), error_code="parser_job_failed",
                facts={"failure": failure, "log_path": str(self._sandbox_dir / _STDERR)},
            )
        if self._worker_lost(exc):
            self._stderr_lines.append(
                "The sandbox parse worker stopped while parsing word %d: %s" % (index + 1, exc))
        return None

    async def _settle(self, seconds: float = _EXIT_GRACE_SECONDS) -> None:
        """Wait (bounded) for a worker whose channel just failed to exit."""
        deadline = time.monotonic() + seconds
        while (self._worker is not None and self._worker.is_running()
               and time.monotonic() < deadline):
            await asyncio.sleep(0.05)

    def _worker_lost(self, exc: Exception) -> bool:
        """The worker is gone: a lost pipe (the process may not be reaped
        yet, so `is_running` can still say True), or a process that exited."""
        if isinstance(exc, (ConnectionError, EOFError)):
            return True
        return self._worker is None or not self._worker.is_running()

    def _timeout_error(self, index: Optional[int]) -> SandboxRunError:
        in_flight = self._in_flight_index if self._in_flight_index is not None else index
        self._in_flight_index = in_flight
        return SandboxRunError(
            "The sandbox parse did not finish within its timeout and was stopped.",
            error_code="parser_timeout",
            facts={"timeout_seconds": int(self._launch.timeout_seconds),
                   "in_flight_index": in_flight,
                   "words_total": len(self._wordforms)},
        )

    def _on_worker_message(self, message: Dict[str, Any]) -> None:
        kind = message.get("type")
        if kind == "load_baseline":
            self._baseline = dict(message.get("baseline") or {})
            self._fold_baseline()
        elif kind == "stage":
            self._emit({"type": "stage", "stage": message.get("stage")})

    def _fold_baseline(self) -> None:
        """The worker's engine facts into `meta.sandbox` (sandbox-worker.md 5)."""
        baseline = self._baseline or {}
        updates: Dict[str, Any] = {
            "parameters_applied": list(baseline.get("parameters_applied") or []),
            "engine_version": baseline.get("engine_version"),
        }
        errors = list(baseline.get("errors") or [])
        if errors:
            generation = self._section().get("generation") or {}
            loaded = [{"kind": "engine_load", "line": _load_error_line(e)} for e in errors]
            updates["generation"] = {
                "engine_load_errors": loaded,
                "load_error_count": int(generation.get("load_error_count") or 0) + len(loaded),
            }
            updates["advisories"] = [ADVISORY_GRAMMAR_LOAD_ERRORS]
        self._update_sandbox(**updates)

    def _load_expected(self) -> List[Any]:
        """Each assertion's `expected`, in corpus order (data-model section 5)."""
        try:
            data = json.loads(Path(self._launch.assertion_file).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise SandboxRunError(
                "The corpus file could not be read: %s" % type(exc).__name__,
                error_code="parser_job_failed",
                facts={"failure": "crashed", "log_path": str(self._launch.assertion_file)},
            ) from exc
        assertions = data.get("assertions") if isinstance(data, dict) else None
        return [a.get("expected") or [] if isinstance(a, dict) else []
                for a in (assertions or [])]

    async def cancel_run(self, run_id: str = "") -> None:
        """Stop now: cancel generation, or kill the worker's tree."""
        self._cancelled = True
        if self._gen_task is not None and not self._gen_task.done():
            self._gen_task.cancel()
        await self._kill()

    async def terminate(self) -> None:
        await self.cancel_run(self.run_id)

    async def finalize(self) -> None:
        """Fold the run's outcome into the record and delete the copy. Idempotent."""
        if self._finalized:
            return
        self._finalized = True
        try:
            if self._gen_task is not None and not self._gen_task.done():
                self._gen_task.cancel()
            self._stop_watchdog()
            if self._worker is not None:
                await self._worker.aclose()
            if self._worker is not None or self._stderr_lines:
                self._write_stderr()
            if self._results:
                self._write_output()
            if self._worker is not None:
                self._fold_outcome()
        finally:
            self._delete_copy()

    async def aclose(self) -> None:
        """Make sure nothing outlives the run: the process, the watchdog, the copy."""
        if self._closed:
            return
        self._closed = True
        if self._gen_task is not None and not self._gen_task.done():
            self._gen_task.cancel()
        if self._worker is not None:
            with contextlib.suppress(Exception):
                await self._worker.aclose()
        self._stop_watchdog()
        self._delete_copy()
        self._release_entry()

    # -- the config ---------------------------------------------------------

    async def _resolve_config(self) -> Path:
        launch = self._launch
        if launch.config_path:
            self._write_named_log(Path(launch.config_path))
            self._update_sandbox(
                copy={"bytes": 0, "cleanup": workdir.CLEANUP_NOT_MADE, "path_if_failed": None},
                versions=self._file_versions(),
            )
            return Path(launch.config_path)

        if not launch.generate_hc_config_path:
            raise SandboxRunError(
                "The project cache needs GenerateHCConfig.exe, and none was given.",
                error_code="parser_job_failed",
                facts={"failure": "crashed", "log_path": str(self._sandbox_dir)},
            )
        if launch.check_engine:
            from .. import parser_probe

            try:
                engine.check_engine(launch.fwdata_path)
            except parser_probe.ParserEngineMismatchError as exc:
                raise SandboxRunError(
                    str(exc) or "The project's parser is not HermitCrab.",
                    error_code="parser_engine_mismatch",
                    detail=dict(exc.detail),
                ) from exc

        versions = self._file_versions()
        inputs = cache.key_inputs(launch.fwdata_path, launch.generate_hc_config_path)
        key = cache.compute_key(inputs)
        entry = cache.lookup(self.project_name, key)
        if entry is not None:
            self._acquire(entry)
        if entry is None:
            with contextlib.suppress(Exception):
                self._copy_bytes = workdir.measure_allowlist(launch.fwdata_path).total_bytes
            self._work_dir = workdir.create(self.run_id, source_fwdata=launch.fwdata_path)
            try:
                self._gen_task = asyncio.ensure_future(cache.ensure_entry(
                    self.project_name,
                    launch.fwdata_path,
                    launch.generate_hc_config_path,
                    work_dir=self._work_dir,
                    run_id=self.run_id,
                    log_dir=self._sandbox_dir,
                    active_parser=launch.active_parser,
                    versions=versions,
                    timeout_seconds=int(launch.generate_timeout_seconds),
                ))
                entry = await self._gen_task
                self._acquire(entry)  # no await since ensure_entry returned
            except cache.ParserConfigFailed as exc:
                detail = exc.detail.model_dump() if hasattr(exc.detail, "model_dump") else dict(exc.detail)
                if detail.get("run_id") is None:
                    detail["run_id"] = self.run_id
                raise SandboxRunError(
                    "GenerateHCConfig could not export the grammar.",
                    error_code="parser_config_failed",
                    detail=detail,
                ) from exc
            except asyncio.CancelledError:
                if not self._cancelled:
                    raise
                raise SandboxRunError(
                    "The sandbox run was cancelled during generation."
                ) from None
            finally:
                self._gen_task = None
                self._delete_copy()
        else:
            self._update_sandbox(
                copy={"bytes": 0, "cleanup": workdir.CLEANUP_NOT_MADE, "path_if_failed": None})

        # Prune AFTER acquiring: this run's entry is in use, so it is spared.
        with contextlib.suppress(Exception):
            cache.prune(self.project_name)
        if not entry.built:
            self._write_reuse_log(entry)
        advisories = [ADVISORY_GRAMMAR_LOAD_ERRORS] if entry.load_error_count else []
        self._update_sandbox(
            config_source={"kind": "project_cache", "cache_key": entry.key},
            generation={
                "reused_cache": not entry.built,
                "cache_key": entry.key,
                "load_error_count": entry.load_error_count,
                "load_errors": entry.load_errors,
            },
            versions=versions,
            advisories=advisories,
        )
        return entry.config_path

    def _resolve_id_map(self) -> Optional[Path]:
        """The config source's validated sidecar, or None when it has none.

        An entry or sandbox whose sidecar is recorded -- or found -- invalid
        is refused with `parser_job_failed`/`id_map_invalid` BEFORE a worker
        is spawned (spec FR-050, "Who refuses an invalid map"). An existing
        but invalid sidecar is never treated as absent.
        """
        if self._launch.named:
            from . import store

            path = store.sandbox_lcm_ids_path(self.project_name, self._launch.sandbox_name) \
                if self._launch.sandbox_name else None
            if path is None:
                sibling = Path(self._launch.config_path).parent / lcm_ids.LCM_IDS_NAME
                path = sibling if sibling.exists() else None
        else:
            path = self._entry.lcm_ids_path if self._entry is not None else None
        if path is None:
            self._id_map_state = "absent"
            return None
        document = lcm_ids.read(path)
        if document is None or document.get("valid") is not True:
            self._id_map_state = "invalid"
            self._update_sandbox(shaping={"applied": False, "id_map": "invalid"})
            invalid = (document or {}).get("invalid_ids") or []
            reason = ((document or {}).get("error")
                      or ("unresolved ids: %s" % invalid if invalid else "unreadable"))
            raise SandboxRunError(
                "The configuration's id map (lcm-ids.json) failed validation (%s), so "
                "Try A Word's shaping cannot be applied safely." % reason,
                error_code="parser_job_failed",
                facts={"failure": "id_map_invalid", "log_path": str(path)},
            )
        self._id_map_state = "valid"
        return Path(path)

    def _resolve_parameters(self) -> Tuple[Dict[str, Any], str, Optional[str]]:
        """FR-047 / D3: the Morpher parameters, their source, and why.

        1. a cache entry's `hc_parameters` (read at generation time);
        2. a live stream read of the project's `.fwdata`: for a named sandbox,
           its originating project (T115); for an old cache entry with no
           recorded parameters, the project itself;
        3. FLEx's defaults.
        """
        defaults = dict(engine.HC_PARAMETER_DEFAULTS)
        if not self._launch.named and self._entry is not None:
            recorded = self._entry.hc_parameters
            if isinstance(recorded, dict):
                return {**defaults, **recorded}, PARAMETERS_CACHE, None
        fwdata = (self._launch.origin_fwdata_path if self._launch.named
                  else self._launch.fwdata_path)
        if not fwdata:
            origin = self._launch.origin_project
            why = ("This sandbox records no originating project" if not origin
                   else "This sandbox's originating project, %s, no longer resolves" % origin)
            return defaults, PARAMETERS_FLEX_DEFAULTS, why + ", so FLEx's own defaults apply."
        reading = engine.read_parameters(fwdata)
        if reading is not None:
            return {**defaults, **reading}, PARAMETERS_LIVE_PROJECT, None
        return defaults, PARAMETERS_FLEX_DEFAULTS, (
            "The project's parser parameters could not be read, so FLEx's own "
            "defaults apply.")

    def _acquire(self, entry: cache.CacheEntry) -> None:
        """Hold the entry for this run (prune spares it); released in aclose."""
        if self._entry is None:
            cache.acquire(entry)
            self._entry = entry

    def _release_entry(self) -> None:
        entry, self._entry = self._entry, None
        if entry is not None:
            with contextlib.suppress(Exception):
                cache.release(entry)

    def _file_versions(self) -> Dict[str, Any]:
        """FieldWorks' HermitCrab and GenerateHCConfig versions (FR-005)."""
        from .. import parser_probe

        generator = self._launch.generate_hc_config_path
        out: Dict[str, Any] = {}
        if generator:
            gen = Path(generator)
            out["generate_hc_config"] = parser_probe.read_file_version(gen)
            out["fieldworks_hermitcrab"] = parser_probe.read_file_version(
                gen.parent / parser_probe.FIELDWORKS_HERMITCRAB_DLL)
        for key, value in (self._launch.versions or {}).items():
            if value is not None:
                out[key] = value
        return out

    def _write_reuse_log(self, entry: cache.CacheEntry) -> None:
        try:
            body = entry.log_path.read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            body = ""
        created = entry.meta.get("created_at") or "an earlier run"
        head = ("Reused cached HC configuration %s (generated %s); no generation ran "
                "for this run.\n" % (entry.key, created))
        self._record.write_sandbox_file(_GEN_LOG, head + body)

    def _write_named_log(self, config: Path) -> None:
        head = ("No generation ran for this run: it used a named sandbox's "
                "configuration, %s, exactly as it is.\n" % config)
        body = ""
        with contextlib.suppress(OSError):
            body = (config.parent / _GEN_LOG).read_text(encoding="utf-8-sig", errors="replace")
        self._record.write_sandbox_file(_GEN_LOG, head + body)

    # -- the copy -----------------------------------------------------------

    def _delete_copy(self) -> None:
        if self._work_dir is None or self._copy_result is not None:
            return
        try:
            result = workdir.delete(self._work_dir)
        except Exception as exc:  # noqa: BLE001 -- recorded, the sweep retries
            _log.warning("Could not delete sandbox copy %s: %s", self._work_dir, exc)
            result = workdir.CleanupResult(workdir.CLEANUP_FAILED, str(self._work_dir), 0)
        self._copy_result = result
        copy = {"bytes": self._copy_bytes}
        copy.update(result.as_dict())
        with contextlib.suppress(Exception):
            self._update_sandbox(copy=copy)

    # -- the worker process -------------------------------------------------

    async def _watchdog(self) -> None:
        """FR-020: the run's wall-clock bound; the worker has none of its own."""
        try:
            await asyncio.sleep(float(self._launch.timeout_seconds))
        except asyncio.CancelledError:
            return
        if self._worker is not None and self._worker.is_running() and not self._finalized:
            _log.warning("Sandbox run %s outlived its %ss timeout; killing its worker.",
                         self.run_id, self._launch.timeout_seconds)
            self._watchdog_fired = True
            await self._kill()

    def _stop_watchdog(self) -> None:
        task = self._watchdog_task
        if task is not None and not task.done():
            task.cancel()

    async def _kill(self) -> None:
        worker = self._worker
        if worker is None or not worker.is_running():
            return
        self._killed = True
        await worker.terminate()

    # -- the record ---------------------------------------------------------

    def _section(self) -> Dict[str, Any]:
        with contextlib.suppress(Exception):
            meta = self._record.read_meta()
            return dict((meta.sandbox if meta is not None else None) or {})
        return {}

    def _update_sandbox(self, **updates: Any) -> None:
        """Merge into `meta.sandbox`: dicts merge, advisories union, rest replace.

        The read is strict (pattern audit sweep 6): a meta.json that stays
        unreadable skips THIS update, logged, rather than merging into `{}`
        and writing back a section that would erase the recorded one.
        """
        from ..parse.record import MetaUnreadable

        try:
            meta = self._record.read_meta_strict()
        except MetaUnreadable as exc:
            _log.warning("Run %s: meta.sandbox update %s skipped: %s",
                         self.run_id, sorted(updates), exc)
            return
        section = dict((meta.sandbox if meta is not None else None) or {})
        for key, value in updates.items():
            if key == "advisories":
                merged = list(section.get("advisories") or [])
                for code in value or []:
                    if code not in merged:
                        merged.append(code)
                section["advisories"] = merged
            elif isinstance(value, dict) and isinstance(section.get(key), dict):
                combined = dict(section[key])
                combined.update(value)
                section[key] = combined
            else:
                section[key] = value
        try:
            self._record.set_section(sandbox=section)
        except MetaUnreadable as exc:
            _log.warning("Run %s: meta.sandbox update %s skipped: %s",
                         self.run_id, sorted(updates), exc)

    def _write_stderr(self) -> None:
        with contextlib.suppress(Exception):
            text = "\n".join(self._stderr_lines)
            self._record.write_sandbox_file(_STDERR, text + ("\n" if text else ""))

    def _write_output(self) -> None:
        """The recorded lines rendered for reading: the `hc_output` section."""
        with contextlib.suppress(Exception):
            self._record.write_sandbox_file(_OUTPUT, render_results(self._results))

    def _fold_outcome(self) -> None:
        """The worker's outcome into `meta.sandbox.worker` and `run.json`."""
        in_flight = self._in_flight_index if (self._watchdog_fired or self._cancelled) else None
        in_flight_word = None
        if in_flight is not None and 0 <= in_flight < len(self._wordforms):
            in_flight_word = self._wordforms[in_flight]

        divergences: List[str] = []
        agreement: Optional[bool] = None
        engine_counters: Optional[Dict[str, int]] = None
        if self._watchdog_fired:
            counters_state = COUNTERS_UNAVAILABLE_TIMEOUT
        elif self._cancelled:
            counters_state = COUNTERS_UNAVAILABLE
        else:
            counters_state = COUNTERS_OK
            if self._mode == MODE_TEST:
                counters = classify.test_counters_from(self._running)
                found = classify.reconcile_test_counters(self._results, counters)
            else:
                counters = classify.parse_counters_from(self._running)
                found = classify.reconcile_parse_counters(self._results, counters)
            engine_counters = counters.to_dict()
            divergences = [d.text for d in found]
            agreement = not divergences

        duration = None
        if self._launched_at is not None:
            duration = int((time.monotonic() - self._launched_at) * 1000)
        exit_code = self._worker.exit_code if self._worker is not None else None
        worker_section = {
            "exit_code": exit_code,
            "timed_out": self._watchdog_fired,
            "killed": self._killed,
            "in_flight_index": in_flight,
            "in_flight_word": in_flight_word,
            "duration_ms": duration,
            "counters": counters_state,
            "engine_counters": engine_counters,
            "counter_agreement": agreement,
        }
        baseline = self._baseline or {}
        with contextlib.suppress(Exception):
            self._record.write_sandbox_file(script.RUN_JSON, json.dumps({
                "worker": worker_section,
                "engine_version": baseline.get("engine_version"),
                "parameters_applied": baseline.get("parameters_applied"),
                "id_map": self._id_map_state,
            }, indent=2) + "\n")
        self._update_sandbox(worker=worker_section)
        if divergences:
            meta = self._record.read_meta()
            existing = list((meta.counter_divergences if meta is not None else None) or [])
            self._record.set_section(counter_divergences=existing + divergences)


def _render_morphs(morphs: List[Mapping[str, Any]]) -> str:
    parts = []
    for morph in morphs:
        marks = "".join(mark for flag, mark in (("guessed", "?"), ("is_circumfix", "~"),
                                                  ("user_added", "+"))
                        if morph.get(flag))
        parts.append("%s %s%s" % (morph.get("form"), morph.get("gloss"), marks))
    return "  ".join(parts)


def render_results(lines: List[Mapping[str, Any]]) -> str:
    """Recorded parse or assertion lines as text (FR-038's `hc_output`).

    One block per word, in order: `[n] word: outcome`, then one indented
    line per analysis (`form gloss` pairs; `?` guessed, `~` circumfix,
    `+` user-added). An assertion line adds its classification and the
    missing/unexpected parses. For reading only -- never parsed back.
    """
    out: List[str] = []
    for line in lines:
        parse = line.get("parse") or {}
        head = "[%d] %s: %s" % (int(line.get("index", 0)) + 1, line.get("wordform"),
                                parse.get("outcome"))
        if parse.get("position") is not None:
            head += " at position %s" % parse["position"]
        if parse.get("error_message"):
            head += " (%s)" % parse["error_message"]
        assertion = line.get("assertion")
        if assertion:
            head += " -> %s" % assertion.get("classification")
            if assertion.get("error_reason"):
                head += " (%s)" % assertion["error_reason"]
        out.append(head)
        if assertion:
            for label in ("missing", "unexpected"):
                for pairs in assertion.get(label) or []:
                    out.append("    %s: %s" % (label, _render_morphs(pairs)))
        else:
            for analysis in parse.get("analyses") or []:
                out.append("    " + _render_morphs(analysis.get("morphs") or []))
    return "\n".join(out) + ("\n" if out else "")


def _load_error_line(error: Mapping[str, Any]) -> str:
    """One loader callback as one line: `<type> (<id>): <message>`."""
    kind = error.get("type") or "Error"
    ident = error.get("id")
    where = f" ({ident})" if ident else ""
    return f"{kind}{where}: {error.get('message') or ''}".strip()
