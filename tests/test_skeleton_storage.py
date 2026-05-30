#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for src/server/skeleton_storage.py (issue #24).

Covers:
- AST extraction of top-level defs (nested defs excluded).
- Dedupe on (name, source) pairs.
- Retrieval by entity / intent substring.
- Tempdir isolation via FLEXTOOLSMCP_SKELETON_DIR env var.
"""

import json
import os
import time
from pathlib import Path
import pytest

from server import skeleton_storage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_skeleton_dir(tmp_path, monkeypatch):
    """Point the storage module at a fresh tempdir for the test.

    Each test gets its own clean directory; the env var override is what
    the module honors at runtime, so we set FLEXTOOLSMCP_SKELETON_DIR.
    """
    monkeypatch.setenv("FLEXTOOLSMCP_SKELETON_DIR", str(tmp_path))
    # Sanity-check the module picks it up.
    assert skeleton_storage.get_skeleton_dir() == Path(str(tmp_path))
    yield tmp_path


# ---------------------------------------------------------------------------
# Capture: AST extraction
# ---------------------------------------------------------------------------


class TestCapture:
    """capture_from_code should only persist top-level defs."""

    def test_top_level_defs_captured_nested_excluded(self, isolated_skeleton_dir):
        """Two top-level defs + one nested def -> 2 captured entries."""
        code = (
            "def pos_abbr(pos):\n"
            "    return pos.Abbreviation.BestAnalysisAlternative.Text\n"
            "\n"
            "def get_words(text):\n"
            "    def helper(seg):\n"
            "        return seg.Analyses\n"
            "    return [helper(s) for s in text.Segments]\n"
        )

        captured = skeleton_storage.capture_from_code(
            code,
            entities_used=["ILexSense"],
            user_intent="list pos abbreviations",
            op_id="op-123",
            session_id="20260529-120000",
            duration_ms=42,
        )

        assert len(captured) == 2
        names = {e["name"] for e in captured}
        assert names == {"pos_abbr", "get_words"}
        # The nested helper must NOT appear.
        assert "helper" not in names

        # Verify file on disk has same content.
        path = skeleton_storage.get_skeleton_path()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        on_disk_names = {json.loads(line)["name"] for line in lines}
        assert on_disk_names == {"pos_abbr", "get_words"}

    def test_capture_records_metadata(self, isolated_skeleton_dir):
        """Captured entries should carry the metadata fields verbatim."""
        code = "def only_one():\n    return 1\n"
        captured = skeleton_storage.capture_from_code(
            code,
            entities_used=["ISegment", "ILexSense"],
            user_intent="count senses",
            op_id="op-abc",
            session_id="20260529-130000",
            duration_ms=99,
        )
        assert len(captured) == 1
        entry = captured[0]
        assert entry["name"] == "only_one"
        assert entry["entities"] == ["ISegment", "ILexSense"]
        assert entry["user_intent"] == "count senses"
        assert entry["op_id"] == "op-abc"
        assert entry["session_id"] == "20260529-130000"
        assert entry["duration_ms"] == 99
        assert entry["captured_at"]  # Non-empty timestamp.
        # Source is dedented + has a def line.
        assert entry["source"].startswith("def only_one()")

    def test_capture_of_empty_code_returns_empty(self, isolated_skeleton_dir):
        """No top-level defs -> no captures, no exceptions."""
        # Bare snippet without any defs.
        result = skeleton_storage.capture_from_code(
            "for x in project.LexEntry.GetAll():\n    pass\n",
            entities_used=["LexEntryOperations"],
            user_intent=None,
            op_id="op-x",
            session_id="20260529-140000",
            duration_ms=10,
        )
        assert result == []
        # No file should have been created with content.
        path = skeleton_storage.get_skeleton_path()
        if path.exists():
            assert path.read_text(encoding="utf-8").strip() == ""

    def test_capture_swallows_syntax_errors(self, isolated_skeleton_dir):
        """Capture must never raise when given invalid Python."""
        result = skeleton_storage.capture_from_code(
            "def broken(:\n    pass",
            entities_used=[],
            user_intent=None,
            op_id="op-bad",
            session_id="s",
            duration_ms=0,
        )
        assert result == []


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------


class TestDedupe:
    """Repeated capture of the same (name, source) should be a no-op."""

    def test_dedupe_same_code_twice(self, isolated_skeleton_dir):
        code = "def pos_abbr(pos):\n    return pos.Abbreviation\n"

        first = skeleton_storage.capture_from_code(
            code,
            entities_used=["IPartOfSpeech"],
            user_intent="abbr",
            op_id="op-1",
            session_id="s",
            duration_ms=5,
        )
        assert len(first) == 1

        second = skeleton_storage.capture_from_code(
            code,
            entities_used=["IPartOfSpeech"],
            user_intent="abbr again",
            op_id="op-2",
            session_id="s",
            duration_ms=5,
        )
        # Same source -> no new capture even though metadata differs.
        assert second == []

        # On disk: still exactly one line.
        path = skeleton_storage.get_skeleton_path()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


class TestRetrieval:
    """find_skeletons should filter and order correctly."""

    def _seed_three_for_lexsense_and_two_for_isegment(self, _isolated_dir):
        """Seed five distinct entries with controlled captured_at ordering."""
        # We need distinguishable timestamps, so we capture sequentially with
        # small sleeps. Sleeps are tiny -- ISO-8601 second precision means
        # the sort is by timestamp, then by file order for ties (which is
        # also insertion order, so most-recent-first still holds).
        seeds = [
            ("def s1(): return 1\n", ["ILexSense"], "list senses"),
            ("def s2(): return 2\n", ["ILexSense"], "count senses"),
            ("def s3(): return 3\n", ["ILexSense"], "iterate senses"),
            ("def t1(): return 4\n", ["ISegment"], "interlinear seg"),
            ("def t2(): return 5\n", ["ISegment"], "list affixes in Fau"),
        ]
        for i, (code, ents, intent) in enumerate(seeds):
            skeleton_storage.capture_from_code(
                code,
                entities_used=ents,
                user_intent=intent,
                op_id=f"op-{i}",
                session_id="s",
                duration_ms=i,
            )
            # Small sleep so ISO timestamps differ second-by-second.
            time.sleep(1.01)

    def test_filter_by_entity(self, isolated_skeleton_dir):
        self._seed_three_for_lexsense_and_two_for_isegment(isolated_skeleton_dir)
        results = skeleton_storage.find_skeletons(
            entity_names=["ILexSense"], limit=10
        )
        assert len(results) == 3
        names = [r["name"] for r in results]
        # Most-recent-first: s3 was the last ILexSense capture.
        assert names == ["s3", "s2", "s1"]
        # None of the ISegment ones leaked in.
        for r in results:
            assert "ILexSense" in r["entities"]

    def test_filter_by_intent_substring(self, isolated_skeleton_dir):
        self._seed_three_for_lexsense_and_two_for_isegment(isolated_skeleton_dir)
        results = skeleton_storage.find_skeletons(
            intent_substring="affix", limit=10
        )
        # Only t2 had "affix" in its user_intent.
        assert len(results) == 1
        assert results[0]["name"] == "t2"

    def test_intent_substring_case_insensitive(self, isolated_skeleton_dir):
        self._seed_three_for_lexsense_and_two_for_isegment(isolated_skeleton_dir)
        results = skeleton_storage.find_skeletons(
            intent_substring="SENSES", limit=10
        )
        assert len(results) == 3
        # All three have "senses" in their intent (cases differ).

    def test_limit_caps_results(self, isolated_skeleton_dir):
        self._seed_three_for_lexsense_and_two_for_isegment(isolated_skeleton_dir)
        results = skeleton_storage.find_skeletons(
            entity_names=["ILexSense"], limit=2
        )
        assert len(results) == 2
        # Most-recent-first still holds: s3 then s2.
        assert [r["name"] for r in results] == ["s3", "s2"]

    def test_list_all_skeletons(self, isolated_skeleton_dir):
        self._seed_three_for_lexsense_and_two_for_isegment(isolated_skeleton_dir)
        results = skeleton_storage.list_all_skeletons(limit=100)
        assert len(results) == 5
        # Most-recent-first across all entries.
        assert results[0]["name"] == "t2"
        assert results[-1]["name"] == "s1"


# ---------------------------------------------------------------------------
# Tempdir isolation contract
# ---------------------------------------------------------------------------


class TestListSkeletonsTool:
    """End-to-end: the flextools_list_skeletons MCP tool reads from the closet."""

    def test_list_skeletons_tool_returns_captured_entries(
        self, isolated_skeleton_dir
    ):
        """Seed one entry, then invoke the tool and verify it shows up."""
        import asyncio
        from server.models import ListSkeletonsInput
        from server.handlers.catalog import handle_list_skeletons

        skeleton_storage.capture_from_code(
            "def hello():\n    return 1\n",
            entities_used=["ILexSense"],
            user_intent="greet",
            op_id="op-test",
            session_id="s",
            duration_ms=5,
        )

        result = asyncio.new_event_loop().run_until_complete(
            handle_list_skeletons(ListSkeletonsInput(limit=10))
        )
        text = result[0].text
        payload = json.loads(text)

        assert payload["count"] == 1
        assert payload["limit"] == 10
        assert payload["skeletons"][0]["name"] == "hello"
        assert "storage_path" in payload


class TestTempdirIsolation:
    """The env var override is the contract the runtime relies on."""

    def test_env_var_overrides_default_dir(self, tmp_path, monkeypatch):
        """Setting the env var should redirect writes."""
        target = tmp_path / "custom_skeletons"
        monkeypatch.setenv("FLEXTOOLSMCP_SKELETON_DIR", str(target))

        skeleton_storage.capture_from_code(
            "def foo(): return 1\n",
            entities_used=[],
            user_intent=None,
            op_id="op-1",
            session_id="s",
            duration_ms=0,
        )

        # The file lives under the override dir, not the default location.
        assert (target / "skeletons.jsonl").exists()

    def test_no_env_var_uses_project_default(self, monkeypatch):
        """Without override, the directory falls back to <root>/.flextoolsmcp."""
        monkeypatch.delenv("FLEXTOOLSMCP_SKELETON_DIR", raising=False)
        default = skeleton_storage.get_skeleton_dir()
        # Default should be under a .flextoolsmcp folder (project-local).
        assert default.name == ".flextoolsmcp"
