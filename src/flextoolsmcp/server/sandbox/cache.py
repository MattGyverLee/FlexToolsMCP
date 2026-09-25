#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The sandbox spine's config cache (parser-check CP5, research R-05, R-12;
data-model section 3; FR-009, FR-010, FR-024..FR-026, SC-006).

A cached config is `config-cache/<project>/<cache_key>/`:

  hc-config.xml         what GenerateHCConfig wrote
  generate-config.log   its whole stdout+stderr, verbatim (FR-009)
  key.json              inputs, timestamps, load errors, versions

THE KEY (FR-024, FR-025). `sha256(canonical JSON of the seven inputs)[:16]`
-- `parse.fingerprint.fingerprint_key`'s recipe -- over the live `.fwdata`
path/size/mtime_ns, the generator's path/size/mtime_ns, and the packaged
script's `$script:HCPARSE_VERSION`. A write to a non-shared project moves
the mtime; `invalidate` covers the rest (a write inside the mtime resolution,
the shared case).

BUILD ONCE (R-12). One `asyncio.Lock` per `(project, cache_key)`. The builder
runs `hcparse.ps1 -Mode Generate` into `<key>.partial/` and renames it onto
`<key>/` only when R-05's three conditions all hold:
  exit code 0, a non-empty config, and a `Writing completed.` line.
A second job waits on the lock and then finds the entry.

`-ConfigOut` CONFINEMENT (FR-026). `build_entry` is the only code in the
package that passes `ConfigOut` to `script.build_argv`, and it passes a
`.partial` path under `config-cache/`. An AST test pins this; the script
refuses a `-ConfigOut` under `sandboxes/` as a second, independent gate.

DELETION (data-model section 1). Every delete here goes through
`_remove_tree` / `_remove_file`, which assert the target is strictly under
`config-cache/` first. No function here accepts a sandbox or corpus path.

PRUNE AND IN-USE (R-12, US6). `prune(project)` keeps the 3 most recently
used usable entries per project (by `last_used_at`) and deletes the rest,
plus every invalidated or unusable entry -- but never one a live run holds.
A run holds an entry through the in-process refcount: `acquire(entry)` right
after `ensure_entry` returns (no `await` in between), `release(entry)` in
its `finally` -- or `with in_use(entry):`. Prune runs at each job start.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import (Any, Awaitable, Callable, Dict, Iterator, List, Optional, Tuple,
                    Union)

from ..parse.fingerprint import fingerprint_key
from . import paths, script

__all__ = [
    "SCHEMA",
    "CONFIG_NAME",
    "LOG_NAME",
    "KEY_JSON",
    "PARTIAL_SUFFIX",
    "PROGRESS_LINES",
    "LOAD_ERROR_KINDS",
    "STDERR_TAIL_LINES",
    "STDERR_TAIL_MAX_BYTES",
    "DEFAULT_GENERATE_TIMEOUT_SECONDS",
    "CacheEntry",
    "ParserConfigFailed",
    "key_inputs",
    "compute_key",
    "classify_load_error",
    "extract_load_errors",
    "stderr_tail",
    "judge_generation",
    "lock_for",
    "reset_state",
    "lookup",
    "build_entry",
    "ensure_entry",
    "invalidate",
    "run_script_subprocess",
    "DEFAULT_KEEP",
    "acquire",
    "release",
    "in_use",
    "refcount",
    "prune",
]

_log = logging.getLogger(__name__)

PathLike = Union[str, Path]
RunScript = Callable[[List[str]], Awaitable[Optional[int]]]

SCHEMA = "flextoolsmcp.hc-cache/1"
CONFIG_NAME = "hc-config.xml"
LOG_NAME = "generate-config.log"
KEY_JSON = "key.json"
PARTIAL_SUFFIX = ".partial"
#: Where a failed build's log is kept when the caller has no run directory.
FAILED_LOG_SUFFIX = "." + LOG_NAME

#: GenerateHCConfig's progress lines (research F-9, R-05). Every other
#: non-blank output line of a successful generation is a load error.
PROGRESS_LINES = (
    "Loading FieldWorks project...",
    "Loading completed.",
    "Writing HC configuration file...",
    "Writing completed.",
)
_WRITING_COMPLETED = PROGRESS_LINES[3]

#: ConsoleLogger.cs's templates, in its order (R-05), then the catch-all.
_LOAD_ERROR_TEMPLATES: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("undefined_phoneme", re.compile(r'^The form ".*" contains an undefined phoneme at ')),
    ("invalid_affix_process", re.compile(r'^The affix process ".*" is invalid\.')),
    ("phoneme_no_grapheme",
     re.compile(r'^The phoneme ".*" does not contain any valid graphemes\.')),
    ("duplicate_grapheme",
     re.compile(r'^The phoneme ".*" has the same grapheme as another phoneme\.')),
    ("invalid_environment", re.compile(r'^The environment ".*" is invalid\. Reason: ')),
    ("invalid_reduplication_form",
     re.compile(r'^The reduplication form ".*" is invalid\. Reason: ')),
    ("invalid_rewrite_rule", re.compile(r'^The rewrite rule ".*" is invalid\. Reason: ')),
)
LOAD_ERROR_KINDS = tuple(kind for kind, _ in _LOAD_ERROR_TEMPLATES) + ("other",)

#: FR-025: cache entries kept per project by `prune`.
DEFAULT_KEEP = 3

#: An entry directory's name: a cache key (`compute_key`).
_KEY_RE = re.compile(r"\A[0-9a-f]{16}\Z")

#: contracts/tools.md section 4.
STDERR_TAIL_LINES = 20
STDERR_TAIL_MAX_BYTES = 4096

#: contracts/hcparse.md section 2 (`-GenerateTimeoutSeconds`).
DEFAULT_GENERATE_TIMEOUT_SECONDS = 600

#: Slack over the script's own generator timeout before the default runner
#: gives up on the script itself (it copies the project first).
_SCRIPT_GRACE_SECONDS = 120


# ---------------------------------------------------------------------------
# Entries and errors
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    """A usable cache entry. `built` is True only when THIS call generated it."""

    project: str
    key: str
    path: Path
    meta: Dict[str, Any] = field(default_factory=dict)
    built: bool = False

    @property
    def config_path(self) -> Path:
        return self.path / CONFIG_NAME

    @property
    def log_path(self) -> Path:
        return self.path / LOG_NAME

    @property
    def load_errors(self) -> List[Dict[str, str]]:
        return list((self.meta.get("generation") or {}).get("load_errors") or [])

    @property
    def load_error_count(self) -> int:
        return int((self.meta.get("generation") or {}).get("load_error_count") or 0)


class ParserConfigFailed(Exception):
    """Generation failed (FR-009); `.detail` is a `ParserConfigFailedDetail`."""

    def __init__(self, detail):
        self.detail = detail
        super().__init__(
            "GenerateHCConfig failed (exit code %s); log: %s" % (detail.exit_code, detail.log_path)
        )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)


def key_inputs(
    fwdata_path: PathLike,
    generator_path: PathLike,
    *,
    hcparse_version: Optional[str] = None,
) -> Dict[str, Any]:
    """The seven key inputs (data-model section 3), in their documented order."""
    fw = Path(fwdata_path).resolve()
    gen = Path(generator_path).resolve()
    fw_stat = fw.stat()
    gen_stat = gen.stat()
    if hcparse_version is None:
        # On the module at call time, so a bump (or a test) is seen.
        hcparse_version = script.read_hcparse_version()
    return {
        "fwdata_path": str(fw),
        "fwdata_size": fw_stat.st_size,
        "fwdata_mtime_ns": fw_stat.st_mtime_ns,
        "generate_hc_config_path": str(gen),
        "generate_hc_config_size": gen_stat.st_size,
        "generate_hc_config_mtime_ns": gen_stat.st_mtime_ns,
        "hcparse_version": str(hcparse_version),
    }


def compute_key(inputs: Dict[str, Any]) -> str:
    """`sha256(canonical JSON of inputs)[:16]` -- `fingerprint_key`'s recipe."""
    return fingerprint_key(inputs)


def classify_load_error(line: str) -> str:
    """The ConsoleLogger template a load-error line matches, else `other`."""
    for kind, pattern in _LOAD_ERROR_TEMPLATES:
        if pattern.match(line):
            return kind
    return "other"


def extract_load_errors(output: str) -> List[Dict[str, str]]:
    """Every non-blank line that is not a progress line, verbatim, tagged.

    An exclusion list (R-05): a template this module does not know is
    counted as `other` -- over-counted and visible, never hidden.
    """
    errors = []
    for raw in output.splitlines():
        line = raw.rstrip("\r")
        if not line.strip() or line.strip() in PROGRESS_LINES:
            continue
        errors.append({"kind": classify_load_error(line), "line": line})
    return errors


def stderr_tail(output: str) -> str:
    """The last 20 lines, non-ASCII escaped (FR-021), capped at 4 KiB (the end kept)."""
    lines = output.splitlines()[-STDERR_TAIL_LINES:]
    text = "\n".join(lines).encode("ascii", "backslashreplace")
    if len(text) > STDERR_TAIL_MAX_BYTES:
        text = text[-STDERR_TAIL_MAX_BYTES:]
        # Start on a line boundary rather than mid-line / mid-escape.
        newline = text.find(b"\n")
        if 0 <= newline < len(text) - 1:
            text = text[newline + 1:]
    return text.decode("ascii")


def judge_generation(exit_code: Optional[int], config_path: PathLike, output: str) -> bool:
    """R-05: exit 0 AND a non-empty config AND a `Writing completed.` line."""
    if exit_code != 0:
        return False
    try:
        if Path(config_path).stat().st_size <= 0:
            return False
    except OSError:
        return False
    return any(line.strip() == _WRITING_COMPLETED for line in output.splitlines())


# ---------------------------------------------------------------------------
# Locks and state
# ---------------------------------------------------------------------------

_LOCKS: Dict[Tuple[str, str], asyncio.Lock] = {}
_REFCOUNTS: Dict[Tuple[str, str], int] = {}


def lock_for(project: str, key: str) -> asyncio.Lock:
    """The build lock for one `(project, cache_key)` (R-12)."""
    lock = _LOCKS.get((project, key))
    if lock is None:
        lock = _LOCKS[(project, key)] = asyncio.Lock()
    return lock


def reset_state() -> None:
    """Forget every lock and refcount (tests; a new event loop)."""
    _LOCKS.clear()
    _REFCOUNTS.clear()


def refcount(project: str, key: str) -> int:
    """How many live runs in this process hold `(project, key)`."""
    return _REFCOUNTS.get((project, key), 0)


def acquire(entry: CacheEntry) -> int:
    """Mark `entry` in use by a run (prune spares it). Returns the new count."""
    k = (entry.project, entry.key)
    _REFCOUNTS[k] = _REFCOUNTS.get(k, 0) + 1
    return _REFCOUNTS[k]


def release(entry: CacheEntry) -> int:
    """Undo one `acquire`; never below 0. Returns the new count."""
    k = (entry.project, entry.key)
    count = max(0, _REFCOUNTS.get(k, 0) - 1)
    if count:
        _REFCOUNTS[k] = count
    else:
        _REFCOUNTS.pop(k, None)
    return count


@contextmanager
def in_use(entry: CacheEntry) -> Iterator[CacheEntry]:
    """`acquire` for the block, `release` in `finally`."""
    acquire(entry)
    try:
        yield entry
    finally:
        release(entry)


# ---------------------------------------------------------------------------
# Guarded file operations
# ---------------------------------------------------------------------------


def _remove_tree(target: Path) -> None:
    """Delete a directory strictly under `config-cache/` (data-model section 1)."""
    if not target.exists():
        return
    paths.assert_under(target, paths.config_cache_root())
    shutil.rmtree(target)


def _remove_file(target: Path) -> None:
    """Delete a file strictly under `config-cache/` (data-model section 1)."""
    if not target.exists():
        return
    paths.assert_under(target, paths.config_cache_root())
    target.unlink()


def _write_json(target: Path, data: Dict[str, Any]) -> None:
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, target)


def _read_meta(entry_dir: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads((entry_dir / KEY_JSON).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _usable_meta(entry_dir: Path, key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """`key.json` if the entry is usable (data-model section 3), else None."""
    if entry_dir.name.endswith(PARTIAL_SUFFIX) or not entry_dir.is_dir():
        return None
    meta = _read_meta(entry_dir)
    if meta is None or meta.get("schema") != SCHEMA:
        return None
    inputs = meta.get("inputs")
    if not isinstance(inputs, dict):
        return None
    try:
        if meta.get("cache_key") != compute_key(inputs):
            return None
    except (TypeError, ValueError):
        return None
    if key is not None and meta.get("cache_key") != key:
        return None
    if meta.get("invalidated_at") is not None:
        return None
    try:
        if (entry_dir / CONFIG_NAME).stat().st_size <= 0:
            return None
    except OSError:
        return None
    return meta


# ---------------------------------------------------------------------------
# Lookup and invalidation
# ---------------------------------------------------------------------------


def _existing_cache_dir(project: str) -> Optional[Path]:
    """`config-cache/<project>/` if it exists; never creates it."""
    cache_dir = paths.config_cache_dir(project)
    return cache_dir if cache_dir.is_dir() else None


def lookup(project: str, key: str, *, touch: bool = True) -> Optional[CacheEntry]:
    """The usable entry for `key`, or None. `touch` updates `last_used_at`."""
    cache_dir = _existing_cache_dir(project)
    if cache_dir is None:
        return None
    entry_dir = cache_dir / key
    meta = _usable_meta(entry_dir, key)
    if meta is None:
        return None
    if touch:
        meta["last_used_at"] = _now_iso()
        try:
            _write_json(entry_dir / KEY_JSON, meta)
        except OSError as exc:  # a read-only touch failure must not lose the entry
            _log.warning("Could not update last_used_at for %s: %s", entry_dir, exc)
    return CacheEntry(project=project, key=key, path=entry_dir, meta=meta, built=False)


def invalidate(project: str) -> int:
    """Mark every entry of `project` invalidated (FR-026). Returns the count."""
    cache_dir = _existing_cache_dir(project)
    if cache_dir is None:
        return 0
    stamp = _now_iso()
    count = 0
    for entry_dir in sorted(cache_dir.iterdir()):
        if not entry_dir.is_dir() or entry_dir.name.endswith(PARTIAL_SUFFIX):
            continue
        meta = _read_meta(entry_dir)
        if meta is None or meta.get("schema") != SCHEMA:
            continue
        if meta.get("invalidated_at") is None:
            meta["invalidated_at"] = stamp
            try:
                _write_json(entry_dir / KEY_JSON, meta)
            except OSError as exc:
                _log.warning("Could not invalidate %s: %s", entry_dir, exc)
                continue
        count += 1
    return count


def prune(project: str, keep: int = DEFAULT_KEEP) -> List[str]:
    """Delete this project's surplus entries; returns the deleted keys (R-12).

    Candidates are `<16 hex>` entry directories only. Unusable ones
    (invalidated, bad `key.json`, empty config) go at refcount 0; usable ones
    are ranked by `last_used_at`, newest first, and those past rank `keep`
    go at refcount 0. An in-use entry is never deleted and takes one of the
    `keep` slots first. Never creates a directory.
    """
    cache_dir = _existing_cache_dir(project)
    if cache_dir is None:
        return []
    usable: List[Tuple[str, str]] = []  # (last_used_at, key)
    doomed: List[str] = []
    for entry_dir in sorted(cache_dir.iterdir()):
        if not entry_dir.is_dir() or not _KEY_RE.match(entry_dir.name):
            continue
        meta = _usable_meta(entry_dir, entry_dir.name)
        if meta is None:
            doomed.append(entry_dir.name)
        else:
            stamp = meta.get("last_used_at") or meta.get("created_at") or ""
            usable.append((str(stamp), entry_dir.name))
    # In-use entries take their slots first, so the total stays at `keep`
    # whenever the live runs allow it; the newest others fill the rest.
    usable.sort(reverse=True)
    held = [key for _stamp, key in usable if refcount(project, key) > 0]
    slots = max(0, int(keep) - len(held))
    others = [key for _stamp, key in usable if refcount(project, key) == 0]
    doomed.extend(others[slots:])

    deleted: List[str] = []
    for key in doomed:
        if refcount(project, key) > 0:
            continue
        try:
            _remove_tree(cache_dir / key)
        except OSError as exc:  # locked by another process; next prune retries
            _log.warning("Could not prune cache entry %s/%s: %s", project, key, exc)
            continue
        deleted.append(key)
    return deleted


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


async def run_script_subprocess(argv: List[str], *, timeout: Optional[float] = None) -> Optional[int]:
    """Run the script's argv (stdin closed); its exit code, or None if killed."""
    from ..subprocess_helpers import _kill_process_tree

    extra: Dict[str, Any] = {}
    if sys.platform != "win32":
        extra["start_new_session"] = True
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        **extra,
    )
    try:
        out, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        _kill_process_tree(process.pid)
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except Exception:  # noqa: BLE001
            pass
        if isinstance(sys.exc_info()[1], asyncio.CancelledError):
            raise
        return None
    if out:
        _log.debug("hcparse Generate console:\n%s", out.decode("ascii", "replace"))
    return process.returncode


def _generator_exit_code(run_dir: Path) -> Optional[int]:
    """`run.json`'s `generate.exit_code`; None if missing, timed out or odd."""
    run = script.load_run_json(run_dir)
    generate = run.get("generate") if run else None
    if not isinstance(generate, dict) or generate.get("timed_out"):
        return None
    code = generate.get("exit_code")
    if isinstance(code, bool) or not isinstance(code, int):
        return None
    return code


def _read_log(run_dir: Path) -> bytes:
    try:
        return (run_dir / LOG_NAME).read_bytes()
    except OSError:
        return b""


def _check_write_targets(work_dir: PathLike, log_dir: Optional[PathLike]) -> None:
    """Refuse a build's write targets outside the system-owned areas (data-model 1).

    `work_dir` must be strictly under `work/`. A `log_dir` is normally the
    run's `sandbox/` under the RUN RECORD dir, which is allowed; one under
    the sandbox root is allowed only in `config-cache/` or `work/`, so a
    user-owned area can never receive a file from the cache.
    """
    paths.assert_under(work_dir, paths.work_root())
    if log_dir is None:
        return
    root = paths.sandbox_root()
    if paths.is_under(log_dir, root, strict=False) and not (
        paths.is_under(log_dir, paths.config_cache_root(), strict=False)
        or paths.is_under(log_dir, paths.work_root(), strict=False)
    ):
        raise paths.SandboxPathError(
            f"Refusing log_dir {log_dir}: under the sandbox root but outside "
            f"config-cache/ and work/"
        )


async def build_entry(
    project: str,
    inputs: Dict[str, Any],
    *,
    work_dir: PathLike,
    run_id: Optional[str] = None,
    log_dir: Optional[PathLike] = None,
    active_parser: Optional[str] = "HC",
    versions: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = DEFAULT_GENERATE_TIMEOUT_SECONDS,
    run_script: Optional[RunScript] = None,
) -> CacheEntry:
    """Generate a config into `<key>.partial/`, judge it, rename it into place.

    The caller holds `lock_for(project, key)` (see `ensure_entry`). Raises
    `ParserConfigFailed` when R-05's conditions do not all hold; the
    `.partial` directory never survives this call.
    """
    from ..response_models import ParserConfigFailedDetail

    _check_write_targets(work_dir, log_dir)
    key = compute_key(inputs)
    cache_dir = paths.config_cache_dir(project)
    final = cache_dir / key
    partial = cache_dir / (key + PARTIAL_SUFFIX)
    paths.assert_under(partial, paths.config_cache_root())

    _remove_tree(partial)  # a killed earlier build
    partial.mkdir(parents=True)
    config_out = partial / CONFIG_NAME

    argv = script.build_argv(
        "Generate",
        GenerateHCConfigPath=inputs["generate_hc_config_path"],
        FwData=inputs["fwdata_path"],
        WorkDir=str(work_dir),
        ConfigOut=str(config_out),
        RunDir=str(partial),
        GenerateTimeoutSeconds=int(timeout_seconds),
    )

    if run_script is None:
        async def run_script(a: List[str]) -> Optional[int]:
            return await run_script_subprocess(
                a, timeout=int(timeout_seconds) + _SCRIPT_GRACE_SECONDS)

    started = time.monotonic()
    try:
        script_exit = await run_script(argv)
        duration_ms = int((time.monotonic() - started) * 1000)
        log_bytes = _read_log(partial)
        output = log_bytes.decode("utf-8-sig", errors="replace")
        exit_code = _generator_exit_code(partial)
        ok = judge_generation(exit_code, config_out, output)

        run_log: Optional[Path] = None
        if log_dir is not None:
            run_log = Path(log_dir) / LOG_NAME
            run_log.parent.mkdir(parents=True, exist_ok=True)
            run_log.write_bytes(log_bytes)

        failed_log = cache_dir / (key + FAILED_LOG_SUFFIX)
        if not ok:
            if run_log is None:
                failed_log.write_bytes(log_bytes)
                run_log = failed_log
            _log.info(
                "GenerateHCConfig failed for %s (generator exit %s, script exit %s)",
                project, exit_code, script_exit,
            )
            raise ParserConfigFailed(ParserConfigFailedDetail(
                exit_code=exit_code,
                stderr_tail=stderr_tail(output),
                log_path=str(run_log),
                run_id=run_id,
            ))

        load_errors = extract_load_errors(output)
        now = _now_iso()
        meta: Dict[str, Any] = {
            "schema": SCHEMA,
            "cache_key": key,
            "inputs": dict(inputs),
            "active_parser": active_parser,
            "created_at": now,
            "last_used_at": now,
            "invalidated_at": None,
            "generation": {
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "writing_completed": True,
                "load_errors": load_errors,
                "load_error_count": len(load_errors),
            },
            "versions": dict(versions or {}),
        }
        _write_json(partial / KEY_JSON, meta)

        # Replace an invalidated (or otherwise unusable) entry, then rename.
        _remove_tree(final)
        os.replace(partial, final)
        _remove_file(failed_log)
    finally:
        _remove_tree(partial)

    return CacheEntry(project=project, key=key, path=final, meta=meta, built=True)


async def ensure_entry(
    project: str,
    fwdata_path: PathLike,
    generator_path: PathLike,
    *,
    work_dir: PathLike,
    run_id: Optional[str] = None,
    log_dir: Optional[PathLike] = None,
    active_parser: Optional[str] = "HC",
    versions: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = DEFAULT_GENERATE_TIMEOUT_SECONDS,
    run_script: Optional[RunScript] = None,
) -> CacheEntry:
    """The usable entry for this project's current inputs, building it once."""
    _check_write_targets(work_dir, log_dir)
    inputs = key_inputs(fwdata_path, generator_path)
    key = compute_key(inputs)
    async with lock_for(project, key):
        entry = lookup(project, key)
        if entry is not None:
            return entry
        return await build_entry(
            project,
            inputs,
            work_dir=work_dir,
            run_id=run_id,
            log_dir=log_dir,
            active_parser=active_parser,
            versions=versions,
            timeout_seconds=timeout_seconds,
            run_script=run_script,
        )
