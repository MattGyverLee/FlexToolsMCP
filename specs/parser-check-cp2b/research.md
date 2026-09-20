# Phase 0 research -- CP2a-bridge + CP2b

Eight findings and the decisions they force. Each was checked against this
repository's source or the installed environment, not inferred from the parent
specification. Where a finding contradicts `CP2-SPEC.md`, the source wins and the
contradiction is stated rather than smoothed.

---

## R-01 -- The floor can be raised. The verification environment still cannot prove it.

**Observed.**

```
python -c "import flexicon; print(flexicon.version)"   ->  4.9.0
python -m pip show pyflexicon                          ->  Version: 4.8.0
flexicon.__file__  ->  D:\Github\_Projects\_LEX\flexicon\flexicon\__init__.py
```

The distribution metadata says `4.8.0`; the code on `sys.path` is the `4.9.0`
working tree, path-installed.

**Escalation E-C is RESOLVED.** `pyflexicon` **4.9.0 is published** (maintainer,
2026-09-19). The tag push and release were the blocking maintainer acts and they
have been performed. The floor may therefore be raised to a version that genuinely
resolves, and FR-011 is dischargeable in full rather than in halves.

**What is still true, and is now the operative constraint.** The published
distribution is **not installed in the environment CP2b will be verified in**, and
the maintainer states it will not be within this session. So every measurement taken
here is taken against a path install whose pip metadata reads `4.8.0`.

`server/versioning.py:124-150` resolves a Python library's version by checking the
**live module attribute first** (`__version__`, then `version`) and falling back to
`importlib.metadata` only when the module carries no usable attribute. The comment
at `:126-131` records why: for editable/path installs pip metadata goes stale while
the source on `sys.path` is what is actually in use (issue #38). The server
therefore already detects `4.9.0` and will look for a `4.9.0` index.

**Decision D-B1 (revised).** The bridge lands as one unit -- floor, index and
equality test together -- and the equality test compares **the version the server
itself resolves** (`versioning.py`'s live-module-first result) against the version
suffix of every bundled flexicon-locked index artifact, then separately against the
floor declared in `pyproject.toml` and `requirements.txt`.

It deliberately does **not** compare against `importlib.metadata`. In this
environment that comparison reads `4.8.0` and would fail against a correct tree; on
a clean install of the published `4.9.0` both sources agree and the comparison adds
nothing. A test that is red for the wrong reason on the maintainer's own machine
gets muted, and a muted test is worse than an absent one.

**The one thing the plan must not claim.** A green equality test here proves floor,
index and *live module* agree. It does **not** prove the published `4.9.0`
distribution installs and satisfies the floor, because that distribution is not
installed here. That is a separate, one-command check
(`pip install "pyflexicon>=4.9.0,<5"` in a clean environment, then re-run the suite)
and the plan schedules it as its own task with its own evidence line rather than
folding it into the equality test. Per Constitution Principle IV as CP2a applied it:
report the measurement, not the impression.

**Alternative considered and rejected.** Deferring the floor bump until a clean
environment exists -- rejected now that E-C is resolved. The floor's whole function
is to stop a user resolving `4.8.0` and getting an import error from
`project.Parser`; deferring it leaves exactly that hole open while the index claims
`4.9.0`, which is the 2.10.0 incident's shape (an index built at 4.5.2 shipped
against a `>=4.3.0` floor).

---

## R-02 -- This server process never opens a project. The held grammar cannot live in it.

**Observed.** Every project-touching operation in this repository runs in a
one-shot child process:

- `handlers/execution.py:5060` `run_scan_module(...)` -- "the MCP server process
  itself never opens a project" (`:5090`).
- It launches through `subprocess_helpers.run_script_async` (`:56`), plain CPython
  via `sys.executable`, with a timeout and a process-tree kill
  (`subprocess_helpers.py:20-50`).
- `project_access.py:16-33` and `project_discovery.py:173` both state and enforce
  the same boundary from the detection side.

**The collision.** The parent spec requires, in the same feature:

- **FR-042 / D2** -- at most one *held* loaded grammar, released on project switch.
- **FR-031 / SC-009** -- an urgent word interleaves at the running batch's next word
  boundary, the batch does not restart, **and the grammar is loaded exactly once for
  both**.
- **FR-043 / SC-015** -- the held grammar's currency is confirmed before every reuse.

A one-shot subprocess per call satisfies none of these: it reloads the grammar every
time, cannot interleave, and has no "held" grammar whose currency could be confirmed.
`loading_grammar` -- the stage the spec singles out as the one that most often
exhausts memory and that dominates a cold run -- would be paid on every single word.

**Decision D-B2.** CP2b introduces a **long-lived parse worker process**, one per
project, owning the LCM cache, the flexicon `project.Parser` area and the held
grammar. The server process owns the queue, the run records and the tool handlers,
and talks to the worker over a line-delimited JSON channel on stdin/stdout.

This is the single largest piece of net-new infrastructure in the checkpoint and it
is exactly the "scope risk" the parent spec's risk register names. It is not
avoidable by construction: any design that keeps the one-shot model forfeits SC-009
and SC-014 outright, and the spec forbids a second, simpler execution path (FR-026).

**Where each guarantee lands.**

| Guarantee | Owner |
|---|---|
| queue, priority ordering, FIFO within level (FR-030) | server |
| grace window, inline-vs-handle (FR-028) | server |
| run record, incremental persistence (FR-029) | server |
| word-boundary interleave (FR-031) | **worker** -- only it knows where a boundary is |
| cooperative cancellation (FR-032) | both -- server sets the flag, worker observes it at the boundary |
| held grammar, single slot, currency (FR-042, FR-043) | **worker** |
| engine gate (FR-015) | **worker**, first statement -- see R-03 |

**Alternatives considered.** (a) Keep one-shot subprocesses and reload per call --
rejected, forfeits SC-009/SC-014 and makes the most expensive step the per-word step.
(b) Open the project in the server process -- rejected, it would break the boundary
three modules currently state and enforce, and would put an LCM cache and a
`.fwdata` lock inside the MCP server's lifetime. (c) A worker per *run* rather than
per project -- rejected, an interleaving urgent word and the batch it interrupts are
two runs that must share one loaded grammar.

**What this costs.** Process lifetime, health and orphan cleanup become this
repository's problem. `subprocess_helpers._kill_process_tree` (issue #57) already
exists because a pythonnet grandchild holding a `.fwdata` lock is a known failure
here; a *long-lived* holder makes that worse, not better. The worker must therefore
release the project on idle timeout and on server shutdown, and the plan schedules a
test for the orphan case rather than leaving it to review.

---

## R-03 -- `check_active_parser` reads an open project, so "first statement of the handler" cannot be literal

**Observed.** `parser_probe.py:751` reads `project.MorphologicalDataOA.ActiveParser`.
That needs an **open project**, which by R-02 exists only in the worker.
`contracts/error-codes.md` and `parser_probe.py:685-714` say the helper is intended
as "the **first statement** of each spine-executing handler ... before any
`HCParser` or config-export construction", and FR-015 restates it.

`ActiveParser` is deliberately re-read live on every call, never cached per session,
because a user can flip it mid-session via Words > Parser > Choose Parser
(`parser_probe.py:733-741`). So a server-side memo of the engine is forbidden, which
removes the obvious workaround.

**Decision D-B3.** The gate runs as the **first statement of the worker's request
handler, before any parser area is touched**, and its refusal is marshalled back
through the channel as `parser_engine_mismatch` unchanged. The server-side handler's
first action remains ordering-significant -- it does no parser work before dispatching
to the worker -- but the *engine* check itself is necessarily in the worker.

FR-015's substance is "before any parser is constructed", and this satisfies it
strictly: nothing constructs a parser before the check, and the check is re-read
live per request rather than per worker lifetime. The plan records the reading so a
reviewer comparing the code against FR-015's literal words finds the reasoning rather
than an apparent violation.

**Guarded by a test, not by the reading.** A test asserts that for an `XAmple`
project the worker records zero calls into the parser area and returns
`parser_engine_mismatch` -- the same negative-assertion shape CP1's T026 uses. The
reading is prose; the test is the control.

---

## R-04 -- A third flexicon-version-locked artifact the Verbatim Constraints do not name

**Observed.** `src/flextoolsmcp/index/` currently holds:

```
python/flexicon_api_v4.8.0.json
python/flexicon_lcm_bridge_v4.8.0.json
common_patterns_flexicon-v4.8.0.json        <-- one directory up
```

`extract_patterns.py:416-419` derives the version from the api filename and writes
`common_patterns_flexicon-v{version}.json`; `curated_recipes.py:11-14` documents the
file as the versioned artifact the server serves recipes from. `refresh.py:584`
confirms pattern extraction runs as part of the same full refresh.

The spec's Verbatim Constraints name only the two files under `index/python/`,
qualified as "which **currently** comprises". That is a statement about that
directory, not a closed list of every flexicon-version-locked file in the repository.

**Decision D-B4.** The bridge regenerates and ships all three, and the equality test
asserts over the **set of flexicon-version-locked artifacts discovered by pattern**,
not over a hardcoded pair. A hardcoded pair is the same shape of defect as the 2.10.0
incident the test exists to prevent: it would pass while a third file sat at the old
version.

---

## R-05 -- `HCParser_DoesNotLoadXCore` must assert against the worker, and R-02 makes that easy

**Observed.** The guarantee is about a **call path, not a class** (SPEC 12.1):
`ParserWorker` and `ParserScheduler` pull xCore in through their own constructor
parameters, so "reuse ParserWorker for consistency" is the refactor the test exists
to catch. Asserting on the *server* process proves nothing -- it never loads
ParserCore at all.

**Decision D-B5.** The test drives a real `Update()` + `ParseWord()` in the worker
process and asserts over the worker's `AppDomain.CurrentDomain.GetAssemblies()`
after the parse, checking for no `XCore` and no `System.Windows.Forms`. The
assertion runs **inside** the worker and its result is returned over the channel, so
it observes the process that actually parsed.

**The vacuity guard.** The assertion must also prove it ran against a real parse --
it asserts positively that `ParserCore` *is* loaded and that the parse produced a
result. A test that passes because the parse never happened is the failure mode here,
and CP1's boundary test (`tests/test_cp1_boundary.py:36-45`) already establishes the
house pattern of proving the exercise was not vacuous.

---

## R-06 -- CP1's boundary regression will fail on CP2b, by design, and must be amended not deleted

**Observed.** `tests/test_cp1_boundary.py` asserts statically, over the whole
`src/flextoolsmcp/server/**` tree via `rglob`, that **no** `HCParser(` construction
exists, no construction is reached through `getattr`/`eval`/`import_module`, and no
reflective-instantiation API is called. Its own docstring says the `rglob` is
deliberate "so modules that land later ... are covered the moment they exist".

CP2b constructs no `HCParser` directly -- it goes through `project.Parser`, and the
facade constructs it inside flexicon, outside this tree. So the static half should
still pass. The **dynamic** half installs a spy over the CLR seam and asserts zero
`ParseWord`/`TraceWordXml`/`Update` invocations while exercising CP1 entry points.
The worker module is not a CP1 entry point, so it is not exercised -- but the file's
framing ("CP1 detects, scans and reports, but never constructs a parser") becomes
false about the repository as a whole the moment CP2b lands.

**Decision D-B6.** The file is **amended, not deleted or weakened**. Its scope is
narrowed in writing from "this repository" to "the CP1 surface", it gains an explicit
allowlist entry for the worker module naming CP2b as the reason, and the allowlist is
pinned by a test so widening it means editing a test rather than appending a line
nobody sees -- the same control CP2a's QC gate imposed on `NON_CONTRACT_PREFIXES`.

Deleting it would discard the guarantee that the *diagnostic* path still never
parses, which is exactly the guarantee CP2b makes easier to break.

---

## R-07 -- The run record has a precedent here, and it is the right one

**Observed.** `server/skeleton_storage.py` is append-only JSONL under a
`threading.Lock`, with an environment-variable directory override
(`FLEXTOOLSMCP_SKELETON_DIR`), defaulting outside the package so it survives
upgrades (`:39-60`). Its own docstring records the debt: no size cap, no rotation.

**Decision D-B7.** The run record follows that shape -- one JSONL per run under a
run directory, appended as each word completes -- which is what FR-029 ("written as
they are produced") and SC-008 ("0 results lost") require: a record that is
`fsync`-appended per word survives a killed process, and one held in memory and
written at the end does not.

**The inherited debt is not inherited silently.** Trace payloads are large (the
parent spec calls their location "a design decision rather than a detail"), and
`skeleton_storage`'s unbounded growth is already a known problem with a small
payload. A run record of traces needs a size cap from day one, not as a follow-up, so
the plan schedules it rather than copying the precedent's omission.

---

## R-08 -- The resolver's terminal accessor is untested

**Observed.** From CP2a's evidence artifact: FR-007 (`Texts.GetGenres`), FR-008
(`Allomorphs.GetOwningEntry`) and FR-009 (`MSA.GetAll`) "each had a single
implementation task in `tasks.md` and no test task was scheduled for any of them.
Nothing pins the empty-collection contract, the null-owner branch, or the MSA
wiring."

Verified present in the tree: `MSAOperations.GetAll` at
`flexicon/code/Lexicon/MSAOperations.py:177`, `TextOperations.GetGenres` at
`:705`, `AllomorphOperations.GetOwningEntry` at `:1307`.

**Why this is a precondition and not a footnote.** FR-018's resolver terminates in
MSA HVOs. It reaches them through `MSA.GetAll`. FR-019 requires that a piece
resolving to no usable analysis is **refused with its candidates named, and no parse
run** -- and SC-005 puts that at 100% with 0 parses. If `GetAll` returns an empty
collection where it should return analyses, the resolver refuses a decomposition that
is in fact valid; if it returns analyses it should not, the resolver passes a bad
restriction into `TraceWordXml`. Both are the silently-narrowed-search failure the
requirement exists to prevent, arriving from underneath it.

**Decision D-B8.** CP2b schedules tests for all three accessors **in the flexicon
repository**, before the resolver is written. They are CP2a's debt by origin but
CP2b's precondition by dependency, and the required invocation there is quoted
verbatim per that repository's Constitution Principle II:

```
python -m pytest -m "not requires_live_project" -q
```

This is the only work in this checkpoint that lands outside FlexToolsMCP. It is
three test files, no production change, and it does not reopen CP2a: the surface is
frozen by the set-equality test and nothing here alters it.

---

## Resolved unknowns

| Unknown from the parent spec | Resolved by |
|---|---|
| Whether the facade is named `TryWord`/`TraceWord` (CP2-SPEC 3.1) | It is not. Six members, listed in `spec.md` Delta 1, frozen by set equality. |
| Where the trace payload is kept | The run record (R-07), per SPEC 5.5 and the parent spec's stated assumption -- with a size cap added. |
| Whether a loaded parser is cached and what invalidates it | Yes, in the worker, one slot, invalidated by `IsUpToDate()` before reuse and by project switch (R-02, D2). |
| Whether CP2 touches `parser_probe.py` | No -- 0 lines, per D1/FR-041/SC-016. Unchanged from CP2a. |
| Whether the three grammar lints fold in here | No -- D5 defers them to CP3, which must re-probe rather than reuse the verdict. |

## Unknowns that remain open, and are not resolvable by research

| Open | Why it cannot be closed here |
|---|---|
| **E-C** -- the `v4.9.0` tag | Maintainer act, irreversible, publishes to PyPI. Gates only the floor half of the bridge (D-B1). |
| **E-D** -- tier A4 live | Requires a live write to make a grammar stale on purpose. Human authorisation against a backed-up or copied project; an unattended run stops with `needs_human`. |
| The branch this repository's CP2b work lands on | Maintainer decision, recorded in `spec.md`. Blocks the first implementation task, not the plan. |
