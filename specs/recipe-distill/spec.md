# Feature Specification: Recipe distill (quality-gate the local recipe journal)

**Feature Branch**: `feat/unified-recipes` (worktree `C:\Github\FlexToolsMCP-recipes`); may move to its own branch at plan time

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "Claude told me that most of the skeletons produced before this rewrite were noise. How can we make sure that we get high-quality atomic recipes (we may only want to keep some novel parts of the recipe)." Scope agreed in conversation: search hygiene, shape fingerprint with PARAMS proposal, explainable candidate scoring, a `distill` step, and a one-time triage of the existing backlog.

**Tier**: Full - per `.specify/memory/constitution.md` v1.0.0. The change
crosses a published contract (`flextools_search_by_capability` recipe results
change by default; `flextools_list_recipes` gains keys; the
`flextools-mcp-recipe` console script gains a subcommand). `plan.md` and
`tasks.md` follow this spec.

**Touches a write path?**: No - nothing in this feature mutates a FieldWorks
project. It reads and rewrites only `~/.flextoolsmcp/recipes.jsonl` and writes
drafts under `~/.flextoolsmcp/recipe-drafts/`. A *distilled* write recipe that
is later shipped inherits the existing live-verification obligation of
`specs/unified-recipes/spec.md` (FR-040..FR-043, Sena 3 only); this feature
does not waive or re-implement it.

**Parent**: `specs/unified-recipes/spec.md` (local capture, ranked search,
`promote`, shipped validator, Sena 3 verification protocol). Reference doc:
`docs/RECIPES.md`.

---

## 1. Context: the journal is not a library

Unified-recipes made capture clean: one local recipe per successful
`run_module` that carries `user_intent` and at least 4 real lines, deduplicated
by a comment/whitespace-insensitive fingerprint. It did not make captures
*good*. Measured on the developer's store (2026-09-28):

- 183 local rows, **all** migrated from legacy skeletons, **all** `use_count` 1.
- 0 rows carry PARAMS; 0 rows are marked `requires_write`.
- Real-line length: 25th percentile 9, median 17, 90th percentile 55.
- Intents are dominated by one-off investigations with hard-coded data
  ("Check whether the morphemes of 'akamwita' exist in the lexicon"),
  test/proof runs ("SC-005 idempotency live proof: restore Target...",
  "monkeypatch _apply_glosses to capture call count"), and single-session
  dumps.

Every one of these rows competes in `flextools_search_by_capability` today;
local rows get a small use-count boost and no quality filter. A single run
cannot tell whether code is a reusable recipe. What signals "recipe" is
**repeated shape with varying values**, and what is worth keeping from a long
investigation is usually **one novel fragment**, not the whole script.

**Principle**: capture stays a dumb, cheap, lossless journal. Quality gating
happens between capture and promotion, with a human (or the assistant acting
for one) making the final keep/cut judgment.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Noise never outranks real recipes in search (Priority: P1)

An assistant asks `flextools_search_by_capability` for "list unparsed
wordforms". Today a migrated one-off probe about a single Swahili word can
appear beside, or instead of, the shipped recipe. After this feature, local
rows that have not earned visibility are left out of capability-search recipe
results by default, while every local row stays browsable through
`flextools_list_recipes(source="local")`.

**Why this priority**: It is the cheapest change and removes the harm now.
Every search already pays for the noise.

**Independent Test**: Load the measured 183-row store (or a fixture copy of
it) and run a fixed query set; no migrated or low-scoring local row appears in
capability-search recipe results, and `list_recipes(source="local")` still
returns all 183.

**Acceptance Scenarios**:

1. **Given** a store where every local row is migrated, **When** any capability
   search runs, **Then** its recipe results contain only shipped recipes and
   the response states how many local rows were withheld and how to see them.
2. **Given** a non-migrated local recipe that has recurred (see FR-004),
   **When** a matching query runs, **Then** it is eligible to appear in search
   results as today.
3. **Given** any store, **When** `flextools_list_recipes(source="local")` runs,
   **Then** it returns withheld rows too, each labeled with its visibility and
   the reason.

---

### User Story 2 - Runs that differ only in values are recognized as one recipe (Priority: P2)

The user checks morphemes for "akamwita" on Monday and for "kuita" on
Thursday. Today these are two unrelated rows. After this feature both carry the
same *shape* fingerprint, form one cluster, and the values that differ between
them ("akamwita" / "kuita") are proposed as a parameter.

**Why this priority**: Recurrence is the strongest evidence that code is a
recipe, and cluster variation is what turns hard-coded one-offs into
parameterized, reusable recipes (0 of 183 rows have PARAMS today).

**Independent Test**: Capture two scripts identical except for one string
literal and one number literal; both rows share a shape fingerprint, the
cluster reports size 2, and the proposal names exactly the two varying
literals, with their observed values.

**Acceptance Scenarios**:

1. **Given** two captured scripts that differ only in literal values, **When**
   they are stored, **Then** their exact fingerprints differ, their shape
   fingerprints match, and they are reported as one cluster.
2. **Given** two scripts that differ in any identifier, call, or control
   structure, **When** they are stored, **Then** their shape fingerprints
   differ.
3. **Given** a cluster, **When** its PARAMS proposal is requested, **Then**
   each literal position whose value varies across members is proposed as a
   parameter with an UPPER_CASE name suggestion, its observed values, and a
   default taken from the most recent member; literals identical across all
   members are not proposed.
4. **Given** a single-member cluster, **When** a PARAMS proposal is requested,
   **Then** hard-coded data literals (FR-009) are proposed as parameters
   instead, flagged as "single observation".

---

### User Story 3 - Each local recipe has an explainable quality score (Priority: P2)

The user, or the assistant on their behalf, asks "which of my local recipes
are worth keeping?" and gets a ranked list. Each row shows a score and the
signals behind it ("+ recurs in 3 sessions", "+ uses 2 raw-LibLCM paths no
shipped recipe covers", "- monkeypatches a private member", "- 55 real
lines"), so nobody has to trust an opaque number.

**Why this priority**: The score drives search visibility (US1), backlog
triage (US5) and the order in which distillation is worth doing (US4).

**Independent Test**: Score a fixture set with one row per signal; each row's
signal list contains exactly the expected signal, and rows sort in the
expected order.

**Acceptance Scenarios**:

1. **Given** any local recipe, **When** it is scored, **Then** the result
   carries a numeric score, a candidacy verdict (candidate / not a candidate),
   and a list of named signals, each with its sign, weight, and the evidence
   that triggered it (line numbers or values).
2. **Given** the same store and the same shipped library, **When** scoring runs
   twice, **Then** scores, verdicts and signal lists are identical.
3. **Given** a recipe whose intent or code matches test/proof smells (FR-010),
   **When** it is scored, **Then** its verdict is "not a candidate" regardless
   of other signals, and the blocking signal is named.

---

### User Story 4 - Distill one atomic recipe out of a long investigation (Priority: P3)

A 55-line investigation contains one genuinely new fragment: how to walk from
an allomorph to its environment through raw LibLCM because flexicon has no
wrapper. The user runs `flextools-mcp-recipe distill <local-id>`, sees the
script with novel lines marked, selects that fragment, and gets a
self-contained, parameterized draft in `~/.flextoolsmcp/recipe-drafts/` that
then goes through the existing shipped validator and Sena 3 verification. The
same investigation can be distilled again with a different selection to yield
a second atomic recipe.

**Why this priority**: This is where high-quality atomic recipes come from,
but it depends on the novelty, clustering and scoring above.

**Independent Test**: Distill a fixture script with `--lines` covering one
fragment that uses a variable assigned earlier; the draft contains the
fragment, the earlier assignment it depends on, the needed imports, and a
PARAMS block; it parses; running the shipped validator on it reports only the
header TODOs promotion already leaves for a human.

**Acceptance Scenarios**:

1. **Given** a local id and no `--lines`, **When** `distill` runs, **Then** it
   prints the numbered script with novel lines marked and the reason for each
   mark, prints the PARAMS proposal, and writes nothing.
2. **Given** a local id, `--lines A-B`, and `--id <new-id>`, **When** `distill`
   runs, **Then** it writes one draft containing lines A-B plus exactly the
   earlier lines those lines need to run (definitions of names they use), the
   imports those need, and a PARAMS block from the proposal.
3. **Given** a selection that uses a name no earlier line defines and the
   runner does not inject, **When** `distill` runs, **Then** it refuses with a
   stable error naming the unresolved names and the lines that would fix it,
   and writes nothing.
4. **Given** any successful distill, **When** it completes, **Then** the draft
   is outside the installed package, carries the same prefilled header and
   "scrub before shipping" warnings as `promote`, and its `origin` value
   records which local id and line range it came from.
5. **Given** a draft whose selection mutates data, **When** it is written,
   **Then** it is marked `requires_write: true` and its writes sit inside an
   `if modifyAllowed:` guard, or the draft is refused with the lines that need
   the guard.

---

### User Story 5 - Triage the existing 183-row backlog once (Priority: P3)

The user runs one triage command over the current store and gets a short,
readable report: which rows were excluded as test/proof runs, how the rest
cluster, and a top-15 list ranked by novelty with each row's signals, ready to
distill. Nothing is deleted; everything not chosen stays in the store, hidden
from search.

**Why this priority**: It recovers the value buried in the backlog, but only
after the scoring (US3) and distill (US4) tools exist.

**Independent Test**: Run triage against a fixture copy of the store; the
report lists every row exactly once, in one of: excluded (with reason),
clustered, or top-N; and the store's contents, apart from computed fields, are
unchanged afterwards.

**Acceptance Scenarios**:

1. **Given** the store, **When** triage runs, **Then** it produces a report
   with counts per disposition and the top-N (default 15) candidates, each
   with id, intent, real-line count, cluster size, score, and signals.
2. **Given** triage has run, **When** the store is inspected, **Then** no row
   was deleted and no row's code, intent, or history changed.
3. **Given** the top-N list, **When** the assistant reads it through the MCP,
   **Then** it can fetch any listed row's code and novelty marks without the
   CLI.

---

### Edge Cases

- **Empty or missing store**: search, scoring, list, triage and distill all
  succeed with empty results and a one-line explanation; nothing is created.
- **Malformed rows**: skipped with the same tolerance as today's reader; never
  fail scoring or triage.
- **Code that does not parse** (possible in migrated rows): gets no shape
  fingerprint, a named "does not parse" signal, and is not a candidate.
- **A cluster mixing projects**: recurrence counts distinct projects as a
  positive signal; project names are never proposed as PARAMS defaults and are
  scrubbed from drafts as `promote` already does.
- **A literal that is really a constant** (for example a writing-system tag
  used identically in every run): not proposed as a parameter, because it
  does not vary.
- **Shipped library changes** (a recipe is added that covers a local row's
  novel terms): that row's novelty signal drops on the next scoring; scores
  are always computed against the current shipped library, never cached
  across versions.
- **Draft id collides** with a shipped id or an existing draft: same exit
  codes and `--force` semantics as `promote`.
- **Selection spans a partial statement** (for example half of a `for` loop):
  the selection is widened to whole statements and the widening is reported.
- **Store over the 2,000-row cap**: the existing eviction rule is unchanged;
  shape fingerprints and scores are recomputed, not preserved, for evicted
  rows.
- **Local recipe used once but written by the user this session**: capture
  stays unchanged, so it is stored; it stays hidden from search until it earns
  visibility, and is always reachable by id.

---

## Requirements *(mandatory)*

### Functional Requirements

**Capture stays unchanged**

- **FR-001**: Local capture MUST keep its current trigger, thresholds and
  never-raise behavior (unified-recipes). This feature MUST NOT make capture
  reject, truncate or rewrite code on quality grounds.

**Search hygiene (US1)**

- **FR-002**: `flextools_search_by_capability` MUST, by default, return only
  shipped recipes and *visible* local recipes in its recipe results.
- **FR-003**: Every migrated local row MUST be withheld from default
  capability search until it recurs after migration (FR-004).
- **FR-004**: A non-migrated local recipe MUST become visible when it is a
  candidate (FR-011) **and** either its `use_count` is at least 2 or its shape
  cluster has at least 2 members. Visibility MUST be recomputed on every load;
  it is derived, never stored as a user-editable flag.
- **FR-005**: When local rows are withheld, the search response MUST say how
  many were withheld and name `flextools_list_recipes(source="local")` as the
  way to see them. The addition MUST be append-only within the current
  contract version.
- **FR-006**: `flextools_list_recipes` MUST continue to return every local row
  for `source="local"` and `source="all"`, adding to each local row its
  visibility, score, candidacy verdict, and shape-cluster size. Existing keys
  and ordering rules MUST NOT change.
- **FR-007**: Fetching a local recipe by `recipe_id` MUST work regardless of
  visibility.

**Shape fingerprint and PARAMS proposal (US2)**

- **FR-008**: Each local recipe MUST have a shape fingerprint computed from the
  same normalization as the exact fingerprint, with every string and number
  literal replaced by a type-preserving placeholder. Identifiers, attribute
  names, calls and control flow MUST remain significant. Recipes sharing a
  shape fingerprint form a cluster.
- **FR-009**: The system MUST produce a PARAMS proposal for any local recipe:
  - For a cluster of 2 or more: each literal position whose value differs
    across members, with a suggested UPPER_CASE name derived from context (the
    variable it is assigned to, or the call argument it fills), its observed
    values, and the most recent member's value as default.
  - For a single-member cluster: literals that look like hard-coded data
    (object forms or glosses, GUIDs, project names, `zzRecipeTest`-prefixed
    names, numeric limits), marked "single observation".
  - The proposal MUST use the existing PARAMS block convention
    (`# --- PARAMS ---` / `# --- END PARAMS ---`) and MUST NOT evaluate any
    literal.

**Candidate scoring (US3)**

- **FR-010**: Scoring MUST be deterministic and computed only from the recipe,
  its cluster, the operations log it links to by `op_id`, and the current
  shipped recipe library and API index. It MUST NOT call a language model or
  any network service. Signals:
  - **Recurrence (+)**: cluster size; distinct sessions (from the operations
    log via `op_ids`); distinct projects; `use_count`.
  - **Novelty (+)**: member and function names in the code that no shipped
    recipe uses; raw-LibLCM accesses that have no flexicon wrapper, counted
    as "flexicon gap" paths. Both MUST come from the shipped validator's own
    raw-LibLCM detection and its flexicon bridge index, so novelty and the
    shipped gate never disagree about what counts as a gap.
  - **Atomicity (+/-)**: real-line count inside the atomic band (default 4-25)
    is positive; each 10 lines above it is negative; touching more than one
    object family (per the recipe's entities) is negative.
  - **Hard-coded data (-)**: GUID literals, Windows user paths, project names,
    `zzRecipeTest` names, literal object forms. "Literal object form" is a
    new heuristic; the plan MUST define it precisely and test it against
    short strings that are legitimate parameters (mode flags, writing-system
    tags, filter words), which MUST NOT be penalized.
  - **Test/proof smell (blocking)**: assigning to attributes of imported
    modules or objects (monkeypatching); calling or assigning `_`-prefixed
    private members; restore/backup-project operations; intents containing
    proof, idempotency, regression, trace, or a spec success-criterion id
    (`SC-###`, `FR-###`, `T###`).
  - **Output hygiene (-)**: `print()`; reporting inside a loop with no filter
    or limit.
- **FR-011**: A recipe is a *candidate* when it parses, has no blocking signal,
  and its score is at or above a documented threshold. The weights, band and
  threshold MUST live in one place and be reported in the scoring output so a
  reader can reproduce any score by hand.
- **FR-012**: Each score MUST be returned with its signal list: signal name,
  sign, weight, and evidence (line numbers, literal values, or counts).

**Assistant surface (US3, US5)**

- **FR-013**: The MCP MUST expose, read-only, a ranked candidate listing: local
  recipes ordered by score, filterable to candidates only, each with score,
  verdict, signals, cluster size and PARAMS proposal, without code; and, for a
  single id, the numbered code with novelty marks. This MAY be new filters on
  `flextools_list_recipes` rather than a new tool; if a new tool is added,
  USAGE.md MUST be updated in the same change.
- **FR-014**: The MCP surface MUST NOT write drafts, modify the store, or
  promote. Writing a draft is a CLI action taken by or for a human.

**Distill (US4)**

- **FR-015**: `flextools-mcp-recipe distill <local-id>` with no selection MUST
  print the numbered code with novel lines marked (and why), the PARAMS
  proposal, and the score and signals, and MUST write nothing.
- **FR-016**: `distill <local-id> --lines A-B --id <new-id> [--out DIR]
  [--force]` MUST write one draft containing: the selected lines, widened to
  whole statements; exactly the earlier top-level statements needed to define
  names the selection uses (transitively), excluding every name the
  `run_module` bare-snippet runner injects (today `project`, `report`,
  `modifyAllowed`, `write_enabled`, `is_empty_multistring`,
  `FLEX_EMPTY_PLACEHOLDER`, `find_writing_system`, `list_writing_systems`).
  That set MUST come from the same source the runner builds its namespace
  from, not a hand-copied list, so the two cannot drift; the imports those
  lines need; and a PARAMS block built from the proposal, with the literals
  replaced by the parameter names.
- **FR-017**: `--lines` MAY be repeated to join several non-contiguous ranges
  into one draft; each distill invocation writes at most one draft.
- **FR-018**: If the selection needs a name nothing defines, distill MUST
  refuse with a stable exit code and a message naming each unresolved name and
  the line that defines it (if any), and MUST write nothing.
- **FR-019**: Drafts MUST reuse `promote`'s header prefill, `match_terms: []`
  and `notes: "TODO"` gate, scrub warnings, default directory
  (`~/.flextoolsmcp/recipe-drafts/`), id validation and exit codes, and MUST
  record provenance (local id and line ranges) in the existing `origin`
  header value, so the shipped file format is unchanged. `origin` renders as
  `local:<id>` today; the plan MUST fix one extended plain-string form for
  line ranges (for example `local:<id>:L10-25`).
  Drafts MUST NEVER be written into the installed package.
- **FR-020**: A draft whose code mutates data MUST be `requires_write: true`
  with every write inside an `if modifyAllowed:` guard; if the selected lines
  mutate outside a guard, distill MUST refuse and name the lines.

**Backlog triage (US5)**

- **FR-021**: `flextools-mcp-recipe triage [--top N]` (default N = 15) MUST
  produce a report that places every local row in exactly one disposition:
  excluded (with the blocking or failing signal), clustered (member of a
  cluster that has a better-ranked representative), or ranked; and MUST list
  the top N ranked rows by score, novelty breaking ties.
- **FR-022**: Triage MUST NOT delete rows or change any row's code, intent,
  history or counters. Computed fields (shape fingerprint, score) MAY be
  persisted as a cache but MUST be recomputable from scratch.
- **FR-023**: The triage report MUST be plain ASCII on the console and MAY also
  be written as a file next to the drafts directory.

**Docs and contract**

- **FR-024**: `docs/RECIPES.md` MUST document visibility, shape fingerprints,
  PARAMS proposals, the scoring signals with their weights, `distill` and
  `triage`.
- **FR-025**: `docs/RECIPES.md` MUST be corrected to match capture as
  implemented: a local recipe's `requires_write` is true whenever the captured
  script is mutating, including dry runs with `write_enabled=False`.
- **FR-026**: New response keys MUST be recorded per `docs/TOOL-CONTRACT.md`
  and the CHANGELOG under `[Unreleased]`; golden fixtures MUST be regenerated
  for changed payloads.

### Key Entities

- **Local recipe**: an existing journal row (unified-recipes). Gains derived
  attributes: shape fingerprint, visibility, score, verdict, signals.
- **Shape cluster**: the set of local recipes sharing a shape fingerprint.
  Attributes: size, distinct sessions, distinct projects, varying literal
  positions with observed values.
- **Signal**: one named, signed, weighted piece of scoring evidence with the
  lines or values that triggered it.
- **PARAMS proposal**: an ordered list of proposed parameters (name, default,
  observed values, origin: cluster variation or single observation), in the
  existing PARAMS block convention.
- **Novelty mark**: a line-level annotation saying why a line is novel
  (member no shipped recipe uses; raw-LibLCM path with no flexicon wrapper).
- **Distilled draft**: a promotion draft whose `origin` value records the
  local id and line ranges; otherwise identical to a `promote` draft.
- **Triage report**: per-row dispositions plus the ranked top N.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Against the measured 183-row store, 0 local rows appear in
  capability-search recipe results for a fixed set of at least 20
  representative queries, and all 183 remain listable.
- **SC-002**: Two scripts that differ only in literal values always land in the
  same cluster, and two that differ in any identifier or call never do, across
  a fixture set of at least 20 pairs.
- **SC-003**: Every row in the 183-row store receives a score with at least one
  named signal, and scoring the whole store completes in under 5 seconds on
  the developer's machine.
- **SC-004**: The triage top 15 contains 0 rows whose intent or code matches a
  test/proof smell, and a human can review all 15 in under 30 minutes using
  only the report and the per-row novelty view.
- **SC-005**: From the backlog, at least 3 atomic recipes (each 25 real lines
  or fewer, with a PARAMS block) are distilled and pass
  `validate_recipe(shipped=True)` once their header TODOs are filled, and pass
  the Sena 3 verification protocol of unified-recipes.
- **SC-006**: Every distill draft parses and runs to completion unchanged in a
  dry run (`modifyAllowed=False`) on Sena 3, or distill refused it with the
  unresolved names; no draft ever fails with a NameError.
- **SC-007**: Capture behavior is unchanged: every existing unified-recipes
  capture test passes without modification.

---

## Assumptions

- The measured store is representative of what other users' stores look like
  after migration; thresholds are tuned on it and documented, not hard-coded
  per user.
- Visibility rule defaults: migrated rows hidden until they recur after
  migration; non-migrated rows visible once they are candidates and have
  recurred (use_count 2+ or cluster 2+). A candidate used once stays hidden
  from search but is always reachable by id and in listings.
- The ranked-candidate listing extends `flextools_list_recipes` (new optional
  filters and keys) rather than adding a tool, unless planning finds the
  existing tool's contract cannot absorb it cleanly.
- Distill is CLI-only; the assistant proposes a selection and the human (or the
  assistant with the human's go-ahead) runs the command. No draft is written
  from the MCP.
- "Novel" is judged against the shipped library and the API index only, not
  against the user's other local recipes.
- The operations log is available for session counts; when it is missing,
  recurrence falls back to `use_count` and cluster size, and the signal says so.
- Dependency closure for distill is static and top-level only: it follows names
  assigned or defined by earlier top-level statements and does not attempt to
  slice inside functions or across dynamic attribute access.
- Out of scope: language-model calls inside the server; automatic promotion
  without human review; changes to the shipped recipe file format; deleting
  local rows.
