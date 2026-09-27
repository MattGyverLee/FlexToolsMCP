"""Issue #286: server.py's warnings.showwarning hook must not recurse.

The hook replaced ``warnings.showwarning`` and then called
``warnings.showwarning`` for every non-HF warning -- i.e. itself -- so any
displayed warning raised RecursionError once server.py had loaded.
"""

import io
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture(scope="module")
def server_module():
    """The executed server.py module (loaded lazily by the package)."""
    import flextoolsmcp.server as pkg

    _ = pkg.APIIndex  # triggers the lazy load of server.py
    return pkg._server_module_cache


def test_hook_is_installed(server_module):
    assert server_module._warning_handler._flextools_original is (
        server_module._original_showwarning
    )


# pytest records warnings around every test (catch_warnings(record=True)), so
# warnings.warn() inside a test never reaches the hook the way it does in the
# running server. Call the handler directly instead: that is exactly the frame
# that used to recurse.

def test_ordinary_warning_forwards_to_original_hook(server_module):
    with patch.object(server_module, "_original_showwarning") as original:
        server_module._warning_handler("ordinary warning", UserWarning, "x.py", 7)
    original.assert_called_once_with(
        "ordinary warning", UserWarning, "x.py", 7, None, None
    )


def test_ordinary_warning_does_not_recurse(server_module, monkeypatch):
    # Recreate the running server's state -- our handler IS
    # warnings.showwarning -- which pytest's recording otherwise undoes.
    # Before the fix the handler called warnings.showwarning (itself) here
    # and raised RecursionError.
    monkeypatch.setattr(warnings, "showwarning", server_module._warning_handler)
    server_module._warning_handler(
        "ordinary warning", UserWarning, "x.py", 7, file=io.StringIO()
    )


def test_hf_unauthenticated_warning_is_logged_once(server_module):
    msg = "You are sending unauthenticated requests to the HF Hub"
    with patch.object(server_module, "_hf_warned", False), patch.object(
        server_module, "_log_warning"
    ) as log, patch.object(server_module, "_original_showwarning") as original:
        server_module._warning_handler(msg, UserWarning, "hf.py", 1)
        server_module._warning_handler(msg, UserWarning, "hf.py", 1)
    log.assert_called_once_with(f"HuggingFace Hub: {msg}")
    original.assert_not_called()


def test_reexecuting_server_py_does_not_stack_hooks(server_module):
    """A second exec of server.py must forward to the ORIGINAL hook, not to
    the first copy of _warning_handler."""
    original = server_module._original_showwarning
    assert not hasattr(original, "_flextools_original")

    saved = warnings.showwarning
    try:
        # Only run the hook-install lines, not the whole server module:
        # re-executing server.py wholesale would build a second MCP server.
        src = Path(server_module.__file__).read_text(encoding="utf-8")
        start = src.index("import warnings as _warnings_module")
        end = src.index("_warnings_module.showwarning = _warning_handler")
        snippet = src[start:end] + "_warnings_module.showwarning = _warning_handler\n"
        ns = {"_log_warning": lambda msg: None}
        exec(compile(snippet, server_module.__file__, "exec"), ns)
        assert ns["_original_showwarning"] is original
        assert warnings.showwarning is ns["_warning_handler"]
    finally:
        warnings.showwarning = saved
