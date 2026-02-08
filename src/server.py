#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FlexTools MCP Server

An MCP server that provides AI assistants with searchable documentation
of the LibLCM and FlexLibs APIs for generating FlexTools scripts.
"""

import json
import asyncio
import sys
import subprocess
import tempfile
import os
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Optional, List, Dict
from dataclasses import dataclass, field

from mcp.server import Server


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
            with open(self.patterns_file, 'w', encoding='utf-8') as f:
                json.dump(self.patterns, f, indent=2, ensure_ascii=False)
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
    semantic_search: SemanticSearch = None

    @classmethod
    def load(cls, index_dir: Path) -> "APIIndex":
        """Load all API indexes from the index directory."""
        index = cls()

        # Load LibLCM
        liblcm_path = index_dir / "liblcm" / "liblcm_api.json"
        if liblcm_path.exists():
            with open(liblcm_path, "r", encoding="utf-8") as f:
                index.liblcm = json.load(f)

        # Load FlexLibs 2.0
        flexlibs2_path = index_dir / "flexlibs" / "flexlibs2_api.json"
        if flexlibs2_path.exists():
            with open(flexlibs2_path, "r", encoding="utf-8") as f:
                index.flexlibs2 = json.load(f)

        # Load FlexLibs Stable
        flexlibs_stable_path = index_dir / "flexlibs" / "flexlibs_api.json"
        if flexlibs_stable_path.exists():
            with open(flexlibs_stable_path, "r", encoding="utf-8") as f:
                index.flexlibs_stable = json.load(f)

        # Load navigation graph
        nav_graph_path = index_dir / "navigation_graph.json"
        if nav_graph_path.exists():
            with open(nav_graph_path, "r", encoding="utf-8") as f:
                index.navigation_graph = json.load(f)

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


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="get_object_api",
            description="Get methods and properties for a FlexTools/LibLCM object like ILexEntry, LexSenseOperations, etc. Use summary_only=true first to see available methods, then request specific methods by name.",
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
            description="Search for methods/functions by what they do. Use natural language queries like 'add gloss to sense', 'create new entry', 'get all entries'. Supports different API modes with fallback behavior.",
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
                        "description": "API mode: 'flexlibs2' (recommended, searches FlexLibs 2.0 primarily), 'flexlibs_stable' (searches stable API with LibLCM fallback), 'liblcm' (raw C# API only), 'all' (search everything). Default: 'all'",
                        "default": "all"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_navigation_path",
            description="Find how to navigate from one object type to another in the FieldWorks data model. For example, how to get from ILexEntry to ILexExampleSentence.",
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
            description="Find code examples for a specific method or operation type.",
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
            description="Get the official FlexTools module template for creating new FlexTools scripts. Returns a ready-to-use Python template with the correct structure, imports, and documentation format.",
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
            description="Execute a FlexTools module against a FieldWorks project using FlexLibs directly. Returns the execution log. Defaults to DRY_RUN mode (read-only) for safety. IMPORTANT: Always backup your project before running with write_enabled=True.",
            inputSchema={
                "type": "object",
                "properties": {
                    "module_code": {
                        "type": "string",
                        "description": "The complete FlexTools module Python code to execute"
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Name of the FieldWorks project to open (e.g., 'Sena 3')"
                    },
                    "write_enabled": {
                        "type": "boolean",
                        "description": "Enable write access to the database. Default is False (read-only/dry-run mode). WARNING: Set to True only after testing!",
                        "default": False
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
                    }
                },
                "required": ["module_code", "project_name"]
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
            description="""Execute FlexLibs2 operations directly against a FieldWorks project without module boilerplate.

Simpler than run_module - just provide the operation code. Common imports (flexlibs2 Operations classes) are auto-available.

Available variables in your code:
- project: The FLExProject instance
- report: Reporter with .Info(), .Warning(), .Error() methods
- write_enabled: Boolean indicating if writes are allowed
- safe_str(obj): Helper to safely convert .NET strings to UTF-8 (handles special characters)

Available imports (auto-imported):
- All flexlibs2 Operations classes (LexEntryOperations, EnvironmentOperations, etc.)
- FLExProject, FP_* exceptions

Example operations:
- "envOps = EnvironmentOperations(project); envOps.Delete(envOps.GetAll()[0])"
- "for entry in LexEntryOperations(project).GetAll(): report.Info(safe_str(project.LexiconGetHeadword(entry)))"

Defaults to DRY_RUN mode. Always backup before write_enabled=True.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "operations": {
                        "type": "string",
                        "description": "Python code to execute. Has access to 'project', 'report', 'write_enabled'. All flexlibs2 Operations classes are pre-imported."
                    },
                    "project_name": {
                        "type": "string",
                        "description": "Name of the FieldWorks project to open (e.g., 'Sena 3')"
                    },
                    "write_enabled": {
                        "type": "boolean",
                        "description": "Enable write access. Default is False (dry-run mode).",
                        "default": False
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
                    }
                },
                "required": ["operations", "project_name"]
            }
        ),
        Tool(
            name="resolve_property",
            description="Resolve a pythonic (suffix-free) property name to its LibLCM equivalent(s). LibLCM uses suffixes (OA, OS, OC, RA, RS, RC) to indicate relationship types. This tool maps friendly names like 'Senses' to their actual API names like 'SensesOS'.",
            inputSchema={
                "type": "object",
                "properties": {
                    "property_name": {
                        "type": "string",
                        "description": "Property name to resolve (e.g., 'Senses', 'SensesOS', 'Entries')"
                    },
                    "context_entity": {
                        "type": "string",
                        "description": "Optional entity context for disambiguation (e.g., 'ILexEntry', 'ILexSense')"
                    }
                },
                "required": ["property_name"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    global api_index

    if api_index is None:
        api_index = APIIndex.load(get_index_dir())

    if name == "get_object_api":
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
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


def paginate_entity(entity: dict, summary_only: bool, method_filter: str, limit: int, offset: int) -> dict:
    """Apply pagination and filtering to an entity's methods."""
    result = {
        "category": entity.get("category"),
        "summary": entity.get("summary", ""),
        "source_file": entity.get("source_file", ""),
    }

    methods = entity.get("methods", [])

    # Apply method filter
    if method_filter:
        filter_lower = method_filter.lower()
        methods = [m for m in methods if filter_lower in m.get("name", "").lower()]

    total_methods = len(methods)
    result["total_methods"] = total_methods

    # Apply pagination
    methods = methods[offset:offset + limit]

    if summary_only:
        # Return just names and signatures
        result["methods"] = [
            {"name": m.get("name"), "signature": m.get("signature", "")}
            for m in methods
        ]
    else:
        result["methods"] = methods

    result["returned_methods"] = len(result["methods"])
    result["has_more"] = (offset + limit) < total_methods
    if result["has_more"]:
        result["next_offset"] = offset + limit

    return result


async def handle_get_object_api(args: dict) -> list[TextContent]:
    """Get API documentation for a specific object type."""
    object_type = args["object_type"]
    include_flexlibs2 = args.get("include_flexlibs2", True)
    include_liblcm = args.get("include_liblcm", True)
    summary_only = args.get("summary_only", False)
    method_filter = args.get("method_filter", "")
    limit = args.get("limit", 50)
    offset = args.get("offset", 0)

    result = {"object_type": object_type, "found": False}

    # Search in FlexLibs 2.0
    if include_flexlibs2 and api_index.flexlibs2:
        entities = api_index.flexlibs2.get("entities", {})
        # Try exact match first
        if object_type in entities:
            result["flexlibs2"] = paginate_entity(
                entities[object_type], summary_only, method_filter, limit, offset
            )
            result["found"] = True
        else:
            # Try partial match (e.g., "LexEntry" matches "LexEntryOperations")
            for name, entity in entities.items():
                if object_type.lower() in name.lower():
                    if "flexlibs2_matches" not in result:
                        result["flexlibs2_matches"] = []
                    result["flexlibs2_matches"].append({
                        "name": name,
                        "category": entity.get("category"),
                        "methods_count": len(entity.get("methods", []))
                    })
                    result["found"] = True

    # Search in LibLCM
    if include_liblcm and api_index.liblcm:
        entities = api_index.liblcm.get("entities", {})
        if object_type in entities:
            result["liblcm"] = paginate_entity(
                entities[object_type], summary_only, method_filter, limit, offset
            )
            result["found"] = True
        else:
            # Try partial match
            for name, entity in entities.items():
                if object_type.lower() in name.lower():
                    if "liblcm_matches" not in result:
                        result["liblcm_matches"] = []
                    result["liblcm_matches"].append({
                        "name": name,
                        "type": entity.get("type"),
                        "category": entity.get("category")
                    })
                    if len(result.get("liblcm_matches", [])) >= 10:
                        break
                    result["found"] = True

    if not result["found"]:
        result["message"] = f"No API documentation found for '{object_type}'. Try searching with search_by_capability or list_categories to explore available APIs."

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def handle_search_by_capability(args: dict) -> list[TextContent]:
    """Search for methods by capability description with API mode support."""
    query = args["query"]
    max_results = args.get("max_results", 10)
    api_mode = args.get("api_mode", "all")
    use_semantic = args.get("semantic", True)

    # Domain-specific synonyms: map linguistics terms to API terms
    # Applied BEFORE search to expand the query
    domain_synonyms = {
        # Parts of speech -> API terms
        "noun": "part of speech POS grammatical category",
        "verb": "part of speech POS grammatical category",
        "adjective": "part of speech POS grammatical category",
        "adverb": "part of speech POS grammatical category",
        "pronoun": "part of speech POS grammatical category",
        "preposition": "part of speech POS grammatical category",
        # Common linguistics terms
        "pos": "part of speech grammatical category",
        "category": "grammatical category part of speech",
        "lemma": "headword citation form lexeme entry",
        "morpheme": "morph allomorph form",
        "affix": "prefix suffix infix circumfix",
        "stem": "root base form",
        "inflection": "inflectional paradigm conjugation declension",
        "derivation": "derivational affix",
        # Data terms
        "translation": "gloss definition meaning",
        "meaning": "gloss definition sense",
        "example": "sentence illustration",
        "pronunciation": "phonetic phonology",
        "etymology": "origin history borrowed",
        "domain": "semantic domain category field",
        "usage": "register style sociolinguistic",
    }

    # Expand query with domain synonyms
    query_lower = query.lower()
    expanded_query = query
    for term, expansion in domain_synonyms.items():
        if term in query_lower:
            expanded_query = f"{query} {expansion}"
            break  # Apply first match only to avoid over-expansion

    results = []
    search_method = "keyword"
    sources_searched = []
    fallback_used = False

    # Define which sources to search based on api_mode
    # Each mode has primary sources and optional fallback sources
    mode_config = {
        "flexlibs2": {
            "primary": ["flexlibs2"],
            "fallback": [],  # FlexLibs 2.0 is comprehensive, rarely needs fallback
            "description": "FlexLibs 2.0 (recommended)"
        },
        "flexlibs_stable": {
            "primary": ["flexlibs_stable"],
            "fallback": ["liblcm"],  # Fall back to LibLCM for uncovered functionality
            "description": "FlexLibs Stable with LibLCM fallback"
        },
        "liblcm": {
            "primary": ["liblcm"],
            "fallback": [],
            "description": "Pure LibLCM"
        },
        "all": {
            "primary": ["flexlibs2", "flexlibs_stable", "liblcm"],
            "fallback": [],
            "description": "All sources"
        }
    }

    config = mode_config.get(api_mode, mode_config["all"])

    # Try semantic search first if available
    if use_semantic and api_index.semantic_search and api_index.semantic_search.enabled:
        # For semantic search, map api_mode to source filter
        semantic_source = api_mode if api_mode in ["flexlibs2", "liblcm"] else "all"
        # Use expanded query to include domain synonyms
        semantic_results = api_index.semantic_search.search(expanded_query, max_results, semantic_source)
        if semantic_results:
            results = semantic_results
            search_method = "semantic"
            sources_searched = [api_mode]

    # Fall back to keyword search
    if not results:
        query_lower = query.lower()

        # Synonym expansion for common operations
        synonyms = {
            # Operations
            "add": ["add", "set", "create", "insert", "append"],
            "set": ["set", "add", "update", "modify", "assign"],
            "get": ["get", "fetch", "retrieve", "find", "read"],
            "delete": ["delete", "remove", "clear", "erase"],
            "remove": ["remove", "delete", "clear"],
            "create": ["create", "add", "new", "make"],
            "update": ["update", "set", "modify", "change"],
            "find": ["find", "search", "get", "lookup", "query"],
            "list": ["list", "getall", "all", "iterate", "enumerate"],
            # Lexicon terms
            "gloss": ["gloss", "translation", "meaning"],
            "definition": ["definition", "meaning", "description"],
            "sense": ["sense", "meaning", "definition"],
            "entry": ["entry", "headword", "lexeme", "word"],
            # Parts of speech - map to API terms
            "noun": ["noun", "pos", "partofspeech", "grammatical", "category"],
            "verb": ["verb", "pos", "partofspeech", "grammatical", "category"],
            "adjective": ["adjective", "pos", "partofspeech", "grammatical", "category"],
            "adverb": ["adverb", "pos", "partofspeech", "grammatical", "category"],
            "pos": ["pos", "partofspeech", "grammatical", "category", "speech"],
            # Other linguistics terms
            "lemma": ["lemma", "headword", "citation", "lexeme"],
            "morpheme": ["morpheme", "morph", "allomorph", "form"],
            "stem": ["stem", "root", "base"],
            "affix": ["affix", "prefix", "suffix", "infix"],
        }

        # Expand query terms with synonyms
        query_terms = query_lower.split()
        expanded_terms = set(query_terms)
        for term in query_terms:
            if term in synonyms:
                expanded_terms.update(synonyms[term])

        # Expand pythonic names to suffixed equivalents (e.g., "senses" -> "sensesos")
        # This allows searching for "Senses" to find "SensesOS"
        suffix_index = api_index.liblcm.get("suffix_index", {}) if api_index.liblcm else {}
        by_pythonic = suffix_index.get("by_pythonic_name", {})
        pythonic_expansions = set()
        for term in list(expanded_terms):
            # Check if term matches a pythonic name (case-insensitive)
            for pythonic_name, matches in by_pythonic.items():
                if pythonic_name.lower() == term:
                    # Add all suffixed variants
                    for match in matches:
                        pythonic_expansions.add(match["full_name"].lower())
        expanded_terms.update(pythonic_expansions)

        def search_source(source_name, index_data, boost=0):
            """Search a single source and return results."""
            source_results = []
            if not index_data:
                return source_results

            for entity_name, entity in index_data.get("entities", {}).items():
                # Search methods
                for method in entity.get("methods", []):
                    score = boost  # Mode-based boost
                    text_to_search = "{} {} {}".format(
                        method.get('name', ''),
                        method.get('description', ''),
                        method.get('summary', '')
                    ).lower()

                    for term in expanded_terms:
                        if term in text_to_search:
                            score += 1
                        if term in method.get('name', '').lower():
                            score += 2

                    if score > boost:  # Only include if actual matches found
                        source_results.append({
                            "score": score,
                            "source": source_name,
                            "entity": entity_name,
                            "name": method.get("name"),
                            "type": "method",
                            "signature": method.get("signature"),
                            "description": method.get("summary", method.get("description", ""))[:150],
                            "category": entity.get("category", "general"),
                        })

                # Search properties (LibLCM only, for pythonic name matching)
                if source_name == "liblcm":
                    for prop in entity.get("properties", []):
                        score = boost
                        prop_name = prop.get('name', '')
                        pythonic_name = prop.get('pythonic_name', prop_name)
                        text_to_search = "{} {} {} {}".format(
                            prop_name,
                            pythonic_name,
                            prop.get('description', ''),
                            prop.get('kind', '')
                        ).lower()

                        for term in expanded_terms:
                            if term in text_to_search:
                                score += 1
                            if term == prop_name.lower() or term == pythonic_name.lower():
                                score += 3  # Exact property name match gets higher boost

                        if score > boost:
                            source_results.append({
                                "score": score,
                                "source": source_name,
                                "entity": entity_name,
                                "name": prop_name,
                                "pythonic_name": pythonic_name if pythonic_name != prop_name else None,
                                "type": "property",
                                "kind": prop.get("kind"),
                                "target_type": prop.get("target_type"),
                                "description": prop.get("description", "")[:150],
                                "category": entity.get("category", "general"),
                            })
            return source_results

        # Search primary sources with boost
        for source in config["primary"]:
            if source == "flexlibs2" and api_index.flexlibs2:
                results.extend(search_source("flexlibs2", api_index.flexlibs2, boost=5))
                sources_searched.append("flexlibs2")
            elif source == "flexlibs_stable" and api_index.flexlibs_stable:
                results.extend(search_source("flexlibs_stable", api_index.flexlibs_stable, boost=3))
                sources_searched.append("flexlibs_stable")
            elif source == "liblcm" and api_index.liblcm:
                results.extend(search_source("liblcm", api_index.liblcm, boost=0))
                sources_searched.append("liblcm")

        # If not enough results, try fallback sources
        if len(results) < max_results and config["fallback"]:
            for source in config["fallback"]:
                if source == "liblcm" and api_index.liblcm and "liblcm" not in sources_searched:
                    fallback_results = search_source("liblcm", api_index.liblcm, boost=0)
                    results.extend(fallback_results)
                    if fallback_results:
                        sources_searched.append("liblcm (fallback)")
                        fallback_used = True

        # Sort by score and limit results
        results.sort(key=lambda x: x["score"], reverse=True)
        results = results[:max_results]

    return [TextContent(type="text", text=json.dumps({
        "query": query,
        "api_mode": api_mode,
        "api_mode_description": config["description"],
        "search_method": search_method,
        "sources_searched": sources_searched,
        "fallback_used": fallback_used,
        "semantic_available": api_index.semantic_search.enabled if api_index.semantic_search else False,
        "results_count": len(results),
        "results": results
    }, indent=2))]


def normalize_object_name(name: str) -> str:
    """Normalize object name to interface format (ILexEntry)."""
    name = name.replace("Operations", "")
    if not name.startswith("I"):
        name = f"I{name}"
    return name


def resolve_pythonic_property(name: str, context_entity: str = None) -> List[Dict]:
    """
    Resolve a pythonic (suffix-free) property name to its LibLCM equivalent(s).

    Args:
        name: Property name (e.g., 'Senses' or 'SensesOS')
        context_entity: Optional entity context (e.g., 'ILexEntry')

    Returns:
        List of matching properties with their full names and kinds
    """
    if not api_index or not api_index.liblcm:
        return []

    suffix_index = api_index.liblcm.get("suffix_index", {})
    if not suffix_index:
        return []

    results = []

    # Check if it's a pythonic name (suffix-free)
    by_pythonic = suffix_index.get("by_pythonic_name", {})
    if name in by_pythonic:
        matches = by_pythonic[name]
        if context_entity:
            # Filter to matching entity
            results = [m for m in matches if m["entity"] == context_entity]
        else:
            results = matches

    # Check if it's a full name (with suffix)
    if not results:
        by_full = suffix_index.get("by_full_name", {})
        if context_entity:
            key = f"{context_entity}.{name}"
            if key in by_full:
                match = by_full[key]
                results = [{
                    "entity": match["entity"],
                    "full_name": name,
                    "pythonic_name": match["pythonic_name"],
                    "kind": match["kind"]
                }]
        else:
            # Search all entities for this full name
            for key, match in by_full.items():
                if key.endswith(f".{name}"):
                    results.append({
                        "entity": match["entity"],
                        "full_name": name,
                        "pythonic_name": match["pythonic_name"],
                        "kind": match["kind"]
                    })

    return results


def find_path_bfs(graph: dict, start: str, end: str, max_depth: int = 5) -> list:
    """Find path between two entities using BFS."""
    from collections import deque

    if start == end:
        return []

    queue = deque([(start, [])])
    visited = {start}

    while queue:
        current, path = queue.popleft()
        if len(path) >= max_depth:
            continue

        for edge in graph.get(current, []):
            target, via, rel_type = edge[0], edge[1], edge[2]

            if target == end:
                return path + [{"from": current, "to": target, "via": via, "type": rel_type}]

            if target not in visited:
                visited.add(target)
                queue.append((target, path + [{"from": current, "to": target, "via": via, "type": rel_type}]))

    return None


def generate_code_from_path(steps: list) -> str:
    """Generate Python code pattern from navigation steps."""
    if not steps:
        return ""

    lines = []
    indent = ""
    current_var = steps[0]["from"].lower().replace("i", "", 1)

    for step in steps:
        prop = step["via"]
        is_collection = prop.endswith("OS") or prop.endswith("OC") or prop.endswith("RC") or prop.endswith("RS")

        if is_collection:
            item_var = step["to"].lower().replace("i", "", 1)
            lines.append(f"{indent}for {item_var} in {current_var}.{prop}:")
            indent += "    "
            current_var = item_var
        else:
            new_var = step["to"].lower().replace("i", "", 1)
            lines.append(f"{indent}{new_var} = {current_var}.{prop}")
            current_var = new_var

    lines.append(f"{indent}# work with {current_var}")
    return "\n".join(lines)


async def handle_get_navigation_path(args: dict) -> list[TextContent]:
    """Find navigation path between two object types using precomputed graph."""
    from_obj = args["from_object"]
    to_obj = args["to_object"]

    from_normalized = normalize_object_name(from_obj)
    to_normalized = normalize_object_name(to_obj)

    result = {
        "from": from_obj,
        "to": to_obj,
        "from_normalized": from_normalized,
        "to_normalized": to_normalized,
        "found": False
    }

    # Check if navigation graph is loaded
    if not api_index.navigation_graph:
        result["message"] = "Navigation graph not loaded. Run refresh.py to generate it."
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    nav_graph = api_index.navigation_graph
    common_paths = nav_graph.get("common_paths", {})
    graph = nav_graph.get("graph", {})

    # Try precomputed common paths first
    path_key = f"{from_normalized} -> {to_normalized}"
    if path_key in common_paths:
        path_info = common_paths[path_key]
        result["found"] = True
        result["source"] = "precomputed"
        result["steps"] = path_info["steps"]
        result["code"] = path_info.get("code_pattern", "")
        result["description"] = f"Navigate from {from_normalized} to {to_normalized}"
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # Fall back to BFS pathfinding
    steps = find_path_bfs(graph, from_normalized, to_normalized)
    if steps:
        result["found"] = True
        result["source"] = "computed"
        result["steps"] = steps
        result["code"] = generate_code_from_path(steps)
        result["description"] = f"Path found via BFS ({len(steps)} step{'s' if len(steps) != 1 else ''})"
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # No path found
    result["message"] = f"No navigation path found from {from_normalized} to {to_normalized}."
    result["hint"] = "Try using get_object_api to explore the properties and relationships of these objects."

    # Suggest nearby objects if available
    if from_normalized in nav_graph.get("entities", {}):
        entity_rels = nav_graph["entities"][from_normalized]
        children = [c["target"] for c in entity_rels.get("children", [])[:5]]
        if children:
            result["reachable_from_source"] = children

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_find_examples(args: dict) -> list[TextContent]:
    """Find code examples for methods or operations."""
    method_name = args.get("method_name")
    operation_type = args.get("operation_type")
    object_type = args.get("object_type")
    max_results = args.get("max_results", 5)

    examples = []

    # Search FlexLibs 2.0 for examples (it has 82% example coverage)
    if api_index.flexlibs2:
        for entity_name, entity in api_index.flexlibs2.get("entities", {}).items():
            # Filter by object type if specified
            if object_type and object_type.lower() not in entity_name.lower():
                continue

            for method in entity.get("methods", []):
                # Filter by method name if specified
                if method_name and method_name.lower() not in method.get("name", "").lower():
                    continue

                # Filter by operation type if specified
                if operation_type:
                    name_lower = method.get("name", "").lower()
                    matches_op = False
                    if operation_type == "create" and any(x in name_lower for x in ["create", "add", "new"]):
                        matches_op = True
                    elif operation_type == "read" and any(x in name_lower for x in ["get", "find", "fetch"]):
                        matches_op = True
                    elif operation_type == "update" and any(x in name_lower for x in ["set", "update", "modify"]):
                        matches_op = True
                    elif operation_type == "delete" and any(x in name_lower for x in ["delete", "remove"]):
                        matches_op = True
                    elif operation_type == "iterate" and any(x in name_lower for x in ["getall", "list", "iterate"]):
                        matches_op = True
                    elif operation_type == "search" and any(x in name_lower for x in ["find", "search", "query"]):
                        matches_op = True

                    if not matches_op:
                        continue

                # Check if method has an example
                if method.get("example"):
                    examples.append({
                        "class": entity_name,
                        "method": method.get("name"),
                        "signature": method.get("signature"),
                        "description": method.get("summary", method.get("description", ""))[:150],
                        "example": method.get("example")
                    })

                    if len(examples) >= max_results:
                        break

            if len(examples) >= max_results:
                break

    return [TextContent(type="text", text=json.dumps({
        "query": {
            "method_name": method_name,
            "operation_type": operation_type,
            "object_type": object_type
        },
        "results_count": len(examples),
        "examples": examples
    }, indent=2))]


async def handle_list_categories(args: dict) -> list[TextContent]:
    """List all available API categories."""
    categories = {}

    # From FlexLibs 2.0
    if api_index.flexlibs2:
        fl2_cats = api_index.flexlibs2.get("categories", {})
        for cat_name, cat_data in fl2_cats.items():
            if cat_name not in categories:
                categories[cat_name] = {"flexlibs2_count": 0, "liblcm_count": 0}
            categories[cat_name]["flexlibs2_count"] = len(cat_data.get("entities", []))

    # From LibLCM
    if api_index.liblcm:
        for entity in api_index.liblcm.get("entities", {}).values():
            cat = entity.get("category", "uncategorized")
            if cat not in categories:
                categories[cat] = {"flexlibs2_count": 0, "liblcm_count": 0}
            categories[cat]["liblcm_count"] += 1

    return [TextContent(type="text", text=json.dumps({
        "categories": categories,
        "total_categories": len(categories)
    }, indent=2))]


async def handle_list_entities_in_category(args: dict) -> list[TextContent]:
    """List all entities in a specific category."""
    category = args["category"].lower()

    entities = {"flexlibs2": [], "liblcm": []}

    # From FlexLibs 2.0
    if api_index.flexlibs2:
        for entity_name, entity in api_index.flexlibs2.get("entities", {}).items():
            if entity.get("category", "").lower() == category:
                entities["flexlibs2"].append({
                    "name": entity_name,
                    "methods_count": len(entity.get("methods", [])),
                    "summary": entity.get("summary", "")[:100]
                })

    # From LibLCM
    if api_index.liblcm:
        for entity_name, entity in api_index.liblcm.get("entities", {}).items():
            if entity.get("category", "").lower() == category:
                entities["liblcm"].append({
                    "name": entity_name,
                    "type": entity.get("type"),
                    "summary": entity.get("summary", entity.get("description", ""))[:100]
                })

    return [TextContent(type="text", text=json.dumps({
        "category": category,
        "entities": entities,
        "counts": {
            "flexlibs2": len(entities["flexlibs2"]),
            "liblcm": len(entities["liblcm"])
        }
    }, indent=2))]


async def handle_get_module_template(args: dict) -> list[TextContent]:
    """Return the official FlexTools module template."""
    module_name = args.get("module_name", "<Module name>")
    synopsis = args.get("synopsis", "<description>")
    modifies_db = args.get("modifies_db", False)

    template = '''#
#   {module_name}
#    - A FlexTools Module -
#
#   {synopsis}
#
#   Platforms: Python .NET and IronPython
#

from flextoolslib import *

#----------------------------------------------------------------
# Documentation that the user sees:

docs = {{FTM_Name        : "{module_name}",
        FTM_Version     : 1,
        FTM_ModifiesDB  : {modifies_db},
        FTM_Synopsis    : "{synopsis}",
        FTM_Description :
"""
<detailed description here>
""" }}

#----------------------------------------------------------------
# The main processing function

def Main(project, report, modifyAllowed):
    """
    Main entry point for the FlexTools module.

    Args:
        project: FLExProject instance providing access to the FieldWorks database
        report: Reporter object for logging (report.Info, report.Warning, report.Error)
        modifyAllowed: Boolean indicating if database modifications are permitted
    """
    report.Info("Starting...")

    # Example: iterate all entries
    # for entry in project.LexiconAllEntries():
    #     headword = project.LexiconGetHeadword(entry)
    #     report.Info("Entry: {{}}".format(headword))

    report.Info("Done.")

#----------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(Main, docs)

#----------------------------------------------------------------
if __name__ == '__main__':
    print(FlexToolsModule.Help())
'''.format(
        module_name=module_name,
        synopsis=synopsis,
        modifies_db=modifies_db
    )

    result = {
        "template": template,
        "notes": [
            "FTM_Version should be an integer (1, 2, 3...), not a string",
            "Main function must be named 'Main' (not 'MainFunction')",
            "Use .format() for string formatting (IronPython compatible), not f-strings",
            "Do not use type hints (IronPython does not support them)",
            "Do not use pathlib (use os.path instead for IronPython compatibility)",
            "FlexToolsModule = FlexToolsModuleClass(Main, docs) uses positional args"
        ],
        "report_methods": [
            "report.Info(message) - Informational message",
            "report.Warning(message) - Warning message",
            "report.Error(message) - Error message",
            "report.Blank() - Blank line",
            "report.FileURL(path) - Create clickable file link"
        ]
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def handle_start_module(args: dict) -> list[TextContent]:
    """Interactive wizard to start creating a new FlexTools module."""
    import sys
    import platform

    # Gather environment info
    env_info = {
        "python_version": "{}.{}.{}".format(sys.version_info.major, sys.version_info.minor, sys.version_info.micro),
        "python_implementation": platform.python_implementation(),
        "platform": platform.system(),
        "can_use_modern_python": sys.version_info >= (3, 6),
    }

    # Check what parameters were provided
    provided = {k: v for k, v in args.items() if v is not None}

    # Define required and optional questions
    required_questions = []
    optional_questions = []

    if "module_name" not in provided:
        required_questions.append({
            "field": "module_name",
            "question": "What should the module be named?",
            "type": "string",
            "example": "Export Custom Data"
        })

    if "synopsis" not in provided:
        required_questions.append({
            "field": "synopsis",
            "question": "Provide a short description of what the module does:",
            "type": "string",
            "example": "Exports custom field data to a file"
        })

    if "api_target" not in provided:
        required_questions.append({
            "field": "api_target",
            "question": "Which API should the module target?",
            "type": "choice",
            "options": [
                {
                    "value": "flexlibs2",
                    "label": "FlexLibs 2.0 (Recommended)",
                    "description": "Modern Python wrappers with 99% documentation coverage and examples. Best for new modules. Use api_mode='flexlibs2' in searches."
                },
                {
                    "value": "flexlibs_stable",
                    "label": "FlexLibs Stable + LibLCM fallback",
                    "description": "Legacy Python wrappers (~40 functions) with LibLCM fallback for advanced features. Use api_mode='flexlibs_stable' in searches."
                },
                {
                    "value": "liblcm",
                    "label": "Pure LibLCM",
                    "description": "Direct C# API access via pythonnet. Maximum flexibility but requires .NET knowledge. Use api_mode='liblcm' in searches."
                }
            ],
            "recommended": "flexlibs2"
        })

    if "modifies_db" not in provided:
        required_questions.append({
            "field": "modifies_db",
            "question": "Will this module modify the FieldWorks database?",
            "type": "boolean",
            "hint": "Set to True if the module creates, updates, or deletes entries, senses, or other data."
        })

    if "domain" not in provided:
        required_questions.append({
            "field": "domain",
            "question": "What is the primary domain this module works with?",
            "type": "choice",
            "options": [
                {"value": "lexicon", "label": "Lexicon", "description": "Entries, senses, definitions, glosses"},
                {"value": "grammar", "label": "Grammar", "description": "Parts of speech, morphology, inflection"},
                {"value": "texts", "label": "Texts", "description": "Interlinear texts, discourse analysis"},
                {"value": "media", "label": "Media", "description": "Pictures, audio files, linked files"},
                {"value": "general", "label": "General", "description": "Project-wide operations, multiple domains"}
            ]
        })

    if args.get("modifies_db") and "include_dry_run" not in provided:
        required_questions.append({
            "field": "include_dry_run",
            "question": "Include a DRY_RUN safety mode? (Recommended for write operations)",
            "type": "boolean",
            "hint": "DRY_RUN mode shows what would happen without making changes. Useful for testing.",
            "recommended": True
        })

    # Optional question - only ask if no required questions remain
    if "test_project" not in provided:
        optional_questions.append({
            "field": "test_project",
            "question": "Do you have a FieldWorks test project to verify the script against?",
            "type": "string",
            "hint": "Provide the project name (e.g., 'Sena 3') or path. This helps verify the script works before running on production data.",
            "optional": True,
            "example": "Sena 3"
        })

    # If we have required questions, return them along with optional ones
    if required_questions:
        questions = required_questions + optional_questions
        return [TextContent(type="text", text=json.dumps({
            "status": "needs_input",
            "environment": env_info,
            "provided": provided,
            "required_questions": required_questions,
            "optional_questions": optional_questions,
            "questions": questions,  # Combined for convenience
            "instructions": "Please ask the user these questions and call start_module again with the answers. Optional questions can be skipped."
        }, indent=2))]

    # All questions answered - generate the template
    module_name = args["module_name"]
    synopsis = args["synopsis"]
    api_target = args["api_target"]
    modifies_db = args["modifies_db"]
    domain = args.get("domain", "general")
    include_dry_run = args.get("include_dry_run", False)
    test_project = args.get("test_project")

    # Build imports
    imports = ["from flextoolslib import *"]

    # Build helper code
    helpers = []
    if include_dry_run:
        helpers.append("""
#----------------------------------------------------------------
# Configuration

DRY_RUN = True  # Set to False to actually make changes
""")

    # Build main function body
    main_body_lines = []

    if modifies_db and include_dry_run:
        main_body_lines.append("""    if not modifyAllowed and not DRY_RUN:
        report.Error("This module requires write access.")
        return

    if DRY_RUN:
        report.Warning("DRY RUN mode - no changes will be made")
""")
    elif modifies_db:
        main_body_lines.append("""    if not modifyAllowed:
        report.Error("This module requires write access.")
        return
""")

    main_body_lines.append("""
    report.Info("Starting...")

    # TODO: Implement module logic

    report.Info("Done.")
""")

    # Combine main body
    main_body = "".join(main_body_lines)

    # Generate final template
    template = """#
#   {module_name}
#    - A FlexTools Module -
#
#   {synopsis}
#
#   API Target: {api_target}
#   Platforms: Python .NET and IronPython
#

{imports}
{helpers}
#----------------------------------------------------------------
# Documentation that the user sees:

docs = {{FTM_Name        : "{module_name}",
        FTM_Version     : 1,
        FTM_ModifiesDB  : {modifies_db},
        FTM_Synopsis    : "{synopsis}",
        FTM_Description :
\"\"\"
{synopsis}

<additional details here>
\"\"\" }}

#----------------------------------------------------------------
# The main processing function

def Main(project, report, modifyAllowed):
    \"\"\"
    Main entry point for the FlexTools module.

    Args:
        project: FLExProject instance providing access to the FieldWorks database
        report: Reporter object for logging (report.Info, report.Warning, report.Error)
        modifyAllowed: Boolean indicating if database modifications are permitted
    \"\"\"
{main_body}

#----------------------------------------------------------------

FlexToolsModule = FlexToolsModuleClass(Main, docs)

#----------------------------------------------------------------
if __name__ == '__main__':
    print(FlexToolsModule.Help())
""".format(
        module_name=module_name,
        synopsis=synopsis,
        api_target=api_target,
        imports="\n".join(imports),
        helpers="".join(helpers),
        modifies_db=modifies_db,
        main_body=main_body
    )

    # API-specific notes and search guidance
    api_notes = {
        "flexlibs2": {
            "search_mode": "flexlibs2",
            "tips": [
                "Use project.Senses.GetAll() to iterate senses",
                "Use project.CustomFields.GetValue/SetValue for custom fields",
                "Use project.Media.* for file operations",
                "Full documentation at 99% coverage with examples"
            ],
            "search_reminder": "Use api_mode='flexlibs2' when calling search_by_capability"
        },
        "flexlibs_stable": {
            "search_mode": "flexlibs_stable",
            "tips": [
                "Use project.LexiconAllEntries() to iterate entries",
                "More limited API (~40 functions)",
                "LibLCM fallback available for advanced features",
                "Compatible with older FlexTools installations"
            ],
            "search_reminder": "Use api_mode='flexlibs_stable' when calling search_by_capability (includes LibLCM fallback)"
        },
        "liblcm": {
            "search_mode": "liblcm",
            "tips": [
                "Direct access to C# LibLCM API via pythonnet",
                "Requires understanding of .NET and LibLCM architecture",
                "Most powerful but also most complex",
                "Use ILexEntry, ILexSense, etc. interface types"
            ],
            "search_reminder": "Use api_mode='liblcm' when calling search_by_capability"
        }
    }

    # Build next steps based on configuration
    next_steps = [
        "Save the template to your FlexTools Modules folder",
        "Replace TODO comments with your implementation",
    ]

    if include_dry_run:
        next_steps.append("Test with DRY_RUN=True first to verify behavior without making changes")

    if test_project:
        next_steps.append("Run the module against '{}' to verify it works correctly".format(test_project))
        next_steps.append("Check the FlexTools report output for any errors or warnings")
    else:
        next_steps.append("IMPORTANT: Test on a backup/sample project before running on production data")

    next_steps.append("Use search_by_capability to find specific API methods you need")

    # Build configuration output
    config = {
        "module_name": module_name,
        "synopsis": synopsis,
        "api_target": api_target,
        "modifies_db": modifies_db,
        "domain": domain,
        "include_dry_run": include_dry_run
    }
    if test_project:
        config["test_project"] = test_project

    api_info = api_notes.get(api_target, {})

    return [TextContent(type="text", text=json.dumps({
        "status": "complete",
        "environment": env_info,
        "configuration": config,
        "template": template,
        "api_guidance": {
            "mode": api_target,
            "search_mode": api_info.get("search_mode", api_target),
            "search_reminder": api_info.get("search_reminder", ""),
            "tips": api_info.get("tips", [])
        },
        "next_steps": next_steps,
        "testing_reminder": "Always test FlexTools modules on a backup or sample project first!" if not test_project else None
    }, indent=2))]


async def handle_run_module(args: dict) -> list[TextContent]:
    """Execute a FlexTools module against a FieldWorks project using FlexLibs directly."""
    module_code = args["module_code"]
    project_name = args["project_name"]
    write_enabled = args.get("write_enabled", False)
    timeout_seconds = args.get("timeout_seconds", 300)

    # Build warnings
    warnings = []
    if write_enabled:
        warnings.extend([
            "*** WRITE MODE ENABLED ***",
            "Changes WILL be made to the database!",
            "Make sure you have a backup of your project!",
            ""
        ])
    else:
        warnings.extend([
            "Running in READ-ONLY mode (dry-run)",
            "No changes will be made to the database.",
            "Set write_enabled=True to enable modifications.",
            ""
        ])

    # Create the runner script that will be executed in a subprocess
    runner_script = '''# -*- coding: utf-8 -*-
"""FlexTools Module Runner - Generated by FlexToolsMCP"""
import sys
import json
import os
import traceback

# ============================================================
# Mock flextoolslib module (so module code can import from it)
# ============================================================
import types

# Create fake flextoolslib module
flextoolslib = types.ModuleType('flextoolslib')

# FlexTools module documentation keys
flextoolslib.FTM_Name = "FTM_Name"
flextoolslib.FTM_Version = "FTM_Version"
flextoolslib.FTM_ModifiesDB = "FTM_ModifiesDB"
flextoolslib.FTM_Synopsis = "FTM_Synopsis"
flextoolslib.FTM_Description = "FTM_Description"
flextoolslib.FTM_Help = "FTM_Help"

# Minimal FlexToolsModuleClass
class FlexToolsModuleClass:
    def __init__(self, runFunction=None, docs=None, configuration=None):
        self.runFunction = runFunction
        self.docs = docs or {}
        self.configuration = configuration or []

    def Run(self, project, report, modifyAllowed=False):
        if self.runFunction:
            self.runFunction(project, report, modifyAllowed)

    def Help(self):
        return self.docs.get(flextoolslib.FTM_Description, "")

flextoolslib.FlexToolsModuleClass = FlexToolsModuleClass

# Register the mock module
sys.modules['flextoolslib'] = flextoolslib

# ============================================================
# Simple Reporter Class (mimics FTReporter interface)
# ============================================================
class SimpleReporter:
    INFO = 0
    WARNING = 1
    ERROR = 2
    BLANK = 3
    TYPE_NAMES = ["INFO", "WARNING", "ERROR", "BLANK"]

    def __init__(self):
        self.messages = []
        self.messageCounts = [0, 0, 0, 0]

    def _report(self, msg_type, msg, ref=None):
        if msg is not None and not isinstance(msg, str):
            msg = repr(msg)
        self.messages.append({
            "type": self.TYPE_NAMES[msg_type],
            "message": msg,
            "ref": ref
        })
        self.messageCounts[msg_type] += 1

    def Info(self, msg, ref=None):
        self._report(self.INFO, msg, ref)

    def Warning(self, msg, ref=None):
        self._report(self.WARNING, msg, ref)

    def Error(self, msg, ref=None):
        self._report(self.ERROR, msg, ref)

    def Blank(self):
        self._report(self.BLANK, "", None)

    def ProgressStart(self, max_val, msg=None):
        pass  # Progress not captured in non-GUI mode

    def ProgressUpdate(self, value):
        pass

    def ProgressStop(self):
        pass

    def FileURL(self, fname):
        import pathlib
        return pathlib.Path(os.path.abspath(fname)).as_uri()


# ============================================================
# Main Execution
# ============================================================
def run_module():
    result = {
        "success": False,
        "project": PROJECT_NAME,
        "write_enabled": WRITE_ENABLED,
        "messages": [],
        "summary": {},
        "error": None
    }

    project = None

    try:
        # Initialize FlexLibs
        from flexlibs import FLExInitialize, FLExCleanup, FLExProject

        FLExInitialize()

        # Open project
        project = FLExProject()
        try:
            project.OpenProject(projectName=PROJECT_NAME, writeEnabled=WRITE_ENABLED)
        except Exception as e:
            result["error"] = "Failed to open project '{}': {}".format(PROJECT_NAME, str(e))
            return result

        # Create reporter
        report = SimpleReporter()

        # Execute the module code in a namespace
        module_namespace = {
            "__name__": "__flextools_module__",
            "__file__": "module.py",
        }

        # Execute the module code to define Main and FlexToolsModule
        exec(MODULE_CODE, module_namespace)

        # Find and call Main function
        if "Main" in module_namespace:
            module_namespace["Main"](project, report, WRITE_ENABLED)
        elif "FlexToolsModule" in module_namespace:
            module_namespace["FlexToolsModule"].Run(project, report, WRITE_ENABLED)
        else:
            result["error"] = "Module code must define either 'Main' function or 'FlexToolsModule'"
            return result

        # Collect results
        result["success"] = True
        result["messages"] = report.messages
        result["summary"] = {
            "info_count": report.messageCounts[SimpleReporter.INFO],
            "warning_count": report.messageCounts[SimpleReporter.WARNING],
            "error_count": report.messageCounts[SimpleReporter.ERROR],
            "total_messages": len(report.messages)
        }

    except Exception as e:
        result["error"] = "Execution error: {}\\n{}".format(str(e), traceback.format_exc())

    finally:
        # Clean up
        if project:
            try:
                project.CloseProject()
            except:
                pass
        try:
            FLExCleanup()
        except:
            pass

    return result


if __name__ == "__main__":
    result = run_module()
    print("===FLEXTOOLS_RESULT_JSON===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
'''

    # Escape the module code for embedding in the script
    # We use repr() to safely escape all special characters
    escaped_module_code = repr(module_code)

    # Create the complete script with configuration
    full_script = '''# Configuration
PROJECT_NAME = {project_name}
WRITE_ENABLED = {write_enabled}
MODULE_CODE = {module_code}

{runner_script}
'''.format(
        project_name=repr(project_name),
        write_enabled=repr(write_enabled),
        module_code=escaped_module_code,
        runner_script=runner_script
    )

    # Write to temporary file
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(full_script)
            temp_script_path = f.name
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Failed to create temporary script: {}".format(str(e)),
            "warnings": warnings
        }, indent=2))]

    try:
        # Run the script in a subprocess
        # Use the same Python interpreter
        # stdin=DEVNULL prevents hanging if FLEx prompts for input
        result = subprocess.run(
            [sys.executable, temp_script_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding='utf-8',
            stdin=subprocess.DEVNULL
        )

        stdout = result.stdout
        stderr = result.stderr

        # Parse the JSON result from stdout
        if "===FLEXTOOLS_RESULT_JSON===" in stdout:
            json_start = stdout.index("===FLEXTOOLS_RESULT_JSON===") + len("===FLEXTOOLS_RESULT_JSON===")
            json_str = stdout[json_start:].strip()
            try:
                execution_result = json.loads(json_str)
            except json.JSONDecodeError as e:
                execution_result = {
                    "success": False,
                    "error": "Failed to parse result JSON: {}".format(str(e)),
                    "raw_output": stdout
                }
        else:
            execution_result = {
                "success": False,
                "error": "No result marker found in output",
                "raw_output": stdout,
                "stderr": stderr
            }

        # Add warnings, metadata, and optionally the full module code for learning
        execution_result["warnings"] = warnings
        execution_result["exit_code"] = result.returncode
        if stderr and not execution_result.get("error"):
            execution_result["stderr"] = stderr
        if args.get("show_code", True):
            execution_result["module_code"] = module_code

        return [TextContent(type="text", text=json.dumps(execution_result, indent=2, ensure_ascii=False))]

    except subprocess.TimeoutExpired:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Execution timed out after {} seconds".format(timeout_seconds),
            "warnings": warnings
        }, indent=2))]

    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Subprocess execution error: {}".format(str(e)),
            "warnings": warnings
        }, indent=2))]

    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_script_path)
        except:
            pass


async def handle_run_operation(args: dict) -> list[TextContent]:
    """Execute FlexLibs2 operations directly without module boilerplate."""
    operations = args["operations"]
    project_name = args["project_name"]
    write_enabled = args.get("write_enabled", False)
    timeout_seconds = args.get("timeout_seconds", 120)

    # Log operation start
    operations_logger.info(f"=== Operation Start ===")
    operations_logger.info(f"Project: {project_name}")
    operations_logger.info(f"Write enabled: {write_enabled}")
    operations_logger.debug(f"Code:\n{operations}")

    # Build warnings
    warnings = []
    if write_enabled:
        warnings.extend([
            "*** WRITE MODE ENABLED ***",
            "Changes WILL be made to the database!",
            ""
        ])
    else:
        warnings.extend([
            "Running in READ-ONLY mode (dry-run)",
            "No changes will be made to the database.",
            ""
        ])

    # Create the runner script with all flexlibs2 imports
    runner_script = '''# -*- coding: utf-8 -*-
"""FlexLibs2 Operation Runner - Generated by FlexToolsMCP"""
import sys
import json
import traceback
import io

# Force UTF-8 stdout on Windows to handle Unicode characters properly
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def safe_str(obj):
    """Safely convert .NET or Python object to UTF-8 string.

    Use this when converting .NET strings that may contain special characters.
    """
    if obj is None:
        return ""
    try:
        s = str(obj)
        # Ensure it's valid UTF-8
        return s.encode('utf-8', errors='replace').decode('utf-8')
    except Exception:
        try:
            return repr(obj)
        except Exception:
            return "(encoding error)"

# Configuration
PROJECT_NAME = {project_name}
WRITE_ENABLED = {write_enabled}
OPERATIONS = {operations}

# ============================================================
# Simple Reporter Class
# ============================================================
class SimpleReporter:
    INFO = 0
    WARNING = 1
    ERROR = 2
    BLANK = 3
    TYPE_NAMES = ["INFO", "WARNING", "ERROR", "BLANK"]

    def __init__(self):
        self.messages = []
        self.messageCounts = [0, 0, 0, 0]

    def _report(self, msg_type, msg, ref=None):
        if msg is not None and not isinstance(msg, str):
            msg = repr(msg)
        self.messages.append({{
            "type": self.TYPE_NAMES[msg_type],
            "message": msg,
            "ref": ref
        }})
        self.messageCounts[msg_type] += 1

    def Info(self, msg, ref=None):
        self._report(self.INFO, msg, ref)

    def Warning(self, msg, ref=None):
        self._report(self.WARNING, msg, ref)

    def Error(self, msg, ref=None):
        self._report(self.ERROR, msg, ref)

    def Blank(self):
        self._report(self.BLANK, "", None)


# ============================================================
# Main Execution
# ============================================================
def run_operation():
    result = {{
        "success": False,
        "project": PROJECT_NAME,
        "write_enabled": WRITE_ENABLED,
        "messages": [],
        "summary": {{}},
        "error": None
    }}

    project = None
    report = SimpleReporter()

    try:
        # Initialize FlexLibs
        from flexlibs import FLExInitialize, FLExCleanup, FLExProject

        # Import all flexlibs2 Operations classes
        from flexlibs2 import (
            # Exceptions
            FP_FileLockedError, FP_FileNotFoundError, FP_MigrationRequired,
            FP_NullParameterError, FP_ParameterError, FP_ProjectError,
            FP_ReadOnlyError, FP_RuntimeError, FP_WritingSystemError,
            # Grammar
            POSOperations, PhonemeOperations, NaturalClassOperations,
            EnvironmentOperations, MorphRuleOperations, InflectionFeatureOperations,
            GramCatOperations, PhonologicalRuleOperations,
            # Lexicon
            LexEntryOperations, LexSenseOperations, ExampleOperations,
            LexReferenceOperations, VariantOperations, PronunciationOperations,
            SemanticDomainOperations, ReversalOperations, EtymologyOperations,
            AllomorphOperations,
            # TextsWords
            TextOperations, WordformOperations, WfiAnalysisOperations,
            ParagraphOperations, SegmentOperations, WfiGlossOperations,
            WfiMorphBundleOperations, MediaOperations, FilterOperations,
            DiscourseOperations,
            # Notebook
            NoteOperations, PersonOperations, LocationOperations,
            AnthropologyOperations, DataNotebookOperations,
            # Lists
            PublicationOperations, AgentOperations, ConfidenceOperations,
            OverlayOperations, TranslationTypeOperations, PossibilityListOperations,
            # System
            WritingSystemOperations, ProjectSettingsOperations,
            AnnotationDefOperations, CheckOperations, CustomFieldOperations,
        )

        FLExInitialize()

        # Open project
        project = FLExProject()
        try:
            project.OpenProject(projectName=PROJECT_NAME, writeEnabled=WRITE_ENABLED)
        except Exception as e:
            result["error"] = "Failed to open project '{{}}': {{}}".format(PROJECT_NAME, str(e))
            return result

        # Make variables available to the operations code
        write_enabled = WRITE_ENABLED

        # Execute the operations
        exec(OPERATIONS, {{
            "project": project,
            "report": report,
            "write_enabled": write_enabled,
            "safe_str": safe_str,
            # All Operations classes
            "FP_FileLockedError": FP_FileLockedError,
            "FP_FileNotFoundError": FP_FileNotFoundError,
            "FP_MigrationRequired": FP_MigrationRequired,
            "FP_NullParameterError": FP_NullParameterError,
            "FP_ParameterError": FP_ParameterError,
            "FP_ProjectError": FP_ProjectError,
            "FP_ReadOnlyError": FP_ReadOnlyError,
            "FP_RuntimeError": FP_RuntimeError,
            "FP_WritingSystemError": FP_WritingSystemError,
            "POSOperations": POSOperations,
            "PhonemeOperations": PhonemeOperations,
            "NaturalClassOperations": NaturalClassOperations,
            "EnvironmentOperations": EnvironmentOperations,
            "MorphRuleOperations": MorphRuleOperations,
            "InflectionFeatureOperations": InflectionFeatureOperations,
            "GramCatOperations": GramCatOperations,
            "PhonologicalRuleOperations": PhonologicalRuleOperations,
            "LexEntryOperations": LexEntryOperations,
            "LexSenseOperations": LexSenseOperations,
            "ExampleOperations": ExampleOperations,
            "LexReferenceOperations": LexReferenceOperations,
            "VariantOperations": VariantOperations,
            "PronunciationOperations": PronunciationOperations,
            "SemanticDomainOperations": SemanticDomainOperations,
            "ReversalOperations": ReversalOperations,
            "EtymologyOperations": EtymologyOperations,
            "AllomorphOperations": AllomorphOperations,
            "TextOperations": TextOperations,
            "WordformOperations": WordformOperations,
            "WfiAnalysisOperations": WfiAnalysisOperations,
            "ParagraphOperations": ParagraphOperations,
            "SegmentOperations": SegmentOperations,
            "WfiGlossOperations": WfiGlossOperations,
            "WfiMorphBundleOperations": WfiMorphBundleOperations,
            "MediaOperations": MediaOperations,
            "FilterOperations": FilterOperations,
            "DiscourseOperations": DiscourseOperations,
            "NoteOperations": NoteOperations,
            "PersonOperations": PersonOperations,
            "LocationOperations": LocationOperations,
            "AnthropologyOperations": AnthropologyOperations,
            "DataNotebookOperations": DataNotebookOperations,
            "PublicationOperations": PublicationOperations,
            "AgentOperations": AgentOperations,
            "ConfidenceOperations": ConfidenceOperations,
            "OverlayOperations": OverlayOperations,
            "TranslationTypeOperations": TranslationTypeOperations,
            "PossibilityListOperations": PossibilityListOperations,
            "WritingSystemOperations": WritingSystemOperations,
            "ProjectSettingsOperations": ProjectSettingsOperations,
            "AnnotationDefOperations": AnnotationDefOperations,
            "CheckOperations": CheckOperations,
            "CustomFieldOperations": CustomFieldOperations,
        }})

        # Collect results
        result["success"] = True
        result["messages"] = report.messages
        result["summary"] = {{
            "info_count": report.messageCounts[SimpleReporter.INFO],
            "warning_count": report.messageCounts[SimpleReporter.WARNING],
            "error_count": report.messageCounts[SimpleReporter.ERROR],
            "total_messages": len(report.messages)
        }}

    except Exception as e:
        result["error"] = "Execution error: {{}}\\n{{}}".format(str(e), traceback.format_exc())
        result["messages"] = report.messages

    finally:
        # Clean up
        if project:
            try:
                project.CloseProject()
            except:
                pass
        try:
            FLExCleanup()
        except:
            pass

    return result


if __name__ == "__main__":
    result = run_operation()
    print("===FLEXTOOLS_RESULT_JSON===")
    print(json.dumps(result, indent=2, ensure_ascii=False))
'''.format(
        project_name=repr(project_name),
        write_enabled=repr(write_enabled),
        operations=repr(operations)
    )

    # Write to temporary file
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(runner_script)
            temp_script_path = f.name
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Failed to create temporary script: {}".format(str(e)),
            "warnings": warnings
        }, indent=2))]

    try:
        # Create environment with UTF-8 encoding for Windows compatibility
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'

        # Run the script in a subprocess
        result = subprocess.run(
            [sys.executable, temp_script_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding='utf-8',
            errors='replace',
            stdin=subprocess.DEVNULL,
            env=env
        )

        stdout = result.stdout
        stderr = result.stderr

        # Parse the JSON result from stdout
        if "===FLEXTOOLS_RESULT_JSON===" in stdout:
            json_start = stdout.index("===FLEXTOOLS_RESULT_JSON===") + len("===FLEXTOOLS_RESULT_JSON===")
            json_str = stdout[json_start:].strip()
            try:
                execution_result = json.loads(json_str)
            except json.JSONDecodeError as e:
                execution_result = {
                    "success": False,
                    "error": "Failed to parse result JSON: {}".format(str(e)),
                    "raw_output": stdout
                }
        else:
            execution_result = {
                "success": False,
                "error": "No result marker found in output",
                "stdout": stdout,
                "stderr": stderr
            }

        # Add warnings, return code, and optionally the executed code for learning
        execution_result["warnings"] = warnings
        execution_result["exit_code"] = result.returncode
        if args.get("show_code", True):
            execution_result["code_executed"] = operations

        # Log operation result
        if execution_result.get("success"):
            operations_logger.info(f"[OK] Operation completed successfully")
            summary = execution_result.get("summary", {})
            operations_logger.info(f"Messages: {summary.get('info_count', 0)} info, {summary.get('warning_count', 0)} warnings, {summary.get('error_count', 0)} errors")
            pattern_tracker.record_operation(operations, success=True)
        else:
            error_msg = execution_result.get("error", "Unknown error")
            operations_logger.error(f"[FAIL] Operation failed: {error_msg}")
            # Extract error type from traceback if present
            error_type = None
            if "AttributeError" in error_msg:
                error_type = "AttributeError"
            elif "TypeError" in error_msg:
                error_type = "TypeError"
            elif "KeyError" in error_msg:
                error_type = "KeyError"
            elif "has no attribute" in error_msg:
                error_type = "MissingAttribute"
            elif "not found" in error_msg.lower():
                error_type = "NotFound"
            pattern_tracker.record_operation(operations, success=False, error_msg=error_msg, error_type=error_type)

        operations_logger.info(f"=== Operation End ===\n")

        # Include pattern recommendations if there are patterns to avoid in this operation
        recommendations = pattern_tracker.get_recommendations()
        if recommendations.get("patterns_to_avoid"):
            execution_result["pattern_warnings"] = [
                p for p in recommendations["patterns_to_avoid"]
                if any(api in operations for api in [p["pattern"].split(".")[-1]])
            ][:2]  # Limit to 2 warnings

        return [TextContent(type="text", text=json.dumps(execution_result, indent=2, default=str))]

    except subprocess.TimeoutExpired:
        operations_logger.error(f"[FAIL] Operation timed out after {timeout_seconds} seconds")
        pattern_tracker.record_operation(operations, success=False, error_msg="Timeout", error_type="Timeout")
        operations_logger.info(f"=== Operation End ===\n")
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Execution timed out after {} seconds".format(timeout_seconds),
            "warnings": warnings
        }, indent=2))]

    except Exception as e:
        error_msg = str(e)
        operations_logger.error(f"[FAIL] Subprocess error: {error_msg}")
        pattern_tracker.record_operation(operations, success=False, error_msg=error_msg, error_type="SubprocessError")
        operations_logger.info(f"=== Operation End ===\n")
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "error": "Subprocess execution error: {}".format(error_msg),
            "warnings": warnings
        }, indent=2))]

    finally:
        # Clean up temporary file
        try:
            os.unlink(temp_script_path)
        except:
            pass


async def handle_get_operation_logs(args: dict) -> list[TextContent]:
    """View operation logs and pattern recommendations."""
    log_lines = args.get("log_lines", 50)
    include_patterns = args.get("include_patterns", True)
    errors_only = args.get("errors_only", False)

    result = {
        "log_file": str(get_log_dir() / "operations.log"),
        "patterns_file": str(get_log_dir() / "patterns.json"),
        "recent_logs": [],
        "recommendations": None
    }

    # Read recent log entries
    log_file = get_log_dir() / "operations.log"
    if log_file.exists():
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Filter to errors only if requested
            if errors_only:
                lines = [l for l in lines if '| ERROR' in l or '| FAIL' in l or '[FAIL]' in l]

            # Get last N lines
            recent = lines[-log_lines:] if len(lines) > log_lines else lines
            result["recent_logs"] = [line.rstrip() for line in recent]
            result["total_log_lines"] = len(lines)
        except Exception as e:
            result["log_error"] = str(e)
    else:
        result["recent_logs"] = ["(No logs yet - run some operations first)"]

    # Include pattern analysis
    if include_patterns:
        pattern_tracker.load()  # Reload to get latest
        recommendations = pattern_tracker.get_recommendations()

        result["recommendations"] = {
            "preferred_patterns": recommendations.get("preferred_patterns", [])[:10],
            "patterns_to_avoid": recommendations.get("patterns_to_avoid", [])[:10],
            "common_errors_needing_fix": recommendations.get("common_errors_needing_fix", [])[:10]
        }

        # Add summary statistics
        api_patterns = pattern_tracker.patterns.get("api_patterns", {})
        total_operations = sum(
            p["success_count"] + p["failure_count"]
            for p in api_patterns.values()
        )
        total_successes = sum(p["success_count"] for p in api_patterns.values())
        total_failures = sum(p["failure_count"] for p in api_patterns.values())

        result["statistics"] = {
            "total_operations": total_operations,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "success_rate": round(total_successes / total_operations * 100, 1) if total_operations > 0 else 0,
            "unique_api_patterns": len(api_patterns),
            "unique_error_patterns": len(pattern_tracker.patterns.get("error_patterns", {}))
        }

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def handle_resolve_property(args: dict) -> list[TextContent]:
    """Resolve pythonic property names to LibLCM equivalents."""
    property_name = args["property_name"]
    context_entity = args.get("context_entity")

    # Use the helper function
    matches = resolve_pythonic_property(property_name, context_entity)

    if not matches:
        # Try to provide helpful suggestions
        result = {
            "property_name": property_name,
            "context_entity": context_entity,
            "found": False,
            "message": f"No property '{property_name}' found",
            "suggestions": []
        }

        # Check if this might be a typo
        suffix_index = api_index.liblcm.get("suffix_index", {}) if api_index.liblcm else {}
        by_pythonic = suffix_index.get("by_pythonic_name", {})

        # Find similar pythonic names
        property_lower = property_name.lower()
        for pythonic_name in by_pythonic.keys():
            if property_lower in pythonic_name.lower() or pythonic_name.lower() in property_lower:
                result["suggestions"].append(pythonic_name)
            elif abs(len(property_name) - len(pythonic_name)) <= 2:
                # Check edit distance for close matches
                if sum(a != b for a, b in zip(property_lower, pythonic_name.lower())) <= 2:
                    result["suggestions"].append(pythonic_name)

        result["suggestions"] = list(set(result["suggestions"]))[:10]
    else:
        result = {
            "property_name": property_name,
            "context_entity": context_entity,
            "found": True,
            "matches": matches,
            "suffix_guide": {
                "OA": "Owning Atomic - single owned child object",
                "OS": "Owning Sequence - ordered collection of owned objects",
                "OC": "Owning Collection - unordered collection of owned objects",
                "RA": "Reference Atomic - single referenced object",
                "RS": "Reference Sequence - ordered collection of references",
                "RC": "Reference Collection - unordered collection of references"
            }
        }

        # Add usage examples if we found matches
        if matches:
            result["usage_examples"] = []
            for match in matches[:3]:  # Limit to first 3
                entity = match.get("entity", "")
                full_name = match.get("full_name", property_name)
                kind = match.get("kind", "property")

                if kind in ("OS", "OC", "RS", "RC"):
                    result["usage_examples"].append(
                        f"for item in obj.{full_name}:  # Iterate {kind} collection"
                    )
                elif kind in ("OA", "RA"):
                    result["usage_examples"].append(
                        f"ref = obj.{full_name}  # Get single {kind} reference"
                    )

    return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


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

    if api_index.flexlibs_stable:
        print(f"[OK] FlexLibs Stable: {len(api_index.flexlibs_stable.get('entities', {}))} entities", file=__import__("sys").stderr)
    else:
        print("[WARN] FlexLibs Stable index not found", file=__import__("sys").stderr)

    print("[INFO] Starting MCP server...", file=__import__("sys").stderr)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
