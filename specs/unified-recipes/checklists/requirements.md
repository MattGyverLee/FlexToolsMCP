# Specification Quality Checklist: Unified recipes

**Purpose**: Validate Companion specification completeness before planning
**Created**: 2026-09-27
**Feature**: [spec.md](../spec.md)

## Content Quality

- [ ] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [ ] Written for non-technical stakeholders
- [x] All mandatory sections completed (User Scenarios, Requirements, Success Criteria)

## Requirement Completeness

- [x] Any [NEEDS CLARIFICATION] markers are genuine ambiguities (<=3) deferred to clarify -- none present
- [x] Each Functional Requirement is a single, testable MUST/SHOULD statement
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [ ] No implementation details leak into the specification

## Notes

- Deliberate fails (accepted, not fixed): this is a Full-tier developer-tool spec
  whose "users" are the assistant and the maintainer. File paths, tool names,
  response keys and the PARAMS marker are published-contract identifiers
  (constitution IV, append-only), so they are pinned in the FRs on purpose.
  Rewriting them as prose would force plan to re-guess the contract.
- Success criteria are measured in queries, rows, characters and counts; the
  tool/key names in SC-006 refer to the contract under test, not a technology.
- Fixed in this pass: FR-006 hard-coded flexicon 4.10.0; release 2.14.0 ships
  indexes for 4.11.0. FR-006 now ties the verified version to the index target.
- Watch for plan: local .venv has pyflexicon 4.10.0 while the committed index
  is 4.11.0 -- Sena 3 verification (FR-042/043) must run on the target version.
- FR-016 cites "FR edge case"; the 2,000-row cap is stated in Edge Cases.
