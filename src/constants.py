#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared constants for API analyzers.

Consolidates magic strings and enums used across flexicon_analyzer and
liblcm_extractor to reduce duplication and prevent inconsistent categorization.
"""

# ---- LibLCM Property Kind Suffixes -----------------------------------------------

# Property relationship kind suffixes (from FieldWorks naming conventions)
PROPERTY_KIND_OWNING_SEQUENCE = "OS"  # Ordered collection of owned objects
PROPERTY_KIND_OWNING_COLLECTION = "OC"  # Unordered collection of owned objects
PROPERTY_KIND_REFERENCE_SEQUENCE = "RS"  # Ordered collection of referenced objects
PROPERTY_KIND_REFERENCE_COLLECTION = "RC"  # Unordered collection of referenced objects
PROPERTY_KIND_OWNING_ATOMIC = "OA"  # Single owned object reference
PROPERTY_KIND_REFERENCE_ATOMIC = "RA"  # Single referenced object

# All property kinds in a tuple for membership tests
PROPERTY_KINDS = (
    PROPERTY_KIND_OWNING_SEQUENCE,
    PROPERTY_KIND_OWNING_COLLECTION,
    PROPERTY_KIND_REFERENCE_SEQUENCE,
    PROPERTY_KIND_REFERENCE_COLLECTION,
    PROPERTY_KIND_OWNING_ATOMIC,
    PROPERTY_KIND_REFERENCE_ATOMIC,
)

# Map property kind to human-readable relationship type
PROPERTY_KIND_TO_RELATIONSHIP = {
    PROPERTY_KIND_OWNING_SEQUENCE: "owns_sequence",
    PROPERTY_KIND_OWNING_COLLECTION: "owns_collection",
    PROPERTY_KIND_REFERENCE_SEQUENCE: "references_sequence",
    PROPERTY_KIND_REFERENCE_COLLECTION: "references_collection",
    PROPERTY_KIND_OWNING_ATOMIC: "owns_atomic",
    PROPERTY_KIND_REFERENCE_ATOMIC: "references_atomic",
}

# Map property kind to detailed description
PROPERTY_KIND_DESCRIPTIONS = {
    PROPERTY_KIND_OWNING_SEQUENCE: "Ordered collection of owned objects (children)",
    PROPERTY_KIND_OWNING_COLLECTION: "Unordered collection of owned objects (children)",
    PROPERTY_KIND_REFERENCE_SEQUENCE: "Ordered collection of referenced objects",
    PROPERTY_KIND_REFERENCE_COLLECTION: "Unordered collection of referenced objects",
    PROPERTY_KIND_OWNING_ATOMIC: "Single owned object reference (child)",
    PROPERTY_KIND_REFERENCE_ATOMIC: "Single referenced object",
}

# ---- Method Categories -----------------------------------------------------------

METHOD_CATEGORY_RETRIEVAL = "retrieval"
METHOD_CATEGORY_MODIFICATION = "modification"
METHOD_CATEGORY_CREATION = "creation"
METHOD_CATEGORY_DELETION = "deletion"
METHOD_CATEGORY_PREDICATE = "predicate"
METHOD_CATEGORY_MANIPULATION = "manipulation"
METHOD_CATEGORY_VALIDATION = "validation"
METHOD_CATEGORY_OPERATION = "operation"

# Map method category to description template
METHOD_CATEGORY_DESCRIPTIONS = {
    METHOD_CATEGORY_RETRIEVAL: "Retrieves data using {name}",
    METHOD_CATEGORY_MODIFICATION: "Modifies data using {name}",
    METHOD_CATEGORY_CREATION: "Creates new objects using {name}",
    METHOD_CATEGORY_DELETION: "Removes or deletes using {name}",
    METHOD_CATEGORY_PREDICATE: "Checks condition using {name}",
    METHOD_CATEGORY_MANIPULATION: "Manipulates data using {name}",
    METHOD_CATEGORY_VALIDATION: "Validates using {name}",
    METHOD_CATEGORY_OPERATION: "Performs operation {name}",
}

# ---- Entity Categories -----------------------------------------------------------

ENTITY_CATEGORY_LEXICON = "lexicon"
ENTITY_CATEGORY_MORPHOLOGY = "morphology"
ENTITY_CATEGORY_WORDFORM = "wordform"
ENTITY_CATEGORY_SCRIPTURE = "scripture"
ENTITY_CATEGORY_NOTEBOOK = "notebook"
ENTITY_CATEGORY_TEXT = "text"
ENTITY_CATEGORY_FEATURE_STRUCTURE = "feature_structure"
ENTITY_CATEGORY_PHONOLOGY = "phonology"
ENTITY_CATEGORY_CORE = "core"
ENTITY_CATEGORY_DISCOURSE = "discourse"
ENTITY_CATEGORY_REVERSAL = "reversal"
ENTITY_CATEGORY_GENERAL = "general"
ENTITY_CATEGORY_REPOSITORY = "repository"
ENTITY_CATEGORY_FACTORY = "factory"
ENTITY_CATEGORY_SERVICE = "service"
ENTITY_CATEGORY_INFRASTRUCTURE = "infrastructure"

# Prefix to category mapping (for LibLCM type names)
ENTITY_PREFIX_TO_CATEGORY = {
    "ILex": ENTITY_CATEGORY_LEXICON,
    "IMo": ENTITY_CATEGORY_MORPHOLOGY,
    "IWfi": ENTITY_CATEGORY_WORDFORM,
    "IScrip": ENTITY_CATEGORY_SCRIPTURE,
    "IScr": ENTITY_CATEGORY_SCRIPTURE,
    "IRn": ENTITY_CATEGORY_NOTEBOOK,
    "IText": ENTITY_CATEGORY_TEXT,
    "IStText": ENTITY_CATEGORY_TEXT,
    "IFs": ENTITY_CATEGORY_FEATURE_STRUCTURE,
    "IPh": ENTITY_CATEGORY_PHONOLOGY,
    "ICm": ENTITY_CATEGORY_CORE,
    "IDs": ENTITY_CATEGORY_DISCOURSE,
    "IReversal": ENTITY_CATEGORY_REVERSAL,
}

# ---- Operation Types (from Flexicon) -------------------------------------------

OPERATION_TYPE_CREATE = "create"
OPERATION_TYPE_READ = "read"
OPERATION_TYPE_UPDATE = "update"
OPERATION_TYPE_DELETE = "delete"
OPERATION_TYPE_ITERATE = "iterate"
OPERATION_TYPE_REORDER = "reorder"
OPERATION_TYPE_MERGE = "merge"
OPERATION_TYPE_GENERAL = "general"

ALL_OPERATION_TYPES = (
    OPERATION_TYPE_CREATE,
    OPERATION_TYPE_READ,
    OPERATION_TYPE_UPDATE,
    OPERATION_TYPE_DELETE,
    OPERATION_TYPE_ITERATE,
    OPERATION_TYPE_REORDER,
    OPERATION_TYPE_MERGE,
    OPERATION_TYPE_GENERAL,
)
