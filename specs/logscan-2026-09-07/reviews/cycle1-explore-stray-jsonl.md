# Cycle 1 - Explore: stray repo-root `operations.jsonl`

**VERDICT: same root cause as MCP#74** - the stray rows are test-harness
telemetry (project `TestProj`, empty `session_id`/`user_intent`, identical
91-byte/4-line code, `duration_s: 0.0`, seq 1-4 within 13 s), and no
cwd-relative log path exists anywhere in `src/`. This is leaked harness
output, not a product path-resolution bug.

## 1. Path computation sites (all absolute, all via `get_log_dir()`)

- `src/flextoolsmcp/server/kernel.py:85-92` - sole resolver:
  `Path.home() / ".flextoolsmcp" / "logs"`, mkdir'd. No env var, no config
  override (grep for `log_dir` / `logs_dir` config keys: zero hits).
- `src/flextoolsmcp/server/handlers/op_telemetry.py:117` - `_get_jsonl_path`
  = `log_dir / "operations.jsonl"`; `:212-216` write; `:229-232` read current
  + `.1`.
- Injection defaults: `src/flextoolsmcp/server/handlers/execution.py:726,
  825, 951, 1000` - `log_dir_fn if log_dir_fn is not None else get_log_dir`;
  also `:1686`.
- `operations.log`: `kernel.py:291-294`, `:369`; consumers
  `execution.py:4668, 4675`, `diagnostic_health.py:368-369`.

## 2. cwd-relative fallback

None in `src/`. The only bare relative default is a **reader** in
`scripts/green_report.py:342`:

```python
input_paths = [Path("operations.jsonl"), Path("operations.jsonl.1")]
```

(help text at `:316` says "default: operations.jsonl + .1 in cwd"). It reads,
never writes.

Residual #74-shaped risk: the four `log_dir_fn: Optional[Any] = None` params
(`execution.py:693, 744, 903, 963`) silently fall back to the real production
log dir when a caller omits the override.

## 3. Stray file contents

5 records (trailing newline), ids `op-014227325-001` ... `op-014240211-004`
- **not** `test-op-*` ids, but unmistakably synthetic. First ts
`2026-09-07T06:42:27Z`, last `2026-09-07T06:42:40Z`. Two invocations (1 row,
then 4 rows 13 s later); outcomes `validate_only` x3 and
`preflight_reject`/`casting_issues_detected` x2, `write_enabled` false/true
pairs, `casting_signature f48c1dc7c0e9f638`.

mtime 2026-09-07 01:42 local - same window as edits to `validators.py`,
`execution.py`, `tests/evals/preflight_runner.py`,
`tests/test_issue40_casting_severity.py`, `tests/test_issue49_validate_only.py`
- i.e. an ad-hoc harness/verification run in the repo root whose log dir
resolved to `.`. Production
`C:\Users\thoua\.flextoolsmcp\logs\operations.jsonl` (471 KB, mtime 03:35)
still carries real ops, so the production log was not the target this time.

## 4. `.gitignore` coverage

`.gitignore` (49 lines) has **no** entry for `operations.jsonl`, `*.jsonl`,
or `logs/` (only `.flextoolsmcp/skeletons.jsonl` and `user-logs/`).
`git status` shows `?? operations.jsonl` - at real risk of being committed.
Recommend adding `operations.jsonl*` / `operations.log*`.

## 5. Does any test create it at repo root?

No. All 40+ telemetry tests use `tmp_path` or an explicit `log_dir_fn`
(e.g. `test_op_telemetry.py:89`, `test_issue42_session_identity.py:141,170`
- the #74 fix), and `tests/evals/preflight_runner.py` never touches jsonl
paths.
