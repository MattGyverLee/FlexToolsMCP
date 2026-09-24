#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #109: JSONL telemetry close helpers require an explicit log_dir_fn."""

import pytest

from flextoolsmcp.server.handlers import execution as execution_mod


@pytest.mark.parametrize(
    "helper_name, kwargs",
    [
        (
            "_log_preflight_reject",
            {
                "op_id": "op-test",
                "seq": 1,
                "duration_s": 0.0,
                "reason_code": "syntax_error",
                "detail": "test",
            },
        ),
        (
            "_log_operation_end_success",
            {
                "op_id": "op-test",
                "seq": 1,
                "duration_s": 0.0,
                "info_count": 0,
                "warning_count": 0,
                "error_count": 0,
            },
        ),
        (
            "_log_operation_failure",
            {
                "op_id": "op-test",
                "seq": 1,
                "duration_s": 0.0,
                "error": "boom",
            },
        ),
        (
            "_log_discovery_redirect",
            {
                "op_id": "op-test",
                "seq": 1,
                "duration_s": 0.0,
                "reason": "api_discovery_required",
                "detail": "test",
            },
        ),
    ],
)
def test_jsonl_close_helpers_require_log_dir_fn(helper_name, kwargs, tmp_path):
    helper = getattr(execution_mod, helper_name)
    with pytest.raises(TypeError):
        helper(**kwargs)


def test_jsonl_close_helper_accepts_explicit_log_dir_fn(tmp_path):
    from flextoolsmcp.server import kernel

    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    execution_mod._log_preflight_reject(
        op_id="op-test",
        seq=1,
        duration_s=0.0,
        reason_code="syntax_error",
        detail="test",
        log_dir_fn=lambda: tmp_path,
    )
    assert (tmp_path / "operations.jsonl").exists()
