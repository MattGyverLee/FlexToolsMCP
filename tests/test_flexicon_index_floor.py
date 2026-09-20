#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CP2a-bridge -- the declared pyflexicon floor, the version the server actually
resolves, and every bundled flexicon-version-locked index artifact must all
name the same version.

WHY THIS FILE EXISTS (parser-check CP2a-bridge, FR-011, SC-013)

CP2a shipped a new parser surface in `flexicon` and released it as 4.9.0.
This repository bundles a *generated index* of that surface, and declares a
*floor* for the package. Three things therefore carry a flexicon version, and
nothing previously forced them to agree:

  1. the declared floor      -- `pyproject.toml` / `requirements.txt`
  2. the resolved version    -- what `server/versioning.py` actually detects
  3. the bundled artifacts   -- `index/**/...flexicon...v<X.Y.Z>.json`

A disagreement here is silent, and it is the bad kind of silent: the server
loads an index describing a surface the installed library does not have, and
the failure surfaces much later as a missing attribute in generated user
code. So this file fails loudly, at test time, naming *which* of the three
disagrees.

TWO DESIGN CONSTRAINTS, BOTH DELIBERATE

(a) The resolved version is what `versioning.py` resolves, NOT
`importlib.metadata`. These genuinely differ in the normal development setup
here: `flexicon` is on `sys.path` from a working tree while pip metadata
describes an older installed wheel. At the time this file was written
`versioning.py` resolved 4.9.0 while `importlib.metadata` read 4.8.0 -- both
correct answers to different questions. `versioning.py`'s answer is the one
that governs which index the server loads (it is live-module-first by
design, see issue #38), so it is the only one worth asserting against.
Asserting `importlib.metadata` here would make this file red on a correct
tree, and the reflex fix would be to delete it.

(b) Artifacts are DISCOVERED BY PATTERN, never hardcoded. The Verbatim
Constraints name two artifacts; there are three. `common_patterns_flexicon-
v<ver>.json` sits one directory up from the other two and uses a `-v`
separator where they use `_v`. A hardcoded pair would have silently ignored
the third forever. Anything that grows a fourth is picked up for free.

Because the sweep is discovery-based it can fail *vacuously*: a broken
pattern discovers nothing and every equality assertion below then passes
over an empty set. `test_discovery_is_not_vacuous` guards exactly that and
must not be deleted.

A LIBLCM REGENERATION SKIP MUST NOT FAIL THIS FILE. `python -m
flextoolsmcp.refresh` skips LibLCM gracefully when FieldWorks / pythonnet is
unavailable, leaving the shipped `*_liblcm-v11.0.0.json` artifacts at
whatever version they were. Those are not flexicon-locked and are excluded
from the sweep; `test_liblcm_artifacts_are_not_swept` pins that exclusion so
the guarantee is structural rather than incidental.

Run with:
    python -m pytest tests/test_flexicon_index_floor.py -q
"""

import re
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
INDEX_DIR = REPO_ROOT / "src" / "flextoolsmcp" / "index"

sys.path.insert(0, str(REPO_ROOT / "src"))

# A bundled artifact is flexicon-version-locked when its stem mentions
# flexicon AND ends in a `_v` / `-v` semver suffix. Both separators are live
# in the tree today; matching only one is the bug this pattern exists to
# avoid. "flexlibs" does not contain "flexicon", so the stable-FlexLibs
# artifacts fall out on their own.
_VERSION_SUFFIX = re.compile(r"[_-]v(\d+\.\d+\.\d+)$")

# Generated artifacts are archived rather than deleted when a refresh moves
# the version on. Archived files keep their OLD version suffix by design, so
# sweeping them would make every refresh red.
_EXCLUDED_DIRS = {"archive", "__pycache__"}

# The three artifact families known to be flexicon-locked at the time of
# writing. Used ONLY as a vacuity floor -- the assertions themselves run over
# whatever is discovered, so a fourth family needs no edit here.
_KNOWN_FAMILIES = {
    "flexicon_api",
    "flexicon_lcm_bridge",
    "common_patterns_flexicon",
}


def _discover_flexicon_artifacts() -> list[tuple[Path, str]]:
    """Every live flexicon-version-locked index artifact, as (path, version)."""
    found: list[tuple[Path, str]] = []
    for path in INDEX_DIR.rglob("*.json"):
        if _EXCLUDED_DIRS & {parent.name for parent in path.parents}:
            continue
        stem = path.stem
        if "flexicon" not in stem.lower():
            continue
        match = _VERSION_SUFFIX.search(stem)
        if match:
            found.append((path, match.group(1)))
    return sorted(found)


def _family_of(path: Path) -> str:
    """The artifact family -- the stem with its version suffix stripped."""
    return _VERSION_SUFFIX.sub("", path.stem)


def _floor_from(text: str, source: str) -> str:
    """The lower bound of the pyflexicon requirement, e.g. '4.9.0'."""
    match = re.search(r"pyflexicon\s*>=\s*(\d+\.\d+\.\d+)", text)
    assert match, f"No pinned 'pyflexicon>=X.Y.Z' requirement found in {source}"
    return match.group(1)


def _pyproject_floor() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    for dep in data.get("project", {}).get("dependencies", []):
        if "pyflexicon" in dep:
            return _floor_from(dep, "pyproject.toml")
    pytest.fail("No 'pyflexicon' entry in pyproject.toml [project].dependencies")


def _requirements_floor() -> str:
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    line = next(
        (ln for ln in text.splitlines() if ln.strip().startswith("pyflexicon")),
        None,
    )
    assert line, "No 'pyflexicon' line in requirements.txt"
    return _floor_from(line, "requirements.txt")


def _resolved_version() -> str | None:
    """What server/versioning.py actually resolves -- live module first."""
    from flextoolsmcp.server.versioning import detect_installed_library_version

    return detect_installed_library_version(
        "Flexicon", import_path="flexicon", package_name="pyflexicon"
    )


# ---------------------------------------------------------------------------
# Vacuity and scope guards -- these protect the assertions below from
# passing over an empty or wrongly-populated set.
# ---------------------------------------------------------------------------


def test_discovery_is_not_vacuous():
    """The sweep must actually find the known flexicon artifact families.

    A discovery-based equality test whose pattern has broken discovers
    nothing and then passes every other assertion in this file trivially.
    That failure mode is invisible in a green run, so it is asserted here
    directly rather than left to be noticed.
    """
    artifacts = _discover_flexicon_artifacts()
    assert artifacts, (
        f"Discovered NO flexicon-version-locked artifacts under {INDEX_DIR}. "
        f"Every equality assertion in this file would now pass vacuously. "
        f"The discovery pattern is broken, or the index was never generated."
    )
    families = {_family_of(path) for path, _ in artifacts}
    missing = _KNOWN_FAMILIES - families
    assert not missing, (
        f"Discovery lost known flexicon artifact families: {sorted(missing)}. "
        f"Found: {sorted(families)}. Either an artifact was deleted or the "
        f"'_v' / '-v' separator handling regressed (common_patterns_flexicon "
        f"uses '-v', the other two use '_v')."
    )


def test_liblcm_artifacts_are_not_swept():
    """LibLCM-locked artifacts must stay out of the flexicon sweep.

    `python -m flextoolsmcp.refresh` skips LibLCM gracefully when FieldWorks
    or pythonnet is unavailable, leaving those artifacts at a version that
    has nothing to do with the pyflexicon floor. If they were swept in, a
    headless refresh would make this file red for a reason it cannot act on.
    """
    swept = [path for path, _ in _discover_flexicon_artifacts()]
    liblcm = [p for p in swept if "liblcm" in p.stem.lower()]
    assert not liblcm, (
        f"LibLCM-locked artifacts were swept into the flexicon floor check: "
        f"{[p.name for p in liblcm]}. A LibLCM regeneration skip must not be "
        f"able to fail this file."
    )
    flexlibs = [p for p in swept if "flexlibs" in p.stem.lower()]
    assert not flexlibs, (
        f"Stable-FlexLibs artifacts were swept into the flexicon floor check: "
        f"{[p.name for p in flexlibs]}. They carry their own, unrelated "
        f"version line."
    )


# ---------------------------------------------------------------------------
# The three-way equality itself.
# ---------------------------------------------------------------------------


def test_pyproject_and_requirements_floors_agree():
    """The floor is declared twice; both declarations must say the same thing."""
    pyproject, requirements = _pyproject_floor(), _requirements_floor()
    assert pyproject == requirements, (
        f"DECLARED FLOOR disagrees with itself: pyproject.toml says "
        f"pyflexicon>={pyproject} but requirements.txt says >={requirements}. "
        f"Raise both together."
    )


def test_declared_floor_matches_every_bundled_artifact():
    """Floor vs artifacts -- the half that needs no flexicon on the path."""
    floor = _pyproject_floor()
    artifacts = _discover_flexicon_artifacts()
    mismatched = [(p, v) for p, v in artifacts if v != floor]
    assert not mismatched, (
        f"BUNDLED ARTIFACTS disagree with the DECLARED FLOOR "
        f"(pyflexicon>={floor}).\n"
        + "\n".join(
            f"  - {p.relative_to(REPO_ROOT)} is v{v}, expected v{floor}"
            for p, v in mismatched
        )
        + f"\n\n{len(artifacts) - len(mismatched)} of {len(artifacts)} "
        f"artifact(s) agree. Regenerate with `python -m flextoolsmcp.refresh` "
        f"or correct the declared floor -- whichever is actually wrong."
    )


def test_declared_floor_matches_resolved_version():
    """Floor vs what the server actually resolves.

    Skipped rather than failed when flexicon is not importable at all: with
    no library on the path there is no resolved version to compare, and the
    artifact/floor half above still runs.
    """
    resolved = _resolved_version()
    if resolved is None:
        pytest.skip(
            "flexicon is not importable here, so versioning.py resolves no "
            "version. The floor-vs-artifact assertion still ran."
        )
    floor = _pyproject_floor()
    assert resolved == floor, (
        f"RESOLVED VERSION disagrees with the DECLARED FLOOR: "
        f"server/versioning.py resolves flexicon v{resolved} but "
        f"pyproject.toml declares pyflexicon>={floor}.\n\n"
        f"Note this is deliberately NOT importlib.metadata, which can "
        f"legitimately differ (stale pip metadata against a working-tree "
        f"install). The resolved value is the one that decides which index "
        f"the server loads, so it is the one that must match."
    )


def test_resolved_version_matches_every_bundled_artifact():
    """Resolved vs artifacts -- the pairing that actually breaks user code.

    This is the third edge of the triangle. It is implied by the other two
    when both pass, but it is asserted separately so that a failure names
    *this* pairing: an index describing a surface the installed library does
    not have is precisely what produces a missing attribute in generated
    user code, far from here.
    """
    resolved = _resolved_version()
    if resolved is None:
        pytest.skip("flexicon is not importable here; nothing to resolve.")
    artifacts = _discover_flexicon_artifacts()
    mismatched = [(p, v) for p, v in artifacts if v != resolved]
    assert not mismatched, (
        f"BUNDLED ARTIFACTS disagree with the RESOLVED VERSION "
        f"(flexicon v{resolved} per server/versioning.py).\n"
        + "\n".join(
            f"  - {p.relative_to(REPO_ROOT)} is v{v}, expected v{resolved}"
            for p, v in mismatched
        )
        + "\n\nThe server would load an index describing a different surface "
        "than the library actually installed. Run "
        "`python -m flextoolsmcp.refresh`."
    )
