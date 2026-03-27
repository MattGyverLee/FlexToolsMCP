#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FLExTools MCP Server

An MCP server that provides AI assistants with searchable documentation
of the LibLCM and FlexLibs APIs for generating FLExTools scripts.
"""

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

# Suppress noisy third-party warnings and output
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
warnings.filterwarnings('ignore', message='.*position_ids.*')
warnings.filterwarnings('ignore', message='.*unauthenticated requests.*')

# Ensure src is in sys.path when running as a script
if __package__ is None:
    _src_path = str(Path(__file__).parent)
    if _src_path not in sys.path:
        sys.path.insert(0, _src_path)

from mcp.server import Server

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


# ============================================================
# FlexLibs2 Operations Contract
# ============================================================
# These sets are required by pre-commit hooks to verify runtime consistency

KNOWN_OPERATIONS = {
    # Grammar
    "POSOperations", "PhonemeOperations", "NaturalClassOperations",
    "EnvironmentOperations", "MorphRuleOperations", "InflectionFeatureOperations",
    "GramCatOperations", "PhonologicalRuleOperations",
    # Lexicon
    "LexEntryOperations", "LexSenseOperations", "ExampleOperations",
    "LexReferenceOperations", "VariantOperations", "PronunciationOperations",
    "SemanticDomainOperations", "ReversalOperations", "EtymologyOperations",
    "AllomorphOperations",
    # TextsWords
    "TextOperations", "WordformOperations", "WfiAnalysisOperations",
    "ParagraphOperations", "SegmentOperations", "WfiGlossOperations",
    "WfiMorphBundleOperations", "MediaOperations", "FilterOperations",
    "DiscourseOperations",
    # Notebook
    "NoteOperations", "PersonOperations", "LocationOperations",
    "AnthropologyOperations", "DataNotebookOperations",
    # Lists
    "PublicationOperations", "AgentOperations", "ConfidenceOperations",
    "OverlayOperations", "TranslationTypeOperations", "PossibilityListOperations",
    # System
    "WritingSystemOperations", "ProjectSettingsOperations",
    "AnnotationDefOperations", "CheckOperations", "CustomFieldOperations",
}

OPERATIONS_CLASSES = {
    # Grammar
    "POSOperations", "PhonemeOperations", "NaturalClassOperations",
    "EnvironmentOperations", "MorphRuleOperations", "InflectionFeatureOperations",
    "GramCatOperations", "PhonologicalRuleOperations",
    # Lexicon
    "LexEntryOperations", "LexSenseOperations", "ExampleOperations",
    "LexReferenceOperations", "VariantOperations", "PronunciationOperations",
    "SemanticDomainOperations", "ReversalOperations", "EtymologyOperations",
    "AllomorphOperations",
    # TextsWords
    "TextOperations", "WordformOperations", "WfiAnalysisOperations",
    "ParagraphOperations", "SegmentOperations", "WfiGlossOperations",
    "WfiMorphBundleOperations", "MediaOperations", "FilterOperations",
    "DiscourseOperations",
    # Notebook
    "NoteOperations", "PersonOperations", "LocationOperations",
    "AnthropologyOperations", "DataNotebookOperations",
    # Lists
    "PublicationOperations", "AgentOperations", "ConfidenceOperations",
    "OverlayOperations", "TranslationTypeOperations", "PossibilityListOperations",
    # System
    "WritingSystemOperations", "ProjectSettingsOperations",
    "AnnotationDefOperations", "CheckOperations", "CustomFieldOperations",
}

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

# Optional imports for semantic search
if TYPE_CHECKING:
    import numpy as np
    import faiss
    from sentence_transformers import SentenceTransformer

try:
    import numpy as np
    import faiss
    from sentence_transformers import SentenceTransformer
    SEMANTIC_SEARCH_AVAILABLE = True
except ImportError:
    SEMANTIC_SEARCH_AVAILABLE = False


@dataclass
class SemanticSearch:
    """Handles semantic search using sentence-transformers and FAISS."""
    model: Any = None
    index: Any = None
    items: List[Dict] = field(default_factory=list)
    enabled: bool = False

    @classmethod
    def load(cls, index_dir: Path) -> "SemanticSearch":
        """Load semantic search index from disk."""
        search = cls()

        if not SEMANTIC_SEARCH_AVAILABLE:
            return search

        embeddings_dir = index_dir / "embeddings"
        embeddings_path = embeddings_dir / "embeddings.npy"
        metadata_path = embeddings_dir / "metadata.json"
        faiss_path = embeddings_dir / "faiss.index"

        if not all(p.exists() for p in [embeddings_path, metadata_path, faiss_path]):
            return search

        try:
            # Load metadata
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            search.items = metadata.get("items", [])

            # Load FAISS index
            search.index = faiss.read_index(str(faiss_path))

            # Load model (lazy - only when needed)
            model_name = metadata.get("_model", "all-MiniLM-L6-v2")
            with warnings.catch_warnings(), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                warnings.filterwarnings('ignore')
                search.model = SentenceTransformer(model_name)

            search.enabled = True
        except Exception as e:
            print(f"[WARN] Failed to load semantic search: {e}")

        return search

    def search(self, query: str, max_results: int = 10, source_filter: str = "all") -> List[Dict]:
        """Perform semantic search on the query."""
        if not self.enabled or not self.model or not self.index:
            return []

        # Encode query
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
        """Load all API indexes matching the installed library versions.

        Detects installed library versions and loads the corresponding API indexes.
        Falls back to latest version if exact match not found.
        """
        index = cls()

        # === LIBLCM ===
        installed_liblcm = get_installed_liblcm_version()
        liblcm_dir = index_dir / "liblcm"

        liblcm_path = None
        if installed_liblcm:
            operations_logger.info(f"Detected installed LibLCM: {installed_liblcm}")
            liblcm_path = find_versioned_api_file(liblcm_dir, "liblcm_api", installed_liblcm)

        # Fall back to latest if exact match not found
        if not liblcm_path:
            if installed_liblcm:
                operations_logger.info(f"No API file for LibLCM {installed_liblcm}, falling back to latest")
            liblcm_path = find_latest_versioned_api_file(liblcm_dir, "liblcm_api")

        # Auto-refresh if still not found
        if not liblcm_path:
            operations_logger.info("No LibLCM API file found, attempting auto-refresh...")
            if auto_refresh_missing_api_file("liblcm", "liblcm_api", liblcm_dir):
                if installed_liblcm:
                    liblcm_path = find_versioned_api_file(liblcm_dir, "liblcm_api", installed_liblcm)
                if not liblcm_path:
                    liblcm_path = find_latest_versioned_api_file(liblcm_dir, "liblcm_api")

        if liblcm_path:
            try:
                with open(liblcm_path, "r", encoding="utf-8") as f:
                    index.liblcm = json.load(f)
                # Extract version from filename (e.g., liblcm_api_v11.0.0.json -> 11.0.0)
                parts = liblcm_path.stem.split("_v")
                index.liblcm_version = parts[-1] if len(parts) >= 2 else None
                if installed_liblcm:
                    operations_logger.info(f"Loaded LibLCM {installed_liblcm} from {liblcm_path.name}")
                else:
                    operations_logger.info(f"Loaded LibLCM from {liblcm_path.name}")
            except Exception as e:
                operations_logger.error(f"Failed to load LibLCM: {e}")

        # === FLEXLIBS 2.0 ===
        installed_flexlibs2 = get_installed_flexlibs2_version()
        flexlibs_dir = index_dir / "flexlibs"

        flexlibs2_path = None
        if installed_flexlibs2:
            operations_logger.info(f"Detected installed FlexLibs 2.0: {installed_flexlibs2}")
            flexlibs2_path = find_versioned_api_file(flexlibs_dir, "flexlibs2_api", installed_flexlibs2)

        # Fall back to latest if exact match not found
        if not flexlibs2_path:
            if installed_flexlibs2:
                operations_logger.info(f"No API file for FlexLibs 2.0 {installed_flexlibs2}, falling back to latest")
            flexlibs2_path = find_latest_versioned_api_file(flexlibs_dir, "flexlibs2_api")

        # Auto-refresh if still not found
        if not flexlibs2_path:
            operations_logger.info("No FlexLibs 2.0 API file found, attempting auto-refresh...")
            if auto_refresh_missing_api_file("flexlibs2", "flexlibs2_api", flexlibs_dir):
                if installed_flexlibs2:
                    flexlibs2_path = find_versioned_api_file(flexlibs_dir, "flexlibs2_api", installed_flexlibs2)
                if not flexlibs2_path:
                    flexlibs2_path = find_latest_versioned_api_file(flexlibs_dir, "flexlibs2_api")

        if flexlibs2_path:
            try:
                with open(flexlibs2_path, "r", encoding="utf-8") as f:
                    index.flexlibs2 = json.load(f)
                # Extract version from filename (e.g., flexlibs2_api_v2.3.0.json -> 2.3.0)
                parts = flexlibs2_path.stem.split("_v")
                index.flexlibs2_version = parts[-1] if len(parts) >= 2 else None
                if installed_flexlibs2:
                    operations_logger.info(f"Loaded FlexLibs 2.0 {installed_flexlibs2} from {flexlibs2_path.name}")
                else:
                    operations_logger.info(f"Loaded FlexLibs 2.0 from {flexlibs2_path.name}")
            except Exception as e:
                operations_logger.error(f"Failed to load FlexLibs 2.0: {e}")

        # === FLEXLIBS STABLE ===
        installed_flexlibs = get_installed_flexlibs_version()

        flexlibs_stable_path = None
        if installed_flexlibs:
            operations_logger.info(f"Detected installed FlexLibs stable: {installed_flexlibs}")
            flexlibs_stable_path = find_versioned_api_file(flexlibs_dir, "flexlibs_api", installed_flexlibs)

        # Fall back to latest if exact match not found
        if not flexlibs_stable_path:
            if installed_flexlibs:
                operations_logger.info(f"No API file for FlexLibs {installed_flexlibs}, falling back to latest")
            flexlibs_stable_path = find_latest_versioned_api_file(flexlibs_dir, "flexlibs_api")

        # Auto-refresh if still not found
        if not flexlibs_stable_path:
            operations_logger.info("No FlexLibs stable API file found, attempting auto-refresh...")
            if auto_refresh_missing_api_file("flexlibs", "flexlibs_api", flexlibs_dir):
                if installed_flexlibs:
                    flexlibs_stable_path = find_versioned_api_file(flexlibs_dir, "flexlibs_api", installed_flexlibs)
                if not flexlibs_stable_path:
                    flexlibs_stable_path = find_latest_versioned_api_file(flexlibs_dir, "flexlibs_api")

        if flexlibs_stable_path:
            try:
                with open(flexlibs_stable_path, "r", encoding="utf-8") as f:
                    index.flexlibs_stable = json.load(f)
                # Extract version from filename (e.g., flexlibs_api_v1.2.8.json -> 1.2.8)
                parts = flexlibs_stable_path.stem.split("_v")
                index.flexlibs_stable_version = parts[-1] if len(parts) >= 2 else None
                if installed_flexlibs:
                    operations_logger.info(f"Loaded FlexLibs stable {installed_flexlibs} from {flexlibs_stable_path.name}")
                else:
                    operations_logger.info(f"Loaded FlexLibs stable from {flexlibs_stable_path.name}")
            except Exception as e:
                operations_logger.error(f"Failed to load FlexLibs stable: {e}")

        # Load navigation graph (find latest liblcm version)
        nav_graph_path = find_latest_versioned_api_file(index_dir, "navigation_graph_liblcm")
        if nav_graph_path and nav_graph_path.exists():
            with open(nav_graph_path, "r", encoding="utf-8") as f:
                index.navigation_graph = json.load(f)
        else:
            # Fall back to unversioned for compatibility
            nav_graph_path = index_dir / "navigation_graph.json"
            if nav_graph_path.exists():
                with open(nav_graph_path, "r", encoding="utf-8") as f:
                    index.navigation_graph = json.load(f)

        # Load casting index (pythonnet interface casting requirements)
        casting_path = find_latest_versioned_api_file(index_dir, "casting_index_liblcm")
        if casting_path and casting_path.exists():
            with open(casting_path, "r", encoding="utf-8") as f:
                index.casting_index = json.load(f)
        else:
            # Fall back to unversioned for compatibility
            casting_path = index_dir / "casting_index.json"
            if casting_path.exists():
                with open(casting_path, "r", encoding="utf-8") as f:
                    index.casting_index = json.load(f)

        # Load semantic search (optional)
        index.semantic_search = SemanticSearch.load(index_dir)

        return index


# Initialize the MCP server
server = Server("flextools-mcp")

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
    try:
        import clr
        clr.AddReference('SIL.LCModel')  # type: ignore

        # Get version from assembly metadata
        try:
            import System  # type: ignore
            asm = System.Reflection.Assembly.Load('SIL.LCModel')
            version_attr = asm.GetName().Version
            version = f"{version_attr.Major}.{version_attr.Minor}.{version_attr.Build}"
            operations_logger.debug(f"Detected LibLCM version from assembly: {version}")
            return version
        except Exception as ex:
            operations_logger.debug(f"Could not extract LibLCM version from assembly: {ex}")
            return None
    except Exception as e:
        operations_logger.debug(f"Could not detect LibLCM version: {e}")
        return None


def get_installed_flexlibs2_version() -> Optional[str]:
    """Detect the version of FlexLibs 2.0 currently installed.

    Returns:
        Version string (e.g., '2.1.0') or None if not detected
    """
    try:
        import flexlibs2

        # Try __version__ attribute
        if hasattr(flexlibs2, '__version__'):
            version = flexlibs2.__version__  # type: ignore
            operations_logger.debug(f"Detected FlexLibs 2.0 version: {version}")
            return version

        # Try getting from package metadata
        try:
            from importlib.metadata import version
            pkg_version = version('flexlibs2')
            operations_logger.debug(f"Detected FlexLibs 2.0 version from metadata: {pkg_version}")
            return pkg_version
        except Exception:
            pass

        operations_logger.debug("FlexLibs 2.0 installed but version not detected")
        return None
    except Exception as e:
        operations_logger.debug(f"Could not detect FlexLibs 2.0 version: {e}")
        return None


def get_installed_flexlibs_version() -> Optional[str]:
    """Detect the version of stable FlexLibs currently installed.

    Returns:
        Version string (e.g., '1.2.8') or None if not detected
    """
    try:
        import flexlibs  # type: ignore

        # Try __version__ attribute
        if hasattr(flexlibs, '__version__'):
            version = flexlibs.__version__  # type: ignore
            operations_logger.debug(f"Detected FlexLibs stable version: {version}")
            return version

        # Try getting from package metadata
        try:
            from importlib.metadata import version
            pkg_version = version('flexlibs')
            operations_logger.debug(f"Detected FlexLibs stable version from metadata: {pkg_version}")
            return pkg_version
        except Exception:
            pass

        operations_logger.debug("FlexLibs stable installed but version not detected")
        return None
    except Exception as e:
        operations_logger.debug(f"Could not detect FlexLibs version: {e}")
        return None


def find_latest_versioned_api_file(index_dir: Path, prefix: str) -> Optional[Path]:
    """Find the latest versioned API file for a library.

    Searches in both the main directory and archive subdirectories.

    Args:
        index_dir: Parent directory (e.g., index/liblcm or index/flexlibs)
        prefix: File prefix (e.g., 'liblcm_api', 'flexlibs2_api')

    Returns:
        Path to latest versioned file, or None if not found
    """
    if not index_dir.exists():
        return None

    import glob
    # Search in both main directory and archive subdirectory
    # Handle both patterns: underscore (liblcm_api_v*.json) and hyphen (casting_index_liblcm-v*.json)
    pattern_underscore = str(index_dir / f"{prefix}_v*.json")
    pattern_hyphen = str(index_dir / f"{prefix}-v*.json")
    files = glob.glob(pattern_underscore) + glob.glob(pattern_hyphen)

    archive_dir = index_dir / "archive"
    if archive_dir.exists():
        archive_pattern_underscore = str(archive_dir / f"{prefix}_v*.json")
        archive_pattern_hyphen = str(archive_dir / f"{prefix}-v*.json")
        files.extend(glob.glob(archive_pattern_underscore) + glob.glob(archive_pattern_hyphen))

    if not files:
        return None

    # Sort by version number (works for semantic versioning)
    def extract_version(filename: str) -> tuple:
        match = re.search(r'v(\d+)\.(\d+)\.(\d+)', filename)
        return tuple(map(int, match.groups())) if match else (0, 0, 0)

    files.sort(key=extract_version)
    return Path(files[-1]) if files else None


def find_versioned_api_file(index_dir: Path, prefix: str, target_version: str) -> Optional[Path]:
    """Find the API file matching a specific installed library version.

    Args:
        index_dir: Parent directory (e.g., index/liblcm or index/flexlibs)
        prefix: File prefix (e.g., 'liblcm_api', 'flexlibs2_api')
        target_version: Version to match (e.g., '11.0.0')

    Returns:
        Path to matching file, or None if not found
    """
    if not index_dir.exists():
        return None

    # Try exact match first in main directory (both underscore and hyphen patterns)
    exact_path_underscore = index_dir / f"{prefix}_v{target_version}.json"
    exact_path_hyphen = index_dir / f"{prefix}-v{target_version}.json"
    if exact_path_underscore.exists():
        operations_logger.info(f"Found exact version match: {prefix}_v{target_version}.json")
        return exact_path_underscore
    if exact_path_hyphen.exists():
        operations_logger.info(f"Found exact version match: {prefix}-v{target_version}.json")
        return exact_path_hyphen

    # Try archive directory (both patterns)
    archive_path_underscore = index_dir / "archive" / f"{prefix}_v{target_version}.json"
    archive_path_hyphen = index_dir / "archive" / f"{prefix}-v{target_version}.json"
    if archive_path_underscore.exists():
        operations_logger.info(f"Found exact version match in archive: {prefix}_v{target_version}.json")
        return archive_path_underscore
    if archive_path_hyphen.exists():
        operations_logger.info(f"Found exact version match in archive: {prefix}-v{target_version}.json")
        return archive_path_hyphen

    # If exact match not found, log and return None
    # (caller will decide whether to fall back to latest or auto-refresh)
    operations_logger.debug(f"No exact match found for {prefix} v{target_version}")
    return None


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
            operations_logger.error(f"Refresh script not found: {refresh_script}")
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

        operations_logger.info(f"Auto-refreshing {library_name} API index...")
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300
        )

        if result.returncode == 0:
            operations_logger.info(f"Successfully refreshed {library_name} API index")
            return True
        else:
            operations_logger.warning(f"Failed to refresh {library_name}: {result.stderr[:500]}")
            return False

    except Exception as e:
        operations_logger.warning(f"Could not auto-refresh {library_name}: {e}")
        return False


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all MCP tools, generated from Pydantic models in tool_definitions.py.

    Each tool is auto-generated from its corresponding Pydantic input model,
    which provides automatic validation and type coercion.
    """
    tools: list[Tool] = []
    for tool_def in TOOL_DEFINITIONS.values():
        tools.append(
            Tool(
                name=tool_def.name,
                description=tool_def.description,
                annotations=tool_def.annotations,
                inputSchema=model_to_tool_schema(tool_def.input_model),
            )
        )
    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    global api_index

    if api_index is None:
        api_index = APIIndex.load(get_index_dir())

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

    # Pre-load indexes
    print("[INFO] Loading API indexes...", file=sys.stderr)
    api_index = APIIndex.load(get_index_dir())

    if api_index.liblcm:
        print(f"[OK] LibLCM: {len(api_index.liblcm.get('entities', {}))} entities", file=__import__("sys").stderr)
    else:
        print("[WARN] LibLCM index not found", file=__import__("sys").stderr)

    if api_index.flexlibs2:
        print(f"[OK] FlexLibs 2.0: {len(api_index.flexlibs2.get('entities', {}))} entities", file=__import__("sys").stderr)
    else:
        print("[WARN] FlexLibs 2.0 index not found", file=__import__("sys").stderr)

    if api_index.casting_index:
        props = len(api_index.casting_index.get("properties", {}))
        colls = len(api_index.casting_index.get("polymorphic_collections", {}))
        print(f"[OK] Casting index: {props} properties, {colls} polymorphic collections", file=__import__("sys").stderr)
    else:
        print("[WARN] Casting index not found", file=__import__("sys").stderr)

    if api_index.flexlibs_stable:
        print(f"[OK] FlexLibs Stable: {len(api_index.flexlibs_stable.get('entities', {}))} entities", file=__import__("sys").stderr)
    else:
        print("[WARN] FlexLibs Stable index not found", file=__import__("sys").stderr)

    print("[INFO] Starting MCP server...", file=__import__("sys").stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
