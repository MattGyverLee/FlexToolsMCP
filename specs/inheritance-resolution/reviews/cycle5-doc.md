# Doc Agent Report -- cycle5-doc

**Date:** 2026-08-13
**Trigger:** Four precisely-specified doc gaps found during CP4 doc-landing verification for #86 (inheritance-resolution)

## Scope

Documentation-only pass. No `.py` file touched. No GitHub issue filed,
commented on, or closed. No commit made. `git stash` not used.

## Verification performed before editing

- `src/flextoolsmcp/server/handlers/api.py:437` -- confirmed
  `KEY_TOTAL_METHODS_INCLUDING_INHERITED = "total_methods_including_inherited"`
  is defined alongside `KEY_TOTAL_PROPERTIES_INCLUDING_INHERITED` (line 438).
- `api.py:638` -- confirmed `result[KEY_TOTAL_METHODS_INCLUDING_INHERITED] = total_methods_including_inherited`
  is written into the `paginate_entity()` response, mirroring the properties
  key at the same function.
- `api.py:575` -- confirmed this is the actual `def paginate_entity(...)` line
  (docs previously cited `api.py:420`, which is inside an unrelated comment
  block about class-side collision counts).
- `api.py:830` -- confirmed `resolve_property`'s only inheritance-related
  emission is `r.setdefault(KEY_INHERITED_FROM, ...)` -- it does not touch
  either `*_including_inherited` total, confirming those are `get_object_api`
  (via `paginate_entity`) only.
- `src/flextoolsmcp/liblcm_extractor.py:700` -- confirmed the filter
  `if iface_name not in ("IDisposable", "IEnumerable", "IComparable")` runs
  before appending to `implemented_interfaces`, i.e. after `GetInterfaces()`
  (line 698) but before storage -- confirms the "full transitive closure"
  claim in `LIBLCM_EXTRACTION_SEMANTICS.md` needed the exclusion caveat.
- Confirmed CHANGELOG.md's `### Added: ... inheritance-aware get_object_api (#86)`
  heading (line 95) already names `total_properties_including_inherited` in
  its anchor text; left the heading untouched per instruction (anchor
  stability), only edited the bullet body.

## Edits applied

### EDIT 1a -- `docs/TOOL-CONTRACT.md` (P1)

- Added new table row for `total_methods_including_inherited`, now at
  **line 198**, immediately after the `total_properties_including_inherited`
  row (line 197). Same 4-column format (`Key | Location | Type |
  Description`), wording mirrors the properties row exactly (own-only counts
  unchanged, new separate key, not a redefinition).
- Reworded the lead sentence, now **lines 183-192** (was lines 183-189,
  "two additional optional fields"). New wording names the three real keys
  (`inherited_from`, `total_properties_including_inherited`,
  `total_methods_including_inherited`) without a bare count, avoiding a
  future off-by-one if a fourth key is ever added. This edit also folds in
  EDIT 2a (see below) since both target the same sentence.

### EDIT 1b -- `CHANGELOG.md` (P1 follow-through)

- Bullet at **lines 112-115** (was a single 2-line bullet at old lines
  112-113) now reads:

  > - **`total_properties_including_inherited`** and
  >   **`total_methods_including_inherited`** added at the top level.
  >   `total_properties` and `total_methods` are both unchanged
  >   (byte-identical, own-only counts).

- Heading text at line 95 (`### Added: `inherited_from` /
  `total_properties_including_inherited` -- inheritance-aware
  `get_object_api` (#86)`) left byte-identical -- anchor link verified
  correct and untouched, per instruction. No other bullet in that entry
  modified.

### EDIT 2 -- `docs/TOOL-CONTRACT.md` (P2)

- **(a)** Over-claim fix folded into the EDIT 1a lead-sentence rewrite above
  (lines 183-188): now states `inherited_from` is emitted by both
  `get_object_api` and `resolve_property`, while both `*_including_inherited`
  totals are produced by `paginate_entity()` and appear on `get_object_api`
  only. Heading at line 181 (`## Inherited member fields (get_object_api,
  resolve_property)`) left unchanged (anchor stability), as instructed.
- **(b)** Closing paragraph, now **line 214**: `api.py:420` corrected to
  `api.py:575` (verified against source, see above).

### EDIT 3 -- `docs/TOOL-CONTRACT.md` (P3)

- **Line 201**: "Class-side ancestor merging is **not** covered by this
  fields" -> "these fields". No other text in that paragraph (lines
  200-205) touched.

### EDIT 4 -- `docs/LIBLCM_EXTRACTION_SEMANTICS.md` (P3)

- **Line 9**, `interfaces` row: added parenthetical after "Full transitive
  closure" -- `(minus IDisposable, IEnumerable, IComparable, filtered out
  before storing -- liblcm_extractor.py:700)`. Table structure unchanged;
  only the one cell's prose was extended.

## Declined / out-of-scope changes

- Did not touch the `## diagnostic_report advisory block` section
  immediately following the edited block in TOOL-CONTRACT.md (line 217+) --
  out of scope for this task.
- Did not alter the CHANGELOG heading text at line 95 despite it only
  naming `total_properties_including_inherited` and not
  `total_methods_including_inherited` -- task explicitly said the anchor is
  verified correct and must not change; only the one bullet was in scope.
- Did not add a template or touch `docs/MANIFEST.md` -- this was a scoped
  precision-fix pass, not a new-doc or archive event; no manifest entries
  changed purpose, trigger set, or status.
- Did not verify or edit any other `api.py:` citation elsewhere in the doc
  tree beyond the two named in the task (line 420 -> 575); a broader sweep
  for stale line-number citations was out of scope for this task and is
  flagged below as a follow-up.

## Files touched

- `D:\Github\_Projects\_LEX\FlexToolsMCP\docs\TOOL-CONTRACT.md`
- `D:\Github\_Projects\_LEX\FlexToolsMCP\CHANGELOG.md`
- `D:\Github\_Projects\_LEX\FlexToolsMCP\docs\LIBLCM_EXTRACTION_SEMANTICS.md`

No `.py` file was read for editing purposes (only read for verification of
existing claims). No GitHub issue was filed, commented on, or closed. No
commit was made; no `git stash` was used.

## Open follow-ups

- A repo-wide sweep for other stale `api.py:` / `liblcm_extractor.py:`
  line-number citations in `docs/` would be worthwhile given the one found
  here (`api.py:420` vs `575`) -- line numbers drift as code changes and
  nothing currently re-verifies them. Suggest as a future doc-audit task,
  not done here (out of the four-edit scope).

---
**Doc Agent:** /lex-doc
