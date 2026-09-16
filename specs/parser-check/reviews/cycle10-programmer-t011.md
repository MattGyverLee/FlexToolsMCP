# Cycle 10 -- Programmer T011

## Shape and composition

Added to `src/flextoolsmcp/server/parser_probe.py`: `SandboxProbe` (`hc`,
`generate_config`), `AgentProbeState` (`state`, `agent_guid`, `active_engine`)
with closed `AGENT_STATE_PRESENT`/`ABSENT`/`SKIPPED` constants, `ParserVersions`
(`parser_core_version`, `lcmodel_install_path`, `hc_tool_version`), a
`probe_hc_agent()` stub (pinned name for T025, always returns `skipped`, never
called at CP1), and the `ParserDetector` class itself -- constructed with no
required positional args (`search_paths` is keyword-only), eagerly populating
`read_probe`/`write_probe`/`sandbox_probe`/`agent_probe`/`active_engine`/
`versions` as plain attributes in `__init__`. `read_probe`/`write_probe` call
T009's `probe_parser_core` over `HCPARSER_MEMBERS`/`WRITE_REQUIRED_MEMBERS`;
`sandbox_probe.hc`/`.generate_config` call T010's `discover_hc_tool`/
`discover_generate_hc_config`. `versions.lcmodel_install_path` reuses T009's
`get_resolved_fieldworks_dir()` (already imported); no new location/reflection
logic added anywhere in this file.

## Structural independence of the three spines

Each of `read_probe`, `write_probe`, `sandbox_probe.hc`, `sandbox_probe.
generate_config` is computed by its own statement in `__init__`, each wrapped
individually by a new `_safe_probe(compute, *, expected_path=None)` helper
that catches `Exception` and maps it to `ProbeResult(ok=False,
signal=SIGNAL_LOAD_FAILED, ...)`. There is no enclosing try/except or shared
early-return spanning more than one spine's computation, so a throw while
computing one spine cannot prevent the statements computing the others from
running -- verified by inspection (four independent `_safe_probe` call sites)
and empirically (`ParserDetector(search_paths=[])` against a missing
FieldWorks install returns all four sub-probes populated with
`signal="absent"`/`not_found`, none `None`).

## `agent_probe`/`active_engine` cannot read as a pass

`agent_probe` is unconditionally `AgentProbeState(state=AGENT_STATE_SKIPPED,
agent_guid=None, active_engine=None)` -- a distinct three-valued `state`
string, never coerced to or folded into `ok=True`/`"present"`. `active_engine`
(top-level) is unconditionally `None`. Both are set directly in `__init__`
with a comment citing D2/D8, never derived from `read_probe`/`write_probe`.
`write_probe`'s `ok` comes only from `probe_parser_core(WRITE_REQUIRED_MEMBERS)`
-- `agent_probe` is never read anywhere in `__init__`'s write-probe
computation.

## No version comparison

`versions.parser_core_version`/`hc_tool_version` are copied verbatim from
`read_probe.detected_version`/`write_probe.detected_version`/`hc_probe.
detected_version` -- no `<`, `>=`, `==` against a literal anywhere in the new
code. `TestDetectedVersionNeverCompared` still passes.

## Pyright

Ran `pyright` on the file: 0 errors/warnings. The `os`/`shutil`/`subprocess`
imports flagged in the task prompt are not actually unused in the current
tree -- T010 already consumes them (`os.environ` in `_hc_override_from_env`,
`shutil.which` in `_find_hc_via_path`, `subprocess.run` in
`_find_hc_via_dotnet_tool_list`); `clr` still carries its existing
`# noqa: F401` + `# pyright: ignore[reportUnusedImport]` from T010. Nothing
left to clear.

## Results

`tests/test_parser_probe.py`: 15/15, unchanged. `ruff check`: clean. Full
suite, measured before/after this addition (T009+T010-only file vs. current):
before 104 failed / 1515 passed / 8 skipped; after 102-103 failed / 1515-1516
passed / 9 skipped (small run-to-run variance from an unrelated flaky
`test_mcp_tools.py` case seen once, not reproducible, not touched by this
file). All failures confined to the five documented in-flight files
(`test_grammar_health.py` 14, `test_grammar_scan_checks.py` 19,
`test_parser_agent_probe.py` 16, `test_parser_engine_gate.py` 16,
`test_parser_health_block.py` 37 -- unchanged, still T012/T013's job). One
`test_parser_agent_probe.py` case
(`TestAgentProbeStateClosedEnum::test_case_sensitive_when_backed_by_an_enum`)
moved from failing to self-skipping now that `AgentProbeState` exists (it
explicitly `pytest.skip`s when the type isn't a Python `enum.Enum`, which
mine deliberately isn't -- a dataclass with a plain `state: str`, matching
`ProbeResult`'s existing style). No regression outside the documented set.
