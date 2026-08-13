# DOCS-PENDING -- inheritance-resolution (issues #85 / #86)

**SUPERSEDED by commit `f930908`** ("docs: complete the #86
inheritance-resolution contract docs (CP4)", cycle 6). Every draft staged
below has landed: the `docs/TOOL-CONTRACT.md` "Inherited member fields"
section (§1, including the `total_methods_including_inherited` row added in
the cycle-5 precision pass), the `CHANGELOG.md` `Added`/`Fixed` entries (§2),
and the new `docs/LIBLCM_EXTRACTION_SEMANTICS.md` plus the `See also`
cross-link in `docs/LIBLCM_CONTEXTUAL_ANALYSIS.md` (§3). This file is
retained only as the drafting trail -- do not paste from it again.

**Original status (historical):** drafted, not yet applied (CP4, gated on the
`workspace_notice` crew landing -- see `SPEC.md` §4 concurrency table).
**Source of truth for the decisions below:** `SPEC.md` DEC-3 (§2), CP4 (§5);
`reviews/cycle1-author.md` §5.

Do not paste any of this until the other crew's `CHANGELOG.md` /
`docs/TOOL-CONTRACT.md` hunks have landed (or been abandoned) and this repo's
`git status` shows those two files clean against `main`. Re-read both files
again at paste time -- their content will have moved once the other crew's
edit lands, so the "insert after X / before Y" anchors below are *content*
anchors (headings, sentences), not line numbers, except where noted as
already-landed and stable.

---

## 1. `docs/TOOL-CONTRACT.md` -- new section

**Where it goes:** as its own `##` section, inserted **after** the
`## RunModuleSuccess envelope (run_module tool)` section ends and **before**
the `## \`diagnostic_report\` advisory block` section begins. At the time this
was drafted that was between line 178 and line 181 -- verify against current
content, not the line numbers, since the other crew's hunks at line 27 and
lines 277-325 are in the same file and may have shifted things below them.

**Why this placement:** the existing document already groups "tool-specific
optional response fields" (RunModuleSuccess's `auto_discovered` /
`_inline_discovery` / `discovery_note`) separately from "cross-cutting
advisory blocks" (`diagnostic_report`, `update_notice`, `workspace_notice`,
all of which attach to *any* success envelope). `inherited_from` /
`total_properties_including_inherited` are tool-specific data fields on
`get_object_api` and `resolve_property` responses, not a cross-cutting
advisory -- so they belong with the former group, immediately before the
advisory-block run begins.

**Wording note:** the other crew's `workspace_notice` section (current lines
277-325) is itself the newest precedent for "additive field, no version
bump." Word this section so the two land as one continuous policy statement
rather than two independent claims -- the paste-ready text below explicitly
chains to `update_notice` **and** `workspace_notice`, not just to the older
`diagnostic_report` precedent lex-author cited in cycle 1.

```markdown
## Inherited member fields (`get_object_api`, `resolve_property`)

`get_object_api` and `resolve_property` responses may carry two additional
optional fields when the target entity has ancestors in its `interfaces`
closure (issue #86, inheritance-resolution CP2). Like `update_notice` and
`workspace_notice`, these are **additive optional fields** -- adding them did
**not** bump the contract version, continuing the same additive-optional
pattern already established by `auto_discovered`, `diagnostic_report`,
`update_notice`, and `workspace_notice`.

| Key | Location | Type | Description |
|---|---|---|---|
| `inherited_from` | per property/method item | string or absent | Name of the ancestor interface the member was merged in from. Absent (not `null`) on members the entity declares itself. Own members always shadow an ancestor member of the same name ("child wins" -- no entity ever emits two entries for the same name). |
| `total_properties_including_inherited` | top-level | integer | Combined count of own-declared **and** merged-inherited properties. `total_properties` is unchanged and stays byte-identical to today's own-only count; this is a new, separate key, not a redefinition. |

**Scope (issue #86, CP2).** Only `I*` interface entities receive the merge.
Class-side ancestor merging is **not** covered by this fields -- class
hierarchies have real semantic overrides (a subclass narrowing
`can_write: true` to `false`, for example) that need a policy decision before
they can be merged safely, and that policy is tracked separately from this
change.

**`summary_only` treatment.** `inherited_from` survives `summary_only`
truncation the same way `casting_notes` does -- it is cheap (one short string
per row) and lets a caller distinguish own-vs-inherited members with a single
`.get("inherited_from")` check without requesting the full (non-summary)
response.

Built by `collect_inherited_members()`, merged into the `properties` /
`methods` candidate lists in `paginate_entity()` (`api.py:420`) before the
existing pagination and `summary_only` logic runs, so filtering, totals,
slicing, and the casting-index join stay consistent with the merged view
rather than the own-only one.
```

---

## 2. `CHANGELOG.md` -- new `[Unreleased]` entry

**Where it goes:** a new `###` entry inside the existing `## [Unreleased]`
block. Insert it **below** the current `### Added: \`workspace_notice\` --
warn when the workspace is a source checkout` entry's bullet list, and
**above** the first dated release heading (currently `## [2.9.1] -
2026-08-10`). Use the heading text and content as content anchors, not a line
number -- the other crew's entry directly above this insertion point is
in-flight and will shift.

**Heading discipline (per SPEC.md DEC-3 / cycle1-author §3):** this is a
normal `Added` entry. Do **not** file it under a `### Tool contract (...)`
heading -- that heading is reserved for removals and renames to the
`tool-responses` contract (see the `### Tool contract (issue #54)` entry
under `## [2.4.0]` for the precedent: it covers the `tool-responses/1.0`
contract's *introduction*, a genuinely versioned event, not a routine
additive field).

```markdown
### Added: `inherited_from` / `total_properties_including_inherited` -- inheritance-aware `get_object_api` (#86)

`get_object_api` previously only listed a type's own (`DeclaredOnly`)
properties and methods -- ancestor-declared members like `IFsClosedValue`'s
`FeatureRA` (declared on a parent interface) were invisible, forcing users
onto fragile workarounds (e.g. parsing `LongName` strings, which breaks on
unordered `ILcmOwningCollection` positional assumptions and on space-bearing
values like Swahili `"NC 4"` / `"NC 1a"`).

- **New `collect_inherited_members()` helper** -- memoized, cycle-guarded walk
  of an entity's `interfaces` closure (already the full transitive closure
  per `liblcm_extractor.py`'s use of .NET `GetInterfaces()`; no recursive walk
  needed for interface ancestors). Merged into `paginate_entity()`'s
  candidate list *before* pagination, filtering, and `summary_only`
  truncation, so all three stay consistent with the merged view.
- **`inherited_from`** tags each merged property/method with its declaring
  ancestor. Own members always shadow an ancestor member of the same name.
- **`total_properties_including_inherited`** added at the top level.
  `total_properties` is unchanged (byte-identical, own-only count).
- **Scoped to interface entities only** (`I*`) this round -- interface
  merging is collision-free (0 interface-side name collisions found across
  the index); class-side merging needs an override-semantics policy and is
  tracked separately.
- Additive optional fields -- **no contract-version bump**, same pattern as
  `update_notice` and `workspace_notice`. Documented in
  [`docs/TOOL-CONTRACT.md`](docs/TOOL-CONTRACT.md#inherited-member-fields-get_object_api-resolve_property).
- `resolve_property` gained a matching ancestor-aware fallback so a property
  found via `get_object_api`'s merged view also resolves via
  `resolve_property` for the same concrete type -- verified by a
  cross-tool consistency test sampled against `get_object_api`,
  `resolve_property`, and `validators._interface_member_names`.
- Canonical case: `IFsClosedValue` merges 2 own properties to 31 total, with
  `FeatureRA` now visible and tagged `inherited_from`.
```

(Adjust the anchor slug in the `docs/TOOL-CONTRACT.md` link once that
section's exact heading text is pasted in, if it differs from
`## Inherited member fields (\`get_object_api\`, \`resolve_property\`)`.)

**Also insert this separate `### Fixed` entry** (this repo's convention keeps
`Fixed` and `Added` as distinct headings rather than mixing bullet types
under one -- see the `## [2.9.1]` block's separate `### Fixed:` entries for
precedent). Placement: same insertion point as the `Added` entry above
(below the `workspace_notice` entry's bullets, above the first dated release
heading) -- order the two relative to each other however CP4 lands them;
content anchors, not line numbers.

```markdown
### Fixed: `get_object_api` pagination under-reported remaining properties (#86)

`has_more` / `next_offset` were computed from `total_methods` alone, so
`properties` had no pagination signal of its own -- a property-heavy entity
could report `has_more: false` while properties beyond the current page were
still unreachable. `IFsClosedValue` (14 combined methods vs 31 combined
properties) flips this after page 3: the method-only signal goes `False`
while 16 properties remain unpaged.

- **`has_more` is now `methods_has_more OR properties_has_more`**, derived
  from both dimensions instead of methods alone.
- Widened to **all** entities, not only the `I*`-interface entities the
  inheritance merge (see `Added` entry above, #86) targets -- the underlying
  under-reporting bug predates and is independent of that merge, and existed
  for every entity's properties. See `SPEC.md` DEC-7 for the scoping
  rationale and the verification matrix (method-heavy merged, property-heavy
  merged, and non-merged non-interface cases).
```

---

## 3. `docs/LIBLCM_CONTEXTUAL_ANALYSIS.md` -- extraction asymmetry note

**Flag before pasting:** read the file at paste time. As of this drafting,
`docs/LIBLCM_CONTEXTUAL_ANALYSIS.md` (283 lines) is entirely about the
*write-protection* contextual analysis -- `certify_script_readonly()`,
`find_liblcm_mutations()`, `find_protected_ranges()` -- i.e. "contextual" here
means "guarded by `modifyEnabled`/`writeEnabled` context," not "reflection
extraction context." It contains **zero** existing references to
`interfaces`, `base_classes`, `GetInterfaces`, `BaseType`, or `DeclaredOnly`.
cycle1-author §5 hedged this ("if it documents `interfaces`/`base_classes`
semantics") -- it does not. There is no existing doc that documents
extraction semantics in depth; the closest incidental mention is a
`GetProperties(BindingFlags...DeclaredOnly)` code excerpt in
`docs/STABILITY-SURVEY-FLEXTOOLSMCP.md` (not a semantics writeup).

**Ruling (lex-lead, cycle 3): trimmed option (b). Still PENDING -- do not
paste into any `docs/` file this cycle.**

Create a **new** doc, `docs/LIBLCM_EXTRACTION_SEMANTICS.md`, holding the
extraction-asymmetry block exactly as drafted below, plus a single `See also`
cross-link line added to `docs/LIBLCM_CONTEXTUAL_ANALYSIS.md` pointing at it.
Do **not** bootstrap `docs/MANIFEST.md` -- that was the costly part of the
original (b) option and is explicitly out of scope for this cycle; it stays
a noted follow-up (see "Open follow-ups" below).

**Rationale:** `LIBLCM_CONTEXTUAL_ANALYSIS.md` is entirely about
write-protection and contains **zero** references to `interfaces`,
`base_classes`, `GetInterfaces`, `BaseType`, or `DeclaredOnly` -- as this
cycle's own draft above already established. Burying reflection-extraction
semantics inside a write-protection doc reproduces the exact discoverability
failure that caused issue #86 (a real capability invisible because it lived
in the wrong document). A same-named-sounding-but-wrong-topic doc is worse
than a slightly heavier docs tree; a one-line cross-link keeps the two
discoverable from each other without merging them.

The paste-ready markdown block itself is unchanged from the original draft
(see below) -- only its destination file changes, from a section appended to
`LIBLCM_CONTEXTUAL_ANALYSIS.md` to the body of the new standalone doc.

**Where it goes:**
- New file `docs/LIBLCM_EXTRACTION_SEMANTICS.md`: the paste-ready block below
  becomes the entire doc body (adjust the `##` heading to `#` top-level if
  this is the file's only section, per this repo's existing single-topic doc
  convention -- verify against a comparable doc at paste time).
- `docs/LIBLCM_CONTEXTUAL_ANALYSIS.md`: add one `See also` line pointing at
  the new doc, placed in its existing `## See Also` section (currently the
  file's last section) -- verify current heading text and existing entries'
  formatting at paste time.

```markdown
## Extraction asymmetry: `interfaces` vs. `base_classes` (inheritance-resolution, issues #85/#86)

`liblcm_extractor.py`'s type extraction does **not** treat interface and
class ancestry the same way. Implementers walking an entity's ancestors for
any purpose (inheritance merging, casting, navigation) will hit this:

| Field | Extractor call | Depth | Notes |
|---|---|---|---|
| `interfaces` | `t.GetInterfaces()` (`liblcm_extractor.py:698`) | **Full transitive closure** -- .NET returns every interface the type implements, directly or via an ancestor. | One pass over `entity["interfaces"]` is sufficient; no recursive walk needed to find all interface ancestors. |
| `base_classes` | `t.BaseType` (`liblcm_extractor.py:695-696`) | **One level only** -- the immediate parent class, not the full class chain. | A class-inheritance chain more than one level deep requires an actual recursive walk; treating `base_classes` as already-flattened will silently miss grandparent-and-higher members. |

Both `properties` and `methods` are extracted with
`BindingFlags.DeclaredOnly` (`liblcm_extractor.py:656`) -- **own-declared
members only**. An entity's `properties`/`methods` lists never include
inherited members; any consumer that wants ancestor members (own or merged)
must read them from the ancestor entity's own record and combine explicitly.

This asymmetry is why an interface-ancestor walk is a single flat pass over
`interfaces` (cheap, cycle-free by construction) while a class-ancestor walk
needs a cycle-guarded loop following `base_classes` until it terminates at
`None`/`Object`.
```

---

## Open follow-ups for CP4

- Confirm the `docs/TOOL-CONTRACT.md` insertion point once the
  `workspace_notice` crew's hunks are merged -- content anchors given above,
  not line numbers.
- §3 is ruled (trimmed option (b), cycle 3): new `docs/LIBLCM_EXTRACTION_SEMANTICS.md`
  doc plus a `See also` line in `docs/LIBLCM_CONTEXTUAL_ANALYSIS.md`. Still
  PENDING paste at CP4.
- No `docs/MANIFEST.md` exists in this repo yet; explicitly out of scope for
  this cycle (see §3 ruling), but the LIBLCM_CONTEXTUAL_ANALYSIS naming
  collision found while drafting §3 remains a concrete argument for
  bootstrapping one in a future cycle.
