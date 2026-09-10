# Cycle 2 / QC: review of the Finding A + Finding B implementation

Target: uncommitted diff on `src/flextoolsmcp/server/validators.py` (+183/-38) and
new `tests/test_cycle2_step2b_finding_a_b.py` (24 tests).
Branch `flexicon-project-bridge-mcp`, base `def958a`. Read-only review
(lex-qc has no Write tool; persisted by the orchestrator).

## VERDICT: APPROVE

Structurally sound, matches the ruled fix-shape exactly, no scope creep, no dead code,
tests assert real discriminators. Two nits only (one since fixed -- see Disposition).

## 1. `_BindingNode` union / `_iter_assign_pairs` (:1204, :1207)

Dispatch is exhaustive over the union: `Assign` (:1249, unpacking special case preserved
byte-for-byte incl. the `strict=True` zip and the starred/arity guard), `AnnAssign` (:1261,
correctly skips `value is None` for a bare `fx: FLExProject`), `NamedExpr` (:1265, always
has both), `For` (:1268, `.target`/`.iter`, no None-skip needed -- both always populated on
a valid `For`), `withitem` (:1271, skips `optional_vars is None` for a bare `with expr:`).
No gap. **OK.**

## 2. Third return value threading (:2654; sites :1001, :3275/:3281, :3692/:3697-3699, :4823/:4830)

- All four sites pass `assigns + bindings` into `_resolve_facade_names`/`_resolve_alias_maps`
  -- verified by grep, no site missed the widening.
- The site that must NOT widen, `_find_cast_alias_property_writes` at :3943, still receives
  bare `ast_assigns`; confirmed single call site.
- The `assigns`-stays-pure-`ast.Assign` invariant is guaranteed **by construction**, not by
  convention: `_collect_assign_call_nodes` (:2674-2680) uses an
  `if / elif isinstance(...) / elif isinstance((AnnAssign, NamedExpr, For, withitem))` chain
  over one `ast.walk`, so a node can land in only one of the three lists -- no path can
  double-file an `Assign` into `bindings`.
- Annotations are honest: `List[_BindingNode]` on the two widened consumers (:1324, :2685)
  matches what is passed (`List[ast.Assign] + List[_BindingNode]` is `List[_BindingNode]`
  since `ast.Assign` is a union member); `_find_cast_alias_property_writes` (:2871) stays
  narrow at `List[ast.Assign]`. **OK.**

## 3. `For` over-typing / `loop_element_types` collision (near :4880-4997)

Confirmed disjoint. `operations_aliases`/`cast_aliases`/`facade_names` are whole-function,
name-keyed dicts built once at Step 1b/4/hvo-gate entry; `loop_element_types` (:4816,
populated :4997) is `(line, name) -> (interface, is_polymorphic)`, built by a separate walk
over `ast.For`/comprehension nodes with polymorphic-return metadata. No shared key space,
no write collision -- the docstring claim at :1236-1245 is accurate. **OK.**

## 4. `_indexed_operations_class_names` (:2838)

Mirrors `_indexed_mutating_method_names` in shape: same `api_index is None -> set()` guard,
same `getattr(api_index, "flexicon", None) or {}` defensive read, same one-pass
comprehension. Missing/None/empty index handled safely, exercised by
`test_none_index_returns_empty_set` and `test_empty_flexicon_returns_empty_set`.
Docstring explains the suffix-vs-index rationale correctly and correctly flags the
`entities` local-rebinding trap at :3743 (`else: entities = {}`) as the reason it re-derives
`flexicon` itself.

**Nit (should-fix): stale line anchor.** The docstring cross-referenced "(:2745-2748)" for
the design principle, but that range is a "Chained rebind" comment inside
`_resolve_alias_maps`; the actual principle text lives at ~:2823-2825. Prose reference
correct, anchor wrong -- would mislead a future reader.

## 5. Test quality (`tests/test_cycle2_step2b_finding_a_b.py`)

- Assertions target real discriminators: `unprotected()`/`protected()`/`unknown()` helpers
  extract `(class, method)` tuples and check `is_certified_readonly` -- not incidental
  strings, not full-dict equality (consistent with the col-audit note).
- The self-suppression row asserts `len(rows) == 2` and *distinct* `col_offset` values rather
  than hardcoding literal offsets -- resilient to formatting changes, and to index version
  bumps (uses a synthetic `make_index()`, never the shipped `flexicon_api_v4.7.0.json`).
- Cases J/K/L are clearly labelled PRE-EXISTING in both the module docstring (:7-16) and the
  `TestTightenedFallback` class comment (:277-278) -- the audit trail reads correctly.
- Cases M (four legit shapes) and N (non-mutating method on a stale class) both assert the
  negative side (`unknown_calls == []`, `is_certified_readonly is True`).

**Nit (non-blocking):** no test covers Step 2's `else: pass` fallthrough combined with Step
2b's tightened fallback both missing. Implicitly covered by the "class not in index falls
through" logic; not required by the brief.

## 6. General quality / dead code

Zero remaining `_resolved_pairs` hits -- clean deletion. No unused helpers;
`_indexed_operations_class_names` has exactly one call site as intended. Comments accurately
describe post-rewrite behavior at every site checked (Step 2b :3841-3861, call sites
:3276-3280, :3693-3696, :4828-4829). `"col": _node.col_offset` added consistently to all
three finding dicts (:3897, :3909, :3917).

## SCOPE-CREEP CHECK

Clean. Steps 1 (:3667) and 1c (:3732) still scan raw un-stripped `code` (no `_strip_comments`
introduced). `detect_missing_operations_imports` / `detect_wrong_library_imports` (:2033,
:2087) and their patterns (:72-73) untouched and still unstripped. Inline stripper duplicates
still at :5149 and :5245, unchanged. `recipe_validator.py` not touched. **No scope creep.**

## Could not assess without running code

Nothing -- behavior was verifiable by static reading against the documented matrix, with the
suite already green (1336) and IDE diagnostics empty.

---

## Disposition (orchestrator)

The should-fix nit in section 4 is **fixed**: the docstring now references
`_indexed_mutating_method_names`' closing paragraph by quoted phrase
("Deliberately index-derived rather than a verb-prefix guess") instead of a numeric anchor,
so it cannot go stale on the next edit. Note the bad anchor originated in the cycle-2
dispatch brief and was relayed verbatim into the implementation.

The section 5 nit is left as-is, non-blocking, consistent with QC's own assessment.
