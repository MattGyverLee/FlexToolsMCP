#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Offline doubles for parser-check CP4's filing tests.

A real `ParseRunner` over fake workers, the same arrangement
`test_parse_text_handler.py` uses for CP3. Two fakes, because filing uses two
processes (R-09):

  * `FakeReadWorker` -- the SHARED read-only worker. Answers the engine gate,
    scope resolution, the agent probe, the refuse-to-file gate's inputs and
    the preview's stored-analysis facts. It never files anything, and it
    records every call so a test can assert what was (not) asked.
  * `FakeFilingWorker` -- the FILING_ROLE worker. It is spawned only by a
    confirmed request that passed every rung; `pool.spawned` records each
    spawn so a test can assert the preview never started one (SC-001).

`filing_env` installs both behind a runner, isolates the config file, the
backup root and the run-record directory under `tmp_path`, enables writing on
the session, and clears the claim registry and the session's issued plans.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from flextoolsmcp import config as config_mod
from flextoolsmcp.server import backup as backup_mod
from flextoolsmcp.server import project_access, project_discovery
from flextoolsmcp.server.handlers import parse as parse_handler
from flextoolsmcp.server.parse.runner import ParseRunner
from flextoolsmcp.server.parse.worker_client import SHARED_ROLE

# The filing package is imported lazily, inside the fixture: a tripwire test
# written BEFORE the code it guards must still collect, and fail on its
# assertion rather than on an ImportError.
FILING_ROLE = "filing"

PROJECT = "Demo"


def analysis(guid, *, opinion="noopinion", in_segment=False, parser_evaluated=True):
    """One stored-analysis fact, as `filing_preview` reports it."""
    return {
        "analysis_guid": guid,
        "user_opinion": opinion,
        "parser_evaluated": parser_evaluated,
        "in_segment": in_segment,
    }


def resolved_words(words, **overrides):
    data = {
        "scope_kind": "words",
        "scope_value": sorted(words),
        "text_ids": [],
        "words": list(words),
        "count_before_limit": len(words),
        "limit": None,
        "truncated": False,
        "vernacular_ws": "id",
        "never_tokenized_text_ids": [],
        "unreadable_wordform_count": 0,
        "notes": [],
    }
    data.update(overrides)
    return data


def clean_gate(errors=None, eligible=None, *, morpher_null=False):
    return {
        "morpher_null": morpher_null,
        "load": {"captured": True, "errors": list(errors or []), "source": "C:/tmp/DemoHCLoadErrors.xml"},
        "eligible": {
            "known": True,
            "entries": list(eligible if eligible is not None else [
                {"entry_guid": "e1", "headword": "pukul"},
                {"entry_guid": "e2", "headword": "kirim"},
            ]),
        },
    }


PRESENT_AGENT = {
    "state": "present", "agent_guid": "kguidAgentHermitCrabParser",
    "agent_name": "HermitCrab", "active_engine": "HC",
    "probe_source": None, "hint": None,
}


class FakeReadWorker:
    """The shared, read-only worker. Nothing here writes."""

    def __init__(
        self,
        *,
        facts: Optional[Dict[str, List[dict]]] = None,
        gate: Optional[dict] = None,
        gates: Optional[List[dict]] = None,
        agent: Optional[dict] = None,
        engine_error: Optional[Exception] = None,
        scope_error: Optional[Exception] = None,
        resolved: Optional[dict] = None,
        project_state: Optional[dict] = None,
        join_known: bool = True,
    ):
        self.calls: List[str] = []
        self.facts = facts if facts is not None else {}
        self._gates = list(gates) if gates else None
        self.gate = gate if gate is not None else clean_gate()
        self.agent = agent if agent is not None else dict(PRESENT_AGENT)
        self.engine_error = engine_error
        self.scope_error = scope_error
        self.resolved = resolved
        self.project_state = project_state if project_state is not None else {
            "parser_has_ever_run": True, "analyses_total": 0,
            "parser_created_analyses": 1, "human_opinion_analyses": 0,
            "indeterminate_analyses": 0, "truncated": False,
        }
        self.join_known = join_known
        self.parse_kwargs: List[dict] = []
        self.batch_parses: Dict[str, dict] = {}

    # -- plumbing the runner uses --
    def listen_to_run(self, *a):
        pass

    def stop_listening(self, *a):
        pass

    def is_running(self):
        return True

    async def cancel_run(self, run_id):
        self.calls.append("cancel_run")

    # -- CP3 --
    async def check_engine(self, **kwargs):
        self.calls.append("check_engine")
        if self.engine_error:
            raise self.engine_error
        return "HC"

    async def resolve_scope(self, **kwargs):
        self.calls.append("resolve_scope")
        if self.scope_error:
            raise self.scope_error
        resolved = dict(self.resolved or resolved_words(kwargs["scope"]["value"]))
        resolved["project_state"] = self.project_state
        return resolved

    async def parse_word(self, **kwargs):
        self.calls.append("parse_word")
        self.parse_kwargs.append(kwargs)
        word = kwargs.get("wordform")
        return {"parse": self.batch_parses.get(word) or {
            "parsed": True, "analysis_count": 0, "analyses": [], "human_analyses": [],
            "error_message": None, "parse_time_ms": 0}, "trace_xml": None}

    # -- CP4 read-only messages --
    async def probe_agent(self, **kwargs):
        self.calls.append("probe_agent")
        return dict(self.agent)

    async def filing_gate(self, **kwargs):
        self.calls.append("filing_gate")
        if self._gates:
            return self._gates.pop(0) if len(self._gates) > 1 else self._gates[0]
        return json.loads(json.dumps(self.gate))

    async def filing_preview(self, **kwargs):
        self.calls.append("filing_preview")
        words = kwargs.get("words") or []
        return {
            "join_known": self.join_known,
            "words": {
                w: {"wordform": w, "found": w in self.facts,
                    "analyses": [dict(a) for a in self.facts.get(w, [])]}
                for w in words
            },
        }


class FakeFilingWorker:
    """The FILING_ROLE worker. Files nothing real: it reports outcomes."""

    def __init__(self, *, outcomes: Optional[Dict[str, dict]] = None, delay: float = 0.0,
                 fail_with: Optional[Exception] = None, fail_after: Optional[int] = None,
                 commit_ok: bool = True, setup_error: Optional[Exception] = None,
                 alive: bool = True):
        self.calls: List[str] = []
        self.setups: List[dict] = []
        self.outcomes = outcomes or {}
        self.delay = delay
        self.fail_with = fail_with
        #: Raise `fail_with` only once this many words have been filed.
        self.fail_after = fail_after
        self.commit_ok = commit_ok
        self.setup_error = setup_error
        self.alive = alive
        self.words: List[str] = []
        self.commits = 0

    def listen_to_run(self, *a):
        pass

    def stop_listening(self, *a):
        pass

    def is_running(self):
        return self.alive

    async def cancel_run(self, run_id):
        self.calls.append("cancel_run")

    async def filing_setup(self, **kwargs):
        self.calls.append("filing_setup")
        self.setups.append(kwargs)
        if self.setup_error is not None:
            raise self.setup_error
        return {"type": "filing_ready"}

    async def filing_commit(self, **kwargs):
        self.calls.append("filing_commit")
        self.commits += 1
        return {"type": "filing_committed", "ok": self.commit_ok,
                "error": None if self.commit_ok else "save failed"}

    async def parse_word(self, **kwargs):
        word = kwargs.get("wordform")
        self.calls.append("parse_word")
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_with is not None and (self.fail_after is None
                                           or len(self.words) >= self.fail_after):
            raise self.fail_with
        self.words.append(word)
        outcome = dict(self.outcomes.get(word) or {"outcome": "filed", "counts": {"reapproved": 1}})
        captures = outcome.pop("captures", None) or []
        if captures and self.setups:
            # Write the captures where the real worker writes them: the run
            # record's filing/deletions.jsonl, fsynced, before "the pump".
            from flextoolsmcp.server.filing.paths import DELETIONS_RELPATH
            from flextoolsmcp.server.parse.record import RunRecord

            root = Path(self.setups[-1]["setup"]["record_root"])
            record = RunRecord(root.name, record_dir=root.parent)
            for line in captures:
                record.append_jsonl(DELETIONS_RELPATH, dict(line, wordform=word))
        return {"parse": {"parsed": True, "analysis_count": 1, "analyses": [],
                          "human_analyses": [], "error_message": None,
                          "parse_time_ms": 0, "filing": outcome},
                "trace_xml": None}


class FakePool:
    """Two roles per project, and a record of what was spawned."""

    def __init__(self, read_worker, filing_worker=None):
        self.read = read_worker
        self.filing = filing_worker or FakeFilingWorker()
        self.spawned: List[str] = []
        self.released: List[tuple] = []

    async def get(self, name, *, role=SHARED_ROLE):
        if role == FILING_ROLE:
            self.spawned.append(FILING_ROLE)
            return self.filing
        return self.read

    def peek(self, name, *, role=SHARED_ROLE):
        return self.filing if role == FILING_ROLE else self.read

    def workers_for(self, name):
        """Mirrors `WorkerPool.workers_for` (#223 own-worker detection)."""
        workers = {}
        if self.read is not None:
            workers[SHARED_ROLE] = self.read
        if FILING_ROLE in self.spawned and self.filing is not None:
            workers[FILING_ROLE] = self.filing
        return workers

    async def release(self, name, *, role=None):
        self.released.append((name, role))

    async def terminate(self, name, *, role):
        return False

    async def aclose(self):
        pass


class FilingEnv:
    def __init__(self, tmp_path: Path, monkeypatch):
        self.tmp_path = tmp_path
        self.monkeypatch = monkeypatch
        self.record_dir = tmp_path / "runs"
        self.projects_dir = tmp_path / "projects"
        self.project_dir = self.projects_dir / PROJECT
        self.project_dir.mkdir(parents=True)
        self.fwdata = self.project_dir / f"{PROJECT}.fwdata"
        self.fwdata.write_bytes(b"<languageproject/>")
        self.backup_root = tmp_path / "backups"
        self.runner: Optional[ParseRunner] = None
        self.pool: Optional[FakePool] = None
        self.backups: List[str] = []

    def install(self, read_worker=None, filing_worker=None, *, grace_window=5):
        self.pool = FakePool(read_worker or FakeReadWorker(), filing_worker)
        self.runner = ParseRunner(pool=self.pool, record_dir=self.record_dir,
                                  grace_window=grace_window)
        parse_handler.set_runner(self.runner)
        return self.runner

    @property
    def read(self) -> FakeReadWorker:
        return self.pool.read

    @property
    def filing(self) -> FakeFilingWorker:
        return self.pool.filing

    def fwdata_sha256(self) -> str:
        import hashlib

        return hashlib.sha256(self.fwdata.read_bytes()).hexdigest()

    def set_access(self, verdict, *, sharing=None):
        holder = project_access.LockHolder(pid=4242, process_name="FieldWorks",
                                           timestamp_ticks=None) if verdict not in ("free", "unknown") else None
        access = project_access.ProjectAccess(
            project_name=PROJECT, verdict=verdict,
            sharing_enabled=sharing if sharing is not None else (verdict == "open_shared"),
            holder=holder, lock_age_seconds=None, probed=verdict != "unknown",
        )
        self.monkeypatch.setattr(project_access, "probe_project_access", lambda name: access)

    def set_config(self, key, value):
        """Set a key in the ISOLATED config (both module copies see it)."""
        import config as bare_config_mod

        config_mod.config_set(key, value)
        bare_config_mod._config_cache = None
        config_mod._config_cache = None


async def call(args: dict) -> dict:
    response = await parse_handler.handle_flextools_parse_text(args)
    return json.loads(response[0].text)


def filing_args(**extra) -> dict:
    args = {"scope_kind": "words", "scope_value": ["pukul", "kirim"], "apply": True}
    args.update(extra)
    return args


@pytest.fixture
def filing_env(tmp_path, monkeypatch):
    env = FilingEnv(tmp_path, monkeypatch)

    # Project resolution and the projects directory, both under tmp_path.
    monkeypatch.setattr(parse_handler, "_resolve_project", lambda name: (name or PROJECT, None))
    monkeypatch.setattr(project_discovery, "get_projects_directory",
                        lambda: (env.projects_dir, "env"))
    monkeypatch.setattr(project_discovery, "get_project_fwdata_path",
                        lambda name: env.project_dir.parent / name / f"{name}.fwdata"
                        if (env.project_dir.parent / name / f"{name}.fwdata").exists() else None)
    monkeypatch.setattr(backup_mod, "get_project_fwdata_path",
                        lambda name: env.fwdata if name == PROJECT else None)
    monkeypatch.setattr(backup_mod, "BACKUP_ROOT", env.backup_root)
    env.set_access("free")

    # The config file, isolated: a test that sets a key never touches
    # ~/.flextoolsmcp. The module is importable under TWO names -- the package
    # form `flextoolsmcp.config` and the bare `config` (conftest puts
    # src/flextoolsmcp on sys.path, and admin.py's fallback import lands
    # there) -- and each holds its own cache and its own CONFIG_FILE, so BOTH
    # are redirected. Patching only one once wrote a real
    # require_write_confirmation=false into the user's config.
    import config as bare_config_mod

    for module in {id(config_mod): config_mod, id(bare_config_mod): bare_config_mod}.values():
        monkeypatch.setattr(module, "CONFIG_DIR", tmp_path / "config")
        monkeypatch.setattr(module, "CONFIG_FILE", tmp_path / "config" / "config.json")
        monkeypatch.setattr(module, "_config_cache", None)
    real_config = Path.home() / ".flextoolsmcp" / "config.json"
    real_before = real_config.read_bytes() if real_config.is_file() else None

    try:
        from flextoolsmcp.server.filing import claims, filer, paths
    except ImportError:  # a tripwire running before the package exists
        claims = filer = paths = None
    if paths is not None:
        monkeypatch.setattr(paths, "projects_directory", lambda: env.projects_dir)
    if filer is not None:
        # The filing surface probe reflects over FieldWorks assemblies;
        # offline it is stubbed to "present". Probe tests override this.
        monkeypatch.setattr(filer, "probe_filing_surface",
                            lambda: filer.SurfaceProbe(ok=True, missing_members=[]))

    session = parse_handler.session_state
    saved = (session.write_enabled, set(getattr(session, "filing_plans", {}) or {}))
    session.write_enabled = True
    session.filing_plans = {}
    session.filing_backed_up_projects = set()
    if claims is not None:
        claims.clear()

    yield env

    if claims is not None:
        claims.clear()
    real_after = real_config.read_bytes() if real_config.is_file() else None
    assert real_after == real_before, "a filing test wrote to the real ~/.flextoolsmcp config"
    session.write_enabled = saved[0]
    session.filing_plans = {}
    session.filing_backed_up_projects = set()
    parse_handler.set_runner(None)
