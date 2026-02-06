# FlexTools AI Assistant - Project Plan

## Project Goal
Build an MCP server that enables AI assistants (Claude Code, Copilot, Gemini CLI) to help users write FlexTools scripts for editing FieldWorks lexicons. The MCP provides indexed, searchable documentation of the LibLCM and FlexLibs APIs with usage examples.

## Core Architecture

### The Stack
```
User Request → AI Assistant → MCP Server → Indexed Documentation
                     ↓
             Generated FlexTools Script
                     ↓
             FLExTools (IronPython)
                     ↓
             FlexLibs 2.0 (Python wrappers)
                     ↓
             LibLCM (C# library)
                     ↓
             FieldWorks Database
```

### Key Components
1. **LibLCM**: C# library - the ground truth API (2,295 entities extracted)
2. **FlexLibs stable**: Current Python wrapper (~71 methods in FLExProject class)
3. **FlexLibs 2.0**: Comprehensive Python wrapper (~90% coverage, 1,398 methods, 78 classes)
4. **FieldWorks**: Main application source - contains real usage examples
5. **FLExTools**: Existing script library - shallow but shows patterns

## Technical Approach

### Primary Method: Static Analysis (Not Heavy AI)
- Parse C# source with reflection/AST tools
- Parse Python source with ast module
- Link through deterministic mapping (FlexLibs 2.0 → C# is 1:1)
- Use AI only for enrichment, not extraction

### Agent Swarm Purpose: Validation & Completion
**NOT** for documentation extraction alone - for validating and completing FlexLibs 2.0 itself:
- Verify LibLCM understanding is complete and consistent
- Find gaps in FlexLibs 2.0 coverage
- Validate implementations are correct
- Generate tests for validation
- Mine usage patterns from FieldWorks

## Phased Implementation

### Phase 1: LibLCM Ground Truth (Week 1)
**Method**: Static analysis

**Tasks**:
- Parse LibLCM C# source completely
- Extract: classes, methods, properties, signatures, return types
- Extract XML documentation comments
- Build object relationship graph (Entry → Sense → Example)
- Document parent/child relationships

**Output**: `liblcm_complete.json` with full API model

**Verification**:
- **Option A**: Cross-reference with FieldWorks usage (find all LibLCM method calls in FieldWorks source)
- **Option B**: Validate relationship graph (inheritance hierarchies, property type references)
- **Option C**: Usage pattern validation (mostly done from your previous work)

**Tools**:
- C# reflection or Roslyn parser
- Custom Python scripts
- Agent assistance for consistency checking

---

### Phase 2: FlexLibs 2.0 Mapping & Validation (Week 1-2)
**Method**: Static analysis + agent validation

**Tasks**:
- Parse FlexLibs 2.0 Python source with ast module
- For each function, extract which C# method(s) it calls
- Map Python parameters to C# parameters
- Document any transformations/abstractions added
- **Validate against Phase 1 output**
- Find gaps (LibLCM methods without Python wrappers)
- Flag potential implementation issues

**Output**: `flexlibs2_mapping.json` linking Python API to C# API

**Verification**:
- Confirm C# calls in Python match Phase 1 extracted methods
- Identify the "almost all" gap - what's missing and why
- Flag suspicious implementations for manual review

**Tools**:
- Python ast parser
- Pattern matching scripts
- Agent for finding inconsistencies

---

### Phase 2b: Method-Level LibLCM Mapping (Week 2)
**Method**: AST body parsing + pattern matching

**Context**:
Phase 2 extracted FlexLibs 2.0 method signatures and docstrings, but not the actual LibLCM calls inside each method. This phase extracts method-to-method mappings to enable bidirectional code conversion between LibLCM C# and FlexLibs 2.0 Python.

**Tasks**:
- Enhance `flexlibs2_analyzer.py` to parse method bodies (not just signatures)
- Extract LibLCM method calls by pattern-matching against known interfaces
- Classify each FlexLibs 2.0 method by mapping type:
  - **1:1 direct**: Single LibLCM call (e.g., `GetGloss` → `sense.Gloss.get_String(ws)`)
  - **Convenience wrapper**: Adds defaults, null handling, HVO resolution
  - **Composite**: Combines multiple LibLCM calls (e.g., `Create` calls factory + sets properties)
  - **Pure Python**: No LibLCM calls, utility operations (e.g., `Sort`, `MoveUp`)
- Map FlexLibs 2.0 parameters to LibLCM parameters
- Document transformations (type conversions, default values)

**Output**: Enhanced `flexlibs2_api.json` with `lcm_mapping` field per method:
```json
{
  "name": "GetGloss",
  "signature": "GetGloss(sense_or_hvo, wsHandle=None)",
  "lcm_mapping": {
    "type": "convenience_wrapper",
    "primary_call": "ILexSense.Gloss.get_String(int ws)",
    "all_calls": [
      "ILexSense.Gloss.get_String(int ws)",
      "ITsString.Text"
    ],
    "param_mapping": {
      "sense_or_hvo": "ILexSense (resolved from HVO if needed)",
      "wsHandle": "ws (defaults to analysis WS)"
    },
    "transformations": [
      "HVO resolution via __GetSenseObject()",
      "Default WS via __WSHandleAnalysis()",
      "Null coalescing to empty string"
    ]
  }
}
```

**Use Cases**:
1. **C# to Python conversion**: Given `sense.Gloss.get_String(ws)`, suggest `project.Senses.GetGloss(sense, ws)`
2. **LibLCM fallback**: When FlexLibs 2.0 lacks coverage, show raw LibLCM equivalent
3. **Documentation enrichment**: Show "under the hood" LibLCM calls in docs
4. **Coverage analysis**: Identify which LibLCM methods have FlexLibs 2.0 wrappers

**Verification**:
- Sample 20 methods manually, verify extracted mappings match source
- Confirm all `lcm_interfaces_used` are covered in mappings
- Cross-reference with Phase 1 LibLCM extraction

**Tools**:
- Python `ast` module for body parsing
- Regex patterns for LibLCM interface detection
- Known interface list from Phase 1

---

### Phase 3: Test Generation (Week 2)
**Method**: Mine existing tests + manual seed tests

**Tasks**:
1. **Extract FieldWorks tests**:
   - Find C# test files in FieldWorks source
   - Extract test logic and expected behaviors
   - Convert to IronPython equivalents
   
2. **Create seed tests manually** (20-30 tests):
   - Common operations (add gloss, merge entries, etc.)
   - Known edge cases
   - Different writing systems
   
3. **Agent expansion** (optional):
   - Generate variations of seed tests
   - Different data, edge cases, boundaries
   - **Human validation required** (review 10% random sample)

**Output**: 
- `test_suite/` directory with pytest tests
- Test coverage report

**Verification**:
- Run tests against real FieldWorks database
- All tests must pass against known-good FlexLibs implementations
- Failed tests indicate either bugs or incorrect test expectations

**NOT doing now**: AI "linguist agent" generating tests - too risky without validation

---

### Phase 4: Usage Example Mining (Week 2-3)
**Method**: Grep/search + AI conversion

**Tasks**:
- Search FieldWorks C# source for LibLCM method calls
- Extract surrounding context (5-10 lines)
- Group by method/operation type
- Batch convert C# examples to IronPython via AI (50-100 per API call)
- Human review sample (20 examples) for accuracy
- Focus on **navigation patterns** more than specific operations

**Output**: `examples.json` with real-world usage patterns

**Example structure**:
```json
{
  "method": "ILexSense.Gloss.set_String",
  "examples": [
    {
      "context": "Adding gloss from UI",
      "csharp": "sense.Gloss.set_String(wsEn, \"house\");",
      "ironpython": "sense.Gloss.set_String(ws_en, 'house')",
      "source": "FieldWorks/Src/LexText/LexTextControls/GlossEditor.cs:142"
    }
  ]
}
```

**Tools**:
- ripgrep/grep for pattern finding
- Claude API for batch conversion
- Manual validation scripts

---

### Phase 5: Documentation Enrichment (Week 3)
**Method**: AI-assisted enhancement

**Tasks**:
1. **Fill missing descriptions**:
   - Where XML docs are empty
   - Generate from method name + signature + context
   
2. **Semantic categorization**:
   - Tag methods by linguistic concept (gloss, definition, phonology, morphology, etc.)
   - Tag by operation type (create, read, update, delete, merge)
   
3. **Add navigation patterns**:
   - Manually document for top 20 objects (Entry, Sense, Form, etc.)
   - "How to get from Entry to ExampleSentence"
   - "How to iterate over all entries"

**Output**: Enriched index with descriptions, categories, navigation

**Tools**:
- Claude API for batch description generation
- Manual curation for critical navigation patterns

---

### Phase 6: Index Construction (Week 3) - COMPLETE
**Method**: Combine all previous phases
**Status**: Complete - all index fields populated

**Structure** (object-centric organization):
```json
{
  "object": "ILexSense",
  "description": "Represents a meaning of a lexical entry",
  "methods": [
    {
      "name": "Gloss.set_String",
      "signature": "set_String(int ws, string text)",
      "returns": "void",
      "description": "Sets gloss text for specified writing system",
      "parameters": [
        {
          "name": "ws",
          "type": "int",
          "description": "Writing system handle (use WritingSystemFactory)"
        },
        {
          "name": "text", 
          "type": "string",
          "description": "Gloss text to set"
        }
      ],
      "examples": [...]
    }
  ],
  "properties": [
    {
      "name": "Definition",
      "type": "IMultiUnicode",
      "description": "Multi-lingual definition text"
    }
  ],
  "relationships": {
    "parent": {
      "type": "ILexEntry",
      "via": "SensesOS",
      "access_pattern": "entry.SensesOS[0]"
    },
    "children": {
      "type": "ILexExampleSentence",
      "via": "ExamplesOS",
      "access_pattern": "sense.ExamplesOS"
    }
  },
  "python_wrappers": {
    "flexlibs_light": null,
    "flexlibs_2": {
      "function": "LexiconSetSenseGloss",
      "signature": "LexiconSetSenseGloss(self, sense, text, ws)",
      "notes": "Accepts ws as string code or handle; adds type flexibility"
    }
  },
  "common_patterns": [
    "for sense in entry.SensesOS:\n    gloss = sense.Gloss.get_String(ws_en)"
  ],
  "test_coverage": {
    "has_tests": true,
    "test_count": 5,
    "edge_cases_covered": ["empty_string", "null_ws", "very_long_text"]
  }
}
```

**Output**: Complete indexed documentation with versioning

---

### Phase 7: MCP Server (Week 3-4) - COMPLETE
**Method**: Standard MCP implementation
**Status**: Complete - 6 tools implemented and working

**Implemented Tools**:
```python
@mcp.tool()
def get_object_api(object_type: str, include_flexlibs2: bool = True, include_liblcm: bool = True) -> dict:
    """Get all methods/properties for an object like ILexSense.
    Returns object-centric documentation including python_wrappers and relationships."""

@mcp.tool()
def search_by_capability(query: str, max_results: int = 10) -> list:
    """Keyword search with synonym expansion: 'add gloss' -> relevant methods."""

@mcp.tool()
def get_navigation_path(from_object: str, to_object: str) -> dict:
    """Find path from Entry to ExampleSentence using navigation graph.
    Uses precomputed paths + BFS fallback. Auto-generates code patterns."""

@mcp.tool()
def find_examples(method_name: str = None, operation_type: str = None, object_type: str = None, max_results: int = 5) -> list:
    """Get code examples from FlexLibs2 docstrings."""

@mcp.tool()
def list_categories() -> list:
    """List all API categories (lexicon, grammar, texts, etc.)."""

@mcp.tool()
def list_entities_in_category(category: str, source: str = "all") -> list:
    """List entities in a category."""

# FUTURE:
# def validate_script(script_text: str) -> dict:
#     """Check if script uses valid API calls. Returns errors/warnings/suggestions."""
```

**Search Implementation** (Current):
- Keyword search with synonym expansion
- Future: sentence-transformers + FAISS/Chroma for semantic search

**Output**: Working MCP server, deployed locally via `claude mcp add`

---

## Agent Swarm Architecture

### Orchestrator Agent
- Coordinates pipeline
- Resolves conflicts between agents  
- Maintains consistency
- Tracks completion percentage
- Manages validation gates between phases

### Specialized Agents

**Agent 1: LibLCM Analyzer**
- Parse C# source completely
- Extract API surface
- Build relationship graph
- Output: Phase 1 deliverable

**Agent 2: Consistency Validator**
- Verify Agent 1's model
- Cross-reference with FieldWorks usage
- Check relationship graph validity
- Flag gaps or inconsistencies

**Agent 3: FlexLibs 2.0 Mapper**
- Parse Python source
- Extract C# calls
- Validate against Agent 1's model
- Find gaps in coverage
- Flag suspicious implementations

**Agent 4: Example Miner**
- Search FieldWorks source
- Extract usage patterns
- Convert C# to IronPython
- Associate with methods

**Agent 5: Test Generator** (limited scope initially)
- Convert FieldWorks C# tests to IronPython
- Generate variations of manual seed tests
- **NOT** generating tests from scratch yet

**Agent 6: Documentation Enricher**
- Fill missing descriptions
- Semantic categorization
- Generate navigation patterns

**Agent 7: Integration Builder**
- Combine all outputs
- Build final index
- Generate MCP-ready format
- Create test coverage reports

### Validation Strategy

**Between each phase**:
1. Agent produces output
2. Automated validation checks
3. Human spot-check (10-20% sample)
4. Gate decision: proceed or iterate
5. If quality < 90%, refine and re-run

**Validation hierarchy**:
1. LibLCM C# source (immutable ground truth)
2. Static extraction (validated against #1)
3. FlexLibs 2.0 analysis (validated against #2)
4. Generated tests (validated against real database)
5. Documentation (validated against #2-4)

---

## Cost Optimization

### Use AI Sparingly
- **Static analysis** (free): Method signatures, parameter mapping
- **Pattern matching** (free): Linking FlexLibs to LibLCM
- **AI for enrichment only** (~$20-50):
  - Missing descriptions
  - Semantic categorization
  - C# to IronPython conversion
  - Example batching

### Local LLM Option
- For high-volume, low-criticality tasks
- Your server: 32GB RAM, 24GB VRAM
- Recommended models:
  - Llama 3.1 70B (quantized) for reasoning
  - Mixtral 8x7B for code analysis
  - Smaller models for simple pattern matching

### Paid API Budget
- Claude Opus/Sonnet for critical validation
- ~$50-100 total for entire project
- Batch operations to minimize calls

---

## Testing Infrastructure

### Test Database
- Snapshot production DB or create test fixture
- Reset between test runs
- Isolated from production data

### Test Harness
```python
class FlexLibsTestRunner:
    def setUp(self):
        self.db = create_test_database()
        
    def execute_test(self, test_code: str):
        try:
            exec(test_code, {'DB': self.db})
            return validate_db_state(self.db)
        finally:
            self.tearDown()
    
    def tearDown(self):
        self.db.rollback_or_restore()
```

### Validation Loop
1. Agent generates test
2. Execute against real database
3. Record pass/fail
4. Manual review failures
5. Feed learnings back to agents

---

## User Abstraction Choices

### Three Levels
1. **LibLCM (C#)**: Direct calls, most powerful, most verbose
2. **FlexLibs Light**: Limited (~40 functions), stable
3. **FlexLibs 2.0**: Comprehensive (~90% coverage), Pythonic, beta

### MCP Default Behavior
- **Auto mode** (default): Use FlexLibs 2.0 when available, fall back to LibLCM
- **Explicit mode**: User specifies preference
- **Fallback allowed**: If FlexLibs 2.0 missing, suggest LibLCM alternative

### User Control
```python
# User can set preference in query:
search_fieldworks_api(
    query="add gloss",
    abstraction_level="flexlibs_2",  # or "liblcm" or "auto"
    fallback_allowed=True
)
```

---

## Version Management

### Index Versioning
```json
{
  "index_version": "1.0.0",
  "liblcm_version": "9.1.0",
  "flexlibs_version": "2.0.0-beta",
  "fieldworks_version": "9.1.x",
  "generated_date": "2025-02-05"
}
```

### Update Strategy
- Track which FieldWorks/LibLCM version index is based on
- When LibLCM updates, re-run extraction pipeline
- Maintain multiple index versions if supporting multiple FieldWorks versions
- Deprecation warnings when methods change

---

## Out of Scope (For Now)

### Dropped / Deferred
- ❌ **Linguist agent**: Too risky without validation framework
- ❌ **Symbolic execution**: Unnecessary complexity
- ❌ **Complete test generation**: Manual seed tests sufficient initially
- ❌ **Auto-fixing bugs**: Just flag issues for now
- ❌ **Multi-version support**: Start with current FieldWorks version

### Future Enhancements
- Advanced test generation with linguistic validation
- Auto-migration tools (FlexLibs Light → 2.0)
- Performance optimization suggestions
- Integration with FieldWorks CI/CD

---

## Success Metrics

### Quality Gates
- **Phase 1**: >99% LibLCM API coverage (verify against FieldWorks usage)
- **Phase 2**: >90% FlexLibs 2.0 correctly mapped to LibLCM
- **Phase 3**: >95% of generated tests pass against real database
- **Phase 4**: >90% of usage examples correctly converted
- **Phase 7**: User can generate working scripts with <2 iterations

### User Testing (Before Phase 9)
- 5 beta users
- 20 real script generation tasks
- Measure: success rate, iteration count, user satisfaction
- Gate: Must achieve >80% first-try success before proceeding

---

## Timeline

### Actual Progress (as of 2026-02-05)

| Phase | Status | Key Outputs |
|-------|--------|-------------|
| Phase 1: LibLCM Ground Truth | COMPLETE | 2,295 entities in flex-api-enhanced.json |
| Phase 2: FlexLibs 2.0 Mapping | COMPLETE | 1,398 methods with lcm_mapping |
| Phase 2b: Method-Level Mapping | COMPLETE | 68% LibLCM coverage, mapping types classified |
| Phase 3: Test Generation | PARTIAL | Test infrastructure pending |
| Phase 4: Example Mining | PARTIAL | 82% docstring examples extracted |
| Phase 5: Documentation Enrichment | COMPLETE | 100% description coverage, semantic categorization |
| Phase 6: Index Construction | COMPLETE | relationships, python_wrappers, common_patterns |
| Phase 7: MCP Server | COMPLETE | 6 tools working, BFS pathfinding |

### Original Schedule (for reference)
- **Week 1**: Phase 1 (LibLCM extraction + validation)
- **Week 2**: Phase 2 (FlexLibs 2.0 mapping) + Phase 3 (test generation starts)
- **Week 3**: Phase 4 (examples) + Phase 5 (enrichment) + Phase 6 (index construction)
- **Week 4**: Phase 7 (MCP server) + testing
- **Week 5**: Beta user testing + iteration
- **Week 6**: Production deployment

---

## Risk Mitigation

### Top Risks
1. **Agent quality varies** → Heavy validation, human spot-checks
2. **FlexLibs 2.0 has bugs** → Tests will catch them, flag for manual fix
3. **Index too large for effective search** → Hierarchical/filtered search
4. **AI generates plausible but wrong info** → Multiple validation layers
5. **Cross-language mapping breaks** → Static analysis catches most issues

### Mitigation Strategy
- Validate early and often
- Human review gates between phases
- Start small (100 methods) before scaling
- Test against real database continuously
- Don't trust AI without verification

---

## Next Immediate Steps

### Week 1 Priority
1. **Verify Phase 1 work** (your previous LibLCM extraction)
2. **Build test harness** (critical infrastructure)
3. **Parse FlexLibs 2.0 source** (static analysis)
4. **Extract 10 sample objects** end-to-end
5. **Validate with manual test** (can Claude generate working scripts from this?)

### Decision Point
**End of Week 1**: If 10-object sample works well → scale up
**If not**: Identify what's missing and iterate

---

## Tools & Technology Stack

### Development
- **Python 3.10+** for MCP server and agents
- **ast module** for Python parsing
- **Roslyn or C# reflection** for C# parsing
- **sentence-transformers** for semantic search
- **FAISS or Chroma** for vector storage
- **pytest** for test suite

### Agent Orchestration
- **Ralph** (https://github.com/snarktank/ralph) for automation
- Or custom Python orchestration
- Or LangGraph if more complex coordination needed

### Deployment
- MCP server runs locally (Python)
- Works with Claude Code, Copilot, Gemini CLI (MCP support confirmed)
- Index stored as JSON files or SQLite
- Usage of the MCP will assume required Fieldworks and liblcm binaries are installed (if only targeting LIBLCM). When creating Python scripts with the MCP, we will assume that either flexLibs (stable) or flexlibs 2.0 is installed. 

---

## Documentation Structure

### Final Index Files
```
/index
  /liblcm
    - classes.json
    - methods.json
    - relationships.json
  /flexlibs
    - light_mapping.json
    - v2_mapping.json
  /examples
    - fieldworks_usage.json
    - navigation_patterns.json
  /tests
    - test_suite/
    - coverage_report.json
  metadata.json
  version.json
```

### MCP Server Files
```
/mcp_server
  server.py
  search.py
  validation.py
  requirements.txt
  README.md
```

---

This is the complete plan based on our discussion. The key insight: **Use static analysis primarily, agents for validation and enrichment, not for generating tests from scratch (yet)**.