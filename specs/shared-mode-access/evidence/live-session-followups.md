# Follow-ups from the live FieldWorks session, 2026-09-08 (#93)

**Purpose:** a self-contained handoff. The live session is finished; these are
the three pieces of work it generated, deliberately deferred to fresh sessions.
Nothing here has been started.

**Read first:** `specs/shared-mode-access/evidence/live-cp4.md`, section
`# Session 2026-09-08`. Every claim below is backed by verbatim tool output
there, and findings are labelled `(a)`-`(m)` in that file. Cite those labels
rather than re-deriving.

**Commits from the session** (all on `main`):

```
87a0c35  CP3 and CP4 both PASS
9d125d1  incidental flexicon API findings
d619742  item 7 (Q3) live result
196a9c7  retract the manage-layouts reading of item 7
f6cbb2b  reframe item 7 SetName as a FLEx-derived field
f523965  item 6 (Q2) PASS -- settles the item 7 hypothesis
1168a7a  item 5 (Q1) -- peer WS change CRASHES FieldWorks
```

**Machine state left behind:**

- `Sena 3` is restored (gloss, reversal indexes, semantic domains, writing
  systems) **except** that `projectSharing` is still `"true"`. It began the
  session with sharing OFF. Item 4 part 1 (the CP3 checkpoint) cannot be
  reproduced until sharing is turned off again in the FLEx UI.
- FieldWorks is closed. It is safe to reopen `Sena 3`: the `fr` writing system
  is gone from the LCM model, the LDML store and `LexiconSettings.plsx`.
- Backups of the removed residue:
  `<session scratchpad>/ws-residue-backup/{fr.ldml,LexiconSettings.plsx.before}`.
  Also recoverable from the Recycle Bin. These can be discarded once nobody
  needs them.

---

## Task 1 -- resume the LEX crew

Invoke `/lex-lead` with a continuation brief. Two checkpoints are ready to sign
off on live evidence, and Section 3 needs reclassifying.

**What to tell lex-lead:**

- **CP3 -- sign off.** Item 4, both parts PASS. A sharing-OFF project held by a
  real FieldWorks process returns the enable-sharing recipe, not the generic
  close-FieldWorks hint (the exact SPEC.md:233-235 criterion). After enabling
  sharing the identical call proceeds.
- **CP4 -- sign off.** Items 1, 2 and 3 PASS, item 3 on all three legs including
  the human UI observation. This closes both gaps that `live-cp4.md` section 6
  listed as still owed: the `open_shared` path is now exercised live under a real
  FLEx master, and the probe has been tested against a genuine FieldWorks holder
  rather than a leftover python process (the "honest limitation" in section 5).
- **Section 3 reclassification:**
  - **Q1 (writing systems) -> Class A, must be refused.** Peer WS changes crash
    FieldWorks 9.3.10 (`NullReferenceException` in
    `WritingSystemListHandler.AddWritingSystemList`, `TextListeners.cs:286`).
    This is CP5-a's acceptance evidence, arriving before CP5 exists. The current
    advisory-note behaviour is inadequate: the note sits in a JSON field the
    user never sees and the consequence is an application crash.
  - **Q2 (possibility lists) -> Class A, safe.** Applied, visible in the FLEx
    UI, durable across a verified restart. No CP5 gate needed.
  - **Q3 (reversal indexes) -> remove from the Section 3 table entirely.** Not a
    shared-mode failure. Splits into two library fixes: an analysis-WS argument
    check on `ReversalIndexes.Create`, and a doc fix or removal for its
    `SetName`.
- **Three #93 code changes** (details in Task 2's FlexToolsMCP list): the
  `_pid_is_alive` false-positive, the blank `mutations_detected`, and the
  `ENABLE_SHARING_REMEDY` wording.
- **One retraction to be aware of** so it is not re-adopted: the reading that
  the peer-created reversal index was "visible in manage layouts but absent from
  the main view" was **withdrawn** (commit `196a9c7`). The layout list does not
  map to reversal indexes. The corrected finding is that the index was never
  visible anywhere in the FLEx UI.

---

## Task 2 -- file the issues

### `MattGyverLee/flexicon`

| # | Finding | Summary |
|---|---|---|
| 1 | (f) | `SemanticDomains.GetAll(recursive=False)` returns an interleaved list: 9 `ICmSemanticDomain` alternating with 9 child `list`s. The natural loop crashes on element 2. `recursive=True` is flat and homogeneous (1792/1792), so the defect is isolated to the non-recursive path. Expected: the 9 top-level domains, flat. |
| 2 | (g) | `GetName`/`GetAbbreviation` resolve through the analysis-**default** WS instead of falling back to `BestAnalysisAlternative`. In `Sena 3` (default analysis `pt`, SemDom names `en`-only) every shipped domain reads as `''`. Consequence: **`FindByName` cannot find any shipped domain**, which breaks the MCP's own curated `add-semantic-domain-to-sense` recipe. That recipe also says `project.SemanticDomain` (singular) where the access path is `project.SemanticDomains` -- confirm whether both are bound. |
| 3 | — | The same default-WS trap on the **write** side: `SetName(obj, x)` and `Create(name, ...)` write into the analysis-default WS, so an object renamed or created with the obvious call appears unchanged/unnamed to an English-reading user. Same root cause as (g); consider a shared fix. |
| 4 | (h) | `ReversalIndexes.Create` has a working duplicate-WS guard but **no analysis-vs-vernacular guard**, contradicting its own docstring. It accepted vernacular `seh` and produced an index invisible everywhere in the FLEx UI while still occupying that WS slot. Should refuse a non-analysis WS. |
| 5 | — | `ReversalIndexes.SetName` targets a field FLEx maintains as **derived** from the writing system. FLEx regenerates it in the default analysis WS on project open, so a default-WS write is discarded; an explicit-WS write survives but is never displayed, because the FLEx reversal UI labels by writing system, not by `Name`. Document as ineffective, or remove. |
| 6 | (i) | `report.Info` output is discarded entirely when an exception escapes -- the response comes back `"messages": []`. Every probe in this session needed defensive `try`/`except` purely to preserve progress output. Flush accumulated messages alongside the error. |
| 7 | (l) | `WritingSystemOperations.Delete` clears the LCM model but leaves `<tag>.ldml` and the `SharedSettings/LexiconSettings.plsx` entry on disk, and does not use the `trash/` mechanism FLEx itself uses. Risks FLEx re-ingesting a WS that LCM says does not exist -- and, given the Q1 crash, crashing again. Means `Create` is not cleanly reversible through the API. |
| 8 | (m) | Peer writes log no provenance: the WS change-log entry reads `Producer="???" ProducerVersion="unknown"` where FLEx records real values. |
| 9 | (e) | `project.Object(guid)` returns an uncast `ICmObject`, so `GetAllSenses` fails with `AttributeError: 'ICmObject' object has no attribute 'SensesOS'`. The MCP's **own** `hvo_stability` runtime primer prescribes exactly this pattern for crossing a call boundary without mentioning the required cast -- its worked example is not runnable as written for the common `ILexEntry` case. Fix the primer, and consider having `project.Object` return a cast object. |

Also worth raising: every write ran with `undoable=False` (finding (b)), so
per-operation rollback was unavailable for the whole session -- flexicon #236.
Confirm whether the MCP runner should be passing that at all.

### `MattGyverLee/FlexToolsMCP`

| # | Finding | Summary |
|---|---|---|
| 1 | **(k)** | `_pid_is_alive` reports a freshly-dead process as ALIVE. `project_access.py:161-178` treats a successful `OpenProcess` as proof of life, but Windows keeps a terminated process object alive while any handle remains open (here the crash reporter). After FieldWorks closed (0 processes; `tasklist` confirms PID gone) the probe still returned `open_shared` and the health warning asserted "process still running". Long-dead python locks classify correctly because they have been reaped, so **the bug is time-dependent and worst in the post-crash window -- exactly when `stale_lock` is needed**. Fix: follow `OpenProcess` with `GetExitCodeProcess`, treat anything but `STILL_ACTIVE` (259) as dead, and preserve the existing access-denied branch. Affects CP2/CP3/CP4/CP5. |
| 2 | (a)/(d) | `mutations_detected` / `mutating_calls_detected` never enumerate calls like `SetGloss`, so the Rung-3 refusal reads *"This run would mutate the database (0 mutation(s) detected)"* and tells the user to "Review `mutations_detected`" -- an empty array. The gate itself is **not** bypassable (verified with `confirmed=False`; it refused correctly), so this is a correctness/UX defect, not a safety hole. Related: `write_certification.is_certified_readonly` was `true` on every run that actually mutated. |
| 3 | — | `ENABLE_SHARING_REMEDY` overstates the reopen requirement. Proven from the lock file: a genuine FLEx reopen rewrites it (new PID + timestamp), and at item 4 part 2 it was byte-identical before and after the flag flip -- so FLEx never reopened, and the peer open succeeded anyway. The reopen matters for FLEx's own cache, not for the server's ability to attach. Soften the wording. |
| 4 | — | Operational note, not necessarily a bug: an MCP server restart silently voids a session's write-discovery state (`discovered_api_count` -> 0), so the first write afterwards is refused with `api_discovery_required`. Handled well -- the refusal inlines the full entity surface under `_inline_discovery` for single-round-trip recovery -- but worth documenting. |

---

## Task 3 -- Session 2 test plan

Beyond the original CP5-a test, three new tests fell out of this session. All
are short. See the expanded "Session 2" section of
`specs/shared-mode-access/evidence/live-session-checklist.md`.

1. **CP5-a** (original) -- `CustomFieldOperations.CreateField` with FLEx open
   must be refused with `requires_exclusive_access`; then succeed with FLEx
   closed. Note `Sena 3` already has custom fields (`Plural`, `Singular` on
   LexEntry; `Parsing Note` on LexSense), so pick an unused name.
2. **Derived-field confirmation** -- run the default-WS `SetName` on a reversal
   index with FLEx **fully closed**, then open FLEx and re-read. If the name is
   still reverted with no peer involved at any point, the derived-field
   explanation is proven and shared mode is conclusively irrelevant to Q3.
3. **Empty-index visibility** -- recreate a reversal index on a vernacular WS,
   add a reversal **entry**, and check whether it now appears in the main
   Reversal Index view. All three indexes held 0 entries during the session, so
   emptiness is ruled out as the sole cause of the `seh` index being hidden
   (`en` and `pt` were equally empty and both displayed), but a conjunctive rule
   like "display if analysis WS **or** has entries" remains untested.
4. **Layout-list baseline** -- establish whether the reversal **layout** list
   read `English, English, Portuguese` before any write. The user's "(still
   there)" after the `seh` index was deleted suggests it is pre-existing
   `Sena 3` configuration; if instead it went 2 -> 3 during the session, an
   orphaned layout was left behind by the delete and needs chasing.

**Process lesson worth carrying forward.** One reading in this session had to be
retracted (`196a9c7`): a UI list was cited as evidence for a specific object
without first establishing what that list enumerates or capturing a
before-reading of it. Every data-side finding was diffed pre/post and none
needed correcting. Future items should capture a before-state for **every UI
surface** they intend to cite, not just for the database.
