#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #320 -- run_module child env lacked PYTHONUTF8/PYTHONIOENCODING.

On Windows the child inherited the cp1252 console locale, so a plain
``open(path, "w")`` of non-ASCII text (e.g. U+02BC MODIFIER LETTER
APOSTROPHE, common in minority-language orthographies) died with
``UnicodeEncodeError: 'charmap' codec can't encode character``.

The fix: ``run_script_async`` now launches with ``utf8_child_env()`` when
the caller passes no explicit env, so the child runs in UTF-8 mode.

Covers:
- the helper builds os.environ + the two overrides and nothing is dropped;
- the helper overrides a pre-existing hostile PYTHONUTF8 value;
- end-to-end: a real child launched through ``run_script_async`` sees the
  vars, runs with ``sys.flags.utf8_mode == 1``, reports UTF-8 as the
  preferred encoding for ``open()``, and round-trips U+02BC through a
  plain ``open(path, "w")`` without UnicodeEncodeError;
- an explicitly passed env is used verbatim (no silent mutation).
"""

import asyncio
import json
import os
import textwrap

from server.subprocess_helpers import run_script_async, utf8_child_env


def test_utf8_child_env_sets_both_vars():
    env = utf8_child_env()
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_utf8_child_env_preserves_parent_env():
    sentinel_key, sentinel_value = "FLEXTOOLSMCP_320_SENTINEL", "kept-value"
    os.environ[sentinel_key] = sentinel_value
    try:
        env = utf8_child_env()
    finally:
        del os.environ[sentinel_key]
    assert env[sentinel_key] == sentinel_value
    # PATH etc. survive the copy.
    assert env.get("PATH") == os.environ.get("PATH")


def test_utf8_child_env_overrides_hostile_values():
    base = dict(os.environ)
    base["PYTHONUTF8"] = "0"
    base["PYTHONIOENCODING"] = "cp1252"
    env = utf8_child_env(base)
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


_CHILD_BODY = textwrap.dedent(
    """\
    import json, locale, os, sys

    probe = {
        "pythonutf8": os.environ.get("PYTHONUTF8"),
        "pythonioencoding": os.environ.get("PYTHONIOENCODING"),
        "utf8_mode": sys.flags.utf8_mode,
        "preferred_encoding": locale.getpreferredencoding(False),
        "stdout_encoding": sys.stdout.encoding,
    }
    # The exact failing call from the issue: plain open() for writing,
    # no encoding= argument, so the platform default applies.
    target = __TARGET__
    with open(target, "w") as f:
        f.write("abc\\u02bcdef\\n")
    with open(target, encoding="utf-8") as f:
        probe["roundtrip"] = f.read()
    print("PROBE:" + json.dumps(probe))
    """
)


def test_run_script_async_child_env_is_utf8(tmp_path):
    """Real child through run_script_async sees the UTF-8 env (issue #320)."""
    target = tmp_path / "extracted_streams.txt"
    script = tmp_path / "child_probe.py"
    script.write_text(
        _CHILD_BODY.replace("__TARGET__", repr(str(target))), encoding="utf-8"
    )

    result = asyncio.run(run_script_async(str(script), timeout_seconds=30))

    assert result["timeout"] is False, result["stderr"]
    assert result["returncode"] == 0, "stderr: {}".format(result["stderr"])
    probe = json.loads(
        next(
            line[len("PROBE:"):]
            for line in result["stdout"].splitlines()
            if line.startswith("PROBE:")
        )
    )
    assert probe["pythonutf8"] == "1"
    assert probe["pythonioencoding"] == "utf-8"
    # The mechanism the fix relies on: UTF-8 mode is really on in the child,
    # so open() defaults to UTF-8 regardless of the host locale.
    assert probe["utf8_mode"] == 1
    assert probe["preferred_encoding"].replace("-", "").lower() == "utf8"
    # And the issue's failing call now round-trips U+02BC without error.
    assert probe["roundtrip"] == "abc\u02bcdef\n"


def test_run_script_async_explicit_env_used_verbatim(tmp_path):
    """An explicit env is not mutated -- callers opting out keep control."""
    script = tmp_path / "echo_env.py"
    script.write_text(
        textwrap.dedent(
            """\
            import json, os
            print("PROBE:" + json.dumps({
                "pythonutf8": os.environ.get("PYTHONUTF8"),
            }))
            """
        ),
        encoding="utf-8",
    )
    explicit = dict(os.environ)
    explicit.pop("PYTHONUTF8", None)

    result = asyncio.run(
        run_script_async(str(script), timeout_seconds=30, env=explicit)
    )

    assert result["returncode"] == 0, result["stderr"]
    probe = json.loads(
        next(
            line[len("PROBE:"):]
            for line in result["stdout"].splitlines()
            if line.startswith("PROBE:")
        )
    )
    assert probe["pythonutf8"] is None
