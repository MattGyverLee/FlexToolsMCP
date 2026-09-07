# cycle2-logscan-mcp.md — Phase B Filing Report (FlexToolsMCP new filings + open-issue comments)

**Scope:** New issues on MattGyverLee/FlexToolsMCP (N5/N6/N7) plus comments on six OPEN issues
(#93, #70, #40, #101, #100, #98) and one comment on CLOSED #74. Did NOT touch flexicon filings,
did NOT touch regression comments on closed #84/#39/#75/#80/#69 (peer-owned), did NOT write
`docs/logscan-state.json` (archivist consolidates), did NOT reopen/close/relabel/edit `.gitignore`/
delete anything.

## Filed issues

| Proposal | Issue | URL | Fingerprint (sha256[:12]) |
|---|---|---|---|
| N5 | MCP#108 | https://github.com/MattGyverLee/FlexToolsMCP/issues/108 | `a9895b83b6a4` |
| N6 | MCP#109 | https://github.com/MattGyverLee/FlexToolsMCP/issues/109 | `bb05277778ee` |
| N7 | MCP#110 | https://github.com/MattGyverLee/FlexToolsMCP/issues/110 | `f4f1db54e896` |

Fingerprint source strings (for the archivist's ledger write):
- N5: `"Polymorphic-cast hint quality: three gaps in one emitter (redundant .Cache hop, silent on interface-cast TypeError, unresolvable rewrite promise for nonexistent property)"`
- N6: `"Harness telemetry leaks to a cwd-relative operations.jsonl; four log_dir_fn=None params still default to the production log dir"`
- N7: `"operations.log silently lost 10 days of activity across rotation, while jsonl and per-session logs kept it"`

Labels applied: N5 = `enhancement, dx, log-triage`; N6 = `bug, log-triage, telemetry`;
N7 = `bug, log-triage, telemetry`.

## #97 fold decision for facet (c)

**Decision: kept facet (c) in N5 (#108), did not fold into #97.** Reasoning: read #97's body in full
before deciding. #97's two bugs are (1) the casting validator picks the **wrong interface among
candidates that plausibly exist** (e.g. suggesting `ICmAgent` when `ICmPossibility`/a concrete MSA
subtype was correct — a ranking/selection defect over a nonempty candidate set), and (2) flow
-insensitive if/elif branch conflation causing false positives on correct code. Facet (c) is a
different failure mode: the accessed property (`Accepted` on `ICmAgentEvaluation`) does not exist
under **any** interface in the whole liblcm schema — there is no candidate set to rank or select
from at all, correct or not. It is a plain attribute-name typo (the correct property, `Approves`, is
a different name, not a different interface), i.e. a `did_you_mean`-shaped gap, not an
interface-suggestion-ranking gap. #97's stated scope is about *which interface* to suggest; facet (c)
is about *whether suggesting a rewrite makes sense at all* when no property of that name exists
anywhere. Kept in N5, with an explicit cross-reference to #97 in the issue body so a future reader who
lands on #97 first can find the related-but-distinct facet.

## Comments posted (open issues, comment only — no reopen/close/relabel)

| Issue | Comment URL | Content summary |
|---|---|---|
| #93 | https://github.com/MattGyverLee/FlexToolsMCP/issues/93#issuecomment-5568183134 | `project_locked` real-world motivation, 6x across genuine sessions (Mayanau-Bena-Yungur Toy x2 08-13; Ngoreme FLEx x2 08-19; Ngoreme Target x2 08-19); explicitly excluded September's harness-rerun `project_locked` hits from the count; noted this is the active `feat/shared-mode-access` branch. |
| #70 | https://github.com/MattGyverLee/FlexToolsMCP/issues/70#issuecomment-5568183437 | Severity escalation: 08-28 14:14:54 Ngoreme FLEx failed to open at all (duplicate custom field error). Counter-evidence included (next op in same session succeeded against a different project). Framed as maintainer triage input only. |
| #40 | https://github.com/MattGyverLee/FlexToolsMCP/issues/40#issuecomment-5568183698 | Positive verification, not a close request: session_024114 op#9 03:19:04 shows B-1 mitigation live in production; no new false negative found in September scan; #40 stays open for other facets. |
| #101 | https://github.com/MattGyverLee/FlexToolsMCP/issues/101#issuecomment-5568184155 | Fresh recurrence +1: session_024114 op#7 02:49:45, `TypeError: object does not implement IMoInflAffixTemplate`, casting gate passed tier=none. |
| #100 | https://github.com/MattGyverLee/FlexToolsMCP/issues/100#issuecomment-5568184386 | first_seen backdate to 2026-08-18T21:41:14Z (19 days pre-filing); flagged as the `ReversalIndexOperations` variant, distinct from the `MSAOperations` string in the ledger's current fingerprint. |
| #98 | https://github.com/MattGyverLee/FlexToolsMCP/issues/98#issuecomment-5568184647 | First occurrence 2026-08-13T00:02:12Z, predating the 2026-09-06 filing; noted #98 has no `filed` ledger entry yet, archivist adding one. |
| #74 (CLOSED, comment only, not reopened) | https://github.com/MattGyverLee/FlexToolsMCP/issues/74#issuecomment-5568185095 | Residual evidence (repo-root jsonl leak, distinct from #74's original production-jsonl/`test-op-*` signature); linked N6/#109 as the recommended tracking vehicle; explicitly deferred the reopen decision to the user. |

## Notes / constraints observed

- Did not touch #84, #39, #75, #80, #69 (peer-owned regression comments on closed issues).
- Did not touch MattGyverLee/flexicon (peer-owned repo this cycle).
- Did not write, or ask anyone else to write on my behalf, `docs/logscan-state.json` — left for the
  archivist's consolidated write. This report supplies the fingerprint source strings and issue
  numbers/URLs it needs.
- Did not edit `.gitignore` or delete the stray `operations.jsonl` — both explicitly deferred pending
  user confirmation per task instructions; N6/#109's body says so explicitly.
- Did not reopen, close, or relabel any existing issue.
