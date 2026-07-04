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
