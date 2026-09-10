# VALIDATION -- T022

**Date:** 2026-09-09 · **Verdict:** all five Success Criteria met; every
Constitution Check row now **PASS**, including the one that was AT RISK.

---

## Success Criteria (spec.md section 5)

### 1. Unit -- CP2, no FieldWorks required

**MET.**

```
python -m pytest tests/test_from_open_project.py -q      (flexicon)
39 passed in 1.23s
```

No `requires_live_project` marker on the file — the bridge opens nothing, and
that is the only marker `pyproject.toml:90-92` registers. Covers T2.1a/b/c
(attribute borrowing, `_undoable is False` under a write-enabled donor,
idempotence), T2.2a/b/c (the three lifecycle refusals and their forbidden
substrings), T2.3 (`FP_ParameterError` naming the donor's module), and SPEC
T1.4 (reachable from the package root with no `__init__.py` edit).

### 2. Live -- CP3, scratch project then Sena 3

**MET.** Both passes green; the gate does not block.

| | Project | Result |
|---|---|---|
| T013 (T3.1) | Sena 3, read parity | 3d shape == control == attach branch, digest `8a88d78d…` over 1462 entries |
| T014 (T3.2) | `Sena3 Bridge Scratch` | write survived host save + fresh-process reopen; `.fwdata` +13 bytes |
| T015 (T3.2) | Sena 3 | reproduced exactly; Sena 3 then restored **byte-for-byte** |

Driven through FlexTools' own `ModuleManager.RunModules()` — the GUI's code
path — with a real process boundary between write and read-back. Corroborated
by `grep` over the raw `.fwdata` and by a read through the MCP stack.
Decision recorded in [`gate-decision-t3.2.md`](./gate-decision-t3.2.md).

### 3. Regression -- full flexicon pytest, no `OpenProject`/`CloseProject` behaviour change

**MET.**

```
python -m pytest -q      (flexicon, branch flexicon-project-bridge)
2463 passed, 9 failed, 23 skipped, 2 xfailed
```

All 9 failures reproduce **identically** on a clean `main` worktree at
`d186cb27` — pre-existing, not regressions:

- 7 × `test_duplicate_operations.py::TestLexEntryDuplicate::*` — a casting bug
  in `LexEntryOperations.Duplicate`, `'IMoForm' object has no attribute
  'PhoneEnvRC'` (`LexEntryOperations.py:443`)
- `test_natural_classes.py::…::test_apply_raises_on_type_mismatch_segments_target`
- `test_text_operations.py::…::test_create_and_delete_text`

An earlier run of the same suite showed only 1 failure. The difference is
**data**, not code: these are live tests that `skipTest("No suitable entry
with …")` when the project lacks matching data, so the skip count moved 30 → 23
as seven of them started finding candidates. Both runs are consistent with
`main`.

Targeted SPEC 5.3 check:

```
python -m pytest -q -k "open_project or OpenProject or close_project or
                        CloseProject or transaction or undoable or from_open_project"
1 failed, 176 passed, 2320 deselected
```

The single failure, `test_FLExProject.py::TestFLExProject::test_OpenProject`,
is a **test-isolation artifact, not a regression**: it passes inside the full
suite (it is absent from the 9 above) and fails in isolation on `main` too,
with the identical `TypeError: Exception has been thrown by the target of an
invocation` at `FLExLCM.py:61` — it needs the `FLExInitialize` an earlier test
performs. Verified on a `main` worktree.

**No `OpenProject`/`CloseProject` test changed behaviour.**

### 4. Cross-repo -- FlexToolsMCP suite against the new pyflexicon

**MET.**

```
python -m pytest -q      (FlexToolsMCP)
1254 passed, 8 skipped, 17 subtests passed
```

Fully green. 1242 before US5; the 12 added are the CP4 pre-flight tests.

### 5. Template pre-flight -- CP4, no FieldWorks, no flexicon uninstall

**MET.**

```
python -m pytest -q tests/test_template_flexicon_preflight.py
12 passed, 3 subtests passed
```

Covers T4.1a (helper present and called as the first statement of `Main()`),
T4.2a (absent → `pip install pyflexicon` + the captured `ImportError`), T4.2b
(pre-bridge → `pip install -U pyflexicon` + the version found, plus both
version-source paths), T4.2c (the no-version-floor ratchet), T4.3a (ASCII in
every emittable message and in the template file), T4.4a (silent + `True` on
success), T4.4b (fail open for both an exploding probe and a hostile `report`).

**Additionally verified in the interpreter that actually matters.** FlexTools
launches via `py` → `C:\Python313\python.exe`, which is *not* the conda
interpreter this session uses. The pre-flight was exercised in both:

```
system  Python 3.13.12   ALL OK
conda   Python 3.12.7    ALL OK
```

That cross-check earned its keep: the two interpreters report **different**
`importlib.metadata` versions for `pyflexicon` (4.1.1 vs 4.6.0) while both load
the same 4.6.0 source. A hardcoded version floor would have answered
differently per environment. The `hasattr` capability probe answers correctly
in both — which is the whole argument for T4.2c's ratchet, now backed by field
evidence rather than reasoning.

**Amended 2026-09-09, after validation, at the user's request.** The user asked
whether the module tracks the flexicon version it was tested against, so it can
fail when unavailable and *warn* when older. It did the first and not the
second. Added: a `_TESTED_AGAINST` constant stamped by
`flextools_get_module_template()` at generation time, and a `report.Warning`
when the installed flexicon parses as older. It is an advisory only — it runs
after the `hasattr` gate has passed and cannot change the return value.

Contract §8.2b records the addition; §8.4's T4.2c is superseded. The original
T4.2c banned *any* version comparison in the template, which was broader than
§8.2 (which bans a version **floor** — a comparison that gates). It is replaced
by a ban on third-party version machinery plus a behavioural ratchet: with
`_TESTED_AGAINST` set to `99.99.99`, a capable flexicon at `0.0.1` still returns
`True` and emits no `Error`. That pins the property directly instead of
approximating it by grep.

The stale `REQUIRES: - Flexicon version 2.0+` line was also corrected — prose,
unenforced, and false, which is exactly the hand-maintained-version rot that
argues for stamping rather than writing the constant by hand.

Suite after the change: **1259 passed**, 8 skipped, 31 subtests (was 1254/17).
Re-verified in both interpreters, and end-to-end with `import flexicon`
genuinely blocked at `meta_path`: the module still imports, `Main()` reports and
returns, and a project object that raises on any attribute access is never
touched.

---

## Constitution Check (plan.md) — re-checked

| Principle (house rule) | Then | Now |
|---|---|---|
| No rename of `flexicon.FLExProject` | PASS | **PASS** — a classmethod was added; the class name is untouched, and the 51 mangled `_FLExProject__WSHandle` sites resolve on a view because the view *is* a `FLExProject`. |
| No duck-type adapter over a flexlibs project | PASS | **PASS** — `cls.__new__(cls)` produces a real flexicon instance; only the `LcmCache` is borrowed. Confirmed live: `isinstance(view, FLExProject)` is `True` and the full facade serves reads identically to the donor. |
| The bridge ships in `flexicon`, not the MCP | PASS | **PASS** — every runtime source change is in the flexicon repo. The MCP's only change is the CP4 template, which spec.md CP4 scopes there deliberately. |
| Never reopen a project FlexTools holds | PASS | **PASS** — `FromOpenProject` calls no `FLExLCM.OpenProject`. Proven live: `CloseProject()` on a view returned `None` and left the host cache alive; no `FP_FileLockedError` occurred in any gate run. |
| No breaking change to existing `OpenProject` callers | PASS | **PASS** — see Success Criterion 3. |
| Windows console output is ASCII-only | PASS | **PASS** — all new exception/log text is ASCII, and the template is ASCII byte-for-byte (`test_t4_3a_the_whole_template_is_ascii`). |
| Write-path changes need live-LCM evidence before approval | **AT RISK, gated** | **PASS — gate cleared.** T3.2 ran on two projects with a real close/reopen; evidence in `evidence/t3_2_persistence_gate_*.txt`, decision in `gate-decision-t3.2.md`. |

### Complexity Tracking — resolved

| Violation | Status |
|---|---|
| CP1 cannot be approved on unit tests alone; needs a live run (T3.2) | **Discharged.** The live run happened and passed. The concern was real and the answer was favourable: the write does persist on the host save, with no flush. |
| `_undoable` forced `False`, making `UndoableOperation()` unavailable on a view | **Stands as designed.** Live evidence confirms the reasoning: a real flexlibs donor has no `_undoable` attribute at all (`donor _undoable: '<unset>'` in every gate run), so there was never a mode to honour. `Transaction()` is sufficient — it is what carried the persisted write. |

---

## Judgment calls made during implementation

1. **T025 also converted `Main()`'s example body from `project.*` to `fx.*`.**
   The task said to add `fx = FLExProject.FromOpenProject(project)` and to leave
   the "CRITICAL REQUIREMENT" preamble and the Shape B `LexEntryOperations(project)`
   examples alone. It did not mention the accessor calls, and leaving them would
   have created `fx` and never used it — teaching the reader that the line is
   decorative. The preamble was left untouched as instructed; the template
   contains no Shape B examples to preserve.

2. **One CP4 test was rewritten after it failed.** The first draft asserted the
   version string degrades to `"unknown"` when the module attribute is
   unreadable. That was a bad assumption, not a bug: the contract specifies
   *two* guarded sources, and the second (`importlib.metadata`) legitimately
   succeeded. Split into two tests — one pinning the fallback to package
   metadata, one pinning `"unknown"` when both sources fail.

## Residual items (not blockers)

- The MCP's shipped API index is `flexicon_api_v4.6.0.json`, generated from
  released 4.6.0, so `flextools_get_object_api('FLExProject')` does not list
  `FromOpenProject`. Index-only staleness; a `python -m flextoolsmcp.refresh` is
  owed once the branch releases.
- US5 is written but, per tasks.md, **ships after CP1 is released** — the probe
  would otherwise warn correctly but uselessly on every machine.
- Cleanup: `Sena3 Bridge Scratch` still carries the sentinel gloss (disposable);
  the three gate modules remain installed under
  `D:\Apps\FlexTools\FlexTools\Modules\BridgeGate`.
