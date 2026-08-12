#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #84: `project.LexSense` is not a real FLExProject accessor.

Two defects, one root cause. Stripping "Operations" off a KNOWN_OPERATIONS
entry was treated as a valid `project.<X>` accessor name. That holds for most
classes (ExampleOperations -> project.Example) but NOT for
LexSenseOperations / PhonologicalRuleOperations, which have no same-named
accessor. Consequences:

  1. The pre-flight accessor gate blessed `project.LexSense.GetGloss(...)`,
     so the shipped flexicon template, curated recipes and docs all taught an
     idiom that AttributeErrors on the first sense access.
  2. `LexSense` was in the candidate pool for its own AttributeError, so the
     runner suggested the failing name back as the top fix -- a loop.

Covers the accessor allowlist, both suggestion paths, auto-fix, and a smoke
test that no shipped template/recipe teaches a phantom accessor.
"""

import ast
import pathlib

import pytest

from flextoolsmcp.server import APIIndex, get_index_dir
from flextoolsmcp.server.constants import KNOWN_OPERATIONS, PROJECT_ACCESSOR_ALIASES
from flextoolsmcp.server.handlers.execution import _try_auto_fix_typos
from flextoolsmcp.server.validators import (
    _project_accessors,
    detect_invalid_project_chains,
    detect_unknown_attribute_error,
)

TEMPLATE_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "flextoolsmcp" / "templates"


@pytest.fixture(scope="module")
def api_index():
    return APIIndex.load(get_index_dir())


# ---------------------------------------------------------------------------
# The allowlist itself
# ---------------------------------------------------------------------------

class TestProjectAccessorAllowlist:
    def test_phantom_accessors_excluded(self, api_index):
        """LexSense / PhonologicalRule must never count as valid accessors."""
        accessors = set(_project_accessors(api_index))
        for phantom in PROJECT_ACCESSOR_ALIASES:
            assert phantom not in accessors

    def test_phantoms_excluded_without_an_index_too(self):
        """The KNOWN_OPERATIONS-only fallback path must be filtered as well."""
        accessors = set(_project_accessors(None))
        for phantom in PROJECT_ACCESSOR_ALIASES:
            assert phantom not in accessors

    def test_real_accessors_still_allowed(self, api_index):
        """Only the two phantoms are dropped -- the other shorthands survive."""
        accessors = set(_project_accessors(api_index))
        for name in ("LexEntry", "Senses", "Example", "WritingSystem", "POS", "PhonRules"):
            assert name in accessors

    def test_every_alias_target_is_a_real_accessor(self, api_index):
        """A mapping that points at another phantom would just move the bug."""
        accessors = set(_project_accessors(api_index))
        for phantom, correct in PROJECT_ACCESSOR_ALIASES.items():
            assert correct in accessors, f"{phantom} -> {correct} is not a real accessor"

    def test_every_alias_key_is_an_operations_shorthand(self):
        """Guards against typos in the alias table itself."""
        for phantom in PROJECT_ACCESSOR_ALIASES:
            assert f"{phantom}Operations" in KNOWN_OPERATIONS


# ---------------------------------------------------------------------------
# Pre-flight gate: project.<phantom> is now rejected, with the right fix
# ---------------------------------------------------------------------------

class TestPreflightRejectsPhantomAccessor:
    def test_lexsense_rejected_and_redirected_to_senses(self, api_index):
        tree = ast.parse("senses = project.LexSense.GetAllSenses(entry)\n")
        result = detect_invalid_project_chains(tree, api_index)
        assert result["has_invalid"] is True
        issue = next(i for i in result["issues"] if i["expr"] == "project.LexSense")
        assert issue["did_you_mean"] == ["Senses"]
        assert issue["match_ratio"] == 1.0
        assert "project.Senses" in issue["suggestion"]

    def test_phonologicalrule_rejected_and_redirected(self, api_index):
        tree = ast.parse("rules = project.PhonologicalRule.GetAll()\n")
        result = detect_invalid_project_chains(tree, api_index)
        issue = next(i for i in result["issues"] if i["expr"] == "project.PhonologicalRule")
        assert issue["did_you_mean"] == ["PhonRules"]

    def test_inner_method_not_double_flagged(self, api_index):
        """Only the accessor is reported; GetGloss isn't a second issue."""
        tree = ast.parse("g = project.LexSense.GetGloss(sense)\n")
        result = detect_invalid_project_chains(tree, api_index)
        assert [i["expr"] for i in result["issues"]] == ["project.LexSense"]

    def test_corrected_form_passes_clean(self, api_index):
        code = (
            "for entry in project.LexEntry.GetAll():\n"
            "    for sense in project.LexEntry.GetAllSenses(entry):\n"
            "        gloss = project.Senses.GetGloss(sense)\n"
        )
        result = detect_invalid_project_chains(ast.parse(code), api_index)
        assert result["has_invalid"] is False, result.get("suggestion")


# ---------------------------------------------------------------------------
# Runtime AttributeError hint: no longer circular
# ---------------------------------------------------------------------------

class TestDidYouMeanIsNotCircular:
    ERROR = "AttributeError: 'FLExProject' object has no attribute 'LexSense'"

    def test_failing_name_is_not_its_own_suggestion(self, api_index):
        result = detect_unknown_attribute_error(self.ERROR, api_index)
        assert result["has_suggestion"] is True
        assert "LexSense" not in result["did_you_mean"]
        assert "project.LexSense" not in result["suggestion"]

    def test_correct_accessor_leads_the_list(self, api_index):
        result = detect_unknown_attribute_error(self.ERROR, api_index)
        assert result["did_you_mean"][0] == "Senses"

    def test_self_filter_applies_to_non_alias_names_too(self, api_index):
        """A name that IS in the candidate pool still can't suggest itself."""
        error = "AttributeError: 'FLExProject' object has no attribute 'Senses'"
        result = detect_unknown_attribute_error(error, api_index)
        assert "Senses" not in result.get("did_you_mean", [])

    def test_ordinary_typo_still_resolved(self, api_index):
        """Regression guard: the pre-existing LexEntries -> LexEntry path."""
        error = "AttributeError: 'FLExProject' object has no attribute 'LexEntries'"
        result = detect_unknown_attribute_error(error, api_index)
        assert result["has_suggestion"] is True
        assert "LexEntry" in result["did_you_mean"]


# ---------------------------------------------------------------------------
# Auto-fix can apply the rewrite (single candidate, ratio 1.0)
# ---------------------------------------------------------------------------

class TestAutoFixRewritesPhantomAccessor:
    def test_lexsense_rewritten_to_senses(self, api_index):
        code = "senses = project.LexSense.GetAllSenses(entry)\n"
        issues = detect_invalid_project_chains(ast.parse(code), api_index)["issues"]
        fixed = _try_auto_fix_typos(code, issues)
        assert fixed is not None
        assert fixed["patched_code"] == "senses = project.Senses.GetAllSenses(entry)\n"
        assert fixed["fixes"][0]["original"] == "LexSense"
        assert fixed["fixes"][0]["replacement"] == "Senses"


# ---------------------------------------------------------------------------
# Smoke test: shipped artifacts must not teach a phantom accessor (issue #84.3)
# ---------------------------------------------------------------------------

class TestShippedArtifactsUsePhantomFreeAccessors:
    """An authoritative template that raises on its own example code should be
    caught here, not by a user copying it."""

    @pytest.mark.parametrize(
        "template", sorted(p.name for p in TEMPLATE_DIR.glob("*.py"))
    )
    def test_template_code_passes_the_accessor_gate(self, template, api_index):
        path = TEMPLATE_DIR / template
        source = path.read_text(encoding="utf-8")
        result = detect_invalid_project_chains(ast.parse(source), api_index)
        assert result["has_invalid"] is False, f"{template}: {result.get('suggestion')}"

    @pytest.mark.parametrize(
        "path", sorted(TEMPLATE_DIR.glob("*.py")) + sorted(TEMPLATE_DIR.glob("*.md"))
    )
    def test_no_phantom_accessor_in_template_prose(self, path):
        """The COMMON PATTERNS notes are what people copy from, so the plain
        text has to be right too -- the AST gate can't see inside a docstring."""
        text = path.read_text(encoding="utf-8")
        for phantom in PROJECT_ACCESSOR_ALIASES:
            assert f"project.{phantom}" not in text, f"{path.name} teaches project.{phantom}"

    def test_no_phantom_accessor_in_curated_recipes(self):
        from flextoolsmcp.curated_recipes import CURATED_RECIPES

        for name, recipe in CURATED_RECIPES.items():
            for phantom in PROJECT_ACCESSOR_ALIASES:
                assert f"project.{phantom}" not in recipe["code"], (
                    f"recipe {name!r} teaches project.{phantom}"
                )

    def test_no_phantom_accessor_in_worked_examples(self):
        from flextoolsmcp.server.worked_examples import WORKED_EXAMPLES

        for example in WORKED_EXAMPLES:
            for phantom in PROJECT_ACCESSOR_ALIASES:
                assert f"project.{phantom}" not in example.get("code", ""), (
                    f"worked example {example['id']!r} teaches project.{phantom}"
                )


# ---------------------------------------------------------------------------
# Follow-on defects the cycle-1 review caught in the fix itself
# ---------------------------------------------------------------------------

def _shipped_code_sources():
    """(label, code) for every artifact that teaches an idiom to users."""
    from flextoolsmcp.curated_recipes import CURATED_RECIPES
    from flextoolsmcp.server.worked_examples import WORKED_EXAMPLES

    for path in sorted(TEMPLATE_DIR.glob("*.py")) + sorted(TEMPLATE_DIR.glob("*.md")):
        yield f"template {path.name}", path.read_text(encoding="utf-8")
    for name, recipe in CURATED_RECIPES.items():
        yield f"recipe {name}", recipe["code"]
    for example in WORKED_EXAMPLES:
        yield f"worked example {example['id']}", example.get("code", "")


class TestGetAllSensesArgumentType:
    """`GetAllSenses` exists on BOTH operations classes with different params:
    LexEntryOperations.GetAllSenses(entry_or_hvo) -> the entry's senses;
    LexSenseOperations.GetAllSenses(sense_or_hvo) -> that sense + subsenses.

    Both accept anything with an `AllSenses` property, so passing an entry to
    the sense flavour silently "works" via duck typing instead of raising --
    which is exactly how the first pass at fixing issue #84 shipped
    `project.Senses.GetAllSenses(entry)` into the authoritative template. The
    accessor gate only checks names, never argument types, so it cannot catch
    this; pin it here instead.
    """

    @pytest.mark.parametrize("label,code", list(_shipped_code_sources()))
    def test_entry_never_passed_to_the_sense_flavour(self, label, code):
        for bad in ("project.Senses.GetAllSenses(entry)",
                    "project.Senses.GetAllSenses(entries["):
            assert bad not in code, (
                f"{label} passes an entry to project.Senses.GetAllSenses, which "
                f"expects a sense -- use project.LexEntry.GetAllSenses(entry)"
            )


class TestTemplateImportsResolve:
    """A bad name in the template's import block is an ImportError that kills
    the module before Main() runs -- strictly worse than the AttributeError
    issue #84 was filed about. The template shipped a nonexistent
    `ReversalOperations` for exactly this reason.
    """

    @pytest.mark.parametrize(
        "template", sorted(p.name for p in TEMPLATE_DIR.glob("*.py"))
    )
    def test_flexicon_imports_exist(self, template):
        """Resolve each `from flexicon...` import against the real package.

        Only flexicon itself is checked -- `from SIL.LCModel import ...` needs
        FieldWorks + pythonnet, which the flexicon-flavour templates don't
        require and CI doesn't have.
        """
        import importlib

        pytest.importorskip("flexicon", reason="import check needs a live flexicon install")
        tree = ast.parse((TEMPLATE_DIR / template).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if module != "flexicon" and not module.startswith("flexicon."):
                continue
            mod = importlib.import_module(module)
            for alias in node.names:
                assert hasattr(mod, alias.name), (
                    f"{template} imports {alias.name!r} from {module}, which does "
                    f"not export it -- the module dies at import time"
                )


class TestAliasTableMatchesLiveInstall:
    """Mirrors scripts/check_project_accessors.py so drift fails in CI too."""

    def test_declared_aliases_are_exactly_the_live_phantoms(self):
        flexicon = pytest.importorskip(
            "flexicon", reason="drift check needs a live flexicon install"
        )
        live = {n for n in dir(flexicon.FLExProject) if not n.startswith("_")}
        shorthands = {
            op[: -len("Operations")] for op in KNOWN_OPERATIONS if op.endswith("Operations")
        }
        phantoms = {n for n in shorthands if n not in live}
        assert phantoms == set(PROJECT_ACCESSOR_ALIASES), (
            "PROJECT_ACCESSOR_ALIASES has drifted from the installed flexicon; "
            "run scripts/check_project_accessors.py"
        )

    def test_alias_targets_exist_on_the_live_class(self):
        flexicon = pytest.importorskip(
            "flexicon", reason="drift check needs a live flexicon install"
        )
        live = {n for n in dir(flexicon.FLExProject) if not n.startswith("_")}
        for phantom, correct in PROJECT_ACCESSOR_ALIASES.items():
            assert correct in live, f"{phantom} -> {correct} is not real either"
