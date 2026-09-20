#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T026: the CP1 boundary regression -- **the CP1 surface** detects, scans and
reports, but never constructs a parser, never loads a grammar, never parses
a word, and never infers parseability from database state (SPEC 3.1).

SCOPE, NARROWED AT CP2b (research.md R-06). This file used to be a
statement about the whole repository, and that reading was correct while
the repository parsed nothing. CP2b is the checkpoint where the assistant
reaches the parser, so the repository-wide reading is now false -- by
design, not by accident. The guarantee is therefore restated as one about
the **CP1 diagnostic surface**: detection, health and the grammar scan
still never parse.

That is the guarantee CP2b makes easiest to break and the one worth
keeping. A health check that quietly started parsing would need a grammar,
would become slow, and would report parseability it inferred rather than
measured -- which is the whole failure the CP1 boundary was drawn against.

The file was **amended, never weakened**. The scan still walks the entire
``src/flextoolsmcp/server/**`` tree by ``rglob``; nothing is skipped. One
violation kind (``parse_operation``) is allowed in one file (the long-lived
parse worker), that allowlist is pinned by its own test class, and parser
*construction* remains forbidden everywhere including there. Deleting the
file instead would have discarded the diagnostic-path guarantee entirely.

Two checks, deliberately combinable rather than one unfalsifiable "no code
path ever does X" assertion:

**(a) Static** -- an AST scan (plus a tokenizer-backed literal scan) over
the whole ``src/flextoolsmcp/server/**`` tree asserting no ``HCParser(``
construction call exists anywhere, no construction is reached through
``getattr``/``eval``/``import_module`` on a computed or literal name, and
no reflective-instantiation API (``Activator.CreateInstance``,
``ConstructorInfo.Invoke``, ...) is called. The tree is walked with
``rglob``, never a hardcoded file list, so modules that land later
(``handlers/grammar_health.py``, further ``scan/`` rows) are covered the
moment they exist.

``parser_probe.py``'s own ``Assembly.LoadFile`` / ``GetTypes`` /
``GetConstructors`` / ``GetMethods`` reflection is *inspection*, not
construction -- SPEC 5.4 requires it (the capability probe reflects over
exactly the members this feature will later bind). It is therefore excluded
by construction: the scanner classifies reflection APIs into a read-only
allowlist and an instantiating denylist, and
``test_parser_probe_inspection_reflection_is_present_and_not_flagged``
pins that the allowlisted calls really do occur in that file -- so the
exclusion is demonstrably exercised rather than silently vacuous.

**(b) Dynamic** -- a spy installed over the CLR construction seam itself
(fake ``clr`` / ``System`` / ``SIL.*`` modules in ``sys.modules``, where
every constructor call, ``Activator.CreateInstance``, ``*.Invoke`` and
``ParseWord``/``TraceWordXml``/``Update`` invocation is recorded) while the
CP1 entry points are exercised: ``ParserDetector()``,
``parser_probe._load_parser_core_members`` (the one function that actually
touches the CLR), ``handle_flextools_health``, and every ``_scan_*`` row in
``scan/grammar_scan_module.py`` plus ``run_grammar_scan`` itself, driven by
a recording fake ``project``. Zero forbidden invocations is the assertion;
the same recorder also proves the exercise was not vacuous (it must have
recorded *some* allowed reflection and *some* project attribute reads).

The task text says "runs the full CP1 test suite with a spy". A literal
nested ``pytest`` invocation was rejected: the CP1 suite is mid-wave (some
test modules intentionally fail-loud against handlers that have not landed
yet -- see ``tests/test_grammar_health.py``'s import of
``server.handlers.grammar_health``), so a nested run's exit status would
report those, not the boundary. Driving the CP1 entry points directly under
the same spy tests the same thing without inheriting an unrelated red.

Why both halves are needed: static alone misses construction reached via a
computed string or ``getattr``; dynamic alone misses dead code the exercise
never reaches. Neither half is written as an unfalsifiable assertion -- each
scanner is itself tested against a planted violation (the
``test_scanner_flags_*`` / ``test_spy_records_*`` tests), so a scanner that
silently stopped working fails this file rather than passing it.

SPEC 3.1 ("never infer parseability from database state") gets its own pair:
statically, no CP1 module may name an ``IWfi*``/wordform-collection
identifier in *code* (docstrings may discuss them -- ``grammar_scan_module``
cites ``IWfiMorphBundle.IsComplete`` as precedent in prose, which is why
this is an AST scan over ``Name``/``Attribute`` nodes and not a grep);
dynamically, no attribute path the fake ``project`` records during the whole
grammar scan may match that family.

Scoping note: the HCParser-construction scan runs tree-wide. The 3.1 scan
and the ``LcmCache`` prohibition run over the **CP1 module set** only --
``parser_probe.py``, everything under ``scan/``, and
``handlers/*health*.py`` (a glob, so ``grammar_health.py`` joins
automatically). The rest of the server legitimately discusses and, in
``handlers/execution.py``, legitimately opens LCM caches and names the
analysis classes; CP1 is the boundary under guard, not the whole product.
"""

from __future__ import annotations

import ast
import asyncio
import io
import re
import subprocess
import sys
import tokenize
import types
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest


# ---------------------------------------------------------------------------
# Tree discovery -- rglob, never a hardcoded file list (later waves add
# handlers/grammar_health.py, a dispatch.py entry and scan rows 3/5/8).
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_ROOT = REPO_ROOT / "src" / "flextoolsmcp" / "server"


def _python_files(root: Path) -> List[Path]:
    """Every .py file under ``root``, __pycache__ excluded, sorted."""
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def server_tree_files() -> List[Path]:
    return _python_files(SERVER_ROOT)


def cp1_module_files() -> List[Path]:
    """The CP1 module set, discovered by shape so future files join it.

    - ``parser_probe.py`` -- the detection spine (SPEC 5.4).
    - ``scan/**`` -- the static grammar-health scan (SPEC 9.5.4/9.5.5).
    - ``handlers/*health*.py`` -- ``diagnostic_health.py`` today,
      ``grammar_health.py`` when T020's handler lands.
    """
    found: List[Path] = []
    probe = SERVER_ROOT / "parser_probe.py"
    if probe.exists():
        found.append(probe)
    scan_dir = SERVER_ROOT / "scan"
    if scan_dir.is_dir():
        found.extend(_python_files(scan_dir))
    handlers_dir = SERVER_ROOT / "handlers"
    if handlers_dir.is_dir():
        found.extend(
            p for p in sorted(handlers_dir.glob("*health*.py"))
            if "__pycache__" not in p.parts
        )
    return sorted(set(found))


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:  # pragma: no cover - defensive
        return str(path)


# ---------------------------------------------------------------------------
# Vocabulary under guard
# ---------------------------------------------------------------------------

# Constructing any of these crosses the CP1 boundary, anywhere in the tree.
FORBIDDEN_CONSTRUCTED_TYPES = frozenset({
    "HCParser",
    "XAmpleParser",
    "ParseFiler",
    "ParserWorker",
})

# Additionally forbidden inside the CP1 module set. ``handlers/execution.py``
# legitimately opens a cache for the run-module spine, so this one is not a
# tree-wide rule.
CP1_FORBIDDEN_CONSTRUCTED_TYPES = FORBIDDEN_CONSTRUCTED_TYPES | frozenset({"LcmCache"})

# Callables that turn a *name* into an object -- the computed-string route
# a pure AST call-node scan would otherwise miss.
DYNAMIC_DISPATCH_CALLABLES = frozenset({
    "getattr", "eval", "exec", "__import__", "import_module", "create_instance",
})

# Reflection that *instantiates* or *invokes*, as opposed to inspecting.
# None of these exists in the tree today; the rule is here so the first one
# to appear is caught.
INSTANTIATING_REFLECTION = frozenset({
    "CreateInstance",
    "CreateInstanceFrom",
    "CreateInstanceAndUnwrap",
    "InvokeMember",
    "Invoke",
})

# Reflection that only *reads* the member surface. SPEC 5.4 requires exactly
# this in parser_probe.py; it is never a boundary crossing.
INSPECTING_REFLECTION = frozenset({
    "LoadFile",
    "LoadFrom",
    "GetTypes",
    "GetType",
    "GetName",
    "GetMembers",
    "GetMethods",
    "GetConstructors",
    "GetParameters",
    "GetGenericArguments",
    "GetElementType",
    "AddReference",
})

# Calling any of these means a word was parsed or a grammar was loaded.
PARSE_OPERATION_NAMES = frozenset({
    "ParseWord",
    "ParseWordXml",
    "TraceWordXml",
    "ProcessParse",
    "LoadGrammar",
    "LoadLanguage",
})

# SPEC 3.1: the analysis/wordform family. Reading any of these to say
# something about parseability is the forbidden inference; CP1 does not read
# them at all, which is the stronger and far cheaper property to assert.
ANALYSIS_STATE_PATTERN = re.compile(
    r"(?:^|[._])(?:I?Wfi[A-Za-z]*"
    r"|Wordform(?:s|Inventory[A-Za-z]*|sOC)?"
    r"|UniqueWordforms"
    r"|Analyses(?:OC|RS)?"
    r"|AnalysisOccurrence[A-Za-z]*"
    r"|ParserCount)(?:$|[._(])"
)

# Argv tokens that would mean the sandbox spine actually ran a parse.
FORBIDDEN_SUBPROCESS_ARGV = frozenset({"hc", "parse", "parse-words", "GenerateHCConfig.exe"})


# ---------------------------------------------------------------------------
# (a) Static scanners
# ---------------------------------------------------------------------------

class Violation(tuple):
    """(kind, file, lineno, detail) with a readable repr for assert output."""

    def __new__(cls, kind: str, filename: str, lineno: int, detail: str):
        return super().__new__(cls, (kind, filename, lineno, detail))

    def __repr__(self) -> str:
        kind, filename, lineno, detail = self
        return f"{kind} at {filename}:{lineno} -- {detail}"


def _callee_name(node: ast.AST) -> Optional[str]:
    """The trailing identifier of a call target, or None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _dotted_name(node: ast.AST) -> Optional[str]:
    """``a.b.c`` for Name/Attribute chains, else None."""
    parts: List[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if not isinstance(cur, ast.Name):
        return None
    parts.append(cur.id)
    return ".".join(reversed(parts))


def _joined_string_constants(node: ast.AST) -> Optional[str]:
    """Fold a literal string ``+`` chain into one string (``"HC" + "Parser"``)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _joined_string_constants(node.left)
        right = _joined_string_constants(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def scan_source_for_construction(
    source: str,
    filename: str,
    forbidden_types: frozenset = FORBIDDEN_CONSTRUCTED_TYPES,
) -> List[Violation]:
    """AST + literal scan of one module for CP1 boundary crossings.

    Returns every violation found; an empty list means the module is clean.
    Split out as a plain function over a source string so the scanner itself
    can be tested against planted violations (see TestScannersAreFalsifiable)
    without writing a bad file into the tree.
    """
    violations: List[Violation] = []
    tree = ast.parse(source, filename=filename)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        name = _callee_name(node.func)

        # 1. Direct construction: HCParser(cache) / module.HCParser(cache).
        if name in forbidden_types:
            violations.append(Violation(
                "direct_construction", filename, node.lineno, f"{name}(...) called",
            ))

        # 2. A factory/static call hung off a forbidden type
        #    (LcmCache.CreateCacheFor..., HCParser.Create...): the receiver,
        #    not the method, is what gives it away.
        receiver = node.func.value if isinstance(node.func, ast.Attribute) else None
        if receiver is not None:
            receiver_name = _dotted_name(receiver)
            if receiver_name and receiver_name.split(".")[-1] in forbidden_types:
                violations.append(Violation(
                    "factory_construction", filename, node.lineno,
                    f"{receiver_name}.{name}(...) called",
                ))

        # 3. Name-driven construction: getattr(mod, "HCParser")(cache),
        #    import_module("...HCParser..."), eval("HCParser(cache)").
        if name in DYNAMIC_DISPATCH_CALLABLES:
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                literal = _joined_string_constants(arg)
                if literal is None:
                    continue
                for forbidden in forbidden_types:
                    if forbidden in literal:
                        violations.append(Violation(
                            "dynamic_construction", filename, node.lineno,
                            f"{name}(..., {literal!r}) names {forbidden}",
                        ))

        # 4. Reflective instantiation/invocation. Inspection-only reflection
        #    (Assembly.LoadFile, GetMembers, GetConstructors, ...) is SPEC
        #    5.4's own probe and is never flagged here.
        if name in INSTANTIATING_REFLECTION:
            violations.append(Violation(
                "reflective_instantiation", filename, node.lineno,
                f"{name}(...) instantiates or invokes a reflected member",
            ))

        # 5. A parse actually happening.
        if name in PARSE_OPERATION_NAMES:
            violations.append(Violation(
                "parse_operation", filename, node.lineno, f"{name}(...) called",
            ))

    # 6. Literal scan over code text with comments and every string literal
    #    (including f-string bodies) removed. Catches call shapes the node
    #    rules above did not enumerate -- e.g. a call through a parenthesised
    #    or subscripted expression -- without the false positives a raw grep
    #    would hit on parser_probe.py's own member-name strings.
    for forbidden in sorted(forbidden_types):
        pattern = re.compile(r"\b" + re.escape(forbidden) + r"\s*\(")
        for lineno, text in _code_only_lines(source).items():
            if pattern.search(text):
                violations.append(Violation(
                    "literal_construction", filename, lineno,
                    f"{forbidden}( appears in executable code text",
                ))

    # De-duplicate: rules 1 and 6 intentionally overlap on the plain case.
    seen = set()
    unique: List[Violation] = []
    for v in violations:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


_FSTRING_START = getattr(tokenize, "FSTRING_START", None)
_FSTRING_END = getattr(tokenize, "FSTRING_END", None)


def _code_only_lines(source: str) -> Dict[int, str]:
    """Map lineno -> executable token text, with comments, string literals
    and f-string bodies stripped.

    A string can never itself construct anything, so removing them is what
    lets this scan coexist with ``parser_probe.py``'s ``"HCParser(LcmCache)"``
    member-name constants and its ``f"HCParser({params})"`` signature
    rendering. Interpolated expressions inside f-strings are dropped here
    too -- rule 1 (AST) already covers those.
    """
    lines: Dict[int, List[str]] = {}
    fstring_depth = 0
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError):  # pragma: no cover - defensive
        return {}
    for tok in tokens:
        if _FSTRING_START is not None and tok.type == _FSTRING_START:
            fstring_depth += 1
            continue
        if _FSTRING_END is not None and tok.type == _FSTRING_END:
            fstring_depth = max(0, fstring_depth - 1)
            continue
        if fstring_depth:
            continue
        if tok.type in (tokenize.COMMENT, tokenize.STRING, tokenize.NL, tokenize.NEWLINE):
            continue
        lines.setdefault(tok.start[0], []).append(tok.string)
    return {lineno: " ".join(parts) for lineno, parts in lines.items()}


def scan_source_for_analysis_state_reads(source: str, filename: str) -> List[Violation]:
    """SPEC 3.1 static half: no CP1 module may *read* the analysis/wordform
    family in code.

    AST-only (``Name``/``Attribute``/``alias``), so prose that discusses the
    family is fine -- ``grammar_scan_module.py`` cites
    ``IWfiMorphBundle.IsComplete`` in a docstring as the LCM precedent for
    ``IMoForm.IsComplete``, and that must stay legal.
    """
    violations: List[Violation] = []
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        candidate: Optional[str] = None
        if isinstance(node, ast.Name):
            candidate = node.id
        elif isinstance(node, ast.Attribute):
            candidate = node.attr
        elif isinstance(node, ast.alias):
            candidate = node.asname or node.name
        if candidate and ANALYSIS_STATE_PATTERN.search("." + candidate):
            lineno = getattr(node, "lineno", 0)
            violations.append(Violation(
                "analysis_state_read", filename, lineno,
                f"{candidate} names the analysis/wordform family (SPEC 3.1)",
            ))
        # A computed read: getattr(obj, "AnalysesOC").
        if isinstance(node, ast.Call) and _callee_name(node.func) in DYNAMIC_DISPATCH_CALLABLES:
            for arg in node.args:
                literal = _joined_string_constants(arg)
                if literal and ANALYSIS_STATE_PATTERN.search("." + literal):
                    violations.append(Violation(
                        "analysis_state_read", filename, node.lineno,
                        f"getattr-style read of {literal!r} (SPEC 3.1)",
                    ))
    return violations


def subprocess_argv_literals(source: str, filename: str) -> List[Tuple[int, List[str]]]:
    """Every literal argv list handed to subprocess in one module.

    Module-level ``NAME = "literal"`` constants are resolved, so
    ``[dotnet, "tool", "list", "-g"]`` and a constant-driven ``[HC_EXE]``
    are both visible. Non-literal elements come back as ``None`` entries.
    """
    tree = ast.parse(source, filename=filename)
    constants: Dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = node.value.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str) and isinstance(node.target, ast.Name):
                constants[node.target.id] = node.value.value

    found: List[Tuple[int, List[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _callee_name(node.func) not in {"run", "Popen", "call", "check_call", "check_output"}:
            continue
        if not node.args:
            continue
        argv_node = node.args[0]
        if not isinstance(argv_node, (ast.List, ast.Tuple)):
            continue
        argv: List[str] = []
        for element in argv_node.elts:
            literal = _joined_string_constants(element)
            if literal is None and isinstance(element, ast.Name):
                literal = constants.get(element.id)
            if literal is not None:
                argv.append(literal)
        found.append((node.lineno, argv))
    return found


# ---------------------------------------------------------------------------
# (a) Static tests
# ---------------------------------------------------------------------------

class TestTreeDiscoveryIsNotVacuous:
    """A scan over zero files passes every assertion below it. Pin the walk
    before trusting anything it reports."""

    def test_server_tree_exists_and_is_substantial(self):
        files = server_tree_files()
        assert len(files) >= 10, f"only found {len(files)} modules under {SERVER_ROOT}"

    def test_walk_is_recursive_and_includes_the_cp1_files(self):
        found = {_rel(p).replace("\\", "/") for p in server_tree_files()}
        for required in (
            "src/flextoolsmcp/server/parser_probe.py",
            "src/flextoolsmcp/server/scan/grammar_scan_module.py",
            "src/flextoolsmcp/server/handlers/diagnostic_health.py",
            "src/flextoolsmcp/server/dispatch.py",
        ):
            assert required in found, f"{required} missing from the tree walk"

    def test_cp1_module_set_is_discovered_by_shape(self):
        cp1 = {_rel(p).replace("\\", "/") for p in cp1_module_files()}
        assert "src/flextoolsmcp/server/parser_probe.py" in cp1
        assert "src/flextoolsmcp/server/scan/grammar_scan_module.py" in cp1
        assert "src/flextoolsmcp/server/handlers/diagnostic_health.py" in cp1
        # handlers/grammar_health.py joins this set automatically when T020
        # lands -- the glob is the point, so assert the glob, not the file.
        assert all(p.exists() for p in cp1_module_files())


#: The ONLY files permitted to call a parse operation (CP2b, research.md
#: R-06). One entry: the long-lived parse worker.
#:
#: WHY THIS EXISTS AT ALL. Before CP2b this repository parsed no words, so
#: "no parse operation anywhere in the tree" was both true and the whole
#: point. CP2b is the checkpoint where the assistant reaches the parser, so
#: that statement stops being true of the repository -- but it must stay
#: true of the **CP1 diagnostic surface**, which is the guarantee CP2b makes
#: easiest to break: a health check that quietly started parsing would be
#: slow, would need a grammar, and would report parseability it inferred
#: rather than measured.
#:
#: SO THE FILE IS AMENDED, NEVER WEAKENED. The scan still walks the whole
#: tree by ``rglob``; no file is skipped. What is narrowed is exactly one
#: violation *kind* in exactly one *file*: ``parse_operation`` in the
#: worker. Construction violations -- ``HCParser(...)``, reflective
#: instantiation -- remain forbidden there too, because the worker reaches
#: the parser through flexicon's facade and constructs nothing itself. A
#: blanket per-file exemption would have thrown that away silently.
#:
#: The allowlist is pinned by ``TestTheParseAllowlistIsPinned`` below, so
#: widening it means editing a test that says why -- the same control CP2a's
#: QC gate imposed on ``NON_CONTRACT_PREFIXES``, and the reason a future
#: handler cannot quietly append itself here.
CP2B_PARSE_OPERATION_ALLOWLIST = frozenset(
    {"src/flextoolsmcp/server/parse/worker_main.py"}
)

#: The package that owns parser execution (FR-026, "one run mechanism").
CP2B_PARSE_PACKAGE = "src/flextoolsmcp/server/parse/"


def _is_parse_operation_allowed(rel_path: str) -> bool:
    return rel_path.replace("\\", "/") in CP2B_PARSE_OPERATION_ALLOWLIST


def scan_with_cp2b_allowlist(source: str, rel_path: str) -> List[Violation]:
    """``scan_source_for_construction`` with CP2b's narrow exception applied.

    Drops ``parse_operation`` violations for an allowlisted file and nothing
    else. Every other kind, and every other file, is reported unchanged.
    """
    violations = scan_source_for_construction(source, rel_path)
    if not _is_parse_operation_allowed(rel_path):
        return violations
    return [v for v in violations if v[0] != "parse_operation"]


class TestStaticNoParserConstructionAnywhereInTheTree:
    """(a) -- no literal or computed ``HCParser(`` construction, tree-wide.

    Since CP2b, also: no parse operation anywhere except the one allowlisted
    worker module. Construction remains forbidden everywhere, including
    there.
    """

    @pytest.mark.parametrize(
        "path", server_tree_files(), ids=lambda p: _rel(p).replace("\\", "/")
    )
    def test_module_constructs_no_parser(self, path: Path):
        rel = _rel(path)
        violations = scan_with_cp2b_allowlist(path.read_text(encoding="utf-8"), rel)
        assert violations == [], "\n".join(repr(v) for v in violations)

    def test_whole_tree_reports_zero_violations(self):
        """The per-file parametrisation above is the readable failure; this
        is the single assertion the boundary is actually stated as."""
        all_violations: List[Violation] = []
        for path in server_tree_files():
            rel = _rel(path)
            all_violations.extend(
                scan_with_cp2b_allowlist(path.read_text(encoding="utf-8"), rel)
            )
        assert all_violations == [], "\n".join(repr(v) for v in all_violations)

    def test_the_worker_still_constructs_no_parser_itself(self):
        """The allowlist buys `parse_operation`, not construction.

        The worker reaches the parser through flexicon's facade, which
        constructs `HCParser` inside flexicon -- outside this tree. If the
        worker ever constructs one directly, that is a boundary crossing
        the allowlist deliberately does not cover.
        """
        worker = REPO_ROOT / "src/flextoolsmcp/server/parse/worker_main.py"
        assert worker.exists(), "the allowlisted worker module is missing"

        violations = scan_source_for_construction(
            worker.read_text(encoding="utf-8"), _rel(worker)
        )
        construction = [v for v in violations if v[0] != "parse_operation"]
        assert construction == [], "\n".join(repr(v) for v in construction)


class TestTheParseAllowlistIsPinned:
    """Widening the allowlist must mean editing a test, not appending a line.

    This is the control that keeps the amendment from decaying into a
    general exemption. Without it, a future module that started parsing
    could be added to the allowlist in one line and nothing would notice.
    """

    def test_the_allowlist_is_exactly_the_worker(self):
        assert CP2B_PARSE_OPERATION_ALLOWLIST == frozenset(
            {"src/flextoolsmcp/server/parse/worker_main.py"}
        ), (
            "The parse-operation allowlist changed. It is meant to hold "
            "exactly one entry -- the long-lived parse worker. Adding a "
            "second means some other module now parses words, which is "
            "either a second execution path (FR-026 forbids one) or the "
            "CP1 diagnostic surface starting to parse (the guarantee this "
            "file exists to protect). Justify it here or revert it."
        )

    def test_every_allowlisted_file_exists(self):
        """A stale entry silently exempts nothing and hides a moved file."""
        for rel in CP2B_PARSE_OPERATION_ALLOWLIST:
            assert (REPO_ROOT / rel).exists(), f"allowlisted file missing: {rel}"

    def test_every_allowlisted_file_lives_in_the_parse_package(self):
        """FR-026: parser execution belongs to one package."""
        for rel in CP2B_PARSE_OPERATION_ALLOWLIST:
            assert rel.startswith(CP2B_PARSE_PACKAGE), (
                f"{rel} parses words but lives outside {CP2B_PARSE_PACKAGE}"
            )

    def test_the_allowlist_actually_suppresses_something(self):
        """A vacuous allowlist would pass this file while protecting nothing.

        The worker really must contain parse operations; if it stopped
        doing so the allowlist would be dead weight and this test says so
        rather than letting it sit there looking meaningful.
        """
        worker = REPO_ROOT / "src/flextoolsmcp/server/parse/worker_main.py"
        raw = scan_source_for_construction(
            worker.read_text(encoding="utf-8"), _rel(worker)
        )
        assert any(v[0] == "parse_operation" for v in raw), (
            "the worker contains no parse operations, so the allowlist "
            "entry for it is exempting nothing"
        )


class TestNoParserExecutionOutsideTheParsePackage:
    """FR-026's structural half: one mechanism, in one package (T060).

    The behavioural half -- that a single word is a run like any other --
    lives in `tests/test_parse_runner.py`. This is the half that survives a
    refactor: a handler that reached the facade directly would be a second
    execution path no matter how it behaved, and it would look perfectly
    reasonable in review.
    """

    def test_no_handler_reaches_the_parser_facade(self):
        handlers_dir = SERVER_ROOT / "handlers"
        offenders: List[Violation] = []
        for path in _python_files(handlers_dir):
            offenders.extend(
                v
                for v in scan_source_for_construction(
                    path.read_text(encoding="utf-8"), _rel(path)
                )
                if v[0] == "parse_operation"
            )
        assert offenders == [], (
            "a handler reaches the parser facade directly. All parser "
            "execution goes through the run mechanism in "
            f"{CP2B_PARSE_PACKAGE} (FR-026):\n"
            + "\n".join(repr(v) for v in offenders)
        )

    def test_parse_operations_in_the_tree_are_confined_to_the_parse_package(self):
        outside: List[str] = []
        for path in server_tree_files():
            rel = _rel(path).replace("\\", "/")
            if rel.startswith(CP2B_PARSE_PACKAGE):
                continue
            if any(
                v[0] == "parse_operation"
                for v in scan_source_for_construction(
                    path.read_text(encoding="utf-8"), rel
                )
            ):
                outside.append(rel)
        assert outside == [], (
            "these modules parse words outside "
            f"{CP2B_PARSE_PACKAGE}: {outside}"
        )


class TestStaticCP1ModulesOpenNoCacheAndRunNoParse:
    @pytest.mark.parametrize(
        "path", cp1_module_files(), ids=lambda p: _rel(p).replace("\\", "/")
    )
    def test_cp1_module_constructs_nothing_and_parses_nothing(self, path: Path):
        violations = scan_source_for_construction(
            path.read_text(encoding="utf-8"),
            _rel(path),
            forbidden_types=CP1_FORBIDDEN_CONSTRUCTED_TYPES,
        )
        assert violations == [], "\n".join(repr(v) for v in violations)

    @pytest.mark.parametrize(
        "path", cp1_module_files(), ids=lambda p: _rel(p).replace("\\", "/")
    )
    def test_cp1_module_never_shells_out_to_the_parser(self, path: Path):
        """The sandbox spine is *discovered* at CP1 (``dotnet tool list -g``),
        never *run* -- running ``hc`` is loading a grammar and parsing."""
        offenders = []
        for lineno, argv in subprocess_argv_literals(
            path.read_text(encoding="utf-8"), _rel(path)
        ):
            for token in argv:
                if token in FORBIDDEN_SUBPROCESS_ARGV:
                    offenders.append((lineno, argv, token))
        assert offenders == [], f"{_rel(path)}: {offenders}"

    def test_the_only_cp1_subprocess_is_the_dotnet_discovery_call(self):
        """Non-vacuity for the test above: there IS a subprocess call in the
        CP1 set, and it is the tool-list discovery one."""
        argvs = []
        for path in cp1_module_files():
            argvs.extend(
                argv for _, argv in subprocess_argv_literals(
                    path.read_text(encoding="utf-8"), _rel(path)
                )
            )
        assert argvs, "expected discover_hc_tool's subprocess call to be visible"
        assert any({"tool", "list", "-g"}.issubset(set(argv)) for argv in argvs), argvs


class TestParserProbeInspectionReflectionIsExcludedNotIgnored:
    """The exclusion the task names -- ``parser_probe.py``'s own
    ``Assembly.LoadFile`` / ``GetMembers``-family reflection -- is excluded
    because it inspects rather than instantiates. Assert it is really there,
    so the exclusion is exercised rather than vacuous."""

    def test_probe_really_does_reflect(self):
        source = (SERVER_ROOT / "parser_probe.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        reflective = {
            _callee_name(n.func)
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and _callee_name(n.func) in INSPECTING_REFLECTION
        }
        assert "LoadFile" in reflective
        assert {"GetTypes", "GetConstructors", "GetMethods"} <= reflective

    def test_that_reflection_is_not_reported_as_a_violation(self):
        source = (SERVER_ROOT / "parser_probe.py").read_text(encoding="utf-8")
        violations = scan_source_for_construction(
            source, "parser_probe.py", forbidden_types=CP1_FORBIDDEN_CONSTRUCTED_TYPES
        )
        assert violations == [], "\n".join(repr(v) for v in violations)

    def test_the_allowlist_and_denylist_do_not_overlap(self):
        assert not (INSPECTING_REFLECTION & INSTANTIATING_REFLECTION)


class TestStaticNeverInfersParseabilityFromDatabaseState:
    """SPEC 3.1, static half."""

    @pytest.mark.parametrize(
        "path", cp1_module_files(), ids=lambda p: _rel(p).replace("\\", "/")
    )
    def test_cp1_module_reads_no_analysis_or_wordform_identifier(self, path: Path):
        violations = scan_source_for_analysis_state_reads(
            path.read_text(encoding="utf-8"), _rel(path)
        )
        assert violations == [], "\n".join(repr(v) for v in violations)

    def test_prose_may_still_discuss_the_family(self):
        """grammar_scan_module.py cites IWfiMorphBundle.IsComplete in a
        docstring as LCM precedent. An AST scan must not flag that -- a grep
        would, which is why this is not a grep."""
        source = (SERVER_ROOT / "scan" / "grammar_scan_module.py").read_text(encoding="utf-8")
        assert "IWfiMorphBundle" in source, "precedent citation gone; update this test"
        assert scan_source_for_analysis_state_reads(source, "grammar_scan_module.py") == []


class TestScannersAreFalsifiable:
    """Every scanner above, fed a planted violation. A scanner that silently
    stopped matching would turn this whole file green for the wrong reason;
    these are what stop that."""

    @pytest.mark.parametrize("snippet,kind", [
        ("parser = HCParser(cache)", "direct_construction"),
        ("parser = parser_core.HCParser(cache)", "direct_construction"),
        ("cache = LcmCache.CreateCacheForNewLcmProject('p')", "factory_construction"),
        ("cls = getattr(mod, 'HCParser')\nparser = cls(cache)", "dynamic_construction"),
        ("cls = getattr(mod, 'HC' + 'Parser')", "dynamic_construction"),
        ("mod = import_module('SIL.FieldWorks.WordWorks.Parser.HCParser')", "dynamic_construction"),
        ("parser = eval('HCParser(cache)')", "dynamic_construction"),
        ("obj = Activator.CreateInstance(clr_type)", "reflective_instantiation"),
        ("obj = ctor.Invoke(None)", "reflective_instantiation"),
        ("result = parser.ParseWord('menulis')", "parse_operation"),
        ("xml = parser.TraceWordXml('menulis', [])", "parse_operation"),
    ])
    def test_construction_scanner_flags_a_planted_violation(self, snippet, kind):
        violations = scan_source_for_construction(
            snippet, "<planted>", forbidden_types=CP1_FORBIDDEN_CONSTRUCTED_TYPES
        )
        assert any(v[0] == kind for v in violations), (
            f"planted {kind!r} not detected; got {violations!r}"
        )

    @pytest.mark.parametrize("snippet", [
        "unparsed = [w for w in project.Wordforms.GetAll() if not w.AnalysesOC.Count]",
        "from SIL.LCModel import IWfiAnalysis",
        "n = wordform.AnalysesOC.Count",
        "words = text.UniqueWordforms()",
        "count = getattr(wf, 'AnalysesOC').Count",
        "analyses = IWfiAnalysis(obj)",
    ])
    def test_analysis_state_scanner_flags_a_planted_violation(self, snippet):
        violations = scan_source_for_analysis_state_reads(snippet, "<planted>")
        assert violations, f"planted SPEC 3.1 violation not detected: {snippet!r}"

    def test_analysis_state_scanner_accepts_the_grammar_objects_cp1_does_read(self):
        clean = (
            "from SIL.LCModel import IMoFormRepository\n"
            "for form in project.ObjectsIn(IMoFormRepository):\n"
            "    if not form.IsComplete:\n"
            "        count += 1\n"
        )
        assert scan_source_for_analysis_state_reads(clean, "<clean>") == []

    def test_construction_scanner_accepts_inspection_only_reflection(self):
        clean = (
            "assembly = System.Reflection.Assembly.LoadFile(str(path))\n"
            "for clr_type in assembly.GetTypes():\n"
            "    for ctor in clr_type.GetConstructors(flags):\n"
            "        params = [p.ParameterType for p in ctor.GetParameters()]\n"
        )
        assert scan_source_for_construction(clean, "<clean>") == []

    def test_literal_scan_ignores_strings_but_not_code(self):
        in_a_string = 'MEMBERS = ("HCParser(LcmCache)",)\n'
        assert scan_source_for_construction(in_a_string, "<clean>") == []
        in_an_fstring = 'members.add(f"HCParser({params})")\n'
        assert scan_source_for_construction(in_an_fstring, "<clean>") == []
        in_code = "p = HCParser (cache)\n"
        assert scan_source_for_construction(in_code, "<planted>") != []

    def test_subprocess_argv_extractor_resolves_module_constants(self):
        source = (
            "COMPONENT_HC = 'hc'\n"
            "def go():\n"
            "    subprocess.run([COMPONENT_HC, 'parse', 'words.txt'])\n"
        )
        argvs = subprocess_argv_literals(source, "<planted>")
        assert argvs and "hc" in argvs[0][1] and "parse" in argvs[0][1]


# ---------------------------------------------------------------------------
# (b) Dynamic spy over the CLR construction seam
# ---------------------------------------------------------------------------

class BoundarySpy:
    """Records everything the CP1 code does at the CLR / project seam.

    ``constructions``, ``parses`` and ``analysis_reads`` must all be empty
    after the exercise; ``inspections`` and ``project_reads`` must not be,
    or the exercise never reached the code it claims to guard.
    """

    def __init__(self) -> None:
        self.constructions: List[str] = []
        self.parses: List[str] = []
        self.analysis_reads: List[str] = []
        self.inspections: List[str] = []
        self.project_reads: List[str] = []
        self.subprocess_argv: List[List[str]] = []

    def clr(self, what: str) -> None:
        if what.rsplit(".", 1)[-1].rstrip("()") in PARSE_OPERATION_NAMES:
            self.parses.append(what)
        else:
            self.inspections.append(what)

    def construct(self, what: str) -> None:
        self.constructions.append(what)

    def parse(self, what: str) -> None:
        self.parses.append(what)

    def read(self, path: str) -> None:
        self.project_reads.append(path)
        if ANALYSIS_STATE_PATTERN.search("." + path.replace(".", ".")):
            self.analysis_reads.append(path)

    def summary(self) -> str:
        return (
            f"constructions={self.constructions!r} parses={self.parses!r} "
            f"analysis_reads={self.analysis_reads!r}"
        )


class _Recorder:
    """A permissive stand-in for any CLR/LCM object.

    Every attribute access and call is recorded with its dotted path, so a
    read of ``project.Wordforms.AnalysesOC`` shows up in
    ``spy.analysis_reads`` even though nothing about it raises. Comparisons
    are falsey and arithmetic returns self, so scan rows run to completion
    against it instead of dying on the first predicate.
    """

    __slots__ = ("_spy", "_path", "_depth")

    def __init__(self, spy: BoundarySpy, path: str, depth: int = 0) -> None:
        self._spy = spy
        self._path = path
        self._depth = depth

    def __getattr__(self, name: str) -> "_Recorder":
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        path = f"{self._path}.{name}"
        self._spy.read(path)
        if name in PARSE_OPERATION_NAMES:
            self._spy.parse(path)
        return _Recorder(self._spy, path, self._depth + 1)

    def __call__(self, *args: Any, **kwargs: Any) -> "_Recorder":
        self._spy.read(f"{self._path}()")
        return _Recorder(self._spy, f"{self._path}()", self._depth + 1)

    def __iter__(self):
        if self._depth > 6:
            return iter(())
        return iter([_Recorder(self._spy, f"{self._path}[item]", self._depth + 1)])

    def __getitem__(self, item: Any) -> "_Recorder":
        return _Recorder(self._spy, f"{self._path}[]", self._depth + 1)

    def __bool__(self) -> bool:
        return False

    def __len__(self) -> int:
        return 0

    def __contains__(self, item: Any) -> bool:
        return False

    def __eq__(self, other: Any) -> bool:
        return False

    def __ne__(self, other: Any) -> bool:
        return True

    def __lt__(self, other: Any) -> bool:
        return False

    def __le__(self, other: Any) -> bool:
        return False

    def __gt__(self, other: Any) -> bool:
        return False

    def __ge__(self, other: Any) -> bool:
        return False

    def __hash__(self) -> int:
        return id(self)

    def __int__(self) -> int:
        return 0

    def __index__(self) -> int:
        return 0

    def __float__(self) -> float:
        return 0.0

    def __mul__(self, other: Any) -> "_Recorder":
        return self

    __rmul__ = __mul__
    __add__ = __mul__
    __radd__ = __mul__
    __sub__ = __mul__
    __rsub__ = __mul__

    def __format__(self, spec: str) -> str:
        return "<recorder>"

    def __str__(self) -> str:
        return "<recorder>"

    def __repr__(self) -> str:
        return f"<recorder {self._path}>"


class _ClrTypeHandle:
    """A CLR type as pythonnet would project it.

    Calling it is either an LCM interface *cast* (allowed -- that is how
    ``IPhPhoneme(obj)`` is written) or an *instantiation* of a type CP1 is
    forbidden to create. The distinction is the type's own name, which is
    exactly the boundary this test exists to hold.
    """

    def __init__(self, spy: BoundarySpy, name: str) -> None:
        self._spy = spy
        self._name = name
        self.Name = name

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self._name in CP1_FORBIDDEN_CONSTRUCTED_TYPES:
            self._spy.construct(f"{self._name}(...)")
        else:
            self._spy.read(f"cast:{self._name}()")
        return _Recorder(self._spy, self._name)

    def __getattr__(self, item: str) -> Any:
        if item.startswith("__"):
            raise AttributeError(item)
        if self._name in CP1_FORBIDDEN_CONSTRUCTED_TYPES:
            # A static factory hung off a forbidden type is still a crossing.
            self._spy.construct(f"{self._name}.{item}")
        return _Recorder(self._spy, f"{self._name}.{item}")


def _make_fake_clr_namespace(spy: BoundarySpy, module_name: str) -> types.ModuleType:
    module = types.ModuleType(module_name)

    def __getattr__(name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        spy.read(f"{module_name}.{name}")
        return _ClrTypeHandle(spy, name)

    module.__getattr__ = __getattr__  # type: ignore[attr-defined]
    return module


class _FakeParam:
    def __init__(self, spy: BoundarySpy, type_name: str) -> None:
        self._spy = spy
        self.ParameterType = _FakeClrType(spy, type_name, members=False)


class _FakeMember:
    """A reflected constructor or method. Inspecting it is fine; ``Invoke``
    is the boundary crossing and is recorded as one."""

    def __init__(self, spy: BoundarySpy, name: str, param_types: Tuple[str, ...]) -> None:
        self._spy = spy
        self.Name = name
        self._param_types = param_types

    def GetParameters(self) -> List[_FakeParam]:
        self._spy.clr(f"{self.Name}.GetParameters")
        return [_FakeParam(self._spy, t) for t in self._param_types]

    def Invoke(self, *args: Any) -> Any:
        self._spy.construct(f"{self.Name}.Invoke(...)")
        return _Recorder(self._spy, self.Name)


class _FakeClrType:
    def __init__(self, spy: BoundarySpy, name: str, members: bool = True) -> None:
        self._spy = spy
        self.Name = name
        self.FullName = f"SIL.FieldWorks.WordWorks.Parser.{name}"
        self.IsGenericType = False
        self.IsArray = False
        self._members = members

    def GetConstructors(self, flags: Any = None) -> List[_FakeMember]:
        self._spy.clr(f"{self.Name}.GetConstructors")
        if not self._members:
            return []
        return [_FakeMember(self._spy, self.Name, ("LcmCache",))]

    def GetMethods(self, flags: Any = None) -> List[_FakeMember]:
        self._spy.clr(f"{self.Name}.GetMethods")
        if not self._members:
            return []
        if self.Name == "ParseFiler":
            return [_FakeMember(self._spy, "ProcessParse", ())]
        return [
            _FakeMember(self._spy, "Update", ()),
            _FakeMember(self._spy, "ParseWord", ("String",)),
            _FakeMember(self._spy, "ParseWordXml", ("String",)),
        ]

    def GetMembers(self, flags: Any = None) -> List[_FakeMember]:
        self._spy.clr(f"{self.Name}.GetMembers")
        return self.GetConstructors(flags) + self.GetMethods(flags)

    def GetGenericArguments(self) -> List["_FakeClrType"]:
        self._spy.clr(f"{self.Name}.GetGenericArguments")
        return []

    def GetElementType(self) -> "_FakeClrType":
        self._spy.clr(f"{self.Name}.GetElementType")
        return self


class _FakeAssemblyName:
    class _Version:
        Major, Minor, Build, Revision = 9, 3, 7, 0

    Version = _Version()


class _FakeAssembly:
    def __init__(self, spy: BoundarySpy) -> None:
        self._spy = spy

    def GetName(self) -> _FakeAssemblyName:
        self._spy.clr("Assembly.GetName")
        return _FakeAssemblyName()

    def GetTypes(self) -> List[_FakeClrType]:
        self._spy.clr("Assembly.GetTypes")
        return [
            _FakeClrType(self._spy, "HCParser"),
            _FakeClrType(self._spy, "ParseFiler"),
        ]

    def CreateInstance(self, name: str, *args: Any) -> Any:
        self._spy.construct(f"Assembly.CreateInstance({name!r})")
        return _Recorder(self._spy, name)


def _install_fake_clr(monkeypatch: pytest.MonkeyPatch, spy: BoundarySpy) -> None:
    """Put a recording CLR in ``sys.modules`` for the duration of one test.

    ``monkeypatch.setitem`` restores the previous entry (including "absent"),
    so a machine that really has pythonnet installed is unaffected after the
    test, and a machine without one still exercises the reflection path.
    """

    class _Assembly:
        @staticmethod
        def LoadFile(path: str) -> _FakeAssembly:
            spy.clr("Assembly.LoadFile")
            return _FakeAssembly(spy)

        @staticmethod
        def LoadFrom(path: str) -> _FakeAssembly:
            spy.clr("Assembly.LoadFrom")
            return _FakeAssembly(spy)

    class _BindingFlags:
        Public, Instance, Static, DeclaredOnly, NonPublic = 1, 2, 4, 8, 16

    class _Activator:
        @staticmethod
        def CreateInstance(clr_type: Any, *args: Any) -> Any:
            spy.construct("Activator.CreateInstance")
            return _Recorder(spy, "instance")

    reflection = types.ModuleType("System.Reflection")
    reflection.Assembly = _Assembly  # type: ignore[attr-defined]
    reflection.BindingFlags = _BindingFlags  # type: ignore[attr-defined]

    system = types.ModuleType("System")
    system.Reflection = reflection  # type: ignore[attr-defined]
    system.Activator = _Activator  # type: ignore[attr-defined]

    clr_module = types.ModuleType("clr")
    clr_module.AddReference = lambda name: spy.clr("clr.AddReference")  # type: ignore[attr-defined]

    sil = types.ModuleType("SIL")
    fieldworks = types.ModuleType("SIL.FieldWorks")
    wordworks = types.ModuleType("SIL.FieldWorks.WordWorks")

    modules = {
        "clr": clr_module,
        "System": system,
        "System.Reflection": reflection,
        "SIL": sil,
        "SIL.FieldWorks": fieldworks,
        "SIL.FieldWorks.WordWorks": wordworks,
        "SIL.LCModel": _make_fake_clr_namespace(spy, "SIL.LCModel"),
        "SIL.FieldWorks.WordWorks.Parser": _make_fake_clr_namespace(
            spy, "SIL.FieldWorks.WordWorks.Parser"
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    sil.LCModel = modules["SIL.LCModel"]  # type: ignore[attr-defined]
    sil.FieldWorks = fieldworks  # type: ignore[attr-defined]
    fieldworks.WordWorks = wordworks  # type: ignore[attr-defined]
    wordworks.Parser = modules["SIL.FieldWorks.WordWorks.Parser"]  # type: ignore[attr-defined]


def _install_subprocess_spy(monkeypatch: pytest.MonkeyPatch, spy: BoundarySpy) -> None:
    """Record (and neutralise) every subprocess the exercise would launch.

    Keeps the run hermetic and fast -- ``discover_hc_tool`` otherwise shells
    out to ``dotnet`` with a 5s timeout -- and makes "CP1 never runs ``hc``"
    a dynamic assertion rather than only a static one.
    """

    class _Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv: Any, *args: Any, **kwargs: Any) -> _Completed:
        spy.subprocess_argv.append([str(a) for a in argv] if isinstance(argv, (list, tuple)) else [str(argv)])
        return _Completed()

    monkeypatch.setattr(subprocess, "run", fake_run)


@pytest.fixture
def boundary_spy(monkeypatch: pytest.MonkeyPatch) -> BoundarySpy:
    spy = BoundarySpy()
    _install_fake_clr(monkeypatch, spy)
    _install_subprocess_spy(monkeypatch, spy)
    return spy


def _exercise_cp1_entry_points(spy: BoundarySpy) -> Dict[str, Any]:
    """Drive every CP1 entry point under the installed spy.

    Returns bookkeeping the tests assert on, so "the exercise ran" is itself
    checkable rather than assumed.
    """
    from pathlib import Path as _Path

    from server import parser_probe
    from server.handlers.diagnostic_health import handle_flextools_health
    from server.scan import grammar_scan_module

    completed: List[str] = []
    failed: Dict[str, str] = {}

    def _try(label: str, fn) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - recorded, see assertions below
            failed[label] = f"{type(exc).__name__}: {exc}"
        else:
            completed.append(label)

    # 1. The detection aggregate the health handler consumes.
    _try("ParserDetector", lambda: parser_probe.ParserDetector())

    # 2. The one function in CP1 that actually touches the CLR. Called
    #    directly because the same-install gate short-circuits before it on
    #    a machine with no FieldWorks -- which would leave the CLR spy with
    #    nothing recorded and the whole dynamic check vacuous.
    _try(
        "_load_parser_core_members",
        lambda: parser_probe._load_parser_core_members(_Path("ParserCore.dll")),
    )

    # 3. The probe seams that shape the health block.
    _try("probe_parser_core_read", lambda: parser_probe.probe_parser_core(
        parser_probe.HCPARSER_MEMBERS))
    _try("probe_parser_core_write", lambda: parser_probe.probe_parser_core(
        parser_probe.WRITE_REQUIRED_MEMBERS))
    _try("discover_hc_tool", lambda: parser_probe.discover_hc_tool())
    _try("discover_generate_hc_config", lambda: parser_probe.discover_generate_hc_config())

    # 4. The tool entry point.
    _try("handle_flextools_health", lambda: asyncio.run(handle_flextools_health({})))
    _try("handle_flextools_health_verbose",
         lambda: asyncio.run(handle_flextools_health({"verbose": True})))

    # 5. Every grammar-scan row, individually and through run_grammar_scan.
    #    Individually as well as together so a row that trips over the
    #    recording stand-in cannot hide the rows after it -- and rows 3/5/8
    #    land in a parallel task, so this must not need editing to cover them.
    project = _Recorder(spy, "project")
    scan_rows = sorted(
        name for name in dir(grammar_scan_module)
        if name.startswith("_scan_") and callable(getattr(grammar_scan_module, name))
    )
    for name in scan_rows:
        _try(name, lambda n=name: getattr(grammar_scan_module, n)(project))
    _try("run_grammar_scan", lambda: grammar_scan_module.run_grammar_scan(project))

    return {"completed": completed, "failed": failed, "scan_rows": scan_rows}


class TestDynamicNoConstructionDuringTheCP1Exercise:
    """(b) -- zero invocations at the construction seam while CP1 runs."""

    def test_no_parser_is_constructed(self, boundary_spy: BoundarySpy):
        _exercise_cp1_entry_points(boundary_spy)
        assert boundary_spy.constructions == [], boundary_spy.summary()

    def test_no_grammar_is_loaded_and_no_word_is_parsed(self, boundary_spy: BoundarySpy):
        _exercise_cp1_entry_points(boundary_spy)
        assert boundary_spy.parses == [], boundary_spy.summary()

    def test_no_parser_binary_is_executed(self, boundary_spy: BoundarySpy):
        _exercise_cp1_entry_points(boundary_spy)
        offenders = [
            argv for argv in boundary_spy.subprocess_argv
            if any(token in FORBIDDEN_SUBPROCESS_ARGV for token in argv)
        ]
        assert offenders == [], offenders

    def test_the_exercise_actually_reached_the_clr_seam(self, boundary_spy: BoundarySpy):
        """Non-vacuity. Zero constructions is only meaningful if the
        reflection that *is* allowed was observed happening."""
        _exercise_cp1_entry_points(boundary_spy)
        assert "Assembly.LoadFile" in boundary_spy.inspections, boundary_spy.inspections
        assert any(
            i.endswith("GetConstructors") for i in boundary_spy.inspections
        ), boundary_spy.inspections

    def test_the_exercise_actually_reached_the_scan_rows(self, boundary_spy: BoundarySpy):
        info = _exercise_cp1_entry_points(boundary_spy)
        assert info["scan_rows"], "no _scan_* rows discovered in grammar_scan_module"
        ran = [name for name in info["completed"] if name.startswith("_scan_")]
        assert ran, f"no scan row completed; failures: {info['failed']}"
        assert boundary_spy.project_reads, "the fake project was never read"

    def test_the_core_entry_points_completed(self, boundary_spy: BoundarySpy):
        info = _exercise_cp1_entry_points(boundary_spy)
        for required in (
            "ParserDetector",
            "_load_parser_core_members",
            "discover_hc_tool",
            "handle_flextools_health",
        ):
            assert required in info["completed"], (
                f"{required} did not complete: {info['failed'].get(required)}"
            )


class TestDynamicNeverInfersParseabilityFromDatabaseState:
    """SPEC 3.1, dynamic half: nothing CP1 touches on a live project is an
    analysis or a wordform collection."""

    def test_no_analysis_or_wordform_path_is_read(self, boundary_spy: BoundarySpy):
        _exercise_cp1_entry_points(boundary_spy)
        assert boundary_spy.analysis_reads == [], boundary_spy.analysis_reads

    def test_the_recorder_would_have_caught_one(self, boundary_spy: BoundarySpy):
        """Falsification of the recorder itself: the same reads CP1 must
        never make, made deliberately, are caught."""
        project = _Recorder(boundary_spy, "project")
        _ = project.Wordforms.GetAll()
        _ = project.Cache.LangProject.WordformInventoryOA.WordformsOC
        assert boundary_spy.analysis_reads, "the SPEC 3.1 recorder is not recording"

    def test_the_recorder_does_not_flag_grammar_reads(self, boundary_spy: BoundarySpy):
        project = _Recorder(boundary_spy, "project")
        _ = project.Phonemes.GetAll()
        _ = project.ObjectsIn("IMoFormRepository")
        assert boundary_spy.project_reads
        assert boundary_spy.analysis_reads == []


class TestSpyIsFalsifiable:
    """The construction spy, fed a planted violation through the same seam
    CP1 code would use. Without these, "zero invocations" is a claim about a
    spy nobody has seen fire."""

    def test_spy_records_a_pythonnet_style_construction(self, boundary_spy: BoundarySpy):
        from SIL.FieldWorks.WordWorks.Parser import HCParser  # type: ignore

        HCParser(object())
        assert boundary_spy.constructions == ["HCParser(...)"]

    def test_spy_records_an_activator_construction(self, boundary_spy: BoundarySpy):
        import System  # type: ignore

        System.Activator.CreateInstance(object())
        assert boundary_spy.constructions == ["Activator.CreateInstance"]

    def test_spy_records_a_reflected_constructor_invoke(self, boundary_spy: BoundarySpy):
        import System  # type: ignore

        assembly = System.Reflection.Assembly.LoadFile("ParserCore.dll")
        for clr_type in assembly.GetTypes():
            if clr_type.Name == "HCParser":
                for ctor in clr_type.GetConstructors(None):
                    ctor.Invoke(None)
        assert boundary_spy.constructions == ["HCParser.Invoke(...)"]

    def test_spy_records_an_lcmcache_construction(self, boundary_spy: BoundarySpy):
        from SIL.LCModel import LcmCache  # type: ignore

        LcmCache("project")
        assert boundary_spy.constructions == ["LcmCache(...)"]

    def test_spy_records_a_parse(self, boundary_spy: BoundarySpy):
        parser = _Recorder(boundary_spy, "parser")
        parser.ParseWord("menulis")
        assert boundary_spy.parses, "a parse went unrecorded"

    def test_spy_records_a_shelled_out_parse(self, boundary_spy: BoundarySpy):
        subprocess.run(["hc", "parse", "words.txt"])
        assert boundary_spy.subprocess_argv == [["hc", "parse", "words.txt"]]

    def test_an_lcm_cast_is_not_a_construction(self, boundary_spy: BoundarySpy):
        from SIL.LCModel import IPhPhoneme  # type: ignore

        IPhPhoneme(object())
        assert boundary_spy.constructions == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
