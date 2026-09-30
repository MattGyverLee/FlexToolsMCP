# Cycle 10 -- Programmer T014: `tests/test_grammar_health.py`

**File:** `tests/test_grammar_health.py` (new, 74 tests across 12 classes).

## What each test group guards

- `TestContractExampleItself` (10 tests, GREEN today): parses the contract
  doc's own `json` fence and asserts against it literally -- no denylisted
  key anywhere, finding/object field sets match the pinned allowlists, no
  verdict words in `measured`, `measured` matches the positive template, no
  `total` key, `next_step: null`, `checks_skipped` reason is exactly
  `lcm_name_unverified`, and the doc text itself states the no-HCParser/
  no-LcmCache/no-IWfiAnalysis guarantees.
- `TestGrammarHealthFindingStructuralClosure` / `TestFoundObjectStructuralClosure`
  (T017, RED): `extra="forbid"`, exact 6-key / 4-key allowlist, parametrized
  rejection of all 12 denylist words as extra fields, plus a generic
  "any unforeseen key" rejection (structural closure, not just name-denial).
  A dedicated test nests a poisoned `FoundObject` dict inside
  `GrammarHealthFinding.objects` and asserts the *outer* construction fails
  -- closure at both nesting levels.
- `TestRecursiveDenylistWalkOverRealModels` (RED): builds real nested
  `GrammarHealthFinding(objects=[FoundObject, ...])` instances, `.model_dump()`s
  them, and walks recursively for denylisted keys, including a self-test that
  plants a `severity` key two levels deep and confirms the walker actually
  catches it (not a vacuous pass).
- `TestOrderInvarianceOfFindings` (RED, CONTRACT AMBIGUITY -- see below):
  runs an assumed assembly seam twice with permuted count magnitudes across
  three spec-rows and asserts `[f.check_id for f in findings]` is
  byte-identical (via `json.dumps`) both times; a dedicated test picks counts
  that explicitly disagree with count-descending order and asserts the
  result is row-order, not count-order; `spec_row: null` extras are checked
  to stay in a fixed position regardless of magnitude; `objects[]` item order
  (by `hvo`) is asserted preserved-not-sorted across two permuted runs; a
  capping test confirms `limit` truncates without resorting and `count`
  stays the true total.
- `TestCountsNeverSummedIntoATotal`, `TestCP1BoundaryOnTheScanModule` /
  `OnTheHandler` (RED): static source-text checks for `IWfiAnalysis`,
  `HCParser(`, `LcmCache(`, `check_active_parser(` -- scoped to the two
  files this task can see (scan module runs in-subprocess; handler runs
  in-process), deliberately lighter than T026's definitive static+dynamic
  scan, which owns `tests/test_cp1_boundary.py`.
- `TestVerdictWordingNeverDescribesAFinding`: parametrized self-test of the
  denylist helper against all 11 verdict words, plus one RED end-to-end test
  through the assumed assembly seam.

## Recursive "any nesting level" walk

`_all_keys(obj)` / `_find_all(obj, key)` / `_all_string_leaves(obj)` walk
dict/list structures unboundedly, mirroring T008's `_find_all` precedent.
`_assert_no_denylisted_keys` lowercases every key found anywhere and
intersects with the 12-word denylist (7 primary + 5 renamed-proxy
backstops); applied to the contract example, to `.model_dump()` of real
nested model instances, and to a hand-assembled two-finding envelope fixture
to prove the deepest nesting level (an `objects[]` item) is covered, not
just the top.

## Order-invariance construction

Two `raw_findings` lists are built with the same three `check_id`/`spec_row`
pairs but magnitudes swapped end-to-end (lowest becomes highest and vice
versa), fed through the assumed seam, and the resulting `check_id` sequences
are compared via `json.dumps(...) == json.dumps(...)`. A second test
constructs a case where row-order and count-descending order actively
disagree and asserts the *row*-order wins. `objects[]` order is checked the
same way using `hvo` as the varying value.

## Positive `measured` template

`^\d[\d,]*\s+\S.*\b(is|are|can|reachable|present|found|exceeds?|matches?|
attach(?:es)?|host(?:s)?|equals?)\b` -- requires a leading count and a
factual/measurement verb. Verified against the contract's own example
string ("3 allomorphs ... are reachable from an optional slot").

## Pass/fail and full-suite delta

`test_grammar_health.py` alone: **23 passed, 51 failed** -- every failure is
a clean `ImportError`/`ModuleNotFoundError` on `GrammarHealthFinding`,
`FoundObject`, `server.handlers.grammar_health`, or `server.scan.
grammar_scan_module` (verified by grepping the `E   ` lines). `ruff check`:
clean. Full suite (`tests/`): **1479 passed, 8 skipped, 36 subtests passed,
123 failed** -- confirmed via a diff run with `--ignore=tests/
test_grammar_health.py` (**1456 passed, 72 failed**, unchanged from the
in-flight T007/T008/T015 RED baseline): this file adds exactly its own +23
passed / +51 failed and touches nothing else. No regression.

## Contract ambiguity

Neither the contract, data-model.md, nor tasks.md pins the Python-level seam
`handlers/grammar_health.py` (T020) will use to turn `grammar_scan_module.py`'s
plain-data results (T015's sibling file independently confirms the module
can only return bool/int/list/dict, since `scan/__init__.py` forbids it from
importing `flextoolsmcp.server.*`) into ordered, capped `GrammarHealthFinding`
instances. This file assumes a pure `_assemble_findings(raw_findings: list[dict],
limit: int = 20) -> list[GrammarHealthFinding]` in `handlers/grammar_health.py`,
mirroring the existing `_build_parser_block()` precedent in
`diagnostic_health.py`. If T020 lands under a different name/shape, only the
`_call_assemble()` helper needs to change -- every ordering/closure assertion
is independent of that choice. Documented in the module docstring alongside
the same assumption for the two source-text boundary checks.
