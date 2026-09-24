#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The CP4 quickstart scenarios, live, on disposable copies (parser-check CP4,
T082-T084; specs/parser-check-cp4/quickstart.md).

Every scenario makes its own fresh `CP4-Scratch-` copy, drives the REAL
handler / runner / worker processes, writes its evidence to
`specs/parser-check-cp4/evidence/`, and deletes the copy and its backups.
Scenario data is seeded or broken through `lcm_writer.run_lcm` in a separate
process, always with the MCP's read worker released first (L-0: a non-shared
project has one opener at a time).

    python tests/live_support/cp4_scenarios.py s1 s23 s4 s5 s6 s7 s8 [--keep]
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve()
REPO = _HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(_HERE.parent))

from lcm_writer import run_lcm  # noqa: E402
from make_disposable import delete_disposable, make_disposable, require_disposable  # noqa: E402

EVIDENCE = REPO / "specs" / "parser-check-cp4" / "evidence"
HC_SOURCE = "IndonesianHC-Complete"
SCALE_SOURCE = "Malay Parsing-20230810withHC"
KEEP = False


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text(response) -> dict:
    return json.loads(response[0].text)


def _write_evidence(name: str, payload: dict) -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    payload = dict(payload, recorded_at=datetime.now(timezone.utc).isoformat())
    (EVIDENCE / f"{name}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[scenario] evidence -> {name}.json", flush=True)


class Live:
    """A scratch copy, a real runner, a write-enabled session. Torn down after."""

    def __init__(self, source: str = HC_SOURCE, *, write_enabled: bool = True):
        self.source = source
        self.write_enabled = write_enabled

    async def __aenter__(self):
        from flextoolsmcp.server import project_discovery
        from flextoolsmcp.server.filing import claims
        from flextoolsmcp.server.handlers import parse as parse_handler
        from flextoolsmcp.server.parse.runner import ParseRunner

        self.ph = parse_handler
        self.copy = make_disposable(self.source)
        self.name = require_disposable(self.copy.name)
        self.fwdata = self.copy.fwdata
        for key in list(project_discovery._cache):       # the copy is new
            project_discovery._cache[key] = 0.0 if key == "expires_at" else None
        claims.clear()
        session = parse_handler.session_state
        session.write_enabled = self.write_enabled
        session.filing_plans = {}
        session.filing_backed_up_projects = set()
        self.record_dir = Path(tempfile.mkdtemp(prefix="cp4-scen-runs-"))
        self.runner = ParseRunner(record_dir=self.record_dir)
        parse_handler.set_runner(self.runner)
        return self

    async def __aexit__(self, *exc):
        with contextlib.suppress(Exception):
            self.ph.set_runner(None)
            await self.runner.aclose()
        if not KEEP:
            delete_disposable(self.name)
            shutil.rmtree(Path.home() / ".flextoolsmcp" / "backups" / self.name, ignore_errors=True)
        shutil.rmtree(self.record_dir, ignore_errors=True)
        return False

    # -- helpers ------------------------------------------------------------

    def scope(self, words) -> dict:
        return {"project_name": self.name, "scope_kind": "words", "scope_value": list(words)}

    async def parse_text(self, **args) -> dict:
        return _text(await self.ph.handle_flextools_parse_text(dict(args)))

    async def try_word(self, word: str) -> dict:
        return _text(await self.ph.handle_flextools_try_word(
            {"project_name": self.name, "word": word, "level": "plain"}))

    async def baseline(self, words) -> str:
        started = await self.parse_text(**self.scope(words))
        await asyncio.wait_for(self.runner.get(started["run_id"]).done.wait(), timeout=1800)
        return started["run_id"]

    async def wait(self, run_id: str, timeout: float = 1800) -> None:
        await asyncio.wait_for(self.runner.get(run_id).done.wait(), timeout=timeout)

    async def log(self, run_id: str, section: str = "summary", **extra) -> dict:
        return _text(await self.ph.handle_flextools_parse_log(
            {"run_id": run_id, "section": section, **extra}))

    async def filing_summary(self, run_id: str) -> dict:
        return ((await self.log(run_id)).get("content") or {}).get("filing") or {}

    async def release_reader(self) -> None:
        from flextoolsmcp.server.parse.worker_client import SHARED_ROLE

        await self.runner.release_worker(self.name, role=SHARED_ROLE)

    async def lcm(self, snippet: str, *, write: bool = False) -> dict:
        await self.release_reader()
        return run_lcm(self.name, snippet, write=write)

    async def words(self, n: int) -> list:
        resolved = await self.runner.resolve_scope(self.name, {"kind": "all_texts", "limit": n})
        return list(resolved["words"])


# ===========================================================================
# S1 -- the preview writes nothing (SC-001, SC-003)
# ===========================================================================


async def s1() -> None:
    out: dict = {"scenario": "S1: the preview writes nothing (US1; SC-001, SC-003)"}
    async with Live(write_enabled=False) as live:
        words = await live.words(2)
        before = _sha(live.fwdata)
        runs_before = len(live.runner.known_run_ids())
        refused = await live.parse_text(**live.scope(words), apply=True)
        out["write_disabled"] = {k: refused.get(k) for k in (
            "status", "error_code", "server_state", "message")}
        out["runs_started_by_refused_call"] = len(live.runner.known_run_ids()) - runs_before

        live.ph.session_state.write_enabled = True
        preview = await live.parse_text(**live.scope(words), apply=True)
        out["preview"] = {k: preview.get(k) for k in ("status", "error_code", "message", "plan_id")}
        out["preview_upper_bound"] = ((preview.get("plan") or {}).get("deletion_projection") or {}).get("upper_bound")
        out["runs_started_by_preview"] = len(live.runner.known_run_ids()) - runs_before

        # SC-003: a scope word the project has never parsed (no wordform).
        novel = "zzqqxcp4neverparsed"
        preview0 = await live.parse_text(**live.scope([novel]), apply=True)
        plan0 = preview0.get("plan") or {}
        out["never_parsed_word"] = {"word": novel, "status": preview0.get("status"),
                                   "error_code": preview0.get("error_code"),
                                   "upper_bound": (plan0.get("deletion_projection") or {}).get("upper_bound"),
                                   "message": preview0.get("message")}
        after = _sha(live.fwdata)
        out["fwdata_sha256_before"], out["fwdata_sha256_after"] = before, after
        out["verdicts"] = {
            "write_disabled_refused": refused.get("error_code") == "server_state_error",
            "no_run_started_by_refusal_or_preview": out["runs_started_by_preview"] == 0,
            "preview_is_confirmation_required": preview.get("error_code") == "confirmation_required",
            "fwdata_byte_identical": before == after,
            "sc003_never_parsed_bound_is_zero": out["never_parsed_word"]["upper_bound"] == 0,
        }
    _write_evidence("s1-preview-writes-nothing", out)


# ===========================================================================
# S2 + S3 -- the conjunction is an upper bound; a disapproval is overwritten
# ===========================================================================

_SEED = r'''
from SIL.LCModel import (IWfiWordformRepository, IWfiAnalysisFactory, IWfiGlossFactory,
    IWfiMorphBundleFactory, ICmAgentRepository, CmAgentTags, IStTxtPara, Opinions)
from SIL.LCModel.Core.Text import TsStringUtils
WORDS = __WORDS__
vern = cache.DefaultVernWs
anal = cache.DefaultAnalWs
hc = service(ICmAgentRepository).GetObject(CmAgentTags.kguidAgentHermitCrabParser)
user = lp.DefaultUserAgent
by_form = {}
for wf in service(IWfiWordformRepository).AllInstances():
    t = wf.Form.VernacularDefaultWritingSystem.Text
    if t:
        by_form[str(t)] = wf
occ = {}
for text in list(lp.InterlinearTexts):
    for para in list(text.ParagraphsOS):
        try:
            p = IStTxtPara(para)
        except Exception:
            continue
        for seg in list(p.SegmentsOS):
            for i, a in enumerate(list(seg.AnalysesRS)):
                if a.ClassName == "WfiWordform":
                    occ.setdefault(a.Guid, (seg, i))
afac = service(IWfiAnalysisFactory); gfac = service(IWfiGlossFactory); mfac = service(IWfiMorphBundleFactory)
def new_analysis(wf, tag):
    a = afac.Create(); wf.AnalysesOC.Add(a)
    mb = mfac.Create(); a.MorphBundlesOS.Add(mb)
    mb.Form.set_String(vern, TsStringUtils.MakeString(tag, vern))
    return a
seeded = {"parser_unused": [], "in_text_direct": [], "in_text_gloss": [], "human_unused": [],
          "in_text_disapproved": [], "pre_existing": {}}
for n, w in enumerate(WORDS):
    wf = by_form[w]
    seeded["pre_existing"][w] = [str(x.Guid).lower() for x in wf.AnalysesOC]
    seg, i = occ[wf.Guid]
    if n < 4:
        made = [new_analysis(wf, f"seed{n}{k}") for k in range(3)]
        for a in made:
            hc.SetEvaluation(a, Opinions.approves)       # parser-evaluated, user noopinion
        used = made[0]
        if n < 2:
            seg.AnalysesRS[i] = used
            seeded["in_text_direct"].append(str(used.Guid).lower())
        else:
            g = gfac.Create(); used.MeaningsOC.Add(g)
            g.Form.set_String(anal, TsStringUtils.MakeString(f"seedgloss{n}", anal))
            seg.AnalysesRS[i] = g
            seeded["in_text_gloss"].append(str(used.Guid).lower())
        seeded["parser_unused"] += [str(a.Guid).lower() for a in made[1:]]
        if n == 0:
            h = new_analysis(wf, "seedhuman")                # human-made, never evaluated, unused
            seeded["human_unused"].append(str(h.Guid).lower())
    else:
        d = new_analysis(wf, "seeddisapproved")
        hc.SetEvaluation(d, Opinions.approves)
        user.SetEvaluation(d, Opinions.disapproves)
        seg.AnalysesRS[i] = d
        seeded["in_text_disapproved"].append(str(d.Guid).lower())
out["seeded"] = seeded
'''

_STATE = r'''
from SIL.LCModel import IWfiAnalysisRepository, ICmObjectRepository
GUIDS = __GUIDS__
user = lp.DefaultUserAgent
repo = service(ICmObjectRepository)
state = {}
for g in GUIDS:
    try:
        obj = repo.GetObject(System.Guid(g))
    except Exception:
        state[g] = {"exists": False}
        continue
    from SIL.LCModel import IWfiAnalysis
    a = IWfiAnalysis(obj)
    state[g] = {"exists": True, "user_opinion": str(a.GetAgentOpinion(user)).rsplit(".", 1)[-1].lower()}
out["state"] = state
'''


async def s23() -> None:
    out: dict = {"scenario": "S2+S3: the projection is the conjunction and an upper bound; a human "
                             "disapproval in use is overwritten (US1, US5; SC-002, SC-011; D-2)"}
    async with Live() as live:
        candidates = ["membuɑt", "membɑt͡ʃɑ", "mendɑlɑm", "mendeŋɑɾ", "menzɑɾɑh"]
        seeded = await live.lcm(_SEED.replace("__WORDS__", json.dumps(candidates, ensure_ascii=False)),
                                write=True)
        out["seed_result"] = seeded
        if "error" in seeded:
            _write_evidence("s2-projection-vs-actual", out)
            return
        s = seeded["seeded"]
        in_text = s["in_text_direct"] + s["in_text_gloss"]
        await live.baseline(candidates)
        preview = await live.parse_text(**live.scope(candidates), apply=True)
        plan = preview.get("plan") or {}
        deletion = plan.get("deletion_projection") or {}
        projected = sorted({g for gs in (deletion.get("by_wordform") or {}).values() for g in gs})
        overwrites = plan.get("disapproval_overwrites") or {}
        out["plan"] = {"upper_bound": deletion.get("upper_bound"), "by_wordform": deletion.get("by_wordform"),
                       "disapproval_overwrites": overwrites,
                       "in_use_approvals_projected": plan.get("in_use_approvals_projected")}
        seeded_deletable = s["parser_unused"] + s["human_unused"]
        started = await live.parse_text(**live.scope(candidates), apply=True, confirmed=True,
                                        plan_id=preview.get("plan_id"))
        out["confirmed"] = {k: started.get(k) for k in ("status", "error_code", "message", "run_id")}
        if not started.get("run_id"):
            out["confirmed_full"] = started
            _write_evidence("s2-projection-vs-actual", out)
            return
        await live.wait(started["run_id"])
        filing = await live.filing_summary(started["run_id"])
        deletions = await live.log(started["run_id"], "deletions", limit=200)
        items = deletions.get("items") or []
        captured = sorted(i["analysis_guid"] for i in items if i.get("kind") == "pre_deletion"
                          and "confirmed_after" not in i)
        deleted_confirmed = sorted(i["analysis_guid"] for i in items
                                   if i.get("confirmed_after") == "deleted")
        out["filing"] = {k: filing.get(k) for k in ("state", "persisted", "counts", "actual_deletions",
                                                    "projected_deletions", "in_use_approvals_recorded",
                                                    "in_use_approvals_note", "disapprovals_overwritten",
                                                    "filed_words", "error")}
        all_guids = seeded_deletable + in_text + s["in_text_disapproved"] + \
            [g for gs in s["pre_existing"].values() for g in gs]
        after = await live.lcm(_STATE.replace("__GUIDS__", json.dumps(all_guids)))
        state = after.get("state") or {}
        gone = sorted(g for g, v in state.items() if not v.get("exists"))
        out["after"] = state
        out["actually_deleted"] = gone
        out["pre_deletion_captures"] = captured
        out["verdicts"] = {
            "no_in_text_analysis_projected": not (set(in_text) & set(projected)),
            "every_seeded_deletable_projected": set(seeded_deletable) <= set(projected),
            "human_made_unevaluated_counted_R01": set(s["human_unused"]) <= set(projected),
            "actual_subset_of_projection_SC002": set(gone) <= set(projected),
            "every_deleted_has_a_pre_deletion_capture": set(gone) <= set(captured),
            "confirmed_after_lines_match": set(deleted_confirmed) == set(gone) if deleted_confirmed else None,
            "in_text_survive": all(state.get(g, {}).get("exists") for g in in_text),
            "in_text_now_user_approved_FR036": all(state.get(g, {}).get("user_opinion") == "approves"
                                                   for g in in_text),
            "s3_overwrite_projected": s["in_text_disapproved"][0] in
            sum((overwrites.get("by_wordform") or {}).values(), []),
            "s3_overwrite_not_in_deletion": s["in_text_disapproved"][0] not in projected,
            "s3_overwrite_listed_with_prior": any(
                d.get("analysis_guid") == s["in_text_disapproved"][0]
                and d.get("prior_user_opinion") == "disapproves"
                for d in (filing.get("disapprovals_overwritten") or [])),
            "s3_disapproval_now_approval": state.get(s["in_text_disapproved"][0], {}).get("user_opinion") == "approves",
        }
        out["seeded"] = s
    _write_evidence("s2-projection-vs-actual", out)
    _write_evidence("s2-auto-approval-survival", {
        "scenario": "FR-036 auto-approval survival (from S2)",
        "in_text": out.get("seeded", {}).get("in_text_direct", []) + out.get("seeded", {}).get("in_text_gloss", []),
        "after": {g: out.get("after", {}).get(g) for g in
                  out.get("seeded", {}).get("in_text_direct", []) + out.get("seeded", {}).get("in_text_gloss", [])},
        "verdict": (out.get("verdicts") or {}).get("in_text_now_user_approved_FR036"),
    })


# ===========================================================================
# S4 -- the gate refuses (US3; SC-005)
# ===========================================================================

_BREAK_SHAPE = r'''
from SIL.LCModel import ILexEntryRepository, IMoStemAllomorph
from SIL.LCModel.Core.Text import TsStringUtils
vern = cache.DefaultVernWs
target = None
for e in service(ILexEntryRepository).AllInstances():
    lf = e.LexemeFormOA
    if lf is not None and lf.ClassName == "MoStemAllomorph" and e.SensesOS.Count > 0:
        t = lf.Form.VernacularDefaultWritingSystem.Text
        if t and len(str(t)) > 2:
            target = e
            break
lf = target.LexemeFormOA
original = str(lf.Form.VernacularDefaultWritingSystem.Text)
lf.Form.set_String(vern, TsStringUtils.MakeString(original + "9", vern))   # "9": no such phoneme
out.update(entry_guid=str(target.Guid).lower(), original=original, broken=original + "9")
'''

_SET_FORM = r'''
from SIL.LCModel import ICmObjectRepository, ILexEntry
from SIL.LCModel.Core.Text import TsStringUtils
vern = cache.DefaultVernWs
e = ILexEntry(service(ICmObjectRepository).GetObject(System.Guid("__GUID__")))
e.LexemeFormOA.Form.set_String(vern, TsStringUtils.MakeString(__TEXT__, vern))
out["set_to"] = __TEXT__
'''

_EMPTY_ONLY_FORM = r'''
from SIL.LCModel import ILexEntryRepository
from SIL.LCModel.Core.Text import TsStringUtils
vern = cache.DefaultVernWs
target = None
for e in service(ILexEntryRepository).AllInstances():
    lf = e.LexemeFormOA
    if (lf is not None and lf.ClassName == "MoStemAllomorph" and e.AlternateFormsOS.Count == 0
            and e.SensesOS.Count > 0):
        t = lf.Form.VernacularDefaultWritingSystem.Text
        if t and len(str(t)) > 2:
            target = e
            break
original = str(target.LexemeFormOA.Form.VernacularDefaultWritingSystem.Text)
target.LexemeFormOA.Form.set_String(vern, TsStringUtils.EmptyString(vern))
out.update(entry_guid=str(target.Guid).lower(), original=original,
           headword=str(target.HeadWord.Text) if target.HeadWord else None)
'''


_READ_FORM = r'''
from SIL.LCModel import ICmObjectRepository, ILexEntry
e = ILexEntry(service(ICmObjectRepository).GetObject(System.Guid("__GUID__")))
out["form"] = str(e.LexemeFormOA.Form.VernacularDefaultWritingSystem.Text)
'''


def _refusal(resp: dict) -> dict:
    keep = ("status", "error_code", "signal", "message", "baseline_source", "new_errors",
            "dropped_entries", "baseline_eligible_count", "eligible_count", "run_id")
    return {k: resp.get(k) for k in keep if k in resp}


async def s4() -> None:
    out: dict = {"scenario": "S4: the gate refuses (US3; SC-005)"}
    async with Live() as live:
        words = await live.words(3)
        out["words"] = words
        base1 = await live.baseline(words)
        out["baseline_1"] = base1

        # (a) a new, logged load error
        broke = await live.lcm(_BREAK_SHAPE, write=True)
        out["a_break"] = broke
        a = await live.parse_text(**live.scope(words), apply=True)
        out["a_preview"] = _refusal(a)
        await live.lcm(_SET_FORM.replace("__GUID__", broke["entry_guid"])
                       .replace("__TEXT__", json.dumps(broke["original"], ensure_ascii=False)), write=True)

        # (b) the silent drop: an entry's only lexeme form emptied
        base2 = await live.baseline(words)
        out["baseline_2"] = base2
        emptied = await live.lcm(_EMPTY_ONLY_FORM, write=True)
        out["b_break"] = emptied
        b = await live.parse_text(**live.scope(words), apply=True)
        out["b_preview"] = _refusal(b)
        await live.lcm(_SET_FORM.replace("__GUID__", emptied["entry_guid"])
                       .replace("__TEXT__", json.dumps(emptied["original"], ensure_ascii=False)), write=True)

        # (c) preview clean, break, then confirm
        base3 = await live.baseline(words)
        clean = await live.parse_text(**live.scope(words), apply=True)
        out["c_clean_preview"] = _refusal(clean)
        broke_c = await live.lcm(_BREAK_SHAPE, write=True)
        before_c = _sha(live.fwdata)
        c = await live.parse_text(**live.scope(words), apply=True, confirmed=True,
                                  plan_id=clean.get("plan_id"))
        out["c_confirm"] = _refusal(c)
        out["c_fwdata_unchanged"] = before_c == _sha(live.fwdata)
        out["baseline_3"] = base3
        out["c_break"] = broke_c
        out["verdicts"] = {
            "a_new_load_errors_refused": a.get("error_code") == "grammar_load_unclean"
            and a.get("signal") == "new_load_errors",
            "a_baseline_is_prior_run": a.get("baseline_source") == f"prior_run:{base1}",
            "b_eligible_forms_dropped_refused": b.get("error_code") == "grammar_load_unclean"
            and b.get("signal") == "eligible_forms_dropped",
            "b_names_the_dropped_entry": any(d.get("entry_guid") == emptied.get("entry_guid")
                                             for d in (b.get("dropped_entries") or [])),
            "c_clean_preview_offered": clean.get("error_code") == "confirmation_required",
            "c_confirmed_call_refused": c.get("error_code") == "grammar_load_unclean",
            "c_nothing_written": out["c_fwdata_unchanged"],
        }
    _write_evidence("s4-refuse-to-file", out)


# ===========================================================================
# S5 -- backup outcomes (US2; SC-004, SC-008)
# ===========================================================================


@contextlib.contextmanager
def _isolated_config():
    """Redirect BOTH importable config modules to a temp file (never ~/.flextoolsmcp)."""
    sys.path.insert(0, str(REPO / "src" / "flextoolsmcp"))
    import config as bare_config
    from flextoolsmcp import config as pkg_config

    real = Path.home() / ".flextoolsmcp" / "config.json"
    real_before = real.read_bytes() if real.is_file() else None
    tmp = Path(tempfile.mkdtemp(prefix="cp4-cfg-"))
    saved = []
    for module in {id(pkg_config): pkg_config, id(bare_config): bare_config}.values():
        saved.append((module, module.CONFIG_DIR, module.CONFIG_FILE, module._config_cache))
        module.CONFIG_DIR, module.CONFIG_FILE, module._config_cache = tmp, tmp / "config.json", None

    def set_key(key, value):
        pkg_config.config_set(key, value)
        for module, *_ in saved:
            module._config_cache = None

    try:
        yield set_key
    finally:
        for module, d, f, c in saved:
            module.CONFIG_DIR, module.CONFIG_FILE, module._config_cache = d, f, c
        shutil.rmtree(tmp, ignore_errors=True)
        real_after = real.read_bytes() if real.is_file() else None
        assert real_before == real_after, "the real ~/.flextoolsmcp/config.json changed"


async def _file_and_read(live, words) -> dict:
    preview = await live.parse_text(**live.scope(words), apply=True)
    plan = preview.get("plan") or {}
    started = await live.parse_text(**live.scope(words), apply=True, confirmed=True,
                                    plan_id=preview.get("plan_id"))
    res = {"plan_backup": plan.get("backup"), "confirmation_setting": plan.get("confirmation_setting"),
           "preview_error_code": preview.get("error_code"),
           "confirmed": {k: started.get(k) for k in ("status", "error_code", "run_id", "backup",
                                                     "no_recovery_warning")}}
    if started.get("run_id"):
        await live.wait(started["run_id"])
        filing = await live.filing_summary(started["run_id"])
        res["record_backup"] = filing.get("backup")
        res["record_no_recovery_warning"] = filing.get("no_recovery_warning")
        meta = json.loads((live.record_dir / started["run_id"] / "meta.json").read_text("utf-8"))
        res["meta_no_recovery_warning"] = (meta.get("filing") or {}).get("no_recovery_warning")
    return res


async def s5() -> None:
    from flextoolsmcp.server import project_discovery

    out: dict = {"scenario": "S5: backup outcomes (US2; SC-004, SC-008)"}
    with _isolated_config() as set_key:
        async with Live() as live:
            words = await live.words(2)
            await live.baseline(words)
            projects_root = Path(project_discovery.get_projects_directory()[0])

            default = await _file_and_read(live, words)
            out["default"] = default
            path = (default["confirmed"].get("backup") or {}).get("path")
            out["default_backup_path"] = path

            set_key("backup_before_write", False)
            off = await _file_and_read(live, words)
            out["backup_disabled"] = off

            set_key("backup_before_write", True)
            set_key("require_write_confirmation", False)
            preview = await live.parse_text(**live.scope(words), apply=True)
            out["require_confirmation_false"] = {
                "error_code": preview.get("error_code"),
                "confirmation_setting": (preview.get("plan") or {}).get("confirmation_setting")}
    backups_root = (Path.home() / ".flextoolsmcp" / "backups").resolve()
    out["verdicts"] = {
        "default_plan_will_be_taken": (default.get("plan_backup") or {}).get("outcome") == "will_be_taken",
        "default_backup_under_backups_dir": bool(path) and backups_root in Path(path).resolve().parents,
        "default_backup_not_under_projects": bool(path) and projects_root.resolve() not in Path(path).resolve().parents,
        "disabled_plan_says_so": (off.get("plan_backup") or {}).get("outcome") == "disabled_by_configuration",
        "disabled_result_warns": bool(off["confirmed"].get("no_recovery_warning")),
        "disabled_record_warns": bool(off.get("meta_no_recovery_warning")),
        "require_confirmation_false_still_requires_it_SC008":
            out["require_confirmation_false"]["error_code"] == "confirmation_required",
        "setting_disclosed": bool(out["require_confirmation_false"]["confirmation_setting"]),
    }
    _write_evidence("s5-backup-outcomes", out)


# ===========================================================================
# S4d + S6 -- mid-run refusal (shared copy) and concurrency (SC-005, SC-006, SC-007)
# ===========================================================================


async def _start_filing(live, words) -> dict:
    preview = await live.parse_text(**live.scope(words), apply=True)
    if preview.get("error_code") != "confirmation_required":
        return {"preview": preview}
    return await live.parse_text(**live.scope(words), apply=True, confirmed=True,
                                 plan_id=preview.get("plan_id"))


async def _until_words(live, run_id: str, n: int, timeout: float = 600) -> int:
    handle = live.runner.get(run_id)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not handle.is_terminal and handle.words_completed < n:
        await asyncio.sleep(0.05)
    return handle.words_completed


async def s4d() -> None:
    """Shared copy: try_word answers DURING filing (FR-027 where it can hold),
    then a grammar break mid-run ends the run `refused_midrun`."""
    from shared_mode import make_shared

    out: dict = {"scenario": "S4d + SC-007 (shared): a read during filing, then a mid-run break"}
    async with Live(SCALE_SOURCE) as live:
        make_shared(live.name)
        words = await live.words(120)
        out["words_in_scope"] = len(words)
        await live.baseline(words)
        started = await _start_filing(live, words)
        run_id = started.get("run_id")
        out["started"] = {k: started.get(k) for k in ("status", "error_code", "run_id", "message")}
        if not run_id:
            out["started_full"] = started
            _write_evidence("s4d-midrun-and-shared-read", out)
            return
        await _until_words(live, run_id, 2)
        t0 = time.monotonic()
        tried = await live.try_word(words[0])
        out["try_word_during_filing"] = {"status": tried.get("status"), "error_code": tried.get("error_code"),
                                         "seconds": round(time.monotonic() - t0, 2),
                                         "run_still_going": not live.runner.get(run_id).is_terminal}
        # Break the grammar from ANOTHER process while the run goes (shared: allowed).
        broke = run_lcm(live.name, _BREAK_SHAPE, write=True)
        out["break"] = broke
        out["words_when_broken"] = live.runner.get(run_id).words_completed
        await live.wait(run_id)
        filing = await live.filing_summary(run_id)
        out["filing"] = {k: filing.get(k) for k in ("state", "persisted", "counts", "filed_words",
                                                    "error", "refusal")}
        out["filed_count"] = len(filing.get("filed_words") or [])
        # Did the filing worker's save (commit + close) overwrite the edit
        # another process made during the run? (#147's hazard, shared mode.)
        after = await live.lcm(_READ_FORM.replace("__GUID__", broke.get("entry_guid", "")))
        out["foreign_edit_after_run"] = after
        out["verdicts"] = {
            "foreign_edit_survived_filing_save": after.get("form") == broke.get("broken"),
            "sc007_try_word_answered_during_run": tried.get("status") == "ok"
            and out["try_word_during_filing"]["run_still_going"],
            "s4d_refused_midrun": filing.get("state") == "refused_midrun",
            "s4d_filed_so_far_reported": out["filed_count"] > 0 and out["filed_count"] < len(words),
        }
    _write_evidence("s4d-midrun-and-shared-read", out)


_CHILD = r'''
import asyncio, json, sys
sys.path.insert(0, sys.argv[3]); sys.path.insert(0, sys.argv[4])
name, record_dir = sys.argv[1], sys.argv[2]
async def main():
    from pathlib import Path
    from flextoolsmcp.server.handlers import parse as ph
    from flextoolsmcp.server.parse.runner import ParseRunner
    ph.session_state.write_enabled = True
    runner = ParseRunner(record_dir=Path(record_dir))
    ph.set_runner(runner)
    words = list((await runner.resolve_scope(name, {"kind": "all_texts", "limit": 120}))["words"])
    scope = {"project_name": name, "scope_kind": "words", "scope_value": words}
    b = json.loads((await ph.handle_flextools_parse_text(dict(scope)))[0].text)
    await runner.get(b["run_id"]).done.wait()
    p = json.loads((await ph.handle_flextools_parse_text(dict(scope, apply=True)))[0].text)
    s = json.loads((await ph.handle_flextools_parse_text(dict(scope, apply=True, confirmed=True, plan_id=p["plan_id"])))[0].text)
    print("RUNID " + str(s.get("run_id")), flush=True)
    await asyncio.sleep(3600)
asyncio.run(main())
'''


async def s6() -> None:
    import subprocess

    from flextoolsmcp.server.filing import claims
    from flextoolsmcp.server.subprocess_helpers import _kill_process_tree

    out: dict = {"scenario": "S6: concurrency and a crash (US4; SC-006, SC-007 non-shared)"}
    async with Live(SCALE_SOURCE) as live:
        words = await live.words(120)
        await live.baseline(words)
        started = await _start_filing(live, words)
        run_id = started.get("run_id")
        out["started"] = {k: started.get(k) for k in ("status", "error_code", "run_id")}
        t0 = time.monotonic()
        second = await live.parse_text(**live.scope(words), apply=True)
        out["second_request"] = {"seconds": round(time.monotonic() - t0, 3),
                                 **{k: second.get(k) for k in ("error_code", "run_id", "started_at",
                                                               "words_completed", "hint")}}
        tried = await live.try_word(words[0])
        out["try_word_during_filing_non_shared"] = {k: tried.get(k) for k in ("status", "error_code")}
        if run_id:
            await live.wait(run_id)
            out["first_run_state"] = (await live.filing_summary(run_id)).get("state")

        # The crash: a child "server" files; it is killed mid-run.
        await live.release_reader()
        child = subprocess.Popen(
            [sys.executable, "-c", _CHILD, live.name, str(live.record_dir), str(REPO / "src"),
             str(_HERE.parent)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            encoding="utf-8")
        crash_run = None
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            line = child.stdout.readline()
            if line.startswith("RUNID "):
                crash_run = line.split()[1]
                break
        words_at_kill = None
        if crash_run and crash_run != "None":
            meta_path = live.record_dir / crash_run / "meta.json"
            while time.monotonic() < deadline:
                with contextlib.suppress(Exception):
                    words_at_kill = json.loads(meta_path.read_text("utf-8")).get("words_completed") or 0
                    if words_at_kill >= 2:
                        break
                await asyncio.sleep(0.1)
        _kill_process_tree(child.pid)
        child.wait(timeout=30)
        out["crash"] = {"run_id": crash_run, "words_completed_at_kill": words_at_kill}
        claims.clear()      # this process never held the child's claim; a restart starts empty
        swept = claims.sweep_orphaned_filing_runs(record_dir=live.record_dir)
        out["crash"]["swept"] = swept
        if crash_run:
            meta = json.loads((live.record_dir / crash_run / "meta.json").read_text("utf-8"))
            out["crash"]["state_after_sweep"] = (meta.get("filing") or {}).get("state")
        after = await live.parse_text(**live.scope(words), apply=True)
        out["crash"]["new_request_after_restart"] = {k: after.get(k) for k in ("error_code", "message")}
        out["verdicts"] = {
            "sc006_refused_in_progress_under_1s": second.get("error_code") == "parser_filing_in_progress"
            and out["second_request"]["seconds"] < 1.0,
            "sc006_four_fields": all(second.get(k) is not None for k in
                                     ("run_id", "started_at", "words_completed", "hint")),
            "non_shared_read_refused_under_m1": tried.get("error_code") == "parser_filing_in_progress",
            "crash_marked_crashed": out["crash"].get("state_after_sweep") == "crashed",
            "new_request_not_refused_in_progress":
                out["crash"]["new_request_after_restart"].get("error_code") != "parser_filing_in_progress",
        }
    _write_evidence("s6-concurrency", out)


# ===========================================================================
# S7 -- live questions Q1 and Q4 (FR-036, FR-038); S8 -- cancel (US2 AS-7)
# ===========================================================================

_Q1 = r'''
from SIL.LCModel import (IWfiWordform, IWfiAnalysisFactory, IWfiMorphBundleFactory,
    IStTxtPara, ICmAgentRepository, CmAgentTags, Opinions)
from SIL.LCModel.Core.Text import TsStringUtils
vern = cache.DefaultVernWs
hc = service(ICmAgentRepository).GetObject(CmAgentTags.kguidAgentHermitCrabParser)
target = None
for text in list(lp.InterlinearTexts):
    for para in list(text.ParagraphsOS):
        try:
            p = IStTxtPara(para)
        except Exception:
            continue
        for seg in list(p.SegmentsOS):
            for i, a in enumerate(list(seg.AnalysesRS)):
                if a.ClassName == "WfiWordform" and IWfiWordform(a).Form.VernacularDefaultWritingSystem.Text:
                    target = (seg, i, IWfiWordform(a))
                    break
            if target: break
        if target: break
    if target: break
seg, i, wf = target
a = service(IWfiAnalysisFactory).Create(); wf.AnalysesOC.Add(a)
mb = service(IWfiMorphBundleFactory).Create(); a.MorphBundlesOS.Add(mb)
mb.Form.set_String(vern, TsStringUtils.MakeString("q1seed", vern))
hc.SetEvaluation(a, Opinions.approves)
seg.AnalysesRS[i] = a
out["before"] = {"segment": str(seg.Guid).lower(), "index": i, "count": seg.AnalysesRS.Count,
                 "next_ref_guid": str(seg.AnalysesRS[i + 1].Guid).lower() if seg.AnalysesRS.Count > i + 1 else None,
                 "ref_class": seg.AnalysesRS[i].ClassName, "ref_guid": str(seg.AnalysesRS[i].Guid).lower(),
                 "wordform_guid": str(wf.Guid).lower(), "analysis_guid": str(a.Guid).lower()}
a.Delete()                               # the generic Delete() path (ParseFiler.cs:311)
ref = seg.AnalysesRS[i] if seg.AnalysesRS.Count > i else None
out["after_same_uow"] = {"count": seg.AnalysesRS.Count,
                         "ref_class": ref.ClassName if ref is not None else None,
                         "ref_guid": str(ref.Guid).lower() if ref is not None else None}
'''

_Q1_READ = r'''
from SIL.LCModel import ICmObjectRepository, ISegment
seg = ISegment(service(ICmObjectRepository).GetObject(System.Guid("__SEG__")))
i = __IDX__
ref = seg.AnalysesRS[i] if seg.AnalysesRS.Count > i else None
out["after_reopen"] = {"count": seg.AnalysesRS.Count,
                       "ref_class": ref.ClassName if ref is not None else None,
                       "ref_guid": str(ref.Guid).lower() if ref is not None else None}
from SIL.LCModel import IWfiWordform
def form_of(g):
    try:
        wf = IWfiWordform(service(ICmObjectRepository).GetObject(System.Guid(g)))
        return {"guid": g, "forms": {str(ws.Id): str(wf.Form.get_String(ws.Handle).Text)
                                     for ws in lp.CurrentVernacularWritingSystems}}
    except Exception as exc:
        return {"guid": g, "error": f"{type(exc).__name__}: {exc}"}
out["wordforms"] = [form_of(g) for g in __WFS__]
out["baseline_text"] = str(seg.BaselineText.Text)[:120] if seg.BaselineText is not None else None
'''


async def s7() -> None:
    out: dict = {"scenario": "S7: Q1 (MoveConcAnnotationsToWordform) and Q4 (FR-038 checker re-probe)"}
    async with Live() as live:
        q1 = await live.lcm(_Q1, write=True)
        out["q1"] = q1
        if "before" in q1:
            wfs = [q1["before"]["wordform_guid"], q1["after_same_uow"]["ref_guid"]]
            again = await live.lcm(_Q1_READ.replace("__SEG__", q1["before"]["segment"])
                                   .replace("__IDX__", str(q1["before"]["index"]))
                                   .replace("__WFS__", json.dumps(wfs)))
            out["q1"]["after_reopen"] = again.get("after_reopen") or again
            out["q1"]["wordforms"] = again.get("wordforms")
            out["q1"]["segment_baseline_text"] = again.get("baseline_text")
            ref = out["q1"]["after_reopen"]
            out["q1"]["verdict"] = {
                "segment_now_references_the_wordform": ref.get("ref_guid") == q1["before"]["wordform_guid"],
                "slot_removed_from_segment": ref.get("count") == q1["before"]["count"] - 1
                and ref.get("ref_guid") == q1["before"]["next_ref_guid"],
                "count_before": q1["before"]["count"], "count_after": ref.get("count"),
            }
    _write_evidence("q1-moveconc", {"question": "Q1 (FR-036): after the generic Delete() of an "
                                                "in-segment analysis, what does the segment hold?",
                                    **out["q1"]})

    # Q4 -- public grammar-health checkers in the INSTALLED assemblies.
    import re

    import clr  # type: ignore  # noqa: F401 -- loads the CLR before System
    import System  # type: ignore

    from flextoolsmcp.server import parser_probe

    fw_dir = Path(r"C:\Program Files\SIL\FieldWorks 9")
    parser_probe._install_directory_resolver(fw_dir)
    pattern = re.compile(r"(Check|Valid|Verif|Health|Diagnos|Problem|Lint|Audit)", re.I)
    found: dict = {}
    for dll in ("ParserCore.dll", "SIL.Machine.Morphology.HermitCrab.dll", "SIL.Machine.dll"):
        asm = System.Reflection.Assembly.LoadFile(str(fw_dir / dll))
        name = asm.GetName()
        entry = {"version": str(name.Version), "types": []}
        try:
            types = list(asm.GetTypes())
        except System.Reflection.ReflectionTypeLoadException as exc:
            types = [t for t in exc.Types if t is not None]
        for t in types:
            if not t.IsPublic:
                continue
            members = sorted({m.Name for m in t.GetMethods() if m.DeclaringType == t and pattern.search(m.Name)})
            if pattern.search(t.Name) or members:
                entry["types"].append({"type": t.FullName, "matching_members": members})
        found[dll] = entry
    _write_evidence("q4-checker-reprobe", {
        "question": "Q4 (FR-038): do the installed ParserCore / HermitCrab assemblies expose a public "
                    "grammar-health checker the gate could call instead of its own diff?",
        "install": str(fw_dir), "pattern": pattern.pattern, "assemblies": found})


async def s8() -> None:
    out: dict = {"scenario": "S8: cancel (US2 AS-7, FR-034)"}
    async with Live(SCALE_SOURCE) as live:
        words = await live.words(120)
        await live.baseline(words)
        before = _sha(live.fwdata)
        started = await _start_filing(live, words)
        run_id = started.get("run_id")
        out["started"] = {k: started.get(k) for k in ("status", "error_code", "run_id")}
        await _until_words(live, run_id, 3)
        cancel = _text(await live.ph.handle_flextools_parse_cancel({"run_id": run_id}))
        out["cancel_response"] = {k: cancel.get(k) for k in ("status", "error_code", "message", "note",
                                                              "filed_words", "state")}
        await live.wait(run_id)
        filing = await live.filing_summary(run_id)
        out["filing"] = {k: filing.get(k) for k in ("state", "persisted", "filed_words", "counts",
                                                    "cancel_note", "error")}
        after = _sha(live.fwdata)
        from flextoolsmcp.server.filing import wording

        blob = json.dumps(cancel) + json.dumps(filing)
        out["verdicts"] = {
            "state_cancelled": filing.get("state") == "cancelled",
            "filed_words_listed": bool(filing.get("filed_words")),
            "stopped_early": len(filing.get("filed_words") or []) < len(words),
            "filed_words_persisted": filing.get("persisted") is True and before != after,
            "cancel_note_given": wording.CANCEL_NOTE in blob,
        }
    _write_evidence("s8-cancel", out)


SCENARIOS = {"s1": s1, "s23": s23, "s4": s4, "s5": s5, "s4d": s4d, "s6": s6, "s7": s7, "s8": s8}


def main(argv=None) -> int:
    global KEEP
    ap = argparse.ArgumentParser()
    ap.add_argument("scenarios", nargs="+")
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)
    KEEP = args.keep
    rc = 0
    for key in args.scenarios:
        started = time.monotonic()
        try:
            asyncio.run(SCENARIOS[key]())
        except Exception as exc:  # noqa: BLE001 -- recorded, next scenario runs
            import traceback

            rc = 1
            _write_evidence(f"{key}-error", {"error": f"{type(exc).__name__}: {exc}",
                                             "traceback": traceback.format_exc()[-4000:]})
        print(f"[scenario] {key} done in {time.monotonic() - started:.0f}s", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
