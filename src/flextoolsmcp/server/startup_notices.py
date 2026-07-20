"""Process-lifetime registry for notices raised during index load.

Index loading happens once at server startup, before any tool call, so a
version-mismatch / failed-refresh condition detected there has nowhere to
surface immediately. This registry stashes such notices so the first
``flextools_start`` call can relay them to the assistant (and thus the user).

Kept deliberately dependency-free: both the top-level ``server`` module and
the ``server.handlers`` package import it, so any heavier dependency here
would risk an import cycle.
"""

from typing import Any, Dict, List

# Populated by the index loader; read by handle_start.
_INDEX_REFRESH_FAILURES: List[Dict[str, Any]] = []


def record_index_refresh_failure(
    library_name: str,
    library_key: str,
    installed_version: str,
    served_version: "str | None",
) -> None:
    """Record that an installed library has no matching index and auto-refresh
    did not produce one, so a (mismatched) shipped index is being served.

    Args:
        library_name: Display name, e.g. "Flexicon".
        library_key: Refresh key, e.g. "flexicon" (used in the CLI hint).
        installed_version: The detected installed library version.
        served_version: The version of the shipped index actually loaded
            (None if unknown).

    Deduped by library_key. The loader runs once per library per process, but
    guarding keeps a re-load (or a test re-entry) from doubling the notice.
    """
    if any(n["library_key"] == library_key for n in _INDEX_REFRESH_FAILURES):
        return
    _INDEX_REFRESH_FAILURES.append(
        {
            "library_name": library_name,
            "library_key": library_key,
            "installed_version": installed_version,
            "served_version": served_version,
        }
    )


def get_index_refresh_failures() -> List[Dict[str, Any]]:
    """Return a copy of the recorded index-refresh-failure notices."""
    return list(_INDEX_REFRESH_FAILURES)


def clear_index_health_notices() -> None:
    """Reset the registry (test isolation)."""
    _INDEX_REFRESH_FAILURES.clear()
