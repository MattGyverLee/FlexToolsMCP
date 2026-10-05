# Pattern audit: "close FieldWorks" guidance on a shared project (T019)

Bug class: a message tells the user to close FieldWorks when FieldWorks holds
the project with sharing on (`open_shared`), where closing it is neither needed
nor the cause of the failure (spec FR-011, FR-013).

Sweep: `grep -rni "close fieldworks\|close flex" src/` plus the plan's
candidate list. Date 2026-09-30.

| Site | Fires on `open_shared`? | Outcome |
|---|---|---|
| `handlers/execution.py` `_diagnose_project_open_error` generic hint ("Close FieldWorks and retry") | Yes, before this change (`build_lock_diagnosis` returns None for `open_shared`) | **Fixed**: `open_shared` now gets "sharing on, the lock is not the cause; closing FieldWorks is not required". The generic text stays for `free` (another program holds the file) and a failed probe |
| `write_ladder.py` refusal guidance fallback ("Close FieldWorks, then retry") | No (reached only for `open_exclusive` / `held_by_other` with no remedy) | **Reworded** so it no longer assumes FieldWorks is the holder; names enabling sharing |
| `write_ladder.py` `open_shared` advisory ("Custom-field and writing-system changes are NOT safe ...") | Yes | **Fixed**: now points to the `requires_exclusive_access` refusal (FR-013) |
| `project_discovery.py:398` "Close FieldWorks (or delete the .lock file ...)" | No: the branch runs only when the live holder is FieldWorks **and** sharing is off | **Kept**: correct advice for `open_exclusive` |
| `project_discovery.py:419` | Comment only | Kept |
| `handlers/teardown_recovery.py:180` "Close FieldWorks/FLEx and any other SIL apps" | Independent of the project lock: it fires on an abandoned machine-wide writing-system store mutex | **Kept**: closing every SIL app that uses the WS store is the real remedy for that mutex |
| `exclusive_access.py`, `session.py` (new text) | Yes, by design | Kept: the exclusive-only refusal is the one case where closing FieldWorks is required; the hint explicitly says not to ask for ordinary edits |
