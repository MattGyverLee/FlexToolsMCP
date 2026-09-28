"""
id: complex-forms-and-variants
intent: Report complex form entries and their component structure, variant entries and their main entry relationships
match_terms: ["complex form entries", "multiword entries", "variant entries", "complex form components", "variant of entry", "entry relationships", "complex form structure"]
entities: ["LexEntry", "LexEntryRef", "ComplexFormType", "VariantType"]
operations: ["read", "iterate"]
requires_write: false
origin: From Ron/FLExTrans Published Modules/ConvertTextToSTAMPformat.py (complex-forms and component gathering) and Utils.py (variant chain walking)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 3
notes: Read-only report in two parts: (1) complex form entries with their component entries listed in order; (2) variant entries with their variant type, chained to the entry that actually holds the senses (walking through variants-of-variants when the immediate main entry has none). project.LexEntry.GetComplexFormComponents legally mixes ILexEntry and ILexSense elements, so each component is resolved with a ClassName check rather than an attribute guess. project.Variants.GetComponentLexemes always returns ILexEntry directly, so no such branching is needed on that path. Morph type names have no flexicon getter and are read via a raw ITsString cast (flexicon gap #583); import ITsString from SIL.LCModel.Core.KernelInterfaces, not SIL.LCModel.
"""
# --- PARAMS ---
SHOW_COMPLEX_FORMS = True  # report complex form entries and components
SHOW_VARIANTS = True  # report variant entries and their chains
# --- END PARAMS ---

import unicodedata
from SIL.LCModel.Core.KernelInterfaces import ITsString

def nfc(text):
    return unicodedata.normalize("NFC", text or "")

def get_morph_type_name(morph_type):
    """Get morph type name from object (raw LCM access - flexicon gap #583)"""
    if morph_type is None:
        return "unknown"
    try:
        return nfc(ITsString(morph_type.Name.BestAnalysisAlternative).Text)  # flexicon gap: #583 (no morph-type name getter)
    except AttributeError:
        return "unknown"

def resolve_complex_form_component_entry(comp):
    """GetComplexFormComponents legally mixes ILexEntry and ILexSense; its own
    docstring's documented pattern is a ClassName check (# raw-lcm: documented
    discriminator), since neither type exposes an isinstance-friendly
    discriminator on the bare ICmObject."""
    if comp.ClassName == "LexEntry":  # raw-lcm: documented discriminator (GetComplexFormComponents docstring)
        return comp
    if comp.ClassName == "LexSense":  # raw-lcm: documented discriminator (GetComplexFormComponents docstring)
        return project.Senses.GetOwningEntry(comp)
    return None

def get_sense_from_entry_or_chain(entry):
    """Walk variant chain to find entry with senses"""
    visited = set()
    while True:
        # Prevent infinite loops
        entry_id = id(entry)
        if entry_id in visited:
            return entry
        visited.add(entry_id)

        # Get senses
        senses = list(project.LexEntry.GetSenses(entry))
        if senses:
            return entry

        # Check if this is a variant with no senses - get all variants of entry
        variants = project.Variants.GetAll(entry)
        if not variants:
            return entry

        # Get the main entry from variant chain (GetComponentLexemes is
        # documented to always return ILexEntry directly)
        found_next = False
        for var in variants:
            components = project.Variants.GetComponentLexemes(var)
            if components:
                entry = components[0]
                found_next = True
                break

        if not found_next:
            return entry

complex_forms_found = 0
variants_found = 0

if SHOW_COMPLEX_FORMS:
    report.Info("=== Complex Form Entries ===")

    for entry in project.LexEntry.GetAll():
        headword = nfc(project.LexEntry.GetHeadword(entry))

        # Get complex form components for this entry
        components = project.LexEntry.GetComplexFormComponents(entry)

        if components and len(components) >= 2:
            complex_forms_found += 1

            report.Info(
                f"{headword} [Complex Form]",
                project.BuildGotoURL(entry)
            )
            report.Info(f"  Components: {len(components)}")

            for i, comp in enumerate(components):
                comp_entry = resolve_complex_form_component_entry(comp)
                if comp_entry is None:
                    report.Info(f"    [{i+1}] (unrecognized component type)")
                    continue
                comp_headword = project.LexEntry.GetHeadword(comp_entry)
                comp_mt = project.LexEntry.GetMorphType(comp_entry)
                mt_name = get_morph_type_name(comp_mt)

                report.Info(f"    [{i+1}] {comp_headword} ({mt_name})")

if SHOW_VARIANTS:
    report.Info("=== Variant Entries ===")

    for entry in project.LexEntry.GetAll():
        headword = nfc(project.LexEntry.GetHeadword(entry))

        # Check for variants of this entry
        variants = project.Variants.GetAll(entry)

        if variants:
            for var in variants:
                var_type = project.Variants.GetType(var)
                type_name = project.Variants.GetTypeName(var_type) if var_type else "none"

                # Get the main entry (first component in variant chain)
                components = project.Variants.GetComponentLexemes(var)
                main_entry = components[0] if components else None

                # Walk variant chain if main entry has no senses
                if main_entry:
                    main_with_senses = get_sense_from_entry_or_chain(main_entry)
                else:
                    main_with_senses = None

                variants_found += 1

                main_headword = "unknown"
                if main_with_senses:
                    main_headword = project.LexEntry.GetHeadword(main_with_senses)

                report.Info(
                    f"{headword} -> {main_headword} [Variant]",
                    project.BuildGotoURL(entry)
                )
                report.Info(f"  Type: {type_name}")

# Summary
if SHOW_COMPLEX_FORMS or SHOW_VARIANTS:
    report.Info("")
    if SHOW_COMPLEX_FORMS:
        report.Info(f"Complex form entries found: {complex_forms_found}")
    if SHOW_VARIANTS:
        report.Info(f"Variant entries found: {variants_found}")
