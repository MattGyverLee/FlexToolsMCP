#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #47: Read-only auto-discovery tests.

Tests:
- _resolve_for_auto_discovery: correct entities pass, naive-fallback entities
  are rejected, cap is enforced.
- count==1: entity auto-discovered on a read run is NOT re-fired on a second
  read run referencing the same entity.
- write-retrigger: entity auto-discovered on a read run DOES re-trigger the
  undiscovered_entity gate on a WRITE run (write-gate isolation via
  validated_apis vs auto_discovered_apis).
- Write gate reads ONLY validated_apis (confirmed via detect_undiscovered_entities
  with a session that has the entity only in auto_discovered_apis).

Run with:
    python -m pytest tests/test_issue47_auto_discovery.py -q -m "not requires_flex"
"""

import sys
import ast
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server.session import SessionState
from flextoolsmcp.server.handlers.execution import (
    _resolve_for_auto_discovery,
    _AUTO_DISCOVER_CAP,
)
from flextoolsmcp.server.validators import detect_undiscovered_entities


# ---------------------------------------------------------------------------
# Minimal fake API index for tests
# ---------------------------------------------------------------------------

def _make_api_index(entities=None, accessor_props=None):
    """Build a minimal fake api_index with a flexicon attribute."""
    entities = entities or {}
    # FLExProject properties drive _accessor_to_ops_map
    fp_props = []
    for accessor, ops_class in (accessor_props or {}).items():
        fp_props.append({"name": accessor, "return_type": ops_class})
    entities["FLExProject"] = {"properties": fp_props}

    class FakeIndex:
        flexicon = {"entities": entities}

    return FakeIndex()


# ---------------------------------------------------------------------------
# _resolve_for_auto_discovery tests
# ---------------------------------------------------------------------------

class TestResolveForAutoDiscovery:

    def test_ops_class_in_entity_table_qualifies(self):
        """Entity ending in 'Operations' that is in the table qualifies."""
        idx = _make_api_index(entities={"LexEntryOperations": {}, "FLExProject": {}})
        result = _resolve_for_auto_discovery(["LexEntryOperations"], idx)
        assert result == ["LexEntryOperations"]

    def test_ops_class_not_in_table_rejected(self):
        """Entity ending in 'Operations' NOT in the table is rejected."""
        idx = _make_api_index(entities={"FLExProject": {}})
        result = _resolve_for_auto_discovery(["POSOperations"], idx)
        assert result == []

    def test_accessor_with_index_mapping_qualifies(self):
        """Accessor resolved via _accessor_to_ops_map to an entity in the table qualifies."""
        idx = _make_api_index(
            entities={"LexSenseOperations": {}, "FLExProject": {}},
            accessor_props={"Senses": "LexSenseOperations"},
        )
        result = _resolve_for_auto_discovery(["Senses"], idx)
        # Accessor resolves to LexSenseOperations (index-derived), which IS in the table
        assert result == ["LexSenseOperations"]

    def test_accessor_without_index_mapping_rejected(self):
        """Accessor NOT in _accessor_to_ops_map is rejected (naive fallback not allowed)."""
        # 'Unknown' is not in accessor_props -> _accessor_to_ops_map won't have it
        idx = _make_api_index(
            entities={"UnknownOperations": {}, "FLExProject": {}},
            accessor_props={},
        )
        result = _resolve_for_auto_discovery(["Unknown"], idx)
        assert result == [], "Naive f'{name}Operations' fallback MUST be rejected"

    def test_cap_enforced(self):
        """At most _AUTO_DISCOVER_CAP entities are returned."""
        entities = {f"Entity{i}Operations": {} for i in range(20)}
        entities["FLExProject"] = {}
        idx = _make_api_index(entities=entities)
        names = [f"Entity{i}Operations" for i in range(20)]
        result = _resolve_for_auto_discovery(names, idx)
        assert len(result) <= _AUTO_DISCOVER_CAP

    def test_empty_input_returns_empty(self):
        idx = _make_api_index()
        assert _resolve_for_auto_discovery([], idx) == []

    def test_none_index_returns_empty(self):
        assert _resolve_for_auto_discovery(["LexEntryOperations"], None) == []

    def test_mixed_qualifying_and_not(self):
        """Only qualifying entities are returned from a mixed list."""
        entities = {"LexEntryOperations": {}, "FLExProject": {}}
        idx = _make_api_index(entities=entities, accessor_props={})
        # LexEntryOperations qualifies (in table), UnknownAccessor does NOT (no map entry)
        result = _resolve_for_auto_discovery(["LexEntryOperations", "UnknownAccessor"], idx)
        assert "LexEntryOperations" in result
        assert "UnknownAccessor" not in result


# ---------------------------------------------------------------------------
# count==1: second read run must NOT re-fire auto-discovery
# ---------------------------------------------------------------------------

class TestCountOneSemantics:
    """
    Once an entity is auto-discovered in session, was_auto_discovered() returns
    True and the execution gate should not re-fire auto-discovery for it.

    We test this at the SessionState level (unit), not at the full handler
    level, because the handler requires a live subprocess.
    """

    def test_second_read_run_entity_already_in_auto_discovered(self):
        """After first auto-discovery, the gate code path (not a re-implementation
        of it) must treat the entity as already satisfied on the second read run.

        We test at the real gate boundary: was_auto_discovered() is the smallest
        code unit that performs the filter in execution.py; we assert its
        behaviour before and after record_auto_discovered_api() to confirm the
        count==1 invariant holds without re-running the filter expression from
        the handler itself.
        """
        s = SessionState()
        s.configure(session_id="test-session-47", api_mode="flexicon")

        # Before first run: entity is NOT yet auto-discovered.
        assert not s.was_auto_discovered("LexEntryOperations"), (
            "Entity should not be auto-discovered before the first read run"
        )

        # Simulate first read run granting the entity (execution.py calls this).
        s.record_auto_discovered_api("LexEntryOperations")

        # After first run: gate returns True -> second run finds nothing new.
        assert s.was_auto_discovered("LexEntryOperations"), (
            "Entity should be auto-discovered after the first read run"
        )
        # The handler early-exits via `previously_auto` for entities where
        # was_auto_discovered() is True -- confirm the gate itself is satisfied,
        # not a copy of the handler's list-comprehension.
        assert not [
            e for e in ["LexEntryOperations"]
            if not s.was_auto_discovered(e)
        ], (
            "Second read run: LexEntryOperations must not appear in new_undiscovered list"
        )

    def test_auto_discovered_not_in_validated_apis(self):
        """Auto-discovered entities are NOT in validated_apis (write-gate isolation)."""
        s = SessionState()
        s.configure(session_id="test-session-47b", api_mode="flexicon")
        s.record_auto_discovered_api("LexSenseOperations")

        assert "LexSenseOperations" not in s.validated_apis, (
            "auto_discovered_apis and validated_apis must remain disjoint"
        )
        assert "LexSenseOperations" in s.auto_discovered_apis


# ---------------------------------------------------------------------------
# Write-gate re-trigger: detect_undiscovered_entities reads ONLY validated_apis
# ---------------------------------------------------------------------------

class TestWriteGateIsolation:
    """
    An entity in auto_discovered_apis but NOT in validated_apis must still
    appear in detect_undiscovered_entities() output, so a WRITE run triggers
    the hard gate.
    """

    def _make_session_with_auto_discovered(self, entity: str) -> SessionState:
        s = SessionState()
        s.configure(session_id="write-gate-test", api_mode="flexicon")
        # Simulate read-run auto-discovery: goes into auto_discovered_apis only
        s.record_auto_discovered_api(entity)
        # Also add the accessor form so it's in auto_discovered but NOT validated
        return s

    def _make_code_tree(self, code: str):
        return ast.parse(code)

    def test_write_gate_fires_for_auto_discovered_only_entity(self):
        """
        Entity that is only in auto_discovered_apis (not validated_apis) MUST
        be flagged as undiscovered by detect_undiscovered_entities.

        This confirms the write gate reads validated_apis and discovered_apis,
        NOT auto_discovered_apis.

        We use project.<Accessor> form (not 'from flexicon import X') so that
        _collect_flexicon_imports does NOT grant implicit satisfaction for the
        import-scan path -- only validated_apis/discovered_apis count here.
        """
        from flextoolsmcp.server.validators import KNOWN_OPERATIONS

        # Pick an entity that is in KNOWN_OPERATIONS
        test_entity = None
        for op in KNOWN_OPERATIONS:
            if op.endswith("Operations") and op != "FLExProject":
                test_entity = op
                break

        if test_entity is None:
            pytest.skip("No suitable entity found in KNOWN_OPERATIONS")

        s = self._make_session_with_auto_discovered(test_entity)
        # Seed discovered_apis with something else so api_discovery_required
        # gate won't fire first (it checks len(discovered_apis) == 0)
        s.discovered_apis.add("SomeOtherEntity.SomeMethod")

        # Use the bare class name directly (not imported from flexicon so the
        # import-scan implicit-discovery path does NOT satisfy the gate).
        # We call the class as a function -- AST walker matches ast.Name nodes
        # whose id is in KNOWN_OPERATIONS.
        code = f"""
ops = {test_entity}(project)
for entry in ops.GetAll():
    pass
"""
        tree = self._make_code_tree(code)
        result = detect_undiscovered_entities(tree, s, api_index=None)

        # The entity should appear as undiscovered because it's only in
        # auto_discovered_apis, not validated_apis or discovered_apis.
        assert result["has_undiscovered"], (
            f"{test_entity} is only in auto_discovered_apis; write gate must "
            f"still flag it as undiscovered (validated_apis gate). "
            f"undiscovered={result['undiscovered']}"
        )

    def test_validated_api_not_reflagged(self):
        """Entity in validated_apis is NOT flagged by detect_undiscovered_entities."""
        from flextoolsmcp.server.validators import KNOWN_OPERATIONS

        test_entity = None
        for op in KNOWN_OPERATIONS:
            if op.endswith("Operations") and op != "FLExProject":
                test_entity = op
                break

        if test_entity is None:
            pytest.skip("No suitable entity found in KNOWN_OPERATIONS")

        s = SessionState()
        s.configure(session_id="write-gate-validated", api_mode="flexicon")
        # Properly validated (simulates get_object_api call)
        s.record_validated_api(test_entity)
        s.discovered_apis.add(f"{test_entity}.GetAll")

        code = f"""
from flexicon import {test_entity}
ops = {test_entity}(project)
for entry in ops.GetAll():
    pass
"""
        tree = ast.parse(code)
        result = detect_undiscovered_entities(tree, s, api_index=None)
        assert not result["has_undiscovered"] or test_entity not in result.get("undiscovered", []), (
            f"{test_entity} is in validated_apis; it should not be flagged. "
            f"undiscovered={result['undiscovered']}"
        )


# ---------------------------------------------------------------------------
# P0 regression: production-path configure() -- NO session_id kwarg
# ---------------------------------------------------------------------------

class TestProductionPathSessionContinuity:
    """
    Regression tests for the P0 bug where configure() with no session_id kwarg
    minted a fresh uuid4 every call, making is_new_session always True and
    wiping discovery state on every flextools_start restart.

    These tests call configure() WITHOUT a session_id kwarg -- the actual
    production path used by admin.py -- and verify the six session invariants.
    """

    def test_same_project_restart_preserves_discovery(self):
        """
        Production path: two configure() calls for the SAME project_name,
        NO session_id kwarg.  Discovery state MUST persist after the second
        call.  This is the test that would have caught the P0.
        """
        s = SessionState()
        # First start -- no session_id kwarg, as admin.py does in production.
        s.configure(api_mode="flexicon", project_name="MyProject")
        first_session_id = s.session_id
        assert first_session_id, "session_id must be set after first configure()"

        # Simulate an auto-discovery that happened during the first run.
        s.record_auto_discovered_api("LexEntryOperations")
        assert s.was_auto_discovered("LexEntryOperations")

        # Second start (re-start / same project) -- still no session_id kwarg.
        s.configure(api_mode="flexicon", project_name="MyProject")

        assert s.session_id == first_session_id, (
            "session_id must NOT change on same-project restart "
            f"(got {s.session_id!r}, expected {first_session_id!r})"
        )
        assert s.was_auto_discovered("LexEntryOperations"), (
            "Discovery state must PERSIST across same-project restart "
            "(P0: uuid4 mint on every call was wiping it)"
        )

    def test_different_project_restart_wipes_discovery(self):
        """
        Production path: second configure() with a DIFFERENT project_name
        MUST wipe discovery state (genuine new session boundary).
        """
        s = SessionState()
        s.configure(api_mode="flexicon", project_name="ProjectA")
        s.record_auto_discovered_api("LexEntryOperations")
        assert s.was_auto_discovered("LexEntryOperations")

        # Different project -- genuine new session.
        s.configure(api_mode="flexicon", project_name="ProjectB")

        assert not s.was_auto_discovered("LexEntryOperations"), (
            "Discovery state must be WIPED when project_name changes "
            "(cross-session isolation invariant)"
        )
        assert s.project_name == "ProjectB"

    def test_explicit_new_session_flag_wipes_discovery(self):
        """new_session=True always wipes, even for the same project."""
        s = SessionState()
        s.configure(api_mode="flexicon", project_name="ProjectA")
        s.record_auto_discovered_api("LexEntryOperations")

        s.configure(api_mode="flexicon", project_name="ProjectA", new_session=True)

        assert not s.was_auto_discovered("LexEntryOperations"), (
            "new_session=True must wipe discovery state even on same project"
        )

    def test_explicit_session_id_change_wipes_discovery(self):
        """Explicit session_id kwarg that differs from current wipes state."""
        s = SessionState()
        s.configure(session_id="session-A", api_mode="flexicon", project_name="ProjectA")
        s.record_auto_discovered_api("LexEntryOperations")

        s.configure(session_id="session-B", api_mode="flexicon", project_name="ProjectA")

        assert not s.was_auto_discovered("LexEntryOperations"), (
            "Different explicit session_id must wipe discovery state"
        )

    def test_explicit_same_session_id_preserves_discovery(self):
        """Explicit session_id kwarg that matches current preserves state."""
        s = SessionState()
        s.configure(session_id="session-A", api_mode="flexicon", project_name="ProjectA")
        s.record_auto_discovered_api("LexEntryOperations")

        s.configure(session_id="session-A", api_mode="flexicon", project_name="ProjectA")

        assert s.was_auto_discovered("LexEntryOperations"), (
            "Same explicit session_id must preserve discovery state"
        )

    def test_write_enabled_not_affected_by_p0_fix(self):
        """
        Write-gate isolation (validators.py:851 satisfied-set logic) must not
        be disturbed -- auto_discovered entities must NOT be in validated_apis
        even after a same-project restart.
        """
        s = SessionState()
        s.configure(api_mode="flexicon", project_name="ProjectA")
        s.record_auto_discovered_api("LexSenseOperations")

        # Same-project restart.
        s.configure(api_mode="flexicon", project_name="ProjectA")

        assert "LexSenseOperations" not in s.validated_apis, (
            "auto_discovered entity must remain out of validated_apis after restart"
        )
        assert s.was_auto_discovered("LexSenseOperations"), (
            "auto_discovered entity must remain in auto_discovered_apis after restart"
        )
