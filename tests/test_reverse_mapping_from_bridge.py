"""Regression tests for the two defects that made member-level coverage
unanswerable from the shipped indexes.

1. The analyzer emitted property names in two spellings -- bare, and with a
   trailing " (Kind)" annotation -- and a name matching BOTH the suffix rule
   and COMMON_LCM_PROPERTIES (LexemeFormOA, MorphTypeRA, PartOfSpeechRA) got
   appended in both forms inside one file. Any join against the LCM index
   silently dropped most property rows.

2. build_reverse_mapping read `method["lcm_mapping"]`, which the analyzer no
   longer writes inline -- that data moved to flexicon_lcm_bridge's
   `by_method`. Every method therefore looked like `pure_python`, hit the
   early `continue`, and nothing was indexed: statistics reported
   total_mappings == 0 and python_wrappers entries carried "methods": [].

Both are silent failures: the structures existed and parsed, they were just
empty, which reads as "no coverage" rather than "not computed".
"""

import ast

from flextoolsmcp.build_reverse_mapping import build_reverse_mapping
from flextoolsmcp.flexicon_analyzer import extract_lcm_calls


# ---------------------------------------------------------------------------
# 1. property-name normalization
# ---------------------------------------------------------------------------

_SAMPLE = """
def GetSenses(self, entry):
    form = entry.LexemeFormOA
    mt = entry.MorphTypeRA
    for s in entry.SensesOS:
        g = s.Gloss
        refs = s.DoNotPublishInRC
    return entry.Hvo
"""


def _analyze(src):
    return extract_lcm_calls(ast.parse(src).body[0], [])


def test_property_names_are_bare():
    props = _analyze(_SAMPLE)["properties_accessed"]
    assert props, "expected property accesses to be detected"
    annotated = [p for p in props if "(" in p]
    assert annotated == [], f"annotated spellings leaked into the index: {annotated}"


def test_property_kinds_recorded_separately():
    out = _analyze(_SAMPLE)
    assert out["property_kinds"]["SensesOS"] == "OwningSequence"
    assert out["property_kinds"]["DoNotPublishInRC"] == "ReferenceCollection"
    assert out["property_kinds"]["LexemeFormOA"] == "OwningAtomic"
    # recognised by name alone, carries no suffix kind
    assert "Gloss" not in out["property_kinds"]


def test_dual_matching_names_appear_once():
    """LexemeFormOA/MorphTypeRA match both the suffix rule and
    COMMON_LCM_PROPERTIES. They must still be emitted exactly once."""
    props = _analyze(_SAMPLE)["properties_accessed"]
    for name in ("LexemeFormOA", "MorphTypeRA"):
        assert props.count(name) == 1, f"{name} emitted {props.count(name)}x"


def test_property_names_join_against_lcm_member_names():
    """A bare name is what liblcm_api stores; an annotated one never matches."""
    props = _analyze(_SAMPLE)["properties_accessed"]
    lcm_member_names = {"LexemeFormOA", "MorphTypeRA", "SensesOS", "Gloss",
                        "DoNotPublishInRC", "Hvo"}
    assert set(props) <= lcm_member_names


# ---------------------------------------------------------------------------
# 2. reverse mapping sourced from the bridge
# ---------------------------------------------------------------------------

def _flexicon_doc():
    return {
        "entities": {
            "LexSenseOperations": {
                "category": "lexicon",
                "lcm_dependencies": ["ILexSense", "ILexEntry"],
                "methods": [
                    {"name": "GetGloss", "signature": "GetGloss(sense)", "summary": "Read a gloss."},
                    {"name": "SetGloss", "signature": "SetGloss(sense, ws, text)", "summary": "Write a gloss."},
                    {"name": "_helper", "signature": "_helper()", "summary": "Pure python."},
                ],
            }
        }
    }


def _bridge_doc():
    return {
        "by_method": {
            "LexSenseOperations.GetGloss": {
                "mapping_type": "direct",
                "properties_accessed": ["Gloss"],
                "methods_called": [".get_String()"],
                "factories_used": [],
                "repositories_used": [],
            },
            "LexSenseOperations.SetGloss": {
                "mapping_type": "convenience",
                "properties_accessed": ["Gloss"],
                "methods_called": [".set_String()"],
                "factories_used": ["ILexSenseFactory"],
                "repositories_used": ["ILexSenseRepository"],
            },
            "LexSenseOperations._helper": {
                "mapping_type": "pure_python",
                "properties_accessed": [],
                "methods_called": [],
                "factories_used": [],
                "repositories_used": [],
            },
        }
    }


def _write(tmp_path, name, doc):
    import json
    p = tmp_path / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_bridge_populates_statistics(tmp_path):
    result = build_reverse_mapping(
        _write(tmp_path, "flexicon_api_v1.0.0.json", _flexicon_doc()),
        None, None,
        _write(tmp_path, "flexicon_lcm_bridge_v1.0.0.json", _bridge_doc()),
    )
    stats = result["statistics"]
    # the pure_python method is correctly skipped; the other two are indexed
    assert stats["total_mappings"] == 2
    assert stats["properties_mapped"] == 2
    assert stats["methods_mapped"] == 2
    assert stats["factories_mapped"] == 1
    assert stats["repositories_mapped"] == 1


def test_bridge_populates_member_buckets(tmp_path):
    result = build_reverse_mapping(
        _write(tmp_path, "flexicon_api_v1.0.0.json", _flexicon_doc()),
        None, None,
        _write(tmp_path, "flexicon_lcm_bridge_v1.0.0.json", _bridge_doc()),
    )
    assert "Gloss" in result["properties"]
    assert {w["method"] for w in result["properties"]["Gloss"]} == {"GetGloss", "SetGloss"}
    assert "get_String" in result["methods"]
    assert "ILexSenseFactory" in result["factories"]
    assert "ILexSenseRepository" in result["repositories"]


def test_wrapper_entries_carry_method_names(tmp_path):
    """python_wrappers is built from this; an empty methods list is what made
    'wrapped' indistinguishable from 'not wrapped' at member level."""
    result = build_reverse_mapping(
        _write(tmp_path, "flexicon_api_v1.0.0.json", _flexicon_doc()),
        None, None,
        _write(tmp_path, "flexicon_lcm_bridge_v1.0.0.json", _bridge_doc()),
    )
    entry = result["by_liblcm_entity"]["ILexSense"]["flexlibs_2"]
    wrappers = entry if isinstance(entry, list) else [entry]
    methods = {m for w in wrappers for m in w["methods"]}
    assert methods == {"GetGloss", "SetGloss"}


def test_missing_bridge_is_empty_but_not_silent(tmp_path, capsys):
    """Without a bridge the result is empty -- that is honest, but it has to
    announce itself rather than look like a real zero-coverage finding."""
    result = build_reverse_mapping(
        _write(tmp_path, "flexicon_api_v1.0.0.json", _flexicon_doc()),
        None, None, None,
    )
    assert result["statistics"]["total_mappings"] == 0
    assert "No bridge index" in capsys.readouterr().out
