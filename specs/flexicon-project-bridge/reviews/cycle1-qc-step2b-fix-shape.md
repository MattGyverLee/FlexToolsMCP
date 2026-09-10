# Cycle 1 / QC: Step 2b fix shape decision

Target: `src/flextoolsmcp/server/validators.py` (`certify_script_readonly` Step 2b, :3726-3747)
Branch: `flexicon-project-bridge-mcp` @ `def958a`
Author: lex-qc (report persisted by the orchestrator -- lex-qc has no Write tool)

## Decision

**Chosen: Option (1) -- invert the question.** Replace the line-keyed `_resolved_pairs`
set (`:3737`, `:3745-3747`) with a per-`ast.Call` check via
`_resolve_receiver_ops_class(_recv, accessor_to_ops, operations_aliases, facade_names)`,
plus a manual `ast.Name.endswith("Operations")` case for Step 1's static form (which that
helper does not cover). No suppression set at all -- each qualifying node stands alone.

## Diff sketch

```python
for _node in ast_calls:
    if not isinstance(_node.func, ast.Attribute):
        continue
    _method_name = _node.func.attr
    if _method_name not in _indexed_mutating:
        continue
    _recv = _node.func.value
    _cls = _resolve_receiver_ops_class(_recv, accessor_to_ops, operations_aliases, facade_names)
    if _cls is None and isinstance(_recv, ast.Name) and _recv.id.endswith("Operations"):
        _cls = _recv.id                 # Step 1's static `SenseOperations.Method(` form
    if _cls is not None:
        continue                       # Step 2 already classified this node authoritatively
    # ... existing report-as-suspected-mutation body, unchanged
```

## (a) Suppression vectors

| Vector | Evidence | Verdict |
|---|---|---|
| `;` packing, nested-as-argument, trailing-comment decoy | run (prior confirmed `proto_fix.py`) | CAUGHT |
| reversed order, comprehension, ternary, one-line `for`, string-literal decoy, bogus-`*Operations` decoy | argued from mechanism; **later run by orchestrator, see addendum** | CAUGHT (structural) |

The un-run vectors are guaranteed, not merely plausible: Option 1 reads only `ast_calls`,
`accessor_to_ops`, `operations_aliases`, `facade_names` -- never `code` text, `lineno`, or
`operations_calls_with_lines`. A comment/string/bogus-class decoy is text-only
(`ast.Constant`, or outside the AST entirely) and produces zero `Call` nodes, so this loop
cannot see it under any physical layout. Order/nesting/ternary/comprehension/one-line-`for`
do not change which `Call` nodes `ast.walk` finds, so per-node evaluation is
layout-invariant by construction.

## (b) Legitimate resolvable shapes -- zero false positives

| Shape | Result |
|---|---|
| `project.LexEntry.Duplicate(e)` | `[]` -- traced: same `_resolve_receiver_ops_class` branch as the run `project.CustomFields.Duplicate` case; `LexEntry` is in `accessor_to_ops` |
| `LexSenseOperations(project).Duplicate(s)` | `[]` (run) |
| `LexSenseOperations.Duplicate(s)` | `[]` (run) |
| `fx = FLExProject.FromOpenProject(project)` + `fx.LexEntry.Duplicate(e)` | `[]` (run) |

## (c) Interaction with the sibling AnnAssign/NamedExpr/For/withitem widening fix

Option 1 stays correct -- and improves -- as `facade_names` grows, because it calls
`_resolve_receiver_ops_class` with the *same* `facade_names`/`operations_aliases`/
`accessor_to_ops` maps Step 1b already builds and consumes. Any name the sibling fix newly
resolves (e.g. `fx: FLExProject = ...`) is automatically honored here for free. Options 2
and 3 have no equivalent coupling.

## (d) `col_offset` in the finding row

Optional for gate correctness. Option 1 has no suppression set, so the `:3747`
self-suppressing bug (two same-name unresolved calls on one line collapsing to one row)
disappears structurally -- every node is processed independently. `col_offset` is only
useful for disambiguating two rows in the user-facing message.

## Rejected: Option 2 (node identity)

The verifier's objection is **confirmed, not refuted**. Steps 1 (`:3557`) and 1c (`:3594`)
are `re.finditer` passes over raw `code` and never hold an `ast.Call` reference, so their
matches have no `id()` to register. A node-identity set populated only from Step 1b's walk
would leave any call resolved solely via Step 1's static form
(`LexSenseOperations.Method(...)`, which Step 1b does not independently handle) unrepresented,
and `ast.walk` in Step 2b would re-find that node and double-report it as
`unresolved_receiver` even though Step 2 classified it correctly via the index. Fixing that
means AST-ifying Steps 1/1c anyway, converging on Option 1 with extra indirection.

## Rejected: Option 3 (composite key with column)

Requires widening `operations_calls_with_lines` to 4-tuples and adding `match.start()`
column math to Steps 1 and 1c -- more sites touched than Option 1. It also leaves the
deeper defect intact: Steps 1/1c still scan un-stripped `code`, so comment/string decoys
still seed the set, merely less likely to collide by chance rather than structurally
excluded. More code for a weaker guarantee.

---

## Addendum (orchestrator): empirical gap closed + a residual hole in the chosen shape

lex-qc had no execution tool, so six of nine vectors were argued structurally. All six were
subsequently run against the shipped index (`flexicon_api_v4.7.0.json`) using
`proto_fix_gapfill.py`. **QC's structural argument holds -- all six are CAUGHT**, and both
legitimate control shapes stay silent:

| Vector | Result |
|---|---|
| C reversed order | CAUGHT `(Duplicate, 4, col 0)` |
| D comprehension | CAUGHT `(Duplicate, 4, col 1)` |
| E ternary | CAUGHT `(Duplicate, 4, col 53)` |
| F one-line `for` | CAUGHT `(Duplicate, 4, col 14)` |
| H string-literal decoy | CAUGHT `(Duplicate, 4, col 44)` |
| I bogus-`*Operations` comment decoy | CAUGHT `(Duplicate, 4, col 0)` |
| `project.LexEntry.Duplicate(e)` (legit) | silent -- no false positive |
| `project.CustomFields.Duplicate(fld)` (legit) | silent -- no false positive |

### Residual hole: the manual `endswith("Operations")` fallback trusts a naming convention

Option 1's fallback (`isinstance(recv, ast.Name) and recv.id.endswith("Operations")`) grants
authoritative-classified status on the strength of a *name suffix*, with no index lookup.
Three adversarial shapes therefore stay silent under Option 1 as specified:

| Case | Option 1 as specified | Tightened variant |
|---|---|---|
| `myOperations = get_agent_ops()` then `myOperations.Duplicate(entry)` | silent | **CAUGHT** |
| `ZzzOperations.Duplicate(entry)` (class not in index) | silent | **CAUGHT** |
| `def go(fooOperations): fooOperations.Duplicate(entry)` | silent | **CAUGHT** |

**Tightened variant:** require the name to be a *known indexed* Operations class rather than
merely suffix-matching --

```python
if _cls is None and isinstance(_recv, ast.Name) and _recv.id in _known_ops_classes:
    _cls = _recv.id     # only 64 real indexed *Operations classes qualify
```

Verified (`proto_fix_tightened.py`): the tightened variant catches all three adversarial
cases and leaves **all four legitimate shapes silent** -- static ops form, inline ctor,
project accessor, and facade alias. `LexSenseOperations` is in the index (64 classes total);
`myOperations` / `ZzzOperations` are not. So the tightening costs nothing.

**These three are PRE-EXISTING holes, not regressions introduced by the fix.** Current
shipped `certify_script_readonly` returns `is_certified_readonly=True`, `confidence='high'`,
`findings=0` for all three (via the line-key path: Step 1's regex matches `myOperations.Duplicate(`,
Step 2 finds the class absent from the index and falls through to `pass`, then Step 2b's
line key suppresses). Option 1 as specified preserves the hole; the tightened variant closes it.

**Recommendation to lex-lead:** adopt Option 1 **with the tightened fallback**, and add
cases J/K/L to the cycle-2 regression matrix. Harnesses:
`scratchpad\proto_fix_gapfill.py`, `scratchpad\proto_fix_tightened.py`.
