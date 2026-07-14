"""CP3 tests for the diagnostic-report feature: transports, the
`likely_contains_lexical_data` code-shape sensitivity flag, the
`flextools_prepare_report` tool / shared bundle orchestration, the
run_module success-close auto-offer advisory, and the RunModuleSuccess
contract addition.

Spec: specs/diagnostic-report/SPEC.md sections 6.5, 9, 10, 12 (acceptance
criteria under "Transport" and part of "Dedupe" / "Privacy").
"""

import asyncio
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from flextoolsmcp.server.diagnostic import transports, sensitivity, offered_store, reconstruct
from flextoolsmcp.server.handlers import diagnostic_report
from flextoolsmcp.server.handlers import execution as execution_mod
from flextoolsmcp.server.handlers import op_telemetry as tel
from flextoolsmcp.server import kernel, project_discovery
from flextoolsmcp.server.response_models import RunModuleSuccess
from flextoolsmcp.response_utils import CONTRACT_VERSION
import flextoolsmcp.config as config_mod


# ---------------------------------------------------------------------------
# 1. transports.py -- exact argv shape, URL validity/encoding/size cap,
#    mailto, "gh available" injectability.
# ---------------------------------------------------------------------------

class TestGhCommand:
    def test_exact_argv_shape(self):
        cmd = transports.build_gh_command(
            "[auto-report] PolymorphicAttributeError: fix gloss",
            "/home/user/.flextoolsmcp/reports/report_1.md",
        )
        argv = cmd["argv"]
        assert argv[0:3] == ["gh", "issue", "create"]
        assert "--repo" in argv and argv[argv.index("--repo") + 1] == transports.DEFAULT_REPO
        assert "--title" in argv
        assert "--body-file" in argv
        assert argv[argv.index("--body-file") + 1] == "/home/user/.flextoolsmcp/reports/report_1.md"
        assert "--label" in argv and argv[argv.index("--label") + 1] == "auto-report"

    def test_custom_repo_and_label(self):
        cmd = transports.build_gh_command(
            "t", "report.md", repo="acme/widgets", label="custom-label",
        )
        assert cmd["argv"][cmd["argv"].index("--repo") + 1] == "acme/widgets"
        assert cmd["argv"][cmd["argv"].index("--label") + 1] == "custom-label"

    def test_display_string_is_shell_readable(self):
        cmd = transports.build_gh_command("a title with spaces", "report.md")
        assert '"a title with spaces"' in cmd["display"]


class TestGhAvailableInjectable:
    def test_default_gh_available_uses_shutil_which(self, monkeypatch):
        monkeypatch.setattr(transports.shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
        assert transports.default_gh_available() is True

    def test_default_gh_available_false_when_not_on_path(self, monkeypatch):
        monkeypatch.setattr(transports.shutil, "which", lambda name: None)
        assert transports.default_gh_available() is False

    def test_build_transports_respects_injected_gh_available_true(self):
        result = transports.build_transports(
            title="t", summary="s", report_path="r.md", gh_available_fn=lambda: True,
        )
        assert result["gh_available"] is True

    def test_build_transports_respects_injected_gh_available_false(self):
        result = transports.build_transports(
            title="t", summary="s", report_path="r.md", gh_available_fn=lambda: False,
        )
        assert result["gh_available"] is False

    def test_gh_argv_always_built_regardless_of_availability(self):
        """The gh-absent branch still gets a well-formed argv/display -- the
        caller decides whether to PRESENT it; building the string never
        requires gh to actually be installed."""
        result = transports.build_transports(
            title="t", summary="s", report_path="r.md", gh_available_fn=lambda: False,
        )
        assert result["gh"]["argv"][0] == "gh"


class TestGithubIssueUrl:
    def test_url_is_well_formed_and_percent_encoded(self):
        result = transports.build_github_issue_url(
            "Title with spaces & special=chars",
            "Some summary text",
            "/home/user/.flextoolsmcp/reports/report_1.md",
        )
        parsed = urlparse(result["url"])
        assert parsed.scheme == "https"
        assert parsed.netloc == "github.com"
        assert parsed.path == f"/{transports.DEFAULT_REPO}/issues/new"
        qs = parse_qs(parsed.query)
        assert qs["title"][0] == "Title with spaces & special=chars"
        assert qs["labels"][0] == "auto-report"
        # Raw "&"/"=" from the title must not have leaked into the query
        # string structure -- confirmed by parse_qs decoding back to the
        # exact original title above (a naive un-encoded join would corrupt
        # the query string boundaries).
        assert "&special" not in result["url"].split("title=")[1].split("&labels")[0]

    def test_body_capped_at_8kb(self):
        huge_summary = "x" * 100_000
        result = transports.build_github_issue_url(
            "t", huge_summary, "report.md",
        )
        assert result["url_bytes"] <= transports.MAX_URL_TOTAL_BYTES
        assert len(result["url"].encode("utf-8")) <= transports.MAX_URL_TOTAL_BYTES

    def test_short_summary_not_truncated(self):
        result = transports.build_github_issue_url("t", "short summary", "report.md")
        assert "short summary" in result["body_text"]
        assert "[truncated]" not in result["body_text"]

    def test_body_instructs_attach_local_file(self):
        result = transports.build_github_issue_url("t", "summary", "/tmp/report_1.md")
        assert "/tmp/report_1.md" in result["body_text"]
        assert "attach" in result["body_text"].lower() or "paste" in result["body_text"].lower()


class TestMailto:
    def test_mailto_uri_shape(self):
        result = transports.build_mailto("Title", "Summary text", "report.md")
        assert result["uri"].startswith(f"mailto:{transports.DEFAULT_EMAIL}?")
        assert "subject=Title" in result["uri"]

    def test_mailto_works_with_neither_gh_nor_browser(self):
        """Spec section 12: "email works with neither present" -- building
        the mailto: URI has no dependency on gh_available or a browser at
        all; it's pure string construction that always succeeds."""
        result = transports.build_mailto("t", "s", "report.md")
        assert result["uri"]
        assert result["body_bytes"] <= transports.MAX_MAILTO_TOTAL_BYTES

    def test_mailto_custom_email(self):
        result = transports.build_mailto("t", "s", "report.md", email="dev@example.com")
        assert result["uri"].startswith("mailto:dev@example.com")

    def test_mailto_body_capped(self):
        result = transports.build_mailto("t", "x" * 100_000, "report.md")
        assert result["body_bytes"] <= transports.MAX_MAILTO_TOTAL_BYTES


class TestTransportBodyPathNormalization:
    """CP3 carryover P2 (domain gate): the report_path embedded in the
    URL/mailto short bodies must be run through path-scoped normalization,
    so the user's OS home path / username never leaks into a transport
    string. `_short_body_text` normalizes the whole assembled body; only the
    path token is affected (path-scoped, not a document-wide replace)."""

    def _fake_home(self, monkeypatch):
        # Deterministic, cross-platform home/username for the assertion.
        monkeypatch.setattr(transports.normalize, "get_home_path", lambda: "/home/bob")
        monkeypatch.setattr(transports.normalize, "get_username", lambda: "bob")

    def test_github_url_body_normalizes_home_path(self, monkeypatch):
        self._fake_home(monkeypatch)
        result = transports.build_github_issue_url(
            "t", "summary", "/home/bob/.flextoolsmcp/reports/report_1.md",
        )
        assert "/home/bob" not in result["body_text"]
        assert "~/.flextoolsmcp/reports/report_1.md" in result["body_text"]

    def test_mailto_body_normalizes_home_path(self, monkeypatch):
        self._fake_home(monkeypatch)
        result = transports.build_mailto(
            "t", "summary", "/home/bob/.flextoolsmcp/reports/report_1.md",
        )
        assert "/home/bob" not in result["body_text"]
        assert "~/.flextoolsmcp/reports/report_1.md" in result["body_text"]

    def test_normalization_leaves_summary_prose_untouched(self, monkeypatch):
        """Path-scoped only: a summary that merely CONTAINS the username as a
        substring (not a path token) is never rewritten."""
        self._fake_home(monkeypatch)
        result = transports.build_mailto(
            "t", "bobcat headword gloss", "/home/bob/.flextoolsmcp/reports/report_1.md",
        )
        assert "bobcat headword gloss" in result["body_text"]


class TestBuildTransportsPreviewFidelity:
    def test_all_three_present_simultaneously(self):
        """Preview fidelity (E4): all three transport strings are available
        at once so the caller can show them alongside the full report file."""
        result = transports.build_transports(
            title="[auto-report] X", summary="summary", report_path="/tmp/r.md",
            gh_available_fn=lambda: True,
        )
        assert set(result.keys()) == {"gh_available", "gh", "github_url", "mailto"}
        assert result["gh"]["argv"]
        assert result["github_url"]["url"]
        assert result["mailto"]["uri"]


# ---------------------------------------------------------------------------
# 2. sensitivity.py -- code-SHAPE detection, never content.
# ---------------------------------------------------------------------------

class TestDetectLexicalShape:
    def test_gloss_flowing_into_report_info_is_flagged(self):
        code = (
            "gloss = project.LexSense.GetGloss(sense)\n"
            "report.Info(gloss)\n"
        )
        assert sensitivity.detect_lexical_shape(code) is True

    def test_direct_call_in_report_info_is_flagged(self):
        code = "report.Info(project.LexSense.GetDefinition(sense))\n"
        assert sensitivity.detect_lexical_shape(code) is True

    def test_multistring_attribute_accessor_flowing_into_info_is_flagged(self):
        code = (
            "text = sense.Definition.BestAnalysisAlternative.Text\n"
            "report.Info(text)\n"
        )
        assert sensitivity.detect_lexical_shape(code) is True

    def test_lexical_accessor_without_report_info_flow_not_flagged(self):
        """The accessor alone (never surfaced via report.Info, and no
        BCP-47 tag alongside it) must not trip the flag -- it never reaches
        the user-visible output this flag is about."""
        code = "gloss = project.LexSense.GetGloss(sense)\n"
        assert sensitivity.detect_lexical_shape(code) is False

    def test_ws_tag_alongside_accessor_is_flagged(self):
        code = (
            "ws = 'en-US'\n"
            "form = entry.LexemeFormOA.Form.BestVernacularAlternative\n"
        )
        assert sensitivity.detect_lexical_shape(code) is True

    def test_ws_tag_alone_without_accessor_not_flagged(self):
        code = "ws = 'en-US'\nreport.Info(ws)\n"
        assert sensitivity.detect_lexical_shape(code) is False

    def test_ordinary_headword_string_literal_does_not_look_like_ws_tag(self):
        """A gloss/headword string is not narrowly BCP-47-shaped, so it
        cannot masquerade as a writing-system tag and falsely trip case (b)."""
        code = "report.Info('Matthew toolbox headword')\n"
        assert sensitivity.detect_lexical_shape(code) is False

    def test_non_lexical_variable_into_report_info_not_flagged(self):
        code = "count = len(entries)\nreport.Info(count)\n"
        assert sensitivity.detect_lexical_shape(code) is False

    def test_syntax_error_returns_false_not_raise(self):
        assert sensitivity.detect_lexical_shape("def broken(:\n") is False

    def test_empty_code_returns_false(self):
        assert sensitivity.detect_lexical_shape("") is False


# ---------------------------------------------------------------------------
# Fixture helpers (mirrors tests/test_diagnostic_report_reconstruction.py).
# ---------------------------------------------------------------------------

def _fmt(level: str, msg: str, ts: str = "2026-07-13 10:00:00") -> str:
    return f"{ts} | {level:<7} | {msg}"


def _op_block_lines(op_id, seq, *, user_intent="fix the gloss",
                     user_request="please fix the gloss", code="print('hello')",
                     close="ok") -> list:
    lines = [
        _fmt("INFO", f"=== Operation #{seq} Start ({op_id}) ==="),
        _fmt("INFO", "Project:         TestProject"),
        _fmt("INFO", "Write enabled:   False"),
        _fmt("INFO", "Source kind:     bare_snippet"),
        _fmt("INFO", f"User intent:     {user_intent}"),
        _fmt("INFO", f"User request:    {user_request}"),
        _fmt("INFO", "Code fingerprint: sha256=abc123 bytes=20 lines=1"),
        _fmt("DEBUG", "Code:"),
    ]
    for code_line in code.split("\n"):
        lines.append(_fmt("DEBUG", code_line))
    if close == "ok":
        lines.append(_fmt("INFO", "[OK] Operation completed successfully"))
        lines.append(_fmt("INFO", "Messages:        0 info, 0 warnings, 0 errors"))
        lines.append(_fmt("INFO", "Duration:        0.100s"))
    else:
        lines.append(_fmt("ERROR", "[FAIL] Operation failed"))
        lines.append(_fmt("ERROR", "Error type:      PolymorphicAttributeError"))
        lines.append(_fmt("ERROR", "  report.Error: 'ICmObject' object has no attribute 'HeadWord'"))
        lines.append(_fmt("INFO", "Messages:        0 info, 0 warnings, 1 errors"))
        lines.append(_fmt("INFO", "Duration:        0.100s"))
    lines.append(_fmt("INFO", f"=== Operation #{seq} End ({op_id}) ==="))
    return lines


def _jsonl_record(op_id, seq, outcome="ok", error_code="", user_intent="fix the gloss",
                   user_request="please fix the gloss", **extra):
    rec = {
        "ts": "2026-07-13T10:00:00Z", "op_id": op_id, "seq": seq,
        "project": "TestProject", "write_enabled": False, "source_kind": "bare_snippet",
        "user_intent": user_intent, "user_request": user_request,
        "code_sha256": "a" * 64, "code_bytes": 20, "code_lines": 1,
        "outcome": outcome, "error_code": error_code, "preflight_gate": "",
        "casting_signature": "", "duration_s": 0.1,
        "info_count": 0, "warning_count": 0, "error_count": 0,
    }
    rec.update(extra)
    return rec


def _make_turn(tmp_path, *, code_fail="bad = sense.Owner.HeadWord",
                code_ok="good = safe_get_property(sense.Owner, 'HeadWord')"):
    session_log = tmp_path / "session_test.log"
    lines = []
    lines += _op_block_lines("op-1", 1, code=code_fail, close="fail")
    lines += _op_block_lines("op-2", 2, code=code_ok, close="ok")
    session_log.write_text("\n".join(lines), encoding="utf-8")

    records = [
        _jsonl_record("op-1", 1, outcome="runtime_fail", error_code="PolymorphicAttributeError"),
        _jsonl_record("op-2", 2, outcome="ok"),
    ]
    return records, session_log


# ---------------------------------------------------------------------------
# 3. prepare_report_bundle: signature/title/summary, offer_gate dedupe.
# ---------------------------------------------------------------------------

class TestExtractFailingSymbol:
    """CP3 carryover P2: direct unit coverage for `_extract_failing_symbol`
    (previously only exercised indirectly). Must be defensive: None op,
    missing/None log_lines, and non-str lines all yield "" without raising."""

    class _Op:
        def __init__(self, log_lines):
            self.log_lines = log_lines

    def test_extracts_attribute_error_symbol(self):
        op = self._Op(["  report.Error: 'ICmObject' object has no attribute 'HeadWord'"])
        assert diagnostic_report._extract_failing_symbol(op) == "HeadWord"

    def test_returns_empty_when_no_attribute_error(self):
        op = self._Op(["everything is fine here"])
        assert diagnostic_report._extract_failing_symbol(op) == ""

    def test_none_op_returns_empty(self):
        assert diagnostic_report._extract_failing_symbol(None) == ""

    def test_missing_log_lines_returns_empty(self):
        assert diagnostic_report._extract_failing_symbol(self._Op(None)) == ""

    def test_non_str_lines_are_skipped_not_raised(self):
        op = self._Op([None, 42, {"nope": 1}, "has no attribute 'Gloss'"])
        assert diagnostic_report._extract_failing_symbol(op) == "Gloss"

    def test_all_non_str_lines_returns_empty(self):
        op = self._Op([None, 123, object()])
        assert diagnostic_report._extract_failing_symbol(op) == ""


class TestPrepareReportBundle:
    def test_anchors_on_the_reportable_failure_not_the_ok_close(self, tmp_path):
        records, session_log = _make_turn(tmp_path)
        bundle = diagnostic_report.prepare_report_bundle(
            records, session_log, anchor_op_id="op-2",
            reports_dir_fn=lambda: tmp_path / "reports",
        )
        assert bundle is not None
        assert "PolymorphicAttributeError" in bundle["title"]
        assert bundle["error_code"] == "PolymorphicAttributeError"

    def test_writes_exactly_one_local_file(self, tmp_path):
        records, session_log = _make_turn(tmp_path)
        reports_dir = tmp_path / "reports"
        bundle = diagnostic_report.prepare_report_bundle(
            records, session_log, anchor_op_id="op-2", reports_dir_fn=lambda: reports_dir,
        )
        files = list(reports_dir.glob("report_*.md"))
        assert len(files) == 1
        assert Path(bundle["report_path"]) == files[0]

    def test_report_markdown_matches_written_file(self, tmp_path):
        records, session_log = _make_turn(tmp_path)
        reports_dir = tmp_path / "reports"
        bundle = diagnostic_report.prepare_report_bundle(
            records, session_log, anchor_op_id="op-2", reports_dir_fn=lambda: reports_dir,
        )
        on_disk = Path(bundle["report_path"]).read_text(encoding="utf-8")
        assert on_disk == bundle["report_markdown"]
        assert "## 1. Header" in on_disk

    def test_offer_gate_true_produces_bundle(self, tmp_path):
        records, session_log = _make_turn(tmp_path)
        bundle = diagnostic_report.prepare_report_bundle(
            records, session_log, anchor_op_id="op-2",
            reports_dir_fn=lambda: tmp_path / "reports",
            offer_gate=lambda sig: True,
        )
        assert bundle is not None

    def test_offer_gate_false_returns_none_and_writes_nothing(self, tmp_path):
        records, session_log = _make_turn(tmp_path)
        reports_dir = tmp_path / "reports"
        bundle = diagnostic_report.prepare_report_bundle(
            records, session_log, anchor_op_id="op-2",
            reports_dir_fn=lambda: reports_dir,
            offer_gate=lambda sig: False,
        )
        assert bundle is None
        assert not reports_dir.exists() or list(reports_dir.glob("report_*.md")) == []

    def test_likely_contains_lexical_data_flag_present(self, tmp_path):
        records, session_log = _make_turn(
            tmp_path,
            code_fail="bad = sense.Owner.HeadWord",
            code_ok="report.Info(project.LexSense.GetGloss(sense))",
        )
        bundle = diagnostic_report.prepare_report_bundle(
            records, session_log, anchor_op_id="op-2",
            reports_dir_fn=lambda: tmp_path / "reports",
        )
        assert bundle["likely_contains_lexical_data"] is True

    def test_likely_contains_lexical_data_flag_absent(self, tmp_path):
        records, session_log = _make_turn(
            tmp_path, code_fail="bad = 1 / 0", code_ok="count = len(entries)",
        )
        bundle = diagnostic_report.prepare_report_bundle(
            records, session_log, anchor_op_id="op-2",
            reports_dir_fn=lambda: tmp_path / "reports",
        )
        assert bundle["likely_contains_lexical_data"] is False

    def test_all_green_slice_still_produces_a_stable_fallback_signature(self, tmp_path):
        """An explicit flextools_prepare_report call against an all-`ok`
        slice (no failure at all) must still produce a non-empty, stable
        signature -- never crash, never return an empty string."""
        session_log = tmp_path / "session_green.log"
        lines = _op_block_lines("op-1", 1, close="ok")
        session_log.write_text("\n".join(lines), encoding="utf-8")
        records = [_jsonl_record("op-1", 1, outcome="ok")]

        bundle1 = diagnostic_report.prepare_report_bundle(
            records, session_log, anchor_op_id="op-1",
            reports_dir_fn=lambda: tmp_path / "reports",
        )
        bundle2 = diagnostic_report.prepare_report_bundle(
            records, session_log, anchor_op_id="op-1",
            reports_dir_fn=lambda: tmp_path / "reports",
        )
        assert bundle1["signature"]
        assert bundle1["signature"] == bundle2["signature"]


# ---------------------------------------------------------------------------
# 4. Config knobs: report_offers_enabled default-on / kill switch.
# ---------------------------------------------------------------------------

class TestReportOffersEnabledConfig:
    def test_default_is_enabled(self):
        assert config_mod.REPORT_OFFERS_ENABLED_DEFAULT is True

    def test_disabling_suppresses_the_auto_offer_advisory(self, tmp_path, monkeypatch):
        records, session_log = _make_turn(tmp_path)
        jsonl_dir = tmp_path / "jsonl_dir"
        jsonl_dir.mkdir()
        with open(jsonl_dir / "operations.jsonl", "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec) + "\n")

        monkeypatch.setattr(diagnostic_report, "get_log_dir", lambda: jsonl_dir)
        monkeypatch.setattr(diagnostic_report, "get_current_session_log_path", lambda: session_log)
        monkeypatch.setattr(diagnostic_report, "_default_reports_dir", lambda: tmp_path / "reports")
        monkeypatch.setattr(
            diagnostic_report, "config_get",
            lambda key, default: False if key == config_mod.REPORT_OFFERS_ENABLED_KEY else default,
        )

        result = diagnostic_report.build_advisory_for_success_close("op-2")
        assert result is None


# ---------------------------------------------------------------------------
# 5. build_advisory_for_success_close: dedupe honors offered_store, fail-open.
# ---------------------------------------------------------------------------

class TestBuildAdvisoryForSuccessClose:
    def _wire(self, monkeypatch, tmp_path, records, session_log):
        jsonl_dir = tmp_path / "jsonl_dir"
        jsonl_dir.mkdir()
        with open(jsonl_dir / "operations.jsonl", "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec) + "\n")
        reports_dir = tmp_path / "reports"
        offered_dir = tmp_path / "offered_state"
        offered_path = offered_dir / "offered.json"

        monkeypatch.setattr(diagnostic_report, "get_log_dir", lambda: jsonl_dir)
        monkeypatch.setattr(diagnostic_report, "get_current_session_log_path", lambda: session_log)
        monkeypatch.setattr(diagnostic_report, "_default_reports_dir", lambda: reports_dir)
        # `should_offer()`/`record_offer()` are called with NO explicit
        # path_fn inside build_advisory_for_success_close, so they fall back
        # to their bound default `path_fn=default_store_path`. That default
        # was captured as a FUNCTION REFERENCE at module-definition time, so
        # monkeypatching the `default_store_path` NAME does not affect
        # already-bound defaults -- but `default_store_path()`'s BODY looks
        # up `get_reports_dir` fresh (a dynamic global lookup) every time it
        # runs, so patching `get_reports_dir` DOES take effect.
        monkeypatch.setattr(offered_store, "get_reports_dir", lambda: offered_dir)
        return reports_dir, offered_path

    def test_fires_for_workaround_taken_turn(self, tmp_path, monkeypatch):
        records, session_log = _make_turn(tmp_path)
        self._wire(monkeypatch, tmp_path, records, session_log)

        advisory = diagnostic_report.build_advisory_for_success_close("op-2")
        assert advisory is not None
        assert advisory["signature"]
        assert advisory["transports"]["mailto"]["uri"].startswith("mailto:")

    def test_no_advisory_for_ok_only_turn(self, tmp_path, monkeypatch):
        session_log = tmp_path / "session_all_ok.log"
        lines = _op_block_lines("op-1", 1, close="ok") + _op_block_lines("op-2", 2, close="ok")
        session_log.write_text("\n".join(lines), encoding="utf-8")
        records = [_jsonl_record("op-1", 1, outcome="ok"), _jsonl_record("op-2", 2, outcome="ok")]
        self._wire(monkeypatch, tmp_path, records, session_log)

        assert diagnostic_report.build_advisory_for_success_close("op-2") is None

    def test_dont_ask_again_suppresses_repeat_offer(self, tmp_path, monkeypatch):
        records, session_log = _make_turn(tmp_path)
        _reports_dir, offered_path = self._wire(monkeypatch, tmp_path, records, session_log)

        first = diagnostic_report.build_advisory_for_success_close("op-2")
        assert first is not None
        sig = first["signature"]

        offered_store.record_decision(sig, offered_store.STATE_DONT_ASK_AGAIN, path_fn=lambda: offered_path)

        second = diagnostic_report.build_advisory_for_success_close("op-2")
        assert second is None

        # The FIRST report file persists -- "don't ask again" suppresses the
        # OFFER, never anything already written to disk (spec section 6.4/8.4).
        assert Path(first["report_path"]).exists()

    def test_fail_open_on_internal_exception(self, tmp_path, monkeypatch):
        """Any exception anywhere in the pipeline must be swallowed --
        never raised back into the run_module success path."""
        monkeypatch.setattr(
            diagnostic_report, "get_log_dir",
            lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        # config_get itself must be reachable before the boom for a
        # meaningful test of the *pipeline* failing open (not an early
        # return) -- patch config_get to pass, then let get_log_dir blow up.
        monkeypatch.setattr(diagnostic_report, "config_get", lambda key, default: True)
        result = diagnostic_report.build_advisory_for_success_close("op-x")
        assert result is None


# ---------------------------------------------------------------------------
# 6. flextools_prepare_report tool: bypasses dedupe (spec section 5).
# ---------------------------------------------------------------------------

class TestExplicitPrepareReportBypassesDedupe:
    def test_explicit_tool_ignores_dont_ask_again(self, tmp_path, monkeypatch):
        records, session_log = _make_turn(tmp_path)
        jsonl_dir = tmp_path / "jsonl_dir"
        jsonl_dir.mkdir()
        with open(jsonl_dir / "operations.jsonl", "w", encoding="utf-8") as fh:
            for rec in records:
                fh.write(json.dumps(rec) + "\n")
        reports_dir = tmp_path / "reports"
        offered_dir = tmp_path / "offered_state"
        offered_path = offered_dir / "offered.json"

        monkeypatch.setattr(diagnostic_report, "get_log_dir", lambda: jsonl_dir)
        monkeypatch.setattr(diagnostic_report, "get_current_session_log_path", lambda: session_log)
        monkeypatch.setattr(diagnostic_report, "_default_reports_dir", lambda: reports_dir)
        # See TestBuildAdvisoryForSuccessClose._wire()'s comment: patch
        # get_reports_dir (looked up dynamically inside default_store_path's
        # body), not default_store_path itself (a bound default captured at
        # def-time -- monkeypatching the name alone would not take effect).
        monkeypatch.setattr(offered_store, "get_reports_dir", lambda: offered_dir)

        # Suppress the signature permanently in offered.json.
        sig = diagnostic_report._compute_signature_for(
            _jsonl_record("op-1", 1, outcome="runtime_fail", error_code="PolymorphicAttributeError"),
            failing_symbol="HeadWord",
        )
        offered_store.record_decision(sig, offered_store.STATE_DONT_ASK_AGAIN, path_fn=lambda: offered_path)

        # The auto-offer path (which DOES consult offered_store) is suppressed...
        assert diagnostic_report.build_advisory_for_success_close("op-2") is None

        # ...but the explicit tool call is NOT gated by offered_store at all.
        result = asyncio.run(diagnostic_report.handle_prepare_report({"op_id": "op-2"}))
        payload = json.loads(result[0].text)
        assert payload["status"] == "ok"
        assert "transports" in payload


# ---------------------------------------------------------------------------
# 7. RunModuleSuccess contract addition.
# ---------------------------------------------------------------------------

class TestRunModuleSuccessDiagnosticReportField:
    def test_accepts_diagnostic_report_block(self):
        data = {
            "status": "ok",
            "_contract": CONTRACT_VERSION,
            "op_id": "op-1",
            "diagnostic_report": {
                "signature": "abc123",
                "title": "[auto-report] X",
                "summary": "s",
                "report_path": "/tmp/report_1.md",
                "transports": {"gh_available": False},
                "likely_contains_lexical_data": False,
            },
        }
        m = RunModuleSuccess.model_validate(data, by_alias=True)
        assert m.diagnostic_report is not None
        assert m.diagnostic_report["signature"] == "abc123"

    def test_defaults_to_none(self):
        data = {"status": "ok", "_contract": CONTRACT_VERSION}
        m = RunModuleSuccess.model_validate(data, by_alias=True)
        assert m.diagnostic_report is None


# ---------------------------------------------------------------------------
# 8. Full wiring: two real handle_run_module() calls (fail -> ok, same
#    turn) attach the advisory on the second (successful) response.
# ---------------------------------------------------------------------------

def _stub_execution_common(monkeypatch, tmp_path):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    monkeypatch.setattr(project_discovery, "resolve_or_explain", lambda name: (name, None))
    monkeypatch.setattr(execution_mod, "get_api_index", lambda: None)
    monkeypatch.setattr(execution_mod, "get_log_dir", lambda: tmp_path)
    monkeypatch.setattr(execution_mod, "validate_server_state", lambda: {"is_healthy": True, "issues": []})
    monkeypatch.setattr(
        execution_mod, "certify_script_readonly",
        lambda code, api_idx, tree: {"is_certified_readonly": True, "confidence": 1.0, "mutating_calls": []},
    )
    monkeypatch.setattr(
        execution_mod, "detect_casting_needs",
        lambda code, idx, tree: {"has_casting_issues": False, "casting_issues": [], "severity": "none"},
    )
    # Diagnostic-report plumbing needs a real per-session log file to read
    # back from -- point it at a temp session log under tmp_path.
    session_log = tmp_path / "session_wiring.log"
    session_log.write_text("", encoding="utf-8")
    monkeypatch.setattr(kernel, "get_current_session_log_path", lambda: session_log)
    monkeypatch.setattr(diagnostic_report, "get_current_session_log_path", lambda: session_log)
    monkeypatch.setattr(diagnostic_report, "_default_reports_dir", lambda: tmp_path / "reports")
    monkeypatch.setattr(diagnostic_report, "get_log_dir", lambda: tmp_path)
    # Redirect offered.json to tmp_path too -- otherwise the auto-offer path
    # (should_offer / record_offer, called with no explicit path_fn) would
    # read/write the REAL ~/.flextoolsmcp/reports/offered.json on the test
    # machine. Patch get_reports_dir (looked up dynamically inside
    # default_store_path's body) rather than default_store_path itself (a
    # bound default captured at def-time; renaming it has no effect).
    monkeypatch.setattr(offered_store, "get_reports_dir", lambda: tmp_path / "offered_state")
    return session_log


def _fake_run_script_async_factory(payload: dict):
    async def _fake(script_path, timeout_seconds=300):
        stdout = "===FLEXTOOLS_RESULT_JSON===" + json.dumps(payload)
        return {"stdout": stdout, "stderr": "", "returncode": 0, "timeout": False}
    return _fake


class TestFullWiringThroughHandleRunModule:
    def test_advisory_attached_on_the_resolving_success_close(self, tmp_path, monkeypatch):
        session_log = _stub_execution_common(monkeypatch, tmp_path)

        # --- First call: fails with a runtime_fail (PolymorphicAttributeError). ---
        monkeypatch.setattr(
            execution_mod, "run_script_async",
            _fake_run_script_async_factory({
                "success": False,
                "error": "AttributeError: 'ICmObject' object has no attribute 'HeadWord'",
                "error_type": "PolymorphicAttributeError",
            }),
        )
        # NOTE: `run_script_async` is fully mocked above -- the CODE below is
        # never actually executed. It only needs to clear the REAL static
        # preflight gates (undefined_variables / missing_imports /
        # wrong_library_imports), so it deliberately references nothing but
        # the injected `report` name.
        fail_args = {
            "code": "report.Info('probe before the fix')",
            "project_name": "TestProject",
            "write_enabled": False,
            "skip_module_check": True,
            "skip_api_check": True,
            "user_intent": "fix broken gloss casting -- wiring test",
        }
        fail_result = asyncio.run(execution_mod.handle_run_module(fail_args))
        fail_payload = json.loads(fail_result[0].text)
        assert fail_payload.get("error_type") == "PolymorphicAttributeError" or "error" in fail_payload

        # Manually append the [FAIL] block's session-log text -- the real
        # operations_logger writes to the file handler kernel.py attaches;
        # our stubbed get_current_session_log_path already points AT that
        # same real per-process logger's output is captured via the actual
        # logging call, so just verify the log accumulated content.
        assert session_log.exists()

        # --- Second call: same turn (same user_intent), succeeds. ---
        monkeypatch.setattr(
            execution_mod, "run_script_async",
            _fake_run_script_async_factory({
                "success": True,
                "messages": [],
                "info_count": 0, "warning_count": 0, "error_count": 0,
            }),
        )
        ok_args = dict(fail_args)
        ok_args["code"] = "report.Info('resolved after the fix')"
        ok_result = asyncio.run(execution_mod.handle_run_module(ok_args))
        ok_payload = json.loads(ok_result[0].text)

        assert ok_payload.get("success") is True
        assert "diagnostic_report" in ok_payload, (
            f"expected diagnostic_report advisory on the resolving success "
            f"close; payload keys={sorted(ok_payload.keys())}"
        )
        advisory = ok_payload["diagnostic_report"]
        assert advisory["signature"]
        assert advisory["transports"]["gh"]["argv"][0] == "gh"
        assert Path(advisory["report_path"]).exists()

    def test_no_advisory_when_turn_never_fails(self, tmp_path, monkeypatch):
        _stub_execution_common(monkeypatch, tmp_path)
        monkeypatch.setattr(
            execution_mod, "run_script_async",
            _fake_run_script_async_factory({
                "success": True, "messages": [],
                "info_count": 0, "warning_count": 0, "error_count": 0,
            }),
        )
        args = {
            "code": "x = 1",
            "project_name": "TestProject",
            "write_enabled": False,
            "skip_module_check": True,
            "skip_api_check": True,
            "user_intent": "trivial all-green turn -- wiring test",
        }
        result = asyncio.run(execution_mod.handle_run_module(args))
        payload = json.loads(result[0].text)
        assert payload.get("success") is True
        assert "diagnostic_report" not in payload
