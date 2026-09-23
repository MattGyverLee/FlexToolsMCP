# Contract: the run artifact

**Date**: 2026-09-22 · **Spec**: [`../spec.md`](../spec.md) · **Data model**: [`../data-model.md`](../data-model.md)

Phase 1 output. **This is a forward commitment.** CP4 and CP5 both read this
artifact without reopening the FieldWorks project, so a shape chosen loosely
here is migrated twice later. It is frozen at the end of the plan's Phase 2,
before anything that consumes it is written.

---

## 1. Layout

CP2b's layout, **as shipped** (`server/parse/record.py:34-42`), plus exactly
one net-new file:

```text
<record dir>/<run_id>/
├── meta.json        # the durable run record -- REWRITTEN whole on stage change
├── results.jsonl    # one line per completed word -- APPENDED and flushed
├── words.txt        # the resolved word list -- NET-NEW at CP3
└── traces/<n>.xml   # trace payloads, out of line, only where a drill-down was taken
```

`<record dir>` is `record.get_record_dir()`, overridable by
`FLEXTOOLSMCP_PARSE_RECORD_DIR`.

### Why this and not the parent spec's listing

The parent spec's section 5.5 names `run.json`, a flat `trace.txt` and four
sandbox files. **That listing is the thing that is wrong** (D-6): it was
written before CP2b existed and describes a layout no code has ever matched.
CP2b shipped `record.py` at `e5afbfd` with these names, and that code is what
CP3 is required to consume without adding a second execution model.

Renaming shipped files at CP3 would be churn on an artifact CP4 and CP5 both
read, to satisfy a listing nothing ever wrote. **CP3 corrects the parent spec
instead**, and that correction lands with CP3 rather than being left as a
silent divergence -- otherwise the next reader comparing the spec to the disk
concludes the implementation drifted, when the opposite happened.

Out-of-line traces are also better on their own merits: a trace payload is XML
measured in tens or hundreds of kilobytes, and a flat `trace.txt` would force
every run to carry every trace in one file.

---

## 2. `run_id`

**32 lowercase hex characters**, minted by `record.new_run_id()`
(`secrets.token_hex(16)`), validated by `\A[0-9a-f]{32}\Z` on every path
construction.

- **Carries no timestamp.** The source document specified a
  timestamp-plus-suffix form; CP2b mints random hex. FR-022 keeps the shipped
  form, and it is **not** re-minted at CP3.
- **Server-issued, always.** It is a path component. A caller-supplied string
  would make directory traversal reachable from a tool argument.

---

## 3. `meta.json`

Rewritten whole on every stage change, via temp file then `os.replace` --
atomic on both POSIX and Windows, so a status poll landing mid-write reads one
whole state or the other, never a half-written file.

**CP2b fields** (unchanged): `run_id`, `stage`, `project_name`, `words_total`,
`words_completed`, `created_at`, `updated_at`, `interleaved_by`, `failure`,
`stage_at_cancel`.

**CP3 additions**: `scope_fingerprint`, `engine_at_submission`,
`engine_changed_midjob`, `load_error_baseline`, `counters`,
`counter_divergences`, `words_path`.

Field meanings are in [`../data-model.md`](../data-model.md) sections 3 and 4.

**Written incrementally** (FR-016), not only at completion. A run that dies
during grammar loading and never reaches a first word still states its terminal
state and the stage it died in.

**Terminal failure** carries exactly one of `out_of_memory | crashed |
cancelled`.

**An engine change mid-job is a warning on the summary, not a refusal**
(FR-024). The engine recorded at submission is the one the results are labelled
with.

---

## 4. `results.jsonl`

One JSON object per line. **Appended, flushed and `fsync`ed before the call
returns** -- already true of `record.append_result`.

The flush is the requirement, not an optimization: a buffered write loses the
tail of a killed run, and the tail is exactly what matters, since a run is
usually killed because of what it was doing at the end.

**Readers must tolerate a malformed trailing line.** A run killed mid-write can
leave a partial final line; everything before it stays valid.
`record.iter_results` already skips rather than raises, and **CP4 and CP5
readers must do the same.** Raising would throw away the results the record
exists to preserve.

Line shape: [`../data-model.md`](../data-model.md) section 5.

---

## 5. `words.txt`

The resolved word list. UTF-8, NFC, one word per line, in resolved order
(descending occurrence, then alphabetical, truncated after ordering).

**The only genuinely net-new file at CP3.** The source document also calls
`results.jsonl` net-new; it is not -- it shipped with CP2b. The word list is
the one thing with no persistence today.

---

## 6. `traces/<n>.xml`

Out-of-line trace payloads. `<n>` is an **int supplied by the runner**, never a
caller string, so the filename cannot carry traversal.

Written **only where a drill-down was taken** (FR-047: capped at a user-chosen
10-20 per session, never auto-traced in bulk). A completed batch over ten
thousand words normally has an empty or absent `traces/` directory.

---

## 7. What is NOT written

**Sandbox-spine files are not written, and are not created empty** (FR-015).
That is CP5's spine. `flextools_parse_log` returns a typed
not-applicable-for-this-spine response naming the spine and the checkpoint that
will fill it -- never an empty section, which reads as "nothing happened."

**No live data-model object reference is ever serialized** (FR-021). The
durable signature and enough rendered text to report without reopening the
project are serialized instead; live references are kept only within the run.

**Nothing here is written to the FieldWorks project.** The artifact is
server-side only (FR-063).

---

## 8. Retention

**Newest 20 runs per project**, ordered by **recorded creation time** --
`meta.json`'s `created_at` (FR-022).

Two mechanisms are explicitly rejected:

- **Not a lexicographic sort of directory names.** The existing backup pruner
  (`server/backup.py:50`) sorts names, and its own comment records that this is
  chronological *only because* backup directories are timestamp-named. Run
  directories are opaque hex, so the same sort would prune in effectively
  random order. FR-022 adopts the pruner's **policy** and rejects its
  **mechanism**.
- **Not `record.list_run_ids()`'s `st_mtime` order.** That ordering is correct
  for its own caller (naming the handles that exist), but mtime is bumped by
  later activity such as a drill-down trace landing in `traces/`, so it is not
  creation order.

A retention implementation that sorts names fails its test.

---

## 9. Compatibility rules for CP4 and CP5

Stated here because this is the file those checkpoints will read.

1. **Additive fields only.** A reader must ignore unknown keys in `meta.json`
   and in a `results.jsonl` line.
2. **Tolerate a truncated final line** in `results.jsonl`, always.
3. **`run_id` form is fixed** -- 32 hex, no timestamp. Do not derive ordering
   from it.
4. **Do not rebuild the segment-occurrence join.** It is built once at CP3 and
   structured for reuse; CP4's deletion projection is the same join for the
   opposite purpose, and a CP4 that rebuilds it is a review finding (FR-043).
5. **Do not grow a second project-state probe.** CP3's is built once with three
   named consumers, and CP4's deletion-projection precondition is the third
   (FR-004).
6. **`traces/` may be absent.** An empty drill-down history is the normal case.
