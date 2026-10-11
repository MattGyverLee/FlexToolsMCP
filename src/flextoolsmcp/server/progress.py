"""Progress notification plumbing (issue #369, Phase 3 / ruling R3).

One seam carries MCP ``notifications/progress`` from the transport to the
long-running operations, with zero handler signature changes:

- The mcp 2.x ``on_call_tool`` adapter in ``server.py`` builds a
  :class:`ProgressReporter` from the request context (bound to
  ``ctx.session.report_progress``) when the request carried a
  ``_meta.progressToken``, and installs it in the ContextVar below for
  the duration of the call.
- Instrumented operations fetch it ambiently via
  :func:`get_progress_reporter` -- the same kernel-style accessor pattern
  as ``get_operations_logger()`` / ``get_api_index()`` -- and report
  milestones or heartbeats without knowing anything about the transport.

Invariants (cycle1-longops section 2.3):

- **No token => no-op reporter => byte-identical behavior.** Direct-call
  tests and the 31 untouched handlers see the default reporter, which
  drops every report.
- **Progress never fails a tool.** Every exception from the sink is
  swallowed inside the reporter (the filing-claim precedent: a progress
  read/emit never fails the operation it describes).
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import time
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

# A sink receives (progress, total, message) and delivers one notification.
# ``ctx.session.report_progress`` matches this shape directly.
ProgressSink = Callable[..., Awaitable[None]]

#: Default elapsed-heartbeat interval for long subprocess waits
#: (run_module, grammar-health scan). Read at call time so tests and
#: embedders can tune it without touching call sites.
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15.0


class ProgressReporter:
    """Reports progress for the in-flight tool call, or nothing at all.

    A reporter with no sink is the no-op default: ``report`` returns
    immediately and ``enabled`` is False, so instrumented code can call
    it unconditionally.
    """

    def __init__(self, sink: Optional[ProgressSink] = None) -> None:
        self._sink = sink

    @property
    def enabled(self) -> bool:
        """True when a real notification sink is attached."""
        return self._sink is not None

    async def report(
        self,
        progress: float,
        total: Optional[float] = None,
        message: Optional[str] = None,
    ) -> None:
        """Emit one progress notification; never raises."""
        if self._sink is None:
            return
        try:
            await self._sink(progress, total, message)
        except Exception:
            # Progress is advisory: a broken or vanished client channel
            # must never surface as a tool failure.
            pass

    def report_nowait(
        self,
        progress: float,
        total: Optional[float] = None,
        message: Optional[str] = None,
    ) -> None:
        """Fire-and-forget variant for synchronous call sites.

        Semantic-search milestones live in a synchronous method that
        blocks the event loop; scheduling the notification is all that is
        achievable there (the queued notifications flush when the loop
        next turns). With no running loop or no sink this drops silently.
        """
        if self._sink is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        try:
            loop.create_task(self.report(progress, total, message))
        except Exception:
            pass


#: The shared no-op reporter (also the ContextVar default).
NO_OP_REPORTER = ProgressReporter()

_CURRENT_REPORTER: contextvars.ContextVar[ProgressReporter] = contextvars.ContextVar(
    "flextoolsmcp_progress_reporter", default=NO_OP_REPORTER
)


def get_progress_reporter() -> ProgressReporter:
    """The reporter for the in-flight tool call (no-op outside one)."""
    return _CURRENT_REPORTER.get()


def set_progress_reporter(
    reporter: ProgressReporter,
) -> "contextvars.Token[ProgressReporter]":
    """Install ``reporter`` as current; returns the reset token."""
    return _CURRENT_REPORTER.set(reporter)


def reset_progress_reporter(token: "contextvars.Token[ProgressReporter]") -> None:
    """Restore the reporter that preceded the matching ``set``."""
    _CURRENT_REPORTER.reset(token)


def _extract_progress_token(params: Any, ctx: Any) -> Any:
    """The request's progressToken, or None when none was supplied.

    The token lives in the request params' meta (wire spelling
    ``_meta.progressToken``; the SDK's Python spelling is
    ``meta.progress_token``). Dict-shaped metas (raw JSON-RPC) are read
    under both spellings. Booleans are rejected, matching the SDK
    dispatcher's own rule.
    """
    for source in (params, ctx):
        meta = getattr(source, "meta", None) if source is not None else None
        if meta is None:
            continue
        token: Any = None
        if isinstance(meta, dict):
            token = meta.get("progress_token", meta.get("progressToken"))
        else:
            token = getattr(meta, "progress_token", None)
        if token is not None and not isinstance(token, bool):
            return token
    return None


def build_progress_reporter(ctx: Any, params: Any) -> ProgressReporter:
    """Build the reporter for one ``tools/call`` request.

    Bound to ``ctx.session.report_progress`` when the request carried a
    progressToken; the no-op reporter otherwise (including ``ctx=None``).
    Never raises: any surprise in the context shape degrades to no-op.
    """
    try:
        if ctx is None:
            return NO_OP_REPORTER
        if _extract_progress_token(params, ctx) is None:
            return NO_OP_REPORTER
        session = getattr(ctx, "session", None)
        sink = getattr(session, "report_progress", None)
        if not callable(sink):
            return NO_OP_REPORTER

        async def _sink(
            progress: float,
            total: Optional[float] = None,
            message: Optional[str] = None,
        ) -> None:
            await sink(progress, total, message)

        return ProgressReporter(_sink)
    except Exception:
        return NO_OP_REPORTER


@contextlib.asynccontextmanager
async def progress_heartbeat(
    label: str,
    *,
    interval: Optional[float] = None,
    reporter: Optional[ProgressReporter] = None,
) -> AsyncIterator[None]:
    """Emit elapsed-time progress around a long opaque await.

    Wraps call sites whose inner operation exposes no progress of its own
    (a subprocess awaited to completion): while the body runs, a
    background task reports ``(elapsed_seconds, total=None,
    "<label>: still running, Ns elapsed")`` every ``interval`` seconds.
    The heartbeat is cancelled in ``finally`` and can never affect the
    wrapped operation -- reporter exceptions are already swallowed, and
    the heartbeat task itself is best-effort throughout.

    With the no-op reporter (no progressToken on the request) no task is
    spawned at all and behavior is identical to the bare await.
    """
    rep = reporter if reporter is not None else get_progress_reporter()
    if interval is None:
        interval = DEFAULT_HEARTBEAT_INTERVAL_SECONDS
    if not rep.enabled or not interval or interval <= 0:
        yield
        return

    started = time.monotonic()

    async def _beat() -> None:
        try:
            while True:
                await asyncio.sleep(interval)
                elapsed = time.monotonic() - started
                await rep.report(
                    elapsed,
                    total=None,
                    message=f"{label}: still running, {elapsed:.0f}s elapsed",
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    task = asyncio.ensure_future(_beat())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
