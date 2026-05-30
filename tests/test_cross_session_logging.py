"""Tests for issue #19 -- [TOOL CALL] / [TOOL ARGS] reaching the durable
cross-session operations.log even after rotate_logging_to_session() fires.

Background: rotate_logging_to_session() previously stripped ALL
RotatingFileHandler instances off the operations logger, including the
one writing to operations.log. Result: 74+ tool invocations across 13
shipped sessions logged ZERO [TOOL CALL] lines into operations.log.

These tests pin the new behavior:
  - operations.log handler is marked with _CROSS_SESSION_HANDLER_FLAG
  - rotate_logging_to_session() keeps it attached
  - INFO-level [TOOL CALL] / [TOOL ARGS] survive a rotate cycle
"""
import logging
import logging.handlers
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def isolated_logger(tmp_path, monkeypatch):
    """Isolate the operations logger to a per-test tmpdir so we don't
    touch the real ~/.flextoolsmcp/logs/ tree. Yields the (logger, log_dir)."""
    # Patch get_log_dir() BEFORE importing kernel so the first setup_logging
    # call writes into tmp_path.
    from server import kernel as kernel_mod

    monkeypatch.setattr(kernel_mod, "get_log_dir", lambda: tmp_path)

    # Detach any pre-existing handlers (the real server may have set them up)
    target_logger = logging.getLogger("flextoolsmcp.operations")
    saved_handlers = target_logger.handlers[:]
    for h in saved_handlers:
        target_logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    # Reset the module-level global so setup_logging behaves as on first run
    monkeypatch.setattr(kernel_mod, "operations_logger", None, raising=False)

    logger = kernel_mod.setup_logging()
    # Stamp the module-level for rotate_logging_to_session() to see it
    monkeypatch.setattr(kernel_mod, "operations_logger", logger, raising=False)

    yield logger, tmp_path

    # Teardown: close + remove all handlers we created so the next test
    # gets a clean slate even though pytest isolates fixtures.
    for h in logger.handlers[:]:
        logger.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_cross_session_handler_flag_is_set(isolated_logger):
    """The operations.log handler must be flagged as cross-session."""
    from server.kernel import _CROSS_SESSION_HANDLER_FLAG

    logger, log_dir = isolated_logger

    flagged = [h for h in logger.handlers
               if isinstance(h, logging.handlers.RotatingFileHandler)
               and getattr(h, _CROSS_SESSION_HANDLER_FLAG, False)]

    assert len(flagged) == 1, (
        "Expected exactly one cross-session handler after setup_logging(); "
        f"got {len(flagged)} (handlers: {logger.handlers!r})"
    )
    # Sanity: it targets operations.log
    assert Path(flagged[0].baseFilename).name == "operations.log"


def test_tool_call_lines_survive_rotation(isolated_logger):
    """[TOOL CALL] records logged AFTER rotate_logging_to_session() must
    still land in operations.log."""
    from server.kernel import rotate_logging_to_session

    logger, log_dir = isolated_logger
    ops_log = log_dir / "operations.log"

    # Pre-rotation call
    logger.info("[TOOL CALL] flextools_start")

    # Rotate to a fake session
    rotate_logging_to_session("20260529-120000")

    # Three post-rotation tool calls
    logger.info("[TOOL CALL] flextools_run_module")
    logger.info('[TOOL ARGS] flextools_run_module: {"code": "..."}')
    logger.info("[TOOL CALL] flextools_get_operation_logs")

    # Flush all handlers
    for h in logger.handlers:
        h.flush()

    contents = _read(ops_log)
    tool_call_count = contents.count("[TOOL CALL]")
    tool_args_count = contents.count("[TOOL ARGS]")

    assert tool_call_count == 3, (
        f"Expected 3 [TOOL CALL] lines in operations.log after rotation, "
        f"got {tool_call_count}. Contents:\n{contents}"
    )
    assert tool_args_count == 1, (
        f"Expected 1 [TOOL ARGS] line (INFO-level) in operations.log, "
        f"got {tool_args_count}. Contents:\n{contents}"
    )


def test_per_session_log_also_receives_records(isolated_logger):
    """Sanity: the per-session log file gets the post-rotation records too,
    i.e. the cross-session log is ADDITIVE not REPLACEMENT."""
    from server.kernel import rotate_logging_to_session

    logger, log_dir = isolated_logger
    session_id = "20260529-130000"

    rotate_logging_to_session(session_id)
    logger.info("[TOOL CALL] flextools_search_by_capability")

    for h in logger.handlers:
        h.flush()

    # Per-session log lives under logs/YYYY-MM-DD/session_<id>.log
    date_dir = log_dir / "2026-05-29"
    session_log = date_dir / f"session_{session_id}.log"
    assert session_log.exists(), f"Per-session log {session_log} not created"

    contents = _read(session_log)
    assert contents.count("[TOOL CALL]") == 1, (
        f"Per-session log should still receive [TOOL CALL] records.\n"
        f"Contents:\n{contents}"
    )


def test_rotation_does_not_stack_per_session_handlers(isolated_logger):
    """Two consecutive rotate_logging_to_session() calls should leave us
    with exactly 2 handlers: the cross-session one + the latest per-session
    one. We don't want N+1 file handles open after N starts."""
    from server.kernel import (
        rotate_logging_to_session,
        _CROSS_SESSION_HANDLER_FLAG,
    )

    logger, _ = isolated_logger

    rotate_logging_to_session("20260529-140000")
    rotate_logging_to_session("20260529-150000")

    file_handlers = [h for h in logger.handlers
                     if isinstance(h, logging.handlers.RotatingFileHandler)]
    cross_handlers = [h for h in file_handlers
                      if getattr(h, _CROSS_SESSION_HANDLER_FLAG, False)]
    session_handlers = [h for h in file_handlers
                        if not getattr(h, _CROSS_SESSION_HANDLER_FLAG, False)]

    assert len(cross_handlers) == 1, "cross-session handler should be unique"
    assert len(session_handlers) == 1, (
        f"Expected 1 per-session handler after two rotates, got "
        f"{len(session_handlers)}; stale handles would leak file descriptors."
    )
