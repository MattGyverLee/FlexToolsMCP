# Research: Unified recipes

Phase 0 decisions for `specs/unified-recipes/spec.md`. Each entry is
Decision / Rationale / Alternatives considered. There are no open
`NEEDS CLARIFICATION` items.

Findings from codebase mapping (2026-09-27) that shape these decisions:

- The feature worktree `C:\Github\FlexToolsMCP-recipes` (`feat/unified-recipes`,
  47ab04a) branched before `main` gained #278 (ClassName-guard fix, #284),
  #280 (MakeFeatStruc mutating, #282), #277, #285 and the 2.14.0 release. The
  "blocked on #278" branch of FR-052 no longer applies once the branch is
  rebased.
- The MCP server has **no `instructions` string** today
  (`server.py:1104` `build_server(...)`; `mcp_compat.py:68-77` forwards
  `**kwargs` to `Server`).
- `handle_run_module` already has `user_intent` (`execution.py:3090`),
  `project_name`, `write_enabled`, `op_id` and `is_mutating_script`
  (`:4923`) in scope. Capture (`:5492`) runs *after* the operations-log stash
  is popped (`:5478`), so capture must take these from locals, not the stash.
- `operations.jsonl` never stores code; it stores `op_id` + `user_intent`,
  which is what legacy migration needs.
- None of the 13 MCPlayground `lib/` scripts has trailing comments on PARAMS
  lines; the only PARAMS comments are standalone lines above a value. None
  NFC-normalizes. Most rely on raw-LCM casts and `ClassName` dispatch;
  `phon_rules.py` uses no flexicon at all.
- The existing curated recipes carry `source: "curated"` and a test pins it
  (`tests/test_recipes.py:59`); `results[0].recipe` exposes that dict as-is.

---

## R1. Where the recipe-file loader lives

**Decision**: New module `src/flextoolsmcp/recipe_files.py` owns everything
about the on-disk format: header parsing, PARAMS parsing, directory loading,
the scrub patterns (GUID / Windows user path / forbidden project names), and
the draft writer used by `promote`. `curated_recipes.py` calls
`load_recipe_library()` at the bottom and merges the result into
`CURATED_RECIPES`.

**Rationale**: Principle VI (one source of truth). The validator (FR-041
scrub check) and the promote command (FR-031 scrub flags) must agree on what
"needs scrubbing" means; one module holding the patterns guarantees that.
Merging at the bottom of `curated_recipes.py` means every existing consumer
(`server/recipes.py`, `extract_patterns.py`, tests) sees file recipes with no
change (FR-004).

**Alternatives considered**: Loader inside `server/recipes.py` (rejected:
`extract_patterns.py` imports `curated_recipes`, not the server package, so
the index would miss file recipes). Separate loader and scrub modules
(rejected: two places to keep in step for no gain).

## R2. Recipe library is data, not a Python package

**Decision**: `src/flextoolsmcp/recipe_library/` has **no `__init__.py`**.
Files are read as text through `importlib.resources.files("flextoolsmcp") /
"recipe_library"`, never imported. Packaging adds `recipe_library/*.py` to
`[tool.setuptools.package-data]` and a `graft` line to `MANIFEST.in`.
`pyrightconfig.json` and ruff `extend-exclude` exclude the directory.

**Rationale**: The files reference runner-injected names (`project`,
`report`, `modifyAllowed`) and would fail import or type checking. With
`packages.find where=["src"]` and no `namespaces=false`, a directory without
`__init__.py` could still be picked up as a namespace package; listing it as
package data and never importing it keeps it inert. A wheel smoke test must
confirm the files ship (FR-005).

**Alternatives considered**: `.recipe` or `.txt` extension (rejected: loses
editor highlighting and linting of real Python, and the MCPlayground format
is `.py`). Recipes as JSON (rejected: code in JSON strings is unreadable and
unreviewable, the current dict's main weakness).

## R3. Header format

**Decision**: The file starts with a module docstring. Each line is
`key: value`. The value is `json.loads`-ed when that succeeds, else kept as a
stripped string. A line indented deeper than its key continues the previous
value (joined with a single space), so `notes` can span lines. Required keys:
`id`, `intent`, `match_terms`, `entities`, `operations`, `requires_write`,
`notes`, `origin`. Optional: `verified_against` (JSON object),
`takes_params` (bool, defaults to "PARAMS block present"). `code` is the file
text after the docstring, with leading blank lines removed. The file stem must
equal `id`.

**Rationale**: Matches FR-002 exactly and stays hand-editable. The stem rule
makes `recipe_id` lookup and collision diagnosis trivial.

**Alternatives considered**: YAML front matter (rejected: new dependency,
and not valid Python). A `RECIPE = {...}` dict literal (rejected: it would
end up in `code` and run).

## R4. PARAMS parsing and descriptions

**Decision**: Find the lines between `# --- PARAMS ---` and
`# --- END PARAMS ---`, `ast.parse` that slice, and for each top-level
`Assign`/`AnnAssign` with a single `Name` target emit
`{name, default, description}`. `default` is `ast.get_source_segment` of the
value (source text, possibly multi-line). `description` is the trailing
`# comment` on the assignment's first line if present, otherwise the
contiguous standalone comment lines directly above it (inside the block),
joined with a space. For multi-line values, comment lines *inside* the value
(the MCPlayground tuple-shape notes) are appended to the description. A
missing block gives `params: []`. A block that does not parse gives
`params: []` plus a loader warning that the validator turns into an issue
when `takes_params` is true.

**Rationale**: FR-003 names trailing comments, but the source scripts put
their descriptions on the lines above or inside the value (for example
`# (lexeme form, morph type, gloss, citation form or None)`). Reading all
three positions keeps the harvested guidance without rewriting every block.

**Alternatives considered**: Trailing comments only (rejected: would give
empty descriptions for every harvested write recipe). Regex over lines
(rejected: breaks on multi-line list/dict defaults).

## R5. Malformed file vs id collision

**Decision**: `load_recipe_library()` returns `(recipes, errors)`. A file
with a malformed header, a missing required key or a stem/id mismatch goes to
`errors`, is skipped, and gets one `logger.error` line; the server still
starts. An **id collision** (between two files, or between a file and a dict
entry) raises `ValueError` at import. A test asserts `errors == []` for the
shipped library, so a malformed file fails CI loudly.

**Rationale**: The spec's edge case asks for "loud in tests, skipped at
runtime" for malformed files, and FR-004 asks for a raise on collision. A
collision can only come from a packaging mistake that CI catches before any
wheel exists, so raising never reaches a user. Silently picking one of two
recipes with the same id would serve the wrong code.

**Alternatives considered**: Raise on every error (rejected: one bad draft
file copied into an editable install would take the server down). Skip on
collision (rejected: FR-004).

## R6. `source` vocabulary on the new surfaces

**Decision**: Internally and in `results[0].recipe`, shipped recipes keep
`source: "curated"` (unchanged dict, unchanged test). The **new** row shape
(`recipes` on search, rows from `flextools_list_recipes`, local entries in
`find_examples.recipes`) carries `source: "shipped" | "local"`, and
`list_recipes(source=...)` takes `all | shipped | local` as the spec pins.
The row builder maps `curated` to `shipped`.

**Rationale**: Principle IV: the existing attachment must not change
(FR-022). The new keys are free to define, and the spec's user-facing words
are "shipped" and "local". The CURATED_RECIPES dict also feeds the
`common-patterns/2.0` index schema, which stays unchanged.

**Alternatives considered**: Rename `curated` to `shipped` everywhere
(rejected: changes a value in a published response and the index schema,
which needs a major bump). Use `curated` on new rows too (rejected: the spec
and USAGE text say shipped/local; "curated" means nothing to a user choosing a
filter).

## R7. Local store: format, identity, write strategy, cap

**Decision**:
- File: `recipes.jsonl` in `FLEXTOOLSMCP_RECIPE_DIR`, else
  `FLEXTOOLSMCP_SKELETON_DIR` (fallback), else `~/.flextoolsmcp/`.
- Fingerprint: run the code through `tokenize`, drop `COMMENT`, `NL` and
  blank lines, collapse runs of whitespace inside each line to one space,
  strip each line, join with `\n`, then take `sha256[:12]`. The id is
  `local-<fp12>`. If tokenize fails, fall back to a line-based strip.
- Capture reads the whole file under the process lock, updates or inserts
  the row, applies the cap, and rewrites through a temp file plus
  `os.replace` (atomic on Windows for same-volume files).
- Cap: 2,000 rows. When over the cap, drop rows ordered by
  `(use_count asc, last_used asc)` until at the cap.

**Rationale**: Repeats must update in place (FR-013), so append-only JSONL no
longer fits; a full rewrite of at most 2,000 rows is cheap. `tokenize`
treats `#` inside string literals correctly, which a regex would not.
Keeping JSONL (not JSON or SQLite) keeps "malformed lines are skipped" and
lets a human read the file.

**Alternatives considered**: SQLite (rejected: overkill at this size, and a
second storage idiom in `~/.flextoolsmcp`). An AST-dump fingerprint (rejected:
two snippets that differ only in a string literal's quoting would collide,
and `ast.dump` changes between Python versions, which would break identity
across upgrades).

## R8. Entity tags for local recipes

**Decision**: Walk the code's AST. For every `project.<X>` attribute access,
map `X` through `validators._accessor_to_ops_map(api_index)` (for example
`Senses` to `LexSenseOperations`) and strip the `Operations` suffix to get
the entity (`LexSense`), matching the style of shipped recipe entities.
Unmapped accessors are kept as written. Add every `Name` matching
`^I[A-Z]\w+$` (LCM interfaces the code names). Sort and de-duplicate. Remove
`_entities_used_in_session`.

**Rationale**: FR-012 wants tags from *this* code, not the session. The map
already exists and handles the flexicon naming divergences (Senses,
Wordforms, PhonRules). Reusing it follows Principle VI.

**Alternatives considered**: Tag with raw accessor names (rejected: would
not match shipped recipe entities or `find_examples(object_type=...)`
filters). Keep session tags as a fallback (rejected: that is the current
noise source, averaging 23 tags per entry).

## R9. Legacy migration strategy

**Decision**: Run once, when `recipes.jsonl` is absent and `skeletons.jsonl`
exists:
1. Group legacy entries by `op_id`, keeping capture order, and join their
   `source` defs back into one code body per op. This restores `Main`
   together with its helpers from the same run (54% of entries reference
   module-level names that the per-def split lost).
2. Take the intent from `operations.jsonl` (plus `.1`) by `op_id`, falling
   back to the entries' own `user_intent`, else `null`.
3. Drop bodies with fewer than 5 real lines, and bodies whose every def is a
   text or `'***'` helper (at most one statement, a return involving
   `.Text`, `BestAnalysis*`/`BestVernacular*` or `'***'`).
4. Merge near-duplicates by fingerprint, summing `use_count` and keeping the
   newest `last_used`.
5. Mark rows `migrated: true`. Search ranks rows with a `null` intent last.

Write the result with the normal atomic writer. The legacy file is only
opened read-only.

**Rationale**: Per-op regrouping is the step that turns fragments back into
runnable code, which is what makes the migrated store worth searching.
SC-004 (at least 50% smaller, nothing under 5 lines) follows from steps 3 and 4.

**Alternatives considered**: Migrate each def separately (rejected: carries
the noise forward). Drop the legacy data (rejected: US2 scenario 4).

## R10. Ranking

**Decision**: One lexical scorer in `server/recipes.py` over both sources,
weighted by *what kind* of word matched and *how rare* it is.

- **Normalization**: lowercase; non-alphanumerics become spaces; a small
  stopword set is dropped ("the", "a", "all", "with", "their", "of", "for",
  "to", "and", "my", "in", "on", "which", "what", "how"); a trailing `s` is
  stripped from words longer than 3 letters.
- **Term bags per recipe**, built once at load time (local recipes when
  captured or loaded):
  - *task*: `match_terms` phrases and `intent` words;
  - *code*: `code_terms`, the function-call and attribute names in the
    recipe's AST (`GetOccurrenceCount`, `PhoneEnvRC`, `AffixTemplatesOS`).
    They are split on camelCase and underscores, LCM suffixes
    (`OA|OS|OC|RA|RS|RC`) and a `Get/Set/Add/Remove/Create` prefix are
    dropped, and an alias table maps each piece to query words;
  - *object*: `entities` split on case, plus the object words in `id`.
- **Alias table**: a dozen or so entries, kept in `recipes.py`:
  - `env` = environment
  - `msa` = grammatical info
  - `pos` = part of speech
  - `infl` = inflection / inflectional
  - `feat`, `feats` = feature
  - `wfi` = wordform
  - `allo` = allomorph
  - `phon` = phonological
  - `templ` = template
  - `occurrence` = frequency, count
  - `parser count` = parsed
- **IDF**: `idf(w) = ln(1 + N / df(w))`, where `N` is the number of recipes
  and `df(w)` is the number of recipes with `w` in any bag. It is recomputed
  when the local store changes. A word present in most recipes ("entry",
  "sense") therefore contributes little, and there is no hard-coded list of
  "common objects". Object words that are really task words ("variant",
  "allomorph", "template", "slot") stay strong because they are rare.
- **Score**:
  - `4.0 * idf-mean` for each `match_terms` phrase whose words are all in
    the query;
  - plus, for each query word, its `idf` times the weight of the best bag it
    hits: task 2.0, code 1.5, object 0.25.
- **Floor**: a row needs a phrase hit or a word score of at least `2.0` to
  appear, which keeps "frobnicate the widgets" empty.
- **Boosts**: shipped +1.0; local `+min(2, 0.5*log2(1+use_count))`; a local
  row with a `null` intent -1.0.
- **Ties**: shipped first, then `id`.
- **Clear winner (code gate)**: `recipes[0]` carries `code` only if all of
  these hold:
  - `score0 >= 3.0`;
  - `score0 >= 1.5 * score1`, or there is no second row;
  - at least one non-object bag contributed to `score0`.

  Otherwise every row is compact and `recipes_ambiguous: true`, plus a
  `recipes_hint` string.
- **No duplicate body**: if the winner's id equals `results[0].recipe.id`,
  the row stays compact with `code_at: "results[0].recipe"`.
- **Old attachment kept separate**: `find_recipe_for_search`, the old
  single-recipe attachment, keeps its current first-match-in-declaration-order
  behaviour over shipped recipes only, so `results[0].recipe` is
  byte-identical for existing queries (FR-022).
- **Constants**: all thresholds and weights are module constants, tuned only
  against the query battery (FR-061), and the battery test pins them.

**Rationale**: The user's direction is that basic object access is easy to
reproduce through the API search, so recipes earn their place on the task
and on hard-to-find calls. IDF makes "entry"-style words cheap without a
list to maintain. The code bag also lets local recipes, which have no
`match_terms`, match on what they actually do. The code gate stops a vague
query from spending a code body on a coin flip; the assistant picks from the
compact rows with one more call, the same cost as an API lookup. Keeping the
old function separate is the only way to prove FR-022 by construction.

**Alternatives considered**:
- Flat word overlap. This was the first draft; it rejected nothing, and
  "entry" matched about 20 recipes at equal scores.
- A hard-coded list of down-weighted object names. It needs maintenance, and
  it would also down-weight "variant" and "template".
- Always sending code for the top row (the original FR-021). It wastes a
  body on ambiguous queries.
- Embeddings. The spec defers them.
- Pointing the old attachment at the new scorer. It could change which
  recipe gets attached.

## R11. Server instructions

**Decision**: Add an `instructions` string (a module constant
`SERVER_INSTRUCTIONS` in `server/tool_definitions.py`, beside the tool
descriptions it summarizes) and pass it through `build_server(...,
instructions=...)`. `mcp_compat._construct` already forwards kwargs. A test
constructs the server under the installed `mcp` and asserts the instructions
round-trip. The same guidance also goes into the `search_by_capability`,
`find_examples` and `list_recipes` descriptions, so clients that ignore
instructions still see it.

**Rationale**: FR-027 names server instructions, and none exist today. Both
supported `mcp` majors accept `instructions` on `Server`; the dual-support
shim (#83) means this must be tested, not assumed.

**Alternatives considered**: Tool descriptions only (rejected: does not
satisfy FR-027, and instructions are the one place a client reads before
choosing a tool).

## R12. Deprecation signalling

**Decision**: Add a `deprecation` object:
`{"deprecated": "<tool or key>", "replacement": "<new>", "removal":
"tool-responses/2.0"}`. `flextools_list_skeletons` adds it at the top level of
its (old-shape) response. `flextools_find_examples` adds it at the top level
only when `skeletons_from_your_sessions` is emitted. Add the constant
`KEY_DEPRECATION` (with `KEY_RECIPES`, `KEY_RECIPES_COUNT`) to
`response_keys.py`. `docs/TOOL-CONTRACT.md` gets both items in its
deprecation timeline.

**Rationale**: This is the first deprecated *tool* in the repo, so there is
no precedent to copy. The nested-`error` precedent is "emit both, document
the removal version", which this follows.

**Alternatives considered**: Deprecation only in the tool description
(rejected: an assistant reading the response would not see it; Principle IV
asks for the old and new shapes in parallel plus a named removal version).

## R13. Promotion CLI

**Decision**: `src/flextoolsmcp/recipe_cli.py` with `main()` and an argparse
subcommand `promote <local-id> --id <new-id> [--out DIR] [--force]`, exposed
as the console script `flextools-mcp-recipe`. It writes `<new-id>.py` using
`recipe_files.render_draft(...)`: a header prefilled from the local record
(`intent`, `entities`, `requires_write`, `origin: "local:<local-id>"`), with
`match_terms: []` and `notes: "TODO"` so the draft *fails* validation until
a human edits it. It also adds an empty PARAMS stub when the code has none. It
prints `scrub before shipping: <line-no>: <line>` for each hit of the shared
scrub patterns plus the record's `projects`, and exits 0. `--out` defaults to
`~/.flextoolsmcp/recipe-drafts/`; if the target exists it refuses without
`--force`.

**Rationale**: FR-030/031 and US5 scenario 1 (never into the package by
default). The draft is meant to fail validation until a human edits it; that
is the review gate.

**Alternatives considered**: An MCP tool for promotion (rejected: promotion
is a developer action, and the spec keeps shipping behind human review).

## R14. Live verification protocol (Sena 3)

**Decision**: Evidence goes in `specs/unified-recipes/evidence/<recipe-id>.md`,
recording the `op_id`, flexicon version, parameter values used, the
report-line excerpt, and the Sena 3 `.fwdata` mtime and SHA-256 before and
after. This applies to every run, not only live writes, because the parse
worker is known to rewrite `.fwdata` on nominally read-only work. Live writes
use objects prefixed `zzRecipeTest` and are cleaned up in the same session;
the cleanup's own pre/post hash is recorded. Unattended runs MAY perform these
live writes: Sena 3 is the designated test project, excepted from constitution
I's "no unattended destructive writes" (1.1.0). A live write on any other
project stops with `needs-human`. The project path is resolved through
`flextools_list_projects` and the name is asserted to be `Sena 3` before any
run. Every run -- read, dry run, or live write -- goes through
`flextools_run_module`; a round never opens the project directly
(`FLExProject().OpenProject`, `FLExInitialize`) or copies `.fwdata` by hand.
A failing `run_module` is reported as BLOCKED with its error and op_id.

**Rationale**: FR-042..FR-044. The standing rules are that Sena 3 is the test
project and Claude-Swahili is never a target.

**Alternatives considered**: A pytest `requires_flex` suite for recipes
(rejected as the primary evidence: the suite is run with
`-m "not requires_flex"` by rule, and FR-042 asks for recorded runs, not a
skipped test).

## R15. Porting raw-LCM access to flexicon

**Decision**: For each harvested script, use flexicon wherever an
equivalent exists in the 4.11.0 index (confirmed with
`flextools_get_object_api` / `search_by_capability` at port time and cited in
the evidence file). Where no equivalent exists (the #542..#547 gaps, and
`phon_rules` rule internals), keep the raw-LCM form with a
`# flexicon gap: MattGyverLee/flexicon#NNN` comment. The FR-045 gate (R18)
enforces this. It must pass today's
validator with no exemption. Take vernacular text through a small in-recipe
`nfc(s)` helper (`unicodedata.normalize("NFC", s or "")`) and apply it on both
sides of every comparison. Look up write targets by GUID or comparator,
never by bare headword string alone. Where a PARAMS value names an entry, the
recipe must resolve it and refuse on 0 or more than 1 match (the source
scripts crash on a missing comparator).

**Rationale**: FR-051 and FR-053, and the harvest's top failure idioms.
Keeping raw-LCM fallbacks is allowed by the spec's edge case; exemptions are
not (constitution I).

**Alternatives considered**: Wait for the flexicon gaps (rejected: FR-052
allows at least 12 of 16, and the spec says the work does not wait).

## R16. Branch baseline

**Decision**: Before implementation, rebase `feat/unified-recipes` onto
`main` (5cc03f0, release 2.14.0) and copy the current
`specs/unified-recipes/` artifacts from the main checkout into the worktree.
All implementation happens in the worktree.

**Rationale**: The worktree is missing #278/#280/#277/#285 and the 4.11.0
indexes that FR-006 pins. The spec on `main` also has uncommitted edits
newer than the worktree's commit.

**Alternatives considered**: Implement on `main` directly (rejected:
repository practice is feature branches/worktrees and a PR the user merges).

## R17. Deprecated members from the index, not only the curated list

**Decision**: Extend `detect_deprecated_members` so it takes an optional
`api_index`. A member counts as deprecated when it appears in
`curated_deprecations.CURATED_DEPRECATIONS` (as today), **or** when its
flexicon index entry carries a deprecation flag or its description contains
a deprecation marker ("deprecated", "Deprecated:", ".. deprecated::"). Index
hits report the index's own replacement text when there is one.
`recipe_validator` passes the index through. The run-time preflight keeps
its current curated-only behaviour, so this feature does not change
`run_module` refusals.

**Rationale**: The curated list holds one family today, while the 4.11.0
flexicon index has nine methods whose docs mention deprecation. Recipes are
the material the assistant teaches from (Principle VI, prose is product), so
they get the stricter check first.

**Alternatives considered**:
- Pyright `reportDeprecated`. There are no stubs: LCM comes through
  pythonnet, flexicon uses no `@deprecated`, and recipe files are excluded
  from pyright (FR-005).
- Adding the nine methods to the curated list by hand. That drifts with
  every flexicon release.
- Also changing the run-time preflight. That is out of scope and would
  change refusal behaviour for user code.

## R18. Minimal raw LibLCM (`detect_raw_lcm_access`)

**Decision**: Add a validator check, used only by `recipe_validator`, that
walks the recipe's AST and flags these forms of raw access:
- `Call` to a `Name` matching `^I[A-Z]\w+$` (an interface cast);
- `Attribute` whose attr matches `\w+(OA|OS|OC|RA|RS|RC)$`;
- `project.project`, `ServiceLocator`, and `.ClassName` comparisons.

For each flagged line:
1. Look the property up in the **inverted flexicon bridge index**
   (`flexicon_lcm_bridge_v<ver>.json` `by_method[*].properties_accessed`,
   inverted once and cached). Rank candidate wrappers by name: `Get*` /
   `GetAll*` for reads, `Add*` / `Set*` / `Remove*` / `Create*` for writes.
   Drop `Duplicate`, `Delete`, `__init__` and `Copy*` as non-equivalents.
2. If a candidate exists and the line has no `# raw-lcm: <reason>` note, the
   check **fails**. The message names up to 3 wrappers, for example
   "PhoneEnvRC: use AllomorphOperations.GetPhoneEnv / AddPhoneEnv /
   RemovePhoneEnv".
3. If no candidate exists, the line must carry `# flexicon gap: <issue>` or
   `# raw-lcm: <reason>` (on the line or the line above), else the check
   fails.
4. A **count** of flagged lines is compared with the header's
   `raw_lcm_lines`. A higher count fails. A lower count passes but emits a
   "lower raw_lcm_lines to N" note, so the count only ratchets down.

When a flexicon gap fix lands (#542..#547) and the index is regenerated,
rule 2 starts firing for the old fallback. The recipe must then be updated;
that is exactly the release-order behaviour we want (flexicon first, then
the MCP index, then the recipes).

**Rationale**: The user asked for minimal LibLCM, "just to fill gaps". The
bridge index already knows which flexicon methods touch which LCM properties
(checked: `PhoneEnvRC` maps to `AllomorphOperations.GetPhoneEnv`,
`AddPhoneEnv` and `RemovePhoneEnv`; `AffixTemplatesOS` maps to
`MorphRuleOperations.GetAllAffixTemplatesForPOS`), so the check is
index-driven (Principles II and III) with no hand-kept table. The note is a
stated, reviewable reason, not a silent exemption, and it sits on a style
gate. Write-safety and casting checks are untouched (Principle I, "gates
never relax").

**Alternatives considered**:
- Banning raw LCM outright. That is impossible for `phon_rules` rule
  internals and the #542..#547 gaps.
- Comment convention only (the previous plan). Nothing enforces it.
- Using `reverse_mapping_liblcm` `by_liblcm_entity`. It is only class-level
  (entity to Operations class) and says nothing about which property is
  wrapped.

**Cost**: The Phase F ports get heavier, because most source scripts are
raw-LCM-first. This is accepted: it is the point of the gate.
