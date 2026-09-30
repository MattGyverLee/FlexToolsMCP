# parser-check CP2 (CP2a): as built

**Status:** Retired 2026-09-29. Landed directly on main in merge `e5afbfd` (2026-09-20, "Merge origin/main into parser-check CP1+CP2+CP2b"); no PR exists. Tasks: 31/31 complete (`c8ccd9d`, QC fixes `c2432a9`, `a044cf0`).
**Full docs:** [specs/_archive/parser-check-cp2/](../_archive/parser-check-cp2/) (spec, plan, tasks, research, data-model, contracts, reviews, evidence). Not read by default.
**Pinned here:** none (no test or code opens these files at runtime; only docstring citations).
**Scope:** CP2a is the flexicon-side half only (repo `C:\Github\flexicon`, released as pyflexicon 4.9.0; this repo now floors at `>=4.11.0,<5`). CP2a-bridge and CP2b live in [../parser-check-cp2b/](../parser-check-cp2b/). No CP2a code is in this repo; the only CP2a file here was the evidence artifact.

## What shipped
- `project.Parser` (`ParserOperations`, read-only facade over the FLEx parser) in flexicon; `from flexicon import ParserOperations` also works.
- Availability that never raises (returns a status object with a reason).
- Three read gaps: plural text genres, allomorph owning entry, MSA read accessor.
- `"parser"` token in `flexicon.CAPABILITIES`.
- Behavioural evidence gate (tiers A1-A3) that CP2b required as its entry condition.

## Public contracts (checked against `C:\Github\flexicon` at v4.11.0-4, `flexicon/code/Parser/ParserOperations.py`)
- `project.Parser.GetAvailability()` -> `ParserAvailability(available: bool, reason: str, version: str|None)` (frozen dataclass, line 83). Version is reported, never compared to a minimum (FR-006).
- `ParseWord(word)`, `ParseWordXml(word)`, `TraceWordXml(word, analyses=None)`. Positional binding only (FR-005).
- `Reload()` = `handle.Reset()` then `handle.Update()` (lines ~593-608); `IsUpToDate() -> bool` is the currency read.
- No write/file operation on the surface (FR-002).
- `TextOperations.GetGenres(text_or_hvo)` (TextOperations.py:864); `AllomorphOperations.GetOwningEntry(allomorph_or_hvo)` (:1554); MSA via `MSAOperations.GetAll` (:177).
- `CAPABILITIES` contains `"parser"` (`flexicon/__init__.py:87`). A token means the build has the surface, not that the parser is reachable; probe `GetAvailability()`.
- MCP side consumer: `src/flextoolsmcp/server/parse/worker_main.py` (calls GetAvailability, confirms IsUpToDate before every reuse). Live requirement text still in force is FR-042/043 (below).

## Key decisions
- Unavailability is a returned status, not an exception or None -- SC-001, first degrading-with-reason return in flexicon (D-A4).
- Reload is reset-then-reload; a bare update short-circuits on an unchanged model and silently serves the stale grammar (D-A5, FR-043).
- Accessor is singular `project.Parser` (D-A3); own domain package (D-A2).
- FR-009 wires the existing MSA wrapper, designs nothing new (D-A6); plural `GetGenres` added, singular kept (D-A9); allomorph owner walks the ownership chain (D-A8).
- `"parser"` token lands last, after tiers A1-A3 pass (D-A10).
- Evidence is a written artifact, not a test count: all four flexicon ratchets are structural and would pass a reload bound to a bare update (D-A12).
- Do not build a typed identity marshaller for traces (FR-010 as amended by E5).

## Gotchas and limits
- An empty analyses restriction on the trace is not "no restriction": the component treats null and empty as opposites and the setting persists past the call. The code clears it via `_ClearAnyRestriction`.
- Never run bare `pytest` in flexicon; it runs live tests in place against real projects.
- Nothing runs in CI for this: no hosted runner, the self-hosted `[windows, fieldworks]` pool has zero runners. All tiers were local and manual.
- FR-004 same-installation test is directory equality only; a foreign component copied into the right directory passes.
- FR-042/043 amendment (issue #223, 2026-09-24): "held grammar" is scoped to the project being open. `<project>.fwdata.lock` must not be held while the worker is idle; the worker closes the project when its queue goes idle and reopens on demand. Currency is still confirmed within a request/batch. Evidence: `_archive/parser-check-cp2/evidence/issue223-live.md`.

## Divergences from the spec
- Names: contract prose describes capabilities generically; shipped names are `GetAvailability`, `ParseWord`, `ParseWordXml`, `TraceWordXml`, `Reload`, `IsUpToDate`. Matches intent.
- pyflexicon version: spec pinned 4.9.0; this repo now requires `>=4.11.0,<5` (requirements.txt:21, pyproject.toml:54).
- Verbatim `4.9.0` claim (`flexicon/__init__.py:15`) is stale; installed version is 4.11.0.
- Branch: handoff asked for `feat/parser-check-cp2` in this repo; work stayed on `feat/parser-check-cp1`. Decision recorded in cp2b evidence.
- Not verified: FR-001..FR-043 individually, the flexicon test tiers, and `contracts/evidence-gate.md` tier procedures (flexicon-side; only the surface above was read).

## Follow-ups and open issues
- needs_human T-item: A4 (live write) deferred to CP2b (escalation E-D); discharged by cp2b T066 (`b1aab42`).
- Debt named in the evidence: the three read gaps had no tests at CP2a close; `_FILE_PATH_DOMAIN_HINTS` lacks a `parser` entry (flexicon `tests/flex_plugin.py`); CHANGELOG tail stale.
