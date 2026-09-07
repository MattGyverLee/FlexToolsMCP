# Cycle-4 QC -- b5f41d8, cea0ca6, aba84d8, d1f30da

**No P0.** Suite re-run clean: `1107 passed, 4 skipped, 12 subtests` (matches
d1f30da's claim). Findings were verified by executing pre- and post-diff
validators side by side, not by static analysis.

## Q1 gate-locality: clean

Diffed every `write_enabled` read in `execution.py` pre/post. Post-diff adds
exactly ONE consumption site (`:2900`, inside the casting block); all others
byte-identical, line-shifted only. `certify_script_readonly`,
`hvo_literal_write_risk` (`:2799`), `nested_unit_of_work` and
`_resolve_alias_maps` untouched. No leakage.

## Q2: no P0

The downgrade branch is guarded by `(not write_enabled) and ...`. Separately,
every B-2/B-4 rewiring is strictly *narrowing* (`typed_root`,
`_alias_satisfies`, `line_var_cast_types` suppress less than the flat dict did),
so the casting gate can only flag MORE. No un-cast polymorphic access reaches
a write run.

## P1-1 (b5f41d8) `validators.py:976` -- typo gate silently weakened on WRITE runs

`interface = _resolve_cast_type_at(...)` can now return `None` for a name that
IS in `cast_aliases`, and `:983 if not interface: continue` drops the issue.
Pre -> post with `d = ILexDb(x)` and typo `d.EntriesOC`:
cast-in-`if`-used-after, cast-in-`try`-used-in-`except`, cast-in-`for`-used-after
all went `has_typos=True (severity "error")` -> `False`. These previously
hard-rejected on read-only AND write runs; now nothing reports them. The commit
message's "write runs still hard-reject ... unchanged" holds for the *decision*,
not what reaches it.

## P1-2 (d1f30da) `execution.py:1783` vs `:2880` -- validate_only inputs are NOT equivalent

The predicate is truly shared (module-level `:1690`, both sites) and
`write_enabled` is honestly threaded (`:1916`). But `handle_run_module` folds
`detect_interface_attribute_typos` into `casting_issues` and forces
`severity="error"` (`:2880-2886`); Gate 5 never calls it (only call site:
`:2880`). With `d = ILexDb(project); d.EntriesOC`,
`write_enabled=False`: run_module rejects, while validate_only returns
`passed: True` plus the note *"run_module would proceed without rejecting"*.
Pre-B-5 it said `passed: False`, which agreed -- B-5 replaced a pessimistic
disagreement with a false reassurance for the whole #39 typo class. The
end-to-end agreement test monkeypatches `detect_interface_attribute_typos` to
no typos, so it cannot catch this.

## P2 findings

1. **b5f41d8** new casting-gate false positives (warning tier, so read-only
   proceeds -- but write runs newly hard-reject): cast in both `if` arms used
   after the conditional; cast in `try` used in `except` (`ExceptHandler` is
   unreachable via `body/orelse/finalbody`, so `_CAST_SCAN_RECURSE_INTO` never
   helps); cast in `for` used after the loop. Cast-in-`for`-used-in-`for` and
   cast-in-`try`-used-after-`try` are correctly NOT flagged. Every divergence
   errs toward over-refusal, the safe direction.
2. **b5f41d8** `preflight_runner.py` Gate 5 models no typo-derived issues (its
   own comment says so), so Tier-1 is blind to P1-2.
3. **aba84d8** `admin.py:276` -- "a brand-new session only ever sees the last
   master flush" is asserted unconditionally, but is established only for
   read-only opens; a write-enabled fresh session calling `SaveChanges()` is
   the untested cross-repo item 6. Defensible thanks to "not *currently*";
   scope it to "a brand-new read-only session" and keep item 6 open. No
   digit+unit duration in the entry (regex test verified).
4. **cea0ca6** #100 is dormant: 0/118 shipped entities carry `access_path`, so
   the generator half is unexercised until a refresh -- entangled with the
   undecided index migration.

## Q4, Q5, Q8: clean

`NOT_CMPOSSIBILITY_NAME_COLLISION` = exactly 6 entries; `IMoMorphType` /
`MoMorphType` not flagged, and the real liblcm index confirms the premise
(`ICmPossibility` in `IMoMorphType.interfaces`, absent from all 3 targets).
Curated-vs-structural was right at a 76-entity FP rate; the liability, a missed
fourth type, is inert rather than wrong -- keep it tied to #87. #100's
absent-key fallback is the only live path and is covered (no-arg / absent /
empty-string; `paginate_entity` both modes); the 63 no-facade entities
unaffected. Fixtures: `b5f41d8` touched one
existing fixture, flipping `write_enabled` false->true, not `expect.outcome`
(still `preflight_reject`), reasoning in `notes` -- STANDARD held. `d1f30da`
added a missing `"severity": "error"` to one mock, matching real
`detect_casting_needs` output; no assertion flipped.
