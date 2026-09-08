
# Draft issues -- #93 live-session follow-ups (Task 2)

**Status: DRAFT ONLY. Nothing in this file has been filed.**

Source of truth: `specs/shared-mode-access/evidence/live-session-followups.md`
("Task 2" tables). Verbatim backing for every finding is in
`specs/shared-mode-access/evidence/live-cp4.md`, `# Session 2026-09-08`,
labelled `(a)`-`(m)`. Each section below links back with a
`(letter) -> evidence/live-cp4.md, "<anchor text>"` pointer instead of
re-deriving the finding.

**Duplicate check caveat:** this drafting pass had no shell/`gh` tool available
(this agent's tool set was Read/Grep/Glob/Edit/Write only), so `gh issue list`
was **not executed** against either repo. Every "duplicate check" line below
records that explicitly. Before filing anything, run:

```
gh issue list --repo MattGyverLee/flexicon --state all --limit 200
gh issue list --repo MattGyverLee/FlexToolsMCP --state all --limit 200
```

and re-check each proposed title against the results. The one exception is
`flexicon #236`, which the session's own follow-up doc already names by
number (undoable=False / no rollback-to-mark API) -- that identification is
taken as given per the task brief, not independently re-verified here.

---

## Root-cause note: flexicon rows 2, 3, 5 (read below before filing)

Rows 2, 3 and 5 in the flexicon table all trace to **one mechanism**: flexicon
resolves an unspecified writing-system argument to the **analysis-default** WS,
not to `BestAnalysisAlternative` (read side) or to something WS-aware, and FLEx
project data (semantic domain names, reversal-index names) is frequently
authored/consumed in a *different* WS (here `en`, while `Sena 3`'s
analysis-default is `pt`).

- **Row 2 (g)** is the **read**-side symptom: `GetName`/`GetAbbreviation`/
  `FindByName` resolve through the default WS and return `''` for
  `en`-only shipped data.
- **Row 3 (unlabelled)** is the **write**-side symptom of the identical
  mechanism: `SetName`/`Create` write into the default WS, so the obvious call
  silently misses the WS an English-reading user looks at.
- **Row 5 (unlabelled)** is a *different, second* bug that only looks like the
  same thing on the surface: `ReversalIndexes.Name` is FLEx-derived (regenerated
  from the writing system on project open), so a **default-WS** write to it is
  discarded by FLEx itself, independent of rows 2/3's mechanism. It happens to
  share a symptom (writes to the default WS "disappear" to an English reader)
  but the root cause is different (derived field, not fallback resolution) and
  the fix is different (document/remove `SetName`, not add a fallback).

**Recommendation: two issues, not one and not three.**
- File rows 2+3 together as **one flexicon issue** ("default-WS resolution
  affects both read and write") -- they are the same bug, same fix location
  (whatever helper resolves an omitted `wsHandle`), and splitting them would
  just make reviewers cross-reference two tickets for one patch.
- File row 5 **separately** -- different root cause, different fix (docs/API
  removal, not a resolution-fallback change), and it lives in
  `ReversalIndexOperations`, not the shared default-WS helper.
- Row 4 (h), the `Create` analysis-vs-vernacular guard, is a third, independent
  bug in the same class (`ReversalIndexOperations`) but not the same mechanism
  as row 5's derived-field issue -- keep it separate too, as drafted below.

---

# Target: MattGyverLee/flexicon

## flexicon-1 -- `SemanticDomainOperations.GetAll(recursive=False)` returns an interleaved, heterogeneous list

- **Proposed title:** Fix `SemanticDomainOperations.GetAll(recursive=False)` returning an interleaved list of domains and child lists
- **Proposed labels:** `bug`, `flexicon`, `semantic-domains`
- **Severity: High.** Justification: breaks the natural/obvious loop over the
  return value on the *second* element for every project, not an edge case;
  `recursive=True` proves the flat contract is intended and achievable, so this
  is a plain contract violation, not a documented limitation.
- **Evidence label:** `(f)` -> `evidence/live-cp4.md`, section
  "### (f) `SemanticDomainOperations.GetAll(recursive=False)` returns a
  heterogeneous, interleaved list"

**Symptom / verbatim reproduction:**

```
recursive=True   len=1792  histogram={'ICmSemanticDomain': 1792}   non-list elements=1792
recursive=False  len=18                                            non-list elements=9
```

```
[0]  ICmSemanticDomain num='1'
[1]  LIST len=14  inner=['ICmSemanticDomain', 'list', 'ICmSemanticDomain']
[2]  ICmSemanticDomain num='2'
[3]  LIST len=12  inner=['ICmSemanticDomain', 'list', 'ICmSemanticDomain']
...  (alternating, 9 domains + 9 lists = 18)
```

```python
for d in project.SemanticDomains.GetAll(recursive=False):
    project.SemanticDomains.GetNumber(d)
# AttributeError: 'list' object has no attribute 'Abbreviation'
#   at SemanticDomainOperations.py:518, number = best_analysis_text(domain.Abbreviation)
```

**Expected vs actual:** Expected the 9 top-level domains, flat, matching the
homogeneous contract `recursive=True` already honors. Actual: 18-element list
alternating `ICmSemanticDomain` / children-`list`, i.e. `recursive=False`
returns the recursion's own intermediate structure instead of a filtered flat
list.

**File:line:** `SemanticDomainOperations.py:518` (crash site in a naive
caller's loop); the `GetAll` implementation itself is the fix location
(not read in this session -- confirm exact line before filing).

**Duplicate check:** Not run (no `gh` access this pass). Recommend
`gh issue list --repo MattGyverLee/flexicon --search "recursive semantic domain"`
before filing.

---

## flexicon-2 -- Default-WS resolution breaks semantic-domain name read AND write (rows 2 + 3, combined)

- **Proposed title:** `SemanticDomainOperations` name accessors and mutators resolve the wrong writing system when none is specified
- **Proposed labels:** `bug`, `flexicon`, `writing-systems`, `semantic-domains`
- **Severity: High.** Justification: on the read side it makes `FindByName`
  unable to find *any* shipped domain in a project whose analysis-default WS
  differs from the shipped-data WS (here, every `Sena 3`-shaped project), and
  it breaks the MCP's own curated `add-semantic-domain-to-sense` recipe
  end-to-end. On the write side the obvious `SetName`/`Create` call produces
  an object that looks unnamed/unchanged to an English-reading user, with no
  error or warning.
- **Evidence labels:** `(g)` -> `evidence/live-cp4.md`, section
  "### (g) `GetName` / `GetAbbreviation` / `FindByName` are unusable..." and
  the unlabelled row-3 write-side confirmation in section "## Item 6 -- Q2,
  possibility-list ... with FLEx open" ("Confirms the default-WS model
  established in item 7, and extends it to `Create`").

**Symptom / verbatim reproduction (read side, finding g):**

```
Find('1')                                  -> ICmSemanticDomain
  GetNumber                                = '1'
  GetName default                          = ''
  GetAbbrev default                        = ''
  GetName(en)                              = 'Universe, creation'
  GetName(pt)                              = ''
  GetName(seh)                             = ''
  raw Name.BestAnalysisAlternative.Text    = 'Universe, creation'
  raw Name.AnalysisDefaultWritingSystem.Text = None
```

```
FindByName("Universe, creation") -> None   # op-094251845-011
```

The MCP's own curated recipe (`flextools_search_by_capability`, id
`add-semantic-domain-to-sense`, `verified_against: {flexicon: "4.2.1",
verified_by: "eval-corpus"}`) calls:

```python
domain = project.SemanticDomain.FindByName("Move")
```

which returns `None` on this project. That snippet also writes
`project.SemanticDomain` (singular) where the documented access path is
`project.SemanticDomains` (plural) -- confirm in the same investigation
whether both are bound, or file as a second sub-defect.

**Symptom / verbatim reproduction (write side, row 3, from item 6):**

```
legA SetName(DEFAULT ws) on domain '1' OK
legC Create OK -> num='10' en='' default='CP4LIVE-DOM-NEW-2026-09-08'
=== after ===
  domain 1 en='Universe, creation' pt='CP4LIVE-DOM-DEFAULTWS-2026-09-08' default='CP4LIVE-DOM-DEFAULTWS-2026-09-08'
  new domain 10 en='' default='CP4LIVE-DOM-NEW-2026-09-08'
```

Human confirmation (predicted before the check, per the evidence file):
"domain 1's english is fine. portuguese is now
CP4LIVE-DOM-DEFAULTWS-2026-09-08 ... 10 has a blank english name."

**Expected vs actual:** Expected `GetName()`/`GetAbbreviation()` with no WS
argument to fall back through `BestAnalysisAlternative` the same way raw LCM
access does; expected `SetName`/`Create` with no `wsHandle` to write somewhere
a typical (English-reading) user will see, or to require an explicit WS.
Actual: both resolve to the analysis-**default** WS specifically, which is
`pt` in `Sena 3` and empty for shipped `en`-only data.

**File:line:** Not captured in this session's raw-object probes; needs a
follow-up read of the resolution helper shared by `GetName`/`SetName`/
`Create` before filing (likely a common WS-default helper used across
`SemanticDomainOperations` and `ReversalIndexOperations`, per row 4/5's
shared symptom-but-different-cause note above).

**Duplicate check:** Not run. Recommend
`gh issue list --repo MattGyverLee/flexicon --search "FindByName writing system"`.

---

## flexicon-3 -- `ReversalIndexes.Create` accepts a vernacular writing system, contradicting its own docstring

- **Proposed title:** `ReversalIndexOperations.Create` should refuse a non-analysis writing system
- **Proposed labels:** `bug`, `flexicon`, `reversal-index`, `validation`
- **Severity: Medium-High.** Justification: not data loss and not a crash, but
  it produces an object that is provably unreachable through the FLEx UI
  (confirmed retraction-corrected finding: "never visible anywhere in the FLEx
  UI") while still occupying the WS slot that would block a later legitimate
  `Create` for that WS -- a real, silent trap, contradicting the method's own
  documented contract.
- **Evidence label:** `(h)` -> `evidence/live-cp4.md`, section
  "### (h) `ReversalIndexOperations.Create` does not validate that the writing
  system is an analysis WS", corroborated by "## Item 7 -- Q3 ... RETRACTION"
  and "REFRAMING" sections.

**Symptom / verbatim reproduction:**

```
Create(pt)  -> FP_ParameterError: Reversal index already exists for writing system pt
Create(seh) -> OK, name='CP4LIVE-new-seh'
```

`seh` is confirmed vernacular (`GetVernacular()` -> `seh`, `seh-fonipa-x-etic`;
`GetAnalysis()` -> `en`, `pt`). The method's own docstring reads "Create a new
reversal index for an **analysis** writing system."

Corrected UI observation (post-retraction, do not cite the manage-layouts
list as evidence -- see the "Do NOT re-adopt" note in the followups doc): the
`seh` index "was never visible anywhere in the FLEx UI" despite surviving a
full FLEx restart with a distinct GUID
(`bde3f661-c058-40cd-bf15-4000e4364bda`).

**Expected vs actual:** Expected `Create` to refuse a vernacular WS the same
way it already refuses a duplicate-WS request (`FP_ParameterError`, working
correctly). Actual: no analysis-vs-vernacular guard exists at all; the
duplicate-WS guard is the only one implemented.

**File:line:** `ReversalIndexOperations.py` (`Create` method) -- exact line
not captured in this session; confirm before filing.

**Duplicate check:** Not run. Recommend
`gh issue list --repo MattGyverLee/flexicon --search "ReversalIndex Create"`.

---

## flexicon-4 -- `ReversalIndexes.SetName` targets a FLEx-derived field and should be documented as ineffective (or removed)

- **Proposed title:** Document (or remove) `ReversalIndexOperations.SetName` -- `IReversalIndex.Name` is FLEx-derived and gets regenerated on project open
- **Proposed labels:** `bug`, `flexicon`, `reversal-index`, `documentation`
- **Severity: Medium.** Justification: not data loss (FLEx's own maintenance
  overwrites the value deterministically, not a shared-mode race) and not a
  crash, but the API silently accepts a write that is provably discarded on
  the very next FLEx open for the common (default-WS) call shape -- a
  correctness trap for anyone using the documented method as documented.
- **Evidence label:** row 5 (unlabelled) -> `evidence/live-cp4.md`, sections
  "### Restart observation -- **item 7 verdict: MIXED..." and "### REFRAMING
  -- ReversalIndex.Name is very likely a FLEx-derived field", confirmed by the
  item-6 discriminator "### Consequences -- this settles the item 7
  hypothesis".

**Symptom / verbatim reproduction:**

```
| index | alternative | pre-restart | post-restart | outcome |
|---|---|---|---|---|
| ws=`en` | `en` name | `CP4LIVE-EN-2026-09-08` | `CP4LIVE-EN-2026-09-08` | survived |
| ws=`en` | `pt` name | `CP4LIVE-Reversal-2026-09-08` | `English` | REVERTED |
| ws=`seh` | `en` name | `CP4LIVE-SEH-2026-09-08` | `CP4LIVE-SEH-2026-09-08` | survived |
| ws=`seh` | `pt` name | `CP4LIVE-new-seh` | `Sena` | REVERTED |
```

Discriminator (item 6, semantic domains, NOT derived): domain 1's `pt` name
`CP4LIVE-DOM-DEFAULTWS-2026-09-08` **survived** the identical restart --
ruling out a general default-WS write-loss mechanism and confirming FLEx is
specifically regenerating `IReversalIndex.Name`, not discarding shared-mode
writes.

**Expected vs actual:** Expected `SetName` on a reversal index, called with
the default (unspecified) WS, to persist like any other field write (as it
does for semantic domains). Actual: FLEx regenerates `Name` in the default
analysis WS from the writing system's language name on every project open,
silently discarding the peer-written value; only an explicit non-default-WS
`SetName` survives, and even that is invisible in the FLEx reversal UI, which
labels indexes by writing system, not by `Name` (confirmed by writing `en`-WS
name explicitly and the main view still reading "English").

**File:line:** `ReversalIndexOperations.py` (`SetName` method) and/or its
docstring; also worth a note in whatever LibLCM doc describes
`IReversalIndex.Name`. Exact lines not captured this session.

**Note:** this is **not** a shared-mode / CP5 concern -- see the root-cause
note above the flexicon section. Keep this issue scoped to flexicon
documentation/API surface, not the #93 CP5 gate work.

**Duplicate check:** Not run. Recommend
`gh issue list --repo MattGyverLee/flexicon --search "ReversalIndex SetName"`.

---

## flexicon-5 -- `report.Info` output is discarded entirely when an exception escapes a run

- **Proposed title:** Preserve accumulated `report.Info` messages when a script raises mid-run
- **Proposed labels:** `bug`, `flexicon`, `dx`
- **Severity: Medium.** Justification: pure diagnostics/UX loss, no data or
  safety impact, but it materially slowed down every subsequent probe in the
  live session (every probe needed defensive `try`/`except` purely to keep
  output), which is the exact scenario (iterative exploration of an
  unfamiliar API) this tooling exists to support.
- **Evidence label:** `(i)` -> `evidence/live-cp4.md`, section
  "### (i) `report.Info` output is discarded when an exception escapes"

**Symptom / verbatim reproduction:**

op `op-094214370-009` emitted roughly a dozen `report.Info` lines successfully
before crashing in the semantic-domain section, and the response came back
with `"messages": []` and `"summary": {}` -- all progress output lost, leaving
only the traceback.

**Expected vs actual:** Expected accumulated messages to be flushed alongside
the error. Actual: messages array is empty whenever an exception escapes,
regardless of how much was logged first.

**File:line:** Not captured (this is flexicon's own report/runner plumbing,
not read directly this session) -- confirm before filing.

**Duplicate check:** Not run. Recommend
`gh issue list --repo MattGyverLee/flexicon --search "report.Info exception"`.

---

## flexicon-6 -- `WritingSystemOperations.Delete` leaves LDML and shared-settings residue on disk

- **Proposed title:** `WritingSystemOperations.Delete` does not remove the writing system's `.ldml` file or its `SharedSettings/LexiconSettings.plsx` entry
- **Proposed labels:** `bug`, `flexicon`, `writing-systems`, `data-integrity`
- **Severity: High.** Justification: leaves a project in a state where FLEx
  may re-ingest a writing system that LCM says does not exist, and -- given
  the confirmed FieldWorks crash on peer WS creation (flexicon row for Q1,
  filed separately against #93/FlexToolsMCP scope, not flexicon) -- risks
  reproducing that crash on next open. Makes `Create` not cleanly reversible
  through the API, which is itself an argument that WS creation should not be
  offered from a peer at all.
- **Evidence label:** `(l)` -> `evidence/live-cp4.md`, section
  "### FINDING (l) -- `WritingSystemOperations.Delete` is incomplete"

**Symptom / verbatim reproduction:**

```
=== after Delete ===
  tag='en' size=12.0
  tag='pt' size=12.0
  tag='seh' size=12.0
  tag='seh-fonipa-x-etic' size=12.0
Exists('fr') after = False
analysis after = ['en', 'pt']
```

But on disk:

```
fr.ldml                 51,564 bytes  Sep 8 10:26   STILL PRESENT
LexiconSettings.plsx    <WritingSystem id="fr">      STILL PRESENT
WritingSystemStore/trash/                            fr.ldml NOT moved here
```

(seven older LDMLs sit in `trash/` from a prior date, confirming FLEx itself
does use that mechanism, and `Delete` does not.)

**Expected vs actual:** Expected `Delete` to either remove the LDML file (or
move it to `trash/`, matching FLEx's own convention) and remove the
`LexiconSettings.plsx` entry. Actual: only the LCM in-memory model is
cleaned; both on-disk artifacts are left behind with no tidy-away path.

**File:line:** `WritingSystemOperations.py` (`Delete` method) -- exact line
not captured this session; confirm before filing.

**Duplicate check:** Not run. Recommend
`gh issue list --repo MattGyverLee/flexicon --search "WritingSystem Delete ldml"`.

---

## flexicon-7 -- Peer-written entries in `idchangelog.xml` carry no provenance

- **Proposed title:** Writing-system changes made via flexicon record `Producer="???" ProducerVersion="unknown"` in `idchangelog.xml`
- **Proposed labels:** `bug`, `flexicon`, `writing-systems`, `minor`
- **Severity: Low.** Justification: purely an audit-log quality gap; no
  functional or data-integrity impact, but the log becomes useless for its
  one job (attributing a change) for exactly the kind of write this session
  was investigating.
- **Evidence label:** `(m)` -> `evidence/live-cp4.md`, section
  "### FINDING (m) -- peer writes record no provenance in the WS change log"

**Symptom / verbatim reproduction:**

```xml
<Add Producer="???" ProducerVersion="unknown" TimeStamp="2026-09-08T15:26:40Z">
  <Id>fr</Id>
</Add>
```

versus FLEx's own entries, e.g. `Producer="FieldWorks" ProducerVersion="Version
8.3.9 (apparent build date: 24-Jul-2017)"`.

**Expected vs actual:** Expected the writer to identify itself (library name +
version) the way FLEx does. Actual: literal placeholder strings `"???"` /
`"unknown"`.

**File:line:** Not captured this session (change-log writer inside
`WritingSystemOperations` or a shared LCM-write path) -- confirm before
filing.

**Duplicate check:** Not run. Recommend
`gh issue list --repo MattGyverLee/flexicon --search "idchangelog provenance"`.

---

## flexicon-8 -- `project.Object(guid)` returns an uncast `ICmObject`; `hvo_stability` primer's worked example is not runnable as written

- **Proposed title:** `project.Object(guid)` should return a cast object (or the `hvo_stability` primer should show the required cast)
- **Proposed labels:** `bug`, `flexicon`, `documentation`, `dx`
- **Severity: Medium.** Justification: hit while executing an official
  checklist item, not while improvising -- the MCP's own most-prominently
  surfaced runtime guidance produces a runtime `AttributeError` for the common
  `ILexEntry` case when followed literally. No data-safety impact (the
  preflight casting gate still degrades gracefully to a `resolve_property`
  fallback at runtime), but it is a real trap for exactly the call pattern the
  primer recommends for crossing a call boundary.
- **Evidence label:** `(e)` -> `evidence/live-cp4.md`, section
  "### Finding (e) -- `project.Object(guid)` returns an uncast `ICmObject`"

**Symptom / verbatim reproduction:**

```
AttributeError: 'ICmObject' object has no attribute 'AllSenses'
  ... during handling of which:
AttributeError: 'ICmObject' object has no attribute 'SensesOS'
  File "flexicon/code/Lexicon/LexEntryOperations.py", line 2673, in GetAllSenses
```

with `polymorphic_error_detected: true`, `object_type: "ICmObject"`,
`property_name: "SensesOS"`.

The `hvo_stability` primer text (per the evidence file) reads:

> "project.Object(...) is the INVERSE -- it accepts an int (hvo, same-run only),
> a str GUID, or a System.Guid, and resolves to the live CmObject. Prefer the
> str-GUID form when crossing a call boundary: project.Object(guid_str)."
> ... "Call 2: entry = project.Object(guid_str)"

with no mention that the returned object must be cast (e.g. to `ILexEntry`)
before an Operations method that reaches for `SensesOS`/`AllSenses` will
accept it.

**Expected vs actual:** Expected either (a) `project.Object()` to return an
already-cast object appropriate to the underlying LCM class, or (b) the
primer's worked example to show the cast explicitly. Actual: neither -- the
example is not runnable as written for the common `ILexEntry` case.

**File:line:** `flexicon/code/Lexicon/LexEntryOperations.py:2673`
(`GetAllSenses` crash site); the `hvo_stability` primer text lives in the MCP
server's own response construction, not flexicon -- **this issue may need to
be split into a flexicon issue (cast on return, or none) and a FlexToolsMCP
doc fix (primer wording)**. Drafted here under flexicon because the
behavioral question ("should `project.Object` cast?") is flexicon's call;
flag the primer-wording half to `/lex-doc` for a FlexToolsMCP-side fix
regardless of the flexicon outcome.

**Duplicate check:** Not run. Recommend
`gh issue list --repo MattGyverLee/flexicon --search "project.Object cast ICmObject"`.

---

## flexicon -- `undoable=False` / no rollback-to-mark API (finding b)

- **Proposed target:** **flexicon #236 (existing issue) -- COMMENT, not a new issue.**
- **Justification:** the task brief identifies #236 as the existing tracker
  for this exact concern, and the followups doc explicitly flags it rather
  than proposing a new issue. This session adds live confirmation that the
  MCP runner is opening projects in this no-rollback legacy mode by default,
  which is new evidence worth attaching to #236, not a new report.
- **Evidence label:** `(b)` -> `evidence/live-cp4.md`, section
  "**(b) No rollback was in effect.**"

**Comment content (for #236, once approved):**

```
stderr verbatim from a live #93 session (2026-09-08), opening a project via
the MCP/flexicon path:

OpenProject: writeEnabled=True with an explicit undoable=False. This opts OUT of
per-operation units of work, which is the default since 4.4.0. In this legacy
mode Transaction() is a labelling/nesting construct only -- liblcm exposes no
reachable rollback-to-mark API in this mode (issue #236). The atomicity unit for
this whole session is the SESSION, not the operation: if code raises
mid-operation, every mutation applied before the failure remains in the
in-memory cache and will be written to disk by CloseProject()/SaveChanges().
Drop the argument to get rollback back.

Every mutating call in the session (items 5, 6, 7, plus the CP4 gloss write/
restore) ran in this mode. Confirms the MCP runner is not opting into
per-operation rollback by default -- worth resolving whether it should.
```

**Duplicate check:** #236 named directly by the task brief and the source
evidence doc; not independently re-verified against `gh issue list` (no
shell access this pass). Confirm #236 is still open and its title/scope match
before posting.

---

# Target: MattGyverLee/FlexToolsMCP

## flextoolsmcp-1 -- `_pid_is_alive` reports a freshly-dead process as ALIVE

- **STATUS: FIXED IN #93 THIS CYCLE -- file only if the user wants a
  standalone tracking issue** (a sibling task in this same cycle is patching
  `project_access.py` for this defect).
- **Proposed title:** `_pid_is_alive` must call `GetExitCodeProcess` after a successful `OpenProcess`, not treat the handle alone as proof of life
- **Proposed labels:** `bug`, `windows`, `lock-detection`
- **Severity: High.** Justification: time-dependent and worst exactly in the
  post-crash window when `stale_lock` detection matters most, affecting
  CP2/CP3/CP4/CP5 uniformly; leaves a user stuck with no remedy except
  manually deleting the lock file.
- **Evidence label:** `(k)` -> `evidence/live-cp4.md`, section
  "### FINDING (k) -- `_pid_is_alive` reports a freshly-dead process as ALIVE"

**Symptom / verbatim reproduction:**

After FieldWorks was fully closed (`Get-Process -Name FieldWorks` count **0**;
`tasklist /FI "PID eq 40568"` -> "No tasks are running which match"), the
probe still reported:

```json
"project_access": {
  "project": "Sena 3",
  "verdict": "open_shared",
  "sharing_enabled": true,
  "holder": {"pid": 40568, "process_name": "FieldWorks",
             "timestamp_ticks": 639244596539187867},
  "lock_age_seconds": 512.646733
}
```

and the health warning asserted: *"held by FieldWorks (PID 40568), **process
still running**."*

```python
if sys.platform == "win32":
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if handle:
        kernel32.CloseHandle(handle)
        return True
```

**Expected vs actual:** Expected a dead PID to yield `stale_lock` per the
documented decision table. Actual: `OpenProcess` succeeds on a
terminated-but-not-yet-reaped process (Windows keeps the kernel object alive
while a handle remains open -- here, almost certainly the crash reporter), so
`_pid_is_alive` returns `True` for a dead PID.

**File:line:** `project_access.py:161-178`.

**Duplicate check:** Not run against `gh issue list` (no shell access this
pass) -- but per the task brief this is being fixed in code this same cycle,
so filing is optional/tracking-only regardless of duplicate status.

---

## flextoolsmcp-2 -- `mutations_detected` / `mutating_calls_detected` never enumerate real mutating calls (self-contradictory refusal message)

- **STATUS: FIXED IN #93 THIS CYCLE -- file only if the user wants a
  standalone tracking issue** (a sibling task in this same cycle is patching
  the mutation-detection enumeration).
- **Proposed title:** Populate `mutations_detected`/`mutating_calls_detected` so the Rung-3 confirmation message is not self-contradictory
- **Proposed labels:** `bug`, `ux`, `write-gate`
- **Severity: Medium.** Justification: confirmed **not** a safety hole (the
  gate itself keys off `writeability.is_mutating_script` and correctly
  refused with `confirmed=False` on re-test) -- but a real correctness/UX
  defect reproduced on three separate ops and two different mutating scripts,
  telling a user legitimately hitting the safety gate to "review" a
  guaranteed-empty array.
- **Evidence labels:** `(a)`/`(d)` -> `evidence/live-cp4.md`, sections
  "**(a) `write_certification` misreports a mutating run as read-only.**" and
  "### Finding (d) -- CORRECTION to finding (a): the confirmation gate is NOT
  bypassable"

**Symptom / verbatim reproduction:**

Real write, demonstrably mutating (`lcm_undoable_action_count: 1`, gloss
changed):

```json
"write_certification": {"is_certified_readonly": true, "confidence": "medium",
                        "mutating_calls_detected": []}
```

Refusal path (`confirmed=False`, op `op-093805998-006`):

```json
{
  "status": "error",
  "error_code": "confirmation_required",
  "message": "This run would mutate the database (0 mutation(s) detected) but confirmed=False. Review `mutations_detected`, then resubmit the SAME call with confirmed=True to execute.",
  "writeability": {"is_mutating_script": true, "mutations_detected": [],
                   "would_require": {"write_enabled": true, "project_lock": true}}
}
```

Root cause named in the evidence file: `project.Senses.SetGloss` (and by
extension other Operations mutators) is not enumerated by whatever populates
`mutations_detected`/`mutating_calls_detected`.

**Expected vs actual:** Expected the message to name the actual mutating
call(s) (e.g. `SetGloss`) so "review `mutations_detected`" is actionable.
Actual: the message asserts a mutation and denies it in the same sentence
("would mutate the database (0 mutation(s) detected)"), and the array a user
is told to review is empty on every run, including runs that indisputably
mutated.

**File:line:** wherever `mutations_detected`/`mutating_calls_detected` /
`write_certification.is_certified_readonly` are populated (not captured by
line number this session -- likely the same static-mutation-detection pass
referenced by `writeability.is_mutating_script`, which *does* correctly flag
these scripts, so the bug is specifically in the per-call enumeration, not
the boolean).

**Duplicate check:** Not run against `gh issue list` -- fixed this cycle per
task brief; file as tracking-only if wanted.

---

## flextoolsmcp-3 -- `ENABLE_SHARING_REMEDY` overstates the reopen requirement

- **STATUS: FIXED IN #93 THIS CYCLE -- file only if the user wants a
  standalone tracking issue** (a sibling task in this same cycle is softening
  the wording).
- **Proposed title:** Soften `ENABLE_SHARING_REMEDY` wording -- a FLEx reopen is not required for a peer to see a `projectSharing` flag flip
- **Proposed labels:** `documentation`, `ux`, `write-gate`
- **Severity: Low.** Justification: the current behavior is not unsafe (the
  peer open succeeds regardless), but the remedy text asserts a false
  precondition ("FLEx will ask to reopen the project -- let it, because the
  flag is read once when the cache opens") that could needlessly make a user
  restart FieldWorks unnecessarily, or worry that their peer write won't take
  effect until they do.
- **Evidence label:** unlabelled -> `evidence/live-cp4.md`, section
  "### Bonus: the item 4 part 2 open question is now settled"

**Symptom / verbatim reproduction:**

```
before: {"PID":35236,"ProcessName":"FieldWorks","Timestamp":639244562327878323}
after:  {"PID":35236,"ProcessName":"FieldWorks","Timestamp":639244562327878323}
```

Lock file byte-identical before and after the sharing flag flip (no reopen
happened), yet the identical peer call proceeded immediately with no refusal:

```json
{"success": true, "project": "Sena 3", "write_enabled": false,
 "messages": [{"type": "INFO", "message": "1462", "ref": null}],
 "error": null, "exit_code": 0}
```

A later, unrelated FLEx restart (item 7) *did* rewrite the lock file (new PID,
new timestamp), proving a genuine reopen is detectable when it happens --
confirming the item-4-part-2 non-reopen was real, not an artifact of a blind
spot in the observation.

**Expected vs actual:** Expected remedy text to match the mechanism: the peer
reads the flag at its own cache-open, so a FLEx-side reopen is unnecessary
for the *server's* ability to attach. Actual: current text says "let it
[reopen], because the flag is read once when the cache opens
(LcmCache.cs:219)", which conflates the master's own cache behavior with the
peer's.

**File:line:** wherever `ENABLE_SHARING_REMEDY` string constant is defined
(not captured by line number this session -- likely `project_access.py` or
adjacent remedy-text module; confirm before filing).

**Duplicate check:** Not run against `gh issue list` -- fixed this cycle per
task brief; file as tracking-only if wanted.

---

## flextoolsmcp-4 -- MCP server restart silently voids session write-discovery state (documentation note, not a bug)

- **STATUS: Documentation, not a defect.** Per the task brief, this is
  explicitly an operational note, not necessarily a bug: the behavior itself
  (refuse-and-recover) already works well.
- **Proposed title:** Document that an MCP server restart voids `discovered_api_count`, requiring one `get_object_api` re-call before the next write
- **Proposed labels:** `documentation`, `operational-note`
- **Severity: Low (informational).** Justification: the refusal path already
  inlines full recovery in one round-trip (`_inline_discovery`); this is
  purely about setting operator expectations, not fixing broken behavior.
- **Evidence label:** unlabelled -> `evidence/live-cp4.md`, section
  "### Incidental: MCP server restarted mid-session, dropping write
  discovery"

**Symptom / verbatim reproduction:**

```
error_code: "api_discovery_required"
session: {..., "discovered_api_count": 0}
op_id: "op-102339089-001"
```

The `op_id` counter reset to `-001` and `discovered_api_count` to `0`,
indicating the MCP server process restarted between calls. Read-only runs
kept working throughout (graceful auto-discovery); only the **write** run
was refused, and only once -- the refusal inlined the full
`SemanticDomainOperations` surface under `_inline_discovery` ("Inlined for
single-round-trip recovery"), so recovery needed no exploratory calls.

**Expected vs actual:** Expected/actual match -- this is recorded as a note,
not a doc-vs-code mismatch. Recommend: add a short paragraph to whichever
doc covers session lifecycle / write-discovery (README or a USAGE_*.md, per
the doc manifest once one exists) describing this restart behavior and
pointing to the `_inline_discovery` recovery path as the expected response.

**File:line:** N/A (behavioral note, not a code citation).

**Duplicate check:** Not applicable -- proposed as a documentation addition,
not an issue against a defect. If the user still wants a tracking issue for
"add this doc paragraph," recommend the `documentation` label only.

---

# READY-TO-FILE checklist

- [ ] Re-run `gh issue list --repo MattGyverLee/flexicon --state all --limit 200`
      and `gh issue list --repo MattGyverLee/FlexToolsMCP --state all --limit 200`;
      cross-check every proposed title above against real results (this draft
      could not run `gh` -- no shell tool was available to this drafting pass).
- [ ] Confirm flexicon #236 is still open, and that its scope matches the
      `undoable=False` comment drafted above, before posting.
- [ ] Decide: file flexicon-2 (rows 2+3) as one issue, per the recommendation
      above, or split -- and record that decision here before filing.
- [ ] Confirm file:line citations marked "not captured this session" by
      reading the actual source before filing (several flexicon items above
      are drafted from behavior only, since the flexicon repo source is
      under a standing advisory lock for this crew and was not read for this
      draft).
- [ ] Decide whether to file flextoolsmcp-1/2/3 at all, given they are being
      fixed in code this same #93 cycle -- default recommendation is
      tracking-only if the user wants a paper trail, otherwise skip.
- [ ] Confirm flextoolsmcp-4 is wanted as an issue vs. folded directly into a
      doc as a documentation PR with no separate tracking issue.
- [ ] Get explicit user sign-off on every title, label set, and severity
      above -- several are drafted judgment calls (see each section's
      "Justification"), not certainties.

**NOTHING IN THIS FILE HAS BEEN FILED. User approval required before any `gh
issue create`.**
