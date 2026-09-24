#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The per-word filing sequence (parser-check CP4, FR-014, FR-017, FR-019,
FR-031, FR-033, FR-040, FR-041; research R-02; data-model sections 7, 9).

For every word, in this order (`filing/classify.py`):

  1. liveness -- the wordform and the parse result are still valid objects,
     or the word is skipped `invalid_object` (FR-019);
  2. unchanged -- the stored checksum equals the new result's: FLEx's filer
     would skip the word, so it is reported `unchanged`, not `filed`;
  3. THE R-02 GUARD -- the filer's own would-delete set, on the live objects,
     must be inside the CONFIRMED projection, and the live in-use disapprovals
     inside the confirmed overwrite projection. If not, the word is skipped
     `outside_projection` and NOTHING is filed for it. This is what makes "no
     analysis is deleted that was not in the confirmed projection" (FR-014)
     something the code enforces rather than hopes;
  4. the captures -- a `pre_deletion` line for each analysis that may be
     deleted, a `disapproval_overwrite` line for each human disapproval that
     will be overwritten, with the PRIOR evaluation -- written BEFORE the pump
     (FR-031, FR-041);
  5. the pump (`filer.file_one`) -- `filed`, or `filer_declined` (FR-019);
  6. the before/after classification, and a `confirmed_after` line per capture.

A word whose parse ended in an error is filed as FLEx files it (FR-017): its
matched set is empty, so every unshielded, unapproved analysis goes; it is
counted in `errored_words`, and its deletions in `errored_word_deletions`.
"""

from flextoolsmcp.server.filing import classify


class FakeWord:
    """A word's live state, and a log of what was asked of it, in order."""

    def __init__(self, wordform="pukul", *, existing=(), after=None, valid=True,
                 checksum_matches=False, errored=False, pump="filed", duplicates=()):
        self.wordform = wordform
        self._existing = [dict(e) for e in existing]
        self._after = after
        self._valid = valid
        self._checksum = checksum_matches
        self._errored = errored
        self._pump = pump
        self._duplicates = set(duplicates)
        self.events = []

    def is_valid(self):
        self.events.append("is_valid")
        return self._valid

    def checksum_matches(self):
        self.events.append("checksum")
        return self._checksum

    def errored(self):
        return self._errored

    def existing(self):
        self.events.append("existing")
        return [dict(e) for e in self._existing]

    def capture(self, guid):
        self.events.append(f"capture:{guid}")
        return {"morph_bundles": [{"morph_guid": "m", "msa_guid": "s", "infl_type_guid": None,
                                   "form": "pukul"}],
                "glosses": [{"guid": "g", "form_by_ws": {"en": "hit"}}],
                "evaluations": [{"agent_guid": "u", "agent_name": "User", "human": True,
                                 "opinion": "disapproves", "date": "2026-01-01"}],
                "category": "v"}

    def pump(self):
        self.events.append("pump")
        return self._pump

    def after(self):
        self.events.append("after")
        return [dict(a) for a in (self._after if self._after is not None else self._existing)]

    def is_duplicate(self, guid):
        return guid in self._duplicates


def a(guid, *, opinion="noopinion", in_use=False, matched=False):
    return {"analysis_guid": guid, "user_opinion": opinion, "in_use": in_use, "matched": matched}


def ctx(projection=None, overwrites=None):
    lines = []
    return classify.FilingContext(
        projection=projection or {}, overwrites=overwrites or {}, sink=lines.append
    ), lines


# ---------------------------------------------------------------------------
# Counts (data-model section 7)
# ---------------------------------------------------------------------------


def test_created_reapproved_deleted_and_in_use_approvals_are_counted():
    word = FakeWord(
        existing=[a("keep", matched=True), a("gone"), a("inuse", in_use=True)],
        after=[a("keep", matched=True), {"analysis_guid": "inuse", "user_opinion": "approves"},
               {"analysis_guid": "new", "user_opinion": "noopinion"}],
    )
    context, lines = ctx(projection={"pukul": ["gone"]})
    out = classify.file_word(context, word)
    assert out["outcome"] == "filed"
    counts = out["counts"]
    assert (counts["created"], counts["reapproved"], counts["deleted"]) == (1, 1, 1)
    assert out["deleted"] == ["gone"] and out["created"] == ["new"]
    assert out["in_use_approvals_recorded"] == 1


def test_a_created_analysis_that_duplicates_a_gloss_only_record_is_counted():
    word = FakeWord(existing=[], after=[{"analysis_guid": "new", "user_opinion": "noopinion"}],
                    duplicates={"new"})
    context, _ = ctx()
    out = classify.file_word(context, word)
    assert out["counts"]["created"] == 1 and out["counts"]["duplicated"] == 1


# ---------------------------------------------------------------------------
# R-02 -- the guard. Nothing is filed outside the confirmed projection.
# ---------------------------------------------------------------------------


def test_a_would_delete_set_larger_than_the_projection_files_nothing():
    word = FakeWord(existing=[a("projected"), a("NOT-projected")])
    context, lines = ctx(projection={"pukul": ["projected"]})
    out = classify.file_word(context, word)
    assert out["outcome"] == "skipped" and out["skip_reason"] == "outside_projection"
    assert "pump" not in word.events, "nothing may be filed for this word"
    assert lines == [], "no capture either: nothing is about to be deleted"
    assert out["outside"] == ["NOT-projected"]


def test_a_word_absent_from_the_projection_with_nothing_to_delete_files():
    word = FakeWord(existing=[a("keep", matched=True)])
    context, _ = ctx(projection={})
    assert classify.file_word(context, word)["outcome"] == "filed"


def test_an_unprojected_in_use_disapproval_files_nothing():
    """SC-011: every overwrite a run makes was projected."""
    word = FakeWord(existing=[a("d1", opinion="disapproves", in_use=True)])
    context, lines = ctx(overwrites={})
    out = classify.file_word(context, word)
    assert out["skip_reason"] == "outside_projection" and "pump" not in word.events
    assert lines == []


def test_the_would_delete_set_is_the_filers_own_predicate():
    existing = [
        a("matched", matched=True),                   # re-approved, not deleted
        a("approved", opinion="approves"),             # user-approved: survives
        a("disapproved", opinion="disapproves"),       # user-disapproved: survives
        a("in-use", in_use=True),                      # in a text: approved, survives
        a("orphan"),                                   # deleted
    ]
    assert classify.would_delete(existing, errored=False) == {"orphan"}


def test_an_unreadable_opinion_counts_as_deletable_so_the_guard_sees_it():
    """Sweep #4: "unreadable" read as shielded let the filer delete unconfirmed."""
    assert classify.would_delete([a("x", opinion="unreadable")], errored=False) == {"x"}
    word = FakeWord(existing=[a("x", opinion="unreadable")])
    context, lines = ctx(projection={})
    out = classify.file_word(context, word)
    assert out["skip_reason"] == "outside_projection" and "pump" not in word.events
    assert lines == []


def test_unknown_segment_use_shields_nothing():
    """Sweep #4: an unreadable join is unknown, never "in no text"."""
    assert classify.would_delete([a("x", in_use=None)], errored=False) == {"x"}
    word = FakeWord(existing=[a("d1", opinion="disapproves", in_use=None)])
    context, _ = ctx(overwrites={})
    out = classify.file_word(context, word)
    assert out["skip_reason"] == "outside_projection" and "pump" not in word.events


def test_projected_unknowns_are_filed_and_captured_first():
    word = FakeWord(existing=[a("x", opinion="unreadable", in_use=None)])
    context, lines = ctx(projection={"pukul": ["x"]})
    assert classify.file_word(context, word)["outcome"] == "filed"
    captures = [line for line in lines if "confirmed_after" not in line]
    assert [(c["kind"], c["analysis_guid"]) for c in captures] == [("pre_deletion", "x")]
    assert word.events.index("capture:x") < word.events.index("pump")


def test_the_filer_side_join_reports_an_unreadable_bag_as_unknown():
    from flextoolsmcp.server.filing.worker_filing import LiveWord

    class Bag:
        def __iter__(self):
            raise RuntimeError("CLR enumeration failed")

    class Wordform:
        OccurrencesBag = Bag()

    live = LiveWord.__new__(LiveWord)
    live._wf = Wordform()
    assert live._segment_refs() is None


# ---------------------------------------------------------------------------
# FR-017 -- an errored word is filed as FLEx files it
# ---------------------------------------------------------------------------


def test_an_errored_word_is_filed_and_counted_separately():
    word = FakeWord(existing=[a("was-matched", matched=True), a("orphan")], errored=True,
                    after=[])
    context, _ = ctx(projection={"pukul": ["orphan", "was-matched"]})
    out = classify.file_word(context, word)
    assert out["outcome"] == "filed" and out["errored"] is True
    assert set(out["deleted"]) == {"orphan", "was-matched"}
    assert out["counts"]["errored_words"] == 1
    assert out["counts"]["errored_word_deletions"] == 2


def test_on_an_errored_word_matched_is_empty():
    assert classify.would_delete([a("x", matched=True)], errored=True) == {"x"}


# ---------------------------------------------------------------------------
# FR-031 / FR-041 -- the captures, BEFORE the pump
# ---------------------------------------------------------------------------


def test_the_capture_lines_are_written_before_the_pump():
    word = FakeWord(existing=[a("gone"), a("d1", opinion="disapproves", in_use=True)],
                    after=[{"analysis_guid": "d1", "user_opinion": "approves"}])
    context, lines = ctx(projection={"pukul": ["gone"]}, overwrites={"pukul": ["d1"]})
    classify.file_word(context, word)
    first_pump = word.events.index("pump")
    assert word.events.index("capture:gone") < first_pump
    assert word.events.index("capture:d1") < first_pump
    kinds = [(line["kind"], line["analysis_guid"]) for line in lines[:2]]
    assert kinds == [("pre_deletion", "gone"), ("disapproval_overwrite", "d1")]


def test_a_capture_carries_enough_to_recognise_and_rebuild_the_analysis():
    word = FakeWord(existing=[a("gone")], after=[])
    context, lines = ctx(projection={"pukul": ["gone"]})
    classify.file_word(context, word)
    capture = lines[0]
    for key in ("kind", "wordform", "analysis_guid", "morph_bundles", "glosses",
                "evaluations", "category"):
        assert key in capture, key
    assert capture["wordform"] == "pukul"


def test_confirmed_after_lines_say_what_happened():
    word = FakeWord(existing=[a("gone"), a("d1", opinion="disapproves", in_use=True)],
                    after=[{"analysis_guid": "d1", "user_opinion": "approves"}])
    context, lines = ctx(projection={"pukul": ["gone"]}, overwrites={"pukul": ["d1"]})
    out = classify.file_word(context, word)
    confirmed = {(line["analysis_guid"], line["confirmed_after"]) for line in lines
                 if "confirmed_after" in line}
    assert confirmed == {("gone", "deleted"), ("d1", "overwritten")}
    assert out["overwritten"] == ["d1"]


def test_the_disapproval_capture_records_the_prior_evaluation():
    word = FakeWord(existing=[a("d1", opinion="disapproves", in_use=True)],
                    after=[{"analysis_guid": "d1", "user_opinion": "approves"}])
    context, lines = ctx(overwrites={"pukul": ["d1"]})
    classify.file_word(context, word)
    overwrite = next(line for line in lines if line["kind"] == "disapproval_overwrite")
    assert overwrite["evaluations"][0]["opinion"] == "disapproves"
    assert overwrite["prior_user_opinion"] == "disapproves"


# ---------------------------------------------------------------------------
# FR-019 -- liveness, and the filer declining
# ---------------------------------------------------------------------------


def test_an_invalid_object_is_skipped_and_nothing_is_asked_of_it():
    word = FakeWord(existing=[a("gone")], valid=False)
    context, lines = ctx(projection={"pukul": ["gone"]})
    out = classify.file_word(context, word)
    assert out["skip_reason"] == "invalid_object"
    assert "pump" not in word.events and lines == []


def test_a_declined_word_is_not_filed_and_its_captures_survive():
    word = FakeWord(existing=[a("gone")], pump="filer_declined")
    context, lines = ctx(projection={"pukul": ["gone"]})
    out = classify.file_word(context, word)
    assert out["outcome"] == "skipped" and out["skip_reason"] == "filer_declined"
    assert out["counts"]["deleted"] == 0
    assert ("gone", "survived") in {(line["analysis_guid"], line.get("confirmed_after"))
                                    for line in lines}


def test_an_unchanged_checksum_is_unchanged_and_not_pumped():
    word = FakeWord(existing=[a("keep", matched=True)], checksum_matches=True)
    context, _ = ctx()
    out = classify.file_word(context, word)
    assert out["outcome"] == "unchanged" and out["counts"]["unchanged"] == 1
    assert "pump" not in word.events


# ---------------------------------------------------------------------------
# Aggregation into the run's FilingCounts
# ---------------------------------------------------------------------------


def test_counts_accumulate_into_the_run_totals():
    totals = classify.empty_counts()
    classify.add_counts(totals, {"created": 1, "deleted": 2,
                                 "skipped": {"outside_projection": 1}})
    classify.add_counts(totals, {"created": 1, "skipped": {"filer_declined": 1}})
    assert totals["created"] == 2 and totals["deleted"] == 2
    assert totals["skipped"] == {"invalid_object": 0, "outside_projection": 1, "filer_declined": 1}
    assert set(totals) == {"created", "reapproved", "duplicated", "deleted", "unchanged",
                           "errored_words", "errored_word_deletions", "skipped"}
