# MCP Startup Optimization - Ralph Loop Progress

## BOTTLENECK FOUND! 🎯

### Per-Component Breakdown
- LibLCM load: **0.398s** ← SLOW (version detection + JSON load)
- FlexLibs 2.0 load: 0.049s (fast)
- FlexLibs stable load: **0.410s** ← SLOW (version detection + JSON load)
- Navigation graph load: 0.006s
- Casting index load: 0.004s
- Semantic search load: 0.000s
- **Total API loading: ~0.867s**

### Root Cause
The slow libraries (LibLCM and FlexLibs stable) are 82% of the startup cost!

### Next Action: Lazy-Load Slow Libraries
Per user request: "only flexlibs2 needs to load at startup, the others can load later if needed"

Strategy:
1. Load only FlexLibs2 at startup (0.049s)
2. Defer LibLCM and FlexLibs stable to first-use lazy loading
3. Keep navigation/casting/semantic search optional

Estimated improvement: 0.867s → ~0.05s API loading (17x faster!)

## Implementation
- [ ] Modify APIIndex.load() to skip LibLCM and FlexLibs stable
- [ ] Add lazy-loading for deferred libraries on first tool call
- [ ] Test startup time improvement
- [ ] Verify no tools break due to missing indexes

## Key Finding
The original lazy-loading commit was RIGHT IDEA but WRONG EXECUTION.
It tried to defer but might have broken tool functionality.
This time we'll do it properly with on-demand loading.
