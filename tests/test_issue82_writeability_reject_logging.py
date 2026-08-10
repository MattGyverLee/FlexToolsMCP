#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #82: an unprotected mutating script must return the
`unprotected_mutations_detected` guidance, not `'str' object has no attribute
'get'`.

The writeability gate itself always worked -- it detected the mutation and
decided to reject. The crash was in the per-issue DEBUG block that *describes*
the rejection: it iterated `cert["raw_lcm_patterns"]` calling `p.get("line")`,
but that list holds plain formatted strings from
`detect_cud_operations()["operations"]`, not the `{"line","method","context"}`
dicts its sibling list `unprotected_liblcm_calls` holds. The AttributeError
escaped the handler and replaced the guidance -- the one message that tells the
caller how to fix the script -- with an error pointing nowhere.

Covers:
- SHAPE CONTRACT: `raw_lcm_patterns` elements are strings (the assumption the
  log line is written against). If this ever becomes dicts, the log line must
  change with it.
- The repro script from the issue logs cleanly and still yields
  `unprotected_mutations_detected`.
- The `raw_lcm` DEBUG line is actually emitted (the reject's diagnostics are
  not silently lost, which is what the try/except must not paper over).
- STRUCTURAL: the diagnostic block can never take down the response --
  arbitrary element shapes, and a None logger (`get_operations_logger()` is
  Optional and returns None pre-init), both degrade the log instead.
- The handler's reject path routes through the helper and still returns the
  guidance payload.

Run with:
    python -m pytest tests/test_issue82_writeability_reject_logging.py -q -m "not requires_flex"
"""

import ast
import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from flextoolsmcp.server.handlers import execution as exec_mod
from flextoolsmcp.server.handlers.execution import _log_writeability_reject
from flextoolsmcp.server.validators import (
    certify_script_readonly,
    detect_cud_operations,
    get_unprotected_write_guidance,
)


# The minimal reproduction from the issue.
REPRO_CODE = (
    "from flexicon import LexEntryOperations\n"
    "ops = LexEntryOperations(project)\n"
    'e = ops.Create("zzz", create_blank_sense=True)\n'
    'report.Info("created entry: %s" % e.Guid)\n'
)


class _FakeIndex:
    """Minimal stand-in for APIIndex.

    Needed because `raw_lcm_patterns` is deliberately NOT a gate (it is
    line-blind), so with no index at all the repro certifies as read-only and
    never reaches the reject path. The index entry is what makes
    `LexEntryOperations.Create` a *gating* mutation -- which is precisely the
    combination that crashed: a mutating call from the index AND a raw_lcm
    string pattern in the same cert.
    """

    def __init__(self):
        self.flexicon = {
            "entities": {
                "LexEntryOperations": {
                    "category": "lexicon",
                    "methods": [
                        {"name": "Create", "signature": "(self, form)",
                         "is_mutating": True},
                        {"name": "GetAll", "signature": "(self)",
                         "is_mutating": False},
                    ],
                    "properties": [],
                }
            }
        }


def _cert(code=REPRO_CODE, index=None):
    return certify_script_readonly(code, index or _FakeIndex(), None)


def _mutating(cert):
    return [m for m in cert.get("mutating_calls", []) if m.get("is_mutating")]


# ---------------------------------------------------------------------------
# Shape contract
# ---------------------------------------------------------------------------

class TestRawLcmPatternsShape:
    """`raw_lcm_patterns` is a list of strings, NOT dicts.

    This is the assumption the DEBUG log line is written against. It is a real
    contract, not an accident: `validators.py` extends the list from
    `detect_cud_operations()["operations"]`, and three other consumers
    (`detected_operations`, `operations_that_will_execute`, `recipe_validator`)
    all treat the elements as strings.
    """

    def test_cud_operations_are_strings(self):
        ops = detect_cud_operations(REPRO_CODE)["operations"]
        assert ops, "repro script must register at least one CUD operation"
        assert all(isinstance(o, str) for o in ops), (
            f"expected plain strings, got {[type(o).__name__ for o in ops]}"
        )

    def test_raw_lcm_patterns_are_strings(self):
        raw = _cert()["raw_lcm_patterns"]
        assert raw, "repro script must populate raw_lcm_patterns"
        assert all(isinstance(p, str) for p in raw), (
            "raw_lcm_patterns changed shape -- the raw_lcm DEBUG line in "
            "_log_writeability_reject must be updated to match"
        )

    def test_sibling_list_really_does_hold_dicts(self):
        """Guards the *reason* for the copy-paste: the sibling list genuinely
        uses line/method/context dicts, so the two loops must stay different."""
        code = (
            "def Main(project, report, modify):\n"
            "    e = project.LexiconAllEntries()[0]\n"
            "    e.CitationForm.set_String(1, 'x')\n"
        )
        calls = certify_script_readonly(code, _FakeIndex(), None).get(
            "unprotected_liblcm_calls"
        ) or []
        if not calls:
            pytest.skip("no unprotected_liblcm_calls detected for this sample")
        assert all(isinstance(c, dict) for c in calls)
        assert {"method", "line", "context"} <= set(calls[0])


# ---------------------------------------------------------------------------
# The actual bug: reject must produce guidance, not AttributeError
# ---------------------------------------------------------------------------

class TestRejectLoggingDoesNotCrash:
    def test_repro_script_is_not_certified_readonly(self):
        """Precondition: the gate does fire on the repro (it always did)."""
        assert _cert()["is_certified_readonly"] is False

    def test_guidance_is_unprotected_mutations_detected(self):
        guidance = get_unprotected_write_guidance(_cert())
        assert guidance.get("error") == "unprotected_mutations_detected"

    def test_logging_the_reject_does_not_raise(self, caplog):
        """The regression itself: this raised AttributeError on the first
        raw_lcm element and took the response down with it."""
        cert = _cert()
        logger = logging.getLogger("test_issue82.ops")
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            with patch.object(
                exec_mod, "get_operations_logger", return_value=logger
            ):
                _log_writeability_reject(cert, _mutating(cert))

    def test_raw_lcm_debug_line_is_emitted(self, caplog):
        """The try/except must not become a way to lose the diagnostics --
        the raw_lcm pattern is actually written to the log."""
        cert = _cert()
        logger = logging.getLogger("test_issue82.ops")
        with caplog.at_level(logging.DEBUG, logger=logger.name):
            with patch.object(
                exec_mod, "get_operations_logger", return_value=logger
            ):
                _log_writeability_reject(cert, _mutating(cert))
        text = caplog.text
        assert "Preflight writeability:" in text
        assert "(rejected)" in text
        assert "raw_lcm_pattern=" in text
        assert "CREATE (Create())" in text
        # The failure sentinel must NOT be present on a healthy path.
        assert "per-issue logging failed" not in text


# ---------------------------------------------------------------------------
# Structural: diagnostics can never take down the response
# ---------------------------------------------------------------------------

class TestDiagnosticBlockIsNonFatal:
    """Issue #82's structural ask: a shape drift must degrade the log, never
    the tool result. Each case below is a shape the block does not expect."""

    @pytest.mark.parametrize(
        "cert",
        [
            # raw_lcm carrying dicts instead of strings (the inverse drift)
            {"raw_lcm_patterns": [{"line": 3, "call": "Create", "kind": "raw_lcm"}]},
            # raw_lcm carrying None / ints
            {"raw_lcm_patterns": [None, 7]},
            # sibling list carrying strings instead of dicts
            {"unprotected_liblcm_calls": ["set_String at line 3"]},
            # both lists wrong type entirely
            {"raw_lcm_patterns": "CREATE", "unprotected_liblcm_calls": 5},
            # empty / missing
            {},
        ],
        ids=["raw_dicts", "raw_none_int", "sibling_strings", "not_lists", "empty"],
    )
    def test_odd_shapes_do_not_raise(self, cert):
        logger = logging.getLogger("test_issue82.ops")
        with patch.object(exec_mod, "get_operations_logger", return_value=logger):
            _log_writeability_reject(cert, [])

    def test_bad_mutating_shape_does_not_raise(self):
        logger = logging.getLogger("test_issue82.ops")
        with patch.object(exec_mod, "get_operations_logger", return_value=logger):
            _log_writeability_reject({}, ["not-a-dict"])

    def test_none_logger_does_not_raise(self):
        """`get_operations_logger()` is Optional and returns None before kernel
        init -- a second latent path to the same opaque-AttributeError symptom."""
        cert = _cert()
        with patch.object(exec_mod, "get_operations_logger", return_value=None):
            _log_writeability_reject(cert, _mutating(cert))

    def test_exploding_logger_does_not_raise(self):
        """Even a logger that throws must not escape the diagnostic block."""
        class _Boom:
            def info(self, *a, **k):
                raise RuntimeError("log backend down")

            def debug(self, *a, **k):
                raise RuntimeError("log backend down")

        cert = _cert()
        with patch.object(exec_mod, "get_operations_logger", return_value=_Boom()):
            with pytest.raises(RuntimeError):
                # Sanity: the fake really does throw...
                _Boom().info("x")
            # ...and the block still swallows it.
            _log_writeability_reject(cert, _mutating(cert))


# ---------------------------------------------------------------------------
# Handler wiring
# ---------------------------------------------------------------------------

class TestHandlerWiring:
    """The reject path must route its diagnostics through the guarded helper
    rather than inlining `.get(...)` loops again."""

    def _reject_block(self):
        src = (
            Path(__file__).parent.parent
            / "src" / "flextoolsmcp" / "server" / "handlers" / "execution.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next(
            n for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "handle_run_module"
        )
        body = "\n".join(src.splitlines()[fn.lineno - 1:fn.end_lineno])
        start = body.find("if not cert[\"is_certified_readonly\"]:")
        assert start != -1, "writeability reject branch not found in handler"
        end = body.find("detect_casting_needs", start)
        assert end != -1
        return body[start:end]

    def test_reject_calls_the_guarded_helper(self):
        assert "_log_writeability_reject(" in self._reject_block()

    def test_reject_does_not_inline_raw_lcm_dict_access(self):
        """The exact regression shape: no un-guarded per-issue loop in the
        handler body. Diagnostics live in the helper, behind its try/except."""
        block = self._reject_block()
        assert "raw_lcm_patterns" not in block, (
            "raw_lcm_patterns is read directly in the handler again -- move the "
            "diagnostics into _log_writeability_reject so a shape drift cannot "
            "take down the guidance response (issue #82)"
        )

    def test_reject_still_returns_the_guidance_payload(self):
        block = self._reject_block()
        assert "get_unprotected_write_guidance(cert)" in block
        assert "json.dumps(guidance" in block
        assert 'error_code="unprotected_writes"' in block
