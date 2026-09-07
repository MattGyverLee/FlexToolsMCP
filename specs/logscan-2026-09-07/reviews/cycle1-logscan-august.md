# Log-Scan Proposal — August window (2026-08-10 -> 2026-08-28)

Phase A only. Read-only. Nothing filed, nothing written to `docs/logscan-state.json`.

Scanned by: peer-scoped instance of `/lex-logscan` (August window only; a sibling
instance owns 2026-09-06/09-07 and was not touched here).

## Scan inventory

**Date directories read** (13 requested, all present): `2026-08-10, 08-11, 08-12,
08-13, 08-14, 08-15, 08-16, 08-18, 08-19, 08-21, 08-26, 08-28`.

**Session log files found:** 514 total across the window.
- 485 are automated test-fixture reruns (see "Excluded as noise").
- 29 are real user/developer sessions, individually grepped for
  `ERROR|Traceback|Exception|CRITICAL|\[FAIL\]|\[REJECT\]` with context:
  - 08-11: `session_091536_auto-Ejagham_Full_GT-Test.log`,
    `session_091817_auto-Ejagham_Full_GT-Test.log`,
    `session_092120_auto-Ejagham_Full_GT-Test.log`
  - 08-12/13: `session_215608_auto-Claude-Swahili.log`,
    `session_215659_auto-Claude-Swahili.log`,
    `session_235236_auto-Claude-Swahili.log` (crosses midnight into 08-13),
    `session_232416_auto-feat-swahili.log`
  - 08-13: `session_005026/005815/091319_auto-Claude-Swahili.log`,
    `session_221201_auto-Mayanau-Bena-Yungur_Toy.log`
  - 08-15: `session_204541_auto-Target.log`, `session_204945_auto-Target.log`
    (CP1/#92 e2e regression-test session)
  - 08-16: `session_101708_auto-Ejagham_Mini.log`
  - 08-18: `session_083201/134005/213820_auto-Ejagham_Mini.log`
  - 08-19: `session_002259/042024/085008_auto-Ejagham_Mini.log`,
    `session_002849/012943_auto-Ngoreme_FLEx.log`,
    `session_025142_auto-Ngoreme_Target.log`
  - 08-21: `session_084257_auto-Mbugwe_LizzieHC_practice.log`
  - 08-26: `session_144717_auto-GT038_NKP2_Throwaway.log`,
    `session_160242_auto-Ejagham_W_Mini.log`
  - 08-28: `session_141154_auto-7a5e324....log`,
    `session_141343_auto-Ngoreme_FLEx.log`,
    `session_164425_auto-94031e534a....log`

**Rollup files — re-baselined (ledger's 2026-07-20 cursor is stale/rotated):**
- `operations.log` **rotated**. The predecessor is now `operations.log.1`
  (5,242,870 bytes; covers 2026-04-07 -> 2026-08-10 11:05:36, i.e. it already
  passed the ledger's old 2,994,063-byte cursor). The live `operations.log` is
  a fresh file: **4,567,946 bytes, 66,313 lines**, first entry
  2026-08-21 08:42:57, last entry 2026-09-07 03:35:06.
  **Gap:** neither file has any line for 2026-08-11 through 2026-08-20
  (log.1 stops mid-08-10; the new log.1 starts 08-21). Text-rollup coverage
  for that 10-day span does not exist; only per-session log files and
  `operations.jsonl` cover it. This is itself a minor logging-robustness gap
  (noted, not proposed as a standalone issue — low severity, no user impact
  since per-session logs + jsonl are unaffected).
- `operations.jsonl` **not rotated**, continuously covers the whole window.
  New baseline: **471,083 bytes, 647 lines total**, record dates span
  2026-07-07 -> 2026-09-07 with no gaps. Records with `ts` in
  `[2026-08-10, 2026-08-28]`: **226**.
  Outcome tally for those 226: `ok=134, preflight_reject=41, runtime_fail=31,
  validate_only=20`.
  Error-code tally: `casting_issues_detected=31, runtime_error=19,
  PolymorphicAttributeError=10, unprotected_writes=2, api_discovery_required=2,
  partial_module_structure=3, OverloadResolutionError=1, project_locked=1,
  confirmation_required=1, syntax_error=1, ReportedError=1`.

**Suggested new `scanned_through` values for the ledger** (for whoever merges
this window in): `operations_log_bytes: 4567946` (post-rotation file),
`operations_log_rotated_predecessor: {"file": "operations.log.1", "bytes":
5242870, "max_date": "2026-08-10"}`, `operations_jsonl_lines: 647`,
`max_log_date: 2026-08-28` (bounded to this scan's assigned window; the
peer scan owns 09-06/09-07).

## Excluded as noise

- **485 automated test-fixture session files** across 08-10, 08-12, 08-13,
  08-14, 08-16, 08-19 — `session_*_auto-Proj_r1_default/explicit_false/
  inherit/readonly.log`, `auto-Proj_coerce/inherit/no_undoable/no_write/
  chk/no_pop/temp/undoable_field.log`, `auto-Issue10TestProject.log`,
  `test-recipes.log`. Confirmed byte-near-identical harness reruns (spot
  checked `session_095208_auto-Proj_r1_default.log` vs
  `session_110307_auto-Proj_r1_default.log`: same session-inheritance /
  write-gate smoke-test shape, differing only in FlexToolsMCP version
  banner). No `ERROR|[FAIL]|[REJECT]` matches in any of them (directory-wide
  grep of 08-14/08-16/08-18 fixture-only ranges came back empty). Excluded
  per the noise-exclusion rule; no genuine defect found inside them this
  pass.
- **`Object of type method is not JSON serializable`** — 08-18 21:45:14,
  `session_213820_auto-Ejagham_Mini.log` op-214452953-010. User's own script
  passed a bound method into `json.dumps(...)`. Not a FlexToolsMCP/flexicon
  defect.
- **`source code string cannot contain null bytes`** — 08-18 21:40:04, same
  session, op syntax_error. The submitted source itself contained a stray
  NUL byte (also independently visible in the session's own log file, which
  contains exactly one `\x00`, tripping `grep`'s binary-file heuristic on
  read — had to re-grep with `-a`). Root cause looks like corruption
  upstream of the MCP (a copy/paste or file-read artifact on the caller's
  side); no evidence it originates in FlexToolsMCP or flexicon. Not proposed.
- **`unprotected_writes` (x2, e.g. Target 08-15 20:46:39, `mutating_calls=
  ['SetForm']`) and `confirmation_required` (x1, Target 08-15 20:51:25)** —
  the write-safety gates working exactly as designed (blocking an
  unguarded `Set*` call / a zero-mutation confirmation loop). Not defects.
- **`ReportedError` — Mbugwe 08-21 08:44:57** — the user's own
  `report.Error("[VERDICT] THE EDGE IS DEAD...")` call, the deliberate
  conclusion of a T067 audit script. A real finding about the user's own
  downstream project, not a FlexToolsMCP/flexicon bug.
- **Two low-confidence one-offs, not proposed for lack of a clear fix
  target:** `type object 'IMoAffixProcessFactory' has no attribute
  'GetMethods'` (08-19 04:24:43, Ejagham Mini — user tried a static
  `.GetMethods()` on the factory *type* rather than reflecting via
  `.GetType().GetMethods()`) and `cannot import name 'IMultiUnicode' from
  'SIL.LCModel.Core.KernelInterfaces'` (08-19 08:50:46, Ejagham Mini — wrong
  import path guess). Each occurred once; no existing issue matches either
  exactly. Flagging for awareness only.

## Deduped recurrences (still open — not regressions)

| Signature | Issue | New occurrence | New last_seen |
|---|---|---|---|
| `ImportError: cannot import name 'ReversalIndexOperations' from 'flexicon'` (Operations classes not exported from top level) | MCP#100 / flexicon#257 (ledger fingerprints `0d7917c944e2` / `da50b2947f5d`) | 08-18 21:41:14, `session_213820_auto-Ejagham_Mini.log` op-... "cannot import name 'ReversalIndexOperations' from 'flexicon'" | **This predates the ledger's recorded `first_seen` of 2026-09-06T20:17:09Z.** Recommend correcting `first_seen` to **2026-08-18T21:41:14Z** when this window is merged in; occurrences+1. |
| `'ILangProject' object has no attribute 'WordformInventoryOA'` (stale worked example, removed in liblcm 11) | MCP#98 (open, not yet in ledger's `filed` map) | 08-13 00:02:12 (spans midnight from `session_235236_auto-Claude-Swahili.log`, `2026-08-12` file) — `'ILangProject' object has no attribute 'WordformInventoryOA'` | **This also predates #98's filing (2026-09-06).** Recommend adding a `filed` entry for #98 with `first_seen: 2026-08-13T00:02:12Z`, occurrences=1 (this window) + whatever the peer 09-06 scan already counted. |
| `casting_issues_detected` preflight rejections (generic aggregate bucket — **note:** ledger's `48c9b7e2a115` already carries a 2026-07-20 correction that issue #48 is closed and not actually a tracker for this; treat as an unowned aggregate, not evidence for any single open issue) | — (aggregate, unowned) | +31 in-window occurrences (31 distinct ops, casting_issues_detected error_code) plus 7 more carrying a `casting` sub-gate alongside `unprotected_writes`/`partial_module_structure` | last_seen 2026-08-28T16:44:39Z |
| `partial_module_structure` preflight rejections (deferred low-volume family, ledger `e9be15c60f2e`) | — (deferred) | +3 in-window (08-18 21:39:42 Ejagham Mini; 08-26 14:48:33 GT038_NKP2_Throwaway; one more same-shape) | cumulative now x5 across all scans; still comparatively low volume, but climbing — flag for the next scan to reassess whether it should graduate to a filed issue |

## REGRESSIONS (recurred after the tracking issue's close date)

All six below are closed issues whose exact signature reappeared, verbatim or
near-verbatim, inside this window — after the closing date. Ledger corrections
needed: several of the "already-tracked" families listed in this task's brief
turn out to be **misattributed** (the referenced issue doesn't actually cover
the bucket, or is closed when the ledger says open) — flagged inline.

1. **MCP#84** — "Official flexicon module template uses nonexistent
   `project.LexSense` accessor; did_you_mean hint is circular." **Closed
   2026-08-12T21:05:10Z.** Recurred **2026-08-12T22:03:12Z — 58 minutes
   later** — `session_215659_auto-Claude-Swahili.log` op-220305383-003:
   ```
   Error: Execution error: 'FLExProject' object has no attribute 'LexSense'
   AttributeError: 'FLExProject' object has no attribute 'LexSense'
   ```
   Confirmed via `gh issue view 84`: the fix was documentation-only (the
   issue body doesn't show a code diff to the template, just "correct forms"
   guidance) — the template itself may not have actually been patched, or
   the patched template hadn't propagated to whatever `flextools_get_module_
   template` served this session. Next-op evidence in the same session shows
   the user recovering by switching to `LexSenseOperations(project)`
   directly.

2. **MCP#39** — "Preflight emits polymorphic-property hint but lets code
   execute anyway." **Closed 2026-07-21T07:38:02Z.** Recurred **10 times**
   in this window (matches the jsonl `PolymorphicAttributeError` tally of
   10 exactly) — same template hint text ("Polymorphic hint: object=X
   property=Y -> resubmit; preflight should now emit casting_issues[*]
   .rewrite...") every time:
   - `'IStPara' object has no attribute 'Contents'` — 08-11 09:18:23,
     `session_091817_auto-Ejagham_Full_GT-Test.log`
   - `'str' object has no attribute 'get_String'` (inside
     `flexicon/code/Lists/AgentOperations.py:309 GetVersion`) — 08-13
     00:02:20, `session_235236_auto-Claude-Swahili.log` op-000211713-013
   - `'int' object has no attribute 'set_String'` — 08-15 20:51:44,
     `session_204945_auto-Target.log`
   - `'RnResearchNbkRepository' object has no attribute 'RecordsOC'` —
     08-15 20:53:19, same session
   - `'LcmCache' object has no attribute 'GetObject'` — 08-15 20:53:51,
     same session (also see new proposal B below — this one is really a
     flexicon library bug, not a user casting mistake, wrapped in a
     misleading "resubmit" hint)
   - `'FLExProject' object has no attribute 'LangProject'` — 08-21
     08:43:40, `session_084257_auto-Mbugwe_LizzieHC_practice.log`
     (cross-refs MCP#69 regression below)
   - `'LcmCache' object has no attribute 'Cache'` — **x4**: 08-21 08:44:34
     (Mbugwe), 08-26 16:02:57 (`session_160242_auto-Ejagham_W_Mini.log`),
     08-28 16:44:57 (`session_164425_auto-94031e534a....log`) — see new
     proposal C below, which argues this specific shape deserves its own
     targeted hint given the frequency
   - `'ILcmServiceLocator' object has no attribute 'GetInstance'` — 08-26
     16:03:13, `session_160242_auto-Ejagham_W_Mini.log` (also independently
     a regression of flexicon#34, below)

3. **MCP#75** — "Preflight/resolve_property does not hint on pythonnet
   'No method matches given arguments' overload failures." **Closed
   2026-07-20T23:31:51Z.** Recurred at a **third call site** (previously
   `GetFields`/`Create`) — 08-11 06:15:37,
   `session_091536_auto-Ejagham_Full_GT-Test.log` op-091543-001:
   ```
   Error type:      OverloadResolutionError
   Error:           Execution error: No method matches given arguments for
                    ISilDataAccess.BeginUndoTask: (<class 'str'>)
   ```

4. **MCP#80** — Part 1 ("Graceful discovery redirect... turn-1 zero-discovery
   `api_discovery_required` should become a `status: ok` advisory-redirect,
   not an error"). **Closed 2026-07-21T06:30:06Z.** Recurred as a **hard
   preflight_reject**, not an advisory, on op #1 of a fresh session, twice:
   - 08-11 06:14:24, `auto-Ejagham Full GT-Test`, op-091424882-001
     (jsonl-only — no matching per-session log file found; likely lost to
     the operations.log rotation/gap noted above)
   - 08-15 20:49:55 local (17:49:55Z), `session_204945_auto-Target.log`:
     ```
     [REJECT] Pre-flight validation blocked execution
     Reason code:     api_discovery_required
       No APIs discovered yet -- call start() / get_object_api() /
       search_by_capability() first.
     ```
   **Ledger correction:** the brief's already-tracked list maps
   `api_discovery_required` recurrences to **MCP#53**
   ("53d4e6f0b229" — "Cold-start tolerance: auto-initialize a read-only
   session on first tool call"). Checked `gh issue view 53`: its body is
   about implicit session auto-init for read-only *tool calls*
   (`get_object_api`, `search_by_capability`, etc.), not about reclassifying
   `run_module`'s turn-1 `api_discovery_required` rejection — it does not
   contain the string `api_discovery_required` anywhere. #53 is also
   **closed** (2026-07-21T07:38:03Z), consistent with the ledger, but it is
   the wrong issue for this bucket. #80 is the correct match (its body
   explicitly names `api_discovery_required` at `execution.py:2240-2292`
   as the exact code path to reclassify). Recommend the ledger retarget
   `53d4e6f0b229` -> #80 and treat this as a regression, not a fresh dedup
   against #53.

5. **MCP#69** — "invalid_api_chain 'did you mean' suggests unrelated
   accessors at low match confidence (`project.LangProject` -> `PossibilityLists`)."
   **Closed 2026-07-20T09:09:30Z.** Recurred **2026-08-21 08:43:40** — same
   root confusion (guessing at how to reach the raw `ILangProject` object),
   `session_084257_auto-Mbugwe_LizzieHC_practice.log`:
   ```
   AttributeError: 'FLExProject' object has no attribute 'LangProject'
   ```
   Same session's *next* attempt (op ending 08:44:34) shows a second,
   different wrong guess for the same target —
   `project.project.Cache.LangProject` -> `'LcmCache' object has no
   attribute 'Cache'` — i.e. the user never got steered toward the actual
   documented accessor `project.lp` in either attempt. (This second guess
   is counted once, under #39 above and under new-proposal C, to avoid
   triple-counting the same log line across three buckets.)

6. **flexicon#34** — "Cookbook: `ILcmServiceLocator` generic methods
   unreachable via pythonnet `GetInstance[T]()` — must use reflection or
   `GetService(Type)`." **Closed 2026-05-27T01:13:58Z** (a documentation/
   cookbook fix, not a code fix). Recurred verbatim **2026-08-26 16:03:13**,
   `session_160242_auto-Ejagham_W_Mini.log`:
   ```
   Error type:      PolymorphicAttributeError
   Error:           Execution error: 'ILcmServiceLocator' object has no
                    attribute 'GetInstance'
   ```
   Recurrence 3 months after a docs-only close suggests the cookbook
   recipe isn't surfacing through `find_examples`/`search_by_capability`
   when someone actually needs it — worth a comment on #34 (Phase B)
   noting the recipe needs better discoverability, not just existence.

## PROPOSED NEW ISSUES

### 1. flexicon — `FLExProject.pyi` stub declares `WriteEnabled: bool`; the real runtime attribute is lowercase `writeEnabled`

- **Repo:** MattGyverLee/flexicon
- **Severity:** P2
- **Type:** bug
- **Evidence:** `session_204945_auto-Target.log:87-96`, op-205103531-003,
  2026-08-15 20:51:09 (17:51:09Z):
  ```
  Error:           Execution error: 'FLExProject' object has no attribute 'WriteEnabled'
  AttributeError: 'FLExProject' object has no attribute 'WriteEnabled'. Did you mean: 'writeEnabled'?
  ```
  Confirmed by reading the checked-out flexicon source
  (`D:\Github\_Projects\_LEX\flexicon\flexicon\code\FLExProject.pyi:72`):
  `WriteEnabled: bool` is declared in the stub. `flexicon/code/FLExProject.py`
  has no such attribute at all (grep came back empty); the real,
  lowercase-`w` attribute is documented separately in the flexicon repo's
  own `CLAUDE.md:140-141` ("the attribute is `writeEnabled`, not
  `WriteEnabled`"). This is a genuine stub/implementation drift: any
  type-checker-following caller, IDE autocomplete, or AI agent that trusts
  the `.pyi` will write `project.WriteEnabled`, which dies at runtime.
- **Suggested fingerprint:** `sha256("AttributeError: FLExProject has no attribute WriteEnabled (stub declares capitalized, impl is lowercase writeEnabled)")[:12]`
- **Proposed labels:** `bug`, `log-triage`
- **Body draft:** "`flexicon/code/FLExProject.pyi:72` declares `WriteEnabled:
  bool`, but `FLExProject.py` never defines that attribute — the real one
  is lowercase `writeEnabled` (confirmed by this repo's own CLAUDE.md and
  by Python's own did-you-mean suggestion on the AttributeError). Any code
  written against the stub (type-checkers, IDE completion, or AI codegen
  reading the `.pyi`) will silently pick the wrong case and crash at
  runtime the first time it checks write mode. Fix: correct the stub's
  casing to `writeEnabled: bool`, or add a case-matching `WriteEnabled`
  property alias if callers already depend on the capitalized form.
  Evidence: `~/.flextoolsmcp/logs/2026-08-15/session_204945_auto-Target.log:87-96`."

### 2. flexicon — `DataNotebookOperations.__GetRecordObject`/`SetTitle`: raw `self.project.project.GetObject(hvo)` — LcmCache has no `GetObject`

- **Repo:** MattGyverLee/flexicon
- **Severity:** P1 (breaks `SetTitle` and any other Notebook method sharing `__GetRecordObject`, on any valid record/HVO input)
- **Type:** bug
- **Evidence:** `session_204945_auto-Target.log:443-465`, op-000211713-013 was a
  different op — this is op ending 2026-08-15 20:53:51 (17:53:51Z):
  ```
  Error type:      PolymorphicAttributeError
  Error:           Execution error: Invalid notebook record object or HVO:
                   RnGenericRec : 11987 - 'LcmCache' object has no attribute 'GetObject'
  Traceback:
    File "...\flexicon\code\Notebook\DataNotebookOperations.py", line 182, in __GetRecordObject
      obj = self.project.project.GetObject(hvo)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    AttributeError: 'LcmCache' object has no attribute 'GetObject'
    ...
    File "...\flexicon\code\Notebook\DataNotebookOperations.py", line 579, in SetTitle
      record = self.__GetRecordObject(record_or_hvo)
    File "...\flexicon\code\Notebook\DataNotebookOperations.py", line 191, in __GetRecordObject
      raise FP_ParameterError(f"Invalid notebook record object or HVO: {record_or_hvo} - {e}")
  flexicon.code.exceptions.FP_ParameterError: Invalid notebook record object
  or HVO: RnGenericRec : 11987 - 'LcmCache' object has no attribute 'GetObject'
  ```
  `self.project.project` is the raw `LcmCache` (confirmed the same way
  flexicon#193 confirmed it: `type(project.project).__name__ ==
  'LcmCache'`). `LcmCache` has no `GetObject` method; the object lookup
  needs to go through `ServiceLocator`'s object repository (e.g.
  `self.project.project.ServiceLocator.GetObject(hvo)`, matching the
  pattern already used elsewhere in the codebase per
  `flexicon.code.exceptions`/other Operations classes). Note this is a
  **library-internal** bug (unlike the "double `.Cache`" trap in proposal
  3, which is a user-facing discoverability gap) — `SetTitle` cannot
  succeed on any valid HVO because `__GetRecordObject` always throws before
  reaching the caller's actual logic, then the preflight layer misreports
  it as a user-fixable "polymorphic hint... resubmit" (see cross-reference
  to MCP proposal below).
- **Suggested fingerprint:** `sha256("AttributeError: LcmCache has no attribute GetObject in DataNotebookOperations.__GetRecordObject")[:12]`
- **Proposed labels:** `bug`, `log-triage`
- **Body draft:** "`DataNotebookOperations.py:182` (`__GetRecordObject`)
  calls `self.project.project.GetObject(hvo)`. `self.project.project` is
  the raw `LcmCache` (same object identity flexicon#193 already
  established), which has no `GetObject` method — object lookup by HVO
  needs to go through the service locator's object repository. This makes
  `__GetRecordObject` — and therefore every public method that calls it,
  starting with `SetTitle` — fail on every valid record/HVO argument, not
  just malformed ones. `__GetRecordObject`'s own except-and-reraise (line
  191) currently disguises this as an `FP_ParameterError` about an
  'invalid' HVO, when the HVO (`RnGenericRec : 11987`) was perfectly valid.
  Fix: use the correct object-repository accessor (see sibling Operations
  classes for the pattern) inside `__GetRecordObject`, and audit whether
  other `Notebook/DataNotebookOperations.py` methods share the same
  raw-`GetObject` mistake. Evidence:
  `~/.flextoolsmcp/logs/2026-08-15/session_204945_auto-Target.log:443-465`.
  See also the related MCP-side observation that the preflight polymorphic
  hint text ('resubmit; preflight should now emit casting_issues[*]
  .rewrite') is actively misleading here, since no amount of user-side
  casting can fix a bug inside the library's own object-lookup helper."

### 3. FlexToolsMCP — recurring "double `.Cache`" trap (`project.project.Cache.X` -> `'LcmCache' object has no attribute 'Cache'`) deserves its own targeted preflight hint

- **Repo:** MattGyverLee/FlexToolsMCP
- **Severity:** P2
- **Type:** enhancement
- **Evidence:** 4 occurrences of the *exact same* error message in this
  20-day window alone:
  - 08-21 08:44:34, `session_084257_auto-Mbugwe_LizzieHC_practice.log:318-321`,
    code `langproj = ILangProject(project.project.Cache.LangProject)`
  - 08-26 16:02:57, `session_160242_auto-Ejagham_W_Mini.log:48-51`
  - 08-28 16:44:57, `session_164425_auto-94031e534a....log:93-96`
  - (a 4th matching instance also folds into the #39 regression tally above)
  All four produce the identical shape:
  ```
  Error type:      PolymorphicAttributeError
  Error:           Execution error: 'LcmCache' object has no attribute 'Cache'
  Polymorphic hint: object=LcmCache property=Cache -> resubmit; preflight
    should now emit casting_issues[*].rewrite and casting_issues[*].imports_needed
  ```
  This is the *exact same textual mistake* flexicon's own maintainers made
  and fixed internally in flexicon#193 ("`MSAOperations.__CreateAndAttach`:
  double `.Cache` breaks all MSA creation" — root cause: "`self.project` is
  the `FLExProject` wrapper. Its `.project` attribute IS the `LcmCache`
  directly... so `self.project.project.Cache` is invalid"). If it's common
  enough to trip up the library's own authors, it is worth a specific,
  named preflight/`resolve_property` pattern-match — rather than falling
  through to the generic "resubmit" hint that currently gives the user zero
  actionable guidance beyond "something about Cache is wrong."
- **Suggested fingerprint:** `sha256("PolymorphicAttributeError: LcmCache has no attribute Cache (redundant .Cache. hop after project.project)")[:12]`
- **Proposed labels:** `enhancement`, `dx`, `log-triage`
- **Body draft:** "Four occurrences in a 20-day window (2026-08-21, 08-26,
  08-28 x2) of the identical mistake: user/AI-generated code writes
  `project.project.Cache.<X>` (or similar `...Cache.Cache...` chains)
  because `project.project` already *is* the `LcmCache` — the trailing
  `.Cache` is always redundant. This is precisely the bug flexicon#193
  found and fixed in the library's own `MSAOperations.__CreateAndAttach`;
  it's evidently a natural mistake, not a one-off typo. Currently preflight
  falls through to the generic polymorphic-hint template ('Polymorphic
  hint: object=LcmCache property=Cache -> resubmit...') which gives no
  concrete fix. Proposed: special-case detect `<expr>.project.Cache` (or
  literally `LcmCache` + attribute `Cache`) in the casting-issue scanner and
  emit a `casting_issues[*].rewrite` that strips the redundant hop, the same
  way other high-confidence patterns already get an inline rewrite. Cross-
  references the MCP#69 regression above (same investigative session,
  same underlying 'how do I reach the raw LangProject/Cache' confusion —
  the actually-documented accessor is `project.lp`)."

---

## Notes for whoever runs Phase B / merges this into `docs/logscan-state.json`

- This scan is **August-window only**; do not merge over the peer's
  2026-09-06/09-07 findings already in the ledger.
- Ledger corrections recommended alongside any new filings:
  - `53d4e6f0b229` is misattributed to MCP#53; retarget to **MCP#80**
    (see regression #4) and mark state as a regression, not a plain dedup.
  - `0d7917c944e2`/`da50b2947f5d` (MCP#100/flexicon#257) `first_seen` should
    move from 2026-09-06T20:17:09Z back to **2026-08-18T21:41:14Z**.
  - MCP#98 (WordformInventoryOA) has no `filed` entry yet in the working
    ledger; add one with `first_seen: 2026-08-13T00:02:12Z` (pending
    whatever the 09-06 peer scan separately recorded).
- Six regressions above (MCP#39, #69, #75, #80, #84; flexicon#34) are strong
  candidates for regression-labeled comments in Phase B, mirroring how the
  existing ledger already handled the #40/#76 and #40/#97 regressions.
- `project_locked` evidence (Mayanau-Bena-Yungur Toy x2 08-13; Ngoreme FLEx
  x2 08-19; Ngoreme Target x2 08-19) is **not proposed** — it's directly in
  scope of the already-open MCP#93 ("Shared-mode access: allow MCP
  operations while FLEx has the project open"), which is this very
  branch's (`feat/shared-mode-access`) feature work. Worth citing as
  additional real-world motivation on #93 in Phase B, not a new issue.
- One escalation worth a comment on the already-open, `needs-routing`
  MCP#70 (AddCustomField 4-arg overload hang): 08-28 14:14:54,
  `session_141343_auto-Ngoreme_FLEx.log:411-425` — the `Ngoreme FLEx`
  project failed to *open at all*: `Failed to open project 'Ngoreme FLEx':
  Attempting to create duplicate custom field with the name NGQ Bantu
  Wordlist Ref #1. PLEASE REPORT THIS TO FlexErrors.` This looks like a
  more severe downstream consequence of whatever left a duplicate custom
  field behind (plausibly connected to #70's AddCustomField hang) — the
  project became unopenable, not just slow. The very next operation in the
  same session succeeded against a *different*, similarly-named project
  (`GT038 T124 Ngoreme`), so this may be project-specific/transient rather
  than universal; flagging for maintainer triage rather than proposing a
  standalone new issue.
