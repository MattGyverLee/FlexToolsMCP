# Contract -- `flextools_grammar_health`

**Checkpoint:** CP1 | **Spine:** in-process read | **Annotation:** `READ_ONLY_SAFE`
| **Contract version:** `tool-responses/1.0` (additive; no bump)

Pure-LCM static scan for path-multiplying grammar properties (SPEC 9.5.5). No parse,
no export, no subprocess to `hc`, no `HCParser`. The primary G4 instrument and the
cheapest thing in the feature.

---

## Input

`GrammarHealthInput` in `server/models.py`.

| Field | Type | Default | Notes |
|---|---|---|---|
| `project_name` | str or null | `null` | Falls back to `session_state.project_name`, as every other project-touching tool does |
| `checks` | list[str] or null | `null` | Restrict to named `check_id`s. `null` runs all implemented checks |
| `limit` | int | 20 | Per-check cap on `objects[]`. SPEC S7: responses summarise, never inline the full set |

## Output

```json
{
  "_contract": "tool-responses/1.0",
  "status": "ok",
  "op_id": "...",
  "project": "<name>",
  "checks_run": ["zero-surface-morph-repeatable", "..."],
  "checks_skipped": [{"check_id": "...", "reason": "lcm_name_unverified"}],
  "findings": [
    {
      "check_id": "zero-surface-morph-repeatable",
      "spec_row": 1,
      "count": 3,
      "measured": "3 allomorphs have an empty surface form",
      "evidence_basis": "PanGloss measured 425x on one five-word slice",
      "objects": [
        {"hvo": 12345, "class_name": "MoStemAllomorph", "label": "-", "goto_url": "silfw://..."}
      ]
    }
  ],
  "next_step": null
}
```

**Row 1's `measured` wording is deliberately unconditional at CP1.** An earlier
draft of this example read "are reachable from an optional slot", which CP1 does
not measure: the slot-reachability walk (slot -> `Affixes` -> MSA -> owning entry
-> `AlternateFormsOS`) is deferred, because the allomorph -> owning-entry hop is a
known flexicon read gap (research D5, tasked flexicon-first under S9). CP1 counts
every zero-surface `IMoForm` regardless of position, so `measured` must not claim
slot-conditioning until that walk lands. The conditioned phrasing returns at CP2.

### Forbidden in the response

Enforced by test, not convention (SPEC 9.5.3, 9.5.7, D7):

- **No scalar score.** No `score`, `grade`, `health`, `rating`, `severity`,
  `priority` or `rank` at any nesting level.
- **No ordering by magnitude.** `findings` is ordered by the 9.5.4 row order --
  highest *measured yield* first, fixed at authoring time -- never sorted by `count`.
- **No total.** Counts are never summed across findings.
- **No verdict wording.** `measured` states what was counted. The strings
  `"invalid"`, `"incorrect"`, `"wrong"`, `"error"`, `"defect"` and `"broken"` must not
  describe a finding. A G4 finding names a **suspect**.
- **Never derived from wordforms or analyses.** The scan reads grammar objects only
  (SPEC 3.1). Reading `IWfiAnalysis` from this tool is a bug, not an optimization.

### `checks_skipped`

A check whose LCM property names are not yet verified is **skipped and named**, never
guessed at. At CP1 that is rows 3 (metathesis half), 5 and 7 until D4's three
outstanding names are confirmed. A silently omitted check reads as "your grammar is
clean", which is the SPEC 8.4 failure applied to our own surface.

### `next_step`

`null` on a direct call. The conditional *proposal* of this scan lives on the parse
tools (SPEC 9.5.5: offered when a parse that should have been quick was not), and
those ship at CP2 -- so at CP1 nothing proposes it and routine calls remain available
to anyone who wants one.

---

## Errors

| Code | When |
|---|---|
| `parser_engine_mismatch` | Never. **This tool does not call `check_active_parser()`** -- it runs no parser and reads no engine-specific object, so refusing on engine would be a gate the spec does not ask for. SPEC 10.2 names only `try_word`, `parse_text` and `parse_sandbox` as callers of the helper |
| `project_not_found`, `project_locked`, `project_drive_unavailable`, `project_path_mismatch` | Reused unchanged from the existing contract |

---

## Behavioural guarantees (asserted by test)

- Constructs no `HCParser` and runs no parse; the project is left untouched.
- Opens no `LcmCache` in the MCP server process -- the scan runs in the
  generated-module subprocess (research D1).
- Output contains no scalar score at any depth.
- A null allomorph attachable at any position is reported as a suspect with its
  count, never as a defect.
- Disabled rules (`IPhSegmentRule.Disabled`) are excluded before counting.
