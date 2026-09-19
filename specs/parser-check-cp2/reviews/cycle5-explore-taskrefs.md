# Cycle 5 -- Explore: CP2a task-list citation audit

**Lane**: `Explore` (read-only), dispatched by the main session in spurt 5.
**Scope**: every concrete `path:line` citation in
`specs/parser-check-cp2/tasks.md`, checked against the **current** flexicon tree
at `D:\Github\_Projects\_LEX\flexicon` (branch `feat/parser-check-cp2`, commit
`c08ede4`).
**Why this lane ran**: spurt 5 was blocked from executing anything in the
flexicon repo (see `.crew-handoff.json` blocker), and this was the one piece of
CP2a de-risking that needs only reads. tasks.md was written in spurt 3; flexicon
has taken commits since. Copying a template that does not say what it was
believed to say is this campaign's documented recurring failure -- it is the
root cause named in issues #36, #39 and #40, and the reason T008 carries its
"do not copy the three unguarded siblings" warning.

**Nothing in this report has been applied to tasks.md.** Apply the three
load-bearing corrections before implementing the tasks that cite them.

---

## Verdict

Twenty-four of the ~30 concrete citations land exactly where tasks.md says they
do -- the tree has drifted far less than feared, and **every ratchet and
registry citation is line-accurate** (T014, T015, T006, T022, T027, T013's pyi
ratchet, T016's alias table). That matters: those are the citations whose
wrongness would have been discovered late and expensively.

Four citations are off by a handful of lines or omit a directory
(`TextOperations.py:660`, `ReversalIndexOperations.py:68-76`,
`RELEASING.md:189`) and are harmless.

**Two are load-bearing wrong, and one task's premise is wrong outright:**

- **T007**'s cited template `LexSenseOperations.GetSemanticDomains` is decorated
  with `@OperationsMethod` **only** -- it does not demonstrate the stacked
  `@wrap_enumerable` the same task instructs the implementer to copy from it.
- **T013**'s claim that `_op_aliases.py:6-8` "reserves plural for collection
  namespaces and singular for service facades (`POS`, `MSA`, `Discourse`,
  `ProjectSettings`)" is not in that file at all; none of those four names
  appear anywhere in it.
- **T009**'s target `flexicon/code/Lexicon/MSAOperations.py` is **not net-new**.
  It already exists at 1230 lines as a write-capable create/set/remove class.

---

## Citation table

| Task | Citation | Status | Correct location / what is actually there |
|---|---|---|---|
| T007 | `BaseOperations.py:172` (decorator order) | OK | `class wrap_enumerable:`; docstring 181-183 "Must be a descriptor to properly delegate to OperationsMethod's `__get__` ... when stacked decorators are used"; Usage block 188-190 shows `@wrap_enumerable` above `@OperationsMethod` |
| T007 | `LexSenseOperations.py:1602` (GetSemanticDomains template) | **WRONG** (as a stacked-decorator template) | 1602 is `def GetSemanticDomains(self, sense_or_hvo):`, but 1601 is `@OperationsMethod` **alone** -- no `@wrap_enumerable`. Body (1637) is `return list(sense.SemanticDomainsRC)`. The stacked pattern lives at `AllomorphOperations.py:102-104` and `ReversalIndexOperations.py:81-83` |
| T007 | `TextOperations.py:660` (singular `GetGenre`, `GenresRC.FirstOrDefault()`) | DRIFTED | 660 is `with self._TransactionCM(f"Set text name '{name}'"):` (inside `SetName`). `@OperationsMethod` at 664, `def GetGenre(self, text_or_hvo):` at **665**; `GenresRC.Count > 0` at 698 and `return text_obj.GenresRC.FirstOrDefault()` at **699** |
| T008 | `LexSenseOperations.py:2826` (null-guard before cast) | OK | `def GetOwningEntry(self, sense_or_hvo):` at 2826; pattern at 2864-2867: `_owner = sense.OwnerOfClass(LexEntryTags.kClassId)` / `if _owner is None: return None` / `return ILexEntry(_owner)` |
| T008/T009 | `AllomorphOperations.py:104` (`GetAll(entry)`) | OK | 102 `@wrap_enumerable`, 103 `@OperationsMethod`, 104 `def GetAll(self, entry_or_hvo=None):`; docstring documents the two-subtype smart collection |
| T009 | `morphosyntax_analysis.py:74` | OK | `class MorphosyntaxAnalysis(LCMObjectWrapper):` |
| T009 | `msa_collection.py:76` | OK | `class MSACollection(SmartCollection):` |
| T009 | "instantiated by no code path at all" | OK (confirmed) | No instantiation anywhere under `flexicon/` source. Only mentions: `MSAOperations.py:128,150-151` (See Also prose), `docs/USAGE_MORPHOSYNTAX.md` (hand-rolled `MSACollection([MorphosyntaxAnalysis(m) for m in entry.MorphoSyntaxAnalysesOC])`), `tests/test_msa_wrappers.py` (mocks) |
| T009 | `lcm_casting.py:652` | OK | `_MSA_POS_PROPERTY = {` -- the ClassName-keyed dispatch dict (653-656) |
| T009 | `lcm_casting.py:662` | OK | `POS_BEARING_MSA_CLASSES = frozenset(_MSA_POS_PROPERTY)` |
| T009 | `lcm_casting.py:665` | OK | `def get_pos_from_msa(msa):` |
| T009 | `LexSenseOperations.py:1177` (consumer) | OK | `def GetPartOfSpeechObject(self, sense_or_hvo):` -- the documented importer of `POS_BEARING_MSA_CLASSES` |
| T009 | `flexicon/code/Lexicon/MSAOperations.py` net-new? | **WRONG (exists)** | Exists, 1230 lines, `class MSAOperations(BaseOperations)` at 115, with `CreateStem`, `CreateDerivAff`, `CreateInflAff`, `CreateUnclassifiedAffix`, `SetStemMsaPos`, `SetDerivAffMsaPos`, `ChangeAffixVariant`, `RemoveOrphaned`, sync props. **No read/GetAll accessor.** `MSAOperations.pyi` also already exists |
| T010/T011 | `BaseOperations.py:590` | OK | `class BaseOperations:` |
| T011 | `ReversalIndexOperations.py:68-76` | DRIFTED (range off by one; path off) | File is `flexicon/code/Reversal/ReversalIndexOperations.py`. 68 is the closing `"""` of the class docstring; `def __init__(self, project):` at **70**, docstring 71-76, `super().__init__(project)` at **77**. Correct range: **70-77** |
| T013 | `FLExProject.py:2181-2209` | OK | `@property` 2180, `def Senses(self):` 2181, `if "_sense_ops" not in self.__dict__:` 2205, function-local `from .Lexicon.LexSenseOperations import LexSenseOperations` 2206, cache+return 2208-2209 |
| T013 | `_op_aliases.py:6-8` (singular reserved for service facades) | **WRONG** | 6-8 read: "FLExProject exposes one accessor per operation namespace. The canonical convention is PLURAL for collection namespaces (project.MorphRules, project.InflectionFeatures, project.Senses, ...)". No mention of service facades; `POS`, `Discourse`, `ProjectSettings` appear **nowhere** in the file. The singular-canonical evidence is the plural->singular block at 79-84 (`LexEntries->LexEntry`, `MSAs->MSA`, `Etymologies->Etymology`, `GramCats->GramCat`) plus `FLExProject.py:1622 POS`, `:1649 LexEntry`, `:2212 MSA`, `:2787 Discourse`, `:2916 ProjectSettings` |
| T013 | `tests/test_pyi_return_annotation_ratchet.py:70-101` | OK | `def test_shared_return_annotations_agree(self):` at 70 through the assert ending at 101; compares normalized `returns` strings, skipping where either side is `None` |
| T013 | `tests/test_docstring_example_ratchet.py` unknown-accessor | OK | `:396` `add("unknown-accessor", "project.%s is not on FLExProject" % attr)`; self-test at `:523-524` |
| T013 | `tests/docstring_example_baseline.json` | OK (exists) | Present |
| T014 | `test_297_init_stub_parity.py:170` | OK | `missing = sorted(runtime_names - stub_all)` (runtime export absent from stub `__all__`) |
| T014 | `:190` | OK | `overstated = sorted(stub_all - runtime_names)` |
| T014 | `:210` | OK | `undeclared = sorted(set(stub_all) - declared)` |
| T015 | `tests/flex_plugin.py:152-222` | OK | `operations_modules = [` at 152, closing `]` at 222 |
| T015 | `:738-808` | OK | `_OPERATIONS_CLASS_DOMAIN = {` at 738, closing `}` at 808 |
| T015 | `:736-737` (keep-in-sync comment) | OK | "Mirrors the operations_modules list in / initialize_flex_for_tests; keep them in sync when adding a new class." |
| T016 | `_op_aliases.py:35` | OK | `OP_NAMESPACE_ALIASES = {` |
| T016 | `:79-84` | OK | `# --- plural guess -> canonical singular accessor ---` at 79, four entries 80-83, `}` at 84 |
| T016 | `:143-149` (raises if canonical missing) | OK (raise spans 145-150) | 143 `for alias_name, canonical_name in aliases.items():`, 144 `if not hasattr(cls, canonical_name):`, 145 `raise AttributeError(` ... closing `)` at 150 |
| T022 | `flexicon/__init__.py:67-72` | OK | `CAPABILITIES = frozenset({` 67, four tokens 68-71, `})` 72 |
| T022 | `:17-66` (`#:` doc block) | OK | Contiguous `#:`/comment block 17-66 immediately above the frozenset |
| T022 | `:31-33` (token semantics) | OK | "IMPORTANT -- a token here means \"this build implements the capability\", NOT \"the capability is active in your session\"." |
| T022 | `test_capabilities.py:36-41` | OK | `EXPECTED_TOKENS = {` 36, four tokens 37-40, `}` 41 |
| T022 | `:54` (set equality) | OK | `assert set(flexicon.CAPABILITIES) == EXPECTED_TOKENS` |
| T022 | `:12-16` (Principle V statement) | OK | "A token added here without a landed capability behind it is a constitution V violation (an API implying a guarantee it does not deliver)" |
| T023 | `flexicon/__init__.py:15` = `version = "4.8.0"` | OK | Exact: `version = "4.8.0"` -- current value confirmed, bump target 4.9.0 still valid |
| T023 | `pyproject.toml:69-72` | OK | `[tool.setuptools.dynamic]` 69, comment 70-71, `version = { attr = "flexicon.version" }` 72 |
| T023 | `RELEASING.md:189` | DRIFTED (path) | Text is exact -- "so that one line is the only edit. Do not add a second version constant." -- but at **`docs/RELEASING.md:189`**; there is no repo-root `RELEASING.md` |
| T023 | `__init__.pyi:12` (type only) | OK | `version: str` (and `CAPABILITIES: frozenset[str]` at 13 -- relevant to T022) |
| T027 | `test_flexlibs2_alias_ratchet.py:150` | OK | `assert not offenders,` -- executable `flexlibs2` imports |
| T027 | `:170` | OK | `assert not offenders,` -- dotted string-literal references |
| T027 | `:285` | OK | `assert not offenders,` -- docs/prose teaching the alias |
| T027 | `:310` | OK | `assert not offenders,` -- Python comments/docstrings |
| T006 | `test_public_casting_export.py:127-153` | OK | `def test_lcm_casting_has_no_module_scope_sil_import(self):` 127 -> `assert offenders == [], ...` 153; `ast.parse(inspect.getsource(...))` + module-scope Import/ImportFrom scan. Good template |
| T005 | `flexicon/__init__.py:76` (pulls in FLExInit) | OK | `from .code.FLExInit import (` |
| T002 | `flexicon/code/Parser/` | MISSING (as expected) | Does not exist -- T002 genuinely creates it |
| T003/T005/T006/T018 | the four parser test files | MISSING (as expected) | None of `tests/operations/test_parser_live.py`, `tests/test_parser_offline.py`, `tests/test_parser_structure.py`, `tests/test_parser_reflective.py` exist |

---

## Load-bearing discrepancies

1. **T007's template does not show the thing T007 says to copy.**
   `LexSenseOperations.py:1601-1602` is `@OperationsMethod` + `def
   GetSemanticDomains`, with **no** `@wrap_enumerable`, returning a plain
   `list(...)`. An implementer told "template: `GetSemanticDomains`" who copies
   it faithfully produces an undecorated method and silently drops the
   stacked-decorator requirement the same task sets. **Fix**: cite
   `AllomorphOperations.py:102-104` (or `ReversalIndexOperations.py:81-83`),
   which actually stack the two; keep `1602` only as the *shape* reference for
   an RC read.

2. **T009's file already exists and is a write class.**
   `flexicon/code/Lexicon/MSAOperations.py` (1230 lines) and its `.pyi` are
   present, containing `CreateStem` / `CreateInflAff` / `RemoveOrphaned` /
   `ChangeAffixVariant` and sync properties. T009 reads as if it creates the
   module; it must instead **add a read accessor into an existing write-capable
   class**. Consequences to think through before implementing: whether the new
   accessor needs `@wrap_enumerable` alongside its write siblings, and -- more
   importantly -- that T009's deliverable is *not* read-only-by-construction the
   way `flexicon/code/Parser/` is, so nothing in T010/T011's read-only framing
   may be inherited by association.

3. **T013's justification citation is false.** `_op_aliases.py:6-8` says nothing
   about service facades and never mentions `POS`, `MSA`, `Discourse` or
   `ProjectSettings`. The singular-is-a-service-facade argument has to rest on
   `_op_aliases.py:79-84` plus the actual `FLExProject.py` properties at
   `:1622`, `:1649`, `:2212`, `:2787`, `:2916`. **The decision (D-A3, singular
   `project.Parser`) is still right -- only its cited evidence is wrong.** Left
   as-is, an implementer who verifies the citation finds the premise unsupported
   and may reopen a settled naming decision.

4. **Two path omissions**: `RELEASING.md` is at `docs/RELEASING.md`, and
   `ReversalIndexOperations.py` is under `flexicon/code/Reversal/`. Also T011's
   `68-76` misses the `super().__init__(project)` line it specifically points at
   -- that is line **77**.
