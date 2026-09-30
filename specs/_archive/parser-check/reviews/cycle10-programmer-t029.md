# T029 -- programmer report

**Verdict: import works.** `handle_run_module`'s subprocess is plain CPython
(`sys.executable`, the same interpreter running the MCP server), launched with
`env=None` (no call site in `execution.py` passes `env=`), so it inherits the
parent's environment. `import flextoolsmcp.server.scan.*` succeeds in it
unconditionally -- T030 must build the **import path**, not the splice path.

**Backed by an executed probe, not a code-read.** I built a scratch script
(scratchpad, deleted after use) that reproduced `run_script_async`
(`src/flextoolsmcp/server/subprocess_helpers.py:56-95`) line-for-line --
same `sys.executable`, same `env=None`, same `asyncio.create_subprocess_exec`
shape -- pointed at a temp script that does
`import flextoolsmcp.server.scan as scan_pkg` and prints the
`===FLEXTOOLS_USER_RESULT===` / `===FLEXTOOLS_RESULT_JSON===` sentinel pair
(mirroring `SimpleReporter.Result`, `execution.py:3871-3888`). Ran twice --
once from the repo root, once from `D:\tmp` -- to rule out cwd-dependence.
Both: `returncode 0`, empty stderr, stdout containing
`{"imported_from": ".../server/scan/__init__.py", "ok": true}` between the
sentinels, parsed back successfully by logic copied from
`execution.py:4481-4490`. Root cause confirmed by code-read as a supporting
fact (not asserted as the probe itself): an editable-install `.pth`
(`__editable__.flextools_mcp-2.11.0.pth` in site-packages) points
`sys.path` at `.../FlexToolsMCP/src` for every process started with this
`python.exe`, independent of cwd or parent `sys.path`.

**Concrete seam for T030:** a new, small script-template function alongside
(not inside) `handle_run_module` in `execution.py`, reusing `SimpleReporter`,
the `OpenProject(...)` call, `run_script_async`, and the existing
`===FLEXTOOLS_USER_RESULT===`/`===FLEXTOOLS_RESULT_JSON===` sentinel pair --
but with a fixed, literal "module code" (`from
flextoolsmcp.server.scan.grammar_scan_module import run_grammar_scan;
report.Result(run_grammar_scan(project))`), never caller-supplied text.

**T030 is NOT forced to refactor `handle_run_module`.** None of its ~1800
lines of write-lock/backup/casting-injection/preflight machinery is needed
for a fixed first-party import; T030 adds a parallel, much smaller function
and T020 wires a new handler to it.

**D1 correction (one sentence):** D1's claim that the scan module is
"covered by the existing preflight/casting validators" is wrong because
those validators only run over the caller-supplied `code` string spliced
into `MODULE_CODE = {code}` -- a module living at
`server/scan/grammar_scan_module.py` and merely imported never passes
through them, so what actually covers it is the repo's own tests and lint,
same as any other first-party file under `src/`.

**Diff check:** `git diff --stat specs/parser-check/research.md` shows
217 insertions(+), 0 deletions -- a single hunk appended after D10, D1-D10
untouched.

Full detail (probe transcript, `.pth` evidence, sentinel-parsing citation,
scope note that no FLEx project was opened) is in `## D11` of
`specs/parser-check/research.md`.
