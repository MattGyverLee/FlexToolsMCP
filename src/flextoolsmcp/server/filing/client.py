#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The server side of the FILING worker's channel (parser-check CP4, R-09).

The filing worker is the one process that opens a project for writing. Its
role, its child module and the one message only it understands
(`filing_setup`) are named HERE, in the filing package, and registered with
the read spine's `WorkerPool` at import -- so `server/parse/`, which a
standing test proves never writes, never names the write spine at all.

A filing run is otherwise an ordinary run: the same `ParseRunner`, the same
record, one `parse` message per word, the same word-boundary cancellation.
"""

from __future__ import annotations

from typing import Any

from ..parse.worker_client import ParseWorkerClient, register_role

__all__ = [
    "FILING_ROLE",
    "FILING_WORKER_MODULE_PATH",
    "FilingWorkerClient",
]

#: The pool key the filing worker lives under, beside SHARED_ROLE and
#: MEASUREMENT_ROLE. Spawned for one filing run and released when it ends;
#: never shared with a read-only run.
FILING_ROLE = "filing"

#: The child module: `server/filing/worker_filing.py`, the only module in the
#: source tree that opens a project with writeEnabled=True (FR-029).
FILING_WORKER_MODULE_PATH = "flextoolsmcp.server.filing.worker_filing"


class FilingWorkerClient(ParseWorkerClient):
    """A `ParseWorkerClient` that can also hand its worker a filing run."""

    def _dispatch(self, message: dict[str, Any]) -> None:
        if message.get("type") in ("filing_ready", "filing_committed"):
            future = self._pending.pop(message.get("request_id") or "", None)
            if future is not None and not future.done():
                future.set_result(message)
            return
        super()._dispatch(message)

    async def filing_setup(
        self, *, request_id: str, run_id: str, setup: dict[str, Any], timeout: float = 120.0
    ) -> dict[str, Any]:
        """Hand the worker its run: the confirmed projection, the gate
        reference it re-checks on every grammar load (R-05), and where to
        append the pre-deletion captures (FR-031). Sent once, before the
        first word; answered with `filing_ready`."""
        return await self._request(
            {"type": "filing_setup", "request_id": request_id, "run_id": run_id, "setup": setup},
            timeout,
        )

    async def filing_commit(
        self, *, request_id: str, run_id: str, timeout: float = 600.0
    ) -> dict[str, Any]:
        """Persist what was filed (FR-034). Answered with `filing_committed`
        `{ok, error}`. Generous timeout: saving a large project takes time."""
        return await self._request(
            {"type": "filing_commit", "request_id": request_id, "run_id": run_id}, timeout
        )


register_role(FILING_ROLE, FILING_WORKER_MODULE_PATH, FilingWorkerClient)
