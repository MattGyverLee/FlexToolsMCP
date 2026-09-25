#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The CP5 sandbox spine, against live FieldWorks projects and FieldWorks' own
bundled HermitCrab (parser-check CP5; specs/parser-check-cp5/quickstart.md,
tasks T091/T094/T095, rewritten for the in-process re-plan by T110).

WHAT THIS MODULE SPECIFIES. It drives the REAL handlers, in process, exactly
as a client would call them -- `handle_flextools_parse_sandbox` (all five
actions), `handle_flextools_health`, and the run tools
`handle_flextools_parse_status` / `_log` / `_diff` -- against the `--sandbox`
parse worker, which loads FieldWorks' bundled HermitCrab DLL via pythonnet.
There is no `hc` console tool any more (D7), so the scenarios that probed
one (the old S1, S2, L-3 and L-5) are gone.

SCRATCH COPIES ONLY (T110). Every scenario reads a `CP5-Scratch-` copy made
by `tests/live_support/make_disposable.py`, never a working project. The
source project is byte-hashed before its copy is made and again when the copy
is deleted, and every sandbox scenario byte-hashes the SCRATCH folder before
and after too (FR-043, SC-001): the sandbox never writes the project it reads.
`*.lock` files are listed rather than hashed.

  * The sandbox-only scenarios share one module-scoped copy per source.
  * A scenario that opens a project with LCM -- the parity comparison
    (SC-003), the id-map validation (D4/R-17), S9's write -- takes a copy of
    its own, since an LCM open may rewrite the `.fwdata` and would move the
    shared copy's cache key under the other scenarios.
  * S9 writes (to its own copy) only with `FLEXTOOLSMCP_CP5_LIVE_WRITE=1`.
  * S12 is the one exception to "copy first": it proves the XAmple refusal
    happens before any copy or open, so it points at `Sena 3` itself and
    asserts the folder is byte-identical and no lock appeared.

THE DESIGNATED PROJECTS (quickstart "Projects"):

    IndonesianHC-Complete           correctness, corpus, parity, isolation
    Circumsanity                    FR-050 circumfix shaping, id-map check
    Malay Parsing-20230810withHC    timeout and scale (S10)
    Sena 3                          the XAmple refusal ONLY (S12)

THE LIVE GATE. Marked `requires_flex`. A missing prerequisite -- Windows,
FieldWorks' projects directory, a designated project, the bundled HermitCrab,
GenerateHCConfig.exe, or a human-prepared setup (S7, L-4) -- SKIPS, unless
`FLEXLIBS_REQUIRE_LIVE=1`, in which case it FAILS.

ISOLATION. The sandbox root (`FLEXTOOLSMCP_PARSE_SANDBOX_DIR`) and the run
records live in a per-module temporary directory, never under
`~/.flextoolsmcp` and never under a project folder.

EVIDENCE goes to `specs/parser-check-cp5/evidence/<id>-<slug>.json`, written
only after a scenario's assertions pass. Each file records the scenario id,
the bundled HermitCrab's and GenerateHCConfig's `FileVersion` (FR-045), the
before/after hashes, and response excerpts.

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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

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

from flextoolsmcp.server import parser_probe, project_discovery  # noqa: E402
from flextoolsmcp.server.handlers import diagnostic_health  # noqa: E402
from flextoolsmcp.server.handlers import parse as parse_handler  # noqa: E402
from flextoolsmcp.server.parse.runner import ParseRunner  # noqa: E402
from flextoolsmcp.server.sandbox import paths as sandbox_paths  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: The correctness source.
HC_PROJECT = os.environ.get("FLEXTOOLSMCP_LIVE_HC_PROJECT", "IndonesianHC-Complete")

#: The circumfix source (FR-050 rules b/c, the id-map check).
CIRCUMFIX_PROJECT = os.environ.get("FLEXTOOLSMCP_LIVE_CIRCUMFIX_PROJECT", "Circumsanity")

#: The timeout / scale source (S10).
SCALE_PROJECT = os.environ.get(
    "FLEXTOOLSMCP_LIVE_SCALE_PROJECT", "Malay Parsing-20230810withHC"
)

#: The XAmple project. Used ONLY for S12's refusal; never opened, never copied.
XAMPLE_PROJECT = "Sena 3"

#: The opt-in for S9, which writes to its own scratch copy.
LIVE_WRITE_ENV = "FLEXTOOLSMCP_CP5_LIVE_WRITE"

EVIDENCE_DIR = REPO_ROOT / "specs" / "parser-check-cp5" / "evidence"

#: S4's word list for IndonesianHC-Complete, whose vernacular is IPA: a root,
#: the same root under the nasal prefix (the prefix replaces its first
#: segment), IPA roots, an apostrophe word (one word, one result, FR-045) and
#: a word outside the orthography. Override with a JSON list for another
#: project.
_DEFAULT_S4_WORDS = [
    "pukul", "memukul", "dɑlɑm", "mɑnis", "ɑnɑk", "wɑkil", "ma'af", "xqzvbw",
]
APOSTROPHE_WORD = os.environ.get("FLEXTOOLSMCP_CP5_APOSTROPHE_WORD", "ma'af")

#: What S4 expects of the root and its prefixed form (IndonesianHC-Complete).
ROOT_WORD = os.environ.get("FLEXTOOLSMCP_CP5_ROOT_WORD", "pukul")
PREFIXED_WORD = os.environ.get("FLEXTOOLSMCP_CP5_PREFIXED_WORD", "memukul")
ROOT_GLOSS = os.environ.get("FLEXTOOLSMCP_CP5_ROOT_GLOSS", "hit")

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


def _require_working_engine():
    engine = parser_probe.discover_fieldworks_hermitcrab()
    if not engine.found:
        _missing(
            "FieldWorks' bundled HermitCrab is required: "
            f"found={engine.found} reason={engine.reason!r}"
        )
    return engine


def _require_generator():
    ghc = parser_probe.discover_generate_hc_config()
    if not ghc.ok:
        _missing(f"GenerateHCConfig.exe not found (expected {ghc.expected_path})")
    return ghc


def _require_sandbox_spine():
    return _require_working_engine(), _require_generator()


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
    """S12's project must not be reachable as any designated source."""
    assert XAMPLE_PROJECT not in (HC_PROJECT, CIRCUMFIX_PROJECT, SCALE_PROJECT)


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
# Scratch copies (T110: scratch copies only)
# ---------------------------------------------------------------------------


@dataclass
class Scratch:
    name: str
    folder: Path
    source: str
    source_guard: ProjectGuard

    @property
    def fwdata(self) -> Path:
        return self.folder / f"{self.name}.fwdata"


def _keep_scratch() -> bool:
    return os.environ.get("FLEXTOOLSMCP_LIVE_KEEP_SCRATCH") == "1"


@contextlib.contextmanager
def scratch_copy(source: str) -> Iterator[Scratch]:
    """A `CP5-Scratch-` copy of `source`; the source is hashed around it and
    the copy is deleted afterwards (unless FLEXTOOLSMCP_LIVE_KEEP_SCRATCH=1)."""
    folder = _project_dir(source)
    root = _projects_root()
    source_guard = ProjectGuard(folder)
    copy = make_disposable(source, root=root, prefix=CP5_SCRATCH_PREFIX)
    name = require_disposable(copy.name, CP5_SCRATCH_PREFIX)
    # The project listing is cached for a few seconds; a copy made just now
    # must be visible to the handlers at once.
    project_discovery.clear_cache()
    try:
        yield Scratch(name=name, folder=copy.path, source=source, source_guard=source_guard)
    finally:
        if not _keep_scratch():
            delete_disposable(name, root=root, prefix=CP5_SCRATCH_PREFIX)
            assert not copy.path.exists(), f"the scratch copy {copy.path} was left behind"
        source_guard.check()


@pytest.fixture(scope="module")
def hc_scratch():
    """The shared, sandbox-only copy of the correctness source."""
    _require_sandbox_spine()
    with scratch_copy(HC_PROJECT) as scratch:
        yield scratch


@pytest.fixture(scope="module")
def circumfix_scratch():
    _require_sandbox_spine()
    with scratch_copy(CIRCUMFIX_PROJECT) as scratch:
        yield scratch


@pytest.fixture(scope="module")
def scale_scratch():
    _require_sandbox_spine()
    with scratch_copy(SCALE_PROJECT) as scratch:
        yield scratch


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

_VERSIONS: Dict[str, Any] = {}


async def _versions() -> Dict[str, Any]:
    """The bundled HermitCrab's and GenerateHCConfig's FileVersions (FR-045),
    as health reports them (read once)."""
    if not _VERSIONS:
        detected = (await _health())["parser"]["detected"]
        _VERSIONS.update({
            "fieldworks_hermitcrab": detected.get("fieldworks_hermitcrab_version"),
            "generate_hc_config": detected.get("generate_hc_config_version"),
            "fieldworks_hermitcrab_path": detected.get("fieldworks_hermitcrab_path"),
        })
    return dict(_VERSIONS)


_EXCERPT_DROP = ("_contract", "error", "session", "libraries", "indexes", "logs", "server",
                 "workspace_notice")


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
    source: Optional[str] = None,
    hashes: Optional[Iterable[ProjectGuard]] = None,
    responses: Optional[Dict[str, Any]] = None,
    observations: Optional[Dict[str, Any]] = None,
    needs_human: bool = False,
) -> Path:
    """Write one scenario's evidence beside the spec (never in a project)."""
    versions = await _versions()
    assert versions.get("fieldworks_hermitcrab") and versions.get("generate_hc_config"), (
        f"FR-045: both FileVersions must be recorded in every evidence file: {versions}"
    )
    payload = {
        "scenario": scenario,
        "project": project,
        "source_project": source,
        "versions": versions,
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
            status.setdefault("record_dir", response.get("record_dir"))
            return status
        await asyncio.sleep(0.05)
    pytest.fail(f"run {response['run_id']} did not finish within {timeout}s: {status}")


async def _parse(project: str, words, **args) -> Dict[str, Any]:
    started = await _sandbox(action="parse", project_name=project, words=words, **args)
    finished = await _finish(started)
    if finished is not started:
        finished.setdefault("_submitted", started)
    return finished


def _submitted(response: Dict[str, Any]) -> Dict[str, Any]:
    """The submission response of a run (the response itself when the run
    was already terminal on submission)."""
    return response.get("_submitted") or response


def _record_dir(response: Dict[str, Any]) -> Optional[Path]:
    record = response.get("record_dir") or response.get("_submitted", {}).get("record_dir")
    return Path(record) if record else None


def _results(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    record = _record_dir(response)
    if record is None:
        return []
    path = record / "results.jsonl"
    lines = []
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            with contextlib.suppress(json.JSONDecodeError):
                lines.append(json.loads(raw))
    return lines


def _by_word(response: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {ln.get("wordform"): ln for ln in _results(response)}


def _record_json(response: Dict[str, Any], *parts: str) -> Optional[Any]:
    record = _record_dir(response)
    if record is None:
        return None
    with contextlib.suppress(OSError, ValueError):
        return json.loads(record.joinpath(*parts).read_text(encoding="utf-8"))
    return None


def _meta_sandbox(response: Dict[str, Any]) -> Dict[str, Any]:
    """`meta.sandbox` as the run recorded it (data-model section 6)."""
    return (_record_json(response, "meta.json") or {}).get("sandbox") or {}


def _outcome(line: Dict[str, Any]) -> Optional[str]:
    return (line.get("parse") or {}).get("outcome") or line.get("outcome")


def _analyses(line: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
    """Each analysis's shaped morphs (FR-048/FR-050 fields included)."""
    return [a.get("morphs") or [] for a in ((line.get("parse") or {}).get("analyses") or [])]


def _forms(line: Dict[str, Any]) -> List[List[str]]:
    return [[m.get("form") for m in morphs] for morphs in _analyses(line)]


def _run_id(response: Dict[str, Any]) -> Optional[str]:
    return response.get("run_id") or response.get("_submitted", {}).get("run_id")


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


def _flex_child(snippet: str, *argv: str, timeout: int = 900) -> Any:
    """Run a flexicon snippet in its OWN interpreter and return its last
    stdout line as JSON. LCM never loads into the test process, and the
    child is only ever pointed at a scratch copy."""
    out = subprocess.run(
        [sys.executable, "-c", snippet, *argv],
        capture_output=True, text=True, encoding="utf-8", timeout=timeout,
        stdin=subprocess.DEVNULL,
    )
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


# ===========================================================================
# S3: health and discovery (US1)
# ===========================================================================


async def test_s3_health_ready(sandbox_home):
    """S3: the bundled engine. ready, both FileVersions, no skew advisory
    (one engine, D7), and the next steps name the sandbox tool."""
    _require_sandbox_spine()
    health = await _health()
    parser = health["parser"]
    assert parser["sandbox"]["status"] == "ready", parser["sandbox"]
    versions = await _versions()
    for key in ("fieldworks_hermitcrab", "generate_hc_config"):
        assert versions[key], f"{key} version not reported: {parser['detected']}"
    assert parser["sandbox"]["advisories"] == [], parser["sandbox"]
    steps = health.get("parser_next_steps") or []
    assert "flextools_parse_sandbox" in json.dumps(steps), steps

    await _evidence(
        "S3", "health-ready",
        responses={"health_parser": parser, "health_parser_next_steps": steps},
    )


# ===========================================================================
# S4-S5: parse words from the project cache (US2, FR-047)
# ===========================================================================


def _assert_s4_shape(response: Dict[str, Any], words: List[str]) -> Dict[str, Dict[str, Any]]:
    assert response.get("status") != "error", response
    assert response.get("stage") == "completed", response
    assert response.get("spine") == "sandbox", response
    by_word = _by_word(response)
    sent = [ln.get("wordform") for ln in _results(response)]
    assert sorted(sent) == sorted(set(words)), f"one result per word (SC-004): {sent}"
    return by_word


async def test_s4_parse_words(sandbox_home, hc_scratch):
    """S4: one result per word; the root parses with its gloss; the prefixed
    form shows BOTH morphs, prefix then root (FR-050, the live regression
    that found every morph keyed alike); IPA words come back whole; the
    apostrophe word is one word with one result; the project's
    `ParserParameters/HC` are applied from the cache (FR-047); the scratch
    copy is untouched and `work/` is empty."""
    from flextoolsmcp.server.sandbox import engine as sandbox_engine

    words = _s4_words()
    guard = ProjectGuard(hc_scratch.folder)
    async with live_runner(sandbox_home):
        started = time.monotonic()
        response = await _parse(hc_scratch.name, words)
        wall = time.monotonic() - started
    by_word = _assert_s4_shape(response, words)

    root = by_word[ROOT_WORD]
    assert _outcome(root) == "parsed", root
    assert any(m["gloss"] == ROOT_GLOSS for morphs in _analyses(root) for m in morphs), root
    prefixed = by_word[PREFIXED_WORD]
    assert _outcome(prefixed) == "parsed", prefixed
    assert all(len(morphs) >= 2 for morphs in _analyses(prefixed)), (
        f"{PREFIXED_WORD} lost a morph in shaping: {prefixed}"
    )
    assert any(morphs[-1]["gloss"] == ROOT_GLOSS for morphs in _analyses(prefixed)), prefixed
    for line in by_word.values():
        for morphs in _analyses(line):
            for morph in morphs:
                assert set(morph) >= {"form", "gloss", "guessed", "is_circumfix", "user_added"}
                assert morph["user_added"] is False, morph  # never in a cache run
    assert len([ln for ln in _results(response) if ln["wordform"] == APOSTROPHE_WORD]) == 1

    sandbox = _meta_sandbox(response)
    project_parameters = sandbox_engine.read_parameters(hc_scratch.fwdata)
    applied = _record_json(response, "sandbox", "hc-params.json")
    run_json = _record_json(response, "sandbox", "run.json") or {}
    assert sandbox.get("parameters_source") == "cache", sandbox
    assert project_parameters is not None
    assert {k: applied.get(k) for k in project_parameters} == project_parameters, (
        applied, project_parameters)
    assert run_json.get("parameters_applied"), run_json
    assert run_json.get("id_map") == "valid", run_json
    assert _work_entries() == [], _work_entries()
    guard.check()

    await _evidence(
        "S4", "parse-words", project=hc_scratch.name, source=HC_PROJECT, hashes=[guard],
        responses={"parse": response},
        observations={
            "words": words, "results": list(by_word.values()), "wall_seconds": wall,
            "parameters_source": sandbox.get("parameters_source"),
            "project_parameters": project_parameters, "applied_parameters": applied,
            "parameters_applied": run_json.get("parameters_applied"),
            "engine_version": run_json.get("engine_version"),
        },
    )


async def test_s5_warm_cache(sandbox_home, hc_scratch):
    """S5: a repeat reuses the cache and takes at most half the cold wall time
    (SC-006). Both warm runs reuse the cache; the faster of the two is the
    one compared, since a warm run is dominated by the worker's own start
    (process, CLR, engine load) and one sample is at the mercy of the box.
    On a small grammar that start is close to the generation it saves, and
    this stays red until a warm sandbox worker is reused (#242)."""
    from flextoolsmcp.server.sandbox import cache as sandbox_cache

    words = _s4_words()
    guard = ProjectGuard(hc_scratch.folder)
    async with live_runner(sandbox_home):
        sandbox_cache.invalidate(hc_scratch.name)
        t0 = time.monotonic()
        cold = await _parse(hc_scratch.name, words)
        cold_wall = time.monotonic() - t0
        warm_runs = []
        for _ in range(2):
            t1 = time.monotonic()
            warm = await _parse(hc_scratch.name, words)
            warm_runs.append((time.monotonic() - t1, warm))
    _assert_s4_shape(cold, words)
    for _, warm in warm_runs:
        _assert_s4_shape(warm, words)
        warm_gen = (warm.get("_submitted") or warm).get("generation") or {}
        assert warm_gen.get("reused_cache") is True, warm_gen
    cold_gen = (cold.get("_submitted") or cold).get("generation") or {}
    assert cold_gen.get("reused_cache") is False, cold_gen
    warm_wall = min(wall for wall, _ in warm_runs)
    assert _work_entries() == []
    guard.check()

    # Recorded before the ratio is judged, so a miss is on file too.
    await _evidence(
        "S5", "warm-cache", project=hc_scratch.name, source=HC_PROJECT, hashes=[guard],
        responses={"cold": cold, "warm": warm_runs[0][1]},
        observations={"cold_wall_seconds": cold_wall,
                      "warm_wall_seconds": [wall for wall, _ in warm_runs],
                      "ratio": cold_wall / warm_wall if warm_wall else None,
                      "worker_duration_ms": [
                          ((_record_json(w, "sandbox", "run.json") or {}).get("worker") or {})
                          .get("duration_ms") for _, w in warm_runs]},
        needs_human=warm_wall > cold_wall / 2,
    )
    assert warm_wall <= cold_wall / 2, (cold_wall, [wall for wall, _ in warm_runs])


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


async def test_s6_sandbox_rehearse(sandbox_home, hc_scratch):
    """S6: create `tighten-env`, edit one LeftEnvironment, run S4's words,
    diff against the project-cache run; the sandbox is outside the project,
    its parameters come from the originating project (FR-047
    `live_project`), and a second create with the same name is refused."""
    name = "tighten-env"
    words = _s4_words()
    guard = ProjectGuard(hc_scratch.folder)
    async with live_runner(sandbox_home):
        baseline = await _parse(hc_scratch.name, words)
        created = await _sandbox(action="create_sandbox", project_name=hc_scratch.name,
                                 sandbox=name)
        assert created.get("status") == "ok", created
        config = Path(created["path"])
        assert not sandbox_paths.is_under(config, hc_scratch.folder), config
        assert not sandbox_paths.is_under(config, _projects_root()), config
        assert (config.parent / "lcm-ids.json").is_file(), "the id map was not copied (FR-050)"
        edited = _loosen_first_left_environment(config)
        rehearsed = await _parse(hc_scratch.name, words, sandbox=name)
        diff = await _diff(_run_id(baseline), _run_id(rehearsed))
        again = await _sandbox(action="create_sandbox", project_name=hc_scratch.name,
                               sandbox=name)
    assert rehearsed.get("stage") == "completed", rehearsed
    assert _meta_sandbox(rehearsed).get("parameters_source") == "live_project", (
        _meta_sandbox(rehearsed))
    assert diff.get("status") != "error", diff
    assert again.get("error_code") == "parse_sandbox_refused", again
    assert again.get("reason") == "sandbox_exists", again
    guard.check()

    await _evidence(
        "S6", "sandbox-rehearse", project=hc_scratch.name, source=HC_PROJECT, hashes=[guard],
        responses={"baseline": baseline, "create": created, "rehearsed": rehearsed,
                   "diff": diff, "create_again": again},
        observations={"edited_left_environment": edited,
                      "parameters_source": _meta_sandbox(rehearsed).get("parameters_source")},
    )


# ===========================================================================
# S7 (+ L-7): the project held by FLEx (a human opens a scratch copy first)
# ===========================================================================


async def test_s7_held_by_flex_and_l7(sandbox_home):
    """S7 / L-7: with FLEx holding a scratch copy (a human makes one with
    make_disposable.py --prefix CP5-Scratch-, opens it in FLEx, and sets
    FLEXTOOLSMCP_CP5_S7_PROJECT to its name and FLEXTOOLSMCP_CP5_S7_HELD to
    shared|exclusive), the run proceeds from a copy of it; sharing on gives
    `staleness: shared_mode_unverifiable`."""
    _require_sandbox_spine()
    held = _require_env("FLEXTOOLSMCP_CP5_S7_HELD",
                        "a human must open a scratch copy in FLEx first (shared or exclusive)")
    name = require_disposable(
        _require_env("FLEXTOOLSMCP_CP5_S7_PROJECT", "the scratch copy FLEx holds"),
        CP5_SCRATCH_PREFIX,
    )
    folder = _project_dir(name)
    guard = ProjectGuard(folder)
    async with live_runner(sandbox_home):
        response = await _parse(name, _s4_words()[:3])
    guard.check()
    observations = {
        "held_mode": held,
        "locks_seen": guard.before["locks"],
        "stage": response.get("stage"),
        "staleness": response.get("staleness"),
        "project_state": response.get("project_state"),
    }
    await _evidence("S7", "held-by-flex", project=name, hashes=[guard],
                    responses={"parse": response}, observations=observations)
    assert response.get("stage") == "completed", response
    if held == "shared":
        assert response.get("staleness") == "shared_mode_unverifiable", response


# ===========================================================================
# S8: corpus regression and new ambiguity (US4, FR-045, SC-005)
# ===========================================================================

#: S8's two deliberate edits (IndonesianHC-Complete): remove the only entry
#: of word A, and duplicate word B's entry under a new gloss.
S8_REGRESSION_WORD = os.environ.get("FLEXTOOLSMCP_CP5_S8_REGRESSION_WORD", "wɑkil")
S8_AMBIGUITY_WORD = os.environ.get("FLEXTOOLSMCP_CP5_S8_AMBIGUITY_WORD", "mɑnis")
S8_ADDED_GLOSS = "cp5-second-sense"


def _entry_of(root: ET.Element, shape: str):
    """The `LexicalEntry` (and its parent) whose allomorph has this shape."""
    for parent in root.iter():
        for entry in list(parent):
            if entry.tag != "LexicalEntry":
                continue
            shapes = [(e.text or "").strip() for e in entry.iter("PhoneticShape")]
            if shape in shapes:
                return parent, entry
    return None, None


def _s8_edit(config: Path) -> Dict[str, Any]:
    """Word A loses its only entry; word B gains a second one. The added
    allomorph carries no `ID` property -- a hand-made morph, which a named
    sandbox emits as `user_added` (FR-050 rule a)."""
    import copy as _copy

    tree = ET.parse(config)
    root = tree.getroot()
    parent_a, entry_a = _entry_of(root, S8_REGRESSION_WORD)
    parent_b, entry_b = _entry_of(root, S8_AMBIGUITY_WORD)
    assert entry_a is not None and entry_b is not None, (
        f"S8 needs lexical entries for {S8_REGRESSION_WORD!r} and {S8_AMBIGUITY_WORD!r}")
    removed_id = entry_a.get("id")
    parent_a.remove(entry_a)

    added = _copy.deepcopy(entry_b)
    added.set("id", f"{entry_b.get('id')}-cp5dup")
    for allomorph in added.iter("Allomorph"):
        allomorph.set("id", f"{allomorph.get('id')}-cp5dup")
        for props in allomorph.findall("Properties"):
            allomorph.remove(props)
    gloss = added.find("Gloss")
    gloss.text = S8_ADDED_GLOSS
    parent_b.insert(list(parent_b).index(entry_b) + 1, added)
    tree.write(config, encoding="utf-8", xml_declaration=True)
    return {"removed_entry": removed_id, "added_entry": added.get("id")}


def _classes(response: Dict[str, Any]) -> Dict[str, List[str]]:
    classes: Dict[str, List[str]] = {}
    for line in _results(response):
        cls = (line.get("assertion") or {}).get("classification")
        if cls:
            classes.setdefault(cls, []).append(line.get("wordform"))
    return classes


async def test_s8_corpus_regression_and_ambiguity(sandbox_home, hc_scratch):
    """S8: baseline parse -> seed_corpus -> a named sandbox with one edit
    that removes word A's only parse and one that gives word B a second
    parse -> run_corpus: exactly one `regression` (A) and one
    `new_ambiguity` (B), each naming the right parse."""
    corpus = f"s8-{int(time.time())}"
    sandbox = f"s8-{int(time.time())}"
    words = _s4_words()
    for extra in (S8_REGRESSION_WORD, S8_AMBIGUITY_WORD):
        if extra not in words:
            words.append(extra)
    guard = ProjectGuard(hc_scratch.folder)
    async with live_runner(sandbox_home):
        seed_run = await _parse(hc_scratch.name, words)
        seeded = await _sandbox(action="seed_corpus", project_name=hc_scratch.name,
                                corpus=corpus, from_run_id=_run_id(seed_run))
        assert seeded.get("status") == "ok", seeded
        created = await _sandbox(action="create_sandbox", project_name=hc_scratch.name,
                                 sandbox=sandbox)
        assert created.get("status") == "ok", created
        edits = _s8_edit(Path(created["path"]))
        ran = await _finish(await _sandbox(action="run_corpus", project_name=hc_scratch.name,
                                           corpus=corpus, sandbox=sandbox))
    assert ran.get("stage") == "completed", ran
    baseline = _by_word(seed_run)
    assert _outcome(baseline[S8_REGRESSION_WORD]) == "parsed", baseline[S8_REGRESSION_WORD]
    assert _outcome(baseline[S8_AMBIGUITY_WORD]) == "parsed", baseline[S8_AMBIGUITY_WORD]
    classes = _classes(ran)
    assert classes.get("regression") == [S8_REGRESSION_WORD], classes
    assert classes.get("new_ambiguity") == [S8_AMBIGUITY_WORD], classes

    by_word = _by_word(ran)
    ambiguous = by_word[S8_AMBIGUITY_WORD]
    added = [m for morphs in _analyses(ambiguous) for m in morphs
             if m.get("gloss") == S8_ADDED_GLOSS]
    assert added and all(m["user_added"] for m in added), ambiguous
    guard.check()

    await _evidence(
        "S8", "corpus-regression-ambiguity", project=hc_scratch.name, source=HC_PROJECT,
        hashes=[guard],
        responses={"seed_run": seed_run, "seed_corpus": seeded, "create": created,
                   "run_corpus": ran},
        observations={"edits": edits, "classes": classes,
                      "regression": by_word.get(S8_REGRESSION_WORD),
                      "new_ambiguity": ambiguous},
    )


# ===========================================================================
# S9: cache invalidation after a write; the sandbox is untouched (US6, FR-026)
# ===========================================================================

_S9_WRITE_SNIPPET = (
    "import sys, json\n"
    "sys.stdout.reconfigure(encoding='utf-8')\n"
    "from flexicon import FLExInitialize, FLExProject, FLExCleanup\n"
    "FLExInitialize()\n"
    "p = FLExProject()\n"
    "p.OpenProject(projectName=sys.argv[1], writeEnabled=True)\n"
    "try:\n"
    "    entry = p.LexEntry.GetAll()[0]\n"
    "    p.LexEntry.SetComment(entry, 'CP5 S9 cache invalidation probe')\n"
    "    print(json.dumps({'wrote': p.LexEntry.GetLexemeForm(entry)}))\n"
    "finally:\n"
    "    p.CloseProject()\n"
    "    FLExCleanup()\n"
)


async def test_s9_invalidation_sandbox_untouched(sandbox_home):
    """S9 (WRITES, its own scratch copy, opt-in): create sandbox X, warm the
    cache, write to the copy, run again: the cache entry is regenerated and
    X is byte-identical (SC-007). The source is untouched."""
    _require_sandbox_spine()
    _require_write_opt_in()
    words = _s4_words()[:4]
    with scratch_copy(HC_PROJECT) as scratch:
        async with live_runner(sandbox_home):
            created = await _sandbox(action="create_sandbox", project_name=scratch.name,
                                     sandbox="x")
            assert created.get("status") == "ok", created
            sandbox_guard = ProjectGuard(Path(created["path"]).parent)
            await _parse(scratch.name, words)
            warm2 = await _parse(scratch.name, words)
        wrote = _flex_child(_S9_WRITE_SNIPPET, scratch.name)
        async with live_runner(sandbox_home):
            after = await _parse(scratch.name, words)
            on_sandbox = await _parse(scratch.name, words, sandbox="x")
        key_before = (_submitted(warm2).get("config_source") or {}).get("cache_key")
        key_after = (_submitted(after).get("config_source") or {}).get("cache_key")
        assert (_submitted(warm2).get("generation") or {}).get("reused_cache") is True
        assert (_submitted(after).get("generation") or {}).get("reused_cache") is False
        assert key_before and key_after and key_before != key_after, (key_before, key_after)
        assert on_sandbox.get("stage") == "completed", on_sandbox
        sandbox_guard.check()
        await _evidence(
            "S9", "invalidation-sandbox-untouched", project=scratch.name, source=HC_PROJECT,
            hashes=[scratch.source_guard, sandbox_guard],
            responses={"create": created, "warm2": warm2, "after_write": after,
                       "on_sandbox": on_sandbox},
            observations={"write": wrote, "cache_key_before": key_before,
                          "cache_key_after": key_after},
        )


# ===========================================================================
# S10: timeout with partial results (US5, FR-020)
# ===========================================================================


def _scale_words(fwdata: Path, count: int) -> List[str]:
    """The project's wordforms, then two-word concatenations of them, up to
    `count` distinct words: enough work that a real engine outlasts the
    minimum timeout."""
    base = _fwdata_wordforms(fwdata, 100000)
    words = list(base)
    seen = set(words)
    for a in base:
        for b in base:
            if len(words) >= count:
                return words
            joined = a + b
            if joined not in seen:
                seen.add(joined)
                words.append(joined)
    return words


async def test_s10_timeout_partial(sandbox_home, scale_scratch):
    """S10: many words and the minimum timeout: `parser_timeout`, a partial
    `words_completed`, the in-flight word named, every result parsed before
    the kill preserved and readable through `parse_log`, `work/` empty."""
    count = int(os.environ.get("FLEXTOOLSMCP_CP5_S10_WORDS", "20000"))
    timeout = int(os.environ.get("FLEXTOOLSMCP_CP5_S10_TIMEOUT", "10"))
    words = _scale_words(scale_scratch.fwdata, count)
    guard = ProjectGuard(scale_scratch.folder)
    async with live_runner(sandbox_home):
        # Warm the cache first so the bound cuts parsing, not generation.
        warm = await _parse(scale_scratch.name, words[:1])
        response = await _parse(scale_scratch.name, words, timeout_seconds=timeout)
        run_id = _run_id(response)
        status = await _status(run_id)
        results = await _log(run_id, "results", limit=5)
    failure = response.get("failure") or {}
    assert failure.get("error_code") == "parser_timeout", response
    completed = response.get("words_completed")
    assert isinstance(completed, int) and 0 < completed < len(words), response
    in_flight = status.get("in_flight")
    assert in_flight and status.get("in_flight_index") is not None, status
    lines = _results(response)
    reached = [ln for ln in lines if _outcome(ln) not in (None, "not_reached")]
    assert len(reached) >= completed, (len(reached), completed)
    assert in_flight not in {ln["wordform"] for ln in reached}, in_flight
    assert results.get("status") != "error" and results.get("total"), results
    assert _work_entries() == [], _work_entries()
    guard.check()

    await _evidence(
        "S10", "timeout-partial", project=scale_scratch.name, source=SCALE_PROJECT,
        hashes=[guard],
        responses={"warm": warm, "parse": response, "status": status, "results": results},
        observations={"timeout_seconds": timeout, "words_total": len(words),
                      "words_completed": completed, "results_preserved": len(reached),
                      "in_flight": in_flight,
                      "in_flight_index": status.get("in_flight_index")},
    )


# ===========================================================================
# S11: a hand-broken sandbox (US5)
# ===========================================================================


async def test_s11_broken_sandbox(sandbox_home, hc_scratch):
    """S11: a truncated sandbox XML fails the run as `parser_job_failed` /
    `engine_unavailable` with the engine's load error, and zero parse results."""
    name = f"broken-{int(time.time())}"
    guard = ProjectGuard(hc_scratch.folder)
    async with live_runner(sandbox_home):
        created = await _sandbox(action="create_sandbox", project_name=hc_scratch.name,
                                 sandbox=name)
        assert created.get("status") == "ok", created
        config = Path(created["path"])
        text = config.read_text(encoding="utf-8")
        config.write_text(text[: len(text) // 2], encoding="utf-8")  # truncated XML
        response = await _parse(hc_scratch.name, _s4_words()[:3], sandbox=name)
        run_id = _run_id(response)
        diagnostics = await _log(run_id, "hc_stdout") if run_id else None
    # contracts/sandbox-worker.md section 8: an unloadable config surfaces
    # once, as `parser_job_failed` / `engine_unavailable`, carrying the load
    # exception's text.
    assert response.get("status") == "error", response
    assert response.get("error_code") == "parser_job_failed", response
    assert response.get("failure") == "engine_unavailable", response
    assert "XmlException" in json.dumps(response, ensure_ascii=False), response
    assert not [ln for ln in _results(response) if _outcome(ln) == "parsed"]
    guard.check()

    await _evidence(
        "S11", "broken-sandbox", project=hc_scratch.name, source=HC_PROJECT, hashes=[guard],
        responses={"create": created, "parse": response, "diagnostics": diagnostics},
    )


# ===========================================================================
# S12: the XAmple project is refused before any copy (US2)
# ===========================================================================


async def test_s12_xample_refused(sandbox_home):
    """S12: `Sena 3` gets `parser_engine_mismatch` before any copy. The
    project is not opened: the hash is identical and no lock file appears
    during the call."""
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
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from flextoolsmcp.server.handlers import parse as p
from flextoolsmcp.server.parse.runner import ParseRunner
from flextoolsmcp.server.sandbox import cache
async def main():
    cache.invalidate(sys.argv[3])
    p.set_runner(ParseRunner(record_dir=Path(sys.argv[2])))
    r = await p.handle_flextools_parse_sandbox(
        {"action": "parse", "project_name": sys.argv[3], "words": ["x"]})
    print(r[0].text, flush=True)
    await asyncio.sleep(3600)
asyncio.run(main())
"""


async def test_s13_orphan_sweep(sandbox_home, hc_scratch):
    """S13: a server killed mid-generation leaves `work/<id>`; the next
    sandbox job in a fresh server removes it."""
    guard = ProjectGuard(hc_scratch.folder)
    before = set(_work_entries())
    child = subprocess.Popen(
        [sys.executable, "-c", _S13_CHILD, str(REPO_ROOT / "src"),
         str(sandbox_home / "runs-child"), hc_scratch.name],
        env=dict(os.environ), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    orphans: List[str] = []
    try:
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline and child.poll() is None:
            orphans = sorted(set(_work_entries()) - before)
            if orphans:
                break
            await asyncio.sleep(0.05)
    finally:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(child.pid)],
                       capture_output=True, check=False)
        child.wait(timeout=60)
    if not orphans:
        err = child.stderr.read().decode("utf-8", "replace") if child.stderr else ""
        out = child.stdout.read().decode("utf-8", "replace") if child.stdout else ""
        pytest.fail("the child server never created a work directory to orphan: "
                    f"stdout={out[-2000:]!r} stderr={err[-3000:]!r}")
    if not set(orphans) & set(_work_entries()):
        pytest.skip("the killed server's work directory was already gone; nothing to sweep")

    async with live_runner(sandbox_home):
        after_run = await _parse(hc_scratch.name, _s4_words()[:2])
    remaining = sorted(set(orphans) & set(_work_entries()))
    assert remaining == [], f"orphaned work dirs survived the sweep: {remaining}"
    guard.check()

    await _evidence(
        "S13", "orphan-sweep", project=hc_scratch.name, source=HC_PROJECT, hashes=[guard],
        responses={"next_run": after_run},
        observations={"orphans": orphans, "remaining": remaining},
    )


# ===========================================================================
# S14: circumfix shaping and the id-map numbering (FR-050 b/c, D4/R-17)
# ===========================================================================

_ID_MAP_SNIPPET = (
    "import sys, json\n"
    "sys.stdout.reconfigure(encoding='utf-8')\n"
    "from flexicon import FLExInitialize, FLExProject, FLExCleanup\n"
    "FLExInitialize()\n"
    "p = FLExProject()\n"
    "p.OpenProject(projectName=sys.argv[1], writeEnabled=False)\n"
    "try:\n"
    "    ids = json.load(open(sys.argv[2], encoding='utf-8'))\n"
    "    out = {}\n"
    "    for i in ids:\n"
    "        try:\n"
    "            o = p.Object(int(i))\n"
    "            out[i] = [str(o.Guid), str(o.ClassName)]\n"
    "        except Exception as e:\n"
    "            out[i] = [None, str(e)]\n"
    "    print(json.dumps(out))\n"
    "finally:\n"
    "    p.CloseProject()\n"
    "    FLExCleanup()\n"
)


def _cache_entry_dir(response: Dict[str, Any]) -> Path:
    from flextoolsmcp.server.sandbox import cache as sandbox_cache

    submitted = response.get("_submitted") or response
    key = (submitted.get("config_source") or {}).get("cache_key")
    entry = sandbox_cache.lookup(submitted["project"], key, touch=False)
    assert entry is not None, f"no cache entry for {submitted.get('project')} / {key}"
    return entry.config_path.parent


def _validate_id_map(scratch: Scratch, id_map_path: Path, work: Path) -> Dict[str, Any]:
    """Open the scratch copy with LCM (in a child) and resolve every id the
    map holds: each must be the object the map names, by GUID and class. This
    is the direct test of "HVO = 1-based `<rt>` document order" (R-17)."""
    id_map = json.loads(id_map_path.read_text(encoding="utf-8"))
    ids = sorted(id_map["ids"], key=int)
    ids_file = work / f"{scratch.name}-ids.json"
    ids_file.write_text(json.dumps(ids), encoding="utf-8")
    resolved = _flex_child(_ID_MAP_SNIPPET, scratch.name, str(ids_file))
    mismatches = {
        i: {"map": id_map["ids"][i], "lcm": resolved.get(i)}
        for i in ids
        if (resolved.get(i) or [None])[0] != id_map["ids"][i]["guid"]
        or (resolved.get(i) or [None, None])[1] != id_map["ids"][i]["class"]
    }
    return {"ids_checked": len(ids), "mismatches": mismatches}


async def test_s14_circumfix_shaping_and_id_map(sandbox_home, tmp_path):
    """S14: on a circumfix project (its own scratch copy), a circumfix word
    shows the circumfix before AND after its stem, both flagged
    `is_circumfix` (FR-050 b/c); then every id in the run's `lcm-ids.json`
    resolves, through LCM itself, to the GUID and class the map recorded."""
    _require_sandbox_spine()
    with scratch_copy(CIRCUMFIX_PROJECT) as scratch:
        words = _fwdata_wordforms(scratch.fwdata, 300)
        guard = ProjectGuard(scratch.folder)
        async with live_runner(sandbox_home):
            response = await _parse(scratch.name, words)
        guard.check()
        assert response.get("stage") == "completed", response
        circumfixed = {}
        for line in _results(response):
            for morphs in _analyses(line):
                flagged = [i for i, m in enumerate(morphs) if m["is_circumfix"]]
                if len(flagged) >= 2:
                    circumfixed[line["wordform"]] = morphs
        assert circumfixed, "no word in the circumfix project came back with a circumfix"
        for word, morphs in circumfixed.items():
            flagged = [i for i, m in enumerate(morphs) if m["is_circumfix"]]
            first, last = flagged[0], flagged[-1]
            assert morphs[first]["gloss"] == morphs[last]["gloss"], (word, morphs)
            assert any(not m["is_circumfix"] for m in morphs[first + 1:last]), (
                f"{word}: the circumfix does not surround a stem: {morphs}")

        id_map_path = _cache_entry_dir(response) / "lcm-ids.json"
        validation = _validate_id_map(scratch, id_map_path, tmp_path)
        assert validation["ids_checked"] > 0, validation
        assert validation["mismatches"] == {}, validation["mismatches"]

        await _evidence(
            "S14", "circumfix-and-id-map", project=scratch.name, source=CIRCUMFIX_PROJECT,
            hashes=[scratch.source_guard, guard],
            responses={"parse": response},
            observations={"circumfixed_words": circumfixed, "id_map_validation": validation,
                          "outcomes": (response.get("result_summary") or {}).get("outcomes")},
        )


# ===========================================================================
# S15: parity with FLEx's own parser (SC-003)
# ===========================================================================


def _nfc_forms(analyses: Iterable[Iterable[str]]) -> List[List[str]]:
    """Forms compared as text, not code points: LCM hands back its stored
    NFD (`c` + U+0327) where the sandbox may carry NFC (`ç`)."""
    import unicodedata

    return sorted([[unicodedata.normalize("NFC", f or "") for f in forms]
                   for forms in analyses])


def _project_forms(line: Dict[str, Any]) -> List[List[str]]:
    return _nfc_forms(a.get("rendered_morphs") or []
                      for a in ((line.get("parse") or {}).get("analyses") or []))


@pytest.mark.parametrize("source", [HC_PROJECT, CIRCUMFIX_PROJECT])
async def test_s15_parity_with_flex(sandbox_home, source):
    """S15 (SC-003): the same words, on the same scratch copy, through the
    sandbox and through FLEx's own parser (`flextools_parse_text`, which runs
    `HCParser` -- the engine behind Try A Word -- in the project worker).
    Parse/no-parse and the shaped morph forms must agree word for word. The
    two disclosed differences are named, not compared: glosses (the sandbox
    reads `Morpheme.Gloss`; FLEx labels by category) and `user_added` morphs
    (named sandboxes only; this is a cache run)."""
    _require_sandbox_spine()
    with scratch_copy(source) as scratch:
        words = _fwdata_wordforms(scratch.fwdata, 60)
        if source == HC_PROJECT:
            words = sorted(set(words) | {ROOT_WORD, PREFIXED_WORD})
        async with live_runner(sandbox_home):
            sandbox_run = await _parse(scratch.name, words)
            project_run = await _finish(await _call(
                parse_handler.handle_flextools_parse_text, project_name=scratch.name,
                scope_kind="words", scope_value=words))
        assert sandbox_run.get("stage") == "completed", sandbox_run
        assert project_run.get("stage") == "completed", project_run
        sandbox_by = _by_word(sandbox_run)
        project_by = _by_word(project_run)
        compared: Dict[str, Any] = {}
        disagreements: Dict[str, Any] = {}
        for word in words:
            if word not in project_by or word not in sandbox_by:
                continue
            flex = project_by[word]
            box = sandbox_by[word]
            row = {
                "flex_parsed": bool((flex.get("parse") or {}).get("parsed")),
                "sandbox_parsed": _outcome(box) == "parsed",
                "flex_forms": _project_forms(flex),
                "sandbox_forms": _nfc_forms(_forms(box)),
            }
            compared[word] = row
            if (row["flex_parsed"] != row["sandbox_parsed"]
                    or row["flex_forms"] != row["sandbox_forms"]):
                disagreements[word] = row

        await _evidence(
            "S15", f"parity-{'hc' if source == HC_PROJECT else 'circumfix'}",
            project=scratch.name, source=source, hashes=[scratch.source_guard],
            responses={"sandbox": sandbox_run, "project": project_run},
            observations={
                "words_compared": len(compared), "disagreements": disagreements,
                "comparison": compared,
                "disclosed_differences": [
                    "glosses: the sandbox reads Morpheme.Gloss; FLEx labels morphs by category",
                    "user_added morphs: emitted in named sandboxes only (none in a cache run)",
                ],
            },
            needs_human=bool(disagreements),
        )
        assert compared, "no word was answered by both parsers"
        assert disagreements == {}, disagreements


# ===========================================================================
# S16: live process isolation (FR-045, FR-046)
# ===========================================================================

_ISOLATION_PROBE = r"""
import json, sys
from flextoolsmcp.server.parse import worker_main as wm
rc = wm.main(sys.argv[1:])
banned = sorted(m for m in sys.modules
                if m.split('.')[0] in ('flexicon', 'flexlibs') or m.startswith('SIL.LCModel'))
sys.stderr.write('ISOLATION:' + json.dumps(banned) + '\n')
sys.exit(rc)
"""


async def test_s16_live_process_isolation(sandbox_home, hc_scratch, tmp_path):
    """S16: during real runs of the sandbox worker on the bundled engine,
    its `assemblies` answer lists no `SIL.LCModel*` assembly, its
    `sys.modules` holds no flexicon/flexlibs, the scratch project folder
    hashes byte-identical, and the worker writes nothing in its cwd."""
    from flextoolsmcp.server.parse.worker_client import ParseWorkerClient, SandboxSpawn

    guard = ProjectGuard(hc_scratch.folder)
    async with live_runner(sandbox_home):
        warm = await _parse(hc_scratch.name, [ROOT_WORD])
    entry_dir = _cache_entry_dir(warm)
    config = entry_dir / "hc-config.xml"
    id_map = entry_dir / "lcm-ids.json"

    client = ParseWorkerClient(
        hc_scratch.name,
        sandbox=SandboxSpawn(config=str(config), id_map=str(id_map), project=hc_scratch.name))
    await client.start()
    try:
        parsed = await client.parse_word(request_id="r0", run_id="s16", wordform=PREFIXED_WORD,
                                         level="batch", index_in_run=0)
        assemblies = await client.loaded_assemblies()
    finally:
        await client.aclose()
    assert parsed["parse"]["outcome"] == "parsed", parsed
    lcm = [n for n in assemblies if n.startswith("SIL.LCModel")]
    assert lcm == [], lcm
    assert any("HermitCrab" in n or n.startswith("SIL.Machine") for n in assemblies), assemblies

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    message = {"type": "parse", "request_id": "r1", "run_id": "s16", "wordform": PREFIXED_WORD,
               "level": "batch", "index_in_run": 0}
    stdin = (json.dumps(message) + "\n" + json.dumps({"type": "shutdown"}) + "\n").encode()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", _ISOLATION_PROBE, "--sandbox", "--config", str(config),
         "--id-map", str(id_map), "--project", hc_scratch.name],
        input=stdin, capture_output=True, cwd=str(cwd), timeout=300, env=env,
    )
    stderr = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, stderr[-3000:]
    report = [ln for ln in stderr.splitlines() if ln.startswith("ISOLATION:")]
    banned = json.loads(report[-1][len("ISOLATION:"):]) if report else None
    assert banned == [], banned
    assert _tree_listing(cwd) == [], _tree_listing(cwd)
    guard.check()

    await _evidence(
        "S16", "live-process-isolation", project=hc_scratch.name, source=HC_PROJECT,
        hashes=[guard],
        responses={"warm": warm},
        observations={"worker_parse": parsed, "assemblies": sorted(assemblies),
                      "lcm_assemblies": lcm, "banned_modules": banned,
                      "cwd_after": _tree_listing(cwd)},
    )


# ===========================================================================
# L-1, L-2, L-4: live questions (recorded)
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


async def test_l1_generator_allowlist(sandbox_home, hc_scratch):
    """L-1: does GenerateHCConfig need more than `.fwdata` + WritingSystemStore?
    Generates from an allowlist copy and from a full copy (both outside the
    projects directory) and records whether the configs are identical."""
    ghc = _require_generator()
    from flextoolsmcp.server.sandbox import workdir

    guard = ProjectGuard(hc_scratch.folder)
    base = sandbox_home / "l1"
    runs: Dict[str, Any] = {}
    for label, allow in (("allowlist", workdir.ALLOWLIST_DIRS), ("full", None)):
        dest = base / label / hc_scratch.name
        _copy_project(hc_scratch.folder, dest, allow)
        runs[label] = _run_generator(Path(ghc.expected_path),
                                     dest / f"{hc_scratch.name}.fwdata",
                                     base / label / "hc-config.xml")
    guard.check()
    identical = runs["allowlist"]["config_sha256"] == runs["full"]["config_sha256"]
    await _evidence(
        "L-1", "generator-allowlist", project=hc_scratch.name, source=HC_PROJECT,
        hashes=[guard],
        observations={"allowlist": list(workdir.ALLOWLIST_DIRS), "runs": runs,
                      "identical": identical},
    )
    assert identical, runs


async def test_l2_leading_dash(sandbox_home, hc_scratch):
    """L-2: a word beginning with `-` is data, not an option: it reaches the
    engine intact and comes back as one result for that exact word."""
    word = os.environ.get("FLEXTOOLSMCP_CP5_L2_WORD", "-an")
    guard = ProjectGuard(hc_scratch.folder)
    async with live_runner(sandbox_home):
        response = await _parse(hc_scratch.name, [word])
    guard.check()
    lines = _results(response)
    assert response.get("stage") == "completed", response
    assert [ln["wordform"] for ln in lines] == [word], lines
    await _evidence(
        "L-2", "leading-dash", project=hc_scratch.name, source=HC_PROJECT, hashes=[guard],
        responses={"parse": response}, observations={"word": word, "results": lines},
    )


async def test_l4_generation_offline(sandbox_home, hc_scratch):
    """L-4: does GenerateHCConfig hang offline (SLDR)? A human disables the
    network and sets FLEXTOOLSMCP_CP5_L4_OFFLINE=1; generation is timed."""
    _require_env("FLEXTOOLSMCP_CP5_L4_OFFLINE", "a human must disable the network first")
    from flextoolsmcp.server.sandbox import cache as sandbox_cache

    guard = ProjectGuard(hc_scratch.folder)
    async with live_runner(sandbox_home):
        sandbox_cache.invalidate(hc_scratch.name)
        t0 = time.monotonic()
        response = await _parse(hc_scratch.name, _s4_words()[:1])
        wall = time.monotonic() - t0
    guard.check()
    await _evidence(
        "L-4", "generation-offline", project=hc_scratch.name, source=HC_PROJECT,
        hashes=[guard], responses={"parse": response},
        observations={"wall_seconds": wall, "generation": response.get("generation")},
        needs_human=True,
    )
