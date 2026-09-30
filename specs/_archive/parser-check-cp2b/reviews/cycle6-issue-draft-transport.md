# Issue draft (cycle 6) -- DRAFT -- NOT FILED. Requires user approval.

## Title
Trace payload crosses the worker IPC channel in one buffered chunk, defeating
the stream limit -- the worker should write traces to the run record itself
and send only a path

## Reproduction
- `flextools_try_word`, `level="explain"`, word `mtu` (3 analyses),
  Claude-Swahili project. Worker channel dies: `Separator is not found, and
  chunk exceed the limit`.

## Mechanism
- `src/flextoolsmcp/server/subprocess_helpers.py:179` spawns the worker via
  `asyncio.create_subprocess_exec` with no `limit=`, so `proc.stdout`
  inherits asyncio's 64 KiB default `StreamReader` buffer.
- `src/flextoolsmcp/server/parse/worker_client.py:262`, `_read_message`,
  reads the whole response -- trace XML included -- as one
  `readline()` + `json.loads()` call. A multi-KB trace blows the buffer
  before a newline separator is ever seen.
- Only *after* that full payload has crossed the channel does
  `src/flextoolsmcp/server/parse/runner.py:411-418` write it out of line via
  `handle.record.write_trace(index, trace_xml)` and replace it with
  `trace_path` in the response entry.
- `specs/parser-check-cp2b/contracts/tools.md` (lines 129-146, 213-217)
  already documents traces as reported by `trace_path`/`trace_bytes`, never
  inlined, and treats "hundreds of KB" as the *normal* case, not an edge
  case (`traces_written` is a first-class summary counter). The contract is
  honored at the tool-response boundary but not at the process boundary,
  where the full trace already crossed stdout before anything strips it.

## Why the ceiling raise is not the fix
Raising `limit=` stops today's crash but leaves the architecture unchanged:
the full trace is still marshalled through `readline()`/`json.loads()` into
one in-memory buffer per call, still scaling with trace size and concurrent
in-flight requests. It raises the ceiling; "hundreds of KB, normal case"
must still fit on the wire. A larger grammar or word reopens the failure at
a higher threshold.

## Proposed direction
Worker writes the trace directly into the run's record directory and sends
only the relative path (`traces/{index}.xml`) over IPC -- mirroring what
`runner.py` already does server-side, one process earlier, so the payload
never crosses the channel.

**Open question -- record-directory ownership.** The record lives
server-side today (`record.py:110`, `get_record_dir()`;
`RunRecord.__init__` at `record.py:196-205` takes `record_dir`/`run_id`
known only to the server). The worker has no notion of either today -- it
only returns `trace_xml` (`worker_main.py`). Moving the write requires
deciding what the worker needs (record dir path, or run id + shared root),
how that's communicated (spawn-time env/arg vs. per-request field), and
confirming write access to that directory in every deployment shape.

## Cross-reference
Checked #165 (CP4, in-process write/ParseFiler), #166 (CP5, sandbox spine),
#167 (CP6, contract codes/CHANGELOG/docs) -- none targets the worker<->record
transport boundary; #167 is nearest but scoped to codes/CHANGELOG, not this
architecture change. Recommend standalone rather than folding into CP4-CP6.

## Duplicate check
Searched (open+closed): "asyncio limit", "StreamReader", "IPC", "worker
channel", "64 KiB", "trace path", "chunk exceed", "Separator is not found".
No existing issue found. Nearest unrelated hits: #112 (CastingOperations
phantom remedy), #130 (unguarded FromOpenProject mutations) -- neither
touches transport.
