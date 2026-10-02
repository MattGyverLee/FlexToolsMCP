# CP5 Scope -- "close FLEx briefly" gate (cycle 5, research only)

Two parallel read-only passes: a code-surface scope and a lex-domain
classification. No code written. Feeds lex-lead's CP5 planning.

## 1. Verdict: CP5 is justified, and for a sharper reason than SPEC states

SPEC Section 3 lists exclusive-only operations as one table. It is really
**two failure classes**, and conflating them understates the danger:

- **Class A -- LCM refuses outright.** Data migration
  (`SharedXMLBackendProvider.cs:108-111`, `LcmDataMigrationForbiddenException`)
  and project rename (`:637-641`, refuses when `OtherApplicationsConnectedCount > 0`).
  Safe by construction: the user gets an exception, not corruption.
- **Class B -- LCM permits it and the write is silently swallowed.** Custom
  field create/modify/delete. This is the class that needs a gate, because
  nothing else will ever catch it.

### The Class B mechanism (re-derived from liblcm source, not taken on trust)

`PerformCommit` is the only path that writes `<AdditionalFields>` to the XML
file, and it is gated `if (metadata.Master == m_peerID)`
(`SharedXMLBackendProvider.cs:478`, also `:408`). A non-master peer's
`HaveAnyModifiedCustomProperties` (`BackendProvider.cs:506-515`) clears and
rebuilds `m_extantCustomFields` from the live MDC on every commit, so the peer's
own bookkeeping believes the field was recorded -- then the declaration is
discarded. The next commit sees no diff and never retries. `CommitLogRecord`
(`CommitLogRecord.cs:17-49`) has no field for custom-field schema at all, so it
cannot even ride along to the master.

Net effect: no exception, no error, no second chance. The field simply does not
exist after restart.

### Strongest precedent: FieldWorks gates this itself

`XWorksViewBase.cs:715` refuses to open the Custom Fields dialog when
`SharedBackendServices.AreMultipleApplicationsConnected(cache)` is true. CP5 is
not inventing a restriction -- it is matching one FLEx already enforces in its
own UI.

Note also that FLEx's `ProjectsInUseLocally` guard (`FieldWorks.cs:813-817`,
used by `DeleteProject` at `:1988`) enumerates only .NET Remoting clients, so it
is **structurally blind to a pythonnet peer**. We cannot rely on FLEx to stop us.

## 2. Classification

| Operation class | Verdict | Confidence |
|---|---|---|
| Ordinary field edits (lexeme form, gloss, definition, citation) | Safe in shared mode | High |
| Create/delete entries and senses | Safe in shared mode | High |
| Custom field create/modify/delete | **Exclusive-only (Class B)** | High |
| Writing system add/change | **Exclusive-only**, mechanism inferred | Medium -- needs live test |
| Possibility lists (semantic domains, POS, morph types) | Probably safe | Medium -- absent from SPEC |
| Reversal index create/regenerate | Uncertain | Low-Med -- absent from SPEC |
| Bulk ops in one UnitOfWork | Safe; amplifies CP4's stale-backup caveat (SPEC.md:253-256) | Med-High |
| Data migration / version upgrade | **Exclusive-only (Class A)** | High |
| Config writes (LexiconSettings.plsx) | Out of scope -- settled "never write" (SPEC.md:77-78) | High |
| Filesystem ops (backup/restore/delete/rename) | **Exclusive-only (Class A)** | High |

## 3. Recommended SPEC amendments before T5.1

1. **Add `failure_class: refused | silently_lost`** to `EXCLUSIVE_ONLY_OPERATIONS`
   (T5.1) so the refusal payload and `docs/SHARED-MODE.md` can calibrate urgency.
   Class A needs no alarm ("LCM will tell you"); Class B needs the strongest
   warning available. Two-line addition to a table SPEC already plans to build.
2. **Split Section 3's table by failure class** rather than listing ten rows flat.
3. **Add possibility lists and reversal indexes explicitly**, even if the entry is
   "confirmed safe, not gated". Silence reads as "vetted" to a future maintainer,
   and that is the assumption CP5 exists to distrust.

## 4. Drift found in SPEC's CP5 tasks (would break T5.1/T5.5 if followed literally)

- **T5.5 says "bump the 16 codes wording".** It is **18** now, in three lockstep
  places: `docs/TOOL-CONTRACT.md:69`, `response_models.py:361`,
  `tests/test_response_contract.py:234` (+ `ALL_ERROR_CODES` at `:200-231`).
  CP5 makes 19.
- **T5.1 names `CustomFieldOperations.UpdateField`, which does not exist** in the
  flexicon 4.5.2 index. `SetFieldName` is the schema-mutating analogue.
- **Raw-LCM names in T5.1** (`AddCustomField`, `UpdateCustomField`,
  `RenameDatabase`, `FieldDescription`) have **zero occurrences in `src/`** --
  reachable only via user-submitted code, so T5.2 must detect them by AST, not
  from any existing table.
- **Unreachable Section 3 rows:** data migration (flexlibs sets
  `DisableDataMigration=True`), Send/Receive, and project backup/restore/delete
  have no callable surface in this MCP. Mark as unreachable, not gated.

## 5. Implementation seam

**`execution.py:4262`** -- between the CP4 `project_locked` refusal (`:4227-4261`)
and the `open_shared` advisory (`:4263-4299`).

Precedence matters: an exclusively-held project running a custom-field script
must get CP3's enable-sharing remedy, *not* CP5's "close FLEx". So the CP5 check
keys on `_live_fw_peer` / `verdict == "open_shared"` (`:4144`), never on
`_access is not None`. Inserting at `:4262` also puts the refusal before backup
(`:4301-4307`), before lock acquisition, before subprocess spawn.

**Open decision:** `_access` is computed only when `needs_lock` (`:4136`). An
exclusive-only op inside a script that somehow certifies read-only bypasses the
gate entirely. Needs an explicit ruling.

**CP3/CP5 message collision:** `build_lock_diagnosis` (`project_access.py:276-321`)
returns `None` for `open_shared`, so a post-hoc LCM failure on a shared project
falls back to the generic "Close FieldWorks and retry" (`execution.py:1207-1213`)
-- the exact message CP5 is meant to be the sole source of, minus the operation
name. Align the two strings.

**Stale pointer:** `project_access.py:283` cites the write gate as
`execution.py:4180`; it is `:4203-4299`. Do not copy that reference.

## 6. Contract chores (T5.5)

New detail model required -- `ProjectLockedDetail` cannot be reused
(`error_code` is `Literal["project_locked"]`, and it is `extra="forbid"`).
Closest structural siblings: `NestedUnitOfWorkDetail` (`response_models.py:263-275`)
and `HvoLiteralWriteRiskDetail` (`:343-357`). Reusable by copy: `verdict`,
`holder_pid`, `holder_process`, `guidance`. New: matched-operations list
(name/line/reason/evidence/failure_class) and the resume recipe.
Then `AnyDetail` union (`:364+`), `GOLDEN_FIXTURES` + `make_golden.py --regen`,
`TOOL-CONTRACT.md` row, `_ASSISTANCE_HINTS_BY_ERROR_CODE` (`session.py:35`).

## 7. Test template

Mirror `tests/test_shared_mode_write_gate.py` (15 tests). Reuse verbatim:
`_parse:55`, `_access(...):61`, `_stub_env:142`, `_stub_probe:172`,
`_allow_execution:176`, `_refuse_execution:187`, `_boom_lock`/`_boom_subprocess:112-117`,
`WRITE_ARGS:192`, `_run:201`. Patch `probe_project_access` on the
**`project_access` module object** (`:173`), not on `execution_mod`.

Cases: `open_shared` + exclusive-only -> refuse, no lock, no subprocess (the
boom-stub proof SPEC Verification step 3 requires); `open_shared` + ordinary
write -> proceeds; `free`/`stale_lock` + exclusive-only -> proceeds (no live
peer); read-only script naming an exclusive-only op -> not gated. Plus a
`RejectionEnvelope.model_validate(data, by_alias=True)` test.

## 8. Needs a human / live FLEx (cannot be settled from source)

1. **Writing-system add/change under shared mode** -- clobber, refusal, or
   reconcile? SPEC's cited lines did not resolve. Gates whether WS belongs in
   T5.1 at all.
2. **Possibility-list mutation with a live FLEx peer** -- peer-write test like
   live-cp4.md Experiment A, aimed at a `CmPossibilityList` item.
3. **Reversal index create/regenerate** -- uncovered anywhere in SPEC.
4. **The `open_shared` path against a real FLEx master** (`live-cp4.md:129-136`)
   -- still the largest unverified assumption under CP4 *and* CP5. Experiment A
   proved python-to-python peer writes, not python-peer-against-FLEx-master.
5. **CP5's own refuse -> close FLEx -> resubmit -> reopen cycle**
   (SPEC.md:358-360, Verification step 5).

Items 1-3 are genuinely open questions, not confirmations. If WS turns out to
reconcile safely, T5.1 shrinks.
