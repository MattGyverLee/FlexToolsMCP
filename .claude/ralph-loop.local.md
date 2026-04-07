# MCP Startup Optimization - Ralph Loop Progress

## Phase 1: COMPLETE ✅

### Bottleneck Identified
- LibLCM load: 0.398s (slow - now deferred)
- FlexLibs stable load: 0.410s (slow - now deferred)
- FlexLibs2 load: 0.049s (fast - kept at startup)
- Total was: 0.867s

### Solution Implemented: Lazy-Loading
- **APIIndex.load()** only loads FlexLibs2 at startup
- Added **ensure_*_loaded()** methods for on-demand loading
- Libraries load on first tool call that needs them

### Results: 15x Faster API Loading! 🚀
- Before: API load 0.867s
- After: API load 0.058s
- **Improvement: 809ms saved**
- Overall startup: 1.79s → 1.03s (43% faster)

## Phase 2: Understanding Remaining 18-Second Delay

### Timeline (from user logs)
- 10:15:50 - Connection state: Running
- 10:16:09 - Loaded APIs message (19s total)

### What We Know
- Our code startup: ~1.03s (measured)
- MCP server initialization + handshake: ~18s (remaining)
- **The bottleneck is NOT in our Python code anymore**

### Next Steps
1. [ ] Test if 18s delay still exists with lazy-loading
2. [ ] Profile MCP server initialization (stdio_server, server.run)
3. [ ] Check for blocking I/O or expensive operations in MCP SDK
4. [ ] Consider async optimization of tool registration
5. [ ] Look for MCP client-side delays (IDE waiting for `initialize` response)

## Commits
1. Timing instrumentation (commit 241a7e4)
2. Lazy-loading implementation (commit 841f6f8)

## Next Iteration Goal
After testing, investigate why MCP initialization takes 18 seconds.
This is now the critical path to optimize further.

## Phase 1B: Integration - Calling Lazy-Load Methods

### Tools Using LibLCM/FlexLibs stable
Need to add ensure() calls before using indexes:

**Files to update:**
- src/server/handlers/api.py (uses api_index.liblcm, api_index.flexlibs_stable)
- src/server/handlers/catalog.py (uses api_index.liblcm)
- src/server/handlers/admin.py (only reads versions, not indexes)

### Pattern to implement:
```python
def handle_tool(args):
    if need_liblcm:
        api_index.ensure_liblcm_loaded()
    # ... use api_index.liblcm
```

### Status: NOT YET DONE
Need to integrate lazy-load calls into handlers.
Without this, tools will fail when trying to access None indexes.
