# Stabilization Strategy: FlexToolsMCP + Flexicon

Date: 2026-07-06
Companions: STABILITY-SURVEY-FLEXTOOLSMCP.md, STABILITY-SURVEY-FLEXICON.md

## The Core Diagnosis

The crown jewel of this stack is the **index** - 1,400+ operations made discoverable without 1,400 tools. But the index is the output of an **implicit contract that spans three layers**, and nothing enforces that contract today:

```
liblcm (C# types, namespaces, OS/OC/RA/RC suffixes)
   |  reflection contract          <- partially guarded (contract tests, upstream monitors)
flexicon (Operations classes, docstring format, @OperationsMethod, naming)
   |  AST-extraction contract      <- UNGUARDED (the weakest link)
FlexToolsMCP index (unified-api-doc/2.0 JSON)
   |  version-match contract       <- silent fallback to latest
AI-generated user scripts
```

Every "silent break" found in both surveys is a case of one layer changing something another layer *assumed* but never *declared*. The fix is not to freeze the repos - it's to make each boundary's contract **explicit, machine-checked, and diffable**, so churn is caught at refresh/CI time instead of in a user's generated script.

The mechanism that solves "I fix one thing and break another" is the same one that solves upstream churn: **make the API surface itself a reviewable artifact**. If every change to flexicon regenerates the index and diffs it against the committed baseline, then any change's blast radius is visible in the PR - added, removed, renamed, re-typed operations - before it ships.

---

## Boundary 1: liblcm -> flexicon

Current state: best-protected boundary. `tests/contract/test_lcm_contract.py` + `expected_contract.json` snapshot, daily `upstream-api-monitor.yml`, weekly `upstream-compatibility-check.yml` (self-hosted FW runner), `last-working-commit.txt` ledger.

Gaps and actions:

1. **Runtime FW version check** (FLExInit.py). `FW_SUPPORTED_VERSIONS = ["9"]` exists but is never verified at startup. Add a check after `clr.AddReference("SIL.LCModel")` that reads the assembly version and fails loudly (or warns) on unsupported versions. This converts "mysterious late AttributeError" into "clear startup message."
2. **Fail-loud casting option.** `cast_to_concrete()` (lcm_casting.py:335-351) silently returns the uncast object when a ClassName lookup misses. Add a strict mode (env var or config) that raises instead, and turn it on in CI/contract tests. Silent-in-production, loud-in-CI.
3. **Centralize LCM type access.** 63 Operations files each import SIL.LCModel types directly. Don't boil the ocean; instead, add a single `lcm_types.py` facade that imports and re-exports every LCM interface flexicon uses, with a generated "types we depend on" manifest. The contract test then checks that manifest against the installed liblcm - one place to see the full dependency surface, one place that fails on removal.
4. **Adapt the copied workflows.** upstream-api-monitor.yml and upstream-compatibility-check.yml still reference "flexlibs" in names/paths; verify they actually run green against flexicon and that the self-hosted runner exists. A monitor that silently doesn't run is worse than none.
5. **Declare the FW/liblcm compatibility range in packaging metadata** (even as a classifier or a `[tool.flexicon]` table in pyproject.toml) so tooling - including FlexToolsMCP - can read it instead of parsing README prose.

---

## Boundary 2: flexicon -> FlexToolsMCP index (the critical one)

Current state: extraction depends on naming conventions (Operations suffix, Get/Set/Create prefixes, OS/OC/RS/RC/OA/RA property suffixes), Sphinx-style docstrings, and `@OperationsMethod` decorators - with **zero validation** that a refreshed index is complete, well-formed, or non-regressive. This is where a routine flexicon refactor silently degrades the crown jewel.

Actions, in priority order:

### 2a. Index diff tool (highest leverage, do first)

Add `scripts/index_diff.py` to FlexToolsMCP that compares two `unified-api-doc/2.0` files and reports:
- entities added / removed
- methods added / removed / signature-changed per entity
- docstring-coverage delta (count and %)
- relationship adds/removals and dangling targets

Wire it into `refresh.py`: after generating a new index, diff against the previous version (the archive/ dir already exists for this). **Fail the refresh** (exit nonzero) on removals or coverage drops unless `--allow-breaking` is passed. Print the diff summary always. This one tool closes the CRITICAL drift-detection gap and doubles as the release-notes generator for index changes.

### 2b. Floors and integrity assertions in the extractors

At the end of generation, assert:
- `metadata.total_types == len(entities)` (and same for methods/properties)
- every relationship source/target exists in entities
- entity count >= a hard floor per library (e.g., flexicon > 60 Operations classes, > 1,100 methods; liblcm > 2,000 types)
- description coverage >= 95% for flexicon (it's at ~99% today - protect that)

These are ~50 lines and convert every "silent misclassification" failure mode (renamed suffix, changed docstring shape, moved namespace) into a loud refresh failure, because all of them manifest as count/coverage drops.

### 2c. Publish the extraction contract INTO flexicon

The conventions FlexToolsMCP depends on should be flexicon's problem to keep, not FlexToolsMCP's problem to discover breaking. Add to flexicon:
- `docs/EXTRACTION_CONTRACT.md`: Operations class suffix, method prefix vocabulary, docstring section format (Args/Returns/Raises/Example/See Also), @OperationsMethod requirement, EnumerableWrapper return convention.
- A pre-commit/CI **docstring validator** (`scripts/check_docstrings.py`): every public method on an Operations class must have a docstring whose sections parse. Fail on drift. (The existing check_decorators.py hook is the template; extend it to check decorator *presence*, not just duplicates.)
- Optionally: run FlexToolsMCP's `flexicon_analyzer` against flexicon in flexicon's own CI (it's pure AST, no FLEx needed) and diff entity/method counts against a committed baseline. Then a flexicon PR that would degrade the index shows it *in the flexicon PR*, which is exactly where you want to see it.

### 2d. JSON Schema for unified-api-doc/2.0

Write the schema down as an actual jsonschema file (`schemas/unified-api-doc-2.0.schema.json`), validate at generation time and (cheaply, structure-only) at server load time. Also stamp the currently-unversioned casting_index with a `_schema` field. Bump the schema version whenever the shape changes and note it in CHANGELOG.

### 2e. Type stubs: automate or demote

47 .pyi files with no sync automation is a liability. Either auto-generate them in CI and fail on drift, or explicitly document that docstrings (not stubs) are the source of truth for extraction and add a stub-vs-source signature comparison test. Don't leave two sources of truth unguarded.

---

## Boundary 3: FlexToolsMCP -> users

1. **Version-mismatch fallback should WARN, not INFO** (server.py:318-357). When the installed flexicon/liblcm version has no matching index and the server falls back to latest, surface it in the session header so both the user and the AI assistant know the index may be stale.
2. **Cap the dependency pin.** `pyflexicon>=4.1.0` with no upper bound means flexicon v5.0.0 (which is already scheduled to remove the flexlibs2 alias) flows straight into MCP installs. flexicon follows semver; pin `pyflexicon>=4.1,<5` and bump the cap deliberately with each verified major. The pyproject comment says the floor-only pin is intentional for "latest Flexicon" - keep that for minors, but majors are exactly what semver caps are for.
3. **Invalidate `_file_discovery_cache`** after auto-refresh writes new index files (versioning.py:23), or key the cache on directory mtime.

---

## Standardizing the Change Process (both repos)

1. **CI parity.** FlexToolsMCP has 20 test files and *no* test workflow - only publish-on-tag. Add a `test.yml` running pytest + `scripts/validate_integrity.py all` + (new) index schema validation on every push/PR. This is the single cheapest stabilization step in the whole plan. flexicon already has local-compat-check.yml; mirror the pattern.
2. **One compatibility matrix, machine-readable.** A `compatibility.json` (live in flexicon, mirrored or fetched by FlexToolsMCP) declaring: flexicon version range <-> supported FW/liblcm versions <-> index schema version <-> FlexToolsMCP minimum version. Every "which versions work together?" question - by you, by CI, by the MCP server at startup - reads this file instead of prose. Update it as part of the release checklist.
3. **Release choreography.** Add to both RELEASING.md files:
   - flexicon release -> regenerate FlexToolsMCP index (`refresh.py`, which always scans all available APIs) -> review the index diff -> commit index + bump + release FlexToolsMCP.
   - Automate the trigger if desired (repository_dispatch from flexicon's publish workflow opening a "refresh index for flexicon vX.Y.Z" issue on FlexToolsMCP), but the checklist alone removes the "forgot to refresh" failure mode.
4. **PR discipline via the diff artifact.** Rule for flexicon: any PR touching a public Operations signature must include (a) a CHANGELOG entry and (b) the extraction-baseline diff (from 2c) in the PR body. The LEX crew's lex-qc gate can enforce this. This is what makes "fix one thing, break another" visible pre-merge instead of post-release.
5. **Burn down the known-issue backlog before adding surface.** API_ISSUES_CATEGORIZED.md Categories 3-5 (6 wrong-interface returns, 5 missing methods, cast-on-yield gaps) are exactly the kind of index-vs-reality drift that erodes trust in the crown jewel: the index documents an operation, the user's script fails. Freeze net-new API until these are closed or explicitly marked in the index (a `"status": "known_issue"` field would let the MCP warn at generation time).

---

## Discoverability (protecting and improving the jewel)

- **Coverage floors as a first-class metric** (2b above): description coverage and example coverage are what make semantic search work. Track them per release in CHANGELOG ("Index: 1,214 methods, 99.2% described, 83% exampled").
- **Return-type annotations** on @OperationsMethod methods (currently ~10% of files). Do this opportunistically - whenever a file is touched, annotate it - and lint that *new* methods must be annotated. Richer types in the index mean better navigation-path and casting answers.
- **Encode the wrapper contract in the index.** Document (and index) that GetAll() returns EnumerableWrapper, never raw IEnumerable, so generated scripts use `.Count` correctly.
- **Keep the object-centric organization stable.** Category names and entity IDs in the index are effectively public API for the MCP tools; treat renames there as breaking changes subject to the diff gate.

---

## Sequencing

**Phase 1 - safety net first (days, no behavior risk):**
1. FlexToolsMCP `test.yml` CI workflow (pytest + validate_integrity)
2. `index_diff.py` + wire into refresh.py with fail-on-removal
3. Generation-time floors/assertions in both extractors
4. WARN-level version-mismatch logging; `pyflexicon<5` cap
5. JSON Schema file + validation

**Phase 2 - move the contract upstream (1-2 weeks):**
6. EXTRACTION_CONTRACT.md + docstring validator in flexicon pre-commit/CI
7. Run flexicon_analyzer baseline diff in flexicon CI
8. Verify/adapt the copied upstream-monitor workflows; confirm the self-hosted runner is alive
9. compatibility.json + release choreography in both RELEASING.md files

**Phase 3 - harden the liblcm boundary (as capacity allows):**
10. Runtime FW version check in FLExInit.py
11. Strict-mode cast_to_concrete (on in CI)
12. lcm_types.py facade + dependency manifest
13. Stub automation-or-demotion decision
14. Burn down API_ISSUES Categories 3-5

**Ongoing rules:**
- Every flexicon public-API PR ships with CHANGELOG entry + index-diff evidence
- Every flexicon release is followed by an index refresh + reviewed diff in FlexToolsMCP
- Coverage floors only ratchet up, never down, without an explicit `--allow-breaking`

The theme throughout: never freeze, always *diff*. The repos stay free to evolve; the contracts at each boundary become artifacts that CI checks and humans review, so churn is absorbed at the boundary it enters instead of propagating silently to generated user scripts.
