#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A scriptable fake of the stand-alone HermitCrab `hc` tool (parser-check CP5).

Faithful to `SIL.Machine.Morphology.HermitCrab.Tool` (Program.cs,
ParseCommand.cs, TestCommand.cs, StatsCommand.cs, Extensions.cs WriteParse,
MorphInfo.cs) in everything the sandbox spine reads:

  * stdout is **UTF-16LE**, no BOM by default (research F-1), `\\r\\n` line
    ends, flushed on every write;
  * `-h`, no args, or no `-i` prints the usage text (F-3) and exits -1;
  * `-i <config> -s <script>` prints the load banner, then runs every
    non-blank, non-`#` script line through hc's own `SplitCommandLine`;
  * `parse <w>` prints `Parsing "<w>"`, then `Parse <n>` + `Morphs:`/`Gloss:`
    lines, or `No valid parses.`, or the invalid-segment line, then
    `Parse time: <n>ms` and a blank line (invalid segment: no time line);
  * `test -p f:g|f:g [-p ...] <w>` prints `Testing "<w>"`, then
    `Test passed.` or `Test failed.` + the unmatched `Expected parses:` /
    `Actual parses:` sections (`None` when empty, F-8), then a blank line;
  * `stats -p` / `stats -t` print hc's counter lines, then a blank line;
  * WriteParse pads each column to max(len(form), len(gloss)) counted in
    UTF-16 code units (F-6), skips zero-width morphs, joins with one space;
    an empty gloss in an ACTUAL parse is printed as `?` (F-7).

A missing config is `IO Error: Could not find file '<path>'.` and exit -1; an
unloadable one is `Load Error: <msg>` and exit -1 (both after the partial
`Reading configuration file "<name>"... ` line, as real hc does).

The fake grammar (the "config")
-------------------------------
The `-i` file is looked up in this order:

  1. a `<FakeGrammar>` element anywhere in the file, whose text (optionally
     wrapped in `<![CDATA[ ... ]]>`) is a JSON grammar. This is what
     `generate_fake.py` writes, inside a `<HermitCrabInput>` root;
  2. otherwise, if the file's stripped text starts with `{`, the whole file
     is the JSON grammar;
  3. otherwise, an XML file with a `<HermitCrabInput` root is an empty
     grammar (every word: no valid parses);
  4. otherwise (empty or not XML) it is a load error, with the .NET
     XmlException wording (`Root element is missing.` /
     `Data at the root level is invalid. Line 1, position 1.`).

The JSON grammar:

    {
      "language": "Sena Fake",          # printed as "<language> loaded."
      "load_error": null,               # a string makes loading fail with it
      "words": {
        "membaca": [                    # a list of parses; each parse is a
          [["mem", "ACT"], ["baca", "read"]]   # list of [form, gloss] morphs
        ],
        "xyz": [],                      # [] -> "No valid parses."
        "q#": {"invalid_segment": 2}    # the PRINTED (1-based) position
      },
      "default": []                     # value for any word not in "words"
    }

Word lookup is an exact string match (no normalisation). `default` takes any
value a word can take; absent, it is `[]`.

Environment knobs (all optional; every name starts `FAKE_HC_`)
---------------------------------------------------------------
  FAKE_HC_MODE            `normal` (default) | `runtime_missing` |
                          `not_hermitcrab` | `load_error` | `echo`
      runtime_missing -- writes the .NET host "framework missing" text to
                          stderr (UTF-8) and exits 0x80008096 (as the
                          signed int -2147450730, i.e. unsigned 0x80008096
                          when read back as a DWORD). Nothing on stdout.
      not_hermitcrab  -- prints some OTHER tool's usage text and exits 1.
      load_error      -- banner fragment, then `Load Error: <msg>`, exit -1.
      echo            -- writes every line of the `-s` script back to stdout
                          verbatim (UTF-16LE), no banner, exit 0.
  FAKE_HC_RUNTIME_VERSION `10.0.0` -- the version in the runtime_missing text.
  FAKE_HC_LOAD_ERROR      message for load_error mode.
  FAKE_HC_SLEEP_ON_WORD   N -- after printing the header of the N-th (0-based)
                          parse/test command, sleep FAKE_HC_SLEEP_SECONDS
                          (default 3600) before finishing it. For timeouts.
  FAKE_HC_CRASH_ON_WORD   N -- after printing the header of the N-th (0-based)
                          parse/test command, exit at once, with no terminator,
                          with FAKE_HC_CRASH_EXIT (default -532462766, the
                          .NET unhandled-exception code 0xE0434352).
  FAKE_HC_CRASH_STDERR    text written to stderr on that crash (default: a
                          .NET-style `Unhandled exception.` line).
  FAKE_HC_WORD_DELAY_MS   sleep this long inside every parse/test (streaming).
  FAKE_HC_BOM             `1` -> emit a UTF-16LE BOM before the first output.
  FAKE_HC_PARSE_STATS     `N,S,F,E` -- override the `stats -p` numbers printed.
  FAKE_HC_TEST_STATS      `N,P,F,E` -- override the `stats -t` numbers printed.
  FAKE_HC_ARGV_FILE       append one JSON line per invocation:
                          {"argv": [...], "cwd": "...", "script": "<text>"|null}
  FAKE_HC_EXIT            force this exit code on an otherwise normal run.

"Word N" counts the parse/test commands the fake actually executes, in
script order, starting at 0 -- the same order as the sent items of
`dispatch.json`.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any, List, Optional, Tuple

# .NET host FrameworkMissingFailure (0x80008096) as a signed 32-bit int.
RUNTIME_MISSING_EXIT = 0x80008096 - (1 << 32)
# CLR unhandled-exception code (0xE0434352) as a signed 32-bit int.
UNHANDLED_EXCEPTION_EXIT = 0xE0434352 - (1 << 32)

_NL = "\r\n"
_OUT = sys.stdout.buffer
_bom_pending = os.environ.get("FAKE_HC_BOM") == "1"


# ---------------------------------------------------------------------------
# Output (UTF-16LE, flushed per write, like Console.Out with Encoding.Unicode)
# ---------------------------------------------------------------------------


def write(text: str) -> None:
    global _bom_pending
    data = text.encode("utf-16-le", errors="surrogatepass")
    if _bom_pending:
        data = b"\xff\xfe" + data
        _bom_pending = False
    _OUT.write(data)
    _OUT.flush()


def writeline(text: str = "") -> None:
    write(text + _NL)


def write_stderr(text: str) -> None:
    sys.stderr.buffer.write(text.encode("utf-8"))
    sys.stderr.buffer.flush()


def u16len(text: str) -> int:
    return len(text.encode("utf-16-le", errors="surrogatepass")) // 2


def pad_right(text: str, width: int) -> str:
    return text + " " * max(0, width - u16len(text))


def write_parse(parse: List[Tuple[str, str]]) -> None:
    """Extensions.WriteParse, verbatim in behaviour."""
    for prefix, pick in (("Morphs: ", 0), ("Gloss:  ", 1)):
        write(prefix)
        first = True
        for morph in parse:
            width = max(u16len(morph[0]), u16len(morph[1]))
            if width > 0:
                if not first:
                    write(" ")
                write(pad_right(morph[pick], width))
                first = False
        writeline()


# ---------------------------------------------------------------------------
# Usage and host failures
# ---------------------------------------------------------------------------

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

OTHER_USAGE_LINES = [
    "Usage: hc [options] <file>",
    "hc - HydroCarbon molecular weight calculator, version 2.3",
    "",
    "  -h    show this help",
]


def runtime_missing_text(version: str) -> str:
    lines = [
        "You must install or update .NET to run this application.",
        "",
        "App: " + os.path.abspath(sys.argv[0]),
        "Architecture: x64",
        "Framework: 'Microsoft.NETCore.App', version '%s' (x64)" % version,
        ".NET location: C:\\Program Files\\dotnet\\",
        "",
        "The following frameworks were found:",
        "  8.0.11 at [C:\\Program Files\\dotnet\\shared\\Microsoft.NETCore.App]",
        "",
        "Learn more:",
        "https://aka.ms/dotnet/app-launch-failed",
        "",
        "To install missing framework, download:",
        "https://aka.ms/dotnet-core-applaunch?framework=Microsoft.NETCore.App"
        "&framework_version=%s&arch=x64&rid=win-x64&os=win10" % version,
    ]
    return _NL.join(lines) + _NL


# ---------------------------------------------------------------------------
# Command-line and script parsing
# ---------------------------------------------------------------------------


def parse_options(argv: List[str]) -> Optional[dict]:
    """Mono.Options for hc's option set. None means an OptionException."""
    opts: dict = {"i": None, "o": None, "s": None, "c": False, "h": False}
    names = {
        "i": "i",
        "input-file": "i",
        "o": "o",
        "output-file": "o",
        "s": "s",
        "script-file": "s",
        "c": "c",
        "continue": "c",
        "h": "h",
        "help": "h",
        "?": "h",
    }
    k = 0
    while k < len(argv):
        arg = argv[k]
        k += 1
        m = re.match(r"^(--|-|/)([^=:]+)(?:[=:](.*))?$", arg)
        if not m or m.group(2) not in names:
            continue  # Mono.Options leaves unknown arguments unparsed
        key = names[m.group(2)]
        if key in ("i", "o", "s"):
            value = m.group(3)
            if value is None:
                if k >= len(argv):
                    return None  # "Missing required value for option"
                value = argv[k]
                k += 1
            opts[key] = value
        else:
            opts[key] = True
    return opts


def split_command_line(line: str) -> List[str]:
    """Program.SplitCommandLine, verbatim in behaviour."""
    chars = list(line)
    in_single = in_double = False
    for idx, ch in enumerate(chars):
        if ch == '"' and not in_single:
            in_double = not in_double
            chars[idx] = "\n"
        if chars[idx] == "'" and not in_double:
            in_single = not in_single
            chars[idx] = "\n"
        if not in_single and not in_double and chars[idx] == " ":
            chars[idx] = "\n"
    return [part for part in "".join(chars).split("\n") if part]


def read_lines(path: str) -> List[str]:
    """StreamReader.ReadLine over a UTF-8 file (BOM detected and dropped)."""
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8-sig", errors="replace")
    lines = re.split(r"\r\n|\r|\n", text)
    if lines and lines[-1] == "":
        lines.pop()
    return lines


# ---------------------------------------------------------------------------
# The fake grammar
# ---------------------------------------------------------------------------


class LoadError(Exception):
    pass


def load_grammar(path: str) -> dict:
    with open(path, "rb") as handle:
        text = handle.read().decode("utf-8-sig", errors="replace")
    m = re.search(r"<FakeGrammar>(.*?)</FakeGrammar>", text, re.S)
    if m:
        body = m.group(1).strip()
        cdata = re.match(r"^<!\[CDATA\[(.*)\]\]>$", body, re.S)
        if cdata:
            body = cdata.group(1)
        grammar = json.loads(body)
    elif text.strip().startswith("{"):
        grammar = json.loads(text)
    elif "<HermitCrabInput" in text:
        name = re.search(r'<Language[^>]*\bname="([^"]*)"', text)
        grammar = {"language": name.group(1) if name else "Language"}
    elif not text.strip():
        raise LoadError("Root element is missing.")
    else:
        raise LoadError("Data at the root level is invalid. Line 1, position 1.")
    if grammar.get("load_error"):
        raise LoadError(str(grammar["load_error"]))
    return grammar


def lookup(grammar: dict, word: str) -> Any:
    words = grammar.get("words") or {}
    if word in words:
        return words[word]
    return grammar.get("default", [])


def actual_parses(value: Any) -> List[List[Tuple[str, str]]]:
    """MorphInfo(parse, morph): an empty gloss becomes `?`."""
    parses = []
    for parse in value:
        parses.append([(str(f), str(g) if g else "?") for f, g in parse])
    return parses


# ---------------------------------------------------------------------------
# The commands
# ---------------------------------------------------------------------------


class Session:
    def __init__(self, grammar: dict) -> None:
        self.grammar = grammar
        self.word_index = 0
        self.parse_count = self.parse_ok = self.parse_failed = self.parse_error = 0
        self.test_count = self.test_passed = self.test_failed = self.test_error = 0
        self.leaked_expected: List[str] = []  # F-5: a bad -p leaks forward
        self.sleep_on = _int_env("FAKE_HC_SLEEP_ON_WORD")
        self.crash_on = _int_env("FAKE_HC_CRASH_ON_WORD")
        self.delay_ms = _int_env("FAKE_HC_WORD_DELAY_MS") or 0

    # -- the per-word knobs, applied right after the header -------------------
    def after_header(self) -> float:
        index = self.word_index
        self.word_index += 1
        if self.crash_on is not None and index == self.crash_on:
            write_stderr(
                os.environ.get(
                    "FAKE_HC_CRASH_STDERR",
                    "Unhandled exception. System.InvalidOperationException: "
                    "fake hc crashed on purpose." + _NL,
                )
            )
            os._exit(_int_env("FAKE_HC_CRASH_EXIT", UNHANDLED_EXCEPTION_EXIT))
        started = time.monotonic()
        if self.sleep_on is not None and index == self.sleep_on:
            time.sleep(float(os.environ.get("FAKE_HC_SLEEP_SECONDS", "3600")))
        if self.delay_ms:
            time.sleep(self.delay_ms / 1000.0)
        return started

    def dispatch(self, args: List[str]) -> None:
        name, rest = args[0], args[1:]
        if name == "parse":
            self.parse(rest)
        elif name == "test":
            self.test(rest)
        elif name == "stats":
            self.stats(rest)
        else:
            writeline("Command '%s' is not recognized." % name)

    def parse(self, rest: List[str]) -> None:
        if rest and rest[0] == "--":
            rest = rest[1:]
        if len(rest) != 1:
            writeline("Invalid number of arguments-- expected 1 more.")
            return
        word = rest[0]
        self.parse_count += 1
        writeline('Parsing "%s"' % word)
        started = self.after_header()
        value = lookup(self.grammar, word)
        if isinstance(value, dict) and "invalid_segment" in value:
            self.parse_error += 1
            writeline(
                "The word contains an invalid segment at position %d."
                % int(value["invalid_segment"])
            )
            writeline()
            return
        parses = actual_parses(value)
        if not parses:
            self.parse_failed += 1
            writeline("No valid parses.")
        else:
            self.parse_ok += 1
            for n, parse in enumerate(parses, 1):
                writeline("Parse %d" % n)
                write_parse(parse)
        elapsed = int((time.monotonic() - started) * 1000)
        writeline("Parse time: %dms" % elapsed)
        writeline()

    def test(self, rest: List[str]) -> None:
        expected_raw = list(self.leaked_expected)
        remaining: List[str] = []
        k = 0
        while k < len(rest):
            arg = rest[k]
            k += 1
            if arg == "--":
                remaining.extend(rest[k:])
                break
            m = re.match(r"^(?:--parse|-p)(?:[=:](.*))?$", arg)
            if m:
                value = m.group(1)
                if value is None:
                    if k >= len(rest):
                        writeline("Missing required value for option '-p'.")
                        return
                    value = rest[k]
                    k += 1
                expected_raw.append(value)
            else:
                remaining.append(arg)
        if len(remaining) != 1:
            writeline("Invalid number of arguments-- expected 1 more.")
            return
        word = remaining[0]
        expected: List[List[Tuple[str, str]]] = []
        for raw in expected_raw:
            morphs = []
            for morph in raw.split("|"):
                parts = morph.strip().split(":")
                if len(parts) < 2:
                    # F-5: the throw is outside the try, so the finally that
                    # clears the -p list never runs and it leaks forward.
                    self.leaked_expected = expected_raw
                    return
                morphs.append((parts[0].strip(), parts[1].strip()))
            expected.append(morphs)
        self.leaked_expected = []
        self.test_count += 1
        writeline('Testing "%s"' % word)
        self.after_header()
        value = lookup(self.grammar, word)
        if isinstance(value, dict) and "invalid_segment" in value:
            self.test_error += 1
            writeline(
                "The word contains an invalid segment at position %d."
                % int(value["invalid_segment"])
            )
            writeline()
            return
        unmatched_actual = []
        for parse in actual_parses(value):
            if parse in expected:
                expected.remove(parse)
            else:
                unmatched_actual.append(parse)
        if expected or unmatched_actual:
            self.test_failed += 1
            writeline("Test failed.")
            writeline("Expected parses:")
            if not expected:
                writeline("None")
            for parse in expected:
                write_parse(parse)
            writeline("Actual parses:")
            if not unmatched_actual:
                writeline("None")
            for parse in unmatched_actual:
                write_parse(parse)
        else:
            self.test_passed += 1
            writeline("Test passed.")
        writeline()

    def stats(self, rest: List[str]) -> None:
        flags = set()
        for arg in rest:
            m = re.match(r"^(?:--|-)(p|parse|t|test|r|reset)$", arg)
            if m:
                flags.add(m.group(1)[0])
        want_p = "p" in flags or not ({"p", "t"} & flags)
        want_t = "t" in flags or not ({"p", "t"} & flags)
        if "r" in flags:
            if want_p:
                self.parse_count = self.parse_ok = self.parse_failed = (
                    self.parse_error
                ) = 0
            if want_t:
                self.test_count = self.test_passed = self.test_failed = (
                    self.test_error
                ) = 0
        else:
            if want_p:
                nums = _override("FAKE_HC_PARSE_STATS") or (
                    self.parse_count,
                    self.parse_ok,
                    self.parse_failed,
                    self.parse_error,
                )
                writeline(
                    "# of parses: %d, successful: %d, failed: %d, error: %d" % nums
                )
            if want_t:
                nums = _override("FAKE_HC_TEST_STATS") or (
                    self.test_count,
                    self.test_passed,
                    self.test_failed,
                    self.test_error,
                )
                writeline("# of tests: %d, passed: %d, failed: %d, error: %d" % nums)
        writeline()


def _int_env(name: str, default: Optional[int] = None) -> Optional[int]:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw, 0)


def _override(name: str) -> Optional[tuple]:
    raw = os.environ.get(name)
    if not raw:
        return None
    return tuple(int(x) for x in raw.split(","))


def _record_argv(argv: List[str], script: Optional[str]) -> None:
    path = os.environ.get("FAKE_HC_ARGV_FILE")
    if not path:
        return
    text = None
    if script and os.path.isfile(script):
        with open(script, "rb") as handle:
            text = handle.read().decode("utf-8", errors="replace")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({"argv": argv, "cwd": os.getcwd(), "script": text}) + "\n"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: List[str]) -> int:
    mode = os.environ.get("FAKE_HC_MODE", "normal")
    opts = parse_options(argv)
    _record_argv(argv, opts.get("s") if opts else None)

    if mode == "runtime_missing":
        write_stderr(
            runtime_missing_text(os.environ.get("FAKE_HC_RUNTIME_VERSION", "10.0.0"))
        )
        return RUNTIME_MISSING_EXIT
    if mode == "not_hermitcrab":
        for line in OTHER_USAGE_LINES:
            writeline(line)
        return 1

    if opts is None or opts["h"] or not opts["i"]:
        for line in USAGE_LINES:
            writeline(line)
        return -1

    if mode == "echo":
        if opts["s"]:
            for line in read_lines(opts["s"]):
                writeline(line)
        return 0

    write('Reading configuration file "%s"... ' % os.path.basename(opts["i"]))
    try:
        if mode == "load_error":
            raise LoadError(
                os.environ.get(
                    "FAKE_HC_LOAD_ERROR", "The feature 'bogus' is not defined."
                )
            )
        if not os.path.isfile(opts["i"]):
            writeline()
            writeline(
                "IO Error: Could not find file '%s'." % os.path.abspath(opts["i"])
            )
            return -1
        grammar = load_grammar(opts["i"])
    except (LoadError, ValueError) as exc:
        writeline()
        writeline("Load Error: " + str(exc))
        return -1
    writeline("done.")
    write("Compiling rules... ")
    writeline("done.")
    writeline("%s loaded." % grammar.get("language", "Language"))
    writeline()

    session = Session(grammar)
    if opts["s"]:
        for line in read_lines(opts["s"]):
            if line.strip().startswith("#") or line.strip() == "":
                continue
            args = split_command_line(line)
            if args:
                session.dispatch(args)
    else:
        # Interactive mode: a prompt, then read stdin until EOF or `exit`.
        write("> ")
        for raw in sys.stdin:
            line = raw.rstrip("\r\n")
            if line.strip() == "exit":
                break
            args = split_command_line(line)
            if args:
                session.dispatch(args)
            write("> ")

    forced = _int_env("FAKE_HC_EXIT")
    return 0 if forced is None else forced


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
