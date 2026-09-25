#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Where the sandbox spine's files live (parser-check CP5, data-model sections
1-5, research R-11, FR-028, FR-042).

ONE ROOT, FOUR AREAS. Everything the spine writes lives under the sandbox root
(`~/.flextoolsmcp/parse/`, overridden by `FLEXTOOLSMCP_PARSE_SANDBOX_DIR`,
the same pattern as `parse/record.get_record_dir`):

  config-cache/<project>/<cache_key>/   system-owned, pruned (cache.py)
  sandboxes/<project>/<name>/           user-owned, never deleted (store.py)
  corpora/<project>/<name>.json         user-owned, never deleted (store.py)
  work/<run_id>/                        the per-run project copy (workdir.py)

NEVER INSIDE A PROJECT FOLDER (FR-042). Every directory handed out here has
been passed through `filing/paths.assert_outside_project` AT THE CALL, not at
import: the override can point anywhere, and the projects directory can change
under a running server. A root inside the FieldWorks projects directory raises
`ArtifactInsideProject`.

`<project>` is the project name as it appears on disk, used verbatim -- which
is how `backup.py` names `backups/<project>/` (it does not transform the
name). A name that could not be a single directory component (a separator,
`.`/`..`, a drive colon) is refused rather than escaped, and every composed
path must `resolve()` under its parent.

USER-SUPPLIED NAMES (FR-028). A sandbox or corpus name is caller input and
becomes a path component, so it is validated by `validate_name` (data-model
section 4) and, after composition, re-checked by resolving under its parent.
Failures raise `SandboxNameError`, whose `reason` is `name_invalid`, ready for
a `parse_sandbox_refused` refusal.

DELETERS. `is_under` / `assert_under` are the guard later deleters use
(cache.py, workdir.py): a delete target must be strictly under `config-cache/`
or `work/` (data-model section 1 invariant).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Union

from ..filing import paths as _filing_paths

__all__ = [
    "ENV_VAR",
    "CONFIG_CACHE",
    "SANDBOXES",
    "CORPORA",
    "WORK",
    "NAME_RE",
    "RESERVED_DEVICE_NAMES",
    "SandboxPathError",
    "SandboxNameError",
    "get_sandbox_root",
    "sandbox_root",
    "area_root",
    "config_cache_root",
    "sandboxes_root",
    "corpora_root",
    "work_root",
    "project_component",
    "config_cache_dir",
    "sandboxes_dir",
    "corpora_dir",
    "work_dir",
    "sandbox_dir",
    "corpus_path",
    "validate_name",
    "require_valid_name",
    "is_under",
    "assert_under",
]

ENV_VAR = "FLEXTOOLSMCP_PARSE_SANDBOX_DIR"
_DEFAULT_SUBDIR = ".flextoolsmcp"
_PARSE_SUBDIR = "parse"

CONFIG_CACHE = "config-cache"
SANDBOXES = "sandboxes"
CORPORA = "corpora"
WORK = "work"
_AREAS = (CONFIG_CACHE, SANDBOXES, CORPORA, WORK)

#: FR-028 / data-model section 4.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

RESERVED_DEVICE_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{i}" for i in range(1, 10)]
    + [f"LPT{i}" for i in range(1, 10)]
)

PathLike = Union[str, Path]


class SandboxPathError(ValueError):
    """A composed sandbox path is unsafe (escapes its parent, bad component)."""


class SandboxNameError(SandboxPathError):
    """A user-supplied sandbox/corpus name breaks the name rule (FR-028).

    `reason` is the refusal reason code (`name_invalid`); `detail` is the
    human sentence naming the rule that was broken.
    """

    reason = "name_invalid"

    def __init__(self, name: object, detail: str) -> None:
        super().__init__(f"Invalid name {name!r}: {detail}")
        self.name = name
        self.detail = detail


# ---------------------------------------------------------------------------
# Roots
# ---------------------------------------------------------------------------


def get_sandbox_root() -> Path:
    """The sandbox root, UNCHECKED. Honors `FLEXTOOLSMCP_PARSE_SANDBOX_DIR`.

    Use `sandbox_root()` (or an area helper) for anything that writes; this
    raw form exists for display and for tests.
    """
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override)
    return Path.home() / _DEFAULT_SUBDIR / _PARSE_SUBDIR


def _guard(path: PathLike) -> Path:
    # Looked up on the module at call time so tests (and filing_fakes) can
    # monkeypatch `filing.paths.projects_directory`.
    return _filing_paths.assert_outside_project(path)


def sandbox_root() -> Path:
    """The sandbox root, resolved and checked outside every project (FR-042)."""
    return _guard(get_sandbox_root())


def area_root(area: str) -> Path:
    """`<root>/<area>` for one of the four areas, checked (FR-042)."""
    if area not in _AREAS:
        raise SandboxPathError(f"Unknown sandbox area {area!r}; expected one of {_AREAS}")
    return _guard(sandbox_root() / area)


def config_cache_root() -> Path:
    return area_root(CONFIG_CACHE)


def sandboxes_root() -> Path:
    return area_root(SANDBOXES)


def corpora_root() -> Path:
    return area_root(CORPORA)


def work_root() -> Path:
    return area_root(WORK)


# ---------------------------------------------------------------------------
# Containment
# ---------------------------------------------------------------------------


def is_under(path: PathLike, root: PathLike, *, strict: bool = True) -> bool:
    """True when `path` resolves inside `root` (case-insensitive, links followed).

    `strict=True` (the default) requires a proper descendant: `root` itself is
    not "under" `root`, so a deleter can never be handed the area root.
    """
    child = _filing_paths._real(path)
    parent = _filing_paths._real(root)
    if not _filing_paths._is_within(child, parent):
        return False
    if strict and len(child.parts) == len(parent.parts):
        return False
    return True


def assert_under(path: PathLike, root: PathLike, *, strict: bool = True) -> Path:
    """Return `path`'s real form, or raise `SandboxPathError` if not under `root`."""
    if not is_under(path, root, strict=strict):
        raise SandboxPathError(f"Refusing path {path}: it is not under {root}")
    return _filing_paths._real(path)


def _child(parent: Path, component: str) -> Path:
    """`parent / component`, resolved, required to stay directly-or-deeper under parent."""
    target = parent / component
    if not is_under(target, parent):
        raise SandboxPathError(f"Refusing path {target}: it resolves outside {parent}")
    return _guard(target)


# ---------------------------------------------------------------------------
# Project component
# ---------------------------------------------------------------------------

_BAD_COMPONENT_CHARS = re.compile(r"[\\/:\x00-\x1f]")


def project_component(project_name: str) -> str:
    """The on-disk component for a project, verbatim as `backup.py` uses it.

    Refused (SandboxPathError) rather than escaped when it could not be one
    directory component: empty, `.`/`..`, a separator, a drive colon, a
    control character, or trailing dot/space (Windows strips those).
    """
    if not isinstance(project_name, str) or not project_name.strip():
        raise SandboxPathError("A project name is required")
    if project_name in (".", "..") or _BAD_COMPONENT_CHARS.search(project_name):
        raise SandboxPathError(f"Project name {project_name!r} is not a single path component")
    if project_name.endswith((".", " ")):
        raise SandboxPathError(f"Project name {project_name!r} ends in '.' or a space")
    return project_name


def config_cache_dir(project_name: str) -> Path:
    """`config-cache/<project>/`, checked."""
    return _child(config_cache_root(), project_component(project_name))


def sandboxes_dir(project_name: str) -> Path:
    """`sandboxes/<project>/`, checked."""
    return _child(sandboxes_root(), project_component(project_name))


def corpora_dir(project_name: str) -> Path:
    """`corpora/<project>/`, checked."""
    return _child(corpora_root(), project_component(project_name))


def work_dir(run_id: str) -> Path:
    """`work/<run_id>/` for a server-issued run id, checked.

    Raises `SandboxPathError` for anything `record.new_run_id()` could not
    mint: a caller string never becomes a path component.
    """
    from ..parse import record

    if not record.is_valid_run_id(run_id):
        raise SandboxPathError(f"{run_id!r} is not a server-issued run id")
    return _child(work_root(), run_id)


# ---------------------------------------------------------------------------
# User-supplied names (FR-028)
# ---------------------------------------------------------------------------


def validate_name(name: object) -> Optional[str]:
    """None when `name` satisfies the name rule, else the sentence saying why."""
    if not isinstance(name, str) or not name:
        return "a name is required"
    if not NAME_RE.match(name):
        return (
            "names are 1-64 characters of letters, digits, '.', '_' or '-', "
            "starting with a letter or digit"
        )
    if name.split(".", 1)[0].upper() in RESERVED_DEVICE_NAMES:
        return "names may not be a Windows reserved device name (CON, PRN, AUX, NUL, COM1-9, LPT1-9)"
    if name.endswith("."):
        return "names may not end in '.'"
    if ".." in name:
        return "names may not contain '..'"
    return None


def require_valid_name(name: object) -> str:
    """Return `name`, or raise `SandboxNameError`."""
    detail = validate_name(name)
    if detail is not None:
        raise SandboxNameError(name, detail)
    return name  # type: ignore[return-value]


def _named_child(parent: Path, name: str, suffix: str = "") -> Path:
    require_valid_name(name)
    try:
        return _child(parent, name + suffix)
    except SandboxPathError as exc:
        # Kept even though the regex excludes separators (data-model 4).
        raise SandboxNameError(name, f"the name resolves outside {parent}") from exc


def sandbox_dir(project_name: str, name: str) -> Path:
    """`sandboxes/<project>/<name>/`; the name is validated (FR-028)."""
    return _named_child(sandboxes_dir(project_name), name)


def corpus_path(project_name: str, name: str) -> Path:
    """`corpora/<project>/<name>.json`; the name is validated (FR-028)."""
    return _named_child(corpora_dir(project_name), name, ".json")
