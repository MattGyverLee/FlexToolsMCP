# Cycle 3 -- Archivist propagation report (CP2-SPEC.md)

Mirrored spec.md's already-applied E1/E2 corrections plus SPEC.md's field-order
authority into CP2-SPEC.md. Three edits, no other files touched.

## Edit 1 -- index path + bridge artifact (lines 56, 189)

Line 56, before:
`A4  MCP: regenerate the index -> index/python/flexicon_api_v4.9.0.json`
Line 56, after:
`A4  MCP: regenerate the index -> src/flextoolsmcp/index/python/flexicon_api_v4.9.0.json`
`     and its version-locked sibling flexicon_lcm_bridge_v4.9.0.json`

Line 189, before:
`- Index: regenerate so \`index/python/flexicon_api_v4.9.0.json\` exists and the
  floor matches the indexed version.`
Line 189, after: same sentence extended to name
`src/flextoolsmcp/index/python/flexicon_api_v4.9.0.json` and its sibling
`flexicon_lcm_bridge_v4.9.0.json`, with "shipping only the api file silently
drops the bridge for 4.9.0" added.

## Edit 2 -- facade table row + footnote (line 93)

Before: `| \`Reload()\` | \`Update()\` | -- |`
After: `| \`Reload()\` | \`Reset()\` then \`Update()\` | -- |`, followed by a new
footnote paragraph stating `Update()` alone is conditional
(`if (m_changeListener.Reset() || m_forceUpdate) LoadParser();`) and citing
FieldWorks' `ParserWorker.ReloadGrammarAndLexicon()` as the reset-then-update
model. Table structure, Mode column, and all other rows unchanged.

## Edit 3 -- field order (line ~373)

Before: `morph`, `candidates`, `position`, `hint`, `resolved_to`*
After: `morph`, `position`, `resolved_to`*, `candidates`, `hint`
Matches SPEC.md line 1987 (D-03 authority). Footnote and "22 to 25" preamble
unchanged.

## Additional sites found

Searched the whole file for `index/python`, `flexicon_api_v4.9.0`,
`flexicon_lcm_bridge`, and bare `Update()`. No occurrences beyond the two
listed sites for the path/bridge fact, and no other bare `Update()` binding
elsewhere in the document. No undisclosed survivors of either retired fact.
