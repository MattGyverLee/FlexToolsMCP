# Domain Expert Review — cycle 3 — 12.3 refuse-to-file gate

**Date:** 2026-09-15 | **Domain:** FieldWorks/HermitCrab parser integration | **Status:** NEEDS-CHANGE (rung 2)

## a) What does FLEx itself do on HC load errors?
`HCLoader.Load` (HCLoader.cs:30) always returns a `Language`; errors only reach an `IHCLoadErrorLogger`. FLEx's own consumer is `HCParser.LoadParser` (HCParser.cs:144-158), which opens `{ProjectName}HCLoadErrors.xml` fresh every load (`XmlWriter.Create`, truncating) and writes via `XmlHCLoadErrorLogger` (HCParser.cs:595-688). The only UI reader is `HCTrace.CreateResultPage` (HCTrace.cs:28-37), which feeds that file's URI as an XSLT param (`prmHCTraceLoadErrorFile`) into `FormatHCTrace.xsl`, which calls `ShowAnyLoadErrors` (FormatHCTrace.xsl:229) on **every** result page render — both `"HCTrace"` and `"HCParse"` (HCTrace.cs:36), i.e. every "Try a Word" invocation, not just explicit trace mode. FLEx **never blocks** on load errors; it parses and inlines a warning in the results page the user is already looking at. Crucially, batch/corpus reparse via `ParserWorker`/`ParserScheduler` has **no UI consumer of the file at all** — a full reparse's load errors are silently written to disk and never shown to anyone. So refusing to file is a genuine divergence from FLEx's single-word UX, but it is *filling a gap*, not overriding an existing warning, for the batch path this feature actually automates. That distinction should be stated in the spec, not left implicit.

## b) Is "pre-existing load errors are benign" true, or convenience?
Plausible but unverified from source alone — load errors correlate with things like slots with no matching affixes, invalid environments, etc., which real analysts routinely leave unfixed for stretches. Nothing in HCLoader.cs suggests errors are rare in the field; treat "benign" as a working hypothesis, not a proven baseline, and say so.

## c) Baseline provenance — the weak joint
Confirmed: nothing in this spec or in FieldWorks defines what the "baseline parse" is. A project never parsed by us has no MCP-generated side file, and FLEx's own `{ProjectName}HCLoadErrors.xml` is overwritten on every load with no timestamp, no grammar-state hash, and no record of which caller (Try-a-Word vs a stale FLEx session vs us) produced it. Comparing against it conflates "changed since I last ran" with "changed since some unknown prior FLEx session, possibly hours old, possibly against an edited grammar." **REFUTED as specified** — rung 2 needs its own MCP-owned baseline (recorded at the start of *our* session/run, keyed to `scope_fingerprint`), not FLEx's side file, which is provenance-blind.

## d) CP1 boundary
CP1 loads no grammar (line 397: "no cache is opened, no grammar is loaded, nothing is parsed"), so it cannot assert current load-error state. It may report only side-file **metadata**: existence, mtime, entry count — framed explicitly as "as of the last recorded load, not verified now." It must never say "grammar loads cleanly" or "N errors present" as a present-tense verdict; that is exactly the section-3.1 violation one layer over (reporting an artifact of past work as current grammar state).

## Verdicts
- Rung 1 (`m_morpher == null` hard refuse): **VALIDATED**.
- Rung 2 (new-error-vs-baseline refuse): **NEEDS-CHANGE** — define an MCP-owned baseline captured at run start; do not compare against FLEx's side file.
- Rung 3 (pre-existing errors warn+count): **VALIDATED**, with (b) flagged as an assumption to state explicitly, not prove.
- Rung 4 (confirmation projects deletions): **VALIDATED**, consistent with 12.2's actual-deletion framing.
