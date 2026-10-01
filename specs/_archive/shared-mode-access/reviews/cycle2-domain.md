# Cycle 2 — Domain assessment: success-demotion semantics (CP1 / #92)

KEEP BUT DOCUMENT

(a) FLExTools' own convention treats `report.Error` as a per-item, non-fatal signal — the style guide's canonical loop pattern (`docs/FLEXTOOLS-STYLE-GUIDE.md:164-185`) explicitly calls `report.Error()` inside a per-entry `except` and continues the loop; `report.Warning` is reserved for things like "no senses found." So `report.Error` was never a "the whole run failed" primitive in FLExTools' own vocabulary — it's the MCP's boolean `success` field, not FLExTools, that forces a binary reading onto a report stream FLExTools itself just displays to a human. CP1 is therefore translating an inherently graded signal into a coarse one, but the alternative (silent success on a broken/partial write) is strictly worse.

(b) A caller that branches only on `success` and retries the whole batch risks harm on non-idempotent operations (Create*, AddAllomorph) but is safe for typical setters like `SetGloss`/`SetLexemeForm`, which overwrite rather than accumulate. This is a real hazard, but it already existed pre-CP1 for any partial-failure batch — CP1 didn't introduce it, it exposed it.

(c) Yes — `summary.error_count`, `summary.info_count`, `summary.total_messages`, and the full `messages[]` array (each with `type`/`message`/`ref`, including the `BuildGotoURL` link) already let a careful caller distinguish "3 of 500 failed" from "everything failed" without any code change.

**Recommendation:** don't touch CP1's semantics. Add a short note (TOOL-CONTRACT.md or FLEXTOOLS-STYLE-GUIDE.md) telling callers: on `ReportedError`, inspect `summary.error_count` vs `total_messages` before deciding whether to retry, and never blind-retry a batch containing `Create*`/append-style mutations — only idempotent setters are safe to re-run.

---

**Provenance:** produced by the read-only lex-domain agent in cycle 2; written to
disk verbatim by the orchestrator because that agent has no write tool.
