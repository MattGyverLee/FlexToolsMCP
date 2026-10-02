#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #351: write-gate regexes over-matched inside longer names.

The gate fails closed, so only over-matches that cannot be a real receiver
are dropped:

- a resolved facade name is one exact identifier (`fx` not in `prefx`);
- a handful of exact English words (`nonsense.Form`, `compose.Comment`,
  `position.Note`) are not receivers.

Everything else stays gated on purpose. Compound FLEx receivers
(`subsense`, `subentry`, `lexentry`, `new_entry`, `newEntry`) have no
structural boundary that separates them from those words, and any name
ending in `project` (`self._project`, `srcProject`, `myproject`) is a
plausible FLExProject handle.
"""

import pytest

from flextoolsmcp.server.validators import (
    _PATTERN_CREATE_GENERIC,
    _PATTERN_CREATE_PROJECT,
    _PATTERN_DELETE_PROJECT,
    _PATTERN_PROJECT_ACCESSOR_CALL,
    _PATTERN_PROPERTY_ASSIGNMENT,
    _PATTERN_UPDATE_PROJECT,
    certify_script_readonly,
    detect_cud_operations,
    find_liblcm_mutations,
)


def _methods(code, facade_names=None):
    return {m["method"] for m in find_liblcm_mutations(code, facade_names)}


class TestOverMatchesGone:
    @pytest.mark.parametrize(
        "code",
        [
            "nonsense.Form = 'x'\n",
            "compose.Comment = 'x'\n",
            "nonsense.Gloss = 'x'\n",
            "position.Note = 'x'\n",
            "self.purpose.Comment = 'x'\n",
        ],
    )
    def test_property_receiver_inside_a_longer_word(self, code):
        assert "property=" not in _methods(code), code
        assert not _PATTERN_PROPERTY_ASSIGNMENT.search(code)

    def test_facade_receiver_inside_a_longer_word(self):
        code = "prefx.LexEntry.SetLexemeForm(e, 'x')\n"
        assert not any(m.startswith("fx.") for m in _methods(code, {"fx"}))

    def test_generic_add_receiver_inside_a_longer_word(self):
        assert not _PATTERN_CREATE_GENERIC.search("nonsense.Things.Add(x)")


class TestRealReceiversStillGated:
    @pytest.mark.parametrize(
        "code",
        [
            "project.LexEntry.Delete(e)\n",
            "self.project.LexEntry.Delete(e)\n",
            "self._project.LexEntry.Delete(e)\n",
            "srcProject.LexEntry.Delete(e)\n",
            "myproject.LexEntry.Delete(e)\n",
            "old_project.LexEntry.Delete(e)\n",
            "subproject.Senses.CreateSense(e)\n",
            "project.LexEntry.Create('x')\n",
            "project.LexEntry.SetLexemeForm(e, 'x')\n",
        ],
    )
    def test_project_receiver(self, code):
        assert any(m.startswith("project.") for m in _methods(code)), code
        assert detect_cud_operations(code)["is_cud"]

    def test_facade_receiver(self):
        code = "fx.LexEntry.SetLexemeForm(e, 'x')\n"
        assert "fx.*.Set/Update" in _methods(code, {"fx"})

    @pytest.mark.parametrize(
        "code",
        [
            "entry.LexemeFormOA = form\n",
            "sense.Gloss = 'x'\n",
            "self.sense.Gloss = 'x'\n",
            "new_entry.LexemeFormOA = form\n",
            "newEntry.LexemeFormOA = form\n",
            "targetSense.Definition = d\n",
            "pos2.Comment = c\n",
            "entryObj.Comment = c\n",
            "subsense.Definition = None\n",
            "subentry.MorphTypeRA = None\n",
            "lexentry.LexemeFormOA = None\n",
            "mainentry.Comment = c\n",
            "self._sense.Gloss = 'x'\n",
            "nonsenseEntry.Gloss = 'x'\n",
        ],
    )
    def test_property_receivers(self, code):
        assert "property=" in _methods(code), code
        assert _PATTERN_PROPERTY_ASSIGNMENT.search(code)

    def test_generic_add_receivers(self):
        assert _PATTERN_CREATE_GENERIC.search("entry.Things.Add(x)")
        assert _PATTERN_CREATE_GENERIC.search("newEntry.Things.Add(x)")
        assert _PATTERN_CREATE_GENERIC.search("new_sense.Things.Add(x)")

    def test_cud_project_patterns(self):
        assert _PATTERN_CREATE_PROJECT.search("project.LexEntry.Create('x')")
        assert _PATTERN_DELETE_PROJECT.search("self.project.LexEntry.Delete(e)")
        assert _PATTERN_UPDATE_PROJECT.search("project.Senses.SetGloss(s, 'x')")
        assert _PATTERN_CREATE_PROJECT.search("myproject.LexEntry.Create('x')")
        assert _PATTERN_DELETE_PROJECT.search("self._project.LexEntry.Delete(e)")
        assert _PATTERN_UPDATE_PROJECT.search("subproject.Senses.SetGloss(s, 'x')")
        assert _PATTERN_PROJECT_ACCESSOR_CALL.search("self._project.LexEntry.Delete(e)")

    def test_generic_add_compound_receivers(self):
        assert _PATTERN_CREATE_GENERIC.search("subsense.Things.Add(x)")
        assert _PATTERN_CREATE_GENERIC.search("lexentry.Things.Add(x)")


class TestReviewerProbes:
    """Whole-script repros: these must not certify read-only."""

    @pytest.mark.parametrize(
        "code",
        [
            "for subsense in e.SensesOS:\n    subsense.Definition = None\n",
            "for lexentry in project.LexiconAllEntries():\n"
            "    lexentry.LexemeFormOA = None\n",
            "for subentry in project.LexiconAllEntries():\n"
            "    subentry.MorphTypeRA = None\n",
            "class T:\n"
            "    def run(self, e):\n"
            "        self._project.LexEntry.Delete(e)\n",
        ],
    )
    def test_not_certified(self, code):
        cert = certify_script_readonly(code, None)
        assert cert["is_certified_readonly"] is False, cert
