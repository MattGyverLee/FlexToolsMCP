"""flexgap - coverage-gap triage for flexicon / flextoolsmcp.

Two independent gap signals, fused into one ranked worklist:

  STATIC   what the shipped indexes say is structurally unreachable.
           Recomputed from index/liblcm/liblcm_api_*.json +
           index/python/flexicon_api_*.json. Answers "what is missing".

  EMPIRICAL what live sessions actually tripped over. Parsed from the log
           surfaces flextoolsmcp writes under ~/.flextoolsmcp/logs/.
           Answers "what is missing AND biting".

A gap that is structural but never hit is a roadmap item. A gap that shows
up in logs is a ticket. Only the join tells you which is which.

Log surfaces consumed (schemas read from flextoolsmcp @ 10e103e):

  patterns.json    PatternTracker. api_patterns{api_call -> success_count,
                   failure_count, last_used, common_errors{type -> {count,
                   example}}} and error_patterns{normalized_msg -> {count,
                   examples[{code, error, timestamp}], api_calls[],
                   first_seen, potential_fix}}.
                   NOTE: this is the only surface that retains CODE.

  operations.jsonl op_telemetry. One line per run_module close:
                   ts, kind, op_id, seq, project, write_enabled, source_kind,
                   user_intent, user_request, session_id, code_sha256,
                   code_bytes, code_lines, outcome, error_code,
                   preflight_gate, casting_signature, duration_s,
                   auto_fixes_applied, auto_discovered[],
                   assistance_triggered, info/warning/error_count.
                   Carries the verbatim user_request but NOT the code.

  operations.log   prose rollup, '%Y-%m-%d %H:%M:%S | LEVEL   | message'
                   with [TOOL CALL] / [BLOCKED] / [TOOL ERROR] markers.
                   Used only for markers the structured surfaces lack.

Usage
-----
    python flexgap.py --index <flextoolsmcp>/src/flextoolsmcp/index \
                      --logs ~/.flextoolsmcp/logs \
                      --out gap_report.md

Either half works alone: omit --logs for a pure structural audit, or point
--logs at a directory a user sent you for triage against the shipped index.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

__all__ = [
    "load_indexes", "build_static_gap_map", "load_patterns", "load_jsonl",
    "extract_lcm_symbols", "triage", "render_report",
]

# --------------------------------------------------------------------------
# LCM symbol recognition
# --------------------------------------------------------------------------

#: Namespace roots that mean "this code reached past flexicon into LibLCM".
#: Taken from flexicon's own api_usage_summary.json namespace list.
LCM_NAMESPACES = (
    "SIL.LCModel", "SIL.FieldWorks", "SIL.WritingSystems", "SIL.Core",
)

_RE_IMPORT = re.compile(
    r"(?:^|\n)\s*from\s+(" + "|".join(re.escape(n) for n in LCM_NAMESPACES) +
    r")[\w.]*\s+import\s+([^\n]+)"
)
_RE_IMPORT_PLAIN = re.compile(
    r"(?:^|\n)\s*import\s+(" + "|".join(re.escape(n) for n in LCM_NAMESPACES) + r")[\w.]*"
)
#: I-prefixed interface names: ILexEntry, IMoStemMsa, ITsString ...
_RE_INTERFACE = re.compile(r"\b(I[A-Z][A-Za-z0-9]{2,})\b")
#: LCM field-suffix properties: SensesOS, ComponentLexemesRS, MsaRA ...
_RE_LCM_PROP = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:OS|OC|RS|RC|OA|RA))\b")
#: Static helper classes: TsStringUtils, LexEntryTags, SegmentServices ...
_RE_STATIC_CLS = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:Tags|Utils|Services|Factory|Repository))\b")

#: Flexicon's own wrapper-call shape, so wrapper calls aren't read as LCM.
_RE_WRAPPER_CALL = re.compile(r"\b(\w+Operations)\s*\(\s*\w+\s*\)\s*\.\s*(\w+)")


def extract_lcm_symbols(code: str) -> Dict[str, List[str]]:
    """Pull LibLCM symbols out of a code snippet.

    Returns {'imports': [...], 'interfaces': [...], 'properties': [...],
             'statics': [...], 'wrapper_calls': ['Class.Method', ...]}.

    The distinction that matters: `imports` is positive evidence that the
    author bypassed flexicon (you cannot `from SIL.LCModel import X` by
    accident), while `interfaces`/`properties` also appear in wrapper code
    and in error text, so they are corroborating, not conclusive.
    """
    code = code or ""
    imports: List[str] = []
    for _ns, names in _RE_IMPORT.findall(code):
        names = names.split("#")[0]
        names = names.strip().strip("()")
        for n in names.split(","):
            n = n.strip().split(" as ")[0].strip()
            if n and n != "*":
                imports.append(n)
    if _RE_IMPORT_PLAIN.search(code):
        imports.append("<module-level SIL import>")
    return {
        "imports": sorted(set(imports)),
        "interfaces": sorted(set(_RE_INTERFACE.findall(code))),
        "properties": sorted(set(_RE_LCM_PROP.findall(code))),
        "statics": sorted(set(_RE_STATIC_CLS.findall(code))),
        "wrapper_calls": sorted({f"{a}.{b}" for a, b in _RE_WRAPPER_CALL.findall(code)}),
    }


# --------------------------------------------------------------------------
# Static half: recompute the structural gap map from the shipped indexes
# --------------------------------------------------------------------------

def _newest(d: Path, pattern: str) -> Optional[Path]:
    hits = sorted(d.glob(pattern))
    return hits[-1] if hits else None


def load_indexes(index_dir: Path) -> Dict[str, Any]:
    """Load the LCM and flexicon indexes, picking the newest version of each."""
    index_dir = Path(index_dir)
    lcm_p = _newest(index_dir / "liblcm", "liblcm_api_v*.json")
    flx_p = _newest(index_dir / "python", "flexicon_api_v*.json")
    brg_p = _newest(index_dir / "python", "flexicon_lcm_bridge_v*.json")
    if lcm_p is None or flx_p is None:
        raise FileNotFoundError(
            f"expected liblcm/liblcm_api_v*.json and python/flexicon_api_v*.json "
            f"under {index_dir}"
        )
    out = {
        "lcm": json.loads(lcm_p.read_text(encoding="utf-8")),
        "flexicon": json.loads(flx_p.read_text(encoding="utf-8")),
        "_paths": {"lcm": str(lcm_p), "flexicon": str(flx_p)},
    }
    if brg_p is not None:
        out["bridge"] = json.loads(brg_p.read_text(encoding="utf-8"))
        out["_paths"]["bridge"] = str(brg_p)
    return out


#: Domains a lexicography wrapper is expected to serve. Gaps outside these
#: are reported but not ranked.
LINGUISTIC_DOMAINS = (
    "lexicon", "grammar", "texts", "wordform", "notebook",
    "discourse", "reversal", "core",
)


def build_static_gap_map(idx: Dict[str, Any]) -> Dict[str, Any]:
    """Compute entity-level reachability of LCM from flexicon.

    `reachable` means the entity appears in flexicon's AST-extracted
    dependency set. That is an ENTITY-level signal: it cannot distinguish
    "fully wrapped" from "referenced once". Member-level coverage is not
    derivable from the shipped indexes (python_wrappers[*].methods is empty
    for every entity, and reverse_mapping's member buckets are unpopulated).

    Gap classification excludes three false-positive classes:
      - base interfaces of a reachable entity (reached via the derived type)
      - the I-counterpart pairing (`MoForm` when `IMoForm` is reachable)
      - `*Internal` entities, which are not public API by convention
    """
    ents = idx["lcm"]["entities"]
    used = set(idx["flexicon"].get("metadata", {}).get("lcm_interfaces_used", []))

    bases_of_reachable = set()
    for n in used:
        ent = ents.get(n)
        if not ent:
            continue
        for b in (ent.get("interfaces") or []) + (ent.get("base_classes") or []):
            bases_of_reachable.add(b)

    rows = []
    for name, ent in ents.items():
        typ = ent.get("type")
        n_meth = len(ent.get("methods") or [])
        n_prop = len(ent.get("properties") or [])
        reachable = name in used
        counterpart = ("I" + name) in used or name.lstrip("I") in used
        internal = "Internal" in name
        rows.append({
            "entity": name,
            "type": typ,
            "domain": ent.get("category"),
            "n_methods": n_meth,
            "n_properties": n_prop,
            "member_surface": n_meth + n_prop,
            "reachable": reachable,
            "is_public": typ in ("interface", "abstract_class"),
            "base_of_reachable": name in bases_of_reachable,
            "i_counterpart_reachable": counterpart,
            "internal_by_convention": internal,
            "in_scope_domain": ent.get("category") in LINGUISTIC_DOMAINS,
        })
    # Measured member coverage, when the index carries it (flextoolsmcp
    # >= the type-aware detection change). This supersedes entity-level
    # reachability: `lcm_interfaces_used` records types flexicon NAMES, not
    # types it operates on, so a type reached via a factory, a traversal or a
    # parameter looked unreachable even when fully wrapped.
    measured = {n: set((e.get("python_wrapper_members") or {}).get("covered") or {})
                for n, e in ents.items() if e.get("python_wrapper_members")}
    for r in rows:
        cov = measured.get(r["entity"], set())
        r["members_measured_covered"] = len(cov)
        r["has_measured_coverage"] = bool(cov)
        r["is_tags_constant_holder"] = r["entity"].endswith("Tags")
    for r in rows:
        # `unreachable` is domain-blind; `true_gap` additionally requires the
        # entity to sit in a domain a lexicography wrapper is expected to
        # serve. Scripture, system, service and the generic `general` bucket
        # are out of scope by design, so counting them as gaps would inflate
        # the backlog with work nobody intends to do.
        r["unreachable"] = (
            r["is_public"] and not r["reachable"]
            and not r["base_of_reachable"]
            and not r["i_counterpart_reachable"]
            and not r["internal_by_convention"]
        )
        # A type with measured member coverage is handled, whatever
        # `lcm_interfaces_used` says. MoAffixForm and IMoInflAffixTemplate both
        # failed this test the old way and are in fact fully/partly wrapped.
        r["true_gap"] = (r["unreachable"] and r["in_scope_domain"]
                         and not r["has_measured_coverage"]
                         and not r["is_tags_constant_holder"]
                         and r["member_surface"] > 0)

    by_entity = {r["entity"]: r for r in rows}
    pub = [r for r in rows if r["is_public"]]
    domains: Dict[str, Dict[str, Any]] = {}
    for r in pub:
        d = domains.setdefault(r["domain"], dict(
            interfaces=0, reachable=0, member_surface=0, surface_reachable=0))
        d["interfaces"] += 1
        d["member_surface"] += r["member_surface"]
        if r["reachable"]:
            d["reachable"] += 1
            d["surface_reachable"] += r["member_surface"]
    for d in domains.values():
        d["pct_member_surface"] = round(
            100.0 * d["surface_reachable"] / d["member_surface"], 1
        ) if d["member_surface"] else None

    # method-level surface of the wrapper itself, for the example-gap check
    fx_methods = [
        dict(cls=cn, method=m["name"], domain=ce.get("category"),
             mutating=bool(m.get("is_mutating")),
             has_example=bool((m.get("example") or "").strip()),
             has_doc=bool((m.get("description") or "").strip()))
        for cn, ce in idx["flexicon"]["entities"].items()
        for m in ce.get("methods", [])
    ]

    return {
        "rows": rows,
        "by_entity": by_entity,
        "domains": domains,
        "reachable_entities": used,
        "flexicon_methods": fx_methods,
        "totals": {
            "lcm_entities": len(ents),
            "public_interfaces": len(pub),
            "public_reachable": sum(r["reachable"] for r in pub),
            "public_surface": sum(r["member_surface"] for r in pub),
            "public_surface_reachable": sum(r["member_surface"] for r in pub if r["reachable"]),
            "true_gaps": sum(r["true_gap"] for r in rows),
            "true_gap_surface": sum(r["member_surface"] for r in rows if r["true_gap"]),
            "measured_coverage_available": bool(measured),
            "types_with_measured_coverage": len(measured),
            "members_measured_covered": sum(len(v) for v in measured.values()),
            "unreachable_any_domain": sum(r["unreachable"] for r in rows),
            "unreachable_out_of_scope": sum(
                r["unreachable"] and not r["in_scope_domain"] for r in rows),
            "flexicon_classes": len(idx["flexicon"]["entities"]),
            "flexicon_methods": len(fx_methods),
            "methods_without_example": sum(not m["has_example"] for m in fx_methods),
            "mutating_without_example": sum(
                not m["has_example"] and m["mutating"] for m in fx_methods),
        },
    }


# --------------------------------------------------------------------------
# Empirical half: load the log surfaces
# --------------------------------------------------------------------------

def load_patterns(path: Path) -> Dict[str, Any]:
    """Load patterns.json (PatternTracker). Tolerates a missing file."""
    path = Path(path)
    if not path.exists():
        return {"api_patterns": {}, "error_patterns": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("api_patterns", {})
    data.setdefault("error_patterns", {})
    return data


def load_jsonl(paths: Iterable[Path]) -> List[Dict[str, Any]]:
    """Load operations.jsonl (+ rotated .1). Bad lines are skipped, not fatal."""
    recs: List[Dict[str, Any]] = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return recs


def discover_logs(log_dir: Path) -> Dict[str, Any]:
    """Find the standard log surfaces under a ~/.flextoolsmcp/logs-shaped dir."""
    log_dir = Path(log_dir)
    jsonl = [log_dir / "operations.jsonl", log_dir / "operations.jsonl.1"]
    return {
        "patterns": log_dir / "patterns.json",
        "jsonl": [p for p in jsonl if p.exists()],
        "operations_log": log_dir / "operations.log",
    }


# --------------------------------------------------------------------------
# The join
# --------------------------------------------------------------------------

#: preflight_gate / error_code values that indicate a workflow problem rather
#: than a coverage problem. Reported separately so they don't pollute the
#: wrapper backlog.
WORKFLOW_CODES = {
    "api_discovery_required", "unprotected_code", "partial_module",
    "server_state_error", "syntax_error", "undefined_variables",
    "missing_imports", "wrong_library_imports", "invalid_api_chain",
}


def _classify(symbol: str, static: Dict[str, Any]) -> str:
    row = static["by_entity"].get(symbol)
    if row is None:
        return "unknown_symbol"
    if row["true_gap"]:
        return "structural_gap"
    if row["reachable"]:
        return "reachable_but_failing"
    if row["base_of_reachable"] or row["i_counterpart_reachable"]:
        return "reachable_via_inheritance"
    return "out_of_scope"


#: What to do about each class, in the order a maintainer would act.
ACTIONS = {
    "casting_index_gap": "add a casting_index entry for this property (gate 5 named it directly)",
    "structural_gap": "add wrapper coverage (no flexicon path exists)",
    "reachable_but_failing": "wrapper exists - check for a bug, a missing example, or a casting hint",
    "unknown_symbol": "symbol absent from the LCM index - refresh the index or fix the extractor",
    "reachable_via_inheritance": "reachable through a base/counterpart type - document the route",
    "out_of_scope": "non-public LCM type - usually no action",
}


def triage(static: Dict[str, Any],
           patterns: Optional[Dict[str, Any]] = None,
           jsonl: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Fuse the static gap map with whatever log evidence is available."""
    patterns = patterns or {"api_patterns": {}, "error_patterns": {}}
    jsonl = jsonl or []

    # ---- 1. failing wrapper calls, from api_patterns -------------------
    # index the wrapper's own documentation state so a failing call can be
    # checked against whether find_examples could ever have helped
    doc_state = {(m["cls"], m["method"]): m for m in static["flexicon_methods"]}
    cls_examples: Dict[str, int] = defaultdict(int)
    cls_methods: Dict[str, int] = defaultdict(int)
    for m in static["flexicon_methods"]:
        cls_methods[m["cls"]] += 1
        cls_examples[m["cls"]] += bool(m["has_example"])

    failing_apis = []
    for api_call, d in patterns.get("api_patterns", {}).items():
        s, f = d.get("success_count", 0), d.get("failure_count", 0)
        total = s + f
        if total and f:
            cls, _, meth = api_call.partition(".")
            m = doc_state.get((cls, meth))
            failing_apis.append({
                "api_call": api_call,
                "uses": total,
                "failures": f,
                "success_rate": round(100.0 * s / total, 1),
                "errors": sorted(d.get("common_errors", {}),
                                 key=lambda k: -d["common_errors"][k].get("count", 0))[:3],
                "last_used": d.get("last_used"),
                # None = not a resolvable flexicon method (project.* or *.Prop shapes)
                "has_example": None if m is None else m["has_example"],
                "class_examples": (f"{cls_examples[cls]}/{cls_methods[cls]}"
                                   if cls in cls_methods else None),
            })
    failing_apis.sort(key=lambda r: (-r["failures"], r["success_rate"]))

    # ---- 2. LCM symbols seen in failing code, from error_patterns ------
    symbol_ev: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"hits": 0, "direct_import": 0, "errors": set(), "snippets": []})
    for err_key, d in patterns.get("error_patterns", {}).items():
        for ex in d.get("examples", []):
            syms = extract_lcm_symbols(ex.get("code", ""))
            direct = set(syms["imports"]) - {"<module-level SIL import>"}
            for s in set(syms["interfaces"]) | direct | set(syms["statics"]):
                rec = symbol_ev[s]
                rec["hits"] += d.get("count", 1)
                if s in direct:
                    rec["direct_import"] += 1
                rec["errors"].add(err_key[:80])
                if len(rec["snippets"]) < 2:
                    rec["snippets"].append((ex.get("code") or "")[:220])

    # ---- 2b. casting signatures, from operations.jsonl ----------------
    # gate 5 computes these from the ACTUAL failing property access, so a
    # recurring signature names a missing casting_index entry precisely -
    # better evidence than anything recoverable from a code snippet.
    casting_hits: Counter = Counter()
    for r in (jsonl or []):
        sig = (r.get("casting_signature") or "").strip()
        if sig:
            casting_hits[sig] += 1

    candidates = []
    for sig, n in casting_hits.items():
        entity, _, member = sig.partition(".")
        row = static["by_entity"].get(entity, {})
        candidates.append({
            "symbol": sig,
            "classification": "casting_index_gap",
            "action": ACTIONS["casting_index_gap"],
            "evidence_hits": n,
            "direct_lcm_import": False,
            "lcm_domain": row.get("domain"),
            "member_surface": row.get("member_surface"),
            "distinct_errors": 1,
            "example_errors": [f"gate 5 casting signature {sig}"],
            "snippets": [],
        })

    for sym, ev in symbol_ev.items():
        cls = _classify(sym, static)
        row = static["by_entity"].get(sym, {})
        candidates.append({
            "symbol": sym,
            "classification": cls,
            "action": ACTIONS[cls],
            "evidence_hits": ev["hits"],
            "direct_lcm_import": ev["direct_import"] > 0,
            "lcm_domain": row.get("domain"),
            "member_surface": row.get("member_surface"),
            "distinct_errors": len(ev["errors"]),
            "example_errors": sorted(ev["errors"])[:2],
            "snippets": ev["snippets"],
        })
    # rank: direct imports first (hard evidence of a bypass), then frequency,
    # then how much LCM surface a wrapper would unlock.
    order = {"structural_gap": 0, "casting_index_gap": 1, "unknown_symbol": 2,
             "reachable_but_failing": 3, "reachable_via_inheritance": 4, "out_of_scope": 5}
    candidates.sort(key=lambda r: (
        order[r["classification"]], not r["direct_lcm_import"],
        -r["evidence_hits"], -(r["member_surface"] or 0)))

    # ---- 3. outcome / gate distribution, from operations.jsonl ---------
    runs = [r for r in jsonl if r.get("kind") == "run_module"]
    outcomes = Counter(r.get("outcome", "") for r in runs)
    gates = Counter(r.get("preflight_gate") for r in runs if r.get("preflight_gate"))
    codes = Counter(r.get("error_code") for r in runs if r.get("error_code"))
    casting = Counter(r.get("casting_signature") for r in runs if r.get("casting_signature"))

    # verbatim user requests on failed ops: what people were trying to do
    failed_requests = [
        {"request": r.get("user_request", "").strip(),
         "error_code": r.get("error_code", ""),
         "gate": r.get("preflight_gate", ""),
         "project": r.get("project", "")}
        for r in runs
        if r.get("outcome") in ("runtime_fail", "preflight_reject", "timeout")
        and (r.get("user_request") or "").strip()
    ]

    # sessions that never reached a green run - the clearest "blocked" signal
    by_session: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in runs:
        by_session[r.get("session_id") or r.get("op_id", "")].append(r)
    stuck = [
        {"session_id": sid, "ops": len(rs),
         "request": next((x.get("user_request", "") for x in rs if x.get("user_request")), ""),
         "codes": sorted({x.get("error_code", "") for x in rs if x.get("error_code")})}
        for sid, rs in by_session.items()
        if rs and not any(x.get("outcome") == "ok" for x in rs)
    ]
    stuck.sort(key=lambda r: -r["ops"])

    workflow_noise = sum(v for k, v in {**gates, **codes}.items() if k in WORKFLOW_CODES)

    return {
        "failing_apis": failing_apis,
        "candidates": candidates,
        "outcomes": dict(outcomes),
        "gates": dict(gates.most_common()),
        "error_codes": dict(codes.most_common()),
        "casting_signatures": dict(casting.most_common(10)),
        "failed_requests": failed_requests,
        "stuck_sessions": stuck,
        "workflow_noise": workflow_noise,
        "n_runs": len(runs),
        "has_log_evidence": bool(runs or patterns.get("error_patterns")),
        "fixes": propose_fixes(static, patterns),
    }


def propose_fixes(static: Dict[str, Any],
                  patterns: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Fill the `potential_fix` slot PatternTracker allocates but never writes.

    `PatternTracker.record_operation` creates every error_patterns entry with
    `"potential_fix": None` and nothing in the server ever sets it, so the
    field is a permanently empty slot in a structure that already holds the
    failing code. This derives a concrete proposal per error pattern from the
    LCM symbols in its code examples, classified against the static gap map.

    Returns {error_key: {"potential_fix": str, "basis": [...], "symbols": [...]}}
    shaped so it can be merged straight back into patterns.json.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for err_key, d in patterns.get("error_patterns", {}).items():
        syms: Counter = Counter()
        direct = set()
        for ex in d.get("examples", []):
            s = extract_lcm_symbols(ex.get("code", ""))
            hard = set(s["imports"]) - {"<module-level SIL import>"}
            direct |= hard
            for name in set(s["interfaces"]) | hard:
                syms[name] += 1
        if not syms:
            continue
        classified = [(n, _classify(n, static)) for n in syms]
        structural = [n for n, c in classified if c == "structural_gap"]
        unknown = [n for n, c in classified if c == "unknown_symbol"]
        reachable = [n for n, c in classified if c == "reachable_but_failing"]

        if structural:
            surf = sum((static["by_entity"].get(n, {}).get("member_surface") or 0)
                       for n in structural)
            fix = (f"No flexicon wrapper reaches {', '.join(sorted(structural)[:3])}"
                   + (" and others" if len(structural) > 3 else "")
                   + f". Add wrapper coverage ({surf} LCM members unlocked), or "
                     f"document api_mode='liblcm' as the supported route for this task.")
            basis = "structural gap in the shipped index"
        elif unknown and direct:
            fix = (f"{', '.join(sorted(unknown)[:3])} is imported from SIL.* but absent "
                   f"from the LCM index. Refresh the index (python src/refresh.py) or "
                   f"check the extractor - a hallucinated symbol and a stale index look "
                   f"identical from here.")
            basis = "symbol not present in the LCM index"
        elif reachable:
            fix = (f"{', '.join(sorted(reachable)[:3])} is reachable from flexicon, so "
                   f"this is a wrapper bug, a missing example, or a casting hint - not a "
                   f"coverage gap. Check find_examples returns a worked pattern for it.")
            basis = "entity reachable; failure is not structural"
        else:
            continue

        out[err_key] = {
            "potential_fix": fix,
            "basis": basis,
            "symbols": sorted(syms),
            "occurrences": d.get("count", 0),
            "first_seen": d.get("first_seen"),
        }
    return out


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def render_report(static: Dict[str, Any], tri: Dict[str, Any],
                  idx_paths: Optional[Dict[str, str]] = None) -> str:
    t = static["totals"]
    L: List[str] = []
    add = L.append
    add("# flexicon coverage-gap triage\n")
    if idx_paths:
        add("Indexes read:\n")
        for k, v in idx_paths.items():
            add(f"- `{k}`: `{v}`")
        add("")

    add("## Structural picture\n")
    pct = 100.0 * t["public_surface_reachable"] / t["public_surface"]
    add(f"- {t['public_reachable']} of {t['public_interfaces']} public LCM interfaces "
        f"reachable ({100.0*t['public_reachable']/t['public_interfaces']:.1f}%), "
        f"covering {t['public_surface_reachable']} of {t['public_surface']} members ({pct:.1f}%).")
    if t.get("measured_coverage_available"):
        add(f"- **Member-level coverage is measured**: {t['members_measured_covered']} members "
            f"across {t['types_with_measured_coverage']} LCM types carry a type-resolved "
            f"access recorded in the index.")
    else:
        add("- **No measured member coverage in this index.** Regenerate with a "
            "flextoolsmcp that writes `python_wrapper_members`; without it the counts "
            "below rest on entity-level reachability, which over-reports badly.")
    add(f"- {t['true_gaps']} candidate gaps carrying {t['true_gap_surface']} members: "
        f"in a served domain ({', '.join(LINGUISTIC_DOMAINS)}), declaring members, not a "
        f"`*Tags` constant holder, not reachable by inheritance, and with ZERO measured "
        f"member coverage.")
    add(f"- A further {t['unreachable_out_of_scope']} unreachable interfaces sit outside "
        f"those domains (scripture, system, service, general) and are not counted as gaps.")
    add("- Unreferenced is not the same as needed-and-missing. Only the log evidence "
        "below can tell you which of these anyone has actually reached for.")
    add(f"- flexicon: {t['flexicon_classes']} classes, {t['flexicon_methods']} methods; "
        f"{t['methods_without_example']} without an example, "
        f"{t['mutating_without_example']} of those mutating.\n")

    add("| LCM domain | interfaces | reachable | member surface | % surface reachable |")
    add("|---|---:|---:|---:|---:|")
    for d, v in sorted(static["domains"].items(),
                       key=lambda kv: -(kv[1]["member_surface"])):
        add(f"| {d} | {v['interfaces']} | {v['reachable']} | {v['member_surface']} | "
            f"{v['pct_member_surface']} |")
    add("")

    if not tri["has_log_evidence"]:
        add("## Live evidence\n")
        add("No log evidence supplied - this run is a structural audit only. "
            "Point `--logs` at a `~/.flextoolsmcp/logs` directory (or one a user "
            "sent you) to rank these gaps by what is actually being hit.\n")
        return "\n".join(L)

    add("## Live evidence\n")
    add(f"- {tri['n_runs']} run_module records; outcomes: "
        + ", ".join(f"{k} {v}" for k, v in sorted(tri["outcomes"].items())) + ".")
    if tri["gates"]:
        add("- preflight gates fired: "
            + ", ".join(f"`{k}` {v}" for k, v in list(tri["gates"].items())[:6]) + ".")
    if tri["error_codes"]:
        add("- error codes: "
            + ", ".join(f"`{k}` {v}" for k, v in list(tri["error_codes"].items())[:6]) + ".")
    _n = tri["workflow_noise"]
    add(f"- {_n} of those {'is a workflow gate' if _n == 1 else 'are workflow gates'} "
        f"(discovery, guards, syntax), not a coverage gap.\n")

    if tri["stuck_sessions"]:
        add("### Sessions that never reached a green run\n")
        add("| session | ops | error codes | user request |")
        add("|---|---:|---|---|")
        for s in tri["stuck_sessions"][:10]:
            req = (s["request"] or "")[:70].replace("|", "/")
            add(f"| `{(s['session_id'] or '')[:12]}` | {s['ops']} | "
                f"{', '.join(c for c in s['codes'] if c) or '-'} | {req} |")
        add("")

    if tri["candidates"]:
        add("### Ranked gap candidates\n")
        add("`direct?` marks a symbol reached by an explicit `from SIL.… import`, "
            "which is positive evidence the author bypassed flexicon.\n")
        add("| symbol | class | direct? | hits | domain | surface | action |")
        add("|---|---|:--:|---:|---|---:|---|")
        for c in tri["candidates"][:25]:
            add(f"| `{c['symbol']}` | {c['classification']} | "
                f"{'yes' if c['direct_lcm_import'] else ''} | {c['evidence_hits']} | "
                f"{c['lcm_domain'] or '-'} | {c['member_surface'] if c['member_surface'] is not None else '-'} | "
                f"{c['action']} |")
        add("")

    if tri["failing_apis"]:
        add("### Wrapper calls with failures\n")
        add("`example?` is whether the index holds a worked example for that exact "
            "method; `class examples` is the ratio for its whole class. A call that "
            "fails repeatedly and has no example is a documentation gap before it is "
            "a code bug - `find_examples` had nothing to return.\n")
        add("| api call | uses | failures | success rate | example? | class examples | common errors |")
        add("|---|---:|---:|---:|:--:|:--:|---|")
        for a in tri["failing_apis"][:20]:
            ex = {True: "yes", False: "**no**", None: "-"}[a["has_example"]]
            add(f"| `{a['api_call']}` | {a['uses']} | {a['failures']} | "
                f"{a['success_rate']}% | {ex} | {a['class_examples'] or '-'} | "
                f"{', '.join(a['errors']) or '-'} |")
        add("")

    if tri.get("fixes"):
        add("### Proposed `potential_fix` entries\n")
        add("PatternTracker allocates a `potential_fix` field on every error pattern "
            "and never writes it. These are derived from the code examples each "
            "pattern already stores, classified against the static gap map; merge "
            "them into `patterns.json` or treat them as ticket drafts.\n")
        for key, f in sorted(tri["fixes"].items(), key=lambda kv: -kv[1]["occurrences"]):
            add(f"- **{key[:90]}** ({f['occurrences']}x, basis: {f['basis']})  \n  {f['potential_fix']}")
        add("")

    if tri["failed_requests"]:
        add("### What users were asking for when it broke\n")
        seen = set()
        for r in tri["failed_requests"]:
            key = r["request"][:80]
            if key in seen:
                continue
            seen.add(key)
            add(f"- _{r['request'][:160]}_  (`{r['error_code'] or r['gate']}`)")
            if len(seen) >= 12:
                break
        add("")

    return "\n".join(L)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--index", required=True, type=Path,
                    help="flextoolsmcp src/flextoolsmcp/index directory")
    ap.add_argument("--logs", type=Path, default=None,
                    help="a ~/.flextoolsmcp/logs-shaped directory")
    ap.add_argument("--patterns", type=Path, default=None, help="explicit patterns.json")
    ap.add_argument("--jsonl", type=Path, nargs="*", default=None,
                    help="explicit operations.jsonl file(s)")
    ap.add_argument("--out", type=Path, default=Path("gap_report.md"))
    ap.add_argument("--csv", type=Path, default=None,
                    help="also write the ranked candidates as CSV")
    ap.add_argument("--fixes", type=Path, default=None,
                    help="write proposed patterns.json potential_fix entries as JSON")
    a = ap.parse_args(argv)

    idx = load_indexes(a.index)
    static = build_static_gap_map(idx)

    pats, recs = None, None
    if a.logs:
        found = discover_logs(a.logs)
        pats = load_patterns(a.patterns or found["patterns"])
        recs = load_jsonl(a.jsonl or found["jsonl"])
    else:
        if a.patterns:
            pats = load_patterns(a.patterns)
        if a.jsonl:
            recs = load_jsonl(a.jsonl)

    tri = triage(static, pats, recs)
    a.out.write_text(render_report(static, tri, idx.get("_paths")), encoding="utf-8")

    if a.csv:
        import csv as _csv
        cols = ["symbol", "classification", "direct_lcm_import", "evidence_hits",
                "lcm_domain", "member_surface", "distinct_errors", "action"]
        with open(a.csv, "w", newline="", encoding="utf-8") as fh:
            w = _csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(tri["candidates"])

    if a.fixes:
        a.fixes.write_text(json.dumps(
            {"error_patterns": {k: {"potential_fix": v["potential_fix"]}
                                for k, v in tri["fixes"].items()},
             "_basis": {k: v["basis"] for k, v in tri["fixes"].items()}},
            indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{a.out}: {static['totals']['true_gaps']} structural gaps, "
          f"{len(tri['candidates'])} log-evidenced candidates, "
          f"{tri['n_runs']} run records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
