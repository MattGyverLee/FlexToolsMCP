# SPEC -- portability pre-flight: refuse modules that cannot run in FlexTools

**Feature:** `portability-preflight`
**Repo:** FlexToolsMCP
**Status:** spec, not implemented
**Filed issues:** (none yet)
**Source:** triage of `user-logs/Kendall/session_{112101,145439,154828}*.log`, 2026-09-09
**Depends on:** `flexicon-project-bridge` (the gate must be able to name a fix
that works)

---

## 1. Context

The MCP injects a **flexicon** `FLExProject` (`execution.py:3911,3939`);
FlexTools injects a **flexlibs** one (`flextoolslib/code/FTModules.py:75,24`).
Two code shapes therefore pass here and fail there:

```python
# Shape A -- the facade off the injected project
for entry in project.LexEntry.GetAll():
    headword = project.LexEntry.GetHeadword(entry)

# Shape B -- an Operations class constructed from the injected project
lex = LexEntryOperations(project)
lex.AddComplexFormComponent(entry, c)
```

Both appear in the Kendall modules. Shape B fails because
`BaseOperations.__init__` binds `self.project = project`
(`flexicon/code/BaseOperations.py:617-624`) and flexicon operations then reach
42 attributes a flexlibs project does not have (170 call sites; 14 of them
whole sub-facades). Shape A fails immediately -- flexlibs has no `LexEntry`
property at all.

The MCP reported `[OK] Operation completed successfully` for every one of these
runs. **The tool that exists to help people write FlexTools modules cannot
currently tell whether the module it just blessed will run in FlexTools.** That
is what this gate fixes.

---

## 2. Settled -- do not revisit

- **Bare snippets are never gated.** `source_kind: bare_snippet` is the
  exploration primitive (`CLAUDE.md`, "Lightweight op form"); it is not
  destined for FlexTools and the injected flexicon project is exactly right for
  it. Gating snippets would destroy the fast path.
- **Full modules are gated.** A `docs` dict plus a `FlexToolsModule` binding is
  a declaration of intent to run under FlexTools. That is the contract we
  check.
- **The gate names a fix, it does not rewrite code.** Auto-migration is
  `broken-script-migration`, invoked explicitly.
- **This is a portability gate, not a correctness gate.** The flagged code runs
  correctly *here*. Message wording must say so, or users will think we are
  reporting a bug in their logic.

---

## 3. Design

### 3a. Where the facade name set comes from

Do **not** hardcode a list of facade properties. It would drift the same way
the `_LIBLCM_MUTABLE_PATTERNS` verb list drifted (issue #93 findings (a)/(d)).

Derive it from the loaded flexicon API index -- the same `api_idx` the mutation
detector already consumes (`validators.py:3200` `certify_script_readonly`). The
index knows the flexicon entity set; the facade properties are its accessor
names (`LexEntry` at `flexicon/code/FLExProject.py:1361`, `Senses` at `:1894`,
`Variants` at `:2140`, and the rest). Add a build step to `refresh.py` that
records the accessor -> Operations-class map explicitly, so the gate has a
first-class input instead of inferring one.

Cross-check the set against what a flexlibs project actually provides, so the
gate flags only genuinely absent names. `flexlibs/code/FLExProject.py` has
`LexiconAllEntries` (`:591`), `LexiconAllEntriesSorted` (`:615`), `WSHandle`
(`:628` private, `:1` public wrapper) and friends -- those are portable and must
not be flagged.

### 3b. Detection

Reuse the existing AST machinery in `validators.py`; do not write a second
walker.

- **Shape A:** `project.<Accessor>.<Method>(...)` -- the same node pattern
  Step 1c of `certify_script_readonly` already matches for the mutation
  detector. Flag when `<Accessor>` is in the flexicon-only set from 3a.
- **Shape B:** `_resolve_alias_maps` (`validators.py`, issue #8 alias tracking)
  already produces the `alias -> Operations class` map for
  `lex = LexEntryOperations(project)`. Flag any such construction whose
  argument is the injected `project` name.

Both shapes must resolve through aliases, because that is how the confirmation
gate was defeated in the same logs -- see `write-authorization-audit`.

### 3c. The verdict

New pre-flight reject, reason code `not_portable_to_flextools`, carrying:

- `shape`: `"facade_access"` or `"operations_construction"`
- `hits`: `[{line, expression, accessor_or_class}]` -- line-accurate, like
  `mutations_detected`
- `fix`: the `FromOpenProject` shape from `flexicon-project-bridge` section 3d,
  rendered with the accessors this module actually uses
- `why`: one line stating the code is valid here and fails under FlexTools,
  naming `FTModules.py:75` as the reason

### 3d. The escape hatch

Some modules genuinely are MCP-only (a one-off audit the user keeps as a file).
Two ways out, both explicit:

1. `run_module(portability="mcp_only")` -- per-call, not sticky.
2. A `docs` key `FTM_McpOnly : True` -- travels with the file, so a re-run next
   week does not re-prompt.

Default is `portability="flextools"`. Never infer the escape from the code.

### 3e. Ordering against the other gates

Run **after** the structure gate (a module missing `docs` is not yet a module)
and **before** the write-confirmation gate (`execution.py:4253`). A module that
cannot run in FlexTools should not first be walked through a live-write
confirmation.

Interaction with `modifiesdb-parity` 3b: both are portability rejects. If both
fire, report both in one response rather than making the user round-trip twice.
Collect pre-flight portability findings into a single reject payload.

---

## 4. Checkpoints

### CP1 -- the facade map

- **T1.1** `refresh.py` emits an explicit accessor map for flexicon
  (`accessor -> Operations class`) into the index, plus the flexlibs public
  method set, so the gate compares two recorded sets rather than guessing.
- **T1.2** Golden test that the map is non-empty and contains the known trio
  (`LexEntry`, `Senses`, `Variants`), so an index regression fails loudly
  instead of silently disabling the gate.

### CP2 -- detection

- **T2.1** `find_nonportable_project_use(code, tree, api_idx) -> list[hit]`
  in `validators.py`, reusing Step 1c matching and `_resolve_alias_maps`.
- **T2.2** Unit matrix: both shapes; aliased and direct; a portable
  `project.LexiconAllEntries()` call (must NOT flag); a facade call on a
  non-injected object (`fx.LexEntry` where `fx = FLExProject.FromOpenProject`
  -- must NOT flag, this is the fixed shape); a snippet (not gated at all).

### CP3 -- the gate

- **T3.1** Wire into `handle_run_module` per 3e, with the combined
  portability payload.
- **T3.2** New error code `not_portable_to_flextools` in
  `docs/TOOL-CONTRACT.md`.
- **T3.3** `portability` input on `run_module` (`models.py`,
  `tool_definitions.py`) and the `FTM_McpOnly` docs key, per 3d.
- **T3.4** `_log_preflight_reject` line, and log the escape hatch when used --
  an `mcp_only` run must be visibly marked in the operations log, or the log
  stops being evidence of portability.

---

## 5. Verification

1. **Unit** -- CP2 matrix, no FieldWorks needed.
2. **Gate** -- boom-stub pattern from
   `tests/test_issue55_write_safety_ladder.py:210-261`: a
   `not_portable_to_flextools` reject takes no lock and spawns no subprocess.
3. **Replay** -- all four distinct module fingerprints from the Kendall logs
   (`b9f01db03221`, `98abf566dc9c`, `527d148f3617`, `0ce1eadb7869`) must be
   refused with line-accurate hits. Keep them as verbatim fixtures; they are
   already extracted from the logs.
4. **Fixed shape passes** -- each of those four, migrated to the
   `FromOpenProject` shape, must pass the gate.
5. **True negative** -- a module using only the flexlibs public surface
   (`project.LexiconAllEntries()`, `project.LexiconGetHeadword(entry)`) passes
   ungated. Note both appear in the Kendall modules already, mixed with the
   non-portable calls.
6. **Contract** -- `make_golden.py --regen`, `pytest
   tests/test_response_contract.py`.
7. **Regression** -- full `pytest`, `validate_integrity.py all`,
   `verify_python.py`.

---

## 6. Out of scope

- Rewriting the offending code -- `broken-script-migration`.
- Running the module under real FlexTools to confirm the verdict --
  `vanilla-flextools-parity`. This gate is static; that spec is the empirical
  check on whether this gate agrees with reality.
- Gating raw LibLCM use. `from SIL.LCModel import ILexEntry` works in both
  hosts and is out of scope, though see `broken-script-migration` section 3c
  for the separate `ILexEntry(c)` cast bug found in the same modules.
