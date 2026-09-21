#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regression + defensive-behaviour tests for the `is_empty_multistring` helper
that execution.py injects into every generated FLExTools module and every
bare snippet run via `run_module`.

Background (P0, pattern audit): the helper was documented (style guide,
tool_definitions.py, admin.py) as True for None, "", or "***", but its
implementation coerced anything that wasn't already a `str` via `str(text)`
before comparing. A raw LCM multistring/tsstring object (exactly what
`sense.Gloss` or `form.Form` yields via direct C# field access -- the style
guide's OWN "LibLCM (raw C#)" example) produces a CLR ToString()/repr that
never equals "" or "***", so an actually-empty field silently reported as
non-empty. This is the same defect *class* just fixed in the grammar
scanner: typed-attribute access on a raw LCM object without resolving to
text first.

The fix makes the helper resolve non-str input via, in order:
    .Text                                  (ITsString)
    .BestAnalysisAlternative.Text          (IMultiUnicode / IMultiString)
    .BestVernacularAlternative.Text        (IMultiUnicode / IMultiString)
falling back to the historical str(text) behaviour if every attempt fails,
and NEVER propagating an exception (this helper runs inside user scripts and
must not be the thing that crashes them).

This test extracts the *actual* function definition straight out of
execution.py's `runner_script` template string (rather than hand-copying the
logic) so a future edit to the shipped helper cannot silently drift out of
sync with what this test verifies.
"""

import ast
import textwrap
import unittest
from pathlib import Path

EXECUTION_PY = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "flextoolsmcp"
    / "server"
    / "handlers"
    / "execution.py"
)


def _load_is_empty_multistring():
    """Extract and exec the real `is_empty_multistring` def from execution.py.

    `runner_script` in execution.py is a plain string literal (the source
    for a subprocess script) -- NOT live code in execution.py itself. We
    parse execution.py's own AST to pull out that string's literal value
    (so we get exactly what ships, un-escaped by any manual copy/paste),
    then parse THAT as its own module to find the `is_empty_multistring`
    FunctionDef, extract its source segment, and exec it in an isolated
    namespace seeded with FLEX_EMPTY_PLACEHOLDER (a free variable the
    function closes over via the enclosing run_module() scope in the real
    runner).
    """
    source = EXECUTION_PY.read_text(encoding="utf-8")
    module_tree = ast.parse(source, filename=str(EXECUTION_PY))

    runner_script_value = None
    for node in ast.walk(module_tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "runner_script"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            runner_script_value = node.value.value
            break

    if runner_script_value is None:
        raise AssertionError(
            "Could not locate `runner_script = '''...'''` in execution.py "
            "-- has the runner-script template been restructured?"
        )

    runner_tree = ast.parse(runner_script_value, filename="<runner_script>")
    func_node = None
    for node in ast.walk(runner_tree):
        if isinstance(node, ast.FunctionDef) and node.name == "is_empty_multistring":
            func_node = node
            break

    if func_node is None:
        raise AssertionError(
            "Could not locate `def is_empty_multistring` inside runner_script "
            "-- has the helper been renamed or moved?"
        )

    func_source = ast.get_source_segment(runner_script_value, func_node)
    if func_source is None:
        raise AssertionError("ast.get_source_segment returned None for is_empty_multistring")
    func_source = textwrap.dedent(func_source)

    namespace = {"FLEX_EMPTY_PLACEHOLDER": "***"}
    exec(compile(func_source, "<is_empty_multistring>", "exec"), namespace)
    return namespace["is_empty_multistring"]


class TestIsEmptyMultistringRegression(unittest.TestCase):
    """The pre-existing str/None/'***'/whitespace behaviour must be
    byte-identical to before -- this half matters as much as the new
    defensive behaviour (no over-tightening)."""

    def setUp(self):
        self.is_empty_multistring = _load_is_empty_multistring()

    def test_none_is_empty(self):
        self.assertTrue(self.is_empty_multistring(None))

    def test_placeholder_is_empty(self):
        self.assertTrue(self.is_empty_multistring("***"))

    def test_empty_string_is_empty(self):
        self.assertTrue(self.is_empty_multistring(""))

    def test_whitespace_only_string_is_empty(self):
        self.assertTrue(self.is_empty_multistring("   "))

    def test_whitespace_padded_placeholder_is_empty(self):
        self.assertTrue(self.is_empty_multistring("  ***  "))

    def test_non_empty_string_is_not_empty(self):
        self.assertFalse(self.is_empty_multistring("hello"))

    def test_whitespace_padded_non_empty_string_is_not_empty(self):
        self.assertFalse(self.is_empty_multistring("  hello  "))


class TestIsEmptyMultistringDefensiveUnwrap(unittest.TestCase):
    """New behaviour: non-str, raw-LCM-shaped objects are resolved to text
    before the emptiness check, instead of being coerced via str()."""

    def setUp(self):
        self.is_empty_multistring = _load_is_empty_multistring()

    def test_object_with_text_attribute_empty_resolves_true(self):
        """A fake ITsString: not a str, not equal to '' or '***', but its
        `.Text` is empty -- must now return True (this was the bug: the old
        implementation returned False here)."""

        class FakeTsString:
            Text = ""

        obj = FakeTsString()
        self.assertNotIsInstance(obj, str)
        self.assertNotEqual(obj, "")
        self.assertNotEqual(obj, "***")
        self.assertTrue(self.is_empty_multistring(obj))

    def test_object_with_text_attribute_non_empty_resolves_false(self):
        class FakeTsString:
            Text = "some gloss"

        self.assertFalse(self.is_empty_multistring(FakeTsString()))

    def test_object_with_best_analysis_alternative_text_empty(self):
        """A fake IMultiUnicode/IMultiString with no `.Text` of its own, but
        an empty `.BestAnalysisAlternative.Text` -- must resolve True."""

        class Alt:
            Text = ""

        class FakeMultiString:
            BestAnalysisAlternative = Alt()

        obj = FakeMultiString()
        self.assertFalse(hasattr(obj, "Text"))
        self.assertTrue(self.is_empty_multistring(obj))

    def test_object_with_best_analysis_alternative_text_non_empty(self):
        class Alt:
            Text = "andiamo"

        class FakeMultiString:
            BestAnalysisAlternative = Alt()

        self.assertFalse(self.is_empty_multistring(FakeMultiString()))

    def test_object_falls_through_to_best_vernacular_alternative(self):
        """`.Text` and `.BestAnalysisAlternative` both raise; only
        `.BestVernacularAlternative.Text` resolves -- must still work, and
        must be tried in the documented order (Text, then Analysis, then
        Vernacular)."""

        class Alt:
            Text = ""

        class FakeMultiString:
            @property
            def Text(self):
                raise AttributeError("no direct Text on this shape")

            @property
            def BestAnalysisAlternative(self):
                raise AttributeError("no analysis alternative available")

            BestVernacularAlternative = Alt()

        self.assertTrue(self.is_empty_multistring(FakeMultiString()))

    def test_unwrapping_that_raises_never_propagates_and_falls_back_to_str(self):
        """Every unwrap attempt raises -- the helper must not propagate the
        exception, and must fall back to the historical str(text) check."""

        class Explode:
            @property
            def Text(self):
                raise RuntimeError("boom: no Text")

            @property
            def BestAnalysisAlternative(self):
                raise RuntimeError("boom: no analysis alt")

            @property
            def BestVernacularAlternative(self):
                raise RuntimeError("boom: no vernacular alt")

            def __str__(self):
                return "***"

        try:
            result = self.is_empty_multistring(Explode())
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"is_empty_multistring propagated an exception: {exc!r}")

        self.assertIsInstance(result, bool)
        self.assertTrue(result)  # str(Explode()) == "***" -> fallback path

    def test_unwrapping_that_raises_and_str_is_non_empty_returns_false(self):
        class Explode:
            @property
            def Text(self):
                raise RuntimeError("boom")

            def __str__(self):
                return "<Explode object at 0x...>"

        try:
            result = self.is_empty_multistring(Explode())
        except Exception as exc:  # pragma: no cover - failure path
            self.fail(f"is_empty_multistring propagated an exception: {exc!r}")

        self.assertIsInstance(result, bool)
        self.assertFalse(result)

    def test_text_attribute_that_is_not_a_string_is_ignored_in_favor_of_fallback(self):
        """If `.Text` exists but isn't a str (e.g. None, or some other CLR
        artifact), the resolver must not use it as-is; it should move on
        (to the next alternative, or to the str() fallback) rather than
        crash on a non-str `.strip()` call."""

        class FakeTsString:
            Text = None

            def __str__(self):
                return "***"

        self.assertTrue(self.is_empty_multistring(FakeTsString()))


if __name__ == "__main__":
    unittest.main()
