"""
id: senses-by-gloss
intent: Look up senses by gloss, exact or fuzzy (similar spelling), with headword, sense number and POS
match_terms: ["find sense by gloss", "gloss lookup", "fuzzy gloss match", "search glosses", "which entry means", "similar glosses"]
entities: ["LexEntry", "LexSense", "MoStemMsa"]
operations: ["read", "iterate"]
requires_write: false
origin: From Ron/FLExTrans Published Modules/LinkSenseTool.py (gather-gloss-to-sense-map and fuzzy-match-glosses)
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 1
notes: Builds a gloss-to-senses map for stem/root entries (affixes excluded by morph type name) with POS, then looks up each requested gloss exactly and, if no exact match, fuzzily (difflib) when the gloss is at least 5 characters and lengths are close. Skips empty glosses (the '***' placeholder normalizes to ""). project.Senses.GetPartOfSpeech already returns the abbreviation string, not a POS object -- do not pass it into project.POS.GetName. Morph type name has no flexicon getter and is read via a raw ITsString cast (flexicon gap #583); import it from SIL.LCModel.Core.KernelInterfaces, not SIL.LCModel.
"""
# --- PARAMS ---
GLOSSES = ["run", "go"]  # exact glosses to look up (case-insensitive); fuzzy match if no exact match
FUZZY_MATCH = True  # enable fuzzy matching for similar glosses
FUZZY_THRESHOLD = 0.74  # fuzzy match similarity threshold (0.0-1.0)
MIN_GLOSS_LEN_FOR_FUZZ = 5  # minimum gloss length for fuzzy matching
MAX_LENGTH_DIFF = 3  # max length difference between source and target for fuzzy match
# --- END PARAMS ---

import unicodedata
from difflib import SequenceMatcher
from SIL.LCModel.Core.KernelInterfaces import ITsString

def nfc(text):
    return unicodedata.normalize("NFC", text or "")

def get_morph_type_name(morph_type):
    """Get morph type name from object (raw LCM access - flexicon gap #583)"""
    if morph_type is None:
        return None
    try:
        return nfc(ITsString(morph_type.Name.BestAnalysisAlternative).Text)  # flexicon gap: #583
    except AttributeError:
        return None

def similarity_ratio(a, b):
    """Calculate similarity ratio between two strings"""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

# Build gloss-to-senses map for stem entries
gloss_map = {}  # gloss -> list of (headword, POS, sense_num, entry_guid)
seen_senses = set()  # track GUIDs to avoid duplicates

report.Info("Building gloss-to-sense map...")

for entry in project.LexEntry.GetAll():
    # Only process stem entries (not affixes)
    mt = project.LexEntry.GetMorphType(entry)
    mt_name = get_morph_type_name(mt)
    if mt_name:
        lname = mt_name.lower()
        if "stem" not in lname and "root" not in lname:
            continue

    headword = nfc(project.LexEntry.GetHeadword(entry))

    # Iterate through senses
    entry_msas = project.MSA.GetAll(entry)
    for sense_num, sense in enumerate(project.LexEntry.GetSenses(entry), 1):
        # Check if sense has an MSA (stem sense); GetMSA returns the raw
        # unwrapped object, so match it against the entry's wrapped MSAs
        # by Hvo-equality to read is_stem_msa (same technique as affix-catalog.py)
        raw_msa = project.Senses.GetMSA(sense)
        if not raw_msa:
            continue
        msa = next((m for m in entry_msas if m == raw_msa), None)
        if not msa or not msa.is_stem_msa:
            continue

        # GetPartOfSpeech already returns the abbreviation string, not a
        # POS object -- do not pass it into project.POS.GetName().
        pos_abbr = project.Senses.GetPartOfSpeech(sense)
        pos = nfc(pos_abbr) if pos_abbr else "unknown"

        # Get gloss
        gloss = nfc(project.Senses.GetGloss(sense))

        # Skip empty glosses
        if not gloss or gloss == "***":
            continue

        # Track by GUID to avoid duplicates
        sense_guid = str(sense)
        if sense_guid in seen_senses:
            continue
        seen_senses.add(sense_guid)

        # Add to map
        sense_info = (headword, pos, sense_num, sense_guid)
        if gloss not in gloss_map:
            gloss_map[gloss] = []
        gloss_map[gloss].append(sense_info)

report.Info(f"Built map with {len(gloss_map)} unique glosses")

# Look up requested glosses
report.Info("")
report.Info("=== Gloss Lookup Results ===")

for query_gloss in GLOSSES:
    query_nfc = nfc(query_gloss.lower())

    # Exact match (case-insensitive)
    exact_matches = []
    for gloss in gloss_map.keys():
        if gloss.lower() == query_nfc:
            exact_matches.extend(gloss_map[gloss])

    # Fuzzy match if no exact matches and fuzzy enabled
    fuzzy_matches = []
    if not exact_matches and FUZZY_MATCH:
        for gloss in gloss_map.keys():
            query_len = len(query_nfc)
            gloss_len = len(gloss)

            # Only try fuzzy match if glosses are long enough and length difference is small
            if (query_len >= MIN_GLOSS_LEN_FOR_FUZZ and
                gloss_len >= MIN_GLOSS_LEN_FOR_FUZZ and
                abs(query_len - gloss_len) <= MAX_LENGTH_DIFF):

                ratio = similarity_ratio(query_nfc, gloss)
                if ratio >= FUZZY_THRESHOLD:
                    fuzzy_matches.extend(gloss_map[gloss])

    # Report results
    report.Info(f"Gloss: '{query_gloss}'")

    if exact_matches:
        report.Info(f"  Exact matches: {len(exact_matches)} sense(s)")
        for headword, pos, sense_num, sense_guid in exact_matches:
            report.Info(f"    {headword}.{sense_num} ({pos})")
    elif fuzzy_matches:
        report.Info(f"  Fuzzy matches: {len(fuzzy_matches)} sense(s)")
        for headword, pos, sense_num, sense_guid in fuzzy_matches:
            report.Info(f"    {headword}.{sense_num} ({pos})")
    else:
        report.Warning(f"  No matches found")

report.Info("")
report.Info(f"Total senses in map: {sum(len(v) for v in gloss_map.values())}")
