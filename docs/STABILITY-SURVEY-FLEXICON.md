# Flexicon Stability & Standardization Survey

Date: 2026-07-06
Scope: ../flexicon repo (companion to STABILITY-SURVEY-FLEXTOOLSMCP.md)
Method: Read-only scan of structure, tests, versioning, liblcm coupling, API surface, known-issue docs.

---

## 1. Repo Structure & Organization

**Package layout:**
- Main package: `flexicon/` (139 Python files across 12 domains)
- Core infrastructure: `flexicon/code/` with domain subpackages:
  - Lexicon (10 Operations classes + helpers), Grammar (9), TextsWords (8), Discourse (7), Notebook (5), Lists (7), System (5), Scripture (6), Reversal (2), Shared (2)
  - Core base classes: BaseOperations, exceptions, lcm_casting
- Sync subsystem: `flexicon/sync/` (9 modules + 10 test modules for hierarchical import/merge/diff)
- Tests: `tests/` and `flexicon/sync/tests/` (87 Python test files)
- Demos/examples: `examples/` and `demos/`
- Docs: `docs/` (26 Markdown files including API_ISSUES, ARCHITECTURE, EXCEPTION_HANDLING)

**Counts:**
- 63 Operations classes (62 subclasses + 1 BaseOperations base)
- ~1,210 `@OperationsMethod`-decorated methods
- 47 `.pyi` type stub files

**Naming conventions:**
- [OK] Highly consistent: `{Domain}{Entity}Operations.py` pattern (LexEntryOperations, POSOperations, ConstChartOperations)
- [OK] All inherit from BaseOperations
- [OK] All methods PascalCase (`GetAll()`, `Create()`, `SetGloss()`)
- [OK] Validation helpers consistently named: `_ValidateParam()`, `_EnsureWriteEnabled()`
- [WARN] Hierarchical list methods renamed params across versions (`flat=` -> `recursive=`, `include_subcategories=` -> `recursive=`; MIGRATION_GUIDE.md:174-220)
- [WARN] Singular vs plural property aliases on FLExProject (both `project.Agents` and `project.Agent`; API_ISSUES_CATEGORIZED.md:74-136)

---

## 2. Test Infrastructure

**Organization:**
- `tests/` with 87 files; mixed mock-only and live-project tests
- Live tests marked `@pytest.mark.requires_live_project`
- Categorized by phase (Phase 0-4) and domain
- Dashboard JSON output (`test_results.json`); live-project ledger (`live_status.json`) tracks CRUD phase coverage per Operations class

**Key fixtures (`tests/conftest.py`):**
- Session-scoped autouse `initialize_flex_for_tests()` handles FLEx DLL loading
- Mock project fixtures (`mock_project_write_enabled`, `mock_project_read_only`)
- Mock LCM object factories (mock_lex_entry, mock_lex_sense, ...)
- `sena3_sandbox()` for destructive Phase E tests (unzips .fwbackup, yields clean .fwdata)

**Contract testing:**
- LibLCM compatibility suite (`tests/contract/test_lcm_contract.py`) in two modes:
  - Mode 1 (static): AST extraction of expected contract (no runtime deps)
  - Mode 2 (live): introspection against installed liblcm assemblies
- Baseline snapshot: `tests/contract/snapshots/expected_contract.json`
- Detects when changes introduce new LCM dependencies

**Mocking strategy:**
- [OK] `unittest.mock.Mock`/`MagicMock` for isolated unit tests
- [OK] Graceful fallback to mock mode if FLEx not installed (`conftest.py:250-258`)
- [WARN] Brittle mock-only tests: `conftest.py:48-52` lists 3 test files that poison `sys.modules["SIL"]` and are skipped entirely (`collect_ignore`) - these never exercise real library behavior

**CI/CD:**
- `publish.yml` - Trusted Publishing (OIDC) to PyPI on version tags
- `upstream-api-monitor.yml` - daily detection of FieldWorks/liblcm API changes
- `upstream-compatibility-check.yml` - weekly contract verification against live FW installation (self-hosted runner)
- `local-compat-check.yml` - per-commit smoke tests without FLEx

**Coverage:**
- No pytest-cov integration visible; no % coverage metrics in repo
- Live-project marker tracking (conftest.py:697-897) enables per-class CRUD phase reporting

---

## 3. Versioning & Release Process

**Version string:**
- Single source: `pyproject.toml:7` -> `version = "4.1.2"`
- No `__version__` in `flexicon/__init__.py` or `_version.py`

**CHANGELOG & migration:**
- `CHANGELOG.md` - Keep a Changelog format, Semantic Versioning, per-release Fixed/Added/Changed/Deprecated/Tests sections
- `MIGRATION_GUIDE.md` covers v1.x -> v2.0 (empty multistring handling), v2.x -> v3.0 (Reversal API removal, Lists consolidation), v2.4 -> v2.5 (parameter renaming)

**Release:**
- Type stubs shipped: `py.typed` marker + 47 `.pyi` files
- CI trigger: `publish.yml` fires on `git tag v*`; build via `pipx run build`; publish via `pypa/gh-action-pypi-publish` with OIDC (no static token)
- Tags follow semver: v4.1.2, v4.1.0, v4.0.1

---

## 4. LibLCM Coupling & Abstraction Layer

**Access pattern:**
- [OK] Centralized-ish: SIL.LCModel imports at top of each of the 63 Operations class files
- [OK] Lazy loading in `lcm_casting.py:81-106`: `_ensure_interfaces()` defers import until first `cast_to_concrete()` call
- [OK] Casting abstraction layer (`lcm_casting.py`, 890 lines): `cast_to_concrete()`, `get_pos_from_msa()`, `get_from_pos_from_msa()`, `validate_merge_compatibility()`, `clone_properties()`, introspection helpers

**Version pinning:**
- `FLExGlobals.py:49` -> `FW_SUPPORTED_VERSIONS = ["9"]` (hard-coded to FieldWorks 9)
- Registry lookup: `FWRegKeys = {"9": r"SOFTWARE\SIL\FieldWorks\9"}`
- [WARN] No runtime version check: FLExInit.py does not verify FW version at startup; relies on registry key presence
- README.rst:30 -> "FieldWorks Language Explorer 9.0.17 - 9.3.1" (human-readable, not enforced)
- `pythonnet >= 3.0.3, <3.1` pinned in pyproject.toml:35

**Direct vs abstracted C# calls:**
- [OK] Most Operations methods route through FLExProject helpers or `cast_to_concrete()`
- [WARN] Direct property access scattered throughout (raw `entry.SensesOS`, `sense.ExamplesOS`, `msa.PartOfSpeechRA`) - intentional, pythonnet respects C# property paths
- [WARN] No versioning guards: no try/except around liblcm types that might be missing in older FW versions

**Known compatibility workarounds:**
- `lcm_casting.py:138` -> `IPhReduplicationRule = None` (no such class in MasterLCModel.xml; back-compat key kept)
- `lcm_casting.py:152-172` -> morphosyntactic prohibition type name mismatches corrected (IMoMorphAdhocProhib / IMoAlloAdhocProhib), old keys exposed for back-compat
- CHANGELOG 4.1.2 -> phonological context casting bug (#222), `GetSyncableProperties` mono ITsString vs multi-string distinction fixed

---

## 5. API Surface Stability

**Deprecation mechanisms:**
- [OK] Compatibility alias: `import flexlibs2` transparently resolves to `flexicon` via meta-path finder, emits DeprecationWarning; removal scheduled v5.0.0

**Docstring conventions:**
- [OK] Comprehensive: one-line summary -> description -> Args/Returns/Raises -> doctest-style Examples -> See Also
- Consistent Sphinx-compatible triple-quoted format (feeds FlexToolsMCP AST extraction cleanly)
- Example: `LexEntryOperations.Create()` (LexEntryOperations.py:131-188)

**FlexToolsMCP extraction compatibility:**
- [OK] Docstrings parse cleanly; `@OperationsMethod` decorator preserved in AST
- [WARN] Type hint coverage is LOW: only 11 of 108 files have return-type annotations; most type info is docstring-only, so extraction depends on docstring parsing, not AST annotations

**Linting & formatting (`.pre-commit-config.yaml`):**
- Black (v24.1.1, line-length 120), Flake8 (v7.0.0, +bugbear, +comprehensions), detect-secrets
- Custom `scripts/check_decorators.py` hook for duplicate @OperationsMethod decorators
- No ruff or pyright config

**Known inconsistencies (API_ISSUES_CATEGORIZED.md, 35 KB, updated 2026-06-30):**
- Category 1 (property name aliases): RESOLVED - singular/plural both supported
- Category 3 (wrong interface returns): 6 demos - generic interface returned instead of typed (e.g., ICmPossibility instead of ICmSemanticDomain)
- Category 4 (missing methods): 5 demos - documented operations that don't exist yet
- Category 5 (cast-on-yield gaps): 3 demos - methods yield base type, downstream re-cast needed (fixed in v4.0.1)

---

## 6. Known Issues & Documentation

**Dedicated docs:**
- `EXCEPTION_HANDLING.md` - .NET exception types, FP_* hierarchy, safe casting patterns
- `API_ISSUES_CATEGORIZED.md` - 28 WARN-status demos across 7 categories
- `ARCHITECTURE.md`, `ARCHITECTURE_COLLECTIONS.md`, `ARCHITECTURE_WRAPPERS.md`
- `TRANSACTION_GUIDE.md` - undo/redo transaction patterns
- Domain usage guides: USAGE_PHONOLOGICAL_RULES.md, USAGE_MORPHOSYNTAX.md, USAGE_ALLOMORPHS.md, etc.
- `CONTRACT_TESTING.md` - LibLCM compatibility verification

### Where LibLCM changes break flexicon silently

1. **No runtime FW version check** (`FLExGlobals.py:49-82`)
   - FW_SUPPORTED_VERSIONS hard-coded to ["9"], never verified at init
   - FW 10 upgrade won't fail at startup; failures surface at first clr.AddReference or property access, hard to diagnose

2. **Scattered direct SIL.LCModel imports** (63 Operations classes)
   - e.g., LexEntryOperations.py:22-40, LexSenseOperations.py:8-26
   - Removed type -> entire Operations class fails to import; renamed cast target -> silent wrong return type

3. **No deprecation/removed-type guards**
   - lcm_casting.py:160-172 worked around missing interfaces with None, but callers didn't always check for None
   - Cast failures wrapped as generic exceptions, hard to correlate with liblcm version

4. **Lazy-loaded interface cache** (`lcm_casting.py:81-106`)
   - Import failure delayed until first cast_to_concrete() call (error message is clear, at least)

5. **Direct property access without hasattr guards** (throughout)
   - e.g., all Lexicon methods assume `project.ObjectsIn(ILexEntryRepository)` exists; a repository rename breaks the whole domain late

6. **ClassName string lookups in cast_to_concrete()** (`lcm_casting.py:335-351`)
   - `obj.ClassName` -> `_interface_cache` lookup; a renamed LCM class silently returns the uncast object -> downstream AttributeError far from cause

### Where flexicon changes break FlexToolsMCP index extraction

1. **Docstring format instability** - AST parser expects Args/Returns/Raises sections; free-form docstrings degrade the index silently
2. **Type stubs (.pyi) out of sync** - 47 stubs, no automation keeping them in sync with .py signatures
3. **@OperationsMethod decorator removal** - check_decorators.py catches duplicates but not removal
4. **Return type polymorphism not encoded in stubs** - `GetAll()` returns EnumerableWrapper; stubs may say IEnumerable
5. **Exception docs vs code drift** - EXCEPTION_HANDLING.md not validated against actual raises
6. **Wrapper classes** (ARCHITECTURE_WRAPPERS.md) - docstrings not in standard format; extraction sees them as undocumented

---

## 7. Summary Table

| Aspect | Rating | Key Findings |
|--------|--------|-------------|
| Package structure | Excellent | 63 Operations classes, clear domain hierarchy, consistent naming |
| Test coverage | Good | 87 test files, live-project markers, but mock-only suite incomplete |
| Versioning | Excellent | Semver in pyproject.toml, CHANGELOG + MIGRATION_GUIDE, Trusted Publisher CI |
| LibLCM coupling | Good | Centralized lcm_casting abstraction, but scattered direct imports + no version checks |
| API stability | Good | Deprecation aliases work, docstrings comprehensive, 11 documented API issues outstanding |
| Type hints | Weak | ~10% of files have return-type annotations; most info docstring-only |
| Linting/formatting | Excellent | Black + Flake8 + custom decorator hook via pre-commit |
| FlexToolsMCP readiness | Caution | Docstring parsing works today, but stubs not auto-synced; return-type polymorphism may confuse extraction |

---

## 8. Critical Recommendations

**For stability:**
1. Add runtime FW version check in FLExInit.py after `clr.AddReference("SIL.LCModel")`, with clear error on mismatch
2. Wrap top-level SIL.LCModel imports in try/except with import-time error reporting (not deferred to use-time)
3. Add hasattr guards before property access on liblcm objects (or centralize repository access)

**For FlexToolsMCP index stability:**
1. Mandate return-type annotations on all @OperationsMethod methods (PEP 484, not docstring-only)
2. Auto-generate .pyi stubs in CI rather than maintaining manually
3. Docstring validator in pre-commit: ensure Args/Returns/Raises sections parse for all public methods
4. Type-stub sync test: compare .pyi signatures against .py at test time; fail on drift

**For known issues:**
1. Resolve Category 3-5 items in API_ISSUES_CATEGORIZED.md (6 wrong-interface, 5 missing-method) before next major release
2. Document the exact cast-on-yield contract expected by FlexToolsMCP (e.g., "all GetAll() return EnumerableWrapper, never raw IEnumerable")

---

## File References

| Aspect | Path |
|--------|------|
| Config/build | `flexicon/pyproject.toml:1-69`, `.pre-commit-config.yaml:1-59` |
| Version/release | `CHANGELOG.md`, `MIGRATION_GUIDE.md:1-260` |
| Base infrastructure | `flexicon/code/BaseOperations.py:1-200`, `flexicon/code/exceptions.py:1-90` |
| LibLCM coupling | `flexicon/code/lcm_casting.py:1-890`, `flexicon/code/FLExGlobals.py:1-167`, `FLExInit.py:1-83` |
| Test config | `tests/conftest.py` (session fixture), `tests/contract/test_lcm_contract.py` |
| Known issues | `docs/API_ISSUES_CATEGORIZED.md`, `docs/EXCEPTION_HANDLING.md` |
| Sample Operations | `flexicon/code/Lexicon/LexEntryOperations.py:1-300`, `flexicon/code/Grammar/POSOperations.py` |
