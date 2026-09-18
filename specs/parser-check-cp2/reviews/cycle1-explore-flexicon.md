# cycle1-explore-flexicon

Cross-repo recon of `D:\Github\_Projects\_LEX\flexicon` (PyPI `pyflexicon`, imported
as `flexicon`) for parser-check CP2 Part A. Read-only; nothing in that repo changed.

## 1. Facade pattern (idiomatic `project.Parser`)

An area is a class subclassing `BaseOperations` (`flexicon\code\BaseOperations.py`),
one file per area under a domain folder (`code\Lexicon\`, `code\Grammar\`,
`code\Reversal\`, `code\TextsWords\`, `code\System\`). Template:
`flexicon\code\Lexicon\AllomorphOperations.py:48` (`class AllomorphOperations(BaseOperations)`),
with a module header comment block, `logger`, LCM imports, a docstring `Usage::`
block, `__init__(self, project)`, and public methods decorated `@OperationsMethod`.

Attachment to `FLExProject` is a lazy `@property` using a `self.__dict__` guard plus
a function-local import -- see `flexicon\code\FLExProject.py:2335` (`ReversalIndexes`),
`:2362` (`ReversalEntries`), `:2240` (`MSA`), `:1916` (`Allomorphs`). Exact shape:

    if "_reversalindex_ops" not in self.__dict__:
        from .Reversal.ReversalIndexOperations import ReversalIndexOperations
        self._reversalindex_ops = ReversalIndexOperations(self)
    return self._reversalindex_ops

Each property carries a Google-style docstring with `Returns:` and a doctest-shaped
`Example:` block (both are ratcheted -- see section 5).

A new `project.Parser` should therefore be: `flexicon\code\Grammar\ParserOperations.py`
defining `ParserOperations(BaseOperations)`; a `Parser` property on `FLExProject` at
the same shape; a stub entry in `flexicon\code\FLExProject.pyi` (cf. `:129
def ReversalIndexes(self) -> ReversalOperations: ...`); a re-export in
`flexicon\__init__.py` (Grammar block, `:123-162`) and in `flexicon\__init__.pyi`
`__all__`; and an alias row in `flexicon\code\_op_aliases.py` `OP_NAMESPACE_ALIASES`
(`:35`) if both numbers are guessable.

## 2. Lazy import / capability-probe precedent

Yes, one: `flexicon\code\lcm_casting.py:84 _ensure_interfaces()` -- a module-global
`_interface_cache` (`:80`) + `_interfaces_loaded` flag, populated on first use of
`cast_to_concrete()`, explicitly "avoids import issues ... if SIL.LCModel is imported
before FLExInit has configured the CLR" (`:92-94`).

Graceful degradation precedent is inside it: optional LCM interfaces are imported
under `try/except ImportError` and set to `None` rather than raising -- `:130-140`
(phonological rules), `:147-153` (compound rules), `:286` (feature structures), and a
hardcoded `None` with a written rationale at `:251-264`.

NOTE the difference from what CP2 needs: `_ensure_interfaces()` itself still **raises**
`ImportError` when SIL.LCModel is entirely absent (`:103`); there is no existing
"unavailable, here is the reason" return value. The nearest deferred assembly load is
`clr.AddReference("FwUtils")` inside a function body at `flexicon\code\FLExGlobals.py:154`;
every other `AddReference` is module-level (`FLExLCM.py:20-31`, `FLExInit.py:47-50`).
So the "probe returns a reason string" half is new, but modelled on existing shapes.

Also relevant: `flexicon\__init__.py:67 CAPABILITIES = frozenset({...})` with a
documented `getattr(flexicon, "CAPABILITIES", frozenset())` probe contract (`:17-40`,
`docs\FLEXTOOLSMCP_WRITE_CONTRACT.md` section 3). A `"parser"` token belongs there.

## 3. Existing parser-adjacent code

None. No `ParserCore`, `HCParser`, `XAmple` (beyond the GUID name
`kguidAgentXAmpleParser` in a docstring, `flexicon\code\Lists\AgentOperations.py:134`),
and no HermitCrab code -- only prose in docstrings warning about parser breakage
(`Grammar\PhonemeOperations.py:231`, `Grammar\StratumOperations.py:240`,
`Lexicon\MSAOperations.py:266-269`, `Lexicon\LexSenseOperations.py:1262,1332`).
Part A is greenfield.

## 4. The three read gaps

(a) **Text genres -- present but first-only.** `flexicon\code\TextsWords\TextOperations.py:660
GetGenre()` returns `GenresRC.FirstOrDefault()` and the docstring says so (`:663-665`).
`SetGenre` (`:699`) clears and re-adds. Full collection is read only in
`GetSyncableProperties` (`:387-388`). Needs a `GetGenres()` (plural).

(b) **Allomorph -> owning entry -- absent as public API.** `AllomorphOperations` has no
`GetOwningEntry`; it only calls the protected `self._GetTypedOwner(allomorph)`
internally (`Lexicon\AllomorphOperations.py:350`, `:423`). Precedent to copy exists in
four siblings: `Lexicon\LexSenseOperations.py:2826`, `Lexicon\EtymologyOperations.py:1150`,
`Lexicon\PronunciationOperations.py:946`, `Lexicon\VariantOperations.py:1011`.

(c) **MSA reads -- absent.** `Lexicon\MSAOperations.py` is create/set/repair only
(`CreateStem:158`, `CreateDerivAff:197`, `CreateInflAff:246`, `CreateUnclassifiedAffix:303`,
`SetStemMsaPos:335`, `SetDerivAffMsaPos:376`, `ChangeAffixVariant:433`,
`RemoveOrphaned:676`, plus sync capture/apply). The only read is
`LexSenseOperations.GetGrammaticalInfo` (`:1526`), which hands back a raw MSA object.
Nothing renders kind/POS as readable text; `lcm_casting.get_pos_from_msa` (`:665`) and
`get_from_pos_from_msa` (`:990`) are the raw building blocks.

## 5. Release mechanics

Version: `flexicon\__init__.py:15 version = "4.8.0"`, read statically by `pyproject.toml`
`[tool.setuptools.dynamic] version = { attr = "flexicon.version" }`.
`docs\RELEASING.md:182-189` names it the single source of truth ("Do not add a second
version constant").

Procedure (`docs\RELEASING.md`): section 3 pre-release gate (offline suite; live LCM
only for write paths -- Part A is read-only, so offline suffices; plus `python -m build`
smoke, section 3 "Build check"); section 4 cut commit touching, IN ORDER:
  1. `flexicon/__init__.py` version
  2. `CHANGELOG.md` `[Unreleased]` -> `## [4.9.0] - <date>` (currently empty, `CHANGELOG.md:12`)
  3. `history.md`
  4. `RELEASE_NOTES_v4.9.0.md`
committed as `chore(release): cut 4.9.0 -- <theme>`; section 5 push `main` first, then
`git tag v4.9.0 && git push origin v4.9.0` (the tag is what publishes to PyPI via
`.github/workflows/publish.yml`), then `gh release create` (publishes docs).

Ratchets Part A must satisfy before the cut:
- `tests\test_297_init_stub_parity.py` (commit `3fbc922`) -- AST-only parity, every
  public name in `__init__.py` must appear in `__init__.pyi`'s `__all__` and vice versa
- `tests\test_pyi_return_annotation_ratchet.py` -- `FLExProject.py` and `.pyi` return
  annotations must not contradict
- `tests\test_docstring_example_ratchet.py` with baseline `tests\docstring_example_baseline.json`
- `tests\test_flexlibs2_alias_ratchet.py`

## 6. Repo state

Branch `main`; HEAD `598f41e chore(release): cut 4.8.0 -- the silent-failure sweep`;
working tree clean. `python -c "import flexicon"` resolves to
`D:\Github\_Projects\_LEX\flexicon\flexicon\__init__.py`, version `4.8.0`, via
`D:\Apps\anaconda3\Lib\site-packages\__editable__.pyflexicon-4.8.0.pth` -- yes, this
checkout is the editable install the MCP resolves.

## 7. Sizing

Roughly 10-13 files. New: `code\Grammar\ParserOperations.py` (~400-600 lines; compare
`StratumOperations.py` 378, `ReversalIndexOperations.py` 554) plus 1-3 offline test
modules. Edited: `FLExProject.py` (+1 property, ~30 lines), `FLExProject.pyi`,
`__init__.py`, `__init__.pyi` (`__all__` + `CAPABILITIES` token), `_op_aliases.py`,
`TextOperations.py` (`GetGenres`), `AllomorphOperations.py` (`GetOwningEntry`),
`MSAOperations.py` (readable-analysis reads), `CHANGELOG.md` / `history.md` /
`RELEASE_NOTES_v4.9.0.md`, plus the docstring-example baseline refresh.

The three read gaps are small and pattern-matched; the Parser facade plus its lazy
probe is the only genuinely new machinery.
