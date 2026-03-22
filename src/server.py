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
from typing import Any, Optional, List, Dict
from dataclasses import dataclass, field
import io
from contextlib import redirect_stdout, redirect_stderr

# Suppress noisy third-party warnings and output
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
warnings.filterwarnings('ignore', message='.*position_ids.*')
warnings.filterwarnings('ignore', message='.*unauthenticated requests.*')

from mcp.server import Server

if __package__:
    from .json_utils import sort_json_arrays
if __package__:
    from .server.handlers.api import (
        handle_get_object_api,
        handle_search_by_capability,
        handle_find_examples,
        handle_resolve_property,
    )
if __package__:
    from .server.handlers.catalog import (
        handle_list_categories,
        handle_list_entities_in_category,
    )
if __package__:
    from .server.handlers.discovery import (
        handle_get_navigation_path,
    )
if __package__:
    from .server.handlers.admin import (
        handle_start,
        handle_manage_config,
        handle_get_session_history,
        handle_undo_last_operation,
        handle_get_module_template,
    )
if __package__:
    from .server.handlers.execution import (
        handle_start_module,
        handle_run_module,
        handle_run_operation,
        handle_get_operation_logs,
    )
else:
    from json_utils import sort_json_arrays
    from server.handlers.api import (
        handle_get_object_api,
        handle_search_by_capability,
        handle_find_examples,
        handle_resolve_property,
    )
    from server.handlers.catalog import (
        handle_list_categories,
        handle_list_entities_in_category,
    )
    from server.handlers.discovery import (
        handle_get_navigation_path,
    )
    from server.handlers.admin import (
        handle_start,
        handle_manage_config,
        handle_get_session_history,
        handle_undo_last_operation,
        handle_get_module_template,
    )
    from server.handlers.execution import (
        handle_start_module,
        handle_run_module,
        handle_run_operation,
        handle_get_operation_logs,
    )


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


# ============================================================
# Operation Logging System
# ============================================================

def get_log_dir() -> Path:
    """Get the log directory path (~/.flextoolsmcp/logs/)."""
    log_dir = Path.home() / ".flextoolsmcp" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging():
    """Configure file logging for operations."""
    log_dir = get_log_dir()
    log_file = log_dir / "operations.log"

    # Create a logger for operations
    logger = logging.getLogger("flextoolsmcp.operations")
    logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers
    if not logger.handlers:
        # File handler with rotation (max 5MB, keep 3 backups)
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)

        # Format: timestamp | level | message
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-7s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# Initialize the operations logger
operations_logger = setup_logging()


@dataclass
class PatternTracker:
    """Tracks API patterns with success/failure counts for learning."""
    patterns_file: Path = None
    patterns: Dict = field(default_factory=dict)

    def __post_init__(self):
        if self.patterns_file is None:
            self.patterns_file = get_log_dir() / "patterns.json"
        self.load()

    def load(self):
        """Load patterns from disk."""
        if self.patterns_file.exists():
            try:
                with open(self.patterns_file, 'r', encoding='utf-8') as f:
                    self.patterns = json.load(f)
            except Exception as e:
                operations_logger.warning(f"Failed to load patterns: {e}")
                self.patterns = {"api_patterns": {}, "error_patterns": {}}
        else:
            self.patterns = {"api_patterns": {}, "error_patterns": {}}

    def save(self):
        """Save patterns to disk."""
        try:
            patterns_to_save = sort_json_arrays(self.patterns)
            with open(self.patterns_file, 'w', encoding='utf-8') as f:
                json.dump(patterns_to_save, f, indent=2, ensure_ascii=False, sort_keys=True)
        except Exception as e:
            operations_logger.warning(f"Failed to save patterns: {e}")

    def extract_api_calls(self, code: str) -> List[str]:
        """Extract API method calls from code."""
        patterns = []
        # Match patterns like: ClassName(project).Method() or ops.Method()
        method_pattern = r'(\w+Operations)\s*\(\s*\w+\s*\)\s*\.\s*(\w+)'
        for match in re.finditer(method_pattern, code):
            patterns.append(f"{match.group(1)}.{match.group(2)}")

        # Match patterns like: project.MethodName()
        project_pattern = r'project\s*\.\s*(\w+)\s*\('
        for match in re.finditer(project_pattern, code):
            patterns.append(f"project.{match.group(1)}")

        # Match attribute access like: entry.SensesOS, sense.Gloss
        attr_pattern = r'(\w+)\s*\.\s*((?:[A-Z]\w*OS|[A-Z]\w*OC|[A-Z]\w*RS|[A-Z]\w*RC|Gloss\w*|Definition\w*|Headword|Form\w*))'
        for match in re.finditer(attr_pattern, code):
            patterns.append(f"*.{match.group(2)}")

        return list(set(patterns))  # Deduplicate

    def record_operation(self, code: str, success: bool, error_msg: str = None, error_type: str = None):
        """Record an operation's success or failure for pattern learning."""
        api_calls = self.extract_api_calls(code)

        for api_call in api_calls:
            if api_call not in self.patterns["api_patterns"]:
                self.patterns["api_patterns"][api_call] = {
                    "success_count": 0,
                    "failure_count": 0,
                    "last_used": None,
                    "common_errors": {}
                }

            pattern_data = self.patterns["api_patterns"][api_call]
            pattern_data["last_used"] = datetime.now().isoformat()

            if success:
                pattern_data["success_count"] += 1
            else:
                pattern_data["failure_count"] += 1
                if error_type:
                    if error_type not in pattern_data["common_errors"]:
                        pattern_data["common_errors"][error_type] = {"count": 0, "example": ""}
                    pattern_data["common_errors"][error_type]["count"] += 1
                    if error_msg:
                        pattern_data["common_errors"][error_type]["example"] = error_msg[:200]

        # Track error patterns for FlexLibs bug identification
        if not success and error_msg:
            error_key = self._normalize_error(error_msg)
            if error_key not in self.patterns["error_patterns"]:
                self.patterns["error_patterns"][error_key] = {
                    "count": 0,
                    "examples": [],
                    "api_calls": [],
                    "first_seen": datetime.now().isoformat(),
                    "potential_fix": None
                }

            err_pattern = self.patterns["error_patterns"][error_key]
            err_pattern["count"] += 1
            if len(err_pattern["examples"]) < 3:
                err_pattern["examples"].append({
                    "code": code[:500],
                    "error": error_msg[:500],
                    "timestamp": datetime.now().isoformat()
                })
            for api_call in api_calls:
                if api_call not in err_pattern["api_calls"]:
                    err_pattern["api_calls"].append(api_call)

        self.save()

    def _normalize_error(self, error_msg: str) -> str:
        """Normalize error message to group similar errors."""
        # Remove specific values, keep the pattern
        normalized = error_msg
        # Remove hex addresses
        normalized = re.sub(r'0x[0-9a-fA-F]+', '0x...', normalized)
        # Remove line numbers
        normalized = re.sub(r'line \d+', 'line N', normalized)
        # Remove specific object names in quotes
        normalized = re.sub(r"'[^']{20,}'", "'...'", normalized)
        # Take first 100 chars as key
        return normalized[:100]

    def get_recommendations(self) -> Dict:
        """Get pattern-based recommendations for API usage."""
        recommendations = {
            "preferred_patterns": [],
            "patterns_to_avoid": [],
            "common_errors_needing_fix": []
        }

        # Find high-success patterns
        for api_call, data in self.patterns.get("api_patterns", {}).items():
            total = data["success_count"] + data["failure_count"]
            if total >= 3:  # Need at least 3 uses to make a recommendation
                success_rate = data["success_count"] / total
                if success_rate >= 0.8:
                    recommendations["preferred_patterns"].append({
                        "pattern": api_call,
                        "success_rate": round(success_rate * 100, 1),
                        "uses": total
                    })
                elif success_rate <= 0.3:
                    recommendations["patterns_to_avoid"].append({
                        "pattern": api_call,
                        "success_rate": round(success_rate * 100, 1),
                        "uses": total,
                        "common_errors": list(data.get("common_errors", {}).keys())[:3]
                    })

        # Find recurring errors that need FlexLibs fixes
        for error_key, data in self.patterns.get("error_patterns", {}).items():
            if data["count"] >= 2:  # Recurring error
                recommendations["common_errors_needing_fix"].append({
                    "error_pattern": error_key,
                    "count": data["count"],
                    "affected_apis": data["api_calls"][:5],
                    "potential_fix": data.get("potential_fix")
                })

        # Sort by relevance
        recommendations["preferred_patterns"].sort(key=lambda x: -x["uses"])
        recommendations["patterns_to_avoid"].sort(key=lambda x: x["success_rate"])
        recommendations["common_errors_needing_fix"].sort(key=lambda x: -x["count"])

        return recommendations


# Global pattern tracker
pattern_tracker = PatternTracker()


# ============================================================
# Session State Management
# ============================================================

@dataclass
class SessionState:
    """Tracks session-wide settings to ensure consistency across tool calls.

    Set by the 'start' tool and respected by all other tools unless overridden.
    """
    api_mode: str = "flexlibs2"       # API mode: flexlibs2, flexlibs_stable, liblcm
    output_type: str = "auto"         # Output type: auto, operation, module
    project_name: str = ""            # FLEx project name (empty = prompt user)
    write_enabled: bool = False       # Write access: False = read-only/dry-run
    initialized: bool = False
    discovered_apis: set = None       # APIs discovered via search_by_capability
    validated_apis: set = None        # APIs validated via get_object_api (required before use)
    api_versions: dict = None         # Track active API versions: {api_name: version}

    def __init__(self):
        self.discovered_apis = set()
        self.validated_apis = set()
        self.api_versions = {}

    def configure(self, **kwargs) -> None:
        """Configure session settings (called by start tool)."""
        if "api_mode" in kwargs:
            self.api_mode = kwargs["api_mode"]
        if "output_type" in kwargs:
            self.output_type = kwargs["output_type"]
        if "project_name" in kwargs:
            self.project_name = kwargs["project_name"]
        if "write_enabled" in kwargs:
            self.write_enabled = kwargs["write_enabled"]
        if "api_versions" in kwargs:
            self.api_versions = kwargs["api_versions"]
        self.initialized = True
        mode_info = f"mode={self.api_mode}, output={self.output_type}"
        mode_info += f", project={self.project_name or '(prompt)'}"
        mode_info += f", write={self.write_enabled}"
        if self.api_versions:
            versions_str = ", ".join(f"{k}={v}" for k, v in sorted(self.api_versions.items()))
            mode_info += f", versions={{{versions_str}}}"
        operations_logger.info(f"Session configured: {mode_info}")

    def record_discovered_api(self, entity: str, method: str) -> None:
        """Record an API that was discovered via get_object_api or search_by_capability."""
        api_key = f"{entity}.{method}" if entity else method
        self.discovered_apis.add(api_key)

    def get_discovered_apis(self) -> set:
        """Get the set of discovered API methods."""
        return self.discovered_apis

    def was_api_discovered(self, entity: str, method: str) -> bool:
        """Check if a specific API was discovered."""
        api_key = f"{entity}.{method}" if entity else method
        # Also check just the method name for flexibility
        return api_key in self.discovered_apis or method in self.discovered_apis

    def clear_discovered_apis(self) -> None:
        """Clear discovered APIs (for new session)."""
        self.discovered_apis = set()
        self.validated_apis = set()

    def record_validated_api(self, entity: str) -> None:
        """Record an API that was validated via get_object_api."""
        self.validated_apis.add(entity)

    def get_unvalidated_apis(self) -> set:
        """Get APIs discovered but not yet validated via get_object_api."""
        return self.discovered_apis - self.validated_apis

    def get_mode(self) -> str:
        """Get the current session API mode."""
        return self.api_mode

    def get_output_type(self) -> str:
        """Get the current session output type."""
        return self.output_type

    def get_project(self) -> str:
        """Get the current session project name (empty if not set)."""
        return self.project_name

    def is_write_enabled(self) -> bool:
        """Get whether write access is enabled for the session."""
        return self.write_enabled
    def summary(self) -> dict:
        """Return session state summary for tool responses."""
        result = {
            "api_mode": self.api_mode,
            "output_type": self.output_type,
            "project_name": self.project_name or "(not set)",
            "write_enabled": self.write_enabled,
            "initialized": self.initialized,
            "discovered_api_count": len(self.discovered_apis)
        }
        return result


# Global session state
session_state = SessionState()


# Helper validation functions were extracted to validators module
# Import them at the top if needed for use in server.py
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    CallToolResult,
)

# Optional imports for semantic search
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
    liblcm: dict = None
    flexlibs2: dict = None
    flexlibs_stable: dict = None
    navigation_graph: dict = None
    casting_index: dict = None
    semantic_search: SemanticSearch = None

    # Track loaded API versions for session logging
    liblcm_version: str = None
    flexlibs2_version: str = None
    flexlibs_stable_version: str = None

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
        clr.AddReference('SIL.LCModel')

        # Get version from assembly metadata
        try:
            import System
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
            version = flexlibs2.__version__
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
        import flexlibs

        # Try __version__ attribute
        if hasattr(flexlibs, '__version__'):
            version = flexlibs.__version__
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
    files.sort(key=lambda x: tuple(map(int, re.search(r'v(\d+)\.(\d+)\.(\d+)', x).groups())))
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
    """List available tools."""
    return [
        Tool(
            name="start",
            description="""[WORKFLOW - BEGIN HERE] Initialize the FlexTools MCP session.

REQUIRED: Sets api_mode to determine which API (flexlibs2, flexlibs_stable, or liblcm) to use.
OPTIONAL: task description for initial API discovery, project_name for operations, etc.

After calling start():
- Use search_by_capability(query='...') for API discovery
- Use get_object_api(object_type='...') for detailed API info
- Use run_operation() or run_module() to execute code against a FieldWorks project

Task and project_name can be set now or updated/provided later as needed.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "api_mode": {
                        "type": "string",
                        "enum": ["flexlibs2", "flexlibs_stable", "liblcm"],
                        "description": "API mode - REQUIRED: 'flexlibs2' (recommended, ~1400 methods), 'flexlibs_stable' (legacy ~71 methods), 'liblcm' (raw C# API). Defaults to flexlibs2."
                    },
                    "task": {
                        "type": "string",
                        "description": "Optional: Task/goal description in natural language (e.g., 'delete senses with test in gloss', 'count entries by part of speech'). Can be provided now or discovered organically later."
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Optional: FLEx project name for run_operation()/run_module(). Can be set now or provided when executing."
                    },
                    "output_type": {
                        "type": "string",
                        "enum": ["auto", "operation", "module"],
                        "description": "Optional: Output type - 'auto' (default, picks based on complexity), 'operation' (quick one-off), 'module' (reusable script)"
                    },
                    "write_enabled": {
                        "type": "boolean",
                        "description": "Enable write access. Default is False (dry-run/read-only). Set True only after testing!",
                        "default": False
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="get_object_api",
            description="[WORKFLOW STEP 3] Get detailed API documentation for an object. Use AFTER search_by_capability to validate and understand the APIs you want to use.\n\nWARNING: Calling get_object_api is required BEFORE using an API in run_operation/run_module. This ensures you have full context of the signature and behavior, reducing debugging.\n\nIMPORTANT: Each API result includes 'import_statement' showing exactly what to add at the top of your code. When you use LexEntryOperations, LexSenseOperations, or any Operations class in your code, you MUST include the import statement shown in the API response.\n\nTip: Use summary_only=true first to explore large objects, then drill down into specific methods.",
            inputSchema={
                "type": "object",
                "properties": {
                    "object_type": {
                        "type": "string",
                        "description": "The object type to look up (e.g., 'ILexEntry', 'LexEntryOperations', 'ILexSense')"
                    },
                    "include_flexlibs2": {
                        "type": "boolean",
                        "description": "Include FlexLibs 2.0 wrapper methods (default: true)",
                        "default": True
                    },
                    "include_liblcm": {
                        "type": "boolean",
                        "description": "Include raw LibLCM interface info (default: true)",
                        "default": True
                    },
                    "summary_only": {
                        "type": "boolean",
                        "description": "Return only method/property names without full details (default: false). Use this first to explore large objects.",
                        "default": False
                    },
                    "method_filter": {
                        "type": "string",
                        "description": "Filter to methods containing this substring (case-insensitive)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of methods to return (default: 50)",
                        "default": 50
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Number of methods to skip for pagination (default: 0)",
                        "default": 0
                    }
                },
                "required": ["object_type"]
            }
        ),
        Tool(
            name="search_by_capability",
            description="[WORKFLOW STEP 2] Search for methods/functions by capability. Returns multiple options. Use natural language queries like 'add gloss to sense', 'create new entry', 'get all entries'.\n\nRECOMMENDED WORKFLOW:\n1. search_by_capability() - discover options (may find more than you'll use)\n2. Review results, choose which APIs you actually need\n3. get_object_api() - for each API you selected, get full details (includes import_statement)\n4. IMPORTANT: When writing code, include ALL import statements shown in API results\n5. Write code using the validated APIs\n6. run_operation() or run_module() - execute with full context\n\nNote: API results include 'import_statement' field—this MUST be in your code.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language description of what you want to do"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 10)",
                        "default": 10
                    },
                    "api_mode": {
                        "type": "string",
                        "enum": ["flexlibs2", "flexlibs_stable", "liblcm", "all"],
                        "description": "API mode: 'flexlibs2' (default, recommended), 'flexlibs_stable' (legacy + LibLCM fallback), 'liblcm' (raw C# only), 'all' (search everything)",
                        "default": "flexlibs2"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_navigation_path",
            description="[WORKFLOW STEP 2] Find how to navigate between object types in the FieldWorks data model. Example: ILexEntry -> ILexSense -> ILexExampleSentence. Call this after search_by_capability to understand how to traverse the data model.",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_object": {
                        "type": "string",
                        "description": "Starting object type (e.g., 'ILexEntry')"
                    },
                    "to_object": {
                        "type": "string",
                        "description": "Target object type (e.g., 'ILexExampleSentence')"
                    }
                },
                "required": ["from_object", "to_object"]
            }
        ),
        Tool(
            name="find_examples",
            description="[WORKFLOW STEP 5] Find code examples for a method or operation type (create, read, update, delete). Use before writing code to see proven patterns. Examples come from FlexLibs2 with 82% coverage.",
            inputSchema={
                "type": "object",
                "properties": {
                    "method_name": {
                        "type": "string",
                        "description": "Specific method name to find examples for"
                    },
                    "operation_type": {
                        "type": "string",
                        "enum": ["create", "read", "update", "delete", "iterate", "search"],
                        "description": "Type of operation to find examples for"
                    },
                    "object_type": {
                        "type": "string",
                        "description": "Object type to filter examples (e.g., 'LexEntry', 'Sense')"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of examples to return (default: 5)",
                        "default": 5
                    }
                }
            }
        ),
        Tool(
            name="list_categories",
            description="List all available API categories (lexicon, grammar, texts, etc.) with their entity counts.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="list_entities_in_category",
            description="List all entities (classes/interfaces) in a specific category.",
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Category name (e.g., 'lexicon', 'grammar', 'texts')"
                    }
                },
                "required": ["category"]
            }
        ),
        Tool(
            name="get_module_template",
            description="[WORKFLOW - REQUIRED BEFORE RUN_MODULE] Get the official FlexTools module template. Must call this to get boilerplate before submitting code to run_module. After discovery (search_by_capability, get_navigation_path, get_object_api, etc.), call this with module_name and synopsis to get properly structured template.",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_name": {
                        "type": "string",
                        "description": "Name for the new module (e.g., 'Export Custom Data')"
                    },
                    "synopsis": {
                        "type": "string",
                        "description": "Short description of what the module does"
                    },
                    "modifies_db": {
                        "type": "boolean",
                        "description": "Whether the module modifies the database (default: false)",
                        "default": False
                    }
                }
            }
        ),
        Tool(
            name="start_module",
            description="Interactive wizard to start creating a new FlexTools module. Checks Python version, gathers requirements, and generates a customized template with appropriate boilerplate code. Call with no arguments to get the list of questions, or provide answers to generate the template.",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_name": {
                        "type": "string",
                        "description": "Name for the new module"
                    },
                    "synopsis": {
                        "type": "string",
                        "description": "Short description of what the module does"
                    },
                    "api_target": {
                        "type": "string",
                        "enum": ["flexlibs2", "flexlibs_stable", "liblcm"],
                        "description": "Target API: 'flexlibs2' (recommended, Python wrappers), 'flexlibs_stable' (legacy wrappers), or 'liblcm' (raw C# via pythonnet)"
                    },
                    "modifies_db": {
                        "type": "boolean",
                        "description": "Whether the module modifies the database"
                    },
                    "domain": {
                        "type": "string",
                        "enum": ["lexicon", "grammar", "texts", "media", "general"],
                        "description": "Primary domain the module works with"
                    },
                    "include_dry_run": {
                        "type": "boolean",
                        "description": "Include DRY_RUN safety mode for write operations"
                    }
                }
            }
        ),
        Tool(
            name="run_module",
            description="[WORKFLOW STEP 6 - EXECUTE] Execute a FlexTools module against a FieldWorks project. PREREQUISITE: Code must be in FlexTools module format with def Main(project, report, modifyAllowed), FlexToolsModuleClass, from flextoolslib import, and docs dict. Use get_module_template to get the proper boilerplate. ALWAYS test with write_enabled=False first. Backup before write_enabled=True.",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_code": {
                        "type": "string",
                        "description": "The complete FlexTools module Python code to execute"
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Name of the FieldWorks project. Uses session value if set by start(), otherwise required."
                    },
                    "write_enabled": {
                        "type": "boolean",
                        "description": "Enable write access. Uses session value if set by start(). Default: False (dry-run)."
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Maximum execution time in seconds (default: 300)",
                        "default": 300
                    },
                    "show_code": {
                        "type": "boolean",
                        "description": "Include full module code in response for learning (default: true)",
                        "default": True
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "Required for CUD operations. Set True to confirm you understand the risks of Create/Update/Delete.",
                        "default": False
                    }
                },
                "required": ["module_code"]
            }
        ),
        Tool(
            name="get_operation_logs",
            description="View operation logs and pattern recommendations. Shows recent failures, common error patterns, and API usage recommendations based on success/failure tracking.",
            inputSchema={
                "type": "object",
                "properties": {
                    "log_lines": {
                        "type": "integer",
                        "description": "Number of recent log lines to return (default: 50)",
                        "default": 50
                    },
                    "include_patterns": {
                        "type": "boolean",
                        "description": "Include pattern analysis and recommendations (default: true)",
                        "default": True
                    },
                    "errors_only": {
                        "type": "boolean",
                        "description": "Only show error entries in logs (default: false)",
                        "default": False
                    }
                }
            }
        ),
        Tool(
            name="run_operation",
            description="""[WORKFLOW STEP 6 - EXECUTE] Execute FlexLibs2 operations directly against a FieldWorks project.

PREREQUISITE WORKFLOW - Do these steps FIRST:
1. search_by_capability - Find the right functions
2. get_navigation_path - Understand object traversal
3. get_object_api - Get API details
4. resolve_property - Check for casting requirements
5. find_examples - Get code patterns

Skipping these steps often leads to: wrong functions, runtime errors, data corruption.

Available: project, report, write_enabled, safe_str(), is_empty_multistring()
Auto-imported: All flexlibs2 Operations classes, FLExProject, FP_* exceptions

ALWAYS run with write_enabled=False first (dry-run). Backup before write_enabled=True.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "operations": {
                        "type": "string",
                        "description": "Python code to execute. Has access to 'project', 'report', 'write_enabled'. All flexlibs2 Operations classes are pre-imported."
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Name of the FieldWorks project. Uses session value if set by start(), otherwise required."
                    },
                    "write_enabled": {
                        "type": "boolean",
                        "description": "Enable write access. Uses session value if set by start(). Default: False (dry-run)."
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": "Maximum execution time in seconds (default: 120)",
                        "default": 120
                    },
                    "show_code": {
                        "type": "boolean",
                        "description": "Include executed code in response for learning (default: true)",
                        "default": True
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "Required for CUD operations. Set True to confirm you understand the risks of Create/Update/Delete.",
                        "default": False
                    }
                },
                "required": ["operations"]
            }
        ),
        Tool(
            name="resolve_property",
            description="[WORKFLOW STEP 4] Resolve property names and check pythonnet casting requirements. CRITICAL: Call this before accessing properties like PartOfSpeechRA to avoid runtime errors. Returns casting warnings and FlexLibs2 helper functions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "property_name": {
                        "type": "string",
                        "description": "Property name to resolve (e.g., 'Senses', 'PartOfSpeechRA', 'Entries')"
                    },
                    "context_entity": {
                        "type": "string",
                        "description": "Optional entity context for disambiguation (e.g., 'ILexEntry', 'IMoMorphSynAnalysis')"
                    },
                    "include_casting_info": {
                        "type": "boolean",
                        "description": "Include pythonnet casting requirements (default: true)",
                        "default": True
                    }
                },
                "required": ["property_name"]
            }
        ),
        Tool(
            name="manage_config",
            description="Get, set, delete, or list persistent configuration values for FlexToolsMCP.",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["get", "set", "delete", "list"],
                        "description": "Configuration action to perform"
                    },
                    "key": {
                        "type": "string",
                        "description": "Dotted key (e.g., 'paths.flexlibs2') for get/set/delete actions"
                    },
                    "value": {
                        "description": "Value to set (required for 'set' action)"
                    }
                },
                "required": ["action"]
            }
        ),
        Tool(
            name="get_session_history",
            description="View this session's operation history and undo/redo availability.",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_operations": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include full list of operations in response"
                    }
                }
            }
        ),
        Tool(
            name="undo_last_operation",
            description="Undo the most recent database write operation. Uses FLEx ActionHandler.Undo().",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    global api_index

    if api_index is None:
        api_index = APIIndex.load(get_index_dir())

    # start() is the only tool that doesn't require initialization
    # All other discovery/execution tools require calling start() first
    if name != "start" and not session_state.initialized:
        return [TextContent(type="text", text=json.dumps({
            "error": "Session not initialized",
            "message": "You must call start() first to initialize the session and set the API mode.",
            "hint": "Call start(task='your task description') to begin. This will discover relevant APIs and configure the session.",
            "available_task_examples": [
                "Add gloss to sense definitions",
                "Delete senses with test in gloss",
                "Count entries by part of speech",
                "Create new lexical entries"
            ]
        }, indent=2))]

    if name == "start":
        return await handle_start(arguments)
    elif name == "get_object_api":
        return await handle_get_object_api(arguments)
    elif name == "search_by_capability":
        return await handle_search_by_capability(arguments)
    elif name == "get_navigation_path":
        return await handle_get_navigation_path(arguments)
    elif name == "find_examples":
        return await handle_find_examples(arguments)
    elif name == "list_categories":
        return await handle_list_categories(arguments)
    elif name == "list_entities_in_category":
        return await handle_list_entities_in_category(arguments)
    elif name == "get_module_template":
        return await handle_get_module_template(arguments)
    elif name == "start_module":
        return await handle_start_module(arguments)
    elif name == "run_module":
        return await handle_run_module(arguments)
    elif name == "run_operation":
        return await handle_run_operation(arguments)
    elif name == "get_operation_logs":
        return await handle_get_operation_logs(arguments)
    elif name == "resolve_property":
        return await handle_resolve_property(arguments)
    elif name == "manage_config":
        return await handle_manage_config(arguments)
    elif name == "get_session_history":
        return await handle_get_session_history(arguments)
    elif name == "undo_last_operation":
        return await handle_undo_last_operation(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    """Run the MCP server."""
    global api_index

    # Pre-load indexes
    print("[INFO] Loading API indexes...", file=__import__("sys").stderr)
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
