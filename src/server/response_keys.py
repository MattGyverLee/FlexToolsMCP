#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared response field names and constants.

Consolidates magic string constants used across all handler modules to provide
a single source of truth for response field names. This eliminates duplication
and makes it easy to rename fields consistently across the entire API.
"""

__all__ = [
    # Basic response fields
    'KEY_NAME', 'KEY_TYPE', 'KEY_MESSAGE', 'KEY_DESCRIPTION', 'KEY_SUMMARY',
    'KEY_ERROR', 'KEY_STATUS', 'KEY_SOURCE', 'KEY_CATEGORY',
    # API-specific response fields
    'KEY_OBJECTS', 'KEY_METHODS', 'KEY_PROPERTIES', 'KEY_RETURN_TYPE',
    'KEY_PARAMETERS', 'KEY_SIGNATURE', 'KEY_EXAMPLE', 'KEY_EXAMPLES',
    'KEY_ENTITY', 'KEY_FOUND', 'KEY_SCORE', 'KEY_MATCHES',
    'KEY_FLEXLIBS2', 'KEY_LIBLCM', 'KEY_FLEXLIBS_STABLE',
    'KEY_FLEXLIBS2_MATCHES', 'KEY_LIBLCM_MATCHES', 'KEY_FLEXLIBS_STABLE_MATCHES',
    'KEY_DISAMBIGUATION', 'KEY_QUERY', 'KEY_RESULTS_COUNT', 'KEY_METHODS_COUNT',
    # Catalog-specific response fields
    'KEY_FLEXLIBS2_COUNT', 'KEY_LIBLCM_COUNT', 'KEY_FLEXLIBS_STABLE_COUNT', 'KEY_TOTAL_COUNT',
    'KEY_CATEGORIES', 'KEY_ENTITIES', 'KEY_TOTAL_CATEGORIES', 'KEY_COMMON_PATHS',
    # Discovery response fields
    'KEY_AVAILABLE', 'KEY_VERSION', 'KEY_VERSIONS', 'KEY_PATH', 'KEY_LOCATION',
    # Execution response fields
    'KEY_SCRIPT', 'KEY_ISSUES', 'KEY_WARNINGS', 'KEY_CONTEXT', 'KEY_OUTPUT',
    'KEY_OPERATION', 'KEY_OBJECT_TYPE',
    # Error response fields
    'KEY_CODE', 'KEY_DETAILS', 'KEY_SUGGESTION', 'KEY_HINT',
    # Admin/session fields
    'KEY_SESSION', 'KEY_STATE', 'KEY_HISTORY', 'KEY_SETTINGS', 'KEY_CONFIGURATION',
    # Casting and type analysis
    'KEY_CASTING_ISSUES', 'KEY_CASTING_WARNINGS', 'KEY_CASTING_HINT',
    'KEY_HAS_CASTING_ISSUES', 'KEY_BASE_TYPE', 'KEY_CONCRETE_TYPES',
    'KEY_POLYMORPHIC_COLLECTIONS',
    # Execution/script analysis
    'KEY_IS_CERTIFIED_READONLY', 'KEY_MODIFIES_DB', 'KEY_MUTATING_CALLS_DETECTED',
    'KEY_EXIT_CODE', 'KEY_STDERR', 'KEY_RAW_OUTPUT', 'KEY_INCLUDE_DRY_RUN',
    'KEY_WRITE_CERTIFICATION', 'KEY_SEVERITY', 'KEY_HOW_TO_FIX',
    # Discovery/navigation
    'KEY_API_TARGET', 'KEY_TARGET', 'KEY_FROM', 'KEY_TO', 'KEY_VIA',
    'KEY_REACHABLE_FROM_SOURCE', 'KEY_GRAPH', 'KEY_COUNTS', 'KEY_SYNOPSIS',
    'KEY_APPLIES_TO',
    # Questions/suggestions
    'KEY_QUESTIONS', 'KEY_QUESTION', 'KEY_SUGGESTIONS', 'KEY_STEPS',
    'KEY_WHY', 'KEY_NEEDS_INPUT', 'KEY_PROVIDED', 'KEY_NEXT_STEPS',
    # Module/script
    'KEY_MODULE_NAME', 'KEY_COMPLETE', 'KEY_PROPERTY', 'KEY_CHILDREN',
    # Execution-specific
    'KEY_SUCCESS', 'KEY_PROJECT', 'KEY_WRITE_ENABLED', 'KEY_MESSAGES',
    'KEY_TEMPLATE', 'KEY_CONFIDENCE',
    # Handler-specific API discovery
    'KEY_SOURCES_SEARCHED', 'KEY_FALLBACK_USED', 'KEY_API_MODE', 'KEY_API_MODE_DESCRIPTION',
    'KEY_SEARCH_METHOD', 'KEY_SEMANTIC_AVAILABLE', 'KEY_IMPORT_STATEMENT', 'KEY_IMPORT_REQUIRED',
    'KEY_TOTAL_METHODS', 'KEY_RETURNED_METHODS', 'KEY_TOTAL_PROPERTIES', 'KEY_RETURNED_PROPERTIES', 'KEY_HAS_MORE', 'KEY_NEXT_OFFSET',
    'KEY_SOURCE_FILE', 'KEY_SESSION_CONTEXT', 'KEY_DETECTED', 'KEY_AUTO_RESOLVED',
    'KEY_SELECTED', 'KEY_REASONING', 'KEY_ALTERNATIVES', 'KEY_METHOD_NAME',
    'KEY_OPERATION_TYPE', 'KEY_PYTHONIC_NAME', 'KEY_KIND', 'KEY_TARGET_TYPE',
    'KEY_IS_MULTISTRING', 'KEY_EMPTY_VALUE_WARNING', 'KEY_PROPERTY_NAME', 'KEY_CONTEXT_ENTITY',
    'KEY_LIMIT', 'KEY_OFFSET', 'KEY_INCLUDE_CASTING_INFO', 'KEY_SUFFIX_GUIDE',
    'KEY_USAGE_EXAMPLES', 'KEY_PYTHONNET_CASTING', 'KEY_REQUIRES_CAST', 'KEY_DEFINED_ON',
    'KEY_NOT_AVAILABLE_ON', 'KEY_WARNING', 'KEY_PATTERN', 'KEY_FLEXLIBS2_HELPER',
    'KEY_AVAILABLE_ON_CONCRETE_TYPES', 'KEY_POLYMORPHIC_COLLECTION_WARNING',
    'KEY_UNIQUE_PROPERTIES_BY_TYPE', 'KEY_PROPERTY_AVAILABILITY_IN_CONTEXT',
    'KEY_HAS_PROPERTY_ON', 'KEY_MISSING_FROM', 'KEY_GUIDANCE',
    # Equivalence / bridge tools
    'KEY_LIBRARY', 'KEY_METHOD', 'KEY_LCM_INTERNALS', 'KEY_ADVISORY',
    'KEY_LCM_NAME', 'KEY_COVERAGE', 'KEY_GAPS',
    # Operation type constants
    'OP_CREATE', 'OP_READ', 'OP_UPDATE', 'OP_DELETE', 'OP_ITERATE', 'OP_SEARCH',
]

# ---- Response Field Names ---------------------------------------------------

# Basic response fields
KEY_NAME = "name"
KEY_TYPE = "type"
KEY_MESSAGE = "message"
KEY_DESCRIPTION = "description"
KEY_SUMMARY = "summary"
KEY_ERROR = "error"
KEY_STATUS = "status"
KEY_SOURCE = "source"
KEY_CATEGORY = "category"

# API-specific response fields
KEY_OBJECTS = "objects"
KEY_METHODS = "methods"
KEY_PROPERTIES = "properties"
KEY_RETURN_TYPE = "return_type"
KEY_PARAMETERS = "parameters"
KEY_SIGNATURE = "signature"
KEY_EXAMPLE = "example"
KEY_EXAMPLES = "examples"
KEY_ENTITY = "entity"
KEY_FOUND = "found"
KEY_SCORE = "score"
KEY_MATCHES = "matches"
KEY_FLEXLIBS2 = "flexlibs2"
KEY_LIBLCM = "liblcm"
KEY_FLEXLIBS_STABLE = "flexlibs_stable"
KEY_FLEXLIBS2_MATCHES = "flexlibs2_matches"
KEY_LIBLCM_MATCHES = "liblcm_matches"
KEY_FLEXLIBS_STABLE_MATCHES = "flexlibs_stable_matches"
KEY_DISAMBIGUATION = "disambiguation"
KEY_QUERY = "query"
KEY_RESULTS_COUNT = "results_count"
KEY_METHODS_COUNT = "methods_count"

# Catalog-specific response fields
KEY_FLEXLIBS2_COUNT = "flexlibs2_count"
KEY_LIBLCM_COUNT = "liblcm_count"
KEY_FLEXLIBS_STABLE_COUNT = "flexlibs_stable_count"
KEY_TOTAL_COUNT = "total_count"
KEY_CATEGORIES = "categories"
KEY_ENTITIES = "entities"

# Discovery response fields
KEY_AVAILABLE = "available"
KEY_VERSION = "version"
KEY_VERSIONS = "versions"
KEY_PATH = "path"
KEY_LOCATION = "location"

# Execution response fields
KEY_SCRIPT = "script"
KEY_ISSUES = "issues"
KEY_WARNINGS = "warnings"
KEY_CONTEXT = "context"
KEY_OUTPUT = "output"
KEY_OPERATION = "operation"
KEY_OBJECT_TYPE = "object_type"

# Error response fields
KEY_CODE = "code"
KEY_DETAILS = "details"
KEY_SUGGESTION = "suggestion"
KEY_HINT = "hint"

# Admin/session fields
KEY_SESSION = "session"
KEY_STATE = "state"
KEY_HISTORY = "history"
KEY_SETTINGS = "settings"
KEY_CONFIGURATION = "configuration"

# Additional API/catalog fields
KEY_TOTAL_CATEGORIES = "total_categories"
KEY_COMMON_PATHS = "common_paths"

# Casting and type analysis fields
KEY_CASTING_ISSUES = "casting_issues"
KEY_CASTING_WARNINGS = "casting_warnings"
KEY_CASTING_HINT = "casting_hint"
KEY_HAS_CASTING_ISSUES = "has_casting_issues"
KEY_BASE_TYPE = "base_type"
KEY_CONCRETE_TYPES = "concrete_types"
KEY_POLYMORPHIC_COLLECTIONS = "polymorphic_collections"

# Execution/script analysis fields
KEY_IS_CERTIFIED_READONLY = "is_certified_readonly"
KEY_MODIFIES_DB = "modifies_db"
KEY_MUTATING_CALLS_DETECTED = "mutating_calls_detected"
KEY_EXIT_CODE = "exit_code"
KEY_STDERR = "stderr"
KEY_RAW_OUTPUT = "raw_output"
KEY_INCLUDE_DRY_RUN = "include_dry_run"
KEY_WRITE_CERTIFICATION = "write_certification"
KEY_SEVERITY = "severity"
KEY_HOW_TO_FIX = "how_to_fix"

# Discovery/navigation fields
KEY_API_TARGET = "api_target"
KEY_TARGET = "target"
KEY_FROM = "from"
KEY_TO = "to"
KEY_VIA = "via"
KEY_REACHABLE_FROM_SOURCE = "reachable_from_source"
KEY_GRAPH = "graph"
KEY_COUNTS = "counts"
KEY_SYNOPSIS = "synopsis"
KEY_APPLIES_TO = "applies_to"

# Question/suggestion fields
KEY_QUESTIONS = "questions"
KEY_QUESTION = "question"
KEY_SUGGESTIONS = "suggestions"
KEY_STEPS = "steps"
KEY_WHY = "why"
KEY_NEEDS_INPUT = "needs_input"
KEY_PROVIDED = "provided"
KEY_NEXT_STEPS = "next_steps"

# Module/script fields
KEY_MODULE_NAME = "module_name"
KEY_COMPLETE = "complete"
KEY_PROPERTY = "property"
KEY_CHILDREN = "children"

# Execution-specific fields
KEY_SUCCESS = "success"
KEY_PROJECT = "project"
KEY_WRITE_ENABLED = "write_enabled"
KEY_MESSAGES = "messages"
KEY_TEMPLATE = "template"
KEY_CONFIDENCE = "confidence"

# Handler-specific API discovery fields
KEY_SOURCES_SEARCHED = "sources_searched"
KEY_FALLBACK_USED = "fallback_used"
KEY_API_MODE = "api_mode"
KEY_API_MODE_DESCRIPTION = "api_mode_description"
KEY_SEARCH_METHOD = "search_method"
KEY_SEMANTIC_AVAILABLE = "semantic_available"
KEY_IMPORT_STATEMENT = "import_statement"
KEY_IMPORT_REQUIRED = "import_required"
KEY_TOTAL_METHODS = "total_methods"
KEY_RETURNED_METHODS = "returned_methods"
KEY_TOTAL_PROPERTIES = "total_properties"
KEY_RETURNED_PROPERTIES = "returned_properties"
KEY_HAS_MORE = "has_more"
KEY_NEXT_OFFSET = "next_offset"
KEY_SOURCE_FILE = "source_file"
KEY_SESSION_CONTEXT = "session_context"
KEY_DETECTED = "detected"
KEY_AUTO_RESOLVED = "auto_resolved"
KEY_SELECTED = "selected"
KEY_REASONING = "reasoning"
KEY_ALTERNATIVES = "alternatives"
KEY_METHOD_NAME = "method_name"
KEY_OPERATION_TYPE = "operation_type"
KEY_PYTHONIC_NAME = "pythonic_name"
KEY_KIND = "kind"
KEY_TARGET_TYPE = "target_type"
KEY_IS_MULTISTRING = "is_multistring"
KEY_EMPTY_VALUE_WARNING = "empty_value_warning"
KEY_PROPERTY_NAME = "property_name"
KEY_CONTEXT_ENTITY = "context_entity"
KEY_LIMIT = "limit"
KEY_OFFSET = "offset"
KEY_INCLUDE_CASTING_INFO = "include_casting_info"
KEY_SUFFIX_GUIDE = "suffix_guide"
KEY_USAGE_EXAMPLES = "usage_examples"
KEY_PYTHONNET_CASTING = "pythonnet_casting"
KEY_REQUIRES_CAST = "requires_cast"
KEY_DEFINED_ON = "defined_on"
KEY_NOT_AVAILABLE_ON = "not_available_on"
KEY_WARNING = "warning"
KEY_PATTERN = "pattern"
KEY_FLEXLIBS2_HELPER = "flexlibs2_helper"
KEY_AVAILABLE_ON_CONCRETE_TYPES = "available_on_concrete_types"
KEY_POLYMORPHIC_COLLECTION_WARNING = "polymorphic_collection_warning"
KEY_UNIQUE_PROPERTIES_BY_TYPE = "unique_properties_by_type"
KEY_PROPERTY_AVAILABILITY_IN_CONTEXT = "property_availability_in_context"
KEY_HAS_PROPERTY_ON = "has_property_on"
KEY_MISSING_FROM = "missing_from"
KEY_GUIDANCE = "guidance"

# Equivalence / bridge tool fields
KEY_LIBRARY = "library"
KEY_METHOD = "method"
KEY_LCM_INTERNALS = "lcm_internals"
KEY_ADVISORY = "advisory"
KEY_LCM_NAME = "lcm_name"
KEY_COVERAGE = "coverage"
KEY_GAPS = "gaps"

# Operation type constants
OP_CREATE = "create"
OP_READ = "read"
OP_UPDATE = "update"
OP_DELETE = "delete"
OP_ITERATE = "iterate"
OP_SEARCH = "search"
