#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #121 (part 1): element_type + polymorphic on flexicon
method records.

Background: the casting preflight had no way to warn about

    for c in project.LexEntry.GetComplexFormComponents(entry):
        project.LexEntry.GetHeadword(c)

because the flexicon index recorded nothing about what type the elements
of a returned collection actually arrive as. Root cause: no field existed
to carry that information.

This adds two things, verified here:

1. `flexicon_analyzer._resolve_element_source_property` -- AST analysis
   that traces a method's `return` statement(s) back to the single LibLCM
   collection property (name ending RS/OS/OC/RC) whose elements feed the
   return value. Deliberately NOT the crude "any RS/OS/OC/RC attribute
   accessed anywhere in the method" bag (`properties_accessed`) -- that bag
   is ambiguous or simply wrong when a method traverses an unrelated
   intermediate collection before reaching the one that actually feeds the
   return value (the GetComplexFormComponents shape: loops over
   `EntryRefsOS` to find the ref, but returns elements of
   `ComponentLexemesRS`).

2. `build_element_types.annotate_element_types` -- a post-process step
   (needs both the flexicon and liblcm indexes in scope, so it can't live
   in flexicon_analyzer.py alone) that cross-references
   `element_source_property` against the LibLCM index's authoritative
   `target_type` for that property, and flags `polymorphic: true` only
   when the resolved element_type is genuinely abstract (ICmObject, a
   casting-index interface_hierarchy key, or an LCM interface with real
   derived interfaces).

Both keys follow the `access_path` (issue #100) omission convention:
absent, not None/false, when unresolved -- so every consumer degrades via
`.get(...)`.
"""

import ast
import json
import textwrap
import unittest
from pathlib import Path


# ---------------------------------------------------------------------------
# _resolve_element_source_property / analyze_method
# ---------------------------------------------------------------------------

class TestResolveElementSourceProperty(unittest.TestCase):
    def _method_node(self, source: str) -> ast.FunctionDef:
        tree = ast.parse(textwrap.dedent(source))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        return next(n for n in cls.body if isinstance(n, ast.FunctionDef))

    def test_list_wrapped_direct_attribute_resolves(self):
        """return list(x.SomethingRS) -- the simplest shape."""
        from flextoolsmcp.flexicon_analyzer import _resolve_element_source_property

        node = self._method_node('''
            class ConstChartOperations:
                def GetRows(self, chart_or_hvo):
                    """Get all rows in a constituent chart."""
                    chart = self.__ResolveObject(chart_or_hvo)
                    return list(chart.RowsOS)
        ''')
        self.assertEqual(_resolve_element_source_property(node), "RowsOS")

    def test_complex_form_components_shape_picks_right_property(self):
        """Mirrors the real LexEntryOperations.GetComplexFormComponents
        shape: loops over EntryRefsOS to find the ref, but the actual
        return value's elements come from ComponentLexemesRS -- the
        crude 'any RS/OS/OC/RC attribute in the method' bag would report
        both (ambiguous); AST tracing of the return value itself must
        pick ComponentLexemesRS only.
        """
        from flextoolsmcp.flexicon_analyzer import _resolve_element_source_property

        node = self._method_node('''
            class LexEntryOperations:
                def GetComplexFormComponents(self, complex_entry_or_hvo):
                    """Get all components of a complex form."""
                    complex_entry = self.__ResolveObject(complex_entry_or_hvo)
                    for entry_ref in complex_entry.EntryRefsOS:
                        if entry_ref.RefType == LexEntryRefTags.krtComplexForm:
                            return self._GetTypedElements(entry_ref.ComponentLexemesRS)
                    return []
        ''')
        result = _resolve_element_source_property(node)
        self.assertEqual(result, "ComponentLexemesRS")
        self.assertNotEqual(result, "EntryRefsOS")

    def test_comprehension_iterable_resolves(self):
        """return self._GetTypedElements(c for c in row.CellsOS if ...) --
        mirrors ConstChartRowOperations.GetWordGroups."""
        from flextoolsmcp.flexicon_analyzer import _resolve_element_source_property

        node = self._method_node('''
            class ConstChartRowOperations:
                def GetWordGroups(self, row_or_hvo):
                    """Get all word groups in a chart row."""
                    row = self.__ResolveObject(row_or_hvo)
                    return self._GetTypedElements(
                        c for c in row.CellsOS if c.ClassName == "ConstChartWordGroup"
                    )
        ''')
        self.assertEqual(_resolve_element_source_property(node), "CellsOS")

    def test_multiple_return_branches_agree(self):
        """if hasattr(...): return list(x.RowsOS) / return [] -- both
        branches must agree on a single candidate (the empty-list branch
        contributes nothing)."""
        from flextoolsmcp.flexicon_analyzer import _resolve_element_source_property

        node = self._method_node('''
            class DiscourseOperations:
                def GetRows(self, chart_or_hvo):
                    """Get all rows in a chart."""
                    chart_obj = self.__GetChartObject(chart_or_hvo)
                    if hasattr(chart_obj, "RowsOS"):
                        return list(chart_obj.RowsOS)
                    return []
        ''')
        self.assertEqual(_resolve_element_source_property(node), "RowsOS")

    def test_deeply_nested_append_does_not_misattribute_outer_loop(self):
        """Mirrors LexReferenceOperations.GetComponentEntries: appends into
        the returned list only happen inside an unrelated *inner* loop
        (over a local `targets` list), nested inside the outer
        `for ref in complex_type.MembersOC:` loop. The outer loop's
        collection must NOT be misattributed as the element source --
        this must resolve to nothing (unresolvable), not a wrong guess.
        """
        from flextoolsmcp.flexicon_analyzer import _resolve_element_source_property

        node = self._method_node('''
            class LexReferenceOperations:
                def GetComponentEntries(self, complex_entry):
                    """Get all component entries."""
                    complex_form = self.__ResolveEntry(complex_entry)
                    components = []
                    complex_type = self.FindType("Complex Forms")
                    if not complex_type:
                        return components
                    for ref in complex_type.MembersOC:
                        targets = list(ref.TargetsRS)
                        for i, target in enumerate(targets):
                            if target.Hvo == complex_form.Hvo:
                                for j, other_target in enumerate(targets):
                                    if i != j and other_target.ClassName == "LexEntry":
                                        if other_target not in components:
                                            components.append(other_target)
                    return components
        ''')
        self.assertIsNone(_resolve_element_source_property(node))

    def test_unrelated_local_variable_iteration_unresolvable(self):
        """Mirrors LexEntryOperations.GetComplexFormsNotSubentries: the
        for-loop iterates a local variable (the result of an earlier
        method call), not a collection attribute directly -- no
        candidate should be found."""
        from flextoolsmcp.flexicon_analyzer import _resolve_element_source_property

        node = self._method_node('''
            class LexEntryOperations:
                def GetComplexFormsNotSubentries(self, entry_or_hvo):
                    """Get complex forms, excluding subentries."""
                    entry = self.__ResolveObject(entry_or_hvo)
                    all_complex_forms = self.GetVisibleComplexFormBackRefs(entry)
                    result = []
                    for lex_ref in all_complex_forms:
                        if not lex_ref.IsSubentry:
                            result.append(lex_ref)
                    return result
        ''')
        self.assertIsNone(_resolve_element_source_property(node))

    def test_ambiguous_across_return_branches_unresolvable(self):
        """Two return statements pointing at two DIFFERENT collection
        properties -- genuinely ambiguous, must resolve to nothing."""
        from flextoolsmcp.flexicon_analyzer import _resolve_element_source_property

        node = self._method_node('''
            class SomeOperations:
                def GetEither(self, flag, obj):
                    """Ambiguous by construction."""
                    if flag:
                        return list(obj.FooOS)
                    return list(obj.BarOC)
        ''')
        self.assertIsNone(_resolve_element_source_property(node))

    def test_no_collection_at_all_unresolvable(self):
        from flextoolsmcp.flexicon_analyzer import _resolve_element_source_property

        node = self._method_node('''
            class SomeOperations:
                def GetGloss(self, sense):
                    """Not a collection-returning method."""
                    return sense.Gloss.BestAnalysisAlternative.Text
        ''')
        self.assertIsNone(_resolve_element_source_property(node))


class TestAnalyzeMethodElementSourceProperty(unittest.TestCase):
    """analyze_method() must set the key only when resolved (access_path
    omission convention, issue #100)."""

    def _method_node(self, source: str) -> ast.FunctionDef:
        tree = ast.parse(textwrap.dedent(source))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        return next(n for n in cls.body if isinstance(n, ast.FunctionDef))

    def test_resolved_case_sets_key(self):
        from flextoolsmcp.flexicon_analyzer import analyze_method

        node = self._method_node('''
            class ConstChartOperations:
                def GetRows(self, chart_or_hvo):
                    """Get all rows in a constituent chart.

                    Returns:
                        list: List of IConstChartRow objects
                    """
                    chart = self.__ResolveObject(chart_or_hvo)
                    return list(chart.RowsOS)
        ''')
        method_info = analyze_method(node, "ConstChartOperations", [])
        self.assertEqual(method_info.get("element_source_property"), "RowsOS")

    def test_unresolved_case_omits_key(self):
        from flextoolsmcp.flexicon_analyzer import analyze_method

        node = self._method_node('''
            class SomeOperations:
                def GetGloss(self, sense):
                    """Not a collection-returning method."""
                    return sense.Gloss.BestAnalysisAlternative.Text
        ''')
        method_info = analyze_method(node, "SomeOperations", [])
        self.assertNotIn("element_source_property", method_info)


# ---------------------------------------------------------------------------
# element_cast_applied detection (issue #121 remediation, defect 3)
# ---------------------------------------------------------------------------

class TestElementCastAppliedDetection(unittest.TestCase):
    """_element_source_uses_cast_helper() / analyze_method()'s
    `element_cast_applied` field."""

    def _method_node(self, source: str) -> ast.FunctionDef:
        tree = ast.parse(textwrap.dedent(source))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
        return next(n for n in cls.body if isinstance(n, ast.FunctionDef))

    def test_get_typed_elements_wrapped_sets_flag(self):
        """The real GetComplexFormComponents shape: `_GetTypedElements`
        wraps the resolved property directly."""
        from flextoolsmcp.flexicon_analyzer import analyze_method

        node = self._method_node('''
            class LexEntryOperations:
                def GetComplexFormComponents(self, complex_entry_or_hvo):
                    """Get all components of a complex form."""
                    complex_entry = self.__ResolveObject(complex_entry_or_hvo)
                    for entry_ref in complex_entry.EntryRefsOS:
                        if entry_ref.RefType == LexEntryRefTags.krtComplexForm:
                            return self._GetTypedElements(entry_ref.ComponentLexemesRS)
                    return []
        ''')
        method_info = analyze_method(node, "LexEntryOperations", [])
        self.assertEqual(method_info.get("element_source_property"), "ComponentLexemesRS")
        self.assertIs(method_info.get("element_cast_applied"), True)

    def test_cast_all_wrapped_sets_flag(self):
        """Bare module-level `cast_all(...)` (what `_GetTypedElements`
        itself delegates to) must also be detected."""
        from flextoolsmcp.flexicon_analyzer import analyze_method

        node = self._method_node('''
            class SomeOperations:
                def GetItems(self, container):
                    """Get items."""
                    return cast_all(container.ItemsOS)
        ''')
        method_info = analyze_method(node, "SomeOperations", [])
        self.assertEqual(method_info.get("element_source_property"), "ItemsOS")
        self.assertIs(method_info.get("element_cast_applied"), True)

    def test_raw_list_wrap_omits_flag(self):
        """A plain `list(x.PropOS)` with no cast helper must NOT set the
        flag -- the caller receives raw pythonnet elements."""
        from flextoolsmcp.flexicon_analyzer import analyze_method

        node = self._method_node('''
            class ConstChartOperations:
                def GetRows(self, chart_or_hvo):
                    """Get all rows."""
                    chart = self.__ResolveObject(chart_or_hvo)
                    return list(chart.RowsOS)
        ''')
        method_info = analyze_method(node, "ConstChartOperations", [])
        self.assertEqual(method_info.get("element_source_property"), "RowsOS")
        self.assertNotIn("element_cast_applied", method_info)

    def test_partial_cast_across_branches_omits_flag(self):
        """Conservative requirement: ALL return statements that resolved
        the winning property must be cast-wrapped. A method that casts on
        one branch but returns the raw collection on another must NOT be
        marked element_cast_applied."""
        from flextoolsmcp.flexicon_analyzer import analyze_method

        node = self._method_node('''
            class SomeOperations:
                def GetItems(self, container, typed):
                    """Get items, optionally cast."""
                    if typed:
                        return self._GetTypedElements(container.ItemsOS)
                    return list(container.ItemsOS)
        ''')
        method_info = analyze_method(node, "SomeOperations", [])
        # Both branches resolve to the SAME property, so element_source_property
        # still resolves unambiguously -- but casting isn't uniform.
        self.assertEqual(method_info.get("element_source_property"), "ItemsOS")
        self.assertNotIn("element_cast_applied", method_info)

    def test_no_element_source_property_never_sets_flag(self):
        """When the property itself doesn't resolve, element_cast_applied
        must never be checked/set either (nothing to anchor it to)."""
        from flextoolsmcp.flexicon_analyzer import analyze_method

        node = self._method_node('''
            class SomeOperations:
                def GetEither(self, flag, obj):
                    """Ambiguous by construction."""
                    if flag:
                        return self._GetTypedElements(obj.FooOS)
                    return self._GetTypedElements(obj.BarOC)
        ''')
        method_info = analyze_method(node, "SomeOperations", [])
        self.assertNotIn("element_source_property", method_info)
        self.assertNotIn("element_cast_applied", method_info)


# ---------------------------------------------------------------------------
# build_element_types.annotate_element_types (LCM cross-annotation)
# ---------------------------------------------------------------------------

class TestAnnotateElementTypes(unittest.TestCase):
    """NOTE on fixture shape: liblcm entities MUST carry a `"type"` key
    (`"interface"` or `"class"`) matching the real index, because
    `build_interface_children()` filters on it (issue #121 defect 1 fix --
    see its docstring). Fixtures that omitted `"type"` entirely would
    silently make every entity look like a non-interface and never
    exercise the fix either way -- a mistake the original version of this
    test file made."""

    def test_unambiguous_property_resolves_and_flags_polymorphic(self):
        """ComponentLexemesRS -> ICmObject on both interface + class
        records (fully agreeing) -- always polymorphic (root abstract
        type), regardless of sibling-interface count."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "LexEntryOperations": {
                    "lcm_dependencies": ["ILexEntryRef"],
                    "methods": [
                        {
                            "name": "GetComplexFormComponents",
                            "element_source_property": "ComponentLexemesRS",
                        }
                    ],
                }
            }
        }
        liblcm_data = {
            "entities": {
                "ILexEntryRef": {
                    "type": "interface",
                    "interfaces": ["ICmObject"],
                    "properties": [
                        {"name": "ComponentLexemesRS", "target_type": "ICmObject", "kind": "RS"}
                    ],
                },
                "LexEntryRef": {
                    "type": "class",
                    "interfaces": ["ILexEntryRef"],
                    "properties": [
                        {"name": "ComponentLexemesRS", "target_type": "ICmObject", "kind": "RS"}
                    ],
                },
                "ILexEntry": {"type": "interface", "interfaces": ["ICmObject"], "properties": []},
                "ILexSense": {"type": "interface", "interfaces": ["ICmObject"], "properties": []},
            }
        }

        stats = annotate_element_types(flexicon_data, liblcm_data)

        method = flexicon_data["entities"]["LexEntryOperations"]["methods"][0]
        self.assertEqual(method["element_type"], "ICmObject")
        self.assertIs(method["polymorphic"], True)
        self.assertEqual(stats, {
            "source_property_candidates": 1,
            "resolved_via_explicit_hint": 0,
            "resolved_via_source_property": 1,
            "return_type_candidates": 0,
            "resolved_via_return_type": 0,
            "resolved": 1,
            "polymorphic": 1,
        })

    def test_single_implementor_interface_not_polymorphic(self):
        """Issue #121 defect 1 (severe): an interface with exactly ONE
        concrete implementing class and no derived sibling interfaces --
        the `ILexSense`/`SensesOS` shape -- must NOT be flagged
        polymorphic. Before the fix, `build_interface_children()` counted
        `LexSense` (a concrete class, `interfaces: ["ILexSense"]`) as a
        'child' of `ILexSense`, so this returned `polymorphic: true` for
        every single-implementor interface in the corpus -- the bug that
        produced 102/102 false-positive `polymorphic: true` records."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "LexEntryOperations": {
                    "lcm_dependencies": [],
                    "methods": [
                        {"name": "GetSenses", "element_source_property": "SensesOS"}
                    ],
                }
            }
        }
        liblcm_data = {
            "entities": {
                "ILexEntry": {
                    "type": "interface",
                    "interfaces": ["ICmObject"],
                    "properties": [
                        {"name": "SensesOS", "target_type": "ILexSense", "kind": "OS"}
                    ],
                },
                "LexEntry": {
                    "type": "class",
                    "interfaces": ["ILexEntry"],
                    "properties": [
                        {"name": "SensesOS", "target_type": "ILexSense", "kind": "OS"}
                    ],
                },
                "ILexSense": {"type": "interface", "interfaces": ["ICmObject"], "properties": []},
                "LexSense": {"type": "class", "interfaces": ["ILexSense"], "properties": []},
            }
        }

        annotate_element_types(flexicon_data, liblcm_data)

        method = flexicon_data["entities"]["LexEntryOperations"]["methods"][0]
        self.assertEqual(method["element_type"], "ILexSense")
        self.assertNotIn("polymorphic", method)

    def test_root_interface_always_polymorphic(self):
        """ICmObject must stay polymorphic regardless of the
        interface_children computation -- it's the hardcoded
        ABSTRACT_ROOT_INTERFACE case, independent of defect 1's fix."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "SomeOperations": {
                    "lcm_dependencies": [],
                    "methods": [
                        {"name": "GetMixed", "element_source_property": "MixedRS"}
                    ],
                }
            }
        }
        liblcm_data = {
            "entities": {
                "IContainer": {
                    "type": "interface",
                    "interfaces": [],
                    "properties": [
                        {"name": "MixedRS", "target_type": "ICmObject", "kind": "RS"}
                    ],
                },
            }
        }

        annotate_element_types(flexicon_data, liblcm_data)

        method = flexicon_data["entities"]["SomeOperations"]["methods"][0]
        self.assertEqual(method["element_type"], "ICmObject")
        self.assertIs(method["polymorphic"], True)

    def test_genuine_sibling_interfaces_flag_polymorphic(self):
        """An interface with multiple derived SIBLING INTERFACES (not just
        one concrete implementor) must be flagged polymorphic -- the
        IMoForm/IConstituentChartCellPart shape."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "SomeOperations": {
                    "lcm_dependencies": [],
                    "methods": [
                        {"name": "GetForms", "element_source_property": "FormsOS"}
                    ],
                }
            }
        }
        liblcm_data = {
            "entities": {
                "IContainer": {
                    "type": "interface",
                    "interfaces": [],
                    "properties": [
                        {"name": "FormsOS", "target_type": "IMoForm", "kind": "OS"}
                    ],
                },
                "IMoForm": {"type": "interface", "interfaces": [], "properties": []},
                "IMoStemAllomorph": {"type": "interface", "interfaces": ["IMoForm"], "properties": []},
                "IMoAffixAllomorph": {"type": "interface", "interfaces": ["IMoForm"], "properties": []},
                "MoStemAllomorph": {"type": "class", "interfaces": ["IMoStemAllomorph", "IMoForm"], "properties": []},
            }
        }

        annotate_element_types(flexicon_data, liblcm_data)

        method = flexicon_data["entities"]["SomeOperations"]["methods"][0]
        self.assertEqual(method["element_type"], "IMoForm")
        self.assertIs(method["polymorphic"], True)

    def test_concrete_leaf_type_resolves_without_polymorphic_flag(self):
        """A property whose target_type has no derived interfaces (a
        concrete leaf) must get element_type but NOT the polymorphic key
        at all -- polymorphic is only ever emitted when true."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "SomeOperations": {
                    "lcm_dependencies": [],
                    "methods": [
                        {"name": "GetLeaves", "element_source_property": "LeavesOS"}
                    ],
                }
            }
        }
        liblcm_data = {
            "entities": {
                "IContainer": {
                    "type": "interface",
                    "interfaces": [],
                    "properties": [
                        {"name": "LeavesOS", "target_type": "ILeafType", "kind": "OS"}
                    ],
                },
                "ILeafType": {"type": "interface", "interfaces": [], "properties": []},
            }
        }

        stats = annotate_element_types(flexicon_data, liblcm_data)

        method = flexicon_data["entities"]["SomeOperations"]["methods"][0]
        self.assertEqual(method["element_type"], "ILeafType")
        self.assertNotIn("polymorphic", method)
        self.assertEqual(stats, {
            "source_property_candidates": 1,
            "resolved_via_explicit_hint": 0,
            "resolved_via_source_property": 1,
            "return_type_candidates": 0,
            "resolved_via_return_type": 0,
            "resolved": 1,
            "polymorphic": 0,
        })

    def test_ambiguous_property_name_disambiguated_by_lcm_dependencies(self):
        """RowsOS is declared on two unrelated interfaces with different
        target_types; the flexicon class's own lcm_dependencies (imported
        LCM interfaces) should pick the right one."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "ConstChartOperations": {
                    "lcm_dependencies": ["IConstChartRow", "IDsConstChart"],
                    "methods": [
                        {"name": "GetRows", "element_source_property": "RowsOS"}
                    ],
                }
            }
        }
        liblcm_data = {
            "entities": {
                "IDsConstChart": {
                    "type": "interface",
                    "interfaces": [],
                    "properties": [
                        {"name": "RowsOS", "target_type": "IConstChartRow", "kind": "OS"}
                    ],
                },
                "ICmFilter": {
                    "type": "interface",
                    "interfaces": [],
                    "properties": [
                        {"name": "RowsOS", "target_type": "ICmRow", "kind": "OS"}
                    ],
                },
                "IConstChartRow": {"type": "interface", "interfaces": [], "properties": []},
                "ICmRow": {"type": "interface", "interfaces": [], "properties": []},
            }
        }

        annotate_element_types(flexicon_data, liblcm_data)

        method = flexicon_data["entities"]["ConstChartOperations"]["methods"][0]
        self.assertEqual(method["element_type"], "IConstChartRow")

    def test_ambiguous_property_name_without_disambiguation_omits_keys(self):
        """Same ambiguous RowsOS property, but the class's lcm_dependencies
        don't narrow it to exactly one candidate -- must omit both keys
        rather than guess."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "SomeOperations": {
                    "lcm_dependencies": [],
                    "methods": [
                        {"name": "GetRows", "element_source_property": "RowsOS"}
                    ],
                }
            }
        }
        liblcm_data = {
            "entities": {
                "IDsConstChart": {
                    "type": "interface",
                    "interfaces": [],
                    "properties": [
                        {"name": "RowsOS", "target_type": "IConstChartRow", "kind": "OS"}
                    ],
                },
                "ICmFilter": {
                    "type": "interface",
                    "interfaces": [],
                    "properties": [
                        {"name": "RowsOS", "target_type": "ICmRow", "kind": "OS"}
                    ],
                },
            }
        }

        stats = annotate_element_types(flexicon_data, liblcm_data)

        method = flexicon_data["entities"]["SomeOperations"]["methods"][0]
        self.assertNotIn("element_type", method)
        self.assertNotIn("polymorphic", method)
        self.assertEqual(stats, {
            "source_property_candidates": 1,
            "resolved_via_explicit_hint": 0,
            "resolved_via_source_property": 0,
            "return_type_candidates": 0,
            "resolved_via_return_type": 0,
            "resolved": 0,
            "polymorphic": 0,
        })

    def test_no_element_source_property_skipped_entirely(self):
        """Methods without element_source_property or a parameterized
        return_type must not be touched."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "SomeOperations": {
                    "lcm_dependencies": [],
                    "methods": [{"name": "GetGloss", "return_type": "str"}],
                }
            }
        }
        liblcm_data = {"entities": {}}

        stats = annotate_element_types(flexicon_data, liblcm_data)

        method = flexicon_data["entities"]["SomeOperations"]["methods"][0]
        self.assertNotIn("element_type", method)
        self.assertNotIn("polymorphic", method)
        self.assertEqual(stats, {
            "source_property_candidates": 0,
            "resolved_via_explicit_hint": 0,
            "resolved_via_source_property": 0,
            "return_type_candidates": 0,
            "resolved_via_return_type": 0,
            "resolved": 0,
            "polymorphic": 0,
        })

    def test_casting_index_hierarchy_key_also_flags_polymorphic(self):
        """The casting_index interface_hierarchy is an explicit secondary
        signal per the issue #121 spec: an element_type that appears as a
        key there must be flagged polymorphic even if the (fabricated,
        minimal) liblcm fixture doesn't itself show derived interfaces."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "SomeOperations": {
                    "lcm_dependencies": [],
                    "methods": [
                        {"name": "GetForms", "element_source_property": "FormsOS"}
                    ],
                }
            }
        }
        liblcm_data = {
            "entities": {
                "IContainer": {
                    "type": "interface",
                    "interfaces": [],
                    "properties": [
                        {"name": "FormsOS", "target_type": "IMoForm", "kind": "OS"}
                    ],
                },
                "IMoForm": {"type": "interface", "interfaces": [], "properties": []},
            }
        }
        casting_index = {"interface_hierarchy": {"IMoForm": {"derived_interfaces": ["IMoStemAllomorph"]}}}

        annotate_element_types(flexicon_data, liblcm_data, casting_index)

        method = flexicon_data["entities"]["SomeOperations"]["methods"][0]
        self.assertEqual(method["element_type"], "IMoForm")
        self.assertIs(method["polymorphic"], True)

    def test_return_type_enumerable_wrapper_resolves_getall_shape(self):
        """Issue #121 defect 2: GetAll-shaped methods have no
        element_source_property (they call a repository, not a `.PropOS`
        collection) but DO carry `EnumerableWrapper[IX]` -- the type
        parameter IS the element type, no LCM bridge lookup needed."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "LexEntryOperations": {
                    "lcm_dependencies": [],
                    "methods": [
                        {"name": "GetAll", "return_type": "EnumerableWrapper[ILexEntry]"}
                    ],
                }
            }
        }
        liblcm_data = {"entities": {"ILexEntry": {"type": "interface", "interfaces": [], "properties": []}}}

        stats = annotate_element_types(flexicon_data, liblcm_data)

        method = flexicon_data["entities"]["LexEntryOperations"]["methods"][0]
        self.assertEqual(method["element_type"], "ILexEntry")
        self.assertNotIn("polymorphic", method)
        self.assertEqual(stats["return_type_candidates"], 1)
        self.assertEqual(stats["resolved_via_return_type"], 1)
        self.assertEqual(stats["source_property_candidates"], 0)

    def test_return_type_list_param_resolves(self):
        """The other parameterized shape actually in the index:
        `list[IX]` (also mostly GetAll methods, on classes that return a
        plain list rather than an EnumerableWrapper)."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "AgentOperations": {
                    "lcm_dependencies": [],
                    "methods": [
                        {"name": "GetAll", "return_type": "list[ICmAgent]"}
                    ],
                }
            }
        }
        liblcm_data = {"entities": {"ICmAgent": {"type": "interface", "interfaces": [], "properties": []}}}

        annotate_element_types(flexicon_data, liblcm_data)

        method = flexicon_data["entities"]["AgentOperations"]["methods"][0]
        self.assertEqual(method["element_type"], "ICmAgent")

    def test_return_type_fallback_only_when_source_property_unresolved(self):
        """Issue #121 defect 2 spec: 'still prefer the LCM target_type
        derivation where a source property resolves, and fall back to the
        type parameter.' When BOTH are present and the source-property
        path resolves, it wins -- even if the return_type parameter names
        a DIFFERENT (here deliberately wrong/fabricated) type, proving the
        precedence rather than merely being consistent with it."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "SomeOperations": {
                    "lcm_dependencies": [],
                    "methods": [
                        {
                            "name": "GetThings",
                            "element_source_property": "ThingsOS",
                            "return_type": "list[IWrongType]",
                        }
                    ],
                }
            }
        }
        liblcm_data = {
            "entities": {
                "IContainer": {
                    "type": "interface",
                    "interfaces": [],
                    "properties": [
                        {"name": "ThingsOS", "target_type": "IRightType", "kind": "OS"}
                    ],
                },
                "IRightType": {"type": "interface", "interfaces": [], "properties": []},
            }
        }

        stats = annotate_element_types(flexicon_data, liblcm_data)

        method = flexicon_data["entities"]["SomeOperations"]["methods"][0]
        self.assertEqual(method["element_type"], "IRightType")
        self.assertEqual(stats["resolved_via_source_property"], 1)
        self.assertEqual(stats["resolved_via_return_type"], 0)

    def test_non_interface_bracketed_return_types_ignored(self):
        """Fluent Python-level query-builder wrapper shapes
        (`AffixTemplateCollection[...]`) and non-interface parameterization
        (`tuple[...]`) must NOT be treated as element types -- see
        `_PARAMETERIZED_COLLECTION_PATTERN`'s docstring for the full
        survey and rationale."""
        from flextoolsmcp.build_element_types import annotate_element_types

        flexicon_data = {
            "entities": {
                "AffixTemplateCollection": {
                    "lcm_dependencies": [],
                    "methods": [
                        {"name": "filter", "return_type": "AffixTemplateCollection[IMoInflAffixTemplate]"},
                    ],
                },
                "CatalogBackedMixin": {
                    "lcm_dependencies": [],
                    "methods": [
                        {"name": "FixGuidsAgainstCatalog", "return_type": "tuple[int, int]"},
                    ],
                },
            }
        }
        liblcm_data = {"entities": {}}

        stats = annotate_element_types(flexicon_data, liblcm_data)

        m1 = flexicon_data["entities"]["AffixTemplateCollection"]["methods"][0]
        m2 = flexicon_data["entities"]["CatalogBackedMixin"]["methods"][0]
        self.assertNotIn("element_type", m1)
        self.assertNotIn("element_type", m2)
        self.assertEqual(stats["resolved"], 0)


# ---------------------------------------------------------------------------
# Real shipped index: locks in the annotation post-refresh
# ---------------------------------------------------------------------------

class TestRealIndexHasComplexFormComponentsAnnotation(unittest.TestCase):
    """The shipped flexicon index (post issue #121 refresh + remediation)
    must carry correct element_type/polymorphic across the four
    representative shapes the remediation round called out."""

    @classmethod
    def setUpClass(cls):
        python_dir = (
            Path(__file__).parent.parent
            / "src" / "flextoolsmcp" / "index" / "python"
        )
        cls.data = None
        if not python_dir.exists():
            return
        candidates = sorted(python_dir.glob("flexicon_api_v*.json"))
        if not candidates:
            return
        with open(candidates[-1], encoding="utf-8") as f:
            cls.data = json.load(f)

    def _method(self, class_name, method_name):
        if self.data is None:
            return None
        entity = self.data.get("entities", {}).get(class_name, {})
        for method in entity.get("methods", []):
            if method.get("name") == method_name:
                return method
        return None

    def test_get_complex_form_components_stays_polymorphic(self):
        """Genuinely mixed ILexEntry/ILexSense elements (LCM data model,
        not just declared type) -- must stay polymorphic even though the
        method already casts via `_GetTypedElements` (defect 3)."""
        method = self._method("LexEntryOperations", "GetComplexFormComponents")
        if method is None:
            self.skipTest("shipped flexicon index / GetComplexFormComponents not found")
        self.assertEqual(method.get("element_type"), "ICmObject")
        self.assertIs(method.get("polymorphic"), True)
        self.assertIs(method.get("element_cast_applied"), True)

    def test_get_senses_not_polymorphic(self):
        """Issue #121 defect 1 regression pin: SensesOS is declared
        directly over ILexSense, which has exactly one concrete
        implementor (LexSense) and no derived sibling interfaces --
        must NOT be polymorphic."""
        method = self._method("LexEntryOperations", "GetSenses")
        if method is None:
            self.skipTest("shipped flexicon index / GetSenses not found")
        self.assertEqual(method.get("element_type"), "ILexSense")
        self.assertNotIn("polymorphic", method)

    def test_get_all_senses_not_polymorphic(self):
        method = self._method("LexEntryOperations", "GetAllSenses")
        if method is None:
            self.skipTest("shipped flexicon index / GetAllSenses not found")
        self.assertEqual(method.get("element_type"), "ILexSense")
        self.assertNotIn("polymorphic", method)

    def test_get_all_resolves_via_return_type_not_polymorphic(self):
        """Issue #121 defect 2 regression pin: LexEntryOperations.GetAll
        has NO element_source_property (it's repository-backed, not a
        `.PropOS` access) but DOES carry `EnumerableWrapper[ILexEntry]`,
        which must resolve `element_type` via the return_type fallback
        path. ILexEntry has no derived sibling interfaces -> not
        polymorphic. This is the validator's negative control: a
        confirmed concrete, non-polymorphic element_type should suppress
        a false-positive casting warning for the single highest-traffic
        method in the whole API."""
        method = self._method("LexEntryOperations", "GetAll")
        if method is None:
            self.skipTest("shipped flexicon index / GetAll not found")
        self.assertEqual(method.get("return_type"), "EnumerableWrapper[ILexEntry]")
        self.assertEqual(method.get("element_type"), "ILexEntry")
        self.assertNotIn("polymorphic", method)

    def test_get_subitems_known_limitation_stays_polymorphic(self):
        """AnthropologyOperations.GetSubitems: `element_type` resolves to
        `ICmPossibility`, which genuinely has 13 sibling interfaces in the
        real LibLCM hierarchy (IChkTerm, ICmAnthroItem, ICmAnnotationDefn,
        ICmCustomItem, ICmLocation, ICmPerson, ICmSemanticDomain,
        ILexEntryInflType, ILexEntryType, ILexRefType, IMoMorphType,
        IPartOfSpeech, IPhPhonRuleFeat), so `polymorphic: true` is a
        CORRECT read of the property's declared type space even after the
        defect 1 fix. In practice, FieldWorks' CmPossibilityList design
        guarantees every item in a given list (e.g. the Anthropology
        Categories list) is homogeneously typed to one concrete class
        (ICmAnthroItem here), making this a known, documented residual
        over-annotation -- see build_element_types.py's module docstring
        ("Scope of the target_type-over-prose rationale... defect 3") for
        why this was NOT auto-corrected: distinguishing "genuinely mixed"
        (GetComplexFormComponents) from "declared-polymorphic but
        domain-homogeneous" (GetSubitems) requires FieldWorks domain
        knowledge not recoverable from the flexicon source or LibLCM
        reflection index. This test pins the CURRENT (known-imperfect)
        behavior so a future fix is a deliberate, visible diff here, not
        a silent behavior change."""
        method = self._method("AnthropologyOperations", "GetSubitems")
        if method is None:
            self.skipTest("shipped flexicon index / GetSubitems not found")
        self.assertEqual(method.get("element_type"), "ICmPossibility")
        self.assertIs(method.get("polymorphic"), True)
        self.assertIs(method.get("element_cast_applied"), True)


if __name__ == "__main__":
    unittest.main()
