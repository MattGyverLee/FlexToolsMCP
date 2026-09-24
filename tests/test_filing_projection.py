#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The deletion projection is an UPPER BOUND on what filing can delete
(parser-check CP4, FR-011..FR-015, FR-040, SC-003; research R-01).

A wrong-implementation TRIPWIRE, written red first (tasks.md T030). The
tempting implementation is to call CP3's `signals.projections.deletion_projection`
-- FR-015 says "reuse CP3's join and probe", and CP3 already ships a thing
called a deletion projection. It is the wrong predicate:

    CP3:    parser-created  AND  user noopinion  AND  not in any segment
    FLEx:                        user noopinion  AND  not in any segment

`ParseFiler.UpdateWordforms` resets the PARSER's opinion on every analysis of
the word, then `SetUnsuccessfulParseEvals` deletes whatever still has parser
noopinion and user noopinion (`ParseFiler.cs:226-227, 312-315`). It does not
care who created the analysis. So an analysis a person made, never evaluated
and never used in a text IS deleted by FLEx -- and is invisible to CP3's
projection, which would make FR-014 ("an upper bound") false. The first
fixture below is exactly that analysis: CP3's predicate returns 0 for it and
the filing bound must return 1.

Also pinned here:
  * an analysis in use only THROUGH A GLOSS is shielded -- through the real
    CP3 join (`oracle.segment_occurrence`), fed fake segments;
  * a human-disapproved analysis is never projected as deletable, is shown as
    its own count, and -- when in use -- is projected as a disapproval FLEx
    will overwrite with an approval (D-2, FR-040), separately from the in-use
    approvals FR-033 counts;
  * an unknown segment use COUNTS toward the bound (the opposite of CP3's
    information projection, and deliberately so);
  * a never-parsed project whose analyses are all spoken for projects exactly
    0, per wordform, with `by_wordform == {}` (FR-013, SC-003);
  * `projection.py` uses THE join and THE probe, and contains no traversal of
    its own (FR-015).
"""

import ast
from pathlib import Path

from flextoolsmcp.server.filing import projection
from flextoolsmcp.server.signals.projections import deletion_projection as cp3_deletion_projection

SRC = Path(__file__).parent.parent / "src" / "flextoolsmcp" / "server"

NEVER_PARSED = {
    "parser_has_ever_run": False, "analyses_total": 3, "parser_created_analyses": 0,
    "human_opinion_analyses": 3, "indeterminate_analyses": 0, "truncated": False,
}
PARSED = dict(NEVER_PARSED, parser_has_ever_run=True, parser_created_analyses=4)


def fact(guid, *, opinion="noopinion", in_segment=False, parser_evaluated=True):
    return {"analysis_guid": guid, "user_opinion": opinion,
            "parser_evaluated": parser_evaluated, "in_segment": in_segment}


def facts_for(**words):
    return {w: {"wordform": w, "found": True, "analyses": list(a)} for w, a in words.items()}


# ---------------------------------------------------------------------------
# R-01: the trap
# ---------------------------------------------------------------------------


def test_a_human_made_never_evaluated_unused_analysis_is_counted():
    human_made = fact("h1", parser_evaluated=False)
    result = projection.project(facts_for(pukul=[human_made]), PARSED)
    assert result.deletion["upper_bound"] == 1
    assert result.deletion["by_wordform"] == {"pukul": ["h1"]}


def test_cp3s_predicate_misses_the_same_analysis():
    """The tripwire's other half: reusing CP3's projection gives 0 here."""
    line = {"wordform": "pukul", "parse": {"human_analyses": [
        {"analysis_guid": "h1", "opinion": "noopinion", "parser_evaluated": False,
         "in_segment": False},
    ]}}
    assert cp3_deletion_projection([line])["count"] == 0


def test_the_predicate_is_the_two_conjuncts_of_fr_011():
    result = projection.project(facts_for(w=[fact("a")]), PARSED)
    assert result.deletion["predicate"] == (
        "user_noopinion AND not_referenced_by_any_segment_directly_or_via_gloss"
    )


# ---------------------------------------------------------------------------
# The conjunction, the shields and the counts
# ---------------------------------------------------------------------------


def test_twelve_unreviewed_four_in_text_projects_at_most_eight():
    """US1 acceptance 2: 12 parser analyses with no human opinion, 4 in a text."""
    analyses = [fact(f"p{i}", in_segment=(i < 4)) for i in range(12)]
    result = projection.project(facts_for(kata=analyses), PARSED)
    assert result.deletion["upper_bound"] == 8
    assert set(result.deletion["by_wordform"]["kata"]).isdisjoint({"p0", "p1", "p2", "p3"})
    assert result.in_use_approvals_projected == 4


def test_a_disapproved_analysis_is_excluded_and_counted_on_its_own():
    result = projection.project(facts_for(w=[fact("d1", opinion="disapproves")]), PARSED)
    assert result.deletion["upper_bound"] == 0
    assert result.deletion["excluded_disapproved"] == 1
    assert result.disapproval_overwrites["count"] == 0, "not in use: nothing to overwrite"


def test_an_in_use_disapproval_is_projected_as_overwritten_not_as_an_approval():
    """D-2 / FR-040: filing sets the user agent to `approves` on every in-use
    analysis, a human disapproval included. Projected separately."""
    result = projection.project(
        facts_for(w=[fact("d1", opinion="disapproves", in_segment=True),
                     fact("n1", in_segment=True)]),
        PARSED,
    )
    assert result.disapproval_overwrites == {"count": 1, "by_wordform": {"w": ["d1"]}}
    assert result.in_use_approvals_projected == 1, "the disapproval is not folded in"
    assert result.deletion["upper_bound"] == 0


def test_an_approved_analysis_is_never_deletable():
    result = projection.project(facts_for(w=[fact("a1", opinion="approves")]), PARSED)
    assert result.deletion["upper_bound"] == 0


def test_an_unknown_segment_use_counts_toward_the_bound():
    """For a BOUND, "could not tell" rounds toward "may be deleted"."""
    result = projection.project(facts_for(w=[fact("u1", in_segment=None)]), PARSED)
    assert result.deletion["upper_bound"] == 1
    assert result.deletion["segment_use_unknown"] == 1
    assert result.deletion["by_wordform"] == {"w": ["u1"]}


def test_an_unreadable_opinion_counts_toward_the_bound():
    result = projection.project(facts_for(w=[fact("x1", opinion="unreadable")]), PARSED)
    assert result.deletion["upper_bound"] == 1
    assert result.deletion["opinion_unknown"] == 1


def test_the_bound_is_per_wordform_and_guids_are_sorted():
    result = projection.project(
        facts_for(b=[fact("z"), fact("y")], a=[fact("m", opinion="approves")]), PARSED
    )
    assert result.deletion["by_wordform"] == {"b": ["y", "z"]}
    assert result.deletion["upper_bound"] == 2


# ---------------------------------------------------------------------------
# FR-013 / SC-003: a concrete number, including 0
# ---------------------------------------------------------------------------


def test_a_never_parsed_project_projects_exactly_zero():
    facts = facts_for(
        pukul=[fact("h1", opinion="approves", parser_evaluated=False)],
        kirim=[fact("h2", in_segment=True, parser_evaluated=False),
               fact("h3", opinion="approves", parser_evaluated=False)],
    )
    result = projection.project(facts, NEVER_PARSED)
    assert result.deletion["upper_bound"] == 0
    assert result.deletion["by_wordform"] == {}
    assert result.deletion["project_state"] == NEVER_PARSED


def test_the_project_state_is_carried_never_used_to_force_the_number():
    """A never-parsed project is NOT short-circuited to 0: if it holds an
    unused analysis nobody has spoken for, FLEx will delete it, so it counts."""
    result = projection.project(facts_for(w=[fact("h1", parser_evaluated=False)]), NEVER_PARSED)
    assert result.deletion["upper_bound"] == 1


def test_a_word_with_no_stored_analyses_contributes_nothing():
    result = projection.project({"w": {"wordform": "w", "found": False, "analyses": []}}, PARSED)
    assert result.deletion["upper_bound"] == 0 and result.deletion["by_wordform"] == {}


# ---------------------------------------------------------------------------
# The gloss path, through THE join (FR-011, FR-015)
# ---------------------------------------------------------------------------


class _Obj:
    def __init__(self, class_name, guid, owner=None):
        self.ClassName = class_name
        self.Guid = guid
        self.Owner = owner


class _Segment:
    def __init__(self, *items):
        self.AnalysesRS = list(items)


def test_an_analysis_in_use_only_through_a_gloss_is_shielded():
    direct = _Obj("WfiAnalysis", "A-DIRECT")
    glossed = _Obj("WfiAnalysis", "A-GLOSSED")
    gloss = _Obj("WfiGloss", "G-1", owner=glossed)
    wordform_only = _Obj("WfiWordform", "WF-1")
    segments = [_Segment(direct), _Segment(gloss, wordform_only)]

    occurrence = projection.fresh_occurrence(lambda: iter(segments))
    stored = {"kata": [
        {"analysis_guid": "a-direct", "user_opinion": "noopinion", "parser_evaluated": True},
        {"analysis_guid": "a-glossed", "user_opinion": "noopinion", "parser_evaluated": True},
        {"analysis_guid": "a-free", "user_opinion": "noopinion", "parser_evaluated": True},
    ]}
    facts = projection.attach_segment_use(stored, occurrence)
    result = projection.project(facts, PARSED)

    assert result.deletion["by_wordform"] == {"kata": ["a-free"]}
    assert result.in_use_approvals_projected == 2


def test_a_join_that_could_not_be_built_is_unknown_not_empty():
    def _broken():
        raise RuntimeError("texts unreadable")

    occurrence = projection.fresh_occurrence(_broken)
    facts = projection.attach_segment_use(
        {"w": [{"analysis_guid": "a", "user_opinion": "noopinion", "parser_evaluated": True}]},
        occurrence,
    )
    assert facts["w"]["analyses"][0]["in_segment"] is None
    assert projection.project(facts, PARSED).deletion["segment_use_unknown"] == 1


def test_a_word_whose_analyses_could_not_be_read_is_named_not_counted_as_zero():
    """Sweep #4: an unreadable analysis list is not "nothing to delete"."""
    occurrence = projection.fresh_occurrence(lambda: iter(()))
    facts = projection.attach_segment_use({"w": projection.UNREADABLE, "v": None}, occurrence)
    deletion = projection.project(facts, PARSED).deletion
    assert deletion["words_unreadable"] == ["w"]
    assert facts["w"]["found"] is None and facts["v"]["found"] is False


class _Wordforms:
    def __init__(self, forms):
        self._forms = forms

    def GetAll(self):
        return list(self._forms)

    def GetForm(self, wordform, ws):
        if wordform == "BROKEN":
            raise RuntimeError("unreadable form")
        return wordform


class _Analyses:
    def GetAll(self, target):
        raise RuntimeError("unreadable analyses")


class _Backend:
    def __init__(self, forms):
        self._project = type("P", (), {"Wordforms": _Wordforms(forms),
                                       "WfiAnalyses": _Analyses()})()

    def _ws_handle(self, ws):
        return 1


def test_the_preview_reader_never_turns_an_unreadable_read_into_an_empty_one():
    from flextoolsmcp.server.filing.preflight_reads import stored_analyses

    assert stored_analyses(_Backend(["kata"]), ["kata", "lain"], None) == {
        "kata": projection.UNREADABLE,            # its analyses threw
        "lain": None,                             # every form read: truly absent
    }
    # One unreadable form: an absent word may BE that wordform.
    assert stored_analyses(_Backend(["BROKEN"]), ["lain"], None) == {"lain": projection.UNREADABLE}


# ---------------------------------------------------------------------------
# FR-015: THE join and THE probe, and no traversal of projection.py's own
# ---------------------------------------------------------------------------


def _imports(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(f"{node.module}.{alias.name}")
    return names


def test_projection_uses_the_one_join_and_the_one_probe():
    tree = ast.parse((SRC / "filing" / "projection.py").read_text(encoding="utf-8"))
    imports = _imports(tree)
    assert any(i.endswith("signals.oracle.segment_occurrence") for i in imports), imports
    assert any(i.startswith("parse.project_state.") or ".parse.project_state." in i
               or i.endswith("project_state.deletion_projection_precondition") for i in imports), imports


def test_projection_contains_no_traversal_of_its_own():
    text = (SRC / "filing" / "projection.py").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in text.splitlines()
        if not line.strip().startswith("#")
    )
    tree = ast.parse(code)
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    forbidden = {"SegmentsOS", "ParagraphsOS", "AnalysesRS", "ContentsOA", "OccurrencesBag"}
    assert not (attrs & forbidden), attrs & forbidden
    called = {n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
              for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert "probe_project_state" not in called, "a second probe traversal"
