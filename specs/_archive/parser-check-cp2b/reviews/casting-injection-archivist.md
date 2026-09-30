# Archivist Investigation: Three-Tier Casting-Helper Injection

**Question:** Was the "three-tier casting-helper injection" feature EVER wired into a live
code path, or was it born dead? Regression (restore) vs. never-shipped (delete)?

## VERDICT

**REGRESSED AT `d3e55d4` ON 2026-04-07** (14:19:43 -0500) -- the feature was genuinely live
for roughly one day (2026-04-06 17:00 to 2026-04-07 14:19), embedded in the actual executed
runner-script template for `handle_run_module`, and then silently orphaned as collateral
damage of an unrelated logging/indentation fix. It has been dead ever since (~5.5 months, not
merely "since 2.3.1" as the retirement commit 078d8e8 conservatively claimed -- the true death
predates the 2.3.1 release, ffa3c0b/2026-07-04, by about three months).

**`_validate_api_mode` VERDICT (separate):** Never independently live -- by design, from its
very first commit (f721a96, 2026-03-14) its only caller was always `_get_api_mode_imports`
itself. It was *transitively* live (executed on every real run) for as long as
`_get_api_mode_imports` had a live call site, i.e. until the same d3e55d4 death. Commit
0d3a791 (2026-09-18) hardened its error handling and fdbf8e9 (2026-09-20) added direct
unit-test call sites, but neither restored any production call path -- both left it exactly as
dead (test-only + internal-only) as they found it.

---

## Recovered Design Intent (from deleted docs/THREE_TIER_INJECTION.md, docs/CASTING_SYSTEM.md)

The feature was a 3-layer defense against polymorphic C# type errors (e.g.
`sense.Owner.HeadWord` raising `AttributeError: 'ICmObject' object has no attribute
'HeadWord'` -- "the problem Dennis encountered"). Layer 1 was static pre-flight detection
(`detect_casting_needs()`, still alive today and unrelated to this verdict). Layer 2 was this
injection system: generated runner scripts would carry a `try: from casting_helpers import
...  except ImportError: <inline fallback defs>` block sized to one of three tiers based on
what the pre-flight scan found:

- **Tier `none`** (0 bytes): pre-flight found no casting issues -- nothing injected.
- **Tier `minimal`** (~50-100 bytes): issues found but user's code already handled them --
  only the specific helpers used (`helpers_needed` set) were injected.
- **Tier `full`** (~200 bytes): defensive mode / unusual code -- all five helpers
  (`safe_get_property`, `smart_cast`, `cast_or_default`, `get_headword`, `get_lexeme_form`)
  injected.

Quoted design intent: "Previously, casting helpers were injected into EVERY execution,
adding 200+ bytes even when not needed. Now they're injected only when necessary." Layer 3
was on-error recovery (`resolve_property()` tool suggestion on a live `AttributeError` --
unrelated to this verdict, still exists independently).

---

## Timeline

| Date | Commit | What happened to the feature |
|---|---|---|
| 2026-02-26 | `bfa8f86` (v1.1.0) | **Birth of `_get_api_mode_imports`.** Two genuinely live call sites confirmed by diff: `handle_run_module` and `handle_run_operation` each computed `api_imports, _ = _get_api_mode_imports(api_mode)` and substituted it into the executed runner script via a `{{API_MODE_IMPORTS}}` placeholder + `.replace()`. No casting-helper concept yet -- this is plain API-mode-string import selection. |
| 2026-03-14 | `f721a96` | **Birth of `_validate_api_mode`**, called only from inside `_get_api_mode_imports` (Gate #1: "validate API mode is valid" before generating imports) -- never an independent call site, by design, from day one. Transitively live via `_get_api_mode_imports`'s live callers. |
| 2026-03-22 | `d06f197` ("splitting server.py") | File split into `src/server/handlers/execution.py`. Both call sites in `handle_run_module` and `handle_run_operation`, and the `_get_api_mode_imports` -> `_validate_api_mode` chain, carried over **unchanged and still live**. Confirmed by grep of the new file's diff (lines 582, 711, 799, 1012, 1096, 1244 all present). Not the regression point despite being flagged as the prime large-refactor suspect. |
| 2026-04-06 17:00 | `1a3e67c` ("Simplify: Consolidate error responses and API mode handling") | **Two things happen in the same commit, pulling in opposite directions.** (a) `_get_casting_helpers_code()` is introduced and wired into `_get_api_mode_imports(api_mode, helpers_needed, injection_tier)`, which now appends a real `try: from casting_helpers import ... except ImportError: <HELPER_FUNCTION_DEFS fallback>` block to the imports string -- for `handle_run_module` this genuinely reached the `{{API_MODE_IMPORTS}}` placeholder substitution and thus the actual executed script (confirmed: `runner_script.replace('{{API_MODE_IMPORTS}}', api_imports_indented)` is retained, unchanged, in this diff). **This is the one moment the three-tier casting injection was truly live end-to-end**, for the `run_module` path. (b) In the *same commit*, hunk `@@ -924,502 +1080,6 @@` deletes `handle_run_operation` **in its entirety** (502 lines removed, 6 added) -- silently killing that function's separate `_get_api_mode_imports` call site. The commit message (7 numbered items, all about error-response consolidation, constants, type annotations, an import-error fix, and a pre-commit script update) **never mentions removing `handle_run_operation`** or losing an API-mode call site -- it is undocumented collateral of an otherwise-labeled "simplify" pass. |
| 2026-04-07 00:31 | `375a955` (Release v2.0.0) | CHANGELOG-only commit (`CHANGELOG.md`, 0 code changes). The three-tier injection was live in `handle_run_module` at the moment this release commit landed. |
| 2026-04-07 14:19 | **`d3e55d4`** ("enhance: Add rich logging format matching version 2.0") | **THE REGRESSION.** Removes the last live call: `api_imports = _get_api_mode_imports(api_mode, helpers_needed=helpers_needed, injection_tier=injection_tier)`, its `textwrap.indent(...)` step, and the `runner_script.replace('{{API_MODE_IMPORTS}}', api_imports_indented)` substitution. Replaces the runner-script template's `{{API_MODE_IMPORTS}}` placeholder with a **hardcoded literal**: `from flexlibs2 import FLExInitialize, FLExCleanup, FLExProject`. The diff's own added comment states the intent plainly: `# Note: API mode imports are now hardcoded in the template (flexlibs2)` and, at the template site, `# (Large script template - hardcoded imports to avoid placeholder/indentation issues)`. **Judgment on intent:** this was a deliberate, scoped fix for a real templating/indentation bug in the runner script -- not a decision to kill API-mode support or casting-helper injection. The commit message (about rich logging format + a Pydantic dict/model bug in `list_entities_in_category`) never mentions API modes, casting helpers, or the fact that `_get_api_mode_imports`/`_get_casting_helpers_code`/`_validate_api_mode` were about to become orphaned. **Textbook collateral damage inside a refactor that was labeled as something else**, exactly the pattern the task asked to look for -- just one commit later than the two commits (`d06f197`, `375a955`) flagged as prime suspects. |
| 2026-04-07 14:43 | `6602b5b` | Unrelated `project_name` param-name fix. No change to the three functions. |
| 2026-05-01 | `8de21e4`, `735d4ca` ("docs", "imgs") | Doc-only touches referencing `casting_helpers`/`_get_casting_helpers_code`; no code path restored. |
| 2026-08-14 | `a4665c8` | No changes to `execution.py`'s three functions (grep confirms zero hits). |
| 2026-09-09 | `3c89c19` (doc pruning) | Deletes `docs/THREE_TIER_INJECTION.md` and `docs/CASTING_SYSTEM.md`. No code changes to the three functions. The retirement was "decided" here in effect (docs gone) but left half-done -- dead code remained in `execution.py` for another 11 days. |
| 2026-09-18 | `0d3a791` (closes #144) | Adds `_probe_undoable_capability()` positioned "before `_validate_api_mode`" in the file -- purely a location marker, confirmed by diff: no hunk actually touches `_validate_api_mode`'s body. Unrelated to this feature. |
| 2026-09-20 | `fdbf8e9` (fix CI FieldWorks-less host) | Hardens `_validate_api_mode`'s exception handling (uninitializable library now returns clean `(False, reason)` instead of raising) and adds direct unit tests calling `execution_mod._validate_api_mode(...)`. Still zero production call sites -- test visibility only. |
| 2026-09-20 | `078d8e8` (this session's prior commit) | Formal retirement. Commit message states the codebase-verified fact independently: `_get_api_mode_imports` had "0 calls, 0 attribute references and no name in any string literal"; "the generated runner does not import `casting_helpers` at all"; and estimates it "had not [run] since at least 2.3.1" -- our archaeology sharpens this: the true death was `d3e55d4`, three months before the 2.3.1 release (`ffa3c0b`, 2026-07-04), within the still-unreleased-as-2.0.1 window (`VERSION` at `d3e55d4` already read `2.0.1`). |

---

## Was `casting_helpers.py` ever imported by the generated runner script?

**Yes, briefly and only as an attempted import that would virtually always fail over to inline
fallback code -- never as a successful module import.** From `1a3e67c` (2026-04-06) through
`d3e55d4` (2026-04-07), the `handle_run_module` runner-script template's imports block
contained a real `try: from casting_helpers import <names> except ImportError: <inline
HELPER_FUNCTION_DEFS>`. The generated temp script/subprocess had no `sys.path` entry pointing
at the package's `casting_helpers.py` (confirmed: no `sys.path` manipulation for this purpose
anywhere in the `1a3e67c` diff), so in practice the `import` branch would raise `ImportError`
and the **inline fallback function definitions** would run instead -- meaning the helpers
(`get_headword`, `safe_get_property`, etc.) genuinely existed in the executed script's
namespace and were callable by user code for that ~24-hour window, just never via the real
`casting_helpers.py` module. After `d3e55d4` hardcoded the import line, neither the module
import nor the inline fallback ever reached the runner script again -- matching the retirement
commit's finding that "the generated runner does not import `casting_helpers` at all," which
this archaeology confirms has been true continuously since 2026-04-07.

---

## Supporting evidence (commands run)

- `git show bfa8f86 -- src/server.py` -- birth, two live call sites via `{{API_MODE_IMPORTS}}`.
- `git show f721a96` -- `_validate_api_mode` birth, called only from `_get_api_mode_imports`.
- `git show d06f197 -- src/server/handlers/execution.py` -- file split, call sites intact.
- `git show 1a3e67c -- src/server/handlers/execution.py` -- casting-tier wiring added
  (live for `handle_run_module`); `handle_run_operation` (502 lines) deleted in the same
  commit, killing its call site.
- `git show 375a955 --stat` -- CHANGELOG-only, confirms no code change at v2.0.0 tagging.
- `git show d3e55d4 -- src/server/handlers/execution.py` -- the regression: placeholder
  substitution and `_get_api_mode_imports` call deleted; hardcoded `flexlibs2` import
  substituted with explicit "avoid placeholder/indentation issues" comment.
- `git show a4665c8 -- '*execution.py'`, `git show 3c89c19 -- '*execution.py'` -- zero hits,
  confirms no revival.
- `git show 0d3a791` -- confirms `_probe_undoable_capability` was only positioned near
  `_validate_api_mode`, not calling it; no functional change to the function.
- `git show fdbf8e9` -- hardens `_validate_api_mode`'s exception handling, adds unit tests
  calling it directly; no production call site added.
- `git log --oneline -- VERSION` and `git show d3e55d4:VERSION` (`2.0.1`) / `git show -s
  --format='%h %ad %s' ffa3c0b` (`2026-07-04`, v2.3.1) -- establishes the ~3-month gap between
  the true death and the retirement commit's conservative "since 2.3.1" claim.
