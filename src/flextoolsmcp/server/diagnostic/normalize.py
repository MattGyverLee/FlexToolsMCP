#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Path-scoped machine-hygiene normalization (spec section 8.3 / decision E2,
NORMATIVE -- has a matching section 12 acceptance criterion).

Two automatic substitutions protect the *user's own machine identity*:
  1. home-dir absolute paths -> `~`
  2. the OS username removed from paths

Both operate ONLY on recognized path-shaped tokens. This is a HARD
REQUIREMENT (spec section 8, item 3): the implementation must NEVER perform
a document-wide find/replace of the username (or home-path) string across
the report body. A naive substring replace would corrupt lexical data
whenever a headword/gloss/example sentence happens to contain the OS
username as a substring -- e.g. OS user `matt` colliding with the gloss
"**Matt**hew's toolbox".

How this module stays safe by construction
-------------------------------------------
`normalize_report_text()` is safe to call on the WHOLE rendered report body
(not just hand-picked "safe" sections) because the substitution is anchored
on genuine path-shaped substrings, not a bare string search:

  1. `_PATH_TOKEN_RE` only matches things that already look like an absolute
     Windows path (`C:\\...`), a UNC path (`\\\\server\\...`), or a POSIX
     home-style path (`/home/...`, `/Users/...`, `/root/...`). A gloss like
     "Matthew's toolbox" never matches this regex at all -- it has no drive
     letter, no leading backslash pair, and isn't rooted under a recognized
     home directory -- so it is never even considered a candidate.
  2. Within a matched path token, the home-dir prefix is replaced with `~`
     only via a full-string prefix compare against the resolved
     `expanduser('~')` / `USERPROFILE` value -- not a substring search.
  3. The username substitution operates on whole PATH SEGMENTS (split on
     `\\` / `/`) and requires an exact (case-insensitive) segment match --
     not "contains". A segment "Matthew's" never equals the segment "matt",
     even inside a path token, so lexical collisions are protected twice
     over: once by the path-token regex not matching lexical prose at all,
     and again by whole-segment (not substring) comparison within any token
     that does match.

No I/O, no network -- pure string transforms. See the package docstring in
`flextoolsmcp.server.diagnostic.__init__` for the no-transmission guard this
module lives under.
"""

import os
import re
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Path-shaped token regex.
# ---------------------------------------------------------------------------
# - win:   drive-letter absolute path, e.g. C:\Users\matt\Documents\foo.py
# - unc:   UNC network path, e.g. \\server\share\matt\foo.py
# - posix: POSIX home-style path, deliberately restricted to /home, /Users,
#          /root roots (NOT a bare leading "/") so we never treat an
#          arbitrary "/" in prose or a URL fragment as a path token.
_PATH_TOKEN_RE = re.compile(
    r"(?P<win>[A-Za-z]:[\\/][^\s\"'<>|]*)"
    r"|(?P<unc>\\\\[^\s\"'<>|]+)"
    r"|(?P<posix>/(?:home|Users|root)/[^\s\"'<>|]*)"
)

_SEG_SPLIT_RE = re.compile(r"([\\/])")


def get_home_path() -> str:
    """Resolve the machine's home directory the same way §8.3 anchors on:
    `USERPROFILE` (Windows) if set, else `expanduser('~')`.
    """
    override = os.environ.get("USERPROFILE")
    if override:
        return override
    return os.path.expanduser("~")


def get_username() -> str:
    """Resolve the OS username. Prefers `USERNAME` (Windows) / `USER`
    (POSIX) env vars; falls back to the last path segment of the home dir.
    """
    for var in ("USERNAME", "USER"):
        val = os.environ.get(var)
        if val:
            return val
    home = get_home_path()
    return Path(home).name if home else ""


def _starts_with_ci(text: str, prefix: str) -> bool:
    if not prefix:
        return False
    return text[: len(prefix)].lower() == prefix.lower()


def _replace_username_segments(token: str, username: str) -> str:
    """Replace path SEGMENTS (never substrings) equal to `username`
    (case-insensitive) with the literal `<user>` placeholder.
    """
    if not username:
        return token
    parts = _SEG_SPLIT_RE.split(token)
    out = []
    for part in parts:
        if part in ("\\", "/"):
            out.append(part)
        elif part.lower() == username.lower():
            out.append("<user>")
        else:
            out.append(part)
    return "".join(out)


def _normalize_path_token(token: str, home_path: str, username: str) -> str:
    """Normalize a single already-matched path-shaped token."""
    if home_path and _starts_with_ci(token, home_path):
        remainder = token[len(home_path):]
        # Boundary check: the match must end exactly at a path-segment
        # boundary (separator or end-of-token). Without this, a home dir
        # "C:\Users\matt" would wrongly prefix-match an UNRELATED sibling
        # directory "C:\Users\matthew" (different user, same string prefix).
        if remainder == "" or remainder[0] in ("\\", "/"):
            token = "~" + remainder
    token = _replace_username_segments(token, username)
    return token


def normalize_report_text(
    text: str,
    *,
    home_path: Optional[str] = None,
    username: Optional[str] = None,
) -> str:
    """Apply path-scoped machine-hygiene normalization to `text` (spec
    section 8.3 / decision E2).

    Safe to call on an entire rendered report body (see module docstring for
    why): only genuine path-shaped substrings are ever touched, and within
    those, only the home-dir prefix and whole path segments equal to the
    username. Lexical content (headwords, glosses, definitions, prose) is
    never a document-wide find/replace target.

    `home_path` / `username` are injectable for testing; default to the
    resolved values from the current process environment.
    """
    if not text:
        return text

    resolved_home = home_path if home_path is not None else get_home_path()
    resolved_user = username if username is not None else get_username()

    def _sub(match: "re.Match") -> str:
        token = match.group(0)
        return _normalize_path_token(token, resolved_home, resolved_user)

    return _PATH_TOKEN_RE.sub(_sub, text)
