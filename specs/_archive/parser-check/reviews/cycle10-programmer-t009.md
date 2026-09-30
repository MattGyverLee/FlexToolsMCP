# Cycle 10 -- Programmer T009

## What was implemented

New module `src/flextoolsmcp/server/parser_probe.py`: `ProbeResult` dataclass
(`ok`, `signal`, `expected_path`, `missing_members`, `detected_version`,
`load_error`) and `probe_parser_core(required_members, *, search_paths=None)`.
Also defines `HCPARSER_MEMBERS` / `PARSE_FILER_MEMBERS` /
`WRITE_REQUIRED_MEMBERS` constants (the read/write required-member sets
T011 will pass in) and the closed `SIGNAL_*` vocabulary. No other public
surface -- `ParserDetector`, `hc`/`GenerateHCConfig.exe` discovery, and the
engine/agent probes are left for T010/T011/T024/T025.

## Same-install check + reflective member probe

`probe_parser_core` gates in order: (1) `get_resolved_fieldworks_dir()`
(recomputed per call, no binding retained) locates the directory holding
`SIL.LCModel.dll`; `locate_liblcm_dll(dll_name="ParserCore.dll", ...)`
locates ParserCore.dll independently (it is *not* assumed to live inside
the resolved dir -- that assumption is exactly what the foreign-install
fixture violates). `ParserCore.dll` absent -> `signal=absent`; present but
`.parent != fieldworks_dir` -> `signal=foreign_install`. Neither branch
reflects, so a bad install never pays a CLR load. (2) `_load_parser_core_members`
reflects `HCParser`'s constructors/methods and `ParseFiler.ProcessParse`
via `Assembly.LoadFile` + `GetConstructors`/`GetMethods`, formatting
signatures (`_format_clr_type`) to match the fixture spelling (`string`,
`IEnumerable<int>`) -- combining the version-read precedent
(`versioning.py:262`) with the `GetMembers`/generic-unwrap precedent
(`liblcm_extractor.py:~330`), narrowed to just these two types rather than
walking the whole assembly. `required_members - found_members` drives
`incompatible_surface` / `missing_members`. Binding stays positional-only
in this module because it never *calls* a bound member (CP1 boundary); the
docstring records the positional-vs-keyword hazard for T024/T025.

## load_failed

`_load_parser_core_members` deliberately never catches; `probe_parser_core`
wraps the one call site in `try/except Exception`, mapping any throw
(SPEC 5.4's "mismatched transitive dependency" case) to
`signal=load_failed`, `load_error=str(exc)`, `missing_members=[]`,
`detected_version=None`, and returns normally -- never propagates.

## detected_version

Reported verbatim on every path that reaches reflection; never compared
against anything, anywhere in this module. `TestDetectedVersionNeverCompared`
(3 parametrized cases, implausible/malformed strings) passes.

## Results

- `tests/test_parser_probe.py`: 0/15 passing before (collection error --
  module didn't exist) -> **15/15 passing** now.
- Full suite: baseline 1437 passed / 8 skipped / 36 subtests + 37 RED
  (T008, by design) + T007 collection failure -> now **1452 passed / 37
  failed / 8 skipped / 36 subtests passed**. The 37 failures are exactly
  T008's `test_parser_health_block.py` (targets `_build_parser_block()` /
  `dh.ParserDetector`, T012/T013's job) -- unchanged in count, still RED
  as documented, not a regression.
- `ruff check src/flextoolsmcp/server/parser_probe.py`: clean.

## Discrepancies

None found between T007/T008's expectations and `data-model.md` -- T007's
seam names (`probe_parser_core`, `_load_parser_core_members`,
`get_resolved_fieldworks_dir`/`locate_liblcm_dll` reuse) matched the
implementation directly; no test-file edits were needed.

## Pyright diagnostics (lines 365,367,391,393 in test_parser_probe.py)

Unaffected by this module's layout. Those lines are the test file's own
`fake_lcmodel_module.LcmCache = _spy` / `fake_sil_module.LCModel = ...`
dynamic attribute assignments on plain `types.ModuleType` instances used to
spy on `SIL.LCModel`/`SIL` in `sys.modules` -- `parser_probe.py` never
imports or references `SIL`/`SIL.LCModel` at all (only `System` /
`System.Reflection` inside `_load_parser_core_members`), so there is no
module-layout choice on my side that changes what pyright sees there. A
follow-up fix, if wanted, belongs to the test file itself (e.g. a `Protocol`
or `cast` at the assignment site) -- out of scope here since T009 must not
edit `tests/test_parser_probe.py`.
