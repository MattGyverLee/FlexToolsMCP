# tasks — getall-contract

Spec: `specs/getall-contract/SPEC.md`. Cycle-1 inventories:
`reviews/cycle1-explore.md`, `reviews/cycle1-lex-domain.md`.

## CP1 — Three-level implementation

Implemented in dependency order (Level 2 → Level 3 → Level 1), since the validator
prefers keying off the reconciled index shape and the corpus flips must match the
validator's advisory output.

### Level 2 — Index returns.type reconciliation
- [x] L2.1 Determine the correct edit layer (extractor/normalizer vs hand-curated
      JSON) per SPEC §5; document the finding.
- [x] L2.2 16 shape-(a) methods → `list[<IElement>]` (deprecate bare `list`).
- [x] L2.3 2 shape-(b) methods → `AllomorphCollection[...]` / `RuleCollection[...]`.
- [x] L2.4 33 shape-(c) methods → `EnumerableWrapper[<IElement>]` (10 strong + 23
      silent; membership in `cycle1-lex-domain.md` §1).
- [x] L2.5 `python src/refresh.py` reproduces the reconciled types (idempotent).

### Level 3 — Validator rule (flexicon mode only)
- [x] L3.1 New `detect_getall_unsafe_idiom` (or equivalent) in `validators.py`;
      shape resolved from Level-2 `returns.type`.
- [x] L3.2 Flags `len()`, subscript/slice, truthiness, double/multi-consume on a
      shape-(c) GetAll result; silent for (a); (b) capability-loss caveat.
- [x] L3.3 No false positive on plain `for x in GetAll():` or single-pass
      `next(...)`; scoped to `api_mode == flexicon`.
- [x] L3.4 Wired into `handlers/execution.py` pipeline; direct unit tests added.

### Level 1 — Mechanical idiom fix (17 sites)
- [x] L1.1 templates: `2-flexicon-template.py:69-70`, `00-FLAVOR-GUIDE.md:149`.
- [x] L1.2 docs+CLAUDE: `CLAUDE.md:281-282`, `FLEXTOOLS-STYLE-GUIDE.md:348-349`,
      `CASTING_SYSTEM.md:156`.
- [x] L1.3 curated_recipes.py:438-439 idiom + **delete false claim at :444**.
- [x] L1.4 worked_examples.py:207-208, :211.
- [x] L1.5 common_patterns JSON: lines 761, 3004, 2253 (+ delete mirrored false
      claim comment). Land per SPEC §5 refresh-safety. **Deviation:** line 2253
      (AllomorphOperations docstring) left unchanged -- see cycle2 report; it's
      shape (b), for which len()/repeat-iteration is safe per SPEC §4, so it was
      not actually an unsafe-idiom site once the taxonomy is reconciled.
- [x] L1.6 Corpus flips (flexicon mode): `issue20_import_satisfies_discovery.yaml`,
      `issue41_parenthesized_multiimport_ok.yaml` → expect new advisory + pass.
- [x] L1.7 Corpus hygiene (no outcome change): fix snippets in `10_`, `11_`, `18_`;
      **leave `15_ok_flexlibs_stable_mode.yaml` unchanged** (SPEC §5).

**Checkpoint:** all three levels implemented, full suite green, corpus flips pass.
Then → CP2 review gate (verification + qc + domain).

## CP2 — Review gate
- [ ] Verification: full suite green, corpus behaves per §7.
- [ ] QC: detector complexity/false-positive surface, refresh idempotence.
- [ ] Domain: (b) capability-loss caveat wording, flexicon-only scoping correct.
- [ ] lex-lead final approval.

## CP3 — Cycle-4 reversal (flexicon 4.2.1 -> 4.3.0 upgrade)

flexicon 4.3.0 standardized GetAll() docstrings and upgraded
`EnumerableWrapper` (flexicon/code/BaseOperations.py commit 205d5a9) into a
genuine, safe behavioral collection (materializes+caches on first access;
`__len__`/`__getitem__`/`__iter__` all safe, repeatable). The CP1 three-level
fix is now WRONG for flexicon mode and was reversed, not layered over. See
`reviews/cycle4-lex-programmer.md` for full detail.

- [x] Level 2: removed `apply_getall_container_shape`/`_canonical_getall_container_type`
      override from `flexicon_analyzer.py`; `flexicon_api_v4.3.0.json` /
      `common_patterns_flexicon-v4.3.0.json` now regenerate directly from
      4.3.0 docstrings, coexisting with the untouched v4.2.1 files.
- [x] Level 3: `detect_getall_unsafe_idiom` scope INVERTED -- silent in
      flexicon mode, fires only in `flexlibs_stable` mode against a
      conservative hand-curated allowlist (`STABLE_ONE_SHOT_METHODS`) of
      FLExProject methods documented as raw one-shot iterators/generators.
      Direct unit tests repointed (21/21 passing).
- [x] Level 1: reframed docs/templates/curated recipes/worked examples to
      the "behavioral collection -- safe to loop/len/subscript/re-iterate;
      list() only when you need a plain list" guidance for flexicon mode.
      Corpus `issue20`/`issue41` un-flipped (advisory removed); `15_`/`18_`
      unaffected (code shape doesn't match the new stable-mode allowlist
      pattern).
- [x] Full suite + eval corpus green (see cycle-4 report for counts).
