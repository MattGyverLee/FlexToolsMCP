#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Workspace sanity check: warn when the session's working directory is a source
checkout of FlexToolsMCP (or of one of the FLEx libraries this MCP documents).

Why this exists
---------------
Users who found this project on GitHub tend to ``git clone`` it and then open
that clone as their Claude Code / Copilot workspace. That is the wrong place to
do FLEx work, and it degrades the assistant in a specific, repeatable way:
instead of calling the ``flextools_*`` tools, the assistant starts *reading the
repository* -- grepping ``index/*.json``, opening the bundled templates, walking
``specs/``, and (worst case) parsing LCM model XML or a project's ``.fwdata``
directly rather than going through the API. The indexed answers are already
available as tool calls; reading source produces slower, less accurate, and
sometimes flatly wrong scripts.

Installing from PyPI makes this less likely but does not prevent it -- the
checkout can still be the *working directory* even when the running code comes
from ``site-packages`` or a ``uvx`` cache. So we detect it at runtime from the
server process's cwd.

Design constraints (mirrors ``update_check.py``)
-----------------------------------------------
  - Cheap: a bounded walk up from cwd doing ``Path.exists()`` probes. No file
    reads, no network, no imports of anything heavy. Safe on the hot path.
  - Fail-open on ANY problem (unresolvable cwd, permission error, weird FS):
    return no notice, never raise into a tool response.
  - ``FLEXTOOLSMCP_NO_WORKSPACE_CHECK=1`` fully disables the feature (this is
    the escape hatch for maintainers who legitimately work *in* the repo).
  - Kept dependency-free so both ``response_utils`` and the handler package can
    import it without risking an import cycle.

cwd caveat: an MCP server launched over stdio inherits the client's working
directory, which is the folder the user opened. That is what makes cwd a usable
proxy for "the workspace". A client that launches the server from somewhere else
simply means the check does not fire -- fail-open, by design.
"""

import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

_ENV_OPT_OUT = "FLEXTOOLSMCP_NO_WORKSPACE_CHECK"

# How many parent directories above cwd to probe. Covers "I opened a subfolder
# of the clone" (e.g. .../FlexToolsMCP/src/flextoolsmcp) without turning into an
# unbounded walk to the filesystem root.
MAX_ANCESTOR_DEPTH = 6

# Repo fingerprints. A directory matches a signature when EVERY relative path
# in ``markers`` exists under it -- two markers per repo so an ordinary user
# folder that happens to contain e.g. a ``flexicon/`` subdirectory does not trip
# the check. Best-effort and purely additive: a marker that stops matching means
# the warning silently stops firing for that repo, which is the safe direction.
_REPO_SIGNATURES: Tuple[Dict[str, Any], ...] = (
    {
        "key": "flextools-mcp",
        "display": "FlexToolsMCP",
        "markers": ("pyproject.toml", "src/flextoolsmcp/__init__.py"),
        "risk": (
            "the assistant tends to grep the bundled API index, templates, and "
            "specs/ instead of calling the flextools_* tools that serve the same "
            "data already parsed"
        ),
    },
    {
        "key": "liblcm",
        "display": "LibLCM (the C# data model)",
        "markers": ("LCM.sln", "src"),
        "risk": (
            "the assistant tends to read the LCM model XML and C# sources "
            "directly instead of using the indexed API -- the single worst "
            "failure mode, because hand-parsed XML bypasses every LCM invariant"
        ),
    },
    {
        "key": "flexicon",
        "display": "Flexicon (the deep Python wrapper)",
        "markers": ("pyproject.toml", "flexicon/__init__.py"),
        "risk": (
            "the assistant tends to read wrapper source instead of calling "
            "flextools_get_object_api, and then writes scripts against "
            "unreleased or internal functions"
        ),
    },
    {
        "key": "flexlibs",
        "display": "FlexLibs (the stable shallow wrapper)",
        "markers": ("setup.cfg", "flexlibs/__init__.py"),
        "risk": (
            "the assistant tends to read wrapper source instead of calling "
            "flextools_get_object_api, and then mixes stable-FlexLibs idioms "
            "into Flexicon scripts"
        ),
    },
    {
        "key": "flextools",
        "display": "FLExTools (the GUI runner)",
        "markers": ("flextoolslib/__init__.py", "FlexTools"),
        "risk": (
            "the assistant tends to read the runner's internals instead of "
            "using flextools_get_module_template and flextools_run_module"
        ),
    },
    {
        "key": "fieldworks",
        "display": "FieldWorks (the application)",
        "markers": ("FieldWorks.sln", "Src"),
        "risk": (
            "the assistant tends to explore application C# source instead of "
            "using the indexed API"
        ),
    },
)

# Once-per-process guard for the envelope-attached copy of the notice.
_notice_emitted = False
_lock = threading.Lock()


def opted_out() -> bool:
    """True when the user disabled the workspace check via the env var.

    Any non-empty value other than "0"/"false"/"no" (case-insensitive) counts as
    opting out, so ``=1`` / ``=true`` / ``=yes`` all work. Matches
    ``update_check.opted_out()`` so the two opt-outs behave identically.
    """
    val = os.environ.get(_ENV_OPT_OUT, "").strip().lower()
    return val not in ("", "0", "false", "no")


def _matches(directory: Path, signature: Dict[str, Any]) -> bool:
    """True when every marker of ``signature`` exists under ``directory``."""
    try:
        return all((directory / rel).exists() for rel in signature["markers"])
    except OSError:
        # Unreadable / disconnected path -- treat as "not a match".
        return False


def detect_source_checkout(
    *,
    cwd_fn: Callable[[], Path] = Path.cwd,
) -> Optional[Dict[str, Any]]:
    """Identify the repo checkout containing cwd, if any.

    Walks cwd and up to ``MAX_ANCESTOR_DEPTH`` ancestors, returning the first
    directory that fingerprints as one of ``_REPO_SIGNATURES``. Nearest match
    wins, so a nested checkout reports the inner repo.

    Returns a dict with ``key``, ``display``, ``risk``, ``repo_root``, ``cwd``,
    and ``running_from_this_checkout``; None when cwd is not inside a known
    checkout (the healthy, common case). Never raises.
    """
    try:
        cwd = Path(cwd_fn()).resolve()
    except Exception:
        return None

    candidates = [cwd, *list(cwd.parents)[:MAX_ANCESTOR_DEPTH]]
    for directory in candidates:
        for signature in _REPO_SIGNATURES:
            if not _matches(directory, signature):
                continue
            return {
                "key": signature["key"],
                "display": signature["display"],
                "risk": signature["risk"],
                "repo_root": str(directory),
                "cwd": str(cwd),
                "running_from_this_checkout": _running_from(directory),
            }
    return None


def _running_from(repo_root: Path) -> bool:
    """True when the executing ``flextoolsmcp`` code lives inside ``repo_root``.

    Distinguishes a maintainer running a source/editable install in its own repo
    (expected; they want the env opt-out) from a user who cloned the repo for
    reference while the server runs from PyPI (the case this check is for).
    Never raises.
    """
    try:
        return repo_root in Path(__file__).resolve().parents
    except Exception:
        return False


def build_notice(checkout: Dict[str, Any]) -> Dict[str, Any]:
    """Construct the ``workspace_notice`` payload for a detected checkout."""
    display = checkout["display"]
    suggested = Path.home() / "flex-scripts"

    if checkout["running_from_this_checkout"]:
        provenance = (
            f"This is also the copy of the server that is running (source or "
            f"editable install). That is normal for maintainers of {display}; "
            f"if that is you, set {_ENV_OPT_OUT}=1 to silence this notice."
        )
    else:
        provenance = (
            "The server itself is running from an installed package, not from "
            "this checkout -- so nothing here is needed to use the MCP. The "
            "clone is only shaping where the assistant looks."
        )

    message = (
        f"Working directory is inside a {display} source checkout "
        f"({checkout['repo_root']}). This is not a good place to write FLEx "
        f"scripts: {checkout['risk']}. {provenance}\n\n"
        f"Recommended: open an empty folder for this work instead -- e.g. "
        f"`mkdir \"{suggested}\"` then reopen the assistant there. Your scripts "
        f"live in your folder; the MCP keeps serving the API from wherever it "
        f"is installed."
    )

    return {
        "detected_repo": checkout["key"],
        "repo_root": checkout["repo_root"],
        "cwd": checkout["cwd"],
        "running_from_this_checkout": checkout["running_from_this_checkout"],
        "message": message,
        "suggested_workspace": str(suggested),
        "assistant_directive": [
            "Do NOT answer FLEx API questions by reading, grepping, or globbing "
            "files in this checkout. Use flextools_search_by_capability, "
            "flextools_get_object_api, flextools_resolve_property, and "
            "flextools_find_examples -- they serve the same data, already parsed.",
            "Do NOT parse LCM model XML, .fwdata, or C#/Python library source to "
            "infer behaviour. Query the API index, and run code through "
            "flextools_run_module.",
            "Do NOT hand-copy a template out of the repo. Call "
            "flextools_get_module_template(flavor='flexicon').",
            "Relay this notice to the user and offer to move to an empty folder "
            "before continuing.",
        ],
        "opt_out_env_var": _ENV_OPT_OUT,
    }


def warning_line(notice: Dict[str, Any]) -> str:
    """One-line form of the notice, for ``warnings`` lists in tool payloads."""
    return (
        f"WORKSPACE: cwd is inside the {notice['detected_repo']} source checkout "
        f"({notice['repo_root']}). Use the flextools_* tools rather than reading "
        f"this repo, and prefer an empty working folder "
        f"(e.g. {notice['suggested_workspace']}). See workspace_notice; silence "
        f"with {notice['opt_out_env_var']}=1."
    )


def get_workspace_notice(
    *,
    once: bool = False,
    cwd_fn: Callable[[], Path] = Path.cwd,
) -> Optional[Dict[str, Any]]:
    """Return the workspace-notice payload, or None when the workspace is fine.

    Args:
        once: When True, emit at most once per process. Used by the response
            envelope, which would otherwise repeat the notice on every single
            tool call. Call sites that *should* always report -- session start
            and ``flextools_health`` -- pass False.
        cwd_fn: Injectable working-directory resolver (tests).

    Never raises: a notice must never be the reason a tool response fails.
    """
    global _notice_emitted
    try:
        if opted_out():
            return None

        checkout = detect_source_checkout(cwd_fn=cwd_fn)
        if checkout is None:
            return None

        if once:
            with _lock:
                if _notice_emitted:
                    return None
                _notice_emitted = True

        return build_notice(checkout)
    except Exception:
        # Absolute backstop, matching update_check.get_update_notice().
        return None
