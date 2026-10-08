# Coverage analysis working files

Supporting material for `docs/COVERAGE-FLEXICON-LCM.md`. This directory holds the
intermediate tables, the tool that produces them, and the rationale for the index
changes the analysis depends on — the things a reviewer needs in order to disagree
with the headline numbers rather than take them on trust.

Nothing here is imported by the server. It is evidence, not code paths.

## State of the branch — read this first

**The committed indexes predate the last two index-affecting code changes.**
`src/flextoolsmcp/index/reverse_mapping_liblcm-v11.0.0.json` was last written at
`08e2062`; `2a9d1de` (bucket slimming + `getattr` member detection) landed after
it and has never been run. Nothing is inconsistent — the provenance hashes in
`docs/COVERAGE-FLEXICON-LCM.md` match the files in the tree, and every number in
this directory was recomputed from those same files — but the measurement
describes the pre-`2a9d1de` index. Regenerating will lower the gap count and
invalidate those hashes.

Consequently the coverage figures are derived from the reverse map's `by_member`
bucket (273 qualified `Type.Member` keys), which is present. The per-entity
`python_wrapper_members` view that `--update-liblcm` writes is *not* in the
committed LibLCM index, so a reviewer who regenerates will see that file change
too.

## What is being claimed

`docs/COVERAGE-FLEXICON-LCM.md` says flexicon demonstrably touches **252 of 2,971
members** of public LibLCM interfaces and abstract classes (8.5%), concentrated in
**71 types** whose combined surface is 882 members (28.6% within those), leaving
**114 candidate gap types carrying 415 members** in the domains a lexicography
wrapper is expected to serve.

That chain rests on three things a reviewer should attack independently:

1. **That member-level coverage is measurable at all.** It was not before this
   branch: `build_reverse_mapping` read `method["lcm_mapping"]` from
   `flexicon_api.json`, which 0 of 1,657 methods carried, so every wrapper
   bucket was emitted empty. An empty structure reads as "no coverage" rather
   than "not computed". See `change-rationale.md`.
2. **That the analyzer resolves receiver types correctly.** A member counts as
   covered only when the LCM type of the receiver is resolved and the LibLCM
   index confirms that type declares the member. Over-resolution inflates
   coverage; under-resolution invents gaps.
3. **That the remaining gaps are gaps.** See the blindness test below — this is
   the measured error rate of the method, and it is not zero.

## Files

| file | what it is |
|---|---|
| `lcm-member-coverage-by-type.csv` | The table behind the figure. One row per LCM type with at least one measured member access: reached / not reached / declared / percent. 71 rows, summing to 252 reached of 882 declared — recomputed from the committed indexes, so it reconciles exactly with the doc. |
| `gap-blindness-test.csv` | The false-positive audit. Every zero-coverage type was grepped against the flexicon source tree. 65 rows: 57 absent from the source entirely, 8 named in it — the detector's measured miss rate on that sample. |
| `flexgap-static-report.md` | Current output of `scripts/flexgap.py` run against the committed indexes, with no log evidence supplied. |
| `reverse-mapping-excerpt.json` | A cut of the committed `reverse_mapping_liblcm-v11.0.0.json` (1.5 MB) showing its shape: the `statistics` block, a `by_member` sample, and one of the bare-name buckets still carrying full wrapper records. |
| `change-rationale.md` | Why the index-generation changes were made. Written against `10e103e` and describes the first three commits of the series only — later commits (type-aware detection, the `getattr` route, bucket slimming) are not in it. |

## Two domain tables that are not the same measure

`docs/COVERAGE-FLEXICON-LCM.md` and `flexgap-static-report.md` both carry a
per-domain table, and they disagree. They are measuring different things:

- The **report** table is *entity-level reachability* — does flexicon name this
  type anywhere. Lexicon reads 79.6%.
- The **doc** table is *measured member coverage* — is this specific property or
  method demonstrably accessed. Lexicon reads 28.0%.

The first is the older, looser signal and the reason the earlier "~90% LCM
coverage" claim was never reproducible. Do not average them.

## Known blind spots in the measurement

Stated so a reviewer can judge how much of the 415 is real:

- **`self.<attr>` receivers are invisible.** 67 occurrences across the source
  (`self._concrete` 31, `self._obj` 29, `self._inner` 5, `self._helper` 2). This
  is why 25 of the 114 candidates are named in the source but show no coverage,
  and it is why `ILexDb` (26 members) and `IPhMetathesisRule` (16) — the two
  largest candidates — are almost certainly false positives. Seeding receiver
  types from `__init__` assignments would move both; it is deliberately not in
  this branch.
- **Union-typed attributes need narrowing.** `IPhMetathesisRule` reaches its
  members through an attribute typed `IPhRegularRule | IPhMetathesisRule`,
  discriminated at runtime by a `class_type` string comparison. No amount of
  annotation reading resolves that without modelling the guard.
- **The `getattr` route landed after the indexes were last rebuilt.** 273
  `getattr(obj, "Name", None)`-shaped accesses exist across 62 files, 44 of them
  naming LCM-known members. The analyzer now reads them; the committed indexes
  predate that. Regenerating will lower the 114 — `IMoStemName` at minimum — and
  will invalidate the provenance hashes in `docs/COVERAGE-FLEXICON-LCM.md`.
- **Five property names still do not resolve** against the LibLCM index:
  `__ExceptionFeatureRC`, `__ResolvePOS`, `POS`, `LanguagesRC`,
  `FeatureConstraintsOC`.
- **No live FieldWorks project is involved.** Every figure derives from the
  committed index files. That is deliberate — those indexes are what the MCP
  server tells a model is true — but it means this measures the indexes, not the
  runtime.

## Regenerating

```
python scripts/flexgap.py --index src/flextoolsmcp/index --out report.md
```

Add `--logs <dir>` pointing at a `~/.flextoolsmcp/logs` directory to join the
structural gaps against what live sessions actually tripped over, and `--csv` to
write the ranked worklist. Without logs the candidate CSV is empty by
construction: a gap with no log evidence is a roadmap item, a gap with log
evidence is a ticket, and only the join distinguishes them.

The indexes themselves rebuild with `python src/refresh.py` followed by
`python src/build_reverse_mapping.py --update-liblcm`.

## Open questions for review

1. Is the denominator right? Both sides are counted as distinct
   `(type, member-name)` pairs: 988 public types declare 3,152 member *records*
   but only **2,971** distinct pairs, because the reverse mapping is name-keyed
   and cannot distinguish overloads. Counting records instead would inflate the
   denominator with members the measurement is structurally unable to reach
   separately. (Collapsing names *globally* rather than per type would give
   1,853, which is not what is reported.)
2. Should inheritance-reachable types be excluded from the candidate list? They
   are now. The counter-argument: `ILexDb` implements only `ICmMajorObject`, so
   an "implements a reachable interface" rule would have cleared 52 of the
   then-119 candidates while hiding real gaps.
3. Is `general` correctly treated as out of scope? It carries the largest
   absolute shortfall in the model (912 unreached members) but holds the
   data-access layer flexicon deliberately does not wrap.
