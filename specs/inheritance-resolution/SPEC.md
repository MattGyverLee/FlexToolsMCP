# SPEC — Inheritance Resolution & Navigation Path Repair (issues #85 / #86)

**Feature:** `inheritance-resolution`
**Status:** in_progress — CP1 partially landed, CP2 designed
**Last updated:** 2026-08-12 (cycle 1 synthesis)
**Cycle-1 evidence:** `specs/inheritance-resolution/reviews/cycle1-{explore,programmer,domain,author}.md`

---

## 1. Problem statement

Three defects, discovered as a chain. Only the first was known when work started.

| # | Defect | Site | Status |
|---|--------|------|--------|
| **D1** | `handle_get_navigation_path` typed `args` as a Pydantic model but dispatch passes a `dict` → `AttributeError` on every call | `discovery.py::handle_get_navigation_path` | **FIXED** (cycle 1) |
| **D2** | `find_path_bfs()` never records `parent[end]` before reconstructing → every match returns `[]`, indistinguishable from "not found" | `discovery.py:77-85` | **OPEN** — pinned by `TestFindPathBfsReconstructionBug` |
| **D3** | No ancestor walk exists anywhere in the runtime; inherited properties (e.g. `FeatureRA` on `IFsClosedValue`) are invisible to `get_object_api` and `resolve_property` | `api.py:420` (`paginate_entity`), `api.py:541` (`resolve_pythonic_property`) | **OPEN** |

D1 masked D2: because the handler crashed before reaching BFS, the reconstruction
bug was never exercised live. D2 has been latent since commit `2053e12`
("Wave 3 Efficiency: Parent tracking") — **only precomputed `common_paths`
entries have ever resolved**; the entire BFS fallback is dead code in effect.

### Corrections to the cycle-1 briefing (recorded so they are not re-litigated)

- **There is no existing ancestor walk to extract.** `resolve_pythonic_property`
  does exact entity-equality matching only (`api.py:556`). What *looks* like
  inheritance resolution is a casting-index rescue at `api.py:1216-1221`, fed by
  offline **descendant**-direction propagation in
  `build_casting_index.py:153-188`, filtered by a noise threshold. The resolver
  must be written from scratch. (Explore §1)
- **But the walk is nearly trivial for the entities that matter.** Per
  `liblcm_extractor.py:698`, `entity["interfaces"]` comes from .NET
  `t.GetInterfaces()` and is **already the full transitive closure**.
  `base_classes` is `t.BaseType` — one level only. Properties are extracted
  `DeclaredOnly`, so each entity's own list is genuinely own-only. (Author §1)
- **`IFsFeatStruc -> IFsFeatDefn` does exist as a 2-hop path in the graph data**
  but the shipped code returns `[]` for it because of D2 — not because the data
  is missing. The earlier "resolves in 2 steps post-fix" claim was true of the
  data, false of the code path.

---

## 2. Decisions (resolved this cycle)

### DEC-1 — D2 is its own issue, but it **blocks closing #85**

Distinct root cause, distinct regression window (`2053e12`), distinct repro.
Filing it separately preserves the regression history and lets the commit
reference it. **However, #85 must NOT be closed until D2 lands.** #85's
user-visible contract is "`flextools_get_navigation_path` works"; today it no
longer crashes but returns `found:false` for everything outside `common_paths`.
Closing on the crash fix alone guarantees a reopen.

→ Fix D2 in CP1, close #85 and the new D2 issue together.

### DEC-2 — Resolver scope: one walk, applied narrowly

Write **one** memoized helper that walks `interfaces` ∪ `base_classes` with a
cycle guard (Explore: max depth 6, avg 1.33, max ancestor set 14 — cost is
negligible, 8.2 MB index already resident). But **apply it in CP2 only to `I*`
interface entities.**

Rationale: Explore found **2214 colliding `(entity, property)` pairs across 250
entities — all class-side, 0 interface-side.** Some are real semantic overrides
(`BackupFileSettings.BackupTime can_write:true` vs `IBackupSettings.BackupTime
can_write:false`). Interface merging is provably collision-free and is what
liblcm discovery actually targets. Class-side merging needs an override-semantics
policy that is not worth blocking #86 on.

- Dedupe rule: **child wins**, own members always shadow ancestors.
- Class-side enablement → follow-up ticket, not CP2.

### DEC-3 — Output shape (adopting lex-author, unmodified)

- Inline **`inherited_from: "<AncestorName>"`** on each merged property/method.
  Merged *before* `api.py:444/482` so filters, totals, slicing and the casting
  join at `api.py:523` all stay consistent.
- `total_properties` stays **byte-identical (own-only)**; add
  `total_properties_including_inherited`.
- **Required internal wiring fix:** `KEY_HAS_MORE`/`KEY_NEXT_OFFSET`
  (`api.py:478-480`, mirrored for properties) currently key off
  `total_properties`. Once the paginated candidate list includes inherited
  members, that math must switch to the combined total internally or pagination
  under-reports remaining pages. Internal fix, not a contract change.
- `inherited_from` is added to the `summary_only` field shape (same treatment
  `casting_notes` gets).
- **No contract version bump.** Additive-optional fields; consistent with every
  prior additive change (`update_notice`, `diagnostic_report`, `auto_discovered`).
- Accepted side effect: merged members flow into
  `session_state.record_discovered_api` (`api.py:742-751`) and thus count as
  "discovered". This is correct — the caller did see them.

### DEC-4 — `required_cast` labeled edges are **CP3, not CP2**

lex-domain is right that a bare path teaches a false model and a flat "no path"
teaches a dead end; a wrong-subtype path is the worst outcome of the three. But
the labeled-edge fix requires (a) navigation-graph regeneration, (b) a
subtype-selection policy (`IMoStemMsa` as the dominant concrete MSA subtype),
and (c) a new edge-level response field. That is a materially separate chunk.

Crucially, the **High**-severity harm lex-domain identified in #86 is that
`FeatureRA` is *hidden*, forcing users onto `LongName` string-parsing — which
fails on unordered `ILcmOwningCollection` positional assumptions and on
space-bearing values like Swahili `"NC 4"` / `"NC 1a"`. **CP2 fixes that
directly** by making `FeatureRA` visible. CP3 is navigation ergonomics on top.

### DEC-5 — `validators._interface_member_names` is read-only this spurt

It is a genuine third instance of the same bug class (recurses one level below
`_depth == 0`; works today only because `interfaces` is pre-flattened; breaks on
class chains >1 level). It **must** be covered by the consistency test — but see
§4: `validators.py` is contested. Assert against it; do not edit it.

### DEC-6 — `git stash` is banned in this repo

Cycle 1 hygiene incident: a `git stash pop` grabbed a concurrent crew's stash and
produced conflict markers in `.claude/settings.json` and `flexicon_analyzer.py`.
Recovered cleanly (verified: `git ls-files -u` empty, both stash entries intact,
no data lost) — but multiple agents share this working tree. Use targeted diffs
or scratchpad copies instead. This constraint is repeated in every cycle-2 prompt.

### DEC-7 — `has_more`/`next_offset` repair widened to all entities, not just merged ones

The `has_more` / `next_offset` fix in `paginate_entity` was widened beyond the
merged (`I*`-interface) entities DEC-2/DEC-3 scope the inheritance merge to. It
now computes `methods_has_more OR properties_has_more` for **all** entities,
not just merged ones.

Reason: `has_more` was previously derived from `total_methods` alone, so
`properties` had no pagination signal whatsoever — this predates and is
independent of the inheritance-merge work. `IFsClosedValue` has 14 combined
methods vs 31 combined properties, so the method-only signal flipped `False`
after page 3 while 16 properties were still unreachable. Scoping the fix to
merged entities only would have left that pre-existing bug live for every
other entity, merged or not.

Verification confirmed correctness across three scenario classes:
method-heavy merged (`ICmObjectInternal`, 64 methods vs 27 properties),
property-heavy merged (`IFsClosedValue`), and non-merged non-interface
(`LexSense`, 79 own properties) — the last of which must be, and is,
unaffected.

**Status:** approved by lex-lead cycle 3; classified a bug fix, not a
contract change.

---

## 3. Cross-tool consistency invariant (acceptance criterion for CP2)

> For every `(property, concrete_type)` pair where `property` is declared (own,
> `DeclaredOnly`) on some ancestor `A` in `concrete_type`'s `interfaces` closure:
> `get_object_api(concrete_type)` MUST list `property` in `properties` with
> `inherited_from == A`, **AND** `resolve_property(property,
> context_entity=concrete_type)` MUST return `found: True` for that same
> `concrete_type`.

Sample the invariant against **three** surfaces: `get_object_api`,
`resolve_property`, and `validators._interface_member_names`.

Canonical case: `IFsClosedValue` merges 2 own → 31 total properties, and
`FeatureRA` becomes visible with `inherited_from` set.

---

## 4. Concurrency constraints (active — another crew shares this tree)

A separate crew is mid-edit on an unrelated `workspace_notice` feature.
Our advisory locks (team `lex-crew-85-86`, session
`a8aebe83-39a6-44c4-a235-a21c671e9e80`) cover only the review `.md` files,
`discovery.py`, and `tests/test_issue85_navigation_path.py`.

| File | Their state | Our action |
|---|---|---|
| `discovery.py` | clear | **EDIT** (we hold the lock) |
| `api.py` | untouched since Jul 21 | **EDIT** — unobstructed |
| `tests/**` (new files) | clear | **EDIT** |
| `validators.py` | their hunks at 20 / 449-460 / 552-576 / 656-676; our target at 765-797 | **READ ONLY** — disjoint regions, but same file; assert, don't edit |
| `docs/TOOL-CONTRACT.md` | their hunks at 27, 277-325 | **DEFER to CP4** — draft text into `DOCS-PENDING.md` |
| `CHANGELOG.md` | new block at top of `[Unreleased]` | **DEFER to CP4** — draft text into `DOCS-PENDING.md` |

Note: the other crew's TOOL-CONTRACT change is itself an additive-field
precedent — the same compatibility question DEC-3 just adjudicated. CP4 should
document both consistently rather than as two unrelated additions.

---

## 5. Checkpoints & tasks

### CP1 — Navigation path actually works (`#85` closable)
- [x] T1.1 Fix `args` dict access in `handle_get_navigation_path` *(cycle 1)*
- [x] T1.2 7 regression tests incl. real `server.call_tool()` dispatch path *(cycle 1)*
- [ ] T1.3 Fix `find_path_bfs()` reconstruction (record the final edge before
      walking `parent`; do **not** mutate `parent[end]` — a visited `end` may
      already hold a different parent)
- [ ] T1.4 Flip `TestFindPathBfsReconstructionBug` from pinning the bug to
      asserting correct behavior; keep the multi-hop + direct-edge cases
- [ ] T1.5 Verify `IFsFeatStruc -> IFsFeatDefn` returns the real 2-hop path
- [ ] T1.6 Confirm `ILexSense -> IFsSymFeatVal` still returns `found:false`
      for the *correct* reason (no downcast edge — CP3, not a bug)

### CP2 — Inheritance merge (`#86` read-path)
- [ ] T2.1 `collect_inherited_members(entity_name, index)` — memoized, cycle-guarded
- [ ] T2.2 Merge into `paginate_entity` before `api.py:444/482`, `inherited_from` tag
- [ ] T2.3 `total_properties_including_inherited`; repoint `has_more`/`next_offset`
- [ ] T2.4 Ancestor-aware fallback in `resolve_pythonic_property`
- [ ] T2.5 Consistency-invariant test across all three surfaces (§3)

### CP3 — `required_cast` labeled downcast edges *(design ready, not started)*
Per lex-domain §4: scoped to the dominant concrete subtype from casting_index's
`base_type`/`concrete_types`, with `_add_polymorphic_warnings` listing alternates
(`InflFeatsOA`, `From/ToMsFeaturesOA`) as advisories — **not** as competing BFS edges.

### CP4 — Docs *(gated on the other crew landing)*
`docs/TOOL-CONTRACT.md`, `CHANGELOG.md` (`Added`, not "Tool contract"),
`docs/LIBLCM_CONTEXTUAL_ANALYSIS.md` (the `GetInterfaces()` full-closure vs
`BaseType` single-level asymmetry).

---

## 6. Issues to file (pending user approval)

Both bodies are drafted in `reviews/cycle1-programmer.md`. Neither should be
filed unattended — issue creation is a user decision.

1. **`find_path_bfs()` never finds a path since the Wave 3 parent-tracking
   rewrite** — blocks closing #85 (DEC-1).
2. **Handler exceptions bypass the structured error envelope** —
   `server.py:986` `await handler(dumped)` is unguarded; this is *why* #85
   surfaced as a raw string instead of a TOOL-CONTRACT error code. Independent
   of this feature; file and defer.
