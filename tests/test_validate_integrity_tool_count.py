"""P2: validate_integrity degraded tool count must match ToolDef registry (32 tools).

When the runtime list_tools() probe fails (common on source checkouts without
an editable install), scripts/validate_integrity.py falls back to AST counting.
That fallback must not treat server.py's dynamic ``Tool(**kwargs)`` loop as an
extra tool registration (which inflated the count to 33 vs 32 ToolDefs).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = REPO_ROOT / "scripts" / "validate_integrity.py"


def _load_validate_integrity():
    spec = importlib.util.spec_from_file_location("validate_integrity", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_ast_tool_count_matches_tooldef_registry():
    vi = _load_validate_integrity()
    names = vi._tool_names_from_definitions()
    assert len(names) == 32
    assert vi._count_tools_from_ast() is True
