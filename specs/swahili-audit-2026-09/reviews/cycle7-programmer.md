# Cycle 7 -- Programmer report: D-1 / #97 Bug 1 (cast fix-string)

Commit: `6e352049006ed66d2ab8d1c92630c92cc53785ef` (code + tests, one commit).

## Consumer audit (pre-edit)
Grepped `src/`, `tests/`, `tests/golden/`, `tests/evals/corpus/`, and
`docs/TOOL-CONTRACT.md` for anything parsing/asserting the `fix` string.
Found:
- `tests/test_validator_cluster_fixes.py:384` -- only asserts
  `cast_interface` OR `fix` is truthy (permissive, unaffected).
- `tests/golden/responses/casting_issues_detected.json` -- `casting_issues: []`
  (empty, no fix content).
- `tests/golden/responses/auto_fix_casting_applied.json` -- asserts on
  `auto_fixes_applied[].replacement`/`cast_interface`, not on `fix`.
- `tests/evals/corpus/issue30_receiver_suffix_naming_skip.yaml` -- `skip:
  true`; asserts only `outcome`/`error_code`, explicitly documents it
  cannot see rewrite-quality content.
- `docs/TOOL-CONTRACT.md` -- no `fix`/`Cast ` references.
No blocked paths; nothing outside the lock set needed changes.

## Diff summary
`src/flextoolsmcp/server/validators.py`:
- New `_casting_candidates_for_fix()` (after `_pick_cast_interface`,
  ~:3484) -- reuses the identical head-split-on-whitespace-and-"(",
  keep-I-prefixed cleaning `_pick_cast_interface` already does; dedups,
  preserves order.
- `:4104-4136` (new) -- builds `fix_msg`: `cast_iface` truthy ->
  `f"Cast {obj_var} to {cast_iface}"`; else candidates found -> `"Cast
  {obj_var} to one of: A, B, C, D, +N more -- ambiguous, call
  flextools_resolve_property(property_name='X', context_entity=...) to
  confirm"` (capped at 4 shown); else -> `"Cast {obj_var} to concrete
  type"` (old placeholder, never IndexErrors).
- `:4145` -- `"fix": fix_msg` replaces the old
  `defined_on.get(...)[0]` line. `available_on`, `severity`, `rewrite`,
  `imports_needed`, `cast_interface` untouched.

## Mutation evidence (verbatim)
**Mutation 1** -- reverted `"fix": fix_msg` back to
`f"Cast {obj_var} to {casting_info.get('defined_on', ['concrete type'])[0]}"`.
Ran `test_issue97_bug1_cast_fix_string.py`: **4 failed, 2 passed**.
Sample failures: `AssertionError: ... match='Cast unrecognized_receiver_zz
to ICmPossibility' is not None : Property 'Abbreviation': cast_interface
is None but fix confidently names 'ICmPossibility'`; `'Cast sense to
ILexEtymology' != 'Cast sense to ILexSense'`; `'Cast wfi_gloss to
ILexEtymology' == 'Cast wfi_gloss to ILexEtymology'` (repro tests);
`'Cast morph_type to ICmAgent' == 'Cast morph_type to ICmAgent'`.
Reverted -> all 6 pass.

**Mutation 2** -- changed the `cast_iface` truthy branch to
`fix_msg = f"Cast {obj_var} to concrete type"` (forces disagreement).
Ran `TestResolvedFixAgreesWithCastInterface`: **2 failed** --
`'Cast sense to concrete type' != 'Cast sense to ILexSense'`;
`'Cast obj to concrete type' != 'Cast obj to IPhEnvironment'`.
Reverted -> both pass.

## Repro note
Of the 4 confirmed pairings, only Gloss->ILexEtymology and
Name->ICmAgent reproduce against the shipped v11.0.0 casting index (both
locked in as tests c/d). `FeatureRA` in this index snapshot resolves to
`['IFsFeatureSpecification', 'IPhFeatureConstraint']`, not `ICmAgent` --
that exact pairing isn't present to reproduce; MSA-family ambiguity is
covered by the 136-property broad sweep instead (test file docstring
states this explicitly, not silently dropped).

## Suite + corpus numbers
`python -m pytest -q`: **1127 passed, 4 skipped, 12 subtests passed**
(>= 1121 required). One run hit
`test_new_exact_file_visible_after_write` (the known D-2 mtime flake);
reran in isolation -> passed. A clean full rerun afterward was fully
green with no failures.
`python -m pytest -q tests/evals/test_corpus.py`: **35 passed, 2 skipped**
(matches expected).
Regression suites (`test_issue40_casting_severity.py`,
`test_issue40_casting_whitelist.py`, `test_issue48_inline_casting.py`,
`test_validator_casting_chains.py`): **70 passed**.

## Status
#97 remains **NOT-CLOSED** pending lead sign-off.
