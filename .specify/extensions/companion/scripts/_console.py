"""ASCII-safe console output for every Companion entry point.

`doctor.py` already guards its own glyphs (`_MARK` / `_MARK_ASCII`) because, in
its author's words, "a UnicodeEncodeError from `print` would escape every
per-check try/except and kill the process -- breaking the never-halts contract
on any console whose encoding is not UTF-8." That reasoning is not specific to
doctor: on a cp1252 Windows console the `->` arrow in `status-context.py`
aborted the script and swallowed its `RESOLUTION:` line entirely, which is the
one line the resume command parses.

This module generalises the same idea once, for all of them. It registers a
codec error handler that transliterates unencodable characters to ASCII instead
of raising, then attaches it to stdout/stderr. Import it and the protection is
installed:

    import _console  # noqa: F401  (installs ASCII-safe stdout/stderr)

On a UTF-8 console nothing changes -- the handler only fires for a character the
stream cannot encode. Only output is affected; strings compared or written to
files keep their original characters, so content-matching regexes (the
`U+27F6 Wait` pattern in `doctor_checks.py`, the `->`/`U+2192` alternation in
`spec_deltas.py`) are untouched.
"""

import codecs
import sys

#: Unencodable character -> ASCII stand-in. Anything absent degrades to "?".
FALLBACKS = {
    "→": "->",     # RIGHTWARDS ARROW
    "⟶": "-->",    # LONG RIGHTWARDS ARROW
    "←": "<-",     # LEFTWARDS ARROW
    "✓": "[OK]",   # CHECK MARK
    "✗": "[FAIL]", # BALLOT X
    "⚠": "[WARN]", # WARNING SIGN
    "ℹ": "[INFO]", # INFORMATION SOURCE
    "↻": "~",      # CLOCKWISE OPEN CIRCLE ARROW (renamed count)
    "−": "-",      # MINUS SIGN
    "—": "--",     # EM DASH
    "–": "-",      # EN DASH
    "…": "...",    # HORIZONTAL ELLIPSIS
    "·": "-",      # MIDDLE DOT
    "\U0001f4c1": "",   # FILE FOLDER
    "\U0001f4ca": "",   # BAR CHART
    "\U0001f50d": "",   # MAGNIFYING GLASS
    "\U0001f449": "->", # POINTING HAND
}

ERROR_NAME = "companion_ascii"


def _handler(exc):
    """Transliterate the offending run to ASCII rather than raising."""
    if not isinstance(exc, UnicodeEncodeError):
        raise exc
    bad = exc.object[exc.start:exc.end]
    return ("".join(FALLBACKS.get(ch, "?") for ch in bad), exc.end)


codecs.register_error(ERROR_NAME, _handler)


def _is_utf8(stream) -> bool:
    enc = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
    return enc in ("utf8", "utf8sig")


def install():
    """Make stdout/stderr ASCII-safe. Best-effort and never raises.

    On a UTF-8 console nothing is changed: the glyphs render correctly, so they
    are left alone. On any other console the stream is downgraded to ASCII with
    the transliterating handler attached. That second step matters beyond the
    crash: a Windows console reports cp1252 while the terminal renders UTF-8, so
    an em dash encodes to byte 0x97 without error and still arrives as a
    replacement character. Encodable is not the same as legible, and only ASCII
    is reliably both.

    JSON payloads are unaffected -- `json.dumps` defaults to `ensure_ascii=True`,
    so machine-read output is already pure ASCII before it reaches the stream.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name, None)
        if stream is None:
            continue
        try:
            if _is_utf8(stream):
                stream.reconfigure(errors=ERROR_NAME)
            else:
                stream.reconfigure(encoding="ascii", errors=ERROR_NAME)
        except Exception:
            pass  # non-reconfigurable stream (pytest capture, pipe wrapper)


install()
