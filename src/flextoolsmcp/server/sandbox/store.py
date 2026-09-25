#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The user-owned side of the sandbox spine: named sandboxes (and, with US4,
corpora) (parser-check CP5; FR-025, FR-028, FR-029, SC-007; data-model
sections 1, 4 and 5; contracts/tools.md sections 5.2 and 5.4).

A sandbox is `sandboxes/<project>/<name>/`:

  hc-config.xml   a byte-identical copy of a cache entry's config, for the
                  user to edit
  origin.json     written once at creation, never rewritten:
                  {schema, name, project, created_at, from_cache_key,
                   from_inputs, sha256_at_creation}

USER-OWNED (FR-025). Nothing here overwrites, replaces or deletes a file.
`create_sandbox` claims the sandbox directory with an exclusive `mkdir` --
if the directory exists at all, whatever it holds, the create is refused
with `SandboxExists` (a `FileExistsError`) and nothing in it is touched --
then writes each file with an exclusive-create open (`"xb"` / `"x"`), so a
race or a second create can never write over the first. A test pins this
by AST: no `"w"`/`"a"`/`"+"` open, no write_text/write_bytes, no
unlink/rmtree/replace/rename in this module. A create that fails midway
(a disk error after the claim) leaves what it wrote; it is never cleaned up
by deleting, because this module never deletes.

DERIVED, NEVER STORED (data-model section 4):
  edited                    sha256 of hc-config.xml != sha256_at_creation;
                            None without a readable origin.json.
  predates_project_grammar  from_cache_key != the key the project's current
                            inputs give (`cache.key_inputs` -- a `stat` of
                            the .fwdata and of GenerateHCConfig; the project
                            is never opened). False when that key cannot be
                            worked out or the origin is missing: the
                            advisory is only raised when it is known true.

The store returns plain data; the handler builds the envelope. Paths in the
returned dicts are `str`.

API
  create_sandbox(project_name, name, entry) -> {"name", "path", "origin":
      {"from_cache_key", "created_at"}}; raises SandboxExists,
      paths.SandboxNameError, ValueError (entry of another project),
      paths.SandboxPathError (entry config not under config-cache/).
  sandbox_config_path(project_name, name) -> Optional[Path]
  read_origin(project_name, name) -> Optional[dict]
  current_key(fwdata_path, generator_path, *, hcparse_version=None) -> Optional[str]
  project_current_key(project_name) -> Optional[str]
  sandbox_status(project_name, name, current_key=<computed>) -> Optional[dict]
  list_sandboxes(project_name, current_key=<computed>) -> list[dict]
  seed_corpus(project_name, name, record: RunRecord) -> {"name", "path",
      "assertion_count", "no_parse_count", "excluded": [{"word", "reason"}],
      "from_run_id"}; raises RunNotFound, RunNotSeedable,
      paths.SandboxNameError, CorpusExists -- in that order.
  load_corpus(project_name, name) -> Corpus(name, path, data, assertions,
      duplicates); raises paths.SandboxNameError, CorpusNotFound,
      CorpusInvalid(.json_path).
  list_corpora(project_name) -> [{"name", "path", "assertion_count"}]
"""

from __future__ import annotations

import hashlib
import json
import logging
import unicodedata
from dataclasses import dataclass, field as _field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from . import cache, paths

__all__ = [
    "SANDBOX_SCHEMA",
    "SANDBOX_CONFIG_NAME",
    "ORIGIN_JSON",
    "ORIGIN_KEYS",
    "LIST_ITEM_KEYS",
    "STATUS_KEYS",
    "SandboxExists",
    "create_sandbox",
    "sandbox_config_path",
    "read_origin",
    "current_key",
    "project_current_key",
    "sandbox_status",
    "list_sandboxes",
]

_log = logging.getLogger(__name__)

PathLike = Union[str, Path]

SANDBOX_SCHEMA = "flextoolsmcp.hc-sandbox/1"
SANDBOX_CONFIG_NAME = "hc-config.xml"
ORIGIN_JSON = "origin.json"
ORIGIN_KEYS = ("schema", "name", "project", "created_at",
               "from_cache_key", "from_inputs", "sha256_at_creation")
#: One row of `list` (contracts/tools.md section 5.4).
LIST_ITEM_KEYS = ("name", "path", "created_at", "edited", "predates_project_grammar")
#: `sandbox_status`: a list row plus the key it was made from.
STATUS_KEYS = LIST_ITEM_KEYS + ("from_cache_key",)

_READ_CHUNK = 1 << 20

#: Sentinel: "work the project's current key out" (vs an explicit None).
_COMPUTE = object()


class SandboxExists(FileExistsError):
    """The sandbox name is taken (FR-028): refusal reason `sandbox_exists`."""

    reason = "sandbox_exists"

    def __init__(self, name: str, path: PathLike) -> None:
        super().__init__(f"A sandbox named {name!r} already exists: {path}")
        self.name = name
        self.path = str(path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_READ_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_new(path: Path, data: bytes) -> None:
    """Create `path` exclusively; FileExistsError if anything is there."""
    with open(path, "xb") as handle:
        handle.write(data)


# ---------------------------------------------------------------------------
# create (FR-028)
# ---------------------------------------------------------------------------


def create_sandbox(project_name: str, name: str, entry: "cache.CacheEntry") -> Dict[str, Any]:
    """Copy `entry`'s config into a new sandbox `name`; never over anything."""
    target = paths.sandbox_dir(project_name, name)  # SandboxNameError
    if entry.project != project_name:
        raise ValueError(
            f"Cache entry belongs to project {entry.project!r}, not {project_name!r}")
    source = paths.assert_under(entry.config_path, paths.config_cache_root())
    data = source.read_bytes()
    inputs = (entry.meta or {}).get("inputs")

    # The claim: the directory itself, exclusively.
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.mkdir()
    except FileExistsError:
        raise SandboxExists(name, target) from None

    config = target / SANDBOX_CONFIG_NAME
    try:
        _write_new(config, data)
    except FileExistsError:  # a racing hand-made file; still never over it
        raise SandboxExists(name, target) from None

    created_at = _now_iso()
    origin = {
        "schema": SANDBOX_SCHEMA,
        "name": name,
        "project": project_name,
        "created_at": created_at,
        "from_cache_key": entry.key,
        "from_inputs": dict(inputs) if isinstance(inputs, dict) else None,
        "sha256_at_creation": hashlib.sha256(data).hexdigest(),
    }
    try:
        _write_new(target / ORIGIN_JSON,
                   json.dumps(origin, indent=2, ensure_ascii=False).encode("utf-8"))
    except FileExistsError:
        raise SandboxExists(name, target) from None
    return {
        "name": name,
        "path": str(config),
        "origin": {"from_cache_key": entry.key, "created_at": created_at},
    }


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def sandbox_config_path(project_name: str, name: str) -> Optional[Path]:
    """`<sandbox>/hc-config.xml` if that file exists (origin.json optional)."""
    config = paths.sandbox_dir(project_name, name) / SANDBOX_CONFIG_NAME
    return config if config.is_file() else None


def _read_origin_at(directory: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads((directory / ORIGIN_JSON).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SANDBOX_SCHEMA:
        return None
    return data


def read_origin(project_name: str, name: str) -> Optional[Dict[str, Any]]:
    """origin.json's contents, or None when absent, unreadable or unknown."""
    return _read_origin_at(paths.sandbox_dir(project_name, name))


def current_key(
    fwdata_path: PathLike,
    generator_path: PathLike,
    *,
    hcparse_version: Optional[str] = None,
) -> Optional[str]:
    """The cache key the project's inputs give now -- by `stat` alone."""
    try:
        inputs = cache.key_inputs(fwdata_path, generator_path,
                                  hcparse_version=hcparse_version)
    except (OSError, ValueError):
        return None
    return cache.compute_key(inputs)


def project_current_key(project_name: str) -> Optional[str]:
    """`current_key` for the project's live .fwdata and the discovered
    GenerateHCConfig; None when either cannot be located or stat'ed."""
    from .. import parser_probe
    from ..filing import paths as filing_paths

    try:
        project_dir = filing_paths.project_dir_for(project_name)
        if project_dir is None:
            return None
        found = parser_probe.discover_generate_hc_config()
        if not getattr(found, "ok", False) or not getattr(found, "expected_path", None):
            return None
        return current_key(Path(project_dir) / (project_name + ".fwdata"),
                           found.expected_path)
    except Exception as exc:  # noqa: BLE001 - a status read must not fail on discovery
        _log.debug("Could not work out the current cache key for %s: %s", project_name, exc)
        return None


def _status_at(directory: Path, name: str, key: Optional[str]) -> Optional[Dict[str, Any]]:
    config = directory / SANDBOX_CONFIG_NAME
    if not config.is_file():
        return None
    origin = _read_origin_at(directory)
    edited: Optional[bool] = None
    from_key = created_at = None
    predates = False
    if origin is not None:
        from_key = origin.get("from_cache_key")
        created_at = origin.get("created_at")
        recorded = origin.get("sha256_at_creation")
        if isinstance(recorded, str):
            try:
                edited = _sha256_file(config) != recorded
            except OSError:
                edited = None
        predates = bool(key is not None and from_key is not None and from_key != key)
    return {
        "name": name,
        "path": str(config),
        "created_at": created_at,
        "edited": edited,
        "predates_project_grammar": predates,
        "from_cache_key": from_key,
    }


def sandbox_status(project_name: str, name: str,
                   current_key: Any = _COMPUTE) -> Optional[Dict[str, Any]]:
    """STATUS_KEYS for one sandbox, or None when its hc-config.xml is absent.

    `current_key` defaults to `project_current_key(project_name)`; pass a
    key (or None, "unknown") to skip the lookup.
    """
    directory = paths.sandbox_dir(project_name, name)
    if not (directory / SANDBOX_CONFIG_NAME).is_file():
        return None
    key = project_current_key(project_name) if current_key is _COMPUTE else current_key
    return _status_at(directory, name, key)


def list_sandboxes(project_name: str, current_key: Any = _COMPUTE) -> List[Dict[str, Any]]:
    """The 5.4 rows for every sandbox of the project, sorted by name."""
    root = paths.sandboxes_dir(project_name)
    if not root.is_dir():
        return []
    names = sorted(
        child.name for child in root.iterdir()
        if child.is_dir() and paths.validate_name(child.name) is None
        and (child / SANDBOX_CONFIG_NAME).is_file()
    )
    if not names:
        return []
    key = project_current_key(project_name) if current_key is _COMPUTE else current_key
    rows = []
    for name in names:
        status = _status_at(paths.sandbox_dir(project_name, name), name, key)
        if status is not None:
            rows.append({k: status[k] for k in LIST_ITEM_KEYS})
    return rows


# ===========================================================================
# Corpora (US4; FR-030, research R-10, data-model section 5)
# ===========================================================================
#
# A corpus is `corpora/<project>/<name>.json`, user-owned under the same
# rules as a sandbox: created once with an exclusive open, never rewritten,
# never deleted.
#
# SEEDING reads a COMPLETED sandbox PARSE run (contracts/tools.md section 3
# check order: the run exists -> it is seedable -> the name is valid -> the
# name is new). `parsed` keeps its analyses exactly, in hc's order, as
# [{form, gloss}] lists; `not_parsed` is `expected: []`; every other outcome
# -- and a parsed word with an analysis that could not be read -- is left
# out and listed with its reason, never silently dropped. Words are stored
# NFC and de-duplicated keeping the first. Morph text is kept verbatim: a
# form or gloss FR-027 cannot express becomes a run-time `error`, not a
# seed-time exclusion.
#
# LOADING validates the whole file before any assertion is used and names
# the JSON path of the first fault (`$.assertions[2].expected[0][1].gloss`).

CORPUS_SCHEMA = "flextoolsmcp.hc-corpus/1"
CORPUS_SUFFIX = ".json"
CORPUS_KEYS = ("schema", "name", "project", "created_at", "seeded_from", "assertions")
SEED_RESULT_KEYS = ("name", "path", "assertion_count", "no_parse_count", "excluded",
                    "from_run_id")
CORPUS_LIST_KEYS = ("name", "path", "assertion_count")

#: Exclusion reasons beyond the outcome names themselves.
EXCLUDED_UNREADABLE = "unreadable"
EXCLUDED_DUPLICATE = "duplicate"

_OUTCOME_PARSED = "parsed"
_OUTCOME_NOT_PARSED = "not_parsed"

__all__ += [
    "CORPUS_SCHEMA",
    "CORPUS_KEYS",
    "SEED_RESULT_KEYS",
    "CORPUS_LIST_KEYS",
    "EXCLUDED_UNREADABLE",
    "EXCLUDED_DUPLICATE",
    "RunNotFound",
    "RunNotSeedable",
    "CorpusExists",
    "CorpusNotFound",
    "CorpusInvalid",
    "Corpus",
    "seed_corpus",
    "load_corpus",
    "list_corpora",
]


class RunNotFound(LookupError):
    """The run to seed from has no record: error code `parse_run_not_found`."""

    reason = error_code = "parse_run_not_found"

    def __init__(self, run_id: str) -> None:
        super().__init__(f"No parse run {run_id!r} was found")
        self.run_id = run_id


class RunNotSeedable(ValueError):
    """Not a completed sandbox parse run of this project: `run_not_seedable`."""

    reason = "run_not_seedable"

    def __init__(self, run_id: str, detail: str) -> None:
        super().__init__(f"Run {run_id} cannot seed a corpus: {detail}")
        self.run_id = run_id
        self.detail = detail


class CorpusExists(FileExistsError):
    """The corpus name is taken: `corpus_exists`."""

    reason = "corpus_exists"

    def __init__(self, name: str, path: PathLike) -> None:
        super().__init__(f"A corpus named {name!r} already exists: {path}")
        self.name = name
        self.path = str(path)


class CorpusNotFound(LookupError):
    """No such corpus file: `corpus_not_found`."""

    reason = "corpus_not_found"

    def __init__(self, name: str, path: PathLike) -> None:
        super().__init__(f"No corpus named {name!r}: {path} does not exist")
        self.name = name
        self.path = str(path)


class CorpusInvalid(ValueError):
    """The corpus file is malformed: `corpus_invalid`, at `json_path`."""

    reason = "corpus_invalid"

    def __init__(self, name: str, path: PathLike, json_path: str, detail: str) -> None:
        super().__init__(f"Corpus {name!r} is invalid at {json_path}: {detail}")
        self.name = name
        self.path = str(path)
        self.json_path = json_path
        self.detail = detail


@dataclass(frozen=True)
class Corpus:
    """A validated corpus. `assertions` are NFC and de-duplicated."""

    name: str
    path: Path
    data: Dict[str, Any]
    assertions: List[Dict[str, Any]]
    duplicates: List[Dict[str, Any]] = _field(default_factory=list)


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


# ---------------------------------------------------------------------------
# seed
# ---------------------------------------------------------------------------


def _check_seedable(project_name: str, record) -> Any:
    """The run's meta, or RunNotFound / RunNotSeedable (in that order).

    The read is strict (pattern audit sweep 6): a meta.json that exists but
    stays unreadable raises `parse.record.MetaUnreadable` (an OSError), which
    is NOT "not found" -- the handler answers it as a transient, retryable
    `server_state_error`. RunNotFound means the record really is absent.
    """
    from ..parse.record import SPINE_SANDBOX
    from ..parse.stages import RunStage

    meta = record.read_meta_strict() if record.exists() else None
    if meta is None:
        raise RunNotFound(record.run_id)
    if meta.effective_spine != SPINE_SANDBOX:
        raise RunNotSeedable(record.run_id, "it is not a sandbox run")
    section = meta.sandbox if isinstance(meta.sandbox, dict) else {}
    if section.get("mode") != "parse":
        raise RunNotSeedable(record.run_id, "it is not a parse run (mode %r)"
                             % (section.get("mode"),))
    if meta.stage != RunStage.COMPLETED.value:
        raise RunNotSeedable(record.run_id, "it did not complete (stage %r)" % (meta.stage,))
    if meta.project_name != project_name:
        raise RunNotSeedable(record.run_id, "it belongs to project %r" % (meta.project_name,))
    return meta


def _expected_from(analyses: Any) -> Optional[List[List[Dict[str, str]]]]:
    """The analyses as expected parses, or None if any is unreadable."""
    if not isinstance(analyses, list):
        return None
    parses = []
    for analysis in analyses:
        if not isinstance(analysis, dict) or analysis.get("readable") is not True:
            return None
        morphs = analysis.get("morphs")
        if not isinstance(morphs, list) or not morphs:
            return None
        parse = []
        for morph in morphs:
            if not isinstance(morph, dict):
                return None
            form, gloss = morph.get("form"), morph.get("gloss")
            if not isinstance(form, str) or not isinstance(gloss, str):
                return None
            parse.append({"form": form, "gloss": gloss})
        parses.append(parse)
    return parses


def seed_corpus(project_name: str, name: str, record) -> Dict[str, Any]:
    """Seed `corpora/<project>/<name>.json` from a completed sandbox parse run."""
    meta = _check_seedable(project_name, record)
    target = paths.corpus_path(project_name, name)  # SandboxNameError
    if target.exists():
        raise CorpusExists(name, target)

    assertions: List[Dict[str, Any]] = []
    excluded: List[Dict[str, str]] = []
    seen = set()
    for line in record.iter_results():
        word = line.get("wordform")
        section = line.get("parse") if isinstance(line.get("parse"), dict) else {}
        outcome = section.get("outcome")
        if not isinstance(word, str) or not word:
            continue
        key = _nfc(word)
        if key in seen:
            excluded.append({"word": word, "reason": EXCLUDED_DUPLICATE})
            continue
        seen.add(key)  # keep-first: an excluded first occurrence still counts
        if outcome == _OUTCOME_NOT_PARSED:
            expected: Optional[list] = []
        elif outcome == _OUTCOME_PARSED:
            expected = _expected_from(section.get("analyses"))
            if not expected:
                excluded.append({"word": word, "reason": EXCLUDED_UNREADABLE})
                continue
        else:
            excluded.append({"word": word, "reason": str(outcome or "unknown")})
            continue
        assertions.append({"word": key, "expected": expected})

    section = meta.sandbox if isinstance(meta.sandbox, dict) else {}
    data = {
        "schema": CORPUS_SCHEMA,
        "name": name,
        "project": project_name,
        "created_at": _now_iso(),
        "seeded_from": {"run_id": record.run_id,
                        "config_source": section.get("config_source")},
        "assertions": assertions,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_new(target, json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
    except FileExistsError:
        raise CorpusExists(name, target) from None
    return {
        "name": name,
        "path": str(target),
        "assertion_count": len(assertions),
        "no_parse_count": sum(1 for a in assertions if not a["expected"]),
        "excluded": excluded,
        "from_run_id": record.run_id,
    }


# ---------------------------------------------------------------------------
# load / validate
# ---------------------------------------------------------------------------


class _Fault(Exception):
    def __init__(self, json_path: str, detail: str) -> None:
        super().__init__(detail)
        self.json_path = json_path
        self.detail = detail


def _validate(data: Any) -> List[Dict[str, Any]]:
    """The assertions of a well-formed corpus, or `_Fault` at the first fault."""
    if not isinstance(data, dict):
        raise _Fault("$", "the file must hold a JSON object")
    if data.get("schema") != CORPUS_SCHEMA:
        raise _Fault("$.schema", "schema must be %r, not %r"
                     % (CORPUS_SCHEMA, data.get("schema")))
    items = data.get("assertions")
    if not isinstance(items, list):
        raise _Fault("$.assertions", "assertions must be a list")
    out = []
    for i, item in enumerate(items):
        at = "$.assertions[%d]" % i
        if not isinstance(item, dict):
            raise _Fault(at, "each assertion must be an object")
        word = item.get("word")
        if not isinstance(word, str) or not word:
            raise _Fault(at + ".word", "word must be a non-empty string")
        expected = item.get("expected")
        if not isinstance(expected, list):
            raise _Fault(at + ".expected",
                         "expected must be a list of parses ([] means no parse)")
        for j, parse in enumerate(expected):
            pat = "%s.expected[%d]" % (at, j)
            if not isinstance(parse, list) or not parse:
                raise _Fault(pat, "each parse must be a non-empty list of morphs")
            for k, morph in enumerate(parse):
                mat = "%s[%d]" % (pat, k)
                if not isinstance(morph, dict):
                    raise _Fault(mat, "each morph must be an object {form, gloss}")
                for part in ("form", "gloss"):
                    if not isinstance(morph.get(part), str):
                        raise _Fault("%s.%s" % (mat, part), "%s must be a string" % part)
        out.append({"word": word,
                    "expected": [[{"form": m["form"], "gloss": m["gloss"]} for m in parse]
                                 for parse in expected]})
    return out


def _read_corpus_file(path: Path, name: str) -> Corpus:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise CorpusNotFound(name, path) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise CorpusInvalid(name, path, "$", "the file could not be read: %s" % exc) from None
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise CorpusInvalid(name, path, "$", "not valid JSON: %s" % exc) from None
    try:
        items = _validate(data)
    except _Fault as fault:
        raise CorpusInvalid(name, path, fault.json_path, fault.detail) from None

    assertions: List[Dict[str, Any]] = []
    duplicates: List[Dict[str, Any]] = []
    kept: Dict[str, int] = {}
    for index, item in enumerate(items):
        key = _nfc(item["word"])
        if key in kept:
            duplicates.append({"word": item["word"], "index": index, "kept_index": kept[key]})
            continue
        kept[key] = index
        assertions.append({"word": key, "expected": item["expected"]})
    return Corpus(name=name, path=path, data=data, assertions=assertions,
                  duplicates=duplicates)


def load_corpus(project_name: str, name: str) -> Corpus:
    """Load and validate a whole corpus (data-model section 5)."""
    path = paths.corpus_path(project_name, name)  # SandboxNameError
    if not path.is_file():
        raise CorpusNotFound(name, path)
    return _read_corpus_file(path, name)


def list_corpora(project_name: str) -> List[Dict[str, Any]]:
    """The 5.4 corpus rows, sorted by name; a broken file has a None count."""
    root = paths.corpora_dir(project_name)
    if not root.is_dir():
        return []
    rows = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_file() or not child.name.endswith(CORPUS_SUFFIX):
            continue
        name = child.name[: -len(CORPUS_SUFFIX)]
        if paths.validate_name(name) is not None:
            continue
        try:
            count: Optional[int] = len(_read_corpus_file(child, name).assertions)
        except (CorpusInvalid, CorpusNotFound):
            count = None
        rows.append({"name": name, "path": str(child), "assertion_count": count})
    return rows
