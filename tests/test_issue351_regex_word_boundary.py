#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #351: write-gate regexes need a left boundary before the receiver.

Without one, `myproject.X.Delete(...)` and `nonsense.Form = ...` matched the
`project` / `sense` receiver patterns. The fix must keep the conventional
prefixed spellings of a real receiver gated: `self.project.X.Delete(...)`,
`new_entry.Gloss = ...` and camelCase `newEntry.LexemeFormOA = ...`.
"""

import pytest

from flextoolsmcp.server.validators import (
    _PATTERN_CREATE_GENERIC,
    _PATTERN_CREATE_PROJECT,
    _PATTERN_DELETE_PROJECT,
    _PATTERN_PROJECT_ACCESSOR_CALL,
    _PATTERN_PROPERTY_ASSIGNMENT,
    _PATTERN_UPDATE_PROJECT,
    detect_cud_operations,
    find_liblcm_mutations,
)


def _methods(code, facade_names=None):
    return {m["method"] for m in find_liblcm_mutations(code, facade_names)}


class TestOverMatchesGone:
    @pytest.mark.parametrize(
        "code",
        [
            "myproject.LexEntry.Delete(e)\n",
            "old_project.LexEntry.Delete(e)\n",
            "subproject.Senses.CreateSense(e)\n",
            "myproject.LexEntry.SetLexemeForm(e, 'x')\n",
        ],
    )
    def test_project_suffix_names_not_project(self, code):
        assert not any(m.startswith("project.") for m in _methods(code)), code

    @pytest.mark.parametrize(
        "code",
        ["nonsense.Form = 'x'\n", "compose.Comment = 'x'\n", "nonsense.Gloss = 'x'\n"],
    )
    def test_property_receiver_inside_a_longer_word(self, code):
        assert "property=" not in _methods(code), code
        assert not _PATTERN_PROPERTY_ASSIGNMENT.search(code)

    def test_facade_receiver_inside_a_longer_word(self):
        code = "prefx.LexEntry.SetLexemeForm(e, 'x')\n"
        assert not any(m.startswith("fx.") for m in _methods(code, {"fx"}))

    def test_generic_add_receiver_inside_a_longer_word(self):
        assert not _PATTERN_CREATE_GENERIC.search("nonsense.Things.Add(x)")

    def test_accessor_call_pattern(self):
        assert not _PATTERN_PROJECT_ACCESSOR_CALL.search("old_project.LexEntry.Delete(e)")


class TestRealReceiversStillGated:
    @pytest.mark.parametrize(
        "code",
        [
            "project.LexEntry.Delete(e)\n",
            "self.project.LexEntry.Delete(e)\n",
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
        assert not _PATTERN_CREATE_PROJECT.search("myproject.LexEntry.Create('x')")
        assert not _PATTERN_DELETE_PROJECT.search("old_project.LexEntry.Delete(e)")
        assert not _PATTERN_UPDATE_PROJECT.search("subproject.Senses.SetGloss(s, 'x')")
