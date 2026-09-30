# Cycle 1 / Explore: comment-stripping scope in validators.py

Branch `flexicon-project-bridge-mcp` @ `def958a`. Read-only investigation
(this agent has no Write tool; persisted by the orchestrator).

## 1. Every regex-over-source site

| Function | Line | Pattern | Strips? |
|---|---|---|---|
| `detect_module_structure` | :392 | `^\s*def Main\s*\(` (inline) | n (anchor makes `# def Main` unmatchable) |
| `detect_module_structure` | :400 | `^\s*docs\s*=\s*\{` (inline) | n (same) |
| `detect_partial_module_structure` | :464 | `^\s*docs\s*=\s*\{` (inline) | n (same) |
| `detect_cud_operations` | :307/:324/:338 | `_PATTERN_CREATE*`/`_SET_*`/`_DELETE*` | **y** (:294) |
| `detect_cud_operations` | :361 | inline `type_patterns` | **y** (:294) |
| `detect_missing_operations_imports` | :1987 | `_PATTERN_KNOWN_OPS` (:72) | **n -- confirmed FP** |
| `detect_missing_operations_imports` | :1998 | `_PATTERN_IMPORT_STMT` (:73) | n (unparsable fallback; `[^#\n]+` self-limits) |
| `detect_wrong_library_imports` | :2042 | inline `(?:from\|import)\s+([\w.]+)` | **n -- confirmed FP** |
| `find_liblcm_mutations` | :3351 | `_LIBLCM_MUTABLE_PATTERNS` (:96) | **y**, per line (:3348) |
| `certify_script_readonly` Step 1 | :3557 | `_PATTERN_OPERATIONS_CALL` (:74) | **n -- the defect** |
| `certify_script_readonly` Step 1c | :3617 | `_PATTERN_PROJECT_ACCESSOR_CALL` (:80) | **n -- the defect** |
| `detect_casting_needs` | :5011 | `pattern_info["pattern_sources"]` | partial -- inline `re.sub(r'#.*$','',line)` at :5004, *duplicating* `_strip_comments` |
| `detect_casting_needs` | :5101 | `property_access_pattern` (:5098) | partial -- inline dup at :5100 |

Non-regex substring reads of raw text: :388, :396, :466. Immune by design:
`find_protected_ranges` (:3385) and `detect_nested_unit_of_work` (:526,
rationale at :529-532) are AST-based.

Reproduced false positives (real index `flexicon_api_v*.json`):
- comment-only `AgentOperations.Create(x)` -> Step 1 -> `mutating_calls`,
  `is_certified_readonly=False` (spurious hard block of read-only code).
- string-literal / docstring `project.Agents.Create(x)` -> Step 1c -> same.
- `# maybe use MorphRuleOperations.Foo(x)` -> `:1987` reports it missing.
- `# from flexlibs import FLExProject` -> `:2042` reports wrong import.

## 2. `_strip_comments` (:178, pattern :37 `#.*$` MULTILINE)

- **Line numbering: preserved.** `.` excludes `\n`, so newline count is
  identical (7 in / 7 out measured) and every character *before* a `#` keeps
  its offset. Therefore `code[:match.start()].count('\n')` at :3560 and :3622
  yields identical line numbers on stripped text. Switching Steps 1/1c is
  line-safe. (Only offsets *after* a `#` shift -- nothing reads those.)
- **Triple-quoted / multi-line strings: NOT handled.** Measured: a
  `project.LexEntry.Create(x)` line inside `"""..."""` still produces a
  `find_liblcm_mutations` hit at that line, and certify's docstring decoy
  above. Only trailing `#` comments are removed.
- **`#` inside a string literal: mishandled, and it eats real code.**
  `t = "a#b"; project.LexEntry.Create(e)` becomes `t = "a` -- the real
  mutation on that line vanishes from `find_liblcm_mutations` (false
  negative in a *stripping* sibling). Worse, stripping before `ast.parse`
  can raise `SyntaxError` (`msg = "tag#1"`), which certify swallows at
  :3550 (`tree = None`), silently disabling Steps 1b/2b/4b. So strip for
  regex passes only -- never reassign the parsed `code`.

## 3. Would stripping break existing tests? No.

Baseline `pytest -q`: 1312 passed, 8 skipped, 36 subtests. With
`validators.textwrap.dedent` shimmed to `_strip_comments(dedent(code))`
(a *stronger* change than needed -- Steps 1/1c *and* `find_protected_ranges`
*and* `ast.parse` all see stripped text): identical, 1312 passed.
No test asserts a pattern hit on comment or string text. Nearest-adjacent
tests only benefit: `tests/test_nested_uow_gate.py:123,132,269`,
`tests/test_issue103_hvo_stability.py:148,318` (both already AST-based),
`tests/test_validators.py:403`. `tests/test_validators.py:409-420`
deliberately asserts nothing about the multi-line-string case -- it documents
the gap in 2. Import-detector tests (`test_validators.py:335,343`;
`test_validator_cluster_fixes.py:123,142`) use clean code. **Zero breakage.**

## 4. Recommendation: separate follow-up, not this fix.

The chosen Step 2b shape (`cycle1-qc-step2b-fix-shape.md:9-13,40-46`) reads
only `ast_calls` and the resolution maps -- never `code`, `lineno` keys, or
`operations_calls_with_lines`. A trailing-comment decoy produces no `Call`
node, so **for the write gate the stripping issue is moot**; do not enlarge
the cycle-1 diff for it.

It remains a live defect on its own merits: (a) Steps 1/1c still seed
`operations_calls_with_lines`, so Step 2 (:3632-3657) emits spurious
`mutating_calls` and `is_certified_readonly=False` from comments/strings --
a read-only script gets hard-blocked; (b) `:1987`/`:2042` FPs flow into
`src/flextoolsmcp/recipe_validator.py:89,105,109`; (c) `detect_casting_needs`
stamps `severity="error"` (:5077) off a stripper that mishandles strings.

Fix direction for the follow-up is *not* "call `_strip_comments` more" -- that
helper is unsafe per 2. Converge on AST-ification (as `detect_nested_unit_of_work`
already did) or a `tokenize`-based stripper that preserves line and
column, plus de-duplicating the inline `re.sub` copies at :5004/:5100.
