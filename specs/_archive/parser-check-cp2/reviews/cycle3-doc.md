# Cycle 3 Doc Pass -- QC wording fixes (cycle2-qc.md section 2)

Scope: `specs/parser-check-cp2/spec.md` only, two precision edits. No decision
changed, no field/enum set changed.

## Edit 1 -- FR-037 field order

Parent authority read at `specs/parser-check/SPEC.md:1987`:
`morph`, `position`, `resolved_to` (`none`\|`ambiguous`\|`no_msa`), `candidates`, `hint`.

**Before:**
> ... refusal MUST carry five detail fields -- `morph`, `candidates`, `position`,
> `hint`, and `resolved_to` (one of `none`, `ambiguous`, or `no_msa`) -- matching
> the parent specification's contract, since ...

**After:**
> ... refusal MUST carry five detail fields -- `morph`, `position`, `resolved_to`
> (one of `none`, `ambiguous`, or `no_msa`), `candidates`, and `hint` -- matching
> the parent specification's contract, since ...

Field set, enum values, "raised from 22" clause, and the silent-narrowing
justification clause are unchanged. The "matching the parent specification's
contract" phrase is kept verbatim (not softened) -- order now actually matches.

## Edit 2 -- FR-011 gate/tag conflation

D4 read at spec.md:641-676 confirms: the evidence gate (three-tier behavioural
proof) is what CP2b may not start without; the release tag/creation are named
explicitly as "the maintainer's acts, not the crew's" -- a separate, later-or-
concurrent act.

**Before:**
> This release is the exit gate of the predecessor phase described in Decision
> D4: nothing on the assistant side is built, let alone tested, until this
> release exists, and pushing the release tag is a maintainer act, not an
> automated one.

**After:**
> This release's existence and version alignment are a precondition for the
> assistant-side work, not the gate that permits it -- the gate is Decision
> D4's evidence requirement, satisfied on its own timeline. Pushing the release
> tag is a maintainer act, not an automated one.

Closing clause preserved verbatim (only sentence-initial capitalization
changed: "and pushing" -> "Pushing"). Two sentences, no new requirement or
decision added.

## Step 3 -- 180-char cache check

- **FR-037**: cached title in `.spec-context.json` truncates at char 180
  mid-way through "...raised from 2" (confirmed by manual count). Edit begins
  ~100 chars later, at "morph`, `position`...". **Falls past 180 -- no resync.**
- **FR-011**: cached title truncates at char 180 mid "...bundled index of
  that". Edit begins after "library MUST name the same released version.",
  well past that point. **Falls past 180 -- no resync.**

`.spec-context.json` was not touched, per the "if and only if" clause.

No other files modified.
