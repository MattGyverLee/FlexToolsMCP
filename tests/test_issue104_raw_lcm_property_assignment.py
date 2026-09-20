#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #104: raw-LCM property assignment must count as mutation even when it
doesn't match the old receiver-name regex.
"""

import ast
import sys

sys.path.insert(0, "src")

from flextoolsmcp.server.validators import (  # noqa: E402
    build_writeability_payload,
    certify_script_readonly,
)


def _mutation_calls(payload):
    return [(m["call"], m["protected"]) for m in payload["mutations_detected"]]


def test_cast_alias_property_write_fails_unprotected_writes():
    code = (
        "from SIL.LCModel import ILexSense\n"
        "s_typed = ILexSense(sense)\n"
        "s_typed.MorphoSyntaxAnalysisRA.PartOfSpeechRA = None\n"
    )

    cert = certify_script_readonly(code, None)

    assert cert["is_certified_readonly"] is False
    assert [m["method"] for m in cert["unprotected_liblcm_calls"]] == [
        "ILexSense.MorphoSyntaxAnalysisRA.PartOfSpeechRA="
    ]


def test_inline_cast_property_write_fails_unprotected_writes():
    code = (
        "from SIL.LCModel import IFsClosedValue\n"
        "IFsClosedValue(t).FeatureRA = None\n"
    )

    cert = certify_script_readonly(code, None)

    assert cert["is_certified_readonly"] is False
    assert [m["method"] for m in cert["unprotected_liblcm_calls"]] == [
        "IFsClosedValue.FeatureRA="
    ]


def test_subscript_off_inline_cast_is_still_detected():
    code = (
        "from SIL.LCModel import ILexEntry\n"
        "ILexEntry(entry).SensesOS[0].MorphoSyntaxAnalysisRA.PartOfSpeechRA = None\n"
    )

    cert = certify_script_readonly(code, None)

    assert cert["is_certified_readonly"] is False
    assert [m["method"] for m in cert["unprotected_liblcm_calls"]] == [
        "ILexEntry.SensesOS.MorphoSyntaxAnalysisRA.PartOfSpeechRA="
    ]


def test_guarded_raw_property_write_is_still_mutating():
    code = (
        "from SIL.LCModel import ILexSense\n"
        "def Main(project, report, modifyAllowed):\n"
        "    s_typed = ILexSense(sense)\n"
        "    if modifyAllowed:\n"
        "        s_typed.MorphoSyntaxAnalysisRA.PartOfSpeechRA = None\n"
    )

    tree = ast.parse(code)
    cert = certify_script_readonly(code, None, tree)
    payload = build_writeability_payload(code, None, tree=tree, cert=cert)

    assert cert["is_certified_readonly"] is True
    assert [m["method"] for m in cert["protected_liblcm_calls"]] == [
        "ILexSense.MorphoSyntaxAnalysisRA.PartOfSpeechRA="
    ]
    assert payload["is_mutating_script"] is True
    assert _mutation_calls(payload) == [
        ("ILexSense.MorphoSyntaxAnalysisRA.PartOfSpeechRA=", True)
    ]
