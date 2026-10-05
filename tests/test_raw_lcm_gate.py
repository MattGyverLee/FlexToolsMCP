#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for unified-recipes T031: the raw-LibLCM gate (FR-045, R18).

``detect_raw_lcm_access`` (used only by ``recipe_validator`` with
``shipped=True``) flags casts to ``I*`` interfaces, ``*OA``/``*OS``/``*OC``/
``*RA``/``*RS``/``*RC`` property access, ``project.project``,
``ServiceLocator`` and ``ClassName`` dispatch. Wrapper suggestions come from
the inverted flexicon bridge index (``flexicon_lcm_bridge_v4.12.0.json``),
never a hand-kept table: ``Duplicate``/``Delete`` are never suggested, and a
``# raw-lcm: <reason>`` note overrides a wrapper suggestion.
"""

import json

import pytest

from flextoolsmcp.recipe_validator import validate_recipe
from flextoolsmcp.server import APIIndex, get_index_dir
from flextoolsmcp.server import kernel
from flextoolsmcp.server.validators import detect_raw_lcm_access


@pytest.fixture(scope="module")
def api_index():
    """Real API index plus the real 4.12.0 bridge file."""
    index = APIIndex.load(get_index_dir())
    index.ensure_flexicon_bridge_loaded()
    assert index.flexicon_lcm_bridge, "flexicon bridge index failed to load"
    return index


@pytest.fixture(autouse=True)
def _configure_session(api_index):
    kernel.set_api_index(api_index)
    kernel.session_state.configure(session_id="test-raw-lcm-gate", api_mode="flexicon")
    yield


PHONE_ENV_CODE = (
    "for entry in project.LexEntry.GetAll():\n"
    "    for allo in project.LexEntry.GetAllAllomorphs(entry):\n"
    "        for env in allo.PhoneEnvRC:\n"
    "            report.Info(str(env))\n"
)

# ProdRestrictRC has no flexicon wrapper (ledger gap B4, flexicon#574).
UNWRAPPED_CODE = (
    "for entry in project.LexEntry.GetAll():\n"
    "    msa = project.LexSense.GetMSA(project.LexEntry.GetAllSenses(entry)[0])\n"
    "    restr = msa.ProdRestrictRC\n"
    "    report.Info(str(restr))\n"
)


def _recipe(code, **overrides):
    recipe = {
        "id": "seed-raw-lcm",
        "intent": "seed",
        "match_terms": ["seed"],
        "entities": ["LexEntry"],
        "operations": ["read"],
        "requires_write": False,
        "code": code,
        "notes": "seed",
        "origin": "test",
        "source": "curated",
        "verified_against": {"flexicon": "4.11.0", "verified_by": "preflight"},
    }
    recipe.update(overrides)
    return recipe


class TestBridgeInversion:
    def test_phone_env_maps_to_allomorph_wrappers(self, api_index):
        bridge = api_index.flexicon_lcm_bridge["by_method"]
        holders = sorted(
            name
            for name, entry in bridge.items()
            for prop in (entry.get("properties_accessed") or [])
            if prop.split(" ")[0] == "PhoneEnvRC"
        )
        assert "AllomorphOperations.GetPhoneEnv" in holders

    def test_duplicate_and_delete_are_never_suggested(self, api_index):
        check = detect_raw_lcm_access(PHONE_ENV_CODE, None, api_index)
        assert check["has_raw"]
        for finding in check["findings"]:
            for suggestion in finding.get("suggestions", []):
                method = suggestion.split(".")[-1]
                assert method not in ("Duplicate", "Delete")
                assert not method.startswith("Copy")
                assert method != "__init__"


class TestWrappedProperty:
    def test_phone_env_without_note_fails_and_names_wrapper(self, api_index):
        check = detect_raw_lcm_access(PHONE_ENV_CODE, None, api_index)
        assert check["has_raw"]
        assert any(
            "AllomorphOperations.GetPhoneEnv" in f.get("message", "")
            for f in check["findings"]
        )

    def test_raw_lcm_note_overrides_wrapper_suggestion(self, api_index):
        code = PHONE_ENV_CODE.replace(
            "for env in allo.PhoneEnvRC:",
            "for env in allo.PhoneEnvRC:  # raw-lcm: iterating the RC directly",
        )
        check = detect_raw_lcm_access(code, None, api_index)
        assert not check["has_raw"], check["findings"]

    def test_gap_note_does_not_override_wrapper_suggestion(self, api_index):
        code = PHONE_ENV_CODE.replace(
            "for env in allo.PhoneEnvRC:",
            "for env in allo.PhoneEnvRC:  # flexicon gap: #999",
        )
        check = detect_raw_lcm_access(code, None, api_index)
        assert check["has_raw"]


class TestUnwrappedProperty:
    def test_unwrapped_without_note_fails(self, api_index):
        check = detect_raw_lcm_access(UNWRAPPED_CODE, None, api_index)
        assert check["has_raw"]

    def test_unwrapped_passes_with_gap_note(self, api_index):
        code = UNWRAPPED_CODE.replace(
            "restr = msa.ProdRestrictRC",
            "restr = msa.ProdRestrictRC  # flexicon gap: #574",
        )
        check = detect_raw_lcm_access(code, None, api_index)
        assert not check["has_raw"], check["findings"]

    def test_unwrapped_passes_with_raw_lcm_note(self, api_index):
        code = UNWRAPPED_CODE.replace(
            "restr = msa.ProdRestrictRC",
            "restr = msa.ProdRestrictRC  # raw-lcm: no wrapper until #574",
        )
        check = detect_raw_lcm_access(code, None, api_index)
        assert not check["has_raw"], check["findings"]


class TestOtherRawForms:
    @pytest.mark.parametrize(
        "snippet",
        [
            "x = IMoStemAllomorph(allo)\nreport.Info(str(x))\n",
            "lp = project.project\nreport.Info(str(lp))\n",
            "svc = ServiceLocator.GetService('x')\nreport.Info(str(svc))\n",
            "if allo.ClassName == 'MoStemAllomorph':\n    report.Info('stem')\n",
        ],
    )
    def test_each_raw_form_is_flagged(self, api_index, snippet):
        check = detect_raw_lcm_access(snippet, None, api_index)
        assert check["has_raw"], snippet


class TestAcronymNamesAreNotRaw:
    # project.POS and GetAllAffixTemplatesForPOS end in "OS" but are
    # flexicon names, not LCM *OS properties (upper-case letter before the
    # suffix).
    def test_pos_accessor_and_for_pos_method_not_flagged(self, api_index):
        code = (
            "verb = project.POS.Find('Verb')\n"
            "for t in project.MorphRules.GetAllAffixTemplatesForPOS(verb):\n"
            "    report.Info(project.POS.GetName(verb))\n"
        )
        check = detect_raw_lcm_access(code, None, api_index)
        assert check["count"] == 0, check["findings"]

    def test_code_terms_keep_pos(self):
        from flextoolsmcp.recipe_files import extract_code_terms

        terms = extract_code_terms("x = project.POS.GetName(p)\n")
        assert "pos" in terms and "speech" in terms, terms


class TestRawLcmLineRatchet:
    def _two_line_code(self):
        return (
            "for entry in project.LexEntry.GetAll():\n"
            "    for allo in project.LexEntry.GetAllAllomorphs(entry):\n"
            "        for env in allo.PhoneEnvRC:  # raw-lcm: iterating directly\n"
            "            for env2 in allo.PhoneEnvRC:  # raw-lcm: second use\n"
            "                report.Info(str(env))\n"
        )

    def test_count_above_raw_lcm_lines_fails(self, api_index):
        result = validate_recipe(
            _recipe(self._two_line_code(), raw_lcm_lines=1), api_index, shipped=True
        )
        assert not result["passed"]
        assert any("raw_lcm_lines" in issue for issue in result["issues"])

    def test_count_equal_to_raw_lcm_lines_passes(self, api_index):
        result = validate_recipe(
            _recipe(self._two_line_code(), raw_lcm_lines=2), api_index, shipped=True
        )
        assert result["passed"], result["issues"]

    def test_count_below_raw_lcm_lines_passes_with_lower_note(self, api_index):
        result = validate_recipe(
            _recipe(self._two_line_code(), raw_lcm_lines=5), api_index, shipped=True
        )
        assert result["passed"], result["issues"]
        assert any("raw_lcm_lines" in note for note in result.get("notes", []))

    def test_raw_access_without_header_count_fails(self, api_index):
        result = validate_recipe(_recipe(self._two_line_code()), api_index, shipped=True)
        assert not result["passed"]
        assert any("raw_lcm_lines" in issue for issue in result["issues"])

    def test_serialised_bridge_file_drives_suggestions(self, api_index):
        # The inversion is tested against the real 4.12.0 bridge file, not a
        # fixture: reload it from disk and compare candidate sets.
        from flextoolsmcp.server.validators import _bridge_property_map

        raw = json.load(
            open(
                get_index_dir() / "python" / "flexicon_lcm_bridge_v4.12.0.json",
                encoding="utf-8",
            )
        )
        assert _bridge_property_map(raw).get("PhoneEnvRC", []) == _bridge_property_map(
            api_index.flexicon_lcm_bridge
        ).get("PhoneEnvRC", [])
