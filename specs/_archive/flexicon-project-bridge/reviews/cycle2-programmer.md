# Cycle 2 / Programmer: Step 2b fix (Finding A) + binding-form widening (Finding B)

Target: `src/flextoolsmcp/server/validators.py`. All diffs in that one file plus
one new test file.

## Diff summary

**Finding A** (`certify_script_readonly` Step 2b, now :3841-3908): deleted the
line-keyed `_resolved_pairs` set and self-suppression. Per `ast.Call` node,
calls `_resolve_receiver_ops_class(recv, accessor_to_ops, operations_aliases,
facade_names)`; only if that returns `None` does the tightened fallback run
(`isinstance(recv, ast.Name) and recv.id in _known_ops_classes`), using the new
`_indexed_operations_class_names(api_index)` (:2838) added beside
`_indexed_mutating_method_names` (:2799). Added `"col": _node.col_offset` to
all three finding dicts built in this block.

**Finding B**: `_BindingNode = Union[Assign, AnnAssign, NamedExpr, For,
withitem]` (:1204). `_iter_assign_pairs` (:1207) dispatches on node type,
keeping the existing tuple-unpacking special case for `Assign` and adding one
branch per sibling form (`AnnAssign`/`NamedExpr` skip when `.value` is `None`;
`withitem` skips when `.optional_vars` is `None`; `For` yields `(target,
iter)` -- documented over-typing per issue #8, noted as disjoint from
`detect_casting_needs`' `loop_element_types` dataflow, different dict, same
lines ~4880). `_collect_assign_call_nodes` (:2654) now returns a 3rd list
`bindings` (the sibling forms only, never `Assign`) alongside the *unchanged*
`assigns: List[ast.Assign]`. All 4 call sites (:1001-area, :3274-area,
:3691-area, :4823-area) now pass `assigns + bindings` into
`_resolve_facade_names`/`_resolve_alias_maps`; `_find_cast_alias_property_writes`
(Step 4b, one call site) still receives the bare `ast_assigns` only -- verified
by grep, no other call site exists.

**col_offset audit**: grepped every `unknown_calls`/`protected_calls`/
`mutating_calls` consumer in `src/` and `tests/` (~40 hits). All either use
`.get()`, extract specific keys into tuples, or assert against `== []`/`== [expected 2-tuples]`.
None asserts an exact key set or full-dict equality on a non-empty finding row.
Added the key with no skip needed.

## Matrix: all rows PASS (24 new tests, `tests/test_cycle2_step2b_finding_a_b.py`)

Rows 1-9 (suppression vectors incl. self-suppression), 10-12 (annotated
bridge with/without index, absent-method), 13 (walrus/for/with-as), J/K/L
(tightened fallback catches), M (4 legit shapes silent), N (non-mutating
method on stale class silent), O (guarded case-K passes gate) -- all PASS.

## Full suite

Before: 1312 passed, 8 skipped, 36 subtests. After: 1336 passed (1312 + 24
new), 8 skipped, 36 subtests. No other deviation.

## Not done

Nothing skipped from the brief. Out-of-scope comment/string stripping
untouched as instructed.
