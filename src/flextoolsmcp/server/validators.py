#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validation and detection functions for FlexToolsMCP.

Provides checks for code structure, safety, and correctness:
- Detect CUD operations (Create/Update/Delete)
- Detect module structure validity
- Check output mechanisms
- Detect errors and undefined variables
- Validate project context
"""

import re
import ast
import textwrap
from typing import Dict, List, Set, Optional, Any, Tuple

try:
    from .constants import KNOWN_OPERATIONS
except ImportError:
    from server.constants import KNOWN_OPERATIONS


# ============================================================
# Module-level compiled patterns (avoid recompilation)
# ============================================================

LCM_COLLECTION_NAMES = (
    "AnalysesOC", "SensesOS", "MorphBundlesOS", "MeaningsOC", "EntriesOC",
    "SubentriesOS", "AllomorphsOS", "ExamplesOS", "ReversalEntriesOC",
    "EvaluationsRC", "PossibilitiesOS", "SubPossibilitiesOS",
    "PronunciationsOS", "LexEntryRefsOS", "ComponentLexemesRS"
)

# Compiled regex patterns for efficiency
_PATTERN_COMMENT = re.compile(r'#.*$', re.MULTILINE)
_PATTERN_CREATE = re.compile(r'\.Create\s*\(', re.IGNORECASE)
_PATTERN_CREATE_COLLECTION = re.compile(
    r'\.(' + '|'.join(LCM_COLLECTION_NAMES) + r')\s*\.\s*Add\s*\(', re.IGNORECASE
)
_PATTERN_CREATE_GENERIC = re.compile(
    r'(entry|sense|wordform|analysis|bundle|gloss)\w*\.\w+\.\s*Add\s*\(', re.IGNORECASE
)
_PATTERN_CREATE_PROJECT = re.compile(r'project\.\w+\.Create\s*\(', re.IGNORECASE)
_PATTERN_INSERT_COLLECTION = re.compile(
    r'\.(' + '|'.join(LCM_COLLECTION_NAMES) + r')\s*\.\s*Insert\s*\(', re.IGNORECASE
)
_PATTERN_DELETE = re.compile(r'\.Delete\s*\(', re.IGNORECASE)
_PATTERN_DELETE_COLLECTION = re.compile(
    r'\.(' + '|'.join(LCM_COLLECTION_NAMES) + r')\s*\.\s*(Remove|Clear)\s*\(', re.IGNORECASE
)
_PATTERN_DELETE_PROJECT = re.compile(r'project\.\w+\.Delete\s*\(', re.IGNORECASE)
_PATTERN_SET_STRING = re.compile(r'\.set_String\s*\(', re.IGNORECASE)
_PATTERN_SET_PROPERTY = re.compile(
    r'\.Set(Occurrences|Form|Gloss|Definition|Category|Analysis)\s*\(', re.IGNORECASE
)
_PATTERN_COPY_ALTERNATIVES = re.compile(r'\.CopyAlternatives\s*\(', re.IGNORECASE)
_PATTERN_PROPERTY_ASSIGNMENT = re.compile(
    r'(entry|sense|wordform|analysis|bundle|morph|gloss|allomorph|pos)\w*\s*\.\s*'
    r'(LexemeFormOA|MorphoSyntaxAnalysisRA|SenseRA|MsaRA|MorphRA|CategoryRA|'
    r'InflectionClassRA|EntryRefsOS|ComponentLexemesRS|PrimaryLexemesRS|'
    r'MorphTypeRA|Gloss|Definition|Form|LiteralMeaning|SummaryDefinition|'
    r'Bibliography|Etymology|Comment|Note)\s*=', re.IGNORECASE
)
_PATTERN_UPDATE_PROJECT = re.compile(
    r'project\.\w+\.(Set|Update|Modify|Change|Edit|Replace)\w*\s*\(', re.IGNORECASE
)
_PATTERN_APPROVAL = re.compile(r'\.(Approve|Reject|SetApprovalStatus)\s*\(', re.IGNORECASE)
_PATTERN_REPORT_INFO = re.compile(r'report\.(Info|Warning|Error|Blank|FileURL)\s*\(')
_PATTERN_REPORT_DIRECT = re.compile(r'report\s*\(')
_PATTERN_KNOWN_OPS = re.compile(r'\b(' + '|'.join(KNOWN_OPERATIONS) + r')\b')
_PATTERN_IMPORT_STMT = re.compile(r'from\s+\w+\s+import\s+([^#\n]+)')
_PATTERN_OPERATIONS_CALL = re.compile(r'(\w+Operations)\s*(?:\(\s*\w+\s*\))?\s*\.\s*(\w+)\s*\(')

# Built-in variables (avoid recreating on every call)
_BUILTIN_NAMES = {
    "print", "len", "range", "list", "dict", "str", "int", "float", "bool",
    "True", "False", "None", "Exception", "ValueError", "TypeError",
    "for", "if", "else", "elif", "while", "def", "class",
    "project", "report", "modifyAllowed", "FLExProject"
}

# Line-aware mutation patterns (pre-compiled for efficiency).
# Each entry produces a per-line hit that can be cross-checked against
# protected ranges. Keep this set in sync with the line-blind patterns in
# detect_cud_operations() -- anything that gates execution MUST be here so
# `if modifyAllowed:` guards are honored.
# Tuple of (compiled_pattern, method_name, category)
_LIBLCM_MUTABLE_PATTERNS = [
    # Raw LCM cache mutations
    (re.compile(r'_cache\s*\.\s*CreateObject\s*\('), 'CreateObject', 'Create'),
    (re.compile(r'_cache\s*\.\s*DeleteObject\s*\('), 'DeleteObject', 'Delete'),
    (re.compile(r'_cache\s*\.\s*BeginNonUndoableTask\s*\('), 'BeginNonUndoableTask', 'BeginNonUndoableTask'),
    # Collection mutations (raw LCM)
    (re.compile(r'\.Add\s*\('), 'Add', 'Mutate'),
    (re.compile(r'\.Remove\s*\('), 'Remove', 'Mutate'),
    (re.compile(r'\.Clear\s*\('), 'Clear', 'Mutate'),
    (re.compile(r'\.MoveTo\s*\('), 'MoveTo', 'Reorder'),
    (re.compile(r'\.Insert\s*\('), 'Insert', 'Mutate'),
    # Flexicon project-accessor mutations: project.<X>.Create/Delete/Set*(...)
    # These are wrapper calls but they still mutate the DB and must be guarded.
    # Without these, project.LexEntry.Create(...) was caught only by the
    # line-blind raw_lcm_patterns path and could not be certified-as-protected.
    (re.compile(r'project\s*\.\s*\w+\s*\.\s*Create\s*\(', re.IGNORECASE), 'project.*.Create', 'Create'),
    (re.compile(r'project\s*\.\s*\w+\s*\.\s*Delete\s*\(', re.IGNORECASE), 'project.*.Delete', 'Delete'),
    (re.compile(r'project\s*\.\s*\w+\s*\.\s*(?:Set|Update|Modify|Change|Edit|Replace)\w*\s*\(', re.IGNORECASE), 'project.*.Set/Update', 'Update'),
    # Raw LCM property setters / approval methods
    (re.compile(r'\.set_String\s*\('), 'set_String', 'Update'),
    (re.compile(r'\.CopyAlternatives\s*\('), 'CopyAlternatives', 'Update'),
    (re.compile(r'\.(?:Approve|Reject|SetApprovalStatus)\s*\('), 'Approve/Reject', 'Update'),
    # Raw LCM property setter methods (exact suffixes -- does not match Operations.SetLexemeForm)
    (re.compile(r'\.Set(?:Occurrences|Form|Gloss|Definition|Category|Analysis)\s*\('), 'Set*', 'Update'),
    # Raw LCM property assignments (entry.LexemeFormOA = ..., sense.Gloss = ..., etc.)
    (re.compile(
        r'(?:entry|sense|wordform|analysis|bundle|morph|gloss|allomorph|pos)\w*\s*\.\s*'
        r'(?:LexemeFormOA|MorphoSyntaxAnalysisRA|SenseRA|MsaRA|MorphRA|CategoryRA|'
        r'InflectionClassRA|EntryRefsOS|ComponentLexemesRS|PrimaryLexemesRS|'
        r'MorphTypeRA|Gloss|Definition|Form|LiteralMeaning|SummaryDefinition|'
        r'Bibliography|Etymology|Comment|Note)\s*=(?!=)',
        re.IGNORECASE
    ), 'property=', 'Update'),
]


# ============================================================
# Utility functions (shared across validators)
# ============================================================

def _strip_comments(code: str) -> str:
    """Remove Python comments from code to avoid false positives in pattern matching."""
    return _PATTERN_COMMENT.sub('', code)


def _is_line_protected(line_num: int, protected_ranges: List[tuple]) -> bool:
    """Check if a line number falls within any protected range."""
    return any(start <= line_num <= end for start, end in protected_ranges)


def validate_server_state() -> dict:
    """Validate that the server's own modules and state are properly initialized.

    This preflight check ensures the server itself is ready before attempting to
    execute user code. Catches import errors and uninitialized state that would
    otherwise cause confusing runtime errors.

    Returns:
        {
            "is_healthy": bool,
            "issues": list,  # List of (severity, message) tuples
            "missing_modules": list,  # Modules that failed to import
            "uninitialized_state": list,  # State variables that are None
        }
    """
    issues = []
    missing_modules = []
    uninitialized_state = []

    # Check that critical server modules can be imported
    critical_modules = [
        ("casting_helpers", "Casting helpers for polymorphic type handling"),
        ("subprocess_helpers", "Subprocess execution wrapper"),
    ]

    for module_name, description in critical_modules:
        try:
            # Try absolute import first
            __import__(f"server.{module_name}")
        except ImportError:
            try:
                # Try relative import from current package
                __import__(module_name)
            except ImportError:
                missing_modules.append(module_name)
                issues.append((
                    "error",
                    f"Missing critical module: {module_name} ({description})"
                ))

    # Check that kernel state is initialized
    try:
        from .kernel import get_api_index, get_operations_logger, get_pattern_tracker
    except ImportError:
        from server.kernel import get_api_index, get_operations_logger, get_pattern_tracker

    # Check API index
    api_index = get_api_index()
    if api_index is None:
        uninitialized_state.append("api_index")
        issues.append((
            "warning",
            "API index not yet loaded (will be loaded on first API discovery)"
        ))

    # Check operations logger
    operations_logger = get_operations_logger()
    if operations_logger is None:
        uninitialized_state.append("operations_logger")
        issues.append((
            "error",
            "Operations logger not initialized (required for logging)"
        ))

    # Check pattern tracker
    pattern_tracker = get_pattern_tracker()
    if pattern_tracker is None:
        uninitialized_state.append("pattern_tracker")
        issues.append((
            "warning",
            "Pattern tracker not initialized (pattern analysis will be unavailable)"
        ))

    # Issue #57 (C): surface stale lock warnings detected at startup.
    # The api_index stores them as startup_lock_warnings (set in server.main()).
    startup_lock_warnings = getattr(api_index, "startup_lock_warnings", [])
    for lock_msg in startup_lock_warnings:
        issues.append(("warning", lock_msg))

    return {
        "is_healthy": len([i for i in issues if i[0] == "error"]) == 0,
        "issues": issues,
        "missing_modules": missing_modules,
        "uninitialized_state": uninitialized_state,
    }


def detect_cud_operations(code: str) -> dict:
    """Detect Create, Update, Delete operations in code that modify the FLEx database.

    Only detects actual Flexicon/LCM database modifications, not:
    - Local Python list operations (results.append(), etc.)
    - Variable assignments to local variables
    - Comments containing keywords

    Returns dict with:
      - is_cud: bool - whether CUD operations detected
      - operations: list - detected operation types
      - risks: list - specific risks identified
      - affected_types: list - data types that may be affected
    """
    operations = []
    risks = []
    affected = set()

    # Remove comments once for all pattern matching
    code_no_comments = _strip_comments(code)

    # === CREATE operations (actual database writes) ===
    # All patterns are pre-compiled at module level for efficiency
    create_patterns = [
        (_PATTERN_CREATE, 'Create()'),
        (_PATTERN_CREATE_COLLECTION, 'collection.Add()'),
        (_PATTERN_CREATE_GENERIC, 'Add()'),
        (_PATTERN_INSERT_COLLECTION, 'Insert()'),
        (_PATTERN_CREATE_PROJECT, 'project.*.Create()'),
    ]

    for pattern, label in create_patterns:
        if pattern.search(code_no_comments):
            operations.append(f"CREATE ({label})")
            risks.append("New data will be added to the database")
            break

    # === UPDATE operations (actual database writes) ===
    # All patterns are pre-compiled at module level for efficiency
    update_patterns = [
        (_PATTERN_SET_STRING, 'set_String()'),
        (_PATTERN_SET_PROPERTY, 'Set*()'),
        (_PATTERN_COPY_ALTERNATIVES, 'CopyAlternatives()'),
        (_PATTERN_PROPERTY_ASSIGNMENT, 'property assignment'),
        (_PATTERN_UPDATE_PROJECT, 'project.*.Set/Update()'),
        (_PATTERN_APPROVAL, 'approval change'),
    ]

    for pattern, label in update_patterns:
        if pattern.search(code_no_comments):
            operations.append(f"UPDATE ({label})")
            risks.append("Existing data will be modified")
            break

    # === DELETE operations (actual database writes) ===
    # All patterns are pre-compiled at module level for efficiency
    delete_patterns = [
        (_PATTERN_DELETE, 'Delete()'),
        (_PATTERN_DELETE_COLLECTION, 'collection.Remove/Clear()'),
        (_PATTERN_DELETE_PROJECT, 'project.*.Delete()'),
    ]

    for pattern, label in delete_patterns:
        if pattern.search(code_no_comments):
            operations.append(f"DELETE ({label})")
            risks.append("Data will be permanently removed")
            break

    # Identify affected data types (only if CUD operations detected)
    if operations:
        type_patterns = {
            r'\bentry\b': 'Lexicon entries',
            r'\bsense\b': 'Senses',
            r'\bexample\b': 'Example sentences',
            r'\bgloss\b': 'Glosses',
            r'\bdefinition\b': 'Definitions',
            r'\bpos\b': 'Parts of speech',
            r'\ballomorph\b': 'Allomorphs',
            r'\breversal\b': 'Reversal entries',
            r'\btext\b': 'Texts',
            r'\bwordform\b': 'Wordforms',
            r'\banalysis\b': 'Analyses',
            r'\bmorph\s*bundle\b': 'Morph bundles',
        }

        for pattern, label in type_patterns.items():
            if re.search(pattern, code_no_comments, re.IGNORECASE):
                affected.add(label)

    return {
        "is_cud": len(operations) > 0,
        "operations": operations,
        "risks": risks,
        "affected_types": list(affected) if affected else ["Unknown - review code carefully"]
    }


def detect_module_structure(code: str) -> dict:
    """Check if code is in valid FlexTools module format.

    A valid FlexTools module must have:
    - from flextoolslib import statement
    - def Main(project, report, modifyAllowed): function
    - FlexToolsModuleClass(...) instantiation
    - docs = {...} dictionary with FTM_* keys

    Returns dict with:
      - is_valid_module: bool - whether all required elements are present
      - missing_elements: list - what's missing (for error messaging)
    """
    missing = []

    # Check for flextoolslib import
    if "from flextoolslib import" not in code:
        missing.append("from flextoolslib import *")

    # Check for Main function with correct signature
    if not re.search(r'^\s*def Main\s*\(', code, re.MULTILINE):
        missing.append("def Main(project, report, modifyAllowed):")

    # Check for FlexToolsModuleClass instantiation
    if "FlexToolsModuleClass(" not in code:
        missing.append("FlexToolsModule = FlexToolsModuleClass(Main, docs)")

    # Check for docs dictionary
    if not re.search(r'^\s*docs\s*=\s*\{', code, re.MULTILINE):
        missing.append("docs = {FTM_Name: ..., FTM_Version: ..., ...}")

    return {
        "is_valid_module": len(missing) == 0,
        "missing_elements": missing
    }


def detect_partial_module_structure(code: str, code_tree: Optional[ast.AST] = None) -> dict:
    """Detect code that is module-shaped but missing scaffolding.

    Fires when `def Main(...)` is present (the user is clearly authoring a
    module) but the surrounding scaffolding (docs dict, FlexToolsModule
    binding) is absent. Bare snippets without `Main` are not flagged --
    they're a legitimate use of the unified runner.

    The signal we want to catch is Dennis's case: a multi-function file with
    `def Main` that runs in the MCP runner only because the runner is
    permissive, but would NOT load if saved as a real FlexTools module file.

    The flextoolslib import is intentionally not checked: the MCP runner
    injects a synthetic flextoolslib module so the import is unnecessary in
    this context. We only flag the parts that matter for `FlexToolsModule
    = FlexToolsModuleClass(Main, docs)` to actually exist.

    Args:
        code: Source code string.
        code_tree: Optional pre-parsed AST (avoids redundant parsing when the
            caller already parsed the code).

    Returns:
        dict with:
          is_partial_module: bool - has Main but missing scaffolding
          has_main: bool - whether `def Main(...)` is present
          missing_elements: list - what's missing (empty if not partial)
          suggestion: str - one-line guidance for the AI
    """
    has_main = False
    if code_tree is None:
        try:
            code_tree = ast.parse(code)
        except SyntaxError:
            return {
                "is_partial_module": False,
                "has_main": False,
                "missing_elements": [],
                "suggestion": "",
            }

    for node in ast.walk(code_tree):
        if isinstance(node, ast.FunctionDef) and node.name == "Main":
            has_main = True
            break

    if not has_main:
        return {
            "is_partial_module": False,
            "has_main": False,
            "missing_elements": [],
            "suggestion": "",
        }

    missing = []
    if not re.search(r'^\s*docs\s*=\s*\{', code, re.MULTILINE):
        missing.append("docs = {FTM_Name: ..., FTM_Synopsis: ..., FTM_ModifiesDB: ..., FTM_Description: ...}")
    if "FlexToolsModuleClass(" not in code:
        missing.append("FlexToolsModule = FlexToolsModuleClass(Main, docs)")

    if not missing:
        return {
            "is_partial_module": False,
            "has_main": True,
            "missing_elements": [],
            "suggestion": "",
        }

    suggestion = (
        "Code defines `Main(...)` but is missing FlexTools module scaffolding. "
        "If this is meant to be a saved FlexTools module file, call "
        "flextools_get_module_template first and copy in the missing pieces. "
        "If this is just a quick test, drop the `def Main:` wrapper and run the "
        "body as a bare snippet, or pass skip_module_check=True to run it as-is."
    )
    return {
        "is_partial_module": True,
        "has_main": True,
        "missing_elements": missing,
        "suggestion": suggestion,
    }


def _project_accessors(api_index: Optional[Any] = None) -> List[str]:
    """Valid project.<X> accessor names.

    Reads the real FLExProject property list from the flexicon index when
    available, unioned with the legacy KNOWN_OPERATIONS-derived names so
    accessors like LexSense (Operations-class shorthand) keep validating.
    Falls back to the KNOWN_OPERATIONS-derived list alone if the index is
    unavailable or has no FLExProject properties.
    """
    legacy = [op[: -len("Operations")] for op in KNOWN_OPERATIONS if op.endswith("Operations")]
    if api_index is None:
        return legacy
    flexicon = getattr(api_index, "flexicon", None) or {}
    entities = flexicon.get("entities") or {}
    flex_project = entities.get("FLExProject") or {}
    real_props = [p.get("name") for p in flex_project.get("properties", []) if p.get("name")]
    if not real_props:
        return legacy
    seen = set()
    merged: List[str] = []
    for name in list(real_props) + legacy:
        if name and name not in seen:
            seen.add(name)
            merged.append(name)
    return merged


def _operation_method_names(api_index: Optional[Any], operations_class: str) -> List[str]:
    """Methods on an Operations class, looked up in the flexicon index."""
    if api_index is None:
        return []
    flexicon = getattr(api_index, "flexicon", None) or {}
    entity = (flexicon.get("entities") or {}).get(operations_class, {})
    return [m.get("name", "") for m in entity.get("methods", []) if m.get("name")]


def _suggest_attribute_matches(attr_name: str, candidates: List[str], cutoff: float = 0.5) -> List[str]:
    """Find close-match candidates for a misspelled attribute name.

    Combines difflib similarity with a camelcase-acronym fallback that catches
    abbreviations like GetPOS -> GetPartOfSpeech.
    """
    import difflib

    matches = difflib.get_close_matches(attr_name, candidates, n=3, cutoff=cutoff)
    if matches:
        return matches

    # Acronym fallback: trailing uppercase letters of attr match candidate's
    # camelcase initials (e.g., POS in GetPOS -> initials of GetPartOfSpeech).
    upper_letters = "".join(c for c in attr_name if c.isupper())
    if len(upper_letters) < 2:
        return []
    acronym_hits = []
    for cand in candidates:
        initials = "".join(re.findall(r"(?:^|[a-z])([A-Z])", cand)) + "".join(
            c for c in cand if c.isupper()
        )
        if upper_letters in initials:
            acronym_hits.append(cand)
    return acronym_hits[:3]


# Issue #39: Python 3.10+ appends "Did you mean: 'X'?" to AttributeError /
# NameError messages. This is authoritative -- it reflects the attributes that
# actually exist on the live runtime object -- so for a typo (e.g. ILexDb has
# no 'EntriesOC', did you mean 'Entries') it beats any statically-guessed cast.
_PATTERN_PY_DID_YOU_MEAN = re.compile(r"Did you mean:?\s*'([^']+)'")


def extract_python_did_you_mean(error_msg: str) -> Optional[str]:
    """Pull the name out of Python's native "Did you mean: 'X'?" suffix.

    Returns the suggested name, or None if the error carries no such suffix.
    """
    if not error_msg:
        return None
    match = _PATTERN_PY_DID_YOU_MEAN.search(error_msg)
    return match.group(1) if match else None


def detect_unknown_attribute_error(error_msg: str, api_index: Optional[Any] = None) -> dict:
    """Detect AttributeErrors on Flexicon wrapper accessors and suggest correct names.

    Targets the common "namespace thrash" pattern where users guess at accessor or
    method names (project.LexEntries -> project.LexEntry, GetPOS -> GetPartOfSpeech).

    Returns dict with:
      - has_suggestion: bool
      - object_type, attribute_name: parsed from the error
      - did_you_mean: list[str] of nearest valid names
      - suggestion: human-readable hint
    """
    pattern = r"'(\w+)'\s+object\s+has\s+no\s+attribute\s+'(\w+)'"
    match = re.search(pattern, error_msg)
    if not match:
        return {"has_suggestion": False}

    object_type, attr_name = match.groups()
    candidates: List[str] = []
    scope = ""

    if object_type in ("FLExProject", "FLExProjectImpl"):
        candidates = _project_accessors(api_index)
        scope = "project"
    elif object_type in KNOWN_OPERATIONS:
        candidates = _operation_method_names(api_index, object_type)
        scope = object_type

    if not candidates:
        return {"has_suggestion": False, "object_type": object_type, "attribute_name": attr_name}

    matches = _suggest_attribute_matches(attr_name, candidates)
    if not matches:
        return {"has_suggestion": False, "object_type": object_type, "attribute_name": attr_name}

    if scope == "project":
        suggestion = f"'{attr_name}' is not a project accessor. Did you mean: {', '.join('project.' + m for m in matches)}?"
    else:
        suggestion = f"'{scope}.{attr_name}' is not a method on {scope}. Did you mean: {', '.join(scope + '.' + m for m in matches)}?"

    return {
        "has_suggestion": True,
        "object_type": object_type,
        "attribute_name": attr_name,
        "did_you_mean": matches,
        "suggestion": suggestion,
    }


# Issue #69: the accessor/method rejection gate must not surface low-confidence
# matches as authoritative "did you mean" fixes. difflib's cutoff=0.7 already
# guards the primary path, but the acronym fallback in _suggest_attribute_matches
# can return a garbage candidate (e.g. LangProject -> PossibilityLists, because
# the acronym "LP" appears in the scrambled initials of "PossibilityList(s)") at
# a real similarity ratio of ~0.15. A wrong-but-confident suggestion is worse
# than none, so any candidate whose measured ratio is below this floor is
# dropped and the code is left for runtime to handle. Calibration: genuine
# accessor typos we DO want to catch score >=0.78 (LexEntries->LexEntry 0.78,
# ReversalEntrie->ReversalEntries 0.97); the false LangProject match is 0.15.
_MIN_CHAIN_MATCH_RATIO = 0.5


def detect_invalid_project_chains(code_tree: Optional[ast.AST], api_index: Optional[Any] = None) -> dict:
    """Pre-flight: scan AST for project.<X> / project.<X>.<Y> references and reject typos.

    Conservative by design: only rejects when difflib finds a HIGH-confidence
    (>=0.7) match against known accessor / method names, AND the measured
    similarity ratio of the top candidate clears _MIN_CHAIN_MATCH_RATIO (issue
    #69 -- suppress low-confidence acronym-fallback matches). If a name is
    unknown but has no confident close match, we let runtime handle it -- avoids
    false positives on dynamic / direct project methods we don't have in the
    index.

    Returns dict with:
      - has_invalid: bool
      - issues: list of dicts with kind/expr/did_you_mean/suggestion
      - suggestion: combined human-readable hint
    """
    if code_tree is None:
        return {"has_invalid": False, "issues": []}

    accessors = set(_project_accessors(api_index))
    # Direct project methods typically start with a verb prefix; treat names
    # with these prefixes as definitely-not-accessors (e.g., GetWritingSystems)
    # and skip them so we don't false-positive against the type-name accessors
    # (WritingSystem, LexEntry). Issue #34: removed blanket "Lexicon" skip --
    # replace it with an enumerated set of known Lexicon* method names so that
    # typos like LexiconGetSenses (should be LexiconGetSense) still get caught.
    method_prefixes = ("Get", "Set", "Has", "Is", "Add", "Remove", "Create",
                       "Delete", "Update", "Find", "Make", "Build", "To", "From")

    # Build enumerated set of known Lexicon* direct-project methods from index.
    # Only names actually in the index pass as valid; others get fuzzy-checked.
    known_lexicon_methods: Set[str] = set()
    if api_index is not None:
        flexicon = getattr(api_index, "flexicon", None) or {}
        flex_project = (flexicon.get("entities") or {}).get("FLExProject", {})
        for m in flex_project.get("methods", []):
            name = m.get("name", "")
            if name.startswith("Lexicon"):
                known_lexicon_methods.add(name)
    issues: List[Dict[str, Any]] = []

    for node in ast.walk(code_tree):
        if not isinstance(node, ast.Attribute):
            continue
        # project.<X>: node.value is Name('project')
        if isinstance(node.value, ast.Name) and node.value.id == "project":
            x = node.attr
            if x in accessors:
                continue
            if x.startswith(method_prefixes):
                continue  # Looks like a direct project method, not an accessor typo
            # Issue #34: Lexicon* names only skip if they're a known indexed method.
            # Unknown Lexicon* names (e.g. LexiconGetSenses typo) fall through.
            if x.startswith("Lexicon") and x in known_lexicon_methods:
                continue
            # Only reject if a *high-confidence* close match exists in the accessor set.
            # Otherwise this might be a direct project method we don't enumerate.
            close = _suggest_attribute_matches(x, list(accessors), cutoff=0.7)
            if close:
                # Compute actual ratio for the top candidate so auto-fix can
                # enforce the >=0.9 threshold (issue #46).
                import difflib as _dl
                _ratio = _dl.SequenceMatcher(None, x.lower(), close[0].lower()).ratio()
                if _ratio < _MIN_CHAIN_MATCH_RATIO:
                    # Issue #69: low-confidence match (typically from the acronym
                    # fallback) -- don't reject valid code toward a wrong name.
                    continue
                issues.append({
                    "kind": "accessor",
                    "expr": f"project.{x}",
                    "typo_attr": x,
                    "lineno": node.lineno,
                    "col_offset": node.col_offset,
                    "did_you_mean": close,
                    "match_ratio": _ratio,
                    "suggestion": f"'project.{x}' is not a valid accessor. Did you mean: {', '.join('project.' + c for c in close)}?",
                })
        # project.<X>.<Y>: node.value is Attribute(value=Name('project'), attr=X)
        elif (
            isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "project"
        ):
            x = node.value.attr
            y = node.attr
            if x not in accessors:
                continue  # outer accessor will be flagged separately if invalid
            ops_class = f"{x}Operations"
            methods = _operation_method_names(api_index, ops_class)
            if not methods or y in methods:
                continue
            close = _suggest_attribute_matches(y, methods, cutoff=0.7)
            if close:
                import difflib as _dl
                _ratio = _dl.SequenceMatcher(None, y.lower(), close[0].lower()).ratio()
                if _ratio < _MIN_CHAIN_MATCH_RATIO:
                    # Issue #69: low-confidence match -- leave for runtime.
                    continue
                issues.append({
                    "kind": "method",
                    "expr": f"project.{x}.{y}",
                    "typo_attr": y,
                    "lineno": node.lineno,
                    "col_offset": node.col_offset,
                    "did_you_mean": close,
                    "match_ratio": _ratio,
                    "suggestion": f"'{y}' is not a method on {ops_class}. Did you mean: {', '.join(f'project.{x}.{c}' for c in close)}?",
                })

    # Deduplicate by expression (same typo can appear many times)
    seen = set()
    unique_issues: List[Dict[str, Any]] = []
    for issue in issues:
        if issue["expr"] in seen:
            continue
        seen.add(issue["expr"])
        unique_issues.append(issue)

    if not unique_issues:
        return {"has_invalid": False, "issues": []}

    return {
        "has_invalid": True,
        "issues": unique_issues,
        "suggestion": " ".join(i["suggestion"] for i in unique_issues),
    }


def _accessor_to_ops_map(api_index: Optional[Any]) -> Dict[str, str]:
    """Map project.<accessor> name -> Operations class name from the API index.

    Used to figure out what entity a `project.Senses.GetAll()` call actually needs
    discovered (LexSenseOperations) -- a naive `f"{accessor}Operations"` is wrong
    for most accessors because flexicon names diverge (Senses->LexSense, Wordforms->
    WfiWordform, PhonRules->PhonologicalRule, ...).
    """
    if api_index is None:
        return {}
    flexicon = getattr(api_index, "flexicon", None) or {}
    fp = (flexicon.get("entities") or {}).get("FLExProject", {})
    mapping: Dict[str, str] = {}
    for prop in fp.get("properties", []) or []:
        name = prop.get("name") or ""
        ret = prop.get("return_type") or ""
        if name and ret.endswith("Operations"):
            mapping[name] = ret
    return mapping


def detect_candidate_entities(
    code_tree: Optional[ast.AST], api_index: Optional[Any] = None, limit: int = 3
) -> List[str]:
    """Identify top-N entity names referenced in code that match the API index.

    Used by the api_discovery_required gate (Issue #29) to inline get_object_api
    docs for likely entities when discovery hasn't happened yet, giving the LLM
    a single-round-trip recovery path.

    Walks the AST for Name nodes (e.g. `LexEntryOperations.GetAll(...)` ->
    'LexEntryOperations') and Attribute nodes rooted at `project.` (e.g.
    `project.LexSense.GetGloss(...)` -> mapped via the index to
    'LexSenseOperations'). Names are scored by occurrence count so the most
    central entity ranks first.
    """
    if code_tree is None:
        return []
    flexicon = getattr(api_index, "flexicon", None) or {}
    entities = flexicon.get("entities") or {}
    if not entities:
        # Fallback to KNOWN_OPERATIONS so the gate at least returns plausible
        # candidates when the index hasn't been loaded yet.
        entity_set: Set[str] = set(KNOWN_OPERATIONS)
    else:
        entity_set = set(entities.keys())

    accessor_to_ops = _accessor_to_ops_map(api_index)
    counts: Dict[str, int] = {}

    for node in ast.walk(code_tree):
        if isinstance(node, ast.Name) and node.id in entity_set:
            counts[node.id] = counts.get(node.id, 0) + 1
        elif isinstance(node, ast.Attribute):
            # project.<Accessor>... -> map to Operations class via index
            if isinstance(node.value, ast.Name) and node.value.id == "project":
                accessor = node.attr
                ops_class = accessor_to_ops.get(accessor) or f"{accessor}Operations"
                if ops_class in entity_set:
                    counts[ops_class] = counts.get(ops_class, 0) + 1

    # Sort by count desc, then by name for stability.
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [name for name, _ in ranked[:limit]]


# Naming: `flexicon` is the current package name; `flexlibs2` is its
# deprecated import alias, which still resolves at runtime, so user code that
# imports from either should satisfy the discovery gate.
_FLEXICON_IMPORT_ROOTS = ("flexicon", "flexlibs2")


def _collect_flexicon_imports(code_tree: Optional[ast.AST]) -> Set[str]:
    """Return the set of names imported from the flexicon package.

    Matches (and the deprecated `flexlibs2` alias, which still resolves):
        from flexicon import SegmentOperations           -> {'SegmentOperations'}
        from flexicon import SegmentOperations as SO     -> {'SegmentOperations'}
        from flexicon.foo import Bar                     -> {'Bar'}
        import flexicon.SegmentOperations                -> {'SegmentOperations'}
        import flexicon.SegmentOperations as SO          -> {'SegmentOperations'}

    Why we key on the *original* name (not the alias): the undiscovered-entity
    gate compares against API-index entity names (SegmentOperations), so an
    `import ... as SO` should still satisfy the gate's "this entity is imported"
    check.
    """
    if code_tree is None:
        return set()
    names: Set[str] = set()
    for node in ast.walk(code_tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in _FLEXICON_IMPORT_ROOTS or any(
                module.startswith(root + ".") for root in _FLEXICON_IMPORT_ROOTS
            ):
                for alias in node.names:
                    if alias.name and alias.name != "*":
                        names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name and any(
                    alias.name.startswith(root + ".") for root in _FLEXICON_IMPORT_ROOTS
                ):
                    # import flexicon.SegmentOperations [as SO]
                    last = alias.name.rsplit(".", 1)[-1]
                    if last:
                        names.add(last)
    return names


def detect_undiscovered_entities(
    code_tree: Optional[ast.AST],
    session_state,
    api_index: Optional[Any] = None,
) -> dict:
    """Per-entity discovery gate: reject code that uses Operations classes / project
    accessors the assistant never validated via flextools_get_object_api.

    Why: the broader api_discovery_required gate only checks "anything ever discovered
    in this session." Once the assistant calls get_object_api for one entity, it can
    use any other entity without discovery -- which led to hallucinated method names
    and silent failures (e.g., project.POSOperations.GetAll() typo, or project.Senses
    used after only LexEntry was discovered).

    Detects:
      - Operations class constructor / classmethod usage: POSOperations(project)
      - Project accessor usage: project.POS, project.LexEntry, project.Senses, ...
        (resolved through the API index, so project.Senses correctly demands
        LexSenseOperations discovery rather than a fictional SensesOperations.)

    A use is satisfied if either the canonical accessor name (POS, LexEntry, Senses)
    OR the Operations-class form (POSOperations, LexSenseOperations) appears in the
    session's validated_apis or as the entity-half of any discovered_apis key.

    Returns dict with:
      - has_undiscovered: bool
      - undiscovered: list[str] -- entity names that need discovery
      - suggestion: human-readable hint with exact tool calls to make
      - imported_undiscovered: list[str] -- undiscovered entities that were
        explicitly imported from flexicon (subset of `undiscovered`). Used by
        the execution handler to inline get_object_api docs and clarify that
        imports alone don't satisfy the discovery gate.
    """
    result = {
        "has_undiscovered": False,
        "undiscovered": [],
        "suggestion": "",
        "imported_undiscovered": [],
    }
    if code_tree is None:
        return result

    accessor_to_ops = _accessor_to_ops_map(api_index)
    # Reverse for "did the assistant call get_object_api(object_type='Senses')?" -> LexSenseOperations
    ops_to_accessor: Dict[str, str] = {v: k for k, v in accessor_to_ops.items()}

    # Build the set of "satisfied" entity names. Accept accessor form, ops-class form,
    # and (when known) the cross-form via the api_index mapping.
    validated = set(session_state.validated_apis)
    discovered_entities = set()
    for api_key in session_state.discovered_apis:
        if "." in api_key:
            discovered_entities.add(api_key.split(".", 1)[0])

    # Issue #31: treat `from flexicon import XOperations` as implicit discovery.
    # Importing an operations class means the user deliberately brought the API
    # surface into scope -- the discovery gate's purpose (ensuring the LLM has
    # seen real method signatures) is satisfied by the import statement itself.
    implicit_discovered = _collect_flexicon_imports(code_tree)
    implicit_accessor_forms: Set[str] = set()
    for name in implicit_discovered:
        if name.endswith("Operations"):
            implicit_accessor_forms.add(name[: -len("Operations")])
        if name in ops_to_accessor:
            implicit_accessor_forms.add(ops_to_accessor[name])
    implicit_all = implicit_discovered | implicit_accessor_forms

    satisfied: Set[str] = set()
    for v in validated | discovered_entities | implicit_all:
        satisfied.add(v)
        # Cross-link accessor <-> ops class via the index when possible
        if v in accessor_to_ops:
            satisfied.add(accessor_to_ops[v])
        if v in ops_to_accessor:
            satisfied.add(ops_to_accessor[v])
        # Naive bidirectional fallback (handles POS/POSOperations even if the index
        # missed the property for some reason).
        if v.endswith("Operations"):
            satisfied.add(v[: -len("Operations")])
        else:
            satisfied.add(v + "Operations")

    # Walk AST for entity references.
    used_entities: Set[str] = set()
    for node in ast.walk(code_tree):
        # POSOperations(project), LexEntryOperations.GetAll(project), etc.
        if isinstance(node, ast.Name) and node.id in KNOWN_OPERATIONS:
            used_entities.add(node.id)
        elif isinstance(node, ast.Attribute):
            # project.<Accessor>...
            if isinstance(node.value, ast.Name) and node.value.id == "project":
                accessor = node.attr
                # Prefer the real index mapping; fall back to naive ops-class form
                # so the gate still works if the index hasn't been loaded yet.
                ops_class = accessor_to_ops.get(accessor) or f"{accessor}Operations"
                if ops_class in KNOWN_OPERATIONS:
                    used_entities.add(ops_class)

    undiscovered = sorted(e for e in used_entities if e not in satisfied)
    if not undiscovered:
        return result

    # Issue #20: identify undiscovered entities that the user actually imported.
    # The discovery gate is sometimes confusing because `from flexicon import X`
    # populates Python's namespace but NOT session_state.discovered_apis -- the
    # rejection then reads as "we couldn't find X" even though X is right there
    # in the import line. Pulling the import set lets the rejection say so
    # explicitly and lets the execution handler inline a get_object_api result
    # for single-import recovery.
    imported_names = _collect_flexicon_imports(code_tree)
    # Also accept the accessor-form of imported names (e.g. user imports
    # LexSenseOperations -> also satisfies project.LexSense / 'Senses' callouts).
    accessor_forms_of_imports: Set[str] = set()
    for name in imported_names:
        if name.endswith("Operations"):
            accessor_forms_of_imports.add(name[: -len("Operations")])
        if name in ops_to_accessor:
            accessor_forms_of_imports.add(ops_to_accessor[name])
    imported_or_accessor = imported_names | accessor_forms_of_imports
    imported_undiscovered = sorted(e for e in undiscovered if e in imported_or_accessor)

    suggestions = "\n  - ".join(
        f"flextools_get_object_api(object_type='{e}')" for e in undiscovered
    )
    base_msg = (
        f"Code uses {len(undiscovered)} entity/entities that were not validated via "
        f"flextools_get_object_api in this session: {', '.join(undiscovered)}.\n\n"
        f"Call these first so you have the real signatures (this prevents hallucinated "
        f"method names like project.POSOperations.GetAll(), which silently fail):\n\n"
        f"  - {suggestions}\n\n"
        f"Tip: get_object_api accepts either form -- 'POS' or 'POSOperations' both work."
    )
    if imported_undiscovered:
        # Surface the import-vs-discovery distinction in plain language so the
        # LLM doesn't loop on "but I imported it" reasoning. Single entity gets
        # a tailored sentence; multiple imports get a comma-joined version.
        entity_label = imported_undiscovered[0]
        if len(imported_undiscovered) == 1:
            import_clarifier = (
                f"Found `from flexicon import {entity_label}` in your code, but the "
                f"discovery gate also requires calling "
                f"`flextools_get_object_api(object_type='{entity_label}')` so you've "
                # Issue #20 follow-up: the gate's purpose is putting the API
                # surface in the LLM's context (loading), not validating Python.
                f"loaded the method shapes into context. Imports alone aren't enough."
            )
        else:
            entity_list = ", ".join(imported_undiscovered)
            import_clarifier = (
                f"Found `from flexicon import ...` for [{entity_list}] in your code, "
                f"but the discovery gate also requires calling "
                f"flextools_get_object_api for each so you've loaded the method "
                f"shapes into context. Imports alone aren't enough."
            )
        base_msg = import_clarifier + "\n\n" + base_msg

    result["has_undiscovered"] = True
    result["undiscovered"] = undiscovered
    result["imported_undiscovered"] = imported_undiscovered
    result["suggestion"] = base_msg
    return result


def detect_polymorphic_error(error_msg: str, casting_index: Optional[Dict] = None) -> dict:
    """Detect polymorphic attribute errors and suggest resolve_property.

    Identifies errors like "'IPhSegmentRule' object has no attribute 'RightHandSidesOS'"
    and suggests using resolve_property to find the correct property and casting.

    Returns dict with:
      - is_polymorphic_error: bool - whether this looks like a polymorphic issue
      - object_type: str - the object type from the error (e.g., 'IPhSegmentRule')
      - property_name: str - the missing property (e.g., 'RightHandSidesOS')
      - suggestion: str - suggested resolve_property call
      - rewrite: str | None - inline cast rewrite if casting_index resolved it
      - imports_needed: list[str] - imports to add alongside the rewrite
    """
    # Match pattern: 'ObjectType' object has no attribute 'PropertyName'
    pattern = r"'(\w+)'\s+object\s+has\s+no\s+attribute\s+'(\w+)'"
    match = re.search(pattern, error_msg)

    if match:
        object_type, property_name = match.groups()

        # Issue #36: mirror the pre-flight casting lookup so runtime errors carry
        # the same self-healing payload (rewrite + imports_needed) that pre-flight
        # rejections do, eliminating an extra round-trip.
        rewrite: Optional[str] = None
        imports_needed: List[str] = []
        if casting_index:
            casting_props = (casting_index or {}).get("properties") or {}
            if property_name in casting_props:
                cast_info = casting_props[property_name]
                available_on = cast_info.get("available_on") or cast_info.get("defined_on") or []
                cast_iface = _pick_cast_interface(
                    property_name, available_on, casting_index, object_type.lower()
                )
                if cast_iface:
                    rewrite = f"{cast_iface}(obj).{property_name}"
                    imports_needed = _imports_for_interface(cast_iface)

        return {
            "is_polymorphic_error": True,
            "object_type": object_type,
            "property_name": property_name,
            "rewrite": rewrite,
            "imports_needed": imports_needed,
            # Issue #22: nudge at the preflight rewrite path first; resolve_property
            # is the secondary escape hatch (e.g. for chained-receiver cases the
            # rewriter deliberately skips).
            "suggestion": (
                f"Re-submit your code -- the preflight casting validator should "
                f"now flag '{property_name}' on '{object_type}' with an inline "
                f"`rewrite` (the cast-wrapped expression) and `imports_needed`. "
                f"If the preflight doesn't catch it (e.g. chained receiver), call "
                f"flextools_resolve_property(property_name='{property_name}', "
                f"context_entity='{object_type}') as a fallback."
            ),
        }

    return {"is_polymorphic_error": False}


def _collect_all_imported_names(code: str) -> Optional[Set[str]]:
    """Collect every name bound by an import in `code` via AST.

    Issue #41: the old regex (`from \\w+ import ([^#\\n]+)`) only saw the first
    physical line of an import, so parenthesized / multi-line forms like

        from flexicon import (
            SegmentOperations,
            WordformOperations,
        )

    left SegmentOperations / WordformOperations out of the imported set and the
    missing-imports gate then false-rejected valid code. AST parsing normalizes
    all import shapes (parenthesized, multi-line, aliased) into one name list.

    Both the original name and any alias are recorded (the missing-imports gate
    compares against the original Operations-class names). Returns None when the
    code can't be parsed, signalling the caller to fall back to the regex scan.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return None
    names: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name and alias.name != "*":
                    names.add(alias.name)
                if alias.asname:
                    names.add(alias.asname)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    names.add(alias.name)
                    names.add(alias.name.rsplit(".", 1)[-1])
                if alias.asname:
                    names.add(alias.asname)
    return names


def detect_missing_operations_imports(code: str, api_mode: str) -> dict:
    """Detect Operations classes used without imports and suggest what to add.

    Args:
        code: User's module/operation code
        api_mode: Selected API mode ('flexlibs_stable', 'flexicon', 'liblcm')

    Returns:
        dict with 'missing_imports', 'has_missing', and 'suggestion'
    """
    result = {
        "missing_imports": [],
        "has_missing": False,
        "suggestion": ""
    }

    # Find all words that match Operations class names using compiled pattern
    matches = _PATTERN_KNOWN_OPS.findall(code)

    if not matches:
        return result

    # Issue #41: collect imported names via AST so parenthesized / multi-line
    # imports are seen. Fall back to the single-line regex only when the code
    # can't be parsed (it can't run in that state either, but the regex keeps
    # behavior unchanged for the unparsable path).
    imported = _collect_all_imported_names(code)
    if imported is None:
        import_lines = _PATTERN_IMPORT_STMT.findall(code)
        imported = set()
        for line in import_lines:
            # Parse comma-separated imports; strip `X as Y` aliases to the name.
            parts = [p.strip().split(" as ")[0].strip() for p in line.split(',')]
            imported.update(parts)

    # Find missing imports
    used = set(matches)
    missing = used - imported

    if missing:
        result["has_missing"] = True
        result["missing_imports"] = sorted(list(missing))

        library = "flexicon" if api_mode == "flexicon" else "flexlibs"
        import_stmt = f"from {library} import {', '.join(sorted(missing))}"

        result["suggestion"] = (
            f"Code uses {len(missing)} Operations class(es) without importing: {', '.join(sorted(missing))}. "
            f"Add this import at the top:\n\n    {import_stmt}\n"
        )

    return result


def detect_wrong_library_imports(code: str, api_mode: str) -> dict:
    """Gate #2: Detect if user code imports from the wrong library for the selected API mode.

    Args:
        code: User's module/operation code
        api_mode: Selected API mode ('flexlibs_stable', 'flexicon', 'liblcm')

    Returns:
        dict with 'has_wrong_imports', 'wrong_imports', and 'suggestion'
    """
    result = {
        "has_wrong_imports": False,
        "wrong_imports": [],
        "suggestion": ""
    }

    # Extract all import statements
    import_pattern = r'(?:from|import)\s+([\w.]+)'
    imports = re.findall(import_pattern, code)

    if api_mode == "flexicon":
        # In flexicon mode, flag imports from stable flexlibs. `flexlibs2` is the
        # deprecated import alias for flexicon (it still resolves), so it is NOT
        # wrong here -- only true stable-flexlibs imports are.
        wrong_libs = [
            imp for imp in imports
            if imp.startswith('flexlibs') and not imp.startswith('flexlibs2')
        ]
        if wrong_libs:
            result["has_wrong_imports"] = True
            result["wrong_imports"] = wrong_libs
            result["suggestion"] = (
                f"Code in flexicon mode is importing from flexlibs (stable). "
                f"Detected: {', '.join(set(wrong_libs))}. "
                f"Use 'from flexicon import ...' instead for API consistency."
            )

    elif api_mode == "flexlibs_stable":
        # In stable mode, warn about flexicon imports (including the deprecated
        # flexlibs2 alias) that target the wrong library.
        wrong_libs = [
            imp for imp in imports
            if imp.startswith('flexicon') or imp.startswith('flexlibs2')
        ]
        if wrong_libs:
            result["has_wrong_imports"] = True
            result["wrong_imports"] = wrong_libs
            result["suggestion"] = (
                f"Code in flexlibs (stable) mode is importing from flexicon. "
                f"Detected: {', '.join(set(wrong_libs))}. "
                f"Use 'from flexlibs import ...' for API consistency."
            )

    return result


def detect_undefined_variables(code: str, tree: ast.AST | None = None) -> dict:
    """Detect likely undefined variables in code using static analysis.

    Looks for variable usage patterns that suggest undefined names:
    - CapitalizedName(...) - likely undeclared class/function (e.g., API_MODE_IMPORTS, SomeOperations)
    - UPPERCASE_VAR - likely internal variable or constant
    - References to MCP internals

    Args:
        code: Python source code string
        tree: Optional pre-parsed AST (if provided, code is not re-parsed)

    Returns dict with:
      - has_undefined: bool - whether undefined variables detected
      - undefined_vars: list - variable names that appear undefined
      - suggestion: str - guidance for fixing
    """
    try:
        # Use pre-parsed tree if provided, otherwise parse
        if tree is None:
            tree = ast.parse(code)
        defined_names = set()
        used_names = set()

        class NameCollector(ast.NodeVisitor):
            def visit_FunctionDef(self, node):
                defined_names.add(node.name)
                # Add function parameters
                for arg in node.args.args:
                    defined_names.add(arg.arg)
                self.generic_visit(node)

            def visit_ClassDef(self, node):
                defined_names.add(node.name)
                self.generic_visit(node)

            def visit_Assign(self, node):
                # Track assignments (x = value)
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined_names.add(target.id)
                self.generic_visit(node)

            def visit_ImportFrom(self, node):
                # Track imports
                for alias in node.names:
                    defined_names.add(alias.asname or alias.name)
                self.generic_visit(node)

            def visit_Import(self, node):
                # Track imports
                for alias in node.names:
                    defined_names.add(alias.asname or alias.name)
                self.generic_visit(node)

            def visit_Name(self, node):
                # Track name usage
                if isinstance(node.ctx, ast.Load):  # Reading, not writing
                    used_names.add(node.id)
                self.generic_visit(node)

        collector = NameCollector()
        collector.visit(tree)

        # Add built-in names (module-level constant, not recreated per call)
        defined_names.update(_BUILTIN_NAMES)

        # Find undefined variables
        undefined = used_names - defined_names

        # Filter out likely false positives (imported in patterns, etc)
        suspicious = []
        for var in undefined:
            # Flag internal-looking names and MCP variables
            if (var.startswith("API_") or var.isupper() or
                var[0].isupper() and "Operations" in var or
                "API_MODE" in var):
                suspicious.append(var)

        if suspicious:
            return {
                "has_undefined": True,
                "undefined_vars": sorted(suspicious),
                "suggestion": f"Undefined variables detected: {', '.join(suspicious)}. Make sure all classes and modules are imported (e.g., 'from flexicon import ...'). Do not use internal MCP variables like API_MODE_IMPORTS."
            }

        return {"has_undefined": False, "undefined_vars": []}

    except SyntaxError:
        # Can't parse code, skip check
        return {"has_undefined": False, "undefined_vars": []}


def validate_project_context(project_name: str, write_enabled: bool, session_initialized: bool = False) -> dict:
    """Validate project context and show what will be affected."""

    if not project_name:
        return {
            "error": "project_name_required",
            "message": "Project name must be set before running operations",
            "how_to_set": [
                "Option 1: Set in start(project_name='MyProject')",
                "Option 2: Set in this call with project_name='MyProject' parameter"
            ],
        }

    return {
        "project_validated": True,
        "target_project": project_name,
        "write_mode": "ENABLED - will modify project" if write_enabled else "READ-ONLY - safe exploration",
        "ready_to_execute": True
    }


def format_cud_warning(cud_info: dict, write_enabled: bool, confirmed: bool = False) -> dict:
    """Format enhanced warning with staged confirmation for data-affecting operations.

    Args:
        cud_info: Dict with 'operations', 'risks', 'affected_types'
        write_enabled: Whether write mode is enabled
        confirmed: Whether user has confirmed code review

    Shows clear progression through safety stages.
    """
    if not confirmed:
        # Stage 1: Code review
        return {
            "confirmation_required": True,
            "stage": "code_review",
            "reason": "This operation involves Create/Update/Delete actions",
            "detected_operations": cud_info["operations"],
            "potential_risks": cud_info["risks"],
            "affected_data": cud_info["affected_types"],
            "current_state": {
                "write_mode": "ENABLED" if write_enabled else "DISABLED (dry-run)",
                "confirmed": False
            },
            "progress": "1/3 - YOU ARE HERE: Review the code",
            "what_happens_next": (
                "Set confirmed=True to proceed to dry-run mode (RECOMMENDED: write_enabled will remain False)"
                if not write_enabled
                else "DANGER: Write mode is enabled. STRONGLY recommend setting write_enabled=False first"
            ),
            "safe_progression": [
                "1. Review the code carefully (YOU ARE HERE)",
                "2. Set confirmed=True with write_enabled=False to dry-run",
                "3. Review dry-run output",
                "4. Backup your project",
                "5. Set confirmed=True with write_enabled=True to execute"
            ]
        }

    if confirmed and not write_enabled:
        # Stage 2: Dry-run
        return {
            "executing": "dry_run",
            "stage": "dry_run",
            "confirmed": True,
            "write_mode": "DISABLED",
            "progress": "2/3 - DRY-RUN: Showing what WOULD happen",
            "will_modify_database": False,
            "note": "This shows exactly what would happen if write_enabled=True",
            "next_steps": [
                "1. Review the dry-run output above carefully",
                "2. Backup your project (if output looks good)",
                "3. Run again with write_enabled=True to execute"
            ]
        }

    if confirmed and write_enabled:
        # Stage 3: Execute
        return {
            "executing": "live",
            "stage": "execute",
            "confirmed": True,
            "write_mode": "ENABLED",
            "progress": "3/3 - EXECUTING: Making changes to database",
            "will_modify_database": True,
            "operations_that_will_execute": cud_info["operations"],
            "affected_data": cud_info["affected_types"],
            "warning": "DATABASE WILL BE MODIFIED - MAKE SURE YOU HAVE A BACKUP!",
            "final_check": "Backup complete? Ready to proceed?"
        }

    # Unreachable - covers all cases (confirmed: bool, write_enabled: bool)
    return {}


def _collect_assign_call_nodes(
    tree: ast.AST,
) -> Tuple[List[ast.Assign], List[ast.Call]]:
    """One ast.walk pass producing both Assign and Call lists for the
    alias/mutation helpers below to consume. Replaces the four separate
    walks the helpers used to do."""
    assigns: List[ast.Assign] = []
    calls: List[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assigns.append(node)
        elif isinstance(node, ast.Call):
            calls.append(node)
    return assigns, calls


def _resolve_alias_maps(
    assigns: List[ast.Assign],
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Build (operations_aliases, cast_aliases) in a single pass over Assigns.

    Operations alias shape:   posOps = POSOperations(project)
                              b = a   (chained -- b inherits a's class)
    Cast alias shape:         s_typed = ILexSense(sense)

    Generic operations match (Name ending in 'Operations', single positional
    arg) survives flexicon adding new Operations classes in parallel without
    us touching a hardcoded list. Generic cast match ('I' + Uppercase) avoids
    false positives like 'IndexCounter' (lowercase second char).

    Note: deliberately does NOT clear aliases on reassignment to something
    unrelated. False positives are safer than false negatives (#8); the
    downstream API-index lookup still determines whether a method is
    actually mutating.
    """
    operations: Dict[str, str] = {}
    casts: Dict[str, str] = {}
    for node in assigns:
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        target_name = node.targets[0].id
        rhs = node.value
        if isinstance(rhs, ast.Call) and isinstance(rhs.func, ast.Name):
            func_id = rhs.func.id
            if func_id.endswith("Operations") and len(rhs.args) == 1:
                operations[target_name] = func_id
            elif (
                len(func_id) >= 2
                and func_id[0] == "I"
                and func_id[1].isupper()
                and len(rhs.args) >= 1
            ):
                casts[target_name] = func_id
        elif isinstance(rhs, ast.Name):
            # Chained rebind: propagate both alias kinds symmetrically so
            #     a = ILexEntry(x)
            #     b = a
            # gives casts['b'] == 'ILexEntry'. Without this, detect_casting_needs
            # (issue #15 fix) would still flag b.LexemeFormOA even though `a` is
            # a known cast.
            if rhs.id in operations:
                operations[target_name] = operations[rhs.id]
            elif rhs.id in casts:
                casts[target_name] = casts[rhs.id]
    return operations, casts


def _find_aliased_operations_calls(
    calls: List[ast.Call], aliases: Dict[str, str]
) -> List[Tuple[str, str, int]]:
    """Find `alias.method(...)` calls where `alias` is an Operations instance.

    Returns (class_name, method_name, line_num) triples to be merged with the
    regex-detected operations calls.
    """
    results: List[Tuple[str, str, int]] = []
    for node in calls:
        if not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        alias_name = node.func.value.id
        if alias_name not in aliases:
            continue
        results.append((aliases[alias_name], node.func.attr, node.lineno))
    return results


def _find_cast_alias_property_writes(
    assigns: List[ast.Assign], cast_aliases: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Find property assignments rooted at a cast-alias variable.

    Detects:
        s_typed.MorphoSyntaxAnalysisRA.PartOfSpeechRA = pos
        s_typed.Gloss = new_value

    Returns mutation dicts compatible with find_liblcm_mutations() output.
    """
    mutations: List[Dict[str, Any]] = []
    for node in assigns:
        for target in node.targets:
            current = target
            attr_chain: List[str] = []
            while isinstance(current, ast.Attribute):
                attr_chain.append(current.attr)
                current = current.value
            if not attr_chain or not isinstance(current, ast.Name):
                continue
            if current.id not in cast_aliases:
                continue
            interface = cast_aliases[current.id]
            chain_str = '.'.join(reversed(attr_chain))
            mutations.append({
                'method': f'{interface}.{chain_str}=',
                'line': node.lineno,
                'category': 'Update',
                'context': f'{current.id}.{chain_str} = ...',
            })
    return mutations


def _extract_interface_names(entries: List[str]) -> set:
    """Pull bare interface names out of `acceptable_interfaces` strings.

    Entries may be bare names ('ILexEntry') or descriptive strings
    ('ILexSense (raw LCM)'). Take the leading non-space, non-paren token
    of each. Necessary because LCM's I-prefixed naming convention has
    492 substring-collision pairs (e.g. 'ICmAgent' is a substring of
    'ICmAgentEvaluation'); a substring match would let a cast to the
    base interface incorrectly satisfy a property defined only on the
    derived interface.
    """
    out: set = set()
    for entry in entries or ():
        if not entry:
            continue
        head = entry.split()[0].split("(")[0].strip()
        if head:
            out.add(head)
    return out


def _alias_satisfies(
    line_num: int,
    prop_name: str,
    acceptable_interfaces: List[str],
    alias_attr_accesses: Dict[int, List[Tuple[str, str]]],
) -> bool:
    """True if a cast-alias-rooted attribute access on `line_num` matches
    `prop_name` AND the alias's interface is among `acceptable_interfaces`.

    `prop_name` is matched as a prefix because KNOWN_CASTING_PATTERNS tags
    (e.g. 'LexemeForm') are family names for the real attribute name
    (e.g. 'LexemeFormOA'); this preserves the prefix semantics of the
    existing pattern `r"\\.LexemeForm"`.

    `acceptable_interfaces` may be bare names ('ILexEntry') or descriptive
    strings ('ILexSense (raw LCM)'). Both shapes are handled by
    `_extract_interface_names`; matching is then exact to avoid the
    substring-collision risk inherent in LCM's I-prefixed naming.
    """
    if not acceptable_interfaces:
        return False
    line_accesses = alias_attr_accesses.get(line_num)
    if not line_accesses:
        return False
    valid_interfaces = _extract_interface_names(acceptable_interfaces)
    if not valid_interfaces:
        return False
    for attr, interface in line_accesses:
        if not (attr == prop_name or attr.startswith(prop_name)):
            continue
        if interface in valid_interfaces:
            return True
    return False


def find_liblcm_mutations(code: str) -> List[Dict[str, Any]]:
    """Find raw LibLCM calls that mutate state.

    Detects patterns like:
    - _cache.CreateObject(...)
    - _cache.DeleteObject(...)
    - _cache.BeginNonUndoableTask()
    - obj.Add(...), obj.Remove(...), obj.Clear(...)
    - obj.MoveTo(...), obj.Insert(...)

    Returns list of mutations with their line numbers for protection context checking.
    """
    mutations = []

    for line_num, line in enumerate(code.split('\n'), 1):
        # Skip comments once per line
        line_content = _strip_comments(line)

        for pattern, method_name, category in _LIBLCM_MUTABLE_PATTERNS:
            if re.search(pattern, line_content):
                mutations.append({
                    'method': method_name,
                    'line': line_num,
                    'category': category,
                    'context': line_content.strip()[:60]  # First 60 chars for display
                })

    return mutations


def find_protected_ranges(code: str, tree: ast.AST | None = None) -> List[tuple]:
    """Find line ranges protected by modifyAllowed or modifyEnabled/writeEnabled guards.

    Detects:
    - if modifyAllowed: blocks (FLExTools standard parameter)
    - with project.modifyEnabled: blocks
    - with self.project.modifyEnabled: blocks
    - if project.writeEnabled: blocks
    - if self.project.writeEnabled: blocks
    - if project.writeEnabled == True: blocks

    Args:
        code: Python source code string
        tree: Optional pre-parsed AST (if provided, code is not re-parsed)

    Returns list of (start_line, end_line) tuples for protected ranges.
    """
    protected = []

    try:
        # Use pre-parsed tree if provided, otherwise parse
        if tree is None:
            tree = ast.parse(code)
    except SyntaxError:
        return protected  # Can't parse, assume no protection

    class ProtectionFinder(ast.NodeVisitor):
        def visit_With(self, node):
            """Find 'with project.modifyEnabled:' blocks."""
            for item in node.items:
                ctx_expr = item.context_expr
                # Match: project.modifyEnabled or self.project.modifyEnabled
                if self._is_modify_enabled(ctx_expr):
                    start_line = node.lineno
                    end_line = node.end_lineno or start_line + 1000
                    protected.append((start_line, end_line))
                    break

            self.generic_visit(node)

        def visit_If(self, node):
            """Find 'if modifyAllowed:' or 'if project.writeEnabled:' blocks."""
            if self._is_write_enabled_check(node.test):
                start_line = node.lineno
                # end_lineno includes the if line, body starts after
                if node.body:
                    end_line = node.body[-1].end_lineno or start_line + 1000
                else:
                    end_line = node.end_lineno or start_line + 1

                protected.append((start_line, end_line))

            self.generic_visit(node)

        def _is_modify_enabled(self, node):
            """Check if expression is 'project.modifyEnabled' or similar."""
            if isinstance(node, ast.Attribute):
                if node.attr == 'modifyEnabled':
                    return True
            return False

        def _is_write_enabled_check(self, node):
            """Check if condition checks 'modifyAllowed', 'writeEnabled', etc."""
            # Pattern: modifyAllowed (name - FLExTools standard parameter)
            if isinstance(node, ast.Name):
                return node.id == 'modifyAllowed'

            # Pattern: project.writeEnabled (attribute)
            if isinstance(node, ast.Attribute):
                return node.attr == 'writeEnabled'

            # Pattern: project.writeEnabled == True (compare)
            if isinstance(node, ast.Compare):
                # Check left side
                if isinstance(node.left, ast.Attribute):
                    if node.left.attr == 'writeEnabled':
                        return True
                if isinstance(node.left, ast.Name):
                    if node.left.id == 'modifyAllowed':
                        return True
                # Check comparators
                for comp in node.comparators:
                    if isinstance(comp, ast.Attribute):
                        if comp.attr == 'writeEnabled':
                            return True
                    if isinstance(comp, ast.Name):
                        if comp.id == 'modifyAllowed':
                            return True
            return False

    finder = ProtectionFinder()
    finder.visit(tree)
    return protected


def certify_script_readonly(code: str, api_index, tree: ast.AST | None = None) -> dict:
    """Certify whether a script makes any Flexicon mutating calls using API index.

    Uses the is_mutating flag from the API index to identify write operations with
    high confidence. Falls back to regex-based detection for code not in the index
    (raw LCM, custom logic, etc.).

    Also detects raw LibLCM mutations and checks if they're protected by
    modifyEnabled or writeEnabled guards.

    Args:
        code: Python code to analyze
        api_index: Loaded API index with is_mutating field per method
        tree: Optional pre-parsed AST (if provided, code is not re-parsed)

    Returns:
        {
          "is_certified_readonly": bool,           # True = no unprotected mutations
          "confidence": str,                       # "high" | "medium" | "low"
          "mutating_calls": [                      # Detected Flexicon mutations
              {"class": str, "method": str, "is_mutating": bool, "source": str}
          ],
          "unprotected_liblcm_calls": [            # Raw LCM calls without guard
              {"method": str, "line": int, "context": str}
          ],
          "protected_liblcm_calls": [              # Raw LCM calls with guard
              {"method": str, "line": int, "context": str}
          ],
          "unknown_calls": [...],                  # Calls not found in index
          "raw_lcm_patterns": [...],               # Regex-detected raw LCM writes
        }
    """
    # Normalize code by removing leading indentation (important for test strings)
    code = textwrap.dedent(code)

    mutating_calls = []
    unknown_calls = []
    raw_lcm_patterns = []
    unprotected_liblcm_calls = []
    protected_liblcm_calls = []
    confidence_sources = {"index": 0, "regex": 0, "unknown": 0}

    # Get protected ranges once for both Flexicon and LibLCM checks
    # Pass pre-parsed tree if available to avoid re-parsing
    protected_ranges = find_protected_ranges(code, tree)

    # Ensure tree is available for AST-based detection (#8 alias/cast tracking).
    # If parsing fails we silently skip AST-based detection -- the regex pass
    # below still runs.
    if tree is None:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            tree = None

    # Step 1: Extract Flexicon Operations method calls with line numbers
    # Use pre-compiled pattern: ClassName(project).MethodName( or ClassName.MethodName( (static)
    operations_calls_with_lines = []

    for match in _PATTERN_OPERATIONS_CALL.finditer(code):
        class_name, method_name = match.groups()
        # Calculate line number from character position
        line_num = code[:match.start()].count('\n') + 1
        operations_calls_with_lines.append((class_name, method_name, line_num))

    # Step 1b: AST-based alias detection (#8). Catches:
    #     posOps = POSOperations(project)
    #     posOps.Create(...)             # <- invisible to the regex above
    # Generic to any *Operations class so flexicon churn doesn't break it.
    # One ast.walk pass feeds both alias kinds + the property-writes helper
    # at Step 4b, instead of four separate walks.
    operations_aliases: Dict[str, str] = {}
    cast_aliases: Dict[str, str] = {}
    ast_assigns: List[ast.Assign] = []
    if tree is not None:
        ast_assigns, ast_calls = _collect_assign_call_nodes(tree)
        operations_aliases, cast_aliases = _resolve_alias_maps(ast_assigns)
        if operations_aliases:
            aliased_calls = _find_aliased_operations_calls(ast_calls, operations_aliases)
            existing = {(c, m, l) for c, m, l in operations_calls_with_lines}
            for triple in aliased_calls:
                if triple not in existing:
                    operations_calls_with_lines.append(triple)

    # Step 2: Look up each call in the API index and check if protected
    if api_index and api_index.flexicon:
        entities = api_index.flexicon.get("entities", {})

        for class_name, method_name, line_num in operations_calls_with_lines:
            # Check if this call is protected by a guard
            is_protected = _is_line_protected(line_num, protected_ranges)

            if class_name in entities:
                class_entity = entities[class_name]
                methods = class_entity.get("methods", [])

                # Search for method in class
                method_found = False
                for method in methods:
                    if method.get("name") == method_name:
                        method_found = True
                        is_mutating = method.get("is_mutating", False)

                        # Only add as unprotected mutation if it's actually mutating and not protected
                        if is_mutating and not is_protected:
                            mutating_calls.append({
                                "class": class_name,
                                "method": method_name,
                                "is_mutating": True,
                                "source": "index",
                                "line": line_num,
                                "protected": False
                            })
                            confidence_sources["index"] += 1
                        elif is_mutating and is_protected:
                            # Protected mutation - don't add to mutating_calls
                            pass
                        else:
                            # Read-only call - still track it
                            mutating_calls.append({
                                "class": class_name,
                                "method": method_name,
                                "is_mutating": False,
                                "source": "index",
                                "line": line_num,
                                "protected": True
                            })
                        break

                if not method_found:
                    # Class found but method not in index.
                    # Issue #32: Get*/Find*/Is*/Has*/Count*/Contains* prefixes are
                    # unambiguously read-only -- don't false-positive them as mutating.
                    _READONLY_PREFIXES = ("Get", "Find", "Is", "Has", "Count", "Contains")
                    if method_name.startswith(_READONLY_PREFIXES):
                        mutating_calls.append({
                            "class": class_name,
                            "method": method_name,
                            "is_mutating": False,
                            "source": "prefix_heuristic",
                            "line": line_num,
                            "protected": True
                        })
                    elif not is_protected:
                        unknown_calls.append({
                            "class": class_name,
                            "method": method_name,
                            "reason": "method not in index",
                            "line": line_num
                        })
                        mutating_calls.append({
                            "class": class_name,
                            "method": method_name,
                            "is_mutating": True,
                            "source": "unknown",
                            "line": line_num,
                            "protected": False
                        })
                        confidence_sources["unknown"] += 1
            else:
                # Class not in index - fall through to regex
                pass

    # Step 3: Regex-based detection for patterns not in index.
    # detect_cud_operations() is line-blind, so we keep its output only as a
    # diagnostic signal (surfaced in the return dict for inspection) but do
    # NOT use it to gate execution -- otherwise a guarded `project.X.Create(...)`
    # would still be blocked because `.Create(` matches globally. The line-aware
    # patterns in _LIBLCM_MUTABLE_PATTERNS handle the gating with protection
    # awareness; this regex pass only contributes to the confidence rating.
    cud_info = detect_cud_operations(code)
    if cud_info["is_cud"]:
        raw_lcm_patterns.extend(cud_info["operations"])
        confidence_sources["regex"] += 1

    # Step 4: Detect raw LibLCM mutations and check if they're protected
    liblcm_mutations = find_liblcm_mutations(code)

    # Step 4b: AST-based cast-alias property writes (#8). Catches:
    #     s_typed = ILexSense(sense)
    #     s_typed.MorphoSyntaxAnalysisRA.PartOfSpeechRA = pos    # <- invisible to regex
    # Reuses cast_aliases + ast_assigns built once at Step 1b.
    if cast_aliases:
        liblcm_mutations.extend(
            _find_cast_alias_property_writes(ast_assigns, cast_aliases)
        )

    # protected_ranges already calculated above in Step 2

    for mutation in liblcm_mutations:
        line_num = mutation['line']
        is_protected = _is_line_protected(line_num, protected_ranges)

        if is_protected:
            protected_liblcm_calls.append({
                'method': mutation['method'],
                'line': line_num,
                'category': mutation['category'],
                'context': mutation['context']
            })
        else:
            unprotected_liblcm_calls.append({
                'method': mutation['method'],
                'line': line_num,
                'category': mutation['category'],
                'context': mutation['context'],
                'is_mutating': True
            })

    # Step 6: Determine confidence level
    total_calls = len(mutating_calls) + len(unknown_calls) + len(unprotected_liblcm_calls)
    if total_calls == 0 and not raw_lcm_patterns:
        confidence = "high"
    elif confidence_sources["unknown"] == 0 and confidence_sources["regex"] == 0 and not unprotected_liblcm_calls:
        confidence = "high"
    elif confidence_sources["unknown"] == 0 and not unprotected_liblcm_calls:
        confidence = "medium"
    else:
        confidence = "low"

    # Step 7: Build certification result.
    # Script is read-only certified if:
    # 1. No Flexicon mutating calls (index lookup, line-aware, protection-checked)
    # 2. No unprotected raw LCM / project-accessor mutations (line-aware, protection-checked)
    # raw_lcm_patterns is intentionally NOT a gate -- it is line-blind and would
    # block guarded code like `if modifyAllowed: project.LexEntry.Create(...)`,
    # producing the contradictory "Found 0 unprotected mutation(s)" + hard-block
    # output users were hitting. The line-aware patterns above cover the same
    # cases with correct protection awareness.
    is_certified_readonly = (
        not any(m.get("is_mutating") for m in mutating_calls)
        and not unprotected_liblcm_calls
    )

    return {
        "is_certified_readonly": is_certified_readonly,
        "confidence": confidence,
        "mutating_calls": [m for m in mutating_calls if m.get("is_mutating")],
        "readonly_calls": [m for m in mutating_calls if not m.get("is_mutating")],
        "unprotected_liblcm_calls": unprotected_liblcm_calls,
        "protected_liblcm_calls": protected_liblcm_calls,
        "unknown_calls": unknown_calls,
        "raw_lcm_patterns": raw_lcm_patterns,
    }


def get_unprotected_write_guidance(cert: dict) -> dict:
    """Generate detailed guidance for fixing unprotected mutations.

    Args:
        cert: Result from certify_script_readonly() with unprotected mutations

    Returns:
        Guidance dict with examples and step-by-step instructions
    """
    mutating = cert.get("mutating_calls", [])
    unprotected_liblcm = cert.get("unprotected_liblcm_calls", [])

    # Build list of unprotected mutations found
    mutations_found = []
    if mutating:
        mutations_found.extend([f"{m['class']}.{m['method']}()" for m in mutating if m.get("is_mutating")])
    if unprotected_liblcm:
        mutations_found.extend([m['method'] + "()" for m in unprotected_liblcm])

    return {
        "error": "unprotected_mutations_detected",
        "message": f"Found {len(mutations_found)} unprotected mutation(s). Code cannot run until protected.",
        "mutations_found": mutations_found,
        "why": "All write operations must be guarded with 'if modifyAllowed:' to prevent accidental data loss.",
        "fix_pattern": {
            "before": "project.LexEntry.SetLexemeForm(entry, 'new_form')",
            "after": "if modifyAllowed:\n    project.LexEntry.SetLexemeForm(entry, 'new_form')\n    report.Info('Updated entry')\nelse:\n    report.Info('(Would update entry to: new_form)')"
        },
        "templates_to_review": [
            "templates/2-flexicon-template.py (recommended - best documented)",
            "templates/1-flexlibs-stable-template.py (for FieldWorks < 9.0)",
            "templates/3-liblcm-template.py (for advanced use cases)"
        ],
        "next_steps": [
            "1. Open a template above to see the if modifyAllowed: pattern in context",
            "2. Update your code to wrap all mutations with: if modifyAllowed:",
            "3. Move read-only logic before the if block",
            "4. Add else block to preview what would be changed",
            "5. Re-run with the updated code"
        ]
    }


# Issue #21 follow-up: receiver-name -> preferred interface tie-break.
# When `defined_on` lists more than one candidate interface, an alphabetical
# pick (the old behavior) produces confidently-wrong rewrites for the most
# ambiguous properties (Form -> ILexEtymology instead of IMoForm, Gloss ->
# ILexEtymology instead of ILexSense, Name -> ICmAgent instead of
# ICmPossibility). The Dennis cascade-failure pattern (memory/
# dennis_cascade_failure.md) shows that a confidently-wrong rewrite is
# worse than no rewrite -- the LLM follows it to a dead end and abandons
# the wrapper layer entirely.
#
# Linguist-convention variable names are a reliable signal: scripts almost
# always call a sense `sense`, an entry `entry`, a POS object `pos`, etc.
# Keep this map small and obvious -- ambiguous variable names (e.g. `obj`,
# `x`) deliberately fall through to None (manual resolve_property).
_RECEIVER_NAME_TO_INTERFACE = {
    "sense": "ILexSense",
    "entry": "ILexEntry",
    "pos": "ICmPossibility",
    "pos_obj": "ICmPossibility",
    "domain": "ICmPossibility",
    "bundle": "IWfiMorphBundle",
    "morph": "IMoForm",
    "seg": "ISegment",
    # Issue #30: common _obj suffix variants used in user scripts
    "sense_obj": "ILexSense",
    "entry_obj": "ILexEntry",
    "seg_obj": "ISegment",
    "para_obj": "IStTxtPara",
    "text_obj": "IStText",
    "wf_obj": "IWfiWordform",
    "wa_obj": "IWfiAnalysis",
    "morph_obj": "IMoForm",
    "bundle_obj": "IWfiMorphBundle",
}

# Suffixes that signal a typed receiver -- strip and retry the base name.
_TYPED_RECEIVER_SUFFIXES = ("_obj", "_typed", "_cast")

# Issue #40: members that live on ICmObject itself -- accessing them never
# requires a cast to a concrete interface, so the polymorphic-casting heuristic
# must never flag them. These were a recurring false-positive source in user
# session logs (e.g. `obj.Hvo`, `obj.Guid`) that forced needless rewrites.
_CASTING_ALWAYS_SAFE_MEMBERS = frozenset({"Guid", "Hvo", "ClassID", "ClassName"})

# Issue #40 (domain ruling): IMultiString/IMultiUnicode VALUE accessors.
# BestAnalysisAlternative and BestVernacularAlternative are returned by
# multistring value properties -- their receiver is already a typed
# IMultiString/IMultiUnicode value, not an ICmObject, so no cast is possible or
# needed. Likewise, chaining .Text off these is a plain string accessor. The
# heuristic must never flag these; they were driving constant false-positive
# rewrites in multilingual-field access patterns.
_CASTING_MULTISTRING_VALUE_MEMBERS = frozenset({
    "BestAnalysisAlternative",
    "BestVernacularAlternative",
    "Text",  # chained off the above; also safe on its own (str attribute)
})

# Issue #40 (domain ruling): conditional members -- safe ONLY when the
# receiver's static declared type (cast_alias) proves it, otherwise keep
# the flag. Maps member name -> set of interface names that declare it safely.
# If the receiver has no cast_alias, the member is still flagged (no inference).
_CASTING_CONDITIONAL_SAFE = {
    "LexemeFormOA": {"ILexEntry"},
    "AnalysesRS": {"ISegment"},
    "Wordform": {"IWfiAnalysis", "IWfiGloss", "IAnalysisOccurrence"},
    "Form": {"IMoForm", "IMoStemAllomorph", "IMoAffixAllomorph",
             "IMoAffixProcess", "IMoStemName"},
    "FreeTranslation": {"ISegment"},
}


def _pick_cast_interface(
    property_name: str,
    available_on: List[str],
    casting_index: Optional[Dict] = None,
    receiver_name: Optional[str] = None,
) -> Optional[str]:
    """Pick the most-specific interface to cast to for `property_name`.

    Strategy:
      1. Prefer entries in `available_on` that start with 'I' (LCM convention).
      2. If exactly one survives, use it.
      3. Otherwise consult casting_index's `defined_on`; if exactly one
         I-prefixed entry, use it.
      4. If multiple candidates remain AND we have a `receiver_name` matching
         a known linguist-convention variable, prefer the matching interface
         when it's in the candidate set.
      5. Otherwise return None. The Dennis cascade-failure pattern shows a
         confidently-wrong rewrite (alphabetical tie-break) is worse than
         no rewrite -- downstream this routes to the existing fallback hint
         ("call flextools_resolve_property to resolve manually").
      6. Drop entries with parenthetical qualifiers like "ILexSense (raw LCM)"
         -- those are descriptive, not importable.
    """
    cleaned: List[str] = []
    for entry in available_on or ():
        if not entry:
            continue
        head = entry.split()[0].split("(")[0].strip()
        if head.startswith("I"):
            cleaned.append(head)
    if len(cleaned) == 1:
        return cleaned[0]

    # Consult the casting_index's defined_on for the canonical interface list.
    defined_on: List[str] = []
    if casting_index:
        props = (casting_index or {}).get("properties") or {}
        info = props.get(property_name) or {}
        defined_on = [
            d for d in info.get("defined_on", []) if isinstance(d, str) and d.startswith("I")
        ]
        if len(defined_on) == 1:
            return defined_on[0]

    # Multiple candidates. Try the receiver-name tie-break before giving up.
    candidates = defined_on if defined_on else cleaned
    if receiver_name and candidates:
        preferred = _RECEIVER_NAME_TO_INTERFACE.get(receiver_name)
        if preferred is None:
            # Issue #30: normalize _obj/_typed/_cast suffix and retry
            for suffix in _TYPED_RECEIVER_SUFFIXES:
                if receiver_name.endswith(suffix):
                    base = receiver_name[: -len(suffix)]
                    preferred = _RECEIVER_NAME_TO_INTERFACE.get(base)
                    if preferred is not None:
                        break
        if preferred and preferred in candidates:
            return preferred

    # Ambiguous and we have no signal to disambiguate. Return None rather
    # than picking alphabetically (Issue #21 follow-up: drop confident-wrong
    # tie-break). The handler's fallback path emits the
    # "call flextools_resolve_property" hint.
    if len(cleaned) > 1 or len(defined_on) > 1:
        return None
    if cleaned:
        return cleaned[0]
    return None


# Issue #21 follow-up: some LCM interfaces live OUTSIDE SIL.LCModel.
# IMultiAccessorBase (and its kin) live in SIL.LCModel.Core.KernelInterfaces.
# Emitting `from SIL.LCModel import IMultiAccessorBase` produces an
# ImportError at runtime, which is worse than no rewrite at all.
# Issue #12 correction: the IMulti* family (IMultiAccessorBase,
# IMultiStringAccessor, IMultiUnicode, IMultiString) actually lives in
# SIL.LCModel -- both LibLCM reflection (the liblcm index) and the #12 user
# session confirm it. The earlier #21 override routed them to
# SIL.LCModel.Core.KernelInterfaces, which produces an ImportError (the exact
# bug class #12 was filed for). Only the ITs* text-string kernel types
# genuinely live in KernelInterfaces and aren't in the LCM domain index, so
# they remain here; everything else falls through to the SIL.LCModel default.
_INTERFACE_NAMESPACE_OVERRIDES = {
    "ITsString": "SIL.LCModel.Core.KernelInterfaces",
    "ITsMultiString": "SIL.LCModel.Core.KernelInterfaces",
    "ITsTextProps": "SIL.LCModel.Core.KernelInterfaces",
    "ITsStrBldr": "SIL.LCModel.Core.KernelInterfaces",
    "ITsIncStrBldr": "SIL.LCModel.Core.KernelInterfaces",
}


def _imports_for_interface(cast_interface: Optional[str]) -> List[str]:
    """Build the imports_needed list for an emitted cast.

    Defaults to `from SIL.LCModel import X`, but routes a small set of
    known-elsewhere interfaces (IMultiAccessorBase et al.) to their real
    namespace. Returns [] when cast_interface is falsy.
    """
    if not cast_interface:
        return []
    ns = _INTERFACE_NAMESPACE_OVERRIDES.get(cast_interface, "SIL.LCModel")
    return [f"from {ns} import {cast_interface}"]


def _find_receiver_name(
    tree: Optional[ast.AST], line_num: int, property_name: str
) -> Optional[str]:
    """Find the receiver variable name for `obj.property_name` on `line_num`.

    Used by `_pick_cast_interface` to disambiguate properties defined on
    multiple interfaces (Issue #21 follow-up). Only returns the name when
    the receiver is a bare ast.Name -- chained or call-rooted receivers
    don't get a tie-break (they also wouldn't get a rewrite emitted).
    """
    if tree is None:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if getattr(node, "lineno", None) != line_num:
            continue
        if node.attr != property_name:
            continue
        receiver = node.value
        if isinstance(receiver, ast.Name):
            return receiver.id
    return None


def _build_cast_rewrite(
    tree: Optional[ast.AST],
    line_num: int,
    property_name: str,
    cast_interface: str,
) -> Optional[str]:
    """Build a single-site cast rewrite for an `obj.PropertyName` access on `line_num`.

    Walks the AST once and finds the *first* attribute access matching
    `property_name` on the target line. Wraps its receiver in
    `cast_interface(receiver)` and returns the unparsed expression.

    Returns None if:
      - tree is None / unparsable,
      - the property is accessed via a complex receiver we don't want to
        single-site rewrite (e.g. chained calls); we deliberately do NOT
        rewrite chained accesses per Issue #21's "single-site only" rule.
    """
    if tree is None or not cast_interface:
        return None
    if not hasattr(ast, "unparse"):
        return None  # Python <3.9; not supported.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if getattr(node, "lineno", None) != line_num:
            continue
        if node.attr != property_name:
            continue
        receiver = node.value
        # Single-site only: skip if receiver is itself a chained Attribute or
        # a Call (e.g. project.X.Y.Z, foo().bar). Acceptable receivers:
        # ast.Name (entry, sense) and ast.Subscript (entries[0]).
        if isinstance(receiver, (ast.Name, ast.Subscript)):
            wrapped_call = ast.Call(
                func=ast.Name(id=cast_interface, ctx=ast.Load()),
                args=[receiver],
                keywords=[],
            )
            new_attr = ast.Attribute(value=wrapped_call, attr=property_name, ctx=ast.Load())
            try:
                return ast.unparse(new_attr)
            except Exception:
                return None
    return None


# ============================================================
# Issue #48: inline casting metadata into discovery-time docs.
#
# get_object_api (the discovery gate's required step) is reliably called;
# resolve_property (#22) is not. Joining per-property casting requirements
# into the discovery response teaches cast-correct code on the first draft.
#
# The guidance MUST be byte-identical to what a preflight rejection would
# emit, so both paths route through the SAME generator: _pick_cast_interface
# picks the interface and _build_cast_rewrite formats the single-site cast.
# ============================================================

_POLY_ITERATION_NOTE = (
    "Items are heterogeneous; cast each item: "
    "concrete = CastingOperations.cast_to_concrete(item)"
)


def build_property_cast_example(
    property_name: str,
    casting_index: Optional[Dict] = None,
    receiver_name: str = "obj",
) -> Optional[str]:
    """Canonical single-site cast rewrite for ``receiver_name.property_name``.

    Shared by the #21 preflight rejection path and the #48 discovery-time
    annotation so the `cast_example` shown at discovery is byte-identical to
    the `rewrite` a rejection would produce for the same access pattern.

    Returns None when the interface can't be unambiguously resolved -- the
    same "no confidently-wrong rewrite" rule enforced by _pick_cast_interface
    (see the Dennis cascade-failure note).
    """
    if not casting_index or not property_name:
        return None
    info = (casting_index.get("properties") or {}).get(property_name) or {}
    defined_on = info.get("defined_on", [])
    cast_iface = _pick_cast_interface(
        property_name, defined_on, casting_index, receiver_name=receiver_name
    )
    if not cast_iface:
        return None
    try:
        tree = ast.parse(f"{receiver_name}.{property_name}")
    except SyntaxError:
        return None
    return _build_cast_rewrite(tree, 1, property_name, cast_iface)


def annotate_properties_with_casting(
    properties: List[Dict[str, Any]],
    casting_index: Optional[Dict] = None,
    summary_only: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """Join #48 casting metadata onto a property list.

    Returns ``(properties_out, annotated_count)``. Properties absent from the
    casting index are left untouched (the original dict object is reused), so a
    property list where nothing matches comes back byte-for-byte identical --
    the golden-test guarantee in the issue.

    In ``summary_only`` mode (#11) per-item fields are suppressed: the caller
    still learns how many properties need casting (for the top-level
    ``casting_notes`` counter) but the compact summary shape stays lean.
    """
    if not casting_index or not properties:
        return properties, 0

    props_idx = casting_index.get("properties") or {}
    poly_idx = casting_index.get("polymorphic_collections") or {}

    annotated_count = 0
    out: List[Dict[str, Any]] = []
    for prop in properties:
        name = prop.get("name")
        info = props_idx.get(name) if name else None
        poly = poly_idx.get(name) if name else None
        if not info and not poly:
            out.append(prop)  # untouched -> byte-identical
            continue

        # Mirror the rejection path's flow-independent skips (issue #40) so the
        # two casting-guidance code paths never diverge: members that live on
        # ICmObject itself (Guid/Hvo/ClassID/ClassName) and multistring value
        # accessors never need a cast. Flagging them here would re-introduce the
        # needless-rewrite false positives #40 removed. The receiver/flow-
        # dependent skips (project.*, cast-alias conditionals, chain segments)
        # have no analogue at discovery time and are intentionally not mirrored.
        cast_safe = (
            name in _CASTING_ALWAYS_SAFE_MEMBERS
            or name in _CASTING_MULTISTRING_VALUE_MEMBERS
        )
        info_annotates = bool(info) and not cast_safe
        if not info_annotates and not poly:
            out.append(prop)  # nothing left to say -> byte-identical
            continue

        annotated_count += 1
        if summary_only:
            out.append(prop)  # count only; no per-item bloat in summary mode
            continue

        new_prop = dict(prop)
        if info_annotates:
            new_prop["requires_cast"] = True
            new_prop["cast_to"] = [
                d for d in info.get("defined_on", []) if isinstance(d, str)
            ]
            example = build_property_cast_example(name, casting_index)
            if example:
                new_prop["cast_example"] = example
        if poly:
            new_prop["polymorphic"] = True
            new_prop["iteration_note"] = _POLY_ITERATION_NOTE
        out.append(new_prop)

    return out, annotated_count


def build_casting_notes(annotated_count: int) -> Optional[str]:
    """Top-level ``casting_notes`` counter string, or None when nothing needs it."""
    if annotated_count <= 0:
        return None
    plural = "property requires" if annotated_count == 1 else "properties require"
    return (
        f"{annotated_count} {plural} casting before access. See requires_cast / "
        "polymorphic markers. Preflight will reject uncast access."
    )


def detect_casting_needs(
    code: str,
    casting_index: Optional[Dict] = None,
    tree: ast.AST | None = None,
) -> dict:
    """Detect property access patterns that likely need casting for all 3 API flavors.

    Uses the casting_index (if available) to identify properties that:
    - Don't exist on base interface types (like ICmObject)
    - Require casting to concrete types (like ILexEntry)
    - Are part of polymorphic collections

    Issue #15 fix: when `tree` is provided (or can be parsed), explicit cast
    aliases (`s_typed = ILexSense(x)`) are honored — subsequent property access
    rooted at the alias is NOT flagged if the cast's interface is listed in the
    property's `defined_on`. This brings the preflight validator in line with
    `certify_script_readonly`, which already honored these aliases.

    Args:
        code: Python code to analyze
        casting_index: Optional pre-built casting index with property metadata
        tree: Optional pre-parsed AST. If None, we attempt ast.parse(code) and
            fall through to regex-only behavior on SyntaxError. This matches the
            tree-or-reparse pattern used in `certify_script_readonly`.

    Returns:
        {
            "has_casting_issues": bool,
            "casting_issues": [...],
            "helpers_needed": set,  # Which specific helpers are needed (for injection)
            "injection_tier": "none" | "minimal" | "full",  # For three-tier injection strategy
            "known_polymorphic_patterns": [...],
            "severity": "error" | "warning"
        }
    """
    issues = []
    helpers_needed = set()  # Track which helpers are actually used

    # Issue #15: build cast_aliases (e_typed = ILexEntry(x)) so the property-
    # access regex below can skip flags when the LHS is already cast to an
    # interface that defines the property. Without this, idiomatic chains like
    #     e = ILexEntry(entry)
    #     lf = e.LexemeFormOA
    # get flagged on the second line even though the cast on the first line
    # already satisfies the requirement.
    cast_aliases: Dict[str, str] = {}
    # alias_attr_accesses: line_num -> list of (attr_name, interface)
    # Lets the regex loops below skip a flag when the underlying AST access is
    # rooted at a cast alias. Built once from the AST so each regex hit only
    # pays a dict lookup + a short list scan.
    alias_attr_accesses: Dict[int, List[Tuple[str, str]]] = {}
    # typed_chain_segments: line_num -> {attr_names that the regex would parse
    # as obj_var but are actually mid-chain property names whose chain root is
    # a typed receiver (cast alias OR inline `I*(...)` call)}. The static cast
    # at the root already constrains the chain's type, so the next attribute
    # in the chain doesn't need a separate cast. Without this, the advanced
    # casting-index loop's regex `(\w+)\.([A-Z]\w+)` flags pairs like
    # `Form.BestVernacularAlternative` in `wf.Form.BestVernacularAlternative`
    # -- treating the property name `Form` as if it were a variable.
    typed_chain_segments: Dict[int, set] = {}
    # Issue #40: operations-class aliases (segOps = SegmentOperations(project))
    # so a method call captured by the property regex (segOps.IsLabel(seg)) is
    # recognized as a wrapper call, not a polymorphic property access.
    operations_aliases: Dict[str, str] = {}
    if tree is None:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            tree = None
    if tree is not None:
        ast_assigns, _ast_calls = _collect_assign_call_nodes(tree)
        operations_aliases, cast_aliases = _resolve_alias_maps(ast_assigns)
        if cast_aliases:
            for node in ast.walk(tree):
                if not isinstance(node, ast.Attribute):
                    continue
                if not isinstance(node.value, ast.Name):
                    continue
                root = node.value.id
                if root not in cast_aliases:
                    continue
                alias_attr_accesses.setdefault(node.lineno, []).append(
                    (node.attr, cast_aliases[root])
                )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if not isinstance(node.value, ast.Attribute):
                continue
            inner = node.value
            root = inner.value
            while isinstance(root, ast.Attribute):
                root = root.value
            typed_root = False
            if isinstance(root, ast.Name) and root.id in cast_aliases:
                typed_root = True
            elif isinstance(root, ast.Call) and isinstance(root.func, ast.Name):
                fid = root.func.id
                if len(fid) >= 2 and fid[0] == "I" and fid[1].isupper():
                    typed_root = True
            if typed_root:
                typed_chain_segments.setdefault(inner.lineno, set()).add(inner.attr)

    # Known polymorphic patterns that ALWAYS need casting across all flavors
    # These are based on C# data model structure, not wrapper-specific
    # Maps pattern → (helper_name, helper_function_to_use)
    KNOWN_CASTING_PATTERNS = {
        "HeadWord": {
            "helper": "get_headword",  # ← Which helper to inject if needed
            "missing_on": ["ICmObject"],
            "available_on": ["ILexEntry"],
            "pattern_sources": [r"\.Owner\s*\.\s*HeadWord", r"entry\s*\.\s*HeadWord"],
            "fix": "from SIL.LCModel import ILexEntry\nentry = ILexEntry(obj)\nheadword = entry.HeadWord.Text",
            "flexicon_helper": "Use cast_to_concrete(obj) from flexicon.code.lcm_casting"
        },
        "LexemeForm": {
            "helper": "get_lexeme_form",  # ← Which helper to inject if needed
            "missing_on": ["ICmObject"],
            "available_on": ["ILexEntry"],
            "pattern_sources": [r"\.LexemeForm", r"entry\s*\.\s*LexemeForm"],
            "fix": "from SIL.LCModel import ILexEntry\nentry = ILexEntry(obj)\nform = entry.LexemeForm",
            "flexicon_helper": "Use cast_to_concrete(obj) to get ILexEntry"
        },
        "ReversalEntriesRC": {
            "helper": "safe_get_property",  # ← Use safe access helper for this
            "missing_on": ["ILexSense (flexicon wrapped)"],
            "available_on": ["ILexSense (raw LCM)"],
            "pattern_sources": [r"sense\s*\.\s*ReversalEntriesRC", r"\.ReversalEntriesRC"],
            "fix": "# Access collection on raw sense object, not flexicon-wrapped\nreversals = list(sense.ReversalEntriesRC)",
            "flexicon_helper": "Unwrap flexicon object first, or use ReversalOperations"
        },
    }

    # Scan code line by line for property access patterns
    for line_num, line in enumerate(code.split('\n'), 1):
        # Skip comments and empty lines
        line_content = re.sub(r'#.*$', '', line).strip()
        if not line_content:
            continue

        # Check each known casting pattern
        for property_name, pattern_info in KNOWN_CASTING_PATTERNS.items():
            for pattern in pattern_info["pattern_sources"]:
                if re.search(pattern, line_content):
                    # Issue #40 (domain ruling): project.X is a Python wrapper
                    # call; the casting gate must never fire when the receiver
                    # is `project`. Check via the AST so we don't lose the
                    # line-level pattern that already matched.
                    _receiver_pre = _find_receiver_name(tree, line_num, property_name)
                    if _receiver_pre == "project":
                        break
                    # Issue #40 (domain ruling): Best* accessors and .Text are
                    # IMultiString/IMultiUnicode value members -- no cast needed.
                    if property_name in _CASTING_MULTISTRING_VALUE_MEMBERS:
                        break
                    # Issue #15: if the access on this line is rooted at a cast
                    # alias whose interface is listed in available_on, the cast
                    # already satisfies the requirement -- don't flag.
                    if _alias_satisfies(
                        line_num,
                        property_name,
                        pattern_info["available_on"],
                        alias_attr_accesses,
                    ):
                        break
                    # Issue #21: inline the structured rewrite so the LLM can
                    # apply the cast without a second resolve_property call.
                    # Issue #21 follow-up: receiver-name signal disambiguates
                    # confidently-wrong tie-breaks (Form / Gloss / Name).
                    receiver_name = _receiver_pre
                    cast_iface = _pick_cast_interface(
                        property_name,
                        pattern_info["available_on"],
                        casting_index,
                        receiver_name=receiver_name,
                    )
                    rewrite = _build_cast_rewrite(
                        tree, line_num, property_name, cast_iface or ""
                    ) if cast_iface else None
                    imports_needed = _imports_for_interface(cast_iface)

                    # Found a potential casting issue
                    issues.append({
                        "property": property_name,
                        "line": line_num,
                        "pattern": line_content[:80],
                        "found_at": line_content[:120],
                        "missing_on": pattern_info["missing_on"],
                        "available_on": pattern_info["available_on"],
                        "fix": pattern_info["fix"],
                        "flexicon_helper": pattern_info["flexicon_helper"],
                        "severity": "error",
                        "rewrite": rewrite,
                        "imports_needed": imports_needed,
                        "cast_interface": cast_iface,
                    })
                    # Track which helper would be needed if this code runs
                    helpers_needed.add(pattern_info.get("helper", "safe_get_property"))
                    break  # Only report once per property per line

    # If casting_index is provided, do advanced lookup for other properties
    if casting_index and isinstance(casting_index, dict):
        casting_props = casting_index.get("properties", {})
        polymorphic_colls = casting_index.get("polymorphic_collections", {})

        # Look for property access that might need casting
        # Pattern: obj.PropertyName or obj.PropertyName()
        property_access_pattern = r'(\w+)\s*\.\s*([A-Z]\w+)\s*(?:\(|$|\.|\[)'
        for line_num, line in enumerate(code.split('\n'), 1):
            line_content = re.sub(r'#.*$', '', line)
            for match in re.finditer(property_access_pattern, line_content):
                obj_var, prop_name = match.groups()

                # Issue #40: universally-safe members (Guid/Hvo/ClassID/ClassName)
                # live on ICmObject itself -- they never need a cast. Skip them
                # so safe read-only access stops getting false-rejected.
                if prop_name in _CASTING_ALWAYS_SAFE_MEMBERS:
                    continue

                # Issue #40 (domain ruling): project.X is a Python wrapper
                # method, not C# interface navigation. The casting heuristic
                # must NEVER fire when the receiver is `project`.
                if obj_var == "project":
                    continue

                # Issue #40 (domain ruling): IMultiString/IMultiUnicode value
                # accessors (BestAnalysisAlternative, BestVernacularAlternative,
                # Text). The receiver of these is already a typed value object,
                # not an ICmObject -- no cast is possible or needed.
                if prop_name in _CASTING_MULTISTRING_VALUE_MEMBERS:
                    continue

                # Issue #40: a call on an Operations-class instance
                # (segOps.IsLabel(seg)) is a flexicon wrapper method, not a
                # polymorphic property access. The regex captures it because the
                # method name is CamelCase; skip when obj_var is a known
                # Operations alias.
                if obj_var in operations_aliases:
                    continue

                # Option-1 false-positive fix: obj_var is a mid-chain property
                # name (e.g. `Form` in `wf.Form.BestVernacularAlternative`) and
                # the chain root is statically typed. The cast at the root
                # already constrains what `obj_var` returns, so flagging the
                # next attribute would require return-type info we don't have.
                # KNOWN_CASTING_PATTERNS still catches `.Owner.HeadWord`-shaped
                # cases (its regex sources are explicit), so this only relaxes
                # the heuristic where it was guessing.
                if obj_var in typed_chain_segments.get(line_num, ()):
                    continue

                # Issue #40 (domain ruling): conditional members -- safe ONLY
                # when an explicit cast_alias proves the receiver's type. The
                # detector has no flow-based type inference; receiver type is
                # known solely from cast_aliases. If the alias proves a safe
                # interface, skip; otherwise keep the flag.
                if prop_name in _CASTING_CONDITIONAL_SAFE:
                    safe_ifaces = _CASTING_CONDITIONAL_SAFE[prop_name]
                    receiver_iface = cast_aliases.get(obj_var)
                    if receiver_iface and receiver_iface in safe_ifaces:
                        continue

                # Check if this property is in the casting index and requires cast
                if prop_name in casting_props:
                    casting_info = casting_props[prop_name]
                    requires_cast = casting_info.get("requires_cast_from", [])
                    defined_on = casting_info.get("defined_on", [])
                    # Issue #15: skip if obj_var is a cast alias whose interface
                    # is in defined_on -- the cast already satisfies the property.
                    # Issue #40: normalize defined_on via _extract_interface_names
                    # so descriptive entries ("IWfiAnalysis (raw LCM)") still match
                    # -- the raw `in defined_on` check missed those, re-flagging
                    # properties like CategoryRA even after `wa = IWfiAnalysis(ana)`.
                    if cast_aliases.get(obj_var) and (
                        cast_aliases[obj_var] in _extract_interface_names(defined_on)
                    ):
                        continue
                    if requires_cast and prop_name not in [i["property"] for i in issues]:
                        # Issue #21: pick a concrete interface from the
                        # casting index and emit a structured rewrite.
                        # Issue #21 follow-up: use obj_var as the receiver
                        # tie-break signal (regex already captured it).
                        cast_iface = _pick_cast_interface(
                            prop_name,
                            casting_info.get("defined_on", []),
                            casting_index,
                            receiver_name=obj_var,
                        )
                        rewrite = _build_cast_rewrite(
                            tree, line_num, prop_name, cast_iface or ""
                        ) if cast_iface else None
                        imports_needed = _imports_for_interface(cast_iface)

                        # New issue not caught by known patterns
                        issues.append({
                            "property": prop_name,
                            "line": line_num,
                            "pattern": line_content[:80],
                            "found_at": line_content.strip()[:120],
                            "missing_on": requires_cast,
                            "available_on": casting_info.get("defined_on", []),
                            "fix": f"Cast {obj_var} to {casting_info.get('defined_on', ['concrete type'])[0]}",
                            "flexicon_helper": "Use resolve_property() tool to find exact casting requirements",
                            "severity": "warning",
                            "rewrite": rewrite,
                            "imports_needed": imports_needed,
                            "cast_interface": cast_iface,
                        })

    # Determine injection tier based on what was found
    # Tier 1 (none): No casting issues detected → Don't inject helpers
    # Tier 2 (minimal): Issues found → Inject only helpers that are needed
    # Tier 3 (full): Unusual situation → Inject full suite for safety
    if len(issues) == 0:
        injection_tier = "none"
    else:
        injection_tier = "minimal"  # Can switch to "full" for defensive mode

    return {
        "has_casting_issues": len(issues) > 0,
        "casting_issues": issues,
        "helpers_needed": helpers_needed,  # Which specific helpers to inject
        "injection_tier": injection_tier,  # Strategy: none | minimal | full
        "known_polymorphic_patterns": list(KNOWN_CASTING_PATTERNS.keys()),
        "severity": "error" if issues else "none"
    }
