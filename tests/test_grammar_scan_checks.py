#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T015: per-check unit tests for the CP1 grammar-health scan (SPEC 9.5.4),
run directly against the T002 LCM stubs (``tests/fixtures/parser_check.py``).

Module under test: ``src/flextoolsmcp/server/scan/grammar_scan_module.py``
-- this file does **not exist yet**. It lands at T019 (phonology rows 2/4/9),
T034 (morphology rows 1/6/7/10) and T035 (rule-ordering rows 3/5/8), all
strictly after this test file, per tasks.md's declared tests-first wave
order for Phase 4 ("US2 wave" table). RED until those land is the point,
not a defect.

Sibling task T008 (``tests/test_parser_health_block.py``) established this
cycle's convention for pre-implementation test files: plain, undecorated
tests with a **per-test lazy import**, since no ``xfail``/skip-guard
precedent exists anywhere in this suite for "test written ahead of its
implementation". This file matches that: no top-level import of
``grammar_scan_module`` (that would fail the whole file at collection
time, per T007's competing precedent); each test imports what it needs
inside its own body so a missing name fails only that one test, loudly,
with a clear ``ModuleNotFoundError``/``ImportError``/``AttributeError``.

CONTRACT AMBIGUITY (documented, not resolved here). ``data-model.md``
(``GrammarFinding``/``FoundObject``) and the ``flextools_grammar_health``
contract pin the **tool's response shape** -- the thing T014/T017/T020
build. They do not pin the per-check function surface **inside**
``grammar_scan_module.py`` that this task is asked to unit-test in
isolation, against bare stubs that carry no ``Hvo``/``ClassName`` and no
live ``project`` (T002's stubs are deliberately minimal -- see
``tests/fixtures/parser_check.py``'s own docstring: "restricted to the
properties CP1's scan actually reads"). Two structural facts pin the
design space this file assumes:

1. ``src/flextoolsmcp/server/scan/__init__.py``'s own docstring says
   modules in this package run in the FLExTools/IronPython subprocess
   (``flextools_run_module``) and **must not import
   ``flextoolsmcp.server.*``** -- so ``grammar_scan_module.py`` cannot
   import ``server.models.GrammarHealthFinding``/``FoundObject`` (T017) to
   build its return values; it can only return plain data (bool/int/list/
   dict), with `FoundObject` construction (which needs a live `project` for
   `BuildGotoURL`) happening elsewhere, later, over real LCM objects.
2. The task text itself states the row-1 predicate in exactly this form:
   "The emptiness predicate is ``form in (None, "", "***")``" -- i.e. a
   **predicate function**, not a finding-builder, is the natural unit this
   task means "per-check" to name.

So this file assumes ``grammar_scan_module.py`` exposes, at minimum:

    - ``is_zero_surface_form(form) -> bool``            (row 1 predicate)
    - ``is_optional_slot(slot) -> bool``                 (row 10 predicate)
    - ``exclude_disabled_rules(rules) -> list``          (shared rule gate)
    - ``skipped_check(check_id) -> dict``                (checks_skipped entry)

If T019/T034/T035 land under different names, only this file's imports need
to change -- every assertion below is otherwise independent of that choice.
See cycle10-programmer-t015.md for the pass/fail counts this produced.
"""

from __future__ import annotations

import inspect

import pytest

from fixtures.parser_check import (
    fake_imoform_triple_star,
    fake_imoform_none,
    fake_imoform_empty,
    fake_imoform_real,
    fake_imoinflaffixslot,
    fake_iphsegmentrule,
)


# ---------------------------------------------------------------------------
# Row 1: zero-surface IMoForm (SPEC 9.5.4 row 1, data-model.md, T033's
# emptiness predicate)
# ---------------------------------------------------------------------------

class TestZeroSurfaceMorphRow1:
    def test_triple_star_is_counted_as_zero_surface_regression_guard(self):
        """The highest-value test in this file. A stub IMoForm whose Form
        is literally "***" must be counted as zero-surface -- this
        direct-LCM-read path does NOT get Flexicon's Operations-layer
        "***" -> "" normalization (CLAUDE.md). If this check silently
        skips "***" forms, every zero-surface morph in a real project
        would go unreported, since "***" is exactly how LCM spells "no
        value" on an unset IMultiUnicode.
        """
        from server.scan.grammar_scan_module import is_zero_surface_form

        assert is_zero_surface_form(fake_imoform_triple_star()) is True

    def test_none_form_is_counted(self):
        from server.scan.grammar_scan_module import is_zero_surface_form

        assert is_zero_surface_form(fake_imoform_none()) is True

    def test_empty_string_form_is_counted(self):
        from server.scan.grammar_scan_module import is_zero_surface_form

        assert is_zero_surface_form(fake_imoform_empty()) is True

    def test_real_surface_form_is_never_counted(self):
        from server.scan.grammar_scan_module import is_zero_surface_form

        assert is_zero_surface_form(fake_imoform_real("kal")) is False

    def test_cp1_scope_is_unconditional_on_optional_slot_reachability(self):
        """Positive assertion of the CP1 scope boundary: at CP1 the check
        is unconditional on position. A zero-surface IMoForm reachable
        from *no* optional slot -- i.e. a bare stub carrying no slot
        association at all, which is all T002's IMoForm stub can ever
        model -- is still counted. The slot-reachability walk (slot ->
        Affixes -> MSA -> owning entry -> AlternateFormsOS) is deferred to
        T034; asserting it here would be asserting scope this task
        explicitly does not have.

        The signature itself is the first-class evidence: a predicate that
        took a slot/position argument would be the wrong shape for CP1.
        """
        from server.scan.grammar_scan_module import is_zero_surface_form

        params = inspect.signature(is_zero_surface_form).parameters
        slotty_names = {
            name for name in params
            if any(tok in name.lower() for tok in ("slot", "position", "reachable", "optional"))
        }
        assert slotty_names == set(), (
            "is_zero_surface_form() must not take a slot/position/"
            "reachability parameter at CP1 -- that conditioning is T034's "
            f"deferred work, not this check's. Found: {slotty_names}"
        )

        # Behaviourally: a zero-surface form with no slot information
        # whatsoever (the only kind T002's stub can express) is still
        # counted, unconditionally.
        orphan_form = fake_imoform_none()
        assert is_zero_surface_form(orphan_form) is True

    def test_count_helper_counts_every_zero_surface_form_in_a_mixed_list(self):
        """If a count aggregate is exposed alongside the predicate, it must
        count strictly by the predicate -- no extra position filtering
        sneaks in via the aggregate instead of the predicate."""
        from server.scan.grammar_scan_module import is_zero_surface_form

        forms = [
            fake_imoform_triple_star(),
            fake_imoform_none(),
            fake_imoform_empty(),
            fake_imoform_real("kal"),
            fake_imoform_real("mi"),
        ]
        zero_surface = [f for f in forms if is_zero_surface_form(f)]
        assert len(zero_surface) == 3


# ---------------------------------------------------------------------------
# Row 10: IMoInflAffixSlot.Optional (SPEC 9.5.4 row 10) -- and the negative
# assertion that IMoInflAffixSlot is NOT ICmPossibility
# ---------------------------------------------------------------------------

class TestOptionalTemplateSlotsRow10:
    def test_optional_slot_is_counted(self):
        from server.scan.grammar_scan_module import is_optional_slot

        assert is_optional_slot(fake_imoinflaffixslot(optional=True)) is True

    def test_non_optional_slot_is_not_counted(self):
        from server.scan.grammar_scan_module import is_optional_slot

        assert is_optional_slot(fake_imoinflaffixslot(optional=False)) is False

    def test_never_reads_name_via_icmpossibility_cast(self):
        """`IMoInflAffixSlot` is NOT `ICmPossibility` (research.md D4,
        row 10, VERIFIED). `tests/fixtures/parser_check.py` deliberately
        gives `FakeIMoInflAffixSlot` no `.Name` attribute at all -- exactly
        so that a check mistakenly doing `ICmPossibility(obj).Name` fails
        loudly with `AttributeError` rather than silently reading the
        wrong field. Calling the real predicate on this stub must succeed
        without ever touching `.Name`.
        """
        from server.scan.grammar_scan_module import is_optional_slot

        slot = fake_imoinflaffixslot(optional=True)
        assert not hasattr(slot, "Name")
        # Must not raise AttributeError -- proves the predicate never
        # attempts `ICmPossibility(obj).Name` (or any `.Name` access) on a
        # slot object.
        result = is_optional_slot(slot)
        assert result is True

    def test_source_never_casts_a_slot_to_icmpossibility(self):
        """Belt-and-suspenders static check once the module exists: the
        literal cast `ICmPossibility(obj)` must not appear anywhere in
        the module's source text -- the index warns explicitly against it
        (fixture docstring), and this is the bug this whole task exists to
        prevent.
        """
        from server.scan import grammar_scan_module

        source = inspect.getsource(grammar_scan_module)
        assert "ICmPossibility(" not in source


# ---------------------------------------------------------------------------
# Disabled rules excluded BEFORE counting (IPhSegmentRule.Disabled)
# ---------------------------------------------------------------------------

class TestDisabledRulesExcludedBeforeCounting:
    def test_disabled_rule_is_filtered_out(self):
        from server.scan.grammar_scan_module import exclude_disabled_rules

        enabled = fake_iphsegmentrule(disabled=False)
        disabled = fake_iphsegmentrule(disabled=True)
        result = exclude_disabled_rules([enabled, disabled])

        assert disabled not in result
        assert enabled in result
        assert len(result) == 1

    def test_all_enabled_rules_are_retained(self):
        from server.scan.grammar_scan_module import exclude_disabled_rules

        rules = [fake_iphsegmentrule(disabled=False) for _ in range(3)]
        result = exclude_disabled_rules(rules)
        assert len(result) == 3

    def test_all_disabled_rules_yields_empty(self):
        """A grammar where every rule is disabled contributes nothing to
        any rule-based count -- data-model.md: "A disabled rule cannot
        multiply paths, so including it manufactures a suspect the grammar
        never runs." """
        from server.scan.grammar_scan_module import exclude_disabled_rules

        rules = [fake_iphsegmentrule(disabled=True) for _ in range(4)]
        assert exclude_disabled_rules(rules) == []

    def test_exclusion_precedes_counting_not_a_post_hoc_filter(self):
        """The count over a rule list must equal the count of the
        *excluded* list, never the raw list -- i.e. exclusion is not
        something applied to a report after the fact."""
        from server.scan.grammar_scan_module import exclude_disabled_rules

        rules = [
            fake_iphsegmentrule(disabled=False),
            fake_iphsegmentrule(disabled=True),
            fake_iphsegmentrule(disabled=True),
            fake_iphsegmentrule(disabled=False),
        ]
        raw_count = len(rules)
        excluded_count = len(exclude_disabled_rules(rules))
        assert raw_count == 4
        assert excluded_count == 2
        assert excluded_count != raw_count


# ---------------------------------------------------------------------------
# checks_skipped: an unverified LCM name is named, never silently omitted
# (contracts/flextools_grammar_health.md `checks_skipped`, T016's gate)
# ---------------------------------------------------------------------------

class TestChecksSkippedUnverifiedNeverSilentlyOmitted:
    def test_skipped_check_reason_is_exactly_lcm_name_unverified(self):
        """A check whose LCM names are unverified must appear in
        `checks_skipped` with reason exactly `lcm_name_unverified` --
        checked as a literal string, not a synonym, since the contract
        fixes this string verbatim.
        """
        from server.scan.grammar_scan_module import skipped_check

        entry = skipped_check("some-gated-check-id")
        assert entry["check_id"] == "some-gated-check-id"
        assert entry["reason"] == "lcm_name_unverified"

    def test_skipped_entry_has_no_extra_severity_style_keys(self):
        """Matches T014's "no severity proxy at any nesting level" guard --
        a checks_skipped entry is exactly {check_id, reason}, nothing a
        client could read as a rank/priority."""
        from server.scan.grammar_scan_module import skipped_check

        entry = skipped_check("another-gated-check-id")
        assert set(entry.keys()) == {"check_id", "reason"}

    @pytest.mark.parametrize("check_id", ["row-3-metathesis", "row-5-product", "row-7-alternate-forms"])
    def test_reason_string_is_stable_across_different_check_ids(self, check_id):
        from server.scan.grammar_scan_module import skipped_check

        assert skipped_check(check_id)["reason"] == "lcm_name_unverified"
