# Cycle 1 QC Review - liblcm-core-coverage

## Part A - Blast radius of retaining parameterized accessors (#136)

Probe (read-only, not committed): `probe_indexed_accessors.py` in the session
scratchpad. Loads the real `liblcm_extractor` functions (`init_pythonnet`,
`find_dll_directory`, `find_assemblies`, `load_assemblies`, `reflect_types`,
`_is_target_type`, `clean_type_name`), points at
`C:\Program Files\SIL\FieldWorks 9`, loads the same 9 assemblies (incl.
`SIL.LCModel.Tools.dll`), reflects 2034 target types with
`Public|Instance|DeclaredOnly` (the same flags `extract_type` uses), then
simulates "retain `get_X`/`set_X` where getter arity>=1 or setter arity>=2".

Results:
- **40 types** gain >=1 parameterized accessor; **171** raw members added.
- Index-param types: Int32 149, enum 4 (`FwNormalizationMode` on
  `ITsString`/`TsString`), other 18 (Guid x3, String x6, generic `TKey`/`Tkey`
  x4, Boolean x2, misc x3).
- **24 real duplicates**: `get_Item`/`set_Item` on 12 types (`IStText`,
  `IScrBook`, `ScrMappingList`, `StyleInfoTable`, `WritingSystemList`,
  `ScrBook`, `StText`, `LcmList`, `LcmReferenceSequence`,
  `LcmOwningSequence`, `OwningSequenceWrapper`, `SmallDictionary`,
  `TreeDictionary`) — ordinary managed C# indexers where `Item` is already a
  real `PropertyInfo` in `properties`. Unlike `ITsString`'s COM case,
  `GetProperties()` here *does* surface the indexer, so retaining the
  accessor would emit a second, method-shaped entry for something already
  documented.
- `ITsString` itself: exactly the 8 members from the issue, confirmed
  (`get_RunAt`, `get_MinOfRun`, `get_LimOfRun`, `get_RunText`,
  `get_PropertiesAt`, `get_Properties`, `get_IsNormalizedForm`,
  `get_NormalizedForm`).
- Net of the 24 dupes: 147 members, but **91 of those (62%) concentrate in 4
  low-level plumbing interfaces** — `SilDataAccessManagedBase` (+24),
  `DomainDataByFlid` (+24), `DomainDataByFlidDecoratorBase` (+22),
  `ISilDataAccess` (+21) — generic FLID accessors (`get_ObjectProp`,
  `get_BooleanProp`, `get_IntProp`, `get_VecItem`, ...) that typed wrapper
  properties already cover and that #136 was not filed for. The actual
  `ITsString` family fix (`ITsString`, `ITsStrBldr`, `TsStrBase`, `TsString`)
  is small: 20 members across 4 related types.

**Risk call: P1.** A literal blanket arity rule is not a clean targeted
recovery — it guarantees 24 duplicate/noisy entries and roughly doubles the
surface of 4 hot low-level types with plumbing most FLExTools scripts never
call. Recommend narrowing the #136 implementation: (1) skip any accessor
whose base name already matches an existing property name on that type
(removes all 24 `Item` dupes for free), and (2) scope retention to
COM-imported/interface types where the indexed member has no backing
`PropertyInfo` at all (the actual `ITsString` shape), rather than every
reflected type. With that guard, the change is P2 and clean (~20 members, 4
types).

## Part B - Commit hygiene

`git log --stat -15` / `git diff` confirm: `liblcm_extractor.py`'s diff is
entirely #135 (`SIL.LCModel.Tools.dll` preload, `EXCLUDED_NAMESPACES`,
`NAMESPACE_TYPE_ALLOWLIST`, `_is_target_type`, `ReflectionTypeLoadException`
recovery via `e.Types`). `liblcm_api_v11.0.0.json` goes 1878 -> 2026 entities
(+148, matching the issue's own count) — purely downstream of that fix.
`casting_index`/`navigation_graph`/`reverse_mapping` (`*_liblcm-v11.0.0.json`)
diffs are new entities (`ActionHandler`, `BidiCharacterFactory`, `CheckWord`,
...) plus one `WritingSystemOperations.method_count` bump (23->25); none
touch flexicon. **CONTRIBUTING.md PR Rule 2 confirmed** — the four liblcm
index files belong with `liblcm_extractor.py`. **VERSIONING.md confirmed**
("old files can be safely deleted", "Independent Updates") — the flexicon
4.7.0->4.8.0 churn touches nothing #135 changed and is its own axis.

**Caution found live:** `pip show pyflexicon` currently reports **4.7.0**
installed, yet the tree already deletes the v4.7.0 index files and adds
v4.8.0 as untracked. Confirm which version is actually canonical before
committing the flexicon churn — if v4.8.0 is stale from an unrelated
session, committing it now ships an index for a version nobody has
installed. No `#135`/`#136` text and no CHANGELOG `[Unreleased]` bullet
exist yet (PR Rule 1).

Recommended split (direct-to-main):

```
# Commit 1 - the fix (add a CHANGELOG bullet before staging)
git add src/flextoolsmcp/liblcm_extractor.py \
        src/flextoolsmcp/index/liblcm/liblcm_api_v11.0.0.json \
        src/flextoolsmcp/index/casting_index_liblcm-v11.0.0.json \
        src/flextoolsmcp/index/navigation_graph_liblcm-v11.0.0.json \
        src/flextoolsmcp/index/reverse_mapping_liblcm-v11.0.0.json \
        CHANGELOG.md
# Subject: fix: recover SIL.LCModel.Core types dropped by ReflectionTypeLoadException (closes #135)

# Commit 2 - independent flexicon refresh (verify installed version first)
git add src/flextoolsmcp/index/common_patterns_flexicon-v4.8.0.json \
        src/flextoolsmcp/index/python/flexicon_api_v4.8.0.json \
        src/flextoolsmcp/index/python/flexicon_lcm_bridge_v4.8.0.json
git rm src/flextoolsmcp/index/common_patterns_flexicon-v4.7.0.json \
       src/flextoolsmcp/index/python/flexicon_api_v4.7.0.json \
       src/flextoolsmcp/index/python/flexicon_lcm_bridge_v4.7.0.json
# Subject: chore: refresh flexicon index to v4.8.0

# Commit 3 - unrelated regen, shares no path with 1 or 2
git add reports/upstream-flexicon-docstring-findings.json \
        reports/upstream-flexicon-docstring-findings.md
# Subject: chore: regenerate upstream flexicon docstring findings
```

Each commit message ends with:
```
Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01QC4jrof7mQuXH8q7WEF8MY
```
