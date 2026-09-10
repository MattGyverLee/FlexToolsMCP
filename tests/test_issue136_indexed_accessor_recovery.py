#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #136: recover parameterized get_/set_ accessors that
extract_method's blanket prefix filter used to drop unconditionally.

Background (see specs/liblcm-core-coverage/reviews/cycle1-domain.md and
cycle1-qc.md): `ITsString` is COM-imported, so `GetProperties()` yields zero
indexed `PropertyInfo` objects for it -- its 8 accessors (get_RunAt,
get_MinOfRun, get_LimOfRun, get_RunText, get_PropertiesAt, get_Properties,
get_IsNormalizedForm, get_NormalizedForm) survive only via `GetMethods()`,
and the old blanket `get_/set_/add_/remove_` filter silently discarded all of
them. The fix relaxes that filter behind two conjunctive gates:

  Gate 1 (arity): retain get_* only if arity >= 1, set_* only if arity >= 2
    (an ordinary zero-arg getter/single-arg setter is already covered by
    extract_property() via GetProperties()).
  Gate 2 (backing accessor): drop the method if it IS the GetMethod/
    SetMethod of a PropertyInfo GetProperties() already surfaced on that
    type (identity check first, base-name string fallback second) -- this
    is what removes the get_Item/set_Item duplicates on IStText, LcmList,
    SmallDictionary, etc., where the managed indexer already has a real
    PropertyInfo.

Coverage:
  (a) An indexed COM accessor (get_Properties(int ich), no backing
      PropertyInfo at all) is retained with indexed: true,
      index_param_type: "Int32".
  (b) A managed indexer's get_Item -- identity-matched to a real
      PropertyInfo's GetGetMethod() -- is DROPPED by gate 2.
  (c) An enum-param accessor (get_IsNormalizedForm(FwNormalizationMode)) is
      retained with indexed: false and no index_param_type key at all.

Plus regression guards: add_/remove_ event accessors and ordinary zero-arg
get_/set_ accessors remain filtered (gate 1's whole reason for existing),
and gate 2's string-name fallback independently drops a same-named
accessor even when identity comparison can't be used.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import flextoolsmcp.liblcm_extractor as liblcm_extractor  # noqa: E402
from flextoolsmcp.liblcm_extractor import (  # noqa: E402
    categorize_method,
    extract_method,
)


# ---- Fakes mirroring the pythonnet reflection surface extract_method uses --

class FakeType:
    def __init__(self, name):
        self.Name = name


class FakeParameterInfo:
    def __init__(self, name, type_name, is_optional=False, has_default=False):
        self.Name = name
        self.ParameterType = FakeType(type_name)
        self.IsOptional = is_optional
        self.HasDefaultValue = has_default
        self.DefaultValue = None


class FakeMethodInfo:
    """Stand-in for System.Reflection.MethodInfo. `.Equals()` mirrors the
    real CLR semantics extract_method's gate 2 relies on: two MethodInfo
    instances describing the *same* underlying accessor compare equal."""

    def __init__(self, name, parameters=None, return_type="Void",
                 is_static=False, is_virtual=True, is_abstract=False):
        self.Name = name
        self._parameters = parameters or []
        self.ReturnType = FakeType(return_type)
        self.IsStatic = is_static
        self.IsVirtual = is_virtual
        self.IsAbstract = is_abstract

    def GetParameters(self):
        return self._parameters

    def Equals(self, other):
        return self is other


class FakePropertyInfo:
    def __init__(self, name, getter=None, setter=None):
        self.Name = name
        self._getter = getter
        self._setter = setter

    def GetGetMethod(self, non_public=True):
        return self._getter

    def GetSetMethod(self, non_public=True):
        return self._setter


@pytest.fixture(autouse=True)
def _pythonnet_available(monkeypatch):
    """extract_method() short-circuits to None unless PYTHONNET_AVAILABLE."""
    monkeypatch.setattr(liblcm_extractor, "PYTHONNET_AVAILABLE", True)


# ---- (a) indexed COM accessor: no backing PropertyInfo at all -------------

def test_indexed_com_accessor_retained_with_indexed_true():
    """get_Properties(int irun) on ITsString (COM-imported, zero
    PropertyInfo objects) must survive with indexed: true and
    index_param_type mirroring the sole Int32 parameter. Parameter is named
    "irun" (a run index) per the real TsStrBase.cs source ("Gets the text
    properties for the specified run"), not "ich" -- the domain review's
    draft assumed a character-offset parameter, which live reflection
    disproves."""
    minfo = FakeMethodInfo(
        "get_Properties",
        parameters=[FakeParameterInfo("irun", "Int32")],
        return_type="ITsTextProps",
    )

    result = extract_method(minfo, type_properties=[])

    assert result is not None
    assert result["name"] == "get_Properties"
    assert result["signature"] == "get_Properties(Int32 irun)"
    assert result["indexed"] is True
    assert result["index_param_type"] == "Int32"
    assert result["category"] == "retrieval"
    assert "writing-system id" in result["description"]
    assert "run index, not a character offset" in result["description"]


def test_get_run_text_indexed_and_teaching_description():
    """get_RunText(int irun) is the review's second named example -- same
    gate-1 shape as get_Properties. Per the real TsStrBase.cs source
    ("Gets the text for the specified run"), the parameter is a run index,
    not a character offset -- the shipped description says so explicitly
    and cross-references get_RunAt(ich) for the offset case."""
    minfo = FakeMethodInfo(
        "get_RunText",
        parameters=[FakeParameterInfo("irun", "Int32")],
        return_type="String",
    )

    result = extract_method(minfo, type_properties=[])

    assert result is not None
    assert result["indexed"] is True
    assert result["index_param_type"] == "Int32"
    assert result["category"] == "retrieval"
    assert "run index, not a character offset" in result["description"]
    assert "get_Properties(irun)" in result["description"]


# ---- (b) managed indexer's get_Item dropped by gate 2 ----------------------

def test_managed_indexer_get_item_dropped_by_identity():
    """A real C# indexer (e.g. LcmList.Item[int]) already has a PropertyInfo
    surfaced via GetProperties(); its GetGetMethod() returns the *same*
    MethodInfo GetMethods() would also yield. Gate 2 must drop it so it is
    not duplicated as a second, method-shaped entry."""
    get_item = FakeMethodInfo(
        "get_Item",
        parameters=[FakeParameterInfo("index", "Int32")],
        return_type="Object",
    )
    item_property = FakePropertyInfo("Item", getter=get_item)

    result = extract_method(get_item, type_properties=[item_property])

    assert result is None


def test_managed_indexer_set_item_dropped_by_identity():
    set_item = FakeMethodInfo(
        "set_Item",
        parameters=[FakeParameterInfo("index", "Int32"), FakeParameterInfo("value", "Object")],
        return_type="Void",
    )
    item_property = FakePropertyInfo("Item", setter=set_item)

    result = extract_method(set_item, type_properties=[item_property])

    assert result is None


def test_string_fallback_drops_same_named_accessor_without_identity_match():
    """Gate 2's secondary fallback: even when the PropertyInfo's
    GetGetMethod() returns a *different* MethodInfo instance than the one
    GetMethods() yielded (identity comparison misses), a base-name string
    match against an existing property named "Item" still drops it."""
    reflected_get_item = FakeMethodInfo(
        "get_Item", parameters=[FakeParameterInfo("index", "Int32")], return_type="Object"
    )
    differently_cached_getter = FakeMethodInfo(
        "get_Item", parameters=[FakeParameterInfo("index", "Int32")], return_type="Object"
    )
    item_property = FakePropertyInfo("Item", getter=differently_cached_getter)

    result = extract_method(reflected_get_item, type_properties=[item_property])

    assert result is None


# ---- (c) enum-param accessor: indexed:false, no index_param_type ----------

def test_enum_param_accessor_retained_indexed_false_no_index_param_type():
    """get_IsNormalizedForm(FwNormalizationMode) has exactly one parameter,
    but it's an enum, not Int32 -- indexed must be false and
    index_param_type must be absent entirely (emitting it would falsely
    assert an index that doesn't exist)."""
    minfo = FakeMethodInfo(
        "get_IsNormalizedForm",
        parameters=[FakeParameterInfo("nm", "FwNormalizationMode")],
        return_type="Boolean",
    )

    result = extract_method(minfo, type_properties=[])

    assert result is not None
    assert result["indexed"] is False
    assert "index_param_type" not in result


def test_two_param_flid_accessor_retained_indexed_false():
    """get_ObjectProp(hvo, flid) is a real, deliberately-kept generic FLID
    accessor (ISilDataAccess et al. -- explicit lead ruling, no type
    allowlist). Two parameters means indexed is false, and
    index_param_type must not appear."""
    minfo = FakeMethodInfo(
        "get_ObjectProp",
        parameters=[FakeParameterInfo("hvo", "Int32"), FakeParameterInfo("flid", "Int32")],
        return_type="Int32",
    )

    result = extract_method(minfo, type_properties=[])

    assert result is not None
    assert result["indexed"] is False
    assert "index_param_type" not in result


# ---- Regression guards: gate 1 still filters what it always filtered ------

def test_ordinary_zero_arg_getter_still_filtered():
    """An ordinary property getter (arity 0) is already covered by
    extract_property() via GetProperties() -- gate 1 must keep rejecting it,
    same as the pre-#136 behavior."""
    minfo = FakeMethodInfo("get_Name", parameters=[], return_type="String")

    assert extract_method(minfo, type_properties=[]) is None


def test_ordinary_single_arg_setter_still_filtered():
    """set_Name(value) has arity 1; gate 1 requires >=2 for setters."""
    minfo = FakeMethodInfo(
        "set_Name", parameters=[FakeParameterInfo("value", "String")], return_type="Void"
    )

    assert extract_method(minfo, type_properties=[]) is None


def test_event_accessors_remain_filtered():
    """add_/remove_ event accessors have no arity/indexing semantics to gate
    on and must remain unconditionally filtered."""
    add_minfo = FakeMethodInfo(
        "add_PropertyChanged",
        parameters=[FakeParameterInfo("handler", "PropertyChangedEventHandler")],
    )
    remove_minfo = FakeMethodInfo(
        "remove_PropertyChanged",
        parameters=[FakeParameterInfo("handler", "PropertyChangedEventHandler")],
    )

    assert extract_method(add_minfo, type_properties=[]) is None
    assert extract_method(remove_minfo, type_properties=[]) is None


def test_normal_pascal_case_method_untouched():
    """A normal API method (no get_/set_ prefix) is unaffected by any of
    #136's gates and never gains indexed/index_param_type."""
    minfo = FakeMethodInfo(
        "GetHeadword", parameters=[FakeParameterInfo("ws", "Int32")], return_type="String"
    )

    result = extract_method(minfo, type_properties=[])

    assert result is not None
    assert "indexed" not in result
    assert "index_param_type" not in result
    assert result["category"] == "retrieval"


def test_categorize_method_recognizes_lowercase_accessor_prefixes():
    """categorize_method's PascalCase checks ("Get", "Set", ...) never match
    the lowercase get_/set_ prefix pythonnet exposes for recovered
    accessors; without an explicit lowercase check they'd all fall through
    to the generic "operation" category instead of the domain review's
    "retrieval"/"modification"."""
    assert categorize_method("get_Properties") == "retrieval"
    assert categorize_method("set_Whatever") == "modification"
