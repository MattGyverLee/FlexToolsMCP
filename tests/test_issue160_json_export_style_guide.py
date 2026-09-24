#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #160: style guide documents JSON-unsafe flexicon return types."""

from pathlib import Path


def test_style_guide_covers_json_unsafe_lcm_returns():
    guide = (Path(__file__).resolve().parents[1] / "docs" / "FLEXTOOLS-STYLE-GUIDE.md").read_text(
        encoding="utf-8"
    )
    assert "find_writing_system" in guide
    assert "GetMorphType" in guide
    assert "JSON" in guide or "json" in guide
    assert "CoreWritingSystemDefinition" in guide
    assert "IMoMorphType" in guide
