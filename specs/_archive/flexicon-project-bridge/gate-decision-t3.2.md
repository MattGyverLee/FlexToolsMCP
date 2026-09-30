# GATE DECISION -- T3.2 write persistence

**Task:** T016 · **Date:** 2026-09-09 · **Decided by:** live evidence, two projects

## Decision

**PASS. CP1 is clear to ship.**

`contracts/from-open-project.md` section 2.2 needs **no** flush step. The spec's
claim that `_undoable = False` alone is sufficient **holds**. This feature does
**not** return to plan, and US4 (docs) and US5 (template pre-flight) are
unblocked.

## The question T016 gates on

From `spec.md` T3.2 — the one thing the plan explicitly could not settle by
reading:

> With FLEx holding the project, does a Phase 1 `Transaction` inside the flexlibs
> non-undoable task actually commit on the host save, or does it need an explicit
> `MainCacheAccessor` flush? […] **If it does not persist, this spec is wrong that
> `_undoable = False` alone is sufficient, and CP3 must block CP1 from shipping.**

## What was run

A write through a `FromOpenProject` attached view, inside `Transaction()`, with
**no** save requested by the module — then the host closed, and a **separate
process** reopened and read the value back.

Driven through FlexTools' own `ModuleManager.RunModules()`, the code path the
GUI's Run button uses: `OpenProject(name, writeEnabled=…)` with the stable
flexlibs class → `Main()` → `CloseProject()` ("Save any changes and release the
LCM Cache"). That close is the host save under test.

| # | Project | Result | Disk delta |
|---|---|---|---|
| T014 | `Sena3 Bridge Scratch` (disposable copy) | **PASS** | +13 bytes, sentinel in `.fwdata`, old value gone |
| T015 | `Sena 3` | **PASS** | +13 bytes, identical arithmetic |

`+13` is exactly `len("T32-GATE-20260909-A") - len("gaguez")` = 19 − 6.

Corroborated three independent ways: FlexTools' own read-back in a fresh
process; `grep` over the raw `.fwdata` with no library in the loop; and a read
through the FlexToolsMCP stack (a different host opening with flexicon rather
than flexlibs).

Evidence artifacts, in the `flexicon` repo:

- `evidence/t3_2_persistence_gate_scratch_2026-09-09.txt`
- `evidence/t3_2_persistence_gate_sena3_2026-09-09.txt`
- `evidence/t3_1_from_open_project_mcp_parity_2026-09-09.txt` (T013, read parity)

## Provenance — was the branch actually loaded?

Checked explicitly, because a pre-bridge `pyflexicon` would invalidate the whole
run.

- FlexTools launches via `py` → `C:\Python313\python.exe`.
- That interpreter's `flexicon` resolves to
  `D:\Github\_Projects\_LEX\flexicon\flexicon\__init__.py` — an **editable**
  install on branch `flexicon-project-bridge`, HEAD `d186cb2`, with
  `_attached_donor` present in the source.
- **Decisive:** every gate run printed `view is donor: False` and
  `view attached: True`. Only branch code can produce those. A pre-bridge
  flexicon dies on the first line of `Main()` with
  `AttributeError: type object 'FLExProject' has no attribute 'FromOpenProject'`.

## Two findings that ride along

**1. The write path is cleanly reversible.** Sena 3 was restored after T015 and
the resulting `.fwdata` is **byte-for-byte identical** to the pre-run backup —
not merely "the gloss is back", but all 55,954,858 bytes. The attached-view
write introduces no incidental churn: no stray timestamps, no reordering, no
residue beyond the field actually changed.

**2. Field evidence for T024's capability-probe decision (CP4).** On the very
machine FlexTools runs on, the two version sources disagree:

```
flexicon.version                         -> "4.6.0"   (the live source)
importlib.metadata.version("pyflexicon") -> "4.1.1"   (stale editable metadata)
```

Five minor releases apart, both "true". A hardcoded version floor compared
against either string would give the wrong answer here **today**. This is exactly
why `tasks.md` T024 specifies a capability probe
(`hasattr(FLExProject, "FromOpenProject")`) and forbids a version comparison,
and why T023's T4.2c ratchet exists. The version string is fit only for the
human-readable half of the message — which is what the contract already says.

## State left behind

| Thing | State |
|---|---|
| `Sena 3` | pristine, verified byte-identical to backup |
| `Sena3 Bridge Scratch` | still carries the sentinel; disposable, delete when done |
| `D:\Apps\FlexTools\FlexTools\Modules\BridgeGate\` | three gate modules installed (A write / B verify / C restore) |
| `flextools` dev checkout `Modules/BridgeGate/` | untracked copies of A and B |
