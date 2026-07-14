# CP3 verification report -- Surface + transport + guard

Verifying: specs/diagnostic-report/reviews/cycle7-lex-programmer.md
(CP3 + CP2-carryover P2 implementation). Spec: SPEC.md sections 8, 9, 10,
12. All findings below are independently re-run, not taken from the
implementation report's claims.

## Status: PASS

## 1. Full suite

Ran from repo root (d:\Github\_Projects\_LEX\FlexToolsMCP):

    python -m pytest -q
    577 passed in 44.87s

Also ran --collect-only: 577 tests collected, matching the run count
exactly. This confirms the claimed baseline (511 + 66 new = 577) with zero
failures and zero regressions. No skips, no xfails observed.

Status: PASS -- actual count matches claimed count exactly.

## 2. No-transmission guard (spec sec 8.1 / sec 12 "No transmission")

Ran tests/test_diagnostic_no_transmission.py alone:

    16 passed in 2.00s

Breakdown, verified by reading the test file as well as running it:

- Static AST scan (test_static_ast_scan_finds_no_transmission_surface,
  10 parametrized cases): parses every *.py in
  src/flextoolsmcp/server/diagnostic/ (__init__.py, normalize.py,
  offered_store.py, reconstruct.py, render.py, sensitivity.py,
  signature.py, transports.py, triggers.py) PLUS
  src/flextoolsmcp/server/handlers/diagnostic_report.py, and fails on any
  import/from of subprocess, smtplib, webbrowser, socket, requests, http
  (root), or the network-capable submodules urllib.request/urllib.error/
  http.client, plus AST Call-site detection of os.system/os.popen/
  webbrowser.open. All 10 pass. I confirmed by ls that the diagnostic
  directory contains exactly these 9 files (plus __init__.py, already
  counted) -- the parametrization is not silently short.
- Scan-coverage sanity
  (test_static_scan_covers_the_whole_diagnostic_tree_and_the_handler):
  reads the test source directly. It asserts the file-name set produced by
  _target_files() contains transports.py, sensitivity.py, reconstruct.py,
  render.py, normalize.py, triggers.py, signature.py, offered_store.py,
  diagnostic_report.py, and len(files) >= 9. This is a real guard against
  an accidentally-empty or truncated glob (e.g. a typo'd *.py pattern)
  silently reducing coverage to zero -- it enumerates by name, not just by
  count, so a glob that matched the wrong directory would also fail it.
  Confirmed adequate.

- Deviation #2 (socket exclusion from dynamic layer) -- explicitly
  checked. "socket" IS in _BANNED_ROOT_MODULES in the static scanner, and
  both visit_Import and visit_ImportFrom check the root module of every
  import statement against that set -- so "import socket",
  "import socket as s", and "from socket import socket" are ALL caught by
  the static layer regardless of import style. The dynamic layer's
  monkeypatch set (_patch_all_transmission_surfaces) deliberately omits
  patching socket.socket globally (documented rationale: asyncio.run() on
  Windows opens an internal self-pipe loopback socketpair, so a blanket
  patch breaks the test harness itself, not the code under test). Since
  the static scan fully bans any socket import anywhere in the guarded
  tree, and the diagnostic/handler modules were verified (item 4 below) to
  contain zero socket references, coverage is not actually lost -- this
  holds.
- Dynamic layer (4 tests):
  test_dynamic_prepare_report_bundle_no_invocation_and_one_write
  parametrized [True, False] (gh-present, gh-absent),
  test_dynamic_mailto_branch_no_invocation, and
  test_dynamic_flextools_prepare_report_tool_end_to_end (drives the real
  flextools_prepare_report MCP tool handler via asyncio.run, not just the
  internal prepare_report_bundle helper). All four monkeypatch
  subprocess.{run,Popen,call,check_call,check_output}, os.system,
  os.popen, smtplib.{SMTP,SMTP_SSL}, webbrowser.open, and
  urllib.request.urlopen to raise AssertionError on any invocation, and a
  Path.write_text counter asserts exactly 1 write per prepared report. All
  4 pass; the write-count assertion (== 1) is exact, not <=.

Status: PASS on all four sub-checks.

## 3. Transport clauses (spec sec 9 / decision E6)

Ran tests/test_diagnostic_report_transport.py alone: 46 passed in 1.92s.

- gh-present argv shape: test_exact_argv_shape asserts
  argv[0:3] == ["gh", "issue", "create"], --repo -> MattGyverLee/FlexToolsMCP
  (transports.DEFAULT_REPO), --title present, --body-file -> the exact
  report path passed in, --label -> "auto-report". Read
  src/flextoolsmcp/server/diagnostic/transports.py::build_gh_command --
  the implementation constructs exactly this argv list, matching spec
  sec 9's literal command. Confirmed.
- gh-absent URL: test_url_is_well_formed_and_percent_encoded uses
  urlparse/parse_qs (not substring matching) to confirm scheme=https,
  netloc=github.com, path=/<repo>/issues/new, and that parse_qs
  round-trips the title/labels back to their original (pre-encoding)
  values -- a real correctness check on percent-encoding, not just
  "contains %20". test_body_capped_at_8kb feeds a 100,000-char summary and
  asserts url_bytes <= MAX_URL_TOTAL_BYTES (8192) both via the returned
  metadata and a direct len(url.encode('utf-8')) check. Confirmed <=8KB is
  enforced on the actual encoded byte length, not the pre-encoding
  character count (percent-encoding can inflate 3x, and the
  implementation's cap/shrink-loop in build_github_issue_url operates on
  encoded bytes for exactly this reason).

- mailto with neither present: test_mailto_works_with_neither_gh_nor_browser
  builds a mailto URI with no gh/browser dependency at all (pure string
  construction) and asserts it's always non-empty and under the byte cap;
  test_dynamic_mailto_branch_no_invocation in the no-transmission suite
  drives this through the real pipeline with all transmission surfaces
  patched to raise, confirming zero invocations.
- gh_available injectable: TestGhAvailableInjectable (5 tests) confirms
  default_gh_available() uses shutil.which only (patched and both
  True/False branches verified, no subprocess call), and that
  build_transports(gh_available_fn=...) respects an injected callable in
  both directions, with the gh argv/display always built regardless of
  availability (caller decides presentation, per spec sec 9).

Status: PASS on all four transport sub-clauses.

## 4. Residual banned-surface grep (independent of the test suite)

    grep -rniE "subprocess|smtplib|webbrowser|import socket|from socket|requests|http\.client|urllib\.request|urllib\.error|os\.system|os\.popen" \
      src/flextoolsmcp/server/diagnostic/ src/flextoolsmcp/server/handlers/diagnostic_report.py

Every match is a docstring/comment reference (e.g. module docstrings in
transports.py, reconstruct.py, triggers.py, offered_store.py, __init__.py
describing the guard itself). Zero actual import statements or call-sites
of any banned surface in the source tree (only .pyc binary matches, which
are compiled artifacts of the same clean source). Matches the "zero
expected" bar.

Status: PASS.

## 5. Cleanliness -- pre-existing unrelated changes

git status shows src/flextoolsmcp/server/validators.py and
tests/test_validator_cluster_fixes.py as modified (not part of this task's
untracked-file set, which is sensitivity.py, transports.py,
handlers/diagnostic_report.py, and the two new test files). I read the
full diff on both:

- validators.py: adds _MIN_CHAIN_MATCH_RATIO = 0.5 and two continue guards
  inside detect_invalid_project_chains(), fixing issue #69 (a
  low-confidence acronym-fallback match, e.g. LangProject ->
  PossibilityLists at ratio ~0.15, being surfaced as an authoritative
  "did you mean" suggestion). This is entirely about the accessor-typo
  pre-flight validator's confidence threshold -- unrelated to
  diagnostic-report (no diagnostic/, transport, or guard code touched).
- tests/test_validator_cluster_fixes.py: 118 lines added, all covering
  the issue #69 ratio-floor fix above.

Neither file appears in the CP3 implementation report's "Modified files"
or "New files" sections, and neither is referenced by any diagnostic-report
test. Confirmed not swept into CP3 work -- these are pre-existing,
independently-scoped changes as stated.

Status: PASS.

## Final assessment

Overall Status: PASS

| Check | Result |
|---|---|
| Full suite | 577 passed / 0 failed (matches claim exactly) |
| No-transmission guard (static) | PASS -- 10/10 file scans clean, coverage-sanity test verified adequate |
| No-transmission guard (dynamic) | PASS -- 4/4 tests, zero invocations, exactly 1 write each |
| Deviation #2 (socket) | Confirmed safe -- static ban is unconditional and covers all import styles |
| Transport: gh argv | PASS -- exact shape matches spec sec 9 |
| Transport: URL | PASS -- valid, percent-encoded (round-trip verified), <=8KB on encoded bytes |
| Transport: mailto | PASS -- works with neither gh nor browser present |
| Transport: gh_available injectable | PASS -- both branches exercised without a real gh |
| Residual grep | PASS -- zero real import/call-site hits, only docstring mentions |
| Cleanliness | PASS -- validators.py / test_validator_cluster_fixes.py changes are issue #69, unrelated to CP3 |

Blockers: None.

Recommendation: APPROVE.

---
Verified By: Verification Agent (cycle 8)
Date: 2026-07-13
