"""CP4 downstream demo: an executable, CI-verified end-to-end walk-through of
the diagnostic-report flow against a FIXTURE session log.

This is the runnable companion to `docs/DIAGNOSTIC-REPORT-DEMO.md`. Each stage
below mirrors a heading in that doc, so the narrative walkthrough can never
silently drift from what the code actually does:

    trigger -> workaround signal -> auto-offer -> prepare -> preview
            -> gh / email / decline -> dedupe

It exercises the real modules (triggers, reconstruct, render, transports,
sensitivity, offered_store, and the handlers/diagnostic_report orchestration)
end to end -- no mocks of the diagnostic pipeline itself, only the log-dir /
session-log / reports-dir location shims so the demo runs against tmp_path.

Spec: specs/diagnostic-report/SPEC.md sections 6-10, 12.
"""

import asyncio
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from flextoolsmcp.server.diagnostic import (
    triggers,
    transports,
    offered_store,
)
from flextoolsmcp.server.handlers import diagnostic_report


# ---------------------------------------------------------------------------
# Fixture: a "workaround taken" turn -- a PolymorphicAttributeError op-1 that
# the user works around in op-2 (same turn, green close). This is the
# canonical §1 case: a real API inconsistency worth reporting to the
# maintainer, discovered and worked around inside one turn.
# ---------------------------------------------------------------------------

def _fmt(level: str, msg: str, ts: str = "2026-07-14 09:15:00") -> str:
    return f"{ts} | {level:<7} | {msg}"


def _fail_block():
    return [
        _fmt("INFO", "=== Session Environment ==="),
        _fmt("INFO", "MCP version:     2.6.1"),
        _fmt("INFO", "flexicon:        4.1.0"),
        _fmt("INFO", "liblcm:          8.3.0"),
        _fmt("INFO", "FieldWorks:      9.1.0"),
        _fmt("INFO", "OS:              Windows-11"),
        _fmt("INFO", "Python:          3.12.0"),
        _fmt("INFO", "=== End Session Environment ==="),
        _fmt("INFO", "[TOOL CALL] flextools_get_object_api"),
        _fmt("INFO", "[TOOL ARGS] flextools_get_object_api: {\"object\": \"ILexSense\"}"),
        _fmt("INFO", "=== Operation #1 Start (op-1) ==="),
        _fmt("INFO", "Project:         DemoProject"),
        _fmt("INFO", "Write enabled:   False"),
        _fmt("INFO", "Source kind:     bare_snippet"),
        _fmt("INFO", "User intent:     read the headword off each sense's owner"),
        _fmt("INFO", "User request:    show me the headword for every sense"),
        _fmt("INFO", "Code fingerprint: sha256=abc123 bytes=42 lines=2"),
        _fmt("DEBUG", "Code:"),
        _fmt("DEBUG", "for s in project.LexSense.GetAll():"),
        _fmt("DEBUG", "    report.Info(s.Owner.HeadWord)"),
        _fmt("ERROR", "[FAIL] Operation failed"),
        _fmt("ERROR", "Error type:      PolymorphicAttributeError"),
        _fmt("ERROR", "  report.Error: 'ICmObject' object has no attribute 'HeadWord'"),
        _fmt("INFO", "Messages:        0 info, 0 warnings, 1 errors"),
        _fmt("INFO", "Duration:        0.120s"),
        _fmt("INFO", "=== Operation #1 End (op-1) ==="),
    ]


def _ok_block():
    return [
        _fmt("INFO", "=== Operation #2 Start (op-2) ==="),
        _fmt("INFO", "Project:         DemoProject"),
        _fmt("INFO", "Write enabled:   False"),
        _fmt("INFO", "Source kind:     bare_snippet"),
        _fmt("INFO", "User intent:     read the headword off each sense's owner"),
        _fmt("INFO", "User request:    show me the headword for every sense"),
        _fmt("INFO", "Code fingerprint: sha256=def456 bytes=61 lines=2"),
        _fmt("DEBUG", "Code:"),
        _fmt("DEBUG", "for s in project.LexSense.GetAll():"),
        _fmt("DEBUG", "    report.Info(project.LexSense.GetGloss(s))"),
        _fmt("INFO", "[OK] Operation completed successfully"),
        _fmt("INFO", "Messages:        3 info, 0 warnings, 0 errors"),
        _fmt("INFO", "Duration:        0.090s"),
        _fmt("INFO", "=== Operation #2 End (op-2) ==="),
    ]


def _records():
    common = {
        "ts": "2026-07-14T09:15:00Z", "project": "DemoProject",
        "write_enabled": False, "source_kind": "bare_snippet",
        "user_intent": "read the headword off each sense's owner",
        "user_request": "show me the headword for every sense",
        "code_bytes": 42, "code_lines": 2, "preflight_gate": "",
        "casting_signature": "", "duration_s": 0.1,
        "info_count": 0, "warning_count": 0, "error_count": 0,
    }
    fail = dict(common, op_id="op-1", seq=1, outcome="runtime_fail",
                error_code="PolymorphicAttributeError", code_sha256="a" * 64,
                error_count=1)
    ok = dict(common, op_id="op-2", seq=2, outcome="ok", error_code="",
              code_sha256="b" * 64, info_count=3)
    return [fail, ok]


@pytest.fixture
def demo_env(tmp_path, monkeypatch):
    """Wire the diagnostic-report location shims at tmp_path and lay down the
    fixture session log + operations.jsonl."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    session_log = log_dir / "session_demo.log"
    session_log.write_text("\n".join(_fail_block() + _ok_block()), encoding="utf-8")

    records = _records()
    with open(log_dir / "operations.jsonl", "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")

    reports_dir = tmp_path / "reports"
    offered_dir = tmp_path / "offered_state"

    monkeypatch.setattr(diagnostic_report, "get_log_dir", lambda: log_dir)
    monkeypatch.setattr(diagnostic_report, "get_current_session_log_path", lambda: session_log)
    monkeypatch.setattr(diagnostic_report, "_default_reports_dir", lambda: reports_dir)
    monkeypatch.setattr(offered_store, "get_reports_dir", lambda: offered_dir)
    return {
        "records": records,
        "session_log": session_log,
        "reports_dir": reports_dir,
        "offered_dir": offered_dir,
    }


# ---------------------------------------------------------------------------
# The walk-through, one test per stage.
# ---------------------------------------------------------------------------

class TestDiagnosticReportDemoWalkthrough:

    def test_stage1_trigger_fires_on_the_reportable_failure(self, demo_env):
        """STAGE 1 -- trigger (§6.1). The runtime_fail op-1 is a reportable
        close; the green op-2 is not."""
        reportable = triggers.find_reportable_closes(demo_env["records"])
        assert [r["op_id"] for r in reportable] == ["op-1"]

    def test_stage2_workaround_signal_is_the_same_turn_ok_close(self, demo_env):
        """STAGE 2 -- workaround-taken signal (§6.2): a reportable failure
        followed by a same-turn `ok` close."""
        records = demo_env["records"]
        assert triggers.find_reportable_closes(records)          # a failure exists
        assert records[-1]["outcome"] == "ok"                    # ...resolved same turn

    def test_stage3_auto_offer_attaches_at_the_success_close(self, demo_env):
        """STAGE 3 -- auto-offer (§6.5/§10). The success close of op-2 carries
        a diagnostic_report advisory anchored on op-1's failure."""
        advisory = diagnostic_report.build_advisory_for_success_close("op-2")
        assert advisory is not None
        assert advisory["error_code"] == "PolymorphicAttributeError"
        assert advisory["signature"]
        assert "PolymorphicAttributeError" in advisory["title"]
        # The failing symbol was pulled from the log for a precise signature.
        assert Path(advisory["report_path"]).exists()

    def test_stage4_explicit_prepare_reconstructs_the_full_turn(self, demo_env):
        """STAGE 4 -- prepare (§5/§10). flextools_prepare_report rebuilds the
        whole turn slice (the v1 recovery path, and the way Claude sizes the
        slice)."""
        result = asyncio.run(diagnostic_report.handle_prepare_report({"op_id": "op-2"}))
        payload = json.loads(result[0].text)
        assert payload["status"] == "ok"
        assert payload["boundary"] == "turn"
        assert payload["error_code"] == "PolymorphicAttributeError"
        assert set(["signature", "title", "summary", "report_path",
                    "report_markdown", "transports",
                    "likely_contains_lexical_data"]).issubset(payload.keys())

    def test_stage5_preview_shows_full_report_and_all_transport_strings(self, demo_env):
        """STAGE 5 -- preview fidelity (E4). The user sees BOTH the full local
        report file (all seven sections) AND the actual capped transport
        string for each channel."""
        result = asyncio.run(diagnostic_report.handle_prepare_report({"op_id": "op-2"}))
        payload = json.loads(result[0].text)

        # (a) The full report file: seven sections, reconstructed slice.
        on_disk = Path(payload["report_path"]).read_text(encoding="utf-8")
        assert on_disk == payload["report_markdown"]
        for heading in ["## 1. Header", "## 2. Request", "## 3. Interpretation",
                        "## 4. What was tried", "## 5. The error",
                        "## 6. The resolution", "## 7. Structured JSONL appendix"]:
            assert heading in on_disk
        assert "PolymorphicAttributeError" in on_disk
        assert "show me the headword for every sense" in on_disk  # verbatim request

        # (b) All three transport strings present simultaneously.
        tr = payload["transports"]
        assert set(tr.keys()) == {"gh_available", "gh", "github_url", "mailto"}

    def test_stage6a_github_via_gh_cli_exact_argv_shape(self, demo_env):
        """STAGE 6a -- GitHub via `gh` CLI (§9, E6). Exact argv shape;
        --body-file carries the full local report."""
        result = asyncio.run(diagnostic_report.handle_prepare_report({"op_id": "op-2"}))
        gh = json.loads(result[0].text)["transports"]["gh"]
        argv = gh["argv"]
        assert argv[0:3] == ["gh", "issue", "create"]
        assert argv[argv.index("--repo") + 1] == transports.DEFAULT_REPO
        assert argv[argv.index("--label") + 1] == "auto-report"
        # The full report file rides along via --body-file (full fidelity).
        body_file = argv[argv.index("--body-file") + 1]
        assert Path(body_file).exists()

    def test_stage6b_github_via_url_is_valid_and_capped(self, demo_env):
        """STAGE 6b -- GitHub via prefilled URL (§9). Valid, percent-encoded,
        body <= 8 KB, instructs the user to attach the local file."""
        result = asyncio.run(diagnostic_report.handle_prepare_report({"op_id": "op-2"}))
        url_obj = json.loads(result[0].text)["transports"]["github_url"]
        parsed = urlparse(url_obj["url"])
        assert parsed.scheme == "https" and parsed.netloc == "github.com"
        assert url_obj["url_bytes"] <= transports.MAX_URL_TOTAL_BYTES
        assert "attach" in url_obj["body_text"].lower() or "paste" in url_obj["body_text"].lower()

    def test_stage6c_email_via_mailto(self, demo_env):
        """STAGE 6c -- email (§9). Private channel; short body, full fidelity
        via the attached local file."""
        result = asyncio.run(diagnostic_report.handle_prepare_report({"op_id": "op-2"}))
        mailto = json.loads(result[0].text)["transports"]["mailto"]
        assert mailto["uri"].startswith(f"mailto:{transports.DEFAULT_EMAIL}")
        assert mailto["body_bytes"] <= transports.MAX_MAILTO_TOTAL_BYTES

    def test_stage6c_email_framing_is_flagged_for_lexical_data(self, demo_env):
        """STAGE 6c -- the workaround op reads a gloss into report.Info, so the
        code-SHAPE sensitivity flag is set: Claude flags GitHub as public and
        offers email. The flag never changes the file or the send decision."""
        result = asyncio.run(diagnostic_report.handle_prepare_report({"op_id": "op-2"}))
        assert json.loads(result[0].text)["likely_contains_lexical_data"] is True

    def test_stage6d_decline_leaves_the_local_file_and_sends_nothing(self, demo_env):
        """STAGE 6d -- decline. "Don't send" always stands; the local report
        file persists for later. (The structural no-transmission guarantee is
        proven separately in tests/test_diagnostic_no_transmission.py.)"""
        result = asyncio.run(diagnostic_report.handle_prepare_report({"op_id": "op-2"}))
        report_path = Path(json.loads(result[0].text)["report_path"])
        assert report_path.exists()
        # Nothing about "declining" is an MCP action -- the user simply does
        # not run any transport. The file stays put.
        assert report_path.read_text(encoding="utf-8")

    def test_stage7_dedupe_suppresses_the_repeat_auto_offer(self, demo_env):
        """STAGE 7 -- dedupe (§6.3-6.4). A first auto-offer records the
        signature; marking it "don't ask again" suppresses the next auto-offer
        for the same failure signature -- but the already-written report file
        is never touched, and the explicit tool still bypasses dedupe (§5)."""
        offered_path = demo_env["offered_dir"] / "offered.json"

        first = diagnostic_report.build_advisory_for_success_close("op-2")
        assert first is not None
        sig = first["signature"]

        offered_store.record_decision(
            sig, offered_store.STATE_DONT_ASK_AGAIN, path_fn=lambda: offered_path,
        )

        # Auto-offer now suppressed...
        assert diagnostic_report.build_advisory_for_success_close("op-2") is None
        # ...but the first report file persists...
        assert Path(first["report_path"]).exists()
        # ...and the explicit recovery tool is NOT gated by dedupe.
        result = asyncio.run(diagnostic_report.handle_prepare_report({"op_id": "op-2"}))
        assert json.loads(result[0].text)["status"] == "ok"
