# Cycle 8 -- Doc Agent: draft GitHub issues from live-session follow-ups (#93 Task 2)

**Output:** `specs/shared-mode-access/issues/DRAFT-issues.md` (new file, new
directory). Nothing filed -- drafting only, per hard constraint.

## Count drafted per repo

- **MattGyverLee/flexicon: 8 draft issues** (flexicon-1 through flexicon-8),
  plus **1 comment-not-issue** recommendation for the existing `undoable=False`
  concern (finding b) against **flexicon #236**.
  - Rows 2 (g) and 3 (unlabelled, write-side default-WS) recommended as **one
    combined issue** (flexicon-2), not two, on shared root cause and shared
    fix location.
  - Row 5 (unlabelled, `ReversalIndex.Name` derived-field) recommended as a
    **separate** issue (flexicon-4) -- same symptom surface as rows 2/3, but
    a distinct root cause (FLEx regenerating an owned field, not a WS-fallback
    bug) and a distinct fix (docs/removal, not a resolution change).
  - Net recommendation: **2 issues for what the source table lists as 3 rows**
    (2+3 merged, 5 separate), not 1 and not 3.
- **MattGyverLee/FlexToolsMCP: 4 draft issues.** Three ((k) `_pid_is_alive`,
  (a)/(d) `mutations_detected`, `ENABLE_SHARING_REMEDY` wording) marked **FIXED
  IN #93 THIS CYCLE -- file only if the user wants a standalone tracking
  issue**, per the task brief. The fourth (MCP-restart voids write-discovery)
  drafted as a **documentation note**, explicitly not framed as a defect.

## Duplicate-check results

**Could not run `gh issue list` against either repo** -- this drafting pass's
tool set was Read/Grep/Glob/Edit/Write only, with no shell/`gh` access. Every
draft's "duplicate check" line records this explicitly and points to the exact
command to run before filing. The one exception is flexicon #236, whose
identification came directly from the task brief (not independently
re-verified) and is recommended as a comment target, not a new issue.

## Could not substantiate

Several `file:line` citations are marked "not captured this session" -- the
evidence file gives behavior/output but not source locations, and the
flexicon repo is under a standing advisory lock for this crew (source not
read). Also **could not commit** the draft file -- no git/shell tool was
available to this agent invocation; the file is written but unstaged.
