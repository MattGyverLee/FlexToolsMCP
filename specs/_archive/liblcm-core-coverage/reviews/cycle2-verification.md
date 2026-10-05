# Cycle 2 Verification -- issue #136 accessor recovery

Verdict: **PASS** (one non-blocking caveat, item 8b -- unrelated working-tree state).
Commits diffed: `d50689f` (#135) -> `98c0fa4` (#136).

**1. Purely additive -- PASS.** Structural diff (entity/method/property sets, not raw
JSON lines): old=2026 entities, new=2026, zero removed, zero added; zero properties
removed/added; **147 methods added across 26 entities, 0 removed**. Raw `git diff`
looked non-additive (1086 `-` lines) only because of JSON key-order churn within
untouched entities (e.g. `MetaDataCache`) -- verified same content exists unchanged in
both commits.

**2. No get_Item/set_Item duplicates -- PASS.** Checked all 12 named entities in the new
index: zero `get_Item`/`set_Item` hits on any of them.

**3. ITsString exactly 8 recovered members -- PASS.** Diff yields exactly: `get_RunAt`,
`get_MinOfRun`, `get_LimOfRun`, `get_RunText`, `get_PropertiesAt`, `get_Properties`,
`get_IsNormalizedForm`, `get_NormalizedForm`. No more, no less.

**4. Field discipline -- PASS** across all 147 recovered entries (not just ITsString's 8):
every entry has `indexed`; `index_param_type` present iff `indexed==True`;
`get_IsNormalizedForm`/`get_NormalizedForm` are `indexed:false` with no
`index_param_type`; zero entries carry `is_property`. Zero violations.

**5. Signature correctness -- PASS**, verified against **live .NET reflection** on the
installed FieldWorks 9 `SIL.LCModel.Core.dll` (ground truth, not source-comparison):
`get_Properties(Int32 irun) -> ITsTextProps`, matching the index exactly.
Note: the cycle-2 task prompt's example text "`get_Properties(int ich)`" matches neither
the index nor the DLL -- actual parameter is `irun`; `ich` belongs to `get_PropertiesAt`
/ `get_RunAt`. Typo in the prompt, not a defect in the commit.

**6. Full pytest suite -- PASS.** 1394 passed, 8 skipped, 0 failed, 36 subtests passed
(51.34s).

**7. Live server check -- PASS.** `handle_get_object_api` in-process against the loaded
index (session `api_mode=liblcm`): `get_Properties` appears both with `summary_only`
unset (default) and explicitly `summary_only=True`, in both cases inside `methods`.

**8. Git status / flexicon isolation -- MIXED.**
- Neither `d50689f` nor `98c0fa4` touches any `flexicon` or `reports/` path -- PASS.
- "The three `*_flexicon-v4.7.0.json` files are present on disk" -- **FAIL**: they do not
  exist (working tree shows them deleted, replaced by untracked v4.8.0 files).
  Pre-existing working-tree state unrelated to #135/#136.

## Follow-up finding by the main session (root cause of 8b)

The cycle-2 `python -m flextoolsmcp.refresh` run re-deleted the v4.7.0 files that were
restored at the start of cycle 2. The underlying reason the versions disagree:

- `pip show pyflexicon` reports **4.7.0**, but that metadata is stale.
- `flexicon.__file__` resolves to `D:\Github\_Projects\_LEX\flexicon\flexicon` -- an
  **editable install of the sibling source repo**, not the PyPI wheel. The source tree
  has since been bumped to 4.8.0 while pip's recorded metadata still says 4.7.0.

So the **v4.8.0 index files are the correct ones** -- they match the live source the
server actually imports. The cycle-2 instruction to restore v4.7.0 was based on trusting
stale pip metadata. This is out of scope for #135/#136 and needs its own issue: either
reinstall so pip metadata matches, or decide the editable sibling checkout is canonical
and commit the v4.8.0 index files.

Source: lex-verification (items 1-8) + main session (root cause), cycle 2.
