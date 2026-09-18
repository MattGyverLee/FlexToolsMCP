# Data Model: parser-check CP2a

Entities CP2a introduces or reshapes in the `flexicon` package. Types are
described by behaviour and by the LCM objects they carry, since flexicon
Operations methods carry no PEP 484 annotations -- types live in the
docstring and in the `.pyi` stub (`LexSenseOperations.py:172-231` is the
house template).

---

## 1. `ParserOperations` -- NEW

The parser area of the project object, reached as `project.Parser`.

| Aspect | Value |
|---|---|
| File | `flexicon/code/Parser/ParserOperations.py` |
| Base | `BaseOperations` (`BaseOperations.py:590`) |
| Construction | `__init__(self, project)` delegating via `super().__init__(project)`, re-documented -- the `ReversalIndexOperations.py:68-76` template |
| Reaches LCM by | `self.project` (the `FLExProject`), `self.project.project` (the `LcmCache`, assigned `FLExProject.py:340`) |
| Registration | lazy read-only `@property` on `FLExProject` with a function-local import and a `__dict__` cache, keyed `_parser_ops` -- the `FLExProject.py:2181-2209` template |
| Decorators | `@OperationsMethod` on every public method; `@wrap_enumerable` stacked **above** it on any method returning an iterable (order matters, `BaseOperations.py:172`) |

**Held state.** At most one loaded grammar, per SC-014. The instance holds
the parser handle and the resolved availability status; switching projects
releases the previous grammar. Nothing else is cached -- the currency
question is answered by asking the parser, not by a local flag, because a
local flag is exactly what goes stale.

**Write surface: none, by construction.** FR-002 requires the absence to be
stated where a future contributor reads it, because the read-only safety
claim of both CP2b tools rests on it. The class therefore carries no
`_EnsureWriteEnabled` call, no `_TransactionCM` block, and no method whose
name records or files a result -- and a standing test enumerates the public
surface to assert it (Principle III: a control, not a promise).

---

## 2. `ParserAvailability` -- NEW (value object)

The answer to "can this project reach the parser?", returned rather than
raised.

| Field | Type | Meaning |
|---|---|---|
| `available` | `bool` | Whether parser operations may be called. |
| `reason` | `str` | Why not, when `available` is `False`. Empty when available. Must state *what was checked*, never imply more (Principle V). |
| `version` | `str` or `None` | The detected parser component version. **Reported, never compared** (FR-006, SC-002). `None` when unavailable. |

**Reason values** correspond to the three US1 acceptance scenarios and to
the checks FR-004 and FR-005 mandate:

| Condition | What the reason states |
|---|---|
| Component absent or relocated | that the parser component could not be found, and where it was looked for |
| Component from a different installation | that the component's installation directory does not match the data model's, naming both -- FR-004's check is **directory equality only** |
| A required operation is missing | which operation was not found by inspection (FR-005) |

**Constraint.** Constructing this object never raises, on any machine, in
any of the above conditions. That is SC-001, and it is the single property
tier A1 exists to test.

**No template exists for this shape** -- see `research.md` F2 and D-A4.
flexicon today raises or silently yields `None`; this is the first
degrading-with-reason return in the package.

---

## 3. Availability state transitions

```
                  (import)
                     |
                     v
          +---------------------+
          |   not yet probed    |   <-- FR-003: import never triggers loading
          +---------------------+
                     |
              first use of project.Parser
                     |
                     v
          +---------------------+
          |      probing        |   directory equality (FR-004)
          |                     |   then member inspection (FR-005)
          +---------------------+
                 /         \
      all checks pass    any check fails
              |               |
              v               v
     +---------------+  +------------------------+
     |   available   |  | unavailable(reason)    |
     | version read, |  | raises nothing         |
     | never compared|  | operations refuse with |
     +---------------+  | that same reason       |
              |         +------------------------+
              |
     grammar loaded on first parse
              |
              v
     +--------------------------+
     | grammar held             |  at most one (SC-014)
     | currency asked before    |  SC-015: 0 parses from an
     | every reuse              |  unconfirmed grammar
     +--------------------------+
          |               ^
          | stale         | reload = reset, then update
          +---------------+  (D-A5 -- never a bare update)
```

**The probe is terminal per instance.** Once resolved, the status is held;
it is not re-probed per call. Switching projects constructs a new area and
releases the previous grammar.

---

## 4. Reshaped: `TextOperations`

| Change | Detail |
|---|---|
| ADD `GetGenres(text)` | Returns every genre assigned to the text; empty list when none. Reads `GenresRC` as a reference collection. Template: `LexSenseOperations.GetSemanticDomains` (`LexSenseOperations.py:1602`). Decorated `@wrap_enumerable @OperationsMethod`. |
| UNCHANGED `GetGenre(text)` | Stays exactly as it is (`TextOperations.py:660`, `GenresRC.FirstOrDefault()`, `None` when empty). Changing its cardinality would be a silent breaking change no structural ratchet would catch -- see D-A9. |

`GenresRC` exists only on `IText` in LCM. There is no entry-level or
sense-level genre field, so FR-007 is fully satisfied at the text level.

---

## 5. Reshaped: `AllomorphOperations`

| Change | Detail |
|---|---|
| ADD `GetOwningEntry(allomorph_or_hvo)` | Returns the `ILexEntry` that owns the allomorph, or `None`. Resolves via `OwnerOfClass(LexEntryTags.kClassId)` and null-guards before casting. Template: `LexSenseOperations.py:2826` -- **not** the one-hop `.Owner` siblings, which are unguarded (D-A8). |

FR-008 is explicit that the relationship already exists in the data model
(`MoForm.OwningEntry`); the gap is that the library never wrapped it. The
existing `AllomorphOperations.GetAll(entry)` (`AllomorphOperations.py:104`)
walks the relationship in the opposite direction, so this closes the round
trip.

---

## 6. Reshaped: `MSAOperations`

| Change | Detail |
|---|---|
| ADD a read accessor over `entry.MorphoSyntaxAnalysesOC` | Wraps each element in the **existing** `MorphosyntaxAnalysis` (`morphosyntax_analysis.py:74`) and returns the **existing** `MSACollection` (`msa_collection.py:76`). Wiring template: `AllomorphOperations.GetAll` (`AllomorphOperations.py:104`), the same two-subtype shape shipped end to end. |

Both the wrapper and the collection are already complete and are currently
instantiated by no code path at all (`research.md` F3). The subtype-divergent
properties are already handled by the wrapper's `is_*` / `as_*` / `pos_*`
families, so no new polymorphic design is introduced. Callers never see
`ClassName` or a cast, satisfying Principle VI.

Where a flat property read is needed, the established convention is a
`ClassName`-keyed dispatch table (`lcm_casting.py:652`, `:662`, `:665`),
consumed as at `LexSenseOperations.py:1177` -- membership check, warning,
`None` for an unknown subtype.

---

## 7. Reshaped: package manifest

| Entity | Change |
|---|---|
| `flexicon.version` | `"4.8.0"` -> `"4.9.0"` at `flexicon/__init__.py:15`. Single source of truth; `pyproject.toml:69-72` reads it via `version = { attr = "flexicon.version" }`. `RELEASING.md:189`: *"Do not add a second version constant."* The stub declares only the type (`__init__.pyi:12`), so there is no literal to bump there. |
| `flexicon.CAPABILITIES` | `+ "parser"` at `flexicon/__init__.py:67-72`. Lands **last**, after the evidence gate (D-A10). Three edits in lockstep: the frozenset, the `#:` doc block above it (`:17-66`), and `EXPECTED_TOKENS` (`tests/write_path_transactions/test_capabilities.py:36-41`). |

**Token semantics.** `flexicon/__init__.py:31-33` warns that a token means
"this build implements it", **not** "active in your session". So `"parser"`
asserts the surface exists -- it does not assert that any given machine can
reach a parser. That runtime question is `ParserAvailability`'s, and the two
must not be conflated by a consumer.

---

## 8. Validation rules

Drawn from the requirements, each landing as a test rather than a
convention (Principle III).

| Rule | Source | Enforced by |
|---|---|---|
| Import never triggers parser loading | FR-003 | AST test asserting no module-scope parser import (template `tests/test_public_casting_export.py:127-153`) |
| No write/record/file method on the parser surface | FR-002 | enumeration test over the public surface, asserted by listing rather than inspection |
| Detected version never compared to a minimum | FR-006, SC-002 | standing AST test, 0 occurrences |
| Every bound operation verified to exist before use | FR-005 | tier A2, against the real installed component |
| Operations bound positionally, not by parameter name | FR-005 | structural assertion in tier A1 |
| Same-installation check is directory equality only | FR-004 | stated in the docstring; the reason string says what was checked |
| At most one grammar held | SC-014 | tier A3, across a two-project sequence |
| No parse from an unconfirmed grammar | SC-015 | tier A3 |
| Reload discards unconditionally | FR-043, SC-015 | tier A3, morpher-identity witness (D-A11) |
