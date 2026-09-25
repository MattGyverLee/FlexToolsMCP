#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The sandbox spine's engine check (parser-check CP5, FR-036, research R-02).

WHAT IT READS. The LIVE `.fwdata`, as a plain file stream, before any copy is
made. Python's `open()` on Windows shares read and write (the CRT's
`_SH_DENYNO`), which is the `FileShare.ReadWrite` R-02 asks for: FLEx may
hold the file open and keep writing, and this read neither blocks it nor is
blocked by it. A plain read takes no `.fwdata.lock`, so a non-shared project
held by another program is still checkable (memory note
`non-shared-projects-single-opener`).

HOW. `ElementTree.iterparse` stops at the first `<rt class="MoMorphData">`
end tag. That element's `ParserParameters` text (the escaped XML a project
stores inside `<Uni>`, unescaped by the parser) goes to
`parse/measure.summarize_parser_parameters`, looked up on the module at call
time, and its `active_parser` is the answer.

NEVER LCM. This module imports nothing from flexicon, flexlibs, pythonnet or
LCM; a test runs it in a fresh interpreter and inspects `sys.modules`.
`parser_probe.check_active_parser` stays the in-process spines' check.

FAIL SAFE. An absent `ActiveParser`, an unparseable file or parameters
document, no MoMorphData object, or a read error that persists after one
retry, all count as XAmple and so refuse with `parser_engine_mismatch`. The
refusal's hint then says the value "could not be read" -- distinct from the
"is XAmple" hint -- so a read that raced a FLEx save is recognisable. Any
unreadable outcome is retried once (a mid-save read may look truncated).

MEMO. A readable result is memoised by `file_key` = `(abs_path, size,
mtime_ns)`, the triple the cache entry's `key.json` records beside
`active_parser`; `remember` primes the memo from key.json so a warm job never
re-scans. Unreadable results are never memoised.

HC PARAMETERS (CP5 re-plan, D3/FR-047). The same `ParserParameters` document
carries the project's `HC` Morpher settings, which `GenerateHCConfig` does not
export. `hc_parameters_from_text` reads them the way `HCParser.LoadParser`
does (`HCParser.cs:145-182`), each missing or unreadable key falling back to
FLEx's own default (`HC_PARAMETER_DEFAULTS`). A readable reading carries them
as `EngineReading.hc_parameters`; `remember` accepts them from key.json.
`read_parameters` is the parameters-only read (FR-047 source 2 for a named
sandbox, T115): it is NOT the engine check, so an absent or XAmple
`ActiveParser` never refuses there; only an unreadable file (after the one
retry) gives None.
"""

from __future__ import annotations

import os
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union

__all__ = [
    "HINT_UNREADABLE_PHRASE",
    "READ_ATTEMPTS",
    "RETRY_DELAY_SECONDS",
    "REASON_ABSENT",
    "REASON_UNPARSEABLE",
    "REASON_NO_MORPH_DATA",
    "REASON_READ_ERROR",
    "FAIL_SAFE_ENGINE",
    "HC_PARAMETER_DEFAULTS",
    "EngineReading",
    "hc_parameters_from_text",
    "file_key",
    "read_engine",
    "read_parameters",
    "check_engine",
    "remember",
    "clear_engine_cache",
]

HINT_UNREADABLE_PHRASE = "could not be read"
READ_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.2

REASON_ABSENT = "absent"
REASON_UNPARSEABLE = "unparseable"
REASON_NO_MORPH_DATA = "no_morph_data"
REASON_READ_ERROR = "read_error"

#: What an unreadable value counts as (FieldWorks' own corrupt-XML default).
FAIL_SAFE_ENGINE = "XAmple"

_MORPH_DATA_CLASS = "MoMorphData"

#: FLEx's defaults when `ParserParameters/HC` omits a setting
#: (`HCParser.LoadParser`: delReapps 0, maxStemCount 2, m_guessRoots and
#: m_mergeAnalyses true, maxAlternatives 0). Keys in data-model order.
HC_PARAMETER_DEFAULTS: Dict[str, Any] = {
    "del_reapps": 0,
    "max_roots": 2,
    "merge_analyses": True,
    "guess_roots": True,
    "max_alternatives": 0,
}

#: data-model key -> (element under `HC`, kind).
_HC_ELEMENTS = (
    ("del_reapps", "DelReapps", int),
    ("max_roots", "MaxRoots", int),
    ("merge_analyses", "MergeAnalyses", bool),
    ("guess_roots", "GuessRoots", bool),
    ("max_alternatives", "MaxAlternatives", int),
)

PathLike = Union[str, Path]
FileKey = Tuple[str, int, int]


@dataclass(frozen=True)
class EngineReading:
    """One engine check's reading of a `.fwdata`."""

    key: FileKey
    readable: bool
    active_parser: Optional[str]
    configured_engine: str
    reason: Optional[str]
    parameters: Optional[dict]
    #: The resolved Morpher settings (`hc_parameters_from_text`), or None
    #: when the file could not be read.
    hc_parameters: Optional[dict] = None


_memo: Dict[FileKey, EngineReading] = {}
_memo_lock = threading.Lock()


def _open_fwdata(path: PathLike):
    """Open the `.fwdata` for a shared, read-only binary stream.

    The single open seam. On Windows `open()` requests read+write sharing,
    so FLEx holding the file open (and writing) does not block the read.
    """
    return open(path, "rb")


def file_key(fwdata: PathLike) -> FileKey:
    """`(abs_path, size, mtime_ns)` of the file now. Raises OSError."""
    path = os.path.abspath(fwdata)
    st = os.stat(path)
    return (path, st.st_size, st.st_mtime_ns)


def clear_engine_cache() -> None:
    with _memo_lock:
        _memo.clear()


def remember(key: FileKey, active_parser: str,
             hc_parameters: Optional[dict] = None) -> None:
    """Prime the memo from a cache entry's key.json (no re-scan while it matches).

    `hc_parameters` is key.json's own `hc_parameters`, carried as-is so a
    warm job's reading records the project's Morpher settings beside
    `active_parser` (T100). None for an entry that predates the key.
    """
    key = (str(key[0]), int(key[1]), int(key[2]))
    reading = EngineReading(
        key=key,
        readable=True,
        active_parser=active_parser,
        configured_engine=active_parser,
        reason=None,
        parameters=None,
        hc_parameters=dict(hc_parameters) if isinstance(hc_parameters, dict) else None,
    )
    with _memo_lock:
        _memo[key] = reading


def _as_bool(text: str) -> Optional[bool]:
    # XElement's (bool) cast: "true"/"false" (any case) or "1"/"0".
    value = text.strip().lower()
    if value in ("true", "1"):
        return True
    if value in ("false", "0"):
        return False
    return None


def _as_int(text: str) -> Optional[int]:
    try:
        return int(text.strip())
    except ValueError:
        return None


def hc_parameters_from_text(raw: Optional[str]) -> Dict[str, Any]:
    """The `ParserParameters/HC` Morpher settings, each defaulted (D3/FR-047).

    Always returns all five keys. An absent, empty or unparseable document,
    and a missing or unreadable element, give FLEx's default for that key --
    where FLEx itself would throw on an unreadable value, a sandbox run
    falls back to the default rather than refusing (the value only tunes
    the parse).
    """
    result = dict(HC_PARAMETER_DEFAULTS)
    text = (raw or "").strip()
    if not text:
        return result
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return result
    hc = root.find("HC")
    if hc is None:
        return result
    for key, tag, kind in _HC_ELEMENTS:
        element = hc.find(tag)
        if element is None:
            continue
        value = (_as_bool if kind is bool else _as_int)(element.text or "")
        if value is not None:
            result[key] = value
    return result


class _Unreadable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _parameters_text(rt: ET.Element) -> Optional[str]:
    params = rt.find("ParserParameters")
    if params is None:
        return None
    uni = params.find("Uni")
    if uni is not None:
        return uni.text or ""
    return params.text or ""


def _scan(fwdata: PathLike) -> Optional[str]:
    """The MoMorphData object's ParserParameters text; raises on failure."""
    with _open_fwdata(fwdata) as stream:
        try:
            for _event, element in ET.iterparse(stream, events=("end",)):
                if element.tag != "rt":
                    continue
                if element.get("class") == _MORPH_DATA_CLASS:
                    return _parameters_text(element)
                element.clear()  # keep memory flat across a large file
        except ET.ParseError as exc:
            raise _Unreadable(REASON_UNPARSEABLE) from exc
    raise _Unreadable(REASON_NO_MORPH_DATA)


def _read_once(
    fwdata: PathLike,
) -> Tuple[Optional[str], Optional[str], Optional[dict], Optional[dict]]:
    """(active_parser, reason, parameters, hc_parameters); exactly one of the
    first two is None."""
    from ..parse import measure  # looked up at call time (patchable)

    try:
        raw = _scan(fwdata)
    except OSError:
        return None, REASON_READ_ERROR, None, None
    except _Unreadable as exc:
        return None, exc.reason, None, None
    if raw is None:
        return None, REASON_ABSENT, None, None
    summary = measure.summarize_parser_parameters(raw)
    if not summary or not summary.get("stored"):
        return None, REASON_ABSENT, summary, None
    if not summary.get("parseable"):
        return None, REASON_UNPARSEABLE, summary, None
    active = summary.get("active_parser")
    if not active:
        return None, REASON_ABSENT, summary, None
    return active, None, summary, hc_parameters_from_text(raw)


def read_engine(fwdata: PathLike) -> EngineReading:
    """Read the active parser from the live `.fwdata`. Never raises."""
    try:
        key = file_key(fwdata)
    except OSError:
        key = (os.path.abspath(fwdata), -1, -1)
    else:
        with _memo_lock:
            hit = _memo.get(key)
        if hit is not None:
            return hit

    reason: Optional[str] = REASON_READ_ERROR
    for attempt in range(READ_ATTEMPTS):
        if attempt:
            time.sleep(RETRY_DELAY_SECONDS)
        active, reason, parameters, hc_parameters = _read_once(fwdata)
        if active is not None:
            try:
                key = file_key(fwdata)
            except OSError:
                pass
            reading = EngineReading(
                key=key,
                readable=True,
                active_parser=active,
                configured_engine=active,
                reason=None,
                parameters=parameters,
                hc_parameters=hc_parameters,
            )
            with _memo_lock:
                _memo[key] = reading
            return reading
    return EngineReading(
        key=key,
        readable=False,
        active_parser=None,
        configured_engine=FAIL_SAFE_ENGINE,
        reason=reason,
        parameters=None,
    )


def read_parameters(fwdata: PathLike) -> Optional[Dict[str, Any]]:
    """The project's `ParserParameters/HC` settings, each defaulted, or None.

    A parameters-only read of the live `.fwdata` (FR-047, D3): no LCM, no
    lock, the same one-retry rule as `read_engine`, and no engine check --
    whatever `ActiveParser` says is ignored. A MoMorphData object with no
    stored parameters is a readable answer (all five defaults); None means
    the file itself could not be read after its retry. Never raises, never
    memoised.
    """
    for attempt in range(READ_ATTEMPTS):
        if attempt:
            time.sleep(RETRY_DELAY_SECONDS)
        try:
            raw = _scan(fwdata)
        except (OSError, _Unreadable):
            continue
        return hc_parameters_from_text(raw)
    return None


def _hint(reading: EngineReading, supported: list) -> str:
    if not reading.readable:
        return (
            f"This project's active parser {HINT_UNREADABLE_PHRASE} from its .fwdata "
            f"({reading.reason}), so it is treated as {FAIL_SAFE_ENGINE!r}; this "
            f"operation requires one of {supported!r}. If FieldWorks was saving the "
            "project, try again. Otherwise check the parser in FieldWorks via "
            "Words > Parser > Choose Parser."
        )
    return (
        f"This project's active parser is {reading.configured_engine!r}, but this "
        f"operation requires one of {supported!r}. Switch the active parser in "
        "FieldWorks via Words > Parser > Choose Parser, or run this operation "
        "against a project configured for a supported engine."
    )


def check_engine(
    fwdata: PathLike, *, supported_engines: Tuple[str, ...] = ("HC",)
) -> EngineReading:
    """Return the reading when its engine is supported (case-sensitive), else
    raise `parser_probe.ParserEngineMismatchError` (FR-036)."""
    reading = read_engine(fwdata)
    if reading.configured_engine in supported_engines:
        return reading
    from .. import parser_probe

    supported = list(supported_engines)
    raise parser_probe.ParserEngineMismatchError(
        {
            "error_code": "parser_engine_mismatch",
            "configured_engine": reading.configured_engine,
            "supported_engines": supported,
            "hint": _hint(reading, supported),
        }
    )
