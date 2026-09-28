"""
id: pos-inventory
intent: Show the part-of-speech hierarchy with abbreviations, inflection classes (including subclasses), stem names, and count of affix templates and slots
match_terms: ["pos hierarchy", "pos tree", "part of speech inventory", "grammar categories", "inflection classes", "stem names", "affix templates count"]
entities: ["PartOfSpeech", "InflectionClass", "MoInflAffixTemplate", "MoInflAffixSlot"]
operations: ["read", "iterate"]
requires_write: false
origin: FLExTools module DoStampSynthesis.py (~661-714) and GenerateParses.py (~185-206, ~209-242) (Ron Lockwood)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 8
notes: Prints the POS tree indented by depth, flagging abbreviations containing spaces or periods (common grammar-setup errors). Inflection classes are shown with their subclasses, stem names with their feature region counts, and affix templates/slots are counted per POS (disabled templates are skipped). SubclassesOC, StemNamesOC and RegionsOC have no flexicon wrapper and are read via raw LCM casts (flexicon gap #580).
"""
# --- PARAMS ---
POS_FILTER = ""  # empty string means show all POS; non-empty filters by exact POS name
SHOW_STEM_NAMES = True  # include stem names and their feature regions
SHOW_INFLECTION_CLASSES = True  # include inflection class hierarchy
SHOW_AFFIX_TEMPLATES = True  # count affix templates and slots
# --- END PARAMS ---
import unicodedata
import re
from SIL.LCModel import IMoInflClass, IPartOfSpeech, IMoStemName


def nfc(text):
    """Normalize text to NFC form for comparison."""
    return unicodedata.normalize("NFC", text or "")


def has_problem_abbr(abbr):
    """Check if abbreviation contains spaces or periods."""
    return bool(re.search(r'[\s.]', abbr or ""))


def show_pos_tree(pos, depth=0):
    """Recursively print POS hierarchy with indentation."""
    abbr = project.POS.GetAbbreviation(pos)
    name = project.POS.GetName(pos)
    indent = "  " * depth

    # Flag problematic abbreviations
    flag = ""
    if has_problem_abbr(abbr):
        flag = " [ERROR: abbr has spaces/periods]"

    report.Info(f"{indent}{nfc(abbr)}: {nfc(name)}{flag}")

    # Show inflection classes if requested
    if SHOW_INFLECTION_CLASSES:
        infl_classes = project.POS.GetInflectionClasses(pos)
        for ic in infl_classes:
            ic_abbr = ic.Abbreviation.BestAnalysisAlternative.Text if ic.Abbreviation else ""
            ic_name = ic.Name.BestAnalysisAlternative.Text if ic.Name else ""
            report.Info(f"{indent}  [class] {nfc(ic_abbr)}: {nfc(ic_name)}")
            # Show subclasses (flexicon gap #580: SubclassesOC not wrapped)
            ic_concrete = IMoInflClass(ic)  # raw-lcm: flexicon gap #580
            if ic_concrete.SubclassesOC and ic_concrete.SubclassesOC.Count > 0:  # raw-lcm: flexicon gap #580
                for subclass in ic_concrete.SubclassesOC:  # raw-lcm: flexicon gap #580
                    sub_abbr = subclass.Abbreviation.BestAnalysisAlternative.Text if subclass.Abbreviation else ""
                    sub_name = subclass.Name.BestAnalysisAlternative.Text if subclass.Name else ""
                    report.Info(f"{indent}    [subclass] {nfc(sub_abbr)}: {nfc(sub_name)}")

    # Show stem names if requested (flexicon gap #580: StemNamesOC not wrapped)
    if SHOW_STEM_NAMES:
        pos_concrete = IPartOfSpeech(pos)  # raw-lcm: flexicon gap #580
        if pos_concrete.StemNamesOC and pos_concrete.StemNamesOC.Count > 0:  # raw-lcm: flexicon gap #580
            for raw_stem_name in pos_concrete.StemNamesOC:  # raw-lcm: flexicon gap #580
                stem_name = IMoStemName(raw_stem_name)  # raw-lcm: flexicon gap #580
                sn_abbr = stem_name.Abbreviation.BestAnalysisAlternative.Text if stem_name.Abbreviation else ""
                if sn_abbr:
                    region_count = stem_name.RegionsOC.Count if stem_name.RegionsOC else 0  # raw-lcm: flexicon gap #580
                    if region_count > 0:
                        report.Info(f"{indent}  [stem] {nfc(sn_abbr)} ({region_count} feature regions)")

    # Count affix templates and slots if requested
    if SHOW_AFFIX_TEMPLATES:
        templates = project.MorphRules.GetAllAffixTemplatesForPOS(pos)
        if templates:
            template_count = 0
            slot_count = 0
            for template in templates:
                if not template.disabled:
                    template_count += 1
                    slot_count += len(template.prefix_slots) + len(template.suffix_slots)
            if template_count > 0:
                report.Info(f"{indent}  [templates] {template_count} active, {slot_count} total slots")

    # Recursively show subcategories
    subcats = project.POS.GetSubcategories(pos, recursive=False)
    for subcat in subcats:
        show_pos_tree(subcat, depth + 1)


# Main loop through all POS
wanted = set()
if POS_FILTER:
    wanted.add(nfc(POS_FILTER))

for pos in project.POS.GetAll(recursive=False):
    name = nfc(project.POS.GetName(pos))

    # Filter if needed
    if wanted and name not in wanted:
        continue

    # Show POS tree starting from this root
    show_pos_tree(pos)
    report.Info("")  # blank line between root POS trees

if wanted and not any(nfc(project.POS.GetName(p)) in wanted for p in project.POS.GetAll()):
    report.Warning(f"no part of speech named '{POS_FILTER}'")
