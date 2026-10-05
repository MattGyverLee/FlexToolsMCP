# Feature Specification: Run on the mcp 2.x line only, and validate tool input before the session gate

**Feature Branch**: `spec/mcp-modernization` (worktree `.claude/worktrees/mcp-modernization`)

**Created**: 2026-10-04

**Status**: Draft

**Input**: User description: "Feature dir: specs/mcp2-only/ (stay on the current branch spec/mcp-modernization; do NOT create a new branch). Scope: PR-B1 and PR-B2 from the umbrella roadmap specs/mcp-modernization/contracts.md (issue #369). PR-B1: require mcp>=2.3,<3 only, retire mcp_compat.py, serve via low-level mcp.server.Server with thin (ctx, params) adapters, and keep three behaviors as production code (jsonschema input pre-validation before the cold-session gate, escaped exceptions -> isError results with verbatim "Error: {exc}" text, list[TextContent] -> CallToolResult wrapping). No wire change, measured against the PR-0 goldens. Dual-era tests plus a required stdio subprocess handshake per era; CI matrix is lowest-direct (mcp 2.3.0, pydantic 2.12, anyio 4.9) + latest, crossed with legacy/auto protocol eras; drop the 1.27.0 downgrade steps; update every hard-coded version-range site. Release R1 = 3.0.0. PR-B2: Pydantic-first validation with new precedence (unknown_tool/invalid_input ahead of session_not_initialized), is_error for invalid_input, internal_error fallback, contract tool-responses/1.1. Depends on PR-0 (separate PR from main). Declare jsonschema explicitly (Q16 default yes)."

**Tier**: Full - per `.specify/memory/constitution.md`. Checkpoint 2 crosses
the published tool-response contract (new error precedence, `tool-responses/1.1`),
and checkpoint 1 changes a runtime dependency's major version, so the release
is a major bump. `plan.md` and `tasks.md` follow this spec.

**Touches a write path?**: No. Neither checkpoint changes what any tool writes
to a FieldWorks project. They change how requests reach the tool handlers and
how rejections are reported. The write gates (`write_enabled`, confirmation,
the exclusive-access gate) MUST behave identically before and after; this is
proven by the PR-0 wire goldens and the cold-session regression tests, not by
a live-LCM write. One manual read-path smoke on **Sena 3** precedes the R1
tag (never Claude-Swahili).

**Parent**: `specs/mcp-modernization/contracts.md`, the umbrella roadmap for
issue #369. Its section 0 (corrections to the issue), section 3 (PR-B1) and
section 4 (PR-B2) are the engineering detail behind this spec, with file and
line anchors. Where they disagree, this spec governs scope and the umbrella
governs the cross-phase invariants.

**Predecessor**: `specs/mcp2-compat/` (#83), the 1.x/2.x compatibility shim.
Checkpoint 1 retires that shim and merges its README and deferred-issue notes
into `specs/_archive/mcp2-compat/`, which already exists.

**Prerequisite (outside this spec)**: PR-0, the wire-level baseline. It lands
on `main` as a separate PR while the server still runs on mcp 1.x. It captures
the `tools/list` surface and the `tools/call` results (text and error flag) for
every tool that runs without FieldWorks, plus the shared rejection paths. This
branch is rebased onto it before checkpoint 1 is implemented. Without that
baseline, "no wire change" in checkpoint 1 cannot be measured.

**Decisions already made** (maintainer, 2026-10-04):

| Question (umbrella section 11) | Answer |
|---|---|
| Q1: Pydantic-first validation with the new precedence | Yes, in checkpoint 2, after the parity audit |
| Q2: CI floor | Keep a lower-bound cell (the whole lowest-direct dependency set) plus latest |
| Q13: version of R1, the release that drops mcp 1.x | **3.0.0** |
| Q16: declare `jsonschema` explicitly | Yes (default accepted) |
| PR-0 placement | Separate PR from `main`, merged first |

**Out of scope**: structured output and `outputSchema` (`specs/structured-output/`),
`status`/`_contract` normalization and the error flag on other hard errors
(PR-E), progress notifications, the registry manifest, and the tool-surface
security work. Removing tracebacks from `internal_error` is Q15, decided in
Phase 5 for both sites at once; checkpoint 2 only makes the escaped-exception
path use the same fields the caught path already uses.

## Checkpoints

| Checkpoint | Roadmap PR | Release | Contract | Wire change |
|---|---|---|---|---|
| CP1 | PR-B1: mcp 2.x only, shim retired | R1 = 3.0.0 | `tool-responses/1.0` | None |
| CP2 | PR-B2: validation before the session gate | R2 (next minor after R1) | `tool-responses/1.1` | Yes, documented |

CP1 and CP2 ship as separate PRs and separate releases, so a revert of either
is clean. CP2 does not start until CP1 has merged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The server keeps working for every client after the dependency move (Priority: P1)

A linguist uses FlexToolsMCP through their AI assistant (Claude Code, Copilot,
Gemini CLI). Some of those assistants speak the new sessionless protocol
(2026-07-28); others still speak an older one (2025-11-25 or earlier). After
upgrading to R1, every assistant connects, lists the same tools, and gets the
same answers and the same rejections it got before, byte for byte in the text.

**Why this priority**: The mcp 1.x line is maintenance-only. Staying on it
freezes the server out of the current protocol era. But a dependency move that
silently changes a tool's answer, or lets a cold-session write slip past the
session gate, is worse than not moving. Nothing else in issue #369 can start
until this lands safely.

**Independent Test**: Run the PR-0 wire goldens against the CP1 build, once
with a client that negotiates the legacy era and once with one that negotiates
the current era. Every golden matches: the text and the error flag, including
the invalid-input, unknown-tool, cold-session and injected-exception paths.

**Acceptance Scenarios**:

1. **Given** a client that negotiates the 2026-07-28 era, **When** it connects
   over stdio, **Then** it sees the server name, a non-empty server version, the
   server instructions, and exactly as many tools as the server defines.
2. **Given** a client that negotiates the 2025-11-25 era, **When** it connects
   over stdio, **Then** it sees the same tools, with the same descriptions,
   annotations and input schemas, as the PR-0 snapshot.
3. **Given** either era, **When** the client calls a read-only tool with valid
   arguments, **Then** the result text equals the PR-0 golden.
4. **Given** either era, **When** the client sends arguments that break the
   tool's input schema, **Then** the call is rejected with the error flag set and
   the same "Input validation error: ..." text as before, and the session state
   is untouched.
5. **Given** a cold session (no `flextools_start` yet), **When** the client calls
   a non-read-only tool such as `run_module`, **Then** the call is refused with
   `session_not_initialized` exactly as before.
6. **Given** a failure in the code that runs around a tool handler (session
   setup, handler lookup, logging), **When** it raises, **Then** the client gets a
   tool result with the error flag set and the text `Error: <message>`, not a
   protocol-level error, in both eras.
7. **Given** a client still on an mcp 1.x SDK, **When** it connects over stdio,
   **Then** the server negotiates an era that client understands and serves it.

---

### User Story 2 - Installs and upgrades fail loudly and point to the fix (Priority: P1)

A user installs or upgrades FlexToolsMCP with `uvx`, `uv tool`, or `pip`. If
their environment would resolve an mcp 1.x, or a too-old pydantic or anyio, the
install refuses rather than producing a server that breaks on the first call.
If the server is started anyway with the wrong mcp, the startup message names
the required range and gives the exact command that fixes it.

**Why this priority**: The audience is mostly non-programmers. A confusing
attribute error thirty calls in is a support ticket; a clear refusal at install
or startup is not (constitution principle V).

**Independent Test**: Try to resolve the package together with `mcp<2.3`; the
resolver refuses. Start the server module with an mcp 1.x on the path; the
startup message names `mcp>=2.3,<3` and the install command.

**Acceptance Scenarios**:

1. **Given** an environment pinned to mcp 1.x, **When** the user installs R1,
   **Then** the resolver reports the conflict instead of installing.
2. **Given** a user who wants to stay on mcp 1.x, **When** they read the README
   and release notes, **Then** they find that 2.15.x is the last compatible
   release and how to pin to it.
3. **Given** a `uvx` user with a cached older build, **When** they read the
   release notes, **Then** they are told to run `uvx flextools-mcp@latest` (or
   `uv tool upgrade flextools-mcp`).
4. **Given** the maintainer's editable `uv tool` install, **When** CP1 merges,
   **Then** RELEASING.md gives a post-merge sequence (stop clients, reinstall,
   check health, then pull) that does not break the running server.

---

### User Story 3 - CI proves both eras and both ends of the dependency range (Priority: P2)

A maintainer or contributor opens a PR. CI tests the server at the lowest
dependency versions the package declares and at the latest ones, and in each
cell tests both protocol eras, in-process and over a real stdio subprocess.
The release workflow repeats the stdio handshake against the built wheel in a
clean environment before anything is published.

**Why this priority**: The floor is a promise. Without a lower-bound cell, a
floor regression ships unnoticed until a user with older packages hits it.
In-process tests alone do not exercise the real current-era stdio path.

**Independent Test**: Read the CI run for a PR that touches nothing else: the
lower-bound and latest cells both run, each runs the legacy and current-era
in-process tests, and the stdio subprocess test is a required check.

**Acceptance Scenarios**:

1. **Given** a PR, **When** CI runs, **Then** one cell resolves the lowest
   declared versions of the direct dependencies (mcp 2.3.0, pydantic 2.12,
   anyio 4.9) and one resolves the latest, and both pass.
2. **Given** a PR, **When** CI runs, **Then** the stdio subprocess handshake runs
   in both eras on Windows as a required check, and nothing reaches stdout
   before the protocol stream opens.
3. **Given** a release tag, **When** the publish workflow runs, **Then** it
   installs the built wheel in a fresh environment and completes a stdio
   handshake in both eras through the installed console script before
   publishing.
4. **Given** the old matrix, **When** CP1 lands, **Then** no CI or publish step
   downgrades to mcp 1.27.0 any more.

---

### User Story 4 - Bad calls are rejected for what they are, even on a cold session (Priority: P2)

An assistant calls a tool that does not exist, or calls a real tool with
malformed arguments, before the session has been started. Today the session
gate answers first, so the assistant is told to start a session, starts one,
retries, and only then learns the real problem. After CP2, the assistant is
told the real problem first: the tool name is unknown (with the nearest valid
names) or the arguments are invalid (with what was wrong), in the same
structured error envelope every other rejection uses, with the error flag set.

**Why this priority**: It removes a wasted round trip and a misleading answer,
and it makes invalid input machine-readable like every other error code
(constitution principle V). It is a contract change, so it waits for CP1 and
ships on its own.

**Independent Test**: On a cold session, call an unknown tool, then a
non-read-only tool with bad arguments. Each returns its own error code with the
error flag set, and the session is still cold afterwards.

**Acceptance Scenarios**:

1. **Given** a cold session, **When** the client calls a tool name that does not
   exist, **Then** it gets `unknown_tool` (not `session_not_initialized`), with
   the error flag set.
2. **Given** a cold session, **When** the client calls a non-read-only tool with
   arguments that fail validation, **Then** it gets `invalid_input` (not
   `session_not_initialized`), with the error flag set.
3. **Given** any session state, **When** the arguments fail validation, **Then**
   the response is the documented `invalid_input` envelope with a contract stamp,
   not the plain "Input validation error" text.
4. **Given** a cold session, **When** either rejection above happens, **Then** the
   session is still cold: no project was opened and nothing was auto-started.
5. **Given** a cold session, **When** the client calls a non-read-only tool with
   valid arguments, **Then** it still gets `session_not_initialized`, unchanged.
6. **Given** a failure in the code around a handler, **When** it raises, **Then**
   the client gets an `internal_error` envelope with the same fields a handler
   failure already produces, with the error flag set.
7. **Given** any response, **When** the client reads the contract stamp, **Then**
   it says `tool-responses/1.1`, and TOOL-CONTRACT.md documents the new
   precedence.

---

### User Story 5 - Validation verdicts do not drift when the validator changes (Priority: P3)

CP2 replaces the schema-based pre-check with the tools' own input models. A
maintainer needs to know, for every tool, whether any input that was accepted
before is now rejected, or the other way round, and every such difference must
be intentional and written down.

**Why this priority**: The two validators can disagree (extra keys, string to
number coercion, missing required fields, tools whose models allow extra keys).
Unaudited drift would turn into confusing rejections for users.

**Independent Test**: A parametrized audit runs every tool against a fixed set
of bad inputs under both validators and lists every verdict that differs; each
listed difference has a CHANGELOG entry.

**Acceptance Scenarios**:

1. **Given** the bad-input set (extra key, wrong type that could coerce, missing
   required field), **When** the audit runs over every tool, **Then** it reports
   each tool whose verdict differs between the old and new validator.
2. **Given** a reported difference, **When** CP2 merges, **Then** the CHANGELOG
   names it as an intended behavior change.

### Edge Cases

- A tool handler returns a mid-call input request (the current era's
  multi-round-trip result) instead of content: it passes through to the client
  unchanged, not wrapped.
- A client negotiates 2024-11-05 or 2025-03-26: it gets text results only, which
  is what it gets today. Nothing in this spec adds structured output.
- A failure is raised while the session is being configured, before any handler
  runs: CP1 returns the `Error: <message>` text with the error flag; CP2 returns
  `internal_error`. In neither case does it become a protocol-level error or
  crash the stdio loop.
- The installed SDK reports an empty server version by default: the server
  still reports its own package version.
- A cold read-only call auto-initializes the session today: that behavior is
  unchanged in both checkpoints.
- An unknown tool name on a cold session in CP1: still `session_not_initialized`
  (behavior verbatim); it changes only in CP2.
- `flextools_start` accepts extra keys by design: the CP2 audit tests the
  session-independent tools separately so this is not reported as drift.
- The stdio test environment must not trigger an index refresh or an update or
  workspace check, or it times out or writes to stdout early.
- The Python floor stays 3.10: mcp 2.3.0 declares `Requires-Python >=3.10`
  (checked on PyPI 2026-10-04), so the py3.10 CI cells remain.
- Python 3.14 needs a higher anyio floor than 3.12; the declared floor carries
  the version marker if the packaging tools support it.

## Requirements *(mandatory)*

### Functional Requirements

**CP1 - mcp 2.x only, behavior verbatim**

- **FR-001**: The package MUST declare `mcp>=2.3.0,<3`, `pydantic>=2.12`, and
  `anyio>=4.9` (higher on Python 3.14 where required), in `pyproject.toml` and
  identically in `requirements.txt`. An mcp 1.x MUST be unsatisfiable.
- **FR-002**: The package MUST declare `jsonschema` as an explicit dependency,
  because it is imported directly and will no longer arrive through the shim.
- **FR-003**: The server MUST register its tools through one path on the SDK's
  low-level server, with thin adapters between the SDK's request shape and the
  existing `list_tools` and `call_tool` functions. It MUST NOT move to the
  decorator-based framework (`docs/TODO.md`, "Do NOT migrate to FastMCP").
- **FR-004**: The compatibility shim module MUST be deleted, and no production
  or test code may read mcp type fields by their camelCase names. A guard test
  MUST enforce this. Constructor keyword arguments are exempt, because the SDK
  accepts both spellings. The shim's remaining helpers (the read-only annotation
  check, the version resolver, the schema reader) are replaced by direct
  snake_case reads or move with the adapter; none survives as a 1.x/2.x branch.
- **FR-005**: Before the session gate, the adapter MUST validate arguments
  against the tool's input schema exactly as the shim does today, returning the
  error flag and the same "Input validation error: ..." text. The check stays
  fail-open, as today: a tool with no input schema, or a missing validator, lets
  the call through to the handler.
- **FR-006**: An exception raised outside a handler but inside a tool call MUST
  become a tool result with the error flag set and the text `Error: <message>`,
  in both eras, and MUST be logged with its traceback to the operations log.
- **FR-007**: A handler's list of text content MUST be wrapped in a tool result;
  a mid-call input-request result MUST pass through unchanged.
- **FR-008**: The server MUST report its own package version and its
  instructions to every client, in both eras.
- **FR-009**: Over stdio, the server MUST serve clients that negotiate the
  2026-07-28 era and clients that negotiate the 2025-11-25 era, and MUST answer
  `server/discover`.
- **FR-010**: Every PR-0 wire golden MUST pass unchanged in both eras: tool list,
  result text, and error flag.
- **FR-011**: When started with an unsupported mcp, the server MUST say which
  range is required and give the exact install command, instead of the old
  1.x/2.x guess.
- **FR-012**: Every place that states the supported mcp range MUST be updated
  to `>=2.3,<3`: packaging, test guards, the startup hint and its test, the
  dependency canary (whose `<2` is already stale), workflow comments,
  RELEASING.md, `docs/TODO.md`, CLAUDE.md, the agent init profile, and the
  server's source comments and its no-package import fallback. References to
  `specs/mcp2-compat/` in the canary script and workflow MUST be repointed to
  `specs/_archive/mcp2-compat/`.
- **FR-013**: CI MUST run a lower-bound cell (the whole lowest-direct dependency
  set) and a latest cell, each covering both eras in process, and a stdio
  subprocess test in both eras as a required check on Windows. The mcp 1.27.0
  downgrade steps MUST be removed.
- **FR-014**: The publish workflow MUST complete a stdio handshake in both eras
  against the built wheel's console script in a fresh environment before
  publishing.
- **FR-015**: R1 MUST be released as **3.0.0**. Its CHANGELOG entry MUST say that
  mcp 2.3+ is required and that 2.15.x is the last release that runs on mcp 1.x,
  under a Breaking heading.
- **FR-016**: The README and release notes MUST tell `uvx` and `uv tool` users
  how to get the new build, and tell pip users in shared environments how to
  stay on 2.15.x. RELEASING.md MUST gain a post-merge sequence for the
  maintainer's editable install. The dev-environment install command in the
  test fail-fast message and in CLAUDE.md MUST be the `uv pip install` form,
  because the venv has no pip.
- **FR-017**: `specs/mcp2-compat/` MUST be merged into the existing
  `specs/_archive/mcp2-compat/` (marking its resolved drafts), not moved over it.

**CP2 - validation before the session gate**

- **FR-018**: Tool lookup and validation against the tool's own input model
  MUST run before the session gate. The schema pre-check from FR-005 MUST then
  be removed.
- **FR-019**: A call to an unknown tool MUST return `unknown_tool`, and a call
  with invalid arguments MUST return `invalid_input`, whatever the session
  state, ahead of `session_not_initialized`.
- **FR-020**: Invalid input MUST be reported as the documented `invalid_input`
  envelope, not as plain text, keeping its documented fields (`tool`,
  `received_arguments`). Echoing the caller's own arguments back is acceptable;
  PR-I1 lints it.
- **FR-021**: Results carrying `invalid_input`, `unknown_tool`, `internal_error`
  or `session_not_initialized` MUST set the error flag. The classifier that
  decides this MUST be shared code that PR-E can reuse.
- **FR-022**: The escaped-exception path from FR-006 MUST return an
  `internal_error` envelope with the same fields the in-handler path already
  uses, so the two look alike.
- **FR-023**: A rejection under FR-019 MUST leave a cold session cold.
- **FR-024**: The contract MUST move to `tool-responses/1.1`. TOOL-CONTRACT.md
  MUST document the new precedence, and the PR-0 goldens for the changed paths
  MUST be regenerated in the same change.
- **FR-025**: A verdict-parity audit MUST compare the old and new validators
  across every tool and a fixed bad-input set, and every difference MUST be
  recorded in the CHANGELOG as intended.

### Key Entities

- **Wire golden**: a normalized record of what a client sees for one request
  (tool list entry, or a call's text and error flag), captured on mcp 1.x by
  PR-0. CP1 must match it; CP2 changes only the goldens for the paths it
  documents.
- **Protocol era**: the protocol revision a client and the server agree on:
  the current sessionless 2026-07-28, or the legacy 2025-11-25 (and older,
  text-only eras).
- **Rejection precedence**: the order in which the server checks a call (tool
  exists, arguments valid, session ready) and so which error code a bad call
  gets.
- **Contract version**: the `tool-responses/*` stamp on every response; minor
  bumps are additive or documented behavior changes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the PR-0 wire goldens match under CP1, in both eras.
- **SC-002**: In both eras, a client connected over stdio lists every tool and
  gets a correct answer from a read-only call, measured in CI on every PR and
  in the publish smoke on every release.
- **SC-003**: Zero code paths in the shipped package still depend on mcp 1.x,
  shown by the deleted shim and a clean guard test.
- **SC-004**: An attempt to install R1 alongside an mcp 1.x fails at resolve
  time in 100% of cases, and starting the server with the wrong mcp prints the
  fix in one message.
- **SC-005**: After CP2, a cold-session call to an unknown tool or with bad
  arguments gets its real error on the first try: zero extra round trips
  through `flextools_start`.
- **SC-006**: Every tool's validation verdict change is listed: the audit's
  difference count equals the number of CHANGELOG entries for it.
- **SC-007**: The maintainer's live server is never broken by this work: it is
  developed in the worktree, and the post-merge reinstall sequence brings the
  server back healthy on the first try.

## Assumptions

- The SDK floor is mcp 2.3.0, the version the umbrella's corrections were
  verified against (dual-era negotiation, the request shapes, the absence of
  built-in input validation). The main checkout's venv still has mcp 1.30, so
  the plan's research step MUST re-confirm these facts in a throwaway 2.3.0
  environment before design is fixed.
- The stdio subprocess test also runs on the Linux smoke job, since it needs no
  FieldWorks; it is required only on Windows.
- PR-0 lands on `main` first, and this branch rebases onto it before CP1 code
  starts. This spec and its plan can be written before then.
- No index refresh is needed: neither checkpoint changes the API indexes, so the
  release-order rule (release pyflexicon first) does not apply unless an
  unrelated refresh lands in the same window.
- The decorator-based framework is rejected for good, for the reasons recorded
  in the project memory and `docs/TODO.md`; this spec does not reopen it.
- Tracebacks stay in `internal_error` as the current contract says, until Q15 is
  decided in Phase 5.
- R2 is a minor release (3.1.0) because the CP2 contract change is a documented
  minor bump.
