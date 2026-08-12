#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #86 CP2: inheritance resolution
(specs/inheritance-resolution/SPEC.md).

Covers:
  T2.1 collect_inherited_members -- memoized, cycle-guarded ancestor walk
       (interfaces UNION base_classes), scoped this cycle to LibLCM
       interface entities only (DEC-2: 250 entities collide across 2214
       (entity, property) pairs on the CLASS side, 0 on the interface
       side -- cycle1-explore.md Sec.3).
  T2.2/T2.3 paginate_entity merges ancestor members before filtering,
       totals, and offset/limit slicing. total_properties/total_methods
       stay byte-identical (own-only, DEC-3); the
       total_*_including_inherited counterparts report the combined
       total; has_more/next_offset are repointed to the combined total so
       pagination does not under-report remaining pages once merged
       members are in the candidate list.
  T2.4 resolve_pythonic_property gains an ancestor-aware fallback that
       only fires when the exact-context-entity match finds nothing.
  T2.5 Cross-tool consistency invariant (SPEC.md Sec.3), sampled against
       THREE surfaces: get_object_api, resolve_property, and
       validators._interface_member_names. The last is READ-ONLY this
       spurt (DEC-5) -- these tests assert against it, they do not edit
       validators.py.

Canonical case (cycle1-explore.md Sec.4): IFsClosedValue merges 2 own ->
31 total properties; FeatureRA (declared on IFsFeatureSpecification)
becomes visible with inherited_from set.
"""

import asyncio
import json

import pytest


def run_async(coro):
    """Run an async coroutine synchronously for tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module")
def real_index():
    """Load the real, shipped LibLCM index once for the module.

    Mirrors tests/test_issue85_navigation_path.py's pattern: `server`
    resolves to the package (server/__init__.py), which lazy-loads
    server.py with `__package__ == "flextoolsmcp"` set explicitly so its
    relative kernel import resolves to the SAME session_state/api_index
    singletons every handler module already shares (see the long comment
    in server/__init__.py's __getattr__ re: issue #10 split-brain).
    """
    from server import APIIndex  # type: ignore
    from server.kernel import initialize_kernel, set_api_index, get_index_dir  # type: ignore

    initialize_kernel()
    idx = APIIndex.load(get_index_dir())
    set_api_index(idx)
    assert idx.liblcm, "liblcm index failed to load -- is the shipped JSON present?"
    return idx


@pytest.fixture
def liblcm_entities(real_index):
    return real_index.liblcm["entities"]


@pytest.fixture(autouse=True)
def _liblcm_mode(real_index):
    """get_object_api/resolve_property only surface liblcm entities when
    the session mode includes it; the session default is 'flexicon'."""
    from server.handlers import api as api_handlers  # type: ignore

    previous = api_handlers.session_state.api_mode
    api_handlers.session_state.api_mode = "liblcm"
    yield
    api_handlers.session_state.api_mode = previous


# ---------------------------------------------------------------------------
# T2.1: collect_inherited_members
# ---------------------------------------------------------------------------

class TestCollectInheritedMembers:
    def test_ifsclosedvalue_merges_2_own_to_31_total(self, liblcm_entities):
        from server.handlers.api import collect_inherited_members

        entity = liblcm_entities["IFsClosedValue"]
        assert len(entity["properties"]) == 2  # own-only, sanity-check the fixture data

        inherited = collect_inherited_members("IFsClosedValue", liblcm_entities)
        own_names = {p["name"] for p in entity["properties"]}
        combined_names = own_names | {p["name"] for p in inherited["properties"]}
        assert len(combined_names) == 31

    def test_featurera_inherited_from_ifsfeaturespecification(self, liblcm_entities):
        from server.handlers.api import collect_inherited_members

        inherited = collect_inherited_members("IFsClosedValue", liblcm_entities)
        by_name = {p["name"]: p for p in inherited["properties"]}
        assert "FeatureRA" in by_name
        assert by_name["FeatureRA"]["inherited_from"] == "IFsFeatureSpecification"

    def test_child_wins_own_member_not_duplicated_as_inherited(self, liblcm_entities):
        from server.handlers.api import collect_inherited_members

        entity = liblcm_entities["IFsClosedValue"]
        own_names = {p["name"] for p in entity["properties"]}
        inherited = collect_inherited_members("IFsClosedValue", liblcm_entities)
        inherited_names = {p["name"] for p in inherited["properties"]}
        assert own_names.isdisjoint(inherited_names)

    def test_memoized_same_index_same_entity(self, liblcm_entities):
        from server.handlers.api import collect_inherited_members

        first = collect_inherited_members("IFsClosedValue", liblcm_entities)
        second = collect_inherited_members("IFsClosedValue", liblcm_entities)
        assert first is second  # cache hit, not just equal

    def test_unknown_entity_returns_empty(self, liblcm_entities):
        from server.handlers.api import collect_inherited_members

        result = collect_inherited_members("INoSuchInterface", liblcm_entities)
        assert result == {"properties": [], "methods": []}

    def test_cycle_guard_does_not_hang(self):
        """Defensive: a hand-authored index with a self-referential
        `interfaces` cycle must not hang collect_inherited_members."""
        from server.handlers.api import collect_inherited_members

        fake_index = {
            "IA": {"type": "interface", "properties": [{"name": "Own"}], "methods": [],
                   "interfaces": ["IB"], "base_classes": []},
            "IB": {"type": "interface", "properties": [{"name": "FromB"}], "methods": [],
                   "interfaces": ["IA"], "base_classes": []},  # cycles back to IA
        }
        result = collect_inherited_members("IA", fake_index)
        names = {p["name"] for p in result["properties"]}
        assert names == {"FromB"}

    def test_second_example_ichkterm_confidence(self, liblcm_entities):
        """Second data point, distinct ancestor chain from the canonical
        case: IChkTerm merges 4 own -> 59 total; ConfidenceRA is declared
        on ICmPossibility."""
        from server.handlers.api import collect_inherited_members

        entity = liblcm_entities["IChkTerm"]
        assert len(entity["properties"]) == 4
        inherited = collect_inherited_members("IChkTerm", liblcm_entities)
        combined = {p["name"] for p in entity["properties"]} | {p["name"] for p in inherited["properties"]}
        assert len(combined) == 59
        by_name = {p["name"]: p for p in inherited["properties"]}
        assert by_name["ConfidenceRA"]["inherited_from"] == "ICmPossibility"


# ---------------------------------------------------------------------------
# T2.2/T2.3: paginate_entity merge + totals + has_more wiring
# ---------------------------------------------------------------------------

class TestPaginateEntityMerge:
    def test_total_properties_byte_identical_own_only(self, liblcm_entities):
        from server.handlers.api import paginate_entity

        entity = liblcm_entities["IFsClosedValue"]
        result = paginate_entity(
            entity, summary_only=False, method_filter="", limit=50, offset=0,
            object_type="IFsClosedValue", library="liblcm", entities_index=liblcm_entities,
        )
        assert result["total_properties"] == 2
        assert result["total_properties_including_inherited"] == 31

    def test_featurera_visible_with_inherited_from(self, liblcm_entities):
        from server.handlers.api import paginate_entity

        entity = liblcm_entities["IFsClosedValue"]
        result = paginate_entity(
            entity, summary_only=False, method_filter="", limit=50, offset=0,
            object_type="IFsClosedValue", library="liblcm", entities_index=liblcm_entities,
        )
        by_name = {p["name"]: p for p in result["properties"]}
        assert "FeatureRA" in by_name
        assert by_name["FeatureRA"]["inherited_from"] == "IFsFeatureSpecification"

    def test_summary_only_shape_keeps_inherited_from(self, liblcm_entities):
        """DEC-3: inherited_from survives summary_only truncation, same
        treatment casting_notes gets."""
        from server.handlers.api import paginate_entity

        entity = liblcm_entities["IFsClosedValue"]
        result = paginate_entity(
            entity, summary_only=True, method_filter="", limit=50, offset=0,
            object_type="IFsClosedValue", library="liblcm", entities_index=liblcm_entities,
        )
        by_name = {p["name"]: p for p in result["properties"]}
        assert by_name["FeatureRA"]["inherited_from"] == "IFsFeatureSpecification"
        assert set(by_name["FeatureRA"].keys()) <= {"name", "description", "inherited_from"}

    def test_has_more_uses_combined_total_not_underreported(self, liblcm_entities):
        """31 combined properties, limit=10: has_more must reflect the
        combined total, not silently stop reporting more pages once the
        2-own total is exhausted (explore.md Sec.2: 'coherence bug merged
        members will amplify')."""
        from server.handlers.api import paginate_entity

        entity = liblcm_entities["IFsClosedValue"]
        result = paginate_entity(
            entity, summary_only=False, method_filter="", limit=10, offset=0,
            object_type="IFsClosedValue", library="liblcm", entities_index=liblcm_entities,
        )
        assert result["total_properties"] == 2
        assert result["total_properties_including_inherited"] == 31
        assert result["returned_properties"] == 10
        assert result["has_more"] is True
        assert result["next_offset"] == 10

    def test_offset_pagination_reaches_featurera(self, liblcm_entities):
        """FeatureRA must be reachable by paging through offset, not just
        visible at offset=0/limit=50 -- proves the merge feeds the SAME
        list that offset/limit slices, not a side channel."""
        from server.handlers.api import paginate_entity

        entity = liblcm_entities["IFsClosedValue"]
        seen = []
        offset = 0
        for _ in range(10):  # 31 properties / 5 per page, generous cap
            result = paginate_entity(
                entity, summary_only=False, method_filter="", limit=5, offset=offset,
                object_type="IFsClosedValue", library="liblcm", entities_index=liblcm_entities,
            )
            seen.extend(p["name"] for p in result["properties"])
            if not result.get("has_more"):
                break
            offset = result["next_offset"]
        assert "FeatureRA" in seen
        assert len(seen) == 31

    def test_non_interface_entity_unaffected(self, liblcm_entities):
        """DEC-2 scope gate: class entities (even ones with real ancestor
        collisions, cycle1-explore.md Sec.3) are NOT merged this cycle."""
        from server.handlers.api import paginate_entity

        entity = liblcm_entities["FsClosedValue"]  # the class, not the interface
        assert entity["type"] == "class"
        own_count = len(entity["properties"])
        result = paginate_entity(
            entity, summary_only=False, method_filter="", limit=50, offset=0,
            object_type="FsClosedValue", library="liblcm", entities_index=liblcm_entities,
        )
        assert result["total_properties"] == own_count
        assert result["total_properties_including_inherited"] == own_count
        assert all("inherited_from" not in p for p in result["properties"])

    def test_no_entities_index_byte_identical_to_pre_feature_shape(self, liblcm_entities):
        """Existing callers (e.g. tests/test_issue48_inline_casting.py) that
        don't pass entities_index must see unchanged output."""
        from server.handlers.api import paginate_entity

        entity = liblcm_entities["IFsClosedValue"]
        result = paginate_entity(
            entity, summary_only=False, method_filter="", limit=50, offset=0,
            object_type="IFsClosedValue", library="liblcm",
        )
        assert result["total_properties"] == 2
        assert result["total_properties_including_inherited"] == 2
        assert all("inherited_from" not in p for p in result["properties"])


# ---------------------------------------------------------------------------
# T2.4: resolve_pythonic_property ancestor-aware fallback
# ---------------------------------------------------------------------------

class TestResolvePythonicPropertyFallback:
    def test_exact_match_still_wins_no_fallback_needed(self, real_index):
        from server.handlers.api import resolve_pythonic_property

        # "Value" is IFsClosedValue's OWN pythonic name for ValueRA.
        matches = resolve_pythonic_property("Value", context_entity="IFsClosedValue")
        assert matches
        assert all(m["entity"] == "IFsClosedValue" for m in matches)
        assert all("inherited_from" not in m for m in matches)

    def test_ancestor_fallback_finds_featurera(self, real_index):
        from server.handlers.api import resolve_pythonic_property

        # cycle1-explore.md Sec.1: by_pythonic_name["Feature"] lists
        # IFsFeatureSpecification, not IFsClosedValue -- the exact match
        # fails and the ancestor-aware fallback must find it.
        matches = resolve_pythonic_property("Feature", context_entity="IFsClosedValue")
        assert matches
        assert any(m["entity"] == "IFsFeatureSpecification" for m in matches)
        assert any(m.get("inherited_from") == "IFsFeatureSpecification" for m in matches)

    def test_fallback_does_not_mutate_shared_index(self, real_index):
        """Regression: tagging inherited_from on a by_pythonic_name match
        must not leak into a DIFFERENT context's lookup of the same
        pythonic name (the suffix index is a shared, module-level
        structure)."""
        from server.handlers.api import resolve_pythonic_property

        resolve_pythonic_property("Feature", context_entity="IFsClosedValue")
        direct = resolve_pythonic_property("Feature", context_entity="IFsFeatureSpecification")
        assert direct
        assert all("inherited_from" not in m for m in direct)

    def test_fallback_scoped_to_interface_entities_only(self, real_index):
        """DEC-2 scope gate: class-side context entities do not get the
        ancestor walk this cycle."""
        from server.handlers.api import resolve_pythonic_property

        matches = resolve_pythonic_property("Feature", context_entity="FsClosedValue")
        assert matches == []


# ---------------------------------------------------------------------------
# T2.5: cross-tool consistency invariant (SPEC.md Sec.3)
# ---------------------------------------------------------------------------

# (concrete_type, inherited property full name, pythonic name, declaring ancestor)
INVARIANT_CASES = [
    ("IFsClosedValue", "FeatureRA", "Feature", "IFsFeatureSpecification"),
    ("IChkTerm", "ConfidenceRA", "Confidence", "ICmPossibility"),
]


class TestConsistencyInvariant:
    """SPEC.md Sec.3: for every (property, concrete_type) pair where
    `property` is declared (own, DeclaredOnly) on some ancestor A in
    concrete_type's interfaces closure: get_object_api(concrete_type) MUST
    list `property` with inherited_from == A, AND resolve_property(property,
    context_entity=concrete_type) MUST return found: True.

    Sampled against a third surface too (validators._interface_member_names)
    per lex-author's cycle-1 caution -- read-only, DEC-5.
    """

    @pytest.mark.parametrize("concrete_type,full_name,pythonic,ancestor", INVARIANT_CASES)
    def test_get_object_api_surface(self, concrete_type, full_name, pythonic, ancestor):
        from server.handlers.api import handle_get_object_api

        args = {"object_type": concrete_type, "limit": 100, "offset": 0}
        result = run_async(handle_get_object_api(args))
        payload = json.loads(result[0].text)
        assert payload["found"] is True
        props = payload["liblcm"]["properties"]
        by_name = {p["name"]: p for p in props}
        assert full_name in by_name, f"{full_name} not visible on {concrete_type}"
        assert by_name[full_name]["inherited_from"] == ancestor

    @pytest.mark.parametrize("concrete_type,full_name,pythonic,ancestor", INVARIANT_CASES)
    def test_resolve_property_surface(self, concrete_type, full_name, pythonic, ancestor):
        from server.handlers.api import handle_resolve_property

        args = {"property_name": pythonic, "context_entity": concrete_type}
        result = run_async(handle_resolve_property(args))
        payload = json.loads(result[0].text)
        assert payload["found"] is True, payload
        assert any(m.get("entity") == ancestor for m in payload.get("matches", []))

    @pytest.mark.parametrize("concrete_type,full_name,pythonic,ancestor", INVARIANT_CASES)
    def test_validators_interface_member_names_surface(
        self, concrete_type, full_name, pythonic, ancestor, real_index
    ):
        """DEC-5: validators._interface_member_names is READ-ONLY this
        spurt -- this asserts against it (per SPEC.md CP2 T2.5), it does
        NOT edit validators.py even though it is the same file another
        crew is editing this cycle (hunks at lines 20/449-460/552-576/
        656-676, disjoint from this function at 765-797)."""
        from server.validators import _interface_member_names

        names = _interface_member_names(concrete_type, real_index)
        assert full_name in names, (
            f"validators._interface_member_names({concrete_type!r}) is missing "
            f"{full_name!r} -- the third surface would diverge from "
            f"get_object_api/resolve_property."
        )


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
