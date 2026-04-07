# MCP Initialization Profiling - Ralph Loop

## Goal
Reduce 18-second MCP server initialization delay to <5 seconds

## Current Understanding
- Module imports + API loading: ~1.04s (completed)
- MCP initialization (unknown where): ~18s
- **Total visible to user: ~19s**

## Timeline from Previous Work
```
10:15:50.499 - Connection state: Running (IDE connects)
10:15:55.500 - Waiting for initialize (5s)
10:16:00.499 - Waiting for initialize (10s)
10:16:05.499 - Waiting for initialize (15s)
10:16:09.587 - Loaded APIs message (19s total)
```

## Hypothesis
The delay is likely in ONE of:
1. **Tool registration** - @server.list_tools/@server.call_tool decorators
2. **Blocking I/O** - Reading files, network calls during init
3. **MCP handshake** - Client-server protocol negotiation
4. **Tool validation** - Pydantic model validation/schema generation
5. **Module initialization** - Something in server package __init__.py

## Investigation Plan

### Phase 1: Narrow Down Location
- [ ] Add timing around stdio_server() context entry/exit
- [ ] Add timing around server.run() entry/exit
- [ ] Add timing around tool handler registration
- [ ] Add timing around Pydantic schema generation

### Phase 2: Identify Culprit
- [ ] Profile which part is slow
- [ ] Check for blocking I/O, file reads, network calls
- [ ] Look for expensive computations (regex, etc.)

### Phase 3: Optimize
- [ ] Defer expensive operations
- [ ] Parallelize if possible
- [ ] Cache results

## Status
Starting Phase 1 investigation
