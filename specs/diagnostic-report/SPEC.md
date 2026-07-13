# Spec: Diagnostic Report / "Send this to the maintainer" flow

Status: APPROVED-WITH-EDITS (LEX crew review cycle 1-2 complete; edits E1-E8 applied)
Author: Claude Code (with matthew_lee@sil.org)
Date: 2026-07-13
Reviews: see [`reviews/`](reviews/) — domain, programmer, doc, qc, logscan (cycle 1)

## 1. Problem / Motivation

The MCP already writes high-quality per-session logs to
`~/.flextoolsmcp/logs/`. These logs capture, for a given turn: what the user
asked, how Claude interpreted it, what code was tried, what error/inconsistency
was hit, and how it was worked around. When a user hands those logs to the
maintainer, bugs get diagnosed and fixed quickly, because the log already
contains the attempt, the expectation, and the LibLCM workaround.

Today that hand-off is entirely manual and undiscoverable: the user has to know
the logs exist, find them, decide what to cut out, and email them. Most users
never do it, so real inconsistencies (especially LibLCM workarounds worth
upstreaming) go unreported.

**Goal:** when the MCP hits a known error class or inconsistency, it should
*offer* — with explicit, informed consent — to package the relevant slice of
the log and send it to the maintainer, preferring a GitHub issue, falling back
to email.

## 2. Non-goals

- No silent / automatic sending. Ever.
- No direct HTTP POST to a maintainer-run backend (no credentials in the MCP,
  no infra to run). Transport is user-initiated via tools they already have.
- Not a telemetry-phone-home system. This is a per-incident, opt-in bug report.
- No new dependency on SMTP configuration inside the MCP.

## 3. What the logs actually contain (grounding)

Two tiers exist today:

### 3.1 `operations.jsonl` (structured, `run_module`-only) — SUPPLEMENT, not payload
`op_telemetry.py`. One JSONL line per `run_module` close (ok / reject / fail).
Fields: `ts, op_id, seq, project, write_enabled, source_kind, user_intent,
code_sha256, code_bytes, code_lines, outcome, error_code, preflight_gate,
duration_s, info/warning/error_count, assistance_triggered`.

Critically it stores a **hash of the code, not the code**, and **no report
output** and **no discovery calls**. It cannot, on its own, explain what Claude
tried or why. It is a correlation/summary layer only.

### 3.2 Session log `logs/YYYY-MM-DD/session_<id>.log` (prose) — PRIMARY payload source
Everything routes through `operations_logger` (`server.py`, `execution.py`,
`kernel.py`). For the failing turn it contains:

| Content | Source | Maps to |
|---|---|---|
| `[TOOL CALL]` / `[TOOL ARGS]` for every tool | `server.py:846-848` | **Request** + **Interpretation** (discovery sequence) |
| `=== Operation #N Start (op_id) ===` block: Project, Write enabled, Source kind, **User intent** (paraphrase; verbatim `user_request` added per section 4), code fingerprint | `execution.py:383-391` | **Request** / **Interpretation** |
| `Preflight casting: issues=… tier=… helpers=…` | `execution.py:415-417` | **Interpretation** |
| `Code:` + code lines (DEBUG) | `execution.py:425-427` | **What was tried** |
| `report.Error` / `report.Warning` / `report.Info` | `execution.py:570-575` | **The error** + **Resolution** |
| Operation close (ok/reject/fail) | close fns | **Resolution / outcome** |

**Decision (confirmed with maintainer): the session log is the primary source.**
`operations.jsonl` is joined in by `op_id`/`seq` to add machine-readable
`error_code` / `outcome` / `code_sha256`.

## 4. Capturing the verbatim user request (NEW — maintainer requirement)

The maintainer wants **the actual TEXT of the user's request**, because the
literal wording carries intent that the paraphrase loses.

Today `user_intent` is explicitly *"a one-line paraphrase of the human request,
supplied by the LLM"* (`execution.py:376-379`). It is Claude's compression, not
the user's words. **The MCP process never sees the raw conversation** — it only
receives tool arguments — so the verbatim request is not recoverable from
existing logs.

**Decision:** add an optional passthrough field so the verbatim request is
captured at the source:
- New optional argument `user_request` (verbatim human text) on
  `flextools_start` (turn-level) and/or `run_module` (op-level), alongside the
  existing `user_intent` paraphrase.
- Claude populates it from the live conversation. When present it is logged in
  the operation-start block (`execution.py`) and stashed into the JSONL record
  next to `user_intent`.
- The report renders BOTH: verbatim `user_request` (primary "Request" section)
  and the `user_intent` paraphrase (as "Interpretation").
- Backward compatible: absent `user_request` falls back to `user_intent`, same
  as `user_intent` already falls back to "(not provided)".

This is a small, additive **input** change (a new optional tool argument), not a
response-envelope change — it is outside the scope of `docs/TOOL-CONTRACT.md`,
which governs response shapes (confirmed by contract review, Q5). It is the only
way to get the real request text into the bundle, and must land before/with this
feature.

## 5. Unit of a report: LLM-sized slice, turn as the default

The maintainer wants "the turn where the error happened and some context" AND
suggests letting the LLM "determine how many steps are necessary to determine
the problem." So the slice is **LLM-sized within a bounded default**, not a
rigid fixed window.

Default boundary — the **turn**: the contiguous run of operations sharing one
`user_intent` ("attempt session").
`op_telemetry.compute_jsonl_statistics()` already groups consecutive
same-`user_intent` records this exact way (lines 230-255) — reuse that grouping
so the report boundary matches the existing green-rate/turns-to-green analytics.

**Grouping-key decision (E7):** the grouping stays keyed on `user_intent`, and
`user_request` (§4) is carried along as payload — it is **not** added to the
group key. Keeping the key unchanged means report boundaries remain identical to
the shipped green-rate / turns-to-green analytics, and a mid-turn request
refinement (which updates `user_request`) does not fragment a single turn into
two. The verbatim `user_request` still renders in the report; it just doesn't
redefine the slice boundary.

LLM-sized override: the report-prep step lets Claude choose how far back the
slice reaches, because Claude knows whether the root cause was set up two ops
earlier (e.g. a bad discovery result) or is self-contained in the failing op:
- `flextools_prepare_report` accepts either an explicit list of `op_id`s to
  include, or a `steps_back` / `include_from_op_id` hint, or nothing (defaults
  to the whole turn).
- Claude is prompted to include the minimum contiguous span that makes the
  problem reproducible: request → the interpretation/discovery that led to the
  wrong code → the failing op → the resolution.
- A safety cap (`MAX_REPORT_OPS`, e.g. 12) bounds runaway slices; if the model
  asks for more, the extra ops are summarized, not dropped silently (log what
  was truncated per the "no silent caps" rule).

The failing op that triggered the offer anchors the slice; it extends backward
to at least the turn start (or the LLM-chosen earlier point) and forward to the
resolution so the maintainer sees the fix (or the give-up).

## 6. Trigger policy

Offer a report only when it is worth the maintainer's time and the user's
attention.

### 6.1 Trigger predicate (E1)

The trigger is **not** a flat "`error_code ∈ REPORTABLE_CODES`" set-membership
test. On a runtime failure the JSONL `error_code` is stamped with the *concrete
exception class name* — `error_code = error_type or "runtime_error"`
([`execution.py:696`](../../src/flextoolsmcp/server/handlers/execution.py), under
`outcome == "runtime_fail"` at `:690`). So real crashes carry codes like
`PolymorphicAttributeError` or `'ILcmServiceLocator' object has no attribute …`,
**not** the literal string `"runtime_error"`. A literal set test would miss all
of them (confirmed by log evidence: the three genuine crashes in the 113-op scan
all had exception-class `error_code`s).

Fire the offer when **any** of these hold on the closing op:

1. `outcome == "runtime_fail"` — **any** exception class (this is the core case;
   match on `outcome`, not on the literal code). Excludes `outcome == "timeout"`.
2. `error_code == "invalid_api_chain"` — a generated chain that passed discovery
   but doesn't exist against the real API (index/doc mismatch).
3. `error_code == "casting_issues_detected"` **and** the recurrence-after-cast
   condition holds — i.e. the same op's casting signature recurs *after* a cast
   was applied, indicating a real coverage gap in `known_polymorphic_patterns`.
   A first-time casting hint that resolves cleanly is proactive guidance, not a
   defect, and does **not** fire.

**Explicitly NOT reportable:** discovery-flow codes (`undiscovered_entity`,
`api_discovery_required`), authoring mistakes (`syntax_error`, `missing_imports`,
`undefined_variables`, `wrong_library_imports`), `unprotected_writes`,
`partial_module_structure`, project/infra codes (`project_locked`,
`project_drive_unavailable`, `project_path_mismatch`, `project_not_found`), and
`server_state_error`.

### 6.2 Workaround-taken signal (inferred; Q2)

No explicit "LibLCM workaround taken" signal exists in the code today. For v1,
**infer** it: within one turn (same `user_intent` grouping, §5), a close with
`outcome ∈ {preflight_reject, runtime_fail}` carrying a reportable code (6.1),
followed by a later same-turn op that closes `ok`. That request → failure →
resolution pair is the workaround signal and matches §7 bundle item 6. Log
evidence confirms this fail → quick-retry → ok pattern is real and frequent.
Promote to a first-class signal only if `casting_helpers` / `resolve_property`
later emit an explicit "cast applied" telemetry point.

### 6.3 Dedupe / rate-limit (E3)

Never offer twice for the same **inconsistency `signature`** — a *code-
independent* key, **not** `(code_sha256, error_code)`. Users iterate code across
a turn (confirmed by the retry pattern in log evidence), so keying on
`code_sha256` would re-offer the same underlying bug on every edit. Define
`signature` as a hash of the underlying inconsistency:

- runtime-fail → `(exception-class, normalized failing API symbol / top
  traceback frame)`;
- `invalid_api_chain` → the offending chain string (normalized);
- casting recurrence → the recurring casting signature.

Policy: **offer once per distinct inconsistency, not per code edit.** Persist
signatures in `~/.flextoolsmcp/reports/offered.json` (§6.4); "don't ask again"
is honored across sessions. A matching §12 acceptance criterion enforces this.

### 6.4 `offered.json` schema (E5)

`~/.flextoolsmcp/reports/offered.json` — a JSON object keyed by `signature`:

```json
{
  "version": 1,
  "entries": {
    "<signature-hash>": {
      "state": "offered" | "declined" | "dont_ask_again",
      "error_code": "<code or exception class>",
      "first_seen": "<ISO-8601 UTC>",
      "last_seen": "<ISO-8601 UTC>",
      "offer_count": <int>
    }
  }
}
```

- `offered` — surfaced at least once; may re-surface only if not yet acted on.
- `declined` — user said "not now"; suppressed for the session, may re-offer later.
- `dont_ask_again` — permanently suppressed for that signature across sessions.
- **Pruning:** cap `entries` (e.g. 500, LRU by `last_seen`) so the file can't
  grow unbounded on long-lived installs; a corrupt/unparseable file is treated
  as empty (fail-open to "offer", never crash the op path).

### 6.5 Surface

The offer is surfaced in the tool response as a `diagnostic_report` advisory
block (an additive optional field on `RunModuleSuccess`; see §10 and contract
review Q5), which Claude relays to the user. The MCP never sends anything itself.

## 7. Bundle contents

Anchored on the failing slice (sections 4-5):

1. **Header:** MCP version, flexicon version, liblcm version, FieldWorks
   version, OS, Python; report schema version.
2. **Request:** the verbatim `user_request` text (section 4) as primary; the
   `flextools_start` args for the turn.
3. **Interpretation:** the LLM's `user_intent` paraphrase + the ordered
   discovery `[TOOL CALL]`/`[TOOL ARGS]` for the slice + preflight casting
   decisions.
4. **What was tried:** the code of each op in the slice (source_kind, write flag).
5. **The error:** `report.Error`/`report.Warning` lines + `error_code` /
   `preflight_gate` / `outcome` from the joined JSONL line(s).
6. **The resolution:** the follow-up op(s) in the slice that went green, or a
   note that the turn was abandoned.
7. **Structured appendix:** the raw JSONL lines for the slice (machine-parseable),
   including `user_request` and `user_intent` fields.

### 7.1 Payload scope decision (confirmed)
Maintainer chose **"everything related to that turn, with user review"** —
because they have been reading session logs, not `operations.jsonl`, and the
session log is where the real context lives (section 3.2 confirms this is
correct; `operations.jsonl` alone is insufficient). So the default bundle
includes the full prose turn slice, NOT a structured-only subset.

The prose slice can contain lexical data (headwords, glosses, definitions) via
`report.Info`. **The report is always sent full-fidelity / unscrubbed** (see §8,
§9) — there is no anonymization step. The safeguards are therefore the *choice
of channel* and the *choice not to send at all*, backed by a human-review
preview.

## 8. Privacy & consent model (the load-bearing part)

The report always goes out **unscrubbed** — the maintainer wants the real data,
because scrubbing hurts fixability. Privacy is protected by *where it goes* and
*whether it goes*, not by masking content:

1. **Never auto-send.** The MCP only writes a local file and prepares transport
   strings; a human must take the send action. Nothing is transmitted from any
   MCP code path (this is structural, not a policy promise — see §9).
2. **Preview before send (E4).** Before choosing a channel the user is shown
   **both** artifacts that make up the send, because they differ by channel:
   (a) the full rendered report file — the complete bytes that would reach the
   maintainer once attached/pasted; and (b) the *actual transport string* for the
   chosen channel — for the `gh` CLI path this carries the full file via
   `--body-file`, but for the GitHub-URL and `mailto:` paths it is only a short
   capped summary (the full file reaches the maintainer only if the user manually
   attaches/pastes it — see §9). Showing only (a) would make "the exact bytes that
   leave the machine" false for two of the three channels, so the preview must
   show both.
3. **Machine-hygiene normalization only — path-scoped, not content scrubbing
   (E2, normative).** Two automatic substitutions protect the *user's own machine
   identity*: home-dir absolute paths → `~`, and the OS username removed from
   paths. These MUST operate **only on recognized path-shaped tokens** —
   substitution is anchored on the resolved `expanduser('~')` / `USERPROFILE`
   value appearing at the start of a path segment, and on file paths in report
   headers, tracebacks, code fingerprints, and discovery-call arguments. It is a
   **hard requirement that the implementation never perform a document-wide
   find/replace of the username (or home-path) string** across the report body.
   Rationale: a naive substring replace would corrupt and partially expose
   lexical data whenever a headword, gloss, or example sentence contains the
   username as a substring (e.g. OS user `matt` matching "**Matt**hew's toolbox"
   in a `report.Info` line), directly violating the "touches no lexical data"
   guarantee. This is a normative constraint, not an implementation detail, and
   has a matching §12 acceptance criterion. It touches no lexical data and does
   not reduce fixability. Automatic, not an offered toggle.
4. **Report file is written locally first** to
   `~/.flextoolsmcp/reports/report_<ts>.md`. Writing it transmits nothing; it is
   the artifact the user reviews and then attaches/pastes. Because it is a plain
   local file the user owns, they may hand-edit/redact it before sending if they
   choose — but **the tool never offers, suggests, or performs anonymization**.
   That remains entirely the user's own manual prerogative, out of scope here.
5. **Consent is per-report.** Approving one report never implies standing
   consent. "Don't ask again" only suppresses *the offer* for that error
   signature; it never sends.

## 9. Transport — three outcomes, user's choice (confirmed)

Given a prepared (unscrubbed) report, the user chooses exactly one of three
outcomes. Claude presents them plainly:

| Outcome | When | Trail |
|---|---|---|
| **1. GitHub issue** (default) | No confidentiality concern with the data | Public, permanent — trackable, dedupeable, normal triage |
| **2. Email to maintainer** | The report contains data the user does not want public (unpublished/sensitive language data) | Private, no public trail; full fidelity preserved |
| **3. Don't send** | The user decides it isn't worth sharing, or is unsure | Nothing leaves the machine; local report file remains for later |

**Routing rule Claude applies at offer time:**
- Default to **GitHub** — it flows well and is the right answer when nothing is
  sensitive. Do not nag or over-warn on ordinary reports.
- If the report **likely carries substantial lexical data**, Claude *flags* that
  a GitHub issue is public and permanent, and offers **email** as the private
  alternative — same full report, no public record. The user decides; this is
  their confidentiality judgment, not the MCP's.
- **Don't send** is always available and never penalized; the local file stays
  put so the user can send later or hand it over by other means.
- No scrubbing/anonymization is offered in any branch. Protection is channel
  choice, not content masking.

**Sensitivity detection is by code shape, not content (Q4, resolved).** The
`likely_contains_lexical_data` flag that drives the email-vs-GitHub *framing*
above is set by inspecting the *shape* of the op's code, never its string
values, so detection itself neither inspects nor leaks the data:
- the code calls a known lexical accessor — `GetGloss`, `GetDefinition`,
  `GetLexemeForm`, `.BestVernacularAlternative`, `.BestAnalysisAlternative`,
  `.Text` on a multistring field — and that result flows into `report.Info(...)`;
  or
- the code references BCP-47-like writing-system tags alongside a multistring
  accessor.
The flag **only** selects which sentence Claude says; it never alters the local
file (always full-fidelity per §7.1) and is never the final send decision —
GitHub stays the default and "don't send" always stands.

Mechanisms per channel (GitHub default):

- **GitHub via `gh` CLI** (if `gh auth status` succeeds):
  `gh issue create --repo MattGyverLee/FlexToolsMCP --title "..."
  --body-file ~/.flextoolsmcp/reports/report_<ts>.md --label auto-report`.
- **GitHub via prefilled issue URL** (no `gh`, has browser):
  `https://github.com/MattGyverLee/FlexToolsMCP/issues/new?title=<url-enc>&labels=auto-report`.
  Body-via-URL is length-capped (~8 KB), so the prefilled body is a SHORT summary
  instructing the user to drag/paste the local report file in.
- **Email** (`mailto:matthew_lee@sil.org?subject=<url-enc>&body=<short>`): short
  body; the real payload is the local report file the user attaches. Private,
  full-fidelity — chosen when the user has a confidentiality concern.

The MCP produces the command / URL / mailto string and the local file; Claude
hands it to the user. The MCP does not itself invoke `gh`, open a browser, or
send mail.

## 10. Proposed surface

- New advisory block `diagnostic_report` in the run_module response envelope
  (opt-in trigger per section 6), carrying: `signature`, `title`, `summary`,
  `report_path` (after the MCP writes it), and `transports` (the prepared
  `gh`/URL/mailto strings).
- Optional passthrough arg `user_request` (verbatim) on `flextools_start` /
  `run_module` (section 4).
- Optional explicit tool `flextools_prepare_report(op_id=..., op_ids=[...],
  steps_back=N)` so a user can ask "report the last error" even when the
  auto-offer was suppressed/deduped, and so Claude can size the slice (section 5).
- Config knobs in `.env` / config: `report_offers_enabled` (default on),
  `report_repo` (default `MattGyverLee/FlexToolsMCP`), `report_email`
  (default maintainer). No anonymization knob — reports are always full-fidelity.

## 11. Open questions — RESOLVED (cycle-1/2 crew review)

All six resolved in the review cycle; reports under
[`reviews/`](reviews/). Decisions are now folded into §4-§9 above.

1. **REPORTABLE_CODES** → RESOLVED (§6.1). `runtime_fail` (any exception class,
   matched on `outcome`), `invalid_api_chain`, and `casting_issues_detected`
   recurrence-only. Grounded in the 16 contract codes + a 113-op log scan.
2. **Workaround signal** → RESOLVED (§6.2). No explicit signal in code; infer
   from (reportable failure → green follow-up in same turn). Log-confirmed real.
3. **Rotation stitching** → RESOLVED. Stitch across rotation, but **JSONL-driven,
   not file-boundary-driven**: resolve the target `op_id`/`seq` list from the
   JSONL, then scan `session_<id>.log[.1/.2/.3]` for the matching
   `=== Operation #N Start/End ===` blocks (a `RotatingFileHandler` never splits a
   single log call) and concatenate in `seq` order. If `backupCount` has already
   recycled a requested op, surface "history truncated by rotation" (no silent
   caps). Verified feasible against the real code (all §3.2 anchors confirmed).
4. **Sensitivity signalling** → RESOLVED (§9). Auto-detect by **code shape**
   (lexical-accessor calls feeding `report.Info`), never by content; drives only
   the email-vs-GitHub framing.
5. **Contract fit** → RESOLVED (§10, §4). Both additions land under
   `tool-responses/1.0`, **no bump**: `diagnostic_report` is an additive optional
   field on `RunModuleSuccess` (same pattern as shipped #46/#47 fields);
   `user_request` is a tool-*input* arg, outside TOOL-CONTRACT.md scope.
6. **`user_request` placement** → RESOLVED (§4, §5). Primary/mandatory on
   `flextools_start` (turn-level); optional override on `run_module` only when
   intent drifts mid-turn. Grouping key stays `user_intent` (E7).

## 12. Acceptance criteria

**Trigger (§6.1):**
- A `run_module` op closing with `outcome == "runtime_fail"` (any exception
  class, e.g. `PolymorphicAttributeError`) yields a `diagnostic_report` offer;
  `outcome == "timeout"` does not. `invalid_api_chain` yields an offer;
  `casting_issues_detected` yields one **only** on recurrence-after-cast.
- Non-reportable codes (discovery/authoring/`unprotected_writes`/
  `partial_module_structure`/project-infra/`server_state_error`) yield no offer.

**Dedupe (§6.3-6.4):**
- The offer fires **once per distinct inconsistency `signature`**, not per code
  edit: two ops in one turn with edited code but the same underlying failure
  (same exception class + failing symbol) produce exactly one offer.
- `dont_ask_again` for a signature suppresses it across a simulated
  server restart (persisted in `offered.json` per the §6.4 schema); a corrupt
  `offered.json` fails open (offer proceeds, no crash).

**Reconstruction (§3, §5):**
- The report reconstructs the failing slice (request → interpretation →
  what-was-tried → error → resolution) from the session log, joined to the
  slice's JSONL lines by `op_id`/`seq`, including verbatim `user_request` when
  supplied. It honors an explicit op selection / `steps_back`, defaults to the
  whole turn, and is bounded by `MAX_REPORT_OPS` (excess ops summarized, not
  silently dropped). A turn spanning a log rotation is stitched via JSONL op_id
  targeting; an op already recycled by rotation is flagged, not silently omitted.

**Privacy / normalization (§8):**
- Report is always full-fidelity / unscrubbed; no anonymization path exists.
- **Path-scoped normalization only (E2):** given a report whose lexical content
  contains the OS username as a substring (e.g. user `matt`, gloss
  "Matthew's toolbox"), normalization rewrites home-path/username **only** inside
  recognized path tokens and leaves the lexical string untouched. A document-wide
  username find/replace is a test failure.

**No transmission (§8.1) — two-layer guard:**
- Static/AST scan of the diagnostic-report module tree fails the build on any
  `subprocess`/`gh`/`git issue create`, `smtplib`, `webbrowser.open`,
  `urllib`/`requests`/`http.client`, or raw `socket` outbound call.
- Dynamic test monkeypatches those to raise on invocation and drives
  `flextools_prepare_report` through gh-present, gh-absent, and email branches:
  asserts zero such invocations and exactly one local file write.

**Transport (§9) — "working" defined (E6):**
- `gh`-present → the prepared command matches the exact `gh issue create` argv
  shape: `--repo MattGyverLee/FlexToolsMCP`, `--body-file <report>`,
  `--label auto-report`. The "gh available" check is injectable so both branches
  run in CI without a real authenticated `gh`.
- `gh`-absent → the prepared URL is valid, correctly percent-encoded, and its
  body is ≤ 8 KB; email works with neither present.
- **Preview fidelity (E4):** the preview shows both the full report file and the
  actual capped transport string for the chosen channel.
- The user is presented exactly three outcomes: GitHub (default), email, or
  don't-send; on decline the local report file persists.
