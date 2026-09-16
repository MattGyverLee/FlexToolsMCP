# Cycle 5 -- Programmer feasibility review of tasks.md (CP1)

## P0

**T019/T020 -- the subprocess bridge does not exist; D1's "covered by the
existing preflight/casting validators" is not achievable as scoped.**
`handlers/execution.py` has no reusable "run this source text/module in the
subprocess" primitive. `handle_run_module` (execution.py:2685-4530+) is one
~1800-line function where: `code = args.get("code")` (2696) is a **string**,
validated in place via `ast.parse(code)` at 2824/3129/3587, then spliced
verbatim into a literal template (`runner_script = '''...'''`, 3714) as
`MODULE_CODE = {code}` (~4172), written to a temp file (`temp_script_path =
f.name`, 4195) and only *then* handed to `run_script_async` (4452/4458),
which just executes an already-materialized file. There is no factored
"build-and-run(code_text, project_name, write_enabled) -> result" function
a second handler can call, and validators only ever run over `code` text
supplied by a caller -- they cannot "cover" a module that already lives at
`server/scan/grammar_scan_module.py`. T019 as written ("the scan itself...
· src/flextoolsmcp/server/scan/grammar_scan_module.py") treats it as an
ordinary importable package module (T001 even gives it `__init__.py`), but
D1 (research.md:126) explicitly claims it is "authored as a module the
harness runs" and "covered by the existing preflight/casting validators" --
which is only true of the text-splice path. T020 ("runs the scan through
the existing generated-module subprocess harness") is one line covering
work that is actually: decide import-vs-text-splice, and either (a) read
the file as text and reuse/extract the casting-validator + templating
internals out of `handle_run_module` (a real refactor, not "reuse"), or (b)
author a new minimal script template that imports the module normally in
the subprocess and returns data via `report.Result()` (execution.py:3869-
3888, the only documented structured-return channel, read back via the
`===FLEXTOOLS_USER_RESULT===` sentinel at 4481-4490) -- neither of which is
its own task. Fix: add a task between T019 and T020 to build (or extract
from `handle_run_module`) the minimal subprocess entry point, and make
T019 explicit that `grammar_scan_module.py` must call `report.Result(...)`
with its findings (it currently says nothing about how results leave the
subprocess).

## P1

**T003/T006 -- new detail models are never added to `AnyDetail`, so
`validate_detail()` cannot validate them.** `response_models.py:364-382`
defines `AnyDetail = Union[SyntaxErrorDetail, ..., HvoLiteralWriteRiskDetail]`
(18 entries) and `validate_detail()` (417-444) builds its discriminated
`TypeAdapter` from `AnyDetail`. T003 only says "Add the four detail
models... matching the pattern from line 142 onward" -- it never says to
extend the `Union` at line 364. Without that edit, T006's envelope test
("each of the four detail models validates its contract example") can only
pass by validating the bare model class directly, silently bypassing the
one shared validator every other code's detail payload goes through, and
the module docstring's "18 per-code detail models" / `validate_detail`'s
"one of the 18 known codes" (417-421) go stale exactly like the
`TOOL-CONTRACT.md` count T004 remembers to bump. Fix: add a line to T003
naming the `AnyDetail` Union edit, and add an assertion to T006 that
`validate_detail()` (not just the bare model) accepts each new code.

**T009 -- `ParserCore.dll` resolution is assumed, not specified.**
`get_resolved_fieldworks_dir()` (versioning.py:204-224) returns the
directory containing `SIL.LCModel.dll`; it does not locate `ParserCore.dll`
inside it. SPEC.md:490-518 names `ParserCore.dll` explicitly as the file to
load, but T009's own line never says "locate `ParserCore.dll` in that
directory" -- an implementer working from tasks.md alone (not SPEC.md) can
plausibly try to reflect over `SIL.LCModel.dll` itself and fail quietly.
`versioning.py`'s only existing `Assembly.LoadFile` use (262) reads
`asm.GetName().Version` and nothing else; the actual member/Type reflection
precedent (`GetMembers`, generic-type unwrapping) lives in
`liblcm_extractor.py` (~330 onward, a different file, over different LCM
interface types), so T009 is combining two precedents that don't currently
share code, not reusing one. Mechanically sound, but the task text should
name the DLL and note the precedent split so review doesn't waste a cycle
asking "which file does this load."

## P2

**T019 is oversized for one task/PR.** Nine checks (rows 1,2,3-epenthesis,
4,5,6,8-corrected,9,10) each with distinct LCM types, per-row casting per
D4 (32/37 `IMoStemAllomorph` properties and 31/36 `IPhRegularRule`
properties require casts), plus universal `IPhSegmentRule.Disabled` gating
and the T016 name-verification gate for 3 of them -- combined with the P0
bridging work above, this is realistically several commits. Consider
splitting by D4's verified/partial grouping (e.g., phonology rows 2/4/9 vs.
morphology rows 1/6/10 vs. rule-ordering rows 3/5/8) so `checks_skipped`
degradation (a name verification failing at T016) doesn't block the whole
module.

**Verified clean, no action needed:** no `[P]`-tagged task pair shares a
file anywhere in the 28 tasks (checked all 28 file targets); US2's file set
(`models.py`, `tool_definitions.py`, `dispatch.py`,
`scan/grammar_scan_module.py`, `handlers/grammar_health.py`) is disjoint
from US1/US3's (`parser_probe.py`, `handlers/diagnostic_health.py`) --
`models.py` and `response_models.py` are confirmed separate files
(server/models.py:1-557, server/response_models.py:1-444). Tool
registration for T017/T018/T020/T021 matches the real four-file pattern
`flextools_health` uses, including `dispatch.py`'s try/except double
handler-import block (dispatch.py:108-186) and `TOOL_DEFINITIONS`-driven
`list_tools()` (server.py:817) -- no `__init__.py` export or separate
READ_ONLY_SAFE registry is missing.
