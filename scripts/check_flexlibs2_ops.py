#!/usr/bin/env python3
"""Verify all FlexLibs2 Operations classes can be imported.

This script attempts to import every Operations class that server.py
references. It catches broken classes early — before a user hits them
at runtime.

Run manually after changing flexlibs2 code:
    python scripts/check_flexlibs2_ops.py

Also runs as part of pre-commit when flexlibs2 is installed.
Exit code 0 = all OK (or flexlibs2 not installed), 1 = failures found.
"""
import sys

# Must match the KNOWN_OPERATIONS set in server.py
OPERATIONS_CLASSES = [
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
]

# Core classes that must also import
CORE_CLASSES = [
    "FLExInitialize", "FLExCleanup", "FLExProject",
]


def main():
    # Check if flexlibs2 is installed at all
    try:
        import flexlibs2  # noqa: F401
    except ImportError:
        print("flexlibs2 not installed — skipping Operations import check.")
        return 0

    failed = []
    passed = 0

    # Check core classes
    for cls_name in CORE_CLASSES:
        try:
            cls = getattr(__import__("flexlibs2", fromlist=[cls_name]), cls_name)
            if cls is None:
                raise AttributeError(f"{cls_name} is None")
            passed += 1
        except (ImportError, AttributeError) as e:
            failed.append((cls_name, str(e)))

    # Check all Operations classes
    for cls_name in OPERATIONS_CLASSES:
        try:
            cls = getattr(__import__("flexlibs2", fromlist=[cls_name]), cls_name)
            if cls is None:
                raise AttributeError(f"{cls_name} is None")
            passed += 1
        except (ImportError, AttributeError) as e:
            failed.append((cls_name, str(e)))

    total = len(CORE_CLASSES) + len(OPERATIONS_CLASSES)

    if failed:
        print(f"FAILED: {len(failed)}/{total} FlexLibs2 classes could not be imported:",
              file=sys.stderr)
        for cls_name, error in failed:
            print(f"  {cls_name}: {error}", file=sys.stderr)
        return 1

    print(f"All {total} FlexLibs2 classes imported OK "
          f"({len(CORE_CLASSES)} core + {len(OPERATIONS_CLASSES)} Operations).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
