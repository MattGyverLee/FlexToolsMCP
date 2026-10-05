# Baseline (T001)

Date: 2026-09-30. Branch `feat/exclusive-access-gate` at `e092fe3`.

Command (run from the worktree, with the main checkout's `.venv` interpreter;
`tests/conftest.py` puts the worktree's `src/` first on `sys.path`):

```
C:\Github\FlexToolsMCP\.venv\Scripts\python.exe -m pytest -q -m "not requires_flex" tests/test_response_contract.py tests/test_parser_error_models.py tests/test_shared_mode_write_gate.py tests/test_shared_mode_lock_diagnosis.py tests/test_script_certification.py
```

Result: **332 passed, 27 deselected, 2 subtests passed** in 4.87s.
