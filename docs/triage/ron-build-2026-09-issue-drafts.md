# Ron-build Log Triage -- Issue Drafts (2026-09-04 .. 2026-09-15)
Status: DRAFT -- nothing filed. Review and approve before any `gh issue create`.

Source: triage shards T1 (2026-09-04/05, German-vocabulary session), T2 (2026-09-10/11, Malayalam AI),
T3 (2026-09-12..14, Malayalam AI), T4 (2026-09-14/15, Malayalam AI). Cross-checked against
`gh issue list --repo MattGyverLee/FlexToolsMCP --state all` and `--repo MattGyverLee/flexicon --state all`,
and against `main` commits `0d3a791` (closes #144) and `991a869` (closes #145).

## Summary Table

| ID | proposed title | repo | severity | occurrences | dates seen | dup of existing issue? |
|----|-----------------|------|----------|--------------|------------|--------------------------|
| ISSUE-01 | New entries/senses/examples default-publish into unrelated publications on creation | flexicon | P1 | 1 audit run uncovering 70 entries + 378 examples | 2026-09-05 | no exact dup found |
| ISSUE-02 | AllomorphOperations.GetForm crashes on non-matching Mo*Allomorph/MoForm subtype (regression of #260) | flexicon | P1 | 5 | 2026-09-10 | regression of flexicon#260 (closed 2026-09-08) |
| ISSUE-03 | FLExProject.OpenProject() rejects 'ui' kwarg on current Flexicon builds | FlexToolsMCP | P1 | 1 (deterministic every session start on this build) | 2026-09-10 | no exact dup found |
| ISSUE-04 | ImportError regression for MSAOperations + new gap for PhonFeatureOperations import name | flexicon | P2 | 4 | 2026-09-10 -> 2026-09-11 | partial regression of flexicon#257 (closed 2026-09-10); related #100 |
| ISSUE-05 | AddPhoneme raises FP_ParameterError on feature-based natural class with no pre-check | flexicon | P2 | 1 | 2026-09-10 | no exact dup found |
| ISSUE-06 | Document/wrap CmPossibilityFactory.Create to avoid overload-resolution TypeErrors | flexicon | P2 | 1 | 2026-09-05 | related flexicon#279 (open, not exact) |
| ISSUE-07 | flexicon API completeness: PhonemeOperations.GetName / LexSenseOperations.GetMSA missing | flexicon | P2 | 2 | 2026-09-13 -> 2026-09-14 | no exact dup found |
| ISSUE-08 | Docs gap: find_writing_system()/GetMorphType() return raw LCM objects, break json.dumps | FlexToolsMCP | P2 | 2 | 2026-09-13 | possible regression of flexicon#211 (closed 2026-07-17) -- verify |
| ISSUE-09 | Bulk-import codegen doesn't auto-create missing POS categories per stated user intent | FlexToolsMCP | P1 | 1 op / 69 sub-failures | 2026-09-13 | no exact dup found |
| ISSUE-10 | undiscovered_entity blocks VariantOperations even though flexicon exposes it | FlexToolsMCP | P2 | 1 | 2026-09-14 | related FlexToolsMCP#100 (open, not exact) |
| ISSUE-11 | Consider proactive stale-lock detection instead of reject-then-retry on project_locked | FlexToolsMCP | P3 | 1 reject+recovery pair | 2026-09-14 | related FlexToolsMCP#145 (closed) -- different code path |

## Drafts

### ISSUE-01
- **repo:** MattGyverLee/flexicon
- **title:** New entries/senses/examples default-publish into unrelated publications on creation
- **labels:** bug, data-integrity, log-triage
- **severity:** P1
- **source findings:** F-T1-03
- **body:**
  ```markdown
  ## What happens
  New `ILexEntry`/`ILexSense` objects (and their example sentences) created via flexicon operations
  are not excluded from unrelated `CmPossibilityList` publications on creation. A themed bulk load
  (e.g. "Car Parts") silently joins every publication it was not explicitly excluded from, including
  unrelated publications like "Body Parts", and newly created examples join *every* publication in
  the project.

  ## Reproduction / evidence
  ```
  2026-09-05 18:07:32 | ERROR   |   report.Error: 70 problem(s) found
  2026-09-05 18:07:32 | WARNING |   report.Warning: Bremsbelag: published in ['Body Parts', 'Car Parts'], expected ['Car Parts']
  2026-09-05 18:07:32 | WARNING |   report.Warning: Autoschlüssel: published in ['Body Parts', 'Car Parts'], expected ['Car Parts']
  2026-09-05 18:07:32 | WARNING |   report.Warning: Stoßdämpfer: published in ['Body Parts', 'Car Parts'], expected ['Car Parts']
  2026-09-05 18:07:32 | WARNING |   report.Warning: ... and 10 more
  ```
  From `session_180332_auto-German_vocabulary.log:770-843`. User's own doc-comment: "the 70 Car Parts
  entries created today silently joined `Body Parts`, and their 378 new example sentences ... joined
  every publication in the project."

  ## User impact
  Ron only discovered the mis-publication via a manual audit script, not from any operation-time
  error or warning. He had to write and run a dedicated repair pass (a second bulk operation) to fix
  already-committed data across 70 entries and 378 examples. Comments in his own scripts
  (`LoadThemeSpec.py`, `SweepThemePublication.py`) show this is the *second* themed load in as many
  days to hit the same gap.

  ## Occurrences
  1 audit-and-repair pair, first seen 2026-09-05 18:07:32 (audit), repaired same day 18:09:31-18:10:50.
  Session: `session_180332_auto-German_vocabulary.log` / `session_182152_auto-German_vocabulary.log`.

  ## Suspected cause
  `ILexEntry`/`ILexSense`/example creation via flexicon operations does not default-exclude new items
  from unrelated publications (`DoNotPublishInRC` is not managed on create), so a themed bulk-load
  silently over-publishes into every publication list in the project unless the caller explicitly
  manages it.

  ## Suggested fix direction
  Either (a) default new entries/senses/examples to being excluded from all publications except an
  explicitly-passed set, or (b) surface a loud warning/report line at creation time listing which
  publications a new item was auto-included in, so callers can immediately see and correct it instead
  of discovering it via a separate audit days later.

  ## Notes
  Filed by /lex-logscan from a runtime-log triage pass (DRAFT -- not yet filed). Fingerprint: 9a1d3172206a.
  ```

### ISSUE-02
- **repo:** MattGyverLee/flexicon
- **title:** AllomorphOperations.GetForm crashes on non-matching Mo*Allomorph/MoForm subtype (regression of #260)
- **labels:** bug, regression, log-triage
- **severity:** P1
- **source findings:** F-T2-05
- **body:**
  ```markdown
  ## What happens
  `AllomorphOperations.GetForm` (via `__GetAllomorphObject`) hard-casts to a single concrete
  `IMoXAllomorph`/`IMoForm` interface without branching on the allomorph's actual subtype, so it
  throws whenever handed the "other" concrete allomorph kind (stem vs affix vs generic MoForm).

  ## Reproduction / evidence
  ```
  2026-09-10 16:18:54 | ERROR   | [FAIL] Operation failed
  2026-09-10 16:18:54 | ERROR   | Error:           Execution error: object does not implement IMoStemAllomorph
  2026-09-10 16:18:54 | DEBUG   |     File "...\flexicon\code\Lexicon\AllomorphOperations.py", line 850, in GetForm
  2026-09-10 16:18:54 | DEBUG   |       allomorph = self.__GetAllomorphObject(allomorph_or_hvo)
  2026-09-10 16:18:54 | DEBUG   |     File "...\AllomorphOperations.py", line 1365, in __GetAllomorphObject
  2026-09-10 16:18:54 | DEBUG   |       return IMoStemAllomorph(obj)
  2026-09-10 16:18:54 | DEBUG   |   TypeError: object does not implement IMoStemAllomorph
  ```
  From `session_161330_auto-Malayalam_AI.log:713-725` and 4 further occurrences (see Occurrences).

  ## User impact
  Recurred 5 times over ~3.5 hours across unrelated scripts inspecting/creating allomorphs for affix
  and stem entries; each time Ron had to fall back to manual `IMoForm(obj)`/`IMoStemAllomorph(obj)`
  casting himself, defeating the purpose of a form-type-agnostic wrapper method.

  ## Occurrences
  5 occurrences, first seen 2026-09-10 16:18:54, last seen 2026-09-10 19:50:58 (IMoStemAllomorph x2,
  IMoForm x2, IMoAffixAllomorph x1). Sessions: `session_161330_auto-Malayalam_AI.log`,
  `session_194358_auto-Malayalam_AI.log`.

  ## Suspected cause
  flexicon#260 ("`AllomorphOperations.__GetAllomorphObject` never casts to IMoForm -- GetForm/Delete
  crash with 'ICmObject' object has no attribute 'Form'") was closed 2026-09-08, two days before this
  cluster of failures. This looks like either an incomplete fix (only one direction of the
  stem/affix/generic-form mismatch was addressed) or a regression -- the failure mode is the same
  class of bug (hard cast to the wrong concrete allomorph interface) but the specific TypeErrors here
  are the *inverse* direction (casting to IMoStemAllomorph/IMoForm and failing on affix/other forms).

  ## Suggested fix direction
  Branch on `ClassName`/concrete subtype inside `__GetAllomorphObject` and try each of
  `IMoStemAllomorph`, `IMoAffixAllomorph`, `IMoForm` in the correct order for the actual object,
  rather than casting to a single fixed interface. Add regression coverage for both directions
  (stem-shaped object handed to an affix-expecting path and vice versa) to prevent re-regression.

  ## Notes
  Filed by /lex-logscan from a runtime-log triage pass (DRAFT -- not yet filed). Fingerprint: 0575f3d82bec.
  Verify against #260's actual fix commit before filing -- may be more appropriate to reopen #260
  than to file a new issue.
  ```

### ISSUE-03
- **repo:** MattGyverLee/FlexToolsMCP
- **title:** FLExProject.OpenProject() rejects 'ui' kwarg on current Flexicon builds
- **labels:** bug, log-triage
- **severity:** P1
- **source findings:** F-T2-01
- **body:**
  ```markdown
  ## What happens
  The MCP's project-open/session bootstrap path calls `FLExProject.OpenProject(..., ui=...)`, but the
  installed Flexicon 4.3.1 build's `OpenProject()` signature does not accept a `ui` keyword argument,
  so the very first operation of a session fails outright.

  ## Reproduction / evidence
  ```
  2026-09-10 15:36:29 | ERROR   | [FAIL] Operation failed
  2026-09-10 15:36:29 | ERROR   | Error:           Failed to open project 'Malayalam AI': FLExProject.OpenProject() got an unexpected keyword argument 'ui'
  2026-09-10 15:36:29 | DEBUG   | Report messages:
  2026-09-10 15:36:29 | WARNING |   report.Warning: flexicon.code.headless_ui.HeadlessLcmUI is not available in this flexicon build; falling back to the WinForms FwLcmUI.
  ```
  From `session_153525_auto-Malayalam_AI.log:118-121`.

  ## User impact
  Whole operation aborted before any project access; blocked Ron's very first read-only survey of the
  project on this session. Self-recovered on retry (the very next operation succeeded), but every
  session start pays this cost until the MCP's assumed Flexicon signature is reconciled with what's
  actually installed.

  ## Occurrences
  1 occurrence in this shard, 2026-09-10 15:36:29, but the code path is deterministic on this
  Flexicon build -- expect it on every `OpenProject` call until fixed.

  ## Suspected cause
  Version-skew between the MCP's assumed Flexicon `OpenProject()` signature (server.py or session
  manager wrapping the call) and the installed Flexicon 4.3.1 API surface -- likely a `ui=` parameter
  added/removed/renamed between Flexicon versions that the MCP doesn't guard for.

  ## Suggested fix direction
  Introspect the installed Flexicon's `OpenProject` signature (or capability-version-gate it, similar
  to the pattern already used for `undoable`) before passing `ui=`, and add a regression test across
  the Flexicon versions this repo claims to support.

  ## Notes
  Filed by /lex-logscan from a runtime-log triage pass (DRAFT -- not yet filed). Fingerprint: a4645303ac0a.
  ```

### ISSUE-04
- **repo:** MattGyverLee/flexicon
- **title:** ImportError regression for MSAOperations + new gap for PhonFeatureOperations import name
- **labels:** bug, regression, log-triage
- **severity:** P2
- **source findings:** F-T2-04
- **body:**
  ```markdown
  ## What happens
  `from flexicon import MSAOperations` and `from flexicon import PhonFeatureOperations` both raise
  `ImportError: cannot import name '...' from 'flexicon'`, recurring 4 times across ~23 hours on two
  different plausible-but-wrong class names.

  ## Reproduction / evidence
  ```
  2026-09-11 09:39:57 | ERROR   | [FAIL] Operation failed
  2026-09-11 09:39:57 | ERROR   | Error:           Execution error: cannot import name 'PhonFeatureOperations' from 'flexicon' (...\flexicon\__init__.py)
  2026-09-11 09:39:57 | DEBUG   |   ImportError: cannot import name 'PhonFeatureOperations' from 'flexicon' (...). Did you mean: 'PhonemeOperations'?
  ```
  From `session_141110_auto-Malayalam_AI.log:730-733`; also `session_161330...log:392-398,2330-2336` and
  `session_145940...log:508-511`.

  ## User impact
  4 wasted round-trips across two sessions/days; no data loss (caught at import time before any
  write), but each failure cost a full LLM turn to interpret and retry with a different guessed name.

  ## Occurrences
  4: `MSAOperations` at 2026-09-10 16:17:03 and 2026-09-11 15:11:10; `PhonFeatureOperations` at
  2026-09-11 09:39:57 and 2026-09-11 14:29:26.

  ## Suspected cause
  flexicon#257 ("`from flexicon import MSAOperations` raises ImportError although the API index
  advertises it") was closed 2026-09-10T19:42:52Z. The `MSAOperations` failure at 2026-09-11 15:11:10
  occurred *after* that close timestamp, suggesting either an incomplete fix or that the fix hadn't
  reached the installed build. The `PhonFeatureOperations` failures are a distinct name never covered
  by #257, and are likely the same root cause as FlexToolsMCP#100 (index entities lack `access_path`,
  so facade-only classes aren't correctly surfaced/importable) -- `get_object_api`/`search_by_capability`
  never surfaced the correct class names (`POSOperations` for MSA-like work, `PhonemeOperations` for
  phon features) before code generation.

  ## Suggested fix direction
  Confirm #257's fix is actually present in the installed 4.3.1 build (version-pin/regression test);
  separately, add `PhonFeatureOperations`-style guidance (or better, correct the guessed name to
  `PhonemeOperations` proactively) to the MCP's discovery/search layer referenced in #100.

  ## Notes
  Filed by /lex-logscan from a runtime-log triage pass (DRAFT -- not yet filed). Fingerprint: 19e03343f7c2.
  Check flexicon#257 and FlexToolsMCP#100 before filing -- this may split into a regression comment on
  #257 plus a comment on #100 rather than a standalone issue.
  ```

### ISSUE-05
- **repo:** MattGyverLee/flexicon
- **title:** AddPhoneme raises FP_ParameterError on feature-based natural class with no pre-check
- **labels:** enhancement, dx, log-triage
- **severity:** P2
- **source findings:** F-T2-03
- **body:**
  ```markdown
  ## What happens
  `NaturalClassOperations.AddPhoneme` raises a hard `FP_ParameterError` when the target natural class
  is feature-based rather than segment-based, with no discoverable way to check a natural class's
  kind before calling it.

  ## Reproduction / evidence
  ```
  2026-09-10 16:14:15 | ERROR   | [FAIL] Operation failed
  2026-09-10 16:14:15 | ERROR   | Error:           Execution error: Cannot add phoneme to feature-based natural class
  2026-09-10 16:14:15 | DEBUG   |     File "...\flexicon\code\Grammar\NaturalClassOperations.py", line 712, in AddPhoneme
  2026-09-10 16:14:15 | DEBUG   |       raise FP_ParameterError("Cannot add phoneme to feature-based natural class")
  2026-09-10 16:14:15 | DEBUG   |   flexicon.code.exceptions.FP_ParameterError: Cannot add phoneme to feature-based natural class
  ```
  From `session_161330_auto-Malayalam_AI.log:176-191`.

  ## User impact
  Blocked Ron's whole phoneme-repopulation script (replacing the stock phoneme inventory with
  Malayalam graphemes) at the first natural class that happened to be feature-based; he had to
  inspect and branch around it manually with no documented signal for which classes were which kind.

  ## Occurrences
  1 occurrence, 2026-09-10 16:14:15.

  ## Suspected cause
  `NaturalClassOperations` has no `GetKind()`/`IsFeatureBased()`-style accessor, so the only way to
  learn a class is feature-based is to hit the exception.

  ## Suggested fix direction
  Add a `NaturalClassOperations.GetKind()` (or `IsFeatureBased`) accessor and document it alongside
  `AddPhoneme` so calling code can branch before attempting the call.

  ## Notes
  Filed by /lex-logscan from a runtime-log triage pass (DRAFT -- not yet filed). Fingerprint: 5d5876e108a1.
  ```

### ISSUE-06
- **repo:** MattGyverLee/flexicon
- **title:** Document/wrap CmPossibilityFactory.Create to avoid overload-resolution TypeErrors
- **labels:** enhancement, dx, log-triage
- **severity:** P2
- **source findings:** F-T1-01
- **body:**
  ```markdown
  ## What happens
  flexicon has no convenience wrapper for creating a new `CmPossibility` (e.g. a "Publication Type"),
  forcing users into raw `SIL.LCModel` reflection where pythonnet's .NET overload resolution errors
  are opaque and don't hint which overload of `Create()` is expected.

  ## Reproduction / evidence
  ```
  2026-09-05 08:07:05 | ERROR   | [FAIL] Operation failed
  2026-09-05 08:07:05 | ERROR   | Error type:      OverloadResolutionError
  2026-09-05 08:07:05 | ERROR   | Error:           Execution error: No method matches given arguments for CmPossibilityFactory.Create: (<class 'System.Guid'>, <class 'SIL.LCModel.ICmPossibilityList'>)
  2026-09-05 08:07:05 | DEBUG   |     File "<string>", line 59, in Main
  2026-09-05 08:07:05 | DEBUG   |   TypeError: No method matches given arguments for CmPossibilityFactory.Create: (<class 'System.Guid'>, <class 'SIL.LCModel.ICmPossibilityList'>)
  ```
  From `session_223903_auto-German_vocabulary.log:896-905`.

  ## User impact
  Ron could not create a new "Publication Type" possibility (needed for a themed vocabulary load) on
  the first attempt and had to spend a follow-up turn discovering the correct raw-LCM call convention
  himself.

  ## Occurrences
  1 occurrence, 2026-09-05 08:07:05.

  ## Suspected cause
  No `CmPossibilityOperations`/`CreatePossibility`-style helper exists in flexicon, so users fall back
  to raw `SIL.LCModel` reflection and guess the wrong overload.

  ## Suggested fix direction
  Add a documented possibility-creation helper (or at minimum a worked example in
  `get_object_api`/docs) covering the correct `CmPossibilityFactory.Create` overload for common cases.
  Related to the open API-decision item in flexicon#279 ("FLExProject possibility helpers need an API
  decision") -- worth resolving together.

  ## Notes
  Filed by /lex-logscan from a runtime-log triage pass (DRAFT -- not yet filed). Fingerprint: 2430405ec599.
  ```

### ISSUE-07
- **repo:** MattGyverLee/flexicon
- **title:** flexicon API completeness: PhonemeOperations.GetName / LexSenseOperations.GetMSA missing
- **labels:** bug, log-triage
- **severity:** P2
- **source findings:** F-T3-04, F-T3-09
- **body:**
  ```markdown
  ## What happens
  Two sibling-accessor gaps in the same session, both blocking read-only diagnostic scripts:
  - `PhonemeOperations` has `GetCodes` but no `GetName` (or equivalent).
  - `LexSenseOperations` has `GetPartOfSpeech`/`GetGloss` but no `GetMSA` accessor for the sense's
    `MorphoSyntaxAnalysisRA`.

  ## Reproduction / evidence
  ```
  2026-09-13 22:42:39 | ERROR   | [FAIL] Operation failed
  2026-09-13 22:42:39 | ERROR   | Error:           Execution error: 'PhonemeOperations' object has no attribute 'GetName'
  2026-09-13 22:42:39 | DEBUG   |     File "<string>", line 8, in <module>
  2026-09-13 22:42:39 | DEBUG   |   AttributeError: 'PhonemeOperations' object has no attribute 'GetName'
  ...
  2026-09-14 12:08:37 | ERROR   | [FAIL] Operation failed
  2026-09-14 12:08:37 | ERROR   | Error:           Execution error: 'LexSenseOperations' object has no attribute 'GetMSA'
  2026-09-14 12:08:37 | DEBUG   |     File "<string>", line 18, in <module>
  2026-09-14 12:08:37 | DEBUG   |   AttributeError: 'LexSenseOperations' object has no attribute 'GetMSA'
  ```
  From `session_223712_auto-Malayalam_AI.log:237-262` and `:3311-3382`.

  ## User impact
  Both blocked read-only diagnostic reads (a phoneme-inventory dump to validate new graphemes, and an
  MSA-kind inspection of existing entries); Ron would otherwise need to fall back to direct
  `IPhPhoneme`/`sen.MorphoSyntaxAnalysisRA` access, defeating the purpose of the wrapper classes.

  ## Occurrences
  2: `PhonemeOperations.GetName` at 2026-09-13 22:42:39; `LexSenseOperations.GetMSA` at
  2026-09-14 12:08:37.

  ## Suspected cause
  Naming-inconsistency vs. sibling `*Operations` classes, which generally expose a name-like getter
  (`LexEntryOperations.GetLexemeForm`, `POSOperations`, etc.) and MSA access where relevant.

  ## Suggested fix direction
  Add `PhonemeOperations.GetName` and `LexSenseOperations.GetMSA` wrappers, and audit other
  `*Operations` classes for the same class of missing-sibling-accessor gap (per T3 shard's own
  recommendation to consolidate rather than file per-method).

  ## Notes
  Filed by /lex-logscan from a runtime-log triage pass (DRAFT -- not yet filed). Fingerprint: 800ccfe4afab.
  ```

### ISSUE-08
- **repo:** MattGyverLee/FlexToolsMCP
- **title:** Docs gap: find_writing_system()/GetMorphType() return raw LCM objects, break json.dumps
- **labels:** documentation, log-triage
- **severity:** P2
- **source findings:** F-T3-03
- **body:**
  ```markdown
  ## What happens
  `find_writing_system(...)` and `project.LexEntry.GetMorphType(e)` return raw LCM/.NET objects
  (`CoreWritingSystemDefinition`, `IMoMorphType`) rather than JSON-safe primitives, so a straightforward
  "dump entries to JSON" script fails with `TypeError: Object of type ... is not JSON serializable`.

  ## Reproduction / evidence
  ```
  2026-09-13 22:39:00 | ERROR   | [FAIL] Operation failed
  2026-09-13 22:39:00 | ERROR   | Error:           Execution error: Object of type IMoMorphType is not JSON serializable
  2026-09-13 22:39:00 | DEBUG   |     File "<string>", line 26, in <module>
  2026-09-13 22:39:00 | DEBUG   |   TypeError: Object of type IMoMorphType is not JSON serializable
  ...
  2026-09-13 22:39:24 | ERROR   | [FAIL] Operation failed
  2026-09-13 22:39:24 | ERROR   | Error:           Execution error: Object of type CoreWritingSystemDefinition is not JSON serializable
  2026-09-13 22:39:24 | DEBUG   |   TypeError: Object of type CoreWritingSystemDefinition is not JSON serializable
  ```
  From `session_223712_auto-Malayalam_AI.log:92-113,157-182`.

  ## User impact
  Two wasted round-trips (~19s combined) before Ron manually added `.Handle` / `.Name.BestAnalysisAlternative.Text`
  accessors himself while trying to dump all entries to JSON for duplicate checking.

  ## Occurrences
  2: `IMoMorphType` at 2026-09-13 22:39:00, `CoreWritingSystemDefinition` at 2026-09-13 22:39:24.

  ## Suspected cause
  flexicon#211 ("find_writing_system() returns a WS object, not the int Handle that get_String/
  GetFreeTranslation need") was closed 2026-07-17, nearly two months before this occurrence -- the
  `CoreWritingSystemDefinition` leak here may indicate that fix didn't cover every call site, or is a
  regression, or (more likely) that #211 fixed the specific `get_String`/`GetFreeTranslation` argument
  case but `find_writing_system()`'s direct return value is still a raw WS object in other contexts.
  The `GetMorphType()` half is a separate, likely-never-filed gap.

  ## Suggested fix direction
  Verify #211's fix scope against this exact call pattern (regression check first). Separately, add a
  FLEXTOOLS-STYLE-GUIDE.md callout (per CLAUDE.md's existing "Empty Multistring Fields" pattern) that
  `find_writing_system()` and `GetMorphType()` return LCM objects, not JSON-safe values, with the
  correct accessor to extract a primitive.

  ## Notes
  Filed by /lex-logscan from a runtime-log triage pass (DRAFT -- not yet filed). Fingerprint: db91684ad7f6.
  Regression-check against flexicon#211 before filing as new.
  ```

### ISSUE-09
- **repo:** MattGyverLee/FlexToolsMCP
- **title:** Bulk-import codegen doesn't auto-create missing POS categories per stated user intent
- **labels:** enhancement, dx, log-triage
- **severity:** P1
- **source findings:** F-T3-05
- **body:**
  ```markdown
  ## What happens
  A generated bulk-import script for closed-class lexical entries (pronouns, interrogatives,
  conjunctions) guarded each row with `if p is None: raise RuntimeError(...)` against
  `project.POS.Find(name)`, but never created the missing part-of-speech categories, even though the
  user's stated plan was "use the grammatical category catalog if the project doesn't currently have a
  needed category." Every one of the 69 rows failed identically.

  ## Reproduction / evidence
  ```
  2026-09-13 23:07:55 | ERROR   | [FAIL] Operation failed
  2026-09-13 23:07:55 | ERROR   | Error type:      ReportedError
  2026-09-13 23:07:55 | ERROR   | Error:           Operation reported 69 error(s) via report.Error(); see messages for details.
  2026-09-13 23:07:55 | ERROR   |   report.Error: FAILED ഞാൻ (1SG): POS not found: Personal pronoun
  2026-09-13 23:07:55 | ERROR   |   report.Error: FAILED നീ (2SG): POS not found: Personal pronoun
  2026-09-13 23:07:55 | DEBUG   |   report.Info: batch=closed planned=69 created=0 skipped_existing=0 failed=69
  ```
  From `session_223712_auto-Malayalam_AI.log:475-691`.

  ## User impact
  100% of the closed-class import batch (69/69 rows) produced zero entries, stalling a large fraction
  of Ron's overall multi-step lexicon-build task for that session.

  ## Occurrences
  1 batch operation, 69 sub-failures, 2026-09-13 23:07:55.

  ## Suspected cause
  This is a code-generation/style-guide gap rather than a framework bug: the per-row guard
  (`if p is None: raise ...`) is defensible in isolation, but the generated script never honored the
  user's explicit fallback instruction to create missing categories first.

  ## Suggested fix direction
  Add a FLEXTOOLS-STYLE-GUIDE.md pattern for "ensure or create" lookups (find-or-create for POS/
  possibility-list entries) so generated bulk-import scripts default to creating missing catalog
  entries when the user's intent says to, rather than hard-failing every dependent row.

  ## Notes
  Filed by /lex-logscan from a runtime-log triage pass (DRAFT -- not yet filed). Fingerprint: 4bca0c7c10b8.
  ```

### ISSUE-10
- **repo:** MattGyverLee/FlexToolsMCP
- **title:** undiscovered_entity blocks VariantOperations even though flexicon exposes it
- **labels:** bug, log-triage
- **severity:** P2
- **source findings:** F-T3-08
- **body:**
  ```markdown
  ## What happens
  A script using `project.Variants.Create(...)` / `project.Variants.AddComponentLexeme(...)` (backed
  by flexicon's `VariantOperations`, which does exist) was rejected pre-flight with
  `undiscovered_entity: undiscovered=['VariantOperations']`.

  ## Reproduction / evidence
  ```
  2026-09-14 10:52:04 | WARNING | [REJECT] Pre-flight validation blocked execution
  2026-09-14 10:52:04 | WARNING | Reason code:     undiscovered_entity
  2026-09-14 10:52:04 | WARNING |   undiscovered=['VariantOperations']
  ```
  From `session_223712_auto-Malayalam_AI.log:2907-2909`.

  ## User impact
  Blocked an oblique-case variant lexeme entry creation step; the underlying flexicon class is real
  and usable, so this is a false rejection purely from an index gap.

  ## Occurrences
  1 occurrence, 2026-09-14 10:52:04.

  ## Suspected cause
  Likely the same root cause documented in FlexToolsMCP#100 ("Index entities lack access_path, so
  project-facade-only classes look top-level importable") -- `VariantOperations` is reached via
  `project.Variants`, a facade attribute, and the static index/entity-discovery pass in
  `flexicon_analyzer` may not be recognizing facade-only classes as discovered entities consistently.

  ## Suggested fix direction
  Cross-reference with #100's fix once landed; if #100 doesn't cover this exact case, extend the
  index-refresh/discovery pass to recognize `VariantOperations` (and audit siblings) as discovered via
  their facade attribute path.

  ## Notes
  Filed by /lex-logscan from a runtime-log triage pass (DRAFT -- not yet filed). Fingerprint: e00ff222d6b6.
  Check against FlexToolsMCP#100 before filing -- may be more appropriate as a comment there.
  ```

### ISSUE-11
- **repo:** MattGyverLee/FlexToolsMCP
- **title:** Consider proactive stale-lock detection instead of reject-then-retry on project_locked
- **labels:** enhancement, dx, log-triage
- **severity:** P3
- **source findings:** F-T3-06
- **body:**
  ```markdown
  ## What happens
  When a project lock is held by a dead PID, the current flow is reject-with-`verdict=held_by_other`,
  then a resubmit ~2 minutes later self-heals via `[SHARED] stale_lock (dead PID) proceeding`. This
  worked correctly in the observed case, but required a full user resubmit rather than resolving
  automatically.

  ## Reproduction / evidence
  ```
  2026-09-14 05:40:56 | WARNING | [REJECT] Pre-flight validation blocked execution
  2026-09-14 05:40:56 | WARNING | Reason code:     project_locked
  2026-09-14 05:40:56 | WARNING |   verdict=held_by_other sharing_enabled=True holder_pid=8452 holder_process=python
  ...
  2026-09-14 05:43:07 | WARNING | [SHARED] 'Malayalam AI' stale_lock (dead PID 8452); proceeding with the write.
  ```
  From `session_223712_auto-Malayalam_AI.log:1091-1140`.

  ## User impact
  ~2 minute stall/blocked retry; no data loss, self-resolved on resubmit.

  ## Occurrences
  1 reject+recovery pair, 2026-09-14 05:40:56 -> 05:43:07.

  ## Suspected cause
  Stale-lock (dead-PID) detection currently only runs as part of the resubmit path, not proactively
  at reject time.

  ## Suggested fix direction
  When `project_locked` would reject with `verdict=held_by_other`, check liveness of `holder_pid`
  before rejecting, and proceed immediately (with the same `[SHARED] stale_lock` logging) if the
  holder is already dead, instead of requiring a resubmit. Note this is a different code path from
  FlexToolsMCP#145 (fixed: health-call lock re-scanning); this is about the run_module preflight path
  specifically.

  ## Notes
  Filed by /lex-logscan from a runtime-log triage pass (DRAFT -- not yet filed). Fingerprint: c484792c180c.
  ```

## Deliberately Not Filed

| signature | why not (benign / duplicate of #N / insufficient evidence) |
|-----------|--------------------------------------------------------------|
| F-T2-06 (`PolymorphicAttributeError` on `RightHandSidesOS`/`get_WritingSystem`, self-labeled issue #40 B-1) | already tracked -- see #39, #40, #108, #111, #122, #123, #137 |
| F-T3-01 (`IMoAffixForm.PhoneEnvRC` PolymorphicAttributeError, preflight reactive not proactive) | duplicate of the same open cluster (#108 "three gaps in one emitter", #122 "runtime hint promises a rewrite that is never produced") |
| F-T3-02 (`casting_issues_detected` on `WritingSystems.CurrentVernacularWritingSystems`, working-as-designed reject) | duplicate of #108/#39 cluster; not a new bug |
| F-T3-07 (6x `casting_issues_detected` rejects in ~90 min, aggregate DX drag) | duplicate of #108/#39/#40 cluster -- add as field-evidence comment on #108, not a new issue |
| F-T3-11 (`IMoStemAllomorph.InflectionClassesRC` PolymorphicAttributeError) | duplicate of same cluster, explicitly noted in T3 as related to F-T3-01 |
| F-T4-01 (4x PolymorphicAttributeError post-hoc across a 29h window, narrow-heuristic-coverage pattern) | duplicate of #108/#122/#39/#40/#123/#137 cluster |
| F-T4-02 (`TypeError: object does not implement IMoStemAllomorph` on unconditional cast in AlternateFormsOS loop) | same cluster as F-T4-01/ISSUE-02's underlying pattern; insufficient evidence to split into its own issue beyond ISSUE-02 |
| F-T4-03 (`AllomorphEnvironments` returns `None`, not empty, breaking a list comprehension) | related to ISSUE-02/#260's allomorph-subtype-handling family; fold into ISSUE-02 as an additional symptom rather than filing separately |
| F-T1-02 (`api_discovery_required` preflight rejects a repair pass reusing prior session's APIs) | possible dup of FlexToolsMCP#80 ("Graceful discovery redirect + provenance-sensitive preflight") -- the log itself cross-references "issue #80" for a related discovery-gate path |
| F-T2-02 (`HeadlessLcmUI` not available, falls back to WinForms `FwLcmUI`, `ConflictingSave` hang hazard) | matches FlexToolsMCP#148 ("HeadlessLcmUI ImportError probe rests on a premise flexicon #285 reversed") -- #285 (closed 2026-09-08) was supposed to make HeadlessLcmUI the default before this 2026-09-10 occurrence; flag as regression evidence on #148, not a new issue |
| F-T2-07 (`Project 'Malayalam AI' is currently locked by another process`, 5x) | pre-fix evidence for FlexToolsMCP#145 (closed 2026-09-18, "flextools_health replays a startup snapshot ... instead of re-scanning") -- these logs (2026-09-10/11) predate the fix; confirms the bug was real, nothing further to file |
| F-T2-08 (`OpenProject(undoable=False)` legacy-mode partial-write hazard, co-occurring with several other failures) | pre-fix evidence for FlexToolsMCP#144 (closed 2026-09-18) and live evidence for the still-open #153 ("Non-undoable degradation is still silent on flexicon <=4.3.0") -- add as a field-evidence comment on #153, not a new issue |
| F-T3-10 (`ITsString.set_String` AttributeError -- user miscast; but the co-occurring `undoable=False` stderr warning shows a real partial-write leak, confirmed by the next operation's own "clean up the empty environment left by the previous failed run") | the AttributeError itself is a user-code bug (not filed); the partial-write leak is the same #144/#153 pattern as F-T2-08 above -- add as further field evidence on #153, not a new issue |
| F-T4-04 (`ArgumentNullException: Parameter name: newby` from pushing `None` into `LcmList.Add`, with the same `undoable=False` stderr) | root cause is a user-script bug (missing `assert obl_type is not None`); the `undoable=False` partial-write angle is again #144/#153 field evidence, not new |
| F-T1-01's raw exemplar overlap, `Execution error: Null parameter.` (`session_194358`, 19:46:50) | insufficient evidence -- looks like exploratory user miscast (`IMoForm(project.Object(sa.Hvo))`), not a clear wrapper bug |
| `TypeError: not all arguments converted during string formatting` (`session_194358` op#1) | user's own `%`-format string/arg-count mismatch in a debug probe, not a framework issue |
| 68-line `report.Error: <letter> stored={} expected={...}` drift-detection output (`session_161330` op#37) | likely a downstream symptom of the #144/#153 undoable=False write-ordering hazard rather than an independent bug; cross-referenced only |
| `[VALIDATE] validate_only close: status=validation_failed` (T3, 2x) | working-as-designed dry-run business-rule validation output, not a tool/framework error |
| Assorted `except Exception:` / `report.Error("preconditions failed...")` / `made, skipped, failed = 0,0,0` lines across all four shards | confirmed to be DEBUG-level echoes of the user's own generated script source, not runtime events (see each shard's own Section 2) |
| Routine `Preflight: passed`, `[SESSION-CONFIGURED]`, session banners | expected structural log lines |

## Proposed logscan-state.json Additions (NOT applied)

```json
{
  "9a1d3172206a": {
    "repo": "MattGyverLee/flexicon",
    "issue": null,
    "url": null,
    "signature": "New entries/senses/examples default-publish into unrelated publications on creation",
    "first_seen": "2026-09-05T18:07:32Z",
    "last_seen": "2026-09-05T18:10:50Z",
    "occurrences": 1,
    "state": "draft-pending-approval"
  },
  "0575f3d82bec": {
    "repo": "MattGyverLee/flexicon",
    "issue": null,
    "url": null,
    "signature": "AllomorphOperations.GetForm TypeError object does not implement IMoStemAllomorph/IMoForm/IMoAffixAllomorph (regression of #260)",
    "first_seen": "2026-09-10T16:18:54Z",
    "last_seen": "2026-09-10T19:50:58Z",
    "occurrences": 5,
    "state": "draft-pending-approval"
  },
  "a4645303ac0a": {
    "repo": "MattGyverLee/FlexToolsMCP",
    "issue": null,
    "url": null,
    "signature": "FLExProject.OpenProject() got an unexpected keyword argument 'ui'",
    "first_seen": "2026-09-10T15:36:29Z",
    "last_seen": "2026-09-10T15:36:29Z",
    "occurrences": 1,
    "state": "draft-pending-approval"
  },
  "19e03343f7c2": {
    "repo": "MattGyverLee/flexicon",
    "issue": null,
    "url": null,
    "signature": "ImportError cannot import name MSAOperations/PhonFeatureOperations from flexicon (partial regression of #257)",
    "first_seen": "2026-09-10T16:17:03Z",
    "last_seen": "2026-09-11T15:11:10Z",
    "occurrences": 4,
    "state": "draft-pending-approval"
  },
  "5d5876e108a1": {
    "repo": "MattGyverLee/flexicon",
    "issue": null,
    "url": null,
    "signature": "NaturalClassOperations.AddPhoneme FP_ParameterError, no pre-check for feature-based natural class",
    "first_seen": "2026-09-10T16:14:15Z",
    "last_seen": "2026-09-10T16:14:15Z",
    "occurrences": 1,
    "state": "draft-pending-approval"
  },
  "2430405ec599": {
    "repo": "MattGyverLee/flexicon",
    "issue": null,
    "url": null,
    "signature": "CmPossibilityFactory.Create OverloadResolutionError, no documented/wrapped possibility-creation helper",
    "first_seen": "2026-09-05T08:07:05Z",
    "last_seen": "2026-09-05T08:07:05Z",
    "occurrences": 1,
    "state": "draft-pending-approval"
  },
  "800ccfe4afab": {
    "repo": "MattGyverLee/flexicon",
    "issue": null,
    "url": null,
    "signature": "PhonemeOperations missing GetName / LexSenseOperations missing GetMSA sibling accessors",
    "first_seen": "2026-09-13T22:42:39Z",
    "last_seen": "2026-09-14T12:08:37Z",
    "occurrences": 2,
    "state": "draft-pending-approval"
  },
  "db91684ad7f6": {
    "repo": "MattGyverLee/FlexToolsMCP",
    "issue": null,
    "url": null,
    "signature": "find_writing_system/GetMorphType return raw LCM objects, break json.dumps (possible regression of flexicon#211)",
    "first_seen": "2026-09-13T22:39:00Z",
    "last_seen": "2026-09-13T22:39:24Z",
    "occurrences": 2,
    "state": "draft-pending-approval"
  },
  "4bca0c7c10b8": {
    "repo": "MattGyverLee/FlexToolsMCP",
    "issue": null,
    "url": null,
    "signature": "Bulk-import codegen does not auto-create missing POS categories per stated user intent",
    "first_seen": "2026-09-13T23:07:55Z",
    "last_seen": "2026-09-13T23:07:55Z",
    "occurrences": 1,
    "state": "draft-pending-approval"
  },
  "e00ff222d6b6": {
    "repo": "MattGyverLee/FlexToolsMCP",
    "issue": null,
    "url": null,
    "signature": "undiscovered_entity: undiscovered=['VariantOperations'] despite flexicon exposing it",
    "first_seen": "2026-09-14T10:52:04Z",
    "last_seen": "2026-09-14T10:52:04Z",
    "occurrences": 1,
    "state": "draft-pending-approval"
  },
  "c484792c180c": {
    "repo": "MattGyverLee/FlexToolsMCP",
    "issue": null,
    "url": null,
    "signature": "project_locked reject-then-retry instead of proactive stale-lock (dead PID) detection",
    "first_seen": "2026-09-14T05:40:56Z",
    "last_seen": "2026-09-14T05:43:07Z",
    "occurrences": 1,
    "state": "draft-pending-approval"
  }
}
```
