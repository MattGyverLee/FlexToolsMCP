# QC Report — diagnostic-report SPEC.md (cycle 1)

> Persisted by the main session on behalf of lex-qc (its task tool set was
> Read/Grep/Glob only — no Write). Content is verbatim from the agent's return.

**Scope:** §8 privacy/consent, §9 transport, §12 testability. Scrubbing/anonymization explicitly out of scope per instructions.

## P0

**P0-1 (§8.3 / §12).** "home-dir absolute paths → `~` and the OS username stripped from paths" does not specify the *matching algorithm*. As written it's ambiguous between (a) regex/prefix matching only on recognized path-shaped tokens (e.g. anchored on `os.path.expanduser('~')` / `USERPROFILE` value at the start of a path segment) and (b) a naive global string-replace of the username substring across the whole report body. (b) would touch lexical data whenever a headword/gloss/example sentence happens to contain the username as a substring (e.g. username `matt` matching "Matthew's toolbox" in a `report.Info` line) — directly violating the "cannot touch lexical data" guarantee and the §12 claim. **Fix:** spec must mandate path-scoped matching only (operate on recognized path tokens — code fingerprints, file paths in headers/tracebacks/discovery args — never a document-wide find/replace of the username string), and state this as a normative constraint, not an implementation detail.

## P1

**P1-1 (§6 dedupe key).** `(code_sha256, error_code)` ties dedupe to the *exact code bytes* of one op. Per §3.1/§5, the whole feature exists because users iterate on code across a turn; any edit changes `code_sha256`, so the same underlying bug will re-offer on every attempt, arguably violating the intent of "never offer twice." Spec doesn't say whether this is intended (offer-per-distinct-code) or a gap. Needs an explicit decision + acceptance criterion.

**P1-2 (§8.2 vs §9 fidelity mismatch).** §8.2 promises preview shows "the exact bytes that would leave the machine." But in the URL-fallback GitHub path and the mailto path (§9), what actually leaves via the transport string is a *short capped summary*, not the full report file (only reaches the maintainer if the user manually attaches/pastes it). The preview step must show BOTH the full file and the actual short string embedded in the URL/mailto, or §8.2's claim is false for those two of three channels.

**P1-3 (offered.json schema undefined).** §6 references `~/.flextoolsmcp/reports/offered.json` but never defines its schema (key format, "offered" vs "declined/don't-ask-again" distinction, growth/pruning). Without a schema, "a duplicate signature does not [re-offer]" (§12) is not implementable-to-spec or testable — reviewer/implementer will guess. Needs explicit schema in §6 or §10.

**P1-4 ("working" undefined in §12).** "gh-present and gh-absent both yield a working GitHub path" has no operational definition. Recommend: gh-present → assert exact `gh issue create` argv shape (repo, `--body-file`, label); gh-absent → assert URL is valid, correctly percent-encoded, and body length ≤ 8KB cap. Without this, the acceptance criterion can't be scored pass/fail.

## P2

**P2-1 (§9 CI testability).** Testing the `gh auth status` branch deterministically requires an injectable "gh available" check rather than a bare subprocess probe, so both branches are unit-testable without a real authenticated `gh` in CI. Not stated in spec.

**P2-2 (§6 file growth).** No pruning/rotation policy for `offered.json`; unbounded growth over long-lived installs. Minor.

## Proposed test for "no transmission from any MCP code path" (§8.1/§12)

Two-layer guard:

1. **Static/AST scan** of the diagnostic-report module tree (and transitive imports) that fails the build if it finds calls to `subprocess.run/Popen/check_call/check_output` with `gh`/`git` args referencing `issue create`, or any use of `smtplib`, `webbrowser.open`, `urllib.request.urlopen`, `requests.*`, `http.client`, or raw `socket.socket` outbound connect. Also assert the module never imports the repo's existing `subprocess_helpers.py` in a way that would execute `gh` (confirmed today that module is generic/non-gh, so this is a regression fence, not a current violation).
2. **Dynamic test**: monkeypatch `subprocess.run/Popen`, `smtplib.SMTP`, `webbrowser.open`, `socket.socket` to raise `AssertionError` if invoked; drive `flextools_prepare_report` end-to-end for both gh-present and gh-absent branches plus the email branch; assert zero mock invocations, exactly one local file write, and that returned strings match the expected `gh`/URL/mailto shapes from P1-4.

**Overall:** §8/§9 no-auto-send structure is sound and testable via the proposed static+dynamic guard. One P0 (path-normalization scoping) plus P1 gaps around dedupe-key scope, preview/transport-fidelity mismatch, offered.json schema, and untestable "working" criteria in §12.
