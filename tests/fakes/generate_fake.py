#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A scriptable fake of FieldWorks' `GenerateHCConfig.exe` (parser-check CP5).

Faithful to `Src/GenerateHCConfig/Program.cs` and `ConsoleLogger.cs`:

  * fewer than two arguments -> the help text, exit 0 (R-05: a 0 with no
    `Writing completed.` is still a failure);
  * `<fwdata>` missing -> `The FieldWorks project file could not be found.`,
    exit 1;
  * success -> the four progress lines (F-9), with any load-error lines
    between `Loading FieldWorks project...` and `Loading completed.`, then
    the config is written, exit 0;
  * locked / older-version -> `Loading failed.` plus the two verbatim lines,
    exit 1;
  * crash (F-10) -> a .NET `Unhandled exception.` on stderr after
    `Loading FieldWorks project...`, no config, exit 0xE0434352 (signed).

The config it writes carries the grammar as a `FakeGrammar` payload:

    <?xml version="1.0" encoding="utf-8"?>
    <HermitCrabInput>
      <Language name="<fwdata stem>" />
      <FakeGrammar><![CDATA[<JSON grammar>]]></FakeGrammar>
    </HermitCrabInput>

The JSON grammar comes from FAKE_GEN_GRAMMAR (see below), else a small
built-in one (`DEFAULT_GRAMMAR`). Its `language` defaults to the fwdata stem.

Stdout is UTF-8 by default, `\\r\\n` line ends, flushed per line.

Environment knobs (all optional; every name starts `FAKE_GEN_`)
---------------------------------------------------------------
  FAKE_GEN_MODE          `normal` (default) | `help` | `locked` |
                         `migration` | `crash` | `empty_config`
      help          -- print the help text and exit 0 whatever the args.
      locked        -- "currently open in another application", exit 1.
      migration     -- "created with an older version of FLEx", exit 1.
      crash         -- NotImplementedException on stderr, no config,
                       exit FAKE_GEN_CRASH_EXIT (default -532462766).
      empty_config  -- all four progress lines, exit 0, a 0-byte config.
  FAKE_GEN_LOAD_ERRORS   N -- emit N load-error lines, cycling through F-9's
                         seven templates (`LOAD_ERROR_TEMPLATES`, in order).
  FAKE_GEN_LOAD_ERROR_LINES  a JSON list of exact lines to emit instead.
  FAKE_GEN_SLEEP_SECONDS a slow start: sleep before the first line (the
                         unverified SLDR start-up). For generate timeouts.
  FAKE_GEN_LISTING_FILE  write a JSON listing of the working folder here:
                         {"root": "<abs>", "fwdata": "<abs>",
                          "dirs": ["rel/posix", ...], "files": [...]}
                         The working folder is the fwdata's grandparent,
                         i.e. `work/<run_id>/` for `work/<run_id>/<name>/<name>.fwdata`
                         (data-model section 2). Listed before anything is written.
  FAKE_GEN_GRAMMAR       the JSON grammar as text, or `@<path>` to a JSON file.
  FAKE_GEN_ARGV_FILE     append {"argv": [...], "cwd": "..."} per invocation.
  FAKE_GEN_ENCODING      stdout encoding (default `utf-8`).
  FAKE_GEN_HONOR_LOCK    `1` -> behave as `locked` when `<fwdata>.lock`
                         exists beside the fwdata (a copied lock tripwire).
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import List

UNHANDLED_EXCEPTION_EXIT = 0xE0434352 - (1 << 32)

PROGRESS_LINES = (
    "Loading FieldWorks project...",
    "Loading completed.",
    "Writing HC configuration file...",
    "Writing completed.",
)

HELP_LINES = (
    "Generates a HermitCrab configuration file from a FieldWorks project.",
    "",
    "generatehcconfig <input-project> <output-config>",
    "",
    "  <input-project>  Specifies the FieldWorks project path.",
    "  <output-config>  Specifies the HC configuration path.",
)

# ConsoleLogger.cs, in order: InvalidShape, InvalidAffixProcess, InvalidPhoneme,
# DuplicateGrapheme, InvalidEnvironment, InvalidReduplicationForm,
# InvalidRewriteRule. `{n}` is the 1-based line number.
LOAD_ERROR_TEMPLATES = (
    'The form "fake{n}" contains an undefined phoneme at {n}.',
    'The affix process "proc{n}" is invalid.',
    'The phoneme "ph{n}" does not contain any valid graphemes.',
    'The phoneme "dup{n}" has the same grapheme as another phoneme.',
    'The environment "/ _ #{n}" is invalid. Reason: fake reason {n}',
    'The reduplication form "[C{n}]" is invalid. Reason: fake reason {n}',
    'The rewrite rule "rule{n}" is invalid. Reason: fake reason {n}',
)

DEFAULT_GRAMMAR = {
    "words": {
        "membaca": [[["mem", "ACT"], ["baca", "read"]]],
        "baca": [[["baca", "read"]], [["baca", "book"]]],
        "xyz": [],
    },
    "default": [],
}

_ENCODING = os.environ.get("FAKE_GEN_ENCODING", "utf-8")


def say(text: str = "") -> None:
    sys.stdout.buffer.write((text + "\r\n").encode(_ENCODING, errors="replace"))
    sys.stdout.buffer.flush()


def say_err(text: str) -> None:
    sys.stderr.buffer.write((text + "\r\n").encode("utf-8"))
    sys.stderr.buffer.flush()


def list_working_folder(fwdata: str) -> None:
    target = os.environ.get("FAKE_GEN_LISTING_FILE")
    if not target:
        return
    fwdata_abs = os.path.abspath(fwdata)
    root = os.path.dirname(os.path.dirname(fwdata_abs))
    dirs: List[str] = []
    files: List[str] = []
    for current, subdirs, names in os.walk(root):
        rel = os.path.relpath(current, root)
        for sub in subdirs:
            dirs.append(os.path.normpath(os.path.join(rel, sub)).replace(os.sep, "/"))
        for name in names:
            files.append(os.path.normpath(os.path.join(rel, name)).replace(os.sep, "/"))
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "root": root,
                "fwdata": fwdata_abs,
                "dirs": sorted(dirs),
                "files": sorted(files),
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )


def load_error_lines() -> List[str]:
    explicit = os.environ.get("FAKE_GEN_LOAD_ERROR_LINES")
    if explicit:
        return [str(line) for line in json.loads(explicit)]
    count = int(os.environ.get("FAKE_GEN_LOAD_ERRORS", "0") or 0)
    return [
        LOAD_ERROR_TEMPLATES[i % len(LOAD_ERROR_TEMPLATES)].format(n=i + 1)
        for i in range(count)
    ]


def grammar_for(fwdata: str) -> dict:
    raw = os.environ.get("FAKE_GEN_GRAMMAR")
    if raw:
        if raw.startswith("@"):
            with open(raw[1:], "r", encoding="utf-8") as handle:
                grammar = json.load(handle)
        else:
            grammar = json.loads(raw)
    else:
        grammar = json.loads(json.dumps(DEFAULT_GRAMMAR))
    grammar.setdefault("language", os.path.splitext(os.path.basename(fwdata))[0])
    return grammar


def write_config(path: str, fwdata: str) -> None:
    grammar = grammar_for(fwdata)
    body = json.dumps(grammar, ensure_ascii=False, indent=2).replace(
        "]]>", "]]]]><![CDATA[>"
    )
    name = (
        grammar["language"]
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
    )
    text = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<HermitCrabInput>\n"
        '  <Language name="%s" />\n'
        "  <FakeGrammar><![CDATA[%s]]></FakeGrammar>\n"
        "</HermitCrabInput>\n" % (name, body)
    )
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def main(argv: List[str]) -> int:
    path = os.environ.get("FAKE_GEN_ARGV_FILE")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"argv": argv, "cwd": os.getcwd()}) + "\n")

    mode = os.environ.get("FAKE_GEN_MODE", "normal")
    if mode == "help" or len(argv) < 2:
        for line in HELP_LINES:
            say(line)
        return 0

    fwdata, config_out = argv[0], argv[1]
    if not os.path.isfile(fwdata):
        say("The FieldWorks project file could not be found.")
        return 1

    sleep = float(os.environ.get("FAKE_GEN_SLEEP_SECONDS", "0") or 0)
    if sleep > 0:
        time.sleep(sleep)

    list_working_folder(fwdata)

    if os.environ.get("FAKE_GEN_HONOR_LOCK") == "1" and os.path.exists(
        fwdata + ".lock"
    ):
        mode = "locked"

    say(PROGRESS_LINES[0])
    if mode == "locked":
        say("Loading failed.")
        say("The FieldWorks project is currently open in another application.")
        say("Close the application and try to run this command again.")
        return 1
    if mode == "migration":
        say("Loading failed.")
        say("The FieldWorks project was created with an older version of FLEx.")
        say("Migrate the project to the latest version by opening it in FLEx.")
        return 1

    for line in load_error_lines():
        say(line)

    if mode == "crash":
        say_err("")
        say_err(
            "Unhandled Exception: System.NotImplementedException: "
            "The method or operation is not implemented."
        )
        say_err(
            "   at GenerateHCConfig.ConsoleLogger.SIL.FieldWorks.WordWorks.Parser."
            "IHCLoadErrorLogger.UnmatchedReduplicationIndexedClass(IMoForm form, "
            "String reason, String environment)"
        )
        return int(
            os.environ.get("FAKE_GEN_CRASH_EXIT", str(UNHANDLED_EXCEPTION_EXIT)), 0
        )

    say(PROGRESS_LINES[1])
    say(PROGRESS_LINES[2])
    if mode == "empty_config":
        open(config_out, "wb").close()
    else:
        write_config(config_out, fwdata)
    say(PROGRESS_LINES[3])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
