# QC Report — CP3 "Surface + transport + guard"

**Date:** 2026-07-13
**Quality Score:** 92/100
**Status:** APPROVE (minor P2 cleanup recommended, non-blocking)

## Pattern-Audit Gate
- Sweep present in PR body: N/A — this is a spurt-cycle implementation report (`specs/diagnostic-report/reviews/cycle7-lex-programmer.md`), not a `bug`-labelled PR/commit closing a GitHub issue.
- Gate applicability: N/A (one-off / feature work). The two "CP2 carryover (P2)" fixes bundled in (`reconstruct.py`'s mismatched-End-marker reset, `render.py`'s unanchored substring stop-marker match) are parser/string-matching bugs, not shaped like any of the five recognized recurring classes (typed attribute access, list/sequence assumptions, default-arg semantics, role disambiguation, multilingual-string typing). Justification: both are novel, narrowly-scoped log-parsing bugs local to this feature's two new modules; there is no sibling codebase pattern to sweep.
- Gate status: **PASS** (N/A, justified)

## Code Quality: 22/25
- Readability: strong — docstrings consistently explain *why*, not just *what* (esp. the fail-open contract on `build_advisory_for_success_close`, and the CP2 substring-vs-startswith fix rationale in `render.py`).
- Maintainability: good factoring; `prepare_report_bundle` cleanly separates reconstruct -> gate -> render -> write -> transports -> sensitivity.
- Consistency: dual try/except import pattern (package-relative vs. absolute) is verbose but matches the rest of the codebase's established convention — not a new issue.

**Issues:**
- `src/flextoolsmcp/server/diagnostic/transports.py:100-109` — `_cap_bytes()` is defined but never called anywhere in the module (confirmed via repo-wide grep — zero references outside its own definition). Both `build_github_issue_url` (lines 155-166) and `build_mailto` (lines 195-203) reimplement an almost byte-identical inline truncation loop instead of using it. Dead code + DRY violation. **P2.**

## Standards Compliance: 24/25
- Style guide: consistent with project conventions (module docstrings, `frozenset`/regex constants at module top, type hints throughout).
- Naming: clear and consistent (`_pick_anchor_record`, `_build_title`, `_build_summary`, `_extract_failing_symbol` all self-describing).
- Organization: correct placement — `handlers/diagnostic_report.py` (does file I/O) kept out of `server/diagnostic/` (pure-function package), matching the documented one-way dependency rule and mirrored by `execution.py`'s existing `diagnostic.triggers` precedent.

**Issues:** None of note.

## Error Handling: 24/25
- **`build_advisory_for_success_close()` fail-open contract — VERIFIED, no leak.** `src/flextoolsmcp/server/handlers/diagnostic_report.py:266-319`: the entire function body (config check, JSONL load, turn lookup, `find_reportable_closes`, session-log resolution, `prepare_report_bundle` call, `offered_store.record_offer`) sits inside one `try: ... except Exception:` block. The exception handler itself (lines 308-318) wraps its own `get_operations_logger()`/`logger.warning(...)` call in a nested `try/except Exception: pass`, so even a logging failure cannot escape. No code path exists outside the outer `try`. Confirmed by `test_fail_open_on_internal_exception` (`tests/test_diagnostic_report_transport.py:481-493`), which forces an exception mid-pipeline and asserts `None` is returned. **This is a real fail-open, not just a documented one.**
- **`_extract_failing_symbol()` — graceful-fallback claim holds in practice.** `src/flextoolsmcp/server/handlers/diagnostic_report.py:92-99`: `None`-guarded entry, `getattr(..., []) or []` guards a missing/`None` attribute, and the regex `.search()` only executes over that iterable. It never raises for the realistic input shape (list of strings from `SliceOp.log_lines`, itself always populated from `reconstruct.py`'s string-only block-parsing). One theoretical gap: if `log_lines` ever contained a non-`str` element, `_ATTR_ERROR_RE.search(line)` would raise `TypeError` — not defensively guarded (no `isinstance` check or inner `try`). This can't happen through any current caller, so it's a latent robustness gap, not a live bug. **P2** (add a defensive `isinstance(line, str)` check or wrap in `try/except` for cheap insurance, given the "never raises" claim in the docstring is currently true only by invariant, not by construction).
- Only indirectly unit-tested (via `test_dont_ask_again_suppresses_repeat_offer` / `test_explicit_tool_ignores_dont_ask_again`'s `failing_symbol="HeadWord"` assumption) — no direct table-driven unit test of `_extract_failing_symbol()` in isolation (multiple matches, no match, non-AttributeError shapes). Acceptable given it's an explicitly-flagged v1 heuristic, but worth a small direct test in CP4. **P2.**
- `sensitivity.detect_lexical_shape()` — the syntax-error/empty-code safety claim is real: `ast.parse` is guarded by `except (SyntaxError, ValueError)` (`src/flextoolsmcp/server/diagnostic/sensitivity.py:131-134`), confirmed by `test_syntax_error_returns_false_not_raise` and `test_empty_code_returns_false`. Minor unguarded theoretical case: `RecursionError`/`MemoryError` on pathological input aren't caught, but this mirrors every other `ast.parse` call site in the codebase and isn't a realistic risk for FLExTools-script-sized inputs. Not flagged as an action item.

## Best Practices: 22/25
- Design patterns: injectable-callable pattern (`gh_available_fn`, `offer_gate`, `reports_dir_fn`) used consistently and well for testability (decision E6).
- No anti-patterns of consequence, aside from the DRY duplication noted above.
- Performance: fine — no obvious hot-path issues; AST walks and string ops are all bounded by single-op code-block size.

**Issues:**
- `transports.py:62-71` (`_quote_argv`) — escapes only embedded double-quotes (`replace('"', '\\"')`), not backslashes, and wraps in POSIX/sh-style double quotes. This is explicitly documented as cosmetic/display-only (the `argv` list is authoritative and unquoted), and is tested only for the simple space-containing case (`test_display_string_is_shell_readable`). On Windows the equivalent cmd.exe/PowerShell quoting rules differ, so a title containing embedded quotes could render a display string that looks plausible but wouldn't actually round-trip if pasted verbatim into a Windows shell. Low real-world impact (display-only, `argv` unaffected) but worth a one-line docstring caveat ("POSIX-style display quoting; not guaranteed to round-trip on Windows shells"). **P2 (cosmetic).**
- `build_github_issue_url` / `build_mailto`'s truncation loop (`transports.py:157-166`, `196-203`) can, in a degenerate case where `title`+`labels` alone (pre-body) already exceed `max_total_bytes`, terminate via the `cut_to <= 0: break` exit while the URL is still over budget — the loop shrinks only `body_text`, never title/labels. Not currently reachable in practice since `_build_title()` caps titles at 200 chars (`diagnostic_report.py:138`) and labels are a small constant, but the cap is not structurally enforced by `build_github_issue_url` itself, so a future caller passing an unbounded title would silently violate the "<=8KB" acceptance criterion. **P2.**

## Final Assessment
**Overall Score:** 92/100
**Recommendation:** APPROVE

No P0 or P1 issues found. In particular, the two highest-risk items flagged for scrutiny — the `build_advisory_for_success_close` fail-open contract and the two-layer no-transmission guard — both hold up under direct inspection: the fail-open wrapping is total (no code path escapes the outer `try`), and the transports/sensitivity modules genuinely never invoke a transmission-capable surface (confirmed by both the static AST scan and the dynamic monkeypatch-and-drive tests, plus my own line-level read of `transports.py`/`sensitivity.py`). All findings are P2 (dead code, DRY duplication, one latent non-`str`-defensiveness gap, one cosmetic quoting caveat, one structurally-unenforced title-length assumption) — worth cleaning up but none block the CP3 merge.

**P0 count: 0**
**P1 count: 0**
**P2 count: 5** (transports.py dead code/DRY at lines 100-109/155-166/195-203; `_extract_failing_symbol` non-str defensiveness at diagnostic_report.py:92-99; missing direct unit test for `_extract_failing_symbol`; `_quote_argv` Windows-shell quoting caveat at transports.py:62-71; unenforced title-length assumption in the URL/mailto truncation loop at transports.py:157-166/196-203)

---
**Reviewed By:** QC Agent

**Files reviewed:**
- `src/flextoolsmcp/server/diagnostic/transports.py`
- `src/flextoolsmcp/server/diagnostic/sensitivity.py`
- `src/flextoolsmcp/server/handlers/diagnostic_report.py`
- `src/flextoolsmcp/server/diagnostic/reconstruct.py`
- `src/flextoolsmcp/server/diagnostic/render.py`
- `src/flextoolsmcp/server/diagnostic/offered_store.py`
- `src/flextoolsmcp/server/diagnostic/signature.py`
- `src/flextoolsmcp/config.py`
- `src/flextoolsmcp/server/handlers/execution.py`
- `src/flextoolsmcp/server/dispatch.py`
- `src/flextoolsmcp/server/models.py`
- `tests/test_diagnostic_report_transport.py`
- `tests/test_diagnostic_no_transmission.py`
- `tests/test_diagnostic_report_reconstruction.py`
