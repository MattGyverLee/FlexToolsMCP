#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check the code that lives inside TEXT against the bundled flexicon index.

Why this exists
---------------
pyright checks ``src/``. It cannot check a ``python`` fence in CLAUDE.md, a
``code`` string in ``curated_recipes``, or an ``Example:`` docstring block
inside ``index/python/flexicon_api_v*.json`` -- none of those are on an import
graph. Yet those are exactly the surfaces the MCP *teaches from*: a stale name
in CLAUDE.md is re-injected into every script Claude generates.

The failure mode is asymmetric. When flexicon renames something, the ``.py``
files break loudly and get fixed; the prose describing them keeps looking
plausible forever. ``ReversalOperations`` survived in CLAUDE.md and the style
guide for months after the template that imported it was fixed.

Authority
---------
The bundled index (``index/python/flexicon_api_v*.json``, generated from the
installed pyflexicon by AST in ``refresh.py``) is the ground truth for names
and signatures. The installed ``flexicon`` module, when importable, adds the
module-level symbols the class index does not enumerate (``cast_to_concrete``,
``Seg``, ``NC``, ...) and lets submodule imports be verified for real. With no
flexicon installed the check still runs, index-only.

Deliberately NOT the authority: ``inspect.signature`` on a live Operations
class. The descriptor protocol reports ``Create(project, *args, **kwargs)``
for everything, so live introspection can confirm that a name EXISTS but
never that a call passes the right arguments. Existence: live or index.
Arity: index only.

Scope -- this repo's own text
-----------------------------
By default this checks only what THIS repo writes:

  md        repo-root ``*.md``, ``docs/*.md`` (not ``docs/archive/``),
            ``src/flextoolsmcp/templates/*.md``
  template  ``src/flextoolsmcp/templates/*.py``
  recipe    ``CURATED_RECIPES`` code strings
  worked    ``WORKED_EXAMPLES`` code strings and their ``see_also`` names
  pycode    our own ``>>>`` docstring examples, plus API claims in our
            comments and docstring prose

``specs/`` and ``tests/*.md`` are campaign records of what was true at the
time -- rewriting them to match today's API would falsify the record.

The API's OWN docstrings (the ``example`` fields in the index) are NOT
scanned by default: that is upstream text, and flexicon now gates it at
source in ``tests/test_docstring_example_ratchet.py``, where the authority
is the library itself rather than a generated index. Scanning it here too
would be checking the same text twice against a weaker authority. It stays
available for cross-checking and for generating the upstream worklist
(``--upstream`` / ``--worklist``).

Prose is judged narrowly. A bare ``project.<X>`` mention in a comment is not
a claim -- this repo's validators discuss wrong names for a living -- so only
a two-segment ``project.<Accessor>.<Member>`` reference or a flexicon import
counts, metavariables (``X``, ``XOperations``) are skipped, and a line
carrying ``doc-check: ignore`` opts out entirely.

Checks
------
  syntax           the snippet does not parse as Python
  bad-import       ``from flexicon[...] import X`` where X does not exist
  unknown-accessor ``project.<X>`` where X is not an FLExProject member
  unknown-method   ``project.<Acc>.<M>`` where M is on no class in the
                   Operations MRO (base classes resolved transitively)
  arity            call passes too few / too many arguments for the signature
  refusing-method  the method exists but always raises NotImplementedError
                   (e.g. PhonRules.SetLeftContext after issue #142) -- a name
                   that resolves but can never run is worse than a typo,
                   because no existence check catches it

Escape hatches (markdown)
-------------------------
Fence info-string metadata, e.g.::

    ```python doc-check=ignore
    ```python flavor=liblcm

``ignore`` skips the block entirely -- for prose that illustrates internals
or pseudo-code rather than API the reader should copy. ``flavor`` overrides
the auto-detected API surface. Flavor is otherwise inferred from the
snippet's own imports, because ``project.LexAllEntries`` is correct in a
flexlibs-stable snippet and wrong in a flexicon one.

Blocking vs reporting
---------------------
Everything this repo owns is BLOCKING: we can fix it. Upstream docstring
examples are only scanned when asked for, and are reported rather than
blocking even then -- they are fixed at MattGyverLee/flexicon and arrive
here at the next ``refresh``. ``--strict`` makes them blocking too.

Usage:
    python scripts/check_doc_snippets.py            # gate this repo's text
    python scripts/check_doc_snippets.py --upstream # + cross-check upstream
    python scripts/check_doc_snippets.py --json     # machine-readable

Exit codes:
    0 = no findings on blocking surfaces
    1 = findings on blocking surfaces
    2 = the check itself could not run (no index, unreadable index)
"""

import argparse
import ast
import glob
import json
import os
import re
import sys
import textwrap
from collections import Counter, defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

BLOCKING_SURFACES = ("md", "template", "recipe", "worked", "pycode")
UPSTREAM_SURFACES = ("docstring",)

# Python we own and therefore check: our own docstrings and comments quote
# flexicon API constantly. templates/ is excluded because it is already its
# own surface, and tests/ because its fixtures are deliberately-wrong code.
PYCODE_GLOBS = ("src/flextoolsmcp/**/*.py", "scripts/*.py")
PYCODE_EXCLUDE = ("templates", "__pycache__")

# In prose we only judge a two-segment claim (`project.Senses.GetGloss`) or a
# flexicon import. A bare `project.<X>` mention is not a claim: this repo's
# own validators discuss wrong names for a living (`project.LexSense` is the
# alias they exist to reject), and flagging those would bury real findings in
# intentional counter-examples.
PROSE_MEMBER_RE = re.compile(r"\bproject\.([A-Za-z_]\w*)\.([A-Za-z_]\w*)")
PROSE_IMPORT_RE = re.compile(r"\bfrom\s+flexicon\s+import\s+([A-Za-z_]\w*)")
PROSE_OPT_OUT = "doc-check: ignore"

# Metavariables, not names. A repo whose job is explaining API-shape rules
# writes `from flexicon import XOperations` constantly, meaning "any
# Operations class". Reporting those as bad imports is noise, and asking
# every such line to carry an opt-out marker would be worse.
METAVARIABLES = frozenset({
    "X", "Y", "Z", "N", "XOperations", "YOperations", "ZOperations",
    "SomeOperations", "MyOperations",
})


class DegradedCheck(Exception):
    """The check cannot see its full ground truth, so its verdict is void.

    Raised instead of reporting findings from a narrowed index: a false
    failure trains people to bypass the gate, which costs more than the gate
    ever earns.
    """

FENCE_RE = re.compile(r"^([ \t]*)```(?:python|py)([^\n]*)\n(.*?)^[ \t]*```", re.S | re.M)


# ---------------------------------------------------------------------------
# Index: the authority
# ---------------------------------------------------------------------------

class Api:
    """The flexicon API surface, as the index (plus live module) describes it."""

    def __init__(self, index_path):
        self.index_path = index_path
        with open(index_path, encoding="utf-8") as fh:
            data = json.load(fh)
        self.entities = data.get("entities") or {}
        flex_project = self.entities.get("FLExProject") or {}

        try:
            from flextoolsmcp.server.constants import (
                KNOWN_OPERATIONS, PROJECT_ACCESSOR_ALIASES,
            )
        except Exception as exc:
            # Never degrade quietly. Without KNOWN_OPERATIONS the accessor
            # universe silently shrinks to the index's under-enumerated
            # property list, and the check starts reporting real accessors
            # (project.Text, project.Example, ...) as typos -- a checker that
            # narrows its own ground truth and then fails the build is worse
            # than no checker.
            raise DegradedCheck(
                "cannot import flextoolsmcp.server.constants (%s) -- run this "
                "with the project environment, not an isolated interpreter" % exc
            )
        self.accessor_aliases = dict(PROJECT_ACCESSOR_ALIASES)

        props = {p["name"] for p in flex_project.get("properties", []) if p.get("name")}
        methods = {m["name"] for m in flex_project.get("methods", []) if m.get("name")}
        # The index's FLExProject property list under-enumerates the real
        # accessors (see scripts/check_project_accessors.py for the full
        # story), so union it with the Operations-shorthand names, minus the
        # two shorthands FLExProject genuinely does not expose.
        shorthand = {
            op[: -len("Operations")]
            for op in KNOWN_OPERATIONS
            if op.endswith("Operations")
        } - set(self.accessor_aliases)
        self.accessors = props | methods | shorthand

        self.accessor_ops = {}
        for p in flex_project.get("properties", []):
            rt = (p.get("return_type") or "").strip()
            if rt.endswith("Operations") and rt in self.entities:
                self.accessor_ops[p["name"]] = rt
        for name in shorthand:
            self.accessor_ops.setdefault(name, name + "Operations")
        for alias, real in self.accessor_aliases.items():
            self.accessor_ops.setdefault(real, alias + "Operations")

        self._own = {}
        for name, entity in self.entities.items():
            members = {}
            for m in entity.get("methods", []):
                members[m["name"]] = {
                    "arity": _signature_arity(m.get("signature")),
                    "refuses": _always_raises_notimplemented(m),
                }
            for p in entity.get("properties", []):
                members.setdefault(p["name"], {"arity": (0, 0), "refuses": False})
            self._own[name] = members
        self._mro_cache = {}

        self.symbols = set(self.entities)
        self.live = None
        try:
            import flexicon as live
            self.live = live
            self.symbols |= {n for n in dir(live) if not n.startswith("_")}
        except Exception:
            pass

        # Deprecated singular/plural accessor aliases, installed onto
        # FLExProject at import time and therefore absent from the index's
        # property list. They are real accessors: `project.Sense.GetGloss(s)`
        # runs (with a DeprecationWarning). Judging them as typos would be
        # wrong in the same direction as the pre-commit degradation.
        self.aliases = {}
        if self.live is not None:
            try:
                from flexicon.code._op_aliases import OP_NAMESPACE_ALIASES
                self.aliases = dict(OP_NAMESPACE_ALIASES)
            except Exception:
                self.aliases = {}
        self.accessors |= set(self.aliases)

    def resolve_accessor(self, name):
        """The Operations class behind an accessor, following aliases."""
        return self.accessor_ops.get(self.aliases.get(name, name))

    def members(self, ops_class):
        """Members of an Operations class, base classes resolved transitively.

        Skipping inheritance is not a small inaccuracy: every Move*/Sort/Swap
        call in the corpus comes from BaseOperations and would be reported as
        a phantom failure.
        """
        if ops_class in self._mro_cache:
            return self._mro_cache[ops_class]
        seen, out, stack = set(), {}, [ops_class]
        while stack:
            cls = stack.pop()
            if cls in seen or cls not in self.entities:
                continue
            seen.add(cls)
            for name, info in self._own.get(cls, {}).items():
                out.setdefault(name, info)
            stack.extend(self.entities[cls].get("base_classes") or [])
        self._mro_cache[ops_class] = out
        return out

    def module_symbol_exists(self, module, symbol):
        """Is `symbol` importable from `module`? None when undecidable."""
        if module == "flexicon":
            if self.live is not None:
                return symbol in self.symbols
            # Index-only: it enumerates classes, not module-level helpers
            # (cast_to_concrete, Seg, NC), so judge only names that follow the
            # Operations-class convention -- enough to catch the
            # ReversalOperations class of rot without inventing verdicts about
            # helpers the index was never going to list.
            if symbol.endswith("Operations") or symbol == "FLExProject":
                return symbol in self.symbols
            return None
        if self.live is None:
            return None  # no install to ask; do not guess about submodules
        try:
            mod = __import__(module, fromlist=["__name__"])
        except Exception:
            return False
        return hasattr(mod, symbol)


def _signature_arity(signature):
    """(min, max) positional arity from an index signature string, self excluded."""
    match = re.match(r"^[\w.]+\((.*)\)\s*$", (signature or "").replace("\n", " "), re.S)
    if not match:
        return (0, 99)
    inner = match.group(1).strip()
    if not inner:
        return (0, 0)
    depth, parts, current = 0, [], ""
    for char in inner:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    low = high = 0
    for raw in parts:
        param = raw.strip()
        if not param or param in ("self", "cls"):
            continue
        if param.startswith("*"):
            high = 99  # *args / **kwargs: no upper bound
            continue
        high += 1
        if "=" not in param:
            low += 1
    return (low, max(high, low))


def _always_raises_notimplemented(method):
    """True for a method the library keeps only to refuse loudly."""
    failures = (method.get("output_behavior") or {}).get("failure") or []
    for failure in failures:
        if (failure.get("exception") == "NotImplementedError"
                and str(failure.get("when", "")).strip().lower().startswith("always")):
            return True
    return False


# ---------------------------------------------------------------------------
# Snippet collection
# ---------------------------------------------------------------------------

class Snippet:
    def __init__(self, surface, where, code, flavor=None, ignored=False):
        self.surface = surface
        self.where = where
        self.code = code
        self.flavor = flavor
        self.ignored = ignored


def _guidance_markdown():
    """Markdown the MCP teaches from -- not the historical record."""
    paths = sorted(glob.glob(os.path.join(REPO_ROOT, "*.md")))
    paths += sorted(p for p in glob.glob(os.path.join(REPO_ROOT, "docs", "*.md")))
    paths += sorted(glob.glob(os.path.join(REPO_ROOT, "src", "flextoolsmcp", "templates", "*.md")))
    return paths


def _parse_fence_meta(info_string):
    meta = {}
    for token in (info_string or "").split():
        if "=" in token:
            key, _, value = token.partition("=")
            meta[key.strip().lower()] = value.strip()
    return meta


def markdown_snippets():
    out = []
    for path in _guidance_markdown():
        rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        for match in FENCE_RE.finditer(text):
            indent, info, body = match.group(1), match.group(2), match.group(3)
            meta = _parse_fence_meta(info)
            line = text[: match.start()].count("\n") + 1
            if indent:
                body = textwrap.dedent(body)
            out.append(Snippet(
                "md", "%s:%d" % (rel, line), body,
                flavor=meta.get("flavor"),
                ignored=meta.get("doc-check") == "ignore",
            ))
    return out


def template_snippets():
    out = []
    pattern = os.path.join(REPO_ROOT, "src", "flextoolsmcp", "templates", "*.py")
    for path in sorted(glob.glob(pattern)):
        rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
        with open(path, encoding="utf-8") as fh:
            out.append(Snippet("template", rel, fh.read()))
    return out


def served_code_snippets():
    """Code strings the server hands back verbatim: recipes and worked examples."""
    out = []
    try:
        from flextoolsmcp.curated_recipes import CURATED_RECIPES
        from flextoolsmcp.server.worked_examples import WORKED_EXAMPLES
    except Exception as exc:
        # A surface that vanishes reports zero findings, which reads exactly
        # like a clean one. Refuse rather than certify what was never checked.
        raise DegradedCheck(
            "cannot import the served code surfaces (%s) -- run this with the "
            "project environment, not an isolated interpreter" % exc
        )
    for recipe_id, recipe in CURATED_RECIPES.items():
        out.append(Snippet("recipe", recipe_id, recipe.get("code", "")))
    for example in WORKED_EXAMPLES:
        out.append(Snippet("worked", example.get("id", "?"), example.get("code", "")))
    return out


def _pycode_files():
    for pattern in PYCODE_GLOBS:
        for path in sorted(glob.glob(os.path.join(REPO_ROOT, pattern), recursive=True)):
            rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
            if any(part in PYCODE_EXCLUDE for part in rel.split("/")):
                continue
            yield path, rel


def pycode_snippets():
    """`>>>` examples in this repo's own docstrings.

    We quote flexicon API in our own docstrings as much as in the markdown,
    and a doctest block there is a full claim -- so it gets the full AST
    check, same as a fence.
    """
    out = []
    for path, rel in _pycode_files():
        try:
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                     ast.AsyncFunctionDef)):
                continue
            doc = ast.get_docstring(node) or ""
            if ">>>" not in doc:
                continue
            line = getattr(node, "lineno", 1)
            out.append(Snippet("pycode", "%s:%d" % (rel, line), _doctest_to_code(doc)))
    return out


def prose_findings(api):
    """API claims in this repo's comments and docstring prose.

    Narrow on purpose. A bare `project.<X>` mention is not a claim -- our
    validators discuss wrong accessor names for a living -- so only a
    two-segment `project.<Accessor>.<Member>` reference or a flexicon import
    is judged. A line carrying `doc-check: ignore` opts out, which is what an
    intentional counter-example should use.
    """
    findings = []
    for path, rel in _pycode_files():
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if PROSE_OPT_OUT in line:
                continue
            for match in PROSE_MEMBER_RE.finditer(line):
                accessor, member = match.group(1), match.group(2)
                ops_class = api.resolve_accessor(accessor)
                if ops_class is None or ops_class not in api.entities:
                    continue  # unknown accessor in prose: not a claim we judge
                members = api.members(ops_class)
                if not members or member in members:
                    continue
                findings.append({
                    "surface": "pycode", "where": rel, "line": lineno,
                    "kind": "unknown-method",
                    "detail": "project.%s.%s does not exist on %s"
                              % (accessor, member, ops_class),
                })
            for match in PROSE_IMPORT_RE.finditer(line):
                symbol = match.group(1)
                if symbol in METAVARIABLES:
                    continue
                if api.module_symbol_exists("flexicon", symbol) is False:
                    findings.append({
                        "surface": "pycode", "where": rel, "line": lineno,
                        "kind": "bad-import",
                        "detail": "from flexicon import %s" % symbol,
                    })
    return findings


def cross_reference_findings(api):
    """`see_also` entries name API members in prose form ("Class.Method").

    They are served next to the code and rot exactly like it -- the
    phonological-rule example pointed at AddInputSegment/SetLeftContext long
    after both were gone -- but no AST walk sees them, so check them here.
    """
    findings = []
    try:
        from flextoolsmcp.server.worked_examples import WORKED_EXAMPLES
    except Exception:
        return findings
    for example in WORKED_EXAMPLES:
        for ref in example.get("see_also", []) or []:
            if "." not in ref:
                continue
            cls, _, member = ref.rpartition(".")
            if cls not in api.entities:
                continue
            members = api.members(cls)
            if member not in members:
                findings.append({
                    "surface": "worked", "where": example.get("id", "?"), "line": 0,
                    "kind": "unknown-method",
                    "detail": "see_also '%s' does not exist on %s" % (ref, cls),
                })
            elif members[member]["refuses"]:
                findings.append({
                    "surface": "worked", "where": example.get("id", "?"), "line": 0,
                    "kind": "refusing-method",
                    "detail": "see_also '%s' always raises NotImplementedError" % ref,
                })
    return findings


def _doctest_to_code(block):
    lines = []
    for raw in textwrap.dedent(block).splitlines():
        stripped = raw.strip()
        if stripped.startswith(">>> "):
            lines.append(stripped[4:])
        elif stripped == ">>>":
            lines.append("")
        elif stripped.startswith("... "):
            lines.append(stripped[4:])
        # bare lines are expected output, not code
    return "\n".join(lines)


def docstring_snippets(api):
    out = []
    for name, entity in api.entities.items():
        if entity.get("example"):
            out.append(Snippet("docstring", name, _doctest_to_code(entity["example"])))
        for member in list(entity.get("methods", [])) + list(entity.get("properties", [])):
            if member.get("example"):
                out.append(Snippet(
                    "docstring", "%s.%s" % (name, member.get("name", "?")),
                    _doctest_to_code(member["example"]),
                ))
    return out


# ---------------------------------------------------------------------------
# Checking
# ---------------------------------------------------------------------------

def detect_flavor(code, tree):
    """Which API surface does this snippet target? Decided by its own imports."""
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
        elif isinstance(node, ast.Import):
            modules += [alias.name for alias in node.names]
    roots = {m.split(".")[0] for m in modules if m}
    if "SIL" in roots or "clr" in roots or "ServiceLocator" in code:
        return "liblcm"
    if "flexlibs" in roots and "flexicon" not in roots:
        return "flexlibs_stable"
    return "flexicon"


def _elided(call):
    """True when the call is written with `...` -- illustrative, not a real call."""
    return any(isinstance(a, ast.Constant) and a.value is Ellipsis for a in call.args)


def check_snippet(snippet, api):
    """Return findings for one snippet. Findings are dicts, JSON-ready."""
    findings = []

    def add(kind, line, detail):
        findings.append({
            "surface": snippet.surface,
            "where": snippet.where,
            "line": line,
            "kind": kind,
            "detail": detail,
        })

    if snippet.ignored:
        return findings

    code = textwrap.dedent(snippet.code)
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        add("syntax", exc.lineno or 0, str(exc.msg))
        return findings

    flavor = snippet.flavor or detect_flavor(code, tree)

    call_args = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            call_args[node.func] = (len(node.args) + len(node.keywords), _elided(node))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] == "flexicon":
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    exists = api.module_symbol_exists(module, alias.name)
                    if exists is False:
                        add("bad-import", node.lineno,
                            "from %s import %s" % (module, alias.name))
            continue

        if flavor != "flexicon" or not isinstance(node, ast.Attribute):
            continue

        # project.<X>
        if isinstance(node.value, ast.Name) and node.value.id == "project":
            attr = node.attr
            if attr.startswith("_"):
                continue  # documented internals, not an API claim
            if attr not in api.accessors:
                add("unknown-accessor", node.lineno, "project.%s" % attr)
            continue

        # project.<Accessor>.<Member>
        if (isinstance(node.value, ast.Attribute)
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "project"):
            accessor, member = node.value.attr, node.attr
            ops_class = api.resolve_accessor(accessor)
            if ops_class is None or ops_class not in api.entities:
                continue
            members = api.members(ops_class)
            if not members:
                continue
            if member not in members:
                add("unknown-method", node.lineno,
                    "project.%s.%s does not exist on %s" % (accessor, member, ops_class))
                continue
            info = members[member]
            if info["refuses"]:
                add("refusing-method", node.lineno,
                    "project.%s.%s always raises NotImplementedError" % (accessor, member))
                continue
            if node in call_args:
                nargs, elided = call_args[node]
                low, high = info["arity"]
                if not elided and (nargs < low or nargs > high):
                    add("arity", node.lineno,
                        "project.%s.%s called with %d arg(s); signature takes %d..%d"
                        % (accessor, member, nargs, low, high))
    return findings


def collect_snippets(api, include_upstream=False):
    snippets = (markdown_snippets() + template_snippets()
                + served_code_snippets() + pycode_snippets())
    if include_upstream:
        snippets += docstring_snippets(api)
    return snippets


def run(include_upstream=False):
    api = Api(find_index())
    snippets = collect_snippets(api, include_upstream=include_upstream)
    findings = []
    for snippet in snippets:
        findings.extend(check_snippet(snippet, api))
    findings.extend(prose_findings(api))
    findings.extend(cross_reference_findings(api))
    return api, snippets, findings


def find_index():
    pattern = os.path.join(REPO_ROOT, "src", "flextoolsmcp", "index", "python",
                           "flexicon_api_v*.json")
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise SystemExit(
            "[ERROR] no flexicon index found at %s -- run "
            "'python -m flextoolsmcp.refresh' first" % pattern
        )
    return matches[-1]


# ---------------------------------------------------------------------------
# Reporting (ASCII only -- Windows console safe)
# ---------------------------------------------------------------------------

def _ascii(text):
    return str(text).encode("ascii", "replace").decode("ascii")


def report(api, snippets, findings, show_upstream, as_json):
    blocking = [f for f in findings if f["surface"] in BLOCKING_SURFACES]
    upstream = [f for f in findings if f["surface"] in UPSTREAM_SURFACES]

    if as_json:
        print(json.dumps({
            "index": os.path.basename(api.index_path),
            "snippets_scanned": len(snippets),
            "blocking": blocking,
            "upstream": upstream,
        }, indent=2))
        return 1 if blocking else 0

    counts = Counter(s.surface for s in snippets)
    print("=" * 72)
    print("Doc-snippet check -- index: %s" % os.path.basename(api.index_path))
    print("  scanned: " + ", ".join("%s=%d" % (k, counts[k]) for k in sorted(counts)))
    if api.live is None:
        print("  [NOTE] flexicon not importable: index-only mode "
              "(submodule imports unverified)")
    print("")

    _print_group("BLOCKING (repo-owned surfaces)", blocking)
    if show_upstream:
        _print_group("UPSTREAM (pyflexicon docstrings -- report, do not edit here)",
                     upstream)
    elif upstream:
        print("[NOTE] %d finding(s) in upstream pyflexicon docstring examples "
              "(--upstream to list)" % len(upstream))
        print("")

    if blocking:
        print("[FAIL] %d finding(s) on blocking surfaces" % len(blocking))
        return 1
    print("[OK] no findings on blocking surfaces")
    return 0


def _print_group(title, findings):
    print("-" * 72)
    print("%s: %d finding(s)" % (title, len(findings)))
    if not findings:
        print("")
        return
    by_kind = defaultdict(list)
    for finding in findings:
        by_kind[finding["kind"]].append(finding)
    for kind in sorted(by_kind):
        print("  [%s] %d" % (kind, len(by_kind[kind])))
        for finding in by_kind[kind]:
            print("    %s:%s  %s" % (finding["where"], finding["line"],
                                     _ascii(finding["detail"])))
    print("")


def _flexicon_source_root():
    """Directory holding flexicon's `code/` tree, or None."""
    try:
        import flexicon
    except Exception:
        return None
    module_file = getattr(flexicon, "__file__", None)
    if not module_file:
        return None
    return os.path.dirname(os.path.abspath(module_file))


def _def_lines(source_path):
    """{('Class', 'member'): lineno, ('Class', None): lineno} from one module."""
    try:
        with open(source_path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except Exception:
        return {}
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        out[(node.name, None)] = node.lineno
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[(node.name, item.name)] = item.lineno
    return out


def _nearest(name, candidates):
    import difflib
    matches = difflib.get_close_matches(name, [c for c in candidates if c != name], n=2, cutoff=0.7)
    return matches


def write_worklist(api, findings, path):
    """Emit the upstream findings as a per-file, per-symbol worklist.

    The gate reports findings against index entities ("AgentOperations.
    FindByType"); anyone fixing them needs a flexicon source path and a line.
    Resolve those here so the list can be worked without re-deriving it.
    """
    upstream = [f for f in findings if f["surface"] in UPSTREAM_SURFACES]
    root = _flexicon_source_root()

    source_of = {}
    for name, entity in api.entities.items():
        rel = (entity.get("source_file") or "").strip()
        if rel:
            source_of[name] = "flexicon/code/%s.py" % rel.replace("\\", "/")

    def_line_cache = {}

    def def_line(entity_name, member):
        rel = source_of.get(entity_name)
        if not rel or root is None:
            return None
        abs_path = os.path.join(os.path.dirname(root), rel.replace("/", os.sep))
        if abs_path not in def_line_cache:
            def_line_cache[abs_path] = _def_lines(abs_path)
        lines = def_line_cache[abs_path]
        return lines.get((entity_name, member)) or lines.get((entity_name, None))

    internal_receivers = {"project.lp", "project.project", "project.lexDB"}
    rows = []
    for finding in upstream:
        entity, _, member = finding["where"].partition(".")
        kind = finding["kind"]
        detail = finding["detail"]
        if kind == "unknown-accessor" and detail in internal_receivers:
            kind = "internal-leak"
        suggestion = ""
        if kind == "unknown-accessor":
            near = _nearest(detail.split(".", 1)[1], api.accessors)
            if near:
                suggestion = "nearest real accessor: " + ", ".join(
                    "project.%s" % n for n in near)
        elif kind == "internal-leak":
            suggestion = ("example is written from inside the class; rewrite it "
                          "against the public FLExProject surface")
        elif kind == "unknown-method":
            ops = api.resolve_accessor(detail.split(".")[1]) if detail.count(".") > 1 else None
            if ops:
                bad = detail.split(".")[2].split(" ")[0]
                near = _nearest(bad, api.members(ops))
                if near:
                    suggestion = "nearest real member: " + ", ".join(near)
        rows.append({
            "kind": kind,
            "entity": entity,
            "member": member or None,
            "detail": detail,
            "file": source_of.get(entity, "?"),
            "def_line": def_line(entity, member or None),
            "example_line": finding["line"],
            "suggestion": suggestion,
        })

    by_file = defaultdict(list)
    for row in rows:
        by_file[row["file"]].append(row)

    kind_counts = Counter(r["kind"] for r in rows)
    lines = []
    lines.append("# Upstream flexicon docstring findings")
    lines.append("")
    lines.append("Generated by `python scripts/check_doc_snippets.py --worklist <path>`")
    lines.append("against `%s`. Regenerate rather than hand-edit."
                 % os.path.basename(api.index_path))
    lines.append("")
    lines.append("These are `Example:` blocks in **pyflexicon's own docstrings**, which")
    lines.append("this MCP indexes and serves verbatim. Fix them in the flexicon repo")
    lines.append("(MattGyverLee/flexicon); they reach FlexToolsMCP at the next")
    lines.append("`python -m flextoolsmcp.refresh`. Nothing here is fixable in this repo.")
    lines.append("")
    lines.append("Paths are relative to the flexicon repo root. `def L<n>` is the line of")
    lines.append("the enclosing `def`/`class`; the offending expression is quoted so the")
    lines.append("exact line inside the docstring can be found by search.")
    lines.append("")
    lines.append("| kind | count | what it means |")
    lines.append("|---|---|---|")
    lines.append("| unknown-accessor | %d | `project.<X>` naming an accessor FLExProject "
                 "does not have |" % kind_counts.get("unknown-accessor", 0))
    lines.append("| internal-leak | %d | example uses `project.lp` / `.project` / `.lexDB` "
                 "-- internals, not the public surface |" % kind_counts.get("internal-leak", 0))
    lines.append("| unknown-method | %d | method absent from the Operations class and every "
                 "base |" % kind_counts.get("unknown-method", 0))
    lines.append("| arity | %d | call passes the wrong number of arguments |"
                 % kind_counts.get("arity", 0))
    lines.append("| refusing-method | %d | member exists but always raises "
                 "NotImplementedError |" % kind_counts.get("refusing-method", 0))
    lines.append("| syntax | %d | the example is not valid Python |"
                 % kind_counts.get("syntax", 0))
    lines.append("")
    lines.append("Total: **%d** findings across **%d** example blocks in **%d** files."
                 % (len(rows), len({(r["entity"], r["member"]) for r in rows}), len(by_file)))
    lines.append("")

    for path_key in sorted(by_file):
        lines.append("## %s" % path_key)
        lines.append("")
        for row in sorted(by_file[path_key],
                          key=lambda r: (r["def_line"] or 0, r["kind"], r["detail"])):
            symbol = "%s.%s" % (row["entity"], row["member"]) if row["member"] else row["entity"]
            location = "def L%s" % row["def_line"] if row["def_line"] else "line unresolved"
            suffix = " -- %s" % row["suggestion"] if row["suggestion"] else ""
            lines.append("- [ ] **%s** `%s` (%s, example line %s): `%s`%s"
                         % (row["kind"], symbol, location, row["example_line"],
                            _ascii(row["detail"]), suffix))
        lines.append("")

    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))

    json_path = os.path.splitext(path)[0] + ".json"
    with open(json_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({
            "index": os.path.basename(api.index_path),
            "counts": dict(kind_counts),
            "findings": rows,
        }, fh, indent=2)
    return path, json_path, len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(__doc__ or "Check code embedded in text.").splitlines()[0]
    )
    parser.add_argument("--upstream", action="store_true",
                        help="also list findings in upstream pyflexicon docstrings")
    parser.add_argument("--strict", action="store_true",
                        help="treat upstream docstring findings as failures too")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="machine-readable output")
    parser.add_argument("--worklist", metavar="PATH",
                        help="write the upstream findings to PATH as a per-file "
                             "worklist (plus a .json sibling) and exit")
    args = parser.parse_args(argv)

    want_upstream = bool(args.upstream or args.strict or args.worklist)
    try:
        api, snippets, findings = run(include_upstream=want_upstream)
    except SystemExit:
        raise
    except DegradedCheck as exc:
        print("[ERROR] check refused to run degraded: %s" % _ascii(exc))
        return 2
    except Exception as exc:  # pragma: no cover - defensive
        print("[ERROR] check could not run: %s" % _ascii(exc))
        return 2

    if args.worklist:
        md_path, json_path, count = write_worklist(api, findings, args.worklist)
        print("[OK] wrote %d upstream finding(s)" % count)
        print("     %s" % md_path)
        print("     %s" % json_path)
        return 0

    status = report(api, snippets, findings,
                    show_upstream=args.upstream or args.strict,
                    as_json=args.as_json)
    if args.strict and any(f["surface"] in UPSTREAM_SURFACES for f in findings):
        return 1
    return status


if __name__ == "__main__":
    sys.exit(main())
