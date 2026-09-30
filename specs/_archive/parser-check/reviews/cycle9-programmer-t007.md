# T007 -- Probe tests (cycle 9)

**File:** `tests/test_parser_probe.py` (new, 300 lines).

## In-flight-test marking convention

Grepped `tests/*.py` for `xfail`/`importorskip`/skip-guard precedent for a
module that doesn't exist yet: none found. The closest convention
(`test_lazy_loader_diagnostics.py`, `test_v1_3_0_upgrade.py`,
`test_issue96_teardown_visibility.py`) is `except ImportError` as
*production-code* graceful degradation, not a test-collection pattern.
Chose **plain, undecorated tests**: a top-level `from flextoolsmcp.server
import parser_probe` that fails loudly with `ModuleNotFoundError` at
collection time until T009 lands. Documented the choice and rationale in
the file's module docstring.

## Tests added (7 classes)

- `TestProbeResultInvariant` -- `ok=True` implies `missing_members == []`
  and `signal is None`; signal is always in the closed vocabulary or `None`.
- `TestForeignInstallSignal` -- ParserCore resolved from a directory other
  than SIL.LCModel.dll's yields `signal=foreign_install`; same-install
  does not.
- `TestIncompatibleSurfaceSignal` -- missing `ParseFiler.ProcessParse`
  yields `signal=incompatible_surface` naming it in `missing_members`; the
  same location still passes the *read*-only required set (`read: ready`,
  `write: unavailable`).
- `TestDetectedVersionNeverCompared` -- parametrized over a suspiciously
  low, suspiciously high, and malformed version string; all three must
  pass with `detected_version` echoed verbatim. This is the standing
  regression guard: it fails the moment anyone adds a floor comparison,
  regardless of comparison strategy (numeric, semver, lexicographic).
- `TestLoadFailedSignal` -- an `Assembly.LoadFile`-throw maps to
  `signal=load_failed` with non-null `load_error` containing the original
  message, and the throw never propagates out of the probe.
- `TestCP1Boundary` -- two tests spying on a faked `SIL.LCModel.LcmCache`
  across (a) the real "DLL not found" short-circuit and (b) all three
  fixture-driven signal scenarios; asserts zero `LcmCache` construction
  calls in every case.

## Assumptions / invented contract (not pinned by data-model.md)

Only `ProbeResult`'s fields and the signal vocabulary are pinned. The
probe entry point's name (`probe_parser_core(required_members, *,
search_paths=None)`) and its assumed internal seams
(`get_resolved_fieldworks_dir`, `locate_liblcm_dll` reused from
`versioning.py`; a new `_load_parser_core_members(dll_path)` reflection
seam) are this file's own design choice, documented at length in the
module docstring so T009's author can reconcile or rename. Patched
`get_resolved_fieldworks_dir`/`locate_liblcm_dll` in both `parser_probe`
and `versioning` (both `raising=False`) to tolerate either import style.

## Fixture note (no changes made)

`FakeParserCoreLocation.same_install` (T002) does raw string equality
between `.parser_core_dir` and `.lcmodel_dir`, which always holds full DLL
*file* paths (including filename) -- so it evaluates `False` for every
existing fixture instance, including `COMPLETE_SAME_INSTALL_PARSER_CORE`.
Did not touch `fixtures/parser_check.py` (not owned this cycle); my tests
derive directory identity themselves via `Path(...).parent` instead of
using `.same_install`. Flagged in the file docstring for whoever next
touches that fixture.

## Verification

- `python -m pytest tests/test_parser_probe.py -q` -- 1 collection error
  (`ModuleNotFoundError: cannot import name 'parser_probe'`), as intended.
- `python -m ruff check tests/test_parser_probe.py` -- all checks passed.
- `python -m pytest tests/ -q --continue-on-collection-errors` --
  **1437 passed, 8 skipped, 36 subtests passed** (exact match to the
  cycle-8 baseline; no regression), plus **1 error** (this file) and
  **37 failed** in `tests/test_parser_health_block.py` (the parallel
  agent's file, also pre-implementation-red against the same missing
  module -- not mine, not investigated further).

No blockers.
