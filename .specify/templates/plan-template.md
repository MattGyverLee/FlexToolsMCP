# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]

**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]

**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]

**Testing**: [e.g., pytest, XCTest, cargo test or NEEDS CLARIFICATION]

**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]

**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]

**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]

**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]

**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

*Source: `.specify/memory/constitution.md` v1.0.0. Answer each; any NO needs an
entry in Complexity Tracking below.*

- [ ] **I. Safety-First Write Path** - Does this feature touch a write path? If
      yes: read-only default preserved, `if modifyAllowed:` guard, pre-write
      backup, explicit confirmation, dry-run rehearsal, and no unattended
      destructive write. No convenience flag relaxes a write-safety or casting
      check.
- [ ] **II. Discovery Over Memory** - Any API surface this plan relies on is
      reachable through the indexes, not assumed from memory. Cross-flavor gaps
      are declared, not silently absent.
- [ ] **III. Self-Contained, Regenerable Extraction** - Extractor or index
      changes stay static-analysis-only, regenerate in one all-or-nothing pass,
      and write to the user overlay rather than the installed package.
- [ ] **IV. Append-Only Versioned Contracts** - Response keys and error codes are
      added, never removed or renamed, within the current contract major. Any
      deprecation names its removal version and dual-emits until then. CHANGELOG
      entry planned.
- [ ] **V. Errors That Teach** - Every new refusal carries a stable error code
      plus actionable guidance, and every new operation is observable through
      both the prose and structured log paths.
- [ ] **VI. One Module, One Source of Truth** - No parallel copy of an existing
      operation. Added complexity is justified here or removed.
- [ ] **VII. Windows-First, No Cross-Platform Shims** - No shim hides a real
      incompatibility; the suite still runs without a live FieldWorks install;
      console output is plain ASCII.
- [ ] **Gate obligations scheduled** - This plan names the tests proving each
      requirement; a shaped bug carries a pattern-audit task; write-path work
      carries a live-LCM verification task with pre/post field evidence.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
