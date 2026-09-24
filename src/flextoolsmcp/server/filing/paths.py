#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Where filing's artifacts may live, and whether a project is in Send/Receive
(parser-check CP4, FR-042, FR-043, R-14).

NOTHING FILING WRITES LIVES INSIDE A PROJECT FOLDER (FR-042). Not the backup,
not the run record, not a pre-deletion capture. A Send/Receive project's
folder is a Mercurial working directory: anything placed in it can be picked
up on the next Send/Receive and committed into the project's shared
repository, where it balloons the history for every collaborator and cannot be
removed. The existing roots -- backups under `~/.flextoolsmcp/backups`, run
records under `record.get_record_dir()` -- already live outside every project,
but `FLEXTOOLSMCP_PARSE_RECORD_DIR` can point anywhere, so the rule is ENFORCED
here at write time rather than assumed. `assert_outside_project` resolves the
real paths and refuses a target under the FieldWorks projects directory.

WHY THE WHOLE PROJECTS DIRECTORY. FR-042 names "the project's folder or any
folder under it". This refuses anything under the projects ROOT, which is a
strict superset: every direct child of that root is a project folder (or a
directory FieldWorks will treat as a candidate one), and a filing artifact
has no business anywhere in it.

SEND/RECEIVE DETECTION (R-14). Chorus keeps a project's Mercurial repository at
`<projects>/<P>/.hg`. Present -> `True`; absent -> `False`; the projects
directory cannot be resolved -> `"unknown"`, which the wording treats as
`True`, because naming the discard-and-re-download route costs nothing when it
turns out not to apply, and omitting it when it does would steer a user
toward restoring a local backup over a shared project.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

__all__ = [
    "DELETIONS_RELPATH",
    "ArtifactInsideProject",
    "projects_directory",
    "project_dir_for",
    "assert_outside_project",
    "send_receive_status",
    "SendReceive",
]

SendReceive = Union[bool, str]  # True | False | "unknown"

#: A filing run's pre-deletion captures, inside its run record (FR-031;
#: data-model section 9). Named here, by the filing package, never in the
#: read spine's record module.
DELETIONS_RELPATH = "filing/deletions.jsonl"


class ArtifactInsideProject(RuntimeError):
    """A filing artifact would be written inside a FieldWorks project folder."""

    def __init__(self, path: Path, projects_root: Path) -> None:
        super().__init__(
            f"Refusing to write {path}: it is inside the FieldWorks projects "
            f"directory ({projects_root}). Filing never writes an artifact "
            f"inside a project folder -- Send/Receive would commit it into the "
            f"project's shared repository (FR-042). Point "
            f"FLEXTOOLSMCP_PARSE_RECORD_DIR (or the backup location) outside "
            f"{projects_root}."
        )
        self.path = path
        self.projects_root = projects_root


def projects_directory() -> Optional[Path]:
    """The FieldWorks projects directory, by the server's own discovery."""
    from .. import project_discovery

    found = project_discovery.get_projects_directory()
    return Path(found[0]) if found else None


def project_dir_for(project_name: str) -> Optional[Path]:
    root = projects_directory()
    return (root / project_name) if root is not None and project_name else None


def _real(path: Union[str, Path]) -> Path:
    # `resolve()` follows symlinks and junctions: an artifact root that is a
    # link INTO a project folder is inside it, whatever its name says.
    try:
        return Path(os.path.realpath(path))
    except (OSError, ValueError):
        return Path(path).absolute()


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child_parts = [p.casefold() for p in child.parts]
        parent_parts = [p.casefold() for p in parent.parts]
    except Exception:  # noqa: BLE001
        return False
    return len(child_parts) >= len(parent_parts) and child_parts[: len(parent_parts)] == parent_parts


def assert_outside_project(
    path: Union[str, Path],
    *,
    projects_root: Optional[Path] = None,
) -> Path:
    """Return `path`'s real form, or raise `ArtifactInsideProject` (FR-042).

    Case-insensitive, and on the RESOLVED path: Windows paths are case-
    insensitive, and a link must not smuggle a write into a project.
    With no resolvable projects directory there is nothing to be inside of,
    and the path is allowed.
    """
    target = _real(path)
    root = projects_root if projects_root is not None else projects_directory()
    if root is None:
        return target
    real_root = _real(root)
    if _is_within(target, real_root):
        raise ArtifactInsideProject(target, real_root)
    return target


def send_receive_status(project_name: str) -> SendReceive:
    """`True` when `<projects>/<P>/.hg` is a directory; `"unknown"` when the
    projects directory cannot be resolved (R-14)."""
    project_dir = project_dir_for(project_name)
    if project_dir is None:
        return "unknown"
    try:
        return (project_dir / ".hg").is_dir()
    except OSError:
        return "unknown"


def treats_as_send_receive(status: SendReceive) -> bool:
    """`unknown` is worded as Send/Receive (see module docstring)."""
    return status is not False
