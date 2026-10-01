#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The shipped flexicon index matches what the generator produces.

Issue #306 follow-up: flags in flexicon_api_v<ver>.json have been
hand-patched (policy: never commit a regenerate against an unreleased
flexicon), so nothing stopped the JSON and flexicon_analyzer from drifting
apart. This runs analyze_flexicon() -- pure AST, no `import flexicon` -- on
the installed flexicon and asserts per-method equality on the fields the
generator owns. Refresh-time annotations (python_wrappers, common_patterns,
element_type, collection_contract, polymorphic, deprecation, lcm_mapping)
are excluded.

Runs only when the installed pyflexicon distribution's version equals the
shipped file's `_source.version`. The version detected from the source tree
cannot be the gate: a development checkout past a release still reports the
release number. Set FLEXTOOLSMCP_DRIFT_FLEXICON_ROOT to a directory holding
flexicon/code (e.g. `git archive v4.11.0` of the flexicon repo) to check a
specific tree; its detected version must then match the shipped file.
"""

import contextlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path

import pytest

from flextoolsmcp.flexicon_analyzer import analyze_flexicon, detect_flexicon_version

INDEX_DIR = Path(__file__).resolve().parent.parent / "src" / "flextoolsmcp" / "index" / "python"

#: Method fields analyze_flexicon owns outright.
GENERATOR_FIELDS = (
    "is_mutating", "return_type", "signature", "usage_hint", "parameters",
    "summary", "description", "is_property", "is_classmethod", "is_staticmethod",
)

ENV_ROOT = "FLEXTOOLSMCP_DRIFT_FLEXICON_ROOT"


def _shipped_files():
    return sorted(INDEX_DIR.glob("flexicon_api_v*.json"))


def _installed_root():
    """Directory containing flexicon/code, found without importing flexicon
    (its __init__ needs FieldWorks; see test_issue134's probe)."""
    try:
        spec = importlib.util.find_spec("flexicon")
    except Exception:  # noqa: BLE001
        return None
    if spec is None or not spec.origin:
        return None
    root = Path(spec.origin).resolve().parent.parent
    return root if (root / "flexicon" / "code").is_dir() else None


def _target():
    """(root, version) to compare against, or a skip reason string."""
    override = os.environ.get(ENV_ROOT)
    if override:
        root = Path(override)
        if not (root / "flexicon" / "code").is_dir():
            return f"{ENV_ROOT}={override} has no flexicon/code"
        return root, detect_flexicon_version(str(root))
    root = _installed_root()
    if root is None:
        return "flexicon is not installed"
    try:
        dist_version = importlib.metadata.version("pyflexicon")
    except importlib.metadata.PackageNotFoundError:
        return "pyflexicon distribution metadata not found"
    return root, dist_version


def _method_map(data):
    out = {}
    for cls, entity in data["entities"].items():
        for m in entity.get("methods", []) or []:
            out[(cls, m["name"])] = m
    return out


def test_shipped_index_matches_generator():
    target = _target()
    if isinstance(target, str):
        pytest.skip(target)
    root, version = target
    shipped_path = INDEX_DIR / f"flexicon_api_v{version}.json"
    if not shipped_path.exists():
        shipped = [p.name for p in _shipped_files()]
        pytest.skip(f"installed flexicon {version} has no shipped index (shipped: {shipped})")

    shipped = json.loads(shipped_path.read_text(encoding="utf-8"))
    assert shipped["_source"]["version"] == version

    with contextlib.redirect_stdout(io.StringIO()):
        generated = analyze_flexicon(str(root))

    want, got = _method_map(shipped), _method_map(generated)
    assert set(got) == set(want), {
        "only_in_generated": sorted(set(got) - set(want))[:20],
        "only_in_shipped": sorted(set(want) - set(got))[:20],
    }
    drift = [
        (cls, name, field, want[(cls, name)].get(field), got[(cls, name)].get(field))
        for (cls, name) in sorted(want)
        for field in GENERATOR_FIELDS
        if want[(cls, name)].get(field) != got[(cls, name)].get(field)
    ]
    assert not drift, f"{len(drift)} generator-owned field(s) drifted, first: {drift[:10]}"
