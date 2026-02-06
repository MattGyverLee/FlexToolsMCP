# Architecture & Design Decisions

This document tracks key architectural and design decisions made during the FlexTools MCP project.

---

## Decision 001: Leverage FLExTools-Generator Foundation
**Date:** 2026-02-05
**Status:** Approved

### Context
The FLExTools-Generator repository already contains comprehensive LibLCM extraction (2,295+ entities, unified-api-doc/2.0 schema).

### Decision
Build on top of FLExTools-Generator outputs rather than re-extracting from scratch:
- Use existing `flex-api-enhanced.json` for LibLCM documentation
- Use existing `unified-api-doc/2.0` schema for consistency
- Focus new effort on FlexLibs 2.0 extraction (the gap)

### Consequences
- Faster development (avoid redoing LibLCM extraction)
- Consistent data format across all sources
- Dependency on FLExTools-Generator outputs

---

## Decision 002: FlexLibs 2.0 as Primary API Layer
**Date:** 2026-02-05
**Status:** Approved

### Context
Three API levels exist:
1. LibLCM (C#) - comprehensive but verbose
2. FlexLibs Light - stable but limited (~40 functions)
3. FlexLibs 2.0 - comprehensive (~90% coverage), Pythonic, beta

### Decision
Default to FlexLibs 2.0 when generating scripts:
- "auto" mode uses FlexLibs 2.0 when available
- Falls back to LibLCM for uncovered functionality
- FlexLibs Light supported but not prioritized

### Consequences
- More Pythonic generated scripts
- Some beta instability risk
- FlexLibs 2.0 extraction completed (78 classes, 1,398 methods)

### Quality Comparison (2026-02-05)
| Source | Entities | Descriptions | Returns | Examples |
|--------|----------|-------------|---------|----------|
| LibLCM | 2,295 | 100% | Minimal | 0% |
| FlexLibs 2.0 | 78 classes | 99% | 61% | 82% |

FlexLibs 2.0 has significantly better documentation quality despite being a wrapper.

---

## Decision 003: Static Analysis Primary, AI for Enrichment
**Date:** 2026-02-05
**Status:** Approved

### Context
Could use heavy AI for documentation generation vs. deterministic extraction.

### Decision
Use static analysis (AST parsing) for extraction, AI only for:
- Filling missing descriptions
- Semantic categorization
- C# to IronPython example conversion

### Consequences
- Reproducible, verifiable outputs
- Lower cost (minimal API calls)
- Ground truth remains source code

---

## Decision 004: Object-Centric Index Organization
**Date:** 2026-02-05
**Status:** Approved

### Context
Could organize index by method name, by category, or by object.

### Decision
Organize around objects (ILexEntry, ILexSense, etc.) with:
- Methods and properties per object
- Relationship navigation paths
- FlexLibs 2.0 wrapper mappings

### Consequences
- Natural navigation for object-oriented code
- Easier "how to get from A to B" queries
- Matches how users think about lexicon structure

---

## Decision 005: Semantic Recategorization of LibLCM Entities
**Date:** 2026-02-05
**Status:** Approved

### Context
The original LibLCM extraction had 980 entities categorized as "general", making category-based queries useless.

### Decision
Recategorize LibLCM entities using:
1. **Namespace rules** - `SIL.LCModel.Core.Text` -> texts, etc.
2. **Naming patterns** - IMo* -> grammar, ILex* -> lexicon, IWfi* -> wordform
3. **FlexLibs2 usage mapping** - If a LibLCM interface is only used by lexicon FlexLibs2 classes, categorize as lexicon
4. **Compiler-generated detection** - Mark `<>c__DisplayClass*` as "internal"

### Results
| Category | Before | After |
|----------|--------|-------|
| general | 980 | 338 |
| system | 0 | 328 |
| grammar | 263 | 294 |
| texts | 27 | 106 |
| scripture | 71 | 100 |
| internal | 0 | 110 |

### Consequences
- Category counts now make sense (LibLCM >= FlexLibs2 in all domains)
- Better search results when filtering by category
- "general" now contains only truly generic entities

---

## Decision 006: Method-Level LibLCM Mapping (Phase 2b)
**Date:** 2026-02-05
**Status:** Approved & Implemented

### Context
Phase 2 extracted FlexLibs 2.0 method signatures and docstrings, but not the actual LibLCM calls inside each method body. This gap prevents:
- Converting C# LibLCM code to FlexLibs 2.0 Python
- Understanding which FlexLibs2 methods are thin wrappers vs. convenience abstractions
- Suggesting LibLCM fallbacks when FlexLibs2 lacks coverage

### Decision
Add Phase 2b to extract method-to-method mappings by:
1. Parsing FlexLibs2 method bodies with Python AST
2. Pattern-matching LibLCM interface calls
3. Classifying mapping types:
   - **1:1 direct**: `GetGloss` -> `sense.Gloss.get_String(ws)`
   - **Convenience wrapper**: Adds defaults, HVO resolution, null handling
   - **Composite**: Multiple LibLCM calls (factory + property sets)
   - **Pure Python**: Utility operations with no LibLCM calls

### Example Mapping
```python
# FlexLibs2 method
def GetGloss(self, sense_or_hvo, wsHandle=None):
    sense = self.__GetSenseObject(sense_or_hvo)
    wsHandle = self.__WSHandleAnalysis(wsHandle)
    gloss = ITsString(sense.Gloss.get_String(wsHandle)).Text
    return gloss or ""
```

Maps to:
```json
{
  "type": "convenience_wrapper",
  "primary_call": "ILexSense.Gloss.get_String(int ws)",
  "transformations": ["HVO resolution", "Default WS", "Null coalescing"]
}
```

### Consequences
- Enables bidirectional code conversion (C# <-> Python)
- Better documentation showing "under the hood" behavior
- Identifies coverage gaps in FlexLibs2
- Increases analyzer complexity (body parsing vs. signature-only)

---

## Decision 007: Navigation Graph with BFS Pathfinding
**Date:** 2026-02-05
**Status:** Approved & Implemented

### Context
The `get_navigation_path` tool originally used 5 hardcoded paths. Users needed paths between many more object pairs.

### Decision
Build a navigation graph from LibLCM property relationships and use BFS for pathfinding:
1. Extract OA/OS/OC/RA/RS/RC relationships from LibLCM properties
2. Build adjacency list graph (909 relationships)
3. Pre-compute 10 common paths (ILexEntry→ILexSense, etc.)
4. Use BFS for any path not precomputed
5. Auto-generate Python code patterns for discovered paths

### Implementation
- `build_navigation_graph.py` extracts relationships and builds graph
- `server.py` loads `navigation_graph.json` and uses BFS fallback
- Code patterns generated dynamically based on property types (OS→for loop, OA→assignment)

### Consequences
- Any valid navigation path can be found (not just 5 hardcoded)
- Users see Python code patterns for any path
- BFS limited to 5 hops to prevent performance issues
- Graph stored in JSON for fast loading

---

## Decision 008: Auto-Generated Method Descriptions
**Date:** 2026-02-05
**Status:** Approved & Implemented

### Context
Some FlexLibs methods (2 in stable, a few in 2.0) lacked docstrings, resulting in empty descriptions.

### Decision
Generate descriptions from method names using pattern matching:
- `Get*` → "Returns the {target}"
- `Set*` → "Sets the {target}"
- `Create*` → "Creates a new {target}"
- `Delete*` → "Deletes the {target}"
- `NumberOf*` → "Returns the count of {target}"
- `Is*`/`Has*`/`Can*` → "Checks whether {condition}"

### Implementation
- `generate_method_description()` in `flexlibs2_analyzer.py`
- Called as fallback when docstring is empty or too short
- CamelCase split to generate readable descriptions

### Consequences
- 100% description coverage for both FlexLibs APIs
- Descriptions are generic but accurate
- No manual annotation required for simple methods

---

## Decision 009: FlexLibs Stable Support
**Date:** 2026-02-05
**Status:** Approved & Implemented

### Context
Originally focused only on FlexLibs 2.0. FlexLibs stable (the original `flexlibs` package) has 71 methods that are still widely used.

### Decision
Support both FlexLibs versions:
1. Add `--flexlibs-path` argument to analyzer for stable version
2. Generate `flexlibs_api.json` alongside `flexlibs2_api.json`
3. Include FlexLibs stable in reverse mapping (`python_wrappers` field)
4. Same schema for both APIs

### Implementation
- `analyze_flexlibs_stable()` function handles single-class structure (FLExProject)
- Method prefix patterns used for categorization (Lexicon*, Text*, etc.)
- refresh.py supports `--flexlibs-only` flag

### Consequences
- Users can choose between stable (simpler) and 2.0 (comprehensive)
- Reverse mapping shows both wrapper options for LibLCM entities
- Maintains backward compatibility with existing FlexTools scripts
