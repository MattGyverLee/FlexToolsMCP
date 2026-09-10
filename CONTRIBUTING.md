# Contributing to FlexToolsMCP

Thank you for contributing. This document covers dev setup, testing, and PR rules.

## Dev Setup

1. Clone the repo and create a virtual environment (Python 3.10+):

   ```
   git clone https://github.com/MattGyverLee/FlexToolsMCP
   cd FlexToolsMCP
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   ```

2. Install in editable mode with dev extras:

   ```
   pip install -e .[dev]
   ```

3. Install the pre-commit hooks (runs lint/format checks before every commit):

   ```
   pre-commit install
   ```

4. Copy and configure `.env`:

   ```
   copy .env.example .env
   # Edit .env to set paths to FieldWorks DLLs, LibLCM, FlexLibs, etc.
   ```

## Refreshing the API Indexes

When LibLCM, FlexLibs, or Flexicon changes, regenerate the bundled indexes:

```
# Refresh all indexes (requires FieldWorks DLLs + .env paths on Windows)
python src/refresh.py
```

There is no per-library flag anymore -- every run scans all available APIs,
since the reverse mapping and pattern extraction cross-link LibLCM,
FlexLibs, and Flexicon entries with each other. LibLCM is best-effort and
is skipped gracefully if FieldWorks DLLs/pythonnet are unavailable.

Commit the updated files under `src/flextoolsmcp/index/` as part of the PR.

## Running Tests

```
pytest
```

Run the integrity validator and Python-syntax checker separately:

```
python scripts/validate_integrity.py all
python scripts/verify_python.py
```

Both must exit clean before opening a PR.

### Code that lives inside text

pyright only sees `src/`. It cannot check a `python` fence in CLAUDE.md, a
`code` string in `curated_recipes`, or a docstring example in the bundled
index -- yet those are the surfaces the MCP teaches from, so a stale name
there is re-injected into every script Claude generates.

```
python scripts/check_doc_snippets.py            # gate the repo's own surfaces
python scripts/check_doc_snippets.py --upstream # + pyflexicon docstrings
```

It runs as a pre-commit hook and as `tests/test_doc_snippets.py`, so a
`refresh.py` bump to a new flexicon version turns CI red if the prose did not
follow. Upstream docstring findings are reported, never blocking -- they are
fixed at MattGyverLee/flexicon and arrive here at the next refresh. To hand
that debt to someone (or to an agent), regenerate the worklist, which
resolves every finding to a flexicon source path and line:

```
python scripts/check_doc_snippets.py --worklist reports/upstream-flexicon-docstring-findings.md
```

If a fence deliberately shows something other than current flexicon API, say
so in its info string rather than leaving the gate to guess:

````
```python doc-check=ignore
```python flavor=flexlibs_stable
````

## PR Rules

Every PR must satisfy the following before it will be merged:

1. **CHANGELOG entry** -- Add a bullet under an `[Unreleased]` heading (or
   the correct version heading) in `CHANGELOG.md` describing what changed
   and why.

2. **Extractor changes need an index diff** -- If you modify
   `flexicon_analyzer.py`, `liblcm_extractor.py`, or any build script,
   regenerate the affected index files (`python src/refresh.py`) and include
   the diff in the PR.

3. **Payload-shape changes need golden-file regen** -- If the JSON shape of
   any MCP tool response changes (new/removed/renamed keys), regenerate the
   relevant golden files in `tests/` and include them in the PR. Update any
   affected snapshot assertions.

4. **Tests green** -- `pytest` must pass with no failures or errors.

5. **Integrity validator clean** -- `python scripts/validate_integrity.py all`
   must exit 0.

6. **Pre-commit checks pass** -- The hooks run automatically on commit; fix
   any failures before pushing.

## Code Style

- Follow PEP 8. The pre-commit config enforces formatting automatically.
- Use descriptive names and include docstrings on public functions.
- Keep FLExTools script templates in the `templates/` directory.
- Windows-only paths and .NET interop (pythonnet) are expected; do not add
  cross-platform shims that paper over real incompatibilities.

## Questions

Open a GitHub Discussion or file an issue. For security issues, see SECURITY.md.
