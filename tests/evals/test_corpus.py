#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tier-1 eval harness runner (issue #51).

Parametrized pytest over every YAML file in tests/evals/corpus/, driving the
preflight validator chain directly via `preflight_runner.run_preflight_chain`
(no LLM, no FieldWorks project, no subprocess). This is a HARD CI gate: a PR
that flips any `expect.outcome` for an existing corpus entry must update the
YAML in the same PR (that diff is the review artifact for gate-behavior
changes -- same philosophy as the index-diff gate in
docs/STABILIZATION-STRATEGY.md).

TODO(#49): switch to driving `run_module`'s `validate_only` mode once it
lands, instead of re-implementing the gate chain in preflight_runner.py.

Entries may set `skip: true` with a `skip_reason` string when the expectation
cannot be verified without a live FieldWorks project/subprocess, or is out of
this runner's modeled scope (see preflight_runner.py's module docstring).
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "flextoolsmcp"))
sys.path.insert(0, str(Path(__file__).parent))  # for `import preflight_runner`

from preflight_runner import run_preflight_chain  # noqa: E402

CORPUS_DIR = Path(__file__).parent / "corpus"

# All 12 preflight error codes the corpus must cover at least once (issue #51
# acceptance criteria). Enumerated from the ordered gate chain in
# preflight_runner.py / handlers/execution.py.
ALL_PREFLIGHT_CODES = {
    "project_name_required",
    "syntax_error",
    "server_state_error",
    "partial_module_structure",
    "unprotected_writes",
    "casting_issues_detected",
    "api_discovery_required",
    "undiscovered_entity",
    "undefined_variables",
    "missing_imports",
    "wrong_library_imports",
    "invalid_api_chain",
}


def _load_corpus() -> List[Tuple[str, Dict[str, Any]]]:
    entries = []
    for path in sorted(CORPUS_DIR.glob("*.yaml")):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: corpus entry must be a YAML mapping")
        entries.append((path.stem, data))
    return entries


_CORPUS_ENTRIES = _load_corpus()


def test_corpus_directory_not_empty():
    """Sanity: the corpus actually loaded something (catches a bad glob/path)."""
    assert _CORPUS_ENTRIES, f"No corpus entries found under {CORPUS_DIR}"


def test_corpus_covers_all_preflight_codes():
    """Acceptance criterion (#51): at least one entry per preflight error_code."""
    covered = {
        entry["expect"]["error_code"]
        for _name, entry in _CORPUS_ENTRIES
        if entry.get("expect", {}).get("error_code")
    }
    missing = ALL_PREFLIGHT_CODES - covered
    assert not missing, f"Corpus is missing coverage for error codes: {sorted(missing)}"


@pytest.mark.parametrize(
    "name,entry",
    _CORPUS_ENTRIES,
    ids=[name for name, _entry in _CORPUS_ENTRIES],
)
def test_corpus_entry(name: str, entry: Dict[str, Any]):
    if entry.get("skip"):
        pytest.skip(entry.get("skip_reason", "no reason given"))

    expect = entry.get("expect") or {}
    expected_outcome = expect.get("outcome")
    expected_error_code = expect.get("error_code")
    expected_auto_fixes = expect.get("auto_fixes", 0)

    assert expected_outcome in ("ok", "preflight_reject"), (
        f"{name}: expect.outcome must be 'ok' or 'preflight_reject', got {expected_outcome!r}"
    )

    # Auto-fix simulation is out of scope for this runner (see
    # preflight_runner.py docstring) -- entries exercising it should be
    # marked skip:true instead of asserting a nonzero count here.
    assert expected_auto_fixes == 0, (
        f"{name}: expect.auto_fixes={expected_auto_fixes} but this runner does not "
        "simulate auto-fix; mark this entry skip:true with a reason instead."
    )

    result = run_preflight_chain(entry)

    assert result.outcome == expected_outcome, (
        f"{name}: expected outcome={expected_outcome!r} got {result.outcome!r} "
        f"(gate={result.gate}, error_code={result.error_code}, detail={result.detail!r})"
    )
    if expected_outcome == "preflight_reject":
        assert result.error_code == expected_error_code, (
            f"{name}: expected error_code={expected_error_code!r} got {result.error_code!r} "
            f"(detail={result.detail!r})"
        )

    # getall-contract SPEC §6 Level 3: optional non-blocking advisory check.
    # Corpus entries only assert this when `expect.advisories` is explicitly
    # present -- absence means "don't care" so the hundreds of pre-existing
    # entries that happen to touch GetAll() aren't forced to declare a stance.
    if "advisories" in expect:
        expected_advisories = sorted(expect["advisories"] or [])
        assert sorted(result.advisories) == expected_advisories, (
            f"{name}: expected advisories={expected_advisories!r} got {sorted(result.advisories)!r}"
        )
