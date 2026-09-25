#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upstream flag watch -- "has upstream started respecting a field we block?"

Some curated deprecations (src/flextoolsmcp/curated_deprecations.py) are
temporary: the member exists but upstream ignores it today, so the MCP
refuses it and redirects elsewhere. DoNotUseForParsing is the first one
(LT-22810): neither FLEx parser reads it, so the MCP steers to
IMoForm.IsAbstract instead -- but FLEx may implement it, with no timeline.

A block with no review process is deferred rot, so this script watches
upstream for the term. For every deprecation carrying an ``upstream_watch``
block it asks GitHub for:

  - code on each watched repo's default branch mentioning the term, outside
    the recorded baseline paths (a new consumer, e.g. HCLoader.cs);
  - PRs and issues in those repos mentioning it, outside ``baseline_refs``;
  - commits in those repos mentioning it.

Anything new is a sign the block may be ready to lift -- a human decides.
.github/workflows/upstream-flag-watch.yml runs it weekly and keeps one
sticky issue per deprecation, commenting (i.e. notifying) only when a
finding appears that the issue has not already reported.

GitHub code search indexes default branches only and skips very large
files, so treat a quiet run as "nothing obvious", not proof.

Usage:
    python scripts/upstream_flag_watch.py              # human-readable report
    python scripts/upstream_flag_watch.py --json       # machine-readable
    python scripts/upstream_flag_watch.py --sync-issue # open/update the issue

Exit codes:
    0  nothing new upstream
    1  at least one new finding (review needed)
    2  the check itself failed (auth, network, rate limit) -- not a verdict
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.curated_deprecations import CURATED_DEPRECATIONS  # noqa: E402

LABEL = "upstream-flag-watch"
SEEN_RE = re.compile(r"<!-- upstream-flag-watch:seen=(\[.*?\]) -->", re.S)


class WatchError(RuntimeError):
    """The check could not run -- distinct from a finding."""


def _gh(args: List[str]) -> str:
    try:
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, encoding="utf-8", timeout=120
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise WatchError(f"gh {' '.join(args[:3])}: {e}") from e
    if proc.returncode != 0:
        raise WatchError(f"gh {' '.join(args[:3])} failed: {proc.stderr.strip()}")
    return proc.stdout


def _search(kind: str, query: str) -> List[Dict[str, Any]]:
    """One page (100) of a REST search; the terms watched here are rare."""
    out = _gh(["api", "-X", "GET", f"search/{kind}", "-f", f"q={query}", "-f", "per_page=100"])
    data = json.loads(out)
    if data.get("incomplete_results"):
        raise WatchError(f"search/{kind} returned incomplete results for {query!r}")
    return data.get("items", [])


def watches() -> Dict[str, Dict[str, Any]]:
    return {
        dep_id: dep
        for dep_id, dep in CURATED_DEPRECATIONS.items()
        if dep.get("upstream_watch")
    }


def scan(dep_id: str, dep: Dict[str, Any]) -> List[Dict[str, str]]:
    """Every finding for one deprecation, baseline already excluded."""
    watch = dep["upstream_watch"]
    term = watch["term"]
    repos: Dict[str, List[str]] = watch["repos"]
    baseline_refs = set(watch.get("baseline_refs", []))
    findings: List[Dict[str, str]] = []

    for repo, baseline in repos.items():
        allowed = set(baseline)
        for item in _search("code", f"{term} repo:{repo}"):
            path = item["path"]
            if path not in allowed:
                findings.append({
                    "key": f"code:{repo}:{path}",
                    "kind": "code",
                    "repo": repo,
                    "title": path,
                    "url": item.get("html_url", f"https://github.com/{repo}"),
                })

    repo_q = " ".join(f"repo:{r}" for r in repos)
    for item in _search("issues", f"{term} {repo_q}"):
        url = item["html_url"]
        if url in baseline_refs:
            continue
        kind = "pr" if "pull_request" in item else "issue"
        findings.append({
            "key": f"{kind}:{url}",
            "kind": kind,
            "repo": item["repository_url"].split("/repos/", 1)[-1],
            "title": f"{item['title']} ({item['state']})",
            "url": url,
        })

    for item in _search("commits", f"{term} {repo_q}"):
        url = item["html_url"]
        if url in baseline_refs:
            continue
        findings.append({
            "key": f"commit:{url}",
            "kind": "commit",
            "repo": item["repository"]["full_name"],
            "title": item["commit"]["message"].splitlines()[0],
            "url": url,
        })
    return findings


def _issue_title(dep_id: str, dep: Dict[str, Any]) -> str:
    term = dep["upstream_watch"]["term"]
    ticket = dep.get("tracking", {}).get("ticket")
    suffix = f" ({ticket})" if ticket else ""
    return f"Upstream watch: {term} may be ready to unblock{suffix} [{dep_id}]"


def render_markdown(dep_id: str, dep: Dict[str, Any], findings: List[Dict[str, str]]) -> str:
    watch = dep["upstream_watch"]
    tracking = dep.get("tracking", {})
    lines = [
        f"The MCP refuses `{watch['term']}` (curated deprecation `{dep_id}`) because "
        "upstream ignores it today. Upstream now mentions it somewhere new -- check "
        "whether FLEx and the parsers respect it yet.",
        "",
    ]
    if tracking:
        lines += [
            f"- Tracking: [{tracking['ticket']}]({tracking['url']})",
            f"- Unblock when: {tracking['unblock_when']}",
            "",
        ]
    lines += ["### Findings", ""]
    for f in findings:
        lines.append(f"- **{f['kind']}** `{f['repo']}` -- [{f['title']}]({f['url']})")
    lines += [
        "",
        "### If the block can be lifted",
        "",
        f"1. Delete `{dep_id}` from `CURATED_DEPRECATIONS` and its `MISPLACED_MEMBERS` "
        "row in `src/flextoolsmcp/curated_deprecations.py`.",
        "2. Re-apply the indexes: `python -m flextoolsmcp.curated_deprecations --apply` "
        "(or a full index refresh), and update the affected tests/goldens.",
        "3. Close this issue.",
        "",
        "### If it is a false alarm",
        "",
        "Add the path to `upstream_watch.repos` (or the URL to `baseline_refs`) so it "
        "stops being reported, and leave this issue open or close it.",
    ]
    return "\n".join(lines)


def _seen_keys(body: str) -> List[str]:
    m = SEEN_RE.search(body or "")
    return json.loads(m.group(1)) if m else []


def sync_issue(dep_id: str, dep: Dict[str, Any], findings: List[Dict[str, str]],
               run_link: Optional[str]) -> str:
    """Open, or update, the sticky issue. Returns what happened."""
    title = _issue_title(dep_id, dep)
    listing = json.loads(_gh([
        "issue", "list", "--label", LABEL, "--state", "open",
        "--json", "number,title,body", "--limit", "100",
    ]))
    existing = next((i for i in listing if f"[{dep_id}]" in i["title"]), None)

    seen = set(_seen_keys(existing["body"])) if existing else set()
    new = [f for f in findings if f["key"] not in seen]
    all_keys = sorted(seen | {f["key"] for f in findings})

    body = render_markdown(dep_id, dep, findings)
    if run_link:
        body += f"\n\n---\n_Last run: {run_link} -- rerun any time via workflow_dispatch._"
    body += f"\n\n<!-- upstream-flag-watch:seen={json.dumps(all_keys)} -->\n"

    if existing is None:
        if not _label_exists():
            _gh(["label", "create", LABEL, "--description",
                 "Automated watch for upstream changes that could lift a curated deprecation",
                 "--color", "d93f0b"])
        _gh(["issue", "create", "--title", title, "--label", LABEL, "--body", body])
        return "created"

    num = str(existing["number"])
    _gh(["issue", "edit", num, "--body", body])
    if new:
        lines = ["New upstream mentions since this issue was last updated:", ""]
        lines += [f"- **{f['kind']}** `{f['repo']}` -- [{f['title']}]({f['url']})" for f in new]
        _gh(["issue", "comment", num, "--body", "\n".join(lines)])
        return f"commented on #{num}"
    return f"refreshed #{num} (nothing new)"


def _label_exists() -> bool:
    labels = json.loads(_gh(["label", "list", "--json", "name", "--limit", "200"]))
    return any(lbl["name"] == LABEL for lbl in labels)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--sync-issue", action="store_true",
                    help="open/update one sticky issue per deprecation with findings")
    ap.add_argument("--run-link", help="link to this run, appended to the issue body")
    args = ap.parse_args(argv)

    try:
        results = {dep_id: scan(dep_id, dep) for dep_id, dep in watches().items()}
        actions = {}
        if args.sync_issue:
            for dep_id, findings in results.items():
                if findings:
                    actions[dep_id] = sync_issue(dep_id, CURATED_DEPRECATIONS[dep_id],
                                                 findings, args.run_link)
    except WatchError as e:
        print(f"upstream_flag_watch: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"findings": results, "issue_actions": actions}, indent=2))
    else:
        for dep_id, findings in results.items():
            print(f"{dep_id}: {len(findings)} new finding(s)")
            for f in findings:
                print(f"  - {f['kind']:6} {f['repo']}: {f['title']}  {f['url']}")
            if dep_id in actions:
                print(f"  issue: {actions[dep_id]}")
    return 1 if any(results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
