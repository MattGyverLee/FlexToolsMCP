#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`offered.json` persistence (spec section 6.4) -- dedupe/rate-limit state for
the diagnostic-report offer.

Schema (`~/.flextoolsmcp/reports/offered.json`):
    {
      "version": 1,
      "entries": {
        "<signature-hash>": {
          "state": "offered" | "declined" | "dont_ask_again",
          "error_code": "<code or exception class>",
          "first_seen": "<ISO-8601 UTC>",
          "last_seen": "<ISO-8601 UTC>",
          "offer_count": <int>
        }
      }
    }

Hard requirements (spec section 6.4 / section 12 acceptance criteria):
  - A corrupt/unparseable file is treated as EMPTY -- fail-open to "offer",
    NEVER crash the op path.
  - Entries are pruned LRU-by-`last_seen` to cap `entries` (default 500) so
    the file can't grow unbounded on long-lived installs.
  - `dont_ask_again` for a signature must persist across a restart (i.e.
    across a fresh process re-reading this file).

No I/O other than local file read/write under ~/.flextoolsmcp/reports/. No
network, no subprocess. See the package docstring in
`flextoolsmcp.server.diagnostic.__init__` for the no-transmission guard this
module lives under.
"""

import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

STORE_VERSION = 1
DEFAULT_ENTRY_CAP = 500

STATE_OFFERED = "offered"
STATE_DECLINED = "declined"
STATE_DONT_ASK_AGAIN = "dont_ask_again"

_VALID_STATES = frozenset({STATE_OFFERED, STATE_DECLINED, STATE_DONT_ASK_AGAIN})


def get_reports_dir() -> Path:
    """Return `~/.flextoolsmcp/reports/`, creating it if needed."""
    reports_dir = Path.home() / ".flextoolsmcp" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir


def default_store_path() -> Path:
    """Default location of offered.json. Injectable via `path_fn` on every
    function below so tests can point at a temp directory."""
    return get_reports_dir() / "offered.json"


def _empty_store() -> Dict[str, Any]:
    return {"version": STORE_VERSION, "entries": {}}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_store(path_fn: Callable[[], Path] = default_store_path) -> Dict[str, Any]:
    """Read offered.json. Fail-open to an empty store on ANY problem
    (missing file, unparseable JSON, wrong shape, OS error) -- this function
    must never raise.
    """
    try:
        path = path_fn()
    except Exception:
        return _empty_store()

    if not path.exists():
        return _empty_store()

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        # Corrupt / unparseable file -> treated as empty (fail-open).
        return _empty_store()

    if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
        # Unexpected shape -> also fail-open rather than propagate a
        # confusing KeyError/TypeError up into the op path.
        return _empty_store()

    data.setdefault("version", STORE_VERSION)
    return data


def save_store(
    store: Dict[str, Any],
    path_fn: Callable[[], Path] = default_store_path,
) -> None:
    """Write offered.json. Best-effort: never raises, so persistence never
    crashes the op path.

    `path_fn()` is guarded on its own (like `load_store()`'s equivalent
    step) because the default `path_fn` (`default_store_path` ->
    `get_reports_dir` -> `Path.home()`) can raise `RuntimeError` when the
    home directory can't be resolved -- that must fail open too, not just
    the narrower `OSError`s from the actual mkdir/open/write below.
    """
    try:
        path = path_fn()
    except Exception:
        return

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(store, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def prune(store: Dict[str, Any], cap: int = DEFAULT_ENTRY_CAP) -> Dict[str, Any]:
    """LRU-prune `store["entries"]` in place (by `last_seen`, oldest first)
    down to at most `cap` entries. Returns `store` for chaining.
    """
    entries = store.get("entries")
    if not isinstance(entries, dict) or len(entries) <= cap:
        return store

    ordered = sorted(entries.items(), key=lambda kv: kv[1].get("last_seen") or "")
    overflow = len(entries) - cap
    for signature, _ in ordered[:overflow]:
        entries.pop(signature, None)
    return store


def get_entry(
    signature: str,
    path_fn: Callable[[], Path] = default_store_path,
) -> Optional[Dict[str, Any]]:
    """Return the stored entry for `signature`, or None if absent (or on any
    load failure, which load_store() already turns into "absent")."""
    store = load_store(path_fn)
    return store.get("entries", {}).get(signature)


def should_offer(
    signature: str,
    path_fn: Callable[[], Path] = default_store_path,
) -> bool:
    """Section 6.3-6.4 dedupe decision for `signature`.

    Fail-open: any load problem is already normalized to "no entry" by
    `load_store()`, which means "never offered before" -> True.

    Only `dont_ask_again` permanently suppresses the offer. `offered` and
    `declined` do not block re-offering here -- `declined` is documented as
    "suppressed for the session" (an ephemeral, in-memory concern outside
    this on-disk store's job) and `offered` alone (not yet acted on) may
    re-surface per spec section 6.4.
    """
    entry = get_entry(signature, path_fn)
    if entry is None:
        return True
    return entry.get("state") != STATE_DONT_ASK_AGAIN


def record_offer(
    signature: str,
    error_code: str,
    *,
    path_fn: Callable[[], Path] = default_store_path,
    cap: int = DEFAULT_ENTRY_CAP,
) -> Dict[str, Any]:
    """Upsert an "offered" touch for `signature`: creates the entry (state
    "offered", offer_count 1) on first sight, or bumps `offer_count` /
    `last_seen` on a repeat -- WITHOUT downgrading an existing
    `dont_ask_again` / `declined` state (an offer touch should not silently
    un-suppress a signature the user already dismissed permanently).

    Persists to disk (best-effort) and returns the resulting entry dict.
    """
    store = load_store(path_fn)
    entries = store.setdefault("entries", {})
    now = _now_iso()

    entry = entries.get(signature)
    if entry is None:
        entry = {
            "state": STATE_OFFERED,
            "error_code": error_code,
            "first_seen": now,
            "last_seen": now,
            "offer_count": 1,
        }
        entries[signature] = entry
    else:
        entry["error_code"] = error_code or entry.get("error_code", "")
        entry["last_seen"] = now
        entry["offer_count"] = int(entry.get("offer_count", 0)) + 1

    prune(store, cap=cap)
    save_store(store, path_fn)
    return entry


def record_decision(
    signature: str,
    decision: str,
    *,
    path_fn: Callable[[], Path] = default_store_path,
    cap: int = DEFAULT_ENTRY_CAP,
) -> Dict[str, Any]:
    """Record the user's decision for `signature`: "offered" (re-surfaced,
    no decision yet), "declined" ("not now"), or "dont_ask_again"
    (permanent). Creates the entry if it doesn't exist yet (defensive --
    normal flow always calls `record_offer()` first).
    """
    if decision not in _VALID_STATES:
        raise ValueError(f"invalid offered.json state: {decision!r}")

    store = load_store(path_fn)
    entries = store.setdefault("entries", {})
    now = _now_iso()

    entry = entries.get(signature)
    if entry is None:
        entry = {
            "state": decision,
            "error_code": "",
            "first_seen": now,
            "last_seen": now,
            "offer_count": 0,
        }
        entries[signature] = entry
    else:
        entry["state"] = decision
        entry["last_seen"] = now

    prune(store, cap=cap)
    save_store(store, path_fn)
    return entry
