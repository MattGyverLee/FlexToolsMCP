#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The `lcm-ids.json` sidecar: the validated id map Try A Word shaping needs
(parser-check CP5 re-plan, D4 reversed, FR-050; data-model section 3).

WHY. `HCParser.GetMorphs` shapes a parse by looking each morph's ids up in
the LCM cache: the allomorph's `ID`/`ID2` (FormID, an `IMoForm`), the
morpheme's `ID` (an MSA) and a positive `InflTypeID` (an `ILexEntryInflType`).
The sandbox worker has no LCM, so this module answers the same questions
once, at Generate time, from a plain stream read, and writes the answers
beside the config. The worker applies rules a-d against the map.

WHERE THE IDS SIT IN THE CONFIG. `GenerateHCConfig` writes them as
`<Properties><Property name="...">n</Property></Properties>`:
  * under an allomorph element (`Allomorph`, or an affix process's
    `MorphologicalSubrule`): `ID` and `ID2` are FormIDs -- role `form`;
  * under a morpheme element (`LexicalEntry`, `MorphologicalRule`,
    `RealizationalRule`): `ID` is the MSA -- role `msa`; `InflTypeID` is an
    inflection type -- role `infl_type`, only when positive.
A `0` FormID/ID2 or a `0` InflTypeID is FLEx's "none" and is not looked up
(rule a skips a 0 FormID; GetMorphs never resolves a 0 ID2 or InflTypeID).
A `Properties` element anywhere else carries nothing GetMorphs reads and is
ignored.

HOW AN ID MAPS TO AN OBJECT. The ids are HVOs, and `.fwdata` does not store
HVOs: LCM's XML backend numbers the objects as it loads them, 1-based, in
`<rt>` document order. So id `n` is the n-th `<rt>` of the file the config
was generated from. Checked against `IndonesianHC-Complete` (CP5 session
2026-09-24): all 82 ids its exported config references landed on an `<rt>`
of the expected class under this numbering (40 MoStemAllomorph, 40
MoStemMsa, 1 MoAffixAllomorph, 1 MoDerivAffMsa). The class check below is
what catches the day the assumption stops holding: a wrong numbering lands
ids on objects of the wrong class, which marks the whole map invalid rather
than shaping silently wrong. (T110 re-checks this live on a circumfix
project.)

THE SOURCE. The file read must be the one `GenerateHCConfig` exported from.
`hcparse.ps1 -Mode Generate` clears its `work/<run_id>/` copy before it
returns, so the cache reads the LIVE `.fwdata` -- shared, read-only, no
lock, no LCM, the same stream read as the engine check (R-02) -- and checks
that its `(path, size, mtime_ns)` still equals the cache key's inputs both
before and after the read. Any movement marks the map invalid
(`error: "source_changed"`), since a file other than the exported one may
number its objects differently. `build_entry` accepts an explicit
`id_source` so a retained byte-identical copy can be read instead.

THE FORM TEXT. `GetMorphs` hands FLEx each morph's `IMoForm`, and FLEx
shows that form's own text -- the allomorph `meŋ`, not the surface `mem` the
engine matched -- keeping the surface string only for a guessed root
(`GuessedString`). The same pass therefore records each form id's `Form`
alternative in the project's default vernacular writing system (the first
`LangProject/CurVernWss` entry) as `form`, and that writing system as the
document's `vernacular_ws`. A form with no text there has no `form` key and
the worker falls back to the surface string, as it does for a map written
before this field existed.

NEVER LCM. Imports nothing from flexicon, flexlibs, pythonnet or LCM.
"""

from __future__ import annotations

import json
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple, Union

__all__ = [
    "SCHEMA",
    "LCM_IDS_NAME",
    "ROLE_FORM",
    "ROLE_MSA",
    "ROLE_INFL_TYPE",
    "FORM_CLASSES",
    "MSA_CLASSES",
    "INFL_TYPE_CLASSES",
    "ERROR_SOURCE_CHANGED",
    "ERROR_READ",
    "ERROR_UNPARSEABLE",
    "referenced_ids",
    "build",
    "read",
]

SCHEMA = "flextoolsmcp.hc-lcm-ids/1"
LCM_IDS_NAME = "lcm-ids.json"

ROLE_FORM = "form"
ROLE_MSA = "msa"
ROLE_INFL_TYPE = "infl_type"

#: The concrete subclasses of each class GetMorphs resolves against.
FORM_CLASSES = frozenset({"MoStemAllomorph", "MoAffixAllomorph", "MoAffixProcess"})
MSA_CLASSES = frozenset({
    "MoStemMsa", "MoDerivAffMsa", "MoInflAffMsa", "MoUnclassifiedAffixMsa", "MoDerivStepMsa",
})
INFL_TYPE_CLASSES = frozenset({"LexEntryInflType"})
_ROLE_CLASSES = {
    ROLE_FORM: FORM_CLASSES,
    ROLE_MSA: MSA_CLASSES,
    ROLE_INFL_TYPE: INFL_TYPE_CLASSES,
}

ERROR_SOURCE_CHANGED = "source_changed"
ERROR_READ = "read_error"
ERROR_UNPARSEABLE = "unparseable"

_ALLOMORPH_TAGS = frozenset({"Allomorph", "MorphologicalSubrule"})
_MORPHEME_TAGS = frozenset({"LexicalEntry", "MorphologicalRule", "RealizationalRule"})
_MORPH_DATA_CLASS = "MoMorphData"
_LANG_PROJECT_CLASS = "LangProject"

_READ_ATTEMPTS = 2
_RETRY_DELAY_SECONDS = 0.2

PathLike = Union[str, Path]
FileKey = Tuple[str, int, int]


class _Unreadable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _role_of(parent_tag: str, name: str) -> Optional[str]:
    if parent_tag in _ALLOMORPH_TAGS and name in ("ID", "ID2"):
        return ROLE_FORM
    if parent_tag in _MORPHEME_TAGS:
        if name == "ID":
            return ROLE_MSA
        if name == "InflTypeID":
            return ROLE_INFL_TYPE
    return None


def referenced_ids(config_path: PathLike) -> Tuple[Dict[int, str], Set[str]]:
    """`({id: role}, invalid)` for every id the config references.

    `invalid` holds the raw text of each id that cannot be one: not an
    integer, negative, a 0 MSA id (GetMorphs casts it unconditionally), or
    one id referenced in two roles. Raises `_Unreadable`.
    """
    ids: Dict[int, str] = {}
    invalid: Set[str] = set()
    stack: list = []
    try:
        with open(config_path, "rb") as stream:
            for event, element in ET.iterparse(stream, events=("start", "end")):
                if event == "start":
                    stack.append(element.tag)
                    continue
                stack.pop()
                if element.tag != "Properties" or not stack:
                    continue
                parent = stack[-1]
                for prop in element.findall("Property"):
                    role = _role_of(parent, prop.get("name") or "")
                    if role is None:
                        continue
                    raw = (prop.text or "").strip()
                    try:
                        value = int(raw)
                    except ValueError:
                        invalid.add(raw)
                        continue
                    if value < 0 or (value == 0 and role == ROLE_MSA):
                        invalid.add(raw)
                        continue
                    if value == 0:
                        continue  # FLEx's "none": never looked up
                    if ids.get(value, role) != role:
                        invalid.add(str(value))
                    ids[value] = role
    except OSError as exc:
        raise _Unreadable(ERROR_READ) from exc
    except ET.ParseError as exc:
        raise _Unreadable(ERROR_UNPARSEABLE) from exc
    return ids, invalid


def _parameters_text(rt: ET.Element) -> Optional[str]:
    from . import engine

    return engine._parameters_text(rt)


def _scan_fwdata(
    fwdata: PathLike, wanted: Set[int]
) -> Tuple[Dict[int, Dict[str, Any]], Optional[str], Optional[str]]:
    """`({hvo: {class, guid, morph_type_guid?, forms?}}, parser_parameters_text,
    default_vernacular_ws)`. `forms` is a form's `Form` alternatives by
    writing system; `_build_once` keeps only the default vernacular one."""
    found: Dict[int, Dict[str, Any]] = {}
    params: Optional[str] = None
    vernacular_ws: Optional[str] = None
    hvo = 0
    try:
        with open(fwdata, "rb") as stream:
            for _event, element in ET.iterparse(stream, events=("end",)):
                if element.tag != "rt":
                    continue
                hvo += 1
                cls = element.get("class")
                if hvo in wanted:
                    item: Dict[str, Any] = {"class": cls, "guid": element.get("guid")}
                    if cls in FORM_CLASSES:
                        surrogate = element.find("MorphType/objsur")
                        item["morph_type_guid"] = (
                            surrogate.get("guid") if surrogate is not None else None)
                        item["forms"] = {
                            auni.get("ws"): auni.text or ""
                            for auni in element.findall("Form/AUni") if auni.get("ws")
                        }
                    found[hvo] = item
                if cls == _MORPH_DATA_CLASS and params is None:
                    params = _parameters_text(element)
                if cls == _LANG_PROJECT_CLASS and vernacular_ws is None:
                    uni = element.find("CurVernWss/Uni")
                    tokens = (uni.text or "").split() if uni is not None else []
                    vernacular_ws = tokens[0] if tokens else None
                element.clear()  # keep memory flat across a large file
    except OSError as exc:
        raise _Unreadable(ERROR_READ) from exc
    except ET.ParseError as exc:
        raise _Unreadable(ERROR_UNPARSEABLE) from exc
    return found, params, vernacular_ws


def _with_form_text(item: Dict[str, Any], vernacular_ws: Optional[str]) -> Dict[str, Any]:
    """The map entry, its `forms` reduced to the default vernacular `form`."""
    entry = {k: v for k, v in item.items() if k != "forms"}
    text = (item.get("forms") or {}).get(vernacular_ws) if vernacular_ws else None
    if text and text != "***":
        entry["form"] = text
    return entry


def _file_key(path: PathLike) -> Optional[FileKey]:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (os.path.abspath(path), st.st_size, st.st_mtime_ns)


def _same_key(a: Optional[FileKey], b: FileKey) -> bool:
    if a is None:
        return False
    return (os.path.normcase(a[0]), a[1], a[2]) == (
        os.path.normcase(os.path.abspath(b[0])), int(b[1]), int(b[2]))


def _document(valid: bool, ids: Dict[str, Any], invalid: Set[str],
              error: Optional[str], vernacular_ws: Optional[str] = None) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "valid": valid,
        "ids": ids,
        "invalid_ids": sorted(invalid, key=lambda raw: (len(raw), raw)),
        "error": error,
        "vernacular_ws": vernacular_ws,
    }


def _build_once(
    config_path: PathLike, fwdata: PathLike, expected_key: Optional[FileKey]
) -> Tuple[Dict[str, Any], Optional[str], bool]:
    """(document, parameters_text, retryable)."""
    try:
        referenced, invalid = referenced_ids(config_path)
    except _Unreadable as exc:
        return _document(False, {}, set(), "config_" + exc.reason), None, False
    if expected_key is not None and not _same_key(_file_key(fwdata), expected_key):
        return _document(False, {}, set(), ERROR_SOURCE_CHANGED), None, False
    try:
        found, params, vernacular_ws = _scan_fwdata(fwdata, set(referenced))
    except _Unreadable as exc:
        return _document(False, {}, set(), exc.reason), None, True
    if expected_key is not None and not _same_key(_file_key(fwdata), expected_key):
        return _document(False, {}, set(), ERROR_SOURCE_CHANGED), None, False

    ids: Dict[str, Any] = {}
    for hvo, role in sorted(referenced.items()):
        item = found.get(hvo)
        if str(hvo) in invalid:
            continue
        if item is None or item.get("class") not in _ROLE_CLASSES[role]:
            invalid.add(str(hvo))
            continue
        ids[str(hvo)] = dict(_with_form_text(item, vernacular_ws), role=role)
    return _document(not invalid, ids, invalid, None, vernacular_ws), params, False


def build(
    config_path: PathLike,
    fwdata: PathLike,
    *,
    expected_key: Optional[FileKey] = None,
) -> Tuple[Dict[str, Any], Optional[str]]:
    """The sidecar document for `config_path`, and the `.fwdata`'s
    `ParserParameters` text (None when it could not be read).

    Never raises. `valid` is False, with `invalid_ids` or `error` saying
    why, whenever any referenced id does not resolve to its role's class, or
    either file cannot be read, or `fwdata`'s `(path, size, mtime_ns)` is not
    `expected_key` before and after the read. A read error is retried once
    (a mid-save read may look truncated), like the engine check.
    """
    document: Dict[str, Any] = _document(False, {}, set(), ERROR_READ)
    params: Optional[str] = None
    for attempt in range(_READ_ATTEMPTS):
        if attempt:
            time.sleep(_RETRY_DELAY_SECONDS)
        document, params, retryable = _build_once(config_path, fwdata, expected_key)
        if not retryable:
            break
    return document, params


def read(path: PathLike) -> Optional[Dict[str, Any]]:
    """A sidecar's document, or None when it is absent, unreadable, or not
    this schema. A None for a path that exists is NOT "absent": a caller
    must treat an unreadable sidecar as invalid (FR-050)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return None
    return data
