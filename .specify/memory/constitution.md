<!--
SYNC IMPACT REPORT
Version change: (none) -> 1.0.0
Rationale: Initial ratification. No prior constitution existed; `.specify/memory/`
was absent and only the unfilled template was present. All content below is
derived from rules already enforced in this repository (CI config, pre-commit
hooks, runtime gates, `.specify/extensions.yml` pipeline hooks, CONTRIBUTING.md,
SECURITY.md, docs/TOOL-CONTRACT.md, docs/VERSIONING.md, RELEASING.md,
docs/FLEXTOOLS-STYLE-GUIDE.md, docs/RALPH-CAMPAIGN.md) rather than newly invented.

Principles defined (7):
  I.   Safety-First Write Path (NON-NEGOTIABLE)
  II.  Discovery Over Memory
  III. Self-Contained, Regenerable Extraction
  IV.  Append-Only Versioned Contracts
  V.   Errors That Teach
  VI.  One Module, One Source of Truth
  VII. Windows-First, No Cross-Platform Shims

Sections added:
  - Additional Constraints (platform, dependencies, packaging, security posture)
  - Development Workflow & Quality Gates (spec tiers, pipeline order, CI gates,
    PR requirements, commit conventions, campaign stop conditions)
  - Governance

Sections removed: none (template placeholders replaced in place).

Templates requiring updates:
  [OK] .specify/memory/constitution.md - written.
  [OK] .specify/templates/plan-template.md - "Constitution Check" gate replaced
       the placeholder with eight explicit per-principle checks.
  [OK] .specify/templates/spec-template.md - added Tier and write-path header
       fields implementing the two-tier policy below.
  [OK] .specify/templates/tasks-template.md - added a Constitution gate
       obligations block (pattern audit, live-LCM verification, CHANGELOG /
       index / golden regeneration) to the Polish phase.
  [OK] .specify/extensions.yml - already encodes the crew gates; no change
       required, it is the machine-readable form of this document.

Deferred / follow-up TODOs:
  - `specs/parser-check-cp2b/reviews/cycle3-qc.md` cites "Constitution QG3".
    This document describes the quality gates but does not assign them QG
    numbers (per the ratification decision to keep 7 principles without a
    numbered gate register). Either correct that citation or add a numbered
    gate register in a future MINOR amendment.
  - `CLAUDE.md` references `docs/DECISIONS.md`, `docs/PROGRESS.md`, and
    `docs/TASKS.md`, none of which exist. Architectural decision history has no
    home; this constitution is currently the closest thing to one.
  - `specs/` naming is not uniform (`spec.md` vs `SPEC.md`, checkpoint specs
    nested in a parent vs sibling directories). The two-tier policy below is
    authoritative; existing directories were not renamed.
-->

# FlexToolsMCP Constitution

FlexToolsMCP exists to make FieldWorks automation accessible to people who are
linguists first and programmers second. Everything below follows from that: the
user's language data is irreplaceable, the user cannot be expected to audit
generated code line by line, and therefore the system - not the user - carries
the burden of being careful.

## Core Principles

### I. Safety-First Write Path (NON-NEGOTIABLE)

A FieldWorks project is a linguist's life's work and there is no undo outside
the system. Every write MUST descend a ladder of independent gates, and no
single gate may be load-bearing:

- **Read-only by default.** `write_enabled` defaults to `False` at both session
  start and per-call. Writes require opting in twice; silence is never consent.
- **Guarded mutations.** Every database mutation in generated or user-supplied
  code MUST sit inside an `if modifyAllowed:` branch. Unguarded mutations are a
  critical defect and MUST be refused at validation time, before execution.
- **Backup before the first write.** A pre-write backup MUST be attempted before
  the first mutating run per session and project. Backup is best-effort and MUST
  NOT raise: a backup failure may degrade the response but must never itself
  destroy a run. Restore stays manual and deliberate.
- **Explicit confirmation.** A script certified as mutating, run with writes
  enabled and without confirmation, MUST be refused before anything executes -
  no lock taken, no subprocess spawned.
- **Dry run precedes write.** Read-only execution is the expected rehearsal for
  every write. Skipping it is the documented path to data corruption.
- **Rollback is reviewed, never automatic.** Undo returns the operation to be
  undone; it does not silently reverse it.
- **Gates never relax.** Provenance, caller assertions, or convenience flags MAY
  skip discovery checks but MUST NEVER relax a write-safety or casting check.
  Write-enabled runs reject casting issues at every severity; read-only runs MAY
  proceed on warnings.
- **No unattended destructive writes.** When a live destructive write is
  required and no human is watching, the run MUST stop and escalate rather than
  proceed.

These are SAFETY properties, not SECURITY boundaries. They protect an honest
user from an honest mistake. They are not designed to resist adversarial input,
and this distinction MUST be stated plainly wherever they are documented.

### II. Discovery Over Memory

The assistant's training memory is not a source of truth about the LibLCM,
FlexLibs, or Flexicon APIs; the indexes are. Modules MUST be assembled from
indexed building blocks that were actually looked up, and execution MUST be
refused when no API discovery has occurred. Every method name in a finished
module MUST trace back to a discovery step the user can audit. An intentional
override MAY exist as an escape hatch, but the default MUST make coding from
memory structurally impossible rather than merely discouraged.

Cross-flavor differences MUST be surfaced explicitly as declared gaps. A
capability that is missing in one flavor is reported, never silently absent.

### III. Self-Contained, Regenerable Extraction

All API documentation MUST be extracted from source by static analysis - AST for
Python, reflection for .NET - with no dependency on an external service. The
index MUST be fully regenerable and therefore auditable and diffable.

Index refresh is all-or-nothing: because reverse mapping and pattern extraction
cross-link LibLCM, FlexLibs, and Flexicon entries to one another, scanning one
library in isolation produces a half-enriched index. There MUST be no
per-library refresh flag. Regenerated indexes are written to a user-writable
overlay, never into the installed package.

Index artifacts are versioned per library and coexist; older versions are
retained rather than overwritten, and a missing version self-heals via a full
refresh. When a required toolchain is unavailable, extraction MUST degrade
gracefully and keep the shipped index rather than failing the whole refresh.

### IV. Append-Only Versioned Contracts

Every tool response MUST carry a contract version stamp. Within a major contract
version, response keys and error-code strings are **append-only**: additions are
free, removals and renames require a major bump and a CHANGELOG entry under a
dedicated heading.

Deprecations MUST be announced with a named removal version and a migration
path, and the old and new shapes MUST be emitted in parallel until that version
lands. Success models tolerate unknown keys; error-detail models treat their
field lists as authoritative.

Library versions are reported, not policed: where a version floor would become a
trap for users on older FieldWorks installations, the version MUST be reported
and never compared, and that guarantee MUST be protected by a regression test.

Releases follow semantic versioning. Runtime dependencies carry both a floor and
a next-major cap, and the floor MUST cover the version any bundled artifact was
built against. Coverage floors and similar quality thresholds ratchet upward;
lowering one requires explicit justification recorded in the same change.

### V. Errors That Teach

A rejection is a teaching opportunity, not a dead end. Every refusal MUST carry
a stable machine-readable error code plus human guidance: what went wrong, the
nearest valid alternatives, and the concrete next call to make. Where the caller
can repair the problem, the system SHOULD ask them to repair and resubmit rather
than simply rejecting.

Failures MUST surface early and loudly. A missing dependency belongs in a clear
startup message, not in a mysterious attribute error thirty calls later.

Every operation MUST be observable: a human-readable log for the user and a
structured record for analysis, emitted from the same code path so the two can
never diverge, and correlated by operation id.

### VI. One Module, One Source of Truth

Write one module; run it everywhere. Parallel copies of the same operation for
different environments MUST NOT be maintained - divergence between them produces
a false sense of safety and, eventually, corrupted data. The canonical entry
point is a single `Main(project, report, modifyAllowed)` signature.

Ceremony is added when it is earned, not before. Bare exploratory snippets are a
first-class primitive; module scaffolding belongs at the point where code is
named, saved, shared, or deployed. Half-converted modules MUST be refused rather
than executed hopefully.

Generated code MUST import its API surface explicitly by name rather than
relying on ambient injection, because the failure mode of the wrong library is
silent, wrong behaviour rather than an error.

Prose is a product surface. Documentation, templates, and recipes are the
material the system teaches from, so their code snippets MUST be validated
against the live API the same way source code is.

### VII. Windows-First, No Cross-Platform Shims

FieldWorks is a Windows application with .NET interop at its core. Windows-only
paths and runtime interop are expected and MUST NOT be papered over with
cross-platform shims that hide real incompatibilities. Other platforms are
supported only as a no-FieldWorks smoke surface: the suite MUST remain runnable
without a live installation, with live-dependent tests explicitly marked and
deselectable.

Console output MUST be plain ASCII. Subprocess boundaries MUST be
UTF-8-configured so that non-Latin script data can never corrupt a result
marker.

## Additional Constraints

**Platform and runtime.** The supported Python floor is declared in
`pyproject.toml` and exercised in CI across at least the floor and the current
target release on Windows, plus one Linux job as the no-FieldWorks smoke
surface. Real work requires Windows and .NET; interop and search dependencies
are core dependencies, not optional extras.

**Dependencies.** `pyproject.toml` is authoritative for dependencies and
`requirements.txt` mirrors it; the two MUST be kept in sync. Runtime
dependencies are capped below the next major version, and a scheduled canary
MUST test against the excluded majors and report findings without failing the
job.

**Packaging and release.** The version lives in a single file. Publication uses
Trusted Publishing with no stored credentials, gated on a wheel smoke test
performed in a clean environment outside the repository. Release tags are pushed
individually and by name. Prefer a patch bump over re-tagging.

**Security posture.** The server is a local stdio tool and MUST NOT be exposed on
a network interface or granted elevated privileges. There is no sandbox. Shared
or downloaded projects are untrusted input, including as a prompt-injection
vector. The threat model MUST be documented honestly, including its limits, and
vulnerabilities are reported privately rather than in public issues.

## Development Workflow & Quality Gates

**Two specification tiers.** Features are specified at the tier their risk
warrants:

- *Full tier* - required for write-path work, multi-checkpoint campaigns, and
  anything crossing a published contract. Artifacts: `spec.md`, `plan.md`,
  `tasks.md`, plus `research.md`, `data-model.md`, `contracts/`, `quickstart.md`,
  `checklists/`, `evidence/`, and `reviews/` as the work requires.
- *Lightweight tier* - a single specification file, optionally with `tasks.md`
  and `reviews/`, for read-only or contained changes.

Genuinely trivial changes - documentation, comments, typing, renames, lint fixes,
test scaffolding, confined to one or two files and touching no write path - need
no specification at all. When the tier is genuinely in doubt, choose the heavier
one. "It is only a one-liner" is never an argument for skipping a write-path
gate: a one-line setter change is a write-path change.

**Pipeline order.** `specify` -> domain review -> `plan` -> plan review ->
`tasks` -> `implement` -> code-quality review -> live verification (write-path
only) -> mark complete. These review gates are registered in
`.specify/extensions.yml` so they fire identically for an unattended campaign
run, an interactive command, and a bare resume. Review gates MUST live in that
file rather than in prompts, because a prompt-driven gate does not exist for a
run that was never prompted.

**Blocking review gates.**

- *Domain gate* - a new specification MUST be validated against LCM and
  FieldWorks source reality, not merely against its own internal consistency:
  named paths exist, every call does what the specification claims, and contract
  field names and field order match the parent specification.
- *Plan gate* - a plan MUST name the tests that will prove each requirement.
  Coverage that is asserted but not scheduled is a blocking finding.
- *Pattern audit* - a bug with a recognizable shape MUST carry a pattern-audit
  section identifying sibling occurrences elsewhere in the codebase, so the fix
  is global rather than point-local. One-offs are exempt with an explicit
  justification, not by silence.
- *Live verification* - any change to a write path MUST carry evidence from a
  live database showing pre- and post-change field values. A mock-only pass is
  not verification, and an unrun verification is not a pass. Write verification
  uses a scratch project with prefixed test objects; read paths may use a
  reference project.

**Merge requirements.** Before a change lands: a CHANGELOG entry exists;
extractor changes carry a regenerated index diff and the regenerated index is
committed with them; payload-shape changes carry regenerated golden files; the
test suite passes; the integrity validator exits clean; pre-commit passes; and
lint passes. Changes to gate behaviour MUST update the gate configuration in the
same change - that diff is the review artifact.

**Tests.** Live-dependent tests are opt-in through environment variables with
safe defaults and a registered marker, never skipped on a missing secret.
Contract behaviour is pinned by golden fixtures covering every error code.
Documentation snippets are tested, so that an upstream version bump reddens CI
when prose was not updated. Regression tests are named for the issue they close.

**Commits.** `type(scope):` subjects with domain-noun scopes; `spec(<feature>):`
is a first-class type for specification and checkpoint-progress commits, which
carry progress fractions and gate status in the subject. Issue closure uses a
lowercase `closes #N` trailer, and - because closure only fires when the commit
reaches the default branch - committing without pushing leaves the work
unfinished. Pattern-audit findings live in the commit body, which is the
artifact review reads.

**Stop conditions.** Automated work carries a durable handoff with exactly three
states: continue, needs-human, or complete. `needs-human` means a human decision
is awaited - including authorization for an outbound action - and does not by
itself indicate failure. It MUST NOT be absorbed or downgraded by a reviewing
agent. Never rewrite published history, force-push, or commit without
authorization for that specific commit: authorization to commit once is not
authorization for every future commit.

## Governance

This constitution supersedes conflicting practice elsewhere in the repository.
Where a document and this constitution disagree, this document governs and the
other document MUST be corrected.

**Amendments** require a written change to this file, a version bump, and
propagation to every dependent artifact in the same change: the plan, spec, and
tasks templates, `.specify/extensions.yml` where a gate is affected, and any
runtime guidance document that restates a changed rule.

**Versioning of this document** follows semantic versioning:

- MAJOR - a principle is removed or redefined in a backward-incompatible way, or
  governance itself changes.
- MINOR - a principle or section is added, or existing guidance is materially
  expanded.
- PATCH - clarification, wording, or non-semantic refinement.

**Compliance.** Reviews verify compliance with these principles, not merely with
the diff in front of them. Added complexity MUST be justified against Principle
VI. A gate this document calls non-negotiable cannot be waived by expedience,
scope, or size of change; it can only be changed by amending this document.

Runtime development guidance lives in `CLAUDE.md`,
`docs/FLEXTOOLS-STYLE-GUIDE.md`, `CONTRIBUTING.md`, and `docs/TOOL-CONTRACT.md`.
Those documents describe how; this one describes what must remain true.

**Version**: 1.0.0 | **Ratified**: 2026-02-05 | **Last Amended**: 2026-09-22
