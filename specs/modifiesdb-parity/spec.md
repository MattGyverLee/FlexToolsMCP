# SPEC -- FTM_ModifiesDB parity: honour the declared write contract

**Feature:** `modifiesdb-parity`
**Repo:** FlexToolsMCP
**Status:** spec, not implemented
**Filed issues:** (none yet)
**Source:** triage of `user-logs/Kendall/session_145439_auto-Test.log`, 2026-09-09
**Depends on:** nothing (ships standalone)

---

## 1. Context

`FTM_ModifiesDB` is a **write lockout** in FlexTools, not documentation.
`flextoolslib/code/FTModuleClass.py:106-112`:

```python
def Run(self, project, report, modifyAllowed = False):
    if self.runFunction:
        # Prevent writes if not documented
        if modifyAllowed and not self.docs[FTM_ModifiesDB]:
            report.Info("(Modifications are allowed, but this module doesn't modify the project.)")
            modifyAllowed = False
        self.runFunction(project, report, modifyAllowed)
```

And in simplified mode it is the *sole* source of the flag --
`flextoolslib/code/FTModules.py:270`:

```python
if FTConfig.simplifiedRunOps:
    modifyAllowed = docs[FTM_ModifiesDB]
```

This MCP drops the clamp entirely:

- `execution.py:4064` sets `"modifyAllowed": WRITE_ENABLED` unconditionally.
- `execution.py:4073` calls `Main` **directly** when present, so our shim
  `FlexToolsModuleClass.Run` (`execution.py:3755-3757`) -- which has no clamp
  anyway -- never executes for a full module.
- The only other references to the key are the template emitter
  (`execution.py:2321`), the `flextoolslib` shim constant (`execution.py:3743`),
  and a presence-check string in the structure validator
  (`validators.py:423`). Nothing ever *reads* the user value.

**Observed consequence.** Session 145439 op#3 (14:57:17): a module declaring
`FTM_ModifiesDB : False` ran with `Write enabled: True`, took a pre-write
backup, and executed `AddComplexFormComponent` + `Delete` against the live
project. Under FlexTools that branch could not have run -- `modifyAllowed`
would have been clamped to False and the module would have reported
"(Modifications are allowed, but this module doesn't modify the project.)".

So the MCP is strictly more permissive than the host it emulates, and the same
file behaves differently in the two. That is the whole bug.

### Why the flag was wrong in the first place

`modifies_db` is asked once, at template time, of the LLM
(`execution.py:2198-2204`) and never revalidated against the code that gets
written. We already compute `mutations_detected` at run time
(`validators.py:3594` `build_writeability_payload`, `validators.py:3554`
`compute_is_mutating_script`), so the contradiction is cheap to detect and we
simply never looked.

---

## 2. Settled -- do not revisit

- **Match FlexTools behaviour, do not invent our own.** The clamp text and
  semantics come from `FTModuleClass.py:106-112` verbatim.
- **Do not silently clamp and continue when mutations are present.** FlexTools
  can afford to (its `report.Info` goes to a human watching a GUI); an MCP run
  that silently no-ops every write would look like success to the model and to
  the user. See 3b.
- **The declared flag is not authority to write.** It gates *down*, never up.
  `ModifiesDB: True` plus `write_enabled=False` is still read-only.

---

## 3. Design

Two distinct behaviours, because the two mismatch directions are not
symmetrical.

### 3a. `ModifiesDB: False` + no mutations detected -- clamp, like FlexTools

Port the clamp. `modifyAllowed` becomes False and the module runs. Emit the
same advisory FlexTools emits so behaviour and output both match.

### 3b. `ModifiesDB: False` + mutations detected -- refuse

This is the Kendall case and it is a **portability lie**: the module cannot do
under FlexTools what it is about to do here. Refuse pre-flight with a new
reason code `modifiesdb_contract_mismatch`, listing the detected mutations
(reuse `build_writeability_payload`, so the payload matches the
`confirmation_required` shape the model already knows how to read) and the
one-line fix: set `FTM_ModifiesDB : True`.

Refusing rather than clamping is the point. Clamping here would hand back a
clean-looking run in which every write silently did nothing -- the exact
failure mode `shared-mode-access` CP1/T1.5 was written to stamp out.

### 3c. `ModifiesDB: True` + `write_enabled=False` -- unchanged

Dry-run, as today. No new behaviour.

### 3d. `ModifiesDB` absent or non-boolean

`validators.py:423` already requires the `docs` dict to exist for a
`partial_module`. Extend to the value: a missing or non-boolean
`FTM_ModifiesDB` in a `full_module` is a structure reject, same tier as the
missing-`docs` reject, pointing at `get_module_template`. A bare snippet has no
`docs` and is unaffected -- see 3e.

### 3e. Bare snippets are out of contract

`source_kind` of `bare_snippet` has no `docs` dict by design
(`CLAUDE.md`, "Lightweight op form"). This gate applies only to
`full_module` and `partial_module`. Snippets stay governed by
`write_enabled` + `confirmed` alone.

### 3f. Read the declared value from the AST, not by exec

The value must be extracted from the already-parsed `code_tree` the pre-flight
path holds -- find the `docs` assignment, then the `FTM_ModifiesDB` key. Never
exec module code to read it: pre-flight runs in-process, before the subprocess,
and executing user code there would be a sandbox escape.

Handle the two spellings: modules import `from flextoolslib import *` so the
key appears as the bare name `FTM_ModifiesDB` (an `ast.Name`), but the shim
also defines the string constant, so a literal `"FTM_ModifiesDB"` key is
legal too. Accept both. Anything not a literal `True`/`False` is 3d.

---

## 4. Checkpoints

### CP1 -- read the declared flag

- **T1.1** New helper in `validators.py`: `read_declared_modifies_db(tree)` ->
  `True` / `False` / `None` (absent) / `"non_literal"`. AST only, per 3f.
- **T1.2** Unit tests: bare-name key, string key, absent key, `None` value,
  a computed value, no `docs` dict at all, `docs` built by `dict()`.

### CP2 -- the gate

- **T2.1** In `handle_run_module`, after `cud_info`/`cert` are computed and
  **before** the `needs_lock` confirmation gate (`execution.py:4253`), add the
  mismatch check per 3b. Ordering matters: a portability lie should be reported
  before we ask the user to confirm a write we are going to refuse anyway.
- **T2.2** New error code `modifiesdb_contract_mismatch` in the tool contract;
  update `docs/TOOL-CONTRACT.md` error table (it documents 18 codes today).
- **T2.3** Structure reject for 3d, alongside the `partial_module_structure`
  reject in `validators.py:423`.
- **T2.4** `_log_preflight_reject` line for both new rejects, so they appear in
  the operations log like `confirmation_required` does.

### CP3 -- the clamp

- **T3.1** Pass the declared value into the subprocess alongside
  `WRITE_ENABLED`, and apply 3a where `modifyAllowed` is bound
  (`execution.py:4064` for the namespace, `:4073` for the `Main` call).
- **T3.2** Port the clamp into the shim `Run` (`execution.py:3755`) too, so the
  `FlexToolsModule`-only path (`:4074`) behaves identically. Both paths, not
  one.
- **T3.3** Emit the FlexTools advisory text through `report.Info` so a clamped
  run is visible in the returned messages, not just in our log.

---

## 5. Verification

1. **Unit** -- `tests/test_modifiesdb_parity.py`: the CP1 extraction matrix,
   plus the gate decision table (declared x detected x `write_enabled`).
2. **Gate** -- use the boom-stub pattern from
   `tests/test_issue55_write_safety_ladder.py:210-261` to prove a
   `modifiesdb_contract_mismatch` reject takes no lock and spawns no
   subprocess.
3. **Replay** -- the exact 2355-byte module from session 145439 op#3
   (`sha256=527d148f3617`) must now be refused, and the same module with
   `FTM_ModifiesDB : True` must reach the confirmation gate. Keep the verbatim
   file as a fixture.
4. **Clamp** -- a read-only-by-declaration module with no mutations runs, and
   its returned messages contain the FlexTools advisory string.
5. **Contract** -- `python tests/make_golden.py --regen`, then
   `pytest tests/test_response_contract.py`.
6. **Regression** -- full `pytest`, plus
   `python scripts/validate_integrity.py all` and
   `python scripts/verify_python.py`.

---

## 6. Out of scope

- Auto-fixing the flag. We refuse and name the fix; we do not rewrite the
  declared contract on the user behalf. (Bulk migration of existing broken
  modules is `broken-script-migration`.)
- Inferring `modifies_db` at template time instead of asking
  (`execution.py:2198`). Worth doing, but it is a template-UX change and this
  gate makes a wrong answer harmless.
- `FTM_Version` / `FTM_Synopsis` / other doc keys -- no behavioural meaning in
  either host.
