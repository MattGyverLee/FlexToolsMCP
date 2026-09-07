# Cycle 10 -- cast_to_concrete phantom remedy: per-symbol verdict

Tested against **pyflexicon 4.5.2** (editable install, `D:\Github\_Projects\_LEX\flexicon`),
runtime introspection, not grep. The handoff's "five places / nonexistent"
framing CONFLATED two symbols with **different** statuses. File two issues.

## Symbol A -- `CastingOperations.cast_to_concrete` : PHANTOM [FAIL]
`from flexicon import CastingOperations` -> `ImportError`. `grep -rn CastingOperations
--include=*.py` over the whole flexicon repo: **zero hits**. No class under any
other name; `dir(flexicon)` has no cast-ish member. Not a rename -- it never existed.
Blast radius: **advisory strings only** (5 sites, not 4 -- lead missed discovery.py:168).

## Symbol B -- `flexicon.code.lcm_casting.cast_to_concrete` : EXISTS, MIS-CALLED [WARN]
Module imports OK; function real at `lcm_casting.py:408`. But signature is
`cast_to_concrete(obj)` -- **ONE arg**. `signature.bind(o, o)` -> "too many
positional arguments". Every shipped call site passes **two**. Separately,
`from flexicon.code.lcm_casting import ... ILexEntry` -> `ImportError`: `ILexEntry`
is function-local inside `_ensure_interfaces()`; `hasattr(m,'ILexEntry')` is False
before *and after* calling it. So shipped template code **crashes**.

---
## ISSUE DRAFT 1 -- Phantom `CastingOperations` advertised in 5 user-facing hints
`CastingOperations` does not exist in pyflexicon 4.5.2 (verified: ImportError +
zero repo occurrences). Users following the hint get `ImportError`.
Sites (all advisory strings, blast radius LOW):
- `src/flextoolsmcp/server/handlers/api.py:1621` (`flexicon_helper`)
- `src/flextoolsmcp/server/handlers/api.py:1636` (`example` -- code-shaped, copy-pasteable)
- `src/flextoolsmcp/server/handlers/discovery.py:163` (`suggestion`)
- `src/flextoolsmcp/server/handlers/discovery.py:168` (`casting_hint`) **[missed in handoff]**
- `src/flextoolsmcp/server/validators.py:3642` (`_POLY_ITERATION_NOTE`)

Correct remedy: `from flexicon.code.lcm_casting import cast_to_concrete` then
`concrete = cast_to_concrete(obj)`. Note `validators.py:3927/3935` already word it
correctly -- copy that phrasing.
Test hazard: `tests/test_issue48_inline_casting.py:92` asserts only the substring
`"cast_to_concrete"`, so it passes both before and after -- it will not catch a
regression. Tighten to assert the full correct call.
PRE-EXISTING (not CP-D's doing). Same failure class as #103 and the
import-advertising surfaces: a remedy advertised without verifying it exists.

## ISSUE DRAFT 2 -- Shipped LibLCM template crashes: wrong arity + non-exported `ILexEntry`
`cast_to_concrete` is REAL but takes one arg; the template passes two, and two docs
import a name the module never exports. `flextools_get_module_template(flavor='liblcm'|'advanced')`
serves `3-liblcm-template.py` (`handlers/admin.py:102-104`), so this is code users run.

SEVERE -- live code, `TypeError` at runtime:
- `templates/3-liblcm-template.py:85, 113, 186`

SEVERE -- copy-paste examples in shipped templates:
- `3-liblcm-template.py:258, 299, 305, 330` (2-arg)
- `templates/00-FLAVOR-GUIDE.md:110, 163` (`ImportError` on `ILexEntry`); `:118, 164, 179` (2-arg)
- `templates/README.md:74` (`ImportError`); `:77, 158` (2-arg)

BENIGN: `templates/README.md:128` (prose). ALREADY CORRECT: `3-liblcm-template.py:32`
(imports interfaces from `SIL.LCModel`, with a comment naming this exact trap --
so the fix is known in-repo and simply wasn't propagated); `validators.py:3927, 3935`.

Fix: drop the second argument everywhere; in the two docs replace the import with
`from flexicon.code.lcm_casting import cast_to_concrete` + `from SIL.LCModel import ILexEntry`.
Corroboration: `user-logs/Dennis-Logs/` shows real generated scripts using both the
phantom `CastingOperations.` form and `flexlibs2.code.lcm_casting` -- users hit this.
PRE-EXISTING. NOT FILED -- awaiting lead authorization.
