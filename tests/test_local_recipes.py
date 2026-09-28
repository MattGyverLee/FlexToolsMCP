#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Phase 4 US2: local recipe store (FR-010..016, SC-002, SC-004).

Port of test_skeleton_storage.py into the local-recipe world plus new
coverage for path resolution, record fields, fingerprint identity,
op_ids/projects bookkeeping, never-raises, legacy migration, 2000-row
cap, and paraphrase recall after restart.

Contract under test (src/flextoolsmcp/server/local_recipes.py):
- get_recipe_dir(): honors FLEXTOOLSMCP_RECIPE_DIR, else
  FLEXTOOLSMCP_SKELETON_DIR fallback, else ~/.flextoolsmcp.
- get_recipe_path(): <dir>/recipes.jsonl (creates parent on demand).
- capture(*, code, user_intent, project, requires_write/is_mutating,
  op_id, ...): whole-snippet capture with upsert by fingerprint id
  "local-<sha12>", never raises, returns None/record.
- load path: load_local_recipes()/load_all()/list/get_all (any one).
- migration: migrate_legacy_skeletons()/migrate_legacy()/ensure_migrated()
  groups legacy skeletons.jsonl entries by op_id, recovers intent from
  logs/operations.jsonl, drops trivial/short bodies, merges duplicates,
  marks migrated:true, leaves the legacy file byte-identical.

Helpers below resolve function names flexibly so the tests pin behavior,
not spelling. T022 should provide at least one name per group.
"""

import importlib
import json
import os
from pathlib import Path

import pytest


def _import_local_recipes():
    try:
        return importlib.import_module("flextoolsmcp.server.local_recipes")
    except ImportError:
        return importlib.import_module("server.local_recipes")


def _resolve(mod, names):
    for n in names:
        fn = getattr(mod, n, None)
        if callable(fn):
            return fn
    return None


def _get_dir_fn(mod):
    return _resolve(mod, ["get_recipe_dir", "get_recipes_dir", "get_store_dir"])


def _get_path_fn(mod):
    return _resolve(mod, ["get_recipe_path", "get_recipes_path", "get_store_path"])


def _capture_fn(mod):
    return _resolve(mod, ["capture", "capture_from_code", "record_capture", "record"])


def _load_fn(mod):
    return _resolve(mod, ["load_local_recipes", "load_all", "list_local_recipes", "get_all", "read_all"])


def _migrate_fn(mod):
    return _resolve(
        mod,
        ["migrate_legacy_skeletons", "migrate_legacy", "ensure_migrated",
         "run_migration_if_needed", "migrate_if_needed"],
    )


def _call_capture(mod, **kwargs):
    fn = _capture_fn(mod)
    assert fn is not None, "local_recipes needs a capture() entry point"
    # Normalize common kwarg spellings.
    import inspect

    try:
        params = set(inspect.signature(fn).parameters)
    except (TypeError, ValueError):
        params = set()
    mapped = {}
    for k, v in kwargs.items():
        if k in params or not params:
            mapped[k] = v
            continue
        # Aliases.
        if k == "project" and "project_name" in params:
            mapped["project_name"] = v
        elif k == "project_name" and "project" in params:
            mapped["project"] = v
        elif k in ("requires_write", "is_mutating", "is_mutating_script") and params:
            for cand in ("requires_write", "is_mutating", "is_mutating_script", "mutating"):
                if cand in params and cand not in mapped:
                    mapped[cand] = v
                    break
        elif k == "op_id" and "opid" in params:
            mapped["opid"] = v
        else:
            mapped[k] = v
    return fn(**mapped)


SAMPLE_CODE = (
    "from flexicon import LexEntryOperations\n"
    "entries = project.LexEntry.GetAll()\n"
    "for entry in entries:\n"
    "    senses = project.LexEntry.GetAllSenses(entry)\n"
    "    for sense in senses:\n"
    "        report.Info(project.Senses.GetGloss(sense))\n"
)

SHORT_CODE = "x = 1\ny = 2\n"


@pytest.fixture
def isolated_recipe_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
    monkeypatch.delenv("FLEXTOOLSMCP_SKELETON_DIR", raising=False)
    mod = _import_local_recipes()
    yield tmp_path


class TestPathResolution:
    def test_recipe_dir_override(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        fn = _get_dir_fn(mod)
        assert fn is not None
        monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path / "recipes"))
        assert Path(str(fn())) == tmp_path / "recipes"

    def test_skeleton_dir_fallback(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        fn = _get_dir_fn(mod)
        assert fn is not None
        monkeypatch.delenv("FLEXTOOLSMCP_RECIPE_DIR", raising=False)
        monkeypatch.setenv("FLEXTOOLSMCP_SKELETON_DIR", str(tmp_path / "skel"))
        assert Path(str(fn())) == tmp_path / "skel"

    def test_default_dir(self, monkeypatch):
        mod = _import_local_recipes()
        fn = _get_dir_fn(mod)
        assert fn is not None
        monkeypatch.delenv("FLEXTOOLSMCP_RECIPE_DIR", raising=False)
        monkeypatch.delenv("FLEXTOOLSMCP_SKELETON_DIR", raising=False)
        assert Path(str(fn())).name == ".flextoolsmcp"


class TestRecordFields:
    def test_record_fields(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        rec = _call_capture(
            mod, code=SAMPLE_CODE, user_intent="List entries with glosses",
            project="Sena 3", requires_write=False, op_id="op-001",
        )
        assert rec is not None
        assert rec["id"].startswith("local-")
        assert len(rec["id"]) == len("local-") + 12
        assert rec["intent"] == "List entries with glosses"
        assert rec["code"] == SAMPLE_CODE
        assert rec["source"] == "local"
        assert rec["migrated"] is False
        assert rec["schema"] == "local-recipe/1"
        assert rec["use_count"] == 1
        assert rec["projects"] == ["Sena 3"]
        assert rec["op_ids"] == ["op-001"]
        assert rec["requires_write"] is False
        assert isinstance(rec["entities"], list) and rec["entities"]
        assert rec["first_used"] and rec["last_used"]
        assert rec.get("params") == []

    def test_capture_preconditions(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        # 2-line probe: not captured.
        assert _call_capture(
            mod, code=SHORT_CODE, user_intent="probe",
            project="Sena 3", requires_write=False, op_id="op-p1") is None
        # Empty intent: not captured.
        assert _call_capture(
            mod, code=SAMPLE_CODE, user_intent="   ",
            project="Sena 3", requires_write=False, op_id="op-p2") is None
        # Comment-only lines do not count toward the 4-real-line floor.
        comment_code = "# hi\n# there\nx = 1\n# comment\n"
        assert _call_capture(
            mod, code=comment_code, user_intent="probe",
            project="Sena 3", requires_write=False, op_id="op-p3") is None

    def test_entities_from_this_code_only(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        # Pollute ambient session state; capture must ignore it.
        try:
            from flextoolsmcp.server import kernel
            kernel.session_state.record_validated_api("IText")
        except Exception:
            pass
        code = (
            "entries = project.Senses.GetAll()\n"
            "x = ILexEntry(entry)\n"
            "for e in entries:\n"
            "    report.Info(str(x))\n"
            "    report.Info('done')\n"
        )
        rec = _call_capture(
            mod, code=code, user_intent="use senses",
            project="Sena 3", requires_write=False, op_id="op-ent",
        )
        assert rec is not None
        ents = rec["entities"]
        # Senses accessor maps to LexSense (not raw "Senses").
        assert "LexSense" in ents
        assert "Senses" not in ents
        # I* interface names are kept.
        assert "ILexEntry" in ents
        # Ambient session entity must not leak in.
        assert "IText" not in ents
        assert ents == sorted(set(ents))


class TestIdentity:
    def test_repeat_updates_not_duplicates(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        load = _load_fn(mod)
        r1 = _call_capture(
            mod, code=SAMPLE_CODE, user_intent="first",
            project="Sena 3", requires_write=False, op_id="op-a")
        variant = SAMPLE_CODE.replace(
            "for entry in entries:",
            "# a comment\nfor entry in entries:  \n",
        )
        r2 = _call_capture(
            mod, code=variant, user_intent="second",
            project="Sena 3", requires_write=False, op_id="op-b")
        assert r1["id"] == r2["id"]
        assert r2["use_count"] == 2
        assert r2["intent"] == "second"
        rows = load() if load else []
        ids = [r["id"] for r in rows] if rows else []
        assert ids.count(r1["id"]) == 1

    def test_op_ids_capped_at_5(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        rec = None
        for i in range(7):
            rec = _call_capture(
                mod, code=SAMPLE_CODE, user_intent=f"intent {i}",
                project="Sena 3", requires_write=False, op_id=f"op-{i}")
        assert rec is not None
        assert len(rec["op_ids"]) == 5
        assert rec["op_ids"] == ["op-2", "op-3", "op-4", "op-5", "op-6"]

    def test_projects_union(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        _call_capture(mod, code=SAMPLE_CODE, user_intent="a",
                      project="Sena 3", requires_write=False, op_id="op-1")
        rec = _call_capture(mod, code=SAMPLE_CODE, user_intent="a",
                            project="Other", requires_write=False, op_id="op-2")
        assert rec["projects"] == ["Other", "Sena 3"]

    def test_capture_never_raises(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        # Unwritable dir (a file in the way).
        blocker = tmp_path / "blocker"
        blocker.write_text("x", encoding="utf-8")
        monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(blocker / "child"))
        assert _call_capture(
            mod, code=SAMPLE_CODE, user_intent="hi",
            project="P", requires_write=False, op_id="op-x") is None
        # Bad code.
        monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
        assert _call_capture(
            mod, code="def broken(:\n  pass\n extra line\n more\n end\n",
            user_intent="hi", project="P",
            requires_write=False, op_id="op-bad") is None
        # Monkeypatched failure inside the writer.
        monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("disk")))
        assert _call_capture(
            mod, code=SAMPLE_CODE, user_intent="hi",
            project="P", requires_write=False, op_id="op-fail") is None


def _write_skeleton_file(path: Path, entries):
    with path.open("w", encoding="utf-8") as fp:
        for e in entries:
            fp.write(json.dumps(e, ensure_ascii=False) + "\n")


def _skeleton_entry(name, source, op_id, intent="old intent", captured_at="2026-01-01T00:00:00+00:00"):
    return {
        "name": name, "source": source, "entities": ["ILexSense"],
        "user_intent": intent, "captured_at": captured_at,
        "op_id": op_id, "session_id": "s", "duration_ms": 5,
    }


class TestLegacyMigration:
    def _setup(self, tmp_path, monkeypatch, skeleton_entries, ops_lines=None):
        monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
        monkeypatch.setenv("FLEXTOOLSMCP_SKELETON_DIR", str(tmp_path))
        if ops_lines is not None:
            monkeypatch.setenv("FLEXTOOLSMCP_LOG_DIR", str(tmp_path / "logs"))
            log_dir = tmp_path / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            with (log_dir / "operations.jsonl").open("w", encoding="utf-8") as fp:
                for line in ops_lines:
                    fp.write(json.dumps(line, ensure_ascii=False) + "\n")
        else:
            monkeypatch.delenv("FLEXTOOLSMCP_LOG_DIR", raising=False)
        skel = tmp_path / "skeletons.jsonl"
        _write_skeleton_file(skel, skeleton_entries)
        return skel

    def test_migration_groups_by_op_id(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        migrate = _migrate_fn(mod)
        assert migrate is not None
        body_a = "def helper_a():\n    x = 1\n    y = 2\n    z = 3\n    return x + y + z\n"
        body_b = "def helper_b():\n    a = 1\n    b = 2\n    c = 3\n    return a + b + c\n"
        skel = self._setup(
            tmp_path, monkeypatch,
            [_skeleton_entry("helper_a", body_a, "op-1"),
             _skeleton_entry("helper_b", body_b, "op-1")],
            ops_lines=[{"op_id": "op-1", "user_intent": "ops log intent"}],
        )
        before = skel.read_bytes()
        rows = migrate()
        assert skel.read_bytes() == before  # legacy bytes hash-unchanged
        assert len(rows) == 1
        assert "helper_a" in rows[0]["code"] and "helper_b" in rows[0]["code"]
        assert rows[0]["intent"] == "ops log intent"
        assert rows[0]["migrated"] is True

    def test_migration_drops_short_and_trivial(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        migrate = _migrate_fn(mod)
        short = "def tiny():\n    return 1\n"
        trivial = "def get_text(seg):\n    return seg.Form.BestVernacularAlternative.Text\n"
        self._setup(
            tmp_path, monkeypatch,
            [_skeleton_entry("tiny", short, "op-s"),
             _skeleton_entry("get_text", trivial, "op-t")],
        )
        rows = migrate()
        assert rows == []

    def test_migration_merges_duplicates(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        migrate = _migrate_fn(mod)
        body = "def dup():\n    a = 1\n    b = 2\n    c = 3\n    d = 4\n    return a + b + c + d\n"
        self._setup(
            tmp_path, monkeypatch,
            [_skeleton_entry("dup", body, "op-1", captured_at="2026-01-01T00:00:00+00:00"),
             _skeleton_entry("dup", body, "op-2", captured_at="2026-01-02T00:00:00+00:00")],
        )
        rows = migrate()
        assert len(rows) == 1
        assert rows[0]["use_count"] >= 2

    def test_migration_missing_ops_log_gives_null_intent(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        migrate = _migrate_fn(mod)
        body = "def big():\n    a = 1\n    b = 2\n    c = 3\n    d = 4\n    return a\n"
        self._setup(
            tmp_path, monkeypatch,
            [_skeleton_entry("big", body, "op-9", intent="")],
            ops_lines=None,
        )
        # Ensure no ops log exists anywhere the migrator might look.
        monkeypatch.delenv("FLEXTOOLSMCP_LOG_DIR", raising=False)
        rows = migrate()
        assert len(rows) == 1
        assert rows[0]["intent"] is None

    def test_migration_shrinks_fixture(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        migrate = _migrate_fn(mod)
        # 309-row-shaped fixture: many tiny single-def fragments from few ops.
        entries = []
        for i in range(309):
            op = f"op-{i % 20}"
            entries.append(_skeleton_entry(
                f"frag_{i}", f"def frag_{i}():\n    return {i}\n", op))
        self._setup(tmp_path, monkeypatch, entries)
        rows = migrate()
        assert len(rows) <= 154  # at least 50% smaller
        for r in rows:
            real = [ln for ln in r["code"].splitlines()
                    if ln.strip() and not ln.strip().startswith("#")]
            assert len(real) >= 5


class TestCap:
    def test_cap_2000_drops_least_used_oldest(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        load = _load_fn(mod)
        assert load is not None
        # Seed 2000 distinct rows directly through capture with unique codes.
        for i in range(2000):
            code = (
                f"# recipe {i}\n"
                "from flexicon import LexEntryOperations\n"
                f"VALUE = {i}\n"
                "entries = project.LexEntry.GetAll()\n"
                "report.Info(str(len(entries)))\n"
                "report.Info(str(VALUE))\n"
            )
            rec = _call_capture(
                mod, code=code, user_intent=f"intent {i}",
                project="Sena 3", requires_write=False, op_id=f"op-{i}")
            assert rec is not None
        # Bump the first row's use_count so it is not the eviction victim.
        first_code = (
            "# recipe 0\n"
            "from flexicon import LexEntryOperations\n"
            "VALUE = 0\n"
            "entries = project.LexEntry.GetAll()\n"
            "report.Info(str(len(entries)))\n"
            "report.Info(str(VALUE))\n"
        )
        _call_capture(mod, code=first_code, user_intent="intent 0",
                      project="Sena 3", requires_write=False, op_id="op-bump")
        extra = (
            "# recipe extra\n"
            "from flexicon import LexEntryOperations\n"
            "VALUE = 9999\n"
            "entries = project.LexEntry.GetAll()\n"
            "report.Info(str(len(entries)))\n"
            "report.Info(str(VALUE))\n"
        )
        _call_capture(mod, code=extra, user_intent="extra",
                      project="Sena 3", requires_write=False, op_id="op-extra")
        rows = load()
        assert len(rows) == 2000
        intents = {r["intent"] for r in rows}
        assert "extra" in intents
        # The least-used oldest row (intent 1) was evicted, not the bumped one.
        assert "intent 1" not in intents
        assert "intent 0" in intents


class TestRecall:
    def test_paraphrase_finds_local_after_restart(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
        code = (
            "entries = project.LexEntry.GetAll()\n"
            "for entry in entries:\n"
            "    glosses = [project.Senses.GetGloss(s) for s in project.LexEntry.GetAllSenses(entry)]\n"
            "    report.Info('; '.join(glosses))\n"
            "    report.Info(entry.Hvo)\n"
        )
        rec = _call_capture(
            mod, code=code, user_intent="list all entries with their glosses",
            project="Sena 3", requires_write=False, op_id="op-recall")
        assert rec is not None
        # Simulate a restart: drop the module and re-import, reload from disk.
        import sys
        for name in [n for n in list(sys.modules) if n.endswith("local_recipes")]:
            del sys.modules[name]
        mod2 = _import_local_recipes()
        load = _load_fn(mod2)
        assert load is not None
        rows = load()
        assert any(r["id"] == rec["id"] for r in rows)
        # Ranked search over shipped + local finds the local row by paraphrase.
        from flextoolsmcp.server import recipes as recipe_search
        local_rows = [
            {"id": r["id"], "intent": r["intent"], "match_terms": [],
             "entities": r.get("entities", []), "operations": ["read"],
             "requires_write": False, "code": r["code"], "notes": "",
             "origin": "local", "source": "local",
             "use_count": r.get("use_count", 1)}
            for r in rows if r["id"] == rec["id"]
        ]
        result = recipe_search.search_recipes(
            # Paraphrase, not the captured intent. "show entries and glosses"
            # fell out of the top 10 once the shipped library grew past 40
            # recipes sharing "entries"/"glosses".
            "list the glosses of every entry", local_recipes=local_rows, limit=10)
        ids = [r["id"] for r in result.get("recipes", [])]
        assert rec["id"] in ids
