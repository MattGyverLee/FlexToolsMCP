# Why Use AI for FieldWorks Tasks?

FieldWorks has a GUI. FlexTools has a module system. LibLCM has documentation. So why would anyone want an AI assistant involved?

## The Manual Approach Works... Sometimes

### For Simple Tasks

If you need to:
- Add a single entry
- Edit a gloss
- Run an existing FlexTools module

Then yes, use the GUI. It's what it's designed for.

### For Repetitive Tasks

If you need to:
- Change 50 glosses that follow a pattern
- Delete entries matching certain criteria
- Bulk-update semantic domains

You could:
1. Learn the FlexTools module structure
2. Learn the FlexLibs API (or LibLCM)
3. Write the module
4. Debug it
5. Test it
6. Run it

Or you could ask: *"Delete all senses where the gloss contains 'obsolete'"*

## The Learning Curve Problem

### How Long Does It Take?

To write your first useful FlexTools module, you need to understand:

| Topic | Estimated Learning Time |
|-------|------------------------|
| FlexTools module structure | 2-4 hours |
| FlexLibs API basics | 4-8 hours |
| LibLCM object model | 8-20 hours |
| pythonnet quirks | 2-4 hours |
| FLEx data conventions | 4-8 hours |
| **Total** | **20-44 hours** |

That's assuming you already know Python and have programming experience.

### The Occasional User Problem

Most FLEx users need to write a module once or twice a year. By the time the next need arises, they've forgotten:
- Which API functions exist
- How to traverse from entries to senses
- The module boilerplate
- Why their last module worked

They end up re-learning everything each time.

### The Dual-Language Barrier

Before FlexLibs 2.0 and this MCP, the biggest barrier was the split between two programming paradigms:

**Simple operations: The "Python way" (FlexLibs)**
```python
# Get a gloss - clean, Pythonic
gloss = lexicon.GetGloss(entry)
```

**Advanced operations: The "C# way" (LibLCM)**
```python
# Get part of speech - requires understanding:
# - .NET object model
# - Interface inheritance
# - pythonnet casting
# - Collection suffixes (OC, OS, RA, etc.)
for msa in entry.MorphoSyntaxAnalysesOC:
    if msa.ClassName == 'MoStemMsa':
        concrete = IMoStemMsa(msa)  # Cast required!
        pos = concrete.PartOfSpeechRA
```

The moment you needed something FlexLibs stable didn't cover (~95% of FLEx features), you had to:

1. **Switch mental models** - From Python idioms to .NET patterns
2. **Learn interface hierarchies** - Which properties belong to which interfaces
3. **Handle pythonnet casting** - Objects typed as base interfaces need explicit casting
4. **Decode naming conventions** - `OC` vs `OS` vs `RA` vs `RS`
5. **Navigate sparse documentation** - LibLCM docs assume C# familiarity

This created a cliff: simple tasks were easy, but anything beyond basic lexicon access required a deep dive into .NET internals.

**FlexLibs 2.0 + MCP flattens this cliff.** The AI handles the translation between what you want and how LibLCM implements it.

## What AI Changes

### Instant Access to Expertise

Instead of searching documentation, reading source code, and experimenting:

```
User: "How do I get all senses that have a specific semantic domain?"

AI: [Searches MCP, finds LexSenseOperations.GetBySemanticDomain]
    Here's the function and an example...
```

The AI has the full API indexed and searchable. It doesn't forget between sessions.

### Natural Language Intent

You describe what you want, not how to implement it:

| Manual Approach | AI Approach |
|-----------------|-------------|
| "I need to iterate LexEntryRepository, check MorphoSyntaxAnalysesOC, cast to IMoStemMsa, compare PartOfSpeechRA.Guid..." | "Find entries with part of speech 'noun'" |

The translation from intent to implementation is the AI's job.

### Error Prevention

The AI (with MCP) knows about:
- pythonnet casting requirements
- Required vs optional parameters
- Common mistakes and how to avoid them
- Transaction handling for write operations

You get warnings before runtime, not cryptic errors after.

### Rapid Iteration

```
User: "Delete senses with 'test' in the gloss"
AI: [Generates code, runs dry-run]
    "Would delete 3 senses: ..."

User: "Actually, only if they also have no examples"
AI: [Modifies code, runs dry-run]
    "Would delete 1 sense: ..."

User: "Perfect, do it"
AI: [Runs with write access]
    "Deleted 1 sense"
```

Each iteration takes seconds, not hours of debugging.

### On-the-Spot Debugging

When something doesn't work, you don't have to figure it out alone:

```
User: "Why did that fail with 'AttributeError: PartOfSpeechRA'?"

AI: "That's a pythonnet casting issue. The MSA objects in
    MorphoSyntaxAnalysesOC are typed as the base interface
    IMoMorphSynAnalysis, which doesn't have PartOfSpeechRA.

    You need to cast to the concrete type first:

    from flexlibs2.code.lcm_casting import get_pos_from_msa
    pos = get_pos_from_msa(msa)

    Let me fix the code..."
```

Compare this to traditional debugging:
1. Google the error message (few relevant results for LibLCM)
2. Search FieldWorks source code
3. Read through interface definitions
4. Experiment with different approaches
5. Eventually find a Stack Overflow post about pythonnet casting

The AI has the context of your code, the MCP's casting index, and can explain *why* it failed in domain-specific terms - not just *what* failed.

## Use Cases Where AI Excels

### One-Off Data Cleaning

"I imported data from a legacy system and need to clean up artifacts."

- Remove specific character sequences from glosses
- Fix encoding issues in vernacular text
- Merge duplicate entries
- Standardize formatting

Writing a module for each of these? Tedious. Asking the AI? Quick.

### Exploratory Queries

"Are there any entries where the citation form doesn't match the lexeme form?"

You might not even know if this is a problem until you check. The AI can query and report without you writing any code.

### Complex Bulk Operations

"For each entry with POS 'verb', if there's no example sentence, add a placeholder example with the text '[needs example]'."

This requires:
- Iterating entries
- Checking POS (with casting!)
- Checking for existing examples
- Creating new example objects
- Setting multilingual text

A significant module to write manually. A single request with AI.

### Learning the API

"Show me how to access the phonological features of an entry's pronunciation."

The AI can explain the object path, show examples, and answer follow-up questions. It's like having a FlexLibs expert available 24/7.

### Prototyping Modules

"I want a module that exports lexicon data to a specific JSON format."

The AI generates a working first draft. You refine it. Much faster than starting from scratch.

## When NOT to Use AI

### Production Modules

If you're writing a module that will be:
- Used repeatedly over months/years
- Shared with other users
- Part of a larger workflow

Then write it properly, with full error handling, documentation, and testing. Use the AI to help draft it, but own the final code.

### Performance-Critical Operations

AI-generated code prioritizes correctness and readability over performance. For operations on very large databases (100k+ entries), you may need hand-optimized code.

### Security-Sensitive Operations

If you're working with sensitive data, understand every line of code that runs. Don't blindly trust AI-generated operations on production data.

## The Hybrid Approach

The most effective workflow combines both:

1. **Use AI for discovery**: "What APIs exist for working with semantic domains?"
2. **Use AI for prototyping**: "Generate a module that does X"
3. **Review and understand**: Read the generated code
4. **Refine manually**: Add error handling, edge cases
5. **Use AI for iteration**: "The module fails when an entry has no senses, fix it"

You get the speed of AI with the reliability of human oversight.

## Cost-Benefit Summary

| Approach | Time Investment | Skill Required | Flexibility |
|----------|-----------------|----------------|-------------|
| GUI only | Low per task | Low | Limited to GUI features |
| Manual module writing | High upfront | High | Maximum |
| AI-assisted | Low per task | Low-Medium | High |

For occasional users doing varied tasks, AI assistance provides the best return on time invested.

## The Real Question

It's not "Should I use AI instead of learning the tools?"

It's "How can AI help me accomplish my linguistic documentation goals faster?"

The tools exist to serve the data. The AI exists to help you use the tools. Neither replaces your judgment about what your data needs.
