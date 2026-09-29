"""
The sandbox backend (CP5 re-plan, contracts/sandbox-worker.md): FieldWorks'
bundled HermitCrab engine run in-process over a generated configuration.

The other module allowed to run parse operations, and the only place the
engine may be built (tests/test_cp1_boundary.py,
CP5_SANDBOX_ENGINE_ALLOWLIST).

Worker-process only: imported by `worker_main.py` (the parse worker) and the
filing worker, never by the MCP server process -- see `worker_main.py`'s
header for why.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from typing import Any, Optional

from .worker_backend import (
    _ParseBackend,
)


# ---------------------------------------------------------------------------
# The sandbox backend (CP5 re-plan, contracts/sandbox-worker.md)
# ---------------------------------------------------------------------------

#: Messages a sandbox worker refuses (D1, FR-049): each assumes an opened
#: FieldWorks project, and a sandbox worker never has one.
SANDBOX_REFUSED_MESSAGES = frozenset({
    "resolve", "engine_check", "resolve_scope", "parser_parameters",
    "agent_probe", "filing_gate", "filing_preview",
})
SANDBOX_REFUSAL_MESSAGE = "not available in sandbox mode"

#: `ParseWord`'s per-word outcomes (contracts/sandbox-worker.md section 4).
SANDBOX_OUTCOMES = ("parsed", "not_parsed", "invalid_segment", "error")

#: Morpher parameters applied by property, when the loaded engine has the
#: property (D3): parameter key -> `Morpher` property name. `guess_roots` is
#: not a property; it is `ParseWord`'s third argument.
_MORPHER_PROPERTIES = (
    ("del_reapps", "DeletionReapplications"),
    ("max_roots", "MaxStemCount"),
    ("merge_analyses", "MergeEquivalentAnalyses"),
    ("max_alternatives", "MaxAlternatives"),
)


class SandboxJobFailed(RuntimeError):
    """The first `parse` of a sandbox run cannot proceed (section 5).

    `failure` is `engine_unavailable` or `id_map_invalid`. Carried to the
    server as `parser_job_failed` with a partial `detail`; `SandboxClient`
    fills in the rest of `ParserJobFailedDetail`.
    """

    error_code = "parser_job_failed"

    def __init__(self, failure: str, message: str) -> None:
        super().__init__(message)
        self.failure = failure
        self.detail = {"failure": failure}


class _InvalidSegment(Exception):
    """`InvalidShapeException`, carried out of the engine as plain data."""

    def __init__(self, position: Optional[int]) -> None:
        super().__init__(f"invalid segment at position {position}")
        self.position = position


class _SandboxBackend(_ParseBackend):
    """Parse an exported HermitCrab config with FieldWorks' own engine.

    No project, no LCM, no flexicon: the config is loaded through
    `XmlLanguageLoader` and parsed by a `Morpher`, the calls Try A Word
    makes, and the result is shaped by FLEx's own rules (`hc_engine`).
    Loading is lazy -- at the first `parse`, never at spawn -- and the
    Morpher is then held for the process's life: `release()` keeps it,
    because there is no project lock to drop (section 7).

    The engine calls live in `_load_engine` and `_parse_raw`, and only
    here: this class is the one place `Morpher` and `XmlLanguageLoader` are
    allowed (`tests/test_cp1_boundary.py`, D2). `_StubSandboxBackend`
    replaces exactly those two methods.
    """

    SANDBOX = True

    def __init__(
        self,
        config_path: str,
        *,
        hc_params_path: Optional[str] = None,
        id_map_path: Optional[str] = None,
        engine_dir: Optional[str] = None,
        named_sandbox: bool = False,
    ) -> None:
        self._config_path = config_path
        self._hc_params_path = hc_params_path
        self._id_map_path = id_map_path
        self._engine_dir = engine_dir
        self._named_sandbox = named_sandbox

        self._loaded = False
        #: A load that failed, kept so a second `parse` fails the same way
        #: without trying again (section 8, "surfaces once").
        self._failure: Optional[SandboxJobFailed] = None
        self._id_map = None
        self._parameters: dict[str, Any] = {}
        self._parameters_applied: list[str] = []
        self._load_errors: list[dict[str, Any]] = []
        self._engine_version: Optional[str] = None
        self._guess_roots = True
        self.load_count = 0

        # Set by `_load_engine`.
        self._morpher: Any = None
        self._engine: dict[str, Any] = {}

    # -- lifecycle ----------------------------------------------------------

    def ensure_grammar(self, run_id: str) -> bool:
        if self._failure is not None:
            raise self._failure
        if self._loaded:
            return False
        from . import hc_engine

        try:
            if self._id_map_path:
                self._id_map = hc_engine.load_id_map(self._id_map_path)
        except hc_engine.IdMapInvalid as exc:
            self._failure = SandboxJobFailed("id_map_invalid", str(exc))
            raise self._failure from exc
        try:
            self._parameters = hc_engine.load_hc_parameters(self._hc_params_path)
            self._guess_roots = bool(self._parameters.get("guess_roots", True))
            self._load_engine()
        except Exception as exc:  # noqa: BLE001 -- any load failure is one outcome
            self._failure = SandboxJobFailed("engine_unavailable", f"{type(exc).__name__}: {exc}")
            raise self._failure from exc
        self._loaded = True
        self.load_count += 1
        return True

    def release(self) -> None:
        """Keep the Morpher: nothing here holds a project (section 7)."""
        return None

    def load_error_baseline(self, load_started: float) -> Optional[dict[str, Any]]:
        """The load's facts, sent once per run as `load_baseline`.

        Besides the loader's error callbacks (folded into
        `meta.sandbox.generation.load_errors`), this carries what only the
        worker knows: which parameters the engine accepted, whether shaping
        ran against a map, and the engine's version.
        """
        return {
            "captured": True,
            "source": self._config_path,
            "errors": list(self._load_errors),
            "parameters": dict(self._parameters),
            "parameters_applied": list(self._parameters_applied),
            "id_map": "valid" if self._id_map is not None else "absent",
            "engine_version": self._engine_version,
        }

    # -- parsing ------------------------------------------------------------

    def parse(
        self,
        wordform: str,
        level: str,
        restricted_to: Optional[tuple[int, ...]],
        *,
        vernacular_ws: Optional[str] = None,
    ) -> dict[str, Any]:
        """One word, every level answered as `batch` (section 3)."""
        from . import hc_engine

        started = time.perf_counter()
        parse: dict[str, Any] = {
            "outcome": "error", "analyses": None, "position": None,
            "error_message": None, "parse_time_ms": None,
        }
        try:
            raw_analyses = self._parse_raw(wordform)
        except _InvalidSegment as exc:
            parse["outcome"] = "invalid_segment"
            parse["position"] = exc.position
            return {"parse": parse, "trace_xml": None}
        except Exception as exc:  # noqa: BLE001 -- one word's error, not the run's
            parse["error_message"] = f"{type(exc).__name__}: {exc}"
            parse["parse_time_ms"] = int((time.perf_counter() - started) * 1000)
            return {"parse": parse, "trace_xml": None}
        parse["parse_time_ms"] = int((time.perf_counter() - started) * 1000)

        analyses = []
        for raw in raw_analyses:
            if self._id_map is None:
                morphs = hc_engine.unshaped(raw)
            else:
                morphs = hc_engine.shape_analysis(
                    raw, self._id_map, named_sandbox=self._named_sandbox
                )
            if morphs is None:
                continue  # rule (d): the whole analysis is dropped
            analyses.append({"morphs": morphs, "guessed": any(m["guessed"] for m in morphs)})

        parse["outcome"] = "parsed" if analyses else "not_parsed"
        parse["analyses"] = analyses if analyses else None
        return {"parse": parse, "trace_xml": None}

    # -- the engine (the D2 allowlist: only these two methods) ----------------

    def _load_engine(self) -> None:
        """Load FieldWorks' HermitCrab, then the config, then a Morpher."""
        from . import hc_engine

        directory = hc_engine.resolve_engine_dir(self._engine_dir)
        dll = directory / hc_engine.ENGINE_DLL
        # The CLR may already be up: an `assemblies` diagnostic imports `clr`,
        # which starts pythonnet's default runtime (.NET Framework on Windows).
        # `load()` after that fails, so it is only called on a cold process.
        if "clr" not in sys.modules:
            try:
                from pythonnet import load

                load("netfx")
            except Exception as exc:  # noqa: BLE001
                if "already" not in str(exc).lower():
                    raise hc_engine.EngineUnavailable(
                        f"the .NET Framework runtime could not be loaded: {exc}"
                    ) from exc
        import clr
        import System

        base = str(directory)

        # FieldWorks resolves its dependencies through binding redirects in
        # FieldWorks.exe.config (SIL.Core 17 -> 18, ...). This process has
        # none, so resolve any assembly by simple name from the same folder.
        def resolve(sender, args):
            name = System.Reflection.AssemblyName(args.Name).Name
            candidate = System.IO.Path.Combine(base, name + ".dll")
            if System.IO.File.Exists(candidate):
                return System.Reflection.Assembly.LoadFrom(candidate)
            return None

        System.AppDomain.CurrentDomain.AssemblyResolve += System.ResolveEventHandler(resolve)
        self._resolver = resolve
        System.Reflection.Assembly.LoadFrom(str(dll))
        clr.AddReference(str(dll))

        from SIL.Machine.Annotations import ShapeNode
        from SIL.Machine.Morphology.HermitCrab import (
            HCFeatureSystem,
            HermitCrabExtensions,
            InvalidShapeException,
            Morpher,
            TraceManager,
            XmlLanguageLoader,
        )
        from System.Collections.Generic import List as NetList

        with contextlib.suppress(Exception):
            info = System.Diagnostics.FileVersionInfo.GetVersionInfo(str(dll))
            self._engine_version = str(info.FileVersion)

        errors = self._load_errors

        def on_error(exc, identifier):
            errors.append({
                "type": str(exc.GetType().Name),
                "id": None if identifier is None else str(identifier),
                "message": str(exc.Message),
            })

        handler = System.Action[System.Exception, System.String](on_error)
        language = XmlLanguageLoader.Load(self._config_path, handler)
        morpher = Morpher(TraceManager(), language)

        morpher_type = morpher.GetType()
        applied = []
        for key, prop in _MORPHER_PROPERTIES:
            if morpher_type.GetProperty(prop) is None:
                continue
            value = self._parameters.get(key)
            setattr(morpher, prop, bool(value) if isinstance(value, bool) else int(value))
            applied.append(key)
        # `ParseWord(word, out trace, guessRoot)` exists in every engine that
        # has `Morpher` at all, so `guess_roots` always takes effect.
        applied.append("guess_roots")
        self._parameters_applied = [k for k in hc_engine.HC_PARAMETER_KEYS if k in applied]

        self._morpher = morpher
        self._engine = {
            "ShapeNode": ShapeNode,
            "NetList": NetList,
            "HCFeatureSystem": HCFeatureSystem,
            "X": HermitCrabExtensions,
            "InvalidShapeException": InvalidShapeException,
        }

    def _parse_raw(self, wordform: str) -> list:
        """`ParseWord`, then each analysis's morphs as `hc_engine.RawMorph`s."""
        from . import hc_engine

        engine = self._engine
        try:
            words, _trace = self._morpher.ParseWord(wordform, None, self._guess_roots)
        except engine["InvalidShapeException"] as exc:
            position = None
            with contextlib.suppress(Exception):
                position = int(exc.Position)
            raise _InvalidSegment(position) from None

        def prop(properties, name):
            if not properties.ContainsKey(name):
                return None
            return properties[name]

        analyses = []
        for word in words:
            table = word.Stratum.CharacterDefinitionTable
            raw = []
            for position, morph in enumerate(word.Morphs):
                # hc's own MorphInfo: the morph's non-Morph children, rendered.
                nodes = engine["NetList"][engine["ShapeNode"]]()
                for child in morph.Children:
                    if engine["X"].Type(child) != engine["HCFeatureSystem"].Morph:
                        nodes.Add(child.Range.Start)
                form = str(engine["X"].ToString(nodes, table, False))
                allomorph = word.GetAllomorph(morph)
                morpheme = allomorph.Morpheme
                gloss = str(morpheme.Gloss) if morpheme.Gloss else "?"
                form_id_value = prop(allomorph.Properties, "ID")
                form_id = None
                if form_id_value is not None:
                    form_id = hc_engine.parse_int_property(form_id_value) or 0
                msa_id = hc_engine.parse_int_property(prop(morpheme.Properties, "ID"))
                infl_type_id = hc_engine.parse_int_property(
                    prop(morpheme.Properties, "InflTypeID")) or 0
                raw.append(hc_engine.RawMorph(
                    form=form,
                    gloss=gloss,
                    guessed=bool(allomorph.Guessed),
                    form_id=form_id,
                    form_id2=hc_engine.parse_int_property(prop(allomorph.Properties, "ID2")) or 0,
                    msa_id=msa_id,
                    infl_type_id=infl_type_id,
                    is_affix_process=str(allomorph.GetType().Name) == "AffixProcessAllomorph",
                    morpheme_key=hc_engine.morpheme_key(
                        msa_id, morpheme.Id, position, infl_type_id),
                ))
            analyses.append(raw)
        return analyses


def _stub_script(config_path: str) -> dict:
    """The stub engine's script: `--config` as a JSON object, or -- for a
    config the fake GenerateHCConfig wrote (tests/fakes/generate_fake.py) --
    the `stub` key of its `<FakeGrammar>` JSON payload. Anything else is
    `{}`, so every word parses as itself."""
    try:
        with open(config_path, encoding="utf-8-sig") as handle:
            text = handle.read()
    except OSError:
        return {}
    try:
        script = json.loads(text)
    except ValueError:
        script = None
        if text.lstrip().startswith("<"):
            import xml.etree.ElementTree as ET

            try:
                payload = ET.fromstring(text).find("FakeGrammar")
                script = json.loads(payload.text or "").get("stub") if payload is not None else None
            except (ET.ParseError, ValueError, AttributeError):
                script = None
    return script if isinstance(script, dict) else {}


class _StubSandboxBackend(_SandboxBackend):
    """`--stub --sandbox`: the sandbox backend with a scriptable engine.

    Everything but the two engine methods is `_SandboxBackend`'s own --
    parameters, the id map and its failures, shaping, the outcome shapes --
    so the client and the handler are provable without FieldWorks. The
    "engine" is `--config` read as JSON when it parses as a JSON object (or
    the `stub` key of a fake-generated config's payload, `_stub_script`):

        {"load_fail": "<message>",            -- the load raises
         "load_errors": [{...}],               -- reported through the callback
         "words": {"<word>": [[{morph}...]]    -- analyses of RawMorph fields
                   | {"invalid_segment": int}  -- InvalidShapeException
                   | {"error": "<message>"}    -- any other exception
                   | {"crash": int}            -- the process exits with that code
                   | {"sleep": seconds}}}      -- sleeps, then parses as unscripted

    An unscripted word parses as one morph, itself, glossed `stub`.
    """

    def __init__(self, config_path: str, *, parse_seconds: float = 0.0, **kwargs: Any) -> None:
        super().__init__(config_path, **kwargs)
        self._parse_seconds = parse_seconds
        self._script: dict[str, Any] = {}

    def _load_engine(self) -> None:
        script = _stub_script(self._config_path)
        if script.get("load_fail"):
            raise RuntimeError(str(script["load_fail"]))
        self._script = script
        self._load_errors.extend(script.get("load_errors") or [])
        self._engine_version = "stub"
        self._parameters_applied = [
            k for k in self._parameters if k != "max_alternatives"
        ]

    def _parse_raw(self, wordform: str) -> list:
        from . import hc_engine

        if self._parse_seconds:
            time.sleep(self._parse_seconds)
        scripted = (self._script.get("words") or {}).get(wordform)
        if scripted is None:
            return [[hc_engine.RawMorph(form=wordform, gloss="stub", guessed=False,
                                        form_id=1, msa_id=2, morpheme_key=wordform)]]
        if isinstance(scripted, dict):
            if "invalid_segment" in scripted:
                raise _InvalidSegment(scripted["invalid_segment"])
            if "crash" in scripted:
                sys.stdout.flush()
                os._exit(int(scripted["crash"]))
            if "sleep" in scripted:
                time.sleep(float(scripted["sleep"]))
                return [[hc_engine.RawMorph(form=wordform, gloss="stub", guessed=False,
                                            form_id=1, msa_id=2, morpheme_key=wordform)]]
            raise RuntimeError(str(scripted.get("error")))
        return [
            [hc_engine.RawMorph(**{"morpheme_key": m.get("form"), "guessed": False, **m})
             for m in analysis]
            for analysis in scripted
        ]
