# Contract: CP3 tool surface

**Date**: 2026-09-22 · **Spec**: [`../spec.md`](../spec.md) · **Plan**: [`../plan.md`](../plan.md)

Phase 1 output. This file is **the transcription source** for implementation.

> **Transcribe from here, not from prose.** CP2's own refusal-detail field-order
> divergence cost two crew cycles and happened during transcription, not
> because the source was wrong. Every verbatim string below was taken from the
> spec's Verbatim Constraints section, which was itself verified against the
> parent spec. Do not re-derive any of it.

---

## 1. Tools

Three new tools. Names are verbatim.

### `flextools_parse_text`

Submits a batch parse over a resolved scope.

| Aspect | Value |
|---|---|
| Annotation | `readOnlyHint=False`, `destructiveHint=True` -- **at its designed maximum capability, from its first release** (FR-025, D-1) |
| Annotation at CP4 | **unchanged.** That is the point of shipping it this way |
| Filing argument | **absent from the schema** until CP4 implements it |
| Description, first line | MUST state the spine and that **filing is not yet reachable** |

Arguments: scope kind and value, optional word limit, optional project name.

**The parser-engine capability check is the first statement of the handler**,
before any parser is constructed, and fires **once, at submission** (FR-024).

Execution: `ParseQueue.enqueue_run(run_id, words, Priority.LOW)` -- the
existing runner's lower-priority path with per-wordform granularity. **No
second execution model** (FR-014).

### `flextools_parse_log`

Reads a run back. **Never calls the engine check** (FR-024) -- it reads prior
artifacts.

Sections, exactly these:

```
summary | config_generation | hc_stdout | hc_output | trace | words | results | deletions
```

(`deletions` was added additively at parser-check CP4: a filing run's
pre-deletion captures. A read-only run answers it with a typed not-applicable,
never an empty section. See `../../parser-check-cp4/contracts/tools.md`.)

- `summary`, `words`, `results`, `trace` -- real content for in-process runs,
  paged.
- `config_generation`, `hc_stdout`, `hc_output` -- sandbox spine. Return a
  **typed not-applicable-for-this-spine response naming the spine and the
  checkpoint that will fill it** (FR-028, SC-007). Never an empty section: an
  empty section reads as "nothing happened."

A trace that cannot be parsed returns the **raw slice, explicitly labelled
raw** (FR-029). No explanation is invented for output the system could not read.

### `flextools_parse_diff`

Compares two runs. **Never calls the engine check** (FR-024).

Buckets, exactly these:

```
fixed | broken | changed | unchanged
```

Differing fingerprints refuse with `parse_scope_mismatch` unless forced; a
forced comparison runs on the **intersection only** and says so (FR-012).

Shared-mode markers, verbatim:

```
staleness: "shared_mode_unverifiable"
```

and `no_change` downgraded to `no_change_unverifiable` (FR-034).

---

## 2. Refusal codes

Five new codes, **additively**. The tool-response contract stays at
`tool-responses/1.0`; the documented code count rises **25 -> 30** with one
changelog entry under the tool-contract heading (FR-059).

Each detail model uses `model_config = ConfigDict(extra="forbid",
populate_by_name=True)` and a `Literal` `error_code`, matching
`response_models.py:476` and `:496`. Each gets a row in
`docs/TOOL-CONTRACT.md`'s table (FR-060).

**Detail fields, in this exact order:**

| Code | Detail fields, in order |
|---|---|
| `parse_scope_empty` | `scope`, `matched_texts`, `hint` |
| `parse_scope_ambiguous` | `scope`, `requested`, `candidates` |
| `parse_scope_mismatch` | `baseline_fingerprint`, `current_fingerprint`, `differing_fields`, `hint` |
| `parser_timeout` | `timeout_seconds`, `words_completed`, `run_id`, `hint` |
| `parser_job_failed` | `state_at_failure`, `failure`, `words_completed`, `words_total`, `run_id`, `log_path` |

Job-failure reasons, exactly these:

```
out_of_memory | crashed | cancelled
```

**`parse_scope_empty` is not reused for a never-tokenized text** (FR-002). A
text with structure but no unique wordforms gets its own conservative wording,
and the response does not assert the text has no words.

---

## 3. Mandated oracle wording

Rendered **verbatim**, never paraphrased, all six cases (FR-040, SC-011).

**Approved and not in any segment:**
```
Approved by [user] on [date].
```

**Approved but occurring in a segment:**
```
Approved under [user] on [date]. This analysis is in use in a text, and approval is recorded for anything left in use -- so it may have been affirmed, or merely used. There is no way to tell which.
```

**Disapproved:**
```
Marked incorrect by [user] on [date].
```

**No stored opinion:**
```
Not yet reviewed by a human -- this is not evidence it is wrong, only that nobody has checked it.
```

**Meaning only:**
```
A human recorded what this word means, but not how it decomposes -- there is no morphology here to compare the parser against.
```

**Sketched but unlinked:**
```
A human began a morphological analysis but did not finish linking it -- [N] of [M] morphs are not linked to a lexical entry, so it cannot be compared to the parser's output.
```

**Mandatory population sentence:**
```
[N] analyses carry a human approval. [M] of those appear in a text, where approval is recorded for anything left in use -- so some of those were used rather than affirmed. There is no way to tell which.
```

### Forbidden words

These MUST NOT be applied to an analysis carrying no stored opinion (FR-040):

```
invalid   incorrect   rejected   flagged
```

Asserted by a scan over every emitted response, not by review (SC-011).

### Provenance split

Exactly this pair, and never the second form:

```
{affirmed, indeterminate}        NOT {affirmed, tacit}
```

**No individual analysis may be labelled `tacit`, `unreviewed` or
`auto_approved`** anywhere in any output (FR-042, SC-012).

---

## 4. Host counters, verbatim

Adopted from the host application's parser report (FR-017):

```
NumWords
NumParseErrors
NumZeroParses
TotalParseTime
TotalAnalyses
TotalUserApprovedAnalysesMissing
TotalUserDisapprovedAnalyses
TotalUserNoOpinionAnalyses
```

Two deliberate divergences, stated **in the artifact itself** via
`counter_divergences`, not only here:

- `TotalUserApprovedAnalysesMissing` -- computed over **fully linked** human
  analyses only (FR-018).
- `TotalUserNoOpinionAnalyses` -- **never** presented, named or documented as a
  count of unreviewed analyses; the affirmed/indeterminate split rides beside it
  (FR-019).

---

## 5. Fixed values

| Thing | Value |
|---|---|
| Run identifier form | **32 lowercase hex**, `secrets.token_hex(16)`, `\A[0-9a-f]{32}\Z`. **No timestamp** |
| Retention | newest **20** runs per project, by **recorded creation time** |
| Drill-down cap range | **10-20** words per session, chosen by the user |
| Contract version | `tool-responses/1.0` (unchanged) |
| Code count | **25 -> 30** |
| Live verification projects | `IndonesianHC-Complete` (correctness), `Malay Parsing-20230810withHC` (scale) |
| Excluded project | **`Sena 3`** -- reports engine `XAmple`; this feature's own engine gate refuses it |
| Standing test | `HCParser_DoesNotLoadXCore` must stay green |

---

## 6. Next-step proposals

Every proposal (FR-057):

- names a tool that **exists** -- 0 exceptions (SC-019)
- carries a **mandatory** cost estimate; `"unbounded"` is legitimate
- carries arguments the caller can use **directly**, without reconstruction
- never proposes a step the project cannot reach, **including any filing step**,
  which at CP3 is every session
- proposes the **static scan before the trace** where both are candidates,
  because it is cheaper than the trace it may make unnecessary

Fires on exactly four conditions (FR-056): a single-word request that misses the
fast-path window; a batch that enters grammar loading and stays there; a
terminal failure; a bounded measurement that exceeds its bound. **Not** on a
request answered inline, and **not** attached to every response (SC-018).
