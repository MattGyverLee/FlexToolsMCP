#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Code-independent inconsistency signature (spec section 6.3).

Never keys on `code_sha256`. Users iterate code across a turn, so a
signature keyed on the code hash would re-offer the same underlying bug on
every edit. Instead the signature captures the underlying inconsistency:

  - runtime-fail             -> hash of (exception-class, normalized
                                 failing API symbol / top traceback frame)
  - invalid_api_chain        -> hash of the normalized offending chain string
  - casting recurrence       -> hash of the recurring casting signature

Pure functions only -- no I/O, no network. See the package docstring in
`flextoolsmcp.server.diagnostic.__init__` for the no-transmission guard this
module lives under.
"""

import hashlib
import re
from typing import Any, Dict, Optional

# Truncated hex digest length -- long enough to avoid collisions in a single
# maintainer's offered.json (hundreds of entries), short enough to eyeball.
_DIGEST_LEN = 16

_WHITESPACE_RE = re.compile(r"\s+")
# Collapse numeric list/index literals so "list[0].Foo" and "list[7].Foo"
# dedupe to the same normalized chain.
_INDEX_RE = re.compile(r"\[\d+\]")


def _normalize_symbol(symbol: str) -> str:
    """Normalize a failing API symbol / top traceback frame for hashing.

    Strips surrounding whitespace, collapses internal whitespace runs, and
    normalizes numeric subscripts (`foo[3]` -> `foo[N]`) so that repeated
    attempts against different list indices still dedupe to one signature.
    """
    s = (symbol or "").strip()
    s = _WHITESPACE_RE.sub(" ", s)
    s = _INDEX_RE.sub("[N]", s)
    return s


def _normalize_chain(chain: str) -> str:
    """Normalize an offending API-chain string the same way as a symbol."""
    return _normalize_symbol(chain)


def _hash(*parts: str) -> str:
    raw = "\x1f".join(parts).encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()[:_DIGEST_LEN]


def signature_for_runtime_fail(exception_class: str, failing_symbol: str) -> str:
    """Section 6.3: signature for a runtime_fail close.

    `exception_class` is the concrete exception class name (this is what
    JSONL's `error_code` already carries for runtime_fail closes, e.g.
    "PolymorphicAttributeError"). `failing_symbol` is the normalized failing
    API symbol / top traceback frame -- NOT available in the JSONL record
    alone; callers source it from the session-log traceback (reconstruction,
    a later checkpoint) or supply it directly.
    """
    return _hash("runtime_fail", exception_class or "", _normalize_symbol(failing_symbol))


def signature_for_invalid_api_chain(chain: str) -> str:
    """Section 6.3: signature for an invalid_api_chain close."""
    return _hash("invalid_api_chain", _normalize_chain(chain))


def signature_for_casting_recurrence(casting_signature: str) -> str:
    """Section 6.3: signature for a casting_issues_detected recurrence.

    `casting_signature` is the recurring casting signature identified by
    `diagnostic.triggers.casting_recurrence_signature()`.
    """
    return _hash("casting_recurrence", casting_signature or "")


def compute_signature(
    record: Dict[str, Any],
    *,
    failing_symbol: Optional[str] = None,
    chain: Optional[str] = None,
    casting_signature: Optional[str] = None,
) -> Optional[str]:
    """Dispatch to the right signature function based on a closed-op record.

    Extra context not present on the bare JSONL record (`failing_symbol`,
    `chain`, `casting_signature`) may be passed explicitly, or the record
    itself may already carry them under the same keys (a future telemetry
    enhancement). Returns None if the record doesn't correspond to any of
    the three signature-bearing cases -- callers should have already
    filtered with `diagnostic.triggers.is_reportable_close()`.
    """
    outcome = record.get("outcome")
    error_code = (record.get("error_code") or "").strip()

    if outcome == "runtime_fail":
        symbol = failing_symbol if failing_symbol is not None else record.get("failing_symbol", "")
        return signature_for_runtime_fail(error_code, symbol)

    if error_code == "invalid_api_chain":
        offending_chain = chain if chain is not None else record.get("offending_chain", "")
        return signature_for_invalid_api_chain(offending_chain)

    if error_code == "casting_issues_detected":
        sig = (
            casting_signature
            if casting_signature is not None
            else record.get("casting_signature", "")
        )
        return signature_for_casting_recurrence(sig)

    return None
