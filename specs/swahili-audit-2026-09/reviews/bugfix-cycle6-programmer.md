# Cycle-6 programmer report -- P2-1 lexical scoping + P2-2 eval blindness

Commit: **(pending -- see final commit sha in the commit this file ships with)**

## Work item 1 -- lexical scope chain

`_build_cast_candidate_set(node, parents, tree)` now walks
`_lexical_scope_chain(node, parents, tree)`: innermost enclosing
`FunctionDef`/`AsyncFunctionDef`/`Lambda` (via `_owning_scope`), then each
further enclosing scope outward, **always ending at `tree` (Module)**.
Per-scope collection (`_walk_scope_body`) stops descending at any nested
`FunctionDef`/`AsyncFunctionDef`/`Lambda`/`ClassDef` -- siblings/unrelated
functions are excluded; module-level casts stay visible everywhere.

Both consumers scoped: typo path (`detect_interface_attribute_typos`,
fallback now `_build_cast_candidate_set(node.value, parents, code_tree)`) and
casting path (`detect_casting_needs`, both the `line_var_cast_types` build
and the `typed_root` check now call it per usage instead of once whole-tree).
`_resolve_alias_maps` and `_CAST_SCAN_RECURSE_INTO` (`ast.Try, ast.With` +
`handlers`) untouched -- confirmed via diff, no hits outside
`_build_cast_candidate_set` and its two call sites.

**Bare-snippet test** (`test_bare_module_level_snippet_typo_still_detected`):
`d = ILexDb(project)\nx = d.EntriesOC` with no `def` anywhere -- still
`has_typos=True`. Plus `test_module_level_cast_visible_inside_function` and
`test_module_level_branch_conflated_cast_reaches_fallback_inside_function`
(module cast inside an `if`/`else`, forcing the fallback, read from inside a
nested function) -- both pass, proving Module is genuinely in the chain for
both positional AND fallback resolution.

**209-combo shape** (`test_cross_function_leak_typo_false_positive_fixed`):
`def a(p): obj=IMoStemMsa(p); obj.Hvo` + `def b(obj): obj.AddComponent`.
Pre-fix (stashed validators.py, ran against the real index):
`has_typos=True`, flagged `"'AddComponent' does not exist on 'IMoStemMsa'"`.
Post-fix: `has_typos=False, issues=[]`.

**False-negative shape** (`test_cross_function_leak_casting_false_negative_fixed`):
`def a(x): obj=IWfiAnalysis(x); obj.Hvo` + `def b(obj): obj.CategoryRA`.
Pre-fix: `has_casting_issues=False` (suppressed). Post-fix:
`has_casting_issues=True`, `CategoryRA` flagged, `cast_interface=IWfiAnalysis`.

**P1-1 matrix**: 4/4 (`test_cast_in_if_used_after_...`,
`..._try_used_in_except_...`, `..._for_used_after_...`,
`test_control_flat_cast_then_use_...`) -- all pass.

**Bug 2**: `test_PROMINENT_bug2_msa_repro_still_zero_false_positives_after_p1_fix`
-- 0/4 false positives, both detectors.

**Four quadrants** (`TestSeverityDecision`): warning+RO proceeds,
warning+WRITE rejects, error+RO rejects, typo+RO rejects -- all 4 pass
unchanged.

## Work item 2 -- eval-corpus blindness to #39

`_FakeAPIIndex` gained `self.liblcm` (real-shaped `ILexDb`/`IWfiAnalysis`
entities, hand-shaped from `liblcm_api_v11.0.0.json`'s property/method
dicts, that file itself untouched) and `self.flexlibs_stable`. New fixture
`tests/evals/corpus/issue39_typo_ilexdb_entriesoc.yaml`: `d =
ILexDb(project); d.EntriesOC` (real property is `Entries`), expects
`preflight_reject` / `casting_issues_detected`.

**RED/GREEN demonstration**: temporarily set `self.liblcm = {"entities":
{}}` (the pre-fix state) and reran `pytest tests/evals/test_corpus.py -k
issue39`:
```
FAILED ...: expected outcome='preflight_reject' got 'ok'
1 failed, 36 deselected
```
Restored the real entities, reran the same command:
```
1 passed, 36 deselected
```
Both observed directly, not asserted from memory.

## Fixture table

| fixture | change | why |
|---|---|---|
| `test_cross_function_leak_typo_false_positive_fixed` | new | locks 209-combo FP class |
| `test_cross_function_leak_casting_false_negative_fixed` | new | locks FN class |
| `test_bare_module_level_snippet_typo_still_detected` | new | locks bare-snippet primitive |
| `test_module_level_cast_visible_inside_function` | new | locks module->function visibility |
| `test_module_level_branch_conflated_cast_reaches_fallback_inside_function` | new | locks fallback reaching Module |
| `issue39_typo_ilexdb_entriesoc.yaml` | new | closes P2-2; proven red/green |
| all existing P1-1/Bug2/quadrant fixtures | unchanged, re-verified | no outcome flipped |

## Suite / corpus results

`pytest -q`: **1121 passed, 4 skipped, 12 subtests** (clean run). One run
mid-session hit the documented `test_new_exact_file_visible_after_write`
mtime-cache flake (fired twice consecutively, then cleared); confirmed
standalone pass immediately after -- reported per instructions, not chased.
Eval corpus: **35 passed, 2 skipped** (34 baseline + 1 new fixture).

Files touched: `src/flextoolsmcp/server/validators.py`,
`tests/evals/preflight_runner.py`, `tests/evals/test_corpus.py` (untouched,
verified compatible), `tests/evals/corpus/issue39_typo_ilexdb_entriesoc.yaml`,
`tests/test_issue40_casting_severity.py`.
