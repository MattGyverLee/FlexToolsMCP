#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JSON Utilities: Sort and normalize API JSON files for deterministic output.

Ensures:
- Dictionary keys are sorted alphabetically
- Inventory/lookup array fields are sorted alphabetically
- Sequence arrays (examples, steps, code snippets) maintain order
"""

from typing import Any


# Arrays that should be sorted (inventory/lookup lists)
SORTABLE_ARRAYS = {
    "properties_accessed",
    "methods_called",
    "factories_used",
    "repositories_used",
    "utilities_used",
    "concrete_types",
    "lcm_dependencies",
    "mappings",
    "entities",
    "interfaces",
    "wraps",
    "wraps_interfaces",
    "imports",
    "namespaces",
    "categories",
    "tags",
    "dependencies",
}


def sort_json_arrays(obj: Any) -> Any:
    """
    Recursively sort sortable array fields in a JSON structure.

    Preserves order for sequence-based arrays (examples, steps, operations, code snippets).
    Sorts inventory/lookup arrays alphabetically for deterministic output.

    Args:
        obj: The JSON object to normalize (dict, list, or primitive)

    Returns:
        The normalized object with sorted arrays
    """
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if isinstance(value, list):
                # Check if this array should be sorted
                if key in SORTABLE_ARRAYS:
                    # Sort if all elements are strings
                    if all(isinstance(item, str) for item in value):
                        result[key] = sorted(set(value))  # Also deduplicate
                    else:
                        # If mixed types or objects, try to sort by string representation
                        try:
                            result[key] = sorted(set(value))
                        except TypeError:
                            # Can't sort (complex objects), keep original order
                            result[key] = value
                else:
                    # Preserve order for non-sortable arrays but recurse into elements
                    result[key] = [sort_json_arrays(item) for item in value]
            else:
                # Recurse into non-array values
                result[key] = sort_json_arrays(value)
        return result
    elif isinstance(obj, list):
        # For lists not matched by key (shouldn't happen with proper structure)
        return [sort_json_arrays(item) for item in obj]
    else:
        # Primitive type, return as-is
        return obj
