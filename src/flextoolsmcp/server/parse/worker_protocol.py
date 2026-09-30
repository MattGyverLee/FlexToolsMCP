"""
The parse worker's wire: protocol constants, the one stdout writer, stderr
diagnostics, and the loaded-assembly probe.

Worker-process only: imported by `worker_main.py` (the parse worker) and the
filing worker, never by the MCP server process -- see `worker_main.py`'s
header for why.
"""

from __future__ import annotations

import contextlib
import json
import sys
import threading
from typing import Any




#: Bumped only on a breaking change to the message shapes above. The server
#: refuses a worker whose protocol it does not know rather than guessing.
PROTOCOL_VERSION = 1

#: How long the worker PROCESS sits idle before exiting.
#:
#: #223: this no longer bounds how long the project (and its `.fwdata`
#: lock) stays held -- that is released the moment the queue empties
#: (`ParseWorker._release_if_idle`), independent of this timeout. What
#: this still bounds is how long the warm process (and its pythonnet /
#: CLR bridge) is kept around so a later request in the same window skips
#: process-startup cost; it still pays again for `OpenProject()` and the
#: first grammar load either way (`ParseWorker._ensure_project_open`).
DEFAULT_IDLE_TIMEOUT_SECONDS = 600.0

_ENV_IDLE_TIMEOUT = "FLEXTOOLSMCP_PARSE_WORKER_IDLE_TIMEOUT"

#: How long the main loop blocks waiting for work before re-checking the
#: idle deadline and the shutdown flag. Small enough to be responsive,
#: large enough not to spin a core.
_POLL_INTERVAL_SECONDS = 0.05


# ---------------------------------------------------------------------------
# stdout is the protocol. Everything else goes to stderr.
# ---------------------------------------------------------------------------

_EMIT_LOCK = threading.Lock()


def _force_utf8_stdio() -> None:
    """Put this process's stdio on UTF-8, whatever the console says.

    THIS IS NOT COSMETIC. On Windows `sys.stdout` defaults to the console
    codepage (cp1252 here), so a wordform or a trace containing a character
    outside that codepage is **silently replaced** on its way across the
    channel -- the first live run of this worker produced a U+FFFD in an
    Indonesian trace for exactly this reason. For a tool whose entire
    subject matter is minority-language orthographies, a stdio encoding
    that quietly mangles non-Latin text is a correctness bug, not a
    configuration detail.

    Called before anything is written, and paired with `ensure_ascii=True`
    on the wire (see `_emit`): the two are deliberate belt and braces,
    because they fail in different places. `ensure_ascii` protects the
    protocol; this protects the diagnostics on stderr, which carry
    arbitrary text and are the only record of a failure between messages.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _emit(message: dict[str, Any]) -> None:
    """Write one protocol line to stdout and flush it.

    The ONLY writer to stdout in this process. The flush is not an
    optimization: the server is reading line by line and a buffered
    response is indistinguishable from a hung worker.

    `ensure_ascii=True` so the wire is pure ASCII regardless of what any
    stdio layer on either side believes the encoding to be. JSON escapes
    non-ASCII as `\\uXXXX`, which survives every codepage; the far side
    decodes it back to the original characters. It costs a few bytes on
    non-Latin text and removes a whole class of platform-dependent
    corruption.
    """
    line = json.dumps(message, ensure_ascii=True)
    with _EMIT_LOCK:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _log(message: str) -> None:
    """Diagnostics. stderr, never stdout -- see the module docstring."""
    sys.stderr.write(f"[parse-worker] {message}\n")
    sys.stderr.flush()


def loaded_assembly_names() -> list[str]:
    """Every CLR assembly loaded into THIS process, by simple name.

    Exists for one caller: `HCParser_DoesNotLoadXCore`
    (tests/test_parser_no_xcore.py), which backs the `READ_ONLY_SAFE`
    annotation on the parse tools. That test has to read the list from the
    process that actually parsed -- the server process never loads
    `ParserCore` at all, so asserting there would prove nothing.

    Returns `[]` when pythonnet is not loaded, which is the stub case. The
    test treats an empty list as "could not observe" and skips rather than
    passing: a vacuous green here would retire the one guarantee that makes
    the read-only claim checkable.
    """
    try:
        import clr  # noqa: F401  -- import side effect: starts the CLR bridge
        from System import AppDomain
    except Exception:  # noqa: BLE001 -- no CLR here; see docstring
        return []

    names = []
    for assembly in AppDomain.CurrentDomain.GetAssemblies():
        with contextlib.suppress(Exception):
            names.append(str(assembly.GetName().Name))
    return names
