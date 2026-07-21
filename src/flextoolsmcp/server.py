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
import os
import warnings
from pathlib import Path
from typing import Any, Optional, List, Dict, TYPE_CHECKING
from dataclasses import dataclass, field
import io
from contextlib import redirect_stdout, redirect_stderr

_imports_std_done = _time_module.time()

# Suppress noisy third-party warnings and output
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
# Cache HuggingFace models under the single user-state root (persistent across
# runs and package upgrades). Only set if the user hasn't chosen their own.
os.environ.setdefault('HF_HOME', str(Path.home() / '.flextoolsmcp' / 'hf'))
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
    from .server.kernel import (
        operations_logger,
        session_state,
    )
    from .server.tool_definitions import TOOLS as TOOL_DEFINITIONS
    from .server.dispatch import get_tool_handler
    from .server.versioning import (
        detect_installed_library_version,
        find_versioned_api_file,
        find_latest_versioned_api_file,
        clear_file_discovery_cache,
    )
    from .server.startup_notices import record_index_refresh_failure
else:
    from server.kernel import (
        operations_logger,
        session_state,
    )
    from server.tool_definitions import TOOLS as TOOL_DEFINITIONS
    from server.dispatch import get_tool_handler
    from server.versioning import (
        detect_installed_library_version,
        find_versioned_api_file,
        find_latest_versioned_api_file,
        clear_file_discovery_cache,
    )
    from server.startup_notices import record_index_refresh_failure
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
# Flexicon Operations Contract
# ============================================================
# These constants are imported from server.constants
# and are required by pre-commit hooks to verify runtime consistency

# Exception classes used in flexicon namespace
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
)

# Optional imports for semantic search - DEFERRED to on-demand loading
# These imports are intentionally NOT done at module level to avoid 14+ second
# startup penalty. They are imported lazily when semantic search is actually used.
if TYPE_CHECKING:
    pass

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
        # scores[0]/indices[0] are the two parallel outputs of the same faiss
        # search() call, so they are always equal length -- strict=True makes
        # that invariant explicit rather than silently tolerating a mismatch.
        for score, idx in zip(scores[0], indices[0], strict=True):
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

# Libraries we've already tried to auto-refresh in this process. Refresh shells
# out to refresh.py (seconds, and it needs the extraction source -- pyflexicon,
# FieldWorks DLLs, or flexlibs -- which may be absent), so we attempt it at most
# once per library per process to keep startup and repeated loads fast.
_REFRESH_ATTEMPTED: set = set()


def _library_key_for_prefix(api_prefix: str) -> str:
    """Map an API file prefix to the refresh CLI library key."""
    if api_prefix == "liblcm_api":
        return "liblcm"
    if api_prefix == "flexicon_api":
        return "flexicon"
    return "flexlibs"


def _extract_file_version(api_path: Path) -> str | None:
    """Extract the version from a versioned API filename.

    Handles both naming patterns: ``prefix_vX.Y.Z.json`` and
    ``prefix-vX.Y.Z.json``. Returns None if no version segment is present.
    """
    stem = api_path.stem
    for sep in ("_v", "-v"):
        if sep in stem:
            return stem.split(sep)[-1]
    return None


def _version_tuple(version: str | None) -> tuple:
    """Best-effort numeric key for older/newer comparison.

    Splits on ``.`` and reads the leading digits of each component, so
    ``11.0.0`` -> ``(11, 0, 0)``. Non-numeric or malformed components read as 0
    rather than raising -- version comparison must never crash startup.
    """
    if not version:
        return ()
    parts = []
    for chunk in str(version).split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _mismatch_direction(shipped_version: str | None, installed_version: str | None) -> str:
    """Describe how the served index version relates to the installed library."""
    shipped, installed = _version_tuple(shipped_version), _version_tuple(installed_version)
    if shipped and installed:
        if shipped < installed:
            return "older than your installed library"
        if shipped > installed:
            return "newer than your installed library"
    return "a different version than your installed library"


def _try_refresh_once(library_key: str, api_prefix: str, lib_dir: Path) -> bool:
    """Auto-refresh a library at most once per process.

    Returns True only if a refresh actually ran and reported success -- in which
    case the file-discovery cache is cleared so files written by the refresh are
    visible to the subsequent lookup (the cache stores negative results too).
    """
    if library_key in _REFRESH_ATTEMPTED:
        return False
    _REFRESH_ATTEMPTED.add(library_key)
    if auto_refresh_missing_api_file(library_key, api_prefix, lib_dir):
        clear_file_discovery_cache()
        return True
    return False


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
        library_name: Display name ('LibLCM', 'Flexicon', etc.)
        api_prefix: API file prefix ('liblcm_api', 'flexicon_api', etc.)
        version_detector: Callable that returns installed version
        attr_name: APIIndex attribute name ('liblcm', 'flexicon', etc.)
        version_attr: APIIndex version attribute name ('liblcm_version', etc.)
    """
    lib_dir = index_dir / "liblcm" if api_prefix == "liblcm_api" else index_dir / "python"
    installed_version = version_detector()
    library_key = _library_key_for_prefix(api_prefix)

    # 1. Exact match for the installed library version.
    api_path = None
    if installed_version:
        _log_info(f"Detected installed {library_name}: {installed_version}")
        api_path = find_versioned_api_file(lib_dir, api_prefix, installed_version)

    # 2. No exact match, but we know the installed version (it may be newer OR
    #    older than anything shipped). Try to regenerate an index that matches
    #    the installed library before serving a non-matching shipped one.
    #    Refresh is attempted at most once per process and needs the extraction
    #    source (pyflexicon / FieldWorks DLLs / flexlibs), so it may not succeed
    #    on every machine.
    if not api_path and installed_version and library_key not in _REFRESH_ATTEMPTED:
        _log_info(
            f"No {library_name} index matching installed v{installed_version}; "
            f"attempting refresh to regenerate it..."
        )
        if _try_refresh_once(library_key, api_prefix, lib_dir):
            api_path = find_versioned_api_file(lib_dir, api_prefix, installed_version)

    # 3. Still no exact match: serve the nearest (latest) shipped index and warn
    #    loudly that the documented API surface may not match the installed
    #    library -- in either direction (missing new APIs, or showing APIs the
    #    installed version lacks).
    if not api_path:
        api_path = find_latest_versioned_api_file(lib_dir, api_prefix)
        if api_path and installed_version:
            shipped_version = _extract_file_version(api_path)
            _log_warning(
                f"{library_name}: no index for installed v{installed_version}; "
                f"serving v{shipped_version or '?'}, which is "
                f"{_mismatch_direction(shipped_version, installed_version)}. "
                f"Documented APIs may not match -- some methods may be missing, or "
                f"shown but absent in your version. Regenerate a matching index with "
                f"'python -m flextoolsmcp.refresh --{library_key}-only'."
            )
            # The library IS installed but auto-refresh (step 2) could not
            # produce a matching index, so we are serving a ballpark shipped
            # index. Stash a notice so flextools_start can offer the user a
            # prefilled bug report (refresh is not yet 100% bulletproof).
            record_index_refresh_failure(
                library_name=library_name,
                library_key=library_key,
                installed_version=installed_version,
                served_version=shipped_version,
            )

    # 4. Nothing shipped at all: last-ditch refresh (skipped if step 2 already
    #    tried this library).
    if not api_path and library_key not in _REFRESH_ATTEMPTED:
        _log_info(f"No {library_name} API file found, attempting auto-refresh...")
        if _try_refresh_once(library_key, api_prefix, lib_dir):
            if installed_version:
                api_path = find_versioned_api_file(lib_dir, api_prefix, installed_version)
            if not api_path:
                api_path = find_latest_versioned_api_file(lib_dir, api_prefix)

    # 5. Load JSON and record the version actually served.
    if api_path:
        try:
            with open(api_path, "r", encoding="utf-8") as f:
                setattr(index, attr_name, json.load(f))
            extracted_version = _extract_file_version(api_path)
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
    flexicon: dict | None = None
    flexlibs_stable: dict | None = None
    navigation_graph: dict | None = None
    casting_index: dict | None = None
    semantic_search: SemanticSearch | None = None
    flexicon_lcm_bridge: dict | None = None
    flexlibs_stable_lcm_bridge: dict | None = None
    reverse_mapping: dict | None = None

    # Track loaded API versions for session logging
    liblcm_version: str | None = None
    flexicon_version: str | None = None
    flexlibs_stable_version: str | None = None

    # Stale lock warnings detected at startup (surfaced by flextools_health)
    startup_lock_warnings: list = field(default_factory=list)

    @classmethod
    def load(cls, index_dir: Path) -> "APIIndex":
        """Load API indexes at startup.

        Parallelizes library loading for 60% faster startup (~0.3s vs ~0.9s).
        - Flexicon, LibLCM, FlexLibs stable loaded concurrently
        - Navigation/casting/semantic search loaded on-demand
        """
        from concurrent.futures import ThreadPoolExecutor

        index = cls()

        # Parallelize three independent API loads (file I/O bound)
        # ThreadPoolExecutor reduces startup from ~0.9s to ~0.3s
        with ThreadPoolExecutor(max_workers=3) as executor:
            executor.submit(
                _load_library_api_index,
                index,
                index_dir,
                "Flexicon",
                "flexicon_api",
                get_installed_flexicon_version,
                "flexicon",
                "flexicon_version",
            )

            executor.submit(
                _load_library_api_index,
                index,
                index_dir,
                "LibLCM",
                "liblcm_api",
                get_installed_liblcm_version,
                "liblcm",
                "liblcm_version",
            )

            executor.submit(
                _load_library_api_index,
                index,
                index_dir,
                "FlexLibs stable",
                "flexlibs_api",
                get_installed_flexlibs_version,
                "flexlibs_stable",
                "flexlibs_stable_version",
            )
            # Context manager waits for all tasks to complete

        # Load navigation and casting at startup (small files, commonly needed)
        index.ensure_navigation_graph_loaded()
        index.ensure_casting_index_loaded()

        # Semantic search remains lazy-loaded (expensive, rarely used)
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

    def _load_lcm_bridge(self, library_label: str, prefix: str, version: str | None) -> dict | None:
        """Load an LCM bridge JSON file by library prefix, with version fallback."""
        bridge_dir = get_index_dir() / "python"

        bridge_path = None
        if version:
            bridge_path = find_versioned_api_file(bridge_dir, prefix, version)
        if not bridge_path:
            bridge_path = find_latest_versioned_api_file(bridge_dir, prefix)

        if not bridge_path:
            _log_warning(f"No {library_label} LCM bridge file found in {bridge_dir}")
            return None

        try:
            with open(bridge_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            _log_info(f"Loaded {library_label} LCM bridge from {bridge_path.name}")
            return data
        except Exception as e:
            _log_error(f"Failed to load {library_label} LCM bridge: {e}")
            return None

    def ensure_flexicon_bridge_loaded(self) -> None:
        """Lazy-load Flexicon LCM bridge if not already loaded."""
        if self.flexicon_lcm_bridge is not None:
            return
        self.flexicon_lcm_bridge = self._load_lcm_bridge(
            "Flexicon", "flexicon_lcm_bridge", self.flexicon_version
        )

    def ensure_flexlibs_stable_bridge_loaded(self) -> None:
        """Lazy-load FlexLibs stable LCM bridge if not already loaded."""
        if self.flexlibs_stable_lcm_bridge is not None:
            return
        self.flexlibs_stable_lcm_bridge = self._load_lcm_bridge(
            "FlexLibs stable", "flexlibs_lcm_bridge", self.flexlibs_stable_version
        )

    def ensure_reverse_mapping_loaded(self) -> None:
        """Lazy-load LibLCM reverse mapping (LCM -> wrapper coverage) if not already loaded."""
        if self.reverse_mapping is not None:
            return
        self.reverse_mapping = _load_json_with_fallback(
            get_index_dir(),
            "reverse_mapping_liblcm",
            "reverse_mapping.json"
        )

# Initialize the MCP server
_server_init_begin = _time_module.time()
server = Server("flextools-mcp")
_server_init_done = _time_module.time()

# Global index (loaded on startup)
api_index: Optional[APIIndex] = None

def get_index_dir() -> Path:
    """Get the working index directory.

    Delegates to file_utils, which returns the in-tree index for source
    checkouts and a user-writable overlay (~/.flextoolsmcp/index, seeded from
    the bundled index) for installed wheels.
    """
    if __package__:
        from .file_utils import get_index_dir as _impl
    else:
        from file_utils import get_index_dir as _impl
    return _impl()

def get_installed_liblcm_version() -> Optional[str]:
    """Detect the version of LibLCM currently installed.

    Returns:
        Version string (e.g., '11.0.0') or None if not detected
    """
    return detect_installed_library_version(
        "LibLCM",
        assembly_name="SIL.LCModel"
    )

def get_installed_flexicon_version() -> Optional[str]:
    """Detect the version of Flexicon currently installed.

    Returns:
        Version string (e.g., '2.1.0') or None if not detected
    """
    return detect_installed_library_version(
        "Flexicon",
        import_path="flexicon",
        package_name="pyflexicon"
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
        library_name: Name of library ('flexlibs', 'flexicon', 'liblcm')
        prefix: File prefix for versioned files
        index_dir: Parent directory

    Returns:
        True if refresh was attempted/successful, False otherwise
    """
    try:
        # Import refresh functions
        import sys

        refresh_script = Path(__file__).parent / "refresh.py"
        if not refresh_script.exists():
            _log_error(f"Refresh script not found: {refresh_script}")
            return False

        import subprocess
        # Run from the package directory so refresh.py's absolute-path script
        # invocations resolve in both source and installed (wheel) layouts.
        project_root = Path(__file__).parent

        cmd = [sys.executable, str(refresh_script)]

        if library_name == 'flexlibs':
            cmd.append("--flexlibs-only")
        elif library_name == 'flexicon':
            cmd.append("--flexicon-only")
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
        kwargs: Dict[str, Any] = {
            "name": tool_def.name,
            "description": tool_def.description,
            "annotations": tool_def.annotations,
            "inputSchema": schema,
        }
        # NOTE (issue #54 follow-up): outputSchema advertisement is intentionally
        # DISABLED. Per MCP spec 2025-06-18, a tool that advertises outputSchema MUST
        # return structuredContent matching it, and clients validate accordingly. This
        # server's call_tool() currently returns text-only (json_response -> [TextContent]),
        # so advertising the schema causes spec-compliant clients (e.g. Claude Code) to
        # reject every response from run_module / get_object_api / search_by_capability.
        # Re-enable ONLY together with returning structuredContent from call_tool() (the
        # low-level mcp API supports returning (list[ContentBlock], dict)) AND after
        # confirming the handler dicts validate against the *Success models. See docs/TODO.md.
        # if tool_def.output_model is not None:
        #     kwargs["outputSchema"] = tool_def.output_model.model_json_schema(by_alias=True)
        tools.append(Tool(**kwargs))

    return tools

# Tools that may run before flextools_start() -- they touch neither the session
# state nor the LCM cache. flextools_start initializes the session; list_projects
# is a read-only directory scan the user typically runs first to pick a project.
_SESSION_INDEPENDENT_TOOLS = frozenset({
    "flextools_start",
    "flextools_list_projects",
    # Issue #56: flextools_health is a pure-read diagnostic composed from
    # existing detectors -- it must be callable even when the session isn't
    # initialized yet (that's precisely the "user is stuck, nothing else
    # works" case it exists to help with).
    "flextools_health",
})


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    # Log tool invocation (with safety check for early init).
    # [TOOL CALL] and [TOOL ARGS] are both INFO so they survive the default
    # log-level cutoff and reach operations.log across sessions (issue #19).
    # Args truncated to 500 chars to keep the record bounded.
    if operations_logger:
        operations_logger.info(f"[TOOL CALL] {name}")
        operations_logger.info(f"[TOOL ARGS] {name}: {json.dumps(arguments, default=str)[:500]}")

    # api_index is pre-loaded in main() at startup, no lazy loading needed
    # Session initialization gate. Exempt tools that need neither the session
    # nor the LCM cache: flextools_start (the initializer itself) and
    # flextools_list_projects (a read-only directory scan -- see
    # handle_list_projects). Listing projects BEFORE start() is the natural
    # first step when the user hasn't named a project yet, so forcing a session
    # (and API discovery) ahead of it is backwards. The discovery gate that
    # matters -- api_discovery_required in run_module -- is unaffected.
    #
    # Issue #53 (cold-start tolerance): a READ_ONLY_SAFE-annotated tool (see
    # tool_definitions.READ_ONLY_SAFE) never touches a project, so a missing
    # session is pure ceremony -- auto-initialize read-only instead of
    # rejecting. flextools_run_module is a special case: it genuinely needs a
    # project, but if the caller already named one in this very call there's
    # no reason to bounce -- initialize the session from it (read-only unless
    # write_enabled was explicitly passed) and let the normal run proceed. If
    # run_module is cold AND has no project_name, it still gets auto-initialized
    # (read-only, no project) so its OWN project_name_required rejection can
    # attach available_projects (see handlers/execution.py) instead of dying
    # here with the old generic message.
    #
    # This must NEVER auto-select a project, and must NEVER set
    # write_enabled=True unless the caller passed it explicitly in THIS call.
    _pending_session_note: Optional[str] = None
    if name not in _SESSION_INDEPENDENT_TOOLS and not session_state.initialized:
        tool_def = TOOL_DEFINITIONS.get(name)
        is_read_only_safe = bool(
            tool_def is not None and getattr(tool_def.annotations, "readOnlyHint", False)
        )
        is_run_module = (name == "flextools_run_module")

        if is_read_only_safe or is_run_module:
            cold_project_name = arguments.get("project_name") if is_run_module else None
            # Only ever honor write_enabled/undoable if the CALLER explicitly
            # passed them on this cold run_module call -- never default to True.
            cold_write_enabled = bool(arguments.get("write_enabled")) if (
                is_run_module and arguments.get("write_enabled") is not None
            ) else False
            cold_undoable = bool(arguments.get("undoable")) if (
                is_run_module and arguments.get("undoable") is not None
            ) else False

            session_state.configure(
                api_mode="flexicon",
                write_enabled=cold_write_enabled,
                undoable=cold_undoable,
                project_name=cold_project_name or "",
            )
            auto_init_count = session_state.record_auto_init()
            if operations_logger:
                operations_logger.info(
                    f"[AUTO-INIT] {name}: cold session auto-initialized "
                    f"(project={cold_project_name or '(none)'}, "
                    f"write_enabled={cold_write_enabled}, count={auto_init_count})"
                )
            if is_read_only_safe:
                _pending_session_note = (
                    "Session auto-initialized (flexicon, read-only). Call "
                    "flextools_start to set a project or change api_mode."
                )
            # Fall through to normal dispatch below -- do NOT return here.
        else:
            # Diagnostic context for #10 (Session-not-initialized between consecutive
            # run_module calls). Static analysis found no code path that resets
            # `initialized` to False, so we log identity info every time this gate
            # fires to catch the live cause next time it happens.
            diag = {
                "session_state_id": id(session_state),
                "session_id": getattr(session_state, "session_id", None),
                "project_name": getattr(session_state, "project_name", None),
                "api_mode": getattr(session_state, "api_mode", None),
                "write_enabled": getattr(session_state, "write_enabled", None),
            }
            err_msg = "Session not initialized. Call flextools_start() first."
            if operations_logger:
                operations_logger.warning(f"[BLOCKED] {name}: {err_msg}")
                operations_logger.warning(f"[BLOCKED-DIAG] {name}: {json.dumps(diag, default=str)}")
            return [TextContent(type="text", text=json.dumps({
                "error": "Session not initialized",
                "message": "You must call flextools_start() first to initialize the session and set the API mode.",
                "hint": "Call flextools_start(task='your task description') to begin. This will discover relevant APIs and configure the session.",
                "_diagnostic": diag,  # See #10 -- helps trace stale-ref / restart cases
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
        if operations_logger:
            operations_logger.error(f"[ERROR] Unknown tool: {name}")
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    handler, input_model = route

    # Validate and parse arguments using Pydantic model
    try:
        validated_args = input_model(**arguments)
    except Exception as e:
        if operations_logger:
            operations_logger.error(f"[VALIDATION ERROR] {name}: {str(e)}")
        return [TextContent(type="text", text=json.dumps({
            "error": "Input validation failed",
            "message": str(e),
            "tool": name,
            "received_arguments": arguments,
        }, indent=2))]

    # Dispatch to handler with validated input (convert to dict for backward compatibility)
    if operations_logger:
        operations_logger.debug(f"[DISPATCHING] {name}")
    dumped = validated_args.model_dump()
    if name == "flextools_start":
        # Let handle_start distinguish user-provided fields from defaults so it
        # can inherit prior session state (e.g. write_enabled) on re-init.
        # Pydantic v2's `model_fields_set` is exactly this set, no re-dump needed.
        dumped["_user_provided_keys"] = validated_args.model_fields_set
    result = await handler(dumped)

    # Issue #53: attach the cold-start auto-init note to the response body
    # (rather than returning it as a separate signal) so it survives whatever
    # transport/serialization the client applies to the tool result.
    if _pending_session_note and result:
        try:
            _parsed = json.loads(result[0].text)
            if isinstance(_parsed, dict):
                _parsed["_session_note"] = _pending_session_note
                result = [TextContent(type="text", text=json.dumps(_parsed, indent=2, ensure_ascii=False))]
        except (ValueError, TypeError):
            pass  # Non-JSON response body (shouldn't happen) -- leave untouched.

    if operations_logger:
        result_text = result[0].text if result else ""
        # Log the OUTCOME at a level that survives the default cutoff, so every
        # tool leaves a visible trace -- and failures especially are never
        # silent. A handler signals a tool-level failure by returning a JSON
        # payload with a top-level "error" key (e.g. template_not_found); those
        # go to WARNING, successes to INFO. The verbose body stays at DEBUG.
        err_code = None
        if result_text:
            try:
                parsed = json.loads(result_text)
                if isinstance(parsed, dict):
                    err_code = parsed.get("error")
            except (ValueError, TypeError):
                err_code = None
        if err_code:
            operations_logger.warning(f"[TOOL ERROR] {name}: {err_code}")
        else:
            operations_logger.info(f"[TOOL OK] {name}")
        # Full result body for reproducibility (first 1000 chars), DEBUG only.
        result_preview = result_text[:1000] if result_text else "(empty)"
        operations_logger.debug(f"[OUT] {name}: {result_preview}")
    return result

async def main():
    """Run the MCP server."""
    global api_index

    _main_start = _time_module.time()
    _module_init_elapsed = _main_start - _startup_begin

    # Pre-load indexes
    _log_info("Loading API indexes...")
    _api_load_start = _time_module.time()
    api_index = APIIndex.load(get_index_dir())
    _api_load_done = _time_module.time()
    _api_load_elapsed = _api_load_done - _api_load_start
    _log_info(f"API indexes loaded in {_api_load_elapsed:.2f}s")

    # Share api_index with kernel module (used by handlers)
    if __package__:
        from .server.kernel import set_api_index, init_operations_logger
    else:
        from server.kernel import set_api_index, init_operations_logger
    set_api_index(api_index)
    init_operations_logger()

    # Issue #57 (C): detect stale .fwdata.lock files at startup (log-only, no deletion).
    if __package__:
        from .server.project_discovery import sweep_stale_locks
    else:
        from server.project_discovery import sweep_stale_locks
    _stale_lock_warnings = sweep_stale_locks()
    # Store on api_index so flextools_health can surface them without re-scanning.
    api_index.startup_lock_warnings = _stale_lock_warnings
    if _stale_lock_warnings:
        for _w in _stale_lock_warnings:
            _log_warning(_w)

    _log_start = _time_module.time()
    if api_index.liblcm:
        version = api_index.liblcm_version or "unknown"
        entities = len(api_index.liblcm.get('entities', {}))
        _log_info(f"LibLCM v{version}: {entities} entities")
    else:
        _log_warning( "LibLCM index not found")

    if api_index.flexicon:
        version = api_index.flexicon_version or "unknown"
        entities = len(api_index.flexicon.get('entities', {}))
        _log_info( f"Flexicon v{version}: {entities} entities")
    else:
        _log_warning( "Flexicon index not found")

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
    if api_index.flexicon and api_index.flexicon_version:
        entities = len(api_index.flexicon.get('entities', {}))
        versions.append(f"Flexicon {api_index.flexicon_version} ({entities} entities)")
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

def run() -> None:
    """Synchronous entry point for the ``flextoolsmcp`` console script.

    Console scripts (and ``python -m flextoolsmcp``) cannot target an async
    function directly, so this wraps ``main()`` in an event loop. This is the
    target referenced by ``[project.scripts]`` in pyproject.toml.
    """
    asyncio.run(main())


if __name__ == "__main__":
    _asyncio_begin = _time_module.time()
    run()
