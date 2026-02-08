# FlexTools MCP Innovations

This document explains the unique features and innovations that FlexTools MCP provides beyond simple code indexing approaches.

## The Problem with Simple Code Indexing

Traditional code indexing (like what language servers or basic documentation tools provide) captures:
- Function signatures and parameters
- Class hierarchies
- Docstrings and comments
- File locations

This is useful for code navigation, but it's **insufficient for AI-assisted code generation** in complex domains like FieldWorks/LibLCM because:

1. **No semantic understanding** - An index knows `GetGloss()` exists, but not that it's related to "translations" or "meanings"
2. **No cross-library awareness** - No connection between Python wrappers and the C# APIs they wrap
3. **No runtime context** - Can't detect pythonnet casting issues that only appear at runtime
4. **No domain knowledge** - Doesn't understand linguistic concepts like "part of speech" or "morpheme"
5. **No relationship graphs** - Can't answer "how do I get from an entry to its example sentences?"

## FlexTools MCP Innovations

### 1. Pythonnet Casting Detection

**Problem:** When iterating LCM collections in pythonnet, objects are returned typed as base interfaces. Properties from derived interfaces cause `AttributeError` at runtime.

```python
# This FAILS at runtime - PartOfSpeechRA is on IMoStemMsa, not IMoMorphSynAnalysis
for msa in entry.MorphoSyntaxAnalysesOC:
    pos = msa.PartOfSpeechRA  # AttributeError!
```

**Innovation:** The `casting_index.json` pre-computes which properties require casting:

```json
{
  "PartOfSpeechRA": {
    "defined_on": ["IMoStemMsa", "IMoInflAffMsa", "IMoUnclassifiedAffixMsa"],
    "requires_cast_from": ["IMoMorphSynAnalysis", "ICmObject"],
    "pythonnet_warning": true
  }
}
```

The `resolve_property` tool surfaces these warnings **before** code is written, and suggests the FlexLibs2 casting helpers.

### 2. Semantic Domain Categorization

**Problem:** LibLCM has 2,295 entities. Finding the right one requires understanding the domain, not just searching names.

**Innovation:** Entities are categorized by semantic domain using namespace and naming pattern analysis:

| Category | Examples | Pattern |
|----------|----------|---------|
| `lexicon` | ILexEntry, ILexSense | Names starting with `ILex`, `Lex` |
| `grammar` | IMoStemMsa, IPhPhoneme | Names starting with `IMo`, `IPh` |
| `texts` | IStText, IStPara | Names starting with `ISt`, `IText` |
| `wordform` | IWfiWordform, IWfiAnalysis | Names starting with `IWfi` |
| `reversal` | IReversalIndex | Names starting with `IReversal` |

This enables queries like "show me all lexicon entities" without knowing exact names.

### 3. Navigation Graph

**Problem:** "How do I get from an entry to its example sentences?" requires understanding the object model.

**Innovation:** Pre-computed navigation paths between object types:

```
ILexEntry -> ILexSense: entry.SensesOS
ILexSense -> ILexExampleSentence: sense.ExamplesOS
ILexEntry -> IMoMorphSynAnalysis: entry.MorphoSyntaxAnalysesOC
```

The `get_navigation_path` tool returns traversal code, not just relationship names.

### 4. Reverse Mapping (LibLCM -> FlexLibs)

**Problem:** User finds `ILexEntry.SensesOS` in LibLCM docs but wants the FlexLibs2 wrapper.

**Innovation:** Bi-directional mapping between C# and Python layers:

```
ILexEntry.SensesOS <-> LexEntryOperations.GetSenses()
ILexSense.Gloss <-> LexSenseOperations.GetGloss() / SetGloss()
```

This is embedded in the indexes, enabling seamless API discovery regardless of which layer the user starts from.

### 5. Cross-Library Linking

**Innovation:** FlexLibs2 entities explicitly link to the LibLCM interfaces they wrap:

```json
{
  "name": "GetPartOfSpeech",
  "lcm_interface": "ILexSense",
  "lcm_property": "MorphoSyntaxAnalysesOC -> PartOfSpeechRA",
  "description": "Gets the Part of Speech for a sense"
}
```

This helps users understand what happens "under the hood" and debug issues.

### 6. Synonym Expansion for Natural Language Search

**Problem:** Users say "part of speech" but the API uses "POS", "category", or "grammatical category".

**Innovation:** Domain-specific synonym mappings:

```python
SYNONYMS = {
    "part of speech": ["pos", "category", "grammatical category", "word class"],
    "definition": ["meaning", "gloss", "translation"],
    "example": ["citation", "illustration", "sample sentence"],
    "headword": ["lexeme", "citation form", "lemma"],
}
```

The `search_by_capability` tool expands queries using these synonyms.

### 7. Pattern Extraction from Docstrings

**Innovation:** Common code patterns extracted from FlexLibs2 docstrings and examples:

| Pattern | Description | Source |
|---------|-------------|--------|
| `iterate_entries` | Loop over all lexical entries | LexEntryOperations.GetAll() |
| `filter_by_pos` | Filter entries by part of speech | FilterOperations examples |
| `batch_update` | Update multiple objects in transaction | Various Operations classes |

The `find_examples` tool returns these patterns by operation type (create, read, update, delete).

### 8. Workflow Orchestration with `start`

**Problem:** Users skip discovery and go straight to `run_operation`, leading to errors.

**Innovation:** The `start` tool enforces a discovery workflow:

```
start(task="delete senses with test in gloss")
  |
  +-> search_by_capability("delete sense gloss")
  +-> get_navigation_path(ILexEntry, ILexSense)
  +-> resolve_property("Gloss") - check casting
  +-> find_examples(operation_type="delete")
  |
  v
Returns: Complete action plan with code skeleton
```

This ensures users understand the APIs before writing code.

### 9. Direct Execution with Safety Rails

**Innovation:** Execute operations directly on FieldWorks databases with:

- **Dry-run mode** (default): Shows what would happen without making changes
- **Write mode**: Requires explicit `write_enabled=True`
- **Project specification**: Must name the target project
- **Transaction wrapping**: All changes are atomic

```python
run_operation(
    project_name="TestProject",
    code="...",
    write_enabled=False  # Default: dry run
)
```

### 10. Multi-API Bridging

**Innovation:** Unified access to three API layers with different trade-offs:

| Layer | Coverage | Documentation | Use Case |
|-------|----------|---------------|----------|
| `flexlibs2` | ~1,400 methods | 99% described, 82% examples | New development |
| `flexlibs_stable` | ~71 methods | Basic | Legacy compatibility |
| `liblcm` | 2,295 entities | Minimal | Maximum flexibility |

The `start` tool accepts a `flavor` parameter to target the appropriate layer.

## Comparison: Simple Index vs FlexTools MCP

| Capability | Simple Index | FlexTools MCP |
|------------|--------------|---------------|
| Find function by name | Yes | Yes |
| Find function by capability | No | Yes (synonym expansion) |
| Navigate object relationships | No | Yes (navigation graph) |
| Detect casting requirements | No | Yes (casting index) |
| Cross-reference C#/Python | No | Yes (reverse mapping) |
| Provide code examples | Limited | Yes (pattern extraction) |
| Guide workflow | No | Yes (`start` tool) |
| Execute code directly | No | Yes (with safety rails) |

## Technical Implementation

### Index Generation Pipeline

```
Source Code
    |
    v
+-------------------+     +-------------------+     +-------------------+
| flexlibs2_analyzer|     | liblcm_extractor  |     | build_casting_index|
| (Python AST)      |     | (.NET reflection) |     | (cross-reference)  |
+-------------------+     +-------------------+     +-------------------+
    |                         |                         |
    v                         v                         v
flexlibs2_api.json      liblcm_api.json          casting_index.json
                              |
                              v
                    +-------------------+
                    | build_reverse_    |
                    | mapping.py        |
                    +-------------------+
                              |
                              v
                    +-------------------+
                    | build_navigation_ |
                    | graph.py          |
                    +-------------------+
                              |
                              v
                    navigation_graph.json
```

### Refresh Command

All indexes can be regenerated from source:

```bash
python src/refresh.py
```

This ensures indexes stay synchronized with upstream changes.

## Future Innovations

1. **Semantic embeddings** - Vector search using sentence-transformers for even better natural language queries
2. **Code validation** - Static analysis of generated code before execution
3. **Test generation** - Generate unit tests for generated modules
4. **Undo/rollback** - Transaction-level undo for write operations
