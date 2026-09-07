# cycle2-logscan-flexicon.md — Phase B Filed (MattGyverLee/flexicon only)

**Scanner:** /lex-logscan (Phase B, cycle 2, filing authorized)
**Scope:** MattGyverLee/flexicon repo only. MattGyverLee/FlexToolsMCP owned by a peer agent
this cycle and not touched here. `docs/logscan-state.json` not written — a consolidated
ledger write is the archivist's job after both flexicon and MCP filings land.

Source briefs read before filing:
- `specs/logscan-2026-09-07/reviews/cycle1-logscan-august.md` (PROPOSED NEW ISSUES #1, #2;
  regression #6 re flexicon#34)
- `specs/logscan-2026-09-07/reviews/cycle1-logscan-september.md` (PROPOSED NEW ISSUES #1, #2)

Local flexicon checkout used for source verification:
`D:\Github\_Projects\_LEX\flexicon` (all cited line numbers confirmed against this checkout
before filing).

## Duplicate checks performed

`gh issue list --repo MattGyverLee/flexicon --state all --search "<terms>"` for:
`AllomorphOperations GetForm IMoForm`, `DataNotebookOperations GetObject`,
`KeyNotFoundException identity map Object`, `WriteEnabled writeEnabled`,
`identity map GetObject`, `AllomorphOperations`. No exact duplicate found for any of the
four filed issues. Closest related-but-distinct hits, read in full and confirmed
non-duplicate:
- **flexicon#176** ("Pattern A sibling sweep — typed Owner casts...") — 11-site sweep;
  does not include `AllomorphOperations.__GetAllomorphObject` or
  `DataNotebookOperations.__GetRecordObject`.
- **flexicon#133** ("Audit gap on #98/#116... InflectionFeatureOperations.Delete and
  DataNotebookOperations.Delete also silent no-op") — same file (`DataNotebookOperations.py`)
  but a different method (`Delete`'s `hasattr(owner, ...)` no-op), not
  `__GetRecordObject`'s raw `GetObject` call.
- **flexicon#193** (closed) — the "double `.Cache`" root-confusion precedent cited as
  cross-reference in N2, not a duplicate of it.
- **flexicon#213/#214/#98** — other `AllomorphOperations` bugs (`Create`'s morph-type
  handling, `Delete`'s hasattr no-op) — different methods, not `__GetAllomorphObject`.

No duplicates found → no issue was skipped/commented-instead-of-filed.

## Filed issues

| Proposal-id | Issue | URL | Fingerprint (sha256[:12] of canonical signature) |
|---|---|---|---|
| N1 | flexicon#260 | https://github.com/MattGyverLee/flexicon/issues/260 | `70b131eb301c` |
| N2 | flexicon#261 | https://github.com/MattGyverLee/flexicon/issues/261 | `39c206b4c315` |
| N3 | flexicon#262 | https://github.com/MattGyverLee/flexicon/issues/262 | `5dc1029cc399` |
| N4 | flexicon#263 | https://github.com/MattGyverLee/flexicon/issues/263 | `abb91b059956` |

Canonical signature strings hashed:
- N1: `AllomorphOperations.__GetAllomorphObject does not cast to IMoForm before GetForm accesses .Form`
- N2: `AttributeError: LcmCache has no attribute GetObject in DataNotebookOperations.__GetRecordObject`
- N3: `FLExProject.Object raises undocumented KeyNotFoundException for stale-but-well-formed GUID instead of returning None`
- N4: `AttributeError: FLExProject has no attribute WriteEnabled (stub declares capitalized, impl is lowercase writeEnabled)`

All four filed with labels `bug, log-triage`. N1's body cites the sibling-sweep target
(`__GetEnvironmentObject` at `AllomorphOperations.py:1114`) and cross-references closed
sweeps #133/#176; a follow-up comment on #260 links forward to #261 once #261's number was
known. N2's body cross-references closed #193 and #133/#176, and links back to #260.

## Comments posted (no state change, no reopen/close/relabel)

| Target | Type | URL |
|---|---|---|
| flexicon#34 (CLOSED) | Regression note, explicitly not a reopen request | https://github.com/MattGyverLee/flexicon/issues/34#issuecomment-5568171084 |
| flexicon#257 (OPEN) | first_seen backdate evidence (ReversalIndexOperations variant, 19 days earlier) | https://github.com/MattGyverLee/flexicon/issues/257#issuecomment-5568172358 |

No issue was reopened, closed, or relabeled.

## Ledger

Not written by this agent per instructions — `docs/logscan-state.json` is left for the
archivist's single consolidated write after both this pass and the peer MCP-scoped pass
have finished filing.
