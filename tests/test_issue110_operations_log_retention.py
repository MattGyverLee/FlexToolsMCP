"""Issue #110: operations.log must retain enough rotated backups.

A low backupCount on the cross-session RotatingFileHandler dropped multi-day
log spans while operations.jsonl and per-session logs kept the same activity.
"""

import logging
from pathlib import Path

import pytest

from server import kernel as kernel_mod


def test_cross_session_handler_uses_extended_backup_count(tmp_path, monkeypatch):
    """The durable operations.log handler keeps more backups than session logs."""
    monkeypatch.setattr(kernel_mod, "get_log_dir", lambda: tmp_path)
    target_logger = logging.getLogger("flextoolsmcp.operations")
    for h in target_logger.handlers[:]:
        target_logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    monkeypatch.setattr(kernel_mod, "operations_logger", None, raising=False)
    logger = kernel_mod.setup_logging()
    monkeypatch.setattr(kernel_mod, "operations_logger", logger, raising=False)
    flagged = [
        h
        for h in logger.handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
        and getattr(h, kernel_mod._CROSS_SESSION_HANDLER_FLAG, False)
    ]
    assert len(flagged) == 1
    assert flagged[0].backupCount == kernel_mod._OPERATIONS_LOG_BACKUP_COUNT
    assert flagged[0].backupCount > kernel_mod._SESSION_LOG_BACKUP_COUNT


def test_operations_log_rotation_preserves_older_backups(tmp_path):
    """Simulate several size rotations; oldest retained backup still has early data."""
    from server.kernel import _make_file_handler

    log_file = tmp_path / "operations.log"
    # Tiny threshold so we can rotate quickly in a unit test.
    handler = _make_file_handler(
        log_file,
        max_bytes=256,
        backup_count=kernel_mod._OPERATIONS_LOG_BACKUP_COUNT,
    )
    handler.setFormatter(
        logging.Formatter("%(message)s")
    )
    logger = logging.getLogger("flextoolsmcp.operations.issue110")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    marker_first = "MARKER_FIRST_ROTATION_EPOCH"
    marker_last = "MARKER_LAST_ROTATION_EPOCH"
    for i in range(40):
        msg = marker_first if i == 0 else (marker_last if i == 39 else f"line-{i:03d}")
        logger.info(msg)
    handler.flush()
    handler.close()

    backup_paths = [log_file] + [
        Path(f"{log_file}.{n}") for n in range(1, kernel_mod._OPERATIONS_LOG_BACKUP_COUNT + 1)
    ]
    combined = "\n".join(
        p.read_text(encoding="utf-8") for p in backup_paths if p.exists()
    )
    assert marker_first in combined, (
        "Earliest marker was lost across rotations -- backupCount too low "
        f"for the cross-session log. Files present: {[p.name for p in backup_paths if p.exists()]}"
    )
    assert marker_last in combined
