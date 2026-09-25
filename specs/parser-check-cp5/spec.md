# Feature Specification: parser-check CP5 -- the sandbox spine: hardened hcparse.ps1, flextools_parse_sandbox, corpus assertions

**Feature Branch**: `feat/parser-check-cp5`

**Created**: 2026-09-24

**Status**: Draft -- `lex-domain` gate cycle 1 run 2026-09-24: APPROVED, no blocking findings (two wording fixes applied). Three questions deferred to clarify (Q1-Q3, each with an adopted default).
**Re-planned 2026-09-24 (see `HANDOFF.md`)**: M-1 ("how do we get a working `hc`") resolved by
dropping the `hc` CLI entirely. Parse and Test now run **in-process, in the parse worker**
(`server/parse/worker_main.py`, `--sandbox` mode, `_SandboxBackend`), calling FieldWorks' own bundled
`SIL.Machine.Morphology.HermitCrab.dll` directly (the same engine Try A Word uses -- 3.8.2 in FW
9.3.11) via pythonnet and `XmlLanguageLoader.Load` / `Morpher` / `ParseWord`. It never imports
flexicon or LCM, opens no project, and writes no files. **Generate mode is unchanged**: the
allowlisted project copy, `GenerateHCConfig.exe`, and the cache still work exactly as designed below.
Every requirement, assumption and constraint that assumed a stand-alone `hc` process for Parse/Test
is superseded; retired text is marked "Retired (CP5 re-plan 2026-09-24)" rather than deleted, per the
project's archive-hygiene convention. See `research.md` R-17 and decisions D1-D8 for the option
comparison and the design details this re-plan adds.

**Input**: User description: "create a spec to resolve https://github.com/MattGyverLee/FlexToolsMCP/issues/166"

**Source document**: GitHub issue #166 (the durable definition of CP5; self-contained by design)
**Parent spec**: [`../parser-check/SPEC.md`](../parser-check/SPEC.md) -- sections 1.1, 1.2, 2 (S3, S4, S6),
4, 5.3, 5.5, 6.2, 7, 10, 10.1, 10.2, 11, 12.5, 13, 14, 15 (CP5 row), 16. If pruned, recover with
`git show e5afbfd:specs/parser-check/SPEC.md`.
**Predecessors**: CP1-CP4 on `main` (CP4 merge `b8c5df6`). The issue says the sandbox spine is
independent of the write spine; #165 is a sequencing dependency, not a code dependency.
**Successor**: #167 (CP6 -- contract codes, CHANGELOG, telemetry, user docs).

**Source-verified against** (2026-09-24):
- `sillsdev/machine` at `b77b2337` (cloned at `C:\Github\machine`),
  `src/SIL.Machine.Morphology.HermitCrab.Tool/` -- `Program.cs`, `ParseCommand.cs`, `TestCommand.cs`,
  `StatsCommand.cs`, `MorphInfo.cs`, `Extensions.cs`, and the `.csproj` (at tags `v3.7.0`, `v3.8.0` and `v3.9.4`).
- `fieldworks` `Src/GenerateHCConfig/Program.cs` and `ConsoleLogger.cs`.
- The installed FieldWorks 9.3.11 (`SIL.Machine.Morphology.HermitCrab.dll` 3.8.2) and this machine's
  .NET installation (runtime 8.0.23 only, no SDK).

**Source-verification note (re-plan, 2026-09-24)**: the `hc`-CLI facts above (`sillsdev/machine`
`Program.cs`, `TestCommand.cs`, etc.) remain accurate as a description of the stand-alone tool and of
the HermitCrab engine it wraps, but they no longer describe how Parse/Test run in this design; they
are superseded for that purpose and kept only where a fact about the *engine itself* (not the CLI)
still applies. `GenerateHCConfig.cs` and the FieldWorks-bundled DLL facts are unaffected -- Generate
mode is unchanged.

---

## Summary

The first four checkpoints ask the parser about the grammar **as it is in the project**. CP5 adds
the third spine: a **rehearsal space**. The linguist, or the assistant on their behalf, exports the
project's grammar to a HermitCrab configuration file, and optionally copies it into a named sandbox
and edits it ("tighten the left environment on this rule"). They then run words, or a whole corpus
of expected parses, against that file. Nothing in this spine can reach the live project: the copy
and the export happen on files the MCP made, and the parse itself happens in a `--sandbox` mode of
the existing parse worker (`server/parse/worker_main.py`) that loads only the exported configuration
and the FieldWorks-bundled HermitCrab engine -- never flexicon, never LCM, never the live project.
That is what makes speculative edits safe (parent 1.2: "Tweaking an exported grammar to test a theory
IS safer than changing the whole database").

**Retired (CP5 re-plan 2026-09-24).** The paragraph below described the original design: a
stand-alone `hc` CLI process, discovered on the machine and driven by a hardened `hcparse.ps1` in
Parse/Test modes. The maintainer's decision (`HANDOFF.md`) replaced that with the in-process worker
design above. `hcparse.ps1`'s **Generate mode only** (the allowlisted copy plus
`GenerateHCConfig.exe`, cached) is unaffected and stays exactly as designed below; H1-H4, H8, H9,
H11 and FR-013, FR-016, FR-017's original wording, and the "the spine's risks are disk and
subprocess" framing applied to a subprocess that no longer exists for Parse/Test. The kept text:

- ~~The spine's risks are disk and subprocess, not the lexicon. The maintainer's `hcparse.ps1`
  already works, and CP5 hardens it (H1-H12) instead of replacing it.~~ Now: the spine's risks are
  disk (Generate mode's copy) and in-process engine isolation (Parse/Test); there is no longer an
  external subprocess to hardening for the parse step itself.
- **H6 -- always delete the project copy.** Today every run leaks a full copy into `%TEMP%`. Still
  applies, to Generate mode's copy.
- **H10 -- keep the cache's config apart from the user's hand-edited one.** Still applies.
- ~~H1 -- find `hc` where it is actually installed.~~ Retired: there is no `hc` to find. Discovery
  now locates the FieldWorks-bundled DLL and `GenerateHCConfig.exe` (FR-001, reworded).
- ~~H4 -- stop trusting exit codes that are always 0.~~ Retired for Parse/Test (no subprocess exit
  code); still applies to `GenerateHCConfig.exe`'s exit code (FR-009, unaffected).

Reading the tool sources turned up six facts the issue does not state. Each was written into this
spec as a requirement; three are retired or reworded by the re-plan:

1. ~~`hc` often cannot be installed or run as the issue describes...~~ **Retired (CP5 re-plan
   2026-09-24).** There is nothing to install: the sandbox uses the HermitCrab DLL FieldWorks already
   ships. The remaining risk is narrower -- can the worker *load* that DLL -- and is handled by D7
   (health checks presence + `FileVersion` only; a load failure surfaces at first run, not at health
   time; see FR-004, FR-007, SC-002).
2. ~~Passing words by file does not remove quoting problems...~~ **Retired (CP5 re-plan
   2026-09-24).** Words reach the worker as JSON-lines protocol messages, never as a quoted line in a
   script file `hc` re-splits. An apostrophe, or any other character, needs no quoting (FR-013,
   retired).
3. ~~Expected-parse strings in `test` have a broken escape...~~ **Retired (CP5 re-plan 2026-09-24).**
   Expected parses are compared as structured `(form, gloss)` sequences in Python, never sent through
   a CLI argument parser, so the delimiter-escaping hazard does not exist (FR-027, reworded).
4. **`GenerateHCConfig` reports grammar load errors but still writes a configuration.** Unaffected --
   Generate mode still works exactly as designed (FR-008, FR-009, FR-010).
5. ~~The sandbox's engine may be a different HermitCrab version from FLEx's own...~~ **Retired (CP5
   re-plan 2026-09-24).** The sandbox worker loads the FieldWorks-bundled DLL itself, at whatever
   version is installed -- it cannot be a different engine, so there is no skew to warn about
   (FR-005, D7, reworded).
6. ~~A killed `hc` run loses buffered output.~~ **Retired (CP5 re-plan 2026-09-24).** There is no
   `hc` output file to buffer. A killed sandbox worker process's partial results are whatever the
   worker had already sent over its JSON-lines protocol before the kill (FR-020, reworded).

---

## Clarifications

### Session 2026-09-24

- Q: What should `parser_tool_missing`'s `install_hint` say for `hc`? → A: The literal command
  `dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool` comes first, unchanged. It is
  followed by one sentence naming the prerequisites: a .NET SDK to install the tool, and the .NET 10
  runtime to run `hc` 3.8 and later. No version is pinned. (Resolves former Q1; FR-007.)

**Still open (deferred at specify):**

Deferred to `/speckit.clarify`. Each question has an adopted default, and the spec is written to
that default.

- **Q2 -- where do corpus expectations come from?** **Default:** from a **baseline run**. Running a
  corpus with no expectations against the project's current grammar records every parse `hc`
  produces, as an assertion file the user owns and may edit. Expectations derived from human-approved
  analyses in the project are out of scope for CP5 (see Out of Scope). [NEEDS CLARIFICATION: is
  seeding from a baseline run enough for CP5, or must CP5 also derive expectations from the
  project's fully linked, human-approved analyses?]
- **Q3 -- what if `hc`'s HermitCrab version differs from the one FieldWorks bundles?** **Moot (CP5
  re-plan 2026-09-24, D7).** There is no separate `hc` install any more: the sandbox worker loads
  FieldWorks' own bundled HermitCrab DLL, the same one Try A Word uses. There is nothing to be
  skewed against, so the skew advisory is removed rather than answered. Retained here only so the
  original question is not silently lost.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Find out whether the sandbox can run, and what to install if it cannot (Priority: P1)

**Reworded (CP5 re-plan 2026-09-24, D7).** A linguist asks the assistant to test a grammar change
safely. Before anything runs, the health check reports whether the sandbox spine is ready. There is
no `hc` to find any more: readiness means the FieldWorks-bundled `SIL.Machine.Morphology.HermitCrab.dll`
is present (with a readable `FileVersion`) and `GenerateHCConfig.exe` is present. If either file is
missing, the message names it and points at repairing or reinstalling FieldWorks -- not at a `dotnet
tool install` command, since nothing is installed separately. Health does **not** attempt to load the
DLL or spawn anything (D7): a DLL that is present but fails to load is discovered only when a sandbox
run is actually attempted, not by health. When the spine is ready, the health check's guidance starts
naming the sandbox tool.

**Why this priority**: every other story depends on it, and on today's typical FLEx machine the
answer is "not ready" only when FieldWorks itself is missing or broken -- which is now the much
narrower and much rarer case than "no `hc` installed".

**Independent Test**: run the health check on two fixtures: no FieldWorks HermitCrab DLL found, and a
present DLL plus `GenerateHCConfig.exe`. Each gets the right status, component detail and hint. On
a third fixture, force the sandbox worker's first load to fail and confirm the failure surfaces as a
run-time `parser_job_failed` (`failure: engine_unavailable`), not as a health finding.

**Acceptance Scenarios**:

1. **Given** the FieldWorks-bundled HermitCrab DLL cannot be found, **When** health runs, **Then**
   `parser.sandbox.status` is `unavailable`, the DLL component reads not found, and the guidance
   names repairing/reinstalling FieldWorks. The guidance never names `flextools_parse_sandbox`.
2. ~~`hc` installed in the default dotnet tools folder but not on PATH~~ **Retired (CP5 re-plan
   2026-09-24).** There is no PATH-based tool discovery any more.
3. ~~An `hc` that exists but whose required runtime is missing~~ **Retired (CP5 re-plan 2026-09-24)
   / superseded by D7.** The analogous case -- the DLL is present but the worker fails to load it --
   is not a health finding at all; it surfaces on the first sandbox run as `parser_job_failed`
   (`failure: engine_unavailable`), never as `unavailable` from health.
4. **Given** the bundled HermitCrab DLL and `GenerateHCConfig.exe` are both present, **When** health
   runs, **Then** `parser.sandbox.status: ready`. The DLL's `FileVersion` and `GenerateHCConfig`'s
   version are reported. There is no second, independently-installed tool version to compare against
   (no skew warning; Q3 moot).
5. **Given** a caller invokes `flextools_parse_sandbox` while the bundled DLL cannot be found, **When**
   the call runs, **Then** it is refused with `parser_tool_missing` (component
   `fieldworks_hermitcrab`, `expected_path` naming `SIL.Machine.Morphology.HermitCrab.dll`), whose
   `install_hint` names repairing/reinstalling FieldWorks. No project copy is made and no worker process is spawned.

---

### User Story 2 - Parse words against the project's exported grammar, safely (Priority: P1)

**Reworded (CP5 re-plan 2026-09-24).** The linguist asks "what does the sandbox make of these
words?". The MCP makes a minimal copy of the project outside every project folder, generates a
HermitCrab configuration from the copy (reusing a cached one when nothing has changed), and hands the
resulting configuration path and the word list to a fresh **sandbox worker process** (`--sandbox`
mode of the existing parse worker), which loads the FieldWorks-bundled HermitCrab engine itself and
parses each word. It returns a summary on the fast path, or a run identifier for a long list. The
project copy (Generate mode's, not the worker's -- the worker never sees the project) is deleted
whatever happens. The results are stored as a normal run record, readable through the existing log,
status and diff tools, and are labelled as the sandbox's results, not the project's.

**Why this priority**: this is the spine itself. Everything else builds on it.

**Independent Test**: parse a small word list that includes non-Latin words, an apostrophe word, and
a word with a known failure. Check that the per-word results are correct, that the live project
folder is byte-identical afterwards, that no Generate-mode copy remains in the temporary area, and
that the sandbox worker process never imported flexicon or LCM (FR-046).

**Acceptance Scenarios**:

1. **Given** an HC project with a working sandbox, **When** the user parses three words, **Then**
   each word gets its own result: parsed with N analyses, not parsed, or error with a reason. The
   run summary's counts match the per-word results.
2. **Given** a word list in a non-Latin script, **When** it is parsed, **Then** no word reports "invalid
   segment at position 1" because of encoding. This is the section-4 regression, as a standing test
   -- now guarded by the JSON-lines protocol's own UTF-8 handling rather than by script quoting.
3. ~~A word containing `'`... reported as "cannot be expressed to hc"~~ **Retired (CP5 re-plan
   2026-09-24).** Words travel as JSON string values over the worker's existing protocol; no
   character needs quoting and no word can fail to be "expressible" any more (FR-013 retired).
4. **Given** any run, **When** it ends in success, failure, timeout or cancellation, **Then** the
   Generate-mode project copy no longer exists, and the live project's files are unchanged. The
   sandbox worker process itself never held a copy or opened the project to begin with.
5. **Given** the project's grammar has not changed since the last run, **When** the user parses again,
   **Then** the cached configuration is reused and generation does not run a second time.
6. **Given** the project is on XAmple, **When** the tool is called, **Then** it is refused with
   `parser_engine_mismatch` before any copy is made and before any sandbox worker is spawned (D6).
7. **Given** FLEx holds the project open, exclusively or shared, **When** the tool is called,
   **Then** the run still proceeds from a copy. When sharing is on, the result carries
   `staleness: "shared_mode_unverifiable"` and its note.

---

### User Story 3 - Rehearse a grammar edit in a named sandbox (Priority: P1)

The linguist wants to try a theory without touching the project. The assistant creates a named
sandbox from the project's current exported grammar and gets its file path. The user or assistant
edits the XML with ordinary file tools. The assistant then parses words or runs the corpus against
the sandbox and compares the result with a baseline run of the project's grammar. The sandbox is
theirs: no cache refresh, grammar change or pruning ever overwrites, invalidates or deletes it.

**Why this priority**: this is the reason the spine exists. It is the "rehearse" rung of the
confidence gradient.

**Independent Test**: create a sandbox, edit one environment, run the same words against the
project's config and against the sandbox, and diff the two runs. Then change the project's grammar
and refresh the cache. The sandbox file must be byte-identical.

**Acceptance Scenarios**:

1. **Given** a project, **When** the user creates sandbox `tighten-env`, **Then** a user-owned copy of
   the current exported configuration exists at a stated path outside every project folder,
   together with a note of which grammar state it came from.
2. **Given** an existing sandbox with that name, **When** creation is requested again, **Then** it
   is refused. The existing file is never overwritten.
3. **Given** an edited sandbox, **When** words are run against it, **Then** the run is recorded as a
   sandbox run of that named config and is diffable against a run of the project's config.
4. **Given** the project's grammar changed after the sandbox was made, **When** the sandbox is used,
   **Then** the result carries an advisory that the sandbox predates the project's current grammar.
   The sandbox is used exactly as it is.
5. **Given** a hand edit that breaks the XML, **When** the sandbox is run, **Then** the run fails --
   **reworded (CP5 re-plan 2026-09-24)**: with `XmlLanguageLoader.Load`'s own exception message
   (surfaced by the sandbox worker), not `hc`'s -- and nothing is reported as a parse result.

---

### User Story 4 - Run corpus assertions and learn which words regressed and which just became ambiguous (Priority: P2)

The linguist keeps a corpus of words with their expected parses. Running it against a
configuration reports each assertion as one of: **pass**; **regression** (an expected parse is
missing, including "no longer parses"); **new ambiguity** (every expected parse is still there, plus
extra ones); **changed** (both at once); or **error**. The corpus is seeded from a baseline run so
the linguist never hand-types expectations. **Reworded (CP5 re-plan 2026-09-24)**: there is no `hc`
text format to hand-type into any more; a corpus entry is a structured JSON list of `(form, gloss)`
pairs (data-model section 5), compared directly against the structured analyses the sandbox worker
returns.

**Why this priority**: it turns a one-off check into a repeatable test, and it separates the two
kinds of failure that a bare pass/fail verdict lumps together. It needs Stories 2 and 3 in place
first.

**Independent Test**: seed a corpus from a baseline run. Break one rule so a word loses its only
parse. Loosen another so a word gains a second parse. Run the corpus. Exactly one assertion is a
regression and one is a new ambiguity, and each names the missing or extra parse.

**Acceptance Scenarios**:

1. **Given** no corpus, **When** the user seeds one from a completed baseline run, **Then** a
   user-owned assertion file holds every word from that run with the parses it produced. A word that
   produced no parse is recorded as an expectation of "no parse".
2. **Given** a corpus, **When** it is run and a word's only expected parse is gone, **Then** that
   assertion is a `regression` and lists the missing parse.
3. **Given** a word keeps its expected parse and gains another, **When** the corpus runs,
   **Then** the assertion is `new_ambiguity`, lists the extra parse, and is **not** counted as a
   pass.
4. **Given** a corpus run, **When** it completes, **Then** its totals are the sums of the
   per-assertion classifications directly -- **reworded (CP5 re-plan 2026-09-24)**: there is no
   separate `hc` counter line to reconcile against; one process (the sandbox worker, via Python)
   computes both the analyses and the totals, so no disagreement between two sources is possible.
5. ~~An assertion whose form or gloss contains `\|`, `:` or `\`... reported as not expressible~~
   **Retired (CP5 re-plan 2026-09-24).** Expected parses are structured data, not text sent through a
   CLI argument parser, so no character is unexpressible any more. A malformed corpus entry (wrong
   shape, not a delimiter problem) is still reported as invalid and the rest of the corpus still runs
   (FR-027, reworded).

---

### User Story 5 - Diagnose a sandbox run afterwards (Priority: P2)

After a sandbox run the linguist or assistant can read what happened. The existing log tool now
fills the three sections it reserved for this spine: configuration generation (including grammar
load errors, Generate mode only), the sandbox worker's captured stdout/stderr (diagnostics and any
engine load errors), and the worker's structured per-word or per-assertion results, rendered for
reading. **Reworded (CP5 re-plan 2026-09-24)**: the latter two sections no longer hold `hc`'s console
transcript and printed result columns -- there is no `hc` -- but they keep their CP3 names
(`hc_stdout`, `hc_output`) and fill the same role for the worker's own output. A run that timed out,
was cancelled or failed still reports how far it got.

**Why this priority**: CP3 reserved these sections as "filled by CP5". Until CP5 fills them they
answer "not applicable", which is untrue for a sandbox run.

**Independent Test**: produce four sandbox runs: one that succeeds, one whose generation logged load
errors, one that timed out, and one against a broken sandbox. Read each section of each run. Every
section is either real content or a typed not-applicable answer. None is empty.

**Acceptance Scenarios**:

1. **Given** a sandbox run, **When** the log is read for `config_generation`, **Then** it shows the
   generator's captured output, with load errors itemised and counted.
2. **Given** an in-process run, **When** a sandbox section is requested, **Then** the existing typed
   not-applicable response is returned, unchanged.
3. **Given** a sandbox run that timed out after 40 of 100 words, **When** its status is read,
   **Then** it names 40 completed words and the word in flight, and the 40 results are readable.
4. **Given** a sandbox run and an in-process run of the same words, **When** they are diffed,
   **Then** the diff runs, and it says plainly that it is comparing two engines and grammar sources.

---

### User Story 6 - Keep disk use bounded (Priority: P3)

Long-running use of the sandbox does not fill the disk. Copies are always deleted. Cached
configurations are pruned. Runs obey the existing retention. A run that would not have room for its
copy is refused before copying.

**Why this priority**: this closes the confirmed leak, but it is housekeeping behind the stories
that deliver value.

**Independent Test**: run 30 sandbox runs, including killed ones. Afterwards no project copies
remain, at most three cached configurations per project remain, and run retention holds.

**Acceptance Scenarios**:

1. **Given** too little free space for twice the files to be copied, **When** a run is requested,
   **Then** it is refused before any copy, naming the space needed and the space free.
2. **Given** the server process is killed mid-run, **When** it next runs a sandbox job, **Then**
   any copy left by an MCP sandbox run is removed.

---

### Edge Cases

- ~~`hc` on disk but not on PATH.~~ **Retired (CP5 re-plan 2026-09-24).** There is no `hc` and no
  PATH-based discovery.
- ~~`hc` present but unable to start.~~ **Superseded by D7.** The analogous case is the bundled DLL
  failing to load in the sandbox worker; that is not a discovery-time check at all (see US1).
- ~~The detected `hc` is not HermitCrab's `hc`.~~ **Retired (CP5 re-plan 2026-09-24).** Nothing is
  discovered by name any more; the worker loads a specific, fully-qualified DLL path.
- ~~A slow or hanging `dotnet tool list -g`.~~ **Retired (CP5 re-plan 2026-09-24).** No `dotnet` tool
  listing is ever run.
- **Word forms.**
  - A word containing whitespace, `'`, `"`, or both quotes: unaffected by quoting concerns now (the
    protocol carries them as ordinary JSON strings), but still worth testing for encoding and
    normalisation.
  - ~~A word beginning with `-`, which `hc`'s option parser may read as an option~~ **Retired (CP5
    re-plan 2026-09-24).** There is no CLI option parser in the path any more.
  - A duplicate word.
  - A word that differs only in Unicode normalisation.
  - An empty list.
- **Grammar load errors during generation.** The configuration is written without the failed
  objects. This is the sandbox's version of "the grammar silently shrank". It is warned about with
  counts, never hidden, and never a refusal, because nothing is written.
- **`GenerateHCConfig` output conditions.**
  - Exit 0 with its help text, no configuration written.
  - Exit 1 with "The FieldWorks project is currently open in another application", because a lock
    marker was copied.
  - Exit 1 with "created with an older version of FLEx", because the project needs migration.
  - A crash with no message.
- **A copied lock marker.** Copying the project folder whole also copies its `.fwdata.lock`, which
  makes `GenerateHCConfig` report the copy as locked. The copy must leave it out.
- **Project folder size.** A Send/Receive project folder holds a Mercurial history, and linked media
  can be gigabytes. Copying the whole folder is wasteful, and the free-space check would refuse
  runs needlessly.
- **Copying mid-save.** FLEx may be saving `.fwdata` while it is copied. A copy that fails to load is
  reported as a generation failure, never as a grammar problem.
- **Shared-mode staleness.** With sharing on, `.fwdata` may not hold a peer's latest grammar edits
  (parent 7.3). The cache key cannot notice this.
- **A runaway word.** One word never finishes. The run timeout kills the sandbox worker process
  (**reworded, CP5 re-plan**: not a `hc` process tree, but the worker process launched for that run).
  Results already produced survive, and the word in flight is named.
- **Cancellation mid-word.** The sandbox worker process is killed. The cancelled state keeps the
  results produced so far.
- ~~Output that cannot be read unambiguously.~~ **Retired (CP5 re-plan 2026-09-24, FR-019
  reworded).** There are no printed columns to misread: each morph's form and gloss are read directly
  from the `Word`/`Morpheme` .NET objects, so this ambiguity class does not exist.
- **An empty morph.** A morph whose allomorph `Property` `ID` (FormID) is absent or `0` is skipped
  (FR-050 rule a) -- **reworded (CP5 re-plan correction 2026-09-24, D4 reversed)**: this is FLEx's
  own Try A Word display rule (`HCParser.GetMorphs`), read from the exported `Properties` via the
  validated `lcm-ids.json` id map, replicated rather than named as a gap. **Exception**: in a named
  sandbox only, a morph a user hand-added (so it has no `ID`) is the sole case this rule does not
  apply to -- it is emitted, flagged `user_added: true` (FR-050).
- **An empty gloss.** A morph with no gloss reads as `?` (`Morpheme.Gloss`, FR-050) -- unaffected in
  substance, only in mechanism (Python reads the .NET object's `Gloss`, not `hc`'s printed `?`).
- **A circumfix morph.** An `AffixProcessAllomorph` with no `ID2` whose form's morph type is
  circumfix appears twice in HermitCrab's own analysis. Both occurrences are emitted, as
  FLEx does; the first is remembered, and the second is emitted as the suffix portion, flagged
  `is_circumfix: true` (FR-050 rule b/c) (corrected 2026-09-24 against `HCParser.cs:347-374`: FLEx emits **both** occurrences -- the first is recorded *and* emitted, so the circumfix shows before and after what it attaches to) -- this is Try A Word's own display convention for the "Leipzig", two-sided circumfix case
  (LT-21447), not a bug to route around.
- **An unresolved id in the id map.** When `lcm-ids.json`'s validation finds an id referenced by the
  config that does not resolve to the expected LCM class, the whole mapping is marked invalid and
  the run fails as `parser_job_failed` (`failure: "id_map_invalid"`) before any word is parsed.
  Shaping is never silently skipped or applied against a partially-trusted map (FR-050).
- **An unexpected error from the sandbox worker.** An exception other than an `InvalidShapeException`
  (invalid segment) may leave no per-word result if it is unhandled. The word is reported as an error
  with no result, never as "not parsed".
- **Sandbox names.** A name that is empty, reserved, or contains path separators or `..` is refused.
- **Two sandbox jobs on one project.** Two jobs run concurrently, each with its own sandbox worker
  process; Generate mode's shared cache entry is still built at most once at a time.
- **A write completes during a sandbox job.** The job keeps its already-generated configuration and
  its already-loaded Morpher (D1: `release()` keeps the Morpher rather than reloading between
  words). The cache entry is invalidated for later jobs.
- **A sandbox-mode message that assumes a live project (D1).** `resolve`, `engine_check`,
  `resolve_scope`, a client-supplied `parser_parameters` override, `agent_probe`, any `filing_*`
  message, and `restricted_to` are all refused with a coded error in `--sandbox` mode; none is
  silently accepted or silently ignored (FR-049).

---

## Requirements *(mandatory)*

### Functional Requirements

**Tool discovery and health (H1)**

- **FR-001** (**Reworded, CP5 re-plan 2026-09-24**): Discovery MUST locate the FieldWorks-bundled
  `SIL.Machine.Morphology.HermitCrab.dll` and `GenerateHCConfig.exe` via the MCP's existing FieldWorks
  path resolution (`versioning.get_resolved_fieldworks_dir()`), and MUST record which FieldWorks
  installation it resolved to. There is no separate `hc` tool to discover, so the four-source
  fallback (override, PATH, dotnet tools folder, dotnet tool listing) and `HC_TOOL_PATH` no longer
  apply to Parse/Test. ~~The script MUST never assume `%LOCALAPPDATA%\HermitCrabTool\hc.dll`~~:
  moot, since no script-based `hc` invocation remains for Parse/Test.
- **FR-002** (**Reworded, CP5 re-plan 2026-09-24**): Neither the sandbox worker nor
  `hcparse.ps1` (Generate mode) MUST hard-code the FieldWorks folder. Both MUST receive the
  FieldWorks installation path, the bundled HermitCrab DLL path, and `GenerateHCConfig.exe`'s path
  from the MCP's existing resolution.
- **FR-003**: **Retired (CP5 re-plan 2026-09-24, D2).** There is no `hc` identity to confirm; the
  worker loads a specific, fully-qualified DLL path rather than discovering a program by name. The
  `hc -h` identity-probe machinery (`parser_probe.py`'s `HC_IDENTITY_PROBE_ARGS`, `HC_PROBE_MODULE`)
  is removed, along with its CP1 boundary carve-out (see D2, and `test_cp1_boundary.py`'s
  `TestHcIdentityProbeNarrowing`, flagged by the QC review as dead code once this lands).
- **FR-004** (**Reworded, CP5 re-plan 2026-09-24, D7**): Health MUST report only whether the bundled
  HermitCrab DLL is present at the resolved FieldWorks path, and whether its `FileVersion` can be
  read. It MUST NOT spawn a process or attempt to load the DLL to test startability (D7): a present
  DLL that later fails to load in the sandbox worker is not a health-time distinction. That failure
  MUST instead surface on the first sandbox run as `parser_job_failed` (`failure: engine_unavailable`).
  Both health states (present/absent) MUST use the existing two-state status.
- **FR-005** (**Reworded, CP5 re-plan 2026-09-24, D7**): Health MUST report two versions: the
  FieldWorks-bundled HermitCrab library's `FileVersion`, and `GenerateHCConfig`'s `FileVersion`. Every
  sandbox run MUST record the same two. ~~A difference between the two HermitCrab versions MUST
  produce a version-skew warning~~: **retired**. There is no independently-installed `hc` engine to be
  skewed against -- the sandbox worker loads the same DLL FieldWorks itself uses -- so the skew
  warning is removed rather than kept dormant (Q3 moot).
- **FR-006**: When the sandbox spine is `ready`, the health guidance MUST be allowed to name
  `flextools_parse_sandbox`. When it is `unavailable`, the guidance MUST never name it. This
  replaces the current "never named" rule. Unaffected by the re-plan except that "ready" is now
  FR-004's narrower condition.
- **FR-007** (**Reworded, CP5 re-plan 2026-09-24, D7**): The sandbox tool MUST refuse with
  `parser_tool_missing` before any copy is made and before any sandbox worker is spawned, when the
  bundled HermitCrab DLL or `GenerateHCConfig.exe` cannot be found. Its fields, in order, are
  `component`, `expected_path`, `install_hint`. ~~For `hc`, the `install_hint` MUST begin with
  `dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool`...~~ **retired**: nothing is
  separately installed. The `install_hint` for a missing bundled DLL MUST instead point at repairing
  or reinstalling FieldWorks, naming the expected FieldWorks install path. The component identifier
  is `fieldworks_hermitcrab` (replacing `hc`; `contracts/tools.md` section 4, `data-model.md`
  section 7), and `expected_path` is the full path of `SIL.Machine.Morphology.HermitCrab.dll`
  under the resolved FieldWorks folder. The `GenerateHCConfig.exe` component value is unchanged.

**Configuration generation (H5, H6, H7, S6)**

- **FR-008**: Generation MUST run against a copy of the project that holds only what the generator
  needs. The copy MUST leave out the project's lock marker, its version-control history, and
  linked media and backup folders. The copy MUST live outside every FieldWorks project folder.
- **FR-009**: The generator's full output MUST be captured to the run's `generate-config.log`. It
  MUST NOT be discarded. Generation MUST count as successful only when the generator exits 0, the
  configuration file exists and is non-empty, and the output contains the generator's
  "Writing completed." line. Anything else MUST fail as `parser_config_failed`, with its fields in
  order: `exit_code`, `stderr_tail`, `log_path`, `run_id`.
- **FR-010**: Grammar load errors that the generator reports while still writing a configuration
  MUST be itemised and counted in the run record and summary, as a warning that the exported grammar
  may lack those objects. They MUST NOT be a refusal.
- **FR-011**: The copied project MUST be deleted when the run ends, on every path: success, failure,
  timeout, cancellation and exception. Before its first sandbox job, a server MUST remove copies left
  behind by MCP sandbox runs that died. A regression test MUST prove no copy remains after each
  terminal path.
- **FR-012**: Before copying, the run MUST check that free space at the copy's destination is at
  least twice the size of the files to be copied. If it is not, the run MUST be refused before any
  copy is made, stating the space needed and the space free.

**Running the sandbox worker (H2, H4, H8, H9, H11; retitled from "Running `hc`", CP5 re-plan 2026-09-24)**

- **FR-013**: **Retired (CP5 re-plan 2026-09-24).** Words no longer reach anything through a script
  file or a command line. They travel as ordinary JSON string values in the worker's existing
  JSON-lines protocol (the same transport CP2b's in-process spine already uses). There is no line
  splitter to quote around, so quoting, BOM and "not expressible" all cease to apply: every word that
  can be represented as a JSON string can be sent.
- **FR-014** (**Reworded, CP5 re-plan 2026-09-24**): Word lists MUST be read as UTF-8 and MUST be
  split on `[,\s]+` where a list arrives as one string, before being sent to the sandbox worker as a
  JSON list. This existing behaviour (H11) MUST be preserved verbatim; only the destination of the
  resulting list changes (a worker message, not an `hc` script file).
- **FR-015**: Word lists MUST be de-duplicated after NFC normalisation, ordered by descending
  occurrence count where counts are known and then alphabetically, and cut to `limit` after
  ordering. The run MUST record whether the limit cut the list. Unaffected by the re-plan.
- **FR-016** (**Reworded, CP5 re-plan 2026-09-24**): Outcomes MUST be decided from the sandbox
  worker's structured per-word response, never from a subprocess exit code -- there is no longer an
  `hc` process whose exit code could be trusted or distrusted. A `ParseWord` call that raises
  `InvalidShapeException` yields `invalid_segment` (with `.Position`, 0-based per the domain review).
  A worker process that crashes, fails to start, or fails to load the configuration (including
  `XmlLanguageLoader.Load` raising) yields a failed run reported with the load exception's message,
  and no word gets a parse result -- the direct successor of the old "exit code -1" case.
- **FR-017** (**Reworded, CP5 re-plan 2026-09-24**): ~~A parse run MUST read the parse counters
  (`stats -p`). A corpus run MUST read the test counters (`stats -t`). When the counters disagree
  with the per-word results...~~ **retired as stated**: there is no separate `hc` counter line to
  read, because the same process that produces each per-word analysis also tallies the run's totals.
  Instead: the run's summary counts (parsed / not parsed / error, or pass / regression / new_ambiguity
  / changed / error for a corpus) MUST be the direct sum of the per-word or per-assertion
  classifications. A test MUST prove this invariant holds for every terminal run, since a bug that
  breaks it can no longer be caught by comparing against an independent counter.
- **FR-018**: Every word sent MUST produce exactly one result. The possible results are: parsed with
  its analyses, not parsed, invalid segment (with position), error without output, and not reached.
  ~~not expressible~~ is retired (FR-013). A word that was sent but produced no output MUST NOT be
  reported as "not parsed". Unaffected otherwise by the re-plan.
- **FR-019** (**Reworded, CP5 re-plan 2026-09-24**): ~~A parse whose printed columns cannot be read
  unambiguously MUST be flagged as such...~~ **retired as stated; there is nothing left to
  misread.** Each morph's form and gloss MUST be read directly from the sandbox worker's structured
  per-morph data (the `Word`/`Morpheme` .NET objects via `MorphInfo`-equivalent extraction, D4), never
  reconstructed from printed, padded text columns. This removes the entire class of column-alignment
  ambiguity FR-019 used to guard against.
- **FR-020** (**Reworded, CP5 re-plan 2026-09-24**): Each sandbox worker invocation MUST run under a
  timeout. On timeout the sandbox worker process MUST be killed (there is no `hc` process tree
  beneath it to kill separately -- the worker calls the engine in-process). The run MUST end in the
  existing `parser_timeout` state, with `timeout_seconds`, `words_completed`, `run_id`, `hint`. Every
  result the worker had already sent over its JSON-lines protocol before the kill MUST be preserved,
  and the word in flight MUST be named. ~~Results written to the output file are buffered, and a
  timeout kill discards them~~ no longer applies: there is no buffered output file for Parse/Test.
- **FR-021** (**Narrowed to Generate mode, CP5 re-plan 2026-09-24**): Everything `hcparse.ps1`'s
  Generate mode prints to the console MUST be ASCII-only. Non-ASCII data MUST travel only in UTF-8
  files. This no longer applies to Parse/Test, which have no script console output; the sandbox
  worker's own stdout/stderr are handled per FR-046 (process isolation) and the existing worker
  logging conventions, not this ASCII rule.

**The script itself (H3, H12; narrowed to Generate mode, CP5 re-plan 2026-09-24)**

- **FR-022** (**Narrowed to Generate mode**): The hardened script MUST ship inside the package as
  `hcparse.ps1`, and MUST be run as `powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass
  -File`, never through string evaluation. It now has exactly one mode, Generate; Parse and Test are
  retired from the script (FR-013, FR-016) and live in the sandbox worker instead.
- **FR-023** (**Narrowed to Generate mode**): The script's Generate-mode invocation MUST write a
  machine-readable `run.json` (or equivalent hand-off) giving its inputs, exit code and timings. The
  MCP MUST fold that file into the existing run record. It MUST NOT scrape the script's console
  prose. Parse and Test results are no longer folded from a script hand-off file at all: they arrive
  over the sandbox worker's JSON-lines protocol directly (QC review, "FR-023 needs redrafting to
  cover Generate mode only").
- **FR-024** (**Narrowed to Generate mode**): The script MUST declare `$script:HCPARSE_VERSION`. That
  value MUST be bumped on every change in the script's (Generate-mode) behaviour, and it MUST be part
  of the cache key. It no longer needs to reflect Parse/Test behaviour, since that code moved to the
  sandbox worker and is versioned with the rest of `src/flextoolsmcp`.

**Three lifecycles (H6, H10; parent 7.1)**

- **FR-025** (**Reworded, CP5 re-plan 2026-09-24**): The design MUST keep three artifacts under
  distinct names, and each MUST have its own lifecycle:
  - **the project copy**: always deleted (FR-011);
  - **the cached configuration**: managed, invalidatable, pruned to 3 per project, least recently
    used first. It is keyed on the `.fwdata` path, size and modification time, on the generator's
    path, size and modification time, and on `$script:HCPARSE_VERSION`;
  - **a user-owned sandbox configuration**: kept until the user removes it. No cache operation may
    ever overwrite, invalidate or delete it.

  Added by the re-plan (D3): the cache entry's `key.json` also holds `hc_parameters`, the project's
  `ParserParameters/HC` settings read at generation time (FR-047). `hc_parameters` MUST NOT be part
  of the cache key -- unlike the grammar itself, the Morpher parameters are applied at run time, not
  baked into the exported XML, so a parameters-only change (or none) never needs regeneration.
- **FR-026**: The cache MUST be invalidated for a project whenever a write run against that project
  completes. That includes `run_module` writes and CP4 filing runs. The script's `-ConfigOut` MUST
  target only the cache. No code path may point it at a sandbox path. Unaffected by the re-plan.

**Sandboxes and corpus assertions**

- **FR-027** (**Reworded, CP5 re-plan 2026-09-24**): ~~Before any expected parse is sent, it MUST be
  checked. An assertion whose form or gloss contains `|`, `:`, `\`, a quote character or whitespace
  MUST be reported as not expressible, and MUST NOT be sent.~~ **retired as stated**: expected parses
  are structured `(form, gloss)` values compared directly against the sandbox worker's structured
  analyses (never sent through a CLI argument parser), so no character makes an assertion
  inexpressible. Instead: before any expected parse is compared, it MUST be validated against the
  corpus schema (data-model section 5). An assertion whose shape is malformed (a non-string form or
  gloss, a missing key, or an expected-parse entry with zero morphs) MUST be reported as invalid and
  MUST NOT be compared. The rest of the corpus MUST still run.
- **FR-028**: A user MUST be able to create a named sandbox from the project's current exported
  configuration. The result MUST return its path and record where it came from (cache key and time).
  Creating over an existing name MUST be refused. Names MUST be validated so that they cannot leave
  the sandbox area.
- **FR-029**: A run against a sandbox that predates the project's current grammar MUST carry an
  advisory saying so. It MUST NOT alter the sandbox.
- **FR-030**: A user MUST be able to seed a corpus assertion file from a completed sandbox run. The
  file records every word with the exact parses the run produced, and "no parse" for words that
  produced none (Q2). The file MUST be user-owned under the same lifecycle as a sandbox.
- **FR-031** (**Reworded, CP5 re-plan 2026-09-24**): Each assertion MUST be classified by comparing
  the recorded expected analyses against the sandbox worker's returned analyses for that word
  directly, as sets of `(form, gloss)` sequences (~~from `hc`'s expected-parse and actual-parse
  sections, not from its pass/fail line~~: there is no `hc` pass/fail line, but the same shape of
  comparison holds):
  - `pass`: every expected parse appeared and nothing else did;
  - `regression`: at least one expected parse is missing, and nothing unexpected appeared;
  - `new_ambiguity`: every expected parse appeared, plus unexpected ones;
  - `changed`: expected parses are missing and unexpected ones appeared;
  - `error`: invalid segment, an invalid corpus entry (FR-027), timeout or no output. ~~not
    expressible~~ is retired (FR-027).
- **FR-032**: The classifications MUST map onto the existing diff buckets. Expected-but-missing maps
  to `broken`, and unexpected maps to `changed`. `new_ambiguity` MUST NOT be counted as a pass or as
  unchanged.
- **FR-033**: When a word is expected to produce no parse and now parses, the assertion MUST be
  classified `new_ambiguity`. It MUST be labelled as "now parses". The word MUST NOT be called fixed.

**The tool and the existing parse surface**

- **FR-034**: `flextools_parse_sandbox` MUST be registered as read-only with respect to the live
  database. The first line of its description MUST state the spine. The description MUST say that
  the tool works on an exported copy, never touches the live project, and welcomes speculative
  edits.
- **FR-035** (**Note, CP5 re-plan 2026-09-24**): The tool MUST use the existing job model: a run
  identifier, the fast path, status polling, and cooperative cancellation (kill the sandbox worker
  process -- there is no separate `hc` process tree beneath it any more). It MUST NOT add a second
  execution path. A per-run `SandboxClient` builds a fresh sandbox worker process per run, outside
  `WorkerPool` (F-13; the pool keys by `(project, role)`, and concurrent sandbox jobs need
  independent engine instances).
- **FR-036** (**Reworded, CP5 re-plan 2026-09-24, D6**): When a project is involved, the engine check
  MUST run before any copy **and before any sandbox worker process is spawned**. It stays
  server-side, in `server/sandbox/engine.py`, reading the live `.fwdata` as a stream (never through
  LCM, per the existing Assumptions bullet). It MUST refuse with `parser_engine_mismatch` when the
  project is not on HermitCrab. The check MUST NOT require opening the live project when its lock is
  held by someone else.
- **FR-037**: Sandbox runs MUST be stored in the existing run-record format and location. They add a
  field recording the run's spine and config source (project cache or named sandbox), and they
  store the sandbox files beside it. All changes MUST be additive, per the CP3 compatibility rules.
  Unaffected by the re-plan.
- **FR-038** (**Reworded, CP5 re-plan 2026-09-24**): The log tool MUST fill `config_generation`,
  `hc_stdout` and `hc_output` for sandbox runs; the section names are kept from CP3's artifact
  contract, but what fills them changes: `config_generation` is unaffected (Generate mode's captured
  output); `hc_stdout` now holds the sandbox worker process's own captured stdout/stderr (diagnostics
  and, on a load failure, the engine's exception text); `hc_output` now holds the worker's structured
  per-word or per-assertion results, rendered for reading, rather than `hc`'s printed columns. The
  tool MUST decide applicability from the run's recorded spine, not from the section name alone. For
  in-process runs it MUST keep returning the existing typed not-applicable response. No section may
  be empty.
- **FR-039**: The diff tool MUST accept sandbox runs. When it compares runs from different spines,
  engines or config sources, it MUST say so in the result.
- **FR-040**: When sharing is on or the project is held by another program, a sandbox run MUST
  report `staleness: "shared_mode_unverifiable"` with its note, and a diff MUST downgrade `no_change`
  to `no_change_unverifiable`.
- **FR-041**: Every sandbox response MUST carry a `next_step` with a mandatory `est_cost`. When a
  run fails, times out or reports load errors, it SHOULD point at the static grammar scan.
- **FR-042**: No sandbox artifact may be written inside any FieldWorks project folder. That covers
  the copy, cache, sandboxes, corpora and run files.
- **FR-043**: The spine MUST NOT open the live project for writing, write to it, or change any
  file in its folder. A test MUST prove the live project folder is byte-identical across a run.
- **FR-044**: Words, parser output and sandbox XML MUST be treated as data, never as instructions,
  in every response.

**Verification**

- **FR-045** (**Reworded, CP5 re-plan 2026-09-24**): CP5 MUST be verified live against an HC project,
  using the sandbox worker's `--sandbox` mode against FieldWorks' own bundled HermitCrab DLL (no
  external `hc` install is needed or possible any more). The live run MUST cover:
  - a non-Latin word list;
  - an apostrophe word (kept as a test case for orthography reasons, though it is no longer testing a
    quoting hazard -- FR-013 is retired);
  - a baseline, then a deliberate sandbox break, then a corpus showing one regression and one new
    ambiguity;
  - a timeout with results preserved;
  - no copy left behind (Generate mode's project copy; the sandbox worker never held one);
  - the sandbox worker's process isolation (FR-046): no LCM/flexicon assembly loaded, no project
    opened, no file written.

  The evidence MUST record the two versions from FR-005 (bundled HermitCrab DLL, `GenerateHCConfig`),
  not the three the original design called for.

**Process isolation (D1, D2; new, CP5 re-plan 2026-09-24)**

- **FR-046**: The sandbox worker process MUST NOT import flexicon or any LCM module, and MUST NOT
  open any FieldWorks project. This MUST be provable, not merely asserted:
  - the worker's `assemblies` message MUST list only the HermitCrab/SIL.Machine assemblies (and
    their ordinary .NET dependencies) actually loaded via the `AssemblyResolve` handler, and MUST
    never list an LCM assembly;
  - `sys.modules` inside the sandbox worker process MUST contain no `flexicon` or `SIL.LCModel`
    entry;
  - FR-043's byte-identity test MUST pass with the sandbox worker running throughout the scenario.
  - In `--sandbox` mode, `Morpher` and `XmlLanguageLoader.Load` join the guarded vocabulary via a
    pinned `CP5_SANDBOX_ENGINE_ALLOWLIST`, scoped to `server/parse/worker_main.py` only (D2). This
    is the CP1 boundary's replacement for the retired `hc -h` identity-probe carve-out (FR-003).

**Engine parameters (D3; new, CP5 re-plan 2026-09-24)**

- **FR-047**: When parsing or testing against a configuration sourced from a project (a cache-run
  config, or a named sandbox run against its originating project), the worker MUST apply the
  project's `ParserParameters/HC` settings to the loaded `Morpher`, mapped as:
  - `DelReapps` -> `DeletionReapplications`;
  - `MaxRoots` -> `MaxStemCount`;
  - `MergeAnalyses` -> `MergeEquivalentAnalyses`;
  - `GuessRoots` -> the `guessRoot` argument of `ParseWord`;
  - `MaxAlternatives` -> the `Morpher`'s `MaxAlternatives` property, applied **only** when the loaded
    `Morpher` exposes it (absent in HermitCrab 3.8.2, the version FieldWorks 9.3.11 bundles; present
    from 3.9.1, per the domain review's `v3.8.2`-tag verification). A `Morpher` that lacks the
    property MUST NOT raise; the setting is simply not applied, and this MUST be visible in
    `parameters_applied`.

  Missing project values MUST fall back to FLEx's own defaults: `DelReapps=0`, `MaxRoots=2`,
  `MergeAnalyses=true`, `GuessRoots=true`, `MaxAlternatives=0`. The source of these values, in
  priority order, MUST be:
  1. `hc_parameters` recorded in the cache entry's `key.json` (FR-025), for a cache-sourced config;
  2. a live stream-read of the project's `.fwdata` (FR-036/D6), for a named-sandbox run made against
     its originating project;
  3. the FLEx defaults, otherwise (including a named sandbox with no recorded originating project).

  Every sandbox run record MUST carry `parser_parameters` (the values used), `parameters_applied`
  (which of the five were actually set on the `Morpher`, since `MaxAlternatives` may be absent), and
  `parameters_source` (one of `cache`, `live_project`, `flex_defaults`).

**Guessed roots (D5; new, CP5 re-plan 2026-09-24)**

- **FR-048**: Each morph in a returned analysis MUST carry a `guessed` flag, read directly from
  `word.GetAllomorph(morph).Guessed` on the .NET `Word` object -- the reliable signal the domain
  review identified, not the fragile "gloss equals form" heuristic. Corpus classification
  (FR-031..FR-033) MUST NOT special-case guessed morphs: a guessed morph compares like any other
  morph, contributing to `pass` / `regression` / `new_ambiguity` / `changed` the same way (D5: "no
  special-casing in corpus classification").

**Try A Word shaping (D4; new, CP5 re-plan correction 2026-09-24 -- D4 reversed)**

- **FR-050**: The sandbox worker MUST replicate FLEx's own Try A Word morph-shaping rules
  (`HCParser.GetMorphs`, `C:\Github\fieldworks\Src\LexText\ParserCore\HCParser.cs:332-440`), not
  treat them as gaps. Per morph of each analysis, in order:
  a. a morph whose allomorph `Property` `ID` (FormID) is absent or `0` MUST be skipped;
  b. an `AffixProcessAllomorph` with no `ID2` whose form's morph type is circumfix
     (`kguidMorphCircumfix`) MUST have its first occurrence recorded **and emitted**; its second
     occurrence MUST also be emitted, as the suffix portion, flagged `is_circumfix: true` (LT-21447,
     the two-sided "Leipzig" circumfix case) (corrected 2026-09-24 against `HCParser.cs:347-374`: FLEx emits **both** occurrences -- the first is recorded *and* emitted, so the circumfix shows before and after what it attaches to);
  c. a morpheme already seen in the analysis MUST be emitted again only if it is the
     APR-circumfix suffix portion from (b) (keyed on `ID`) or has `ID2 > 0` (a two-part circumfix,
     keyed on `ID2`); otherwise it MUST be skipped;
  d. the whole analysis MUST be dropped if a form ID, the morpheme's MSA `ID`, or a positive
     `InflTypeID` does not resolve in the validated id map below;
  and, as `GetMorphs` does last, an emitted infix or infixing interfix MUST be placed before the
  morph it interrupts (inserted ahead of the last emitted morph). `is_circumfix` is also `true`
  for a morph emitted through `ID2 > 0` (FLEx's own `MorphInfo.IsCircumfix = formID2 > 0`).

  During Generate mode, the MCP MUST write a sidecar `lcm-ids.json` into the cache entry beside
  `hc-config.xml` (server-side, a plain stream read of the byte-identical `work/<run_id>/` copy,
  never through LCM). For every id referenced by the exported config it MUST record `{guid, class,
  morph_type_guid}` (`morph_type_guid` present only for `MoForm` subclasses), and, for a `MoForm`,
  its `form` text in the project's default vernacular writing system (**added at T110,
  2026-09-25**): a shaped morph MUST show that allomorph form, as FLEx's `MorphInfo.Form` does,
  and only a guessed morph (FLEx's `GuessedString`) or one whose form has no such text shows the
  surface string the engine matched. It MUST validate that
  every `FormID`/`ID2` resolves to a `MoForm` subclass, every MSA `ID` to a `MoMorphSynAnalysis`
  subclass, and every `InflTypeID` to a `LexEntryInflType`. Any id that fails to resolve MUST mark
  the whole mapping invalid, and the run MUST then fail as `parser_job_failed` (`failure:
  "id_map_invalid"`) rather than silently skip or partially apply shaping. The sandbox worker MUST
  receive the sidecar's path (`--id-map <path>`) and apply rules a-d against it; "resolves" in rule
  (d) means "present in this validated map". `key.json` MUST record the sidecar's path as part of
  the cache entry, and creating a named sandbox MUST copy the sidecar the same way it copies the
  rest of the cache entry's inputs (FR-028).

  **Who refuses an invalid map.** The server-side check order owns the refusal: a config source
  whose sidecar is recorded `valid: false` MUST be refused as `parser_job_failed` (`failure:
  "id_map_invalid"`) before any sandbox worker is spawned (`contracts/tools.md` section 3). The
  worker MUST also re-check the map before its first `parse` and fail the same way if the map is
  invalid or cannot be parsed. That second check is a backstop only; it is not the primary gate.

  **A config source with no sidecar (older than the sidecar).** A named sandbox created before this
  requirement existed has no `lcm-ids.json`. (Cache entries cannot be in this state: the
  `HCPARSE_VERSION` bump changes every cache key, so every cache entry is rebuilt with a sidecar.)
  For such a source, and only for it, the worker MUST run with no id map and emit every morph
  unshaped. This MUST be disclosed, never silent: the run record MUST carry
  `meta.sandbox.shaping.id_map: "absent"`, and the response MUST carry an advisory saying Try A
  Word shaping was not applied and that re-creating the sandbox from a current cache entry will
  restore it. A sidecar that exists but is invalid is never treated as absent. It always fails as
  above. The allowed `shaping.id_map` values are `"valid"` and `"absent"`.

  **Exception, named sandboxes only**: a morpheme or allomorph a user hand-adds to a named
  sandbox's `hc-config.xml` has no `ID`. Rule (a) MUST NOT apply to it: it MUST be emitted, flagged
  `user_added: true`, and rule (d) MUST NOT drop an analysis on its account. A morph whose `ID` is
  present but absent from the validated map MUST still follow rule (d).

**Sandbox-mode message refusals (D1; new, CP5 re-plan 2026-09-24)**

- **FR-049**: In `--sandbox` mode, the worker MUST refuse, with a coded error (never a silent no-op
  and never a silent success), any message that assumes a live project or lexicon: `resolve`,
  `engine_check`, `resolve_scope`, a client-supplied `parser_parameters` override, `agent_probe`, any
  `filing_*` message, and `restricted_to`. Internal hooks that other, shared code paths call
  unconditionally MUST instead return neutral values rather than raising, so that shared machinery
  keeps working against a sandbox worker without special-casing it:
  - `preflight()` is a no-op that reports success;
  - `active_engine()` returns `None`;
  - `eligible_entries()` returns `{"known": False, "entries": []}`.

  `release()` MUST keep the loaded `Morpher` in memory rather than releasing it between words (it is
  the same load-once, reuse-per-run behaviour the in-process spine's `_release_if_idle` does not
  give the real backend -- see #223, D8, out of scope for CP5 -- but the sandbox backend gets it
  deliberately, since reloading a `Morpher` per word would cost the ~190 ms first-parse load on every
  single word).

### Key Entities

- **Project copy**: a temporary, minimal copy of a project, made only so the configuration can be
  generated. It is always deleted.
- **Cached configuration**: a configuration generated from a project and keyed on the grammar
  source, the generator and the script version. The system owns it and replaces it freely.
- **Sandbox**: a named, user-owned copy of a configuration that the user may edit. It records its
  origin. Cache logic never touches it.
- **Corpus (assertion file)**: a user-owned list of words, each with its expected parses (form and
  gloss per morph) or "no parse". It is usually seeded from a baseline run.
- **Sandbox run**: one job against one configuration source, stored as a normal run record. It
  records its spine, config source, the **two** engine versions (**reworded, CP5 re-plan
  2026-09-24**: the bundled HermitCrab DLL and `GenerateHCConfig`, not three -- there is no
  separately-installed `hc`), the applied parser parameters and their source (FR-047), generation
  warnings and per-word or per-assertion results.
- **Assertion result**: one corpus word's classification (FR-031), with the missing and unexpected
  parses listed.
- **Id map (`lcm-ids.json`)**: a sidecar written into a cache entry during Generate mode, mapping
  every id (`ID`/`ID2`/`InflTypeID`) referenced by the exported grammar to its LCM class (and morph
  type, for `MoForm` subclasses). Validated at generation time; an unresolved id fails the mapping
  as a whole, and the run then fails as `parser_job_failed` (`failure: "id_map_invalid"`) rather
  than silently skipping FLEx's own Try A Word shaping rules (FR-050). Copied into a named sandbox
  at creation, the same way the rest of the cache entry's inputs are.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After 100% of tested sandbox runs, whatever their terminal state, no project copy
  remains, and the live project folder is byte-identical to before the run.
- **SC-002** (**Reworded, CP5 re-plan 2026-09-24, D7**): On a machine where the FieldWorks-bundled
  HermitCrab DLL cannot be found, health names the correct cause in 100% of runs, and the sandbox
  tool is never proposed. ~~On one with an `hc` that cannot start~~: retired, there is no such
  machine state to test for any more. A DLL that is present but fails to load is **not** detected by
  health (D7); it surfaces on the first sandbox run as `parser_job_failed` (`failure:
  engine_unavailable`), and that path is exercised by a fixture/live test, not a health test.
- **SC-003** (**Reworded, CP5 re-plan 2026-09-24 -- the domain review's parity definition, cycle 1,
  section "Proposed SC-003 parity definition"**): Sandbox parity with Try A Word, at the same engine
  version (now guaranteed, not merely checked, since the sandbox always loads FieldWorks' own bundled
  DLL):
  (a) the same parsed / not-parsed / invalid-segment outcome, and the same set of `(form, gloss)`
  sequences, for words whose analyses involve no circumfix and only ids that resolve in the live
  project;
  (b) guessed-root analyses (FR-048) are flagged via `Guessed` and compared as their own category,
  never lumped with non-guessed analyses;
  (c) the Morpher settings (FR-047/D3: `DelReapps`, `MaxRoots`->`MaxStemCount`, `MergeAnalyses`,
  `GuessRoots`, and `MaxAlternatives` where the engine has it) are taken from the same project's
  `ParserParameters`, with FLEx's defaults when absent;
  (d) **Reworded (D4 reversed, maintainer correction 2026-09-24).** Circumfix doubling,
  `FormID==0` morph-skipping, and dropping an analysis whose `IMoForm`/MSA/`ILexEntryInflType` ids
  do not resolve are **not** gaps: they are FLEx's own Try A Word display rules
  (`HCParser.GetMorphs`, FR-050) and the sandbox replicates them via the validated `lcm-ids.json`
  id map. The only two remaining named differences, disclosed rather than silently passed or
  failed, are: glosses come from the exported `Morpheme.Gloss`, not the live senses Try A Word
  shows; and, in a named sandbox only, a user-added morph (no `ID`) is emitted with `user_added:
  true` rather than skipped, by design (FR-050). A named sandbox older than the sidecar
  (`shaping.id_map: "absent"`, FR-050) is outside parity: it is reported as unshaped, and it is
  neither passed nor failed on SC-003.
  ~~A non-Latin word list and an apostrophe word give the same per-word results... at matching
  HermitCrab versions~~ is folded into (a): version-matching is now automatic, not a live-verification
  variable.
- **SC-004**: Every word sent produces exactly one result. Zero words disappear silently.
- **SC-005**: In a corpus with one deliberate regression and one deliberate new ambiguity, exactly
  those two assertions are classified as such, and each lists the right parse.
- **SC-006**: A second run against an unchanged grammar skips generation, and in the maintainer's
  test it runs at least twice as fast as a cold run.
- **SC-007**: No cache operation changes a sandbox or corpus file. Their bytes are identical across
  cache refresh, invalidation and pruning.
- **SC-008**: A run that times out preserves 100% of the results produced before the kill, and names
  the word in flight.
- **SC-009**: The three sandbox log sections return real content for 100% of sandbox runs, and never
  return an empty section.
- **SC-010**: The existing test suite, the read-only boundary tests and the error-model field-order
  tests remain green.

## Assumptions

- **The run-record format is CP3's, not the parent's old listing.** CP3's artifact contract corrected
  the parent's listing (`run.json`, `hc-output.txt`, and so on). `run.json` survives only as the
  script's hand-off file, which the MCP folds into the record (FR-023).
- **The bundled script is canonical, for Generate mode (narrowed, CP5 re-plan 2026-09-24).** The
  contributed root-level `hcparse.ps1` is replaced by the packaged, hardened copy. Its history stays
  in git, and its section-4 lessons are carried forward verbatim (FR-014) for the word-list splitting
  behaviour that survives the re-plan. The script's Parse/Test modes are retired; that behaviour now
  lives in `server/parse/worker_main.py`'s `--sandbox` mode.
- **Sandbox and corpus files live under `~/.flextoolsmcp`,** beside the existing run records, cache
  and backups. They are never under a project folder.
- **The engine check reads the live file as a stream, before any copy, never through LCM -- and now,
  before any sandbox worker is spawned too (updated, CP5 re-plan 2026-09-24, D6).** It
  reads `ActiveParser` from the live `.fwdata` as a plain read-only file stream (shared
  read/write), so it runs before any copy, as FR-036 requires, and never opens the project. On
  non-shared projects an LCM open takes the lock, and FLEx may hold it; a plain file read takes no
  lock and works while FLEx has the project open (research R-02). `ActiveParser` is not an element
  of its own in the `.fwdata` file. It sits inside the XML text of the `MoMorphData` object's
  `ParserParameters` string, so it is read in two steps: stream to the first `MoMorphData` object,
  then parse that string's inner XML. An absent or unreadable value (including a read error that
  persists after one retry) counts as XAmple, so the check fails safe (CP2 domain review). This check
  lives in `server/sandbox/engine.py` and stays server-side, never inside the sandbox worker process
  itself (D6) -- it is what decides whether a worker gets spawned at all.
- ~~Console output survives a kill; file output does not.~~ **Superseded (CP5 re-plan 2026-09-24).**
  This was about `hc`'s own console-vs-file buffering, which no longer exists for Parse/Test. FR-020
  now needs partial results to come from whatever the sandbox worker has already sent over its
  JSON-lines protocol before the kill, which is a property of that protocol (already relied on by the
  in-process spine), not of a subprocess's stream buffering.
- ~~`hc` is run without its continue-on-load-error flag.~~ **Superseded (CP5 re-plan 2026-09-24).**
  There is no `hc` continue-on-load-error flag in this design. The analogous fact: a configuration the
  worker cannot fully load (`XmlLanguageLoader.Load` raising) fails loudly with that exception's
  message (US3 scenario 5, reworded). The generator's load errors happen earlier and are handled by
  FR-010, unaffected.
- **No full-folder copy.** Which files the generator needs, such as the `.fwdata` and the
  writing-system store, is decided in planning and verified live. The free-space check measures what
  is actually copied. Unaffected by the re-plan (Generate mode).
- **Engine versions (reworded, CP5 re-plan 2026-09-24):** FieldWorks 9.3.11 bundles HermitCrab 3.8.2.
  ~~`hc` 3.8.x needs .NET 10, and 3.7.x runs on .NET 8.~~ Moot: there is no separately-installed `hc`
  to need a .NET SDK/runtime pairing at all. The sandbox worker runs under whatever runtime the MCP
  server itself already runs under, loading the bundled DLL via pythonnet netfx.
- **`GenerateHCConfig` initialises the SLDR at start-up.** Whether that needs network access is
  unverified. If it hangs offline, the generation timeout covers it. Unaffected by the re-plan
  (Generate mode).
- **The engine check follows the existing preflight.** It is `check_active_parser`, and its refusal
  shape is `ParserEngineMismatchDetail`. Unaffected by the re-plan.
- **New (CP5 re-plan 2026-09-24, D2): the CP1 boundary's guarded vocabulary grows, scoped
  narrowly.** `Morpher` and `XmlLanguageLoader.Load` are added to a pinned
  `CP5_SANDBOX_ENGINE_ALLOWLIST` that applies only inside `server/parse/worker_main.py`'s
  `--sandbox` mode. This replaces the originally-planned `hc -h` identity-probe carve-out (former
  FR-003, R-04), which is removed along with the `hc` discovery it existed for.
- **New (CP5 re-plan correction 2026-09-24, D4 reversed, FR-050).** The `lcm-ids.json` sidecar is
  written server-side by the same plain stream read of the byte-identical `work/<run_id>/` copy the
  engine check already uses (R-02), never through LCM. Its HVO-equals-`rt`-document-order reading is
  an observed LCM XML-backend load-order behaviour, not a documented contract (research.md D4), so
  it is guarded by validation rather than trusted outright: an id that does not resolve to the
  expected class fails the run as `parser_job_failed` (`failure: "id_map_invalid"`), never a
  silent mis-shape.

## Out of Scope

- Filing anything from a sandbox run. This is semantically impossible (parent 1.1), and no path to
  it may exist.
- Editing grammar XML for the user, or suggesting rule edits (parent 18). CP5 gives the path, and the
  user or assistant edits the file with ordinary tools.
- Deriving corpus expectations from the project's human-approved analyses (Q2 default). This is
  deferred.
- ~~Installing `hc`, the .NET SDK or a runtime on the user's behalf.~~ **Retired (CP5 re-plan
  2026-09-24).** There is nothing separate to install; the sandbox uses FieldWorks' own bundled
  engine. The analogous out-of-scope item is: repairing or reinstalling a broken FieldWorks
  installation on the user's behalf. CP5 names this in the `parser_tool_missing` hint, never performs
  it.
- XAmple, and anything other than Windows.
- Contract-catalog prose, CHANGELOG, telemetry and user documentation beyond the contract rows. These
  belong to CP6 (#167).

## Verbatim Constraints

**Re-plan note (2026-09-24)**: constraints below marked *(Generate mode only)* still describe
`hcparse.ps1` exactly as designed. Constraints marked **Retired** described the stand-alone `hc` CLI
and no longer apply; they are kept, struck through, so the retirement is visible rather than a silent
deletion. New constraints from the re-plan are marked **New**.

- Tool: `flextools_parse_sandbox`. Unaffected.
- Script *(Generate mode only)*: `hcparse.ps1`; version constant `$script:HCPARSE_VERSION`; parameter
  `-ConfigOut`; generator log `generate-config.log`; hand-off file `run.json`. ~~parameter
  `-TimeoutSeconds`~~: that parameter belonged to the script's Parse/Test invocation, retired; the
  sandbox worker's own timeout is a Python-side setting, not a script parameter.
- Invocation *(Generate mode only)*: `powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass
  -File`.
- **New**: sandbox worker mode: `python -m flextoolsmcp.server.parse.worker_main --sandbox` (the
  existing `worker_main.py` entry point, same `ParseWorker` loop and JSON-lines protocol, with a
  `_SandboxBackend`).
- Health: `parser.sandbox.status: ready` / `unavailable`; components ~~`hc`~~,
  `fieldworks_hermitcrab` (**New**, replaces `hc`; its `expected_path` is the
  `SIL.Machine.Morphology.HermitCrab.dll` path), `GenerateHCConfig.exe` (unaffected). The same
  `component` values are used by `parser_tool_missing`.
- ~~Install hint: `dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool`.~~ **Retired.**
  **New** install hint: points at repairing/reinstalling the FieldWorks installation.
- ~~Override: `HC_TOOL_PATH` (existing).~~ **Retired.** There is no external `hc` path to override;
  the FieldWorks installation path resolution (`versioning.get_resolved_fieldworks_dir()`) is used
  instead, unchanged from the rest of the MCP.
- ~~`hc` commands: `parse`, `test`, `stats -p`, `stats -t`; test output sections `Expected parses:`
  and `Actual parses:`.~~ **Retired.** There is no `hc` CLI and no such commands or output sections.
  The sandbox worker's JSON-lines protocol carries structured messages instead (see
  `contracts/bridge.md` / worker protocol docs for the existing message shapes it reuses).
- Error codes and fields, in this order:
  - `parser_tool_missing`: `component`, `expected_path`, `install_hint` (existing shape; `component`
    values and `install_hint` text change per above)
  - `parser_config_failed`: `exit_code`, `stderr_tail`, `log_path`, `run_id` (new; Generate mode only,
    unaffected by the re-plan)
  - `parser_timeout`: `timeout_seconds`, `words_completed`, `run_id`, `hint` (existing; now applies to
    the sandbox worker's own timeout, not `hc`'s)
  - `parser_engine_mismatch` (existing, unchanged)
  - **New**: `parser_job_failed` (`failure: engine_unavailable`), for a bundled DLL that is present
    but fails to load in the sandbox worker (D7) -- the run-time counterpart to health's
    presence-only check.
- Log sections: `config_generation`, `hc_stdout`, `hc_output`. Names unaffected; contents reworded
  per FR-038 (`hc_stdout` -> the sandbox worker's own captured stdout/stderr; `hc_output` -> the
  worker's structured results, rendered).
- Staleness: `shared_mode_unverifiable`; diff verdict `no_change_unverifiable`. Unaffected.
- The leak location named in the issue: `%TEMP%`. Unaffected (Generate mode's copy).
- Contract version stays `tool-responses/1.0`. Unaffected.
- **New**: the guarded-vocabulary constant `CP5_SANDBOX_ENGINE_ALLOWLIST` (D2), scoped to
  `server/parse/worker_main.py`, permitting `Morpher` and `XmlLanguageLoader.Load` in `--sandbox`
  mode only.
- **New**: run-record fields `parser_parameters`, `parameters_applied`, `parameters_source` (values
  `cache` / `live_project` / `flex_defaults`) (FR-047/D3), and per-morph `guessed` (FR-048/D5).
- **New (D4 reversed, CP5 re-plan correction 2026-09-24)**: sidecar `lcm-ids.json`, part of the
  cache entry and copied into a named sandbox at creation (FR-050); per-morph `is_circumfix` and
  `user_added` (FR-050), alongside `guessed` (FR-048/D5); `parser_job_failed` failure value
  `id_map_invalid` (FR-050), alongside `engine_unavailable` (D7); run-record field
  `meta.sandbox.shaping.id_map` (`"valid"` / `"absent"`) and advisory `shaping_not_applied`
  (FR-050, a config source older than the sidecar).
