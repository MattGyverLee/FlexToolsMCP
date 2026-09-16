# Cycle 10 -- Programmer T010

## What was added

Two discovery functions in `src/flextoolsmcp/server/parser_probe.py`, plus
supporting constants (`COMPONENT_HC`, `COMPONENT_GENERATE_HC_CONFIG`,
`SANDBOX_COMPONENTS`, `HC_INSTALL_HINT`, `HC_EXPECTED_PATH_DESCRIPTION`,
`HC_PATH_ENV_VAR`, `HC_DISCOVERY_TIMEOUT_SECONDS`,
`SANDBOX_SIGNAL_NOT_FOUND`/`SANDBOX_SIGNAL_TIMEOUT`) for T011 to wire into
`ParserDetector.sandbox_probe = {hc, generate_config}`. No `ParserDetector`,
no engine gate, no agent probe -- out of T010's scope.

## `hc` discovery

`discover_hc_tool(*, override_path=None, timeout=HC_DISCOVERY_TIMEOUT_SECONDS)`
tries three lookups in order: (1) `override_path` or the `HC_TOOL_PATH` env
var -- the "config override" SPEC 13 H1 calls for, mirroring
`versioning.py`'s `FIELDWORKS_DLL_PATH` precedent, for PATH-restricted
environments and dotnet-free tests; (2) `shutil.which("hc")`, the common
case once the dotnet tools shim dir is on PATH; (3) `dotnet tool list -g`,
parsed for an `hc` row. Never touches `%LOCALAPPDATA%\HermitCrabTool\hc.dll`.

## Timeout

`HC_DISCOVERY_TIMEOUT_SECONDS = 5.0`, a module-level constant, bounds
`subprocess.run([dotnet, "tool", "list", "-g"], timeout=timeout)` inside
`_find_hc_via_dotnet_tool_list`. `subprocess.TimeoutExpired` is caught there
and reported back as `(None, "dotnet tool list -g exceeded {timeout}s
timeout", timed_out=True)`. `discover_hc_tool` maps `timed_out=True` to
`signal=SANDBOX_SIGNAL_TIMEOUT` ("timeout"); every other not-found path
(dotnet absent, `hc` not listed, non-hc-related failure) maps to
`SANDBOX_SIGNAL_NOT_FOUND` ("not_found") -- two distinct, closed signals so a
hang is never indistinguishable from a plain miss. `load_error` always
carries the diagnostic text. No exception path can propagate out of
`discover_hc_tool`.

## `GenerateHCConfig.exe` discovery

`discover_generate_hc_config(*, search_paths=None)` is a plain filesystem
check, not a subprocess call -- no timeout needed. It reuses T009's own
`get_resolved_fieldworks_dir()` / `locate_liblcm_dll(dll_name=...)`
precedent verbatim (same pattern as `probe_parser_core`'s `ParserCore.dll`
lookup), since the exe ships with FieldWorks rather than as a dotnet tool.

## `clr` diagnostic (line 209)

Not fixed as a removal -- it is not a genuine unused import. `import clr`
is a deliberate availability probe: pythonnet's `clr` module import itself
raises `ImportError` when pythonnet is absent, which is the signal
`probe_parser_core` relies on to map to `signal="load_failed"`; the name
`clr` is never referenced afterward by design (already documented by the
existing `# noqa: F401` comment). Removing it would silently defeat that
check. Instead added `# pyright: ignore[reportUnusedImport]` alongside the
existing comments to quiet the diagnostic without weakening the probe.

## Results

- `tests/test_parser_probe.py`: 15/15 before and after (unchanged, still
  green).
- `python -m ruff check src/flextoolsmcp/server/parser_probe.py`: clean.
- Full suite: 141 failed / 1478 passed / 8 skipped / 36 subtests, all in
  `tests/test_grammar_health.py` (52), `tests/test_grammar_scan_checks.py`
  (19), `tests/test_parser_agent_probe.py` (17), `tests/test_parser_engine_gate.py`
  (16), `tests/test_parser_health_block.py` (37 -- unchanged count, T012/T013's
  job, expected RED). No failure outside these five known in-flight/expected
  files; no regression introduced by this change.
