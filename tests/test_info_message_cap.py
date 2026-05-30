"""Tests for issue #25 -- cap report.Info messages on run_module responses.

Background: a single run_module invocation can emit 785 info messages,
flooding the LLM's context with no semantic gain. We cap info messages
at a configurable limit (default 100) using a "keep first cap//2 + last
cap//2 + truncation marker" slice. Warnings and errors are NEVER capped.
"""
import pytest


def _make_info(i):
    return {"type": "INFO", "message": f"info-{i}", "ref": None}


def _make_warning(i):
    return {"type": "WARNING", "message": f"warning-{i}", "ref": None}


def _make_error(i):
    return {"type": "ERROR", "message": f"error-{i}", "ref": None}


def _count(messages, level):
    from server.handlers.execution import _classify_message_level
    return sum(1 for m in messages if _classify_message_level(m) == level)


def test_synthetic_500_infos_capped_to_101():
    """The task spec: 500 info messages + cap=100 => exactly 101 entries
    (50 head + 50 tail + 1 truncation marker)."""
    from server.handlers.execution import _cap_info_messages

    messages = [_make_info(i) for i in range(500)]
    capped, stats = _cap_info_messages(messages, cap=100)

    assert len(capped) == 101, (
        f"Expected exactly 101 items (50 + marker + 50); got {len(capped)}"
    )
    assert stats == {
        "original_info_count": 500,
        "kept_info_count": 100,
        "truncated": True,
        "cap": 100,
    }
    # First 50 are the head
    for i in range(50):
        assert capped[i]["message"] == f"info-{i}"
    # Position 50 is the marker
    assert "truncated" in capped[50]["message"]
    assert "additional info messages" in capped[50]["message"]
    # Last 50 are the tail
    for i, m in enumerate(capped[51:], start=450):
        assert m["message"] == f"info-{i}"


def test_cap_disabled_with_zero():
    """cap=0 means no cap -- return everything as-is."""
    from server.handlers.execution import _cap_info_messages

    messages = [_make_info(i) for i in range(300)]
    capped, stats = _cap_info_messages(messages, cap=0)

    assert capped is messages or len(capped) == 300
    assert stats["truncated"] is False
    assert stats["original_info_count"] == 300
    assert stats["kept_info_count"] == 300


def test_under_cap_passes_through():
    """fewer infos than cap => unchanged."""
    from server.handlers.execution import _cap_info_messages

    messages = [_make_info(i) for i in range(50)]
    capped, stats = _cap_info_messages(messages, cap=100)

    assert len(capped) == 50
    assert stats["truncated"] is False


def test_warnings_and_errors_never_capped():
    """Warnings and errors must survive intact regardless of cap."""
    from server.handlers.execution import _cap_info_messages

    # 200 infos interleaved with 10 warnings and 5 errors
    messages = []
    for i in range(200):
        messages.append(_make_info(i))
        if i % 20 == 0:
            messages.append(_make_warning(i))
        if i % 40 == 0:
            messages.append(_make_error(i))

    original_warnings = _count(messages, "WARNING")
    original_errors = _count(messages, "ERROR")

    capped, stats = _cap_info_messages(messages, cap=50)

    # Every warning and every error survives
    assert _count(capped, "WARNING") == original_warnings
    assert _count(capped, "ERROR") == original_errors
    # Info count is capped (50 kept + 1 marker)
    info_after = sum(
        1 for m in capped
        if m.get("type") == "INFO" and "truncated" not in (m.get("message") or "")
    )
    assert info_after == 50
    assert stats["original_info_count"] == 200
    assert stats["kept_info_count"] == 50
    assert stats["truncated"] is True


def test_odd_cap_split():
    """Odd cap value: head = cap//2, tail = cap - cap//2 (so tail >= head by 1)."""
    from server.handlers.execution import _cap_info_messages

    messages = [_make_info(i) for i in range(100)]
    capped, stats = _cap_info_messages(messages, cap=7)

    # 3 head + marker + 4 tail = 8 entries
    assert len(capped) == 8
    assert capped[0]["message"] == "info-0"
    assert capped[1]["message"] == "info-1"
    assert capped[2]["message"] == "info-2"
    assert "truncated" in capped[3]["message"]
    assert capped[4]["message"] == "info-96"
    assert capped[5]["message"] == "info-97"
    assert capped[6]["message"] == "info-98"
    assert capped[7]["message"] == "info-99"
    assert stats["kept_info_count"] == 7
    assert stats["truncated"] is True


def test_empty_messages():
    """Empty input -> empty output, no truncation."""
    from server.handlers.execution import _cap_info_messages

    capped, stats = _cap_info_messages([], cap=100)
    assert capped == []
    assert stats["truncated"] is False
    assert stats["original_info_count"] == 0


def test_msgtype_int_form_still_classified():
    """Legacy payloads with integer msgType (0=INFO, 1=WARNING, 2=ERROR)
    must still be classified correctly."""
    from server.handlers.execution import _cap_info_messages, _classify_message_level

    legacy = [
        {"msgType": 0, "message": "old-info"},
        {"msgType": 1, "message": "old-warn"},
        {"msgType": 2, "message": "old-err"},
    ]
    assert _classify_message_level(legacy[0]) == "INFO"
    assert _classify_message_level(legacy[1]) == "WARNING"
    assert _classify_message_level(legacy[2]) == "ERROR"

    # Pad with INFO entries to trigger the cap and confirm legacy infos count
    legacy.extend(_make_info(i) for i in range(200))
    capped, stats = _cap_info_messages(legacy, cap=10)
    assert stats["original_info_count"] == 201  # 1 legacy + 200 new
    assert stats["truncated"] is True
