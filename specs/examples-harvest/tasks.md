# tasks — examples-harvest

Spec: `specs/examples-harvest/SPEC.md`.
Corpus: `MyFlextool/FlexTools Modules-20260812T202142Z-1-001.zip` (75 modules).
Verification projects: `French-FLExTrans-Demo2025` (primary), `Sena 3` (secondary).

Status key: `[ ]` todo · `[~]` in progress · `[x]` done · `[?]` blocked on a decision

## P0 — Verification harness

- [ ] `scripts/verify_recipes.py` — run each recipe read-only against both
      projects via the MCP runner; write one evidence record per (recipe, project).
- [ ] Evidence schema + directory `specs/examples-harvest/evidence/`
      (fields listed in SPEC §5).
- [ ] Degenerate-output check: non-empty result required on the primary project,
      so a recipe cannot pass by reporting zero rows everywhere.
- [ ] CI assertion in `tests/`: every `source: "curated"` recipe has an evidence
      record whose `flexicon_version` matches the indexed version. Skips cleanly
      where FieldWorks is absent.
- [ ] Re-verify the 4 existing POS recipes as the harness's own smoke test
      (`count-senses-by-pos`, `list-entries-with-pos`, `find-entries-missing-pos`,
      `list-parts-of-speech`). Investigate any that fail — they were never confirmed.

## P1 — Narrow proof (2 recipes, full loop)

- [ ] Harvest + translate `From Ron/SetFeatures.py` (151 lines, 5 hits).
- [ ] Harvest + translate `From Matthew/Bulk_Set_Stem_Name.py` (302 lines, 13 hits).
- [ ] Resolve every ambiguous method name by argument type before translating
      (SPEC §4). Add a `TestGetAllSensesArgumentType`-style assertion per ambiguity found.
- [ ] Execute-verify both; commit evidence records.
- [ ] **Review gate — stop here and assess before scaling.**

## P2 — Inflection features (the zero-coverage gap)

- [ ] list all inflection features in a project
- [ ] read the feature structure attached to a sense/MSA
      (note: `FeatureStructureGetAll()` yields nothing — reach via owners, SPEC §3)
- [ ] find senses missing inflection features
- [ ] feature-value inventory per closed feature
- [ ] list inflection classes
- [ ] POS-scoped feature lookup

## P3 — POS / MSA depth

- [ ] MSA-shape awareness: stem vs affix MSA handling
- [ ] Mine `Overpowered_Affixes.py` and FLExTrans `Utils.py` for idiom
- [ ] Guard recipes against empty POS names (`Sena 3` has one — SPEC §3)

## P4 — Sibling repos

- [ ] FLExTrans `Dev/{Lib,Modules}` sweep
- [ ] GramTrans `src/gramtrans/Lib` sweep

## Decisions needed

- [?] **Write verification.** Bulk_Set_* and SetFeatures are mutating; this spec
      dry-runs them only. Designate a disposable scratch project (candidates:
      `ResembliO-Delete`, `Circumsanity` — neither probed yet) and an undo
      strategy, or accept dry-run-only permanently?
- [?] **Attribution.** Confirm contributors are content for derived recipes to
      ship in this repo, and settle the credit line format.

## Notes

- Do NOT re-run a case-insensitive `POS` grep over any corpus — it matches
  "purpose"/"position". Use the word-boundary API-name pattern in SPEC §2.1.
- Do NOT mechanically find-replace accessors across the corpus. That is precisely
  how issue #84's regression was introduced.
- `feat-swahili` has zero entries; never use it as a sole verification project.
