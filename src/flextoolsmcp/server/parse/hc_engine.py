#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pure helpers for the parse worker's `--sandbox` mode (parser-check CP5
re-plan, contracts/sandbox-worker.md; research.md R-17, D1-D8).

The sandbox worker parses an exported HermitCrab config by calling the
FieldWorks-bundled engine directly (`_SandboxBackend` in `worker_main.py`).
Everything that can be said about that without .NET lives here, so it is
unit-testable on any machine:

  * where the engine is (`resolve_engine_dir`);
  * the Morpher parameters the client resolved (`load_hc_parameters`);
  * the validated `lcm-ids.json` sidecar (`load_id_map`);
  * FLEx's own Try A Word shaping of a raw analysis (`shape_analysis`), a
    port of `HCParser.GetMorphs`
    (`fieldworks/Src/LexText/ParserCore/HCParser.cs:332-440`).

**This module constructs no parser.** `XmlLanguageLoader` and `Morpher`
are named only inside `_SandboxBackend` (the CP1 boundary allowlist,
`tests/test_cp1_boundary.py`, D2). Nothing here imports pythonnet, flexicon
or LCM, so the server may import it too.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

__all__ = [
    "ENGINE_DLL",
    "DEFAULT_HC_PARAMETERS",
    "HC_PARAMETER_KEYS",
    "ID_MAP_SCHEMA",
    "EngineUnavailable",
    "IdMap",
    "IdMapInvalid",
    "RawMorph",
    "load_hc_parameters",
    "load_id_map",
    "resolve_engine_dir",
    "shape_analysis",
]

#: The engine FieldWorks ships and Try A Word parses with (D7).
ENGINE_DLL = "SIL.Machine.Morphology.HermitCrab.dll"

#: FLEx's own defaults when a project's `ParserParameters/HC` omits a key
#: (`HCParser.cs:147-153` and the constructor's `m_guessRoots`/`m_mergeAnalyses`).
DEFAULT_HC_PARAMETERS: dict[str, Any] = {
    "del_reapps": 0,
    "max_roots": 2,
    "merge_analyses": True,
    "guess_roots": True,
    "max_alternatives": 0,
}
HC_PARAMETER_KEYS = tuple(DEFAULT_HC_PARAMETERS)

ID_MAP_SCHEMA = "flextoolsmcp.hc-lcm-ids/1"

#: `MoMorphTypeTags` GUIDs the shaping rules branch on (the same model GUIDs
#: `server/filing/eligibility.py` lists).
MORPH_TYPE_CIRCUMFIX = "d7f713df-e8cf-11d3-9764-00c04f186933"
MORPH_TYPE_INFIX = "d7f713da-e8cf-11d3-9764-00c04f186933"
MORPH_TYPE_INFIXING_INTERFIX = "18d9b1c3-b5b6-4c07-b92c-2fe1d2281bd4"
_INFIX_TYPES = frozenset({MORPH_TYPE_INFIX, MORPH_TYPE_INFIXING_INTERFIX})

#: `id-map` roles, as `sandbox/cache.py` records them per id.
ROLE_FORM = "form"
ROLE_MSA = "msa"
ROLE_INFL_TYPE = "infl_type"


class EngineUnavailable(RuntimeError):
    """The FieldWorks HermitCrab engine could not be found or loaded."""


class IdMapInvalid(ValueError):
    """The `--id-map` sidecar is recorded invalid, or cannot be read."""


# ---------------------------------------------------------------------------
# The engine directory
# ---------------------------------------------------------------------------


def _default_engine_dirs() -> list[Path]:
    """`FIELDWORKS_DLL_PATH`, then the standard FieldWorks 9 folders -- the
    same places `server/versioning.py` looks for the install it binds to."""
    dirs: list[Path] = []
    env_path = os.environ.get("FIELDWORKS_DLL_PATH")
    if env_path:
        dirs.append(Path(env_path))
    dirs.extend([
        Path(r"C:/Program Files/SIL/FieldWorks 9"),
        Path(r"C:/Program Files (x86)/SIL/FieldWorks 9"),
    ])
    return dirs


def resolve_engine_dir(explicit: Optional[str] = None) -> Path:
    """The folder holding `ENGINE_DLL` and its dependencies.

    `--engine-dir` wins when given (the client passes the install the server
    already resolved, D6); otherwise the first default location that holds
    the DLL. Raises `EngineUnavailable` naming what was looked for.
    """
    if explicit:
        directory = Path(explicit)
        if not (directory / ENGINE_DLL).is_file():
            raise EngineUnavailable(f"{ENGINE_DLL} not found in {directory}")
        return directory
    for candidate in _default_engine_dirs():
        if (candidate / ENGINE_DLL).is_file():
            return candidate
    raise EngineUnavailable(f"{ENGINE_DLL} was not found in any FieldWorks installation")


# ---------------------------------------------------------------------------
# Parameters (D3): client-sourced, worker-applied
# ---------------------------------------------------------------------------


def load_hc_parameters(path: Optional[str]) -> dict[str, Any]:
    """The resolved Morpher parameters, every key defaulted.

    `path` is `--hc-params`; None means no source had them, so FLEx's
    defaults apply. An unknown key is ignored and a missing one defaulted,
    so an older or newer client cannot make the worker fail here.
    """
    resolved = dict(DEFAULT_HC_PARAMETERS)
    if not path:
        return resolved
    with open(path, encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"--hc-params {path!r} is not a JSON object")
    for key in HC_PARAMETER_KEYS:
        if data.get(key) is not None:
            resolved[key] = data[key]
    return resolved


# ---------------------------------------------------------------------------
# The id map (FR-050, data-model.md section 3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdMap:
    """A validated `lcm-ids.json`: id -> `{guid, class, role, morph_type_guid?}`."""

    ids: Mapping[str, Mapping[str, Any]]

    def _entry(self, value: int, role: str) -> Optional[Mapping[str, Any]]:
        entry = self.ids.get(str(value))
        if entry is None:
            return None
        # A map written before per-id roles has no `role`; the class check
        # was already done when it was validated, so accept it.
        entry_role = entry.get("role")
        if entry_role is not None and entry_role != role:
            return None
        return entry

    def form(self, value: int) -> Optional[Mapping[str, Any]]:
        return self._entry(value, ROLE_FORM)

    def has_msa(self, value: int) -> bool:
        return self._entry(value, ROLE_MSA) is not None

    def has_infl_type(self, value: int) -> bool:
        return self._entry(value, ROLE_INFL_TYPE) is not None


def load_id_map(path: str) -> IdMap:
    """Read `--id-map`, trusting its own recorded `valid` flag (section 5).

    Raises `IdMapInvalid` when the file cannot be parsed, is not this
    schema, or is recorded `valid: false`; the message names the invalid
    ids so the failure line says which ones.
    """
    try:
        with open(path, encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise IdMapInvalid(f"the id map {path!r} could not be read: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != ID_MAP_SCHEMA:
        raise IdMapInvalid(f"the id map {path!r} is not a {ID_MAP_SCHEMA} document")
    if data.get("valid") is not True:
        invalid = data.get("invalid_ids") or []
        raise IdMapInvalid(f"the id map is recorded invalid; unresolved ids: {invalid}")
    ids = data.get("ids")
    if not isinstance(ids, dict):
        raise IdMapInvalid(f"the id map {path!r} has no `ids` object")
    return IdMap(ids=ids)


# ---------------------------------------------------------------------------
# Try A Word shaping (FR-050): a port of HCParser.GetMorphs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawMorph:
    """One morph as the engine returned it, before any shaping.

    Ids are the `<Property>` values the exported config carries, read as
    ints. `form_id` is None when the allomorph has no `ID` property at all
    (a user hand-edit in a named sandbox), which rule (a) treats differently
    from an explicit `0`.
    """

    form: str
    gloss: str
    guessed: bool
    form_id: Optional[int]
    form_id2: int = 0
    msa_id: Optional[int] = None
    infl_type_id: int = 0
    is_affix_process: bool = False
    #: The morpheme's identity within one analysis. `GetMorphs` keys its
    #: already-seen dictionary on the `Morpheme` object; the worker passes
    #: a stable per-morpheme key (the MSA id, else the engine's own id).
    morpheme_key: Any = None


def morpheme_key(msa_id: Optional[int], engine_id: Any, position: int,
                 infl_type_id: int = 0) -> Any:
    """The already-seen key for rule (c): the MSA id, else the engine's id.

    `GetMorphs` keys on the `Morpheme` object. GenerateHCConfig leaves the
    engine's `Morpheme.Id` unset, so keying on it made every morph collide
    and dropped all but the first (a root after its prefix). A morpheme is
    exported per MSA, except that an inflectional variant carries its main
    entry's MSA with its own `InflTypeID`, so the key is the pair. With no
    MSA id, the engine's id; with neither, a key unique to the position,
    which can never merge two morphs (rule (d) drops such a morph's analysis
    anyway, unless it is `user_added`, which rule (c) never consults).
    """
    if msa_id is not None:
        return ("msa", msa_id, infl_type_id or 0)
    if engine_id is not None and str(engine_id):
        return ("id", str(engine_id))
    return ("position", position)


def _emitted(morph: RawMorph, *, is_circumfix: bool, user_added: bool,
             form_text: Optional[str] = None) -> dict[str, Any]:
    return {
        "form": form_text or morph.form,
        "gloss": morph.gloss,
        "guessed": bool(morph.guessed),
        "is_circumfix": is_circumfix,
        "user_added": user_added,
    }


def unshaped(morphs: Sequence[RawMorph]) -> list[dict[str, Any]]:
    """Every morph, in engine order: the no-id-map path (`id_map: "absent"`)."""
    return [_emitted(m, is_circumfix=False, user_added=False) for m in morphs]


def shape_analysis(
    morphs: Sequence[RawMorph],
    id_map: IdMap,
    *,
    named_sandbox: bool,
) -> Optional[list[dict[str, Any]]]:
    """Apply FLEx's Try A Word rules to one analysis; None drops it.

    Follows `HCParser.GetMorphs` statement for statement, with the id map
    standing in for the LCM repositories it consults:

      a. a morph whose `ID` is `0` or absent is skipped -- except, in a named
         sandbox, one with no `ID` at all, which is emitted as `user_added`;
      b. an affix-process allomorph with no `ID2` whose form is a circumfix
         is remembered on its first occurrence; its second occurrence is the
         suffix portion (LT-21447). Both are emitted, as FLEx does, so the
         circumfix appears before and after what it attaches to;
      c. a morpheme already seen is emitted again only as (b)'s suffix
         portion, or through its `ID2` form (a two-part circumfix);
         otherwise it is skipped;
      d. the whole analysis is dropped if a form id, the MSA id or a
         positive `InflTypeID` is not in the validated map (FLEx's
         `TryGetObject` failures). A `user_added` morph is exempt;
      and, as `GetMorphs` does last, an infix is placed before the morph it
      interrupts rather than after it.

    `is_circumfix` is true for a two-part circumfix morph (`ID2 > 0`, FLEx's
    own `MorphInfo.IsCircumfix`) and for (b)'s suffix portion.

    A shaped morph's `form` is the map's `form` text for the form id it was
    emitted through -- the allomorph FLEx shows (`meŋ`), not the surface
    string the engine matched (`mem`) -- except for a guessed morph, which
    keeps the surface string as FLEx's `GuessedString` does. A map entry with
    no `form` (an older map, or no text in the vernacular) keeps the surface.
    """
    seen: set = set()
    apr_circumfixes: set = set()
    result: list[dict[str, Any]] = []

    for morph in morphs:
        if morph.form_id is None:
            if not named_sandbox:
                continue
            result.append(_emitted(morph, is_circumfix=False, user_added=True))
            continue
        if morph.form_id == 0:
            continue

        suffix_portion = False
        form_id2 = morph.form_id2 or 0
        if form_id2 == 0 and morph.is_affix_process:
            circum = id_map.form(morph.form_id)
            if circum is None:
                return None
            if circum.get("morph_type_guid") == MORPH_TYPE_CIRCUMFIX:
                if morph.form_id in apr_circumfixes:
                    suffix_portion = True
                else:
                    apr_circumfixes.add(morph.form_id)

        key = morph.morpheme_key
        if key not in seen or suffix_portion:
            current_form_id = morph.form_id
        elif form_id2 > 0:
            current_form_id = form_id2
        else:
            continue

        form_entry = id_map.form(current_form_id)
        if form_entry is None:
            return None
        if morph.msa_id is None or not id_map.has_msa(morph.msa_id):
            return None
        if (morph.infl_type_id or 0) > 0 and not id_map.has_infl_type(morph.infl_type_id):
            return None

        seen.add(key)
        # FLEx shows the allomorph's own form (`MorphInfo.Form`), and the
        # surface string only for a guessed root (`GuessedString`).
        emitted = _emitted(
            morph, is_circumfix=form_id2 > 0 or suffix_portion, user_added=False,
            form_text=None if morph.guessed else form_entry.get("form"),
        )
        if form_entry.get("morph_type_guid") in _INFIX_TYPES and result:
            result.insert(len(result) - 1, emitted)
        else:
            result.append(emitted)

    return result


def parse_int_property(value: Any) -> Optional[int]:
    """A `<Property>` value as an int. The XML loader stores them as
    strings (`XmlLanguageLoader.LoadProperties`); None when unparseable."""
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        return None
