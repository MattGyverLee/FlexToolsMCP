# Cycle-5 QC re-review -- a1f6897 (P1 pair), ffd4bf4 (primer scoping)

**No P0. No P1.** Both cycle-4 P1s are genuinely closed. Suite re-run
`1115 passed, 4 skipped, 12 subtests`; corpus `34 passed, 2 skipped` --
matches both commits. All four pre-verified items are true (the third call
site is `preflight_runner.py:291`; `:283` is a comment).

## Q1 union breadth: NOT a new false-negative source (measured)

Against the real liblcm index, genuine-typo detection held at **~99% for
N = 1, 2, 3, 4, 6, 8, 12, 16, 24 and 32** candidate interfaces (200
mutated-real-member trials per N). No N kills detection: LCM interfaces
share a large inherited base, so the union grows sub-linearly (Bug 2's
4-way MSA union: 72 -> 83 names) while a *nonexistent* attribute stays
absent from all of them. Suppression bites only real properties valid on
one arm -- the accepted trade, nothing wider.

## Q2 candidate-map scope: real cross-function leak -- P2, not P1

`_build_cast_candidate_set` (`validators.py:2492`) walks the WHOLE tree and
leaks across `def` boundaries both ways. Confirmed end-to-end:

- **Typo FP** -- `def a(p): obj = IMoStemMsa(p); obj.Hvo` + `def b(obj):
  obj.AddComponent` flags *"'AddComponent' does not exist on IMoStemMsa"* on
  correct code, error tier, hard-rejecting read-only AND write runs. 209
  such combos exist among 12 common interfaces alone.
- **Casting FN** -- `def a(x): obj = IWfiAnalysis(x)...` + `def b(obj):
  obj.CategoryRA` suppresses the genuine uncast access (`_candidates` feeds
  `typed_root` `:3791` and the `& safe_ifaces` intersections `:3961`/`:3985`).

Not P1: both shapes *restore* the pre-`b5f41d8` flat `cast_aliases[...]`
lookup, and the union is strictly **narrower** on FPs than that baseline --
`b5f41d8` briefly narrowed it; this returns to the 4-cycle norm. Cheap fix:
scope the map to the nearest enclosing `FunctionDef`.

## Q3 `_resolve_alias_maps`: genuinely untouched

Zero diff hunks touch it. `_resolve_cast_type_at`'s only callers are `:985`
and `:3753`/`:3791`, both in scope, so the `handlers` addition at `:2411`
cannot reach mutation detection (`:2951`) or `detect_hvo_literal_args`
(`:2608`). `_CAST_SCAN_RECURSE_INTO` unchanged.

## Q4/Q6 three call sites + four quadrants: identical, intact

All three post-process to the same boolean (`(not we) and not
has_error_severity`; the runner's `we or has_error` is its negation).
Verified end-to-end with REAL detection: warning+RO -> proceed;
**warning+WRITE -> REJECT**; **typo+RO -> REJECT**; typo+WRITE -> REJECT.
`run_module` and `validate_only` agree in every cell.

## Q5 agreement test: now real

Neither detector is monkeypatched (`test_issue49_validate_only.py:373`
`_RealCastingFakeIndex`); `..._on_readonly_typo_class` (`:472`) drives a real
`ILexDb.EntriesOC` through both paths. Sound.

## Q8 fixtures: clean

No corpus YAML touched; `test_issue40_casting_severity.py` has **zero**
removed lines; no assertion flipped anywhere.

## Remaining P2s

1. **`a1f6897` -- Tier-1 evals are still 100% blind to #39.** The pipeline
   is correctly rewired, but `FAKE_API_INDEX.liblcm["entities"] == []`
   (`preflight_runner.py:73-155`), so `_interface_member_names` returns
   `set()` for every interface and the typo detector can never fire.
   Cycle-4 P2-2 is rewired, not fixed; `:285-287`'s "to the extent
   FAKE_API_INDEX's entities cover it" covers nothing.
2. **`a1f6897` -- slash-joined pseudo-interface label.** `"/".join(...)`
   (`validators.py:1022`) reaches the user-facing message and
   `object_type`/`missing_on`/`available_on` (`:1053-1058`) as a name no
   index contains. Cosmetic only: `imports_needed=[]` /
   `cast_interface=None` keep auto-fix out.
3. **`ffd4bf4` (`admin.py:278-289`) -- accurate but mildly
   self-undercutting.** `why` byte-unchanged; no digit+unit duration
   anywhere (regex test passes); "may ... untested" correctly hedges what
   explore-96 section 6 calls source-SUPPORTED. It omits that remedy 1
   needs `SaveChanges()` *before* the `undoable=False` envelope
   (`execution.py:3810`), so the path is unreachable from `run_module`
   today -- which the same sentence opens by saying. Wording nit, not an
   overclaim.
