#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Phase 2 Foundational: recipe file format + loader (FR-001..005).

Covers header parsing (JSON and string values, continuation lines),
code excluding the docstring, PARAMS parsing (trailing / above-line /
inside-value comments, multi-line defaults, missing block -> []),
malformed-file skip with one error naming the file and key, merge into
CURATED_RECIPES, id collision raises (file vs file, file vs dict), and
library-is-package-data via importlib.resources.
"""

import importlib.resources
from pathlib import Path

import pytest

from flextoolsmcp import recipe_files
from flextoolsmcp.recipe_files import (
    extract_code_terms,
    load_recipe_library,
    parse_params,
    parse_recipe_source,
)


def _write_recipe(tmp_path: Path, stem: str, text: str) -> Path:
    p = tmp_path / f"{stem}.py"
    p.write_text(text, encoding="utf-8")
    return p


HEADER_BASIC = '''\
"""
id: my-recipe
intent: Do something useful
match_terms: ["do something", "useful task"]
entities: ["LexEntry"]
operations: ["read"]
requires_write: false
origin: test
notes: A short note.
"""
# --- PARAMS ---
COUNT = 10  # how many to list
# --- END PARAMS ---
report.Info("hi")
'''


class TestHeaderParse:
    def test_json_and_string_values(self):
        recipe = parse_recipe_source(HEADER_BASIC, filename="my-recipe.py")
        assert recipe["id"] == "my-recipe"
        assert recipe["intent"] == "Do something useful"
        assert recipe["match_terms"] == ["do something", "useful task"]
        assert recipe["entities"] == ["LexEntry"]
        assert recipe["requires_write"] is False
        # plain string values stay strings
        assert recipe["origin"] == "test"
        assert recipe["notes"] == "A short note."

    def test_continuation_lines_joined(self):
        text = '''\
"""
id: cont-recipe
intent: Something
match_terms: ["x"]
entities: ["LexEntry"]
operations: ["read"]
requires_write: false
origin: test
notes: First line
    second line
    third line
"""
report.Info("hi")
'''
        recipe = parse_recipe_source(text, filename="cont-recipe.py")
        assert recipe["notes"] == "First line second line third line"

    def test_code_excludes_docstring(self):
        recipe = parse_recipe_source(HEADER_BASIC, filename="my-recipe.py")
        assert "Do something useful" not in recipe["code"]
        assert "match_terms" not in recipe["code"]
        assert 'report.Info("hi")' in recipe["code"]
        assert "# --- PARAMS ---" in recipe["code"]


class TestParamsParse:
    def test_trailing_comment(self):
        code = "# --- PARAMS ---\nCOUNT = 10  # how many to list\n# --- END PARAMS ---\n"
        params = parse_params(code)
        assert params == [
            {"name": "COUNT", "default": "10", "description": "how many to list"}
        ]

    def test_above_line_comment(self):
        code = (
            "# --- PARAMS ---\n"
            "# how many to list, most frequent first\n"
            "COUNT = 10\n"
            "# --- END PARAMS ---\n"
        )
        params = parse_params(code)
        assert len(params) == 1
        assert params[0]["name"] == "COUNT"
        assert params[0]["default"] == "10"
        assert params[0]["description"] == "how many to list, most frequent first"

    def test_inside_value_comments(self):
        code = (
            "# --- PARAMS ---\n"
            "TARGETS = [\n"
            '    "a",  # first item\n'
            '    "b",  # second item\n'
            "]\n"
            "# --- END PARAMS ---\n"
        )
        params = parse_params(code)
        assert len(params) == 1
        assert params[0]["name"] == "TARGETS"
        assert '"a"' in params[0]["default"]
        assert "first item" in params[0]["description"]
        assert "second item" in params[0]["description"]

    def test_multiline_defaults(self):
        code = (
            "# --- PARAMS ---\n"
            "TARGETS = [\n"
            '    "zaa",\n'
            '    "ambi",\n'
            "]\n"
            "# --- END PARAMS ---\n"
        )
        params = parse_params(code)
        assert len(params) == 1
        assert params[0]["name"] == "TARGETS"
        assert "zaa" in params[0]["default"]
        assert "ambi" in params[0]["default"]

    def test_missing_block_gives_empty(self):
        recipe = parse_recipe_source(
            '''\
"""
id: noparams
intent: Something
match_terms: ["x"]
entities: ["LexEntry"]
operations: ["read"]
requires_write: false
origin: test
notes: n
"""
report.Info("hi")
''',
            filename="noparams.py",
        )
        assert recipe["params"] == []


class TestMalformedAndCollision:
    def test_malformed_file_skipped_with_one_error(self, tmp_path):
        _write_recipe(
            tmp_path,
            "bad-recipe",
            '''\
"""
id: bad-recipe
match_terms: ["x"]
entities: ["LexEntry"]
operations: ["read"]
requires_write: false
origin: test
notes: n
"""
report.Info("hi")
''',
        )
        recipes, errors = load_recipe_library(tmp_path)
        assert recipes == {}
        assert len(errors) == 1
        # one error naming the file and the missing key
        assert "bad-recipe" in errors[0]
        assert "intent" in errors[0]

    def test_stem_id_mismatch_skipped(self, tmp_path):
        _write_recipe(
            tmp_path,
            "other-stem",
            '''\
"""
id: some-id
intent: Something
match_terms: ["x"]
entities: ["LexEntry"]
operations: ["read"]
requires_write: false
origin: test
notes: n
"""
report.Info("hi")
''',
        )
        recipes, errors = load_recipe_library(tmp_path)
        assert recipes == {}
        assert len(errors) == 1
        assert "other-stem" in errors[0] or "some-id" in errors[0]

    def test_id_collision_file_vs_file_raises(self, tmp_path):
        body = '''\
"""
id: dup-recipe
intent: Something
match_terms: ["x"]
entities: ["LexEntry"]
operations: ["read"]
requires_write: false
origin: test
notes: n
"""
report.Info("hi")
'''
        _write_recipe(tmp_path, "dup-recipe", body)
        sub = tmp_path / "sub"
        sub.mkdir()
        _write_recipe(sub, "dup-recipe", body)
        # same id in two files under the tree -> raise
        with pytest.raises(ValueError, match="dup-recipe"):
            load_recipe_library(tmp_path)

    def test_id_collision_file_vs_dict_raises(self, tmp_path):
        from flextoolsmcp.curated_recipes import CURATED_RECIPES

        existing_id = next(iter(CURATED_RECIPES))
        _write_recipe(
            tmp_path,
            existing_id,
            f'''\
"""
id: {existing_id}
intent: Something
match_terms: ["x"]
entities: ["LexEntry"]
operations: ["read"]
requires_write: false
origin: test
notes: n
"""
report.Info("hi")
''',
        )
        file_recipes, _ = load_recipe_library(tmp_path)
        with pytest.raises(ValueError, match=existing_id):
            recipe_files.merge_recipes(dict(CURATED_RECIPES), file_recipes)


class TestMergeAndPackaging:
    def test_file_recipes_merged_into_curated(self):
        from flextoolsmcp.curated_recipes import CURATED_RECIPES

        assert "parser-coverage" in CURATED_RECIPES
        recipe = CURATED_RECIPES["parser-coverage"]
        assert recipe["code"]
        assert recipe.get("params") is not None
        assert any(p["name"] == "COUNT" for p in recipe["params"])

    def test_library_is_package_data(self):
        lib = importlib.resources.files("flextoolsmcp") / "recipe_library"
        assert lib.is_dir()
        names = [p.name for p in lib.iterdir() if p.name.endswith(".py")]
        assert "parser-coverage.py" in names


class TestCodeTerms:
    def test_camelcase_split_and_alias(self):
        terms = extract_code_terms("x = project.Allomorph.GetPhoneEnv(a)\n")
        assert "phone" in terms
        assert "environment" in terms

    def test_underscore_split(self):
        terms = extract_code_terms("project.LexEntry.GetAll()\n")
        assert "lex" in terms or "entry" in terms
