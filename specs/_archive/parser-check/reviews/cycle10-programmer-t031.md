# T031 report -- GrammarHealthChecker reflection probe

**Assembly probed.** `C:\Program Files\SIL\FieldWorks 9\SIL.Machine.Morphology.HermitCrab.dll`
(assembly version `3.8.2.0`), directory resolved via `get_resolved_fieldworks_dir()`
(`versioning.py:204`) -- the same-install accessor `parser_probe.py` (T009) already
uses. Same-directory dependencies `SIL.Core.dll` (`18.0.0.0`) and `SIL.Machine.dll`
(`3.8.2.0`) were also loaded, for reasons below.

**Method.** Pure reflection: `Assembly.LoadFile` + `GetTypes()`/`GetMembers()`,
reusing `parser_probe.py`'s own idiom verbatim rather than inventing a new one. A
bare `LoadFile` + `GetTypes()` on the target DLL throws
`ReflectionTypeLoadException` on this machine -- the identical failure
`probe_parser_core(HCPARSER_MEMBERS)` itself hits for `ParserCore.dll` here
(independently reproduced), caused by `Assembly.LoadFile` not probing the loaded
file's own directory for dependencies on this .NET Framework runtime. Pre-loading
the two same-directory dependency DLLs via `Assembly.LoadFile` (loads metadata
only, executes nothing) resolved this: `GetTypes()` then returned all 195 types
with no exception -- a complete, unambiguous scan, not a partial one.

**Verdict: NOT PRESENT.** No type named `GrammarHealthChecker` exists among the
195 fully-resolved types, and no type whose name contains `Grammar`, `Checker`,
or `Health` exists anywhere in the assembly. Stronger than "present but not
public" -- absent outright from the exact namespace/assembly the fully-qualified
name targets.

**Decision: defer to CP2.** The type doesn't exist on this installed toolchain,
so there's no free capability to fold into T034/T035. Independent of that,
folding it in would still couple CP1's pure-LCM scan (D1) to the HermitCrab
assembly and cross the CP1 boundary -- the deferral holds even under a future
SIL.Machine release that adds the type. Recorded as scoped to this machine's
installed version (`3.8.2.0`), not asserted for other installs.

**Confirmations.** Nothing was instantiated; no grammar loaded; no parser
constructed -- only `Assembly.LoadFile`/`GetTypes`/`GetMembers` reflection calls.
All probe scripts lived in and were deleted from the scratchpad directory; nothing
was added under `src/` or `tests/`. `research.md` diff is append-only: `## D10`
added at the end (118 new lines including the leading `---` separator); D1-D9's
bytes are a verified unchanged prefix of the new file content (confirmed by
direct byte comparison against `git show HEAD:...research.md` plus the
pre-existing uncommitted D8/D9 additions already in the working tree before this
task started).
