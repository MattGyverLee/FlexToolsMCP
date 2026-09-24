#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The CP4 filing path, against live FieldWorks projects (parser-check CP4, US5;
specs/parser-check-cp4/quickstart.md).

THIS MODULE MAY WRITE -- BUT ONLY TO A DISPOSABLE COPY. CP4 is the first
parser-check checkpoint with a write path, and FR-037 confines every live
write test to a project named `CP4-Scratch-<...>`, copied fresh from a
designated source by `tests/live_support/make_disposable.py` and deleted
afterwards. The `scratch` fixture below is the only way a test here gets a
project name, and it refuses any name without the prefix -- twice: once when
the copy is made, and again on the name handed to the test. A working project
is never opened by this module, not even read only.

THE DESIGNATED SOURCES, and why `Sena 3` is not one of them (as in CP3):

    IndonesianHC-Complete           correctness. The parity group (T081) and
                                    scenarios 1-5, 7 and 8.
    Malay Parsing-20230810withHC    scale. Scenario 6 (concurrency).

    Sena 3                          EXCLUDED BY NAME. It uses the XAmple
                                    engine, which filing refuses before a
                                    parser is built; substituting it would
                                    test the refusal, not the feature.

THE LIVE GATE. On a machine without FieldWorks, or without a designated
source project, every test here SKIPS -- unless `FLEXLIBS_REQUIRE_LIVE=1`, in
which case a missing prerequisite FAILS (quickstart, Prerequisites). The CI
live job sets it, so a silently empty live run cannot report green.

Evidence goes to `specs/parser-check-cp4/evidence/` and NEVER into a project
folder (FR-042).

Task mapping (specs/parser-check-cp4/tasks.md Phase 8):

    T080    this module: the marker, the scratch fixture, the live gate
    T081    the parity group: the eligibility port agrees with the loader
    T082-4  quickstart scenarios 1-8, run by a maintainer on a live host;
            several steps need a human editing the copy in FieldWorks (break
            a rule, empty a form) or killing the server mid-run, so their
            evidence is recorded by hand under the same evidence directory

Deselect on a machine without FieldWorks with `-m "not requires_flex"`.
"""

import contextlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.requires_flex

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent / "live_support"))

from make_disposable import (  # noqa: E402
    SCRATCH_PREFIX,
    NotDisposable,
    delete_disposable,
    is_disposable_name,
    make_disposable,
    projects_dir,
    require_disposable,
)

#: The correctness source.
HC_PROJECT = os.environ.get("FLEXTOOLSMCP_LIVE_HC_PROJECT", "IndonesianHC-Complete")

#: The scale source (scenario 6).
SCALE_PROJECT = os.environ.get(
    "FLEXTOOLSMCP_LIVE_SCALE_PROJECT", "Malay Parsing-20230810withHC"
)

#: Named here so the exclusion is greppable. Nothing in this module opens it.
EXCLUDED_XAMPLE_PROJECT = "Sena 3"

EVIDENCE_DIR = REPO_ROOT / "specs" / "parser-check-cp4" / "evidence"

#: One live probe may load a whole grammar; generous, but not unbounded.
_PROBE_TIMEOUT = 900


def _require_live() -> bool:
    return os.environ.get("FLEXLIBS_REQUIRE_LIVE") == "1"


def _missing(reason: str):
    """Skip -- or, under `FLEXLIBS_REQUIRE_LIVE=1`, fail -- a live prerequisite."""
    if _require_live():
        pytest.fail(f"live prerequisite missing (FLEXLIBS_REQUIRE_LIVE=1): {reason}")
    pytest.skip(reason)


def _evidence(name, payload):
    """Write one scenario's evidence, stamped, beside the spec (FR-042)."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    payload = dict(payload, recorded_at=datetime.now(timezone.utc).isoformat())
    (EVIDENCE_DIR / f"{name}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )


def _live_prerequisites(source: str) -> Path:
    """FieldWorks, a live flexicon, and the source project -- or skip/fail."""
    if sys.platform != "win32":
        _missing("live filing tests need Windows with FieldWorks installed")
    try:
        import flexicon  # noqa: F401
    except Exception as exc:  # noqa: BLE001 -- flexicon raises non-ImportError without FieldWorks
        _missing(f"flexicon unavailable (no live FieldWorks install?): {exc}")
    try:
        root = projects_dir()
    except FileNotFoundError as exc:
        _missing(str(exc))
    if not (root / source / f"{source}.fwdata").is_file():
        _missing(f"designated source project {source!r} is not installed under {root}")
    return root


@contextlib.contextmanager
def _scratch_copy(source: str):
    """A fresh `CP4-Scratch-` copy of `source`, deleted afterwards (FR-037).

    Keep it for inspection with `FLEXTOOLSMCP_LIVE_KEEP_SCRATCH=1`; teardown
    refuses any name without the prefix, whatever happens above it.
    """
    if source == EXCLUDED_XAMPLE_PROJECT:
        pytest.fail(f"{EXCLUDED_XAMPLE_PROJECT!r} is excluded; it is never a source.")
    root = _live_prerequisites(source)
    copy = make_disposable(source, root=root)
    try:
        yield require_disposable(copy.name)
    finally:
        if os.environ.get("FLEXTOOLSMCP_LIVE_KEEP_SCRATCH") != "1":
            delete_disposable(copy.name, root=root)


@pytest.fixture(scope="module")
def scratch():
    """The correctness project's scratch copy -- the only project name a test gets."""
    with _scratch_copy(HC_PROJECT) as name:
        yield name


# ---------------------------------------------------------------------------
# The guards (they need no project, but live here so they travel with it)
# ---------------------------------------------------------------------------


def test_the_excluded_project_is_never_a_source():
    assert HC_PROJECT != EXCLUDED_XAMPLE_PROJECT
    assert SCALE_PROJECT != EXCLUDED_XAMPLE_PROJECT


def test_no_designated_source_is_itself_a_scratch_name():
    """A source named CP4-Scratch-* would be a copy of a copy: stale state."""
    assert not is_disposable_name(HC_PROJECT)
    assert not is_disposable_name(SCALE_PROJECT)


@pytest.mark.parametrize("name", [HC_PROJECT, SCALE_PROJECT, EXCLUDED_XAMPLE_PROJECT,
                                  "", SCRATCH_PREFIX, "cp4-scratch-lowercase"])
def test_a_working_project_name_is_refused(name):
    with pytest.raises(NotDisposable):
        require_disposable(name)
    with pytest.raises(NotDisposable):
        delete_disposable(name)


def test_the_live_gate_turns_a_missing_prerequisite_into_a_failure(monkeypatch):
    monkeypatch.setenv("FLEXLIBS_REQUIRE_LIVE", "1")
    with pytest.raises(pytest.fail.Exception):
        _missing("probe")
    monkeypatch.delenv("FLEXLIBS_REQUIRE_LIVE")
    with pytest.raises(pytest.skip.Exception):
        _missing("probe")


# ---------------------------------------------------------------------------
# T081 -- the parity group: the eligibility port agrees with the loader
# ---------------------------------------------------------------------------


def _run_parity_probe(project_name: str) -> dict:
    require_disposable(project_name)
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).parent / "live_support" / "parity_probe.py"),
         project_name],
        capture_output=True, text=True, encoding="utf-8", timeout=_PROBE_TIMEOUT,
        env=dict(os.environ, PYTHONPATH=str(REPO_ROOT / "src")),
    )
    lines = [ln for ln in completed.stdout.splitlines() if ln.startswith("{")]
    assert completed.returncode == 0 and lines, (
        f"parity probe failed (rc={completed.returncode}):\n"
        f"{completed.stderr[-4000:]}\n{completed.stdout[-2000:]}"
    )
    return json.loads(lines[-1])


def test_t081_the_eligibility_port_matches_the_loaded_grammar(scratch):
    """Principle VI's mitigation: the port and `HCLoader` agree, entry for entry.

    Count equality is the task's letter; set equality is asserted because two
    offsetting disagreements would pass a count and still mis-name the
    entries FR-039 reports as dropped.
    """
    result = _run_parity_probe(scratch)
    _evidence("t081-eligibility-parity", {"source": HC_PROJECT, **result})
    assert result["port_count"] == result["loader_count"], result
    assert result["agree"], (
        f"port-only: {result['port_only'][:20]}; loader-only: {result['loader_only'][:20]}"
    )


def test_t081_parity_holds_on_the_scale_project_too():
    """The correctness project loads one affix rule; the scale project's much
    larger lexicon exercises the port's rule-side branches as well."""
    with _scratch_copy(SCALE_PROJECT) as name:
        result = _run_parity_probe(name)
    _evidence("t081-eligibility-parity-scale", {"source": SCALE_PROJECT, **result})
    assert result["port_count"] == result["loader_count"], result
    assert result["agree"], (
        f"port-only: {result['port_only'][:20]}; loader-only: {result['loader_only'][:20]}"
    )
