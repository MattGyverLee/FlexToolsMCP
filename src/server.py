#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FLExTools MCP Server

An MCP server that provides AI assistants with searchable documentation
of the LibLCM and FlexLibs APIs for generating FLExTools scripts.
"""

import time as _time_module
_startup_begin = _time_module.time()

import json
import asyncio
import sys
import subprocess
import tempfile
import os
import logging
import re
import warnings
from pathlib import Path
from datetime import datetime
from typing import Any, Optional, List, Dict, TYPE_CHECKING
from dataclasses import dataclass, field
import io
from contextlib import redirect_stdout, redirect_stderr

_imports_std_done = _time_module.time()

# Suppress noisy third-party warnings and output
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
# Cache HuggingFace models to home directory (persistent across runs)
os.environ['HF_HOME'] = str(Path.home() / '.cache' / 'flextoolsmcp' / 'hf')
warnings.filterwarnings('ignore', message='.*position_ids.*')

# Capture HF Hub unauthenticated warning to log it properly
import warnings as _warnings_module
_hf_warned = False

def _warning_handler(message, category, filename, lineno, file=None, line=None):
    """Custom warning handler to capture and log HF Hub warnings."""
    global _hf_warned
    msg_str = str(message)
    if 'unauthenticated' in msg_str.lower() and not _hf_warned:
        _hf_warned = True
        _log_warning(f"HuggingFace Hub: {msg_str}")
    elif 'unauthenticated' not in msg_str.lower():
        # Show other warnings normally
        _warnings_module.showwarning(message, category, filename, lineno, file, line)

_warnings_module.showwarning = _warning_handler

# Ensure src is in sys.path when running as a script
if __package__ is None:
    _src_path = str(Path(__file__).parent)
    if _src_path not in sys.path:
        sys.path.insert(0, _src_path)

_mcp_import_begin = _time_module.time()
from mcp.server import Server
_mcp_import_done = _time_module.time()

_local_imports_begin = _time_module.time()
if __package__:
    from .json_utils import sort_json_arrays
    from .server.kernel import (
        get_log_dir,
        setup_logging,
        operations_logger,
        session_state,
        pattern_tracker,
    )
    from .server.utils import model_to_tool_schema
    from .server.tool_definitions import TOOLS as TOOL_DEFINITIONS
    from .server.dispatch import get_tool_handler
    from .server.constants import KNOWN_OPERATIONS, OPERATIONS_CLASSES
    from .server.versioning import (
        detect_installed_library_version,
        find_versioned_api_file,
        find_latest_versioned_api_file,
    )
else:
    from json_utils import sort_json_arrays
    from server.kernel import (
        get_log_dir,
        setup_logging,
        operations_logger,
        session_state,
        pattern_tracker,
    )
    from server.utils import model_to_tool_schema
    from server.tool_definitions import TOOLS as TOOL_DEFINITIONS
    from server.dispatch import get_tool_handler
    from server.constants import KNOWN_OPERATIONS, OPERATIONS_CLASSES
    from server.versioning import (
        detect_installed_library_version,
        find_versioned_api_file,
        find_latest_versioned_api_file,
    )
_local_imports_done = _time_module.time()

# Safe logging helper that works even before initialization
def _log_info(msg: str) -> None:
    """Log info message, safely handling None logger during early init."""
    if operations_logger:
        operations_logger.info(msg)

def _log_error(msg: str) -> None:
    """Log error message, safely handling None logger during early init."""
    if operations_logger:
        operations_logger.error(msg)

def _log_warning(msg: str) -> None:
    """Log warning message, safely handling None logger during early init."""
    if operations_logger:
        operations_logger.warning(msg)

# ============================================================
# FlexLibs2 Operations Contract
# ============================================================
# These constants are imported from server.constants
# and are required by pre-commit hooks to verify runtime consistency

# Exception classes used in flexlibs2 namespace
KNOWN_EXCEPTIONS = {
    # Standard exceptions
    "FP_AccessViolationException",
    "FP_ArgumentException",
    "FP_IndexOutOfRangeException",
    "FP_InvalidOperationException",
    "FP_InvalidCastException",
    "FP_KeyNotFoundException",
    "FP_NullReferenceException",
    "FP_OperationCanceledException",
    "FP_TimeoutException",
    # FlexLibs-specific exceptions
    "FP_FileLockedError",
    "FP_FileNotFoundError",
    "FP_MigrationRequired",
    "FP_NullParameterError",
    "FP_ParameterError",
    "FP_ProjectError",
    "FP_ReadOnlyError",
    "FP_RuntimeError",
    "FP_WritingSystemError",
}

# Logging and kernel state are now imported from server.kernel
# See imports at top (from .server.kernel import ...)

# Session state is now imported from server.kernel (initialized there)
# See imports at top (from .server.kernel import session_state)

# Helper validation functions were extracted to validators module
# Import them at the top if needed for use in server.py
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
    ToolAnnotations,
)

# Optional imports for semantic search - DEFERRED to on-demand loading
# These imports are intentionally NOT done at module level to avoid 14+ second
# startup penalty. They are imported lazily when semantic search is actually used.
if TYPE_CHECKING:
    import numpy as np
    import faiss
    from sentence_transformers import SentenceTransformer

SEMANTIC_SEARCH_AVAILABLE = False  # Will be determined at runtime

@dataclass
class SemanticSearch:
    """Handles semantic search using sentence-transformers and FAISS."""
    model: Any = None
    index: Any = None
    items: List[Dict] = field(default_factory=list)
    enabled: bool = False
    model_name: str = "all-MiniLM-L6-v2"  # Lazy-loaded on first search

    @classmethod
    def load(cls, index_dir: Path) -> "SemanticSearch":
        """Load semantic search index from disk."""
        search = cls()

        embeddings_dir = index_dir / "embeddings"
        embeddings_path = embeddings_dir / "embeddings.npy"
        metadata_path = embeddings_dir / "metadata.json"
        faiss_path = embeddings_dir / "faiss.index"

        if not all(p.exists() for p in [embeddings_path, metadata_path, faiss_path]):
            return search

        try:
            # Lazy-import faiss only if embeddings exist (avoids 14+ second startup cost)
            import faiss

            # Load metadata
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            search.items = metadata.get("items", [])

            # Load FAISS index
            _log_info("Loading semantic search index...")
            search.index = faiss.read_index(str(faiss_path))

            # Store model name for lazy loading (model loads on first search, not at startup)
            search.model_name = metadata.get("_model", "all-MiniLM-L6-v2")
            search.enabled = True
            _log_info("Semantic search ready (model loads on first search)")
        except ImportError:
            _log_warning("faiss not installed, semantic search disabled")
        except Exception as e:
            _log_warning(f"Failed to load semantic search: {e}")

        return search

    def search(self, query: str, max_results: int = 10, source_filter: str = "all") -> List[Dict]:
        """Perform semantic search on the query."""
        if not self.enabled or not self.index:
            return []

        # Lazy-load model on first search
        if not self.model:
            try:
                # Import SentenceTransformer only on first search (not at startup)
                from sentence_transformers import SentenceTransformer

                cache_dir = Path.home() / '.cache' / 'flextoolsmcp' / 'hf'
                cache_dir.mkdir(parents=True, exist_ok=True)
                model_cache = cache_dir / 'hub' / f'models--sentence-transformers--{self.model_name.replace("/", "--")}'

                if model_cache.exists():
                    _log_info(f"Loading embedding model '{self.model_name}' from cache...")
                else:
                    _log_info(f"Downloading embedding model '{self.model_name}' (~50MB, cached for future runs)...")

                with warnings.catch_warnings(), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    warnings.filterwarnings('ignore')
                    self.model = SentenceTransformer(self.model_name)

                _log_info("Model ready, search in progress...")
            except Exception as e:
                _log_error(f"Failed to load embedding model: {e}")
                return []

        # Encode query
        try:
            import faiss
        except ImportError:
            _log_error("faiss not available for semantic search")
            return []

        query_embedding = self.model.encode([query], convert_to_numpy=True)
        faiss.normalize_L2(query_embedding)

        # Search
        k = min(max_results * 3, len(self.items))  # Get more results for filtering
        scores, indices = self.index.search(query_embedding, k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.items):
                continue

            item = self.items[idx]

            # Filter by source
            if source_filter != "all" and item.get("source") != source_filter:
                continue

            results.append({
                "score": float(score),
                "source": item.get("source"),
                "entity": item.get("entity"),
                "name": item.get("name"),
                "type": item.get("type"),
                "description": item.get("description", "")[:150],
                "category": item.get("category"),
                "signature": item.get("signature", ""),
            })

            if len(results) >= max_results:
                break

        return results

def _load_library_api_index(
    index: "APIIndex",
    index_dir: Path,
    library_name: str,
    api_prefix: str,
    version_detector: callable,
    attr_name: str,
    version_attr: str,
) -> None:
    """Load a single library's API index with version fallback logic.

    Consolidates the repetitive pattern of:
    1. Detect installed version
    2. Try exact version match
    3. Fall back to latest version
    4. Auto-refresh if still missing
    5. Load JSON and store version

    Args:
        index: APIIndex instance to populate
        index_dir: Parent index directory
        library_name: Display name ('LibLCM', 'FlexLibs 2.0', etc.)
        api_prefix: API file prefix ('liblcm_api', 'flexlibs2_api', etc.)
        version_detector: Callable that returns installed version
        attr_name: APIIndex attribute name ('liblcm', 'flexlibs2', etc.)
        version_attr: APIIndex version attribute name ('liblcm_version', etc.)
    """
    lib_dir = index_dir / "liblcm" if api_prefix == "liblcm_api" else index_dir / "flexlibs"
    installed_version = version_detector()

    # Try exact version match
    api_path = None
    if installed_version:
        _log_info(f"Detected installed {library_name}: {installed_version}")
        api_path = find_versioned_api_file(lib_dir, api_prefix, installed_version)

    # Fall back to latest if exact match not found
    if not api_path:
        if installed_version:
            _log_info(f"No API file for {library_name} {installed_version}, falling back to latest")
        api_path = find_latest_versioned_api_file(lib_dir, api_prefix)

    # Auto-refresh if still not found
    if not api_path:
        _log_info(f"No {library_name} API file found, attempting auto-refresh...")
        library_key = "liblcm" if api_prefix == "liblcm_api" else ("flexlibs2" if api_prefix == "flexlibs2_api" else "flexlibs")
        if auto_refresh_missing_api_file(library_key, api_prefix, lib_dir):
            if installed_version:
                api_path = find_versioned_api_file(lib_dir, api_prefix, installed_version)
            if not api_path:
                api_path = find_latest_versioned_api_file(lib_dir, api_prefix)

    # Load JSON and extract version
    if api_path:
        try:
            with open(api_path, "r", encoding="utf-8") as f:
                setattr(index, attr_name, json.load(f))
            # Extract version from filename (e.g., liblcm_api_v11.0.0.json -> 11.0.0)
            parts = api_path.stem.split("_v")
            extracted_version = parts[-1] if len(parts) >= 2 else None
            setattr(index, version_attr, extracted_version)
            if installed_version:
                _log_info(f"Loaded {library_name} {installed_version} from {api_path.name}")
            else:
                _log_info(f"Loaded {library_name} from {api_path.name}")
        except Exception as e:
            _log_error(f"Failed to load {library_name}: {e}")

def _load_json_with_fallback(index_dir: Path, versioned_prefix: str, unversioned_name: str) -> dict | None:
    """Load JSON file with versioned name fallback to unversioned name (DRY consolidation).

    Tries to load {versioned_prefix}_vX.Y.Z.json, falls back to {unversioned_name}.json.
    This pattern was duplicated for navigation_graph and casting_index (DRY violation).

    Args:
        index_dir: Parent index directory
        versioned_prefix: Prefix for versioned file search (e.g., 'navigation_graph_liblcm')
        unversioned_name: Unversioned fallback filename (e.g., 'navigation_graph.json')

    Returns:
        Loaded JSON dict or None if not found
    """
    # Try versioned first
    versioned_path = find_latest_versioned_api_file(index_dir, versioned_prefix)
    if versioned_path and versioned_path.exists():
        try:
            with open(versioned_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Fall back to unversioned
    unversioned_path = index_dir / unversioned_name
    if unversioned_path.exists():
        try:
            with open(unversioned_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return None

@dataclass
class APIIndex:
    """Holds the loaded API documentation indexes."""
    liblcm: dict | None = None
    flexlibs2: dict | None = None
    flexlibs_stable: dict | None = None
    navigation_graph: dict | None = None
    casting_index: dict | None = None
    semantic_search: SemanticSearch | None = None

    # Track loaded API versions for session logging
    liblcm_version: str | None = None
    flexlibs2_version: str | None = None
    flexlibs_stable_version: str | None = None

    @classmethod
    def load(cls, index_dir: Path) -> "APIIndex":
        """Load API indexes at startup.

        Only FlexLibs2 is loaded at startup for speed (0.049s).
        LibLCM and FlexLibs stable are lazy-loaded on first use (deferred 0.808s).
        Navigation/casting/semantic search are optional and loaded on-demand.
        """
        index = cls()

        # Load all three main APIs at startup (~0.9s combined, much better UX)
        # Previous lazy-loading saved 0.8s but caused delays on first API calls
        _load_library_api_index(
            index,
            index_dir,
            "FlexLibs 2.0",
            "flexlibs2_api",
            get_installed_flexlibs2_version,
            "flexlibs2",
            "flexlibs2_version",
        )

        _load_library_api_index(
            index,
            index_dir,
            "LibLCM",
            "liblcm_api",
            get_installed_liblcm_version,
            "liblcm",
            "liblcm_version",
        )

        _load_library_api_index(
            index,
            index_dir,
            "FlexLibs stable",
            "flexlibs_api",
            get_installed_flexlibs_version,
            "flexlibs_stable",
            "flexlibs_stable_version",
        )

        # Navigation, casting, and semantic search are optional and loaded on-demand
        return index

    def ensure_liblcm_loaded(self) -> None:
        """Lazy-load LibLCM if not already loaded. Called by tools that need it."""
        if self.liblcm is not None:
            return  # Already loaded

        _lib_start = _time_module.time()
        _load_library_api_index(
            self,
            get_index_dir(),
            "LibLCM",
            "liblcm_api",
            get_installed_liblcm_version,
            "liblcm",
            "liblcm_version",
        )
        _lib_done = _time_module.time()

    def ensure_flexlibs_stable_loaded(self) -> None:
        """Lazy-load FlexLibs stable if not already loaded. Called by tools that need it."""
        if self.flexlibs_stable is not None:
            return  # Already loaded

        _lib_start = _time_module.time()
        _load_library_api_index(
            self,
            get_index_dir(),
            "FlexLibs stable",
            "flexlibs_api",
            get_installed_flexlibs_version,
            "flexlibs_stable",
            "flexlibs_stable_version",
        )
        _lib_done = _time_module.time()

    def ensure_navigation_graph_loaded(self) -> None:
        """Lazy-load navigation graph if not already loaded."""
        if self.navigation_graph is not None:
            return  # Already loaded

        _nav_start = _time_module.time()
        self.navigation_graph = _load_json_with_fallback(
            get_index_dir(),
            "navigation_graph_liblcm",
            "navigation_graph.json"
        )
        _nav_done = _time_module.time()

    def ensure_casting_index_loaded(self) -> None:
        """Lazy-load casting index if not already loaded."""
        if self.casting_index is not None:
            return  # Already loaded

        _cast_start = _time_module.time()
        self.casting_index = _load_json_with_fallback(
            get_index_dir(),
            "casting_index_liblcm",
            "casting_index.json"
        )
        _cast_done = _time_module.time()

    def ensure_semantic_search_loaded(self) -> None:
        """Lazy-load semantic search if not already loaded."""
        if self.semantic_search is not None:
            return  # Already loaded

        _search_start = _time_module.time()
        self.semantic_search = SemanticSearch.load(get_index_dir())
        _search_done = _time_module.time()

# Initialize the MCP server
_server_init_begin = _time_module.time()
server = Server("flextools-mcp")
_server_init_done = _time_module.time()

# Global index (loaded on startup)
api_index: Optional[APIIndex] = None

def get_index_dir() -> Path:
    """Get the index directory path."""
    return Path(__file__).parent.parent / "index"

def get_installed_liblcm_version() -> Optional[str]:
    """Detect the version of LibLCM currently installed.

    Returns:
        Version string (e.g., '11.0.0') or None if not detected
    """
    return detect_installed_library_version(
        "LibLCM",
        assembly_name="SIL.LCModel"
    )

def get_installed_flexlibs2_version() -> Optional[str]:
    """Detect the version of FlexLibs 2.0 currently installed.

    Returns:
        Version string (e.g., '2.1.0') or None if not detected
    """
    return detect_installed_library_version(
        "FlexLibs 2.0",
        import_path="flexlibs2",
        package_name="flexlibs2"
    )

def get_installed_flexlibs_version() -> Optional[str]:
    """Detect the version of stable FlexLibs currently installed.

    Returns:
        Version string (e.g., '1.2.8') or None if not detected
    """
    return detect_installed_library_version(
        "FlexLibs stable",
        import_path="flexlibs",
        package_name="flexlibs"
    )

# find_latest_versioned_api_file and find_versioned_api_file are now imported from .server.versioning
# (See imports at top of file)

def auto_refresh_missing_api_file(library_name: str, prefix: str, index_dir: Path) -> bool:
    """Auto-refresh a missing API file by running the analyzer.

    Args:
        library_name: Name of library ('flexlibs', 'flexlibs2', 'liblcm')
        prefix: File prefix for versioned files
        index_dir: Parent directory

    Returns:
        True if refresh was attempted/successful, False otherwise
    """
    try:
        # Import refresh functions
        import sys
        from pathlib import Path as PathlibPath

        refresh_script = Path(__file__).parent / "refresh.py"
        if not refresh_script.exists():
            _log_error(f"Refresh script not found: {refresh_script}")
            return False

        import subprocess
        project_root = Path(__file__).parent.parent

        cmd = [sys.executable, str(refresh_script)]

        if library_name == 'flexlibs':
            cmd.append("--flexlibs-only")
        elif library_name == 'flexlibs2':
            cmd.append("--flexlibs2-only")
        elif library_name == 'liblcm':
            cmd.append("--liblcm-only")
        else:
            return False

        _log_info(f"Auto-refreshing {library_name} API index...")
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            _log_info(f"Successfully refreshed {library_name} API index")
            return True
        else:
            _log_warning(f"Failed to refresh {library_name}: {result.stderr[:500]}")
            return False

    except Exception as e:
        _log_warning(f"Could not auto-refresh {library_name}: {e}")
        return False

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all MCP tools, generated from Pydantic models in tool_definitions.py.

    Each tool is auto-generated from its corresponding Pydantic input model,
    which provides automatic validation and type coercion.
    Schemas are cached to avoid regeneration on each list_tools() call.
    """
    tools: list[Tool] = []
    for tool_def in TOOL_DEFINITIONS.values():
        schema = tool_def.get_schema()  # Uses cached schema if available
        tools.append(
            Tool(
                name=tool_def.name,
                description=tool_def.description,
                annotations=tool_def.annotations,
                inputSchema=schema,
            )
        )

    return tools

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    # api_index is pre-loaded in main() at startup, no lazy loading needed
    # Session initialization gate: flextools_start is the only tool that doesn't require it
    if name != "flextools_start" and not session_state.initialized:
        return [TextContent(type="text", text=json.dumps({
            "error": "Session not initialized",
            "message": "You must call flextools_start() first to initialize the session and set the API mode.",
            "hint": "Call flextools_start(task='your task description') to begin. This will discover relevant APIs and configure the session.",
            "available_task_examples": [
                "Add gloss to sense definitions",
                "Delete senses with test in gloss",
                "Count entries by part of speech",
                "Create new lexical entries"
            ]
        }, indent=2))]

    # Look up handler and input model from dispatch router
    route = get_tool_handler(name)
    if route is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    handler, input_model = route

    # Validate and parse arguments using Pydantic model
    try:
        validated_args = input_model(**arguments)
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "error": "Input validation failed",
            "message": str(e),
            "tool": name,
            "received_arguments": arguments,
        }, indent=2))]

    # Dispatch to handler with validated input (convert to dict for backward compatibility)
    return await handler(validated_args.model_dump())

async def main():
    """Run the MCP server."""
    global api_index
    import time

    _main_start = _time_module.time()
    _module_init_elapsed = _main_start - _startup_begin

    # Pre-load indexes
    _log_info("Loading API indexes...")
    _api_load_start = _time_module.time()
    api_index = APIIndex.load(get_index_dir())
    _api_load_done = _time_module.time()
    _api_load_elapsed = _api_load_done - _api_load_start
    _log_info(f"API indexes loaded in {_api_load_elapsed:.2f}s")

    _log_start = _time_module.time()
    if api_index.liblcm:
        version = api_index.liblcm_version or "unknown"
        entities = len(api_index.liblcm.get('entities', {}))
        _log_info(f"LibLCM v{version}: {entities} entities")
    else:
        _log_warning( "LibLCM index not found")

    if api_index.flexlibs2:
        version = api_index.flexlibs2_version or "unknown"
        entities = len(api_index.flexlibs2.get('entities', {}))
        _log_info( f"FlexLibs 2.0 v{version}: {entities} entities")
    else:
        _log_warning( "FlexLibs 2.0 index not found")

    if api_index.casting_index:
        props = len(api_index.casting_index.get("properties", {}))
        colls = len(api_index.casting_index.get("polymorphic_collections", {}))
        _log_info( f"Casting index: {props} properties, {colls} polymorphic collections")
    else:
        _log_warning( "Casting index not found")

    if api_index.flexlibs_stable:
        version = api_index.flexlibs_stable_version or "unknown"
        entities = len(api_index.flexlibs_stable.get('entities', {}))
        _log_info( f"FlexLibs Stable v{version}: {entities} entities")
    else:
        _log_warning( "FlexLibs Stable index not found")
    _log_done = _time_module.time()

    # Print version and entity summary to console so user knows what APIs are loaded
    _versions_start = _time_module.time()
    versions = []
    if api_index.liblcm and api_index.liblcm_version:
        entities = len(api_index.liblcm.get('entities', {}))
        versions.append(f"LibLCM {api_index.liblcm_version} ({entities} entities)")
    if api_index.flexlibs2 and api_index.flexlibs2_version:
        entities = len(api_index.flexlibs2.get('entities', {}))
        versions.append(f"FlexLibs2 {api_index.flexlibs2_version} ({entities} entities)")
    if api_index.flexlibs_stable and api_index.flexlibs_stable_version:
        entities = len(api_index.flexlibs_stable.get('entities', {}))
        versions.append(f"FlexLibs {api_index.flexlibs_stable_version} ({entities} entities)")
    _versions_done = _time_module.time()

    if versions:
        # Note: Can't use stdout during init (breaks MCP protocol parser)
        # So we use stderr, which shows as [warning] but displays the data
        print(f"Loaded APIs: {', '.join(versions)}", file=sys.stderr, flush=True)

    _log_info( "Starting MCP server...")

    _stdio_server_begin = _time_module.time()
    async with stdio_server() as (read_stream, write_stream):
        _stdio_server_done = _time_module.time()

        _server_run_begin = _time_module.time()
        try:
            await server.run(read_stream, write_stream, server.create_initialization_options())
        except Exception as e:
            print(f"[ERROR] server.run() raised exception: {e}", file=sys.stderr, flush=True)
            raise
        finally:
            _server_run_done = _time_module.time()

if __name__ == "__main__":
    _asyncio_begin = _time_module.time()
    asyncio.run(main())
