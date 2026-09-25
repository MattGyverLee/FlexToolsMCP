#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The seam to the packaged `hcparse.ps1` (parser-check CP5, contracts/hcparse.md,
research R-01, R-12, FR-022, FR-024).

The script is the mechanism for Generate mode -- its one remaining mode since
the CP5 re-plan moved Parse and Test into the parse worker's `--sandbox`
mode (contracts/sandbox-worker.md). This module is how Python finds it,
knows its version, builds its command line, and reads what it left behind:

  script_path()          the packaged script, next to this package (the
                         `file_utils.get_bundled_templates_dir` convention:
                         resolve from `__file__`, never a repo-root walk)
  read_hcparse_version() `$script:HCPARSE_VERSION`, the one source of truth
                         for the version that enters every cache key (R-12)
  build_argv()           an argv LIST, never a command string (FR-022)
  load_run_json()        a tolerant reader: a missing, empty, truncated or
                         non-object file is None, because a killed script
                         never reaches `finally` (R-06)
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

__all__ = [
    "VERSION_RE",
    "ARGV_PREFIX",
    "RUN_JSON",
    "MODES",
    "HcparseVersionError",
    "script_path",
    "read_hcparse_version",
    "build_argv",
    "load_run_json",
]

#: Pinned by contracts/hcparse.md section 2 and research R-12.
VERSION_RE = re.compile(r"^\$script:HCPARSE_VERSION\s*=\s*'([^']+)'", re.MULTILINE)

#: FR-022: the invocation prefix, before `str(script_path())`.
ARGV_PREFIX = ("powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File")

RUN_JSON = "run.json"
#: Parse and Test are retired (the script refuses them with exit 2).
MODES = ("Generate",)


class HcparseVersionError(RuntimeError):
    """The packaged script does not declare exactly one HCPARSE_VERSION."""


def script_path() -> Path:
    """The packaged `flextoolsmcp/scripts/hcparse.ps1`."""
    return (Path(__file__).resolve().parent.parent.parent / "scripts" / "hcparse.ps1")


def _parse_version(text: str) -> str:
    matches = VERSION_RE.findall(text)
    if len(matches) != 1:
        raise HcparseVersionError(
            f"hcparse.ps1 must declare $script:HCPARSE_VERSION exactly once; "
            f"found {len(matches)} declaration(s)"
        )
    return matches[0]


@functools.lru_cache(maxsize=1)
def read_hcparse_version() -> str:
    """The script's `$script:HCPARSE_VERSION`, read once and cached."""
    try:
        text = script_path().read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise HcparseVersionError(f"Cannot read {script_path()}: {exc}") from exc
    return _parse_version(text)


def _param_name(key: str) -> str:
    # Accept either the script's own spelling (`FwData`) or a leading dash.
    name = key[1:] if key.startswith("-") else key
    if not name or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", name):
        raise ValueError(f"Invalid hcparse parameter name {key!r}")
    return name


def build_argv(mode: str, **params: Any) -> List[str]:
    """The script's argv as a list: the FR-022 prefix, the script, then
    `-Mode <mode>` and one `-Name value` pair per parameter, in the order
    given. `None` values are omitted; `Path`s and numbers are `str()`-ed.

    Parameter names are the script's (`FwData`, `RunDir`,
    `GenerateTimeoutSeconds`, ...). Values are never quoted or joined: each
    is one argv element.
    """
    if mode not in MODES:
        raise ValueError(f"Unknown hcparse mode {mode!r}; expected one of {MODES}")
    argv: List[str] = [*ARGV_PREFIX, str(script_path()), "-Mode", mode]
    for key, value in params.items():
        name = _param_name(key)
        if name == "Mode":
            raise ValueError("Pass the mode positionally, not as a parameter")
        if value is None:
            continue
        if isinstance(value, bool):
            raise ValueError(f"hcparse parameter {name} takes a value, not a bool")
        argv.extend([f"-{name}", str(value)])
    return argv


def _load_json_object(path: Path) -> Optional[Dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not raw.strip():
        return None
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_run_json(run_dir: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """`<run_dir>/run.json` as a dict, or None if missing/empty/truncated."""
    return _load_json_object(Path(run_dir) / RUN_JSON)
