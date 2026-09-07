#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #100: facade-only classes advertised as importable.

MSAOperations (and any other Operations class reachable only via a
`FLExProject` facade property, e.g. `project.MSA`) is shape-identical in the
index to the 43 genuinely top-level-importable flexicon entities, so a
generated script that follows the advertised `import_statement` gets
`ImportError: cannot import name 'MSAOperations' from 'flexicon'`.

Coverage:
  - flexicon_analyzer._extract_facade_access_paths recovers
    {ClassName: "project.<prop>"} from FLExProject.py's memoization idiom
    (`self._x_ops = ClassName(self)` inside an `@property` body).
  - analyze_class() sets entity["access_path"] only when the facade map has
    a hit for that class name; the key is OMITTED (not None) otherwise, so
    every consumer's `.get("access_path")` degrades to today's behavior --
    this is the well-tested normal path since the shipped index predates
    the fix.
  - server.handlers.api._build_entity_import prefers access_path when
    present, and falls back to the historical "from <lib> import <Entity>"
    line when it's absent (including when no `entity` arg is passed at
    all, matching pre-fix call sites).
  - server.handlers.api.paginate_entity's result dict (get_object_api's
    summary AND full mode) carries access_path through -- it previously did
    not, since paginate_entity builds a bespoke result dict rather than
    passing the raw entity through.
  - The real shipped flexicon index (pre-refresh) has no access_path key
    anywhere yet, confirming the absent-key fallback is exercised against
    real data, not just synthetic fixtures.
"""

import ast
import json
import textwrap
import unittest
from pathlib import Path


# ---------------------------------------------------------------------------
# _extract_facade_access_paths
# ---------------------------------------------------------------------------

class TestExtractFacadeAccessPaths(unittest.TestCase):
    """Mirrors the real memoization idiom at
    flexicon/code/FLExProject.py:1516-1546 (the MSA property)."""

    def _write_fixture(self, tmp_path: Path, body: str) -> Path:
        code_dir = tmp_path / "flexicon" / "code"
        code_dir.mkdir(parents=True)
        (code_dir / "FLExProject.py").write_text(textwrap.dedent(body), encoding="utf-8")
        return code_dir

    def test_facade_only_class_recovered(self):
        import tempfile
        from flextoolsmcp.flexicon_analyzer import _extract_facade_access_paths

        with tempfile.TemporaryDirectory() as tmp:
            code_dir = self._write_fixture(Path(tmp), '''
                class FLExProject:
                    @property
                    def MSA(self):
                        """Access to morphosyntactic-analysis operations."""
                        if "_msa_ops" not in self.__dict__:
                            from .Lexicon.MSAOperations import MSAOperations
                            self._msa_ops = MSAOperations(self)
                        return self._msa_ops
            ''')
            paths = _extract_facade_access_paths(code_dir)

        self.assertEqual(paths.get("MSAOperations"), "project.MSA")

    def test_multiple_facade_properties_all_recovered(self):
        import tempfile
        from flextoolsmcp.flexicon_analyzer import _extract_facade_access_paths

        with tempfile.TemporaryDirectory() as tmp:
            code_dir = self._write_fixture(Path(tmp), '''
                class FLExProject:
                    @property
                    def LexEntry(self):
                        if "_lexentry_ops" not in self.__dict__:
                            from .Lexicon.LexEntryOperations import LexEntryOperations
                            self._lexentry_ops = LexEntryOperations(self)
                        return self._lexentry_ops

                    @property
                    def MSA(self):
                        if "_msa_ops" not in self.__dict__:
                            from .Lexicon.MSAOperations import MSAOperations
                            self._msa_ops = MSAOperations(self)
                        return self._msa_ops
            ''')
            paths = _extract_facade_access_paths(code_dir)

        self.assertEqual(paths.get("LexEntryOperations"), "project.LexEntry")
        self.assertEqual(paths.get("MSAOperations"), "project.MSA")

    def test_non_property_method_ignored(self):
        """A plain (non-@property) method with the same assignment idiom
        must not be picked up -- only @property bodies count."""
        import tempfile
        from flextoolsmcp.flexicon_analyzer import _extract_facade_access_paths

        with tempfile.TemporaryDirectory() as tmp:
            code_dir = self._write_fixture(Path(tmp), '''
                class FLExProject:
                    def _build_helper(self):
                        self._helper_ops = HelperOperations(self)
                        return self._helper_ops
            ''')
            paths = _extract_facade_access_paths(code_dir)

        self.assertEqual(paths, {})

    def test_missing_file_returns_empty(self):
        import tempfile
        from flextoolsmcp.flexicon_analyzer import _extract_facade_access_paths

        with tempfile.TemporaryDirectory() as tmp:
            code_dir = Path(tmp) / "flexicon" / "code"
            code_dir.mkdir(parents=True)
            paths = _extract_facade_access_paths(code_dir)

        self.assertEqual(paths, {})

    def test_no_flexproject_class_returns_empty(self):
        import tempfile
        from flextoolsmcp.flexicon_analyzer import _extract_facade_access_paths

        with tempfile.TemporaryDirectory() as tmp:
            code_dir = self._write_fixture(Path(tmp), '''
                class SomethingElse:
                    @property
                    def MSA(self):
                        self._msa_ops = MSAOperations(self)
                        return self._msa_ops
            ''')
            paths = _extract_facade_access_paths(code_dir)

        self.assertEqual(paths, {})


# ---------------------------------------------------------------------------
# analyze_class() -- access_path annotation
# ---------------------------------------------------------------------------

class TestAnalyzeClassAccessPath(unittest.TestCase):
    def _class_node(self, source: str) -> ast.ClassDef:
        tree = ast.parse(textwrap.dedent(source))
        return next(n for n in tree.body if isinstance(n, ast.ClassDef))

    def test_facade_hit_sets_access_path(self):
        from flextoolsmcp.flexicon_analyzer import analyze_class

        node = self._class_node('''
            class MSAOperations:
                """Creation + attach operations for MSAs."""
                def CreateStem(self, sense, pos):
                    """Create a stem MSA."""
                    pass
        ''')
        entity = analyze_class(node, "Lexicon/MSAOperations", [], {"MSAOperations": "project.MSA"})
        self.assertEqual(entity["access_path"], "project.MSA")

    def test_no_facade_map_omits_key(self):
        """Default (facade_access_paths=None) -- the pre-fix call shape."""
        from flextoolsmcp.flexicon_analyzer import analyze_class

        node = self._class_node('''
            class LexEntryOperations:
                """Entry operations."""
                def Create(self, form):
                    pass
        ''')
        entity = analyze_class(node, "Lexicon/LexEntryOperations", [])
        self.assertNotIn("access_path", entity)

    def test_facade_map_present_but_no_hit_omits_key(self):
        from flextoolsmcp.flexicon_analyzer import analyze_class

        node = self._class_node('''
            class SomeHelper:
                """Not facade-reachable."""
                def DoThing(self):
                    pass
        ''')
        entity = analyze_class(node, "System/SomeHelper", [], {"MSAOperations": "project.MSA"})
        self.assertNotIn("access_path", entity)


# ---------------------------------------------------------------------------
# server.handlers.api._build_entity_import
# ---------------------------------------------------------------------------

class TestBuildEntityImportAccessPath(unittest.TestCase):
    def test_access_path_preferred_when_present(self):
        from server.handlers.api import _build_entity_import

        entity = {"access_path": "project.MSA"}
        result = _build_entity_import(
            "flexicon", "MSAOperations", "flexicon.code.Lexicon.MSAOperations", entity
        )
        self.assertEqual(result, "project.MSA")

    def test_absent_access_path_falls_back_to_import_line(self):
        """Golden fallback: entity dict present but with no access_path key
        (today's shipped-index shape) -- byte-identical to pre-fix output."""
        from server.handlers.api import _build_entity_import

        entity = {"name": "LexEntryOperations"}
        result = _build_entity_import(
            "flexicon", "LexEntryOperations", "flexicon.code.Lexicon.LexEntryOperations", entity
        )
        self.assertEqual(result, "from flexicon import LexEntryOperations")

    def test_no_entity_arg_falls_back(self):
        """Callers that don't pass `entity` at all (the 4 sites' pre-fix
        signature) must see unchanged behavior."""
        from server.handlers.api import _build_entity_import

        result = _build_entity_import(
            "flexicon", "LexEntryOperations", "flexicon.code.Lexicon.LexEntryOperations"
        )
        self.assertEqual(result, "from flexicon import LexEntryOperations")

    def test_empty_access_path_string_falls_back(self):
        """Falsy-but-present access_path (e.g. "") must not short-circuit --
        defensive against a generator bug emitting "" instead of omitting
        the key."""
        from server.handlers.api import _build_entity_import

        entity = {"access_path": ""}
        result = _build_entity_import(
            "flexicon", "LexEntryOperations", "flexicon.code.Lexicon.LexEntryOperations", entity
        )
        self.assertEqual(result, "from flexicon import LexEntryOperations")

    def test_liblcm_still_uses_namespace_form(self):
        """liblcm entities never carry access_path -- unaffected either way."""
        from server.handlers.api import _build_entity_import

        result = _build_entity_import("liblcm", "ILexEntry", "SIL.LCModel")
        self.assertEqual(result, "from SIL.LCModel import ILexEntry")

    def test_liblcm_missing_namespace_returns_empty(self):
        from server.handlers.api import _build_entity_import

        result = _build_entity_import("liblcm", "ILexEntry", "")
        self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# server.handlers.api.paginate_entity -- summary-mode field allowlist
# ---------------------------------------------------------------------------

class TestPaginateEntityAccessPath(unittest.TestCase):
    def _entity(self, **overrides):
        base = {
            "category": "lexicon",
            "summary": "Test entity",
            "source_file": "Lexicon/MSAOperations",
            "methods": [],
            "properties": [],
        }
        base.update(overrides)
        return base

    def test_access_path_surfaces_full_mode(self):
        from server.handlers.api import paginate_entity

        entity = self._entity(access_path="project.MSA")
        result = paginate_entity(
            entity, summary_only=False, method_filter="", limit=50, offset=0,
            object_type="MSAOperations", library="flexicon",
        )
        self.assertEqual(result["access_path"], "project.MSA")

    def test_access_path_surfaces_summary_mode(self):
        """Issue #100 flagged this as unverified: the summary-mode result is
        a hand-built dict, so a new entity-level key must be carried
        explicitly or it silently never surfaces via get_object_api."""
        from server.handlers.api import paginate_entity

        entity = self._entity(access_path="project.MSA")
        result = paginate_entity(
            entity, summary_only=True, method_filter="", limit=50, offset=0,
            object_type="MSAOperations", library="flexicon",
        )
        self.assertEqual(result["access_path"], "project.MSA")

    def test_absent_access_path_omitted(self):
        from server.handlers.api import paginate_entity

        entity = self._entity()
        result = paginate_entity(
            entity, summary_only=False, method_filter="", limit=50, offset=0,
            object_type="LexEntryOperations", library="flexicon",
        )
        self.assertNotIn("access_path", result)


# ---------------------------------------------------------------------------
# Real shipped index: documents the pre-refresh state
# ---------------------------------------------------------------------------

class TestRealIndexPreRefreshState(unittest.TestCase):
    """The working tree's shipped flexicon index predates this fix (a
    regeneration is explicitly out of scope for this task, and forbidden
    while an unrelated 4.4.1 -> 4.5.2 migration is uncommitted). These tests
    lock in that the absent-access_path fallback is genuinely the live,
    exercised path today -- not just a hypothetical."""

    @classmethod
    def setUpClass(cls):
        idx_path = (
            Path(__file__).parent.parent
            / "src" / "flextoolsmcp" / "index" / "python" / "flexicon_api_v4.5.2.json"
        )
        if not idx_path.exists():
            cls.entity = None
            return
        with open(idx_path, encoding="utf-8") as f:
            data = json.load(f)
        cls.entity = data.get("entities", {}).get("MSAOperations")

    def test_msa_operations_has_no_access_path_yet(self):
        if self.entity is None:
            self.skipTest("shipped flexicon index / MSAOperations entity not found")
        self.assertNotIn("access_path", self.entity)

    def test_build_entity_import_falls_back_for_unrefreshed_index(self):
        if self.entity is None:
            self.skipTest("shipped flexicon index / MSAOperations entity not found")
        from server.handlers.api import _build_entity_import

        namespace = self.entity.get("namespace", "") or ""
        result = _build_entity_import("flexicon", "MSAOperations", namespace, self.entity)
        # Documents the known-broken pre-refresh behavior this fix targets --
        # it only self-heals once someone runs a refresh.
        self.assertEqual(result, "from flexicon import MSAOperations")


# ---------------------------------------------------------------------------
# Cycle-7 CP-D D-3: paginate_entity's is_operations_class import-advertising
# branch (server/handlers/api.py:689-712-ish) -- confirmed no-op triage
# ---------------------------------------------------------------------------

class TestKnownOperationsImportInvariant(unittest.TestCase):
    """paginate_entity's `is_operations_class` branch unconditionally emits
    `from {library} import {object_type}` for every object_type in
    constants.KNOWN_OPERATIONS, without consulting entity["access_path"]
    (the issue #100 facade truth computed a few lines above it in the same
    function). That is only safe because every current KNOWN_OPERATIONS
    member is ALSO genuinely top-level importable from flexicon -- confirmed
    here at runtime against the installed package (flexicon 4.5.2), not by
    reading names. 42 of the 43 members additionally have a facade
    access_path (e.g. LexEntryOperations -> project.LexEntry) but remain
    top-level importable too, so advertising the bare import is never wrong
    for them today.

    Widened cycle 9 (P1-1): the hazard is bigger than "MSAOperations is the
    one facade-only class". Of ALL 64 flexicon `*Operations` classes, 13 are
    facade-only (no top-level import -- e.g. MSAOperations, reachable only
    via `project.MSA`) and 8 more are unreachable by either route (measured
    with `_extract_facade_access_paths` against the installed flexicon
    4.5.2, same helper `TestExtractFacadeAccessPaths` above exercises).
    `test_msa_operations_deliberately_excluded_from_known_operations` used
    to pin a single hardcoded name; it now asserts KNOWN_OPERATIONS is
    disjoint from the FULL live-computed facade-only/unreachable set, so it
    still fires (hasattr-based) if ANY of those 21 classes -- not just
    MSAOperations -- is ever added to KNOWN_OPERATIONS.

    This pins the invariant that makes today's api.py is_operations_class
    branch a documented no-op. If it ever fails, KNOWN_OPERATIONS has gained
    a facade-only or unreachable member and that branch needs the
    access_path-aware fix that was deferred in cycle 7 (see
    specs/swahili-audit-2026-09/reviews/cycle7-programmer-p2.md for the full
    analysis)."""

    @staticmethod
    def _live_facade_only_and_unreachable_operations():
        """Recompute the full facade-only/unreachable *Operations set live
        against the installed flexicon package + shipped index (not a
        hardcoded list), mirroring cycle8-qc.md's P1-1 measurement."""
        import flexicon
        from flextoolsmcp.flexicon_analyzer import _extract_facade_access_paths

        idx_path = (
            Path(__file__).parent.parent
            / "src" / "flextoolsmcp" / "index" / "python" / "flexicon_api_v4.5.2.json"
        )
        with open(idx_path, encoding="utf-8") as f:
            data = json.load(f)
        ops_names = sorted(n for n in data.get("entities", {}) if n.endswith("Operations"))

        flexicon_code_base = Path(flexicon.__file__).parent / "code"
        facade = _extract_facade_access_paths(flexicon_code_base)

        hazardous = set()
        for name in ops_names:
            if not hasattr(flexicon, name):
                # Not top-level importable -- facade-only or unreachable,
                # either way an unconditional `from flexicon import {name}`
                # would be broken.
                hazardous.add(name)
        return hazardous

    def test_every_known_operations_member_is_top_level_importable(self):
        try:
            import flexicon
        except Exception as exc:
            # P3 (cycle8-qc.md): a bare skipTest leaves this tripwire
            # unguarded in a flexicon-less CI with no visible signal beyond
            # the skip reason. Make it loud: the message states plainly
            # that the invariant is UNCHECKED this run, not just why.
            self.skipTest(
                f"flexicon not importable in this environment ({exc}) -- "
                "KNOWN_OPERATIONS top-level-importability tripwire is "
                "UNGUARDED for this run."
            )

        from flextoolsmcp.server.constants import KNOWN_OPERATIONS

        not_importable = sorted(
            name for name in KNOWN_OPERATIONS if not hasattr(flexicon, name)
        )
        self.assertEqual(
            not_importable,
            [],
            "KNOWN_OPERATIONS contains facade-only class(es) that are NOT "
            "top-level importable from flexicon: %r -- server/handlers/"
            "api.py's is_operations_class branch now advertises a broken "
            "import for these; see cycle7-programmer-p2.md STEP 2 for the "
            "deferred fix." % not_importable,
        )

    def test_known_operations_disjoint_from_full_facade_only_set(self):
        """Widened P1-1 tripwire: not just MSAOperations -- KNOWN_OPERATIONS
        must contain none of the 21 (13 facade-only + 8 unreachable)
        flexicon `*Operations` classes that are NOT top-level importable."""
        try:
            hazardous = self._live_facade_only_and_unreachable_operations()
        except Exception as exc:
            self.skipTest(
                f"could not compute live facade-only set in this "
                f"environment ({exc}) -- widened tripwire is UNGUARDED for "
                "this run."
            )

        from flextoolsmcp.server.constants import KNOWN_OPERATIONS

        overlap = sorted(KNOWN_OPERATIONS & hazardous)
        self.assertEqual(
            overlap,
            [],
            "KNOWN_OPERATIONS contains facade-only/unreachable class(es) "
            "%r -- server/handlers/api.py's is_operations_class branch now "
            "advertises a broken top-level import for these; needs the "
            "access_path-aware fix deferred in "
            "cycle7-programmer-p2.md." % overlap,
        )
        # Documents the previously-pinned single fact as a sanity check that
        # the live computation still agrees with the measured baseline.
        self.assertIn("MSAOperations", hazardous)


if __name__ == "__main__":
    unittest.main()
