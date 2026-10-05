#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The docs must not promise an undo the system does not have
(specs/_archive/exclusive-access-gate FR-020..FR-026).

There is no MCP undo: LCM's undo stack lives in memory and every run_module
is a fresh process, and FLEx records peer writes as non-undoable (research
R4). The old `flextools_undo_last_operation` tool was removed (#92), so a doc
may name it only to say so.

Also pins docs/SHARED-MODE.md to the exclusive-access gate as shipped: the
refusal code, the recovery facts, and one "Close FLEx for these" row per
category in EXCLUSIVE_ONLY_OPERATIONS.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")

from flextoolsmcp.server.exclusive_access import (  # noqa: E402
    CATEGORY_LABELS,
    EXCLUSIVE_ONLY_OPERATIONS,
)

REPO = Path(__file__).resolve().parent.parent
SHARED_MODE = REPO / "docs" / "SHARED-MODE.md"


def _checked_files():
    files = [
        p for p in sorted((REPO / "docs").rglob("*.md"))
        # Archived plans are history, not guidance.
        if "archive" not in p.relative_to(REPO / "docs").parts
    ]
    files += [
        REPO / "USAGE.md",
        REPO / "README.md",
        REPO / "src" / "flextoolsmcp" / "server" / "tool_definitions.py",
    ]
    return [p for p in files if p.exists()]


CHECKED = _checked_files()


def _ids(paths):
    return [str(p.relative_to(REPO)) for p in paths]


@pytest.mark.parametrize("path", CHECKED, ids=_ids(CHECKED))
def test_a_undo_tool_named_only_as_removed(path):
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "undo_last_operation" in line:
            assert "removed" in line.lower(), (
                f"{path.name}:{lineno} names undo_last_operation without saying "
                f"it was removed: {line.strip()}"
            )


@pytest.mark.parametrize("path", CHECKED, ids=_ids(CHECKED))
def test_b_no_reverse_a_write_claim(path):
    assert "can reverse a write" not in path.read_text(encoding="utf-8").lower()


@pytest.mark.parametrize(
    "phrase",
    [
        "requires_exclusive_access",
        "navigate away",
        "F5",
        "non-undoable",
        "empty undo history",
    ],
)
def test_c_shared_mode_states_the_facts(phrase):
    assert phrase.lower() in SHARED_MODE.read_text(encoding="utf-8").lower()


def _close_flex_table():
    text = SHARED_MODE.read_text(encoding="utf-8")
    section = re.search(r"## Close FLEx for these\n(.*?)\n## ", text, re.S)
    assert section, "SHARED-MODE.md has no 'Close FLEx for these' section"
    return [ln for ln in section.group(1).splitlines() if ln.startswith("| **")]


def test_d_every_category_has_a_row():
    rows = _close_flex_table()
    categories = {op.category for op in EXCLUSIVE_ONLY_OPERATIONS}
    assert categories == set(CATEGORY_LABELS)
    for category in categories:
        label = CATEGORY_LABELS[category]
        assert any(row.startswith(f"| **{label}**") for row in rows), category


def test_d_every_wrapper_method_is_named_in_its_row():
    rows = _close_flex_table()
    for op in EXCLUSIVE_ONLY_OPERATIONS:
        if op.wrapper is None:
            continue
        label = CATEGORY_LABELS[op.category]
        row = next(r for r in rows if r.startswith(f"| **{label}**"))
        for method in op.wrapper[1]:
            assert method in row, (op.key, method)
