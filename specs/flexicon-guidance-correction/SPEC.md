# SPEC -- correct the flexicon guidance that generated the broken modules

**Feature:** `flexicon-guidance-correction`
**Repo:** FlexToolsMCP
**Status:** spec, not implemented
**Filed issues:** (none yet)
**Source:** triage of `user-logs/Kendall/session_{112101,145439,154828}*.log`, 2026-09-09
**Depends on:** `flexicon-project-bridge` (cannot document a fix that does not
exist yet)

---

## 1. Context

Every broken module in the Kendall logs opens with the same two lines:

```python
from flextoolslib import *
from flexicon import FLExProject, LexEntryOperations, VariantOperations
```

`FLExProject` is never referenced in any of those module bodies. It is a dead
import -- and we told him to write it. Three places do:

1. **`CLAUDE.md`**, "Preferred: Flexicon" -- the mandated template carries
   `from flexicon import (FLExProject, LexEntryOperations, ...)` under the
   comment `# CRITICAL: Explicitly import from flexicon`, followed by:

   > **Silent Failure Risk**: FLExTools loads stable flexlibs first. Without
   > explicit flexicon imports, your code will silently use the wrong (stable)
   > version

   and the worked contrast:

   ```python
   # WRONG - Gets stable flexlibs version
   entry = project.LexEntry.GetAll()
   # CORRECT - Guarantees flexicon version
   from flexicon import LexEntryOperations
   entry = project.LexEntry.GetAll()
   ```

   The two branches are **identical** in the operative line, and the claim is
   false: importing a class does not change which instance FlexTools passes to
   `Main()`. Worse, `project.LexEntry` is the shape that cannot work under
   FlexTools at all.

2. **`docs/FLEXTOOLS-STYLE-GUIDE.md:119-122`** -- the same claim:
   `# DON'T rely on global imports (FLExTools will shadow with stable flexlibs)`
   / "FLExTools loads stable flexlibs first. Without explicit imports, code
   silently uses the wrong library." Also `:326` ("Assume stable flexlibs is
   available/correct") and `:414` ("Prevent silent shadowing by stable
   flexlibs").

3. **The shipped template** -- `execution.py:318` hardcodes the import line
   `"flexicon": "from flexicon import FLExInitialize, FLExCleanup, FLExProject"`,
   so `get_module_template(flavor='flexicon')` emits the dead import itself.
   `src/flextoolsmcp/templates/2-flexicon-template.py` needs the same check.

**There is no shadowing mechanism.** FlexTools does not shadow flexicon with
flexlibs; it simply constructs a flexlibs project
(`flextoolslib/code/FTModules.py:75,24`) and hands it in. The guidance
diagnosed a real symptom (modules behaving differently under FlexTools) with an
invented cause, and prescribed a fix that cannot work. Then the MCP, which
injects a flexicon project (`execution.py:3911,3939`), confirmed the fix
"worked" on every run.

This spec exists because bad guidance is a defect with a blast radius: it
generated at least four distinct broken modules across three sessions, and it
will keep generating them until the text changes.

---

## 2. Settled -- do not revisit

- **Delete the shadowing claim outright.** Do not soften it. There is no
  mechanism; a hedged version is still false and still misleads.
- **Keep "prefer flexicon".** That part is sound -- coverage, docs, multistring
  normalisation. Only the *reason given for the import* and the
  `project.<Facade>` idiom are wrong.
- **The guidance must teach one portable shape**, the `FromOpenProject` form
  from `flexicon-project-bridge` section 3d. Two shapes ("this for the MCP,
  that for FlexTools") reintroduces the bug.
- **`CLAUDE.md` is the highest-leverage file.** It is loaded into every session
  in this repo and it currently mandates the broken template. Fix it first.

---

## 3. Design

### 3a. What replaces the claim

The honest statement, to appear in all three places in substantially this form:

> FlexTools constructs the project object itself, using **flexlibs**
> (`flextoolslib/code/FTModules.py:75`). This MCP constructs a **flexicon**
> one. Importing a name from flexicon does not change which object your
> `Main()` receives -- so a module that calls `project.LexEntry.*` or
> `LexEntryOperations(project)` runs here and fails in FlexTools. To get the
> flexicon API surface in a module that must run in both, attach a flexicon
> view to the project you were handed:
>
> ```python
> fx = FLExProject.FromOpenProject(project)
> ```

### 3b. The corrected mandated template

Replace the `CLAUDE.md` template body. The import comment stops claiming
shadowing and starts explaining the bridge. The worked example must use `fx`,
not `project`, for every flexicon call, and must keep using `project` for the
flexlibs-portable calls so the distinction is visible:

```python
from flexicon import FLExProject

def Main(project, report, modifyAllowed):
    fx = FLExProject.FromOpenProject(project)   # flexicon view over the host project

    entries = fx.LexEntry.GetAll()
    report.Info(f"Processing {len(entries)} entries...")
    for entry in entries:
        for sense in fx.LexEntry.GetAllSenses(entry):
            report.Info(f"  {fx.Senses.GetGloss(sense)}")
```

Note the existing `CLAUDE.md` example already uses `project.LexEntry` and
`project.Senses` -- both non-portable. Every code sample in all three documents
must be swept, not just the headline template.

### 3c. Import hygiene

- Drop `FLExProject` from the template import when the module does not bridge;
  add it when it does. After 3b it is always needed, so the line stays -- but
  now it is load-bearing.
- `FLExInitialize` / `FLExCleanup` (`execution.py:318`) are for standalone
  scripts that open their own project. A FlexTools module must not call them --
  the host owns initialisation. Remove them from the module template and say
  why.

### 3d. Scope of the sweep

Files to change:

- `CLAUDE.md` (project instructions) -- the template, the "Why This Matters"
  section, the "Don'ts" entry about omitting flexicon imports.
- `docs/FLEXTOOLS-STYLE-GUIDE.md` -- `:84`, `:90`, `:119-122`, `:326`, `:332`,
  `:378`, `:414`, `:558`, and every code sample.
- `src/flextoolsmcp/templates/2-flexicon-template.py`,
  `1-flexlibs-stable-template.py` (verify it does not make the inverse error),
  `3-liblcm-template.py`, `00-FLAVOR-GUIDE.md`, `README.md`.
- `execution.py:318` (the import string) and the template emitter around
  `:2300-2360`.
- `~/.claude/CLAUDE.md` -- the user global file carries the same template. Out
  of this repo, so flag it for the user rather than editing it silently.

### 3e. Make the docs testable

The reason this survived is that no test reads the documentation. Add a check
that extracts every fenced `python` block from `CLAUDE.md`, the style guide,
and the templates, and asserts none of them contains a non-portable shape --
reusing `find_nonportable_project_use` from `portability-preflight` CP2. The
docs then fail the build the same way code does.

This is the durable fix. Everything else in this spec is a one-time edit.

---

## 4. Checkpoints

### CP1 -- the template and the claim

- **T1.1** Rewrite the `CLAUDE.md` flexicon template per 3b and replace the
  "Why This Matters" / "Silent Failure Risk" text with 3a.
- **T1.2** Same for `docs/FLEXTOOLS-STYLE-GUIDE.md`, all sites in 3d.
- **T1.3** Update `execution.py:318` and the shipped template files; drop
  `FLExInitialize`/`FLExCleanup` from the module flavour per 3c.
- **T1.4** Update the `CLAUDE.md` "Don'ts" bullet -- "Don't omit the flexicon
  imports - this causes silent failures with wrong library versions" is the
  same false claim in miniature.

### CP2 -- the guard

- **T2.1** `tests/test_docs_portability.py` per 3e: harvest fenced python
  blocks from the doc set and the templates, assert zero non-portable hits.
- **T2.2** Include the doc harvest in `scripts/validate_integrity.py` so it
  runs in the same place the other integrity checks do.

### CP3 -- tell the user

- **T3.1** Report the `~/.claude/CLAUDE.md` overlap to the user with the exact
  replacement text; do not edit their global file as part of this work.
- **T3.2** A short note in `docs/DECISIONS.md`: the shadowing claim was wrong,
  what replaced it, and why (so it does not get reintroduced by someone reading
  old commits).

---

## 5. Verification

1. **Automated** -- CP2. This is the acceptance test: the docs cannot contain a
   non-portable sample.
2. **Manual read-through** -- one pass over the changed sections checking that
   no residual sentence implies imports change the injected object.
3. **End-to-end** -- `flextools_get_module_template(flavor='flexicon')`, then
   run its output unmodified through the `portability-preflight` gate: it must
   pass. Today it would be refused, which is the sharpest statement of the bug.
4. **Regression** -- full `pytest`, `validate_integrity.py all`,
   `verify_python.py`.

---

## 6. Out of scope

- Migrating modules users have already saved -- `broken-script-migration`.
- The `GetAll()` behavioural-collection guidance, multistring `***`
  normalisation, and the other CLAUDE.md content: unaffected and correct.
- Rewriting the flexlibs-stable template to the bridge shape. A module that
  deliberately targets stable flexlibs is portable by construction; verify it
  makes no inverse claim (T1.3) and otherwise leave it.
