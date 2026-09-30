# Cycle 3 -- Programmer: CP1 landing zone in diagnostic_health.py / versioning.py

## 1. Where detectors belong

New module: `src/flextoolsmcp/server/parser_probe.py`. `diagnostic_health.py`'s
docstring claim ("pure COMPOSITION... no new detection logic") is a contract
other code/tests rely on; relaxing it papers over scope creep. `versioning.py`
is the wrong host too -- it's generic semver/file-discovery plumbing with zero
.NET-object-graph knowledge; CP1's "same install" + "surface exists" checks
are parser-domain. Recommendation: `parser_probe.py`, imported by
`diagnostic_health.py` exactly like `versioning.py`/`project_access.py` are
today (lines 52-69, 71-74). Tradeoff: one more import block and a fourth
`_LIBRARY_SPECS`-style entry; acceptable, keeps the docstring literally true.

## 2. Does locate_liblcm_dll retain the resolved directory

No. `locate_liblcm_dll()` (versioning.py:178-201) is pure -- takes
`search_paths` (or rebuilds via `_default_liblcm_search_paths()`), returns a
fresh `Path` per call, no module-level memoization (unlike
`find_versioned_api_file`, which caches on a dir-state token).
`_build_fieldworks_block()` (diagnostic_health.py:169-179) calls it fresh:
`dll_path = locate_liblcm_dll()`. Nothing stores "which install did we bind"
across calls today.

Smallest change: `locate_liblcm_dll()` already returns the full DLL path, so
`dll_path.parent` *is* the install dir -- add a thin wrapper
`get_resolved_fieldworks_dir() -> Optional[Path]` (= `locate_liblcm_dll().parent`
or None) and have `_build_fieldworks_block()` and the new parser probe both
call it. No caching needed for correctness (recomputation is cheap -- filesystem
checks only, per versioning.py:190-192's own docstring), just a shared accessor.

## 3. THE SHARP ONE

(a) No. No `MetadataLoadContext`/`ReflectionOnlyLoad`/out-of-process probe
exists anywhere in-repo. Precedent (grep `AddReference`/`LoadFile`/`GetTypes`)
is `liblcm_extractor.py:332` (`Assembly.LoadFile(str(path.absolute()))`) then
`GetTypes()`/`GetMethods(BindingFlags...)` (lines 402, 836, 938) -- a full
pythonnet CLR load, never metadata-only. pythonnet has no reflection-only load
mode, so following precedent means `ParserCore.dll` reflection *is* a full
load, same as `detect_liblcm_version_from_disk()` already does for
`SIL.LCModel.dll` (versioning.py:230-234).

(b) Cost/risk: loading runs static initializers and eagerly resolves
manifest-referenced dependencies even if unused. Whether `ParserCore.dll`
pulls `xCore`/FieldWorks UI assemblies at load time is agent 2's detection
question (out of scope here), but the *shape* is real: assembly load is not
side-effect-free like a file-existence check, and a mismatched transitive
dependency can throw during load, before any member is inspected.

(c) Reword 5.4. Current: "This is reflection only: no cache is opened, no
grammar is loaded, nothing is parsed." Still literally true but invites
misreading as metadata-only/zero-cost. Proposed: "This probe loads
`ParserCore.dll` into the process via reflection (the same
`Assembly.LoadFile` + `GetMethods` pattern `liblcm_extractor.py` already uses
for `SIL.LCModel.dll`) and inspects its members; it never opens an
`LcmCache`, loads a grammar, or parses a word." The CP1 test at SPEC.md:1355
("no cache opened, no grammar loaded, no parse") is about LCM-level side
effects, not CLR-load cost, so it survives the reword unchanged.

## 4. Threat to laziness

Not by itself. "Lazy" (5.4) means `import flexicon` must not eagerly load
`ParserCore.dll` -- the probe only runs when the parser facade or
`flextools_health` is invoked, matching how `locate_liblcm_dll()`/
`detect_liblcm_version_from_disk()` already behave (called from a handler,
not at import time). The real cost is per-call, not per-import: a heavier
load than a file check should be gated behind `verbose=True` or memoized,
mirroring `_build_verbose_block()`'s existing placement -- a call-site
decision, not a lazy-import violation.

## 5. Test seams

`tests\test_flextools_health.py` extends directly: `TestComputeLibraryMatch`
(tmp_path fixtures) is the template, and the `monkeypatch.setattr(dh,
"detect_installed_library_version", ...)` pattern (lines 317-318, 345-346,
368) shows precedent for faking absent/foreign installs with no real
FieldWorks box -- monkeypatch the new `parser_probe` detector the same way,
and simulate "foreign install" by pointing `locate_liblcm_dll`'s
`search_paths` and a fake `ParserCore.dll` fixture at two different
`tmp_path` dirs. No `tests\test_versioning.py` exists yet; CP1 tests for
`get_resolved_fieldworks_dir()` belong in this file or a new one.
