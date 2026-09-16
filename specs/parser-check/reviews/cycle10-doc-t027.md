# T027 report -- SPEC 9.5.4 corrections

## Fix 1 -- Row 8 (line 1407)
Before: `rule ordering within \`IMoStratum\`; standalone derivational rule count equals chain depth`
After: `rule ordering is \`IPhSegmentRule.OrderNumber\`, grouped via \`InitialStratumRA\`/\`FinalStratumRA\` -- **verified**; \`IMoStratum\` has no rule collection, only \`Abbreviation\`, \`Description\`, \`Name\`, \`PhonemesRA\`; standalone derivational rule count equals chain depth`

## Fix 2 -- implementation note (lines 1414-1422)
Before: `Two implementation notes:` / `**Only rows 2, 4 and 9 have had their LCM property names verified**...`
After: `Three implementation notes:` / `**Rows 1, 2, 3 (epenthesis half), 4, 6, 8, 9 and 10 have had their LCM property names verified**... Three items remain *proposed*...: row 3's metathesis half (\`IPhMetathesisRule\`), row 5's rule-count product, and row 7's \`AlternateFormsOS\` half.` No verdict asserted on the three outstanding items -- stated as outstanding only, per instruction (T016 owns them).

## Fix 3 -- OrderNumber caveat (new bullet, lines 1427-1430)
Added third bullet: `**\`OrderNumber\` is a per-stratum-pair counter, not a grammar-wide ordinal.** Each rule references exactly one \`InitialStratumRA\`/\`FinalStratumRA\` pair, so \`OrderNumber\` is comparable only within that pair's grouping. Never sort or compare it across pairs.`

## Fix 4 -- SPEC 15 CP1 row (line 1982)
Before: `**HC-agent probe with \`parser_agent_missing\` refusal** (12.7);`
After: `**HC-agent probe with \`parser_agent_missing\` refusal logic, shipped with tests; first live caller at CP2** (12.7);`

## Confirmation
No section or row renumbered. Rows 1-10 in 9.5.4 and the CP row labels in section 15 are unchanged in identity/order. No text outside the four target spans was touched.

## Out-of-scope observations
Row 3's cell text itself ("an `IPhRegularRule` with an empty structural description; any `IPhMetathesisRule`") was left untouched per scope -- it does not carry a "verified" marker for its epenthesis half, which the note now claims is verified. Once T016 settles the metathesis half, a follow-up may want per-clause verified/outstanding markers directly in row 3's cell (matching the row 2/4/8/9 pattern) rather than relying solely on the note. Flagging, not fixing -- outside T027's four listed fixes.
