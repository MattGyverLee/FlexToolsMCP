# Lock-Site Inventory (mechanical enumeration)

**Feature:** specs/shared-mode-access (issue #93)
**Produced:** 2026-09-07 by lex-qc, cycle 7
**Status:** DURABLE / LIVING ARTIFACT. Re-run the greps below and diff against
this table before claiming any lock-related sweep is complete.

---

## Why this document exists

Three consecutive judgement-based "sibling sweeps" for one bug class each
declared themselves complete and each was falsified by the next reviewer:

- commit `6677fd8` asserted "no sibling sites found" -> missed `execution.py:2030`
- commit `ad1d50c` was the corrective sweep -> missed
  `project_discovery.py:372-377`, four lines below the branch it was editing

Prose claims of completeness are no longer accepted as evidence. This table is
the replacement: a mechanical enumeration that a later reviewer can re-run,
re-derive, and diff line-by-line. **A row justified as CORRECT is as load-bearing
as a row marked DEFECT** -- the CORRECT rows are what make the absence of a
finding checkable rather than merely asserted.

---

## The bug class

**Code that concludes something about project accessibility from the BARE
EXISTENCE of a `.fwdata.lock` file, rather than from `probe_project_access()`'s
composed verdict.** A lock file on disk is compatible with at least three
materially different realities: a *stale* lock (the claiming PID is dead), a
*live `open_shared`* holder (FieldWorks has it open with project sharing on, so
writes through the shared commit log are fine), and a *genuine exclusive hold*
(`open_exclusive` / `held_by_other`). Collapsing all three into a single boolean
"locked" produces false blocking advice -- most damagingly "Close FieldWorks",
which is wrong when nothing is running to close and wrong again when the holder
is a leftover python process rather than FieldWorks.

The canonical correct semantics live in
`src/flextoolsmcp/server/project_access.py:327-395` (`probe_project_access`).
Its documented decision table maps an **UNKNOWN / unparseable holder** to
**`open_exclusive`** -- erring *safe* -- explicitly **NOT** to `stale_lock`.
Any site that maps an unknown holder to "stale" is the exact inversion of the
canonical fallback and is a DEFECT by construction.

Absence of a lock file concluding `free` is correct and is not part of the bug
class. Reading a lock file's *contents* (holder PID / ProcessName) and composing
liveness is correct. Only *bare existence -> accessibility conclusion* is the
defect shape.

---

## Reproduction commands and raw counts

Run from the repository root (`D:\Github\_Projects\_LEX\FlexToolsMCP`).

```
grep -rn "\.lock" --include=*.py src/
```
**26 hits across 6 files** -- matches the stated baseline exactly.
Files: `handlers/diagnostic_health.py`, `handlers/execution.py`,
`project_access.py`, `project_discovery.py`, `response_models.py`, `server.py`.

```
grep -rn "check_project_locked\|read_lock_holder\|_lock_path_for\|sweep_stale_locks" --include=*.py src/
```
**21 hits across 5 files** (`handlers/diagnostic_health.py`,
`handlers/execution.py`, `project_access.py`, `project_discovery.py`,
`server.py`).

```
grep -rni "lock" --include=*.py src/flextoolsmcp/server/handlers/
```
**152 hits across 6 files.** Note this count is dominated by false friends:
`_build_*_block`, "log block", "non-blocking advisory", "HARD BLOCK",
`get_project_write_lock` (an asyncio in-process mutex, unrelated to
`.fwdata.lock`). The genuinely lock-file-related subset is enumerated below;
the rest are recorded here only so a future reviewer knows the 152 was read and
triaged rather than skimmed.

Test-side cross-check:
```
grep -rn "Stale lock detected" --include=*.py .
```
**3 hits:** `src/.../project_discovery.py:374` (the emitter),
`tests/test_shared_mode_access.py:442` (a docstring), and
`tests/test_shared_mode_access.py:451` (the assertion).
```
grep -c "Stale lock detected" tests/test_startup_lock_sweep.py
```
**0.** See the TEST section for why this matters.

---

## Table: every lock site in `src/`

Legend for **BLOCKING-CLAIM?**: does the site assert, to a human or to a machine
consumer, that the project is locked / inaccessible / requires user action?

### Canonical layer -- `src/flextoolsmcp/server/project_access.py`

| file:line | what it reads | what it concludes | user-facing wording | BLOCKING-CLAIM? | verdict | justification |
|---|---|---|---|---|---|---|
| `project_access.py:96-97` | nothing (pure path construction, `_lock_path_for`) | nothing | none | no | **CORRECT** | Builds the `<proj>.fwdata.lock` path; concludes nothing, so cannot exhibit the bug class. |
| `project_access.py:100-137` | `lock_path.is_file()`, then the file's JSON | `None` = no lock file at all; `LockHolder` with `None` fields = present-but-unparseable | none | no | **CORRECT** | Deliberately distinguishes "absent" from "unreadable" instead of collapsing both; that distinction is what lets callers err safe. |
| `project_access.py:115-117` | `lock_path.is_file()` | early-returns `None` on absence | none | no | **CORRECT** | Absence -> nothing to hold. Not the bug class (only *existence*-based conclusions are). |
| `project_access.py:250-262` | `verdict == "open_exclusive"` plus `holder is None or holder.pid is None` | holder unidentifiable -> "treating it as exclusively held" | "A .fwdata.lock file is present but unreadable, so the holder could not be identified. Treating it as exclusively held. If no FieldWorks or python process is actually running, the lock is stale -- delete it manually and retry. This server never deletes lock files." | yes (correctly) | **CORRECT** | Reference wording for the unknown-holder case: asserts exclusivity (safe), declines to name FieldWorks, offers "stale" only as a conditional the user must verify. `project_discovery.py:372-377` should read like this and does not. |
| `project_access.py:263-273` | `verdict == "held_by_other"` plus holder facts | live non-FieldWorks holder | "The lock is held by a live process that is not FieldWorks: PID N (name) ... enabling project sharing does not resolve it. Wait for that process to exit (or end it), then retry." | yes (correctly) | **CORRECT** | Never says "Close FieldWorks", because FieldWorks is provably not the holder. |
| `project_access.py:305-320` | `verdict == "stale_lock"` plus `holder.pid` | dead holder -> retry will likely succeed | "A .fwdata.lock file is present naming PID N, but that process is no longer running, so this is a stale lock, not a live collision. LCM treats a stale lock as acquirable ... simply retrying ... This server never deletes lock files ..." | no (explicitly non-blocking) | **CORRECT** | Reference wording for a *proven* stale lock. Reachable only when a PID was parsed and found dead -- never from bare existence. |
| `project_access.py:327-395` | lock existence + holder JSON + PID liveness + `LexiconSettings.plsx` | one of free / open_shared / open_exclusive / stale_lock / held_by_other | none directly | no | **CORRECT** | The canonical composer. Documented fallback: unknown holder -> `open_exclusive`. Every other site in this table is judged against this one. |
| `project_access.py:362-370` | `lock_path.is_file()` | absent -> `"free"` | none | no | **CORRECT** | Absence-based, not existence-based. |
| `project_access.py:372-388` | `read_lock_holder()` + `_pid_is_alive()` + sharing flag | the five-way verdict | none | no | **CORRECT** | `pid_alive is None` (unknown) falls to the `else` -> `open_exclusive`, exactly as documented. |

### Primitive -- `src/flextoolsmcp/server/project_discovery.py`

| file:line | what it reads | what it concludes | user-facing wording | BLOCKING-CLAIM? | verdict | justification |
|---|---|---|---|---|---|---|
| `project_discovery.py:262-274` | `lock.exists()` | returns the `Path` if a lock file exists, else `None` | none | no (but the *name* implies one) | **DEFECT (P3, naming/contract)** | The body is honest about what it does, but its name -- `check_project_locked` -- asserts a conclusion the return value does not support. Two of the three historical misses (`execution.py:2042`, and the original #33 write gate) came from callers trusting the name. The hazard is the name and docstring, not the code. |
| `project_discovery.py:291-330` | `os.listdir` of the projects dir | which projects have lock files | (docstring only) | no | **CORRECT** | Enumeration scaffold; the per-lock conclusions are the rows below. |
| `project_discovery.py:319` | -- | imports `read_lock_holder`, `_pid_is_alive` | none | no | **CORRECT** | Deferred import breaking a real circular dependency; documented in place. |
| `project_discovery.py:333-335` | `lock_path.exists()` | skip projects with no lock | none | no | **CORRECT** | Loop gate only; makes no accessibility claim. |
| `project_discovery.py:337-343` | `read_lock_holder()` + `lock_path.stat().st_mtime` | holder identity + lock age | age string embedded in every message | no | **CORRECT** | Fact gathering. (Age comes from mtime here vs. .NET ticks in `probe_project_access` -- a cosmetic inconsistency, not this bug class.) |
| `project_discovery.py:344-354` | holder PID present **and** `_pid_is_alive(pid)` is True | live holder -> the user must close FieldWorks | "Lock detected: `<path>` (N min old), held by `<ProcessName>` (PID N), process still running. **Close FieldWorks** (or delete the .lock file only if no FW process is running) to allow write operations on this project." | **yes** | **DEFECT (P2)** | Evidence is a live PID, not bare existence, so this is not the *narrow* bug class -- but the conclusion is still composed without consulting `ProcessName` or the sharing flag. It says "Close FieldWorks" when `holder_desc` may literally read "held by python (PID N)" (`held_by_other`, where `build_access_remedy` states that closing FieldWorks does **not** resolve it), and it declares writes impossible when the holder may be FieldWorks with sharing ON (`open_shared`), where CP4 deliberately *permits* the write. Same wording-drift failure `build_lock_diagnosis()` exists to prevent. |
| `project_discovery.py:355-371` | holder PID present **and** dead | proven stale -> no action required | "Lock detected: ... process no longer running (stale). This is a stale lock: LCM treats it as acquirable, so the next write attempt should succeed without any action. Delete the .lock file manually only if writes keep failing ..." | no (correctly non-blocking) | **CORRECT** | This is `ad1d50c`'s fix and it is right: liveness proven false before "stale" is claimed, no "Close FieldWorks", manual deletion demoted to a last resort. Matches `build_lock_diagnosis()`'s stale text in substance. |
| `project_discovery.py:372-377` (`else:` at 372, message at 373-377) | **bare `lock_path.exists()` only** -- reached when `holder is None` or `holder.pid is None`, i.e. the lock file is empty / non-JSON / missing `PID` | (a) the lock is **stale**, and simultaneously (b) FieldWorks is running and must be closed | "**Stale lock detected**: `<path>` (N min old). **Close FieldWorks** (or delete the .lock file only if no FW process is running) to allow write operations on this project." | **yes** | **DEFECT (P1) -- CONFIRMED** | The canonical bug. Three independent faults: (1) it declares "Stale" from an unknown holder, the exact **inversion** of `probe_project_access`'s documented fallback (unknown -> `open_exclusive`, err safe); (2) it is self-contradictory -- a stale lock by definition has no live holder, so "Close FieldWorks" cannot coexist with "Stale"; (3) it names FieldWorks specifically when the file contained no `ProcessName` at all. `build_access_remedy`'s unknown-holder branch (`project_access.py:250-262`) already contains the correct text for this exact state. The message reaches users through two channels (see the two AMPLIFIER rows below). |
| `project_discovery.py:379-380` | -- | logs at WARNING and accumulates whichever `msg` was built | relays the above verbatim | inherits | **CORRECT (relay)** | Emission point; carries whatever the branches above produced. Fixing the branches fixes this. |

### Consumers -- `src/flextoolsmcp/server/handlers/execution.py`

| file:line | what it reads | what it concludes | user-facing wording | BLOCKING-CLAIM? | verdict | justification |
|---|---|---|---|---|---|---|
| `execution.py:1198-1216` | the subprocess's **error string** (`in use by another program` / `LcmFileLockedException` / `FP_FileLockedError` / `currently in use`) -- no lock file read | the project is locked | "Most common cause: FieldWorks GUI is open with this project. Close FieldWorks and retry. Other causes: another MCP session has the project open, or a stuck `.fwdata.lock` file ... Delete it only when sure no FW process is running." | yes | **CORRECT (with caveat)** | Outside the bug class: the evidence is an actual LCM refusal, not a file's existence, so a blocking claim is warranted. Caveat for the record: this generic text is also what survives when the probe raises **or** returns `free`/`open_shared` (pinned by `test_shared_mode_lock_diagnosis.py:110-116`) -- i.e. LCM refused but the probe disagrees. The hedged "most common cause" phrasing is the only thing keeping that honest. Not a defect today; revisit if the fallback is ever tightened. |
| `execution.py:1229-1275` | `probe_project_access()` verdict via `build_lock_diagnosis()` / `build_access_remedy()` | replaces the generic hint with a verdict-specific one | delegated entirely to `project_access.py` | yes (verdict-driven) | **CORRECT** | The CP3 enrichment. Delegates all wording to the canonical module so CP3 and CP4 cannot drift; degrades silently to the generic hint on any failure; a single atomic `diag.update(extra)` so no partial payload shape can escape. |
| `execution.py:1844` | nothing (syntax-error fallback) | `"would_require": {"write_enabled": False, "project_lock": False}` | none | no | **N-A** | A declaration of what the *script* would require, not a claim about the project's state. Same field name, different subject; recorded so a future grep-driven reviewer does not re-flag it. |
| `execution.py:2035-2047` | `check_project_locked(project_name)` -- **bare `.exists()`** | `project_lock["locked"] = True/False` in the `validate_only` payload | machine-readable `locked` field, plus `lock_file` | **yes (machine-facing)** | **DEFECT (P2)** | The site `6677fd8` missed. `locked: true` is emitted for a stale lock and for a live `open_shared` holder -- both states in which a write would in fact succeed under CP4's gate. The enrichment on the following lines mitigates but does not correct it: `locked` remains the field named for the question callers ask, and an LLM consumer reading `locked: true` will report the project unavailable regardless of an adjacent `blocking: false`. |
| `execution.py:2049-2076` | `probe_project_access()` | additively sets `verdict`, `sharing_enabled`, `blocking` (True only for `open_exclusive`/`held_by_other`) | none (structured fields) | no | **CORRECT (incomplete)** | This is `ad1d50c`'s enrichment and it is well-built: additive, verdict-driven, defensive try/except with a debug log, `blocking` computed from exactly the two refusing verdicts. Recorded gap (not a defect in itself): when the probe raises, `verdict`/`blocking` are **absent** and the payload silently degrades to the bare `locked` boolean of the row above, with nothing signalling that the qualifier is missing. |
| `execution.py:2091` | -- | attaches `project_lock` to the response | -- | inherits | **CORRECT (relay)** | Emission point for the two rows above. |
| `execution.py:4162-4187` | `probe_project_access(project_name)`, computed once, only when `needs_lock` | `_access`; `_live_fw_peer` when the verdict is `open_shared` | none | no | **CORRECT** | Single probe, ordered before the confirmation gate, computed only under write intent -- read-only runs are never gated, which is the point of CP4 (T4.3). |
| `execution.py:4268-4302` | `_access.verdict in ("open_exclusive", "held_by_other")` | refuse the write | `project_locked` error with `guidance=build_access_remedy(...)`, plus `verdict`, `sharing_enabled`, `holder_pid`, `holder_process`, `remedy` | **yes (correctly)** | **CORRECT** | The reference consumer. Dispatches on the composed verdict, not on file existence; refuses exactly the two verdicts a write cannot survive; ships the probe facts so the caller can tell the 20-second FLEx fix apart from a real process collision. |
| `execution.py:4272` | `check_project_locked(project_name)` | the lock file's **path**, for reporting only | populates `lock_file_path` | no | **CORRECT** | Uses the existence-based primitive purely to fill in a path, *after* the verdict has already decided. This is the safe way to call `check_project_locked`. |
| `execution.py:4290-4293` | `_remedy or "Close FieldWorks, then retry. Read-only operations do not require closing FieldWorks."` | fallback guidance | that literal | yes | **N-A (unreachable)** | `build_access_remedy()` returns non-`None` for **both** verdicts that can reach this branch (`open_exclusive` -> unknown-holder text or `ENABLE_SHARING_REMEDY`; `held_by_other` -> its own text), so the `or` arm is dead. Harmless at runtime but misleading to a reader, since the dead string is the exact wording this bug class is about. |
| `execution.py:4306-4323` | `_access.verdict == "open_shared"` | proceed, attach a `shared_mode` advisory | "FieldWorks has this project open with sharing enabled, so this run attached as a non-master LCM peer ... Custom-field and writing-system changes are NOT safe from a peer ..." | no (correctly permissive) | **CORRECT** | The inverse of the bug class done right: a lock file exists and the write proceeds anyway, with the caveat that actually matters. |
| `execution.py:4325-4342` | `_access.verdict == "stale_lock"` | proceed | "A .fwdata.lock file is present but the process that claimed it is no longer running, so the lock is stale. Proceeding: LCM treats a stale lock as acquirable. This server never deletes lock files." | no (correctly permissive) | **CORRECT** | Reached only via a probe-proven dead PID, never from bare existence. Contrast with `project_discovery.py:372-377`, which uses near-identical "stale" vocabulary from *no* evidence. |
| `execution.py:4448-4451` | `_shared_mode is not None` | surfaces the advisory on the result | relays the two notes above | no | **CORRECT (relay)** | Emission point. |
| `execution.py:4460-4470` | subprocess error | routes to `_diagnose_project_open_error` | relays rows 1-2 of this section | inherits | **CORRECT (relay)** | Emission point. |
| `execution.py:4166`, `4178`, `4193`, `4347`, `4366-4369` | `needs_lock`, `get_project_write_lock` | in-process asyncio mutex serializing this server's own writes | none | no | **N-A** | `get_project_write_lock` is an in-process concurrency primitive with no relationship to `.fwdata.lock`. Recorded because `grep -i lock` returns it and a future reviewer will otherwise re-triage it from scratch. |

### Relays / reporting -- `diagnostic_health.py`, `response_models.py`, `server.py`

| file:line | what it reads | what it concludes | user-facing wording | BLOCKING-CLAIM? | verdict | justification |
|---|---|---|---|---|---|---|
| `handlers/diagnostic_health.py:245` | `api_index.startup_lock_warnings` | appends the startup sweep's strings to `flextools_health` warnings | relays `sweep_stale_locks()` output **verbatim** | inherits | **CORRECT (relay) -- AMPLIFIER** | Makes no claim of its own, but it is the channel by which `project_discovery.py:372-377`'s wording reaches users inside a diagnostic tool. Listed so the blast radius of the P1 defect is on the record; fixing the emitter fixes this. |
| `handlers/diagnostic_health.py:276-310` | `probe_project_access(session_state.project_name)` | full verdict block: `verdict`, `sharing_enabled`, `holder`, `lock_age_seconds` | structured, no prose | no | **CORRECT** | Explicitly replaced an older `locked: bool` block with the composed verdict -- the model `execution.py:2035-2047` should follow. |
| `handlers/diagnostic_health.py:293`, `309` | `access.lock_age_seconds` | reports age | structured | no | **CORRECT** | Fact reporting only. |
| `response_models.py:281-301` (`ProjectLockedDetail`) | -- | payload schema for `project_locked` | docstring: "the mere existence of a .fwdata.lock file is no longer the reason for this rejection -- it is now raised only for ... `open_exclusive` and `held_by_other`" | no | **CORRECT** | The schema encodes the correct contract, and `extra="forbid"` meant the probe fields had to be modelled before the handler could send them. This docstring is the written statement of the rule the P1 defect violates. |
| `server.py:1043-1052` | `sweep_stale_locks()` at startup | stores warnings on `api_index.startup_lock_warnings`, logs each at WARNING | relays verbatim | inherits | **CORRECT (relay) -- AMPLIFIER** | Second delivery channel for the P1 defect (the server log). Log-only, never deletes -- correct on that axis. |

---

## Table: TEST assertions in the same bug class

A test can pin bad wording in place, which is how a defect survives a corrective
sweep. Enumerated on the same terms.

| file:line | what it asserts | BLOCKING-CLAIM pinned? | verdict | justification |
|---|---|---|---|---|
| `tests/test_shared_mode_access.py:440-453` | writes an **empty** lock file, then asserts `"Stale lock detected" in warnings[0]`. Docstring: *"Regression guard: tests/test_startup_lock_sweep.py's empty-lock fixtures must keep matching the original 'Stale lock detected' wording (no holder info available)."* | **yes** | **DEFECT (P1-companion) -- assertion by false comment** | The docstring's justification is **factually false, and independently verified false**: `grep -c "Stale lock detected" tests/test_startup_lock_sweep.py` returns **0**. That file's only wording assertions are in `test_lock_file_detected` (lines 47-62), which check for the project name and the substring `".fwdata.lock"` -- both deliberately wording-agnostic and both satisfied by any corrected message. The test therefore pins the exact P1 defect wording on the strength of a dependency that does not exist. This is plausibly the mechanism by which `ad1d50c` corrected the branch four lines above and left this one: the test made the bad wording look load-bearing. |
| `tests/test_shared_mode_access.py:417` | `"no longer running (stale)" in warnings[0]` for a dead, identified PID | no | **CORRECT** | Pins the *correct* dead-holder wording; evidence-backed. |
| `tests/test_shared_mode_access.py:405-414` | `"python"`, `"54480"`, `"still running"` for a live non-FieldWorks holder | no | **CORRECT (note)** | Asserts only the facts, not the remedy -- so it does **not** pin the "Close FieldWorks" text flagged at `project_discovery.py:344-354`. The P2 fix is therefore test-unblocked. |
| `tests/test_shared_mode_access.py:274`, `293` | `access.verdict == "stale_lock"` for probe-level dead-PID cases | no | **CORRECT** | Verdict-level, canonical. |
| `tests/test_startup_lock_sweep.py:47-62` | project name + `".fwdata.lock"` substring appear in the warning | no | **CORRECT** | Deliberately wording-agnostic. **This is the file the `:442` docstring misrepresents.** Any reworded message that still names the project and the lock file passes unchanged. |
| `tests/test_startup_lock_sweep.py:100-111` | a WARNING-level record mentioning the project is emitted | no | **CORRECT** | Level and subject only, no wording. |
| `tests/test_rejection_payloads.py:484` | `"Close FieldWorks" in diag["hint"]` for an `in use by another program` LCM error | yes | **CORRECT** | Pins the generic pre-probe hint at `execution.py:1206-1215`, which is exception-evidenced, not existence-evidenced. Legitimate in class terms. |
| `tests/test_shared_mode_lock_diagnosis.py:104` | the generic `"Close FieldWorks"` hint survives when the probe **raises** | yes | **CORRECT** | Pins the documented degrade-to-generic path, and additionally asserts no probe facts leak onto the payload. |
| `tests/test_shared_mode_lock_diagnosis.py:110-116` | the generic `"Close FieldWorks"` hint for verdicts `free` and `open_shared` | yes | **CORRECT (with caveat)** | Matches `build_lock_diagnosis()`'s documented contract. Caveat mirrors the `execution.py:1198-1216` row: it pins "Close FieldWorks" for an `open_shared` project, where FieldWorks being open is precisely *not* the problem. Defensible only because LCM has already refused the open. Flagged for visibility, not for change in this cycle. |
| `tests/test_shared_mode_lock_diagnosis.py:67-79` | the stale-lock diagnosis names the dead PID, contains `"stale"`, and `remedy is None` | no | **CORRECT** | Pins the canonical stale text and the deliberate `remedy is None`. |
| `tests/test_shared_mode_lock_diagnosis.py:81-91` | `held_by_other` names the PID/process and says `"does not resolve it"` | yes (correctly) | **CORRECT** | Pins the correct non-FieldWorks wording. |
| `tests/test_shared_mode_write_gate.py:243` | `advisory["verdict"] == "stale_lock"` | no | **CORRECT** | Verdict-level. |

**Assertion-by-comment audit result:** exactly one instance found repo-wide --
`tests/test_shared_mode_access.py:442`. It was checked by grepping the file it
names; the claim is false. No other lock-related test justifies an assertion by
citing a sibling test file.

---

## Summary of findings

| Priority | Site | One-line |
|---|---|---|
| **P1** | `project_discovery.py:372-377` | "Stale lock detected" + "Close FieldWorks" from bare existence when the holder is unknown -- inverts `probe_project_access`'s documented safe fallback. |
| **P1-companion** | `tests/test_shared_mode_access.py:440-453` | Pins the P1 wording via a docstring citing a dependency that provably does not exist. |
| **P2** | `execution.py:2035-2047` | `project_lock["locked"]` is bare `.exists()`; true for stale and `open_shared` locks that do not block a write. |
| **P2** | `project_discovery.py:344-354` | Live-holder branch says "Close FieldWorks" without consulting `ProcessName` or the sharing flag; wrong for `held_by_other` and for `open_shared`. |
| **P3** | `project_discovery.py:262-274` | `check_project_locked`'s name asserts a conclusion its return value does not support; proximate cause of two of the three historical misses. |
| note | `execution.py:4290-4293` | Dead `or "Close FieldWorks..."` fallback -- unreachable, but it is the exact wording under audit sitting in the reference consumer. |
| note | `execution.py:2049-2076` | Enrichment vanishes silently on probe failure, leaving the bare `locked` boolean unqualified. |

**Totals: 38 sites enumerated (26 in `src/`, 12 in `tests/`). 4 DEFECT, 2 notes,
the remainder CORRECT / N-A.**

---

## How to re-verify this document

1. Re-run the four grep commands above; confirm the counts (26 / 21 / 152 / 0).
2. For each row, open `file:line` and confirm the "what it reads" column against
   the code. A row whose line numbers have drifted must be re-anchored, not
   deleted.
3. Any new `.lock` hit not present in this table is an un-audited site: add a row
   before claiming a sweep is complete.
4. Do **not** replace this table with a prose assertion that the sweep is done.
   That method has failed three times and has been retired.
