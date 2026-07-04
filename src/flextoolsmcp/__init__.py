# FlexTools MCP Server
try:
    from importlib.metadata import version as _version

    __version__ = _version("flextools-mcp")
except Exception:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
