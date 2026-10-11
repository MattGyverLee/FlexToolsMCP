# Cycle 2 — Synthesis: integration-fit gate for the whole 5-phase change (issue #369)

Branch `feat/369-mcp-modernization`, HEAD `b4adb61`, base `origin/main` `c1c751f`.
Scope: the five phase commits `bfee45d` (P1), `15ad1eb` (P2), `184bcf9` (P3),
`722422a` (P4), `b4adb61` (P5). Read-only review; no code was changed.

Verdict: the code itself is coherent across phases (see §2 — no cross-phase
defect found). The drift is almost entirely in **live documentation and spec
bookkeeping**: three live docs still describe the pre-#369 world, the
CHANGELOG's Unreleased section was never touched, and not one checkbox in
`tasks.md`/`spec.md` has been reconciled. All are cheap text fixes, but two of
them (TODO.md, specs/mcp2-compat) actively misstate current behaviour, and the
repo's own close-out task makes checkbox reconciliation a PR precondition.

---

## 1. Leftover inconsistencies (grep sweep: `mcp_compat`, `1.x`, `>=1.27`, dual-support, FastMCP/MCPServer)

### Legitimately historical / correct — no action

| Hit | Why it is fine |
|---|---|
| `CHANGELOG.md:551-583` ("MCP 1.x/2.x dual support", `mcp>=1.27.0,<3`), `:2246-2254` (the `<2` cap) | Released-version sections; they record what was true then. |
| `specs/_archive/mcp2-compat/dual-support-analysis.md`, `specs/_archive/unified-recipes/{research.md,.spec-context.json}` | Archive. |
| `specs/mcp-modernization/reviews/cycle1-*.md`, `spec.md:9-16` | This spec's own audit trail; the MCPServer/FastMCP mentions are the R1 ruling record (Shape A chosen, Shape B rejected). |
| `tests/test_mcp_compat.py:6,24,31` | The file was rewritten, not left stale: its docstring states the shim is retired and the tests now target the inlined adapter in `server.py`. The name is a historical label only. |
| `tests/test_dependency_bounds.py:9,19,69-79` | Regression guard that *rejects* a 1.x floor — the opposite of a leftover claim. |
| `pyproject.toml:33-36`, `requirements.txt:1,5` | Correctly state `mcp>=2,<3`, 2.x-only. |
| `src/flextoolsmcp/response_utils.py:291`, `server.py:1122`, `server/handlers/execution.py:1324`, `docs/TOOL-CONTRACT.md:238` ("tool-responses/1.x", "backward compat") | These are the tool-response contract version and handler-dict conventions, unrelated to the `mcp` library major. |
| `docs/STABILITY-SURVEY-FLEXTOOLSMCP.md:36` "dual-mode import guards" | Dual-mode = package/script import guard, not dual mcp support. |

### Live inconsistencies (in the fix list, §6)

1. **`docs/TODO.md:7-43` — the P1 item is now false.** It is headed
   "Status: open", says the `outputSchema` advertisement in `list_tools()` is
   "commented out" as the Option-A hotfix, and says
   `tests/test_response_contract.py::TestOutputSchema` "now guards that NO
   tool advertises outputSchema". Phase 2 did the opposite of all three:
   `server.py` `list_tools()` advertises for the batch-1 set, the adapter
   returns `structuredContent`, and `15ad1eb` rewrote that test file. The
   item's premise (`mcp` 1.27.0's tuple return, `docs/TODO.md:27`) and its
   closing claim of an "unused FastMCP 2.14 dependency" (`:39-43`) are also
   stale — no `fastmcp` appears in `pyproject.toml` or `requirements.txt`.
   This is the exact follow-up Phase 2 implemented; the TODO must be marked
   done/superseded by #369 or deleted.
2. **`specs/mcp2-compat/` is a live (non-archive) spec directory describing a
   dead state.** `specs/mcp2-compat/README.md:3-7` frames the directory as
   "Dual support for mcp 1.x and 2.x (#83, closed)" with live deferred
   drafts, and `specs/mcp2-compat/deferred-issues.md` §1 ("Port to mcp 2.0")
   states as present fact that "flextools-mcp currently caps `mcp` at
   `>=1.27.0,<2` … this issue tracks the eventual forward port." The port
   has landed on this branch; nothing in either file points at #369.
3. **No other live hits.** `README.md`, `SETUP.md`, `STATUS.md` contain no
   `1.27`/dual-support/FastMCP claims (grep clean); `src/` contains no
   `mcp_compat` reference at all (the module is deleted and
   `src/flextoolsmcp/server/__init__.py` has no shim import left).

---

## 2. Cross-phase coherence (Phases 2 + 3 on the Phase 1 adapter)

Read end-to-end: `server.py` `make_call_tool_handler._on_call_tool`
(`:1359-1405`), `call_tool` (`:979-1227`), `server/progress.py`.

**The interaction is correct.** The ordering chain is:

1. Adapter installs the request's reporter:
   `set_progress_reporter(build_progress_reporter(ctx, params))` at
   `server.py:1382-1384`, reset in `finally` at `:1396-1397`.
2. `call_tool` re-sets the ambient reporter around dispatch only
   (`:1137`, reset in `finally` at `:1156-1157`). The token nesting is sound:
   the inner reset restores the adapter's reporter, the outer reset restores
   the pre-request value, and a raising handler returns `error_response`
   from the `except` while the `finally` still resets — the reporter cannot
   leak into a later call.
3. The `_session_note` rewrite happens **inside** `call_tool`, after
   dispatch (`:1159-1167`), i.e. before the adapter sees the content.
4. Only then does the adapter derive structured content:
   `derive_structured_content(name, content)` at `:1399`, which parses
   `content[0].text` (`:894-927`) — the final, post-rewrite payload, exactly
   as R2 required. Text bytes are passed through untouched
   (`CallToolResult(content=list(content), …)`, `:1400-1403`).

Error paths are consistently structured-content-free, by construction:
`error_response` always emits top-level `status="error"` + `error_code`
(`src/flextoolsmcp/response_utils.py:275-280`), and `derive_structured_content`
returns `None` for either marker (`server.py:925`). This covers all three
early returns in `call_tool` (session gate, unknown tool, validation) as well
as handler exceptions. The adapter-level exception path (`:1390-1395`)
returns a plain-text `is_error` result before derivation is reached.

Heartbeat/milestone call sites read the reporter ambiently at call time
(`progress_heartbeat` defaults to `get_progress_reporter()`,
`server/progress.py:196`), and all instrumented sites run inside the
dispatch bracket: semantic milestones (`server.py` `SemanticSearch.load`/
`search`), run_module and grammar-scan heartbeats
(`server/handlers/execution.py:6388,6395,7334`), sandbox milestones
(`server/handlers/parse/sandbox.py`). Startup loads in `main()` run against
the `NO_OP_REPORTER` default, as designed.

Two minor observations, neither a defect:

- **`report_nowait` can outlive the call.** `progress.py:100-113` schedules
  fire-and-forget tasks on the loop; a milestone queued near the end of a
  call may be delivered after the `CallToolResult` has been returned (the
  sink is session-bound and survives the ContextVar reset). Clients ignore
  late progress; the sink swallows errors. Worth a sentence in the module
  docstring, not a code change.
- **Cold-init note is dropped when the handler raises.** If
  `_pending_session_note` was set (cold auto-init, `call_tool` `:1029-1053`)
  and the handler then raises, the `except` return at `:1146-1154` bypasses
  the note attachment at `:1159`. Pre-existing shape (the note attach has
  always sat after dispatch), and the session *was* initialized, so the only
  loss is the advisory text. Follow-up at most.

---

## 3. Docs coherence

**`scripts/validate_integrity.py all` — clean.** Run in the venv with
absolute `PYTHONPATH`: syntax OK, import guards OK, "server.py: 31 tools
registered [OK]", "USAGE.md: all 31 tools documented [OK]", tool output
models golden + minimal payloads OK, flexicon contract passed (runtime
checks skipped, flexicon not installed). No integrity debt from any phase.

**CHANGELOG.md — an Unreleased entry is owed (must fix).** The file has a
live `## [Unreleased]` section (`CHANGELOG.md:3-20`) with an explicit
convention note: issue-linked bullets sorted ascending by issue number,
non-issue changes under Other. The immediately preceding feature followed
it in its own commit — `10e103e` (#218) added its Unreleased bullet
(CHANGELOG +12) alongside the code, and that bullet is still visible at
`CHANGELOG.md:10-19`. **None of the five phase commits touched
CHANGELOG.md** (verified per-commit `--stat`). A 5-phase, user-visible
change (dependency floor, structured output, progress notifications,
registry manifest, a security fix) with no Unreleased entry breaks the
file's own stated convention.

**STATUS.md — no entry; follow-up, not a blocker.** `STATUS.md:3-8` opens
with an "Active feature" block per repo convention, and prior features
recorded themselves there — but the convention is already loosely kept (the
head still names the September swahili-audit campaign; several merged
features since are absent), and grep finds no #369/mcp-2.x mention anywhere
in the file. Adding a short active-feature entry is consistent with
convention; its absence does not misstate anything, unlike §1 items 1-2.

**USAGE.md — no false claims; new behaviour undocumented (follow-up).**
Phase 5's annotation reclassifications do not contradict USAGE: the only
READ_ONLY_SAFE claim in USAGE is for `flextools_list_recipes`
(`USAGE.md:44,47`), which was not reclassified, and the `flextools_parse_sandbox`
row (`USAGE.md:91`) says "never touches the live project", which remains
true — Phase 5's point (tool_definitions.py, the comment block at the
`flextools_parse_sandbox` ToolDef, ~`:830`) is that it writes under
`~/.flextoolsmcp/parse/`, not that it writes the project. `flextools_start`
(`USAGE.md:20`) makes no read-only claim, matching its new description text
("This call is not read-only", tool_definitions.py `:112-117`). What USAGE
lacks is any mention of the new client-visible behaviour: grep for
`structuredContent`/`outputSchema`/"progress" finds only an unrelated
`flextools_parse_status` row (`USAGE.md:86`). The tool table is still
accurate, so this is documentation completeness, not correctness.

**Phase 4 description choice — resolved, thinly documented.** tasks.md
required picking pyproject ≤100 chars *or* a registry-only description and
noting which. The branch took the registry-only route: `server.json`
carries a 97-char description while `pyproject.toml:5`'s description
remains 115 chars. The choice is visible in the artifacts but noted
nowhere (commit `722422a` has an empty body); a one-line note in tasks.md
when reconciling checkboxes (§4) closes it.

---

## 4. Spec hygiene — `specs/mcp-modernization/tasks.md` + `spec.md`

**Every checkbox in both files is unchecked: tasks.md has 34 `[ ]` and 0
`[x]`; spec.md's Acceptance has 7 `[ ]` and 0 `[x]`.** Phases 1-5 are
implemented and committed, so the dominant drift is *done but not checked*.
Per-item audit against the branch (excluding the known-open workflow,
publish, and refresh items):

Done but unchecked — Phase 1: pyproject/requirements floor + comments
(`bfee45d`); adapter inlined in server.py; `resolve_server_version` moved
(`server.py:1234`), `mcp_compat.py` deleted; `server/__init__.py` shim
lines dropped; tests rewritten incl. the raw JSON-RPC `server/discover` +
legacy `initialize` stdio smoke (`tests/test_mcp_compat.py:321-373`) —
which also satisfies spec.md Acceptance box 2; dependency-bounds floor
assertion. Phase 2: all five items (`15ad1eb`, incl. the handlers/api.py
shadowing removal and golden byte-compare). Phase 3: all items (`184bcf9`;
C/B/E/H sites verified in §2). Phase 4: server.json present and
schema-shaped, README `mcp-name` at `README.md:1`, manifest test landed
(`722422a`). Phase 5: P0 fix, truth-table reconciliation
(parse_sandbox and flextools_start re-annotated in tool_definitions.py),
T1–T12 suite (`tests/test_tool_poisoning_regression.py`, 936 lines), in
`b4adb61`.

Unchecked and genuinely not done (other than the known-open set):

- **Phase 1, kernel.py item** ("verify unchanged under 2.x; touch only if a
  test proves otherwise") — no commit touches kernel.py and the suite
  passes, so the verification outcome is "unchanged", but it is recorded
  nowhere; tick it with that note or leave an explicit note.
- **Phase 5, S-P1-5 fencing item** — asks to extend "data, never
  instructions" framing where small *and report what balloons*. The
  parse_sandbox description carries the framing
  (tool_definitions.py, `flextools_parse_sandbox` description), but no
  report of what was/wasn't extended exists in the spec dir; the item
  cannot be honestly ticked or closed without that one-paragraph report.
- **Phase 4, description-choice note** (§3 above).
- Close-out items are legitimately open — this review is the lex-synthesis
  leg of the first one.

No box is checked-but-not-done (there are no checked boxes at all). The
risk is the inverse of the usual one: as written, the PR cannot claim
`closes #369` — the close-out task itself conditions that on the
Acceptance boxes being verified, and spec.md's boxes 1, 3, 4, 5, 6 are
verifiably satisfiable today.

---

## 5. Duplication / extraction

No phase introduced a duplicated helper that copies another phase's new
code. Two extraction candidates, both pre-existing patterns the branch
inherited rather than created:

1. **Version resolution is implemented twice.** `server.py:1234-1260`
   `resolve_server_version()` (moved verbatim from the shim in Phase 1)
   duplicates the metadata-then-VERSION-file-walk in
   `server/kernel.py:510-530` (the session-header version). The server.py
   docstring even says "Mirrors the logic in server/kernel.py". One shared
   helper in kernel (server.py already imports from it) would remove the
   drift risk; follow-up, not a blocker — both copies currently agree.
2. **"Parse the first text payload" now has three sites in server.py
   alone**: the new `derive_structured_content` (`:915`), the
   `_session_note` rewrite (`:1161`), and the outcome logger (`:1178`),
   plus the same shape in `server/handlers/parse_telemetry.py:129`. They
   differ in failure handling (derive: skip; note: leave untouched; log:
   err_code=None), so a shared `_parse_first_payload(content) -> dict|None`
   helper is a small, safe extraction
...[truncated 3331 chars]