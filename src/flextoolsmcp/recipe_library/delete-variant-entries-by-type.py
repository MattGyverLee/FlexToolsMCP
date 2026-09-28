"""
id: delete-variant-entries-by-type
intent: Delete variant entries with a specified variant type (e.g. Capitalized variants)
match_terms: ["delete variant entries", "remove variant entries by type", "delete capitalized variant entries", "remove variants of a given type", "clean up variant entries"]
entities: ["LexEntry", "LexEntryRef", "VariantType"]
operations: ["delete"]
requires_write: true
origin: FLExTools module RemoveCapitalVariantEntries.py (Ron Lockwood)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-dryrun"}
raw_lcm_lines: 0
notes: Deletes variant entries whose variant type matches the specified type. Only deletes entries that are solely a variant (no senses of their own); entries with senses are always left alone even if also linked as a variant. Uses a two-pass approach (collect, then delete) and validates the variant type with project.Variants.FindType before any write. The variant type is matched by object identity against the resolved type, not by comparing display strings, since Unicode normalization can differ between a stored type name and a literal typed in PARAMS. GetType returns only the first type on a variant ref; a ref with more than one type is not fully enumerated, matching the single-type behavior of the original FLExTools module this was based on.
"""
# --- PARAMS ---
VARIANT_TYPE = "Capitalized"  # variant type name to match for deletion (e.g. "Capitalized")
# --- END PARAMS ---
import unicodedata

# Validate variant type before any write
vt = project.Variants.FindType(VARIANT_TYPE)
if vt is None:
    names = [project.Variants.GetTypeName(t) for t in project.Variants.GetAllTypes()]
    report.Error(f"unknown variant type {VARIANT_TYPE!r}; available={names}")
    modifyAllowed = False
else:
    report.Info(f"Variant type '{VARIANT_TYPE}' validated.")

# First pass: collect entries to delete
entries_to_delete = []
for entry in project.LexEntry.GetAll():
    senses = project.LexEntry.GetSenses(entry)

    # Only consider entries with no senses of their own (solely variants)
    if senses:
        continue

    # Check if this is a variant entry with the matching type
    variant_refs = project.Variants.GetAll(entry)
    if not variant_refs:
        continue

    # Check the variant type by object identity against the already-resolved
    # `vt` (from FindType), not by re-comparing display strings -- Unicode
    # normalization can differ between GetTypeName's output and VARIANT_TYPE,
    # so a raw string comparison could silently never match. GetType returns
    # only the first type on a variant ref.
    for var_ref in variant_refs:
        var_type = project.Variants.GetType(var_ref)
        if var_type and var_type == vt:
            entries_to_delete.append(entry)
            break

report.Info(f"Found {len(entries_to_delete)} variant entry/entries with type '{VARIANT_TYPE}'")

# Second pass: delete collected entries
deleted_count = 0
for entry in entries_to_delete:
    headword = project.LexEntry.GetHeadword(entry)
    if not modifyAllowed:
        report.Info(f"(dry run) would delete variant entry '{headword}'")
    if modifyAllowed:
        try:
            project.LexEntry.Delete(entry)
            deleted_count += 1
            report.Info(f"Deleted variant entry '{headword}'")
        except Exception as e:
            report.Error(f"Failed to delete variant entry '{headword}': {e}")

if modifyAllowed:
    report.Info(f"Deleted {deleted_count} variant entry/entries with type '{VARIANT_TYPE}'.")
