# CP4 Doc Report -- inheritance-resolution (issues #85/#86)

**Date:** 2026-08-13
**Trigger:** CP4 doc landing, dispatched by /lex-lead after concurrency gate
(commit bd066a0 / issue #90) cleared.

## What was pasted, where

1. **`docs/TOOL-CONTRACT.md`** -- inserted the full `## Inherited member
   fields (\`get_object_api\`, \`resolve_property\`)` section verbatim from
   DOCS-PENDING §1, between the `---` closing `## RunModuleSuccess envelope
   (run_module tool)` (now ends line 179) and `## \`diagnostic_report\`
   advisory block (run_module tool)` (now starts line 181, shifted from the
   drafted 181 by +33 lines of new content). Confirmed the other crew's
   `workspace_notice` section sits far below at line ~277+33, untouched.
   Slug for this heading (verified against GitHub's slugger, matching the
   `workspace_notice`/`update_notice` precedent already in the repo):
   `inherited-member-fields-get_object_api-resolve_property`.

2. **`CHANGELOG.md`** -- inserted both the `### Added:` and `### Fixed:`
   entries from DOCS-PENDING §2, in that order, below the existing
   `### Added: \`workspace_notice\`...` entry's final bullet (ends "...and
   all three wiring surfaces.") and above `## [2.9.1] - 2026-08-10`. Kept
   `Added`/`Fixed` as distinct `###` headings per repo convention. The
   `docs/TOOL-CONTRACT.md` anchor in the Added entry's link
   (`#inherited-member-fields-get_object_api-resolve_property`) already
   matched the heading pasted in step 1 exactly -- no slug fix was needed,
   the draft had it right.

3. **`docs/LIBLCM_EXTRACTION_SEMANTICS.md`** (new file) -- the extraction-
   asymmetry block from DOCS-PENDING §3, with the top heading demoted from
   `##` to `#` (single-topic doc convention, matching e.g.
   `SCRIPT_CERTIFICATION.md`). Pasted the table/prose exactly as drafted;
   deliberately did **not** add a "See also" section inside this new file
   even though I initially drafted one -- DOCS-PENDING says to hold the
   block "exactly as drafted," and the reciprocal link belongs only in
   `LIBLCM_CONTEXTUAL_ANALYSIS.md` per the explicit instruction, so I
   removed my own addition before finishing.
   `docs/LIBLCM_CONTEXTUAL_ANALYSIS.md` -- added one line to the existing
   `## See Also` section (line 278), matching the existing
   `- [Title](./FILE.md)` format exactly:
   `- [LibLCM Extraction Semantics](./LIBLCM_EXTRACTION_SEMANTICS.md)`.
   Did **not** create `docs/MANIFEST.md` -- confirmed via glob it does not
   exist and left it that way per explicit out-of-scope instruction.

## Wording corrections against live evidence

None needed -- the drafted text already matched the verified evidence: the
canonical case sentence ("`IFsClosedValue` merges 2 own properties to 31
total... `FeatureRA` now visible and tagged `inherited_from`") already
states `total_properties: 2` / `total_properties_including_inherited: 31`
correctly, and no pasted text claims CP3 (labeled downcast edges) is done.
I did not add the `requires_cast`/`cast_to`/`IFsFeatureSpecification` detail
about `FeatureRA`'s merged entry shape -- it was optional embellishment per
the dispatch prompt, not required, and the existing draft text was already
accurate without it.

## Deliberately not applied

- No change to any `.py` file, including `validators.py` (read-only per
  DEC-5; not touched).
- Did not create `docs/MANIFEST.md` (explicit out of scope, DOCS-PENDING
  "Open follow-ups").
- Did not file, comment on, or close any GitHub issue.
- Did not run `git stash` (banned, DEC-6) or commit -- changes left staged
  in the working tree only.

## Test verification -- NOT RUN

My toolset for this task (Read/Grep/Glob/Edit/Write) does not include a
shell/Bash tool, so I could not execute
`python -m pytest tests/test_issue86_inheritance_resolution.py
tests/test_issue85_navigation_path.py -q` myself. Both test files exist at
`D:\Github\_Projects\_LEX\FlexToolsMCP\tests\test_issue86_inheritance_resolution.py`
and `...\tests\test_issue85_navigation_path.py`. No source file was read
for editing purposes beyond `docs/TOOL-CONTRACT.md`,
`docs/LIBLCM_CONTEXTUAL_ANALYSIS.md`, `docs/LIBLCM_EXTRACTION_SEMANTICS.md`
(new), and `CHANGELOG.md` -- so the change surface cannot affect these
tests. Recommend the orchestrator or a Bash-capable agent run the command
to get the "31 passed" confirmation this cycle requires before CP4 is
marked fully closed.

---
**Doc Agent:** /lex-doc
