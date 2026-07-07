# FlexToolsMCP Stability & Standardization Survey

Date: 2026-07-06
Scope: FlexToolsMCP repo only (companion survey of flexicon in progress)
Method: Read-only scan of tests, versioning, extractors, schema, release process, drift tooling.

---

FlexToolsMCP is a mature, well-documented MCP server with thoughtful versioning infrastructure, extensive test coverage, and deliberate architectural constraints. Below is the detailed assessment across six areas.

---

## 1. Test Infrastructure: Mature & Layered

**What exists:**

- **20 pytest test files** at `tests/`
  - Tests cover async locking, validators, casting chains, rejection payloads, script certification, version detection, undo mechanics
  - All tests runnable without live FieldWorks (pure Python, mock-friendly)
  - `tests/conftest.py:1-27` provides shared `reset_session_state` fixture

- **Static analysis test suite** (`test_flexicon_static_analysis.py`):
  - Analyzes 201 Python files without execution
  - Detects 7 pattern categories: unchecked_indexing, bare_except, broad_except, silent_fail, str_none_conversion, unsafe_int_conversion, multistring_check
  - Generates JSON report (`test_static_analysis.json`)
  - Runs ~10 seconds, no dependencies beyond ast/pathlib

- **Operational dry-run tests** (`test_flexicon_operations.py`):
  - 20 test templates (CRUD, Unicode, null references) that validate test structure without executing
  - Designed to run in FLExTools environment with live projects
  - Supports `dry_run=True` mode for safe validation

- **Pre-commit hooks** (`.pre-commit-config.yaml:1-36`):
  - `check-ast` - Python syntax validation
  - `ruff` - fatal errors only (E9, F63, F7, F82)
  - `verify-src-imports` - dual-mode import guards (`if __package__`)
  - `check-flexicon-ops` - Flexicon Operations classes load at commit time

- **Contract validation** (`scripts/validate_integrity.py:1-300`):
  - `syntax` subcommand: AST parse all src/ files
  - `imports` subcommand: check relative imports guarded by `if __package__:`
  - `server` subcommand: verify tool count >= 10 (runtime or AST fallback)
  - `refresh` subcommand: verify `refresh.py --help` exposes expected flags
  - `flexicon` subcommand: verify Flexicon Operations/exceptions at commit time
  - `all` subcommand: run all checks (default)

- **CI/CD:**
  - Minimal: only `.github/workflows/publish.yml` (publish-on-tag)
  - No continuous testing workflow
  - Build/test responsibility falls on developer

**Assessment:** Tests are comprehensive and runnable in isolation (no live FieldWorks required), but CI is minimal - there is no automated testing on push, only on release tags. Pre-commit hooks provide a development safety net.

---

## 2. Versioning Mechanisms: Semver Filenames + Auto-Refresh

**Version detection (`src/flextoolsmcp/server/versioning.py:39-321`):**

- `extract_version(filename)` (`versioning.py:39-53`):
  - Regex: `r'v(\d+)\.(\d+)\.(\d+)'`
  - Parses filenames like `liblcm_api_v11.0.0.json` -> `(11, 0, 0)`
  - Falls back to `(0, 0, 0)` if not found (silent)

- `detect_installed_library_version()` (`versioning.py:56-133`):
  - Tries live module attributes (`__version__`, `version`) first (key for editable installs)
  - Falls back to importlib.metadata
  - Handles C# assemblies via pythonnet reflection (SIL.LCModel)
  - Logged at INFO when successful, DEBUG when failing

- `detect_liblcm_version_from_disk()` (`versioning.py:136-188`):
  - Reads SIL.LCModel.dll directly via `Assembly.LoadFile()`
  - Searches default FieldWorks paths + `FIELDWORKS_DLL_PATH` env var
  - Used in session header logging (`kernel.py:227-250`)

- **File discovery** (`versioning.py:191-234`):
  - `find_api_files()` supports both `{prefix}_v*.json` and `{prefix}-v*.json` patterns
  - Searches main dir + archive/ subdir
  - Caches results in process-lifetime cache (`_file_discovery_cache`)
  - `find_latest_versioned_api_file()` returns newest version by semantic sort
  - `find_versioned_api_file()` does exact match; tries main + archive

**Index location & overlay system (`docs/VERSIONING.md:1-164`):**
- Bundled baseline: shipped inside wheel as package data (`src/flextoolsmcp/index/`)
- User overlay: `~/.flextoolsmcp/index/` (created at runtime if indexes are auto-refreshed)
- Source checkout: in-tree `src/flextoolsmcp/index/` (regenerated files committable)
- `get_index_dir()` (`file_utils.py`) resolves which to use

**Versioned API file naming:**
- `flexicon_api_v4.1.2.json` (current)
- `liblcm_api_v11.0.0.json` (LibLCM)
- `flexlibs_api_v1.2.8.json` (legacy)
- Archive: `index/flexlibs/archive/flexicon_api_v4.1.0.json`

**Auto-refresh on version mismatch (`src/server.py:318-357`):**
1. Detect installed version
2. Try exact match with `find_versioned_api_file()`
3. Fall back to latest with `find_latest_versioned_api_file()`
4. If still missing, call `auto_refresh_missing_api_file()` (triggers refresh script)
5. Load JSON, extract version from filename, store in APIIndex

**Version mismatch handling:**
- If installed version differs from available index: auto-refresh triggered
- If refresh fails: falls back to latest available (permissive, not strict)
- Mismatch logged at INFO level (not error)
- **Brittle point:** silent fallback to latest - users may not realize their index is stale

**Schema versioning in generated indexes:**
- Each file opens with `"_schema": "unified-api-doc/2.0"` (`liblcm_extractor.py:964-975`)
- Flexicon also uses `"_schema": "unified-api-doc/2.0"`
- Navigation graph: `"_schema": "navigation-graph/1.0"`
- Casting index: not explicitly versioned in `_schema`
- Common patterns: `"_schema": "common-patterns/1.0"`
- Reverse mapping: `"_schema": "reverse-mapping/1.0"`

**Assessment:** Versioning is solid - semantic filenames, parallel file discovery, and smart fallback logic. But the caching in `_file_discovery_cache` (process-lifetime, no invalidation) and silent fallback to latest are potential brittleness points. Missing version mismatch warnings.

---

## 3. Coupling to Flexicon & LibLCM: Tight on AST/Naming; Loose on DLL

### Flexicon analyzer (`src/flextoolsmcp/flexicon_analyzer.py`)

Dependencies (what breaks if upstream changes):

- **Docstring format:** Expects triple-quoted docstrings parsed as `ast.Expr` with `ast.Constant` (`flexicon_analyzer.py:181-192`)
  - *Brittle:* If Flexicon switches to a different docstring convention (pydantic docstrings, raw comments), extraction fails silently
- **Method naming conventions:** Categorizes by prefix (Get*, Set*, Create*, Delete*, etc.) (`flexicon_analyzer.py:800+`)
  - *Brittle:* If method names change, categories misfire (e.g., ListEntries vs GetAllEntries)
- **Class naming:** Detects Operations classes by suffix (`flexicon_analyzer.py:400-500`)
  - *Brittle:* Any rename like `OperationsMethod` -> `Operations` or `OpsMethods` breaks detection
- **Multistring property names:** Hard-coded set (`flexicon_analyzer.py:38-40`)
  - *Brittle:* If Flexicon adds Form, ShortName, etc., they're not recognized as multistring
- **AST shape assumptions:** Expects class definitions with methods as `ast.FunctionDef` inside `ast.ClassDef`
  - *Loud failure:* If Flexicon uses decorators/metaclasses differently, AST visitor may skip methods
- **Relationship suffixes (OS, OC, RS, RC, OA, RA):** Extracted from property names by regex match on naming convention
  - *Brittle:* If property names change (e.g., `SensesOS` -> `SensesList`), relationships aren't recognized

Example extraction flow (`flexicon_analyzer.py:1250-1380`):

```python
# Reads source, parses AST, visits ClassDef nodes
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name.endswith('Operations'):
        # Extract docstring (expects first stmt to be Expr with Constant)
        docstring = extract_docstring(node)
        # Parse docstring for "Arguments:" / "Returns:" / "Raises:" sections
        parsed = parse_docstring(docstring)
        # Method iteration expects ast.FunctionDef children
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                # Extract params from arg list, defaults from default values
                params = [p.arg for p in item.args.args]
```

### LibLCM extractor (`src/flextoolsmcp/liblcm_extractor.py:1-1099`)

Dependencies (what breaks if upstream changes):

- **Assembly loading:** Expects SIL.Core.dll -> SIL.LCModel.Core.dll -> SIL.LCModel.dll dependency order (`liblcm_extractor.py:174-187`)
  - *Loud failure:* If DLL is missing, `Assembly.LoadFile()` throws; caught and logged
- **Property suffix detection:** Relies on naming convention (SensesOS, SensesOC, etc.) (`liblcm_extractor.py:384-398`)
  - *Brittle:* If FieldWorks renames properties (e.g., `SensesOS` -> `SenseSequence`), relationships aren't detected
- **MultiString detection:** Checks type name (IMultiString, IMultiUnicode) + presence of `get_String`/`set_String` methods (`liblcm_extractor.py:367-381`)
  - *Brittle:* If MultiString API changes (e.g., add method parameter), detection may miss it
- **Namespace filtering:** Hard-coded target namespaces (`liblcm_extractor.py:190-199`)
  - *Brittle:* If types move to a new namespace (e.g., SIL.LCModel.Misc), they're excluded
- **Reflection API assumptions:** Expects `PropertyType.Name`, `ParameterType.Name`, etc. to be available
  - *Loud failure:* If reflection API changes, `GetProperties()` / `GetMethods()` throws

Example reflection flow (`liblcm_extractor.py:654-759`):

```python
# Load assemblies via pythonnet
assemblies = load_assemblies(assembly_paths, dll_dir)
# Reflect types from target namespaces
types = reflect_types(assemblies)  # Uses pre-compiled regex on namespace
# For each type, extract properties (PublicInstance | DeclaredOnly)
for p in t.GetProperties(BindingFlags.Public | BindingFlags.Instance):
    # Check property name suffix (OS, OC, RS, RC, OA, RA)
    kind = determine_property_kind(p.Name)
    # Extract element type from generic args
    element_type = get_element_type(p.PropertyType)
    # Check MultiString by type name + method presence
    is_ms = is_multistring_type(p.PropertyType)
```

### Silent vs. loud failures

| Change | Flexicon | LibLCM | Impact |
|--------|----------|--------|--------|
| Rename method (GetX -> ReadX) | Silent (wrong category) | Silent (still extracted, wrong semantics) | AI generates wrong code |
| Change docstring format | Silent (no description) | N/A | Search/discovery fails |
| Move type to new namespace | N/A | Silent (type excluded) | Missing API surface |
| Rename property suffix (OS -> Seq) | Silent (no relationship) | Silent (no relationship) | AI doesn't know about container |
| Remove MultiString method (set_String) | Silent (type detected as plain) | Silent (type detected as plain) | AI tries direct assignment |

**Upstream change resilience summary:**
- AST extraction (Flexicon): will silently misclassify if naming conventions change
- Reflection extraction (LibLCM): will silently exclude types if namespaces change
- No integration tests comparing refreshed indexes against known-good baselines
- No diff tooling to detect breaking changes (e.g., removed method, renamed property)

---

## 4. Contract / Schema: Defined but Not Validated

**Schema definitions:**

| File | Schema ID | Standard |
|------|-----------|----------|
| liblcm_api_v11.0.0.json | `unified-api-doc/2.0` | Custom (no published spec) |
| flexicon_api_v4.1.2.json | `unified-api-doc/2.0` | Custom (no published spec) |
| flexlibs_api_v1.2.8.json | `unified-api-doc/2.0` | Custom (no published spec) |
| navigation_graph_liblcm-v11.0.0.json | `navigation-graph/1.0` | Custom (no published spec) |
| casting_index_liblcm-v11.0.0.json | (none - implicit) | Custom (no published spec) |
| reverse_mapping_liblcm-v11.0.0.json | `reverse-mapping/1.0` | Custom (no published spec) |
| common_patterns_flexicon-v4.1.2.json | `common-patterns/1.0` | Custom (no published spec) |

**unified-api-doc/2.0 structure** (from liblcm_api_v11.0.0.json):

```json
{
  "_schema": "unified-api-doc/2.0",
  "_source": { "type": "liblcm", "version": "11.0.0", "description": "...", "url": "..." },
  "metadata": {
    "total_types": 0, "total_interfaces": 0, "total_classes": 0,
    "total_methods": 0, "total_properties": 0, "total_relationships": 0,
    "namespaces": ["..."], "categories": { "<category>": 0 }
  },
  "entities": {
    "<type_id>": {
      "id": "<type_id>", "name": "<type_name>",
      "type": "interface|class|enum|struct|abstract_class",
      "namespace": "<namespace>", "category": "<category>",
      "properties": [ { "name": "...", "type": "...", "kind": "...", "relationship": "..." } ],
      "methods": [ { "name": "...", "signature": "...", "return_type": "...", "parameters": [] } ]
    }
  },
  "categories": { "<category>": { "description": "...", "entities": ["<id>"] } },
  "relationships": [ { "source": "...", "property": "...", "type": "...", "target": "..." } ]
}
```

**Validation at runtime:**
- Minimal: `json.load()` validates JSON syntax only
- No schema validation: no JSONSchema file, no `jsonschema.validate()` call
- No entity count checks (e.g., `total_types == len(entities)`)
- No relationship validation (source/target entities exist)
- No diff against previous version (no breaking-change detection)

**Validation at index generation:**
- `sort_json_arrays()` called before write in both extractors (consistent ordering only)
- No other validation: no entity count checks, no relationship validation

**File-level validation in `scripts/validate_integrity.py`:**
- Does not validate index schema completeness
- Does not check entity counts

**Assessment:** Schema is defined informally in docstrings/comments but not in a published JSON Schema file. Validation is absent - only syntax checking. No drift detection or breaking-change warnings.

---

## 5. Release / Change Process: Documented, Tag-Driven

**Version source:**
- Single source: `VERSION` file (read by pyproject.toml as `dynamic = ["version"]`)
- Example: `2.3.3` -> published as `flextools-mcp==2.3.3` on PyPI

**CHANGELOG (`CHANGELOG.md:1-194`):**
- Entries per version (e.g., [2.3.3] - 2026-07-06)
- Grouped by: Index, Internal, Features, Fixes, Tests, Docs, Observability, Known Limitations
- Minimal format - free text, no structured template

**Release process (`RELEASING.md:1-138`):**

Automated (preferred):
1. Bump VERSION file + update CHANGELOG.md
2. Commit: `git commit -am "release: X.Y.Z"`
3. Tag: `git tag vX.Y.Z`
4. Push: `git push && git push --tags`
5. `.github/workflows/publish.yml` triggers on `push tags v*`: builds wheel + sdist, runs `twine check`, uploads to PyPI via Trusted Publishing (OIDC); no API token stored in repo

Manual fallback:
1. Optional: `python -m flextoolsmcp.refresh` (refresh bundled indexes)
2. Bump VERSION
3. `rm -rf dist build; python -m build`
4. Optional: TestPyPI dry-run
5. `uv publish` or `uvx twine upload dist/*`

**Pre-release testing:**
- No formal QA gate; manual testing recommended

**Git conventions:**
- Tag format: `vX.Y.Z`; commit message `release: X.Y.Z` (convention, not enforced)
- No branch protection rules mentioned

**Assessment:** Release process is mature, automated, and well-documented. Tag-driven CI with Trusted Publishing is industry-standard. Minor friction: manual CHANGELOG updates and no rollback strategy documented.

---

## 6. Drift Detection & Index Diff Tooling: Absent

**What exists:**
- None. No tooling to detect breaking changes between index versions.
- No script to compare `flexicon_api_v4.1.1.json` vs `flexicon_api_v4.1.2.json`
- No warning if a method is removed or renamed
- No validation that entity count is increasing/consistent
- Archive directory (`index/flexlibs/archive/`) is storage only, not comparison

**What's needed but missing:**
- Breaking-change detection: removed methods, renamed properties, type namespace changes
- Index diff report: adds/removals/modifications between versions
- Coverage regression check: warn if entity count drops
- Entity count validator: `metadata.total_types == len(entities)`
- Relationship validator: relationship targets exist in entities
- Schema evolution tracker: document when unified-api-doc schema changes

**Closest alternative:**
- Git history of index files shows raw JSON diffs, but no structured analysis

**Assessment:** No drift detection or index-diff tooling exists. This is the largest gap in standardization.

---

## Weakest Points (Where Silent Breaks Lurk)

Ranked by severity:

### 1. Naming convention coupling (CRITICAL)
- Flexicon/LibLCM extraction relies entirely on method names (GetX, SetX, CreateX) and property suffixes (OS, OC, etc.)
- Silent break: `GetHeadword` -> `ReadHeadword` or `SensesOS` -> `SenseSequence` fails silently
- No guard: no test comparing refreshed index against known-good baseline
- Files: `flexicon_analyzer.py:800-900` (method categorization), `liblcm_extractor.py:384-398` (property suffix detection)

### 2. Docstring parsing (HIGH)
- Analyzer assumes triple-quoted docstrings as `ast.Expr` with `ast.Constant`
- Silent break: docstring convention change -> descriptions vanish
- No guard: no integration test checking docstring count above a floor
- File: `flexicon_analyzer.py:181-192`

### 3. Namespace filtering in LibLCM (MEDIUM)
- Reflection only includes hardcoded target namespaces
- Silent break: new namespace (e.g., SIL.LCModel.NewModule) silently excluded
- No guard: no check that type count is stable/increasing
- File: `liblcm_extractor.py:190-199`

### 4. Version mismatch fallback (MEDIUM)
- Server silently falls back to latest index when no exact version match
- Silent break: FieldWorks upgraded 11 -> 12, no v12 index, server uses stale v11 API silently
- No guard: no startup warning surfaced to user
- File: `src/server.py:318-357`

### 5. No relationship validation (MEDIUM)
- `relationships` list has target references but no existence validation
- Silent break: skipped type -> dangling relationship targets -> resolver failures
- File: `liblcm_extractor.py:890-901`

### 6. Caching without invalidation (LOW-MEDIUM)
- `_file_discovery_cache` lives process-lifetime with no invalidation
- File: `server/versioning.py:23`

### 7. No schema validation (LOW)
- Generated indexes are valid JSON but completeness is not validated
- File: `flexicon_analyzer.py` (document stamping without validation)

---

## Recommendations for Hardening

1. **Integration tests** comparing refreshed index against known-good baseline:

```python
def test_flexicon_api_index_stability():
    prev = load_json("index/flexicon_api_v4.1.1.json")
    curr = load_json("index/flexicon_api_v4.1.2.json")
    assert len(curr["entities"]) >= len(prev["entities"]), "entity count regression"
    assert all(meth in curr_methods for meth in prev_methods), "method removal"
```

2. **Schema validation** at index generation time:

```python
from jsonschema import validate
validate(instance=api_doc, schema=unified_api_doc_2_0_schema)
```

3. **Breaking-change detection** in refresh script:

```python
def detect_breaking_changes(prev, curr):
    removed = set(prev["entities"]) - set(curr["entities"])
    if removed:
        print(f"WARNING: Removed entities: {removed}")
```

4. **Log version mismatch at WARN level:**

```python
if installed_version and not api_path:
    _log_warning(f"No index for {library_name} {installed_version}; using latest fallback")
```

5. **Entity/relationship count assertions** after generation:

```python
assert api_doc["metadata"]["total_types"] == len(api_doc["entities"])
for rel in api_doc["relationships"]:
    assert rel["source"] in api_doc["entities"], f"dangling source: {rel['source']}"
```

---

## Summary Table

| Area | Maturity | Coverage | Validation | Drift Detection |
|------|----------|----------|-----------|-----------------|
| Tests | Mature (20 pytest files) | Good (async, validators, casting, version detect) | Static AST + pre-commit hooks | None |
| Versioning | Mature (semver filenames, auto-refresh) | Complete (3 libraries, archive support) | Minimal (syntax only) | None |
| Coupling | Tight (naming conventions, AST/reflection) | ~90% (Flexicon), ~2300 types (LibLCM) | Silent failures on rename | None |
| Schema | Defined (unified-api-doc/2.0) | Informally documented | JSON syntax only | None |
| Release | Professional (tag-driven CI, Trusted Publishing) | Complete (CHANGELOG, VERSION file) | Build metadata check | None |
| Drift Detection | **Absent** | N/A | N/A | **CRITICAL GAP** |

The codebase is production-ready with thoughtful architecture, but lacks automated safeguards against silent API surface drift. The biggest risk is a Flexicon or LibLCM upstream change that breaks extraction silently (renaming, namespace relocation, docstring format change) without warning.
