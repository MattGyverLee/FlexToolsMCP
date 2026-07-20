# Releasing FLExToolsMCP to PyPI

FLExToolsMCP is published to [PyPI](https://pypi.org/) as **`flextools-mcp`**.
Users install it with `uvx flextools-mcp` / `pip install flextools-mcp`.

There are two ways to release:

- **Automated (preferred, tag-triggered):** push a `vX.Y.Z` tag and the
  [`Publish to PyPI`](.github/workflows/publish.yml) GitHub Action builds and
  uploads via **Trusted Publishing** (OIDC — no token stored anywhere). See
  [Automated release](#automated-release) below.
- **Manual:** run the build + upload from your machine. See
  [Manual release](#manual-release).

> The indexed API documentation ships inside the wheel as package data, so a
> release is just: refresh (if needed) -> bump version -> build -> upload.

## Automated release

### One-time: register the trusted publisher on PyPI

- **First release ever** (project does not exist yet): add a *pending
  publisher* at https://pypi.org/manage/account/publishing/ with:
  - PyPI project name: `flextools-mcp`
  - Owner: `MattGyverLee`  ·  Repository: `FlexToolsMCP`
  - Workflow: `publish.yml`  ·  Environment: `pypi`
- **After the project exists:** the same settings live at
  https://pypi.org/manage/project/flextools-mcp/settings/publishing/

No API token is created or stored — GitHub exchanges a short-lived OIDC token
at publish time. (Optionally add a `pypi` environment in the repo's
Settings -> Environments with required reviewers to gate releases.)

### Cut a release

```bash
# 1. bump VERSION (+ CHANGELOG), commit
# 2. tag and push
git commit -am "release: X.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```

The tag push triggers the workflow: it builds the wheel + sdist, runs
`twine check`, and publishes to PyPI. Watch it under the repo's **Actions** tab.
`workflow_dispatch` also lets you run it manually from that tab.

## Manual release

## One-time setup

1. A PyPI account with 2FA enabled: https://pypi.org/manage/account/
2. An API token: https://pypi.org/manage/account/token/
   - For the **first** upload the project does not exist yet, so create an
     **account-scoped** token.
   - After the first release, create a **project-scoped** token for
     `flextools-mcp` and use that going forward.
3. Build tooling (already in the dev extra): `pip install -e ".[dev]"`, plus
   `build` and `twine`/`uv` available (`uvx` fetches twine on demand).

## Release procedure

### 1. (Optional) Refresh the bundled indexes

Only when LibLCM / FlexLibs / Flexicon changed and you want the new API surface
baked into this release. Requires FieldWorks DLLs + `.env` paths on Windows.

```bash
python -m flextoolsmcp.refresh          # or: python src/flextoolsmcp/refresh.py
git add src/flextoolsmcp/index
```

### 2. Bump the version

PyPI **rejects re-uploading an existing version**, so every release needs a new
number. The version is single-sourced from the `VERSION` file (read by
`pyproject.toml` via `dynamic = ["version"]`).

```bash
# edit VERSION, e.g. 2.3.0 -> 2.3.1
```

Keep `CHANGELOG.md` in step with the new version.

### 3. Build the artifacts

```bash
rm -rf dist build src/*.egg-info      # clean, so stale builds are not uploaded
python -m build                        # -> dist/flextools_mcp-X.Y.Z-py3-none-any.whl + .tar.gz
```

The wheel filename uses `flextools_mcp` (PyPI normalizes the hyphen to an
underscore in filenames); the project name stays `flextools-mcp`.

### 4. (Recommended) Dry-run on TestPyPI

```bash
uvx twine upload --repository testpypi dist/*
# smoke-test the uploaded package actually runs:
uvx --index https://test.pypi.org/simple/ flextools-mcp
```

### 5. Upload to PyPI

```bash
uv publish                             # or: uvx twine upload dist/*
```

Credentials:
- **twine**: username `__token__`, password is the `pypi-...` token
  (or set `TWINE_USERNAME=__token__` / `TWINE_PASSWORD=pypi-...`).
- **uv**: set `UV_PUBLISH_TOKEN=pypi-...`.

### 6. Verify the live release

```bash
uvx flextools-mcp@latest               # pulls from PyPI and starts the server
```

Then tag the release in git:

```bash
git commit -am "release: X.Y.Z"
git tag vX.Y.Z
git push && git push --tags
```

## Notes

- **User data** (logs, saved skeletons, cached models, runtime-refreshed
  indexes) lives under `~/.flextoolsmcp/` and persists across upgrades; it is
  never written into the installed package.
- **Dependencies** (including `pyflexicon`) are declared in `pyproject.toml`.
  `requirements.txt` mirrors them for source development; keep the two in sync.
- The automated path (tag -> GitHub Action -> Trusted Publishing) is the
  preferred way to release; the manual steps above are the fallback and are
  also what the workflow runs internally.

---

## Pre-release Checklist

Before tagging any release, verify:

- [ ] `pytest` exits green with no failures or errors (this includes the
      Tier-1 eval corpus under `tests/evals/corpus/` -- it runs as part of
      the normal suite and is a hard CI gate; see [Eval harness](#eval-harness)
      below).
- [ ] `python scripts/validate_integrity.py all` exits clean.
- [ ] If indexes changed: review the index diff and confirm it reflects
      the intended API surface changes.
- [ ] **Tier-2 live evals run and headline numbers pasted into CHANGELOG**
      (see [Eval harness](#eval-harness) below). Manual, pre-release only --
      never CI-required. Report medians over 2 runs; note as N/A only if
      skipped for a patch release with no assistant-facing changes (tool
      descriptions, preflight gates, or index content).
- [ ] `CHANGELOG.md` entry written for this version.
- [ ] `VERSION` file bumped to the new version number.
- [ ] TestPyPI dry-run completed and the uploaded package starts without
      errors (`uvx --index https://test.pypi.org/simple/ flextools-mcp`).

---

## Eval harness

Issue #51 added a two-tier eval harness under `tests/evals/` to catch
first-pass-green regressions before they reach users (motivated by #26 --
zero modules saved in 13 sessions -- and #29 -- 7/13 sessions rejected on
op #1 -- both only caught after the fact by reading production logs).

### Tier 1 -- replay corpus (automatic, CI-gated)

`tests/evals/corpus/*.yaml` holds ~30 scripts with expected preflight gate
outcomes (`expect.outcome: ok | preflight_reject` + `expect.error_code`).
`tests/evals/test_corpus.py` drives the preflight validator chain directly
(no LLM, no FieldWorks project, no subprocess) via
`tests/evals/preflight_runner.py`. It runs as part of the normal `pytest`
invocation -- nothing extra to do at release time beyond making sure the
suite is green.

**If a PR changes gate behavior** (a corpus entry's `expect.outcome` flips),
the YAML must be updated in the same PR -- that diff IS the review artifact
for the gate-behavior change, same philosophy as the index-diff gate above.

### Tier 2 -- live LLM task evals (manual, pre-release only)

`tests/evals/tasks/*.yaml` holds ~15 task prompts (intent only, no code) --
e.g. "Find all entries whose citation form differs from lexeme form and
report them". `tests/evals/tier2_runner_skeleton.py` documents the shape of
a runner that would drive a real assistant session against the MCP server
and emit the same JSONL schema as production telemetry (so
`scripts/green_report.py`-style tooling can render it) -- **the skeleton is
not wired to a live LLM**; it's a documented harness contract for whoever
runs Tier 2 by hand (or automates it later) to fill in.

Run before each release:

1. Opt in: `FLEXTOOLSMCP_LIVE_EVALS=1`
2. Drive each task in `tests/evals/tasks/*.yaml` against a real assistant
   session connected to this MCP server, using a real (test/sample)
   FieldWorks project matching the task's `project` field.
3. Record turns-to-green per task against `success_check`.
4. Paste headline numbers into `CHANGELOG.md`, e.g.:

   ```
   eval: 13/15 tasks green, median 1 turn, was 11/15
   ```

Cost control: Tier 2 is opt-in and manual -- **never** made a CI-required
gate. Report medians over 2 runs rather than a single run (turn count is
somewhat noisy across sessions).

---

## Rollback Procedure

PyPI **does not allow re-uploading a yanked version** under the same
version number. If a bad release reaches PyPI, follow these steps:

### 1. Yank the bad release on PyPI

Go to https://pypi.org/manage/project/flextools-mcp/releases/ and yank
the affected version. A yanked release is hidden from `pip install` without
an exact pin but is not deleted; existing pinned installs still resolve it
(they receive a deprecation warning).

### 2. Publish a replacement

You have two options:

- **Patch bump (preferred):** Fix the issue on `main`, bump to the next
  patch version (e.g. 2.3.3 -> 2.3.4), and publish normally via tag push.
- **Post-release:** If the code is correct but only metadata/packaging was
  broken, you may publish a `.postN` release (e.g. `2.3.3.post1`) from the
  same commit. Use this sparingly; prefer a patch bump for clarity.

### 3. Document both events in CHANGELOG

Add a note under the replacement version's entry:

```
### Packaging
- Replaced yanked v2.3.3 (reason: <brief description>). PyPI yank applied
  to v2.3.3; v2.3.4 is the safe replacement.
```

This ensures the history is auditable and users who read the changelog
understand why the version sequence skipped or doubled.
