# T032 report -- D-note for `active_engine`'s unconditional `null` at CP1

**D-number used:** D8 (`## D8. active_engine is unconditionally null at CP1`).

**Precis.** Records that `flextools_health`'s `parser.active_engine` is
unconditionally `null` at CP1 because the handler never opens a project (same
premise as D2's `agent_probe: "skipped"`), and `ActiveParser` can only be read
from an open project. States plainly that `null` is the only truthful value --
not a placeholder or TODO -- and that `active_engine` is informational only,
never a status input (the engine-mismatch gate lives in `check_active_parser`,
T024). Names T012's `_build_parser_block()` assertion as what this note gates,
and records that CP2 changes the value (echoes `ActiveParser`, still
informational) once a spine-executing handler holds an open project.

**Cross-references cited:**
- research D2 (`flextools_health`'s parser block never opens a project)
- `specs/parser-check/data-model.md` §`ParserDetector` return shape --
  "`active_engine` is informational only. It never decides a status"
- `specs/parser-check/contracts/flextools_health-parser-block.md` --
  "`active_engine` is informational only -- it echoes `ActiveParser` when a
  project is open, else `null`"

**Diff confirmation.** Append-only. New content added after the existing D7
section's closing line ("...an implementer would sort by it."), running from
the newly inserted `---` separator through the end of file (D8 spans roughly
lines 227-256 post-edit). D1-D7 (original lines 1-226) are byte-unchanged --
no rewording, renumbering, or reflow was performed on any existing note.

No other files were touched. No commit was made.
