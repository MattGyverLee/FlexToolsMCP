#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`hc`, hosted on the HermitCrab engine that ships with FieldWorks.

FieldWorks bundles `SIL.Machine.Morphology.HermitCrab.dll` -- the engine
behind Try A Word -- but not the stand-alone `hc` console tool (a .NET 10
dotnet global tool, `SIL.Machine.Morphology.HermitCrab.Tool`). This script
is that tool, ported line for line from SIL.Machine v3.8.2
(`src/SIL.Machine.Morphology.HermitCrab.Tool`: Program.cs, ParseCommand.cs,
TestCommand.cs, StatsCommand.cs, TracingCommand.cs, Extensions.cs,
MorphInfo.cs), and run through pythonnet on the .NET Framework runtime
FieldWorks itself uses, against FieldWorks' own copy of the engine. The
engine is therefore always the exact version FieldWorks parses with.

It is a drop-in `hc` for the sandbox spine (`hcparse.ps1`):

  * the same options (`-i`, `-o`, `-s`, `-c`, `-h`) and exit codes (-1 on
    usage, `IO Error:` and `Load Error:`; 0 otherwise);
  * the same commands (`parse`, `test`, `stats`, `tracing`), dispatched
    from a script through hc's own `SplitCommandLine`;
  * the same output, byte for byte where the spine reads it: UTF-16LE, no
    BOM, `\\r\\n` line ends, flushed per write.

Two deliberate differences, both only where hc would fail to start:

  * `-h` prints the usage text and then checks that the engine loads (it
    loads no grammar and parses nothing). If it cannot load, the reason goes
    to stderr as one `hc: engine unavailable: <why>` line and the exit code
    is ENGINE_UNAVAILABLE_EXIT, so discovery reads "found, but cannot
    start" -- the same verdict a missing .NET runtime gets for real hc.
  * a run whose engine cannot load prints `Load Error: <why>` (exit -1),
    the same shape as a grammar hc cannot load.

The engine directory is `FLEXTOOLSMCP_HC_ENGINE_DIR` when set (the MCP sets
it to the FieldWorks install it binds to), else the standard FieldWorks
locations. The script imports nothing from the package.

Quirks kept on purpose, because parity with hc is the point: a `\\` before
a `|` or `:` in a `test -p` expectation loops forever (TestCommand.Split;
hcparse.ps1 refuses such expectations), and an unreadable `-p` leaks into
the next `test` command (the list is cleared in a `finally` the parse of
the expectations never reaches).
"""

from __future__ import annotations

import os
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

#: The engine assembly, as FieldWorks ships it.
ENGINE_DLL = "SIL.Machine.Morphology.HermitCrab.dll"

#: Env override for the directory holding ENGINE_DLL and its dependencies.
ENGINE_DIR_ENV_VAR = "FLEXTOOLSMCP_HC_ENGINE_DIR"

#: `-h` could print the usage text but the engine did not load. Distinct
#: from hc's -1 so discovery can tell "cannot start" from "is not hc".
ENGINE_UNAVAILABLE_EXIT = 3

#: Prefix of the one stderr line `-h` writes when the engine will not load.
ENGINE_UNAVAILABLE_PREFIX = "hc: engine unavailable: "

#: .NET's unhandled-exception process exit code (0xE0434352), signed.
UNHANDLED_EXCEPTION_EXIT = 0xE0434352 - (1 << 32)

USAGE_LINES = [
    "Usage: hc [OPTIONS]",
    "HermitCrab.NET is a phonological and morphological parser.",
    "",
    "  -i, --input-file=FILE      read configuration from FILE",
    "  -o, --output-file=FILE     write results to FILE",
    "  -s, --script-file=FILE     runs commands from FILE",
    "  -c, --continue             continues when an error occurs while loading the",
    "                               configuration",
    "  -h, --help                 show this help message and exit",
]

_NL = "\r\n"


# ---------------------------------------------------------------------------
# Writers: Console.Out (UTF-16LE, Encoding.Unicode) and an -o StreamWriter
# ---------------------------------------------------------------------------


class _Writer:
    """A TextWriter over a byte stream: `Write` / `WriteLine`, flushed."""

    def __init__(self, stream, encoding: str) -> None:
        self._stream = stream
        self._encoding = encoding

    def write(self, text: str) -> None:
        self._stream.write(text.encode(self._encoding, errors="surrogatepass"))
        self._stream.flush()

    def writeline(self, text: str = "") -> None:
        self.write(text + _NL)

    def close(self) -> None:
        self._stream.close()


CONSOLE = _Writer(sys.stdout.buffer, "utf-16-le")


def _u16len(text: str) -> int:
    return len(text.encode("utf-16-le", errors="surrogatepass")) // 2


def _pad_right(text: str, width: int) -> str:
    return text + " " * max(0, width - _u16len(text))


def write_parse(out: _Writer, parse: Sequence[Tuple[str, str]]) -> None:
    """Extensions.WriteParse: each column padded to max(len(form),
    len(gloss)) in UTF-16 code units, zero-width morphs skipped."""
    for prefix, pick in (("Morphs: ", 0), ("Gloss:  ", 1)):
        out.write(prefix)
        first = True
        for morph in parse:
            width = max(_u16len(morph[0]), _u16len(morph[1]))
            if width > 0:
                if not first:
                    out.write(" ")
                out.write(_pad_right(morph[pick], width))
                first = False
        out.writeline()


# ---------------------------------------------------------------------------
# Command lines: Mono.Options for hc's options, Program.SplitCommandLine
# ---------------------------------------------------------------------------

_OPTION_RE = re.compile(r"^(--|-|/)([^=:]+)(?:[=:](.*))?$")


class OptionError(Exception):
    """Mono.Options' OptionException."""


def parse_options(argv: Sequence[str], spec: Dict[str, Tuple[str, bool]]) -> Tuple[Dict[str, List[Any]], List[str]]:
    """Mono.Options over ``spec`` (name -> (key, takes_value)).

    Returns ``(values, extra)``: every value per key, in order (a flag is
    ``True``), and the unprocessed arguments. An unknown option is left in
    ``extra``; ``--`` ends option processing and is dropped; a bundled
    single-dash flag carries its value inline (``-pX`` is ``-p X``).
    """
    values: Dict[str, List[Any]] = {}
    extra: List[str] = []
    k = 0
    processing = True
    while k < len(argv):
        arg = argv[k]
        k += 1
        if processing and arg == "--":
            processing = False
            continue
        if not processing:
            extra.append(arg)
            continue
        m = _OPTION_RE.match(arg)
        if not m:
            extra.append(arg)
            continue
        flag, name, inline = m.group(1), m.group(2), m.group(3)
        if name in spec:
            key, takes_value = spec[name]
            if takes_value:
                if inline is None:
                    if k >= len(argv):
                        raise OptionError(f"Missing required value for option '{flag}{name}'.")
                    inline = argv[k]
                    k += 1
                values.setdefault(key, []).append(inline)
            else:
                values.setdefault(key, []).append(True)
            continue
        # A bundled single-dash option: `-pX` (value) or `-ab` (flags).
        if flag == "-" and name[:1] in spec and inline is None:
            key, takes_value = spec[name[:1]]
            if takes_value:
                values.setdefault(key, []).append(name[1:])
                continue
            if all(ch in spec and not spec[ch][1] for ch in name):
                for ch in name:
                    values.setdefault(spec[ch][0], []).append(True)
                continue
        extra.append(arg)
    return values, extra


_HC_OPTIONS: Dict[str, Tuple[str, bool]] = {
    "i": ("i", True),
    "input-file": ("i", True),
    "o": ("o", True),
    "output-file": ("o", True),
    "s": ("s", True),
    "script-file": ("s", True),
    "c": ("c", False),
    "continue": ("c", False),
    "h": ("h", False),
    "help": ("h", False),
}


def split_command_line(line: str) -> List[str]:
    """Program.SplitCommandLine, verbatim in behaviour."""
    chars = list(line)
    in_single = in_double = False
    for idx in range(len(chars)):
        if chars[idx] == '"' and not in_single:
            in_double = not in_double
            chars[idx] = "\n"
        if chars[idx] == "'" and not in_double:
            in_single = not in_single
            chars[idx] = "\n"
        if not in_single and not in_double and chars[idx] == " ":
            chars[idx] = "\n"
    return [part for part in "".join(chars).split("\n") if part]


def read_script_lines(path: str) -> List[str]:
    """StreamReader.ReadLine over a UTF-8 file (a BOM is detected and dropped)."""
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8-sig", errors="replace")
    lines = re.split(r"\r\n|\r|\n", text)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def show_help(out: _Writer = CONSOLE) -> None:
    for line in USAGE_LINES:
        out.writeline(line)


# ---------------------------------------------------------------------------
# The engine (pythonnet, .NET Framework)
# ---------------------------------------------------------------------------


class EngineUnavailable(Exception):
    """The FieldWorks HermitCrab engine could not be loaded."""


def _default_engine_dirs() -> List[Path]:
    """Where to look when no directory is passed in: the same install
    locations ``server/versioning.py`` searches (``FIELDWORKS_DLL_PATH``,
    then the standard FieldWorks 9 folders). A copy, not an import, so this
    script stays free of the package."""
    dirs: List[Path] = []
    env_path = os.environ.get("FIELDWORKS_DLL_PATH")
    if env_path:
        dirs.append(Path(env_path))
    dirs.extend([
        Path(r"C:/Program Files/SIL/FieldWorks 9"),
        Path(r"C:/Program Files (x86)/SIL/FieldWorks 9"),
    ])
    return dirs


def engine_dir() -> Path:
    """``FLEXTOOLSMCP_HC_ENGINE_DIR`` when set (the MCP always sets it), else
    the first default location that holds the engine."""
    override = os.environ.get(ENGINE_DIR_ENV_VAR)
    if override:
        return Path(override)
    for candidate in _default_engine_dirs():
        if (candidate / ENGINE_DLL).is_file():
            return candidate
    raise EngineUnavailable("no FieldWorks installation was found")


class Engine:
    """The loaded engine's types, and the few calls hc makes on them."""

    def __init__(self, directory: Path) -> None:
        dll = directory / ENGINE_DLL
        if not dll.is_file():
            raise EngineUnavailable(f"{ENGINE_DLL} not found in {directory}")
        try:
            from pythonnet import load

            load("netfx")
        except Exception as exc:  # noqa: BLE001 -- any failure is "cannot start"
            if "already" not in str(exc).lower():
                raise EngineUnavailable(f"the .NET Framework runtime could not be loaded: {exc}")
        try:
            import clr  # noqa: F401
            import System

            base = str(directory)

            # FieldWorks resolves its dependencies through binding redirects in
            # FieldWorks.exe.config (SIL.Core 17 -> 18, ...); a host process has
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
                AffixTemplate,
                FailureReason,
                HCFeatureSystem,
                HermitCrabExtensions,
                IMorphologicalRule,
                InvalidShapeException,
                IPhonologicalRule,
                Morpher,
                Stratum,
                TraceManager,
                TraceType,
                XmlLanguageLoader,
            )
            from System.Collections.Generic import List as NetList
        except EngineUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            raise EngineUnavailable(f"{ENGINE_DLL} could not be loaded: {exc}")

        self.System = System
        self.ShapeNode = ShapeNode
        self.NetList = NetList
        self.AffixTemplate = AffixTemplate
        self.FailureReason = FailureReason
        self.HCFeatureSystem = HCFeatureSystem
        self.X = HermitCrabExtensions
        self.IMorphologicalRule = IMorphologicalRule
        self.InvalidShapeException = InvalidShapeException
        self.IPhonologicalRule = IPhonologicalRule
        self.Morpher = Morpher
        self.Stratum = Stratum
        self.TraceManager = TraceManager
        self.TraceType = TraceType
        self.XmlLanguageLoader = XmlLanguageLoader

    def load_language(self, path: str, quit_on_error: bool):
        if quit_on_error:
            return self.XmlLanguageLoader.Load(path)
        ignore = self.System.Action[self.System.Exception, self.System.String](lambda ex, ident: None)
        return self.XmlLanguageLoader.Load(path, ignore)

    def morph_infos(self, parse) -> List[Tuple[str, str]]:
        """Extensions.GetMorphInfos / MorphInfo(Word, Annotation<ShapeNode>)."""
        infos: List[Tuple[str, str]] = []
        table = parse.Stratum.CharacterDefinitionTable
        for morph in parse.Morphs:
            nodes = self.NetList[self.ShapeNode]()
            for child in morph.Children:
                if self.X.Type(child) != self.HCFeatureSystem.Morph:
                    nodes.Add(child.Range.Start)
            form = self.X.ToString(nodes, table, False)
            gloss = parse.GetAllomorph(morph).Morpheme.Gloss
            if not gloss:
                gloss = "?"
            infos.append((str(form), str(gloss)))
        return infos


# ---------------------------------------------------------------------------
# HCContext and the commands
# ---------------------------------------------------------------------------


class Context:
    """HCContext: the language, the morpher, the output and the counters."""

    def __init__(self, engine: Engine, language, out: _Writer) -> None:
        self.engine = engine
        self.language = language
        self.out = out
        self.morpher = None
        self.reset_parse_stats()
        self.reset_test_stats()

    def compile(self) -> None:
        self.morpher = self.engine.Morpher(self.engine.TraceManager(), self.language)

    def reset_parse_stats(self) -> None:
        self.parse_count = self.successful_parse_count = 0
        self.failed_parse_count = self.error_parse_count = 0

    def reset_test_stats(self) -> None:
        self.test_count = self.passed_test_count = 0
        self.failed_test_count = self.error_test_count = 0


class Command:
    """A ManyConsole ConsoleCommand: a name, options, a fixed argument count."""

    name = ""
    options: Dict[str, Tuple[str, bool]] = {}
    #: None: any number of additional arguments.
    arguments: Optional[int] = None

    def __init__(self, context: Context) -> None:
        self.context = context

    def run(self, values: Dict[str, List[Any]], remaining: List[str]) -> int:
        raise NotImplementedError


class ParseCommand(Command):
    name = "parse"
    arguments = 1

    def run(self, values, remaining) -> int:
        ctx, eng, out = self.context, self.context.engine, self.context.out
        word = remaining[0]
        try:
            ctx.parse_count += 1
            out.writeline(f'Parsing "{word}"')
            started = time.perf_counter()
            results, trace = ctx.morpher.ParseWord(word, None)
            results = list(results)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if not results:
                ctx.failed_parse_count += 1
                out.writeline("No valid parses.")
            else:
                ctx.successful_parse_count += 1
                for index, result in enumerate(results, 1):
                    out.writeline(f"Parse {index}")
                    write_parse(out, eng.morph_infos(result))
            if ctx.morpher.TraceManager.IsTracing:
                self._print_trace(trace, 0, set())
            out.writeline(f"Parse time: {elapsed_ms}ms")
            out.writeline()
            return 0
        except eng.InvalidShapeException as ise:
            ctx.error_parse_count += 1
            out.writeline(f"The word contains an invalid segment at position {ise.Position + 1}.")
            out.writeline()
            return 1

    # -- tracing (ParseCommand.PrintTrace) -----------------------------------

    def _print_trace(self, trace, indent: int, line_indices: set) -> None:
        eng, out = self.context.engine, self.context.out
        out.write(_TRACE_TYPE_STRINGS.get(str(trace.Type), "") or "")
        out.write(" [")
        first = True
        rule_label = self._rule_label(trace.Source)
        if rule_label:
            if trace.SubruleIndex >= 0:
                out.write(f"{rule_label}: {trace.Source.Name}({trace.SubruleIndex})")
            else:
                out.write(f"{rule_label}: {trace.Source.Name}")
            first = False
        analysis = str(trace.Type) in _ANALYSIS_TRACE_TYPES
        for label, word in (("Input", trace.Input), ("Output", trace.Output)):
            if word is None:
                continue
            if not first:
                out.write(", ")
            first = False
            table = word.Stratum.CharacterDefinitionTable
            shape = (
                eng.X.ToRegexString(word.Shape, table, True)
                if analysis
                else eng.X.ToString(word.Shape, table, True)
            )
            out.write(f"{label}: {shape}")
        if str(trace.FailureReason) != "None":
            if not first:
                out.write(", ")
            out.write(f"Reason: {trace.FailureReason}")
        out.writeline("]")

        if not trace.IsLeaf:
            children = list(trace.Children)
            for i, child in enumerate(children):
                self._print_indent(indent, line_indices)
                out.writeline("|")
                self._print_indent(indent, line_indices)
                out.write("+-")
                last = i == len(children) - 1
                if not last:
                    line_indices.add(indent)
                self._print_trace(child, indent + 2, line_indices)
                if not last:
                    line_indices.discard(indent)

    def _print_indent(self, indent: int, line_indices: set) -> None:
        for i in range(indent):
            self.context.out.write("|" if i in line_indices else " ")

    def _rule_label(self, rule) -> Optional[str]:
        eng = self.context.engine
        if rule is None:
            return None
        if isinstance(rule, eng.Stratum):
            return "Stratum"
        if isinstance(rule, (eng.IMorphologicalRule, eng.IPhonologicalRule)):
            return "Rule"
        if isinstance(rule, eng.AffixTemplate):
            return "Template"
        return None


_TRACE_TYPE_STRINGS = {
    "WordAnalysis": "Word Analysis",
    "WordSynthesis": "Word Synthesis",
    "Successful": "Successful Parse",
    "Failed": "Failed Parse",
    "Blocked": "Blocked Parse",
    "LexicalLookup": "Lexical Lookup",
    "StratumAnalysisInput": "Stratum Analysis In",
    "StratumAnalysisOutput": "Stratum Analysis Out",
    "StratumSynthesisInput": "Stratum Synthesis In",
    "StratumSynthesisOutput": "Stratum Synthesis Out",
    "TemplateAnalysisInput": "Template Analysis In",
    "TemplateAnalysisOutput": "Template Analysis Out",
    "TemplateSynthesisInput": "Template Synthesis In",
    "TemplateSynthesisOutput": "Template Synthesis Out",
    "MorphologicalRuleAnalysis": "Morphological Rule Analysis",
    "MorphologicalRuleSynthesis": "Morphological Rule Synthesis",
    "PhonologicalRuleAnalysis": "Phonological Rule Analysis",
    "PhonologicalRuleSynthesis": "Phonological Rule Synthesis",
}

_ANALYSIS_TRACE_TYPES = frozenset({
    "WordAnalysis",
    "LexicalLookup",
    "StratumAnalysisInput",
    "StratumAnalysisOutput",
    "TemplateAnalysisInput",
    "TemplateAnalysisOutput",
    "MorphologicalRuleAnalysis",
    "PhonologicalRuleAnalysis",
})


def _split_escaped(text: str, delimiter: str):
    """TestCommand.Split, verbatim -- including its infinite loop on a `\\`
    right before a delimiter (the C# `continue` re-tests `start > 0` with
    `start` unchanged)."""
    start = 0
    while True:
        end = text.find(delimiter, start)
        if end == -1:
            yield text[start:]
        elif end == 0:
            yield ""
        elif text[end - 1] != "\\":
            yield text[start:end]
        else:
            if start > 0:
                continue
            break
        start = end + 1
        if not start > 0:
            break


def _read_parse_string(parse_str: str) -> List[Tuple[str, str]]:
    """TestCommand.ReadParseString. A morph without `:` raises, as the C#
    index `parts[1]` does."""
    morphs = []
    for morph in _split_escaped(parse_str, "|"):
        parts = list(_split_escaped(morph.strip(), ":"))
        morphs.append((parts[0].strip(), parts[1].strip()))
    return morphs


class TestCommand(Command):
    name = "test"
    options = {"p": ("p", True), "parse": ("p", True)}
    arguments = 1

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        self.expected_parses: List[str] = []

    def run(self, values, remaining) -> int:
        ctx, eng, out = self.context, self.context.engine, self.context.out
        word = remaining[0]
        # Outside the try, as in the C#: a bad -p raises before the finally
        # that clears the list, so it leaks into the next test command.
        expected = [_read_parse_string(p) for p in self.expected_parses]
        try:
            ctx.test_count += 1
            out.writeline(f'Testing "{word}"')
            actual: List[List[Tuple[str, str]]] = []
            for parse in ctx.morpher.ParseWord(word):
                infos = eng.morph_infos(parse)
                found = False
                for i, exp in enumerate(expected):
                    if list(exp) == infos:
                        del expected[i]
                        found = True
                        break
                if not found:
                    actual.append(infos)

            if expected or actual:
                ctx.failed_test_count += 1
                out.writeline("Test failed.")
                out.writeline("Expected parses:")
                if not expected:
                    out.writeline("None")
                else:
                    for exp in expected:
                        write_parse(out, exp)
                out.writeline("Actual parses:")
                if not actual:
                    out.writeline("None")
                else:
                    for act in actual:
                        write_parse(out, act)
            else:
                ctx.passed_test_count += 1
                out.writeline("Test passed.")
            out.writeline()
            return 0
        except eng.InvalidShapeException as ise:
            ctx.error_test_count += 1
            out.writeline(f"The word contains an invalid segment at position {ise.Position + 1}.")
            out.writeline()
            return 1
        finally:
            self.expected_parses.clear()


class StatsCommand(Command):
    name = "stats"
    options = {
        "p": ("p", False),
        "parse": ("p", False),
        "t": ("t", False),
        "test": ("t", False),
        "r": ("r", False),
        "reset": ("r", False),
    }
    arguments = 0

    def run(self, values, remaining) -> int:
        ctx, out = self.context, self.context.out
        parse, test, reset = "p" in values, "t" in values, "r" in values
        if not parse and not test:
            parse = test = True
        if reset:
            if parse:
                ctx.reset_parse_stats()
            if test:
                ctx.reset_test_stats()
        else:
            if parse:
                out.writeline(
                    f"# of parses: {ctx.parse_count}, successful: {ctx.successful_parse_count}, "
                    f"failed: {ctx.failed_parse_count}, error: {ctx.error_parse_count}"
                )
            if test:
                out.writeline(
                    f"# of tests: {ctx.test_count}, passed: {ctx.passed_test_count}, "
                    f"failed: {ctx.failed_test_count}, error: {ctx.error_test_count}"
                )
        out.writeline()
        return 0


class TracingCommand(Command):
    name = "tracing"
    arguments = None

    def run(self, values, remaining) -> int:
        manager = self.context.morpher.TraceManager
        if remaining:
            manager.IsTracing = remaining[0] == "on"
        self.context.out.writeline(
            "Tracing is turned on." if manager.IsTracing else "Tracing is turned off."
        )
        return 0


def dispatch(commands: List[Command], args: List[str], out: _Writer) -> int:
    """ConsoleCommandDispatcher.DispatchCommand, for the shapes hc scripts use."""
    if not args:
        return -1
    name, rest = args[0], args[1:]
    command = next((c for c in commands if c.name.lower() == name.lower()), None)
    if command is None:
        out.writeline(f"Command '{name}' is not recognized.")
        return -1
    try:
        values, remaining = parse_options(rest, command.options)
    except OptionError as exc:
        out.writeline(str(exc))
        return -1
    if isinstance(command, TestCommand):
        command.expected_parses.extend(values.get("p", []))
    if command.arguments is not None and len(remaining) != command.arguments:
        if len(remaining) < command.arguments:
            out.writeline(
                f"Invalid number of arguments-- expected {command.arguments - len(remaining)} more."
            )
        else:
            out.writeline(f"Extra parameters specified: {', '.join(remaining[command.arguments:])}")
        return -1
    return command.run(values, remaining)


# ---------------------------------------------------------------------------
# Program.Main
# ---------------------------------------------------------------------------


def _is_io_error(engine: Optional[Engine], exc: BaseException) -> bool:
    if isinstance(exc, OSError):
        return True
    if engine is not None:
        try:
            return isinstance(exc, engine.System.IO.IOException)
        except Exception:  # noqa: BLE001
            return False
    return False


def _exception_message(exc: BaseException) -> str:
    message = getattr(exc, "Message", None)
    return str(message) if message is not None else str(exc)


def main(argv: Optional[Sequence[str]] = None, *, engine_factory: Optional[Callable[[], Engine]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    make_engine = engine_factory or (lambda: Engine(engine_dir()))
    try:
        values, _extra = parse_options(argv, _HC_OPTIONS)
    except OptionError:
        show_help()
        return -1

    input_file = (values.get("i") or [None])[-1]
    output_file = (values.get("o") or [None])[-1]
    script_file = (values.get("s") or [None])[-1]
    quit_on_error = "c" not in values
    show = "h" in values

    if show or not input_file:
        show_help()
        if show:
            # The one addition to hc's -h: prove the engine can start.
            try:
                make_engine()
            except EngineUnavailable as exc:
                sys.stderr.buffer.write((ENGINE_UNAVAILABLE_PREFIX + str(exc) + "\n").encode("utf-8"))
                sys.stderr.buffer.flush()
                return ENGINE_UNAVAILABLE_EXIT
        return -1

    output: Optional[_Writer] = None
    engine: Optional[Engine] = None
    try:
        if output_file:
            output = _Writer(open(output_file, "wb"), "utf-8")
        CONSOLE.write(f'Reading configuration file "{os.path.basename(input_file)}"... ')
        engine = make_engine()
        language = engine.load_language(input_file, quit_on_error)
        CONSOLE.writeline("done.")

        context = Context(engine, language, output or CONSOLE)
        CONSOLE.write("Compiling rules... ")
        context.compile()
        CONSOLE.writeline("done.")
        CONSOLE.writeline(f"{language.Name} loaded.")
        CONSOLE.writeline()
    except Exception as exc:  # noqa: BLE001 -- hc catches everything here
        CONSOLE.writeline()
        if _is_io_error(engine, exc):
            CONSOLE.writeline("IO Error: " + _exception_message(exc))
        else:
            CONSOLE.writeline("Load Error: " + _exception_message(exc))
        if output is not None:
            output.close()
        return -1

    commands: List[Command] = [
        ParseCommand(context),
        TracingCommand(context),
        TestCommand(context),
        StatsCommand(context),
    ]

    try:
        if script_file:
            for line in read_script_lines(script_file):
                if not line.strip().startswith("#") and line.strip() != "":
                    dispatch(commands, split_command_line(line), context.out)
        else:
            CONSOLE.write("> ")
            line = sys.stdin.readline()
            while line and line.rstrip("\r\n").strip() != "exit":
                text = line.rstrip("\r\n")
                if text.strip() in ("?", "help"):
                    for command in commands:
                        CONSOLE.writeline(command.name)
                else:
                    dispatch(commands, split_command_line(text), context.out)
                CONSOLE.write("> ")
                line = sys.stdin.readline()
    except Exception:  # noqa: BLE001 -- an unhandled .NET exception ends hc
        sys.stderr.buffer.write(("Unhandled exception. " + traceback.format_exc()).encode("utf-8"))
        sys.stderr.buffer.flush()
        return UNHANDLED_EXCEPTION_EXIT

    if output is not None:
        output.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
