#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The port of HCLoader's two private form predicates (parser-check CP4, FR-039,
R-12; the Principle VI justified violation, pinned live by T081's parity test).

`HCLoader.IsValidLexEntryForm` (`HCLoader.cs:579-589`) and `IsValidRuleForm`
(`:536-569`) exclude a form WITHOUT calling the error logger. An entry whose
forms all fail them never reaches the grammar and leaves no line in the
load-error file -- D-1's silent path. They are private instance methods that
depend on mid-load state, so the gate cannot call them; it ports them. One
fixture per branch below, each named for the line it mirrors.

The live parity test (T081) found three more silent drops, ported below:
an infix with no position and a bracketed affix with no environment; an entry
whose MSAs route no morpheme into the grammar; and an inflectional affix
whose slots all lie outside enabled templates. Whether a PRESENT environment
validates is still not ported (it needs the loader's natural-class tables);
that residual is named in `filing/eligibility.py`'s docstring.
"""

import pytest

from flextoolsmcp.server.filing import eligibility as el

T = el.MORPH_TYPES


def form(cls="MoStemAllomorph", morph="stem", text="pukul", *, abstract=False,
         inputs=0, outputs=0, envs=0, positions=0):
    return {"class_name": cls, "morph_type": T[morph] if morph else None,
            "is_abstract": abstract, "form": text,
            "input_count": inputs, "output_count": outputs,
            "env_count": envs, "position_count": positions}


def entry(lexeme=None, alternates=(), guid="e1", headword="pukul", *,
          msas=None, senses=1, variant_msas=()):
    """`msas=None` is an unread routing: the form predicates alone decide."""
    return {"entry_guid": guid, "headword": headword, "lexeme": lexeme,
            "alternates": list(alternates), "msas": msas,
            "sense_count": senses, "variant_msas": list(variant_msas)}


def msa(kind, *slots):
    return {"kind": kind, "slots": list(slots)}


# ---------------------------------------------------------------------------
# IsValidLexEntryForm (HCLoader.cs:579-589)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("morph", ["root", "stem", "bound_root", "bound_stem", "phrase"])
def test_a_stem_type_stem_allomorph_is_a_valid_lex_entry_form(morph):
    assert el.is_valid_lex_entry_form(form(morph=morph))


@pytest.mark.parametrize("morph", ["clitic", "enclitic", "proclitic", "particle"])
def test_a_clitic_type_stem_allomorph_is_a_valid_lex_entry_form(morph):
    assert el.is_valid_lex_entry_form(form(morph=morph))


def test_a_non_stem_allomorph_is_not_a_lex_entry_form():            # :581-582
    assert not el.is_valid_lex_entry_form(form(cls="MoAffixAllomorph", morph="stem"))


def test_an_empty_form_is_not_a_lex_entry_form():                   # :585-586
    assert not el.is_valid_lex_entry_form(form(text=""))


def test_a_form_of_only_dotted_circles_is_empty():                  # RemoveDottedCircles
    assert not el.is_valid_lex_entry_form(form(text="◌◌"))


def test_an_abstract_form_is_not_a_lex_entry_form():                # :585
    assert not el.is_valid_lex_entry_form(form(abstract=True))


@pytest.mark.parametrize("morph", ["prefix", "suffix", "infix", "circumfix", None])
def test_a_non_stem_non_clitic_type_is_not_a_lex_entry_form(morph):  # :588
    assert not el.is_valid_lex_entry_form(form(morph=morph))


# ---------------------------------------------------------------------------
# IsValidRuleForm (HCLoader.cs:536-569)
# ---------------------------------------------------------------------------


def test_an_affix_process_with_more_than_one_input_is_a_rule_form():   # :539-540
    assert el.is_valid_rule_form(form(cls="MoAffixProcess", morph=None, text="", inputs=2))


def test_an_affix_process_with_more_than_one_output_is_a_rule_form():
    assert el.is_valid_rule_form(form(cls="MoAffixProcess", morph=None, text="", outputs=2))


def test_an_affix_process_with_one_input_and_one_output_is_not():
    assert not el.is_valid_rule_form(form(cls="MoAffixProcess", morph=None, text="", inputs=1, outputs=1))


def test_an_empty_or_abstract_affix_is_not_a_rule_form():            # :542-544
    assert not el.is_valid_rule_form(form(cls="MoAffixAllomorph", morph="prefix", text=""))
    assert not el.is_valid_rule_form(form(cls="MoAffixAllomorph", morph="prefix", abstract=True))


@pytest.mark.parametrize("morph", ["proclitic", "enclitic"])
def test_a_proclitic_or_enclitic_is_a_rule_form(morph):             # :550-552
    assert el.is_valid_rule_form(form(cls="MoStemAllomorph", morph=morph))


@pytest.mark.parametrize("morph", ["prefix", "prefixing_interfix", "suffix", "suffixing_interfix"])
def test_a_prefix_or_suffix_shape_is_a_rule_form(morph):            # :554-560
    assert el.is_valid_rule_form(form(cls="MoAffixAllomorph", morph=morph, text="ber-"))


def test_a_bracketed_affix_needs_an_environment():                   # :558-559
    bracketed = dict(cls="MoAffixAllomorph", morph="suffix", text="[C]-i")
    assert el.is_valid_rule_form(form(**bracketed, envs=1))
    assert not el.is_valid_rule_form(form(**bracketed, envs=0))


def test_a_reduplication_bracket_needs_no_environment():            # :558, "[...]"
    assert el.is_valid_rule_form(form(cls="MoAffixAllomorph", morph="prefix", text="[...]-"))


@pytest.mark.parametrize("morph", ["infix", "infixing_interfix"])
def test_an_infix_needs_a_position(morph):                          # :562-564, T081 (-el-)
    assert el.is_valid_rule_form(form(cls="MoAffixAllomorph", morph=morph, text="-em-", positions=1))
    assert not el.is_valid_rule_form(form(cls="MoAffixAllomorph", morph=morph, text="-em-"))


@pytest.mark.parametrize("morph", ["root", "stem", "circumfix", "simulfix", None])
def test_any_other_type_is_not_a_rule_form(morph):                  # :568
    assert not el.is_valid_rule_form(form(cls="MoAffixAllomorph", morph=morph, text="x"))


# ---------------------------------------------------------------------------
# HasValidRuleForm (HCLoader.cs:517-534), incl. the circumfix branch
# ---------------------------------------------------------------------------


def test_a_circumfix_needs_a_valid_prefix_and_suffix_alternate():  # :519-531
    lexeme = form(cls="MoAffixAllomorph", morph="circumfix", text="ke- -an")
    prefix = form(cls="MoAffixAllomorph", morph="prefix", text="ke-")
    suffix = form(cls="MoAffixAllomorph", morph="suffix", text="-an")
    assert el.has_valid_rule_form(entry(lexeme, [prefix, suffix]))
    assert not el.has_valid_rule_form(entry(lexeme, [prefix]))
    assert not el.has_valid_rule_form(entry(lexeme, [suffix]))
    assert not el.has_valid_rule_form(entry(lexeme, [prefix, form(cls="MoAffixAllomorph", morph="suffix", text="")]))


def test_a_non_circumfix_needs_any_valid_rule_form():               # :533
    assert el.has_valid_rule_form(entry(form(cls="MoAffixAllomorph", morph="prefix", text="ber-")))
    assert not el.has_valid_rule_form(entry(form(cls="MoAffixAllomorph", morph="prefix", text="")))


# ---------------------------------------------------------------------------
# The entry: eligible if a lex-entry form OR a rule form reaches the grammar
# ---------------------------------------------------------------------------


def test_a_root_with_a_form_is_eligible():
    assert el.is_eligible(entry(form()))


def test_an_emptied_only_lexeme_form_is_not_eligible():             # D-1's case
    assert not el.is_eligible(entry(form(text="")))


def test_an_alternate_form_keeps_an_entry_eligible():
    assert el.is_eligible(entry(form(text=""), [form(text="pukul")]))


def test_an_affix_entry_is_eligible_through_its_rule_form():
    assert el.is_eligible(entry(form(cls="MoAffixAllomorph", morph="suffix", text="-kan")))


def test_an_entry_with_no_forms_is_not_eligible():
    assert not el.is_eligible(entry(None))


# ---------------------------------------------------------------------------
# MSA routing (LoadLexEntries, LoadMorphologicalRule) and templates (:295-300)
# ---------------------------------------------------------------------------

SUFFIX = form(cls="MoAffixAllomorph", morph="suffix", text="-kan")


def test_a_stem_form_needs_a_stem_msa():
    assert el.is_eligible(entry(form(), msas=[msa("stem")]))
    assert not el.is_eligible(entry(form(), msas=[]))
    assert not el.is_eligible(entry(form(), msas=[msa("deriv")]))


def test_a_senseless_variant_borrows_its_components_msas():
    assert el.is_eligible(entry(form(), msas=[], senses=0, variant_msas=[msa("stem")]))
    # With senses, the loader never looks at the components.
    assert not el.is_eligible(entry(form(), msas=[], senses=1, variant_msas=[msa("stem")]))


@pytest.mark.parametrize("kind", ["deriv", "unclassified", "stem"])
def test_these_msa_kinds_route_an_affix_rule(kind):
    assert el.is_eligible(entry(SUFFIX, msas=[msa(kind)]))


def test_an_affix_with_no_rule_msa_routes_nowhere():
    assert not el.is_eligible(entry(SUFFIX, msas=[]))
    assert not el.is_eligible(entry(SUFFIX, msas=[msa("other")]))


def test_a_slotless_inflectional_affix_joins_the_stratum():
    assert el.is_eligible(entry(SUFFIX, msas=[msa("infl")]), frozenset())


def test_a_slotted_inflectional_affix_needs_an_enabled_template():    # T081 (-kan2, ber-)
    slotted = entry(SUFFIX, msas=[msa("infl", "slot-1")])
    assert el.is_eligible(slotted, frozenset({"slot-1"}))
    assert not el.is_eligible(slotted, frozenset({"slot-2"}))
    assert el.is_eligible(slotted, None), "unread templates are not judged"


def test_disabling_a_template_drops_its_affixes_from_the_named_set():
    entries = [entry(SUFFIX, guid="k", headword="-kan", msas=[msa("infl", "s1")])]
    assert el.eligible_from_facts(entries, ["S1"]) == [{"entry_guid": "k", "headword": "-kan"}]
    assert el.eligible_from_facts(entries, []) == []


def test_eligible_entries_names_each_entry():
    entries = [entry(form(), guid="e1", headword="pukul"),
               entry(form(text=""), guid="e2", headword="kirim")]
    assert el.eligible_from_facts(entries) == [{"entry_guid": "e1", "headword": "pukul"}]


# ---------------------------------------------------------------------------
# The CLR reader: plain facts from LCM objects, read-only
# ---------------------------------------------------------------------------


class _Text:
    def __init__(self, text):
        self.Text = text


class _Multi:
    def __init__(self, text):
        self.VernacularDefaultWritingSystem = _Text(text)


class _MorphType:
    def __init__(self, guid):
        self.Guid = guid


class _Form:
    def __init__(self, cls, morph, text, abstract=False):
        self.ClassName = cls
        self.MorphTypeRA = _MorphType(T[morph]) if morph else None
        self.Form = _Multi(text)
        self.IsAbstract = abstract


class _Count(list):
    @property
    def Count(self):
        return len(self)


class _Msa:
    def __init__(self, cls, slots=()):
        self.ClassName = cls
        self.SlotsRC = [type("Slot", (), {"Guid": g})() for g in slots]


class _Entry:
    def __init__(self, guid, headword, lexeme, alternates=(), msas=(), senses=1):
        self.Guid = guid
        self.HeadWord = _Text(headword)
        self.LexemeFormOA = lexeme
        self.AlternateFormsOS = list(alternates)
        self.MorphoSyntaxAnalysesOC = list(msas)
        self.SensesOS = _Count([object()] * senses)
        self.EntryRefsOS = []


def test_the_reader_turns_lcm_objects_into_facts():
    lcm_entry = _Entry("E1", "pukul", _Form("MoStemAllomorph", "root", "pukul"),
                       msas=[_Msa("MoStemMsa")])
    facts = el.entry_facts(lcm_entry)
    assert facts["entry_guid"] == "e1" and facts["headword"] == "pukul"
    assert facts["lexeme"]["morph_type"] == T["root"]
    assert el.is_eligible(facts)


def test_the_reader_does_not_raise_on_a_missing_morph_type():
    lcm_entry = _Entry("E2", "x", _Form("MoStemAllomorph", None, "x"))
    assert not el.is_eligible(el.entry_facts(lcm_entry))


def test_the_reader_reads_msa_kinds_and_slots():
    lcm_entry = _Entry("E3", "-kan", _Form("MoAffixAllomorph", "suffix", "kan"),
                       msas=[_Msa("MoInflAffMsa", ["S-1"]), _Msa("MoDerivAffMsa")])
    facts = el.entry_facts(lcm_entry)
    assert facts["msas"] == [{"kind": "infl", "slots": ["s-1"]}, {"kind": "deriv", "slots": []}]
    assert facts["sense_count"] == 1 and facts["variant_msas"] == []


def test_the_reader_reports_unreadable_routing_as_unread():
    lcm_entry = _Entry("E4", "x", _Form("MoStemAllomorph", "root", "x"))
    del lcm_entry.MorphoSyntaxAnalysesOC
    facts = el.entry_facts(lcm_entry)
    assert facts["msas"] is None and el.is_eligible(facts)


def test_the_reader_counts_an_affix_allomorphs_environments_and_positions():
    infix = _Form("MoAffixAllomorph", "infix", "el")
    infix.PhoneEnvRC = _Count()
    infix.PositionRS = _Count([object()])
    facts = el.entry_facts(_Entry("E5", "-el-", infix, msas=[_Msa("MoDerivAffMsa")]))
    assert facts["lexeme"]["position_count"] == 1 and facts["lexeme"]["env_count"] == 0
    assert el.is_eligible(facts)
