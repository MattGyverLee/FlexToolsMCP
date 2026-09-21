# Original Author Review — CP2b Delta 6/7 prose vs. shipped code

**Date:** 2026-09-20
**Score:** 6/10
**Status:** CONCERNS

## Rationale

Delta 6 and Delta 7 read like this spec's other deltas — belief, fact, and why the gap mattered — not like changelog entries wearing a spec's clothes; that register goal is met. The "piece 1"/"Delta 6" numbering collision was real but confined to the cycle-1 archivist memo and cycle-2 doc-agent's note to self — it never reached spec.md, tools.md, CHANGELOG.md or TOOL-CONTRACT.md, all four of which use "Delta 6"/"Delta 7" (or plain prose) consistently under the settled reading. The defect is truthfulness: `_summarize_trace`'s Returns clause and every outward description of it (spec.md Delta 6, tools.md, TOOL-CONTRACT.md) describe a clean two-shape outcome ("derived from the trace document already in hand," "provably identical... not an approximation") that omits the third code path — a rootless document silently manufactures `{"parsed": False, "analysis_count": 0}` from nothing, not derived from anything. Worse, the comment guarding that branch argues the fabrication is *not* inventing a fact ("Treated the same as zero `<Analysis>` — never as an error"), which is the opposite of the judgment already settled for cycle 4. The contract text is also one clause short of the completeness the checkpoint exists to deliver: it says `restricted` "never" carries `parsed`, but never states outright that the key is *absent*, not present-and-false.

## Findings and rewrites

1. **Truthfulness gap — rootless branch has no outward mention.** `worker_main.py` `_summarize_trace` docstring (`:839-843`):
   > `Returns:`
   > `` `{"parsed": bool, "analysis_count": int}` when the document has no ``
   > `` `<Error>` (whether or not it has any `<Analysis>`), or ``
   > `` `{"parse_error": str}` alone when it does.``

   Replacement — add the third, real branch and flag it as known debt:
   > `Returns:` ... (as above), or a defensive `{"parsed": False, "analysis_count": 0}` when the document has no `Root` at all — manufactured, not derived, because there is nothing to derive from; ruled in cycle 4 to become `parse_error` instead (see comment at the `root is None` check).

2. **The comment is not just silent, it argues the wrong conclusion.** `worker_main.py:846-850`:
   > `Defensive only: a document with no root carries no analyses and no error to report. Treated the same as zero <Analysis> -- never as an error, which would be inventing a fact the document does not contain.`

   This is backwards: a rootless document cannot be read at all, so *asserting* zero `<Analysis>` is the invented fact, not avoiding one. Replacement:
   > `Defensive only, and arguably wrong today: a document with no Root cannot be read, so calling it parsed: False asserts something this branch has no basis for -- the same ambiguity <Error> exists to resolve, just triggered a different way. Ruled in cycle 4 to become parse_error; left as parsed: False here only until that lands.`

3. **spec.md Delta 6 overstates derivation as universal.** `:180-181`:
   > `The fix derives the answer from the trace document already in hand -- no second parser call.`

   This is true for two of three branches. Add one sentence naming the exception rather than let a reader assume full coverage:
   > `...no second parser call, except the rootless branch, which has no document to derive from and currently fabricates parsed: False; that is tracked to close in cycle 4, not this one.`

4. **Contract tables leave "absent" implicit.** `contracts/tools.md:130` and `docs/TOOL-CONTRACT.md:271` both say:
   > `**never** parsed/analysis_count -- these names are reserved for "does this word parse at all,"...`

   A caller who defaults missing keys to `False` reproduces exactly the bug this checkpoint fixed elsewhere. Append to both:
   > `-- the keys are absent from the object entirely, never present and set to false.`

5. **No action needed:** CHANGELOG.md and TOOL-CONTRACT.md use no delta numbering at all, so the cycle-1/cycle-2 "piece 1" collision cannot reach them — confirmed, not a finding.
