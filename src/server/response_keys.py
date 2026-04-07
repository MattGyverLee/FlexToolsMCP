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
    'KEY_FLEXLIBS2', 'KEY_LIBLCM', 'KEY_FLEXLIBS2_MATCHES', 'KEY_LIBLCM_MATCHES',
    'KEY_DISAMBIGUATION', 'KEY_QUERY', 'KEY_RESULTS_COUNT', 'KEY_METHODS_COUNT',
    # Catalog-specific response fields
    'KEY_FLEXLIBS2_COUNT', 'KEY_LIBLCM_COUNT', 'KEY_TOTAL_COUNT',
    'KEY_CATEGORIES', 'KEY_ENTITIES',
    # Discovery response fields
    'KEY_AVAILABLE', 'KEY_VERSION', 'KEY_VERSIONS', 'KEY_PATH', 'KEY_LOCATION',
    # Execution response fields
    'KEY_SCRIPT', 'KEY_ISSUES', 'KEY_WARNINGS', 'KEY_CONTEXT', 'KEY_OUTPUT',
    'KEY_OPERATION', 'KEY_OBJECT_TYPE',
    # Error response fields
    'KEY_CODE', 'KEY_DETAILS', 'KEY_SUGGESTION', 'KEY_HINT',
    # Admin/session fields
    'KEY_SESSION', 'KEY_STATE', 'KEY_HISTORY', 'KEY_SETTINGS', 'KEY_CONFIGURATION',
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
KEY_FLEXLIBS2_MATCHES = "flexlibs2_matches"
KEY_LIBLCM_MATCHES = "liblcm_matches"
KEY_DISAMBIGUATION = "disambiguation"
KEY_QUERY = "query"
KEY_RESULTS_COUNT = "results_count"
KEY_METHODS_COUNT = "methods_count"

# Catalog-specific response fields
KEY_FLEXLIBS2_COUNT = "flexlibs2_count"
KEY_LIBLCM_COUNT = "liblcm_count"
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
