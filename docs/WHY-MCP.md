# Why You Need an MCP for FieldWorks and FlexTools

This document explains why working with FieldWorks and FlexTools benefits from a specialized MCP (Model Context Protocol) server, rather than just asking an AI assistant directly.

## The FieldWorks Complexity Problem

### A Deep, Interconnected Data Model

FieldWorks Language Explorer (FLEx) manages linguistic data through LibLCM (Language and Culture Model), a sophisticated C# object model with:

- **2,295+ interfaces and classes** - Far too many to memorize
- **Deep inheritance hierarchies** - `IMoStemMsa` extends `IMoMorphSynAnalysis` extends `ICmObject`
- **Complex relationships** - Entries contain senses, which contain examples, which contain translations...
- **Multiple access patterns** - Properties like `SensesOS` (owning sequence), `MorphoSyntaxAnalysesOC` (owning collection), `PartOfSpeechRA` (reference atomic)

### The Suffix Convention

LibLCM uses suffixes to indicate relationship types:

| Suffix | Meaning | Example |
|--------|---------|---------|
| `OS` | Owning Sequence (ordered) | `entry.SensesOS` |
| `OC` | Owning Collection (unordered) | `entry.MorphoSyntaxAnalysesOC` |
| `OA` | Owning Atomic (single owned) | `entry.LexemeFormOA` |
| `RS` | Reference Sequence | `sense.SemanticDomainsRS` |
| `RC` | Reference Collection | `sense.AnthroCodesRC` |
| `RA` | Reference Atomic | `msa.PartOfSpeechRA` |

An AI without this knowledge will guess wrong constantly.

### The pythonnet Casting Problem

When using LibLCM from Python via pythonnet, collections return objects typed as their base interface:

```python
# This looks correct but FAILS at runtime
for msa in entry.MorphoSyntaxAnalysesOC:
    pos = msa.PartOfSpeechRA  # AttributeError!
    # msa is typed as IMoMorphSynAnalysis, not IMoStemMsa
```

The fix requires knowing:
1. Which concrete types exist (MoStemMsa, MoDerivAffMsa, MoInflAffMsa, etc.)
2. Which properties belong to which types
3. How to cast in pythonnet: `IMoStemMsa(msa)`

No AI model has this in its training data. It must be looked up.

## The FlexTools Development Challenge

### Three API Layers

Developers must navigate three interconnected APIs:

```
FlexLibs 2.0 (Python, ~1,400 methods)
    |
    v
FlexLibs stable (Python, ~71 methods)
    |
    v
LibLCM (C#, 2,295 entities)
```

Each layer has different:
- Naming conventions
- Error handling patterns
- Documentation quality
- Coverage of FLEx features

### The "Which Function?" Problem

To get a sense's gloss, you could:

1. **FlexLibs 2.0**: `LexSenseOperations.GetGloss(sense, writing_system)`
2. **FlexLibs stable**: `lexicon.GetGloss(entry)` (entry level only)
3. **LibLCM direct**: `sense.Gloss.get_String(ws_handle).Text`

Without knowing all three options and their trade-offs, an AI will:
- Invent functions that don't exist
- Use the wrong abstraction level
- Miss simpler solutions

### The Module Boilerplate Problem

Every FlexTools module requires specific boilerplate:

```python
# -*- coding: utf-8 -*-
from flextoolslib import *

docs = {FTM_Name: "Module Name",
        FTM_Version: "1.0",
        FTM_ModifiesDB: True,
        FTM_Synopsis: "What it does",
        FTM_Description: "Detailed description"}

def Main(project, report, modify=True):
    # Your code here
    pass
```

This structure isn't well-documented online. AI models frequently get it wrong.

## Why a Generic AI Fails

### Limited Training Data

AI models are trained on public code. FieldWorks/FlexTools code is:
- Mostly in private/institutional repositories
- Sparse on GitHub compared to mainstream frameworks
- Often outdated or incomplete in examples

### No Runtime Context

A generic AI cannot:
- List your actual FLEx projects
- Inspect your database structure
- Test code before suggesting it
- Know which writing systems you have

### Hallucination Risk

Without authoritative API documentation, AI models confidently suggest:
- Functions that don't exist (`lexicon.GetAllSenses()`)
- Wrong parameter orders
- Deprecated patterns
- Syntax that works in C# but not Python

## What the MCP Provides

### Authoritative API Indexes

The MCP maintains indexed, searchable documentation:

| Index | Contents | Update Frequency |
|-------|----------|------------------|
| `liblcm_api.json` | 2,295 C# entities | On LibLCM release |
| `flexlibs_api.json` | 71 stable methods | On FlexLibs release |
| `flexlibs2_api.json` | 1,400+ methods | On FlexLibs 2.0 release |
| `casting_index.json` | Pythonnet casting rules | Derived from LibLCM |
| `navigation_graph.json` | Object relationships | Derived from LibLCM |

### Domain-Specific Search

Instead of keyword matching, the MCP understands linguistics:

| User Query | MCP Understands |
|------------|-----------------|
| "part of speech" | POS, category, grammatical category, word class |
| "definition" | meaning, gloss, translation |
| "headword" | lexeme, citation form, lemma |

### Workflow Guardrails

The MCP enforces best practices:

1. **Discovery first** - Find the right APIs before writing code
2. **Casting checks** - Warn about pythonnet issues before runtime
3. **Dry-run default** - Test code in read-only mode first
4. **Explicit write** - Require confirmation for database modifications

### Direct Execution

Beyond code generation, the MCP can:
- Execute operations directly on FLEx databases
- Show what would change before committing
- Handle the FlexLibs2 initialization automatically

## Real-World Comparison

### Without MCP

```
User: "Delete senses with 'test' in the gloss"

AI: "Here's some code that should work..."
[Writes code using non-existent functions]
[Forgets pythonnet casting]
[Skips error handling]
[User spends 2 hours debugging]
```

### With MCP

```
User: "Delete senses with 'test' in the gloss"

AI: [Calls start tool]
    -> Finds LexSenseOperations.Delete, GetGloss
    -> Checks for casting requirements (none for Gloss)
    -> Gets delete examples
    -> Returns complete code skeleton

AI: [Calls run_operation with write_enabled=False]
    -> "Would delete 3 senses: ..."

User: "Looks good, do it"

AI: [Calls run_operation with write_enabled=True]
    -> "Deleted 3 senses"
```

## The Bottom Line

| Challenge | Without MCP | With MCP |
|-----------|-------------|----------|
| Finding the right function | Guessing/hallucination | Indexed search |
| Understanding relationships | Trial and error | Navigation graph |
| pythonnet casting | Runtime errors | Compile-time warnings |
| Code correctness | Often wrong | Verified patterns |
| Testing safely | Hope for the best | Dry-run first |
| Time to working code | Hours | Minutes |

An MCP doesn't make the AI smarter - it gives the AI the right reference materials and tools to work with a complex, specialized domain effectively.
