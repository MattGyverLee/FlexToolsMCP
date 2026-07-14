#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Transport STRING building (spec section 9) -- CP3.

This module builds three transport artifacts as PLAIN STRINGS/argv-lists.
It NEVER invokes any of them: no `subprocess`, no `gh`, no browser, no
`smtplib`, no HTTP client, no raw socket. Building a string that CONTAINS
the word "gh" or "mailto:" is fine; this module never reaches for anything
that would actually send/open/execute it. See the package docstring in
`flextoolsmcp.server.diagnostic.__init__` for the no-transmission guard
this module lives under (statically AND dynamically enforced --
`tests/test_diagnostic_no_transmission.py`).

Three outcomes (spec section 9, user's choice, MCP never chooses):
  1. GitHub issue via `gh` CLI       -> exact argv list + display string.
  2. GitHub issue via prefilled URL  -> percent-encoded URL, body <= 8 KB.
  3. Email via `mailto:`             -> percent-encoded mailto: URI.

"gh available" is an INJECTABLE check (`gh_available_fn`) so CI can
exercise both the gh-present and gh-absent branches without a real
authenticated `gh` binary (spec section 12, decision E6). The default
implementation (`default_gh_available`) only checks whether an executable
named `gh` exists on PATH via `shutil.which` -- this is a filesystem/PATH
lookup, NOT a process invocation, so it does not violate the no-
transmission guard (`shutil` is not on the banned-imports list; nothing
here spawns `gh` or asks it to authenticate/run anything).
"""

import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

# Path-scoped machine-hygiene normalization (spec section 8.3 / E2). Pure
# string transforms, no I/O -- importing it keeps this module inside the
# no-transmission guard. Used to strip the OS username / home path out of the
# report_path embedded in the URL/mailto short bodies (CP3 carryover P2,
# domain gate): these were the one transport string not run through
# normalize_report_text(), so the user's local path (with their OS username)
# leaked into the prefilled GitHub-URL and mailto: bodies.
try:
    from . import normalize
except ImportError:  # pragma: no cover - script/relative-import fallback
    from server.diagnostic import normalize

DEFAULT_REPO = "MattGyverLee/FlexToolsMCP"
DEFAULT_EMAIL = "matthew_lee@sil.org"
DEFAULT_LABEL = "auto-report"

# Spec section 9/12: the prefilled-URL body is length-capped to ~8 KB.
# We cap the total constructed URL (not just the raw pre-encoded text) so
# the acceptance criterion ("its body is <= 8 KB") holds after percent-
# encoding, which can expand non-ASCII/space-heavy text up to ~3x.
MAX_URL_TOTAL_BYTES = 8 * 1024
MAX_MAILTO_TOTAL_BYTES = 8 * 1024

GITHUB_NEW_ISSUE_BASE = "https://github.com/{repo}/issues/new"


def default_gh_available() -> bool:
    """Injectable "is the gh CLI present" check.

    Only checks PATH via `shutil.which` -- never invokes `gh` (no
    `subprocess`, no `gh auth status`). Callers who want the stronger
    "gh is authenticated" check must inject their own callable; this
    default answers only "is a `gh` executable installed", which is enough
    to decide whether to PREFER the `gh` command over the URL fallback when
    presenting the three outcomes to the user.
    """
    return shutil.which("gh") is not None


TRUNC_SUFFIX = "\n... [truncated]"


def _quote_argv(arg: str) -> str:
    """POSIX-shell display quoting for the human-readable `display` string
    ONLY. The `argv` list is the authoritative, unquoted argument vector --
    this string is cosmetic, for showing the user the equivalent command line.

    Caveat (CP3 carryover P2): this uses POSIX double-quote escaping. On a
    Windows `cmd.exe` prompt the escaping rules differ (`^` metacharacters,
    no `\\"` escape inside double quotes), so the `display` string is a
    readable approximation, not a guaranteed copy-paste-safe Windows command
    line. Anyone actually executing the report transport should use the
    `argv` list (passed to the process without a shell), never re-parse
    `display`. `display` exists only to show the user roughly what would run.
    """
    if arg == "":
        return '""'
    if any(c in arg for c in (" ", "\t", '"', "'")):
        escaped = arg.replace('"', '\\"')
        return f'"{escaped}"'
    return arg


def build_gh_command(
    title: str,
    report_path: "Path | str",
    *,
    repo: str = DEFAULT_REPO,
    label: str = DEFAULT_LABEL,
) -> Dict[str, Any]:
    """Build the exact `gh issue create` argv shape (spec section 9/12):

        gh issue create --repo <repo> --title "<title>" \\
            --body-file <report_path> --label <label>

    Returns {"argv": [...], "display": "<shell-quoted string>"}. Building
    this dict never runs `gh` -- it is pure string/list construction.
    """
    argv: List[str] = [
        "gh", "issue", "create",
        "--repo", repo,
        "--title", title,
        "--body-file", str(report_path),
        "--label", label,
    ]
    display = " ".join(_quote_argv(a) for a in argv)
    return {"argv": argv, "display": display}


def _short_body_text(summary: str, report_path: "Path | str") -> str:
    """Shared short-body text for the URL and mailto transports (spec
    section 9): a short human summary plus an explicit instruction to
    attach/paste the full local report file, since the URL/mailto body is
    NOT the full-fidelity payload (only `gh --body-file` carries the whole
    file).

    The assembled body is run through `normalize.normalize_report_text()`
    (spec section 8.3 / E2) before it is returned. This matters for the
    embedded `report_path`: it is an absolute local path under the user's
    home dir (e.g. `C:\\Users\\<name>\\.flextoolsmcp\\reports\\report_*.md`),
    which would otherwise carry the user's OS username into the GitHub-URL /
    mailto short body -- the one transport string that used to skip
    normalization (CP3 carryover P2, domain gate). Normalization is
    path-scoped (home dir -> `~`, username segment -> `<user>`), so the
    human summary text is untouched.
    """
    body = (
        f"{summary}\n\n"
        f"Full details (full fidelity) are in the local report file:\n"
        f"{report_path}\n\n"
        f"Please attach or paste that file's contents into this report."
    )
    return normalize.normalize_report_text(body)


def _shrink_body_to_fit(
    build_fn: Callable[[str], str],
    body_text: str,
    max_total_bytes: int,
) -> "tuple[str, str]":
    """Shrink `body_text` (in the PRE-encoding domain) in ~20% byte-budget
    steps until `build_fn(body_text)` fits within `max_total_bytes` after
    percent-encoding, then return `(built_string, final_body_text)`.

    Shared by the GitHub-URL and mailto transports (CP3 carryover P2, DRY:
    the two builders previously carried byte-for-byte identical shrink
    loops). Percent-encoding only ever expands text, so cutting the
    pre-encoded body reliably shrinks the encoded result.

    Structural size invariant (CP3 carryover P2): the loop only ever shrinks
    the BODY, never the title/labels/fixed prefix baked into `build_fn`. That
    is sound because those are bounded upstream well under `max_total_bytes`
    -- the title is capped at 200 chars by `_build_title()`, the label is a
    short constant, and the base URL/mailto prefix is fixed -- so an
    empty-body build always fits. The `if cut_to <= 0: break` guard is the
    belt-and-suspenders backstop against a pathologically tiny
    `max_total_bytes`: it guarantees termination rather than a valid result
    in that (non-production) case.
    """
    built = build_fn(body_text)
    while len(built.encode("utf-8", errors="replace")) > max_total_bytes and body_text:
        # Cut the raw (pre-encoding) text -- percent-encoding only expands,
        # so shrinking pre-encoding text reliably shrinks the encoded output.
        cut_to = max(0, int(len(body_text) * 0.8))
        if cut_to >= len(body_text):
            cut_to = len(body_text) - 1
        body_text = body_text[:cut_to] + TRUNC_SUFFIX
        built = build_fn(body_text)
        if cut_to <= 0:
            break
    return built, body_text


def build_github_issue_url(
    title: str,
    summary: str,
    report_path: "Path | str",
    *,
    repo: str = DEFAULT_REPO,
    label: str = DEFAULT_LABEL,
    max_total_bytes: int = MAX_URL_TOTAL_BYTES,
) -> Dict[str, Any]:
    """Build the prefilled GitHub "new issue" URL (spec section 9/12):

        https://github.com/<repo>/issues/new?title=<enc>&labels=<enc>&body=<enc>

    The body is a SHORT summary (never the full report) -- the URL is
    length-capped to `max_total_bytes` total after percent-encoding, per
    the "~8 KB" cap in spec section 9/12. Truncation shrinks the body text
    (never the title/labels) until the encoded URL fits.
    """
    base = GITHUB_NEW_ISSUE_BASE.format(repo=repo)
    body_text = _short_body_text(summary, report_path)

    def _build(body: str) -> str:
        params = (
            f"title={quote(title, safe='')}"
            f"&labels={quote(label, safe='')}"
            f"&body={quote(body, safe='')}"
        )
        return f"{base}?{params}"

    url, body_text = _shrink_body_to_fit(_build, body_text, max_total_bytes)

    return {
        "url": url,
        "body_text": body_text,
        "body_bytes": len(body_text.encode("utf-8", errors="replace")),
        "url_bytes": len(url.encode("utf-8", errors="replace")),
    }


def build_mailto(
    title: str,
    summary: str,
    report_path: "Path | str",
    *,
    email: str = DEFAULT_EMAIL,
    max_total_bytes: int = MAX_MAILTO_TOTAL_BYTES,
) -> Dict[str, Any]:
    """Build the `mailto:` URI (spec section 9): private channel, short
    body, full-fidelity payload is the local report file the user attaches.
    """
    body_text = _short_body_text(summary, report_path)

    def _build(body: str) -> str:
        return (
            f"mailto:{email}?subject={quote(title, safe='')}"
            f"&body={quote(body, safe='')}"
        )

    uri, body_text = _shrink_body_to_fit(_build, body_text, max_total_bytes)

    return {
        "uri": uri,
        "body_text": body_text,
        "body_bytes": len(body_text.encode("utf-8", errors="replace")),
    }


def build_transports(
    *,
    title: str,
    summary: str,
    report_path: "Path | str",
    repo: Optional[str] = None,
    email: Optional[str] = None,
    label: str = DEFAULT_LABEL,
    gh_available_fn: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """Build all three transport artifacts (spec section 9/10).

    Always builds all three -- the `gh` argv/display is built regardless of
    whether `gh` is actually installed (it's just string construction); the
    `gh_available` flag tells the caller/Claude whether to PRESENT the `gh`
    option or fall back to the URL. Never invokes anything.
    """
    resolved_repo = repo or DEFAULT_REPO
    resolved_email = email or DEFAULT_EMAIL
    check = gh_available_fn or default_gh_available
    gh_present = bool(check())

    return {
        "gh_available": gh_present,
        "gh": build_gh_command(title, report_path, repo=resolved_repo, label=label),
        "github_url": build_github_issue_url(
            title, summary, report_path, repo=resolved_repo, label=label,
        ),
        "mailto": build_mailto(title, summary, report_path, email=resolved_email),
    }
