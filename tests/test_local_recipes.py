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


# ---------------------------------------------------------------------------
# Issue #309: remember gate, intent+entities dedupe, requires_write evidence,
# legacy write-flag repair, promote honours the corrected flag.
# ---------------------------------------------------------------------------

SWALLOW_CODE = (
    "for wf in project.Wordforms.GetAll():\n"
    "    try:\n"
    "        status = project.Wordforms.TryWord(wf)\n"
    "    except Exception:\n"
    "        status = 'No - Unknown issue'\n"
    "    report.Info('Analyzed %s: %s' % (wf, status))\n"
)

LITERAL_TABLE_CODE = (
    "UNPARSED = [('000', 154091), ('abc', 12)]\n"
    "for word, count in UNPARSED:\n"
    "    wf = project.Wordforms.Find(word)\n"
    "    report.Info('%s: %d' % (word, count))\n"
)

WRITE_CODE = (
    "entries = project.LexEntry.GetAll()\n"
    "for entry in entries:\n"
    "    form = project.LexEntry.GetLexemeForm(entry)\n"
    "    if form.endswith('-'):\n"
    "        project.LexEntry.SetLexemeForm(entry, form.rstrip('-'))\n"
)

MSGS = [{"type": "info", "message": "gloss one"},
        {"type": "info", "message": "gloss two"}]


class TestRememberGate:
    def test_swallowed_exception_not_remembered(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        assert mod.remember_rejection_reason(SWALLOW_CODE) is not None
        assert _call_capture(mod, code=SWALLOW_CODE, user_intent="top 10 unparsed",
                             project="P", op_id="op-sw", messages=MSGS) is None

    def test_skip_handlers_and_reported_errors_allowed(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        skip = SWALLOW_CODE.replace("status = 'No - Unknown issue'", "continue")
        reported = SWALLOW_CODE.replace(
            "status = 'No - Unknown issue'",
            "report.Warning('could not parse')\n        continue")
        uses_exc = SWALLOW_CODE.replace(
            "except Exception:\n        status = 'No - Unknown issue'",
            "except Exception as e:\n        status = 'failed: ' + str(e)")
        narrow = SWALLOW_CODE.replace("except Exception:", "except KeyError:")
        for code in (skip, reported, uses_exc, narrow):
            assert mod.remember_rejection_reason(code, MSGS) is None, code

    def test_literal_table_not_remembered(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        assert "literal" in (mod.remember_rejection_reason(LITERAL_TABLE_CODE) or "")
        assert _call_capture(mod, code=LITERAL_TABLE_CODE, user_intent="top unparsed",
                             project="P", op_id="op-lit", messages=MSGS) is None
        # Direct iteration over an inline table is flagged too.
        inline = LITERAL_TABLE_CODE.replace(
            "for word, count in UNPARSED:",
            "for word, count in sorted([('000', 154091)]):")
        assert mod.remember_rejection_reason(inline) is not None

    def test_literal_table_heuristic_is_conservative(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        # Flat literal filter lists are fine.
        flat = LITERAL_TABLE_CODE.replace(
            "UNPARSED = [('000', 154091), ('abc', 12)]", "UNPARSED = ['000', 'abc']"
        ).replace("for word, count in UNPARSED:", "for word in UNPARSED:\n    count = 0")
        assert mod.remember_rejection_reason(flat) is None
        # A table inside the PARAMS block is a tunable input, not fabricated data.
        params = (
            "# --- PARAMS ---\n"
            "UNPARSED = [('000', 154091), ('abc', 12)]\n"
            "# --- END PARAMS ---\n"
        ) + LITERAL_TABLE_CODE.split("\n", 1)[1]
        assert mod.remember_rejection_reason(params) is None

    def test_trivial_messages_not_remembered(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        repeated = [{"type": "info", "message": "Analyzed 000: No - Unknown issue"}] * 24
        assert _call_capture(mod, code=SAMPLE_CODE, user_intent="x", project="P",
                             op_id="op-t1", messages=repeated) is None
        assert _call_capture(mod, code=SAMPLE_CODE, user_intent="x", project="P",
                             op_id="op-t2", messages=[]) is None
        failing = [{"type": "info", "message": "wf1: 'X' object has no attribute 'TryWord'"},
                   {"type": "info", "message": "wf2: unknown error"}]
        assert _call_capture(mod, code=SAMPLE_CODE, user_intent="x", project="P",
                             op_id="op-t3", messages=failing) is None
        # Distinct messages that merely share a template are real output.
        varied = [{"type": "info", "message": f"entry {w}: 2 senses"} for w in ("a", "b", "c")]
        assert _call_capture(mod, code=SAMPLE_CODE, user_intent="x", project="P",
                             op_id="op-t4", messages=varied) is not None

    def test_new_rows_marked_unverified(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        rec = _call_capture(mod, code=SAMPLE_CODE, user_intent="glosses",
                            project="P", op_id="op-v", messages=MSGS)
        assert rec is not None and rec["verified"] is False


class TestIntentEntitiesDedupe:
    def test_same_intent_and_entities_collapse(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        load = _load_fn(mod)
        r1 = _call_capture(mod, code=SAMPLE_CODE, user_intent="Top 10 unparsed wordforms",
                           project="P", op_id="op-1", messages=MSGS)
        drifted = SAMPLE_CODE + "report.Info('done')\n"
        r2 = _call_capture(mod, code=drifted, user_intent="top 10  unparsed wordforms.",
                           project="P", op_id="op-2", messages=MSGS)
        assert r1 is not None and r2 is not None
        assert r2["id"] == r1["id"]
        assert r2["use_count"] == 2
        assert r2["code"] == drifted  # newest successful code wins
        assert len(load()) == 1

    def test_different_entities_do_not_collapse(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        load = _load_fn(mod)
        _call_capture(mod, code=SAMPLE_CODE, user_intent="same intent",
                      project="P", op_id="op-1", messages=MSGS)
        other = (
            "texts = project.Texts.GetAll()\n"
            "for t in texts:\n"
            "    name = project.Texts.GetName(t)\n"
            "    report.Info(name)\n"
        )
        _call_capture(mod, code=other, user_intent="same intent",
                      project="P", op_id="op-2", messages=MSGS)
        assert len(load()) == 2


class TestRequiresWriteEvidence:
    def test_derive_requires_write(self):
        mod = _import_local_recipes()
        d = mod.derive_requires_write
        assert d(SAMPLE_CODE) is False
        assert d(SAMPLE_CODE, declared=True) is True
        assert d(SAMPLE_CODE, performs_writes=True) is True
        assert d(SAMPLE_CODE, write_enabled=True, lcm_undoable_action_count=3) is True
        # Write-enabled with no count reported: when in doubt, write.
        assert d(SAMPLE_CODE, write_enabled=True) is True
        # Write-enabled, LCM saw nothing, code reads only: stays read.
        assert d(SAMPLE_CODE, write_enabled=True, lcm_undoable_action_count=0) is False
        # Write-shaped code is a write even when the caller said otherwise.
        assert d(WRITE_CODE, write_enabled=False) is True

    def test_capture_stores_write_evidence(self, isolated_recipe_dir):
        mod = _import_local_recipes()
        rec = _call_capture(mod, code=SAMPLE_CODE, user_intent="repair features",
                            project="P", op_id="op-w", requires_write=False,
                            write_enabled=True, lcm_undoable_action_count=12,
                            messages=MSGS)
        assert rec["requires_write"] is True
        assert rec["operations"] == ["read", "write"]
        rec2 = _call_capture(mod, code=WRITE_CODE, user_intent="strip hyphens",
                             project="P", op_id="op-w2", requires_write=False,
                             messages=MSGS)
        assert rec2["requires_write"] is True


def _legacy_row(rid, code, op_ids=None, intent="legacy"):
    return {
        "id": rid, "intent": intent, "code": code, "entities": [],
        "requires_write": False, "operations": ["read"], "params": [],
        "projects": [], "first_used": "2026-09-01T00:00:00+00:00",
        "last_used": "2026-09-01T00:00:00+00:00", "use_count": 1,
        "op_ids": op_ids or [], "source": "local", "migrated": False,
        "schema": "local-recipe/1",
    }


class TestLegacyWriteRepair:
    def _seed(self, tmp_path, monkeypatch, rows, ops_lines=None):
        monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
        monkeypatch.delenv("FLEXTOOLSMCP_SKELETON_DIR", raising=False)
        log_dir = tmp_path / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("FLEXTOOLSMCP_LOG_DIR", str(log_dir))
        with (log_dir / "operations.jsonl").open("w", encoding="utf-8") as fp:
            for line in ops_lines or []:
                fp.write(json.dumps(line) + "\n")
        with (tmp_path / "recipes.jsonl").open("w", encoding="utf-8") as fp:
            for r in rows:
                fp.write(json.dumps(r) + "\n")

    def test_write_shaped_legacy_row_flipped_on_load(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        self._seed(tmp_path, monkeypatch, [
            _legacy_row("local-aaaaaaaaaaaa", WRITE_CODE, intent="Normalize allomorphs"),
            _legacy_row("local-bbbbbbbbbbbb", SAMPLE_CODE, intent="list glosses"),
        ])
        rows = {r["id"]: r for r in _load_fn(mod)()}
        fixed = rows["local-aaaaaaaaaaaa"]
        assert fixed["requires_write"] is True
        assert fixed["operations"] == ["read", "write"]
        assert fixed["requires_write_repaired"] is True
        assert rows["local-bbbbbbbbbbbb"]["requires_write"] is False
        # Persisted, not just patched in memory.
        on_disk = [json.loads(ln) for ln in
                   (tmp_path / "recipes.jsonl").read_text(encoding="utf-8").splitlines()]
        assert {r["id"]: r["requires_write"] for r in on_disk}["local-aaaaaaaaaaaa"] is True

    def test_row_from_write_enabled_op_flipped(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        self._seed(tmp_path, monkeypatch, [
            _legacy_row("local-cccccccccccc", SAMPLE_CODE, op_ids=["op-w1"]),
            _legacy_row("local-dddddddddddd", SAMPLE_CODE + "report.Info('x')\n",
                        op_ids=["op-r1"]),
        ], ops_lines=[{"op_id": "op-w1", "write_enabled": True},
                      {"op_id": "op-r1", "write_enabled": False}])
        rows = {r["id"]: r for r in _load_fn(mod)()}
        assert rows["local-cccccccccccc"]["requires_write"] is True
        assert rows["local-dddddddddddd"]["requires_write"] is False

    def test_promote_honours_repaired_flag(self, tmp_path, monkeypatch):
        import importlib
        cli = importlib.import_module("flextoolsmcp.recipe_cli")
        self._seed(tmp_path, monkeypatch, [
            _legacy_row("local-eeeeeeeeeeee", WRITE_CODE, intent="Consolidate verb slots"),
        ])
        out = tmp_path / "drafts"
        rc = cli.main(["promote", "local-eeeeeeeeeeee", "--id", "consolidate-slots",
                       "--out", str(out)])
        assert rc == 0
        text = (out / "consolidate-slots.py").read_text(encoding="utf-8")
        assert "requires_write: true" in text
        assert 'operations: ["read", "write"]' in text

    def test_render_draft_never_downgrades_write_operations(self):
        from flextoolsmcp import recipe_files
        rec = _legacy_row("local-ffffffffffff", SAMPLE_CODE)
        rec["operations"] = ["read", "write"]
        text = recipe_files.render_draft(rec, "some-draft")
        assert "requires_write: true" in text


# ---------------------------------------------------------------------------
# Issue #309 QC follow-ups: fail-closed write detection, repair survives a
# failed persist, locked load, unique temp files, migration derivation.
# ---------------------------------------------------------------------------

# A Flexicon mutator the detect_cud_operations regexes do not know.
UNKNOWN_MUTATOR_CODE = (
    "entries = project.LexEntry.GetAll()\n"
    "for entry in entries:\n"
    "    form = project.LexEntry.GetLexemeForm(entry)\n"
    "    if form:\n"
    "        project.Allomorphs.AddToEntry(entry, form + '-a')\n"
)


class TestWriteDetectionWithoutIndex:
    def test_unknown_mutator_is_write_when_index_unavailable(self, monkeypatch):
        mod = _import_local_recipes()
        from flextoolsmcp.server import kernel, validators
        monkeypatch.setattr(kernel, "get_api_index", lambda: None)
        # Pin the gap: the regex fallback alone would call this read-only.
        assert validators.detect_cud_operations(UNKNOWN_MUTATOR_CODE)["is_cud"] is False
        assert mod.derive_requires_write(UNKNOWN_MUTATOR_CODE) is True

    def test_index_lookup_raising_does_not_fail_open(self, monkeypatch):
        mod = _import_local_recipes()
        from flextoolsmcp.server import kernel

        def _boom():
            raise RuntimeError("index not loaded")
        monkeypatch.setattr(kernel, "get_api_index", _boom)
        assert mod.derive_requires_write(UNKNOWN_MUTATOR_CODE) is True
        raw_lcm = UNKNOWN_MUTATOR_CODE.replace(
            "project.Allomorphs.AddToEntry(entry, form + '-a')",
            "entry.MorphoSyntaxAnalysisRA = None")
        assert mod.derive_requires_write(raw_lcm) is True

    def test_python_builtins_are_not_mutators(self, monkeypatch):
        mod = _import_local_recipes()
        from flextoolsmcp.server import kernel
        monkeypatch.setattr(kernel, "get_api_index", lambda: None)
        code = (
            "rows = []\n"
            "seen = set()\n"
            "for entry in project.LexEntry.GetAll():\n"
            "    rows.append(project.LexEntry.GetHeadword(entry).replace('-', ''))\n"
            "    seen.add(entry.Hvo)\n"
            "report.Info(str(len(rows)))\n"
        )
        assert mod.derive_requires_write(code) is False


class TestRepairPersistFailure:
    def test_load_returns_repaired_rows_when_persist_fails(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        TestLegacyWriteRepair()._seed(tmp_path, monkeypatch, [
            _legacy_row("local-111111111111", WRITE_CODE, intent="Normalize allomorphs"),
        ])

        def _fail(*_a, **_k):
            raise PermissionError("recipes.jsonl is open in another process")
        monkeypatch.setattr(mod, "_atomic_write", _fail)
        rows = _load_fn(mod)()
        assert rows and rows[0]["requires_write"] is True
        # Not persisted yet ...
        on_disk = json.loads((tmp_path / "recipes.jsonl").read_text(encoding="utf-8"))
        assert on_disk["requires_write"] is False
        # ... and retried on the next load once writing works again.
        monkeypatch.undo()
        TestLegacyWriteRepair()._seed(tmp_path, monkeypatch, [
            _legacy_row("local-111111111111", WRITE_CODE, intent="Normalize allomorphs"),
        ])
        rows = _load_fn(mod)()
        assert rows[0]["requires_write"] is True
        on_disk = json.loads((tmp_path / "recipes.jsonl").read_text(encoding="utf-8"))
        assert on_disk["requires_write"] is True

    def test_load_holds_write_lock(self, isolated_recipe_dir, monkeypatch):
        mod = _import_local_recipes()
        import threading
        entered = []

        class _Recording:
            def __init__(self):
                self._lock = threading.Lock()

            def __enter__(self):
                entered.append(True)
                return self._lock.__enter__()

            def __exit__(self, *a):
                return self._lock.__exit__(*a)

        monkeypatch.setattr(mod, "_WRITE_LOCK", _Recording())
        _load_fn(mod)()
        assert entered


class TestAtomicWriteTempFile:
    def test_unique_temp_and_no_leftovers(self, tmp_path):
        mod = _import_local_recipes()
        path = tmp_path / "recipes.jsonl"
        # A stale fixed-name temp from an old writer must not be reused.
        (tmp_path / "recipes.jsonl.tmp").write_text("junk", encoding="utf-8")
        mod._atomic_write(path, [{"id": "local-a"}])
        assert json.loads(path.read_text(encoding="utf-8")) == {"id": "local-a"}
        leftovers = sorted(p.name for p in tmp_path.iterdir())
        assert leftovers == ["recipes.jsonl", "recipes.jsonl.tmp"]

    def test_temp_cleaned_up_on_failure(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        path = tmp_path / "recipes.jsonl"
        monkeypatch.setattr(os, "replace", lambda *a, **k: (_ for _ in ()).throw(
            PermissionError("locked")))
        with pytest.raises(PermissionError):
            mod._atomic_write(path, [{"id": "local-a"}])
        assert list(tmp_path.iterdir()) == []


class TestMigrationDerivesWrite:
    def test_migrated_write_skeleton_requires_write(self, tmp_path, monkeypatch):
        mod = _import_local_recipes()
        monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(tmp_path))
        monkeypatch.setenv("FLEXTOOLSMCP_SKELETON_DIR", str(tmp_path))
        monkeypatch.delenv("FLEXTOOLSMCP_LOG_DIR", raising=False)
        body = (
            "def strip_hyphens(project):\n"
            "    for entry in project.LexEntry.GetAll():\n"
            "        form = project.LexEntry.GetLexemeForm(entry)\n"
            "        if form.endswith('-'):\n"
            "            project.LexEntry.SetLexemeForm(entry, form.rstrip('-'))\n"
        )
        _write_skeleton_file(tmp_path / "skeletons.jsonl",
                             [_skeleton_entry("strip_hyphens", body, "op-m1")])
        rows = _migrate_fn(mod)()
        assert len(rows) == 1
        assert rows[0]["requires_write"] is True
        assert rows[0]["operations"] == ["read", "write"]


class TestPlaceholderHandlerPinned:
    def test_string_placeholder_in_broad_handler_rejected(self):
        """Intentional: `except Exception: label = "(none)"` is not remembered.

        A string placeholder turns a failure into plausible output -- the
        #309 "No - Unknown issue" case is exactly that shape -- and not
        remembering a run is cheap. Empty-string / None / pass / continue
        fallbacks, and handlers that report or use the exception, stay
        allowed.
        """
        mod = _import_local_recipes()
        code = (
            "for sense in project.Senses.GetAll():\n"
            "    try:\n"
            "        label = project.Senses.GetPartOfSpeech(sense)\n"
            "    except Exception:\n"
            "        label = '(none)'\n"
            "    report.Info(label)\n"
        )
        assert mod.remember_rejection_reason(code) is not None
        assert mod.remember_rejection_reason(
            code.replace("label = '(none)'", "label = ''")) is None
