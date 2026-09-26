"""Tests for LibLCM index post-build sanity checks (#140)."""

from flextoolsmcp.liblcm_index_sanity import (
    ANCHOR_MIN_MEMBER_COUNTS,
    apply_index_sanity_audit,
    audit_anchor_entities,
    audit_namespace_coverage,
)


def _entity(entity_id: str, namespace: str, *, props=(), methods=()):
    return {
        "id": entity_id,
        "namespace": namespace,
        "properties": [{"name": n} for n in props],
        "methods": [{"name": n} for n in methods],
    }


def test_audit_namespace_coverage_flags_empty_kernel_interfaces():
    api_doc = {
        "entities": {
            "ILexEntry": _entity(
                "ILexEntry",
                "SIL.LCModel",
                props=["LexemeFormOA"],
                methods=["GetAll"],
            ),
        }
    }
    warnings = audit_namespace_coverage(api_doc)
    assert any("KernelInterfaces" in w for w in warnings)


def test_audit_namespace_coverage_clean_on_representative_counts():
    entities = {
        "ILexEntry": _entity(
            "ILexEntry",
            "SIL.LCModel",
            props=["LexemeFormOA", "SensesOS", "CitationForm"],
            methods=["GetAll", "AddSense", "RemoveSense", "GetGuid"],
        ),
    }
    for i in range(55):
        entities[f"ITsStub{i}"] = _entity(
            f"ITsStub{i}",
            "SIL.LCModel.Core.KernelInterfaces",
            props=["A", "B", "C"],
            methods=["M1"],
        )
    for i in range(12):
        entities[f"ITextStub{i}"] = _entity(
            f"ITextStub{i}",
            "SIL.LCModel.Core.Text",
            props=["A"],
            methods=["M1"],
        )
    for i in range(50):
        entities[f"ILexStub{i}"] = _entity(
            f"ILexStub{i}",
            "SIL.LCModel",
            props=["A"],
            methods=["M1"],
        )

    warnings = audit_namespace_coverage({"entities": entities})
    assert warnings == []


def test_audit_anchor_entities_missing_and_hollow():
    api_doc = {"entities": {}}
    assert any("ITsString" in w for w in audit_anchor_entities(api_doc))

    api_doc = {
        "entities": {
            "ITsString": _entity("ITsString", "SIL.LCModel.Core.KernelInterfaces"),
        }
    }
    warnings = audit_anchor_entities(api_doc)
    assert any("only 0 indexed" in w for w in warnings)


def test_apply_index_sanity_audit_records_metadata():
    api_doc = {"entities": {}, "metadata": {}}
    warnings = apply_index_sanity_audit(api_doc)
    assert warnings
    assert api_doc["metadata"]["index_sanity_warnings"]
    assert api_doc["metadata"]["coverage_gaps"]


def test_anchor_thresholds_match_documented_anchors():
    assert "ITsString" in ANCHOR_MIN_MEMBER_COUNTS
    assert "ILexEntry" in ANCHOR_MIN_MEMBER_COUNTS
