# Cycle 8 -- QC: CP-D (6e35204, 71576a6, ce267e0, eb66ac4)

All numbers are my own runtime measurements, not the reports'.

## P0 -- blocks CP-D
**P0-1 Contract drift.** `docs/TOOL-CONTRACT.md:207-210` still says `fix` "is
built from `defined_on[0]`, an arbitrary selection -- see issue #97 Bug 1,
**not yet repaired**". 6e35204 says `closes #97 Bug 1`. Cycle-7's audit
claimed no `fix`/`Cast ` reference here -- falsified; its grep missed the
backticked form (same shape as 8f72b9f). Rewrite those 4 lines to the
resolved / ambiguous / degrade trichotomy.

## P1
**P1-1 D-3's rationale is factually wrong** (`handlers/api.py:700-703`;
`tests/test_issue100_access_path.py:~398`): "MSAOperations is the one flexicon
Operations class that IS facade-only". Measured (flexicon 4.5.2 +
`_extract_facade_access_paths`): of 64 `*Operations` in
`flexicon_api_v4.5.2.json`, **13 are facade-only** and 8 more are unreachable
by either route. The no-op *conclusion* holds (none is in KNOWN_OPERATIONS),
but the comment understates the hazard 13x and
`test_msa_operations_deliberately_excluded...` pins the wrong fact. Fix the
wording; assert over the real facade-only set.

**P1-2 The truncated head reintroduces alphabetical bias**
(`validators.py:4113-4130`). Across the 136 ambiguous props: 89 have 2
candidates, 26 have 3, 4 have 4, **17 exceed the cap**. `Name` (36) renders
`one of: ICmAgent, ICmFile, ICmFilter, ICmFolder, +32 more` -- ICmAgent first,
the very pairing #97 cited. A model picking the first is back in the Dennis
failure.

**P1-3 The escape hatch is circular; `context_entity=...` unfillable.**
`resolve_property` with `property_name` only (`handlers/api.py:1539-1620`)
returns the same `defined_on` plus a generic "cast on obj.ClassName" hint;
with `context_entity` it needs the answer as input. `context_entity=...` is
literal `Ellipsis` -- copied verbatim it is valid Python meaning nothing
(precedent for filling it: `validators.py:1413`).

### Item-3 proposals
- `>6` candidates: emit **no list** -- `Cast {obj} to the concrete interface
it actually is. {N} interfaces declare '{prop}' -- too many to guess.
Determine it from where {obj} came from (the wrapper method's return type), or
cast at runtime: CastingOperations.cast_to_concrete({obj}) (dispatches on
{obj}.ClassName).`
- `2..6`: keep names, kill first-pick -- `... one of (ALPHABETICAL, not ranked
-- do NOT pick the first): A, B, C. Choose by {obj}'s provenance, or use
CastingOperations.cast_to_concrete({obj}).`
- Cap 4->6 covers 123/136 fully. Never emit bare `context_entity=...`: omit
the optional arg, or `context_entity='<the interface {obj} actually is>'`.

## P2
- **Docstring over-claims** (`versioning.py:277-295`: entry creation bumps dir
mtime "on both Windows and POSIX ... exactly the signal we need"). Measured
**58/200 (29%)** rapid double-writes left `st_mtime` unchanged. Correct it.
The race is real but narrow: in-process refresh clears the cache explicitly
(`server.py:351`), so only out-of-band writers are exposed and it self-heals
on the next dir change -- not a P0. D-2 does give the test a guarantee
production lacks, so same-tick invalidation is now covered nowhere.
- `tests/test_flextools_health.py:~40` claims "~15-25% ... confirmed
empirically"; measured rates were 12.5% and 2.5%. Unsupported range.
- `validators.py:3488-3502` **duplicates** rather than reuses the cleaning at
:3441-3447 (its comment claims otherwise). Extract `_clean_interface_head()`.
- **`fix` is heterogeneous**: the known-pattern tier emits pasteable code
(:3910-3926, documented `docs/CASTING_SYSTEM.md:34`); the new value is prose
with a tool call -- pasted-into-script risk. Move prose to `flexicon_helper`.

## P3
- Both helpers `IndexError` on a whitespace-only `defined_on` entry (:3443,
:3495); none shipped (latent).
- `["ILexSense","ILexSense (raw LCM)"]` -> `cast_interface None` but one
candidate -> `one of: ILexSense -- ambiguous`. 0 props affected today.
- `_bump_dir_mtime` writes future-dated mtimes (+1s/write).
- Extract `fix_msg` into `_fix_message()`; only end-to-end tested.
- Tripwire `skipTest`s when flexicon is unimportable (so it is unguarded in a
flexicon-less CI); test 2 is near-tautological given test 1.

## Independent 43/43 re-check -- CONFIRMED
`KNOWN_OPERATIONS` is a 43-member set; `OPERATIONS_CLASSES is
KNOWN_OPERATIONS`. `hasattr` **and** real `getattr` against installed
flexicon: **43/43 importable, 0 failures**; 42/43 also carry a facade path.
`"MSAOperations" in KNOWN_OPERATIONS` False, `hasattr` False, facade
`project.MSA`. **Design call: the documented no-op is right** for
`api.py:689`; widen the tripwire per P1-1. That tripwire is genuine
(hasattr-based, fires on any added facade-only member), not a tautology.

## Item 4/6
`_pick_cast_interface`, `_RECEIVER_NAME_TO_INTERFACE` and
`_build_cast_candidate_set` are **untouched**: the range has one removed src
line (the old `fix`), and `git diff 250469c..HEAD -- tests/` has **zero**
removed lines -- nothing flipped or deleted. Bare-snippet invariant verified
live: a module-level snippet with no `Main` yields the same 2 issues and
byte-identical `fix` strings as the wrapped form. 62 + 70 passed.

## Item 7 -- evidence audit
- **D-1 strong**: two mutations, quoted assertions, revert-to-green;
FeatureRA non-repro disclosed honestly. Only its consumer audit failed --
P0-1 sits in the file it called clean.
- **D-2 agreed weak**: 0/40 after 1/40 is not evidence (~120+ runs needed).
Only the 5/40 test carries signal; the mechanism is supported by my 58/200 --
the evidence that should have been offered.
- **D-3 right method, over-generalized**: a claim about all flexicon
Operations classes drawn from a check covering only the 43.
