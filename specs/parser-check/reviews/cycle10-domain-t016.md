# Cycle 10 -- T016: verify the three outstanding 9.5.4 LCM names

**Agent:** lex-domain (verification) + main session (file write)
**File touched:** `specs/parser-check/research.md` -- appended `## D9`, lines 259-287.

## Tooling note

lex-domain's toolset for this invocation was Read/Grep/Glob/WebFetch only -- no
Write, Edit or Bash, and no live `flextools_get_object_api` MCP tool. It therefore
read the index JSON that the tool serves from directly:

- `src/flextoolsmcp/index/liblcm/liblcm_api_v11.0.0.json`
- `src/flextoolsmcp/index/casting_index_liblcm-v11.0.0.json`

The verification is against the same data the tool would have returned. The main
session performed the append verbatim from the agent's text.

## Verdicts -- all three WRITTEN, none skipped

| Sub-check | Index evidence | Verdict | Consumer |
|---|---|---|---|
| `IMoAffixProcess` (row 5) | Entity at `liblcm_api_v11.0.0.json:94897`; `interfaces: [ICmObject, ICmObjectOrId, IMoAffixForm, IMoForm]`; own props `FeatureConstraints`, `InputOS`, `OutputOS`. `concrete_types` member of every `IMoForm`-rooted polymorphic collection; class-name map at casting_index:301. Needs `IMoAffixProcess(form)` after an `obj.ClassName` check. | **WRITTEN** | T035 |
| `IPhMetathesisRule` (row 3, metathesis half) | Entity at `liblcm_api_v11.0.0.json:108341`; `interfaces: [ICmObject, ICmObjectOrId, IPhSegmentRule]`. Inheritance caveat checked directly, not assumed. One of two concrete types under `IPhPhonData.PhonRulesOS` (:109579); class-name map at casting_index:450. | **WRITTEN** | T035 |
| `ILexEntry.AlternateFormsOS` (row 7, 2nd half) | Declared directly on `ILexEntry` (`liblcm_api_v11.0.0.json:86250`); `kind: "OS"`, `owns_sequence`, `target_type: "IMoForm"`. `.Count > 1` is a collection-level read -- no per-element cast. | **WRITTEN** | T034 |

`IMoStemAllomorph.StemNameRA` (row 7's first half) was already verified in D4 and
was not re-litigated.

## Consequence for downstream tasks

No `checks_skipped` / `lcm_name_unverified` entry arises from T016. T034 writes
row 7's `AlternateFormsOS` half as a real check; T035 writes row 5 and row 3's
metathesis half as real checks. D9 records the counterfactual branch explicitly so
the "never silently dropped" rule stays visible even though it did not fire.

## Incidental finding (out of scope, worth filing)

`IPhPhonData.PhonRulesOS` is **not** enumerated in the casting index's
`polymorphic_collections` table -- only `IMoForm`- and `IMoMorphSynAnalysis`-rooted
collections are. That is a gap in the casting index, not evidence against
`IPhMetathesisRule`. Flagged here rather than fixed: it is outside CP1 scope.

## Append-only confirmation

D1-D8 are byte-unchanged. `git diff --stat specs/parser-check/research.md` reports
59 insertions, 0 deletions across this cycle (D8's 32 + D9's 27).
