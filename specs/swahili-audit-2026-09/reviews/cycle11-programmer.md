# Cycle 11 - Programmer report (CP-E: cast_to_concrete phantom remedy)

Both `cast_to_concrete` advisory bugs from cycle10-phantom.md are fixed.
Pre-existing failure class, same as #103 (advisory text drifted from the
real API).

Commits (report committed first, per protocol; shas added here in this
follow-up doc commit once the code commits existed):
- `5a71102` docs: this report
- `1f8e90b` fix: rewrite cast_to_concrete phantom advisories (Symbol A + B)
- `ffafb8c` test: drop dead facade assignment (bundled freebie, separate)

## Symbol A - true phantom `CastingOperations` (re-derived lines)

- `src/flextoolsmcp/server/handlers/api.py:1621, :1636`
- `src/flextoolsmcp/server/handlers/discovery.py:163, :169` (drifted +1
  from the briefed :168)
- `src/flextoolsmcp/server/validators.py:3642` (`_POLY_ITERATION_NOTE`)

All five rewritten to `cast_to_concrete(obj)` / `cast_to_concrete(item)`
"from flexicon.code.lcm_casting", matching the phrasing already correct at
validators.py:3927/3935 (untouched). Verified zero remaining
`CastingOperations` hits under src/flextoolsmcp (grep, excluding .pyc).

## Symbol B - wrong arity + bad import (all line numbers matched the brief)

`src/flextoolsmcp/templates/3-liblcm-template.py`: dropped the second arg
at :87, :115 (live code, was :85/:113), :191 (`cast_to_interface` helper,
was :186 - also stripped its now-meaningless `interface_type` param), and
in the prose examples at :263, :304, :310, :335 (was :258/299/305/330).
Left the already-correct import block at :32 untouched.

`00-FLAVOR-GUIDE.md`: bad `from flexicon.code.lcm_casting import
cast_to_concrete, ILexEntry` at :110 and :167 (was :110/:163) split into
two imports; arity fixed at :122, :169, :184 (was :118/164/179).

`README.md`: bad import at :74 split; arity fixed at :78, :159 (was
:77/158). Benign prose at :129 (was :128, shifted +1 by the added import
line) left alone as instructed.

## RED/GREEN evidence

**Tightened substring test** (`test_issue48_inline_casting.py`,
`test_polymorphic_collection_annotated`): replaced the pass-either-way
`assertIn("cast_to_concrete", ...)` with `assertIn("concrete =
cast_to_concrete(item)", ...)` + `assertNotIn("CastingOperations", ...)`.
RED before the validators.py fix:
`AssertionError: 'concrete = cast_to_concrete(item)' not found in 'Items
are heterogeneous; cast each item: concrete =
CastingOperations.cast_to_concrete(item)'`. GREEN after.

**New class `TestShippedLiblcmTemplateCastingArity`** (same file, 3
tests): regex-scans the shipped template for every `cast_to_concrete(...)`
call (live + prose) and asserts exactly one arg; asserts no `from
flexicon.code.lcm_casting import ...` line names `ILexEntry`; and pins
the real installed `cast_to_concrete` signature (1 positional param) so
the test can't drift from reality again. RED before the template fix:
7 bad sites reported - `('entry_hvo, ILexEntry', 2)`,
`('sense_hvo, ILexSense', 2)`, `('obj, interface_type', 2)`,
`('item, ILexEntry', 2)` x1, `('entry_hvo, ILexEntry', 2)` x2,
`('entry, ILexEntry', 2)` - matching all 7 call sites. GREEN after (import
and signature sub-tests already passed pre-fix since the template's own
top import block was already correct).

## Bundled freebie (separate commit)

`tests/test_issue100_access_path.py`: deleted the dead `facade =
_extract_facade_access_paths(flexicon_code_base)` assignment (never read)
plus its now-orphaned import and `flexicon_code_base` local - the
`hasattr`-based hazard set is unaffected by design. Confirmed
`test_every_known_operations_member_is_top_level_importable`-adjacent
tripwire class still passes: 21/21 in that file, before and after.

## Suite numbers

Baseline (pre-cycle, commit 36a5a1c): 1135 passed, 4 skipped, 12 subtests.
After both fixes + 3 new tests: **1138 passed, 4 skipped, 12 subtests**
(1135 + 3 new arity/import/signature tests, no regressions).

## Untouched per constraints

`execution.py`, `versioning.py`, `index/**`, `operations.jsonl`,
`docs/logscan-state.json`, cycle1 reviews. No GitHub issue touched, no
push. Lockout session `405409e3-8de7-4014-89c3-1a3262513baf` released
after commits.
