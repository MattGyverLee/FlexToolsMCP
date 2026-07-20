#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Proactive update notice (issue #79).

Tells users when a newer ``flextools-mcp`` release is on PyPI. Neither ``uvx``,
``uv tool``, nor ``pip`` proactively notifies, so users get silently stuck on an
old build (a stale ``uvx`` cache served a pre-2.6.2 build with Flexicon 4.1.2
even though 2.6.2 was published). The notice rides out on the tool-response
envelope (see ``response_utils.build_response_with_context``) so the assistant
relays it -- the only channel a non-programmer FLEx user reliably sees.

Design constraints (issue #79 acceptance criteria):
  - The tool-call hot path NEVER performs a network call. It only reads a cached
    result from ``~/.flextoolsmcp/update-check.json``. A guarded daemon thread
    does the actual PyPI fetch in the background.
  - Cached ~24h; the network is hit at most once per TTL.
  - Fail-open on ANY problem (offline, timeout, malformed response, corrupt
    cache, unresolvable home) -- return no notice, never raise into the op path.
    Mirrors the fail-open discipline of ``diagnostic/offered_store.py``.
  - ``FLEXTOOLSMCP_NO_UPDATE_CHECK=1`` fully disables the feature.
  - Source/dev installs (``__version__ == "0.0.0.dev0"``) are skipped.
  - The notice is emitted at most once per process.
"""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

DIST_NAME = "flextools-mcp"
PYPI_JSON_URL = f"https://pypi.org/pypi/{DIST_NAME}/json"

# Network check at most once per this many seconds (24h).
CACHE_TTL_SECONDS = 24 * 60 * 60
# Hard cap on the PyPI request so a hung endpoint never lingers on the daemon
# thread. The hot path never waits on this regardless.
FETCH_TIMEOUT_SECONDS = 3.0

# Sentinel version from __init__.py when running from a source checkout with no
# installed distribution metadata. We can't meaningfully compare it to PyPI.
_DEV_VERSION = "0.0.0.dev0"

_ENV_OPT_OUT = "FLEXTOOLSMCP_NO_UPDATE_CHECK"

# Once-per-process guards.
_notice_emitted = False
_refresh_started = False
_lock = threading.Lock()


def opted_out() -> bool:
    """True when the user disabled update checks via the opt-out env var.

    Any non-empty value other than "0"/"false"/"no" (case-insensitive) counts
    as opting out, so ``=1`` / ``=true`` / ``=yes`` all work.
    """
    val = os.environ.get(_ENV_OPT_OUT, "").strip().lower()
    return val not in ("", "0", "false", "no")


def get_installed_version() -> Optional[str]:
    """Installed ``flextools-mcp`` version, or None if it can't be determined
    or is the source-checkout dev sentinel (which we don't compare)."""
    try:
        from importlib.metadata import version as _version

        v = _version(DIST_NAME)
    except Exception:
        return None
    if not v or v == _DEV_VERSION:
        return None
    return v


def _cache_path() -> Path:
    """``~/.flextoolsmcp/update-check.json``. May raise if home is unresolvable;
    every caller guards this."""
    return Path.home() / ".flextoolsmcp" / "update-check.json"


def _load_cache(path_fn: Callable[[], Path] = _cache_path) -> Dict[str, Any]:
    """Read the cache file. Fail-open to an empty dict on ANY problem -- never
    raises."""
    try:
        path = path_fn()
    except Exception:
        return {}
    try:
        if not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_cache(data: Dict[str, Any], path_fn: Callable[[], Path] = _cache_path) -> None:
    """Best-effort write. Never raises."""
    try:
        path = path_fn()
    except Exception:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _is_newer(latest: str, installed: str) -> bool:
    """True if ``latest`` is a strictly newer release than ``installed``.

    Prefers ``packaging.version`` (PEP 440 aware); falls back to a naive
    dotted-integer compare if packaging isn't importable. On any parse problem,
    returns False (fail-closed on the *comparison* so we never nag with a bogus
    'update available')."""
    try:
        from packaging.version import InvalidVersion, Version

        try:
            return Version(latest) > Version(installed)
        except InvalidVersion:
            return False
    except Exception:
        pass

    def _parts(v: str):
        out = []
        for chunk in v.split("."):
            num = "".join(ch for ch in chunk if ch.isdigit())
            out.append(int(num) if num else 0)
        return out

    try:
        return _parts(latest) > _parts(installed)
    except Exception:
        return False


def _fetch_latest(timeout: float = FETCH_TIMEOUT_SECONDS) -> Optional[str]:
    """Fetch the latest version string from PyPI. Fail-open to None on ANY
    problem (offline, timeout, non-200, malformed JSON)."""
    try:
        import httpx

        resp = httpx.get(
            PYPI_JSON_URL,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        info = resp.json().get("info", {})
        latest = info.get("version")
        return latest if isinstance(latest, str) and latest else None
    except Exception:
        return None


def _cache_is_fresh(cache: Dict[str, Any], now: float) -> bool:
    ts = cache.get("last_checked_epoch")
    if not isinstance(ts, (int, float)):
        return False
    return (now - ts) < CACHE_TTL_SECONDS


def refresh_cache(
    *,
    force: bool = False,
    path_fn: Callable[[], Path] = _cache_path,
    fetch_fn: Callable[[], Optional[str]] = _fetch_latest,
    now_fn: Callable[[], float] = time.time,
) -> Optional[str]:
    """Refresh the cached 'latest' version from PyPI if the cache is stale.

    Returns the latest version now known (from a fresh fetch or the still-fresh
    cache), or None. Never raises. This is what the daemon thread runs; it is
    also directly unit-testable via the injected fns.
    """
    if opted_out():
        return None
    now = now_fn()
    cache = _load_cache(path_fn)
    if not force and _cache_is_fresh(cache, now):
        latest = cache.get("latest")
        return latest if isinstance(latest, str) else None

    latest = fetch_fn()
    # Always stamp the check time so a transient outage doesn't cause a fetch on
    # every single call for the next 24h; retain the last known 'latest' if the
    # fetch failed.
    new_cache = {
        "last_checked_epoch": now,
        "last_checked_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "latest": latest if latest is not None else cache.get("latest"),
    }
    _save_cache(new_cache, path_fn)
    return new_cache["latest"] if isinstance(new_cache["latest"], str) else None


def ensure_background_refresh(
    *,
    path_fn: Callable[[], Path] = _cache_path,
) -> None:
    """Kick off a single guarded daemon thread that refreshes the cache if
    stale. Idempotent per process; returns immediately. No-op when opted out.

    Called from the (already fast) response path so the feature is entirely
    self-contained -- no server-startup wiring required. The thread's fetch
    never blocks the caller.
    """
    global _refresh_started
    if opted_out():
        return
    with _lock:
        if _refresh_started:
            return
        _refresh_started = True

    def _run() -> None:
        try:
            refresh_cache(path_fn=path_fn)
        except Exception:
            pass

    try:
        threading.Thread(
            target=_run, name="flextoolsmcp-update-check", daemon=True
        ).start()
    except Exception:
        # If a thread can't be spawned, silently skip -- update notice is a
        # nicety, never a requirement.
        pass


def build_notice(installed: str, latest: str) -> Dict[str, Any]:
    """Construct the ``update_notice`` envelope payload."""
    return {
        "installed": installed,
        "latest": latest,
        "update_available": True,
        "message": (
            f"A newer FlexToolsMCP ({latest}) is available; you are on "
            f"{installed}. Upgrading also pulls the latest compatible Flexicon."
        ),
        "upgrade_commands": {
            "uvx": f"uvx {DIST_NAME}@latest",
            "uv_tool": f"uv tool upgrade {DIST_NAME}",
            "pip": f"pip install -U {DIST_NAME}",
        },
    }


def get_update_notice(
    *,
    path_fn: Callable[[], Path] = _cache_path,
) -> Optional[Dict[str, Any]]:
    """Return the update-notice payload if a newer release is known, else None.

    HOT PATH: reads only the local cache -- never hits the network. Kicks off
    the background refresh (guarded, once per process) so the cache is populated
    for subsequent calls this session. Emits the notice at most once per
    process. Never raises.
    """
    global _notice_emitted
    try:
        if opted_out():
            return None

        installed = get_installed_version()
        if installed is None:
            return None

        # Populate/refresh cache in the background for later calls; does not
        # block and does not affect this call's cache read below.
        ensure_background_refresh(path_fn=path_fn)

        cache = _load_cache(path_fn)
        latest = cache.get("latest")
        if not isinstance(latest, str) or not latest:
            return None
        if not _is_newer(latest, installed):
            return None

        with _lock:
            if _notice_emitted:
                return None
            _notice_emitted = True

        return build_notice(installed, latest)
    except Exception:
        # Absolute backstop: a notice must never break a tool response.
        return None
