#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T014 (parser-check CP1): response-contract tests for `flextools_grammar_health`.

Authority: specs/parser-check/contracts/flextools_grammar_health.md (the
authoritative response shape -- asserted against literally), SPEC.md 9.5.2,
9.5.3, 9.5.4 (the ten-row check table -- its row order IS the required
`findings` order), 9.5.7 and 3.1, research.md D7 ("No scalar score, and what
that means for the output shape"), data-model.md (`GrammarFinding`/
`GrammarHealthFinding` and `FoundObject`). See tasks.md T014.

STATUS AT WRITE TIME: RED BY DESIGN. `GrammarHealthInput` /
`GrammarHealthFinding` / `FoundObject` (src/flextoolsmcp/server/models.py)
land at T017; the scan (src/flextoolsmcp/server/scan/grammar_scan_module.py)
at T019/T034/T035; the handler (src/flextoolsmcp/server/handlers/
grammar_health.py) at T020 -- all strictly after this file, per tasks.md's
declared "US2" wave table (W1: T014/T015 ... W6: T020). Every test that
touches one of those unimplemented names fails at import time
(ModuleNotFoundError/AttributeError) until it lands. That is the declared
tests-first wave order, not a defect.

Sibling task T008 (tests/test_parser_health_block.py) established this
cycle's convention for pre-implementation test files: plain, undecorated
tests with a per-test lazy import (no xfail/skip precedent exists anywhere
in this suite for "test written ahead of its implementation"), so a missing
name fails only that one test, loudly, with a clear error -- not a
whole-file collection error. This file follows the same convention.
Sibling task T015 (tests/test_grammar_scan_checks.py, same cycle) documents
a structural fact this file also relies on: `scan/__init__.py` forbids
`grammar_scan_module.py` from importing `flextoolsmcp.server.*`, so that
module can only return plain data (bool/int/list/dict) -- it cannot build
`GrammarHealthFinding`/`FoundObject` instances itself. Something in
`handlers/grammar_health.py` (T020) must therefore be the seam that turns
raw per-check results into those closed models and orders/caps them for the
response. That handler-side seam's *name* is not pinned by any doc this
file could find.

CONTRACT AMBIGUITY (documented, not resolved here): this file assumes
`server.handlers.grammar_health` exposes a module-level
`_assemble_findings(raw_findings: list[dict], limit: int = 20) ->
list[GrammarHealthFinding]` that (a) orders `raw_findings` by `spec_row`
ascending -- the 9.5.4 row order -- with `spec_row: null` entries (the three
9.5.1 extras PanGloss does not cover) sorted last, never by `count`; (b) caps
each finding's `objects[]` at `limit`, preserving whatever order the raw
per-check result already had (no re-sort during capping); and (c) validates
each item through `GrammarHealthFinding`/`FoundObject`. This mirrors
`diagnostic_health.py`'s existing `_build_parser_block()` precedent -- a
pure assembly function, separable from the network/subprocess layer, that
T008 already tests the same way. If T020 lands under a different name or
shape, only the `_call_assemble()` helper below needs to change -- every
ordering/closure assertion is otherwise independent of that choice.

Where a check does not require T020's still-undetermined interface at all,
this file grounds it directly against the checked-in contract document
instead of waiting -- `contracts/flextools_grammar_health.md`'s own JSON
example is parsed and walked, so several assertions here are meaningful
*today*, not just once implementation lands. That satisfies the task's "read
first ... assert against it literally" instruction independent of wave
order.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, List

import pytest

# ---------------------------------------------------------------------------
# Shared vocabulary (SPEC 9.5.3, 9.5.7, research D7, tasks.md T014)
# ---------------------------------------------------------------------------

# Primary severity-proxy words, plus the five renamed-proxy backstops
# ("the last five are renamed-proxy backstops, not the primary guard").
_SEVERITY_PRIMARY = {"score", "grade", "health", "rating", "severity", "priority", "rank"}
_SEVERITY_BACKSTOPS = {"impact", "tier", "weight", "urgency", "significance"}
_SEVERITY_DENYLIST = _SEVERITY_PRIMARY | _SEVERITY_BACKSTOPS
assert len(_SEVERITY_DENYLIST) == 12

_VERDICT_WORDS = {
    "invalid", "incorrect", "wrong", "error", "defect", "broken",
    "faulty", "flawed", "problematic", "malformed", "bug",
}
assert len(_VERDICT_WORDS) == 11

# A "factual, count-based phrasing template" (T014's positive check): a
# measured string must open with a count and use a factual/measurement verb,
# never assert a verdict with no visible evidence.
_MEASURED_TEMPLATE_RE = re.compile(
    r"^\d[\d,]*\s+\S.*\b(is|are|can|reachable|present|found|exceeds?|"
    r"matches?|attach(?:es)?|host(?:s)?|equals?)\b",
    re.IGNORECASE,
)

_CONTRACT_PATH = (
    Path(__file__).resolve().parent.parent
    / "specs" / "parser-check" / "contracts" / "flextools_grammar_health.md"
)

_FINDING_ALLOWLIST = {"check_id", "spec_row", "count", "measured", "evidence_basis", "objects"}
_FOUND_OBJECT_ALLOWLIST = {"hvo", "class_name", "label", "goto_url"}


# ---------------------------------------------------------------------------
# Generic recursive walkers (mirrors test_parser_health_block.py's _find_all)
# ---------------------------------------------------------------------------

def _all_keys(obj: Any) -> List[str]:
    """Every dict key found anywhere under `obj`, at any nesting depth."""
    found: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.append(k)
            found.extend(_all_keys(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_all_keys(item))
    return found


def _find_all(obj: Any, key: str) -> List[Any]:
    """Every value found anywhere under dict key `key`, at any nesting depth."""
    found: List[Any] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                found.append(v)
            found.extend(_find_all(v, key))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_all(item, key))
    return found


def _all_string_leaves(obj: Any) -> List[str]:
    """Every string value found anywhere under `obj`, at any nesting depth."""
    found: List[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            found.extend(_all_string_leaves(v))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_all_string_leaves(item))
    elif isinstance(obj, str):
        found.append(obj)
    return found


def _assert_no_denylisted_keys(obj: Any) -> None:
    keys_lower = {k.lower() for k in _all_keys(obj)}
    offenders = keys_lower & _SEVERITY_DENYLIST
    assert not offenders, f"severity-proxy key(s) found at some nesting level: {offenders}"


def _assert_no_verdict_words(text: str) -> None:
    lowered = text.lower()
    offenders = {w for w in _VERDICT_WORDS if w in lowered}
    assert not offenders, f"verdict word(s) {offenders} found in: {text!r}"


def _load_contract_example() -> dict:
    """Parse the ```json fenced block from the contract doc -- the literal
    "Output" example in contracts/flextools_grammar_health.md."""
    text = _CONTRACT_PATH.read_text(encoding="utf-8")
    match = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
    assert match, "contract doc must contain a ```json fenced Output example"
    return json.loads(match.group(1))


# ---------------------------------------------------------------------------
# Grounded against the checked-in contract doc itself -- meaningful today,
# not just once implementation lands (per this task's "assert against it
# literally" instruction).
# ---------------------------------------------------------------------------

class TestContractExampleItself:
    def test_example_parses_as_json(self):
        example = _load_contract_example()
        assert isinstance(example, dict)

    def test_example_has_no_severity_proxy_key_at_any_nesting_level(self):
        example = _load_contract_example()
        _assert_no_denylisted_keys(example)

    def test_example_finding_field_set_matches_the_pinned_allowlist(self):
        example = _load_contract_example()
        findings = example["findings"]
        assert findings, "contract example must show at least one finding"
        for finding in findings:
            assert set(finding.keys()) == _FINDING_ALLOWLIST

    def test_example_found_object_field_set_matches_the_pinned_allowlist(self):
        example = _load_contract_example()
        for finding in example["findings"]:
            for obj in finding["objects"]:
                assert set(obj.keys()) == _FOUND_OBJECT_ALLOWLIST

    def test_example_measured_has_no_verdict_words(self):
        example = _load_contract_example()
        for measured in _find_all(example, "measured"):
            _assert_no_verdict_words(measured)

    def test_example_measured_matches_the_factual_count_based_template(self):
        example = _load_contract_example()
        for measured in _find_all(example, "measured"):
            assert _MEASURED_TEMPLATE_RE.search(measured), (
                f"measured text does not match the factual, count-based "
                f"phrasing template: {measured!r}"
            )

    def test_example_has_no_total_key_anywhere(self):
        example = _load_contract_example()
        keys_lower = {k.lower() for k in _all_keys(example)}
        assert "total" not in keys_lower
        assert "total_count" not in keys_lower
        assert "count_total" not in keys_lower

    def test_example_next_step_is_null(self):
        example = _load_contract_example()
        assert example["next_step"] is None

    def test_example_checks_skipped_reason_is_lcm_name_unverified(self):
        example = _load_contract_example()
        for entry in example["checks_skipped"]:
            assert entry["reason"] == "lcm_name_unverified"

    def test_contract_states_never_derived_from_wordforms_or_analyses(self):
        text = _CONTRACT_PATH.read_text(encoding="utf-8")
        assert "Never derived from wordforms or analyses" in text
        assert "IWfiAnalysis" in text

    def test_contract_states_no_hcparser_no_lcmcache(self):
        text = _CONTRACT_PATH.read_text(encoding="utf-8")
        assert "Constructs no `HCParser`" in text
        assert "Opens no `LcmCache`" in text


# ---------------------------------------------------------------------------
# Structural closure of GrammarHealthFinding -- the PRIMARY guard (T017).
# ---------------------------------------------------------------------------

class TestGrammarHealthFindingStructuralClosure:
    _VALID_KWARGS = dict(
        check_id="zero-surface-morph-repeatable",
        spec_row=1,
        count=3,
        measured="3 allomorphs with an empty surface form are reachable from an optional slot",
        evidence_basis="PanGloss measured 425x on one five-word slice",
        objects=[],
    )

    def test_field_allowlist_is_exactly_six_keys(self):
        from server.models import GrammarHealthFinding

        assert set(GrammarHealthFinding.model_fields.keys()) == _FINDING_ALLOWLIST

    def test_extra_is_forbid(self):
        from server.models import GrammarHealthFinding

        assert GrammarHealthFinding.model_config.get("extra") == "forbid"

    def test_valid_construction_round_trips(self):
        from server.models import GrammarHealthFinding

        finding = GrammarHealthFinding(**self._VALID_KWARGS)
        assert finding.check_id == "zero-surface-morph-repeatable"
        assert finding.count == 3

    @pytest.mark.parametrize("bad_key", sorted(_SEVERITY_DENYLIST))
    def test_rejects_each_severity_proxy_field(self, bad_key):
        from pydantic import ValidationError
        from server.models import GrammarHealthFinding

        with pytest.raises(ValidationError):
            GrammarHealthFinding(**self._VALID_KWARGS, **{bad_key: 1})

    def test_rejects_an_unknown_field_not_in_the_denylist_too(self):
        """Structural closure, not just name-denial: ANY unrecognized key is
        rejected, not only the ones on our specific denylist."""
        from pydantic import ValidationError
        from server.models import GrammarHealthFinding

        with pytest.raises(ValidationError):
            GrammarHealthFinding(**self._VALID_KWARGS, totally_unforeseen_field="x")


# ---------------------------------------------------------------------------
# Structural closure of FoundObject -- closed the same way, one nesting
# level down (T017/T014: "objects[] items need their own closed model").
# ---------------------------------------------------------------------------

class TestFoundObjectStructuralClosure:
    _VALID_KWARGS = dict(hvo=12345, class_name="MoStemAllomorph", label="-", goto_url="silfw://...")

    def test_field_allowlist_is_exactly_four_keys(self):
        from server.models import FoundObject

        assert set(FoundObject.model_fields.keys()) == _FOUND_OBJECT_ALLOWLIST

    def test_extra_is_forbid(self):
        from server.models import FoundObject

        assert FoundObject.model_config.get("extra") == "forbid"

    def test_valid_construction_round_trips(self):
        from server.models import FoundObject

        obj = FoundObject(**self._VALID_KWARGS)
        assert obj.hvo == 12345

    def test_label_empty_string_allowed_never_triple_star(self):
        """data-model.md: label is "" when the field is empty, never
        "***" (flexicon normalizes). The model must accept "" as a valid
        label -- it is not itself responsible for rejecting "***", but this
        pins that "" is the correct empty spelling at this layer."""
        from server.models import FoundObject

        obj = FoundObject(hvo=1, class_name="MoStemAllomorph", label="", goto_url=None)
        assert obj.label == ""

    @pytest.mark.parametrize("bad_key", sorted(_SEVERITY_DENYLIST))
    def test_rejects_each_severity_proxy_field(self, bad_key):
        from pydantic import ValidationError
        from server.models import FoundObject

        with pytest.raises(ValidationError):
            FoundObject(**self._VALID_KWARGS, **{bad_key: 1})

    def test_rejects_an_unknown_field_not_in_the_denylist_too(self):
        from pydantic import ValidationError
        from server.models import FoundObject

        with pytest.raises(ValidationError):
            FoundObject(**self._VALID_KWARGS, totally_unforeseen_field="x")

    def test_nested_inside_grammar_health_finding_is_closed_too(self):
        """"Any nesting level" enforced at every level, not just the top:
        an unknown key on a nested objects[] item must reject construction
        of the enclosing GrammarHealthFinding, not be silently swallowed."""
        from pydantic import ValidationError
        from server.models import GrammarHealthFinding

        with pytest.raises(ValidationError):
            GrammarHealthFinding(
                check_id="zero-surface-morph-repeatable",
                spec_row=1,
                count=1,
                measured="1 allomorph with an empty surface form is reachable from an optional slot",
                evidence_basis=None,
                objects=[{"hvo": 1, "class_name": "MoStemAllomorph", "label": "-", "goto_url": None, "severity": "high"}],
            )


# ---------------------------------------------------------------------------
# Recursive "any nesting level" walk over real model output (backstop,
# T014: "the last five are renamed-proxy backstops, not the primary guard").
# ---------------------------------------------------------------------------

class TestRecursiveDenylistWalkOverRealModels:
    def _build_finding(self):
        from server.models import FoundObject, GrammarHealthFinding

        return GrammarHealthFinding(
            check_id="zero-surface-morph-repeatable",
            spec_row=1,
            count=2,
            measured="2 allomorphs with an empty surface form are reachable from an optional slot",
            evidence_basis="PanGloss measured 425x on one five-word slice",
            objects=[
                FoundObject(hvo=1, class_name="MoStemAllomorph", label="-", goto_url="silfw://a"),
                FoundObject(hvo=2, class_name="MoStemAllomorph", label="-", goto_url="silfw://b"),
            ],
        )

    def test_no_denylisted_key_anywhere_in_a_serialized_finding(self):
        finding = self._build_finding()
        _assert_no_denylisted_keys(finding.model_dump())

    def test_no_denylisted_key_anywhere_in_a_multi_finding_envelope_fixture(self):
        """The envelope's top-level shape is pinned by the contract; this
        combines two real, closed Finding instances under it to prove the
        walk catches a violation at the deepest level (objects[] items),
        not just the top."""
        finding_a = self._build_finding()
        from server.models import FoundObject, GrammarHealthFinding

        finding_b = GrammarHealthFinding(
            check_id="unbounded-quantifier",
            spec_row=4,
            count=1,
            measured="1 iteration context has an unbounded maximum",
            evidence_basis=None,
            objects=[FoundObject(hvo=3, class_name="PhIterationContext", label="", goto_url=None)],
        )
        envelope = {
            "_contract": "tool-responses/1.0",
            "status": "ok",
            "project": "TestProj",
            "checks_run": [finding_a.check_id, finding_b.check_id],
            "checks_skipped": [{"check_id": "epenthesis-or-metathesis", "reason": "lcm_name_unverified"}],
            "findings": [finding_a.model_dump(), finding_b.model_dump()],
            "next_step": None,
        }
        _assert_no_denylisted_keys(envelope)
        assert "total" not in {k.lower() for k in _all_keys(envelope)}

    def test_the_walker_actually_detects_a_planted_violation(self):
        """Regression-proofs the walker itself: it must not vacuously pass.
        A "severity" key planted deep inside an objects[] item must be
        caught."""
        finding = self._build_finding().model_dump()
        finding["objects"][1]["severity"] = "high"
        with pytest.raises(AssertionError):
            _assert_no_denylisted_keys(finding)

    def test_measured_matches_the_factual_template_on_real_model_instances(self):
        finding = self._build_finding()
        assert _MEASURED_TEMPLATE_RE.search(finding.measured)
        _assert_no_verdict_words(finding.measured)


# ---------------------------------------------------------------------------
# Order-invariance (T014's hardest guard): findings ordered by 9.5.4 row
# order, NEVER by count magnitude. Uses the assumed T020 assembly seam --
# see the module docstring's CONTRACT AMBIGUITY note.
# ---------------------------------------------------------------------------

def _raw_finding(check_id, spec_row, count, hvos):
    return {
        "check_id": check_id,
        "spec_row": spec_row,
        "count": count,
        "measured": f"{count} objects trip {check_id}",
        "evidence_basis": None,
        "objects": [
            {"hvo": h, "class_name": "MoStemAllomorph", "label": "-", "goto_url": None}
            for h in hvos
        ],
    }


def _call_assemble(raw_findings, limit=20):
    """See module docstring's CONTRACT AMBIGUITY note for the assumption
    this encodes: server.handlers.grammar_health exposes a pure
    `_assemble_findings(raw_findings, limit)` seam."""
    from server.handlers.grammar_health import _assemble_findings

    return _assemble_findings(raw_findings, limit=limit)


class TestOrderInvarianceOfFindings:
    def test_findings_ordered_by_spec_row_ascending_regardless_of_count_magnitude(self):
        # Run A: highest spec_row has the highest count.
        run_a = [
            _raw_finding("zero-surface-morph-repeatable", 1, 5, [1]),
            _raw_finding("unbounded-quantifier", 4, 500, [2]),
            _raw_finding("duplicate-feature-bundle", 9, 50, [3]),
        ]
        findings = _call_assemble(run_a)
        assert [f.spec_row for f in findings] == [1, 4, 9]

    def test_order_is_byte_identical_across_two_permuted_magnitude_runs(self):
        run_a = [
            _raw_finding("zero-surface-morph-repeatable", 1, 5, [1]),
            _raw_finding("unbounded-quantifier", 4, 500, [2]),
            _raw_finding("duplicate-feature-bundle", 9, 50, [3]),
        ]
        # Run B: same three checks, magnitudes permuted so the previous
        # winner-by-count is now the loser-by-count.
        run_b = [
            _raw_finding("zero-surface-morph-repeatable", 1, 500, [1]),
            _raw_finding("unbounded-quantifier", 4, 5, [2]),
            _raw_finding("duplicate-feature-bundle", 9, 1, [3]),
        ]
        order_a = json.dumps([f.check_id for f in _call_assemble(run_a)])
        order_b = json.dumps([f.check_id for f in _call_assemble(run_b)])
        assert order_a == order_b, (
            "findings order changed when only count magnitudes were "
            "permuted -- this is exactly the 'first finding is worst' "
            "smuggling path 9.5.7/D7 forbid"
        )

    def test_findings_are_never_sorted_descending_by_count(self):
        """Belt-and-suspenders: explicitly construct the case where a
        count-descending sort and the 9.5.4 row-order sort disagree, and
        assert the result is row-order, not count-order."""
        raw = [
            _raw_finding("zero-surface-morph-repeatable", 1, 1, [1]),   # lowest count
            _raw_finding("unbounded-quantifier", 4, 999, [2]),          # highest count
        ]
        findings = _call_assemble(raw)
        by_count_desc = sorted(raw, key=lambda r: -r["count"])
        assert [f.check_id for f in findings] != [r["check_id"] for r in by_count_desc]
        assert [f.spec_row for f in findings] == [1, 4]

    def test_null_spec_row_extras_are_never_sorted_before_numbered_rows(self):
        """The three 9.5.1 causes PanGloss does not cover have `spec_row:
        null`. Whatever their fixed position is, it must not be magnitude
        dependent either -- assert it stays fixed (last, per 9.5.4's "we
        would be first" framing of the numbered rows) across permuted
        counts."""
        run_a = [
            _raw_finding("short-allomorph", None, 1, [1]),
            _raw_finding("zero-surface-morph-repeatable", 1, 999, [2]),
        ]
        run_b = [
            _raw_finding("short-allomorph", None, 999, [1]),
            _raw_finding("zero-surface-morph-repeatable", 1, 1, [2]),
        ]
        order_a = [f.spec_row for f in _call_assemble(run_a)]
        order_b = [f.spec_row for f in _call_assemble(run_b)]
        assert order_a == order_b == [1, None]

    def test_objects_within_a_finding_are_never_reordered_by_magnitude(self):
        """objects[] item order must reflect scan order, never be
        magnitude-sorted -- checked across two runs where the "magnitude"
        (hvo, standing in for whatever a real scan would vary) is permuted
        between calls."""
        run_a = [_raw_finding("zero-surface-morph-repeatable", 1, 3, [100, 5, 42])]
        run_b = [_raw_finding("zero-surface-morph-repeatable", 1, 3, [5, 42, 100])]

        hvos_a = [o.hvo for o in _call_assemble(run_a)[0].objects]
        hvos_b = [o.hvo for o in _call_assemble(run_b)[0].objects]

        assert hvos_a == [100, 5, 42], "objects[] must preserve raw scan order, not sort ascending/descending"
        assert hvos_b == [5, 42, 100], "objects[] must preserve raw scan order, not sort ascending/descending"
        assert hvos_a != sorted(hvos_a)
        assert hvos_b != sorted(hvos_b)

    def test_objects_are_capped_at_limit_without_resorting(self):
        raw = [_raw_finding("zero-surface-morph-repeatable", 1, 5, [10, 20, 30, 40, 50])]
        findings = _call_assemble(raw, limit=2)
        assert [o.hvo for o in findings[0].objects] == [10, 20]
        # count reflects the true total, never truncated to len(objects[]).
        assert findings[0].count == 5


# ---------------------------------------------------------------------------
# Counts are evidence, never summed into a total.
# ---------------------------------------------------------------------------

class TestCountsNeverSummedIntoATotal:
    def test_assembled_findings_carry_no_total_field_anywhere(self):
        raw = [
            _raw_finding("zero-surface-morph-repeatable", 1, 10, [1]),
            _raw_finding("unbounded-quantifier", 4, 20, [2]),
        ]
        findings = _call_assemble(raw)
        dumped = [f.model_dump() for f in findings]
        keys_lower = {k.lower() for k in _all_keys(dumped)}
        assert "total" not in keys_lower
        assert "total_count" not in keys_lower
        assert "sum" not in keys_lower


# ---------------------------------------------------------------------------
# CP1 boundary (SPEC 3.1): grammar objects only, never IWfiAnalysis or
# wordforms; no HCParser; no LcmCache in the MCP server process. The
# definitive static+dynamic scan is T026's (tests/test_cp1_boundary.py);
# these are lightweight, module-scoped supplements once the relevant files
# exist.
# ---------------------------------------------------------------------------

class TestCP1BoundaryOnTheScanModule:
    def test_scan_module_source_never_mentions_iwfianalysis(self):
        import inspect

        from server.scan import grammar_scan_module

        source = inspect.getsource(grammar_scan_module)
        assert "IWfiAnalysis" not in source

    def test_scan_module_source_never_constructs_hcparser(self):
        import inspect

        from server.scan import grammar_scan_module

        source = inspect.getsource(grammar_scan_module)
        assert "HCParser(" not in source

    def test_scan_module_source_never_opens_an_lcmcache(self):
        import inspect

        from server.scan import grammar_scan_module

        source = inspect.getsource(grammar_scan_module)
        assert "LcmCache(" not in source


class TestCP1BoundaryOnTheHandler:
    def test_handler_source_never_opens_an_lcmcache_in_the_mcp_server_process(self):
        """The scan itself runs in the generated-module subprocess
        (research D1); the handler runs IN the MCP server process, so this
        is where "opens no LcmCache in the MCP server process" is actually
        checkable at the file this test can see."""
        import inspect

        from server.handlers import grammar_health

        source = inspect.getsource(grammar_health)
        assert "LcmCache(" not in source

    def test_handler_does_not_call_check_active_parser(self):
        """Per the contract: this tool does not call check_active_parser()
        -- it runs no parser and reads no engine-specific object."""
        import inspect

        from server.handlers import grammar_health

        source = inspect.getsource(grammar_health)
        assert "check_active_parser(" not in source


# ---------------------------------------------------------------------------
# Verdict wording: "invalid"/"incorrect"/.../"bug" never describe a finding.
# A denylist alone is bypassed by synonym, which is exactly what the
# positive template check (above, TestContractExampleItself and
# TestRecursiveDenylistWalkOverRealModels) exists to close.
# ---------------------------------------------------------------------------

class TestVerdictWordingNeverDescribesAFinding:
    @pytest.mark.parametrize("word", sorted(_VERDICT_WORDS))
    def test_verdict_word_checker_flags_every_denylisted_word(self, word):
        """Regression-proofs the checker itself against every word in the
        list -- not a vacuous pass."""
        with pytest.raises(AssertionError):
            _assert_no_verdict_words(f"3 allomorphs are {word}")

    def test_verdict_word_checker_accepts_factual_phrasing(self):
        _assert_no_verdict_words(
            "3 allomorphs with an empty surface form are reachable from an optional slot"
        )

    def test_assembled_findings_measured_text_has_no_verdict_words(self):
        raw = [_raw_finding("zero-surface-morph-repeatable", 1, 3, [1, 2, 3])]
        findings = _call_assemble(raw)
        for f in findings:
            _assert_no_verdict_words(f.measured)


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
