#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dependency cap canary -- "is any upper bound now holding us back?"

Upper bounds on runtime deps (mcp>=1.27.0,<2, pyflexicon<5, flexlibs<2) protect
fresh installs from the mcp-2.0.0 class of break, where 11 releases shipped
broken because an uncapped `>=` silently resolved to an incompatible major.
See specs/mcp2-compat/.

But a cap with no review process is just deferred rot: Dependabot is
configured to track development dependencies only (.github/dependabot.yml),
precisely because runtime deps are capped -- so nothing tells us when a cap
has started excluding a release we could actually use.

This script closes that loop. For every capped runtime dependency it asks
PyPI for the latest stable release and reports whether our specifier
excludes it. .github/workflows/dep-cap-canary.yml runs it monthly, then
installs the excluded versions and runs the test suite against them, so the
answer to "can we raise this cap?" arrives already tested.

Usage:
    python scripts/cap_canary.py              # human-readable report
    python scripts/cap_canary.py --markdown   # GitHub issue body
    python scripts/cap_canary.py --json       # machine-readable

Exit codes:
    0  no capped dependency is excluding a newer release (nothing to do)
    1  at least one cap is now excluding a newer release (review needed)
    2  the check itself failed (network, parse error) -- not a verdict
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:  # py3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py3.10 local runs
    tomllib = None

from packaging.requirements import Requirement
from packaging.version import InvalidVersion, Version

REPO_ROOT = Path(__file__).parent.parent
PYPI_URL = "https://pypi.org/pypi/{name}/json"
TIMEOUT = 30

# Deps whose cap exists for a reason we already understand and do not want
# re-litigated every month. The canary still reports them, but flags them as
# expected rather than actionable.
KNOWN_INTENTIONAL_CAPS = {
    "mcp": (
        "2.0.0 removed the low-level Server decorator API. Dual 1.x/2.x "
        "support is tracked in issue #83; see "
        "specs/mcp2-compat/dual-support-analysis.md."
    ),
}


def read_runtime_dependencies() -> list[str]:
    """Return the raw dependency strings from [project].dependencies."""
    pyproject = REPO_ROOT / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")

    if tomllib is not None:
        return tomllib.loads(text)["project"]["dependencies"]

    # py3.10 fallback: the dependencies array is a flat list of quoted
    # strings; `#` comments live outside quotes so quote-matching is safe.
    block = re.search(r"^dependencies\s*=\s*\[(.*?)^\]", text, re.S | re.M)
    if not block:
        raise ValueError("Could not locate [project].dependencies in pyproject.toml")
    return re.findall(r'"([^"]+)"', block.group(1))


def latest_stable_version(name: str) -> Version:
    """Latest non-prerelease, non-yanked release on PyPI."""
    with urllib.request.urlopen(PYPI_URL.format(name=name), timeout=TIMEOUT) as resp:
        payload = json.load(resp)

    candidates = []
    for raw, files in payload.get("releases", {}).items():
        if not files or all(f.get("yanked") for f in files):
            continue  # no artifacts, or every artifact yanked
        try:
            parsed = Version(raw)
        except InvalidVersion:
            continue
        if parsed.is_prerelease or parsed.is_devrelease:
            continue
        candidates.append(parsed)

    if not candidates:
        raise ValueError(f"No stable releases found for {name}")
    return max(candidates)


def audit() -> dict:
    """Compare every capped runtime dep against the latest release on PyPI."""
    results = {"blocked": [], "current": [], "uncapped": [], "errors": []}

    for raw in read_runtime_dependencies():
        req = Requirement(raw)
        has_upper_bound = any(
            spec.operator in ("<", "<=", "==", "~=") for spec in req.specifier
        )

        if not has_upper_bound:
            # Deferred issue 2 in specs/mcp2-compat/deferred-issues.md tracks
            # capping these; until then they carry the uncapped risk instead.
            results["uncapped"].append({"name": req.name, "requirement": raw})
            continue

        try:
            latest = latest_stable_version(req.name)
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            results["errors"].append({"name": req.name, "error": str(exc)})
            continue

        entry = {
            "name": req.name,
            "requirement": raw,
            "specifier": str(req.specifier),
            "latest": str(latest),
            "note": KNOWN_INTENTIONAL_CAPS.get(req.name),
        }
        # prereleases=False: a cap "blocking" only an alpha is not news.
        if req.specifier.contains(latest, prereleases=False):
            results["current"].append(entry)
        else:
            results["blocked"].append(entry)

    return results


def render_text(results: dict) -> str:
    lines = ["Dependency cap canary", "=" * 21, ""]

    if results["blocked"]:
        lines.append("[REVIEW] Caps now excluding a newer stable release:")
        for e in results["blocked"]:
            lines.append(f"  - {e['name']}: pinned {e['specifier']}, latest is {e['latest']}")
            if e["note"]:
                lines.append(f"      note: {e['note']}")
    else:
        lines.append("[OK] No cap is excluding a newer stable release.")

    if results["current"]:
        lines.append("")
        lines.append("[OK] Caps still admitting the latest release:")
        for e in results["current"]:
            lines.append(f"  - {e['name']}: {e['specifier']} admits {e['latest']}")

    if results["uncapped"]:
        lines.append("")
        lines.append("[INFO] Uncapped runtime deps (deferred issue 2):")
        for e in results["uncapped"]:
            lines.append(f"  - {e['requirement']}")

    if results["errors"]:
        lines.append("")
        lines.append("[WARN] Could not check:")
        for e in results["errors"]:
            lines.append(f"  - {e['name']}: {e['error']}")

    return "\n".join(lines)


def render_markdown(results: dict) -> str:
    lines = [
        "<!-- managed by scripts/cap_canary.py -- body is rewritten each run -->",
        "## Dependency cap review",
        "",
        "Upper bounds keep fresh installs safe (see `specs/mcp2-compat/`), but a",
        "cap nobody revisits is deferred rot. This issue is rewritten by the",
        "monthly `dep-cap-canary` workflow; the test verdict below says whether",
        "the excluded version actually works.",
        "",
    ]

    if results["blocked"]:
        lines += [
            "### Caps excluding a newer stable release",
            "",
            "| Dependency | Our specifier | Latest on PyPI | Known reason |",
            "|---|---|---|---|",
        ]
        for e in results["blocked"]:
            lines.append(
                f"| `{e['name']}` | `{e['specifier']}` | `{e['latest']}` | "
                f"{e['note'] or '_none recorded -- review_' } |"
            )
    else:
        lines += ["### No cap is excluding a newer stable release", "",
                  "Nothing to review this cycle."]

    if results["uncapped"]:
        lines += ["", "### Still uncapped", "",
                  "Tracked in deferred issue 2 (`specs/mcp2-compat/deferred-issues.md`):",
                  ""]
        lines += [f"- `{e['requirement']}`" for e in results["uncapped"]]

    if results["errors"]:
        lines += ["", "### Could not check", ""]
        lines += [f"- `{e['name']}`: {e['error']}" for e in results["errors"]]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--markdown", action="store_true", help="GitHub issue body")
    args = parser.parse_args()

    try:
        results = audit()
    except Exception as exc:  # parse failure, unreadable pyproject, etc.
        print(f"[ERROR] cap canary could not run: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(results, indent=2))
    elif args.markdown:
        print(render_markdown(results))
    else:
        print(render_text(results))

    return 1 if results["blocked"] else 0


if __name__ == "__main__":
    sys.exit(main())
