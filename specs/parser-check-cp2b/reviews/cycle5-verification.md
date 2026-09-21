# Live verification -- cycle 5, narrow probe (plain vs explain at count > 1)

**Project:** `Claude-Swahili` (11,175 wordforms). Opened read-only
(`writeEnabled=False`, worker default) via `handle_flextools_try_word`
directly, the same seam `tests/test_parse_live.py` uses. **Opened, twice,
in ~8-10s each** -- not a bottleneck.

## Screening
25 candidate Swahili wordforms queued at `level='plain'` (real vocabulary
chosen for productive Bantu affixation). Screening stopped at word 1:

```
'mtu' -> status=ok, parsed=true, analysis_count=3
```

One word screened was sufficient -- `analysis_count=3` on the very first
probe. No further screening needed.

## The comparison -- and what actually happened
Ran `level='explain'` on `'mtu'` against the same project. **The worker's
own IPC channel broke before returning any answer**, reproduced on two
independent fresh workers:

```
Parse worker read loop failed: Separator is not found, and chunk exceed the limit
Parse run ... failed during parsing: Parse worker for 'Claude-Swahili' closed
its channel before answering.
```

`explain`'s response: `status: error`, `error_code: runtime_error`,
`stage_at_failure: parsing`. No `analysis_count`, no trace, at all.

Root cause (read, not executed): `worker_client.py` reads the child's
line-delimited JSON with `proc.stdout.readline()` (`worker_client.py:262`),
which inherits asyncio's default `StreamReader` limit (64 KiB) unless
explicitly widened. `mtu`'s 3-analysis `TraceWordXml` trace, serialized to
one JSON line, exceeds that limit -- `asyncio.LimitOverrunError`'s own
message is literally "Separator is not found, and chunk exceed the limit".
This is a transport-layer ceiling, not a parser or count-derivation defect,
but it sits directly in the write/read path this checkpoint's diff touches
(`worker_main.py`) and it is the FIRST count>1 case this feature has ever
been run against live.

## Cleanup
Both crashed workers were reaped by the runner's own guard ("issue #57"),
confirmed via process listing (no leftover `worker_main`/`Claude-Swahili`
python.exe). `Claude-Swahili.fwdata.lock` timestamp unchanged
(pre-existing, unrelated to this probe) -- nothing written, nothing new
locked.

## VERDICT
FAIL (count 3, plain 3 vs explain CRASH -- worker channel broke before
returning any count)

The equality premise (`<Analysis>` count == `ParseResult.Analyses.Count`)
was never actually exercised at count>1: `explain` cannot complete on the
one multi-analysis word found, so no comparison was possible. This is
worse than an unequal-count result -- it means the design's untested edge
(count>1) is not merely unverified but **currently unreachable live** via
`explain`, on a real project, on the first attempt. File an issue for the
`readline()` limit before claiming count>1 is safe.
