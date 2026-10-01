# Cycle 6 -- Doc Agent: SPEC amendment ahead of T5.1-T5.6 implementation

**Edited:** `specs/shared-mode-access/SPEC.md` only. No source/test files touched.

## What changed

- **Section 3** split into 3a (Class A, `refused`) / 3b (Class B,
  `silently_lost`) / 3c (unclassified: possibility lists, reversal indexes)
  / 3d (unreachable: data migration, Send/Receive, backup/restore/delete --
  explicitly excluded from `EXCLUSIVE_ONLY_OPERATIONS`). Added the Class B
  mechanism paragraph (`PerformCommit` gate, `HaveAnyModifiedCustomProperties`
  self-update, `CommitLogRecord`'s missing field) and the `XWorksViewBase
  .cs:715` precedent, verbatim per the rulings.
- **T5.1** fixed: dropped `UpdateField` (doesn't exist in flexicon 4.5.2),
  named `SetFieldName` as the analogue; kept the AST-detection note for
  the four raw-LCM names; added the custom-fields-only scoping note.
- **T5.3** now states the three lex-lead rulings verbatim (insertion seam,
  precedence, detect-first/probe-second), with line numbers re-verified
  against the current tree, not copied from the handoff.
- **T5.5** rewrote the code-count claim with re-grepped, verified locations.
- **New T5.6** -- align the `execution.py:1207-1216` generic fallback with
  CP5's `open_shared` message; `build_lock_diagnosis()` returns `None` for
  `open_shared`.
- **Section 8** gained P2-4 and P2-8 (the two QC items lex-lead declined to
  action this cycle).

## Re-grep result on the code-count claim

SPEC said "16 codes." Confirmed **18 today**, verified fresh (not trusted
from the handoff): `docs/TOOL-CONTRACT.md:69`, `tests/test_response_contract
.py:9` (docstring) and `:234` (class docstring), `ALL_ERROR_CODES` at
`tests/test_response_contract.py:200-230`. Also found a fourth lockstep
location the handoff didn't name: `response_models.py:10` ("18 per-code
detail models") -- already correct, added to T5.5's bump list. Confirmed
`response_models.py:361` carries no count wording (handoff's caution was
correct). CP5 makes it **19** everywhere.

## Line-number drift found (post cycle-6 commits 520dba4/ad1d50c)

Handoff cited `execution.py:4262` for the insertion seam; current tree has
the CP4 refusal ending at `:4303` and `open_shared` beginning at `:4305` --
seam is now `:4304`, before backup at `:4346`. `_live_fw_peer` is at `:4186`.
Recorded the shift in SPEC and flagged it as re-verify-again-before-landing.

## Not verified / left for programmer

- Whether `RenameDatabase` truly belongs in T5.1's raw-name AST-detection
  list given Class A doesn't require gating -- kept as instructed (matches
  the literal handoff text) rather than relitigating; flagged inline as a
  scoping tension for the implementer to notice.

Commit prepared: "docs: amend SPEC Section 3 + CP5 tasks ahead of
implementation (#93)" -- not yet made (see below).
