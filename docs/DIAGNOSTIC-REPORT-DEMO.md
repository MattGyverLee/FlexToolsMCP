# Diagnostic-report: end-to-end walk-through

This is the downstream demo for the "send this to the maintainer" flow
(spec: [`specs/diagnostic-report/SPEC.md`](../specs/diagnostic-report/SPEC.md)).
It walks a single real scenario from the failure that triggers an offer all the
way to the three send outcomes, against a fixture session log.

Every stage below has an executable, CI-verified counterpart in
[`tests/test_diagnostic_report_demo.py`](../tests/test_diagnostic_report_demo.py)
(one test per stage, same headings), so this narrative can never silently drift
from what the code does. Run it with:

```bash
python -m pytest tests/test_diagnostic_report_demo.py -q
```

## The one guarantee to keep in mind

The MCP **never transmits anything**. It writes one local report file and
builds transport *strings*; a human takes every send action. There is no code
path that spawns `gh`, opens a browser, sends mail, or opens a socket — this is
enforced structurally (static AST scan + dynamic monkeypatch test:
[`tests/test_diagnostic_no_transmission.py`](../tests/test_diagnostic_no_transmission.py)),
not by policy. See SPEC.md §8.1/§12.

## The scenario

A user asks: *"show me the headword for every sense."* Claude writes a first
attempt that reaches for `sense.Owner.HeadWord`:

```python
for s in project.LexSense.GetAll():
    report.Info(s.Owner.HeadWord)
```

`ICmObject` has no `HeadWord` attribute (a polymorphic-collection casting
pitfall — the exact class of inconsistency the maintainer wants to hear about),
so op-1 closes `runtime_fail` with `PolymorphicAttributeError`. Claude works
around it in the same turn with a wrapped accessor:

```python
for s in project.LexSense.GetAll():
    report.Info(project.LexSense.GetGloss(s))
```

op-2 closes `ok`. The failure was real, was worked around, and — left alone —
would go unreported. That is what this flow is for.

---

## Stage 1 — Trigger (§6.1)

The op-1 close matches the trigger predicate: `outcome == "runtime_fail"` (any
exception class, excluding `timeout`). `invalid_api_chain` and recurring
`casting_issues_detected` also trigger; the 13 explicitly non-reportable codes
(discovery/authoring/project-infra/`server_state_error`/…) never do. The green
op-2 is not itself a reportable close.

## Stage 2 — Workaround-taken signal (§6.2)

There is no explicit "I worked around it" flag in the logs. The signal is
*inferred*: a reportable failure followed by a same-turn `ok` close. That pair
is the cue that an inconsistency was hit and survived — worth offering to
report.

## Stage 3 — Auto-offer (§6.5 / §10)

At op-2's success close, `run_module`'s response carries a `diagnostic_report`
advisory block (additive optional field on `RunModuleSuccess`; documented in
[`docs/TOOL-CONTRACT.md`](TOOL-CONTRACT.md)). It is anchored on op-1's failure
and carries `signature`, `title`, `summary`, `report_path`, `transports`,
`likely_contains_lexical_data`, and `error_code`. The signature is
code-independent (keyed on exception class + normalized failing symbol, here
`HeadWord`), so re-editing the code and hitting the same failure does not
re-offer.

> **v1 limitation (accepted).** The auto-offer attaches only at a same-turn
> `ok` close. A turn that fails reportably and is then *abandoned* is not
> auto-offered — recover with `flextools_prepare_report` (Stage 4). Tracked in
> [issue #72](https://github.com/MattGyverLee/FlexToolsMCP/issues/72).

## Stage 4 — Prepare (§5 / §10)

`flextools_prepare_report` rebuilds the report on demand. It defaults to the
whole turn and also accepts explicit `op_id` / `op_ids` / `steps_back`, so
Claude can size the slice — and it is the recovery path when the auto-offer was
deduped or the turn was abandoned. It bypasses the dedupe store entirely (an
explicit request is always honored). The turn is reconstructed by joining
`operations.jsonl` to the session-log `=== Operation #N Start/End ===` blocks by
`op_id`/`seq`, stitched across log rotations, and bounded by `MAX_REPORT_OPS`
(excess ops are summarized, never silently dropped).

## Stage 5 — Preview (E4)

Before any send, the user is shown **both** artifacts, because they differ by
channel:

1. **The full local report file** — the complete bytes that reach the
   maintainer once attached/pasted. Seven sections: header (versions), request
   (verbatim `user_request`), interpretation (`user_intent` + discovery calls +
   casting decisions), what-was-tried (the code of each op), the error, the
   resolution, and a structured JSONL appendix. Machine-hygiene normalization
   (home dir → `~`, OS username → `<user>`) is applied **path-scoped only** — it
   never touches lexical prose (SPEC.md §8.3/E2).
2. **The actual transport string** for the chosen channel. For `gh` this
   carries the whole file via `--body-file`; for the GitHub-URL and `mailto:`
   channels it is only a short, capped summary (the full file reaches the
   maintainer only if the user attaches/pastes it).

The report file lives at `~/.flextoolsmcp/reports/report_<ts>.md`. Writing it
transmits nothing; the user owns it and may hand-edit it before sending — the
tool never offers or performs anonymization.

## Stage 6 — The three outcomes (§9)

Claude presents exactly three choices; the MCP never chooses.

### 6a — GitHub via `gh` CLI (default)

Exact argv shape, full fidelity via `--body-file`:

```
gh issue create --repo MattGyverLee/FlexToolsMCP \
  --title "[auto-report] PolymorphicAttributeError: read the headword off each sense's owner" \
  --body-file ~/.flextoolsmcp/reports/report_<ts>.md \
  --label auto-report
```

The MCP builds this argv; it does not run it. "gh available" is a PATH check
(`shutil.which`), injectable so CI exercises both the present and absent
branches.

### 6b — GitHub via prefilled issue URL (no `gh`, has a browser)

```
https://github.com/MattGyverLee/FlexToolsMCP/issues/new?title=<enc>&labels=auto-report&body=<enc>
```

Body-via-URL is length-capped (~8 KB after percent-encoding), so the prefilled
body is a short summary that instructs the user to attach/paste the local
report file. The embedded `report_path` is normalized (home dir → `~`), so the
URL never leaks the user's OS username.

### 6c — Email via `mailto:` (private)

```
mailto:matthew_lee@sil.org?subject=<enc>&body=<short>
```

Short body; the real payload is the local report file the user attaches.
Private, full-fidelity — the right choice when the report may carry
unpublished/sensitive language data.

**Routing framing.** The workaround op reads a gloss into `report.Info`, so the
`likely_contains_lexical_data` flag is set — detected from code **shape** (a
known lexical accessor flowing into `report.Info`), never from content. GitHub
stays the default, but Claude flags that a GitHub issue is public and permanent
and offers email as the private alternative. The flag only chooses which
sentence Claude says; it never alters the local file's fidelity and is never the
final send decision.

### 6d — Don't send

Always available, never penalized. "Declining" is simply not running any
transport — the local report file stays put so the user can send it later or
hand it over by other means. Nothing leaves the machine.

## Stage 7 — Dedupe (§6.3–§6.4)

The first offer records the signature in `~/.flextoolsmcp/reports/offered.json`
(fail-open on corruption, LRU-pruned at 500 entries). If the user picks "don't
ask again", the same failure signature is suppressed from future auto-offers —
across restarts. Consent is per-report: approving one never grants standing
consent, and "don't ask again" only suppresses *the offer*, never sends
anything and never touches an already-written report file. The explicit
`flextools_prepare_report` tool still works — it is never gated by the dedupe
store.

---

## Where the pieces live

| Concern | Module |
|---|---|
| Trigger predicate / workaround signal / dedupe gate | `server/diagnostic/triggers.py`, `offered_store.py`, `signature.py` |
| Slice reconstruction + rotation stitching | `server/diagnostic/reconstruct.py` |
| Report rendering (7 sections) | `server/diagnostic/render.py` |
| Path-scoped normalization | `server/diagnostic/normalize.py` |
| Transport string building (never invoked) | `server/diagnostic/transports.py` |
| Code-shape sensitivity flag | `server/diagnostic/sensitivity.py` |
| Orchestration + `flextools_prepare_report` + advisory | `server/handlers/diagnostic_report.py` |
| Advisory wiring at the success close | `server/handlers/execution.py` |
| No-transmission guard (static + dynamic) | `tests/test_diagnostic_no_transmission.py` |
