#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Disposable project copies for live write tests (parser-check CP4, FR-037).

EVERY LIVE WRITE RUNS ON A COPY. CP4 is the first checkpoint that writes to a
FieldWorks project, and the write it performs -- filing parser results --
deletes analyses and cannot be undone. A live test that filed into a working
project in place would be the exact failure the feature exists to guard
against, so the rule is enforced here rather than trusted to each test:

  * a copy is always named ``CP4-Scratch-<source>-<stamp>``;
  * every destructive operation (teardown) REFUSES a name without the
    ``CP4-Scratch-`` prefix, whatever the caller passes;
  * the source project is only ever READ -- nothing is written inside it,
    not a marker, not a lock, not a log (FR-042);
  * the copy's ``.hg`` directory is deleted, so a scratch copy can never take
    part in Send/Receive and push its damage to a shared repository;
  * a stale ``.fwdata.lock`` in the source is not copied: it belongs to the
    process holding the source, not to the copy.

Command line (quickstart "Disposable copy")::

    python tests/live_support/make_disposable.py --from "IndonesianHC-Complete"
    python tests/live_support/make_disposable.py --from "IndonesianHC-Complete" --as "CP4-Scratch-IndonesianHC"
    python tests/live_support/make_disposable.py --delete "CP4-Scratch-IndonesianHC"

Library::

    with disposable_project("IndonesianHC-Complete") as copy:
        ...  # copy.name is the project name to open
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

#: The one prefix a disposable copy may carry. Teardown refuses anything else.
SCRATCH_PREFIX = "CP4-Scratch-"

_FWDATA_EXT = ".fwdata"


class NotDisposable(ValueError):
    """A name that is not a scratch copy was handed to a destructive call."""


@dataclass(frozen=True)
class DisposableProject:
    name: str
    path: Path
    source: str

    @property
    def fwdata(self) -> Path:
        return self.path / f"{self.name}{_FWDATA_EXT}"


def is_disposable_name(name: str) -> bool:
    return bool(name) and name.startswith(SCRATCH_PREFIX) and len(name) > len(SCRATCH_PREFIX)


def require_disposable(name: str) -> str:
    """Return ``name`` if it is a scratch copy; raise otherwise (FR-037)."""
    if not is_disposable_name(name):
        raise NotDisposable(
            f"{name!r} is not a disposable copy. Live write tests run only on "
            f"projects named {SCRATCH_PREFIX}<...> (FR-037); a working project "
            f"is never written in place."
        )
    return name


def projects_dir(explicit: Optional[Path] = None) -> Path:
    """The FieldWorks projects directory, by the server's own discovery."""
    if explicit is not None:
        return Path(explicit)
    src = Path(__file__).resolve().parents[2] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from flextoolsmcp.server.project_discovery import get_projects_directory

    found = get_projects_directory()
    if not found:
        raise FileNotFoundError(
            "The FieldWorks projects directory could not be located; set "
            "FW_PROJECTS_DIR or install FieldWorks."
        )
    return Path(found[0])


def _ignore_for_copy(directory: str, names: list) -> set:
    # Locks belong to whoever holds the SOURCE, and a Mercurial repository
    # would make the copy Send/Receive-capable. Neither is copied.
    ignored = {n for n in names if n.endswith(".lock")}
    if ".hg" in names:
        ignored.add(".hg")
    return ignored


def make_disposable(
    source: str,
    *,
    name: Optional[str] = None,
    root: Optional[Path] = None,
) -> DisposableProject:
    """Copy ``source`` to a new ``CP4-Scratch-`` project and return it.

    The source is read, never written. Refuses if the target already exists:
    reusing a scratch copy from an earlier run would make a test's "before"
    state whatever that run left behind.
    """
    base = projects_dir(root)
    src_dir = base / source
    src_fwdata = src_dir / f"{source}{_FWDATA_EXT}"
    if not src_fwdata.is_file():
        raise FileNotFoundError(f"No project {source!r} at {src_fwdata}")

    if name is None:
        stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
        name = f"{SCRATCH_PREFIX}{source}-{stamp}"
    require_disposable(name)

    dest_dir = base / name
    if dest_dir.exists():
        raise FileExistsError(
            f"{dest_dir} already exists. A scratch copy is never reused; "
            f"delete it first (--delete {name!r})."
        )

    shutil.copytree(src_dir, dest_dir, ignore=_ignore_for_copy)
    copied = dest_dir / f"{source}{_FWDATA_EXT}"
    target = dest_dir / f"{name}{_FWDATA_EXT}"
    if copied != target:
        os.replace(copied, target)
    # Belt and braces: the ignore above already skipped .hg, but a nested
    # copy of one (never expected) must not survive either.
    for hg in dest_dir.rglob(".hg"):
        if hg.is_dir():
            shutil.rmtree(hg, ignore_errors=True)
    return DisposableProject(name=name, path=dest_dir, source=source)


def delete_disposable(name: str, *, root: Optional[Path] = None) -> bool:
    """Delete a scratch copy. REFUSES any name without the scratch prefix."""
    require_disposable(name)
    dest_dir = projects_dir(root) / name
    if not dest_dir.exists():
        return False
    # Resolve and re-check: a symlink or junction named CP4-Scratch-* that
    # points at a real project must not be followed into it.
    real = dest_dir.resolve()
    if not is_disposable_name(real.name):
        raise NotDisposable(f"{dest_dir} resolves to {real}, which is not a scratch copy.")
    shutil.rmtree(real)
    return True


@contextlib.contextmanager
def disposable_project(
    source: str, *, root: Optional[Path] = None, keep: bool = False
) -> Iterator[DisposableProject]:
    """A scratch copy for the length of a ``with`` block, then torn down."""
    copy = make_disposable(source, root=root)
    try:
        yield copy
    finally:
        if not keep:
            with contextlib.suppress(Exception):
                delete_disposable(copy.name, root=root)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--from", dest="source", help="Project to copy (read only).")
    group.add_argument("--delete", help="Scratch copy to delete (CP4-Scratch- prefix required).")
    parser.add_argument("--as", dest="name", help="Name for the copy (CP4-Scratch- prefix required).")
    parser.add_argument("--projects-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        if args.delete:
            removed = delete_disposable(args.delete, root=args.projects_dir)
            print(f"{'Deleted' if removed else 'No such copy'}: {args.delete}")
            return 0
        copy = make_disposable(args.source, name=args.name, root=args.projects_dir)
        print(f"Created {copy.name} at {copy.path}")
        return 0
    except (NotDisposable, FileExistsError, FileNotFoundError) as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
