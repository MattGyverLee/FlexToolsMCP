# after_specify domain gate (lex-domain), 2026-09-30

Limit: LCM and FieldWorks source were not available locally, so LCM-level
claims were not re-checked (now an Assumption the plan must close).

- BLOCKING, fixed: `SyncForeignChanges()` raises `FP_ReadOnlyError` in a
  read-only session and `FP_TransactionError` when undoable
  (`flexicon/code/FLExProject.py:1321-1334`). US5 and FR-030/031 now apply to
  write-enabled `undoable=False` runs only.
- Fixed: writing-system mutators named (`Create`, `Ensure`, `Delete`, `Set*`
  modifiers; `Duplicate` to check); custom-field schema mutators named
  (`CreateField`, `DeleteField`, `SetFieldName`); value setters excluded
  (FR-002a); raw writing-system manager calls keyed on receiver.
- Fixed: "three undo facts" corrected to four; the SHARED-MODE.md Undo
  section is extended, not new.
- For planning: generic close-FieldWorks fallback at `execution.py:1267`, and
  similar wording at `write_ladder.py:157`; contract count is 46
  (`TOOL-CONTRACT.md:82`, `tests/test_response_contract.py:525-530`), with
  stale "44 codes" text at `TOOL-CONTRACT.md:721`; `tool_definitions.py:133-142,
  661, 718` mention undo; parse-filing writing-system reach is unconfirmed.
