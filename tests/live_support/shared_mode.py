#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared-mode scratch copies (parser-check CP4 live support).

`make_shared(copy)` turns on FieldWorks project sharing for a `CP4-Scratch-`
copy by setting `projectSharing="true"` in `SharedSettings/LexiconSettings.plsx`
-- the attribute FieldWorks' Sharing tab writes, and the one
`project_access.is_project_sharing_enabled` reads. Refuses any other name.

    python tests/live_support/shared_mode.py CP4-Scratch-<...>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))

from make_disposable import projects_dir, require_disposable  # noqa: E402


def make_shared(name: str, *, root: Path | None = None) -> Path:
    require_disposable(name)
    plsx = projects_dir(root) / name / "SharedSettings" / "LexiconSettings.plsx"
    text = plsx.read_text(encoding="utf-8")
    if 'projectSharing="' in text:
        text = re.sub(r'projectSharing="[^"]*"', 'projectSharing="true"', text, count=1)
    else:
        text = text.replace("<ProjectLexiconSettings", '<ProjectLexiconSettings projectSharing="true"', 1)
    plsx.write_text(text, encoding="utf-8")
    return plsx


if __name__ == "__main__":
    print(make_shared(sys.argv[1]))
