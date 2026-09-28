#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local recipe store (unified-recipes Phase 4, FR-010..016).

Replaces server/skeleton_storage.py. Captures whole successful snippets
as one local recipe, deduplicated by a comment/whitespace-insensitive
fingerprint, with one-time legacy migration from skeletons.jsonl.

Storage: UTF-8 JSONL (ensure_ascii=False), atomic rewrite via temp +
os.replace, 2,000-row cap. Never raises; capture returns None on any
failure or precondition miss.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import tokenize
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

_RECIPE_ENV = "FLEXTOOLSMCP_RECIPE_DIR"
_SKELETON_ENV = "FLEXTOOLSMCP_SKELETON_DIR"
_LOG_ENV = "FLEXTOOLSMCP_LOG_DIR"
_DEFAULT_SUBDIR = ".flextoolsmcp"
_FILENAME = "recipes.jsonl"
_LEGACY_FILENAME = "skeletons.jsonl"
_SCHEMA = "local-recipe/1"
_CAP = 2000

_WRITE_LOCK = Lock()

__all__ = [
    "get_recipe_dir",
    "get_recipe_path",
    "fingerprint_code",
    "fingerprint",
    "capture",
    "capture_from_code",
    "load_local_recipes",
    "load_all",
    "list_local_recipes",
    "get_all",
    "migrate_legacy_skeletons",
    "migrate_legacy",
    "ensure_migrated",
]


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def get_recipe_dir() -> Path:
    override = os.environ.get(_RECIPE_ENV)
    if override:
        return Path(override)
    fallback = os.environ.get(_SKELETON_ENV)
    if fallback:
        return Path(fallback)
    return Path.home() / _DEFAULT_SUBDIR


def get_recipe_path() -> Path:
    directory = get_recipe_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / _FILENAME


def _legacy_candidates() -> List[Path]:
    cands: List[Path] = []
    try:
        cands.append(get_recipe_dir() / _LEGACY_FILENAME)
    except Exception:
        pass
    skel_env = os.environ.get(_SKELETON_ENV)
    if skel_env:
        cands.append(Path(skel_env) / _LEGACY_FILENAME)
    # skeleton_storage default location (best-effort, read-only).
    try:
        from . import skeleton_storage as _skel  # type: ignore
        try:
            cands.append(Path(str(_skel.get_skeleton_path())))
        except Exception:
            pass
    except Exception:
        try:
            import skeleton_storage as _skel2  # type: ignore
            try:
                cands.append(Path(str(_skel2.get_skeleton_path())))
            except Exception:
                pass
        except Exception:
            pass
    # Dedupe, preserve order.
    seen = set()
    out: List[Path] = []
    for p in cands:
        s = str(p)
        if s not in seen:
            seen.add(s)
            out.append(p)
    return out


def _ops_log_candidates() -> List[Path]:
    cands: List[Path] = []
    log_env = os.environ.get(_LOG_ENV)
    if log_env:
        cands.append(Path(log_env) / "operations.jsonl")
        cands.append(Path(log_env) / "operations.jsonl.1")
    try:
        cands.append(get_recipe_dir() / "logs" / "operations.jsonl")
        cands.append(get_recipe_dir() / "logs" / "operations.jsonl.1")
    except Exception:
        pass
    cands.append(Path.home() / _DEFAULT_SUBDIR / "logs" / "operations.jsonl")
    cands.append(Path.home() / _DEFAULT_SUBDIR / "logs" / "operations.jsonl.1")
    # Also try kernel log dir if importable.
    try:
        from . import kernel as _k  # type: ignore
        try:
            ld = _k.get_log_dir()
            if ld:
                cands.append(Path(str(ld)) / "operations.jsonl")
        except Exception:
            pass
    except Exception:
        pass
    seen = set()
    out: List[Path] = []
    for p in cands:
        s = str(p)
        if s not in seen:
            seen.add(s)
            out.append(p)
    return out


# ---------------------------------------------------------------------------
# Fingerprint (R7)
# ---------------------------------------------------------------------------

def _normalize_code(code: str) -> str:
    try:
        # Find COMMENT token starts so '#' inside strings survives.
        comment_starts: Dict[int, int] = {}
        try:
            toks = tokenize.generate_tokens(io.StringIO(code).readline)
            for tok in toks:
                if tok.type == tokenize.COMMENT:
                    srow, scol = tok.start
                    if srow not in comment_starts or scol < comment_starts[srow]:
                        comment_starts[srow] = scol
        except Exception:
            comment_starts = {}
        lines = code.splitlines()
        normed: List[str] = []
        for i, line in enumerate(lines, start=1):
            if i in comment_starts:
                line = line[: comment_starts[i]]
            # Collapse whitespace runs to one space, strip, drop blanks.
            collapsed = re.sub(r"\s+", " ", line).strip()
            if collapsed:
                normed.append(collapsed)
        return "\n".join(normed)
    except Exception:
        # Line-based fallback.
        normed = []
        for line in code.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            normed.append(re.sub(r"\s+", " ", stripped))
        return "\n".join(normed)


def fingerprint_code(code: str) -> str:
    return hashlib.sha256(_normalize_code(code).encode("utf-8")).hexdigest()[:12]


# Backwards/forwards alias.
def fingerprint(code: str) -> str:
    return fingerprint_code(code)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _real_line_count(code: str) -> int:
    n = 0
    for line in code.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            n += 1
    return n


# ---------------------------------------------------------------------------
# Entities (R8)
# ---------------------------------------------------------------------------

_FALLBACK_OPS = {
    "Senses": "LexSense",
    "LexEntry": "LexEntry",
    "LexEntries": "LexEntry",
    "Wordforms": "WfiWordform",
    "Wordform": "WfiWordform",
    "Texts": "Text",
    "Text": "Text",
    "PhonRules": "PhonologicalRule",
    "PartsOfSpeech": "PartOfSpeech",
}

_INTERFACE_RE = re.compile(r"^I[A-Z]\w+$")


def _accessor_map() -> Dict[str, str]:
    try:
        try:
            from . import validators as _v  # type: ignore
        except ImportError:
            import validators as _v  # type: ignore
        api_index = None
        try:
            try:
                from . import kernel as _k  # type: ignore
            except ImportError:
                import kernel as _k  # type: ignore
            try:
                api_index = _k.get_api_index()
            except Exception:
                api_index = None
        except Exception:
            api_index = None
        try:
            m = _v._accessor_to_ops_map(api_index)
            if isinstance(m, dict) and m:
                return m
        except Exception:
            pass
    except Exception:
        pass
    return {}


def _entities_from_code(code: str) -> List[str]:
    ents: set = set()
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    mapping = _accessor_map()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            val = node.value
            if isinstance(val, ast.Name) and val.id == "project":
                accessor = node.attr
                ops = mapping.get(accessor)
                if ops:
                    ent = ops[:-len("Operations")] if ops.endswith("Operations") else ops
                    ents.add(ent)
                elif accessor in _FALLBACK_OPS:
                    ents.add(_FALLBACK_OPS[accessor])
                else:
                    ents.add(accessor)
        elif isinstance(node, ast.Name):
            if _INTERFACE_RE.match(node.id or ""):
                ents.add(node.id)
    return sorted(ents)


def _extract_params(code: str) -> List[Dict[str, str]]:
    try:
        try:
            from .. import recipe_files as _rf  # type: ignore
        except ImportError:
            import recipe_files as _rf  # type: ignore
        params = _rf.parse_params(code)
        if isinstance(params, list):
            return params
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------

def _read_rows(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        if not path.exists():
            return rows
        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict) and obj.get("id"):
                    rows.append(obj)
    except Exception:
        return rows
    return rows


def _atomic_write(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        for r in rows:
            fp.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(str(tmp), str(path))


def _apply_cap(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(rows) <= _CAP:
        return rows
    rows_sorted = sorted(
        rows,
        key=lambda r: (int(r.get("use_count", 0) or 0), str(r.get("last_used", ""))),
    )
    return rows_sorted[len(rows) - _CAP:]


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------

def capture(
    code: str = "",
    *,
    user_intent: Optional[str] = None,
    user_request: Optional[str] = None,
    project: Optional[str] = None,
    project_name: Optional[str] = None,
    requires_write: bool = False,
    is_mutating: bool = False,
    is_mutating_script: bool = False,
    mutating: bool = False,
    op_id: str = "",
    op_ids: Optional[List[str]] = None,
    session_id: str = "",
    **_extra: Any,
) -> Optional[Dict[str, Any]]:
    try:
        intent = (user_intent or "")
        if not intent.strip():
            return None
        intent = intent.strip()
        if not code or _real_line_count(code) < 4:
            return None
        try:
            ast.parse(code)
        except SyntaxError:
            return None
        fp = fingerprint_code(code)
        rid = f"local-{fp}"
        entities = _entities_from_code(code)
        params = _extract_params(code)
        mut = bool(requires_write or is_mutating or is_mutating_script or mutating)
        proj = project if project is not None else (project_name or "")
        now = _now_iso()
        with _WRITE_LOCK:
            try:
                _maybe_migrate_locked()
            except Exception:
                pass
            try:
                path = get_recipe_path()
            except Exception:
                return None
            rows = _read_rows(path)
            existing = None
            for r in rows:
                if r.get("id") == rid:
                    existing = r
                    break
            if existing is not None:
                existing["use_count"] = int(existing.get("use_count", 1) or 1) + 1
                existing["last_used"] = now
                oids = list(existing.get("op_ids", []) or [])
                if op_id and op_id not in oids:
                    oids.append(op_id)
                existing["op_ids"] = oids[-5:]
                projs = set(existing.get("projects", []) or [])
                if proj:
                    projs.add(proj)
                existing["projects"] = sorted(projs)
                if mut:
                    existing["requires_write"] = True
                    existing["operations"] = ["read", "write"]
                existing["intent"] = intent
                existing["code"] = code
                if entities:
                    existing["entities"] = entities
                if params:
                    existing["params"] = params
                if "operations" not in existing:
                    existing["operations"] = ["read", "write"] if bool(existing.get("requires_write")) else ["read"]
                rows = _apply_cap(rows)
                try:
                    _atomic_write(path, rows)
                except Exception:
                    return None
                return dict(existing)
            record: Dict[str, Any] = {
                "id": rid,
                "intent": intent,
                "code": code,
                "entities": entities,
                "requires_write": mut,
                "operations": ["read", "write"] if mut else ["read"],
                "params": params,
                "projects": [proj] if proj else [],
                "first_used": now,
                "last_used": now,
                "use_count": 1,
                "op_ids": [op_id] if op_id else [],
                "source": "local",
                "migrated": False,
                "schema": _SCHEMA,
            }
            rows.append(record)
            rows = _apply_cap(rows)
            try:
                _atomic_write(path, rows)
            except Exception:
                return None
            return dict(record)
    except Exception:
        return None


# Alias for skeleton-era callers/tests.
def capture_from_code(code: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
    # Old shape: capture_from_code(code, entities_used=..., user_intent=..., ...)
    kwargs.pop("entities_used", None)
    kwargs.pop("entities", None)
    return capture(code, **kwargs)


def load_local_recipes() -> List[Dict[str, Any]]:
    try:
        _maybe_migrate_locked()
    except Exception:
        pass
    try:
        return _read_rows(get_recipe_path())
    except Exception:
        return []


def load_all() -> List[Dict[str, Any]]:
    return load_local_recipes()


def list_local_recipes(limit: int = 100) -> List[Dict[str, Any]]:
    rows = load_local_recipes()
    rows.sort(key=lambda r: str(r.get("last_used", "")), reverse=True)
    return rows[:limit]


def get_all() -> List[Dict[str, Any]]:
    return load_local_recipes()


# ---------------------------------------------------------------------------
# Legacy migration (R9)
# ---------------------------------------------------------------------------

def _load_ops_intents() -> Dict[str, str]:
    intents: Dict[str, str] = {}
    for p in _ops_log_candidates():
        try:
            if not p.exists():
                continue
            with p.open("r", encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    oid = obj.get("op_id") or obj.get("opId")
                    ui = obj.get("user_intent")
                    if ui is None:
                        ui = obj.get("user_request", "")
                    if oid and ui and str(ui).strip() and oid not in intents:
                        intents[str(oid)] = str(ui).strip()
        except Exception:
            continue
    return intents


def _is_trivial_helper_source(source: str) -> bool:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    if not funcs:
        return False
    for fn in funcs:
        # At most one statement (allow docstring + return).
        body = [n for n in fn.body
                if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                        and isinstance(n.value.value, str))]
        if len(body) > 1:
            return False
        if len(body) == 0:
            return True
        stmt = body[0]
        if not isinstance(stmt, ast.Return):
            return False
        seg = ast.get_source_segment(source, stmt) or ""
        if (".Text" in seg or "BestAnalysis" in seg
                or "BestVernacular" in seg or "'***'" in seg or '"***"' in seg):
            continue
        return False
    return True


def _migrate_once() -> List[Dict[str, Any]]:
    try:
        recipe_path = get_recipe_path()
    except Exception:
        return []
    # Run once: if recipes.jsonl already has valid rows, do nothing.
    try:
        if recipe_path.exists():
            existing = _read_rows(recipe_path)
            if existing:
                return existing
    except Exception:
        pass
    legacy_path: Optional[Path] = None
    for cand in _legacy_candidates():
        try:
            if cand.exists() and cand.stat().st_size > 0:
                legacy_path = cand
                break
        except Exception:
            continue
    if legacy_path is None:
        return []
    try:
        raw_entries: List[Dict[str, Any]] = []
        with legacy_path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    raw_entries.append(obj)
    except Exception:
        return []
    if not raw_entries:
        return []
    # Group by op_id, keep capture order.
    groups: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for e in raw_entries:
        oid = str(e.get("op_id", "") or "unknown")
        if oid not in groups:
            groups[oid] = []
            order.append(oid)
        groups[oid].append(e)
    ops_intents = _load_ops_intents()
    merged: Dict[str, Dict[str, Any]] = {}
    for oid in order:
        entries = groups[oid]
        parts: List[str] = []
        for e in entries:
            src = e.get("source", "") or ""
            if src and src not in parts:
                parts.append(src.rstrip() + "\n")
        body = "\n".join(parts).strip() + "\n" if parts else ""
        if not body:
            continue
        if _real_line_count(body) < 5:
            continue
        if _is_trivial_helper_source(body):
            continue
        # Intent: ops log, else entries' own, else null.
        intent: Optional[str] = ops_intents.get(oid)
        if not intent:
            for e in entries:
                ui = (e.get("user_intent") or "").strip()
                if ui:
                    intent = ui
                    break
        fp = fingerprint_code(body)
        rid = f"local-{fp}"
        captured = [str(e.get("captured_at", "") or "") for e in entries]
        captured = [c for c in captured if c]
        first = min(captured) if captured else _now_iso()
        last = max(captured) if captured else _now_iso()
        entities = _entities_from_code(body)
        if not entities:
            union: set = set()
            for e in entries:
                for en in e.get("entities", []) or []:
                    if en:
                        union.add(en)
            entities = sorted(union)
        if rid in merged:
            m = merged[rid]
            m["use_count"] = int(m.get("use_count", 1)) + 1
            if last > str(m.get("last_used", "")):
                m["last_used"] = last
            if first < str(m.get("first_used", "")):
                m["first_used"] = first
            oids = list(m.get("op_ids", []) or [])
            if oid not in oids:
                oids.append(oid)
            m["op_ids"] = oids[-5:]
            if intent and not m.get("intent"):
                m["intent"] = intent
        else:
            merged[rid] = {
                "id": rid,
                "intent": intent,
                "code": body,
                "entities": entities,
                "requires_write": False,
                "operations": ["read"],
                "params": [],
                "projects": [],
                "first_used": first,
                "last_used": last,
                "use_count": 1,
                "op_ids": [oid],
                "source": "local",
                "migrated": True,
                "schema": _SCHEMA,
            }
    rows = list(merged.values())
    rows = _apply_cap(rows)
    try:
        _atomic_write(recipe_path, rows)
    except Exception:
        return rows
    return rows


def _maybe_migrate_locked() -> List[Dict[str, Any]]:
    try:
        return _migrate_once()
    except Exception:
        return []


def migrate_legacy_skeletons(*_a: Any, **_k: Any) -> List[Dict[str, Any]]:
    try:
        with _WRITE_LOCK:
            return _migrate_once()
    except Exception:
        return []


def migrate_legacy(*_a: Any, **_k: Any) -> List[Dict[str, Any]]:
    return migrate_legacy_skeletons()


def ensure_migrated(*_a: Any, **_k: Any) -> List[Dict[str, Any]]:
    return migrate_legacy_skeletons()


def run_migration_if_needed(*_a: Any, **_k: Any) -> List[Dict[str, Any]]:
    return migrate_legacy_skeletons()


def migrate_if_needed(*_a: Any, **_k: Any) -> List[Dict[str, Any]]:
    return migrate_legacy_skeletons()
