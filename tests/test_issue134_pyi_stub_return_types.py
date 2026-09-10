#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #134: consult a sibling .pyi stub for return-type extraction.

flexicon ships 47 `.pyi` stubs beside its 111 source modules, carrying 542
return annotations, and the analyzer consulted none of them -- `grep -rn
"\\.pyi" src/` returned nothing before this change. A def with neither an
inline annotation nor a Google-style `Returns:` block indexed as
`return_type: ""` even when the stub next to it stated the type.

Coverage:
  - extract_stub_return_types() maps {(class_or_None, func): return_type}
    from a sibling stub, recursing into nested classes and keying
    module-level functions off a None class name.
  - It degrades quietly: no stub, or an unparsable one, yields {} rather
    than raising, so the 64 stubless modules index exactly as before.
  - _return_type_from_annotation() normalizes both annotation tiers
    identically -- notably a string forward reference (`-> "FLExProject"`)
    renders as `FLExProject`, without the quotes ast.unparse() would keep.
  - Precedence is inline annotation > docstring > stub, and the stub tier
    only ever fills a return_type that is still "".

  - REGRESSION GUARD (the reason the stub ranks last): run against the real
    installed flexicon, enabling the stub tier must fill return types and
    overwrite none. Issue #134 as filed proposed preferring the stub *over*
    the docstring; measured, that would rewrite 133 concrete LCM interface
    names into type-erased placeholders, because flexicon's stubs type LCM
    objects as `Any` -- a stub must not require SIL.LCModel to import. The
    LCM cross-annotation step and find_wrappers_for_lcm key off exactly
    those names, so stub-first is a data-loss change. This test fails if
    anyone reorders the tiers.
"""

import ast
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flextoolsmcp.flexicon_analyzer import (  # noqa: E402
    _return_type_from_annotation,
    analyze_flexicon,
    analyze_method,
    extract_stub_return_types,
    infer_output_behavior,
    parse_docstring,
)


# ---- extract_stub_return_types ---------------------------------------------

def _write_pair(tmp_path, py_src, pyi_src):
    """Write Mod.py, plus Mod.pyi when pyi_src is not None."""
    py = tmp_path / "Mod.py"
    py.write_text(py_src, encoding="utf-8")
    if pyi_src is not None:
        (tmp_path / "Mod.pyi").write_text(pyi_src, encoding="utf-8")
    return py


STUB_WITH_NESTING = (
    "from typing import Any, Optional\n"
    "\n"
    "def helper(a: int) -> str: ...\n"
    "\n"
    "class Outer:\n"
    "    def Method(self) -> Optional[int]: ...\n"
    "    class Inner:\n"
    "        def Deep(self) -> bool: ...\n"
)


def test_stub_map_covers_classes_nested_classes_and_module_functions(tmp_path):
    py = _write_pair(tmp_path, "x = 1\n", STUB_WITH_NESTING)
    stub = extract_stub_return_types(py)

    # Module-level functions key off None, not "".
    assert stub[(None, "helper")] == "str"
    assert stub[("Outer", "Method")] == "Optional[int]"
    # A nested class's methods key off the innermost class name.
    assert stub[("Inner", "Deep")] == "bool"


def test_unannotated_defs_are_absent_not_empty(tmp_path):
    py = _write_pair(tmp_path, "x = 1\n", (
        "class C:\n"
        "    def NoAnnotation(self): ...\n"
        "    def Annotated(self) -> int: ...\n"
    ))
    stub = extract_stub_return_types(py)
    assert ("C", "NoAnnotation") not in stub
    assert stub[("C", "Annotated")] == "int"


def test_missing_stub_yields_empty_dict(tmp_path):
    py = _write_pair(tmp_path, "def f(): pass\n", None)
    assert extract_stub_return_types(py) == {}


def test_unparsable_stub_yields_empty_dict_without_raising(tmp_path, capsys):
    py = _write_pair(tmp_path, "x = 1\n", "class C:\n  def broken( -> int: ...\n")
    assert extract_stub_return_types(py) == {}
    assert "Ignoring unparsable stub" in capsys.readouterr().out


# ---- _return_type_from_annotation ------------------------------------------

@pytest.mark.parametrize("annotation, expected", [
    ("int", "int"),
    ('"FLExProject"', "FLExProject"),      # forward ref: quotes stripped
    ("None", "None"),
    ("Optional[int]", "Optional[int]"),
    ("EnumerableWrapper[Any]", "EnumerableWrapper[Any]"),
    ("typing.List[str]", "typing.List[str]"),
])
def test_annotation_rendering(annotation, expected):
    fn = ast.parse("def f() -> " + annotation + ": ...").body[0]
    assert _return_type_from_annotation(fn.returns) == expected


def test_no_annotation_renders_empty():
    fn = ast.parse("def f(): ...").body[0]
    assert _return_type_from_annotation(fn.returns) == ""


# ---- precedence: inline annotation > docstring > stub ----------------------

DOCSTRING_METHOD = (
    "def Create(self):\n"
    '    """Make one.\n'
    "\n"
    "    Returns:\n"
    "        ICmAgent: the new agent.\n"
    '    """\n'
)

ANNOTATED_METHOD = (
    'def Create(self) -> "LexEntry":\n'
    '    """Make one.\n'
    "\n"
    "    Returns:\n"
    "        ICmAgent: the new agent.\n"
    '    """\n'
)


def _method_node(src):
    return ast.parse(src).body[0]


def test_stub_fills_when_docstring_is_silent():
    node = _method_node("def Delete(self):\n    'Remove it.'\n")
    info = analyze_method(node, "AgentOperations", [],
                          {("AgentOperations", "Delete"): "None"})
    assert info["return_type"] == "None"


def test_docstring_beats_stub_when_they_disagree():
    """The 133-name guard at unit scale: ICmAgent must survive `Any`."""
    node = _method_node(DOCSTRING_METHOD)
    assert parse_docstring(ast.get_docstring(node))["return_type"] == "ICmAgent"

    info = analyze_method(node, "AgentOperations", [],
                          {("AgentOperations", "Create"): "Any"})
    assert info["return_type"] == "ICmAgent"


def test_inline_annotation_beats_both():
    node = _method_node(ANNOTATED_METHOD)
    info = analyze_method(node, "AgentOperations", [],
                          {("AgentOperations", "Create"): "Any"})
    assert info["return_type"] == "LexEntry"


def test_module_level_function_reads_the_none_keyed_entry():
    node = _method_node("def helper(a):\n    'Do a thing.'\n")
    # analyze_method receives "" as the class name for a top-level function;
    # it must normalize that to the None key the stub map uses.
    info = analyze_method(node, "", [], {(None, "helper"): "str"})
    assert info["return_type"] == "str"


def test_absent_stub_map_leaves_behavior_unchanged():
    node = _method_node("def Delete(self):\n    'Remove it.'\n")
    assert analyze_method(node, "AgentOperations", [], None)["return_type"] == ""


# ---- regression guard against the real installed flexicon ------------------

def _flexicon_repo_root():
    try:
        import flexicon
    except ImportError:
        return None
    # analyze_flexicon() wants the root that contains flexicon/code/.
    root = Path(flexicon.__file__).resolve().parent.parent
    return root if (root / "flexicon" / "code").is_dir() else None


def _census(doc):
    return {
        (eid, m["name"]): m.get("return_type", "")
        for eid, e in doc["entities"].items()
        for kind in ("methods", "properties")
        for m in e.get(kind, [])
    }


def test_stub_tier_is_strictly_additive_on_real_flexicon(monkeypatch):
    """Enabling the stub tier must fill types and overwrite none.

    This encodes why #134 was implemented as a fallback rather than as
    filed. Flip the tiers and the overwrite count jumps to 133, every one
    of them a concrete LCM interface name replaced by `Any` /
    `Optional[Any]` / `List[Any]`.
    """
    root = _flexicon_repo_root()
    if root is None:
        pytest.skip("flexicon source tree not available")

    import flextoolsmcp.flexicon_analyzer as fa

    real = fa.extract_stub_return_types
    monkeypatch.setattr(fa, "extract_stub_return_types", lambda p: {})
    without = _census(analyze_flexicon(str(root)))
    monkeypatch.setattr(fa, "extract_stub_return_types", real)
    with_stub = _census(analyze_flexicon(str(root)))

    overwritten = {k: (without[k], with_stub[k]) for k in with_stub
                   if without.get(k) and with_stub[k] and without[k] != with_stub[k]}
    lost = {k: without[k] for k in with_stub
            if without.get(k) and not with_stub[k]}
    filled = {k: with_stub[k] for k in with_stub
              if not without.get(k) and with_stub[k]}

    assert overwritten == {}, "stub tier overwrote existing types: %r" % (overwritten,)
    assert lost == {}, "stub tier dropped existing types: %r" % (lost,)
    assert len(filled) > 50, "expected many gaps filled, got %d" % len(filled)

    # A concrete LCM interface from a docstring must survive, even though
    # the stub for that same method says `Any`.
    assert with_stub[("AgentOperations", "Create")] == "ICmAgent"


def test_shipped_index_reflects_the_stub_tier():
    """The shipped index must be regenerated after this change, not stale."""
    idx = (Path(__file__).resolve().parents[1] / "src" / "flextoolsmcp" /
           "index" / "python")
    files = sorted(idx.glob("flexicon_api_v*.json"))
    if not files:
        pytest.skip("no shipped flexicon index")

    doc = json.load(files[-1].open(encoding="utf-8"))
    fp = doc["entities"].get("FLExProject", {})
    members = fp.get("methods", []) + fp.get("properties", [])
    hits = [m for m in members if m["name"] in ("GetFieldID", "Object")]
    assert hits, "FLExProject.GetFieldID/Object missing from the index"
    for m in hits:
        assert m.get("return_type"), (
            "FLExProject.%s still has an empty return_type -- "
            "re-run `python -m flextoolsmcp.refresh`" % m["name"]
        )


# ---- void vs Optional in output_behavior -----------------------------------
#
# Resolving 63 more `-> None` methods exposed a latent bug: bare `None` and
# `Optional[X]` shared one branch, so every void setter and deleter was
# advertised as returning "None when not found". A void method returns no
# value at all -- there is nothing for a caller to inspect.

def test_void_return_has_no_empty_result():
    ob = infer_output_behavior("Delete", "None", "", [])
    assert ob["success"]["type"] == "None"
    assert ob["empty"] is None


def test_optional_return_keeps_its_not_found_sentinel():
    ob = infer_output_behavior("GetFieldID", "Optional[int]", "", [])
    assert ob["empty"] == {"value": "None", "description": "None when not found"}


def test_bare_optional_keeps_its_not_found_sentinel():
    assert infer_output_behavior("Find", "Optional", "", [])["empty"] is not None


def test_no_void_method_in_shipped_index_claims_an_empty_value():
    idx = (Path(__file__).resolve().parents[1] / "src" / "flextoolsmcp" /
           "index" / "python")
    files = sorted(idx.glob("flexicon_api_v*.json"))
    if not files:
        pytest.skip("no shipped flexicon index")

    doc = json.load(files[-1].open(encoding="utf-8"))
    offenders = [
        "%s.%s" % (eid, m["name"])
        for eid, e in doc["entities"].items()
        for kind in ("methods", "properties")
        for m in e.get(kind, [])
        if m.get("return_type") == "None"
        and (m.get("output_behavior") or {}).get("empty")
    ]
    assert offenders == [], (
        "void methods advertising an empty result: %r" % (offenders,))
