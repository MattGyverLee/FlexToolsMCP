# Spec: Diagnostic Report / "Send this to the maintainer" flow

Status: DRAFT (awaiting LEX crew review cycle)
Author: Claude Code (with matthew_lee@sil.org)
Date: 2026-07-13

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

This is a small, additive contract change but it is the only way to get the real
request text into the bundle. It must land before/with this feature.

## 5. Unit of a report: LLM-sized slice, turn as the default

The maintainer wants "the turn where the error happened and some context" AND
suggests letting the LLM "determine how many steps are necessary to determine
the problem." So the slice is **LLM-sized within a bounded default**, not a
rigid fixed window.

Default boundary — the **turn**: the contiguous run of operations sharing one
`user_intent`/`user_request` ("attempt session").
`op_telemetry.compute_jsonl_statistics()` already groups consecutive
same-`user_intent` records this exact way (lines 230-255) — reuse that grouping
so the report boundary matches the existing green-rate/turns-to-green analytics.

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
attention:

- Fire when the closing `error_code` is in a curated `REPORTABLE_CODES` set —
  the inconsistency / known-LibLCM-workaround classes, NOT ordinary user syntax
  errors or `partial_module_structure` nudges.
- Also fire on an explicit "inconsistency detected" signal (e.g. a workaround
  path taken in LibLCM interop) if/when such a signal is emitted.
- **Dedupe / rate-limit:** never offer twice for the same
  `(code_sha256, error_code)` signature. Persist offered/suppressed signatures
  (e.g. `~/.flextoolsmcp/reports/offered.json`) with a "don't ask again for this
  error" honored across sessions.
- The offer is surfaced in the tool response as a `diagnostic_report` advisory
  block (see TOOL-CONTRACT envelope), which Claude relays to the user. The MCP
  never sends anything itself.

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

**This raises the redaction stakes** (section 8): the prose slice can contain
lexical data (headwords, glosses, definitions) via `report.Info`. Because the
default is "everything," the mandatory human-review preview is the primary
safeguard and must be excellent.

## 8. Privacy & consent model (the load-bearing part)

Because the default payload includes full prose (which may contain unpublished
language data), consent must be informed and the preview must be honest:

1. **Never auto-send.** The MCP emits an offer; the human must act.
2. **Mandatory full preview.** Before any send, the user is shown the *exact*
   bytes that would leave their machine — the rendered report file — not a
   summary of it. Claude presents it and asks explicitly.
3. **Redaction pass applied before preview:**
   - Home-dir absolute paths → `~`.
   - Machine/user names in paths stripped.
   - Project name: replaced with a stable hash by default; user may opt to
     include the real name.
   - Offer an optional **"anonymize data"** toggle (see 8.1) that masks the text
     payload of `report.Info`/`report.Error` lines (keeps structure, drops the
     headword/gloss strings). Default OFF given the "everything" choice, but
     one-keystroke available and surfaced in the offer.
4. **Report file is written locally first** to
   `~/.flextoolsmcp/reports/report_<ts>.md`. Nothing is transmitted by writing
   it; it is the artifact the user reviews and then chooses to attach/paste.
5. **Consent is per-report.** Approving one report never implies standing
   consent. "Don't ask again" only suppresses *the offer* for that error
   signature; it never sends.

### 8.1 The "anonymize data" option and its cost (confirmed)

The user may choose to **anonymize** the report before sending. When enabled it
masks the lexical/text payload — the actual headword, gloss, definition, and
other language-data strings carried in `report.Info`/`report.Error` and echoed
in code — while preserving structure, field names, types, error codes, casting
decisions, and the shape of the data.

**Claude must state the tradeoff at the moment of offering**, not bury it:

> Anonymizing removes the actual words from your lexicon, which protects
> unpublished language data — but it can make the bug **harder or impossible to
> fix** when the bug depends on the specific data (e.g. a particular Unicode
> sequence, an empty-vs-`***` multistring, a writing-system mismatch, a
> diacritic or normalization edge case, an unusually long form). For
> logic/API-shape bugs, anonymizing usually costs nothing.

Design implications:
- The toggle is presented with this caveat inline; it is not a silent switch.
- **Graduated anonymization, not all-or-nothing.** Prefer masking that keeps
  diagnostically useful invariants even while hiding meaning, e.g.:
  - preserve string length, script/writing-system tag, and Unicode category
    profile (has-combining-marks, has-astral, is-normalized) while replacing
    glyphs with placeholders;
  - keep the empty / `***` / non-empty distinction verbatim (it is itself a
    frequent bug source per CLAUDE.md multistring notes);
  - keep structural punctuation and whitespace.
  This lets many data-dependent bugs still reproduce without shipping the words.
- The report header records `anonymized: true|false` and, when true, *which*
  masking profile was applied, so the maintainer knows what was withheld and can
  ask the user to re-send un-anonymized (or with a narrower mask) if the masked
  report proves insufficient.
- Config default `report_default_anonymize` (default OFF, per the maintainer's
  "everything with review" choice); an org/admin may flip the default ON for
  sensitivity-first deployments.

## 9. Transport (confirmed: GitHub, email fallback)

Priority order:

1. **GitHub via `gh` CLI**, if `gh` is installed and authenticated:
   `gh issue create --repo MattGyverLee/FlexToolsMCP --title "..."
   --body-file ~/.flextoolsmcp/reports/report_<ts>.md --label auto-report`.
   Detected by probing `gh auth status`.
2. **GitHub via prefilled issue URL** if `gh` is absent but a browser is:
   `https://github.com/MattGyverLee/FlexToolsMCP/issues/new?title=<url-enc>&labels=auto-report`.
   Issue-body-via-URL is length-capped (~8 KB practical), so the prefilled body
   is a SHORT summary that instructs the user to drag/paste the local report
   file into the issue. The full bundle rides in as an attachment/paste, not in
   the URL.
3. **Email fallback** (`mailto:matthew_lee@sil.org?subject=<url-enc>&body=<short>`)
   for users with neither GitHub account nor `gh`. Same pattern: short body,
   real payload is the attached local report file.

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
  (default maintainer), `report_default_anonymize` (default off; §8.1).

## 11. Open questions for the crew

1. What exactly belongs in `REPORTABLE_CODES`? (lex-domain / lex-logscan input.)
2. Is there a distinct "LibLCM workaround taken" signal we can trigger on, or do
   we infer it from error_code + a green follow-up? (lex-domain.)
3. Should the prose slice reconstruct across the current session log only, or
   also stitch a turn that spans a session-log rotation boundary? (lex-programmer.)
4. Anonymization (§8.1): which masking profile best preserves reproducibility
   while hiding meaning? Is the length/script/empty-vs-`***`/Unicode-category
   set sufficient, or are there bug classes that need more (or can tolerate
   less)? Should any deployment default anonymize ON? (lex-domain / privacy.)
5. Does the `diagnostic_report` advisory block (and the `user_request`
   passthrough arg) fit the frozen TOOL-CONTRACT envelope, or does either need a
   contract minor bump? (lex-doc / lex-qc.)
6. Should `user_request` live on `flextools_start` (turn-level) only, on
   `run_module` (per-op) only, or both? Per-op costs tokens but survives
   intent-drift within a turn. (lex-programmer / lex-domain.)

## 12. Acceptance criteria

- Given a `run_module` failure whose `error_code` is reportable and unseen, the
  response carries a `diagnostic_report` block; a duplicate signature does not.
- A written report file reconstructs the failing slice (request → resolution)
  from the session log, joined with the slice's JSONL lines, and includes the
  verbatim `user_request` when Claude supplied it.
- The report slice honors an explicit LLM-supplied op selection / `steps_back`,
  falling back to the whole turn, bounded by `MAX_REPORT_OPS`.
- Redaction removes home paths and machine/user names; project name is hashed by
  default.
- No transmission occurs from any MCP code path; only local file write + prepared
  transport strings.
- `gh`-present and `gh`-absent both yield a working GitHub path; email works with
  neither.
- With anonymize ON, no lexical/text payload leaves the machine; the report
  header records `anonymized: true` + the masking profile, and the
  length/script/empty-vs-`***` invariants (§8.1) are preserved. Claude states
  the fixability tradeoff at offer time.
