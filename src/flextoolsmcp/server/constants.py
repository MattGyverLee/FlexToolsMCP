#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared constants for FlexToolsMCP.

This module centralizes constants that are used across multiple modules
to avoid duplication and ensure consistency.
"""

# ============================================================
# Known Flexicon Operations Classes
# ============================================================
# Complete set of Operations classes available in Flexicon.
# Used by validators and analysis tools.
#
# These sets are required by pre-commit hooks to verify runtime consistency.

KNOWN_OPERATIONS = {
    # Grammar
    "POSOperations", "PhonemeOperations", "NaturalClassOperations",
    "EnvironmentOperations", "MorphRuleOperations", "InflectionFeatureOperations",
    "GramCatOperations", "PhonologicalRuleOperations",
    # Lexicon
    "LexEntryOperations", "LexSenseOperations", "ExampleOperations",
    "LexReferenceOperations", "VariantOperations", "PronunciationOperations",
    "SemanticDomainOperations", "EtymologyOperations",
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

# ============================================================
# Non-Enumerable Operations (no GetAll() method)
# ============================================================
# These Operations classes don't follow the standard GetAll() pattern
# because they manage domain-specific collections (checks, fields, charts, etc.)
# rather than generic objects. See validation exemptions in scripts/validate_integrity.py
#
# - CheckOperations: has GetAllCheckTypes() (not objects)
# - CustomFieldOperations: has GetAllFields() (not objects)
# - DiscourseOperations: has GetAllCharts() (charts in texts, not top-level)
# - InflectionFeatureOperations: has FeatureGetAll(), FeatureStructureGetAll() (nested)
# - PossibilityListOperations: has GetAllLists() (lists, not items)
# - ProjectSettingsOperations: singleton (only one settings object per project)
#
NON_ENUMERABLE_OPERATIONS = {
    "CheckOperations",
    "CustomFieldOperations",
    "DiscourseOperations",
    "InflectionFeatureOperations",
    "PossibilityListOperations",
    "ProjectSettingsOperations",
}

OPERATIONS_CLASSES = KNOWN_OPERATIONS  # Alias for backwards compatibility

# ============================================================
# API Mode Values
# ============================================================
# Supported API modes. Used across validators, models,
# and execution handlers to ensure consistent validation.
API_MODES = ("flexicon", "flexlibs_stable", "liblcm")
API_MODES_DEFAULT = "flexicon"

# Deprecated api_mode aliases -> canonical value. `flexlibs2` was the previous
# name for flexicon (pip install pyflexicon); callers passing the old value are
# transparently mapped to the new one so existing configs / scripts keep working.
API_MODE_ALIASES = {
    "flexlibs2": "flexicon",
}


def normalize_api_mode(value):
    """Map a deprecated api_mode alias to its canonical value.

    Non-string values and unknown modes are returned unchanged so downstream
    validation (Literal/enum checks) still fires on genuinely invalid input.
    """
    if isinstance(value, str):
        return API_MODE_ALIASES.get(value, value)
    return value
