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
# Operations shorthands that are NOT project accessors (issue #84)
# ============================================================
# Most Operations classes have a same-named shorthand on FLExProject
# (LexEntryOperations -> project.LexEntry, ExampleOperations -> project.Example).
# Two do not, so stripping "Operations" off the class name invents an accessor
# that raises AttributeError at runtime:
#
#   project.LexSense         -> AttributeError  (real accessor: project.Senses)
#   project.PhonologicalRule -> AttributeError  (real accessor: project.PhonRules)
#
# Keeping these out of the accessor allowlist lets the pre-flight gate reject
# them, and the mapping gives it the one right answer instead of a fuzzy guess.
# Verify against a live install with scripts/check_project_accessors.py.
PROJECT_ACCESSOR_ALIASES = {
    "LexSense": "Senses",
    "PhonologicalRule": "PhonRules",
}

# Issue #101: morphology list types that declare their own `Name` field but are
# NOT ICmPossibility (base=CmObject in MasterLCModel.xml). Curated set only --
# not a structural heuristic (see handlers/api.py docstring).
NOT_CMPOSSIBILITY_NAME_COLLISION = frozenset({
    "IMoInflAffixSlot", "MoInflAffixSlot",
    "IMoInflAffixTemplate", "MoInflAffixTemplate",
    "IMoInflClass", "MoInflClass",
})


def not_cmpossibility_warning(object_type: str) -> str | None:
    """Human-readable warning for issue #101 name-collision types, else None."""
    if object_type not in NOT_CMPOSSIBILITY_NAME_COLLISION:
        return None
    return (
        f"{object_type} is NOT ICmPossibility (base=CmObject in "
        f"MasterLCModel.xml). Its `Name` is its own MultiUnicode attribute, "
        f"not an inherited ICmPossibility.Name -- do NOT cast via "
        f"ICmPossibility(obj).Name. Access .Name directly on the object "
        f"(cast to {object_type} itself if you need the interface). "
        f"Contrast: IMoMorphType genuinely IS ICmPossibility, so that cast "
        f"is correct there."
    )


# Owning/ref property names whose return type is provably one of the
# NOT_CMPOSSIBILITY_NAME_COLLISION types (MasterLCModel.xml).
NOT_CMPOSSIBILITY_PROVENANCE_ATTRS = frozenset({
    "InflectionClassRA",
    "DefaultInflectionClassRA",
    "InflectionClassesOC",
    "InflectionClassesRC",
    "SubclassesOC",
    "AffixSlotsOC",
    "SlotsRC",
    "SlotRA",
    "SlotsRS",
    "PrefixSlotsRS",
    "SuffixSlotsRS",
    "EncliticSlotsRS",
    "ProcliticSlotsRS",
    "AffixTemplatesOS",
    "TemplateRA",
})

NOT_CMPOSSIBILITY_RECEIVER_NAMES = frozenset({
    "slot", "affix_slot", "infl_slot", "slot_obj",
    "template", "tmpl", "templ", "affix_template", "template_obj",
    "infl_class", "inflection_class", "infl_cls", "inflClass", "infl_class_obj",
})

_INFL_CLASS_PROVENANCE = frozenset({
    "InflectionClassRA",
    "DefaultInflectionClassRA",
    "InflectionClassesOC",
    "InflectionClassesRC",
    "SubclassesOC",
})
_INFL_SLOT_PROVENANCE = frozenset({
    "AffixSlotsOC",
    "SlotsRC",
    "SlotRA",
    "SlotsRS",
    "PrefixSlotsRS",
    "SuffixSlotsRS",
    "EncliticSlotsRS",
    "ProcliticSlotsRS",
})


def not_cmpossibility_type_for_provenance_attr(attr: str) -> str | None:
    """Return IMoInfl* interface for a known provenance property, else None."""
    if attr in _INFL_CLASS_PROVENANCE:
        return "IMoInflClass"
    if attr in _INFL_SLOT_PROVENANCE:
        return "IMoInflAffixSlot"
    if attr in {"AffixTemplatesOS", "TemplateRA"}:
        return "IMoInflAffixTemplate"
    return None


def not_cmpossibility_type_for_receiver_name(name: str) -> str | None:
    """Map curated receiver variable names to NOT_ICmPossibility types."""
    if name in {"slot", "affix_slot", "infl_slot", "slot_obj"}:
        return "IMoInflAffixSlot"
    if name in {"template", "tmpl", "templ", "affix_template", "template_obj"}:
        return "IMoInflAffixTemplate"
    if name in {
        "infl_class", "inflection_class", "infl_cls", "inflClass", "infl_class_obj",
    }:
        return "IMoInflClass"
    return None


# ============================================================
# Raw LCM handle names that map to Flexicon project accessors (issue #69)
# ============================================================
# These are native LCM/C# handle names that Flexicon exposes under a different
# (shorter) accessor name.  Code that uses the raw name directly (e.g. taken
# from LCM documentation or older FlexLibs scripts) gets a helpful advisory
# pointing at the Flexicon name instead of a confusing fuzzy-match suggestion.
#
# Unlike PROJECT_ACCESSOR_ALIASES (Operations shorthands), these keys are NOT
# required to be Operations class names -- they are raw LCM property names that
# don't correspond to any Operations class at all.
#
# Hint texts are defined in validators.py alongside the detection logic.
PROJECT_RAW_HANDLE_ALIASES = {
    "LangProject": "lp",
    "LanguageProject": "lp",
    "LangProj": "lp",
    "LexDb": "lexDB",
    "LexDbOA": "lexDB",
}

# ============================================================
# API Mode Values
# ============================================================
# Supported API modes. Used across validators, models,
# and execution handlers to ensure consistent validation.
API_MODES = ("flexicon", "flexlibs_stable", "liblcm")
API_MODES_DEFAULT = "flexicon"
# Issue #164: run_module codegen always imports flexicon; other api_mode values
# steer documentation search and preflight only until mode-conditional codegen
# returns (#163).
EXECUTION_API_MODE = "flexicon"

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
