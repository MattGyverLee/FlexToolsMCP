#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Curated recipes for the dominant search intents (issue #52).

This is the single source of truth for shipped ("curated") recipes. It is:

  - imported by ``server.recipes`` at runtime to serve recipes from
    ``search_by_capability`` / ``find_examples`` (mirrors the pattern used by
    ``server.worked_examples.WORKED_EXAMPLES``),
  - imported by ``extract_patterns.py`` to merge into the versioned
    ``common_patterns_flexicon-v<version>.json`` index file under the
    ``recipes`` key (schema ``common-patterns/2.0``), so the shipped JSON
    stays in sync with what the server actually serves,
  - exercised by ``tests/test_recipes.py`` against the full preflight
    validator chain (``recipe_validator.validate_recipe``) as a CI gate --
    every entry here MUST pass before it can ship.

Recipe code is bare-snippet form per CLAUDE.md: no ``def Main``, no
``docs``/``FlexToolsModule`` boilerplate. ``project``, ``report``, and
``modifyAllowed`` are pre-injected by the runner. flexicon imports are
included where needed. ``requires_write`` recipes always guard their mutation
with ``if modifyAllowed:``.

Never add an entry with ``source: "mined"`` here -- mined candidates are
reviewed by a human and only added to this file once flipped to "curated"
(see ``extract_patterns.py --mine-operations-log``).
"""

from typing import Any, Dict

FLEXICON_VERIFIED_VERSION = "4.2.1"

CURATED_RECIPES: Dict[str, Dict[str, Any]] = {
    "list-entries-with-glosses": {
        "intent": "List all entries with their glosses",
        "match_terms": ["list entries", "dump lexicon", "dump entries", "show glosses", "all entries with glosses"],
        "entities": ["LexEntry", "LexSense"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "for entry in project.LexEntry.GetAll():\n"
            "    headword = project.LexEntry.GetHeadword(entry)\n"
            "    for sense in project.LexEntry.GetAllSenses(entry):\n"
            "        gloss = project.LexSense.GetGloss(sense)\n"
            "        report.Info(f\"{headword}: {gloss}\")\n"
        ),
        "notes": "GetGloss returns '' for empty (never '***'). GetAll returns an EnumerableWrapper.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "count-senses-by-pos": {
        "intent": "Count senses grouped by part of speech",
        "match_terms": ["count senses by pos", "senses by part of speech", "pos distribution", "count by pos"],
        "entities": ["LexEntry", "LexSense"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "from collections import Counter\n\n"
            "counts = Counter()\n"
            "for entry in project.LexEntry.GetAll():\n"
            "    for sense in project.LexEntry.GetAllSenses(entry):\n"
            "        pos = project.LexSense.GetPartOfSpeech(sense) or \"(none)\"\n"
            "        counts[pos] += 1\n\n"
            "for pos, n in counts.most_common():\n"
            "    report.Info(f\"{pos}: {n}\")\n"
        ),
        "notes": "GetPartOfSpeech returns a display string (or None); use GetPartOfSpeechObject if you need the ICmPossibility.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "find-empty-definitions": {
        "intent": "Find senses with an empty definition",
        "match_terms": ["find empty definitions", "senses with no definition", "missing definition", "empty definition"],
        "entities": ["LexEntry", "LexSense"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "for entry in project.LexEntry.GetAll():\n"
            "    headword = project.LexEntry.GetHeadword(entry)\n"
            "    for sense in project.LexEntry.GetAllSenses(entry):\n"
            "        definition = project.LexSense.GetDefinition(sense)\n"
            "        if not definition:\n"
            "            report.Info(f\"{headword}: sense {project.LexSense.GetSenseNumber(sense)} has no definition\")\n"
        ),
        "notes": "GetDefinition normalizes '***' to '' -- 'if not definition' is the correct empty check.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "add-gloss-to-sense": {
        "intent": "Add or update the gloss on a sense",
        "match_terms": ["add gloss", "set gloss", "update gloss", "add a gloss to a sense"],
        "entities": ["LexEntry", "LexSense"],
        "operations": ["update", "write"],
        "requires_write": True,
        "code": (
            "entry = project.LexEntry.Find(\"run\")\n"
            "if entry is None:\n"
            "    report.Error(\"Entry 'run' not found\")\n"
            "else:\n"
            "    senses = project.LexEntry.GetAllSenses(entry)\n"
            "    if not senses:\n"
            "        report.Error(\"Entry has no senses\")\n"
            "    else:\n"
            "        sense = senses[0]\n"
            "        if modifyAllowed:\n"
            "            project.LexSense.SetGloss(sense, \"to move rapidly on foot\")\n"
            "            report.Info(f\"Set gloss: {project.LexSense.GetGloss(sense)}\")\n"
            "        else:\n"
            "            report.Info(\"(Would set gloss to 'to move rapidly on foot')\")\n"
        ),
        "notes": "WARNING: this recipe writes to the database. Only runs the mutation when modifyAllowed is True.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "batch-update-citation-forms": {
        "intent": "Batch-update citation forms across multiple entries",
        "match_terms": ["batch update citation forms", "update citation form", "bulk update citation forms", "set citation forms"],
        "entities": ["LexEntry"],
        "operations": ["update", "write", "iterate"],
        "requires_write": True,
        "code": (
            "# Map of headword -> new citation form.\n"
            "updates = {\n"
            "    \"run\": \"run (v.)\",\n"
            "    \"walk\": \"walk (v.)\",\n"
            "}\n\n"
            "for headword, new_citation in updates.items():\n"
            "    entry = project.LexEntry.Find(headword)\n"
            "    if entry is None:\n"
            "        report.Warning(f\"Entry '{headword}' not found; skipping\")\n"
            "        continue\n"
            "    if modifyAllowed:\n"
            "        project.LexEntry.SetCitationForm(entry, new_citation)\n"
            "        report.Info(f\"{headword}: citation form -> {new_citation}\")\n"
            "    else:\n"
            "        report.Info(f\"(Would set citation form of '{headword}' to '{new_citation}')\")\n"
        ),
        "notes": "WARNING: this recipe writes to the database. Replace the `updates` dict with your real batch before running with write enabled.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "find-duplicate-headwords": {
        "intent": "Find duplicate headwords in the lexicon",
        "match_terms": ["find duplicate headwords", "duplicate entries", "duplicate headword", "homograph check"],
        "entities": ["LexEntry"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "from collections import defaultdict\n\n"
            "by_headword = defaultdict(list)\n"
            "for entry in project.LexEntry.GetAll():\n"
            "    headword = project.LexEntry.GetHeadword(entry)\n"
            "    by_headword[headword].append(entry)\n\n"
            "for headword, entries in by_headword.items():\n"
            "    if len(entries) > 1:\n"
            "        report.Info(f\"{headword}: {len(entries)} entries (likely homographs, or true duplicates)\")\n"
        ),
        "notes": "Multiple entries sharing a headword may legitimately be homographs (distinguished by HomographNumber) -- inspect before deleting anything.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "list-texts": {
        "intent": "List all texts in the project",
        "match_terms": ["list texts", "dump texts", "show all texts", "iterate texts"],
        "entities": ["Text"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "for text in project.Text.GetAll():\n"
            "    name = project.Text.GetName(text)\n"
            "    paragraph_count = project.Text.GetParagraphCount(text)\n"
            "    report.Info(f\"{name}: {paragraph_count} paragraph(s)\")\n"
        ),
        "notes": "GetName is the vernacular title; use GetTitle for the analysis-language title if set.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "list-wordforms": {
        "intent": "List all wordforms in the project",
        "match_terms": ["list wordforms", "dump wordforms", "show all wordforms", "iterate wordforms"],
        "entities": ["Wordform"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "for wordform in project.Wordform.GetAll():\n"
            "    form = project.Wordform.GetForm(wordform)\n"
            "    occurrences = project.Wordform.GetOccurrenceCount(wordform)\n"
            "    report.Info(f\"{form}: {occurrences} occurrence(s)\")\n"
        ),
        "notes": "GetOccurrenceCount reflects analyzed occurrences in texts, not raw string frequency.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "reversal-lookup": {
        "intent": "Look up reversal index entries and their senses",
        "match_terms": ["reversal lookup", "reversal index", "list reversal entries", "reversal entries for sense"],
        "entities": ["ReversalIndexEntry", "ReversalIndex"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "for index in project.ReversalIndexes.GetAll():\n"
            "    ws = project.ReversalIndexes.GetWritingSystem(index)\n"
            "    report.Info(f\"Reversal index: {ws}\")\n"
            "    for rev_entry in project.ReversalIndexes.GetEntries(index):\n"
            "        form = project.ReversalEntries.GetForm(rev_entry)\n"
            "        senses = project.ReversalEntries.GetSenses(rev_entry)\n"
            "        report.Info(f\"  {form}: {len(senses)} sense(s)\")\n"
        ),
        "notes": "A project may have one reversal index per analysis writing system.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "list-entries-with-pos": {
        "intent": "List entries alongside the part of speech of each sense",
        "match_terms": ["list entries with pos", "entries and part of speech", "headword and pos", "list entries part of speech"],
        "entities": ["LexEntry", "LexSense"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "for entry in project.LexEntry.GetAll():\n"
            "    headword = project.LexEntry.GetHeadword(entry)\n"
            "    for sense in project.LexEntry.GetAllSenses(entry):\n"
            "        pos = project.LexSense.GetPartOfSpeech(sense) or \"(unspecified)\"\n"
            "        report.Info(f\"{headword} [{pos}]\")\n"
        ),
        "notes": "Same shape as list-entries-with-glosses but keyed on POS instead of gloss.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "find-entries-missing-pos": {
        "intent": "Find senses that have no part of speech assigned",
        "match_terms": ["find entries missing pos", "senses without pos", "missing part of speech", "no pos assigned"],
        "entities": ["LexEntry", "LexSense"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "for entry in project.LexEntry.GetAll():\n"
            "    headword = project.LexEntry.GetHeadword(entry)\n"
            "    for sense in project.LexEntry.GetAllSenses(entry):\n"
            "        pos = project.LexSense.GetPartOfSpeech(sense)\n"
            "        if not pos:\n"
            "            report.Info(f\"{headword}: sense {project.LexSense.GetSenseNumber(sense)} has no POS\")\n"
        ),
        "notes": "A sense may have no MSA at all, in which case GetPartOfSpeech returns None/empty.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "add-example-to-sense": {
        "intent": "Add an example sentence to a sense",
        "match_terms": ["add example", "add example sentence", "add an example to a sense", "create example"],
        "entities": ["LexEntry", "LexSense", "LexExampleSentence"],
        "operations": ["create", "write"],
        "requires_write": True,
        "code": (
            "entry = project.LexEntry.Find(\"run\")\n"
            "if entry is None:\n"
            "    report.Error(\"Entry 'run' not found\")\n"
            "else:\n"
            "    senses = project.LexEntry.GetAllSenses(entry)\n"
            "    if not senses:\n"
            "        report.Error(\"Entry has no senses\")\n"
            "    else:\n"
            "        sense = senses[0]\n"
            "        if modifyAllowed:\n"
            "            example = project.Example.Create(sense, \"He runs every morning.\")\n"
            "            project.Example.SetTranslation(example, \"He runs every morning.\")\n"
            "            report.Info(\"Added example sentence\")\n"
            "        else:\n"
            "            report.Info(\"(Would add example 'He runs every morning.')\")\n"
        ),
        "notes": "WARNING: this recipe writes to the database.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "find-entries-without-examples": {
        "intent": "Find senses that have no example sentences",
        "match_terms": ["find entries without examples", "senses without examples", "missing example sentence", "no example"],
        "entities": ["LexEntry", "LexSense"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "for entry in project.LexEntry.GetAll():\n"
            "    headword = project.LexEntry.GetHeadword(entry)\n"
            "    for sense in project.LexEntry.GetAllSenses(entry):\n"
            "        if project.LexSense.GetExampleCount(sense) == 0:\n"
            "            report.Info(f\"{headword}: sense {project.LexSense.GetSenseNumber(sense)} has no examples\")\n"
        ),
        "notes": "GetExampleCount avoids materializing the full example list just to check emptiness.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "list-senses-with-definitions-and-examples": {
        "intent": "List senses together with definition and example text",
        "match_terms": ["list senses with definitions", "senses and examples", "full sense dump", "sense detail report"],
        "entities": ["LexEntry", "LexSense", "LexExampleSentence"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "for entry in project.LexEntry.GetAll():\n"
            "    headword = project.LexEntry.GetHeadword(entry)\n"
            "    for sense in project.LexEntry.GetAllSenses(entry):\n"
            "        definition = project.LexSense.GetDefinition(sense)\n"
            "        examples = [project.Example.GetExample(ex) for ex in project.LexSense.GetExamples(sense)]\n"
            "        report.Info(f\"{headword}: {definition} | examples: {examples}\")\n"
        ),
        "notes": "GetExamples returns ILexExampleSentence objects; pass each through Example.GetExample for the text.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "add-semantic-domain-to-sense": {
        "intent": "Assign a semantic domain to a sense",
        "match_terms": ["add semantic domain", "assign semantic domain", "set semantic domain", "tag sense with domain"],
        "entities": ["LexEntry", "LexSense", "SemanticDomain"],
        "operations": ["update", "write"],
        "requires_write": True,
        "code": (
            "entry = project.LexEntry.Find(\"run\")\n"
            "domain = project.SemanticDomain.FindByName(\"Move\")\n"
            "if entry is None or domain is None:\n"
            "    report.Error(\"Entry 'run' or semantic domain 'Move' not found\")\n"
            "else:\n"
            "    senses = project.LexEntry.GetAllSenses(entry)\n"
            "    if not senses:\n"
            "        report.Error(\"Entry has no senses\")\n"
            "    else:\n"
            "        sense = senses[0]\n"
            "        if modifyAllowed:\n"
            "            project.LexSense.AddSemanticDomain(sense, domain)\n"
            "            report.Info(\"Added semantic domain 'Move'\")\n"
            "        else:\n"
            "            report.Info(\"(Would add semantic domain 'Move')\")\n"
        ),
        "notes": "WARNING: this recipe writes to the database. FindByName is case-sensitive to the semantic domain list's naming.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "count-entries-by-morphtype": {
        "intent": "Count entries grouped by morph type (stem, prefix, suffix, etc.)",
        "match_terms": ["count entries by morph type", "morph type distribution", "count by morph type", "stems vs affixes"],
        "entities": ["LexEntry"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "from collections import Counter\n\n"
            "counts = Counter()\n"
            "for entry in project.LexEntry.GetAll():\n"
            "    morph_type = project.LexEntry.GetMorphType(entry) or \"(unknown)\"\n"
            "    counts[morph_type] += 1\n\n"
            "for morph_type, n in counts.most_common():\n"
            "    report.Info(f\"{morph_type}: {n}\")\n"
        ),
        "notes": "GetAvailableMorphTypes lists the valid morph type strings for this project if you need to validate input.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "list-parts-of-speech": {
        "intent": "List all parts of speech defined in the project",
        "match_terms": ["list parts of speech", "list pos categories", "all pos", "dump pos list"],
        "entities": ["PartOfSpeech"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "for pos in project.POS.GetAll():\n"
            "    name = project.POS.GetName(pos)\n"
            "    abbr = project.POS.GetAbbreviation(pos)\n"
            "    entry_count = project.POS.GetEntryCount(pos)\n"
            "    report.Info(f\"{name} ({abbr}): {entry_count} sense(s)\")\n"
        ),
        "notes": "GetEntryCount here counts senses tagged with this POS, despite the method name.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "list-pronunciations": {
        "intent": "List pronunciations recorded for entries",
        "match_terms": ["list pronunciations", "dump pronunciations", "show pronunciation forms", "entries with pronunciation"],
        "entities": ["LexEntry", "LexPronunciation"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "for entry in project.LexEntry.GetAll():\n"
            "    headword = project.LexEntry.GetHeadword(entry)\n"
            "    for pron in project.Pronunciation.GetAll(entry):\n"
            "        form = project.Pronunciation.GetForm(pron)\n"
            "        report.Info(f\"{headword}: {form}\")\n"
        ),
        "notes": "Pronunciation.GetAll takes the owning entry, unlike most other GetAll() calls which take no arguments.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "add-pronunciation-to-entry": {
        "intent": "Add a pronunciation form to an entry",
        "match_terms": ["add pronunciation", "set pronunciation form", "add ipa pronunciation", "create pronunciation"],
        "entities": ["LexEntry", "LexPronunciation"],
        "operations": ["create", "write"],
        "requires_write": True,
        "code": (
            "entry = project.LexEntry.Find(\"run\")\n"
            "if entry is None:\n"
            "    report.Error(\"Entry 'run' not found\")\n"
            "else:\n"
            "    if modifyAllowed:\n"
            "        pron = project.Pronunciation.Create(entry, \"r\\u028cn\")\n"
            "        report.Info(\"Added pronunciation\")\n"
            "    else:\n"
            "        report.Info(\"(Would add pronunciation '/r\\u028cn/')\")\n"
        ),
        "notes": "WARNING: this recipe writes to the database.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "find-senses-with-multiple-glosses-in-ws": {
        "intent": "Report senses that already have a gloss in more than one writing system",
        "match_terms": ["senses with multiple gloss writing systems", "multilingual gloss check", "gloss in multiple languages"],
        "entities": ["LexEntry", "LexSense"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "for entry in project.LexEntry.GetAll():\n"
            "    headword = project.LexEntry.GetHeadword(entry)\n"
            "    for sense in project.LexEntry.GetAllSenses(entry):\n"
            "        analysis_gloss = project.LexSense.GetGloss(sense)\n"
            "        french_gloss = project.LexSense.GetGloss(sense, project.WSHandle('fr'))\n"
            "        if analysis_gloss and french_gloss:\n"
            "            report.Info(f\"{headword}: has gloss in default + fr\")\n"
        ),
        "notes": "Adjust the second writing system tag ('fr') to whatever additional analysis WS the project uses.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
    "count-entries-total": {
        "intent": "Report the total number of entries and senses in the project",
        "match_terms": ["count entries", "how many entries", "total entries", "project size summary", "entry count"],
        "entities": ["LexEntry", "LexSense"],
        "operations": ["read", "iterate"],
        "requires_write": False,
        "code": (
            "entries = project.LexEntry.GetAll()\n"
            "entry_count = len(entries)\n"
            "sense_count = sum(project.LexEntry.GetSenseCount(e) for e in entries)\n"
            "report.Info(f\"Entries: {entry_count}\")\n"
            "report.Info(f\"Senses: {sense_count}\")\n"
        ),
        "notes": "GetAll returns an EnumerableWrapper that supports len(); no need to materialize a Python list first.",
        "source": "curated",
        "verified_against": {"flexicon": FLEXICON_VERIFIED_VERSION, "verified_by": "eval-corpus"},
    },
}
