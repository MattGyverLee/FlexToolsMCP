#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SC-008 / FR-004: nothing in the shipped build can bypass confirmation for
filing. A wrong-implementation TRIPWIRE, written before the filing handler
existed (tasks.md T014).

Three surfaces are enumerated rather than spot-checked, because a bypass is
something someone adds later "just for testing":

  * the `flextools_parse_text` input schema -- every property name;
  * every configuration key the server defines (`config.py`'s `*_KEY`);
  * every environment variable the server reads (`os.environ` / `getenv`
    literals and `_ENV*` constants under `src/`).

Any name matching `write|backup|force|override|skip|bypass|unattended|
auto_confirm` fails the test, apart from the three filing arguments and the
PRE-EXISTING names listed in `_PRE_CP4_ALLOWED` below, each with the reason
it cannot lower the confirmation rung for filing. FR-004's scope is "anything
introduced by this feature": a pre-existing key is allowed only when this
file says why it is harmless, and the one that COULD be harmful --
`require_write_confirmation` -- is exercised end to end below.

THE CRUCIAL ASSERTION: with `require_write_confirmation=false` set through
`flextools_manage_config`, a filing request still returns
`confirmation_required` (R-08). Honouring that key for filing would ship a
bypass on day one; the naive implementation -- reuse `run_module`'s
confirmation check verbatim -- does exactly that, and fails here.
"""

import ast
import asyncio
import re
from pathlib import Path

import filing_fakes
from flextoolsmcp.server.models import ParseTextInput

#: The shared offline fixture (tests/filing_fakes.py).
filing_env = filing_fakes.filing_env

SRC = Path(__file__).parent.parent / "src" / "flextoolsmcp"

BYPASS_SHAPED = re.compile(r"write|backup|force|override|skip|bypass|unattended|auto_confirm", re.I)

#: The filing arguments themselves (contracts/tools.md section 1).
_FILING_ARGUMENTS = {"apply", "confirmed", "plan_id"}

#: Names that existed before CP4 and match the pattern, with why each one
#: cannot skip or pre-answer filing's confirmation.
_PRE_CP4_ALLOWED = {
    # Lowers run_module's confirmation rung. Filing READS it only to disclose
    # it in the plan; it never lowers filing's rung (R-08) -- asserted below.
    "require_write_confirmation": "disclosed, never honoured for filing",
    # Opts out of the pre-write BACKUP, not the confirmation. Honoured for
    # filing, and disclosed in the plan before the human confirms, with the
    # no-recovery warning on the result (FR-007, US2 AS-3).
    "backup_before_write": "backup opt-out, disclosed before confirmation",
    # How many backups to keep. Touches no rung.
    "backup_retention": "retention count, touches no rung",
}


def _config_keys() -> set:
    tree = ast.parse((SRC / "config.py").read_text(encoding="utf-8"))
    keys = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith("_KEY"):
                    keys.add(str(node.value.value))
    return keys


_ENV_LITERAL = re.compile(
    r"""(?:environ\.get|getenv|environ\[)\(?\s*["']([A-Z][A-Z0-9_]+)["']"""
    r"""|_ENV[A-Z_]*\s*=\s*["']([A-Z][A-Z0-9_]+)["']"""
)


def _environment_variables() -> set:
    names = set()
    for path in SRC.rglob("*.py"):
        for match in _ENV_LITERAL.finditer(path.read_text(encoding="utf-8", errors="replace")):
            names.add(match.group(1) or match.group(2))
    return names


def _offenders(names) -> list:
    return sorted(
        n for n in names
        if BYPASS_SHAPED.search(n) and n not in _FILING_ARGUMENTS and n not in _PRE_CP4_ALLOWED
    )


def test_the_parse_text_schema_has_no_bypass_shaped_argument():
    properties = ParseTextInput.model_json_schema()["properties"]
    assert _offenders(properties) == []
    assert _FILING_ARGUMENTS <= set(properties)


def test_no_configuration_key_is_bypass_shaped():
    keys = _config_keys()
    assert keys, "config.py defines no *_KEY constants -- the enumeration is broken"
    assert _offenders(keys) == []


def test_no_environment_variable_is_bypass_shaped():
    names = _environment_variables()
    assert names, "no environment variables found -- the enumeration is broken"
    assert _offenders(names) == []


def test_the_allowlist_names_only_keys_that_exist():
    """A stale allowlist entry would silently widen the next key's welcome."""
    assert set(_PRE_CP4_ALLOWED) <= _config_keys()


# ---------------------------------------------------------------------------
# R-08: require_write_confirmation=false does NOT lower filing's rung
# ---------------------------------------------------------------------------


def test_require_write_confirmation_false_still_requires_confirmation_for_filing(filing_env):
    from flextoolsmcp.server.handlers.admin import handle_manage_config
    from filing_fakes import FakeReadWorker, analysis, call, filing_args

    filing_env.install(FakeReadWorker(facts={"pukul": [analysis("a1")]}))
    asyncio.run(handle_manage_config(
        {"action": "set", "key": "require_write_confirmation", "value": False}
    ))
    from flextoolsmcp.config import config_get

    assert config_get("require_write_confirmation") is False

    first = asyncio.run(call(filing_args()))
    assert first["error_code"] == "confirmation_required", first
    assert filing_env.pool.spawned == [], "the filing worker must not start for a preview"
    setting = first["plan"]["confirmation_setting"]
    assert setting == {"require_write_confirmation": False, "effective_for_filing": True}

    # And `confirmed=True` alone -- with no plan_id -- is not a way round it.
    second = asyncio.run(call(filing_args(confirmed=True)))
    assert second["error_code"] == "confirmation_required"
    assert filing_env.pool.spawned == []
