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

Issue #309: a run is only remembered when it looks like real work (see
remember_rejection_reason), rows with the same intent + entities collapse
into one, and requires_write comes from the run's write evidence (see
derive_requires_write) rather than a default. Legacy rows stored as
read-only are re-checked on load and flipped to write when the evidence
says so, so a reused write recipe never skips the dry-run gate.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import tempfile
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
    "remember_rejection_reason",
    "derive_requires_write",
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
# Remember gate (issue #309)
# ---------------------------------------------------------------------------
#
# A run that "succeeded" is not necessarily worth remembering. Three cheap,
# deliberately conservative checks decide; any hit means the run is not
# stored (missing a recipe costs little, a fabricated one gets reused):
#
# 1. Swallowed exception that fabricates a result: a bare / `except
#    Exception` / `except BaseException` handler that neither re-raises,
#    nor reports via report.Error / report.Warning, nor uses the caught
#    exception, but does produce a non-empty string literal (e.g.
#    `status = "No - Unknown issue"`). Plain skip handlers (pass, continue,
#    return None) are allowed -- shipped recipes use them for probes.
# 2. Hard-coded source data: a for-loop iterates a literal table -- a
#    list/tuple/set whose items are all tuples/lists of constants, at least
#    one mixing a string with a number, e.g. [('000', 154091)] -- defined
#    outside the PARAMS block. Rows like that are pasted query results, not
#    data read from the project. Flat literal lists (filters, names) and
#    anything inside PARAMS are not flagged.
# 3. Trivial messages (only when the caller passes them): no report output
#    at all; every message carries a failure marker ("unknown issue",
#    "has no attribute", ...); or 3+ messages identical once digits are
#    masked.

_BROAD_EXC_NAMES = {"Exception", "BaseException"}
_FAILURE_MARKER_RE = re.compile(
    r"unknown issue|unknown error|has no attribute|"
    r"traceback \(most recent|not implemented",
    re.IGNORECASE,
)
_PARAMS_START_MARK = "# --- PARAMS ---"
_PARAMS_END_MARK = "# --- END PARAMS ---"


def _is_broad_handler(handler: ast.ExceptHandler) -> bool:
    t = handler.type
    if t is None:
        return True
    elts = t.elts if isinstance(t, ast.Tuple) else [t]
    for e in elts:
        name = e.id if isinstance(e, ast.Name) else (
            e.attr if isinstance(e, ast.Attribute) else "")
        if name in _BROAD_EXC_NAMES:
            return True
    return False


def _handler_fabricates(handler: ast.ExceptHandler) -> bool:
    has_string = False
    for stmt in handler.body:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Raise):
                return False
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr in ("Error", "Warning")):
                return False
            if handler.name and isinstance(n, ast.Name) and n.id == handler.name:
                return False
            if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and n.value.strip()):
                has_string = True
    return has_string


def _has_fabricating_handler(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_broad_handler(node):
            if _handler_fabricates(node):
                return True
    return False


def _params_line_range(code: str) -> Optional[range]:
    start = None
    for i, line in enumerate(code.splitlines(), start=1):
        s = line.strip()
        if start is None and s.startswith(_PARAMS_START_MARK):
            start = i
        elif start is not None and s.startswith(_PARAMS_END_MARK):
            return range(start, i + 1)
    return None


def _is_const(n: ast.AST) -> bool:
    return isinstance(n, ast.Constant) or (
        isinstance(n, ast.UnaryOp) and isinstance(n.operand, ast.Constant))


def _is_number(n: ast.AST) -> bool:
    if isinstance(n, ast.UnaryOp):
        n = n.operand
    return (isinstance(n, ast.Constant) and isinstance(n.value, (int, float))
            and not isinstance(n.value, bool))


def _is_literal_table(n: ast.AST) -> bool:
    if not isinstance(n, (ast.List, ast.Tuple, ast.Set)) or not n.elts:
        return False
    mixed = False
    for row in n.elts:
        if not isinstance(row, (ast.Tuple, ast.List)) or not row.elts:
            return False
        if not all(_is_const(c) for c in row.elts):
            return False
        has_str = any(isinstance(c, ast.Constant) and isinstance(c.value, str)
                      for c in row.elts)
        if has_str and any(_is_number(c) for c in row.elts):
            mixed = True
    return mixed


def _iterates_literal_table(code: str, tree: ast.AST) -> bool:
    params = _params_line_range(code)

    def _outside_params(n: ast.AST) -> bool:
        return params is None or getattr(n, "lineno", 0) not in params

    tables: set = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and _is_literal_table(node.value)
                and _outside_params(node)):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    tables.add(tgt.id)

    def _is_table_ref(n: ast.AST) -> bool:
        if isinstance(n, ast.Name):
            return n.id in tables
        if _is_literal_table(n):
            return _outside_params(n)
        # sorted(rows), enumerate(rows), list(rows), rows[:10]
        if isinstance(n, ast.Call) and n.args:
            return _is_table_ref(n.args[0])
        if isinstance(n, ast.Subscript):
            return _is_table_ref(n.value)
        return False

    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.comprehension)) and _is_table_ref(node.iter):
            return True
    return False


def _message_texts(messages: List[Any]) -> List[str]:
    texts: List[str] = []
    for m in messages:
        t = m.get("message") if isinstance(m, dict) else m
        if t is None:
            continue
        t = str(t).strip()
        if t:
            texts.append(t)
    return texts


def _reported_error(messages: List[Any]) -> bool:
    """True when any report message is ERROR-level (issue #335)."""
    for m in messages:
        if isinstance(m, dict) and str(m.get("type", "")).strip().lower() == "error":
            return True
    return False


def _trivial_messages_reason(messages: List[Any]) -> Optional[str]:
    # Issue #335: the runner's success flag only means "no uncaught
    # exception"; a run that called report.Error did not succeed at its task
    # and is not a recipe to hand back next session.
    if _reported_error(messages):
        return "the run reported errors"
    texts = _message_texts(messages)
    if not texts:
        return "no report output"
    if all(_FAILURE_MARKER_RE.search(t) for t in texts):
        return "every message reports an unknown/failed result"
    if len(texts) >= 3 and len({re.sub(r"\d+", "#", t) for t in texts}) == 1:
        return "identical repeated messages"
    return None


def remember_rejection_reason(code: str,
                              messages: Optional[List[Any]] = None
                              ) -> Optional[str]:
    """Why a successful run should NOT be remembered, or None if it may be.

    ``messages`` is the run's report message list; None means unknown and
    skips the message checks (store-level callers without a run).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return "code does not parse"
    try:
        if _has_fabricating_handler(tree):
            return "broad except handler swallows the error and fabricates a result"
        if _iterates_literal_table(code, tree):
            return "source data is a hard-coded literal table"
        if messages is not None:
            return _trivial_messages_reason(list(messages))
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# requires_write derivation (issue #309)
# ---------------------------------------------------------------------------

# Capitalised .NET / Flexicon mutator verbs. Case-sensitive on purpose:
# Python's own list.append / set.add / dict.update / str.replace are
# lowercase and never match.
_MUTATOR_METHOD_RE = re.compile(
    r"^(Create|Add|Set|Delete|Remove|Move|Merge|Insert|Replace|Clear)([A-Z_]|$)")
# Raw LibLCM owning/reference property suffixes (SensesOS, CategoryRA, ...).
_LCM_FIELD_RE = re.compile(r"\w(OA|RA|OS|RS|OC|RC)$")


def _mutator_names_in(tree: ast.AST) -> bool:
    """Name-based write scan that needs no API index.

    Flags any call to a capitalised mutator method on any receiver
    (project.LexEntry.SetLexemeForm, entry.SensesOS.Add, ops.MergeObject)
    and any assignment to a raw LCM OA/RA/OS/RS/OC/RC property. Coarse on
    purpose: it backs up the index-based certifier when that cannot run,
    and a false positive only costs a dry run.
    """
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and _MUTATOR_METHOD_RE.match(node.func.attr)):
            return True
        if (isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)
                and _LCM_FIELD_RE.search(node.attr)):
            return True
    return False


def _code_is_write_shaped(code: str) -> bool:
    """Static write evidence, reusing the run_module write detectors.

    True when the code reads ``modifyAllowed`` (a write guard, not just the
    Main() parameter), when the name-based mutator scan hits, when
    detect_cud_operations() flags a CUD call, or when the index-based
    certifier (compute_is_mutating_script) finds any mutation, guarded or
    not. The name scan always runs, so a missing validators module or API
    index degrades to a coarser check instead of failing open to read-only.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Code that cannot be vetted is treated as a write.
        return True
    for node in ast.walk(tree):
        if (isinstance(node, ast.Name) and node.id == "modifyAllowed"
                and isinstance(node.ctx, ast.Load)):
            return True
    if _mutator_names_in(tree):
        return True
    try:
        try:
            from . import validators as _v  # type: ignore
        except ImportError:
            import validators as _v  # type: ignore
    except Exception:
        return False
    cud: Dict[str, Any] = {}
    try:
        cud = _v.detect_cud_operations(code) or {}
        if cud.get("is_cud"):
            return True
    except Exception:
        cud = {}
    idx = None
    try:
        try:
            from . import kernel as _k  # type: ignore
        except ImportError:
            import kernel as _k  # type: ignore
        idx = _k.get_api_index()
    except Exception:
        idx = None
    if idx is not None:
        try:
            cert = _v.certify_script_readonly(code, idx, tree)
            if _v.compute_is_mutating_script(cert, cud):
                return True
        except Exception:
            pass
    return False


def derive_requires_write(
    code: str,
    *,
    declared: bool = False,
    write_enabled: Optional[bool] = None,
    performs_writes: Optional[bool] = None,
    lcm_undoable_action_count: Any = None,
) -> bool:
    """Decide requires_write from the run's write evidence; when in doubt, True.

    - declared (the caller's is_mutating_script) or performs_writes -> True
    - LCM recorded undoable actions (> 0) -> True (catches #280 index gaps)
    - write_enabled run that reported no action count -> True
    - code is write-shaped (_code_is_write_shaped) -> True
    A write_enabled run whose LCM count was 0 and whose code shows no write
    stays read-only, so a write-enabled session does not taint read recipes.
    """
    if declared or performs_writes is True:
        return True
    count: Optional[int] = None
    if lcm_undoable_action_count is not None:
        try:
            count = int(lcm_undoable_action_count)
        except (TypeError, ValueError):
            count = None
    if count is not None and count > 0:
        return True
    if write_enabled and count is None:
        return True
    return _code_is_write_shaped(code)


def _norm_intent(intent: Any) -> str:
    return re.sub(r"\s+", " ", str(intent or "")).strip().casefold().rstrip(".!? ")


# ---------------------------------------------------------------------------
# Legacy requires_write repair (issue #309)
# ---------------------------------------------------------------------------
#
# Rows written before #309 (and rows migrated from skeletons.jsonl) could be
# stored requires_write False although the run wrote. On load, any such row
# whose code is write-shaped, or whose recorded op_ids include a
# write_enabled run in operations.jsonl, is flipped to requires_write True
# and tagged requires_write_repaired. The check is keyed on the file's
# (mtime, size) so unchanged stores are not re-scanned on every load.

_REPAIR_SEEN: Dict[str, Any] = {}


def _stat_key(path: Path) -> Optional[tuple]:
    try:
        st = path.stat()
        return (st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def _load_write_enabled_op_ids() -> set:
    ids: set = set()
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
                    if not isinstance(obj, dict) or not obj.get("write_enabled"):
                        continue
                    oid = obj.get("op_id") or obj.get("opId")
                    if oid:
                        ids.add(str(oid))
        except Exception:
            continue
    return ids


def _repair_write_flags(rows: List[Dict[str, Any]]) -> bool:
    candidates = [r for r in rows if not bool(r.get("requires_write"))]
    if not candidates:
        return False
    write_ops: Optional[set] = None
    changed = False
    for r in candidates:
        evidence = _code_is_write_shaped(str(r.get("code") or ""))
        if not evidence and r.get("op_ids"):
            if write_ops is None:
                write_ops = _load_write_enabled_op_ids()
            evidence = any(str(o) in write_ops for o in r.get("op_ids") or [])
        if evidence:
            r["requires_write"] = True
            r["operations"] = ["read", "write"]
            r["requires_write_repaired"] = True
            changed = True
    return changed


def _ensure_write_flags_locked(path: Path) -> Optional[List[Dict[str, Any]]]:
    """Repair legacy write flags; caller holds _WRITE_LOCK.

    Returns the rows it read (repaired in memory), or None when the store
    was already checked at this (mtime, size). If persisting the repair
    fails (e.g. a Windows PermissionError from os.replace) the repaired
    rows are still returned, so callers never see the stale False flags,
    and the cache is left unset so the next load retries the write.
    """
    key = _stat_key(path)
    if key is None or _REPAIR_SEEN.get(str(path)) == key:
        return None
    rows = _read_rows(path)
    if rows and _repair_write_flags(rows):
        try:
            _atomic_write(path, rows)
        except Exception:
            return rows
    _REPAIR_SEEN[str(path)] = _stat_key(path)
    return rows


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
    # Unique temp file in the same directory: a fixed recipes.jsonl.tmp
    # collides when two threads or server processes write at once.
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp",
                               dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            for r in rows:
                fp.write(json.dumps(r, ensure_ascii=False) + "\n")
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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
    write_enabled: Optional[bool] = None,
    performs_writes: Optional[bool] = None,
    lcm_undoable_action_count: Any = None,
    messages: Optional[List[Any]] = None,
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
        # Issue #309: swallowed-exception / hard-coded-data / trivial-output
        # runs are not worth remembering.
        if remember_rejection_reason(code, messages) is not None:
            return None
        fp = fingerprint_code(code)
        rid = f"local-{fp}"
        entities = _entities_from_code(code)
        params = _extract_params(code)
        # Issue #309: requires_write from the run's write evidence, not a
        # default -- a reused write recipe must hit the dry-run gate.
        mut = derive_requires_write(
            code,
            declared=bool(requires_write or is_mutating or is_mutating_script or mutating),
            write_enabled=write_enabled,
            performs_writes=performs_writes,
            lcm_undoable_action_count=lcm_undoable_action_count,
        )
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
            repaired: Optional[List[Dict[str, Any]]] = None
            try:
                repaired = _ensure_write_flags_locked(path)
            except Exception:
                repaired = None
            # Build on the repaired rows so this write persists the repair
            # even if the repair's own write failed.
            rows = repaired if repaired is not None else _read_rows(path)
            existing = None
            for r in rows:
                if r.get("id") == rid:
                    existing = r
                    break
            if existing is None:
                # Issue #309: same intent + same entities is the same recipe,
                # even when the code drifted (keeps the newest code).
                key = _norm_intent(intent)
                for r in rows:
                    if (_norm_intent(r.get("intent")) == key
                            and sorted(r.get("entities") or []) == entities):
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
                # Sticky on purpose: once any run of this recipe (by
                # fingerprint or intent+entities) wrote, it stays a write.
                # A later read-only run never clears the flag, because a
                # stale True only costs a dry run while a stale False lets
                # a write skip the dry-run gate.
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
                existing.setdefault("verified", False)
                rows = _apply_cap(rows)
                try:
                    _atomic_write(path, rows)
                except Exception:
                    return None
                _REPAIR_SEEN[str(path)] = _stat_key(path)
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
                # Auto-remembered, never human-reviewed (issue #309).
                "verified": False,
                "schema": _SCHEMA,
            }
            rows.append(record)
            rows = _apply_cap(rows)
            try:
                _atomic_write(path, rows)
            except Exception:
                return None
            _REPAIR_SEEN[str(path)] = _stat_key(path)
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
        path = get_recipe_path()
    except Exception:
        return []
    try:
        with _WRITE_LOCK:
            try:
                _maybe_migrate_locked()
            except Exception:
                pass
            # Issue #309: flip legacy read-only rows that actually wrote.
            # Use the repaired rows even if persisting them failed.
            repaired: Optional[List[Dict[str, Any]]] = None
            try:
                repaired = _ensure_write_flags_locked(path)
            except Exception:
                repaired = None
            if repaired is not None:
                return repaired
            return _read_rows(path)
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
            # Issue #309: legacy skeletons carry no write record, so derive
            # the flag from the code instead of defaulting to read-only.
            mig_write = derive_requires_write(body)
            merged[rid] = {
                "id": rid,
                "intent": intent,
                "code": body,
                "entities": entities,
                "requires_write": mig_write,
                "operations": ["read", "write"] if mig_write else ["read"],
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
