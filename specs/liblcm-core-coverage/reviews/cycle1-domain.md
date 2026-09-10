# Domain Expert Review: Indexed .NET Property Shape (Issue #136)

**Corrected root cause:** `ITsString` is COM-imported; `GetProperties()` yields zero indexed `PropertyInfo` objects. The 8 accessors survive only via `GetMethods()`. The issue's `pinfo.GetIndexParameters()` fix is inapplicable -- there is no `pinfo`. The fix must relax `extract_method`'s blanket `get_/set_/add_/remove_` filter (liblcm_extractor.py:517) for methods with parameters, and route them through `extract_method`, not `extract_property`.

**(a) List placement -- `methods`, not `properties`, not a third list.** `paginate_entity`'s `summary_only` thin row for methods keeps `name` + `signature` + `description`; the thin properties row keeps only `name` + `description` -- no signature at all. Since these entries exist *only* to teach a call signature, dropping them into `properties` would make them invisible in the default (summary) view most callers see. They are also literally `MethodInfo`, not `PropertyInfo`, at the reflection level -- `methods` matches ground truth. A third list is rejected: every doc, example, and existing consumer reads `properties`+`methods` only; TOOL-CONTRACT.md's additive-field discipline (inherited_from, diagnostic_report, etc.) always extends existing shapes as sibling keys, never adds a parallel structural list a caller must learn to check.

**(b) Emitted `name` -- the literal accessor, `get_Properties`.** Confirmed by live reflection: pythonnet exposes only `ts.get_Properties(i)`; there is no `ts.Properties[i]` form. Emitting bare `Properties` would be copy-pasteable but wrong (AttributeError at runtime); `Properties[int]` isn't valid Python. `signature` must read `get_Properties(int ich)` so the summary_only view alone is copy-paste correct.

**(c) Extra fields.** Add `"indexed": true` per the issue's ask, plus `"index_param_type"` mirroring `parameters[0].type`. Do not add `"is_property": true` -- these are recovered as methods, not properties, and claiming otherwise misrepresents the reflection. get_/set_ pairs (none on `ITsString` itself but generalizing to other types) emit as **two independent method entries**, not one merged object -- they have distinct signatures/examples and merging would break the "every entry is directly callable" invariant the rest of `methods` guarantees.

**(d) Teaching text** (belongs on the member entries AND as a workflow example in FLEXTOOLS-STYLE-GUIDE.md -- the entry teaches the single call, the guide teaches the multi-run iteration pattern):
- `get_Properties`: "Returns the ITsTextProps in effect at character offset `ich`. Call `.GetIntPropValues(FwTextPropType.ktptWs)` on the result to read the writing-system id for that run."
- `get_RunText`: "Returns the substring of the run containing offset `ich`. Pair with `get_Properties(ich)` for text+properties together; use `RunCount`/`get_MinOfRun(i)`/`get_LimOfRun(i)` to iterate every run."

**(e) `get_IsNormalizedForm(FwNormalizationMode)` -- same recovery path, `"indexed": false`.** Mechanical rule for the implementer: `indexed = (len(parameters) == 1 and parameters[0].type == "Int32")`. An enum-typed single parameter is an ordinary parameterized accessor, not an index.

**JSON -- `get_Properties`:**
```json
{
  "name": "get_Properties",
  "signature": "get_Properties(int ich)",
  "return_type": "ITsTextProps",
  "parameters": [{"name": "ich", "type": "Int32", "is_optional": false, "has_default": false}],
  "indexed": true,
  "index_param_type": "Int32",
  "category": "retrieval",
  "description": "Returns the ITsTextProps in effect at character offset ich. Call .GetIntPropValues(FwTextPropType.ktptWs) on the result to read the writing-system id for that run.",
  "is_static": false, "is_virtual": true, "is_abstract": false
}
```

**JSON -- `get_RunText`:**
```json
{
  "name": "get_RunText",
  "signature": "get_RunText(int ich)",
  "return_type": "String",
  "parameters": [{"name": "ich", "type": "Int32", "is_optional": false, "has_default": false}],
  "indexed": true,
  "index_param_type": "Int32",
  "category": "retrieval",
  "description": "Returns the substring belonging to the run containing offset ich. Pair with get_Properties(ich) to read both the run's text and its properties (e.g. writing system) in one pass; use RunCount/get_MinOfRun(i)/get_LimOfRun(i) to iterate all runs.",
  "is_static": false, "is_virtual": true, "is_abstract": false
}
```

---

Source: lex-domain, cycle 1. Files read: `src/flextoolsmcp/liblcm_extractor.py` (437-580), `src/flextoolsmcp/server/handlers/api.py` (`paginate_entity`, 633-865), `docs/TOOL-CONTRACT.md`, GitHub issue #136.
