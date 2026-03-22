# Async Concurrency Analysis: FlexToolsMCP

**Date**: 2026-03-22
**Status**: Analysis Complete - Safe Patterns Identified
**Verdict**: ✓ Read-only tools CAN run async safely. ✗ Write operations MUST serialize per-project.

---

## Executive Summary

The MCP server uses subprocess isolation for `run_module` and `run_operation`, making each execution independent at the Python interpreter level. **However, the critical bottleneck is the FieldWorks database file itself**, which does not support concurrent writes.

**Safe to parallelize**: All read-only tools (search, get_object_api, list_categories, etc.)
**Must serialize**: Write operations on the same FieldWorks project (run_module with write_enabled=True, run_operation with CUD)
**Risk level**: Subprocess isolation + FieldWorks write locking = moderate risk if not managed

---

## Architecture Overview

### Process Model

```
MCP Server (async event loop)
├── Tool Handlers (async)
│   ├── read_only_tools (searchable, non-destructive)
│   │   ├── get_object_api
│   │   ├── search_by_capability
│   │   ├── get_navigation_path
│   │   ├── list_categories
│   │   └── find_examples
│   │
│   └── execution_tools (subprocess-based)
│       ├── run_module (write_enabled=T/F)
│       └── run_operation (with/without CUD)
│
└── Subprocess Pool
    ├── Subprocess N (independent Python interpreter)
    │   ├── FLExInitialize()
    │   ├── project = FLExProject().OpenProject(projectName, writeEnabled)
    │   ├── module.Run(project, report, modifyAllowed)
    │   └── project.CloseProject()
    │
    └── Subprocess N+1 (independent Python interpreter)
        ├── FLExInitialize()
        ├── project = FLExProject().OpenProject(projectName, writeEnabled)
        └── exec(operations, namespace)
```

### Key Files

- **[server.py:684-725](server.py#L684-L725)** - `@server.call_tool()` dispatcher (async, validates args with Pydantic)
- **[execution.py:481-899](src/server/handlers/execution.py#L481-L899)** - `handle_run_module()` (spawns subprocess)
- **[execution.py:901-1372](src/server/handlers/execution.py#L901-L1372)** - `handle_run_operation()` (spawns subprocess)
- **[subprocess_helpers.py](src/server/subprocess_helpers.py)** - `run_script_async()` (uses asyncio.create_subprocess_exec)
- **[kernel.py:304](src/server/kernel.py#L304)** - Global `session_state` (shared across handlers)
- **[kernel.py:310](src/server/kernel.py#L310)** - Global `pattern_tracker` (disk I/O, NOT synchronized)

---

## Detailed Safety Analysis

### 1. Read-Only Tools (Safe for Async Parallelization)

These tools read from in-memory API indexes loaded at server startup:

```python
# [server.py:432]
api_index: Optional[APIIndex] = None  # Loaded once at startup

# [server.py:684-725]
@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    # All read-only tools operate on api_index (read-only shared state)
    return await handler(validated_args.model_dump())
```

**Tools**:
- `get_object_api` - Reads from `api_index.flexlibs2` / `api_index.liblcm`
- `search_by_capability` - Reads from `api_index.semantic_search` (FAISS index)
- `get_navigation_path` - Reads from `api_index.navigation_graph`
- `list_categories` - Reads from `api_index.flexlibs2.get("categories")`
- `find_examples` - Reads from `api_index.flexlibs2.get("examples")`

**Concurrency Safety**:
- ✓ Index dictionaries are not mutated during runtime (loaded at startup, never updated)
- ✓ Dictionary reads in Python are atomic at the bytecode level (GIL protection)
- ✓ FAISS index is read-only after loading
- ✓ No file I/O during tool execution
- ✓ Session state reads are read-only: `session_state.get_mode()`, `session_state.get_project()`

**Verdict**: **SAFE to run 10+ concurrent read-only tools**

---

### 2. Write Operations (Serial Per-Project)

#### A. Process-Level Isolation (Good)

Each `run_module` and `run_operation` spawns a separate subprocess:

```python
# [execution.py:823-826]
result = await run_script_async(
    temp_script_path,
    timeout_seconds=timeout_seconds
)

# [subprocess_helpers.py:40-46]
process = await asyncio.create_subprocess_exec(
    sys.executable,
    script_path,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    stdin=asyncio.subprocess.DEVNULL,
    env=env,
)
```

**Each subprocess gets**:
- Independent Python interpreter (separate PID)
- Separate FlexLibs2 instance (separate heap)
- Separate LibLCM connection (if using liblcm mode)

**Verdict**: ✓ **No Python-level data corruption** between concurrent subprocesses

#### B. FieldWorks Database Write Contention (CRITICAL RISK)

**The real bottleneck**: The FieldWorks database file(s) in the project directory:

```
~/Library/Application Support/SIL/FieldWorks/Projects/MyProject/
├── MyProject.fwdata         # Main SQLite database
├── MyProject.fwdata-wal     # Write-ahead log
└── MyProject.fwdata-shm     # Shared memory file
```

When two subprocesses try to `FLExProject().OpenProject(projectName, writeEnabled=True)` **simultaneously**:

```python
# [execution.py:710-715]
try:
    project.OpenProject(projectName=PROJECT_NAME, writeEnabled=WRITE_ENABLED)
except Exception as e:
    result["error"] = "Failed to open project..."
```

**What happens**:

| Scenario | Behavior | Risk |
|----------|----------|------|
| `run_operation(..., project="MyProject", write_enabled=True)` called twice concurrently | Both subprocesses try to acquire write lock on MyProject.fwdata | SQLite lock timeout, one fails with "Database is locked" |
| Two writes to same entry simultaneously | Both get different cached copies; last write wins | **DATA LOSS** (silently) |
| One write, one read simultaneously | Read may see partial/corrupted data | **DATA CORRUPTION** (silent) |
| Write in subprocess A, read-check in subprocess B | B sees old value | **CONSISTENCY VIOLATION** |

**Verdict**: ✗ **CRITICAL: Multiple concurrent writes to same project = data corruption**

---

### 3. Shared State in MCP Server

#### A. Session State (Safe if Read-Only During Execution)

```python
# [kernel.py:304]
session_state: SessionState = SessionState()

# [execution.py:485-487]
project_name = args.get("project_name", session_state.get_project())
write_enabled = args.get("write_enabled", session_state.is_write_enabled())
api_mode = session_state.get_mode()
```

**Usage Pattern**:

1. `flextools_start()` calls `session_state.configure(project="MyProject", write_enabled=False, ...)`
2. Multiple `run_operation()` calls read from `session_state` (no writes)
3. `session_state` is only written by `flextools_start()` and `reset_session()`

**Concurrency Safety**:
- ✓ If tool reads don't trigger writes during execution, state is safely shared
- ✓ If `flextools_start()` is called while operations are running, could cause inconsistency (not a typical pattern)

**Verdict**: ✓ **SAFE** if start() is called once before operations

#### B. Pattern Tracker (Disk I/O Race Condition)

```python
# [kernel.py:310]
pattern_tracker: PatternTracker = PatternTracker()

# [kernel.py:159-168]
def save(self):
    """Save patterns to disk."""
    try:
        patterns_to_save = sort_json_arrays(self.patterns)
        with open(self.patterns_file, 'w', encoding='utf-8') as f:  # <- NOT ATOMIC
            json.dump(patterns_to_save, f, indent=2, ...)
```

**Risk**: Two concurrent operations both call `pattern_tracker.record_operation()` → both read patterns.json → both modify in-memory → both write back → **lost updates**

```python
# [execution.py:1322, 1326]
pattern_tracker.record_operation(operations, success=True)   # Concurrent!
pattern_tracker.record_operation(operations, success=False, error_msg=error_msg)  # Race condition
```

**Verdict**: ✗ **UNSAFE**: Concurrent operations can lose pattern tracking data

**Mitigation**: Use file locking or move pattern tracking to a dedicated sync handler

---

### 4. Temporary File Creation

```python
# [execution.py:809-819]
with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, ...) as f:
    f.write(full_script)
    temp_script_path = f.name
```

**Safety**:
- ✓ `tempfile.NamedTemporaryFile()` with `delete=False` creates unique filenames
- ✓ Multiple concurrent calls get different temp files (OS guarantees)
- ✓ Cleanup happens in finally block (safe even if exception)

**Verdict**: ✓ **SAFE**

---

### 5. Subprocess Output Parsing

```python
# [execution.py:839-857]
if "===FLEXTOOLS_RESULT_JSON===" in stdout:
    json_start = stdout.index("===FLEXTOOLS_RESULT_JSON===") + len(...)
    json_str = stdout[json_start:].strip()
    execution_result = json.loads(json_str)
```

**Safety**: ✓ Each subprocess produces its own stdout (separate process) - **no race condition**

---

## Recommended Concurrency Patterns

### Pattern A: Parallel Read-Only Operations (Safe)

```python
# Multiple async tools can run concurrently
async def handle_multiple_searches():
    tasks = [
        get_object_api({"object_type": "ILexEntry"}),
        search_by_capability({"query": "delete entries"}),
        get_navigation_path({"from": "ILexEntry", "to": "ILexSense"}),
    ]
    results = await asyncio.gather(*tasks)
    return results
```

**Concurrency**: Limited only by asyncio event loop (no blocking calls)
**Safety**: ✓ All tools read from read-only api_index

---

### Pattern B: Smart Serialization (Only for CUD Operations)

The implementation uses **smart locking** that only serializes when absolutely necessary:

```python
# [kernel.py]
project_write_locks: Dict[str, asyncio.Lock] = {}

def get_project_write_lock(project_name: str) -> asyncio.Lock:
    if project_name not in project_write_locks:
        project_write_locks[project_name] = asyncio.Lock()
    return project_write_locks[project_name]

# [execution.py - handle_run_operation and handle_run_module]
cud_info = detect_cud_operations(code)  # Already done

# Only lock if: write_enabled=True AND CUD detected
needs_lock = write_enabled and cud_info["is_cud"]

if needs_lock:
    write_lock = get_project_write_lock(project_name)
    async with write_lock:
        result = await run_script_async(...)
else:
    # No lock: read-only or metadata-only operations
    result = await run_script_async(...)
```

**Concurrency**:
- Read-only operations on any project: unlimited parallel ✓
- Metadata-only writes (config changes, etc.): unlimited parallel ✓
- CUD operations on project A: serialized (blocked by lock)
- CUD operations on project B: runs in parallel (different lock)
- CUD read + metadata write on same project: both can run in parallel

**Safety**: ✓ Only CUD operations are serialized per-project
**Efficiency**: ✓ Minimizes blocking - no locks unless data is modified

---

### Pattern C: Mixed Read + Write (Advanced)

```python
# Read-only operations COULD run during writes (if FieldWorks supports it)
# But this is risky - recommend serializing anyway to be safe

async def handle_run_operation_mixed(args: dict):
    project = args.get("project_name", session_state.get_project())
    write_enabled = args.get("write_enabled", False)

    # For safety, serialize ALL operations on a project
    # (even read-only, to avoid consistency issues)
    if project not in project_locks:
        project_locks[project] = asyncio.Lock()

    async with project_locks[project]:
        return await handle_run_operation_original(args)
```

**When to use**: Conservative approach, zero risk of consistency violations

---

## Specific Risks Identified

### Risk 1: Concurrent Writes to Same Project

**Scenario**:
```python
# User calls these at exactly the same time:
await run_operation(
    operations="entry = LexEntryOperations(project).Create(...)",
    project_name="MyProject",
    write_enabled=True
)

await run_operation(
    operations="entry.Sense.GetAll()",
    project_name="MyProject",
    write_enabled=True
)
```

**What happens**:
1. Both subprocesses call `FLExProject().OpenProject("MyProject", writeEnabled=True)`
2. Both acquire file handle to MyProject.fwdata-wal
3. FlexLibs2 caches load state
4. First operation creates entry, commits
5. Second operation reads old cached state, modifies, commits
6. First operation's changes are lost

**Severity**: 🔴 **CRITICAL** - Silent data loss

**Mitigation**: Implement per-project write lock as shown in Pattern B

---

### Risk 2: Pattern Tracker File I/O Race

**Scenario**:
```python
# Two operations run concurrently
# Both call pattern_tracker.record_operation() at the same time
```

**What happens**:
1. Operation A reads patterns.json → updates in-memory dict
2. Operation B reads patterns.json → updates in-memory dict
3. Operation A writes updated patterns.json
4. Operation B writes patterns.json (overwrites A's changes)
5. Operation A's pattern data is lost

**Severity**: 🟡 **MEDIUM** - Lost analytics, not user data

**Mitigation**:
- Use file locking: `fcntl.flock()` on Unix, `msvcrt.locking()` on Windows
- Or move to database-backed pattern tracking

---

### Risk 3: Session State Mutation During Execution

**Scenario**:
```python
# User calls:
flextools_start(task="...", project="ProjectA", write_enabled=False)

# Then concurrently calls:
run_operation(..., project="ProjectB", write_enabled=True)  # Should use ProjectB
```

**What happens**:
1. Session state is set to ProjectA/read-only
2. run_operation defaults to session_state project (ProjectA) ← BUG
3. Writes occur on wrong project

**Severity**: 🟡 **MEDIUM** - User error + code error combined

**Mitigation**:
- Tools ALWAYS require explicit project/write_enabled (no session defaults)
- Or document that start() must complete before other tools run

---

## Testing Strategy

### Test 1: Parallel Read-Only Operations

```python
async def test_parallel_searches():
    """Verify 100 concurrent searches don't corrupt state."""
    tasks = [
        search_by_capability({"query": f"test{i}", ...})
        for i in range(100)
    ]
    results = await asyncio.gather(*tasks)
    assert all(r.success for r in results)
    assert api_index unchanged  # Verify no mutations
```

**Expected**: All succeed, no errors

---

### Test 2: Serialized Writes (with lock)

```python
async def test_concurrent_writes_with_lock():
    """Verify write lock prevents data corruption."""
    project_name = "TestProject"

    async def write_op(i):
        return await run_operation(
            operations=f"entry = LexEntryOperations(project).Create(headword='{i}')",
            project_name=project_name,
            write_enabled=True
        )

    results = await asyncio.gather(*[write_op(i) for i in range(10)])
    assert all(r.success for r in results)
    assert project has 10 entries (not lost)
```

**Expected**: All 10 entries created (lock prevents loss)

---

### Test 3: Concurrent Writes WITHOUT Lock (negative test)

```python
async def test_concurrent_writes_without_lock():
    """Demonstrate data corruption without lock."""
    # Remove project_write_locks

    async def write_op(i):
        return await run_operation(...)

    results = await asyncio.gather(*[write_op(i) for i in range(10)])
    final_entry_count = check_project_entries()
    assert final_entry_count < 10  # Data loss!
```

**Expected**: Entry count < 10 (demonstrates need for lock)

---

## Recommendations

### Immediate (Phase 1)

- ✅ **Keep async for read-only tools** - They are safe and perform well
- ✅ **Keep subprocess isolation** - Good design, prevents GIL contention
- 🔴 **Add per-project write locks before 1.0** (CRITICAL)

  ```python
  # In kernel.py or new sync.py module
  project_write_locks: Dict[str, asyncio.Lock] = {}

  def get_project_write_lock(project_name: str) -> asyncio.Lock:
      if project_name not in project_write_locks:
          project_write_locks[project_name] = asyncio.Lock()
      return project_write_locks[project_name]
  ```

- 🟡 **Add file locking to pattern_tracker.save()** (MEDIUM priority)

  ```python
  # In kernel.py PatternTracker.save()
  import fcntl

  def save(self):
      with open(self.patterns_file, 'r+') as f:
          fcntl.flock(f.fileno(), fcntl.LOCK_EX)  # Exclusive lock
          json.dump(patterns_to_save, f, ...)
          fcntl.flock(f.fileno(), fcntl.LOCK_UN)  # Release lock
  ```

---

### Phase 2 (Future)

- Implement read-write locks (allow multiple reads, exclusive write)
- Consider connection pooling for FlexLibs2 project instances
- Monitor actual concurrency patterns from users
- Implement telemetry for "writes blocked waiting for lock" metrics

---

## Summary Table

| Component | Async Safe? | Notes |
|-----------|------------|-------|
| Read-only tools | ✅ Yes | Safe for 100+ concurrent |
| Session state (read-only) | ✅ Yes | Assuming start() completes first |
| Pattern tracker | ❌ No | Race condition on save() |
| Write operations (same project) | ❌ No | **CRITICAL** - needs per-project lock |
| Write operations (different projects) | ⚠️ Maybe | Depends on FieldWorks locking behavior |
| Subprocess isolation | ✅ Yes | Each gets independent interpreter |
| Temp file creation | ✅ Yes | OS provides unique filenames |
| Output parsing | ✅ Yes | Each subprocess has own stdout |

---

## Conclusion

**Your suspicion is correct**: Edit functions in `run_module` and `run_operation` **MUST NEVER run concurrently on the same project**. The risk is data corruption at the FieldWorks database level.

**Implementation priority**:
1. Add `project_write_locks: Dict[str, asyncio.Lock]` (5 minutes)
2. Protect `run_module` and `run_operation` with lock (2 lines per handler)
3. Add file locking to `pattern_tracker.save()` (1 line)

**Result**: Safe concurrent reads, serialized writes per-project, zero data loss risk.
