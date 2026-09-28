# Feature Specification: Unified recipes (skeletons become recipes; harvested recipe library)

**Feature Branch**: `feat/unified-recipes` (worktree `C:\Github\FlexToolsMCP-recipes`)

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "Collect 'skeletons' of working tasks that might be reusable, so that the MCP will learn the user's ways. I honestly don't know if the skeletons are really being referenced when we search for capabilities. Some should 'graduate' to the release for other users, though we may need to make them more generic." Follow-ups: "3 tasks: harvest some useful generic recipes and choose some to distribute, make recipes more discoverable. I don't think there's value of distinguishing recipes and skeletons, but recipes is probably the better word." "The MCPlayground skills should be GOLDEN." "The MCPlayground files also show how to make reusable scripts with parameters."

**Tier**: Full - per `.specify/memory/constitution.md` v1.0.0. The change
crosses a published contract (tool list, response keys) and ships recipes that
write to FieldWorks projects. `plan.md` and `tasks.md` follow this spec.

**Touches a write path?**: Yes - shipped write recipes mutate FieldWorks data
when run with `modifyAllowed`. Every write recipe carries a live-LCM
verification obligation on the **Sena 3** test project (see FR-040..FR-043).
Local-recipe capture writes only to `~/.flextoolsmcp/`, never to a project.

**Related issues**: flexicon #542-#547 (API gaps found by the harvest; fixed
separately by another agent). FlexToolsMCP #277 (preflight reflection bypass),
issue #278 (`ClassName`-guard false positive), issue #279 (top-level `Main()`
double run), issue #280 (`write_certification` misses `MakeFeatStruc`).
Original closet: #24; recipes: #52; `user_intent`: #18.

---

## 1. Context: what exists today and why it does not work

Two separate mechanisms hold "code that worked", and neither reaches the place
the assistant actually looks.

**Skeleton closet** (`server/skeleton_storage.py`, issue #24). After every
successful `run_module`, each *top-level `def`* in the code is appended to
`~/.flextoolsmcp/skeletons.jsonl`. Measured on the developer's machine
(309 entries, 2026-07-15..09-25):

- `flextools_search_by_capability` never consults it. USAGE.md claims it does;
  it does not.
- Only `flextools_find_examples` shows skeletons (key
  `skeletons_from_your_sessions`, max 3, newest first, filtered by entity).
  `flextools_list_skeletons` dumps them.
- `user_intent` is hard-coded to `None` at capture
  (`execution.py` `_capture_skeletons_after_success`) although `run_module`
  receives `user_intent` and `operations.jsonl` records it for ~190/193 matching
  ops. Nothing can be found by intent.
- Entity tags are the *whole session's* API list (avg 23, max 62 per def)
  (`_entities_used_in_session`), so the entity filter barely filters.
- About 60% of entries are noise: tiny `'***'`-to-text helpers, near-duplicates
  under different names, test probes. `Main` bodies are split from their
  helpers; 54% of entries reference module-level names that were never
  captured, so they do not run on their own.

**Curated recipes** (`curated_recipes.py`, issue #52). 24 hand-written,
validator-gated snippets, wired into `search_by_capability` and
`find_examples`. But:

- They cover only basic lexicon reads/writes. Nothing covers parser coverage,
  affix templates/slots, allomorph environments, phonological rules or
  safety-checked bulk import, which is what real grammar sessions repeat.
- Matching is "first recipe whose `match_terms` words are all in the query";
  at most one recipe, attached to the top method hit only.
- There is no parameter convention; recipes hard-code their inputs.
- `FLEXICON_VERIFIED_VERSION` is `4.2.1`.

**Proven format outside the repo.** The `flex-parse-fixup` skill
(`C:\Github\MCPlayground\.claude\skills\flex-parse-fixup\scripts\lib\`) keeps
23 hand-refined scripts. Each is complete, runnable `run_module` code that
opens with a parameter block:

```python
# --- PARAMS ---
TARGETS = ["...", "..."]
# --- END PARAMS ---
```

To reuse one, the assistant edits only the values inside the block and runs
the file with `source="existing"`. Scripts named `w_*` write, and guard every
write with `if modifyAllowed:`. This is the format this spec adopts.

## 2. Decisions already made

- **One concept, called "recipes".** Skeletons and recipes are not
  distinguished to the user. A recipe is either *shipped* (in the package, for
  every user) or *local* (captured from this user's own successful runs). Same
  shape, same search, same listing tool.
- **Recipes are full runnable scripts, not skeletal pseudocode.** Pseudocode
  saves tokens up front but makes the assistant re-discover every call, cast
  and retry; the harvest shows that is where sessions lose time (e.g. ~15
  failed attempts before a parser-coverage script ran; 14 casting rejections
  in one user's sessions). Token cost is controlled by *response size*, not by
  degrading the code: search and listing return compact rows; full code comes
  back only for the top match or on request by id.
- **Parameters use the `# --- PARAMS ---` block**, as in MCPlayground. No new
  `run_module` argument; the assistant edits values in place.
- **The MCPlayground scripts are the primary source** for the first shipped
  batch, preferred over other versions of the same task. A second user's
  (Ron's) tasks are strong evidence of real need; he consented to this use.
  His code is rewritten to current flexicon (his raw-LibLCM writes predate the
  flexicon slot API). None of his data ships.
- **`DoNotUseForParsing` is deprecated.** No recipe uses it.
- **Sena 3 is the only test project.** Claude-Swahili is a work project; no
  verification, test or check runs against it. Harvested Claude-Swahili code
  is source material only, with Swahili-specific defaults removed.
- **Contracts are append-only** (constitution IV): the old tool name and
  response key stay as deprecated aliases until `tool-responses/2.0`.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Search finds a working recipe (Priority: P1)

A linguist asks the assistant "which frequent words don't parse yet?". The
assistant calls `flextools_search_by_capability`. The response carries a
ranked `recipes` list whose top row is the shipped parser-coverage recipe,
with full code and its parameters. The assistant sets `COUNT = 50`, runs it,
and gets the answer on the first run, with no discovery loop and no casting
errors.

**Why this priority**: This is the question the user asked ("are they really
referenced when we search?"). Without it, neither local nor shipped recipes
help.

**Independent Test**: With only the existing 24 recipes plus the new search
path, run `search_by_capability` on a battery of natural queries (FR-061) and
check the expected recipe is in the top 3.

**Acceptance Scenarios**:

1. **Given** the shipped library, **When** the query is "list the affix
   templates and slots for verbs", **Then** `recipes[0].id` is the
   templates/slots recipe and it includes `code` and `params`.
2. **Given** a query no recipe covers ("frobnicate the widgets"), **When**
   searched, **Then** `recipes` is empty and method results are unchanged.
3. **Given** the pre-existing test query "list all entries with their
   glosses", **When** searched, **Then** `results[0].recipe` is still
   attached exactly as before (back-compat), and its code is not repeated in
   `recipes`.
4. **Given** the object-only query "entry", **When** searched, **Then**
   `recipes` holds up to 3 compact rows with no `code`, and
   `recipes_ambiguous` is true.
5. **Given** the query "phone environments on an allomorph", **When**
   searched, **Then** a recipe whose code uses `PhoneEnv` ranks in the top 3
   (a match through function and property names).

---

### User Story 2 - The MCP remembers what worked for this user (Priority: P1)

Yesterday the user had the assistant write a script that lists entries whose
glosses are longer than five words. Today, in a new session, they ask for
"long glosses again". Search returns yesterday's script as a local recipe,
labelled with the intent they gave, when it was last used and how many times
it succeeded.

**Why this priority**: "Learn the user's ways" is the original goal. The
capture exists but stores fragments without intent, so it is unfindable.

**Independent Test**: Run a successful snippet with `user_intent`, restart the
server, search for a paraphrase of the intent, and check the local recipe is
returned with its full code.

**Acceptance Scenarios**:

1. **Given** a successful `run_module` with `user_intent="List entries with
   glosses over five words"` and 12 non-blank lines, **When** the op finishes,
   **Then** one local recipe is stored with that intent, the whole snippet as
   code, entity tags taken from that code only, and `use_count` 1.
2. **Given** the same code (ignoring comments and whitespace) succeeds again,
   **When** captured, **Then** no duplicate appears; `use_count` becomes 2 and
   `last_used` updates.
3. **Given** a 2-line probe, or a run without `user_intent`, **When** it
   succeeds, **Then** nothing is captured.
4. **Given** an existing `skeletons.jsonl`, **When** the server first loads
   local recipes, **Then** legacy entries are migrated with intent recovered
   from `operations.jsonl` by `op_id`, trivial helpers dropped, and the
   original file left in place, untouched.

---

### User Story 3 - A shipped library of real grammar and lexicon recipes (Priority: P1)

A new user on another language project gets, out of the box, runnable recipes
for the tasks grammar and lexicon sessions repeat: parser coverage, lexicon
lookup, entry modelling detail, affix templates and slots, allomorph
environments, phonological rules, the "who uses this form?" check before
editing, safe bulk entry creation, entries modelled on an existing comparator,
texts from lines, variant entries.

**Why this priority**: Graduating recipes to all users is the second half of
the request, and the harvest found every one of these tasks missing from the
shipped set.

**Independent Test**: Each shipped recipe passes the validator in CI, and each
read recipe runs unchanged (default params) on Sena 3 with no errors; each
write recipe runs on Sena 3 with `modifyAllowed=False` and reports what it
would do.

**Acceptance Scenarios**:

1. **Given** the recipe file `lexicon-form-lookup.py`, **When** loaded,
   **Then** its `params` list is derived from the PARAMS block (names,
   defaults, trailing-comment descriptions) and it appears in
   `CURATED_RECIPES`.
2. **Given** a vernacular form stored decomposed (NFD) in the project,
   **When** `lexicon-form-lookup` is run with the composed (NFC) spelling,
   **Then** it still finds the entry.
3. **Given** any write recipe, **When** run with `modifyAllowed=False`,
   **Then** it changes nothing and reports each change it would make.

---

### User Story 4 - Browse what recipes exist (Priority: P2)

The user asks "what can you already do with templates?". The assistant calls
`flextools_list_recipes(query="template")` and gets compact rows (id, intent,
shipped/local, reads or writes, params, use count), then fetches one with
`recipe_id` to see its code.

**Why this priority**: Makes the library visible as a capability list without
guessing search phrases. It also replaces `flextools_list_skeletons`.

**Independent Test**: Call the tool with each filter and with `recipe_id`;
check shapes and that no row carries code unless `recipe_id` is given.

**Acceptance Scenarios**:

1. **Given** no arguments, **When** called, **Then** all shipped and local
   recipes are listed as compact rows, shipped first, with no `code` field.
2. **Given** `recipe_id="parser-coverage"`, **When** called, **Then** the full
   recipe with `code` is returned.
3. **Given** a client still calling `flextools_list_skeletons`, **When**
   called, **Then** it returns local recipes in the old row shape plus a
   `deprecation` notice naming `flextools_list_recipes` and removal at
   `tool-responses/2.0`.

---

### User Story 5 - Promote a local recipe to the shipped library (Priority: P3)

The developer finds a local recipe that worked across several sessions and
runs `flextools-mcp-recipe promote <local-id> --id long-glosses`. A draft
recipe file is written with the header filled in from the local record
(intent, entities, reads/writes, origin) and a PARAMS stub. The developer
generalizes it, and CI's validator gate decides when it can ship.

**Why this priority**: Turns the manual harvest done for this spec into a
repeatable path. Lower priority because the first batch is ported by hand.

**Independent Test**: Promote a fixture local recipe into a temp directory;
the draft parses as a recipe file and fails validation only where the stub
needs human editing.

**Acceptance Scenarios**:

1. **Given** a local recipe, **When** promoted without `--out`, **Then** the
   draft goes to `~/.flextoolsmcp/recipe-drafts/`, never into the package.
2. **Given** a draft containing a GUID literal, a Windows user path or a known
   project name, **When** promoted, **Then** the command lists each such line
   as "scrub before shipping".

---

### Edge Cases

- A recipe file's header is malformed or its id collides with a dict recipe:
  loading fails loudly at import time in tests, and at runtime the bad file is
  skipped with one logged error (the server must still start).
- The PARAMS block is missing or malformed: `params` is `[]`; the recipe still
  loads; the validator warns if the header says it takes parameters.
- `recipes.jsonl` has malformed lines: skipped, as the skeleton store does now.
- `operations.jsonl` is missing or has no match for a legacy `op_id`: the
  legacy entry migrates with `intent` null and the lowest rank, or is dropped
  if trivial.
- The same snippet succeeds on two projects: one local recipe; `projects`
  records both names (local only; never shipped).
- A local recipe was captured with writes: `requires_write` is true; search
  rows show it; its code already contains the `modifyAllowed` guard because
  `run_module` refused it otherwise.
- A shipped recipe trips the `ClassName`-guard false positive (#278): it must
  be restructured to pass today's validator, or held back until #278 lands.
  Shipping it with a validator exemption is not allowed (constitution I:
  gates never relax).
- A recipe needs a flexicon function that does not exist yet (#542-#547): it
  may ship with the raw-LCM fallback plus a comment naming the issue, and must
  be updated when the flexicon release lands (release order: flexicon first,
  then regenerate MCP indexes).
- The local store grows without bound: capped at 2,000 recipes; oldest
  least-used rows are dropped on rewrite.

## Requirements *(mandatory)*

### Functional Requirements

**Recipe file format and loader**

- **FR-001**: Shipped recipes MUST be loadable from one-file-per-recipe
  sources under `src/flextoolsmcp/recipe_library/*.py`, in addition to the
  existing `CURATED_RECIPES` dict entries.
- **FR-002**: Each recipe file MUST begin with a metadata docstring of
  `key: value` lines (values JSON-parsed where possible) carrying at least
  `id`, `intent`, `match_terms`, `entities`, `operations`,
  `requires_write`, `notes`, `origin`. The loader MUST strip the docstring;
  `code` is the rest of the file.
- **FR-003**: The loader MUST derive `params` from the `# --- PARAMS ---` /
  `# --- END PARAMS ---` block: each top-level assignment becomes
  `{name, default (source text), description (trailing comment)}`.
- **FR-004**: File recipes MUST be merged into `CURATED_RECIPES` so every
  existing consumer (`server/recipes.py`, `extract_patterns.py`, tests) sees
  them. An id collision MUST raise at import time.
- **FR-005**: The library directory MUST be package data in the wheel and
  excluded from pyright (the files reference runner-injected names).
- **FR-006**: `FLEXICON_VERIFIED_VERSION` MUST be bumped to the flexicon
  version the batch is verified against, which MUST equal the flexicon
  version the shipped MCP indexes target (4.11.0 as of release 2.14.0).

**Local recipes (replace the skeleton closet)**

- **FR-010**: `server/skeleton_storage.py` MUST be replaced by
  `server/local_recipes.py`, storing to `~/.flextoolsmcp/recipes.jsonl`
  (override: `FLEXTOOLSMCP_RECIPE_DIR`; the old `FLEXTOOLSMCP_SKELETON_DIR`
  is honoured as a fallback).
- **FR-011**: After a successful `run_module`, the WHOLE executed code MUST be
  captured as one local recipe when `user_intent` is non-empty and the code
  has at least 4 non-blank, non-comment lines. Per-`def` capture is removed.
- **FR-012**: A local recipe MUST record: `id` (`local-<fingerprint12>`),
  `intent`, `code`, `entities` (derived from THIS code's AST: `project.<X>`
  accessors mapped to entity names, plus `I*` interfaces it names),
  `requires_write` (true if the run was write-enabled and the code is
  mutating), `projects`, `first_used`, `last_used`, `use_count`, `op_ids`
  (last 5), `source: "local"`.
- **FR-013**: Identity MUST be a fingerprint of the code with comments and
  blank lines removed and whitespace normalized. A repeat MUST update
  `use_count`/`last_used`/`op_ids`/`projects` rather than add a row.
- **FR-014**: Capture MUST never raise or fail the op (current guarantee).
- **FR-015**: On first load, if `recipes.jsonl` is absent and
  `skeletons.jsonl` exists, legacy entries MUST be migrated: intent recovered
  from `logs/operations.jsonl` by `op_id`; entries under 5 lines or whose
  body is only a text/`'***'` helper dropped; near-duplicates merged. The
  legacy file MUST NOT be modified or deleted.
- **FR-016**: The local store MUST be capped (FR edge case: 2,000 rows).

**Search and discovery**

- **FR-020**: `server/recipes.py` MUST provide one ranked search over shipped
  and local recipes. It scores query words against these fields, weighted
  from highest to lowest:
  1. task text: `match_terms` phrases, then `intent` words;
  2. function and property names used in the recipe's code, extracted by
     AST and split on camelCase and underscores, with a small alias table
     (for example `env` = environment, `msa` = grammatical info);
  3. object names (`entities`, and object words in `id`), weighted lowest.

  Each word is weighted by how rare it is across the recipe set (IDF-style),
  so a word shared by most recipes (for example "entry") contributes little.
  Normalization covers case, punctuation and plural `-s`. Shipped recipes,
  and local recipes with a higher `use_count`, get a boost.
- **FR-021**: `flextools_search_by_capability` MUST add `recipes` (up to 3
  rows), `recipes_count` and `recipes_ambiguous` to its response. The first
  row carries full `code` only when it is a clear winner: its score is above a
  minimum, at least 1.5 times the second row's, and not reached through object
  names alone. Otherwise every row is compact (no `code`),
  `recipes_ambiguous` is true, and the response carries a hint to refine the
  query or fetch one with `flextools_list_recipes(recipe_id=...)`. A response
  never carries the same recipe's code twice: when the winner is also
  attached at `results[0].recipe`, the `recipes[0]` row stays compact and
  points at that attachment (`code_at: "results[0].recipe"`).
- **FR-022**: The existing `results[0].recipe` attachment MUST keep working
  unchanged (append-only contract).
- **FR-023**: `flextools_find_examples` MUST include matching local recipes in
  its existing `recipes` list. `skeletons_from_your_sessions` MUST still be
  emitted in parallel, marked deprecated, until `tool-responses/2.0`.
- **FR-024**: A new tool `flextools_list_recipes` MUST accept `query`,
  `source` (`all`|`shipped`|`local`), `requires_write` (optional bool),
  `limit`, and `recipe_id`. Without `recipe_id` it returns compact rows only;
  with it, the full recipe.
- **FR-025**: `flextools_list_skeletons` MUST remain as a deprecated alias
  (local recipes, old row shape, plus a deprecation notice) until
  `tool-responses/2.0`.
- **FR-026**: Serving a recipe (search top row, `list_recipes` by id) MUST
  record its entities as validated discovery, as curated recipes already do
  (constitution II).
- **FR-027**: Tool descriptions and server instructions MUST tell the
  assistant to check `recipes` before composing code, and how to use PARAMS
  (edit values only; run with `source="existing"` when the code is unchanged
  apart from PARAMS).

**Promotion**

- **FR-030**: A console script `flextools-mcp-recipe` MUST support
  `promote <local-id> --id <new-id> [--out DIR]`, writing a draft recipe file
  (header prefilled, PARAMS stub) to `~/.flextoolsmcp/recipe-drafts/` by
  default.
- **FR-031**: `promote` MUST flag lines containing GUID literals, Windows user
  paths, or project names recorded in the local recipe, as needing scrubbing.
- **FR-032**: `extract_patterns --mine-operations-log` docs and code comments
  MUST point at the new local-recipe store instead of the skeleton closet.

**Recipe validation and verification**

- **FR-040**: Every shipped recipe MUST pass `recipe_validator.validate_recipe`
  in CI (existing gate, extended to file recipes).
- **FR-041**: The validator MUST also check:
  - the PARAMS block parses;
  - every shipped recipe with `requires_write` guards writes with
    `if modifyAllowed:`;
  - no recipe uses a deprecated member. A member counts as deprecated if it
    is curated as deprecated (for example `DoNotUseForParsing`) or if the
    flexicon index marks it deprecated (a deprecation flag or docstring);
  - no shipped recipe contains a GUID literal, a Windows user path, or the
    names `Claude-Swahili`/`Target` as defaults.
- **FR-045**: The validator MUST keep raw LibLCM use minimal
  (`detect_raw_lcm_access`). It flags these forms of raw access: casts to
  `I*` interfaces, `*OA`/`*OS`/`*OC`/`*RA`/`*RS`/`*RC` property access,
  `project.project`, `ServiceLocator`, and `ClassName` dispatch. For each one:
  (a) where the flexicon bridge index shows a flexicon wrapper for that
  property, the recipe fails and the message names the wrapper;
  (b) otherwise the line MUST carry `# flexicon gap: <issue>` or
  `# raw-lcm: <reason>`, or the recipe fails. A `raw-lcm:` note may override a
  wrong wrapper suggestion from (a), but only with a stated reason. Each
  shipped recipe's header records `raw_lcm_lines`, and a test fails when the
  count in the code exceeds it. This is a style gate. The note never relaxes
  a write-safety or casting check.
- **FR-042**: Every shipped READ recipe MUST have been run unchanged (default
  params, or params set to Sena 3 data) on **Sena 3** via `run_module`, with
  no errors; evidence recorded under `specs/unified-recipes/evidence/`.
- **FR-043**: Every shipped WRITE recipe MUST have been run on **Sena 3** with
  `modifyAllowed=False` (dry run), showing the intended changes. A live write
  on Sena 3 with pre/post evidence is required for any recipe that creates or
  deletes objects. Before and after each live run, record the Sena 3 `.fwdata`
  mtime and hash. No verification run ever targets Claude-Swahili.
- **FR-044**: Each recipe's `verified_against` MUST record the flexicon
  version and `verified_by` (`preflight`, `sena3-read`, `sena3-dryrun`,
  `sena3-live`).

**First shipped batch**

- **FR-050**: The first batch MUST include recipes for these tasks (source in
  brackets; MCPlayground `lib/` preferred where it has the task):
  1. `parser-coverage` - coverage % and top-N unparsed wordforms by frequency
     [MCPlayground `candidates.py`; logs; Ron]
  2. `lexicon-form-lookup` - do these forms exist as lexeme form, headword or
     allomorph; NFC on both sides [MCPlayground `lexicon_lookup.py`; Ron's
     NFC fix]
  3. `entry-parser-detail` - allomorphs in order, environments, IsAbstract,
     MSA, POS, inflection class, features, slots [`entry_detail.py`]
  4. `wordform-analyses` - existing analyses (morph + gloss) of given words
     [`wordform_analyses.py`]
  5. `form-usage-before-edit` - analyses that use an entry's forms, with human
     and parser opinion; the check to run before changing forms
     [`allomorph_refs.py`]
  6. `affix-templates-and-slots` - templates for given POSes, slots (optional
     marked), affixes in each slot, environments [`templates_slots_envs.py`]
  7. `phonological-rules` - every rule and, for a name filter, its contexts and
     exception features [`phon_rules.py`]
  8. `wordform-case-variants` - case variants of target wordforms with counts
     [`find_variants.py`]
  9. `create-entries-idempotent` - new entries/senses from rows, skipping
     existing lf+gloss+POS, validating every POS before any write
     [`w_create_entries.py`; Ron's bulk import]
  10. `create-entry-like-comparator` - new stems copying a comparator's POS,
      inflection class and features [`w_create_stem_like.py`]
  11. `set-allomorph-environments` - remove/add EXISTING environments on one
      allomorph [`w_set_allomorph_env.py`]
  12. `add-inflectional-affix` - new affix entry with POS and slots copied from
      a comparator affix [`w_add_affix.py`]
  13. `add-allomorph` - add an allomorph, optionally with an existing
      environment [`w_add_allomorph.py`]
  14. `create-text-from-lines` - create a text with one paragraph per line;
      warn if the title exists rather than delete-and-recreate [Ron]
  15. `create-variant-entries` - create variant entries of a given variant
      type for (main, variant) pairs [Ron]
  16. `affix-template-setup` - POS subcategory, template, add existing slots,
      repoint stem MSAs (restoring inflection class) [developer op
      `op-142307019-033`]
- **FR-051**: Each ported recipe MUST use the current flexicon API wherever an
  equivalent exists, use GUID or comparator lookups rather than headword
  strings for writes, NFC-normalize vernacular comparisons, and report through
  `report.*` (never `print`).
- **FR-052**: Recipes blocked on #278 or a flexicon gap MAY be deferred to a
  second batch; the spec is complete when at least 12 of the 16 ship.
- **FR-053**: Recipe `notes` SHOULD carry the "don't do this" lessons the
  harvest found in two or more sources, where relevant to that recipe (e.g.
  don't cast flexicon wrappers such as `AffixTemplate` to LCM interfaces; read
  `MorphType` names, don't `.lower()` the object; restore `InflectionClassRA`
  after `SetStemMsaPos`).

**Documentation and tests**

- **FR-060**: USAGE.md (tool reference checked by
  `scripts/validate_integrity.py server`), CLAUDE.md's skeleton-closet
  paragraph, README's user-data line, and a new `docs/RECIPES.md` (format,
  PARAMS, local capture, promotion, verification rules) MUST be updated.
  CHANGELOG MUST record the new tool, the new response keys, and the
  deprecations with their removal version.
- **FR-061**: Tests MUST cover: file loader and PARAMS parsing; id collision;
  local capture rules (FR-011..FR-013); legacy migration; ranked search
  including a battery of at least 20 natural queries mapped to expected
  recipes (top-3 hit); `list_recipes` filters and `recipe_id`; the deprecated
  alias and key; tool list updates in `test_mcp_tools.py`.
- **FR-062**: Test suites MUST be run with `-m "not requires_flex"`; live
  checks are done deliberately against Sena 3 only.

### Key Entities

- **Recipe**: a runnable `run_module` snippet plus metadata: id, intent,
  match terms, entities, operations, reads/writes, params, notes, source
  (`shipped`/`local`), origin, verification record.
- **Recipe file**: the on-disk source of one shipped recipe (metadata
  docstring + PARAMS block + code).
- **Local recipe record**: one JSONL row in `~/.flextoolsmcp/recipes.jsonl`
  with usage stats and provenance (projects, op ids).
- **Parameter**: a name, default value and description taken from the PARAMS
  block.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the query battery (FR-061), the expected recipe is in the top
  3 `recipes` rows for at least 90% of queries; today the rate is near zero
  for anything outside basic lexicon reads.
- **SC-002**: After one successful run with an intent, a paraphrased search in
  a new session returns that local recipe in the top 3.
- **SC-003**: At least 12 new shipped recipes, each passing the validator and
  each verified on Sena 3 per FR-042/FR-043.
- **SC-004**: Migrated local store is at least 50% smaller than the legacy
  `skeletons.jsonl` row count, with no remaining entry under 5 lines.
- **SC-005**: A compact recipe row averages under 400 characters; a search
  response carries at most one full code body in total, counting
  `results[0].recipe`, and none for an ambiguous or object-only query (for
  example "entry").
- **SC-006**: No response key or tool present before this change disappears
  (contract test).

## Assumptions

- The flexicon API gaps (#542-#547) are fixed by another agent; this work
  does not wait for them (FR-052 covers blocked recipes).
- The current preflight stays as-is during this work; #277-#280 are fixed
  separately. Recipes are made to pass today's validator.
- Lexical ranking is enough for the recipe set's size (tens to low hundreds).
  Embedding-based ranking over recipe intents is a possible follow-up, using
  the existing `semantic_search` if enabled.
- Local recipes stay on the user's machine. They are never uploaded or
  shipped; only `promote` plus human review moves code into the package.
- Harvested evidence (six scanner reports, a domain review and a synthesis,
  2026-09-25/26) informs the recipe list; it lives outside the repo and is
  summarized here, not committed, because it quotes project data.

## Appendix A: Harvest summary

Sources scanned 2026-09-25/26: developer MCP logs (19 date folders, ~18 MB,
~700 successful `run_module` ops), `skeletons.jsonl` (309 entries),
MCPlayground `flex-parse-fixup` scripts (23 `lib/` scripts plus run records),
and a second user's logs (22 sessions, German and Malayalam projects,
381 ops).

- Recurring tasks across sources (sources in brackets): parser coverage [all
  six]; affix templates/slots [all six; opens nearly every grammar session];
  lexicon form lookup [4]; allomorph environments [4]; POS subcategory and
  repoint [4]; bulk entry import [2, both of the second user's projects];
  text creation [2]; variant entries [second user, both projects].
- Flexicon gaps filed: slot readers (#542), inflectional-affix slot reader
  (#543), MSA feature-structure reader (#544), sense `DoNotPublishIn` (#545),
  allomorph `IsAbstract` (#546), `AddSubcategory` catalog id (#547).
- Safety-check issues filed: #277-#280 (see header).
- Most common failure idioms: wrong inventory path
  (`WordformInventoryOA`) instead of `project.Wordforms.GetAll()`; casting
  flexicon wrappers to LCM interfaces; comparing vernacular text without
  Unicode normalization; `print()` instead of `report`; bulk writes without
  validating lookups first; a module that calls its own `Main()`.
