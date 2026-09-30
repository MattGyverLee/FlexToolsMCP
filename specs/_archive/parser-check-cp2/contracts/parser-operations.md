# Contract: `ParserOperations` public surface (CP2a)

The interface a script author, a test, or CP2b codes against. Identifiers
pinned by the spec's Verbatim Constraints are reproduced **exactly** as
written there; they are the contract, not a description of it.

Implementation repository: `D:\Github\_Projects\_LEX\flexicon`.

---

## Verbatim identifiers used by CP2a

Copied without alteration from `spec.md` -> Verbatim Constraints:

| Identifier | Value |
|---|---|
| Released script-library version | `4.9.0` |
| Live verification projects | `IndonesianHC-Complete`, `Malay Parsing-20230810withHC` |
| The shipped capability check this checkpoint must not modify | `src/flextoolsmcp/server/parser_probe.py` |

Both live projects are confirmed installed under
`C:\ProgramData\SIL\FieldWorks\Projects`.

Identifiers listed in Verbatim Constraints but belonging to later slices --
`pyflexicon>=4.9.0,<5` and the bundled index artifacts (CP2a-bridge);
`flextools_try_word`, `flextools_parse_status`, `READ_ONLY_SAFE`, the run
stages and the priority levels (CP2b); `HCParser_DoesNotLoadXCore` (CP2b) --
are **not** part of this contract. They are recorded in `plan.md`'s scope
fence so they are not implemented early by association.

---

## Access

```
project.Parser
```

Singular, per D-A3. Registered as a lazy read-only `@property` on
`FLExProject` with a function-local import and a `__dict__` cache under
`_parser_ops`, matching `FLExProject.py:2181-2209`.

Also importable top-level, per the package-wide rule that every Operations
class is reachable as `from flexicon import X`:

```
from flexicon import ParserOperations
```

Both forms are required: the property is what scripts use, the top-level
export is what the stub-parity ratchet checks.

---

## Availability

Asking whether the parser is reachable **never raises**, on any machine.
This is SC-001 and it is the property tier A1 exists to test.

| Member | Returns | Contract |
|---|---|---|
| availability status | `ParserAvailability` | `available: bool`, `reason: str`, `version: str \| None`. See `data-model.md` section 2. |

- When unavailable, `reason` states **what was checked** and nothing more.
  FR-004's same-installation test is directory equality only; a foreign
  component copied into the correct directory passes undetected, and the
  docstring says so (Principle V).
- `version` is reported and **never compared against a minimum** (FR-006).
  SC-002 requires 0 such comparisons anywhere, asserted by a standing test
  on each side of the repository boundary.
- Calling a parser operation while unavailable raises a flexicon exception
  whose message is that same `reason`. Asking *whether* it is available
  does not.

---

## Operations

The five capabilities FR-001 requires. Names below are the contract;
parameter binding is **positional**, never by keyword, per FR-005 -- the
interface and implementation disagree on parameter names for two of the
underlying operations, and positional binding is what makes that
disagreement harmless.

| Capability | Input | Output | Notes |
|---|---|---|---|
| Plain parse of a word | word form | the parser's structured result | Object identity **is** preserved: results carry live `IMoForm` / `IMoMorphSynAnalysis` / `ILexEntryInflType` references, not strings (FR-010). |
| Parse returning the parser's structured output | word form | serialized parse document | Objects survive as integer identifiers on an already-serialized document. |
| Trace, optionally restricted to caller-supplied analyses | word form, optional analysis selection | serialized trace document | Identity here requires a repository lookup to rehydrate -- **do not plan a typed object-identity marshaller for the trace** (FR-010, as amended by E5). |
| Reload the grammar | -- | -- | **Reset, then reload. Two steps.** A bare update short-circuits on an unchanged model and does nothing, failing silently and serving the next parse from the stale grammar the caller believes was discarded (D-A5, FR-043). |
| Ask whether the loaded grammar is current | -- | `bool` | The currency read FR-043's "confirmed before reuse" clause requires. SC-015: 0 parses served from a grammar whose currency was not confirmed immediately before reuse. |

### Absent by construction

There is **no** operation that records, files, or otherwise writes a parse
result (FR-002). The absence is stated in the class docstring, because the
read-only safety claim of both CP2b tools rests on this surface being
unable to reach a write path -- and it is enforced by an enumeration test
over the public surface, not by the absence of a line of code.

---

## Read gaps closed alongside the facade

These are ordinary Operations-class additions, independent of parser
availability. A machine with no parser component still gets all three.

| Requirement | Surface | Contract |
|---|---|---|
| FR-007 | `project.Texts` -- add plural genre read | Returns **every** genre assigned to a text; empty list when none. The existing singular accessor is unchanged (D-A9). |
| FR-008 | `project.Allomorphs` -- add owning-entry read | Returns the owning `ILexEntry`, or `None`. Walks the ownership chain rather than taking one hop (D-A8). |
| FR-009 | `project.MSA` -- add read accessor | Returns the existing `MSACollection` of existing `MorphosyntaxAnalysis` wrappers. Callers never see `ClassName` or a cast; subtype differences are handled by the wrapper's `is_*` / `as_*` families (D-A6, Principle VI). |

---

## Package manifest

| Item | Contract |
|---|---|
| `flexicon.version` | `"4.9.0"` -- single source of truth at `flexicon/__init__.py:15`; `pyproject.toml` reads it by attribute. |
| `flexicon.CAPABILITIES` | Gains the token `"parser"`. Added **last**, after tiers A1-A3 pass. A token present without a landed capability behind it is a Constitution Principle V violation, asserted by a frozen literal. |

**Token semantics, stated so a consumer cannot misread it.** A CAPABILITIES
token means *this build implements the surface*. It does **not** mean the
parser is reachable on the machine reading it. That runtime question is
answered only by the availability status above. CP2b must probe
availability rather than infer it from the token.

---

## Stability

CP2b codes against this surface. Anything here may still change **before**
the `4.9.0` tag is pushed; after the tag it is a released public API and
changes cost a version. The tag push is a maintainer act (escalation E-C),
so the last reversible moment is the prepared release commit.
