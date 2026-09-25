#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The CP5 sandbox spine, against live FieldWorks projects and a real `hc`
(parser-check CP5; specs/parser-check-cp5/quickstart.md, tasks T091/T094/T095).

WHAT THIS MODULE SPECIFIES. It drives the REAL handlers, in process, exactly
as a client would call them -- `handle_flextools_parse_sandbox` (all five
actions), `handle_flextools_health`, and the run tools
`handle_flextools_parse_status` / `_log` / `_diff` / `_cancel` -- and asserts
the quickstart's expectations for scenarios S1-S13. The seven live questions
L-1..L-7 are recorded as scenarios too: they CAPTURE observations for a human
to answer later (T095 folds the answers into code), so they assert only the
safety invariants and never an answer.

THE SANDBOX SPINE NEVER WRITES THE PROJECT. Every scenario therefore takes a
BYTE-IDENTITY HASH of the whole project folder before and after (FR-043,
SC-001) and asserts it is unchanged. `*.lock` files are listed separately
rather than hashed, so a lock FLEx already holds (S7) is visible without
masking a real write. The one scenario that needs a project write -- S9,
cache invalidation -- runs ONLY on a `CP5-Scratch-` copy made by
`tests/live_support/make_disposable.py` with `prefix=CP5_SCRATCH_PREFIX`, and
ONLY with `FLEXTOOLSMCP_CP5_LIVE_WRITE=1` set in addition to the live gate.
L-6 makes a scratch copy too (Try A Word opens the project it reads), so it
shares that opt-in. Nothing here writes into a working project.

THE DESIGNATED PROJECTS (quickstart "Projects"):

    IndonesianHC-Complete           correctness (S1-S9, S11, S13, L-1..L-7)
    Malay Parsing-20230810withHC    timeout and scale (S10)
    Sena 3                          the XAmple refusal ONLY (S12). The tool
                                    must refuse before any copy, so the
                                    project is never opened -- the hash and a
                                    lock watch during the call prove it.

THE LIVE GATE. Marked `requires_flex`. A missing prerequisite -- Windows,
FieldWorks' projects directory, a designated project, a working `hc`,
GenerateHCConfig.exe, or a human-prepared setup (S7, S8, L-4) -- SKIPS, unless
`FLEXLIBS_REQUIRE_LIVE=1`, in which case it FAILS. A scenario whose setup is
a machine STATE contrary to the current one (S1 needs NO hc; S2 needs an hc
that cannot start) always skips: it cannot be produced on that machine.

ISOLATION. The sandbox root (`FLEXTOOLSMCP_PARSE_SANDBOX_DIR`) and the run
records live in a per-module temporary directory, never under
`~/.flextoolsmcp` and never under a project folder.

EVIDENCE goes to `specs/parser-check-cp5/evidence/<id>-<slug>.json`, written
only after a scenario's assertions pass. Each file records the scenario id,
the three versions of FR-005 (the hc tool, FieldWorks' HermitCrab,
GenerateHCConfig), the before/after hashes, and response excerpts.

Deselect on a machine without FieldWorks with `-m "not requires_flex"`.
"""

import asyncio
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pytest

pytestmark = pytest.mark.requires_flex

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent / "live_support"))

from make_disposable import (  # noqa: E402
    CP5_SCRATCH_PREFIX,
    delete_disposable,
    make_disposable,
    projects_dir,
    require_disposable,
)

from flextoolsmcp.server import parser_probe  # noqa: E402
from flextoolsmcp.server.handlers import diagnostic_health  # noqa: E402
from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.sandbox import paths as sandbox_paths  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: The correctness source.
HC_PROJECT = os.environ.get("FLEXTOOLSMCP_LIVE_HC_PROJECT", "IndonesianHC-Complete")

#: The timeout / scale source (S10).
SCALE_PROJECT = os.environ.get(
    "FLEXTOOLSMCP_LIVE_SCALE_PROJECT", "Malay Parsing-20230810withHC"
)

#: The XAmple project. Used ONLY for S12's refusal; never opened, never copied.
XAMPLE_PROJECT = "Sena 3"

#: The opt-in for anything that makes a scratch copy and writes to it (S9, L-6).
LIVE_WRITE_ENV = "FLEXTOOLSMCP_CP5_LIVE_WRITE"

EVIDENCE_DIR = REPO_ROOT / "specs" / "parser-check-cp5" / "evidence"

#: The verbatim install command (FR-007, contracts/tools.md section 4).
HC_INSTALL_COMMAND = "dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool"

#: S4's word list: an apostrophe word (one word, FR-014), a both-quotes word
#: (not expressible in hc's command language), non-Latin text, and a word the
#: grammar should not parse. Override with a JSON list for another project.
_DEFAULT_S4_WORDS = [
    "makan", "dimakan", "memakan", "rumah", "ma'af", "a'b\"c", "rumahé",
    "ماكان", "xqzvbw",
]
APOSTROPHE_WORD = os.environ.get("FLEXTOOLSMCP_CP5_APOSTROPHE_WORD", "ma'af")
BOTH_QUOTES_WORD = os.environ.get("FLEXTOOLSMCP_CP5_BOTH_QUOTES_WORD", "a'b\"c")

_TERMINAL = {"completed", "failed", "cancelled"}

#: The stand-alone run's generous bound; a live grammar export takes a minute.
_RUN_TIMEOUT = 1800


def _s4_words() -> List[str]:
    raw = os.environ.get("FLEXTOOLSMCP_CP5_S4_WORDS")
    return json.loads(raw) if raw else list(_DEFAULT_S4_WORDS)


# ---------------------------------------------------------------------------
# The live gate
# ---------------------------------------------------------------------------


def _require_live() -> bool:
    return os.environ.get("FLEXLIBS_REQUIRE_LIVE") == "1"


def _missing(reason: str):
    """Skip -- or, under `FLEXLIBS_REQUIRE_LIVE=1`, fail -- a live prerequisite."""
    if _require_live():
        pytest.fail(f"live prerequisite missing (FLEXLIBS_REQUIRE_LIVE=1): {reason}")
    pytest.skip(reason)


def _contrary_state(reason: str):
    """The scenario's setup is a machine state this machine is not in. It
    cannot be produced here, so it skips even under the live gate."""
    pytest.skip(reason)


def _projects_root() -> Path:
    if sys.platform != "win32":
        _missing("live sandbox tests need Windows with FieldWorks installed")
    try:
        return projects_dir()
    except FileNotFoundError as exc:
        _missing(str(exc))


def _project_dir(name: str) -> Path:
    root = _projects_root()
    folder = root / name
    if not (folder / f"{name}.fwdata").is_file():
        _missing(f"designated project {name!r} is not installed under {root}")
    return folder


def _hc():
    parser_probe.clear_hc_probe_cache()
    return parser_probe.discover_hc_tool()


def _require_working_hc():
    hc = _hc()
    if not (hc.found and hc.starts is True):
        _missing(
            "a working hc is required (blocked on M-1; research R-15): "
            f"found={hc.found} starts={hc.starts} reason={hc.reason!r}"
        )
    return hc


def _require_generator():
    ghc = parser_probe.discover_generate_hc_config()
    if not ghc.ok:
        _missing(f"GenerateHCConfig.exe not found (expected {ghc.expected_path})")
    return ghc


def _require_sandbox_spine():
    return _require_working_hc(), _require_generator()


def _require_write_opt_in():
    if os.environ.get(LIVE_WRITE_ENV) != "1":
        _missing(
            f"this scenario writes to a {CP5_SCRATCH_PREFIX} copy; set "
            f"{LIVE_WRITE_ENV}=1 to opt in"
        )


def _require_env(name: str, what: str) -> str:
    value = os.environ.get(name)
    if not value:
        _missing(f"{what} (set {name})")
    return value


def test_the_xample_project_is_never_a_designated_source():
    """S12's project must not be reachable as either designated source."""
    assert HC_PROJECT != XAMPLE_PROJECT
    assert SCALE_PROJECT != XAMPLE_PROJECT


def test_the_live_gate_turns_a_missing_prerequisite_into_a_failure(monkeypatch):
    monkeypatch.setenv("FLEXLIBS_REQUIRE_LIVE", "1")
    with pytest.raises(pytest.fail.Exception):
        _missing("probe")
    monkeypatch.delenv("FLEXLIBS_REQUIRE_LIVE")
    with pytest.raises(pytest.skip.Exception):
        _missing("probe")


# ---------------------------------------------------------------------------
# Safety: the byte-identity hash, the lock watch, the work/ check
# ---------------------------------------------------------------------------


def _folder_hash(folder: Path) -> Dict[str, Any]:
    """SHA-256 over every file's relative path and bytes, sorted. `*.lock`
    files are listed, not hashed (a lock FLEx holds is not a write)."""
    digest = hashlib.sha256()
    locks: List[str] = []
    count = 0
    total = 0
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        rel = path.relative_to(folder).as_posix()
        if path.name.endswith(".lock"):
            locks.append(rel)
            continue
        digest.update(rel.encode("utf-8") + b"\0")
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        digest.update(h.digest())
        count += 1
        total += path.stat().st_size
    return {"sha256": digest.hexdigest(), "files": count, "bytes": total, "locks": locks}


class ProjectGuard:
    """Hash before, hash after, assert identical (FR-043, SC-001)."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.before = _folder_hash(folder)
        self.after: Optional[Dict[str, Any]] = None

    def check(self) -> Dict[str, Any]:
        self.after = _folder_hash(self.folder)
        assert self.after["sha256"] == self.before["sha256"], (
            f"the project folder {self.folder} changed during a sandbox scenario "
            f"(FR-043): before={self.before} after={self.after}"
        )
        return self.record()

    def record(self) -> Dict[str, Any]:
        return {"folder": str(self.folder), "before": self.before, "after": self.after}


class LockWatch:
    """Polls a project folder for new `*.lock` files while a call runs (S12)."""

    def __init__(self, folder: Path, interval: float = 0.02):
        self.folder = folder
        self.interval = interval
        self.initial = {p.name for p in folder.glob("*.lock")}
        self.seen: set = set()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        while not self._stop.is_set():
            with contextlib.suppress(OSError):
                self.seen |= {p.name for p in self.folder.glob("*.lock")} - self.initial
            time.sleep(self.interval)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=5)


def _tree_listing(root: Path) -> List[str]:
    if not root.exists():
        return []
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


def _work_entries() -> List[str]:
    root = sandbox_paths.work_root()
    return sorted(p.name for p in root.iterdir()) if root.is_dir() else []


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

_VERSIONS: Dict[str, Any] = {}


async def _versions() -> Dict[str, Any]:
    """The three versions of FR-005, as health reports them (read once)."""
    if not _VERSIONS:
        detected = (await _health())["parser"]["detected"]
        _VERSIONS.update({
            "hc_tool": detected.get("hc_tool_version"),
            "fieldworks_hermitcrab": detected.get("fieldworks_hermitcrab_version"),
            "generate_hc_config": detected.get("generate_hc_config_version"),
            "hc_source": detected.get("hc_source"),
            "hc_path": detected.get("hc_path"),
        })
    return dict(_VERSIONS)


_EXCERPT_DROP = ("_contract", "error", "session", "libraries", "indexes", "logs", "server")


def _excerpt(response: Any, limit: int = 20000) -> Any:
    """A response trimmed for evidence: envelope noise dropped, size capped."""
    if isinstance(response, dict):
        trimmed = {k: v for k, v in response.items() if k not in _EXCERPT_DROP}
    else:
        trimmed = response
    text = json.dumps(trimmed, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return trimmed
    return {"truncated": True, "text": text[:limit]}


async def _evidence(
    scenario: str,
    slug: str,
    *,
    project: Optional[str] = None,
    hashes: Optional[Iterable[ProjectGuard]] = None,
    responses: Optional[Dict[str, Any]] = None,
    observations: Optional[Dict[str, Any]] = None,
    needs_human: bool = False,
) -> Path:
    """Write one scenario's evidence beside the spec (never in a project)."""
    payload = {
        "scenario": scenario,
        "project": project,
        "versions": await _versions(),
        "hashes": [g.record() for g in (hashes or [])],
        "responses": {k: _excerpt(v) for k, v in (responses or {}).items()},
        "observations": observations or {},
        "needs_human": needs_human,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{scenario.lower()}-{slug}.json"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return path


# ---------------------------------------------------------------------------
# Driving the real handlers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sandbox_home():
    """A per-module sandbox root and record dir, outside every project."""
    home = Path(tempfile.mkdtemp(prefix="cp5-live-"))
    old = os.environ.get(sandbox_paths.ENV_VAR)
    os.environ[sandbox_paths.ENV_VAR] = str(home / "parse")
    try:
        yield home
    finally:
        if old is None:
            os.environ.pop(sandbox_paths.ENV_VAR, None)
        else:
            os.environ[sandbox_paths.ENV_VAR] = old
        shutil.rmtree(home, ignore_errors=True)


@contextlib.asynccontextmanager
async def live_runner(home: Path):
    runner = ParseRunner(record_dir=home / "runs")
    parse_handler.set_runner(runner)
    try:
        yield runner
    finally:
        parse_handler.set_runner(None)
        await runner.aclose()


async def _call(handler, **args) -> Dict[str, Any]:
    response = await handler(args)
    return json.loads(response[0].text)


async def _health() -> Dict[str, Any]:
    return await _call(diagnostic_health.handle_flextools_health, verbose=False)


async def _sandbox(**args) -> Dict[str, Any]:
    return await _call(parse_handler.handle_flextools_parse_sandbox, **args)


async def _status(run_id: str) -> Dict[str, Any]:
    return await _call(parse_handler.handle_flextools_parse_status, run_id=run_id)


async def _log(run_id: str, section: str, **args) -> Dict[str, Any]:
    return await _call(
        parse_handler.handle_flextools_parse_log, run_id=run_id, section=section, **args
    )


async def _diff(baseline: str, current: str) -> Dict[str, Any]:
    return await _call(
        parse_handler.handle_flextools_parse_diff,
        baseline_run_id=baseline, current_run_id=current,
    )


async def _cancel(run_id: str) -> Dict[str, Any]:
    return await _call(parse_handler.handle_flextools_parse_cancel, run_id=run_id)


async def _finish(response: Dict[str, Any], timeout: float = _RUN_TIMEOUT) -> Dict[str, Any]:
    """Poll a started run to a terminal stage; a refusal comes back as is."""
    if response.get("status") == "error" or not response.get("run_id"):
        return response
    if response.get("stage") in _TERMINAL:
        return response
    deadline = time.monotonic() + timeout
    status = response
    while time.monotonic() < deadline:
        status = await _status(response["run_id"])
        if status.get("status") == "error" or status.get("stage") in _TERMINAL:
            return status
        await asyncio.sleep(0.5)
    pytest.fail(f"run {response['run_id']} did not finish within {timeout}s: {status}")


async def _parse(project: str, words, **args) -> Dict[str, Any]:
    started = await _sandbox(action="parse", project_name=project, words=words, **args)
    finished = await _finish(started)
    finished.setdefault("_submitted", started)
    return finished


def _results(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    record = response.get("record_dir") or response.get("_submitted", {}).get("record_dir")
    if not record:
        return []
    path = Path(record) / "results.jsonl"
    lines = []
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(json.JSONDecodeError):
                lines.append(json.loads(raw))
    return lines


def _outcome(line: Dict[str, Any]) -> Optional[str]:
    return (line.get("parse") or {}).get("outcome") or line.get("outcome")


def _run_id(response: Dict[str, Any]) -> Optional[str]:
    return response.get("run_id") or response.get("_submitted", {}).get("run_id")


def _record_dir(response: Dict[str, Any]) -> Optional[Path]:
    record = response.get("record_dir") or response.get("_submitted", {}).get("record_dir")
    return Path(record) if record else None


def _as_dict(obj: Any) -> Any:
    """A probe result as plain data for evidence (dataclass or namedtuple)."""
    if hasattr(obj, "_asdict"):
        return obj._asdict()
    if hasattr(obj, "__dataclass_fields__"):
        return {k: getattr(obj, k) for k in obj.__dataclass_fields__}
    return getattr(obj, "__dict__", repr(obj))


def _names_tool(value: Any, tool: str) -> bool:
    return tool in json.dumps(value, ensure_ascii=False)


def _fwdata_wordforms(fwdata: Path, limit: int) -> List[str]:
    """Vernacular wordforms, stream-read from the `.fwdata` (read only, no
    LCM, no lock) -- the same access the engine check uses (R-02)."""
    words: List[str] = []
    seen = set()
    with open(fwdata, "rb") as fh:
        for _, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag == "rt":
                if elem.get("class") == "WfiWordform":
                    for auni in elem.iter("AUni"):
                        text = (auni.text or "").strip()
                        if text and " " not in text and text not in seen:
                            seen.add(text)
                            words.append(text)
                        break
                    if len(words) >= limit:
                        break
                elem.clear()
    return words


# ===========================================================================
# S1-S3: health and discovery (US1)
# ===========================================================================


async def test_s1_no_hc_health_and_refusal(sandbox_home):
    """S1: no hc. Health says unavailable with the install command and never
    names the sandbox tool; the tool refuses with `parser_tool_missing`
    before copying anything. Runnable on this machine now (T094)."""
    folder = _project_dir(HC_PROJECT)
    hc = _hc()
    if hc.found:
        _contrary_state(f"S1 needs a machine without hc; hc was found at {hc.path}")

    health = await _health()
    sandbox = health["parser"]["sandbox"]
    hc_component = next(c for c in sandbox["components"] if c["component"] == "hc")
    steps = health.get("parser_next_steps") or []
    assert sandbox["status"] == "unavailable", sandbox
    assert hc_component["found"] is False, hc_component
    assert _names_tool(steps, HC_INSTALL_COMMAND), steps
    assert not _names_tool(steps, "flextools_parse_sandbox"), steps

    guard = ProjectGuard(folder)
    before_tree = _tree_listing(sandbox_paths.sandbox_root())
    async with live_runner(sandbox_home):
        refusal = await _sandbox(action="parse", project_name=HC_PROJECT, words=["makan"])
    assert refusal.get("status") == "error", refusal
    assert refusal.get("error_code") == "parser_tool_missing", refusal
    assert refusal.get("component") == "hc", refusal
    assert str(refusal.get("install_hint", "")).startswith(HC_INSTALL_COMMAND), refusal
    assert refusal.get("next_step"), refusal
    assert all("est_cost" in rung for rung in refusal["next_step"]), refusal
    assert _tree_listing(sandbox_paths.sandbox_root()) == before_tree, (
        "the refusal created something under the sandbox root"
    )
    guard.check()

    await _evidence(
        "S1", "health-no-hc", project=HC_PROJECT, hashes=[guard],
        responses={
            "health_parser": health["parser"],
            "health_parser_next_steps": steps,
            "parse_sandbox_refusal": refusal,
        },
        observations={
            "discovery": {
                "found": hc.found, "starts": hc.starts, "source": hc.source,
                "signal": hc.signal, "reason": hc.reason,
                "expected_path": hc.expected_path,
            },
            "sandbox_root_unchanged": True,
        },
    )


async def test_s2_hc_cannot_start(sandbox_home):
    """S2: hc 3.8+ present without .NET 10. found, not startable, the reason
    names the runtime, and the tool refuses before any copy."""
    folder = _project_dir(HC_PROJECT)
    hc = _hc()
    if not hc.found:
        _missing("S2 needs an hc that is installed but cannot start (none found)")
    if hc.starts is not False:
        _contrary_state(f"S2 needs an hc that cannot start; this one starts={hc.starts}")

    health = await _health()
    component = next(c for c in health["parser"]["sandbox"]["components"]
                     if c["component"] == "hc")
    assert component["found"] is True and component["starts"] is False, component
    assert component["signal"] == parser_probe.SANDBOX_SIGNAL_RUNTIME_MISSING, component
    assert component["reason"], component

    guard = ProjectGuard(folder)
    work_before = _work_entries()
    async with live_runner(sandbox_home):
        refusal = await _sandbox(action="parse", project_name=HC_PROJECT, words=["makan"])
    assert refusal.get("error_code") == "parser_tool_missing", refusal
    assert _work_entries() == work_before, "a copy was started for an hc that cannot start"
    guard.check()

    await _evidence(
        "S2", "health-cannot-start", project=HC_PROJECT, hashes=[guard],
        responses={"health_parser": health["parser"],
                   "health_parser_next_steps": health.get("parser_next_steps"),
                   "parse_sandbox_refusal": refusal},
        observations={"reason": component["reason"], "work_unchanged": True},
    )


async def test_s3_health_ready(sandbox_home):
    """S3: a working hc. ready, three versions, the skew advisory iff they differ."""
    _require_sandbox_spine()
    health = await _health()
    parser = health["parser"]
    detected = parser["detected"]
    assert parser["sandbox"]["status"] == "ready", parser["sandbox"]
    versions = await _versions()
    for key in ("hc_tool", "fieldworks_hermitcrab", "generate_hc_config"):
        assert versions[key], f"{key} version not reported: {detected}"
    skewed = parser_probe.hermitcrab_versions_differ(
        versions["hc_tool"], versions["fieldworks_hermitcrab"]
    )
    has_advisory = parser_probe.ADVISORY_HC_ENGINE_VERSION_SKEW in parser["sandbox"]["advisories"]
    assert has_advisory == bool(skewed), parser["sandbox"]
    steps = health.get("parser_next_steps") or []
    assert _names_tool(steps, "flextools_parse_sandbox"), steps

    await _evidence(
        "S3", "health-ready",
        responses={"health_parser": parser, "health_parser_next_steps": steps},
        observations={"skewed": bool(skewed)},
    )


# ===========================================================================
# S4-S5: parse words from the project cache (US2)
# ===========================================================================


def _assert_s4_shape(response: Dict[str, Any], words: List[str]) -> List[Dict[str, Any]]:
    assert response.get("status") != "error", response
    assert response.get("stage") == "completed", response
    assert response.get("spine") == "sandbox", response
    assert response.get("results_label"), response
    lines = _results(response)
    sent = [ln.get("wordform") for ln in lines]
    assert sorted(sent) == sorted(set(words)), f"one result per word: {sent}"
    by_word = {ln.get("wordform"): ln for ln in lines}
    if APOSTROPHE_WORD in by_word:
        assert _outcome(by_word[APOSTROPHE_WORD]) != "not_expressible", by_word[APOSTROPHE_WORD]
    if BOTH_QUOTES_WORD in by_word:
        assert _outcome(by_word[BOTH_QUOTES_WORD]) == "not_expressible", by_word[BOTH_QUOTES_WORD]
    assert not response.get("counter_divergences"), response.get("counter_divergences")
    return lines


async def test_s4_parse_words(sandbox_home):
    """S4: one result per word, the apostrophe word is one word, the
    both-quotes word is `not_expressible`, no "invalid segment at position
    1", the counters agree, the project is untouched, `work/` is empty."""
    _require_sandbox_spine()
    folder = _project_dir(HC_PROJECT)
    words = _s4_words()
    guard = ProjectGuard(folder)
    async with live_runner(sandbox_home):
        started = time.monotonic()
        response = await _parse(HC_PROJECT, words)
        wall = time.monotonic() - started
        lines = _assert_s4_shape(response, words)
        stdout = await _log(_run_id(response), "hc_stdout")
    assert "invalid segment at position 1" not in json.dumps(stdout).lower(), stdout
    assert _work_entries() == [], _work_entries()
    guard.check()

    await _evidence(
        "S4", "parse-words", project=HC_PROJECT, hashes=[guard],
        responses={"parse": response, "hc_stdout": stdout},
        observations={"words": words, "results": lines, "wall_seconds": wall},
    )


async def test_s5_warm_cache(sandbox_home):
    """S5: a repeat reuses the cache and takes at most half the cold wall time (SC-006)."""
    _require_sandbox_spine()
    folder = _project_dir(HC_PROJECT)
    from flextoolsmcp.server.sandbox import cache as sandbox_cache

    words = _s4_words()
    guard = ProjectGuard(folder)
    async with live_runner(sandbox_home):
        sandbox_cache.invalidate(HC_PROJECT)
        t0 = time.monotonic()
        cold = await _parse(HC_PROJECT, words)
        cold_wall = time.monotonic() - t0
        t1 = time.monotonic()
        warm = await _parse(HC_PROJECT, words)
        warm_wall = time.monotonic() - t1
    _assert_s4_shape(cold, words)
    _assert_s4_shape(warm, words)
    assert (cold.get("generation") or {}).get("reused_cache") is False, cold.get("generation")
    assert (warm.get("generation") or {}).get("reused_cache") is True, warm.get("generation")
    assert warm_wall <= cold_wall / 2, (cold_wall, warm_wall)
    assert _work_entries() == []
    guard.check()

    await _evidence(
        "S5", "warm-cache", project=HC_PROJECT, hashes=[guard],
        responses={"cold": cold, "warm": warm},
        observations={"cold_wall_seconds": cold_wall, "warm_wall_seconds": warm_wall},
    )


# ===========================================================================
# S6: rehearse a change in a named sandbox (US3)
# ===========================================================================


def _loosen_first_left_environment(config: Path) -> Optional[str]:
    """Empty the first `LeftEnvironment` in a sandbox's XML; return its old text."""
    tree = ET.parse(config)
    for elem in tree.iter():
        if elem.tag.endswith("LeftEnvironment") and len(elem):
            before = ET.tostring(elem, encoding="unicode")
            for child in list(elem):
                elem.remove(child)
            tree.write(config, encoding="utf-8", xml_declaration=True)
            return before
    return None


async def test_s6_sandbox_rehearse(sandbox_home):
    """S6: create `tighten-env`, edit one LeftEnvironment, run S4's words,
    diff against the project-cache run; the sandbox is outside the project
    and a second create with the same name is refused."""
    _require_sandbox_spine()
    folder = _project_dir(HC_PROJECT)
    name = "tighten-env"
    words = _s4_words()
    guard = ProjectGuard(folder)
    async with live_runner(sandbox_home):
        baseline = await _parse(HC_PROJECT, words)
        created = await _sandbox(action="create_sandbox", project_name=HC_PROJECT, sandbox=name)
        assert created.get("status") == "ok", created
        config = Path(created["path"])
        assert not sandbox_paths.is_under(config, folder), config
        assert not sandbox_paths.is_under(config, _projects_root()), config
        assert isinstance(created.get("next_step"), list) and created["next_step"], created
        edited = _loosen_first_left_environment(config)
        rehearsed = await _parse(HC_PROJECT, words, sandbox=name)
        diff = await _diff(_run_id(baseline), _run_id(rehearsed))
        again = await _sandbox(action="create_sandbox", project_name=HC_PROJECT, sandbox=name)
    assert rehearsed.get("stage") == "completed", rehearsed
    assert diff.get("status") != "error", diff
    assert again.get("error_code") == "parse_sandbox_refused", again
    assert again.get("reason") == "sandbox_exists", again
    guard.check()

    await _evidence(
        "S6", "sandbox-rehearse", project=HC_PROJECT, hashes=[guard],
        responses={"baseline": baseline, "create": created, "rehearsed": rehearsed,
                   "diff": diff, "create_again": again},
        observations={"edited_left_environment": edited,
                      "diff_shows_change_needs_human_review": True},
    )


# ===========================================================================
# S7 (+ L-7): the project held by FLEx
# ===========================================================================


async def test_s7_held_by_flex_and_l7(sandbox_home):
    """S7 / L-7: with FLEx holding the project (a human opens it first and
    sets FLEXTOOLSMCP_CP5_S7_HELD=shared|exclusive), the run proceeds from a
    copy; sharing on gives `staleness: shared_mode_unverifiable`. The
    observation answers L-7 (stream read and copy while held)."""
    _require_sandbox_spine()
    folder = _project_dir(HC_PROJECT)
    held = _require_env("FLEXTOOLSMCP_CP5_S7_HELD",
                        "a human must open the project in FLEx first (shared or exclusive)")
    guard = ProjectGuard(folder)
    async with live_runner(sandbox_home):
        response = await _parse(HC_PROJECT, _s4_words()[:3])
    guard.check()
    observations = {
        "held_mode": held,
        "locks_seen": guard.before["locks"],
        "stage": response.get("stage"),
        "error_code": response.get("error_code"),
        "staleness": response.get("staleness"),
        "project_state": response.get("project_state"),
    }
    await _evidence("S7", "held-by-flex", project=HC_PROJECT, hashes=[guard],
                    responses={"parse": response}, observations=observations)
    await _evidence("L-7", "stream-read-while-held", project=HC_PROJECT, hashes=[guard],
                    responses={"parse": response}, observations=observations,
                    needs_human=True)
    assert response.get("stage") == "completed", response
    if held == "shared":
        assert response.get("staleness") == "shared_mode_unverifiable", response


# ===========================================================================
# S8: corpus regression and new ambiguity (US4)
# ===========================================================================


async def test_s8_corpus_regression_and_ambiguity(sandbox_home):
    """S8: seed a corpus from an S4 run, run it against a human-edited
    sandbox (FLEXTOOLSMCP_CP5_S8_SANDBOX) where word A lost its only parse
    and word B gained one: exactly one regression (A) and one new ambiguity
    (B); the totals equal `stats -t`."""
    _require_sandbox_spine()
    folder = _project_dir(HC_PROJECT)
    sandbox = _require_env("FLEXTOOLSMCP_CP5_S8_SANDBOX", "a human-edited sandbox for S8")
    word_a = _require_env("FLEXTOOLSMCP_CP5_S8_REGRESSION_WORD", "S8's word A")
    word_b = _require_env("FLEXTOOLSMCP_CP5_S8_AMBIGUITY_WORD", "S8's word B")
    corpus = f"s8-{int(time.time())}"
    guard = ProjectGuard(folder)
    async with live_runner(sandbox_home):
        seed_run = await _parse(HC_PROJECT, _s4_words() + [word_a, word_b])
        seeded = await _sandbox(action="seed_corpus", project_name=HC_PROJECT,
                                corpus=corpus, from_run_id=_run_id(seed_run))
        assert seeded.get("status") == "ok", seeded
        ran = await _finish(await _sandbox(action="run_corpus", project_name=HC_PROJECT,
                                           corpus=corpus, sandbox=sandbox))
    lines = _results(ran)
    classes: Dict[str, List[str]] = {}
    for line in lines:
        assertion = line.get("assertion") or {}
        cls = assertion.get("class") or assertion.get("classification")
        if cls:
            classes.setdefault(cls, []).append(line.get("wordform"))
    assert classes.get("regression") == [word_a], classes
    assert classes.get("new_ambiguity") == [word_b], classes
    assert not ran.get("counter_divergences"), ran.get("counter_divergences")
    guard.check()

    await _evidence(
        "S8", "corpus-regression-ambiguity", project=HC_PROJECT, hashes=[guard],
        responses={"seed_run": seed_run, "seed_corpus": seeded, "run_corpus": ran},
        observations={"classes": classes, "results": lines},
    )


# ===========================================================================
# S9: cache invalidation after a write; the sandbox is untouched (US6, FR-026)
# ===========================================================================


_S9_WRITE = """
entries = project.LexEntry.GetAll()
entry = entries[0]
if modifyAllowed:
    project.LexEntry.SetComment(entry, "CP5 S9 cache invalidation probe")
report.Info("wrote comment on " + project.LexEntry.GetLexemeForm(entry))
"""


async def test_s9_invalidation_sandbox_untouched(sandbox_home):
    """S9 (WRITES, scratch copy only, opt-in): create sandbox X, warm the
    cache, write through `run_module`, run again: the cache entry is
    regenerated and X is byte-identical (SC-007). The source is untouched."""
    _require_sandbox_spine()
    _require_write_opt_in()
    source_folder = _project_dir(HC_PROJECT)
    root = _projects_root()
    from flextoolsmcp.server.handlers import execution

    source_guard = ProjectGuard(source_folder)
    copy = make_disposable(HC_PROJECT, root=root, prefix=CP5_SCRATCH_PREFIX)
    try:
        name = require_disposable(copy.name, CP5_SCRATCH_PREFIX)
        words = _s4_words()[:4]
        async with live_runner(sandbox_home):
            created = await _sandbox(action="create_sandbox", project_name=name, sandbox="x")
            assert created.get("status") == "ok", created
            sandbox_dir = Path(created["path"]).parent
            sandbox_guard = ProjectGuard(sandbox_dir)
            warm = await _parse(name, words)
            warm2 = await _parse(name, words)
            wrote = await _call(execution.handle_run_module, code=_S9_WRITE,
                                project_name=name, write_enabled=True, confirmed=True)
            assert wrote.get("status") == "ok", wrote
            after = await _parse(name, words)
            on_sandbox = await _parse(name, words, sandbox="x")
        assert (warm2.get("generation") or {}).get("reused_cache") is True, warm2
        assert (after.get("generation") or {}).get("reused_cache") is False, after
        key_before = (warm2.get("config_source") or {}).get("cache_key")
        key_after = (after.get("config_source") or {}).get("cache_key")
        assert key_before and key_after and key_before != key_after, (key_before, key_after)
        assert on_sandbox.get("stage") == "completed", on_sandbox
        sandbox_guard.check()
        source_guard.check()
        await _evidence(
            "S9", "invalidation-sandbox-untouched", project=name,
            hashes=[source_guard, sandbox_guard],
            responses={"create": created, "warm": warm, "warm2": warm2, "write": wrote,
                       "after_write": after, "on_sandbox": on_sandbox},
            observations={"cache_key_before": key_before, "cache_key_after": key_after,
                          "source": HC_PROJECT},
        )
    finally:
        if os.environ.get("FLEXTOOLSMCP_LIVE_KEEP_SCRATCH") != "1":
            delete_disposable(copy.name, root=root, prefix=CP5_SCRATCH_PREFIX)


# ===========================================================================
# S10: timeout with partial results (US5, FR-020)
# ===========================================================================


async def test_s10_timeout_partial(sandbox_home):
    """S10: the Malay project, 100 words, a timeout cutting the run early:
    `parser_timeout`, a partial `words_completed`, the in-flight word named,
    the completed results readable through `parse_log`, `work/` empty."""
    _require_sandbox_spine()
    folder = _project_dir(SCALE_PROJECT)
    words = _fwdata_wordforms(folder / f"{SCALE_PROJECT}.fwdata", 100)
    if len(words) < 100:
        _missing(f"{SCALE_PROJECT} has fewer than 100 wordforms ({len(words)})")
    timeout = int(os.environ.get("FLEXTOOLSMCP_CP5_S10_TIMEOUT", "10"))
    guard = ProjectGuard(folder)
    async with live_runner(sandbox_home):
        # Warm the cache first so the bound cuts parsing, not generation.
        warm = await _parse(SCALE_PROJECT, words[:1])
        response = await _parse(SCALE_PROJECT, words, timeout_seconds=timeout)
        run_id = _run_id(response) or response.get("run_id")
        status = await _status(run_id) if run_id else None
        results = await _log(run_id, "results") if run_id else None
    assert response.get("error_code") == "parser_timeout" or (
        (response.get("failure") or {}).get("error_code") == "parser_timeout"
    ), response
    completed = response.get("words_completed")
    assert isinstance(completed, int) and completed < len(words), response
    assert results and results.get("status") != "error", results
    assert _work_entries() == [], _work_entries()
    guard.check()

    await _evidence(
        "S10", "timeout-partial", project=SCALE_PROJECT, hashes=[guard],
        responses={"warm": warm, "parse": response, "status": status, "results": results},
        observations={"timeout_seconds": timeout, "words_total": len(words),
                      "words_completed": completed,
                      "in_flight": (status or {}).get("in_flight")},
    )


# ===========================================================================
# S11: a hand-broken sandbox (US5)
# ===========================================================================


async def test_s11_broken_sandbox(sandbox_home):
    """S11: a broken sandbox XML fails the run with hc's `Load Error:` in
    `hc_stdout` and zero parse results."""
    _require_sandbox_spine()
    folder = _project_dir(HC_PROJECT)
    name = f"broken-{int(time.time())}"
    guard = ProjectGuard(folder)
    async with live_runner(sandbox_home):
        created = await _sandbox(action="create_sandbox", project_name=HC_PROJECT, sandbox=name)
        assert created.get("status") == "ok", created
        config = Path(created["path"])
        text = config.read_text(encoding="utf-8")
        config.write_text(text[: len(text) // 2], encoding="utf-8")  # truncated XML
        response = await _parse(HC_PROJECT, _s4_words()[:3], sandbox=name)
        run_id = _run_id(response)
        stdout = await _log(run_id, "hc_stdout") if run_id else None
    failed = response.get("status") == "error" or response.get("stage") == "failed"
    assert failed, response
    assert "Load Error" in json.dumps(stdout or response, ensure_ascii=False), (stdout, response)
    assert not [ln for ln in _results(response) if _outcome(ln) == "parsed"]
    guard.check()

    await _evidence(
        "S11", "broken-sandbox", project=HC_PROJECT, hashes=[guard],
        responses={"create": created, "parse": response, "hc_stdout": stdout},
    )


# ===========================================================================
# S12: the XAmple project is refused before any copy (US2)
# ===========================================================================


async def test_s12_xample_refused(sandbox_home):
    """S12: `Sena 3` gets `parser_engine_mismatch` before any copy. The
    project is not opened: the hash is identical and no lock file appears
    during the call. (Step 3 checks the tools before step 4 reads the
    engine, so this needs the working spine.)"""
    _require_sandbox_spine()
    folder = _project_dir(XAMPLE_PROJECT)
    guard = ProjectGuard(folder)
    work_before = _work_entries()
    async with live_runner(sandbox_home):
        with LockWatch(folder) as watch:
            response = await _sandbox(action="parse", project_name=XAMPLE_PROJECT,
                                      words=["kudya"])
    assert response.get("error_code") == "parser_engine_mismatch", response
    assert response.get("configured_engine") != "HC", response
    assert not watch.seen, f"lock files appeared during the call: {watch.seen}"
    assert _work_entries() == work_before, "a copy was started for an XAmple project"
    guard.check()

    await _evidence(
        "S12", "xample-refused", project=XAMPLE_PROJECT, hashes=[guard],
        responses={"parse": response},
        observations={"locks_seen_during_call": sorted(watch.seen)},
    )


# ===========================================================================
# S13: the orphaned work directory is swept (US6)
# ===========================================================================


_S13_CHILD = r"""
import asyncio, json, sys
sys.path.insert(0, sys.argv[1])
from flextoolsmcp.server.handlers import parse as p
from flextoolsmcp.server.parse.runner import ParseRunner
async def main():
    p.set_runner(ParseRunner(record_dir=sys.argv[2]))
    words = json.loads(open(sys.argv[4], encoding="utf-8").read())
    r = await p.handle_flextools_parse_sandbox(
        {"action": "parse", "project_name": sys.argv[3], "words": words})
    print(r[0].text, flush=True)
    await asyncio.sleep(3600)
asyncio.run(main())
"""


async def test_s13_orphan_sweep(sandbox_home):
    """S13: a server killed mid-run leaves `work/<id>`; the next sandbox job
    in a fresh server removes it."""
    _require_sandbox_spine()
    folder = _project_dir(HC_PROJECT)
    words = _fwdata_wordforms(folder / f"{HC_PROJECT}.fwdata", 3000) or _s4_words()
    word_file = sandbox_home / "s13-words.json"
    word_file.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    guard = ProjectGuard(folder)
    before = set(_work_entries())
    child = subprocess.Popen(
        [sys.executable, "-c", _S13_CHILD, str(REPO_ROOT / "src"),
         str(sandbox_home / "runs-child"), HC_PROJECT, str(word_file)],
        env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    orphans: List[str] = []
    try:
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline and child.poll() is None:
            orphans = sorted(set(_work_entries()) - before)
            if orphans:
                break
            await asyncio.sleep(0.2)
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(child.pid)],
                       capture_output=True, check=False)
        child.wait(timeout=60)
    if not orphans:
        pytest.fail("the child server never created a work directory to orphan")
    assert set(orphans) <= set(_work_entries()), "the kill left no orphan to sweep"

    async with live_runner(sandbox_home):
        after_run = await _parse(HC_PROJECT, _s4_words()[:2])
    remaining = sorted(set(orphans) & set(_work_entries()))
    assert remaining == [], f"orphaned work dirs survived the sweep: {remaining}"
    guard.check()

    await _evidence(
        "S13", "orphan-sweep", project=HC_PROJECT, hashes=[guard],
        responses={"next_run": after_run},
        observations={"orphans": orphans, "remaining": remaining},
    )


# ===========================================================================
# L-1..L-6: live questions (recorded; a human answers them in T095)
# ===========================================================================


def _run_generator(generator: Path, fwdata: Path, out: Path, timeout: int = 900) -> Dict[str, Any]:
    completed = subprocess.run(
        [str(generator), str(fwdata), str(out)],
        capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
    )
    return {
        "exit_code": completed.returncode,
        "output": (completed.stdout + completed.stderr).decode("utf-8", "replace")[-4000:],
        "config_bytes": out.stat().st_size if out.is_file() else None,
        "config_sha256": hashlib.sha256(out.read_bytes()).hexdigest() if out.is_file() else None,
    }


def _copy_project(src: Path, dest: Path, allow: Optional[Iterable[str]] = None) -> None:
    """Copy a project folder OUTSIDE the projects directory (read-only on
    the source). `allow` limits the copy to the .fwdata plus those dirs."""
    dest.mkdir(parents=True)
    name = src.name
    shutil.copy2(src / f"{name}.fwdata", dest / f"{name}.fwdata")
    for child in src.iterdir():
        if child.name.endswith(".lock") or child.name == ".hg" or child.suffix == ".fwdata":
            continue
        if allow is not None and child.name not in allow:
            continue
        if child.is_dir():
            shutil.copytree(child, dest / child.name,
                            ignore=shutil.ignore_patterns("*.lock", ".hg"))
        else:
            shutil.copy2(child, dest / child.name)


async def test_l1_generator_allowlist(sandbox_home):
    """L-1: does GenerateHCConfig need more than `.fwdata` + WritingSystemStore?
    Generates from an allowlist copy and from a full copy (both outside the
    projects directory) and records whether the configs are identical."""
    _require_working_hc()
    ghc = _require_generator()
    folder = _project_dir(HC_PROJECT)
    from flextoolsmcp.server.sandbox import workdir

    guard = ProjectGuard(folder)
    base = sandbox_home / "l1"
    runs: Dict[str, Any] = {}
    for label, allow in (("allowlist", workdir.ALLOWLIST_DIRS), ("full", None)):
        dest = base / label / HC_PROJECT
        _copy_project(folder, dest, allow)
        runs[label] = _run_generator(Path(ghc.expected_path),
                                     dest / f"{HC_PROJECT}.fwdata",
                                     base / label / "hc-config.xml")
    guard.check()
    await _evidence(
        "L-1", "generator-allowlist", project=HC_PROJECT, hashes=[guard],
        observations={
            "allowlist": list(workdir.ALLOWLIST_DIRS), "runs": runs,
            "identical": runs["allowlist"]["config_sha256"] == runs["full"]["config_sha256"],
        },
        needs_human=True,
    )


async def test_l2_leading_dash(sandbox_home):
    """L-2: does a word beginning with `-` reach `parse` intact?"""
    _require_sandbox_spine()
    folder = _project_dir(HC_PROJECT)
    word = os.environ.get("FLEXTOOLSMCP_CP5_L2_WORD", "-an")
    guard = ProjectGuard(folder)
    async with live_runner(sandbox_home):
        response = await _parse(HC_PROJECT, [word])
        stdout = await _log(_run_id(response), "hc_stdout") if _run_id(response) else None
    guard.check()
    await _evidence(
        "L-2", "leading-dash", project=HC_PROJECT, hashes=[guard],
        responses={"parse": response, "hc_stdout": stdout},
        observations={"word": word, "results": _results(response),
                      "test_half": "needs a corpus assertion (run_corpus) with the same word"},
        needs_human=True,
    )


async def test_l3_stdout_bom(sandbox_home):
    """L-3: does piped hc stdout carry a UTF-16 BOM, and does PowerShell 5.1
    decode it cleanly? Records `run.json.hc.stdout_bom` and `hc-stdout.txt`."""
    _require_sandbox_spine()
    folder = _project_dir(HC_PROJECT)
    word = os.environ.get("FLEXTOOLSMCP_CP5_L3_WORD", "ماكان")
    guard = ProjectGuard(folder)
    async with live_runner(sandbox_home):
        response = await _parse(HC_PROJECT, [word])
    guard.check()
    record = _record_dir(response)
    run_json = stdout_text = None
    if record is not None:
        with contextlib.suppress(OSError, ValueError):
            run_json = json.loads((record / "sandbox" / "run.json").read_text(encoding="utf-8"))
        with contextlib.suppress(OSError):
            stdout_text = (record / "sandbox" / "hc-stdout.txt").read_text(encoding="utf-8")
    await _evidence(
        "L-3", "stdout-bom", project=HC_PROJECT, hashes=[guard],
        responses={"parse": response},
        observations={"word": word, "stdout_bom": ((run_json or {}).get("hc") or {}).get("stdout_bom"),
                      "hc_stdout_txt": stdout_text,
                      "word_round_trips": bool(stdout_text and word in stdout_text)},
        needs_human=True,
    )


async def test_l4_generation_offline(sandbox_home):
    """L-4: does GenerateHCConfig hang offline (SLDR)? A human disables the
    network and sets FLEXTOOLSMCP_CP5_L4_OFFLINE=1; generation is timed."""
    _require_sandbox_spine()
    folder = _project_dir(HC_PROJECT)
    _require_env("FLEXTOOLSMCP_CP5_L4_OFFLINE", "a human must disable the network first")
    from flextoolsmcp.server.sandbox import cache as sandbox_cache

    guard = ProjectGuard(folder)
    async with live_runner(sandbox_home):
        sandbox_cache.invalidate(HC_PROJECT)
        t0 = time.monotonic()
        response = await _parse(HC_PROJECT, _s4_words()[:1])
        wall = time.monotonic() - t0
    guard.check()
    await _evidence(
        "L-4", "generation-offline", project=HC_PROJECT, hashes=[guard],
        responses={"parse": response},
        observations={"wall_seconds": wall, "generation": response.get("generation")},
        needs_human=True,
    )


async def test_l5_runtime_missing_text(sandbox_home):
    """L-5: what does the .NET host print when hc's runtime is missing?
    Runs exactly `hc -h` (the R-04 shape) on the discovered hc, or on
    FLEXTOOLSMCP_CP5_L5_HC, and records exit code and both streams."""
    override = os.environ.get("FLEXTOOLSMCP_CP5_L5_HC")
    path = override or _hc().path
    if not path or not Path(path).is_file():
        _missing("L-5 needs an hc binary (discovered, or FLEXTOOLSMCP_CP5_L5_HC)")
    argv = parser_probe.hc_invoke_argv(path) + ["-h"]
    completed = subprocess.run(argv, capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
    stdout = completed.stdout
    await _evidence(
        "L-5", "runtime-missing-text",
        observations={
            "argv": argv,
            "exit_code": completed.returncode,
            "exit_code_hex": f"0x{completed.returncode & 0xFFFFFFFF:08X}",
            "stdout_utf16le": stdout.decode("utf-16-le", "replace")[-4000:],
            "stdout_bom": stdout[:2] == b"\xff\xfe",
            "stderr_utf8": completed.stderr.decode("utf-8", "replace")[-4000:],
            "probe": _as_dict(parser_probe.probe_hc(path)),
        },
        needs_human=True,
    )


async def test_l6_sandbox_matches_try_word(sandbox_home):
    """L-6 (scratch copy, opt-in): at matching HermitCrab versions, do the
    sandbox's results equal Try A Word's (SC-003)? Records both for 20 words."""
    _require_sandbox_spine()
    _require_write_opt_in()
    source_folder = _project_dir(HC_PROJECT)
    root = _projects_root()
    words = _fwdata_wordforms(source_folder / f"{HC_PROJECT}.fwdata", 20)
    source_guard = ProjectGuard(source_folder)
    copy = make_disposable(HC_PROJECT, root=root, prefix=CP5_SCRATCH_PREFIX)
    try:
        name = require_disposable(copy.name, CP5_SCRATCH_PREFIX)
        async with live_runner(sandbox_home):
            sandbox_run = await _parse(name, words)
            try_word = {}
            for word in words:
                try_word[word] = await _call(parse_handler.handle_flextools_try_word,
                                             word=word, project_name=name)
        by_word = {ln.get("wordform"): ln for ln in _results(sandbox_run)}
        comparison = {
            w: {"sandbox_parsed": (by_word.get(w, {}).get("parse") or {}).get("parsed"),
                "try_word_status": try_word[w].get("status"),
                "try_word_parsed": try_word[w].get("parsed")}
            for w in words
        }
        source_guard.check()
        await _evidence(
            "L-6", "sandbox-vs-try-word", project=name, hashes=[source_guard],
            responses={"sandbox": sandbox_run, "try_word": try_word},
            observations={"comparison": comparison, "source": HC_PROJECT},
            needs_human=True,
        )
    finally:
        if os.environ.get("FLEXTOOLSMCP_LIVE_KEEP_SCRATCH") != "1":
            delete_disposable(copy.name, root=root, prefix=CP5_SCRATCH_PREFIX)
