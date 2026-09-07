# Cycle 9 -- Programmer report: CP-D close-out (P0-1 + 4 ruled-in findings)

Commits: `c6cbd25` (TASK 0, 3 untracked reports), `97bd304` (code+doc+tests).

## Widened mechanism-name audit (TASK 1)
Grepped `defined_on`, `defined_on[0]`, `_pick_cast_interface`, `cast_interface`,
`arbitrary`, `#97`, `Bug 1` across docs/, README.md (no hits), CHANGELOG.md,
docs/CASTING_SYSTEM.md (no hits), src/, tests/golden/, tests/evals/corpus/.
Findings: TOOL-CONTRACT.md:209-210 (fixed, below). docs/INNOVATIONS.md:38 --
`defined_on` in a JSON schema example, unrelated, accurate. CHANGELOG.md --
historical entries describing past changes, not current-state claims,
unaffected. tests/golden/*.json -- field values only. tests/evals/corpus --
unrelated prose. `docs\logscan-state.json` had a hit but is explicitly
off-limits/unstaged. **Stale but out-of-lock-set** (flag for lead/user):
`STATUS.md:76,88`, `specs/swahili-audit-2026-09/.crew-handoff.json:41,101`,
`tasks-bugfix-campaign.md:584` all still assert "#97 Bug 1 not yet
repaired" -- none is in my editable set.

## TOOL-CONTRACT.md rewrite
Trichotomy: resolved -> `"Cast {obj} to {interface}"` (agrees with
`cast_interface`); ambiguous -> candidate-set/count message, `cast_interface:
null`; no-candidate -> "concrete type" placeholder. States #97 Bug 1 is
repaired without claiming #97 itself is closed.

## Final message text (both tiers, verbatim)
`>6`: `"Cast {obj} to the concrete interface it actually is. {N} interfaces
declare '{prop}' -- too many to guess. Determine it from where {obj} came
from (the wrapper method's return type that produced it), or dispatch at
runtime on {obj}.ClassName."`
`2..6`: `"Cast {obj} to one of: {A, B, C} -- this list is ALPHABETICAL, NOT
ranked by likelihood; do not just pick the first. Determine the correct one
from where {obj} came from (the wrapper method's return type that produced
it), or dispatch at runtime on {obj}.ClassName."`

## cast_to_concrete precondition: NOT verified, NOT advertised
`CastingOperations` class does not exist anywhere in the real flexicon 4.5.2
package or its API index (grep + import attempts both fail). The bare
`cast_to_concrete(obj)` function IS real (`flexicon/code/lcm_casting.py:408`)
but flexicon's own `CLAUDE.md:255` documents it "for internal use only".
Advertising either would repeat the #103 failure class, so I dropped it and
fell back to provenance/ClassName guidance only. Also dropped the
`flextools_resolve_property(context_entity=...)` suggestion entirely
(P1-3: circular, and the bare `context_entity=...` was literal Ellipsis) --
no message emits it now, trivially satisfying test (c).

## TASK 3 behavior-preservation proof
Before/after equality for `_casting_candidates_for_fix` across all 986
properties in the shipped index: **0 mismatches**. For `_pick_cast_interface`
(rebuilt old inline logic vs. current shared-helper version) across 986
properties x 6 receiver names = 5916 combinations: **0 mismatches**.

## Mutation evidence (verbatim highlights, all reverted)
1. Disabled the `>6` branch (`if False:`): tests (a)/(d) failed --
   `'36 interfaces declare' not found in "Cast morph_type to one of: ICmAgent,
   ..."`. Reverted -> 10/10 pass.
2. Mutated the not-ranked warning text: test (b) failed -- `'ALPHABETICAL'
   not found in "...MUTATED_AWAY_WARNING ranked by likelihood..."`. Reverted.
3. `_clean_interface_head` -> `return None`: tests (a)/(b) failed --
   `'Cast morph_type to concrete type'` / `'Cast unrecognized_receiver_zz to
   concrete type'`. Reverted -> 111/111 casting-suite pass.
4. TASK 4: added `MSAOperations` then `StratumOperations` to
   `KNOWN_OPERATIONS` -- both trip `test_known_operations_disjoint_from_
   full_facade_only_set` (`AssertionError: Lists differ: ['StratumOperations']
   != []`), proving the widened tripwire, unlike the old MSAOperations-only
   pin, catches any of the 21 hazardous classes. Reverted -> 21/21 pass.
Note: real shipped index data has zero entries with parenthetical/whitespace
suffixes or non-I-prefixed heads, so the head-splitting edge case itself has
no live-data mutation coverage (matches QC's P3 latent-only note); mutation 3
instead proves the extraction wiring is load-bearing.

## TASK 4 / TASK 5
api.py:689-703 wording corrected to the real 13-facade-only/8-unreachable-of-
64 measurement; no-op conclusion unchanged. Tripwire widened to assert
`KNOWN_OPERATIONS` disjoint from the live-computed hazardous set; flexicon-
less-CI skip messages now state plainly the tripwire is unguarded.
test_flextools_health.py's "~15-25%" replaced with the four real numbers
(5/40, 1/40 -- cycle7-programmer-p2.md; 40/300 -- cycle8-verification.md;
58/200 -- cycle8-qc.md), each cited.

## Suite/corpus/invariant
`pytest -q`: 1133 passed (1129+4 new), 4 skipped, 12 subtests.
`evals/test_corpus.py`: 35 passed, 2 skipped. Casting regression set (7
files): 111 passed. Bare-snippet invariant: independently re-verified live
-- bare module-level snippet and `Main`-wrapped form produced identical
issue counts and byte-identical `fix` strings for Name and Gloss.

`versioning.py`: confirmed untouched (`git diff` empty, not in either
commit). `git status --porcelain`: only pre-existing untouched items
remain (index migration, cycle1-*.md, operations.jsonl).
