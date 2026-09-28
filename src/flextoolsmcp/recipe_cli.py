#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Promote a local recipe to a shipped-library draft (unified-recipes Phase 7,
FR-030, FR-031, R13).

Console script: ``flextools-mcp-recipe promote <local-id> --id <new-id>
[--out DIR] [--force]``.

The draft is rendered with ``recipe_files.render_draft``: header prefilled
from the local record, ``match_terms: []`` and ``notes: "TODO"`` so it fails
shipped validation until a human edits it. Lines needing scrubbing (GUID,
Windows user path, record projects, forbidden names) are printed, one per
line, as ``scrub before shipping: L<n>: <text>``.

Exit codes: 0 written; 2 unknown local id; 3 target exists without --force;
4 bad new-id (not kebab-case) or shipped-id collision.

Console output is ASCII-only; draft files are UTF-8.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path
from typing import Optional, Sequence

if __package__:
    from .recipe_files import find_scrub_lines, render_draft
else:
    from recipe_files import find_scrub_lines, render_draft  # type: ignore

if __package__:
    try:
        from .server import local_recipes as _local_recipes
    except ImportError:
        _local_recipes = None  # type: ignore
else:
    try:
        from server import local_recipes as _local_recipes  # type: ignore
    except ImportError:
        _local_recipes = None  # type: ignore

if __package__:
    try:
        from .curated_recipes import CURATED_RECIPES as _CURATED
    except ImportError:
        _CURATED = {}  # type: ignore
else:
    try:
        from curated_recipes import CURATED_RECIPES as _CURATED  # type: ignore
    except ImportError:
        _CURATED = {}  # type: ignore

__all__ = ["main", "default_out_dir", "is_kebab_case"]


_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def is_kebab_case(value: str) -> bool:
    return bool(_KEBAB_RE.match(value or ""))


def _ascii(text: str) -> str:
    return text.encode("ascii", errors="replace").decode("ascii")


def default_out_dir() -> Path:
    return Path.home() / ".flextoolsmcp" / "recipe-drafts"


def _shipped_ids() -> set:
    ids = set()
    try:
        ids.update(dict(_CURATED or {}).keys())
    except Exception:
        pass
    if __package__:
        try:
            from .recipe_files import load_recipe_library
        except Exception:
            return ids
    else:
        try:
            from recipe_files import load_recipe_library  # type: ignore
        except Exception:
            return ids
    try:
        file_recipes, _ = load_recipe_library()
        ids.update(file_recipes.keys())
    except Exception:
        pass
    return ids


def _load_locals() -> list:
    if _local_recipes is None:
        return []
    for name in ("load_local_recipes", "load_all", "list_local_recipes", "get_all"):
        fn = getattr(_local_recipes, name, None)
        if callable(fn):
            try:
                rows = fn() if name != "list_local_recipes" else fn(limit=5000)
            except TypeError:
                try:
                    rows = fn()
                except Exception:
                    continue
            except Exception:
                continue
            if isinstance(rows, list):
                return rows
    return []


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flextools-mcp-recipe",
        description="Promote a local recipe to a shipped-library draft.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    promote = sub.add_parser(
        "promote",
        help="Write a draft recipe file from a local recipe.",
    )
    promote.add_argument("local_id", help="Local recipe id (e.g. local-abc123).")
    promote.add_argument("--id", dest="new_id", required=True,
                         help="New recipe id (kebab-case, e.g. my-recipe).")
    promote.add_argument("--out", dest="out", default=None,
                         help="Output directory (default: ~/.flextoolsmcp/recipe-drafts).")
    promote.add_argument("--force", action="store_true",
                         help="Overwrite the target file if it exists.")
    return parser


def _cmd_promote(local_id: str, new_id: str, out: Optional[str],
                 force: bool) -> int:
    if not is_kebab_case(new_id):
        print(_ascii(f"error: --id {new_id!r} is not kebab-case "
                     "(lowercase letters, digits, hyphens)"))
        return 4
    if new_id in _shipped_ids():
        print(_ascii(f"error: --id {new_id!r} collides with a shipped recipe id"))
        return 4

    rows = _load_locals()
    by_id = {r.get("id"): r for r in rows if isinstance(r, dict) and r.get("id")}
    record = by_id.get(local_id)
    if record is None:
        print(_ascii(f"error: unknown local recipe {local_id!r}"))
        nearest = difflib.get_close_matches(
            local_id, sorted(by_id.keys()), n=3, cutoff=0.3)
        if nearest:
            print(_ascii(f"nearest ids: {', '.join(nearest)}"))
            print(_ascii(f"did you mean: {nearest[0]}?"))
        else:
            print(_ascii("no local recipes found; capture one with run_module + user_intent first"))
        return 2

    out_dir = Path(out) if out else default_out_dir()
    target = out_dir / f"{new_id}.py"
    if target.exists() and not force:
        print(_ascii(f"error: {target} exists (use --force to overwrite)"))
        return 3

    draft = render_draft(record, new_id)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(draft, encoding="utf-8")
    except OSError as e:
        print(_ascii(f"error: cannot write {target}: {e}"))
        return 3

    print(_ascii(str(target)))
    projects = list(record.get("projects", []) or [])
    try:
        hits = find_scrub_lines(record.get("code", ""), projects)
    except Exception:
        hits = []
    for lineno, text in hits:
        print(_ascii(f"scrub before shipping: L{lineno}: {text}"))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "promote":
        return _cmd_promote(args.local_id, args.new_id, args.out, args.force)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
