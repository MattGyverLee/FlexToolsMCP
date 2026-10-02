#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #317 -- read-only audit recipes must report findings via
report.Warning, not report.Error.

A run's ``success`` flag is derived from what the script reported (CP1,
issue #92): any ``report.Error()`` demotes the envelope to
``success: false`` with ``error_type: "ReportedError"`` ("Operation
reported N error(s) via report.Error(); see messages for details.").
Weaker models read ``success: false`` as "my call broke", even when the
audit ran exactly as intended. Audit findings are not run failures:
they ride as warnings and the run stays ``success: true``. The
convention is documented in docs/TOOL-CONTRACT.md ("report.Error =>
success: false, and the audit-findings convention").

Covers:
  - morpheme-character-check.py: the recipe source uses report.Warning
    for its findings and contains no report.Error call.
  - Behaviour: executing the recipe against stub project data with
    disallowed characters yields warnings and zero errors, so the
    envelope rule computes success: true.
  - Envelope rule, exercised through the real generated runner against
    the fake flexicon package (no FieldWorks): warnings alone keep
    success: true; any report.Error flips success: false.
"""

from pathlib import Path
from types import SimpleNamespace

from test_issue96_teardown_visibility import (  # noqa: E402
    _capture_generated_script,
    _run_script,
    _write_fake_flexicon,
)

RECIPE_PATH = (
    Path(__file__).parent.parent
    / "src"
    / "flextoolsmcp"
    / "recipe_library"
    / "morpheme-character-check.py"
)


def _run(monkeypatch, tmp_path, code):
    """Run the real generated runner for `code` against fake flexicon."""
    script = _capture_generated_script(monkeypatch, tmp_path, code=code)
    script_path = tmp_path / "runner.py"
    script_path.write_text(script, encoding="utf-8")
    _write_fake_flexicon(tmp_path / "fake_pkgs", with_headless_ui=True)
    return _run_script(script_path, tmp_path / "fake_pkgs")


# ---------------------------------------------------------------------------
# Tier 1: the recipe source reports audit findings as warnings.
# ---------------------------------------------------------------------------


class TestRecipeSource:
    def test_no_report_error_in_recipe(self):
        source = RECIPE_PATH.read_text(encoding="utf-8")
        assert "report.Error" not in source, (
            "morpheme-character-check is a read-only audit; data findings "
            "must use report.Warning so the run stays success:true (#317)"
        )

    def test_findings_reported_as_warnings(self):
        source = RECIPE_PATH.read_text(encoding="utf-8")
        # Two finding sites: disallowed chars in headword, and in affix gloss.
        assert source.count("report.Warning(") >= 2


# ---------------------------------------------------------------------------
# Tier 2: executing the recipe against stub data yields warnings, not errors.
# ---------------------------------------------------------------------------


class _StubReport:
    def __init__(self):
        self.messages = []  # (level, message) tuples

    def Info(self, msg, ref=None):
        self.messages.append(("INFO", msg))

    def Warning(self, msg, ref=None):
        self.messages.append(("WARNING", msg))

    def Error(self, msg, ref=None):
        self.messages.append(("ERROR", msg))


def _stub_project():
    """Minimal project stub shaped like the recipe's call sites."""
    entries = [
        SimpleNamespace(headword="bad word", glosses=["okgloss"]),  # space in headword
        SimpleNamespace(
            headword="fine", glosses=["bad<gloss"]
        ),  # angle bracket in gloss
        SimpleNamespace(headword="fine", glosses=["ok"]),  # clean control
    ]
    return SimpleNamespace(
        LexEntry=SimpleNamespace(
            GetAll=lambda: entries,
            GetHeadword=lambda e: e.headword,
            GetSenses=lambda e: e.glosses,
        ),
        Senses=SimpleNamespace(GetGloss=lambda s: s),
        BuildGotoURL=lambda e: "goto://entry",
    )


class TestRecipeExecution:
    def test_findings_are_warnings_and_success_holds(self):
        source = RECIPE_PATH.read_text(encoding="utf-8")
        report = _StubReport()
        namespace = {"project": _stub_project(), "report": report}
        exec(compile(source, str(RECIPE_PATH), "exec"), namespace)

        levels = [lvl for lvl, _ in report.messages]
        assert "ERROR" not in levels, [m for m in report.messages]

        warnings = [msg for lvl, msg in report.messages if lvl == "WARNING"]
        assert len(warnings) == 2, [m for m in report.messages]
        assert any('Headword "bad word"' in m for m in warnings), warnings
        assert any('Affix gloss "bad<gloss"' in m for m in warnings), warnings

        # The envelope rule (issue #92 / #317): error_count > 0 flips
        # success to false; warnings never do.
        error_count = sum(1 for lvl in levels if lvl == "ERROR")
        assert error_count == 0
        success = not (error_count > 0)
        assert success is True


# ---------------------------------------------------------------------------
# Tier 3: the envelope rule itself, via the real generated runner.
# ---------------------------------------------------------------------------


class TestEnvelopeSemantics:
    def test_warnings_alone_keep_success_true(self, monkeypatch, tmp_path):
        payload = _run(
            monkeypatch,
            tmp_path,
            "report.Info('audit complete')\n"
            "report.Warning('Headword \"bad word\" contains disallowed characters:  ')\n"
            "report.Warning('Affix gloss \"bad<gloss\" in sense contains disallowed characters: <')\n",
        )
        assert payload["success"] is True
        assert payload["summary"]["error_count"] == 0
        # Lower bound: the runner may add its own setup warning (see #347),
        # so count the script's warnings as a minimum.
        assert payload["summary"]["warning_count"] >= 2
        texts = [m.get("message") or str(m) for m in payload["messages"]]
        assert any("bad word" in t for t in texts), texts
        assert any("bad<gloss" in t for t in texts), texts

    def test_report_error_demotes_success(self, monkeypatch, tmp_path):
        """Pins the documented contract: report.Error => success:false."""
        payload = _run(
            monkeypatch,
            tmp_path,
            "report.Info('audit complete')\n"
            "report.Error('Headword \"bad word\" contains disallowed characters:  ')\n",
        )
        assert payload["success"] is False
        assert payload.get("error_type") == "ReportedError"
        assert "report.Error()" in payload.get("error", "")
        assert payload["summary"]["error_count"] == 1
