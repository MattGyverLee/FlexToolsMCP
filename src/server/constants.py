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

OPERATIONS_CLASSES = KNOWN_OPERATIONS  # Alias for backwards compatibility

# ============================================================
# API Mode Values
# ============================================================
# Supported FlexLibs API modes. Used across validators, models,
# and execution handlers to ensure consistent validation.
API_MODES = ("flexlibs2", "flexlibs_stable", "liblcm")
API_MODES_DEFAULT = "flexlibs2"
