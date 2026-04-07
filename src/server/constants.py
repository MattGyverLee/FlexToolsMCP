#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared constants for FlexToolsMCP.

This module centralizes constants that are used across multiple modules
to avoid duplication and ensure consistency.
"""

# ============================================================
# Known FlexLibs2 Operations Classes
# ============================================================
# Complete set of Operations classes available in FlexLibs2.
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
# Supported FlexLibs API modes. Used across validators, models,
# and execution handlers to ensure consistent validation.
API_MODES = ("flexlibs2", "flexlibs_stable", "liblcm")
API_MODES_DEFAULT = "flexlibs2"
