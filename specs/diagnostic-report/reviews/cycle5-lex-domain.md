# Cycle 5 -- Domain Expert review (CP2 E2 normalization vs privacy guarantee)

**E2 normative gate: PASS.**

`src/flextoolsmcp/server/diagnostic/normalize.py` is genuinely path-scoped, not
a document-wide replace. `_PATH_TOKEN_RE` (lines 60-64) only matches
drive-letter (`C:\...`), UNC (`\\server\...`), or POSIX home-rooted
(`/home|/Users|/root/...`) tokens -- ordinary prose never matches. Grep and
full-file read confirm no `str.replace`/blanket `re.sub` of the bare
username/home string anywhere in the module; all substitution happens inside
`_sub()` via `_PATH_TOKEN_RE.sub`, operating only on already-matched tokens.

**Section 12 acceptance case: PASS.** `test_e2_username_substring_in_lexical_data_survives`
(lines 329-343) exercises exactly the spec's own example (`C:\Users\matt\...`
normalized to `~\...`, gloss "Matthew's toolbox" untouched). The companion
`test_e2_document_wide_replace_would_have_failed_this_test` (346-354)
independently proves the fixture is meaningful by showing a naive
case-insensitive `re.sub("matt", ...)` *does* corrupt "Matthew's toolbox" --
so the survival assertion isn't vacuous.

**Segment-boundary correctness: PASS.** `_normalize_path_token` (115-126)
requires the byte after the home-path prefix match to be a separator or
end-of-string before substituting `~`; without it, `C:\Users\matt` would
wrongly swallow `C:\Users\matthew\...`. `test_e2_sibling_directory_not_falsely_prefix_matched`
(358-368) covers this directly and asserts the sibling path is preserved
verbatim. Username removal is additionally segment-exact (split on `\`/`/`,
case-insensitive equality, never substring), so `matt` never matches segment
`matthew` even inside a genuine path token -- double protection, confirmed by
code and by the sibling test's own reasoning.

## Judgment calls

**(a) MAX_REPORT_OPS: keep-most-recent-verbatim, summarize-earlier -- PASS.**
Spec section 5 mandates only "no silent drop," not a selection policy. Keeping the
failure/resolution tail verbatim (closest to reproduction) while
summarizing earlier discovery/setup steps is the domain-correct choice for
maintainer reproducibility; the full uncapped slice still rides along in the
JSONL appendix, so no information is actually lost.

**(b) Header fallback note on rotation-recycled block -- PASS.** Per section 3.2,
the session log is the primary source of truth; re-deriving versions
out-of-band risks reporting environment values that disagree with what was
actually running at incident time. Honest omission is the safer diagnostic
posture than a guessed header.

---
**Reviewed by:** Domain Expert Agent
