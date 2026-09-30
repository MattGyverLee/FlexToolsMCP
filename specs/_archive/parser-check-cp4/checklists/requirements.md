# Specification Quality Checklist: parser-check CP4 -- in-process write

**Purpose**: Validate Companion specification completeness before planning
**Created**: 2026-09-23
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) -- FieldWorks/LCM names appear only where the parent spec binds behaviour to them, or under Verbatim Constraints
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders -- to the extent this domain allows; audience is the maintainer + LEX crew
- [x] All mandatory sections completed (User Scenarios, Requirements, Success Criteria)

## Requirement Completeness

- [x] Any [NEEDS CLARIFICATION] markers are genuine ambiguities (≤3) deferred to clarify -- Q1 rung-2 escape, Q2 shared-mode filing, Q3 errored results; each has an adopted default
- [x] Each Functional Requirement is a single, testable MUST/SHOULD statement
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded (Out of Scope section)
- [x] Dependencies and assumptions identified (CP3 FR-004/FR-023/FR-025/FR-042/FR-043; run_module ladder)

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into the specification

## Notes

- Source-verified against `FieldWorks/Src/LexText/ParserCore/ParseFiler.cs` (2026-09-23). Three facts the parent spec under-states are now explicit: the segment shield includes glosses (`:310`), an errored result deletes every unshielded analysis (`:229-231`), and each filed word removes all parser-sourced problem annotations project-wide (`:217-224`).
- Rung-order divergence from the issue text (backup vs lock) is recorded under Assumptions.
- Mandatory backup diverges from `run_module`'s disk-space fallback (`execution.py` ~4681); FR-007.
- lex-domain pass 1 (2026-09-23): 2 BLOCKING corrected in place -- D-1 silent form exclusion (FR-039, US3 test b, SC-005), D-2 disapproval overwrite (FR-040/041, SC-011). Non-blocking: FLEx idle-queue retry divergence now disclosed (FR-019).
