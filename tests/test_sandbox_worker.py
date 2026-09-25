#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The parse worker's `--sandbox` mode (parser-check CP5 re-plan, T096/T098/T112;
contracts/sandbox-worker.md sections 1-8).

Three layers, none of which needs FieldWorks:

  * `hc_engine`'s pure helpers -- the id map, the parameters, and FLEx's
    Try A Word shaping (`HCParser.GetMorphs`), one test per rule;
  * `ParseWorker` driven in-process over `_StubSandboxBackend`, which is
    `_SandboxBackend` with only its two engine methods replaced -- the
    refusals (D1), the outcome shapes, the load and id-map failures, and the
    held Morpher;
  * a real `--stub --sandbox` child started through `ParseWorkerClient`
    with a `SandboxSpawn`, so the argv hook and `main()`'s routing are the
    ones that run in production.

The live engine is exercised by T110 (`tests/test_parse_live_cp5.py`).

Run with:
    python -m pytest tests/test_sandbox_worker.py -q
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse import hc_engine  # noqa: E402
from flextoolsmcp.server.parse import worker_main as wm  # noqa: E402
from flextoolsmcp.server.parse.hc_engine import (  # noqa: E402
    IdMap,
    RawMorph,
    shape_analysis,
)
from flextoolsmcp.server.parse.worker_client import (  # noqa: E402
    ParseWorkerClient,
    SandboxSpawn,
    WorkerError,
)

CIRCUMFIX = hc_engine.MORPH_TYPE_CIRCUMFIX
INFIX = hc_engine.MORPH_TYPE_INFIX
SUFFIX = "d7f713dd-e8cf-11d3-9764-00c04f186933"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _form(guid_suffix, morph_type=SUFFIX):
    return {"guid": f"g{guid_suffix}", "class": "MoAffixAllomorph", "role": "form",
            "morph_type_guid": morph_type}


def _msa(guid_suffix):
    return {"guid": f"m{guid_suffix}", "class": "MoInflAffMsa", "role": "msa"}


#: A synthetic `lcm-ids.json` covering every rule (T112).
IDS = {
    "10": _form(10, "d7f713e5-e8cf-11d3-9764-00c04f186933"),  # a root
    "11": _form(11),
    "12": _form(12, CIRCUMFIX),          # an affix-process circumfix
    "13": _form(13),                     # a two-part circumfix's first part
    "14": _form(14),                     # ... and its ID2 second part
    "15": _form(15, INFIX),
    "100": _msa(100),
    "101": _msa(101),
    "102": _msa(102),
    "103": _msa(103),
    "104": _msa(104),
    "200": {"guid": "i200", "class": "LexEntryInflType", "role": "infl_type"},
}
ID_MAP = IdMap(ids=IDS)


def _m(form, form_id, msa_id, key=None, **kw):
    return RawMorph(form=form, gloss=form.upper(), guessed=kw.pop("guessed", False),
                    form_id=form_id, msa_id=msa_id, morpheme_key=key or form, **kw)


def _forms(shaped):
    return [m["form"] for m in shaped]


def _write_map(tmp_path, *, valid=True, ids=None, invalid_ids=()):
    path = tmp_path / "lcm-ids.json"
    path.write_text(json.dumps({
        "schema": hc_engine.ID_MAP_SCHEMA, "valid": valid,
        "ids": IDS if ids is None else ids, "invalid_ids": list(invalid_ids),
    }), encoding="utf-8")
    return str(path)


def _write_script(tmp_path, script):
    path = tmp_path / "hc-config.json"
    path.write_text(json.dumps(script), encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# 1. Shaping: HCParser.GetMorphs, one rule per test (FR-050)
# ---------------------------------------------------------------------------


class TestShapingRules:
    def test_rule_a_skips_a_zero_or_absent_form_id(self):
        shaped = shape_analysis(
            [_m("zero", 0, 100), _m("absent", None, 101), _m("root", 10, 102)],
            ID_MAP, named_sandbox=False,
        )
        assert _forms(shaped) == ["root"]

    def test_rule_a_named_sandbox_emits_a_morph_with_no_id_as_user_added(self):
        shaped = shape_analysis(
            [_m("handmade", None, None), _m("root", 10, 102)],
            ID_MAP, named_sandbox=True,
        )
        assert _forms(shaped) == ["handmade", "root"]
        assert shaped[0]["user_added"] is True and shaped[1]["user_added"] is False

    def test_rule_a_named_sandbox_still_skips_an_explicit_zero(self):
        shaped = shape_analysis([_m("zero", 0, 100), _m("root", 10, 102)],
                                ID_MAP, named_sandbox=True)
        assert _forms(shaped) == ["root"]

    def test_rule_b_affix_process_circumfix_appears_before_and_after(self):
        # LT-21447: FLEx emits both occurrences; the second is the suffix portion.
        raw = [
            _m("ke", 12, 100, key="circ", is_affix_process=True),
            _m("root", 10, 102),
            _m("an", 12, 100, key="circ", is_affix_process=True),
        ]
        shaped = shape_analysis(raw, ID_MAP, named_sandbox=False)
        assert _forms(shaped) == ["ke", "root", "an"]
        assert [m["is_circumfix"] for m in shaped] == [False, False, True]

    def test_rule_c_a_repeated_morpheme_is_skipped(self):
        raw = [_m("a", 11, 100, key="k"), _m("root", 10, 102), _m("a", 11, 100, key="k")]
        assert _forms(shape_analysis(raw, ID_MAP, named_sandbox=False)) == ["a", "root"]

    def test_rule_c_keys_on_the_msa_when_the_engine_id_is_unset(self):
        # GenerateHCConfig leaves `Morpheme.Id` unset (live: memukul came back
        # as `mem` alone). Distinct MSAs must stay distinct morphemes.
        raw = [
            _m("mem", 11, 100, key=hc_engine.morpheme_key(100, None, 0)),
            _m("ukul", 10, 102, key=hc_engine.morpheme_key(102, None, 1)),
        ]
        assert _forms(shape_analysis(raw, ID_MAP, named_sandbox=False)) == ["mem", "ukul"]

    def test_a_shaped_morph_shows_the_allomorph_form_not_the_surface(self):
        # FLEx's MorphInfo.Form: `meŋ` + `pukul`, where the engine matched
        # `mem` + `ukul`. A guessed morph keeps its surface (GuessedString).
        ids = dict(IDS)
        ids["11"] = dict(IDS["11"], form="meŋ")
        ids["10"] = dict(IDS["10"], form="pukul")
        id_map = IdMap(ids=ids)
        shaped = shape_analysis([_m("mem", 11, 100), _m("ukul", 10, 102)],
                                id_map, named_sandbox=False)
        assert _forms(shaped) == ["meŋ", "pukul"]
        guessed = shape_analysis([_m("mem", 11, 100), _m("ukul", 10, 102, guessed=True)],
                                 id_map, named_sandbox=False)
        assert _forms(guessed) == ["meŋ", "ukul"]

    def test_a_map_entry_without_form_text_keeps_the_surface(self):
        shaped = shape_analysis([_m("mem", 11, 100), _m("ukul", 10, 102)],
                                ID_MAP, named_sandbox=False)
        assert _forms(shaped) == ["mem", "ukul"]

    def test_morpheme_key_prefers_msa_then_engine_id_then_position(self):
        assert hc_engine.morpheme_key(100, "e1", 0) == hc_engine.morpheme_key(100, "e2", 5)
        # An inflectional variant shares its main entry's MSA, not its identity.
        assert hc_engine.morpheme_key(100, None, 0) != hc_engine.morpheme_key(100, None, 1, 200)
        assert hc_engine.morpheme_key(None, "e1", 0) == hc_engine.morpheme_key(None, "e1", 3)
        assert hc_engine.morpheme_key(None, None, 0) != hc_engine.morpheme_key(None, None, 1)
        assert hc_engine.morpheme_key(None, "", 0) != hc_engine.morpheme_key(None, "", 1)

    def test_rule_c_a_repeated_morpheme_with_id2_is_re_emitted(self):
        raw = [
            _m("pre", 13, 103, key="two-part", form_id2=14),
            _m("root", 10, 102),
            _m("suf", 13, 103, key="two-part", form_id2=14),
        ]
        shaped = shape_analysis(raw, ID_MAP, named_sandbox=False)
        assert _forms(shaped) == ["pre", "root", "suf"]
        assert all(m["is_circumfix"] for m in (shaped[0], shaped[2]))

    @pytest.mark.parametrize("morph", [
        _m("lost-form", 99, 100),
        _m("lost-msa", 11, 999),
        _m("no-msa", 11, None),
        _m("lost-infl", 11, 100, infl_type_id=999),
    ])
    def test_rule_d_drops_the_whole_analysis(self, morph):
        assert shape_analysis([_m("root", 10, 102), morph], ID_MAP,
                              named_sandbox=False) is None

    def test_rule_d_accepts_a_known_infl_type(self):
        shaped = shape_analysis([_m("root", 10, 102), _m("x", 11, 100, infl_type_id=200)],
                                ID_MAP, named_sandbox=False)
        assert _forms(shaped) == ["root", "x"]

    def test_rule_d_checks_the_role_not_just_the_number(self):
        # An MSA id used as a form id is not a MoForm: FLEx's TryGetObject fails.
        assert shape_analysis([_m("x", 100, 100)], ID_MAP, named_sandbox=False) is None

    def test_rule_d_exempts_a_user_added_morph(self):
        shaped = shape_analysis([_m("handmade", None, 999), _m("root", 10, 102)],
                                ID_MAP, named_sandbox=True)
        assert _forms(shaped) == ["handmade", "root"]

    def test_an_infix_is_placed_before_the_morph_it_interrupts(self):
        raw = [_m("pre", 11, 100), _m("root", 10, 102), _m("in", 15, 104)]
        assert _forms(shape_analysis(raw, ID_MAP, named_sandbox=False)) == ["pre", "in", "root"]

    def test_guessed_is_carried_per_morph(self):
        shaped = shape_analysis([_m("root", 10, 102, guessed=True), _m("x", 11, 100)],
                                ID_MAP, named_sandbox=False)
        assert [m["guessed"] for m in shaped] == [True, False]

    def test_unshaped_emits_every_morph_in_engine_order(self):
        raw = [_m("zero", 0, 100), _m("a", 11, 100, key="k"), _m("a", 11, 100, key="k")]
        assert _forms(hc_engine.unshaped(raw)) == ["zero", "a", "a"]


# ---------------------------------------------------------------------------
# 2. The id map and the parameters
# ---------------------------------------------------------------------------


class TestIdMapAndParameters:
    def test_a_valid_map_loads(self, tmp_path):
        assert hc_engine.load_id_map(_write_map(tmp_path)).form(10) is not None

    def test_a_map_recorded_invalid_is_refused_naming_its_ids(self, tmp_path):
        with pytest.raises(hc_engine.IdMapInvalid, match="4918"):
            hc_engine.load_id_map(_write_map(tmp_path, valid=False, invalid_ids=[4918]))

    @pytest.mark.parametrize("text", ["{not json", "[]", '{"schema": "other/1", "valid": true}'])
    def test_an_unreadable_map_is_refused(self, tmp_path, text):
        path = tmp_path / "lcm-ids.json"
        path.write_text(text, encoding="utf-8")
        with pytest.raises(hc_engine.IdMapInvalid):
            hc_engine.load_id_map(str(path))

    def test_parameters_default_to_flex(self):
        assert hc_engine.load_hc_parameters(None) == hc_engine.DEFAULT_HC_PARAMETERS

    def test_parameters_override_only_known_keys(self, tmp_path):
        path = tmp_path / "p.json"
        path.write_text(json.dumps({"max_roots": 4, "guess_roots": False, "other": 1}),
                        encoding="utf-8")
        resolved = hc_engine.load_hc_parameters(str(path))
        assert resolved["max_roots"] == 4 and resolved["guess_roots"] is False
        assert "other" not in resolved and resolved["del_reapps"] == 0

    def test_an_explicit_engine_dir_without_the_dll_is_unavailable(self, tmp_path):
        with pytest.raises(hc_engine.EngineUnavailable, match=hc_engine.ENGINE_DLL):
            hc_engine.resolve_engine_dir(str(tmp_path))


# ---------------------------------------------------------------------------
# 3. ParseWorker over the sandbox backend, in-process
# ---------------------------------------------------------------------------


def _worker(backend):
    out = []
    worker = wm.ParseWorker(None, backend=backend, idle_timeout=5, emit=out.append)
    return worker, out


def _parse_msg(word, index=0, run_id="run", **extra):
    return {"type": "parse", "request_id": f"r{index}", "run_id": run_id,
            "wordform": word, "level": "batch", "index_in_run": index, **extra}


def _drive(worker, messages):
    for message in messages:
        worker.handle_message(message)
    worker.handle_message({"type": "shutdown"})
    worker.run()


def _by_type(out, kind):
    return [m for m in out if m.get("type") == kind]


class TestSandboxWorker:
    @pytest.mark.parametrize("kind", sorted(wm.SANDBOX_REFUSED_MESSAGES))
    def test_project_bound_messages_are_refused(self, tmp_path, kind):
        worker, out = _worker(wm._StubSandboxBackend(_write_script(tmp_path, {})))
        worker.handle_message({"type": kind, "request_id": "q"})
        assert out == [{"type": "error", "request_id": "q", "run_id": None,
                        "error_code": None, "detail": None,
                        "message": wm.SANDBOX_REFUSAL_MESSAGE}]

    def test_a_restricted_parse_is_refused(self, tmp_path):
        worker, out = _worker(wm._StubSandboxBackend(_write_script(tmp_path, {})))
        worker.handle_message(_parse_msg("w", restricted_to=[1]))
        assert out[0]["message"] == wm.SANDBOX_REFUSAL_MESSAGE
        assert worker._queue.dequeue() is None

    def test_outcomes_have_the_contract_shape(self, tmp_path):
        script = {"words": {
            "none": [],
            "bad": {"invalid_segment": 2},
            "boom": {"error": "kaput"},
            "two": [[{"form": "a", "gloss": "A", "guessed": True, "form_id": 1, "msa_id": 2}]],
        }}
        worker, out = _worker(wm._StubSandboxBackend(_write_script(tmp_path, script)))
        _drive(worker, [_parse_msg(w, i) for i, w in enumerate(["ok", "none", "bad", "boom", "two"])])
        parses = {m["wordform"]: m["parse"] for m in _by_type(out, "result")}
        assert parses["ok"]["outcome"] == "parsed"
        assert parses["ok"]["analyses"][0]["morphs"][0] == {
            "form": "ok", "gloss": "stub", "guessed": False,
            "is_circumfix": False, "user_added": False}
        assert parses["none"] == {"outcome": "not_parsed", "analyses": None, "position": None,
                                  "error_message": None, "parse_time_ms": parses["none"]["parse_time_ms"]}
        assert parses["bad"]["outcome"] == "invalid_segment" and parses["bad"]["position"] == 2
        assert parses["bad"]["parse_time_ms"] is None
        assert parses["boom"]["outcome"] == "error"
        assert parses["boom"]["error_message"] == "RuntimeError: kaput"
        assert parses["two"]["analyses"][0]["guessed"] is True
        assert all(m["trace_xml"] is None for m in _by_type(out, "result"))

    def test_an_analysis_dropped_by_rule_d_leaves_not_parsed(self, tmp_path):
        script = {"words": {"w": [[{"form": "w", "gloss": "W", "guessed": False,
                                    "form_id": 999, "msa_id": 100}]]}}
        backend = wm._StubSandboxBackend(_write_script(tmp_path, script),
                                         id_map_path=_write_map(tmp_path))
        worker, out = _worker(backend)
        _drive(worker, [_parse_msg("w")])
        parse = _by_type(out, "result")[0]["parse"]
        assert parse["outcome"] == "not_parsed" and parse["analyses"] is None

    def test_the_baseline_reports_parameters_applied_and_shaping(self, tmp_path):
        params = tmp_path / "p.json"
        params.write_text(json.dumps({"max_alternatives": 3}), encoding="utf-8")
        backend = wm._StubSandboxBackend(
            _write_script(tmp_path, {"load_errors": [{"type": "X", "id": "e1", "message": "m"}]}),
            hc_params_path=str(params), id_map_path=_write_map(tmp_path))
        worker, out = _worker(backend)
        _drive(worker, [_parse_msg("a", 0), _parse_msg("b", 1)])
        baselines = _by_type(out, "load_baseline")
        assert len(baselines) == 1  # once per run
        baseline = baselines[0]["baseline"]
        assert baseline["id_map"] == "valid"
        assert baseline["parameters"]["max_alternatives"] == 3
        assert "max_alternatives" not in baseline["parameters_applied"]
        assert baseline["errors"] == [{"type": "X", "id": "e1", "message": "m"}]
        # The baseline arrives before the first word's result.
        kinds = [m["type"] for m in out]
        assert kinds.index("load_baseline") < kinds.index("result")

    def test_no_id_map_means_unshaped_and_absent(self, tmp_path):
        script = {"words": {"w": [[{"form": "z", "gloss": "Z", "guessed": False, "form_id": 0}]]}}
        worker, out = _worker(wm._StubSandboxBackend(_write_script(tmp_path, script)))
        _drive(worker, [_parse_msg("w")])
        assert _by_type(out, "load_baseline")[0]["baseline"]["id_map"] == "absent"
        assert _by_type(out, "result")[0]["parse"]["analyses"][0]["morphs"][0]["form"] == "z"

    def test_an_invalid_id_map_fails_the_first_parse_and_every_later_one(self, tmp_path):
        backend = wm._StubSandboxBackend(
            _write_script(tmp_path, {}),
            id_map_path=_write_map(tmp_path, valid=False, invalid_ids=[7]))
        worker, out = _worker(backend)
        _drive(worker, [_parse_msg("a", 0), _parse_msg("b", 1)])
        errors = _by_type(out, "error")
        assert [e["error_code"] for e in errors] == ["parser_job_failed"] * 2
        assert all(e["detail"] == {"failure": "id_map_invalid"} for e in errors)
        assert "7" in errors[0]["message"]
        assert _by_type(out, "result") == [] and backend.load_count == 0

    def test_an_unloadable_config_surfaces_once_and_is_never_reloaded(self, tmp_path):
        backend = wm._StubSandboxBackend(_write_script(tmp_path, {"load_fail": "broken XML"}))
        calls = []
        original = backend._load_engine
        backend._load_engine = lambda: (calls.append(1), original())[1]
        worker, out = _worker(backend)
        _drive(worker, [_parse_msg("a", 0), _parse_msg("b", 1)])
        errors = _by_type(out, "error")
        assert len(errors) == 2
        assert all(e["detail"] == {"failure": "engine_unavailable"} for e in errors)
        assert "broken XML" in errors[0]["message"]
        assert calls == [1]

    def test_idle_release_keeps_the_morpher(self, tmp_path):
        backend = wm._StubSandboxBackend(_write_script(tmp_path, {}))
        worker, out = _worker(backend)
        worker.handle_message(_parse_msg("a", 0))
        worker.handle_message({"type": "shutdown"})
        worker.run()
        worker._release_if_idle()
        worker.release()
        worker._draining.clear()
        worker.handle_message(_parse_msg("b", 1, run_id="run2"))
        worker.handle_message({"type": "shutdown"})
        worker.run()
        assert backend.load_count == 1
        assert len(_by_type(out, "result")) == 2

    def test_cancel_drops_queued_words(self, tmp_path):
        worker, out = _worker(wm._StubSandboxBackend(_write_script(tmp_path, {})))
        worker.handle_message(_parse_msg("a", 0))
        worker.handle_message({"type": "cancel", "run_id": "run"})
        worker.handle_message({"type": "shutdown"})
        worker.run()
        assert _by_type(out, "result") == []
        assert _by_type(out, "cancelled")[0]["words_completed"] == 0


# ---------------------------------------------------------------------------
# 4. The argv hook and main()'s routing, in a real child (T098)
# ---------------------------------------------------------------------------


class TestSandboxSpawn:
    def test_argv_carries_only_what_is_given(self):
        assert SandboxSpawn(config="c.xml").argv() == ["--sandbox", "--config", "c.xml"]
        full = SandboxSpawn(config="c.xml", hc_params="p.json", id_map="m.json",
                            engine_dir="E", project="Proj", named_sandbox=True)
        assert full.argv() == ["--sandbox", "--config", "c.xml", "--hc-params", "p.json",
                               "--id-map", "m.json", "--engine-dir", "E",
                               "--project", "Proj", "--named-sandbox"]

    def test_the_client_builds_sandbox_argv_instead_of_project_argv(self):
        client = ParseWorkerClient("Proj", stub=True, parse_delay=0.1,
                                   sandbox=SandboxSpawn(config="c.xml", project="Proj"))
        assert client.spawn_args() == ["--sandbox", "--config", "c.xml", "--project", "Proj",
                                       "--stub", "--parse-delay", "0.1"]
        assert ParseWorkerClient("Proj").spawn_args() == ["--project", "Proj"]

    def test_sandbox_without_config_and_project_mode_without_project_are_usage_errors(self):
        with pytest.raises(SystemExit):
            wm.main(["--sandbox"])
        with pytest.raises(SystemExit):
            wm.main([])

    async def test_a_stub_sandbox_child_parses_and_refuses(self, tmp_path):
        config = _write_script(tmp_path, {"words": {"bad": {"invalid_segment": 1}}})
        client = ParseWorkerClient(
            "Proj", stub=True,
            sandbox=SandboxSpawn(config=config, id_map=_write_map(tmp_path), project="Proj"))
        await client.start()
        try:
            ok = await client.parse_word(request_id="r0", run_id="x", wordform="kata",
                                         level="batch", index_in_run=0)
            assert ok["parse"]["outcome"] == "not_parsed"  # stub ids 1/2 are not in IDS
            bad = await client.parse_word(request_id="r1", run_id="x", wordform="bad",
                                          level="batch", index_in_run=1)
            assert bad["parse"]["outcome"] == "invalid_segment"
            with pytest.raises(WorkerError):
                await client.check_engine(request_id="e", timeout=30)
            assert not any(n.startswith("SIL.LCModel") for n in await client.loaded_assemblies())
        finally:
            await client.aclose()


# ---------------------------------------------------------------------------
# 5. Isolation (T108; FR-043, FR-046; contracts/sandbox-worker.md section 8)
# ---------------------------------------------------------------------------

#: Runs the real `main()` in a child, then reports every LCM-side module the
#: process ever imported. Stdin carries the protocol lines, as in production.
_ISOLATION_PROBE = r"""
import json, sys
from flextoolsmcp.server.parse import worker_main as wm
rc = wm.main(sys.argv[1:])
banned = sorted(m for m in sys.modules
                if m.split('.')[0] in ('flexicon', 'flexlibs') or m.startswith('SIL.LCModel'))
sys.stderr.write('ISOLATION:' + json.dumps(banned) + '\n')
sys.exit(rc)
"""


def _tree(root: Path) -> dict:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


class TestIsolation:
    def test_a_sandbox_worker_imports_no_lcm_and_writes_no_file(self, tmp_path):
        """A full run -- parses, an invalid segment, an engine error and a
        loader error -- in a scratch working directory: no flexicon or LCM
        module is imported, and neither the cwd nor the inputs change."""
        import subprocess

        inputs = tmp_path / "in"
        inputs.mkdir()
        config = _write_script(inputs, {
            "load_errors": [{"type": "X", "id": "e1", "message": "m"}],
            "words": {"bad": {"invalid_segment": 0}, "boom": {"error": "threw"}},
        })
        id_map = _write_map(inputs)
        cwd = tmp_path / "cwd"
        cwd.mkdir()
        before_inputs = _tree(inputs)
        lines = [_parse_msg(w, i) for i, w in enumerate(["kata", "bad", "boom", "lagi"])]
        lines.append({"type": "shutdown"})
        stdin = "".join(json.dumps(m) + "\n" for m in lines).encode("ascii")

        proc = subprocess.run(
            [sys.executable, "-c", _ISOLATION_PROBE, "--sandbox", "--stub",
             "--config", config, "--id-map", id_map, "--project", "Proj"],
            input=stdin, capture_output=True, cwd=str(cwd), timeout=60,
        )
        assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
        out = [json.loads(line) for line in proc.stdout.decode("ascii").splitlines() if line]
        outcomes = [m["parse"]["outcome"] for m in _by_type(out, "result")]
        assert outcomes == ["not_parsed", "invalid_segment", "error", "not_parsed"]
        report = [line for line in proc.stderr.decode("utf-8", "replace").splitlines()
                  if line.startswith("ISOLATION:")]
        assert report and json.loads(report[-1][len("ISOLATION:"):]) == []
        assert list(cwd.iterdir()) == [], "the sandbox worker wrote into its cwd"
        assert _tree(inputs) == before_inputs, "the sandbox worker changed its inputs"

    def test_the_sandbox_code_path_names_no_project_api(self):
        """Static half: nothing on `--sandbox`'s path imports flexicon or
        constructs a project (mirrors test_cp1_boundary.py's AST scan)."""
        import ast

        forbidden_names = {"FLExProject", "OpenProject", "LcmCache"}
        source = Path(wm.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
        scanned = [classes["_SandboxBackend"], classes["_StubSandboxBackend"],
                   ast.parse(Path(hc_engine.__file__).read_text(encoding="utf-8"))]
        for node in scanned:
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in sub.names] + [getattr(sub, "module", None) or ""]
                    assert not any(n.split(".")[0] in ("flexicon", "flexlibs") for n in names), (
                        ast.dump(sub))
                    assert not any(n.startswith("SIL.LCModel") for n in names), ast.dump(sub)
                if isinstance(sub, ast.Name):
                    assert sub.id not in forbidden_names, sub.id
                if isinstance(sub, ast.Attribute):
                    assert sub.attr not in forbidden_names, sub.attr
