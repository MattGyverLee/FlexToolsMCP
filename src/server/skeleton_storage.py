#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Skeleton storage closet (issue #24).

Persists working helper functions across sessions so that the same
``pos_abbr`` / ``get_words`` / ``seg_interlinear`` helpers don't have to be
rewritten on every server restart. After a ``flextools_run_module`` op
succeeds, top-level ``def`` nodes from the executed code are captured here.
``flextools_find_examples`` and the dedicated ``flextools_list_skeletons``
tool surface them back to the user later.

Storage layout
--------------
- One JSON object per line (JSONL) in ``skeletons.jsonl``.
- Append-only writes; duplicates (same ``name`` + same ``source``) are
  silently skipped on capture.
- Default location: ``<project-root>/.flextoolsmcp/skeletons.jsonl``.
  Override via the ``FLEXTOOLSMCP_SKELETON_DIR`` env var.

Follow-ups (not in MVP):
- Size cap / rotation -- the JSONL grows unbounded right now.
- Embedding-based recall instead of substring matching on user_intent.
- Per-session pruning when a captured helper later fails.
"""

from __future__ import annotations

import ast
import json
import os
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Iterable, List, Optional, TypedDict


# ---------------------------------------------------------------------------
# Path / IO helpers
# ---------------------------------------------------------------------------

_ENV_VAR = "FLEXTOOLSMCP_SKELETON_DIR"
_DEFAULT_SUBDIR = ".flextoolsmcp"
_FILENAME = "skeletons.jsonl"

# Single-process serialization. The MCP server is single-process today, but
# capture happens from an async handler -- we still want consistent append
# semantics even if two ops finish in quick succession.
_WRITE_LOCK = Lock()


def _project_root() -> Path:
    """Return the project root (two levels up from this file).

    Layout: <root>/src/server/skeleton_storage.py
    """
    return Path(__file__).resolve().parent.parent.parent


def get_skeleton_dir() -> Path:
    """Resolve the skeleton storage directory, honoring the env override."""
    override = os.environ.get(_ENV_VAR)
    if override:
        return Path(override)
    return _project_root() / _DEFAULT_SUBDIR


def get_skeleton_path() -> Path:
    """Resolve the full JSONL path. Creates the parent directory on demand."""
    directory = get_skeleton_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / _FILENAME


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class SkeletonClosetEntry(TypedDict):
    name: str                   # function name (e.g. "pos_abbr")
    source: str                 # the def source (top-level def, dedented)
    entities: List[str]         # entity names the function walks
    user_intent: Optional[str]  # if RunModuleInput.user_intent provided (issue #18)
    captured_at: str            # ISO timestamp
    op_id: str
    session_id: str
    duration_ms: int


# ---------------------------------------------------------------------------
# AST extraction
# ---------------------------------------------------------------------------


def _extract_top_level_defs(code: str) -> List[ast.FunctionDef]:
    """Return only module-level ``def`` nodes from ``code``.

    Nested defs (closures, methods of inline classes, defs inside ``Main``)
    are deliberately excluded -- they aren't reusable helpers in isolation.
    Parse failures are swallowed; capture must never crash the caller.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    return [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    ]


def _def_source(code: str, node: ast.FunctionDef) -> Optional[str]:
    """Slice ``code`` to get the textual source for a top-level def.

    ``ast.get_source_segment`` is the canonical way; we fall back to a
    manual line slice if it returns None (older Pythons, decorators in
    odd positions, etc.). Result is dedented for storage cleanliness.
    """
    segment = ast.get_source_segment(code, node)
    if segment is None:
        # Manual fallback: use line numbers (1-indexed).
        lines = code.splitlines()
        start = (node.lineno - 1) if node.lineno else 0
        end_lineno = getattr(node, "end_lineno", None)
        if end_lineno is None:
            return None
        segment = "\n".join(lines[start:end_lineno])

    return textwrap.dedent(segment).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


def _iter_entries(path: Path) -> Iterable[SkeletonClosetEntry]:
    """Stream entries from the JSONL file. Skips malformed lines."""
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    # Don't fail the whole read on one bad line.
                    continue
    except OSError:
        return


def _load_all(path: Path) -> List[SkeletonClosetEntry]:
    return list(_iter_entries(path))


def _is_duplicate(
    existing: Iterable[SkeletonClosetEntry],
    name: str,
    source: str,
) -> bool:
    """A skeleton is a duplicate if same function name AND identical source."""
    for entry in existing:
        if entry.get("name") == name and entry.get("source") == source:
            return True
    return False


def _now_iso() -> str:
    """UTC ISO-8601 timestamp with seconds precision (sortable, stable)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def capture_from_code(
    code: str,
    *,
    entities_used: List[str],
    user_intent: Optional[str],
    op_id: str,
    session_id: str,
    duration_ms: int,
) -> List[SkeletonClosetEntry]:
    """Parse ``code`` via AST and persist one entry per top-level def.

    Returns newly-captured entries (may be empty if the code has no top-level
    defs, all defs are duplicates, or parsing failed). Never raises; capture
    failure must never break the calling op.
    """
    try:
        defs = _extract_top_level_defs(code)
        if not defs:
            return []

        path = get_skeleton_path()
        existing = _load_all(path)
        captured: List[SkeletonClosetEntry] = []
        captured_at = _now_iso()
        # Normalize entities once.
        entities_clean = [e for e in (entities_used or []) if e]

        with _WRITE_LOCK:
            # Re-read inside the lock would be safer if other writers exist;
            # for now the single-process MCP makes this acceptable.
            with path.open("a", encoding="utf-8") as fp:
                for node in defs:
                    source = _def_source(code, node)
                    if not source:
                        continue
                    if _is_duplicate(existing, node.name, source):
                        continue
                    entry: SkeletonClosetEntry = {
                        "name": node.name,
                        "source": source,
                        "entities": list(entities_clean),
                        "user_intent": user_intent,
                        "captured_at": captured_at,
                        "op_id": op_id,
                        "session_id": session_id,
                        "duration_ms": int(duration_ms),
                    }
                    fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    captured.append(entry)
                    # Track in-memory so multiple defs in the same op
                    # also dedupe against each other.
                    existing.append(entry)

        return captured
    except Exception:
        # Capture must never propagate -- the op already succeeded.
        return []


def find_skeletons(
    *,
    entity_names: Optional[List[str]] = None,
    intent_substring: Optional[str] = None,
    limit: int = 5,
) -> List[SkeletonClosetEntry]:
    """Retrieve persisted skeletons.

    Filters (all ANDed):
      - ``entity_names``: any-of match against the entry's ``entities`` list.
      - ``intent_substring``: case-insensitive substring of ``user_intent``.

    Most-recent-first within the filtered set (``captured_at`` desc).
    """
    path = get_skeleton_path()
    entries = _load_all(path)
    entity_set = {e for e in (entity_names or []) if e}
    intent_lc = intent_substring.lower() if intent_substring else None

    def _matches(entry: SkeletonClosetEntry) -> bool:
        if entity_set:
            entry_entities = set(entry.get("entities") or [])
            if not (entry_entities & entity_set):
                return False
        if intent_lc:
            intent = (entry.get("user_intent") or "").lower()
            if intent_lc not in intent:
                return False
        return True

    matched = [e for e in entries if _matches(e)]
    matched.sort(key=lambda e: e.get("captured_at", ""), reverse=True)
    return matched[:limit]


def list_all_skeletons(limit: int = 100) -> List[SkeletonClosetEntry]:
    """Return every persisted skeleton, most-recent-first, up to ``limit``."""
    entries = _load_all(get_skeleton_path())
    entries.sort(key=lambda e: e.get("captured_at", ""), reverse=True)
    return entries[:limit]
