# cycle1-logscan-september.md — Phase A Log-Scan Proposal

**Scanner:** /lex-logscan (Phase A, read-only)
**Window:** `logs/2026-09-06/*` (excluding `session_183210_auto-Claude-Swahili.log`, already triaged into
F1-F6 / MCP#100,#101,#102 / flexicon#257,#258) + `logs/2026-09-07/*` (all files).
**Peer window (not scanned here):** `logs/2026-08-10`..`2026-08-28`.
**Branch:** `feat/shared-mode-access`. Fix commits in-window: `a1f6897` (2026-09-07 01:33:15,
"candidate-union fallback closes P1-1/P1-2", #39/#40/#97) and `1e30148` (2026-09-07 02:07:28,
"scope the candidate-union fallback to the lexical scope chain", #40 cycle 6).

---

## Scan inventory

**2026-09-06** (excluding the already-triaged session_183210):
- `session_230055_auto-Claude-Swahili.log` (410,392 bytes; real user session, read in full via
  targeted grep + context reads) — spans 2026-09-06 23:01 through 2026-09-07 01:41 (a long-running
  session that crosses the day boundary).
- `session_231319_auto-Issue10TestProject.log` (62,077) + `session_231354_test-recipes.log` (1,331)
- `session_231431_auto-Issue10TestProject.log` (62,077) + `session_231506_test-recipes.log` (1,331)
- `session_233233_auto-Issue10TestProject.log` (71,954) + `session_233308_test-recipes.log` (1,331)
- `session_233638_auto-Issue10TestProject.log` (71,954) + `session_233713_test-recipes.log` (1,331)
- `session_233744_auto-Issue10TestProject.log` (71,954) + `session_233820_test-recipes.log` (1,331)
- `session_234612_auto-Issue10TestProject.log` (71,956) + `session_234648_test-recipes.log` (1,331)

**2026-09-07** (all files; ~60 total):
- `session_013534_auto-Claude-Swahili.log` (45,995; real user session, read in full)
- `session_024114_auto-Claude-Swahili.log` (120,440; real user session, read in full)
- 27 × `auto-Issue10TestProject.log` / paired `test-recipes.log` harness reruns, sizes clustering at
  73,398 / 79,895 / 82,408 / 84,731 bytes.

**Harness-rerun dedup grouping** (by byte-size, confirming they are identical scripted verification
runs, not distinct user activity): size groups found were **62077 → 71954 → 71956 → 73398 → 79895 →
82408 → 84731**, each group internally byte-identical apart from timestamps. `Reason code:` lines
inside every group land at the *same source line number* every time within a group (e.g.
`confirmation_required` always at line 97, `nested_unit_of_work` always at 880/897,
`project_locked` always at 1026/1045/1064 for the 62077/71954/71956/73398 groups). One representative
file per group was read plus every boundary transition:
- 71954→71956 (2026-09-06 23:46): no new reason codes, byte delta is cosmetic (timestamp text).
- 71956→73398 (crosses into 09-07 00:05): still the same 3 reason codes (confirmation_required,
  nested_unit_of_work×2, project_locked×3) at the same relative offsets — harness unchanged.
- 73398→79895 (00:27): **adds 3× `casting_issues_detected`** before `confirmation_required` — the
  harness script grew a new casting-gate test block (consistent with active work on #39/#40/#97
  immediately before `a1f6897`).
- 79895→82408 (00:50): reason-code shape unchanged; size delta is harness bookkeeping (op-id/line
  padding), no new behavior.
- 82408→84731 (01:31, i.e. `session_013101`, 2 minutes *before* `a1f6897` at 01:33:15): **adds a 4th
  `casting_issues_detected`** line (at line 164) ahead of `confirmation_required` — the harness grew
  again immediately around the fix commit, consistent with the developer adding a regression
  assertion for the P1-1/P1-2 fix just before committing it.
- The 84731 group is stable from `session_013101` (01:31:01) through `session_021201` (02:12:01),
  i.e. **unchanged across `1e30148`** (02:07:28) — the scope-narrowing fix in cycle 6 did not change
  this harness script's output, meaning cycle 6 fixed a case this generic harness doesn't exercise.

**Ops counted:** the two 2026-09-06 real sessions contain ~102 operations combined
(session_230055 alone reaches "Operation #102" by its end); the two 2026-09-07 real sessions add
~9 (session_013534) + ~12 (session_024114) more. Harness reruns are 3-4 operations each × 33 files
≈ 115 additional (noise) operations, not counted toward triage findings.

## Excluded as noise

1. **All 33 `auto-Issue10TestProject` / `test-recipes` harness-rerun pairs** (both days) — confirmed
   scripted regression-verification runs for the #39/#40/#97 casting-gate bugfix campaign (identical
   byte sizes, identical reason-code line numbers within each size group, monotonically growing only
   at the two commit boundaries noted above). Not user activity; excluded per task scope guard.
2. **`'milele' 'eternity': no feature structure`** (session_230055, 2026-09-06 23:44:36) — a
   `report.Error()` raised by the *user's own script* about missing linguistic feature-structure data
   on a specific lexeme; this is domain/content, not a code defect. (Same operation's stderr also
   surfaces a legacy `undoable=False` mode notice that correctly self-cites already-closed flexicon
   issue #236 — informational, not a new defect. Also of interest only as confirmation that this
   branch's shared-mode-access feature is live: `[SHARED] 'Claude-Swahili' open_shared (holder PID
   58536); proceeding with the write as a non-master peer.`)
3. **`undefined_variables` rejection** (session_024114 op#2, 2026-09-07 02:42:35, `FLEX_EMPTY_PLACEHOLDER`
   not defined) — single self-inflicted typo, corrected by the AI on the very next resubmit (op#3
   defines `EMPTY = "***"` instead). Consistent with the already-deferred low-volume
   `undefined_variables` bucket in the ledger; not re-proposed.
4. **`[AUTO-FIX] casting: patch did not pass re-preflight; falling back to rejection`** (session_024114
   op#1, 2026-09-07 02:42:10) — read in full context: the auto-fix subsystem correctly detected its
   own patch didn't resolve the casting issues and safely fell back to the ordinary reject path. This
   is the feature working as designed, not a bug.
5. **`Preflight casting: issues=1 severity=warning (read-only run) -- proceeding without rejecting
   (issue #40 B-1).`** (session_024114 op#9, 2026-09-07 03:19:04) — this is *positive* evidence the
   `#40`/`a1f6897` mitigation (soften single-issue casting rejections to warnings on read-only runs)
   is live and working in production. Not a defect; flagged for the archivist/lead as confirmation
   worth attaching to #40, not something this scan files.

## Deduped recurrences (against `docs/logscan-state.json` working tree + live GitHub)

| Signature observed this window | Existing issue | Evidence |
|---|---|---|
| `casting_issues_detected` preflight rejections, high frequency across nearly every real op | MCP#48 (aggregate bucket, per ledger correction) | pervasive; session_230055 op#1 (23:01:31, issues=5), session_013534 op#1 (issues=10), session_024114 op#1 (issues=8), etc. |
| `TypeError: object does not implement IMoInflAffixTemplate` (casting gate passed tier=none, runtime TypeError) | **MCP#101** (`IMoInflAffixSlot / IMoInflAffixTemplate / IMoInflClass are not ICmPossibility`) | session_024114 op#7 (2026-09-07 02:49:45) — exact type named in #101's own title. |
| Casting gate over-rejects code casting a shared variable name across sibling if/elif branches (MSA/ClassName-dispatch idiom) | MCP#40 (reopened regression) | Not re-observed as a *fresh* instance this window (the `a1f6897`/`1e30148` fix landed mid-window); see "Already-fixed-on-branch" below. |
| Casting validator suggests wrong interface / OA-RA double count | MCP#97 | Not re-observed as a fresh instance this window. |

## REGRESSIONS (recurrence after close date)

None found in this window. (MCP#40's regression was already recorded by the prior 2026-09-06 scan
that produced `d297f59ec7ce`; this window is largely *after* the fix landed, see below.)

## Already-fixed-on-branch (defect present only before the in-window commits)

- The #39/#40/#97 "casting gate over-rejects / suggests wrong cast" failure mode that dominated the
  pre-`a1f6897` harness runs (00:26-01:27, 3-4 `casting_issues_detected` lines per harness run,
  matching the pattern already tracked) is the exact class `a1f6897`/`1e30148` targeted. Post-fix
  evidence (session_024114 op#9, 03:19:04) shows the new warn-not-reject behavior explicitly labelled
  `(issue #40 B-1)` in the log — i.e. the fix is confirmed live and working. **Not re-filed.**
- No NEW false-negative was found where the landed fix caused previously-gated code to run unsafely
  unrejected — see "Casting-gate blind spots" finding #3 below for a *different*, pre-existing gap
  (raw pythonnet interface casts were never covered by the gate at all, before or after the fix).

## Cross-window collision note (for the lead to merge with the August-window peer)

The following recurring *classes* (not specific occurrences) are broad enough that the peer's
August window likely also contains instances, and any filing decision should be reconciled with
theirs before Phase B:
- `casting_issues_detected` volume (MCP#48 aggregate) — near-universal across all real sessions in
  both windows.
- Polymorphic AttributeError / wrong-cast-suggestion family (MCP#39/#40/#97) — recurring theme,
  though this window's fresh instances are the *new* findings below (#3), which are a distinct facet
  (missing/wrong diagnostic hint, not the gate's reject/accept decision itself).

## PROPOSED NEW ISSUES (4)

### 1. flexicon — bug — **P1**
**Title:** `AllomorphOperations.__GetAllomorphObject never casts to IMoForm — GetForm/Delete crash with 'ICmObject' object has no attribute 'Form' on any object resolved via project.Object()`

**Evidence:**
- `logs/2026-09-07/session_013534_auto-Claude-Swahili.log`, op#2 (2026-09-07 02:05:27):
  ```
  ERROR   | Error type:      PolymorphicAttributeError
  ERROR   | Error:           Execution error: 'ICmObject' object has no attribute 'Form'
  DEBUG   |   File "D:\...\flexicon\flexicon\code\Lexicon\AllomorphOperations.py", line 632, in GetForm
  DEBUG   |     form = ITsString(allomorph.Form.get_String(wsHandle)).Text
  DEBUG   |   AttributeError: 'ICmObject' object has no attribute 'Form'
  ```
  User code: `obj = project.Object(guid); ... actual = allomorphs.GetForm(obj)` — a documented,
  common pattern (verify-GUIDs-before-delete) that this session used explicitly because the user was
  about to run a destructive delete and wanted a dry-run sanity check first.
- Confirmed by reading the source directly (this machine has a local flexicon checkout at
  `D:\Github\_Projects\_LEX\flexicon`): `AllomorphOperations.py:1100-1112`
  ```python
  def __GetAllomorphObject(self, allomorph_or_hvo):
      """Resolve HVO or object to IMoForm. ... Returns: IMoForm: The resolved allomorph object."""
      if isinstance(allomorph_or_hvo, int):
          return self.project.Object(allomorph_or_hvo)
      return allomorph_or_hvo
  ```
  Neither branch ever casts to `IMoForm` — the docstring's contract ("Resolve ... to IMoForm") is not
  honored. `GetForm` (`AllomorphOperations.py:632`) then accesses `.Form` on whatever this returns
  without its own cast, so any caller who resolves the allomorph via `project.Object(hvo_or_guid)`
  (an `int` HVO **or** a GUID string) gets a bare `ICmObject`/`ICmObjectId`, not `IMoForm`, and the
  method throws.
- The user's own *second* attempt at the same script (`session_013534` op#3, 2026-09-07 02:06:48)
  worked around this by adding an explicit `IMoForm(obj)` cast before calling `GetForm`/`Delete` —
  proof the fix (cast in `__GetAllomorphObject`) is trivial and exactly what a caller has to do
  manually today.

**Suspected origin:** flexicon (`AllomorphOperations.py`, `__GetAllomorphObject` private resolver).
This is the same "missing-cast-before-property-access" defect class that has been fixed roughly a
dozen times elsewhere in flexicon's history (closed issues #98, #116, #151, #159, #160, #162, #166,
#168, #199, #248, etc.) — worth a sibling-sweep audit of other `__Get*Object`-style private
resolvers (e.g. `__GetEnvironmentObject`, immediately adjacent at `AllomorphOperations.py:1114`,
has the identical pattern and is equally suspect though not directly observed failing this window).

**Proposed signature hash (sha256, first 12 hex):** `sha256("AllomorphOperations.__GetAllomorphObject does not cast to IMoForm before GetForm accesses .Form")` → compute at file time.

**Proposed labels:** `bug`, `log-triage`

---

### 2. flexicon — bug — **P2**
**Title:** `FLExProject.Object(hvoOrGuid) raises an undocumented KeyNotFoundException for stale/unresolvable identifiers instead of returning None`

**Evidence:**
- `logs/2026-09-07/session_013534_auto-Claude-Swahili.log`, op#4 (2026-09-07 02:08:57):
  ```
  ERROR   | Error:           Execution error: Key d66eaaaa-9794-473a-9d4f-480b603fd01b not found in identity map (actually just an ID is present)
  DEBUG   |   File "D:\...\flexicon\flexicon\code\FLExProject.py", line 3224, in Object
  DEBUG   |       return self.project.ServiceLocator.GetObject(hvoOrGuid)
  DEBUG   |   System.Collections.Generic.KeyNotFoundException: Key ... not found in identity map (actually just an ID is present)
  ```
  The user's script (and, separately, *three other scripts in the same two sessions*, e.g.
  `session_013534` ops #2/#3/#5 and `session_024114`) all check `obj = project.Object(guid); if obj is
  None: ...` as their not-found handling — a pattern that appears to be the taught idiom (it works
  fine for a *format-invalid* string, which raises `FP_ParameterError`, but never for a
  well-formed-but-stale GUID, which instead throws a raw CLR exception past the wrapper).
- Confirmed by reading `FLExProject.py:3212-3226` — `Object()` has exactly two outcomes: return the
  resolved object, or raise (`FP_ParameterError` for bad format, or an *unhandled* CLR
  `KeyNotFoundException`/similar for a valid-but-absent id). There is no code path that returns
  `None`.
- The user diagnosed this themselves in-session and wrote a local workaround (`session_013534`
  op#5, 2026-09-07 02:11:26): `def resolve(guid): try: return project.Object(guid) except Exception:
  return None  # project.Object raises KeyNotFoundException for a GUID that is no longer in the
  identity map, rather than returning None.`

**Suspected origin:** flexicon (`FLExProject.py:Object`). Either the docstring/contract should be
corrected to document the exception (and callers taught to catch it), or — preferably, since it
matches the "not found → None" idiom used everywhere else in this codebase — `Object()` should catch
`KeyNotFoundException`-class failures and return `None`.

**Proposed labels:** `bug`, `log-triage`

---

### 3. FlexToolsMCP — enhancement — **P2**
**Title:** `Polymorphic-cast diagnostic hint is inconsistent: silent for pythonnet interface-cast TypeErrors, and misleading (promises a resubmit-fixable rewrite) when the accessed property genuinely doesn't exist on any concrete subtype`

**Evidence (two related facets from the same "Polymorphic hint" subsystem):**

- **(a) No hint at all for interface-cast `TypeError`s.** `session_230055` op#100
  (2026-09-07 00:29:05): user code casts an `ICmAgent` (from `lang.AnalyzingAgentsOC`) to
  `ICmPossibility` — a legitimately wrong cast (`ICmAgent` does not implement `ICmPossibility`; its
  `Name` field is native to `ICmAgent` itself). Preflight said `passed (tier=none)`; runtime raised
  `TypeError: object does not implement ICmPossibility`, and — unlike every `AttributeError`-based
  failure in the same session — **no** `Polymorphic hint:` line was logged, leaving the caller with
  a bare pythonnet cast-failure message and no resubmit guidance.
- **(b) A hint is given, but is unresolvable, when the property name is simply wrong.** Same
  session, op#101 (2026-09-07 00:29:37): `'ICmAgentEvaluation' object has no attribute 'Accepted'` →
  `INFO | Polymorphic hint: object=ICmAgentEvaluation property=Accepted -> resubmit; preflight
  should now emit casting_issues[*].rewrite and casting_issues[*].imports_needed`. Checked against
  `liblcm_api_v11.0.0.json` (`ICmAgentEvaluation` entity, `src/flextoolsmcp/index/liblcm/`): the
  interface has exactly two properties, `Approves` and `Human` — **no** type in the whole schema has
  an `Accepted` property (the real property, used correctly two operations later in the same
  session, is `Approves`). The hint's promise ("preflight should now emit casting_issues[*].rewrite")
  cannot be fulfilled by any cast, because the property is a plain naming typo, not a
  polymorphism/casting problem — sending the caller down a resubmit round-trip that can only fail
  again.

**Suspected origin:** FlexToolsMCP (the polymorphic-hint / casting_issues rewrite-suggestion
machinery invoked after a runtime `PolymorphicAttributeError`/interface-`TypeError`). Two candidate
fixes: (i) also emit a hint (or at minimum classify) `TypeError: object does not implement X` cast
failures, not just `AttributeError`s; (ii) before promising a resubmit-fixable rewrite, check whether
*any* concrete subtype in the index actually has the requested property name — if not, say so
plainly (closest fuzzy-match name, à la `did_you_mean`) instead of implying a cast will fix it.

**Proposed labels:** `enhancement`, `log-triage`

---

### 4. Domain/process note — not filed as a code issue (FYI for the lead)
`session_024114` op#9 (03:19:04) is a clean, in-the-wild confirmation that the `#40 B-1` mitigation
(soften single low-severity casting issues to a warning on read-only runs) is live in production and
behaving as designed. Recommend the archivist/lead attach this log excerpt as a closing-verification
comment on MCP#40 rather than filing anything new.

## Roadblocks / DX

None beyond what is already covered by #3 above and the existing deferred low-volume buckets
(`undefined_variables`, `partial_module_structure`, `undiscovered_entity` — none of which exceeded
their prior counts materially in this window; see "Excluded as noise" #3).

---

**To proceed:** approve which of new-issue proposals **#1, #2, #3** to file (say "file all" / "file
1,2" / "skip"). Item **#4** is not a filing candidate, just a note for the lead/archivist.
