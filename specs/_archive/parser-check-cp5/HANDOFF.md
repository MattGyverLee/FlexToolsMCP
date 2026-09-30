# CP5 handoff: sandbox parsing moves into the parse worker (decision 2026-09-24)

Branch `feat/parser-check-cp5`. The working tree is clean apart from this file,
`reference/`, and the companion state files. Nothing from this session is committed.

## Where things stand

- Tasks T001–T094 are done (`tasks.md`). T095 (the live checks) was
  `needs_human`, blocked on **M-1**, "how do we get a working `hc`".
- **M-1 is resolved, but not the way the plan assumed.** The maintainer's
  direction: rely on the HermitCrab that ships with FieldWorks. FieldWorks 9
  ships the **engine** (`C:\Program Files\SIL\FieldWorks 9\SIL.Machine.Morphology.HermitCrab.dll`,
  FileVersion 3.8.2.0, the same engine Try A Word uses) and
  `GenerateHCConfig.exe`. It does **not** ship the `hc` console tool. On this
  machine: no `hc` on PATH, no .NET SDK, and the .NET 8 runtime only.
- **Decision (option 2 of 3):** the sandbox stops shelling out to an `hc`
  CLI. It parses the exported config **in the existing parse worker**, calling
  the FieldWorks engine directly. The maintainer picked this as the
  lowest-maintenance route: one parse path, no copy of `hc`'s program, no
  parsing of `hc`'s text output, and no command-language escaping.
  - Rejected, option 1: a packaged `hc` stand-in (`hc_fw.py`) run by
    `hcparse.ps1`. It was built and worked, and is kept in `reference/`. It was
    rejected because it duplicates `hc`'s program and `hc_output.py` depends
    on its exact text format, so both drift with every SIL.Machine or FLEx
    update.
  - Rejected, option 3: dropping sandbox parsing altogether.
- The maintainer's own framing of the question: "we've been calling the
  parser, why do we need all this new architecture?" Keep the redesign small
  and reuse what exists.

## Proven facts (verified live this session)

- The engine loads in a pythonnet `netfx` process. It targets netstandard2.0.
  It references `SIL.Core` 17, while FieldWorks ships 18 and FLEx relies on
  binding redirects in `FieldWorks.exe.config`. A host process therefore
  needs an `AppDomain.AssemblyResolve` handler that loads any assembly by
  simple name from the FieldWorks folder. That handler is in
  `reference/hc_fw_prototype.py` (`Engine.__init__`).
- The engine calls themselves, all public API (see `Engine.morph_infos` in the
  prototype):
  - `XmlLanguageLoader.Load(path)` (or `Load(path, Action<Exception,string>)`
    for hc's `-c`), then `Morpher(TraceManager(), language)`, then
    `ParseWord(word)`. That returns `Word`s, or throws
    `InvalidShapeException` (`.Position` is 0-based).
  - The form and gloss of one morph, as hc's `MorphInfo` builds them: the
    morph annotation's children whose `HermitCrabExtensions.Type(a) !=
    HCFeatureSystem.Morph`, their `Range.Start` collected into a
    `List[ShapeNode]`, then `HermitCrabExtensions.ToString(nodes,
    word.Stratum.CharacterDefinitionTable, False)`. The gloss is
    `word.GetAllomorph(morph).Morpheme.Gloss`, with an empty gloss shown as `?`.
- Load plus compile of a 62 KB config takes about 0.25 s; the first parse
  takes about 190 ms, and later ones about 50 ms.
- Test fixture: `GenerateHCConfig.exe` on a **scratch copy** of
  `IndonesianHC-Complete` took 2.7 s. `pukul` gives `pukul/hit`; `memukul`
  gives `mem-ukul VBL-hit`. The orthography is IPA (`mɑnis`, `dɑlɑm`), so
  Latin test words hit invalid-segment errors.
- **Parity gap to note (SC-003):** FLEx's `HCParser.LoadParser`
  (`fieldworks/Src/LexText/ParserCore/HCParser.cs:145-182`) applies the
  project's `ParserParameters/HC` settings to the Morpher: `DelReapps`,
  `MaxRoots` → `MaxStemCount`, `MergeAnalyses`, `MaxAlternatives`, and
  `GuessRoots` passed to `ParseWord`. The `hc` CLI applies none of them.
  Since the worker now calls the engine itself, it can apply them too and get
  real Try A Word parity. Recommended; the values come from the project's
  `MorphologicalDataOA.ParserParameters` XML.

## What to build (suggested order)

1. **Amend the CP5 docs first**: `plan.md` (the M-1 row and research R-15),
   `research.md`, `contracts/hcparse.md` and `contracts/tools.md` (health
   `hc_source` and the component vocabulary), then `tasks.md` (replace T095;
   add re-plan tasks). Run `/speckit-companion-plan` or `-tasks` if you want
   companion tracking. Record the decision with
   `write-context.py --decision`.
2. **Worker**: add a sandbox parse operation to `server/parse/worker_main.py`
   (`_RealBackend` / `ParseWorker`). It loads a config path through
   `XmlLanguageLoader`, caches the Morpher per (config path, mtime), and
   parses and tests words, returning the same structured analyses the sandbox
   runner already expects. Keep the CP1 boundary:
   `tests/test_cp1_boundary.py` pins parse operations to
   `server/parse/worker_main.py` only (`CP2B_PARSE_OPERATION_ALLOWLIST`).
   Worker-side code fits that allowlist, so no boundary amendment is needed.
3. **Sandbox runner/client**: `server/sandbox/client.py` (`SandboxClient`,
   built by `server/parse/runner.py:687`) currently runs `hcparse.ps1 -Mode
   Parse/Test` and tails `hc-stdout.txt` through `hc_output.py`. Point it at
   the worker instead. Keep **Generate** mode as it is: the allowlisted copy
   plus GenerateHCConfig, cached by `sandbox/cache.py`. Only Parse/Test move.
4. **Discovery and health**: the sandbox's parse engine becomes "the FieldWorks
   HermitCrab DLL is present and loads". Retire or demote `hc` discovery in
   `parser_probe.py` (`discover_hc_tool`, `probe_hc`, and the `hc -h` narrowing
   in `test_cp1_boundary.py`), and change the health rungs and install hints
   in `handlers/diagnostic_health.py` and `handlers/parse.py`
   (`HC_INSTALL_HINT`). The skew advisory becomes moot: the engine is
   FieldWorks' own.
5. **Remove the dead parts** once nothing uses them: the `hcparse.ps1`
   Parse/Test modes, `hc_output.py`, the word-quoting and leading-dash rules
   (R-09, L-2), and `tests/fakes/hc_fake.py`, with their tests. Bump
   `HCPARSE_VERSION` (it is part of the cache key) if the script changes.
6. **Live checks (old T095)**: run the S/L scenarios that still apply, against
   a scratch copy, with `-m requires_flex`. Mind the memories: "read-only"
   live tests have rewritten real `.fwdata`, and a non-shared project allows
   only one opener.

## Reference material

- `reference/hc_fw_prototype.py`: the rejected `hc` host. It is useful for the
  engine-loading code (`Engine`), `morph_infos`, the trace printer, and the
  test-command matching semantics (expected parses matched as ordered
  (form, gloss) sequences).
- `reference/hc-host-attempt.diff`: the rejected wiring into `parser_probe`,
  `hcparse.ps1`, the client and the health hints. Shows every place `hc`
  discovery touches.
- `hc` 3.8.2 source: `git -C C:\Github\machine show v3.8.2:src/SIL.Machine.Morphology.HermitCrab.Tool/<file>`.
- The test venv is `.venv/Scripts/python.exe`. The system `python` lacks
  pydantic. Before this session's edits, the non-live sandbox, health and
  boundary suites passed (735 tests).
