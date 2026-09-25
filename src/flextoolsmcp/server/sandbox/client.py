#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The sandbox spine's per-run client (parser-check CP5, research R-06, R-07,
R-11, F-13; data-model 6.2-6.6; FR-011, FR-016..FR-020, FR-023, FR-035).

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
                front. Then `-Mode Parse` is launched for the WHOLE list as
                one subprocess: stdin, stdout and stderr all DEVNULL.
  parse_word()  a word dispatch.json marked unsent is `not_expressible` at
                once; any other word awaits its block, tailed from
                `sandbox/hc-stdout.txt` every `POLL_INTERVAL_SECONDS` through
                `hc_output.BlockReader`. After the script exits: a word with
                a block gets it (an incomplete block is `error_no_output`), a
                word with none is `not_reached`; unless the run timed out, was
                cancelled, or hc failed to start -- those raise
                `SandboxRunError` for the runner to map.
  finalize()    before any terminal stage (the runner calls it): wait for the
                script (bounded by the watchdog), write `hc-output.txt`
                (hc-stdout minus the load banner), fold `run.json` into
                `meta.sandbox`, reconcile `stats -p` with the per-word tally
                into `counter_divergences`, delete the copy. Idempotent.
  cancel_run()  kills the PowerShell tree (`_kill_process_tree`), which takes
                hc with it; results already streamed stay recorded.

THE HAND-OFF IS A FILE (FR-023). Nothing here reads the script's console:
its streams go to DEVNULL, and data comes only from `run.json`,
`dispatch.json` and `hc-stdout.txt`. `tests/test_sandbox_client.py` checks
this over this module's AST.

THREE-WAY DELETION (R-11). The script deletes its copy in `finally`, but a
tree kill skips that; so this client deletes `work/<run_id>/` itself, right
after generation and again (idempotently) in `finalize` / `aclose`, whether
the script exited or was killed. The startup sweep is the third way.

THE WATCHDOG. `TimeoutSeconds + WATCHDOG_GRACE_SECONDS` after launch the
script's tree is killed if it is still running: a backstop for a script
that fails to enforce its own timeout. It ends the run as `parser_timeout`.

WORD FILE (decision). The runner writes `words.txt` for every batch run
(`RunRecord.create`), and it is passed as `-WordFile`; for a non-batch run
the client writes it through `RunRecord.write_words`. No other word file is
created -- `sandbox/` holds exactly `record.SANDBOX_FILES`.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import logging
import sys
import time
import unicodedata
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

from ..parse.worker_client import WorkerError
from . import cache, classify, engine, hc_output, script, workdir

__all__ = [
    "SANDBOX_ROLE",
    "POLL_INTERVAL_SECONDS",
    "WATCHDOG_GRACE_SECONDS",
    "DEFAULT_TIMEOUT_SECONDS",
    "COUNTERS_OK",
    "COUNTERS_UNAVAILABLE",
    "COUNTERS_UNAVAILABLE_TIMEOUT",
    "SandboxLaunch",
    "SandboxRunError",
    "SandboxClient",
]

_log = logging.getLogger(__name__)

#: The runner's worker role for this spine (R-07). Never a pool key.
SANDBOX_ROLE = "sandbox"

#: How often `hc-stdout.txt` is tailed (R-06).
POLL_INTERVAL_SECONDS = 0.1

#: The Python watchdog fires at `TimeoutSeconds + this` (R-06).
WATCHDOG_GRACE_SECONDS = 30

DEFAULT_TIMEOUT_SECONDS = 600

#: `meta.sandbox.hc.counters` (data-model 6.2). `unavailable` is for a run
#: whose hc never printed its `stats -p` line for another reason (a crash, a
#: cancel, a start failure).
COUNTERS_OK = "ok"
COUNTERS_UNAVAILABLE_TIMEOUT = "unavailable_timeout"
COUNTERS_UNAVAILABLE = "unavailable"

MODE_PARSE = "parse"
MODE_TEST = "test"

#: A result flag (SC-004, FR-018): hc's block for this sent word named a
#: different word, so no block is attributed to it or to any later sent word.
FLAG_ATTRIBUTION_MISMATCH = "attribution_mismatch"

_HC_SCRIPT = "hc-script.txt"
_HC_COMMANDS = ("parse", "test")

ADVISORY_GRAMMAR_LOAD_ERRORS = "grammar_load_errors"
ADVISORY_LEADING_DASH = "leading_dash_unverified"

#: Script exit codes (contracts/hcparse.md section 3).
_EXIT_HC_START_FAILED = 5
_EXIT_TIMEOUT = 6

_STDOUT = "hc-stdout.txt"
_OUTPUT = "hc-output.txt"
_GEN_LOG = cache.LOG_NAME

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
    `hc_invoke_argv` is accepted for the record only: the script itself
    runs a `.dll` through `dotnet` (contracts/hcparse.md section 2).
    """

    fwdata_path: str
    hc_path: str
    generate_hc_config_path: Optional[str] = None
    config_path: Optional[str] = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    generate_timeout_seconds: int = cache.DEFAULT_GENERATE_TIMEOUT_SECONDS
    watchdog_grace_seconds: float = WATCHDOG_GRACE_SECONDS
    check_engine: bool = True
    active_parser: Optional[str] = "HC"
    versions: Optional[Dict[str, Any]] = None
    hc_invoke_argv: Optional[List[str]] = None
    #: Test mode (US4): the corpus JSON (data-model section 5), already
    #: validated by the handler. Set -> `-Mode Test -AssertionFile`; None ->
    #: `-Mode Parse -WordFile`. `corpus_path` is accepted as an alias.
    assertion_file: Optional[str] = None

    @property
    def mode(self) -> str:
        return MODE_TEST if self.assertion_file else MODE_PARSE

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
        missing = [k for k in ("fwdata_path", "hc_path") if not kwargs.get(k)]
        if missing:
            raise ValueError("sandbox_launch lacks %s" % ", ".join(missing))
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


def _parse_argv(launch: SandboxLaunch, *, config: PathLike, word_file: PathLike,
                run_dir: PathLike) -> List[str]:
    """The script's argv (FR-022: a list, never a command string):
    `-Mode Test -AssertionFile` for a corpus run, else `-Mode Parse -WordFile`."""
    if launch.mode == MODE_TEST:
        return script.build_argv(
            "Test",
            HcPath=str(launch.hc_path),
            Config=str(config),
            AssertionFile=str(launch.assertion_file),
            RunDir=str(run_dir),
            TimeoutSeconds=int(launch.timeout_seconds),
        )
    return script.build_argv(
        "Parse",
        HcPath=str(launch.hc_path),
        Config=str(config),
        WordFile=str(word_file),
        RunDir=str(run_dir),
        TimeoutSeconds=int(launch.timeout_seconds),
    )


def _same_word(hc_word: Optional[str], sent_word: str) -> bool:
    """hc echoes its argument verbatim, unquoted (ParseCommand.cs /
    TestCommand.cs: `Parsing "{0}"` / `Testing "{0}"` after SplitCommandLine
    strips the quotes), so the header word is the sent word; NFC-compared."""
    if hc_word is None:
        return False
    return unicodedata.normalize("NFC", hc_word) == unicodedata.normalize("NFC", sent_word)


def _kill_tree(pid: int) -> None:
    # Looked up at call time so a test can observe it.
    from .. import subprocess_helpers

    subprocess_helpers._kill_process_tree(pid)


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------


class SandboxClient:
    """One sandbox run: one copy, one config, one script process."""

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

        self._proc: Optional[asyncio.subprocess.Process] = None
        self._launched_at: Optional[float] = None
        self._watchdog_task: Optional[asyncio.Task] = None
        self._gen_task: Optional[asyncio.Future] = None
        self._work_dir: Optional[Path] = None
        self._copy_bytes = 0
        self._copy_result: Optional[workdir.CleanupResult] = None
        self._entry: Optional[cache.CacheEntry] = None

        self._items: Optional[List[Dict[str, Any]]] = None
        self._ordinal: Dict[int, int] = {}
        self._reader = hc_output.BlockReader()
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._offset = 0
        self._stream_done = False
        self._parse_blocks: List[hc_output.Block] = []
        self._tail_ordinal: Optional[int] = None
        self._counters: Any = None  # ParseCounters | TestCounters
        self._results: List[Any] = []  # WordResults (parse) / lines (test)
        self._mode = self._launch.mode
        self._block_kind = (hc_output.BLOCK_TEST if self._mode == MODE_TEST
                            else hc_output.BLOCK_PARSE)
        #: Test mode: each assertion's `expected`, by assertion index (= the
        #: dispatch index; the script never reorders or de-duplicates).
        self._expected: List[Any] = []

        self._started = False
        self._cancelled = False
        self._killed = False
        self._watchdog_fired = False
        self._finalized = False
        self._closed = False
        self._in_flight_index: Optional[int] = None
        #: The first sent ordinal whose block named another word; from it on
        #: nothing is attributed (see `_record_mismatch`).
        self._mismatch_at: Optional[int] = None

    # -- the worker-client interface ----------------------------------------

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid if self._proc is not None else None

    @property
    def worker_pid(self) -> Optional[int]:
        return self.pid

    @property
    def launch(self) -> SandboxLaunch:
        return self._launch

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

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
        """Resolve the config (generating it on a miss) and launch the script."""
        if self._started:
            return
        self._started = True
        self._emit({"type": "stage", "stage": "loading_grammar"})
        self._sandbox_dir.mkdir(parents=True, exist_ok=True)

        word_file = Path(self._record.words_path)
        if not word_file.is_file():
            self._record.write_words(self._wordforms)
        if self._mode == MODE_TEST:
            self._expected = self._load_expected()

        config = await self._resolve_config()
        if self._cancelled:
            raise SandboxRunError("The sandbox run was cancelled before hc started.")

        argv = _parse_argv(self._launch, config=config, word_file=word_file,
                           run_dir=self._sandbox_dir)
        extra: Dict[str, Any] = {}
        if sys.platform != "win32":
            extra["start_new_session"] = True
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            **extra,
        )
        self._launched_at = time.monotonic()
        self._watchdog_task = asyncio.ensure_future(self._watchdog(self._proc))

    async def parse_word(
        self,
        *,
        request_id: str = "",
        run_id: str = "",
        wordform: str,
        index_in_run: int = 0,
        **_ignored: Any,
    ) -> Dict[str, Any]:
        """This word's `results.jsonl` parse section (data-model 6.4)."""
        await self._ensure_dispatch()
        index = int(index_in_run)
        items = self._items or []
        if index >= len(items):
            raise SandboxRunError(
                "The script's dispatch.json lists %d words; the run has more." % len(items),
                error_code="parser_job_failed",
                facts={"failure": "crashed", "log_path": str(self._sandbox_dir / script.DISPATCH_JSON)},
            )
        item = items[index]
        flags = list(item.get("flags") or [])
        sent_word = item.get("word")
        if not isinstance(sent_word, str):
            sent_word = wordform
        block = None
        status = hc_output.OUTCOME_NOT_EXPRESSIBLE
        if item.get("sent"):
            ordinal = self._ordinal[index]
            status = hc_output.OUTCOME_NOT_REACHED
            if self._mismatch_at is None:
                block = await self._await_block(ordinal, index)
                if block is not None and not _same_word(block.word, sent_word):
                    self._record_mismatch(index, sent_word, block.word)
                    block = None
            if self._mismatch_at is not None and ordinal >= self._mismatch_at:
                # NEVER shift results onto the wrong word (SC-004, FR-018).
                block = None
                status = hc_output.OUTCOME_ERROR_NO_OUTPUT
                if FLAG_ATTRIBUTION_MISMATCH not in flags:
                    flags.append(FLAG_ATTRIBUTION_MISMATCH)
        if self._mode == MODE_TEST:
            result = (hc_output.parse_test_block(block) if block is not None
                      else hc_output.placeholder_test_result(sent_word, status))
            expected = self._expected[index] if index < len(self._expected) else []
            line = classify.assertion_to_line(index, sent_word, expected, result, flags=flags)
            self._results.append(line)
            return {"parse": line["parse"], "assertion": line["assertion"]}
        result = (hc_output.parse_block(block) if block is not None
                  else hc_output.placeholder_result(sent_word, status))
        line = classify.word_result_to_line(index, sent_word, result, flags=flags)
        self._results.append(result)
        return {"parse": line["parse"]}

    def _record_mismatch(self, index: int, sent_word: str, hc_word: Optional[str]) -> None:
        """hc's block for a sent word names another word: stop attributing.

        The word and every later sent word become `error_no_output` with
        `attribution_mismatch`; a note joins `counter_divergences`; the words
        themselves go only into the data field `meta.sandbox.hc
        .attribution_mismatch` (FR-044). hc's raw text stays in hc-output.txt.
        """
        self._mismatch_at = self._ordinal[index]
        _log.error(
            "Sandbox run %s: hc's output block for sent word %d names a different "
            "word than dispatch.json; results are not attributed from there on.",
            self.run_id, index,
        )
        note = (
            "Result attribution stopped at dispatch index %d: hc's output block there "
            "names a different word than dispatch.json sent, so that word and every "
            "later sent word are recorded as error_no_output with flag %s; hc's raw "
            "output is kept in sandbox/hc-output.txt" % (index, FLAG_ATTRIBUTION_MISMATCH)
        )
        with contextlib.suppress(Exception):
            self._update_sandbox(hc={"attribution_mismatch": {
                "index": index, "sent_word": sent_word, "hc_word": hc_word}})
            meta = self._record.read_meta()
            existing = list((meta.counter_divergences if meta is not None else None) or [])
            self._record.set_section(counter_divergences=existing + [note])

    def _load_expected(self) -> List[Any]:
        """Each assertion's `expected`, in corpus order (data-model section 5)."""
        import json

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
        """Stop now: cancel generation, or kill the script's tree (R-06)."""
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
            await self._wait_exit()
            if self._proc is not None:
                self._pump(final=True)
                self._write_output()
                self._fold_run_json()
        finally:
            self._delete_copy()

    async def aclose(self) -> None:
        """Make sure nothing outlives the run: the process, the watchdog, the copy."""
        if self._closed:
            return
        self._closed = True
        if self._gen_task is not None and not self._gen_task.done():
            self._gen_task.cancel()
        if self.is_running():
            await self._kill()
        if self._watchdog_task is not None and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._watchdog_task
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

    # -- the script process -------------------------------------------------

    async def _watchdog(self, proc: asyncio.subprocess.Process) -> None:
        limit = float(self._launch.timeout_seconds) + float(self._launch.watchdog_grace_seconds)
        try:
            await asyncio.wait_for(proc.wait(), timeout=limit)
        except asyncio.TimeoutError:
            if proc.returncode is None:
                _log.warning("hcparse.ps1 outlived its timeout by %ss; killing its tree.",
                             self._launch.watchdog_grace_seconds)
                self._watchdog_fired = True
                await self._kill()

    async def _kill(self) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            return
        self._killed = True
        await asyncio.to_thread(_kill_tree, proc.pid)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(proc.wait(), timeout=10)

    def _exited(self) -> bool:
        return self._proc is None or self._proc.returncode is not None

    async def _wait_exit(self) -> None:
        """Wait for the script; the watchdog bounds this."""
        if self._proc is None:
            return
        while self._proc.returncode is None:
            if self._watchdog_task is not None and self._watchdog_task.done():
                await self._kill()
                break
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(self._proc.wait()), timeout=1.0)

    # -- the streams --------------------------------------------------------

    async def _ensure_dispatch(self) -> None:
        if self._items is not None:
            return
        while True:
            data = script.load_dispatch_json(self._sandbox_dir)
            items = data.get("items") if isinstance(data, dict) else None
            if (isinstance(items, list)
                    and (len(items) >= len(self._wordforms) or self._exited())
                    # hc-stdout.txt is opened only after hc-script.txt is
                    # written whole, so from then on the count is final.
                    and ((self._sandbox_dir / _STDOUT).exists() or self._exited())):
                break
            if self._exited():
                items = None
                break
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        if items is None:
            raise self._terminal_error(None) or SandboxRunError(
                "The script ended before it wrote dispatch.json; hc never ran.",
                error_code="parser_job_failed",
                facts={"failure": "crashed", "log_path": str(self._sandbox_dir / script.RUN_JSON)},
            )
        self._items = [dict(item) if isinstance(item, dict) else {} for item in items]
        ordinal = 0
        for position, item in enumerate(self._items):
            if item.get("sent"):
                self._ordinal[position] = ordinal
                ordinal += 1
        commands = self._hc_script_commands()
        if commands is not None and commands != ordinal:
            # Blocks are attributed by order, so a script that does not hold
            # exactly the sent words cannot be read at all (SC-004).
            _log.error(
                "Sandbox run %s: dispatch.json marks %d words sent but hc-script.txt "
                "holds %d commands; the run is failed rather than mis-attributed.",
                self.run_id, ordinal, commands,
            )
            with contextlib.suppress(Exception):
                self._update_sandbox(hc={"dispatch_mismatch": {
                    "sent": ordinal, "script_commands": commands}})
            await self._kill()
            raise SandboxRunError(
                "dispatch.json marks %d words sent but hc-script.txt holds %d "
                "commands; results could not be attributed." % (ordinal, commands),
                error_code="parser_job_failed",
                facts={"failure": "crashed", "log_path": str(self._sandbox_dir / _HC_SCRIPT)},
            )
        if any(ADVISORY_LEADING_DASH in (item.get("flags") or []) for item in self._items):
            self._update_sandbox(advisories=[ADVISORY_LEADING_DASH])

    def _hc_script_commands(self) -> Optional[int]:
        """How many parse/test commands hc-script.txt holds; None if unreadable."""
        try:
            text = (self._sandbox_dir / _HC_SCRIPT).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            return None
        count = 0
        for line in text.splitlines():
            parts = line.strip().split(None, 1)
            if parts and parts[0] in _HC_COMMANDS:
                count += 1
        return count

    def _take(self, blocks: List[hc_output.Block]) -> None:
        for block in blocks:
            if block.kind == self._block_kind:
                self._parse_blocks.append(block)
            elif block.kind == hc_output.BLOCK_STATS:
                read = (hc_output.parse_test_counters if self._mode == MODE_TEST
                        else hc_output.parse_counters)
                for text in (block.header,) + tuple(block.body):
                    self._counters = read(text) or self._counters

    def _pump(self, *, final: bool = False) -> None:
        """Read whatever hc-stdout.txt has gained; at the end, close the stream."""
        if self._stream_done:
            return
        path = self._sandbox_dir / _STDOUT
        data = b""
        try:
            with open(path, "rb") as handle:
                handle.seek(self._offset)
                data = handle.read()
        except OSError:
            data = b""
        if data:
            self._offset += len(data)
            self._take(self._reader.feed_text(self._decoder.decode(data)))
        if final:
            self._stream_done = True
            rest = self._decoder.decode(b"", final=True)
            if rest:
                self._take(self._reader.feed_text(rest))
            tail = self._reader.finish()
            self._take(tail)
            if tail and tail[-1].kind == self._block_kind and not tail[-1].complete:
                self._tail_ordinal = len(self._parse_blocks) - 1

    async def _await_block(self, ordinal: int, index: int) -> Optional[hc_output.Block]:
        """The sent word's block, or None when hc never reached it."""
        while True:
            self._pump()
            if ordinal < len(self._parse_blocks):
                return self._parse_blocks[ordinal]
            if self._exited():
                break
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

        self._pump(final=True)
        error = self._terminal_error(ordinal)
        in_hand = ordinal < len(self._parse_blocks)
        if error is not None and (not in_hand or ordinal == self._tail_ordinal):
            raise error
        if in_hand:
            return self._parse_blocks[ordinal]
        return None

    def _index_of_ordinal(self, ordinal: Optional[int]) -> Optional[int]:
        if ordinal is None:
            return None
        for index, value in self._ordinal.items():
            if value == ordinal:
                return index
        return None

    def _timed_out(self, run: Optional[Dict[str, Any]]) -> bool:
        hc = (run or {}).get("hc") or {}
        code = self._proc.returncode if self._proc is not None else None
        return bool(self._watchdog_fired or hc.get("timed_out") or code == _EXIT_TIMEOUT)

    def _terminal_error(self, ordinal: Optional[int]) -> Optional[SandboxRunError]:
        """Why the run cannot give this word a result, or None (a crash)."""
        if self._cancelled:
            return SandboxRunError("The sandbox run was cancelled; hc was stopped.")
        run = script.load_run_json(self._sandbox_dir)
        hc = (run or {}).get("hc") or {}
        if self._timed_out(run):
            in_flight = hc.get("in_flight_index")
            if not isinstance(in_flight, int) or isinstance(in_flight, bool):
                in_flight = self._index_of_ordinal(
                    self._tail_ordinal if self._tail_ordinal is not None else ordinal)
            self._in_flight_index = in_flight
            return SandboxRunError(
                "hc did not finish within its timeout and was stopped.",
                error_code="parser_timeout",
                facts={"timeout_seconds": int(self._launch.timeout_seconds),
                       "in_flight_index": in_flight,
                       "words_total": len(self._wordforms)},
            )
        code = self._proc.returncode if self._proc is not None else None
        text = self._read_stdout() or ""
        load_error = hc_output.detect_load_error(text)
        if load_error is not None or (not self._parse_blocks and code not in (0, None)):
            return SandboxRunError(
                "hc could not start on this configuration; its message is in "
                "sandbox/hc-stdout.txt.",
                error_code="parser_job_failed",
                facts={"failure": "crashed",
                       "log_path": str(self._sandbox_dir / _STDOUT),
                       "load_error": load_error.line if load_error else None},
            )
        return None

    def _read_stdout(self) -> Optional[str]:
        try:
            return (self._sandbox_dir / _STDOUT).read_bytes().decode("utf-8-sig", errors="replace")
        except OSError:
            return None

    # -- the record ---------------------------------------------------------

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
        versions = section.get("versions") or {}
        if isinstance(versions, dict):
            from .. import parser_probe

            skew = parser_probe.hermitcrab_versions_differ(
                versions.get("hc_tool"), versions.get("fieldworks_hermitcrab"))
            section["version_skew"] = skew
            if skew:
                codes = list(section.get("advisories") or [])
                if parser_probe.ADVISORY_HC_ENGINE_VERSION_SKEW not in codes:
                    codes.append(parser_probe.ADVISORY_HC_ENGINE_VERSION_SKEW)
                section["advisories"] = codes
        try:
            self._record.set_section(sandbox=section)
        except MetaUnreadable as exc:
            _log.warning("Run %s: meta.sandbox update %s skipped: %s",
                         self.run_id, sorted(updates), exc)

    def _write_output(self) -> None:
        text = self._read_stdout()
        if text is not None:
            with contextlib.suppress(Exception):
                self._record.write_sandbox_file(_OUTPUT, hc_output.strip_banner(text))

    def _fold_run_json(self) -> None:
        """`run.json` into `meta.sandbox` (FR-023), counters into divergences."""
        run = script.load_run_json(self._sandbox_dir) or {}
        hc = run.get("hc") if isinstance(run.get("hc"), dict) else {}
        timed_out = self._timed_out(run)

        in_flight = self._in_flight_index
        if in_flight is None:
            candidate = hc.get("in_flight_index")
            if isinstance(candidate, int) and not isinstance(candidate, bool):
                in_flight = candidate
            elif timed_out or self._cancelled:
                in_flight = self._index_of_ordinal(self._tail_ordinal)
        in_flight_word = None
        if in_flight is not None and self._items and 0 <= in_flight < len(self._items):
            in_flight_word = self._items[in_flight].get("word")

        divergences: List[str] = []
        agreement: Optional[bool] = None
        if timed_out:
            counters_state = COUNTERS_UNAVAILABLE_TIMEOUT
        elif self._counters is not None and not self._cancelled:
            counters_state = COUNTERS_OK
            reconcile = (classify.reconcile_test_counters if self._mode == MODE_TEST
                         else classify.reconcile_parse_counters)
            divergences = [d.text for d in reconcile(self._results, self._counters)]
            agreement = not divergences
        else:
            counters_state = COUNTERS_UNAVAILABLE

        load_error = hc_output.detect_load_error(self._read_stdout() or "")
        duration = run.get("duration_ms")
        if not isinstance(duration, int) and self._launched_at is not None:
            duration = int((time.monotonic() - self._launched_at) * 1000)
        hc_section = {
            "exit_code": hc.get("exit_code"),
            "timed_out": timed_out,
            "killed": bool(hc.get("killed") or self._killed),
            "in_flight_index": in_flight,
            "in_flight_word": in_flight_word,
            "duration_ms": duration,
            "counters": counters_state,
            "hc_counters": self._counters.to_dict() if self._counters else None,
            "counter_agreement": agreement,
            "stdout_bom": hc.get("stdout_bom"),
            "script_exit_code": self._proc.returncode if self._proc is not None else None,
            "watchdog_fired": self._watchdog_fired,
            "load_error": load_error.line if load_error else None,
        }
        version = run.get("hcparse_version")
        if not isinstance(version, str):
            with contextlib.suppress(Exception):
                version = script.read_hcparse_version()
        self._update_sandbox(hc=hc_section, versions={"hcparse": version})
        if divergences:
            meta = self._record.read_meta()
            existing = list((meta.counter_divergences if meta is not None else None) or [])
            self._record.set_section(counter_divergences=existing + divergences)
