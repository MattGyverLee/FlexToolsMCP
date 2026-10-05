# Cycle 1 — QC: `__getattr__` error laundering in the lazy server loader

> Authored by the lex-qc agent (read-only role, no Write tool); transcribed to
> this path verbatim by the main session.

## P0 — AttributeError laundered into misleading ImportError

**File:** `src/flextoolsmcp/server/__init__.py:152-166`

Root cause: `spec.loader.exec_module(_server_module)` (line 160) has no
try/except. Python's `from X import Y` machinery treats *only* `AttributeError`
raised out of a module's `__getattr__` specially — it reinterprets it as
"attribute absent" and re-raises `ImportError: cannot import name`. Any
`AttributeError` raised while *executing* server.py's top-level code (e.g. a
decorator failure at server.py:808) gets this treatment and the real
traceback/message is destroyed.

**Fix (structural hardening, matching #82's house style):** wrap only the
`exec_module` call:

```python
try:
    spec.loader.exec_module(_server_module)
except Exception as exc:
    raise ImportError(
        f"flextoolsmcp.server lazy-load of '{name}' failed: server.py raised "
        f"{type(exc).__name__} while executing (NOT a missing-attribute error). "
        f"See chained cause below."
    ) from exc
_server_module_cache = _server_module
```

Catch `Exception`, not just `AttributeError` — any exception type crossing this
boundary deserves an unambiguous, chained re-raise rather than depending on the
accident of which exception classes CPython's import machinery happens to
special-case. `raise ... from exc` satisfies B904 and preserves the original
traceback via `__cause__`. Add a regression test analogous to
`tests/test_issue82_writeability_reject_logging.py`: monkeypatch `exec_module`
to raise `AttributeError`, assert the resulting `ImportError` message contains
"NOT a missing-attribute error" and `exc.__cause__` is the original
`AttributeError`.

## P1 — Failed load retries the whole exec on every access

`_server_module_cache` (line 75) is set only on success (line 161), so a broken
server.py re-executes in full on *every* subsequent lazy attribute touch
(`run`, `main`, `APIIndex`, `Server`, ...) until fixed. Beyond wasted work,
server.py's top-level code has side effects (logging setup, decorator
registration on the `server` object) — repeated re-exec risks compounding
secondary errors that further obscure the original one.

Fix: cache the failure too. Add `_server_load_error: Optional[BaseException] = None`;
on exec failure, set it before raising; on entry, if `_server_load_error is not
None`, immediately `raise ImportError(...) from _server_load_error` without
re-executing.

## P2 — Missing-vs-broken ambiguity at lines 164-166

Once the P0 fix lands, this becomes moot: reaching
`hasattr(_server_module_cache, name)` at line 164 now only happens after a
*verified successful* exec, so a `False` here unambiguously means "genuinely not
defined in server.py" — Python's resulting `ImportError: cannot import name` is
then accurate, not laundered. No fix strictly required beyond P0; optionally
enrich the fallthrough message at line 167 to say "listed in LAZY_IMPORTS but
not found in server.py after successful load" for future maintainers.

## P2 — Sibling sweep

- `src/flextoolsmcp/server/kernel.py:38-48` — catches only `ImportError`, not
  `Exception`/`AttributeError`. This does **not** match the defect class; a
  genuine `AttributeError` inside the `mcp.*` import chain propagates untouched
  with full traceback. No fix needed.
- `src/flextoolsmcp/server/handlers/_import_helper.py:29-104` and the ~15
  duplicated inline `try: from ..X import Y / except ImportError: from X import Y`
  dual-mode blocks across `execution.py`, `admin.py`, `catalog.py`,
  `dispatch.py`, etc. — narrower risk variant: if the relative-import branch
  fails for a reason *other* than mode mismatch, the original `ImportError`'s
  message/traceback is discarded (no `from exc` chaining) when the fallback is
  attempted. Lower severity — dual-mode import is the accepted architecture and
  only one branch is ever live per deployment — but worth chaining
  (`raise ... from exc`) if the fallback also fails, for the same
  diagnostic-preservation reason as the P0 fix.
- Confirmed via grep: no other `except AttributeError` blocks and no other
  `spec_from_file_location`/`exec_module` sites exist in `src/flextoolsmcp/` —
  the `__init__.py` lazy loader is the sole true instance of this exact bug class.

**File reviewed:** `src/flextoolsmcp/server/__init__.py` (lines 77-167)
**Related:** `src/flextoolsmcp/server/kernel.py:38-48`,
`src/flextoolsmcp/server/handlers/_import_helper.py`, `CHANGELOG.md` (#82 entry)
