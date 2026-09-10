# Cycle 2 / Archivist: draft issue -- comment/string-stripping false positives

Draft only. Not filed. Duplicate check: `gh issue list --search` on "strip
comments", "certify_script_readonly", "mutating_calls" found no exact
match. Nearest neighbors are #126 (`find_liblcm_mutations` receiver-blind
on `.Add()`, OPEN) and #131 (`is_certified_readonly=true` on mutating runs,
OPEN) -- both are false-*negative* write-gate bugs (mutations slip through);
this issue is the false-*positive* direction (read-only code gets
hard-blocked) plus two import-detector FPs, so no overlap/duplicate to
flag. Closed #7 ("Found 0 unprotected mutation(s)") is a different root
cause (contradictory gate/message wiring), not this stripping defect.
Line numbers below verified against the live file
`src/flextoolsmcp/server/validators.py` on branch `flexicon-project-bridge-mcp`.

---

## Ready-to-file issue

**Title:** Un-stripped comment/string scanning causes false positives in certify_script_readonly, import detectors, and casting-needs severity

**Labels:** bug

**Body:**

```markdown
## Summary

Several regex-over-raw-`code` scans in `src/flextoolsmcp/server/validators.py`
do not strip comments/strings first, so text inside comments, string
literals, and docstrings is treated as real code. The most severe instance
hard-blocks read-only scripts.

## 1. certify_script_readonly hard-blocks read-only code (primary)

- Step 1 (`validators.py:3557`, `_PATTERN_OPERATIONS_CALL`) and Step 1c
  (`validators.py:3617`, `_PATTERN_PROJECT_ACCESSOR_CALL`) scan un-stripped
  `code` and seed `operations_calls_with_lines`.
- Step 2 (`validators.py:3632-3657`) turns those seeds into
  `mutating_calls`, driving `is_certified_readonly=False`.
- Reproduced against the real index (`flexicon_api_v*.json`):
  - a comment-only `# AgentOperations.Create(x)` line -> Step 1 match ->
    `mutating_calls` populated -> read-only script certified as mutating.
  - a string-literal / docstring `"project.Agents.Create(x)"` -> Step 1c
    match -> same outcome.

A script that performs zero mutations gets rejected by the write gate
purely because a comment or docstring happens to mention an operations
method name.

## 2. Import-detector false positives

- `detect_missing_operations_imports` (`validators.py:1987`,
  `_PATTERN_KNOWN_OPS`) and `detect_wrong_library_imports`
  (`validators.py:2042`, inline `(?:from|import)\s+([\w.]+)`) both scan
  un-stripped `code`.
- Reproduced: `# maybe use MorphRuleOperations.Foo(x)` is reported as a
  missing import; `# from flexlibs import FLExProject` in a comment is
  reported as a wrong-library import.
- These flow downstream into `src/flextoolsmcp/recipe_validator.py:89,105,109`,
  so the false positives propagate into recipe validation output too.

## 3. detect_casting_needs stamps severity="error" off a duplicated, buggy stripper

- `detect_casting_needs` (`validators.py:5077`) sets `severity="error"`
  based on matches from two *inline* re-implementations of comment
  stripping (`re.sub(r'#.*$', '', line)` at `validators.py:5004` and
  `validators.py:5100`) rather than reusing `_strip_comments`.

## Meta-finding: why the fix is not "call _strip_comments more"

`_strip_comments` (`validators.py:178`, pattern at `validators.py:37`,
`#.*$` MULTILINE) preserves line numbering exactly (measured: identical
newline counts before/after), so Steps 1/1c *could* safely switch to
stripped text for line-number purposes. But `_strip_comments` has two
correctness bugs of its own:

- It does not handle triple-quoted or multi-line string literals, so code
  inside a docstring is still scanned as real code (this is *part of* the
  certify_script_readonly defect above, not a separate one).
- It mishandles a `#` inside a single-line string literal and **eats real
  code**: `t = "a#b"; project.LexEntry.Create(e)` becomes `t = "a`, which
  drops the real mutation from `find_liblcm_mutations` -- a false
  *negative* in a stripping consumer that already uses it
  (`validators.py:3348`). Worse, running `_strip_comments` output through
  `ast.parse` can raise `SyntaxError` on a string like `msg = "tag#1"`,
  and `certify_script_readonly` swallows that at `validators.py:3550`
  (`tree = None`), silently disabling Steps 1b/2b/4b.

Therefore: do not simply route Steps 1/1c/1987/2042/5004/5100 through the
existing `_strip_comments`. Converge on one of:

- AST-ification, following the precedent already set by
  `detect_nested_unit_of_work` (`validators.py:526`, rationale at
  `validators.py:529-532`), or
- a `tokenize`-based stripper that preserves both line *and* column
  (unlike the current regex, which only preserves line), used
  consistently everywhere, with the inline duplicates at
  `validators.py:5004` and `validators.py:5100` deleted in favor of it.

## Test evidence

`pytest -q` baseline: 1312 passed, 8 skipped, 36 subtests. Swapping in a
*stronger* simulated change (stripping before Steps 1/1c, before
`find_protected_ranges`, and before `ast.parse`) still passes all 1312 --
no existing test asserts a pattern hit on comment or string text, so this
is safe to fix. `tests/test_validators.py:409-420` already documents the
multi-line-string gap in `_strip_comments` and should be extended, not
contradicted, by whatever fix lands here.

## Not in scope here

`certify_script_readonly` Step 2b itself is unaffected by this issue: the
write-gate fix landing separately changes Step 2b to read only AST `Call`
nodes and resolution maps, never raw `code`/`lineno` text, so a
comment/string decoy produces no `Call` node for that step. This issue
covers the three other consumers (Steps 1/1c seeding `mutating_calls`,
the two import detectors, and the casting-needs severity stamp), which
remain live regardless of the Step 2b fix.

## Related

- #126 -- different false-positive mechanism (receiver-blind `.Add()`
  matching), same "hard-blocks read-only code" symptom class.
- #131 -- opposite direction (false negative: mutating code certified as
  read-only).
```


---

## Filed

Filed as #133 on MattGyverLee/FlexToolsMCP with user authorization.
Line anchors were refreshed to post-commit values and pinned to 23ff2c8 before
filing, since the write-gate fix shifted every line number in this draft
(Step 1 :3557 -> :3668, Step 1c :3617 -> :3733, import detectors :1987/:2042 ->
:2033/:2087, inline strippers :5004/:5100 -> :5150/:5246, the tree = None
swallow :3550 -> :3662).
