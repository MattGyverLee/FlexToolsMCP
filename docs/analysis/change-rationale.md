# Make member-level wrapper coverage derivable

Against `10e103e`. Two defects, one consequence: `find_wrappers_for_lcm` and
`resolve_property` can report that an LCM *entity* is touched, but not whether
a specific property or method is wrapped — and the structures that should hold
that answer are present, well-formed, and empty. An empty structure reads as
"no coverage" rather than "not computed", which is the silent-absence failure
mode `docs/` sets out to avoid.

## 1. `build_reverse_mapping` reads a field the analyzer stopped writing

`build_reverse_mapping` resolves each method's mapping from
`method["lcm_mapping"]` on `flexicon_api.json`. That data now lives in
`flexicon_lcm_bridge_v*.json` under `by_method`, keyed `"<Class>.<method>"`.
Measured on the shipped v4.12.0 indexes:

| | count |
|---|---:|
| methods in `flexicon_api.json` carrying inline `lcm_mapping` | **0 / 1657** |
| methods resolvable as `"<Class>.<method>"` in `by_method` | **1657 / 1657** |
| of those, `mapping_type != pure_python` (i.e. indexable) | 912 |

So `mapping_type` defaulted to `pure_python` for every method, every one hit
the early `continue`, and nothing was ever indexed. Two visible symptoms, one
cause:

- `reverse_mapping_liblcm-v11.0.0.json` ships with `methods`, `properties`,
  `factories` and `repositories` as empty dicts and `statistics.total_mappings
  == 0`.
- `class_info["methods"]` stayed empty, so every `python_wrappers` entry
  written into `liblcm_api.json` carries `"methods": []` — **0 of 2026**
  entities have a non-empty method list.

**Fix.** `build_reverse_mapping` takes a `bridge_path` and resolves each
method's mapping from `by_method`, falling back to the legacy inline field so
an older `flexicon_api.json` still builds. `main()` locates the bridge via the
existing `find_latest_versioned_api_file`. A missing bridge now warns instead
of silently producing an empty mapping, and `print_summary` calls out
`total_mappings == 0` explicitly.

Rebuilt against the shipped indexes:

| statistic | before | after |
|---|---:|---:|
| `total_mappings` | 0 | **912** |
| `properties_mapped` | 0 | **1253** |
| `methods_mapped` | 0 | **757** |
| `factories_mapped` | 0 | **137** |
| `repositories_mapped` | 0 | **18** |
| wrapper entries with a non-empty `methods` list | 0 / 577 | **493 / 577** |

## 2. The analyzer emitted property names in two spellings

`extract_lcm_calls` appended `f"{attr_name} ({suffix_type})"` for
suffix-matched properties and a bare `attr_name` for names in
`COMMON_LCM_PROPERTIES`. Those sets overlap — `LexemeFormOA`, `MorphTypeRA`
and `PartOfSpeechRA` match both rules — so the same property was written in
two different spellings inside one index. Of 191 distinct names in the shipped
bridge, 178 fail to resolve against `liblcm_api.json`; 173 of those resolve
once `" (Kind)"` is stripped.

**Fix.** `properties_accessed` now holds bare names — what
`liblcm_api.entities[*].properties[*].name` actually contains — and the field
kind moves to a parallel `property_kinds` map, so both facts are available
without string surgery. The kind is no longer lost; it is just no longer
welded into the key. Rebuilt reverse-map property keys resolve at **183 / 188
(97.3%)**.

The five that remain unresolved are worth a separate look, and the index can
now say so instead of hiding them in the 178: `__ProdRestrictRC`,
`__ResolvePOS` and `POS` look like Python-side attributes misclassified as LCM
properties by the extractor, while `LanguagesRC` and `FeatureConstraintsOC`
are absent from the LCM v11 index entirely.

### Compatibility

`validators._bridge_property_map` already did `str(prop).split(" ")[0]`, which
passes bare names through unchanged; its docstring is updated and the split
retained so an index built by an older analyzer still inverts correctly.
`build_reverse_mapping.extract_interface_from_property` and
`_classify_mapping_type` likewise already stripped the annotation. No consumer
required the annotated spelling — grep for `(OwningSequence)` and friends
returns comments and docstrings only.

## Tests

`tests/test_reverse_mapping_from_bridge.py`, 8 tests, no FieldWorks and no
live project — they run on in-memory dicts and a parsed AST:

- property names are bare, carry no annotation, and join against LCM member names
- kinds are recorded in `property_kinds`, including the suffix-bearing names
- `LexemeFormOA` / `MorphTypeRA` are emitted exactly once despite matching both rules
- a bridge populates `statistics`, all four member buckets, and the wrapper
  `methods` lists, while `pure_python` methods are still skipped
- a missing bridge yields an empty mapping **and says so** — the regression
  that started this was an empty result that looked like a real finding

`17 passed, 3 skipped` applying the patch to a clean `10e103e` worktree
(the new file plus `test_flexicon_index_drift`, `test_flexicon_index_floor`,
`test_liblcm_index_sanity`).

## Regenerating

The patch changes generators, not the committed indexes. To pick up the new
format:

```
python src/refresh.py                 # rebuilds flexicon_api + bridge
python src/build_reverse_mapping.py --update-liblcm
```

Until that runs, the shipped bridge keeps the annotated spelling; the reverse
map builds correctly either way because the extractor strips it.

## Unrelated observation

`tests/conftest.py` imports the full server handler stack at collection time,
so these index-only tests pull in `mcp` and (on Windows) `pywin32` before a
single assertion runs. Not addressed here, but it makes the pure-data tests
heavier to run than they need to be.
