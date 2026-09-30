## Feasibility review — lex-programmer, cycle 1

### §3.2 anchors — confirmed
All cited anchors exist and match:
- `[TOOL CALL]`/`[TOOL ARGS]`: `src/flextoolsmcp/server.py:847-848` (comment at 843-845). Both INFO, args truncated 500 chars.
- `=== Operation #{seq} Start ({op_id}) ===` block (Project/Write enabled/Source kind/User intent/fingerprint): `src/flextoolsmcp/server/handlers/execution.py:383-391`.
- `Preflight casting: issues=… tier=… helpers=…`: `execution.py:415-417`.
- `Code:` + DEBUG lines: `execution.py:425-427`.
- `report.Error`/`Warning`/`Info` replay: `execution.py:570-575` (via `_log_report_messages`, `execution.py:536-575`; note INFO only replays on failure — success path never logs info prose, only counts).
Turn reconstruction from prose is feasible: every op is self-bookended (Start/End with matching `op_id`+`seq`), so a scanner can extract exact op-block spans by regex without needing the JSONL at all.

### §3.1 join — deterministic, confirmed
`op_id` and `seq` are both stamped in the prose block header (`execution.py:383`) and in the JSONL record (`op_telemetry.py:143-144`, written by `_write_jsonl_line`). `seq` comes from a process-lifetime `itertools.count(1)` (`execution.py:297`, `_next_op_id` at 300-312); `op_id` is `op-<HHMMSS><ms>-<seq:03d>`, unique across restarts. Since both identifiers are written from the *same* call site stash (`_stash_op_start`, `op_telemetry.py:54-88`, drained exactly once per close, `op_telemetry.py:135-139`), the join is deterministic by construction — prose and JSONL can never disagree on which op_id maps to which seq.

### §5 turn grouping — reusable, with one gap
`compute_jsonl_statistics()`'s intent-grouping loop (`op_telemetry.py:230-255`) is exactly the boundary described — confirmed. Reusable as-is for the *default* turn slice. Gap: it groups on `user_intent` only; §4's new `user_request` field isn't threaded through this function, so if `user_request` is added per-op, the grouping key should probably become `(user_intent, user_request)` or stay `user_intent`-keyed with `user_request` carried along — worth an explicit decision, not automatic. `steps_back`/`include_from_op_id`/explicit `op_ids` and `MAX_REPORT_OPS=12` summarize-not-drop are new logic with no current equivalent; straightforward to add as a thin wrapper around the existing grouping + prose extractor, no blocking obstacle found.

### Q3 (§11.3) — recommend: yes, stitch across rotation
Two independent rotation mechanisms exist, both risk splitting a turn:
1. **Size rotation** on the per-session file itself: `RotatingFileHandler(maxBytes=5MB, backupCount=3)` (`kernel.py:107-112`, applied to `session_<id>.log` at `kernel.py:161` / `206-209`). A verbose turn (large code dumps at DEBUG, `execution.py:425-427`) can push past 5MB mid-turn, splitting content between the current file and `.log.1`.
2. **Session-switch rotation**: `rotate_logging_to_session()` (`kernel.py:166-211`) opens a *new* `session_<id>.log` when `flextools_start` fires again, detaching the old handler. This is a turn *boundary* by construction (flextools_start is turn-level per §4), so it shouldn't split a turn in normal use — lower risk, not zero if a client calls `flextools_start` mid-turn.

**Concrete stitching approach**: don't rely on file boundaries at all — use the target `op_id`/`seq` list resolved from JSONL (which rotates independently, at 10k lines, `op_telemetry.py:43,99-111`) to know exactly which `=== Operation #{seq} Start/End ({op_id}) ===` blocks to look for, then scan `session_<id>.log`, `.log.1`, `.log.2`, `.log.3` (RotatingFileHandler never splits a single `logger.info()` call across files, so each block is intact in exactly one file), concatenate matched blocks in `seq` order regardless of source file, and reorder by seq if needed. If `backupCount=3` has already recycled past a requested `steps_back` op, surface "history truncated by rotation" per the no-silent-caps rule rather than silently omitting it.

### §4/Q6 (§11.6) — plumbing assessment
No `user_request` field exists yet anywhere in `tool_definitions.py`, `execution.py`, or `op_telemetry.py` — this is greenfield, not a retrofit. Plumbing points: `_log_operation_start` (`execution.py:358-369`) already threads `user_intent` as an optional kwarg logged with a `(not provided)` fallback (`execution.py:387`) — `user_request` can follow the identical pattern (new optional param, new log line, new stash field in `_stash_op_start`/`op_telemetry.py:54-63` and `_OP_STASH` dict `op_telemetry.py:78-87`, new JSONL record field `op_telemetry.py:141-162`). Backward compat is clean: optional arg, default None, same fallback idiom already used for `user_intent`. Per-op (`run_module`) placement is more useful than turn-level (`flextools_start`) alone since it survives intent-drift mid-turn per the spec's own reasoning, and costs one extra string per op — no contract break, additive field on an existing optional-arg model.

### §8.3 machine-hygiene normalization — feasible, no existing utility
No home-path/username scrubbing utility currently exists anywhere in `src/` (checked `file_utils.py`, `config.py`, `kernel.py`, `skeleton_storage.py`, `server.py` — only plain `Path.home()` usage for directory construction, e.g. `file_utils.py:23`). This must be written new: a simple string substitution (`str(Path.home())` → `~`, OS username token stripped) applied once, at render time, to the fully-assembled report text just before the local write to `~/.flextoolsmcp/reports/report_<ts>.md`. Because it's a literal-substring replace over the rendered buffer (not a structural walk), it can safely target only path strings and cannot reach into lexical `report.Info` content unless a headword coincidentally contains the OS username substring — negligible/acceptable risk, matches spec's "touches no lexical data" claim.

### Summary
No blocking feasibility issues found. All cited line anchors check out. Recommend: (1) decide whether turn-grouping keys on `user_intent` alone or the pair once `user_request` lands: (2) yes, stitch across the size-based `backupCount` rotation using JSONL-driven op_id targeting, not file-boundary assumptions.
