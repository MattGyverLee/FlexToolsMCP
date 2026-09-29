#
#   speckit_git.py
#
#   Git side of the speckit rounds: publish the spec folder on the feature
#   branch so other agents can see where a feature stands.
#
#   The spec folder (specs/<feature>/) travels with the feature branch, in
#   the feature's worktree, and reaches main only when the PR merges. After
#   every round the drivers call sync_spec(), which commits ONLY that folder
#   in the worktree and pushes it to origin/<feature branch>. Other dirty
#   files in the worktree are never swept in. Round logs
#   (specs/<feature>/rounds/) stay local via the folder's .gitignore.
#
#   Feature code is not handled here: the speckit-round skill commits and
#   pushes it on the same branch at the end of each phase, after the phase's
#   tests pass.
#
#   Nothing here ever commits or pushes on main. With no feature worktree
#   (e.g. before the branch exists) the sync is skipped.
#
#   Best-effort by design: a failed sync prints a warning and returns; it
#   never stops a pipeline run.
#
#   Usage (by hand, e.g. after an interactive /speckit step):
#       python scripts/speckit_git.py sync [specs/NNN-name] [-m "message"]
#
#   Platform: any (needs git on PATH)
#
#   Copyright 2026
#

import argparse
import subprocess
import sys
from pathlib import Path

LOCAL_ONLY = ("rounds/",)       # entries the spec folder's .gitignore must carry
PROTECTED = ("main", "master")  # never commit spec syncs here


def git(root, *args, check=False):
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if check and proc.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {(proc.stderr or proc.stdout).strip()}")
    return proc


def ensure_local_only_ignored(root, feature_dir):
    """Keep round logs out of git: add LOCAL_ONLY entries to the folder's .gitignore."""
    path = root / feature_dir / ".gitignore"
    try:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
    except OSError:
        return
    missing = [e for e in LOCAL_ONLY if e not in text.split()]
    if missing:
        block = "\n# speckit round logs -- local only (scripts/speckit_git.py).\n" + "\n".join(missing) + "\n"
        path.write_text(text.rstrip("\n") + ("\n" if text else "") + block, encoding="utf-8")


def sync_spec(feature_dir, message):
    """Commit specs/<feature>/ in the feature worktree and push it to its branch.

    Returns a one-line status ("pushed <sha> to <branch>", "nothing to sync",
    or a "skipped: ..." / "failed: ..." reason). Never raises.
    """
    from speckit_rounds import feature_worktree
    spec = Path(feature_dir).as_posix()
    try:
        root = feature_worktree(Path(feature_dir))
        if root is None:
            return f"skipped: no worktree on a branch named for {Path(feature_dir).name}"
        branch = git(root, "branch", "--show-current").stdout.strip()
        if not branch or branch in PROTECTED:
            return f"skipped: worktree is on '{branch or 'detached HEAD'}', not a feature branch"
        ensure_local_only_ignored(root, feature_dir)
        git(root, "add", "-A", "--", spec, check=True)
        if git(root, "diff", "--cached", "--quiet", "--", spec).returncode == 0:
            return "nothing to sync"
        # A pathspec on commit takes ONLY those paths, even if something else
        # in the worktree happens to be staged.
        git(root, "commit", "-m", message, "--", spec, check=True)
        sha = git(root, "rev-parse", "--short", "HEAD").stdout.strip()
        # Explicit refspec: the worktree may track origin/main.
        if git(root, "push", "-u", "origin", f"HEAD:refs/heads/{branch}").returncode == 0:
            return f"pushed {sha} to {branch}"
        return f"failed: committed {sha} on {branch} locally, push rejected"
    except (OSError, RuntimeError) as exc:
        return f"failed: {exc}"


def main():
    ap = argparse.ArgumentParser(description="Publish a spec folder on its feature branch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="commit + push specs/<feature>/ on the feature branch")
    s.add_argument("feature_dir", nargs="?", help="specs/NNN-name (default: .specify/feature.json)")
    s.add_argument("-m", "--message", help="commit message")
    args = ap.parse_args()

    from speckit_rounds import resolve_feature_dir
    feature_dir = resolve_feature_dir(args.feature_dir)
    msg = args.message or f"spec({feature_dir.name}): sync spec folder"
    print(f"[INFO] spec sync: {sync_spec(feature_dir, msg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
