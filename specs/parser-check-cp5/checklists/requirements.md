# Specification Quality Checklist: parser-check CP5 -- the sandbox spine

**Purpose**: Validate Companion specification completeness before planning
**Created**: 2026-09-24
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs). HermitCrab, FieldWorks and PowerShell names appear only where the issue or parent spec binds behaviour to them, or under Verbatim Constraints.
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders, as far as this domain allows. The audience is the maintainer and the LEX crew.
- [x] All mandatory sections completed (User Scenarios, Requirements, Success Criteria)

## Requirement Completeness

- [x] Any [NEEDS CLARIFICATION] markers are genuine ambiguities (≤3) deferred to clarify, not unresolved guesses. They are Q1 (install hint versus prerequisites), Q2 (where corpus expectations come from) and Q3 (engine version skew), and each has an adopted default.
- [x] Each Functional Requirement is a single, testable MUST/SHOULD statement
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded (Out of Scope section)
- [x] Dependencies and assumptions identified: the CP3 run-record contract, the existing probes, `backup.py`'s free-space rule, and CP4 filing, which invalidates the cache

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into the specification

## Notes

- Source-verified 2026-09-24 against `sillsdev/machine` (`b77b2337`, HermitCrab.Tool), FieldWorks `Src/GenerateHCConfig`, and the installed FieldWorks 9.3.11 / .NET 8 runtime. Six facts the issue does not state became requirements:
  - **SDK and .NET 10 prerequisites** for installing and running `hc` (FR-004, Q1).
  - **Quote-toggle splitting** of script lines (FR-013).
  - **The broken `\` escape** in `test` expectations (FR-027).
  - **`GenerateHCConfig` exit codes and load-error behaviour.** It exits 0 on help, and a config is still written when load errors occur (FR-009, FR-010).
  - **HermitCrab version skew** between `hc` and FieldWorks (FR-005, Q3).
  - **Buffered `-o` output lost on a timeout kill** (FR-020).
- Correction to the parent listing: the run artifacts follow CP3's record contract, and `run.json` is only the script's hand-off file (Assumptions).
