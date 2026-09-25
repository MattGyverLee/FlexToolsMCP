# SPEC -- the catch: detect and migrate non-portable modules

**Feature:** `broken-script-migration`
**Repo:** FlexToolsMCP
**Status:** spec, not implemented
**Filed issues:** (none yet)
**Source:** triage of `user-logs/Kendall/session_{112101,145439,154828}*.log`, 2026-09-09
**Depends on:** `flexicon-project-bridge` (the target shape),
`portability-preflight` (the detector)

---

## 1. Context

Modules written against the old guidance are already on disk, in users FlexTools
module folders, and they run green under this MCP forever. The static gate
(`portability-preflight`) stops *new* ones and refuses old ones; it does not
repair them. This spec is the repair path.

Scale is not hypothetical: four distinct broken modules appear in three
sessions from one user in one day, and the guidance that produced them
(`CLAUDE.md`, `docs/FLEXTOOLS-STYLE-GUIDE.md:119-122`,
`execution.py:318`) has been shipping for the life of the project.

### What migration must and must not touch

The Kendall modules carry **three defects at different layers**, and conflating
them would be a serious mistake:

1. **Non-portable project use** -- mechanical, safely rewritable. This is the
   only thing the migrator changes.
2. **A wrong write contract** -- `FTM_ModifiesDB : False` on a module
   containing `AddComplexFormComponent` + `Delete` (session 145439 op#3).
   Flipping it to `True` *enables writes under FlexTools that are currently
   clamped off* (`FTModuleClass.py:106-112`). **Never auto-flip.** Report it and
   let a human decide.
3. **Genuine logic bugs** -- out of scope to fix, in scope to report:
   - `variants.Delete(ref)` sits inside the inner `for c in components:` loop,
     so an entry with 2+ components deletes the same ref repeatedly, the second
     call operating on a dead object.
   - `ILexEntry(c)` is wrong, not merely redundant: variant
     `ComponentLexemesRS` elements can be a **LexSense**, and flexicon
     `AddComplexFormComponent` already accepts uncast objects by comparing
     `ClassName` against `("LexEntry", "LexSense")`
     (`flexicon/code/Lexicon/LexEntryOperations.py:2790`, flexicon issue #270).
     The cast throws on exactly the input the uncast object handles.
   - The conversion drops the variant type: variant refs carry a
     `VariantEntryTypes`, and `AddComplexFormComponent` creates a ref with
     none.

A migrator that silently "fixed" 2 or 3 would be changing what the module does
to the user data. It rewrites 1 and reports 2 and 3.

---

## 2. Settled -- do not revisit

- **Rewrite only the project-object shape.** Semantics unchanged, byte-for-byte
  identical behaviour under the MCP.
- **Never edit in place without an explicit opt-in.** Default output is a new
  file plus a diff.
- **Never auto-flip `FTM_ModifiesDB`.** It gates writes; changing it is the
  user decision.
- **Preserve comments and formatting.** These are files users read and maintain
  (`CLAUDE.md`: "Comment non-obvious code - users will read and maintain
  this"). That rules out `ast.unparse`, which discards comments and reflows
  everything. Surgical text edits only -- see 3b.
- **Idempotent.** Running the migrator on migrated output is a no-op.

---

## 3. Design

### 3a. Two entry points

1. **Inline catch.** When `run_module` refuses with
   `not_portable_to_flextools`, attach a `migration` block to the rejection:
   the rewritten code plus a unified diff. The model can then re-submit the
   fixed module without a round-trip through the user. This is where the catch
   pays for itself -- the refusal becomes self-healing.
2. **Bulk sweep.** New tool `flextools_migrate_modules(path, mode)` over a file
   or directory of `.py` modules. `mode` is `report` (default), `write_copy`,
   or `in_place`. `in_place` requires an existing git checkout or takes a
   timestamped backup first.

### 3b. The rewrite, mechanically

AST for *analysis*, byte offsets for *editing*. Every node we touch is an
`ast.Attribute` or `ast.Call` with `lineno`/`col_offset`/`end_lineno`/
`end_col_offset`, so each edit is a span replacement in the original source.
Apply edits back-to-front so earlier offsets stay valid. Comments, blank lines,
and the `docs` dict come through untouched.

Rules, in order:

1. **Ensure the import.** `from flexicon import FLExProject` -- extend an
   existing `from flexicon import (...)` rather than adding a second one.
2. **Insert the bridge** as the first statement of `Main` body, after the
   docstring if present:
   `fx = FLExProject.FromOpenProject(project)`.
   Pick a name that does not collide with an existing binding in that scope
   (`fx`, then `fxproj`, then `_fx`).
3. **Facade access:** `project.<Accessor>` -> `fx.<Accessor>` for every
   accessor in the flexicon-only set (from `portability-preflight` CP1).
4. **Operations construction:** `LexEntryOperations(project)` ->
   `LexEntryOperations(fx)`. Prefer the minimal edit over rewriting the call to
   `fx.LexEntry`, so an existing alias (`lex = ...`) and all its call sites
   keep working with a one-token change.
5. **Leave portable calls alone.** `project.LexiconAllEntries()` (flexlibs
   `:591`), `project.LexiconGetHeadword(...)`, `project.WSHandle(...)` and the
   rest of the flexlibs public surface stay on `project`. The Kendall modules
   mix both on adjacent lines, so this is the common case, not an edge case.
6. **Do not touch** `from SIL.LCModel import ...`, raw LCM access, or anything
   in section 1 item 3.

### 3c. The advisory report

Alongside the diff, per module:

- `portability`: what was rewritten (line-accurate).
- `write_contract`: the `FTM_ModifiesDB` mismatch, if any, with the sentence
  that under FlexTools the current value clamps `modifyAllowed` to False, and
  that setting it to `True` enables the writes. Never applied automatically.
- `advisories`: the section-1 item-3 class of finding. Seed the detector with
  the three shapes actually observed:
  - a mutating call on a collection element inside a loop over that
    collection, or a `Delete(x)` whose argument is not the innermost loop
    variable (the double-delete shape);
  - `ILexEntry(...)` / `cast_to_concrete(...)` wrapping an argument to a
    flexicon method that the index marks as accepting a base `ICmObject`;
  - a variant-to-complex-form conversion with no type carried across.

Advisories are reported, never applied. Where a shape looks general, hand it to
the `sweep-pattern` skill rather than hardcoding a one-off.

### 3d. Verifying a migration actually worked

A migration is only trustworthy if the migrated module runs under real
FlexTools. Wire the output straight into `vanilla-flextools-parity`: for each
corpus entry, migrate then run both paths and require verdict `match`. A
migration that produces code the static gate accepts but vanilla FlexTools
rejects is a failed migration, and only the parity harness can tell.

### 3e. Where the modules are

- The path the user passes.
- The skeleton closet (`CLAUDE.md`, issue #24) once it lands -- saved snippets
  are exactly the population at risk.
- Not the users whole disk. No filesystem crawl beyond the given path.

---

## 4. Checkpoints

### CP1 -- the rewriter

- **T1.1** `src/flextoolsmcp/migration/rewrite.py`: span-edit engine per 3b,
  no `ast.unparse`.
- **T1.2** Unit matrix: each of the six rules; mixed portable/non-portable in
  one module; an aliased Operations construction; a `Main` with and without a
  docstring; a name collision on `fx`; a module already migrated (no-op);
  a module with `docs` built via `dict()`; a syntax-error module (refuse
  cleanly).
- **T1.3** Golden diffs for all seven Kendall fingerprints, byte-exact, so a
  regression in comment or formatting preservation fails loudly.

### CP2 -- entry points

- **T2.1** `migration` block on the `not_portable_to_flextools` rejection
  per 3a-1.
- **T2.2** `flextools_migrate_modules` tool per 3a-2, with the three modes and
  the `in_place` backup precondition. Contract entry in
  `docs/TOOL-CONTRACT.md`.
- **T2.3** Advisory report per 3c.

### CP3 -- proof

- **T3.1** Migrate the corpus, run through `vanilla-flextools-parity`, require
  `match` per 3d.
- **T3.2** Assert the migrated output passes `portability-preflight` and, where
  the original had a `FTM_ModifiesDB` mismatch, still gets refused by
  `modifiesdb-parity` -- because migration deliberately did not flip it. **This
  pair of assertions is what proves the layers stayed separate.**

---

## 5. Verification

1. **Unit** -- CP1, headless.
2. **Golden** -- CP1/T1.3 diffs.
3. **Parity** -- CP3/T3.1 *(requires FieldWorks + human authorization)*. This
   is the acceptance test.
4. **Layer separation** -- CP3/T3.2.
5. **Idempotency** -- migrate twice, second run reports zero changes.
6. **Safety** -- `in_place` with no git checkout and no backup possible must
   refuse, not proceed.
7. **Regression** -- full `pytest`, `validate_integrity.py all`,
   `verify_python.py`.

---

## 6. Out of scope

- Fixing the logic bugs in section 1 item 3. Reported, never rewritten.
- Flipping `FTM_ModifiesDB` (settled).
- Migrating away from raw LibLCM or `SIL.LCModel` imports -- portable in both
  hosts.
- Rewriting modules that target stable flexlibs deliberately. Detect the
  flexlibs-only flavour and skip with a note; they are already portable.
