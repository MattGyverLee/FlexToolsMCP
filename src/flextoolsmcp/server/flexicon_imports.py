#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Static check of ``flexicon`` import names (issue #305).

Weak models invent import names -- importing ``WfiWordformOperations`` or
``InflectionFeatures`` from flexicon, or the module path
``flexicon.Lexicon`` -- and only learn at runtime, from a bare
ImportError with no suggestion. This module answers "does flexicon export
that?" WITHOUT importing flexicon: ``import flexicon`` initialises
FieldWorks globals and raises a bare Exception on a host with no FieldWorks
(see execution._probe_undoable_capability), so the server never imports it.

The public surface is read statically:

* ``importlib.util.find_spec("flexicon")`` locates the installed package
  without executing it (top-level specs never run the package);
* the package ``__init__.py`` is parsed with ``ast``: every module-level
  bound name (imports, assignments, defs, classes, also inside top-level
  ``if``/``try``) plus ``__all__``;
* the package directory gives the importable submodule paths
  (``flexicon.code.Lexicon.LexEntryOperations`` ...).

When flexicon's source cannot be found, the names in the API index
(``import_statement`` lines and ``top_level_importable`` entities) are the
fallback surface: only Operations-shaped names are judged against it (the
index does not list module-level helpers), and submodule paths are not
checked. With neither, the
check is skipped (fail open): this gate must never reject valid code
because the server could not see the library.

A module that defines ``__getattr__`` or star-imports something we cannot
resolve is treated as open (any name passes).

No sibling imports: ``validators`` passes in the API index and the
accessor map.
"""

from __future__ import annotations

import ast
import difflib
import importlib.util
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

ROOTS = ("flexicon", "flexlibs2")  # flexlibs2 is flexicon's deprecated alias

_IMPORT_STMT_RE = re.compile(r"^\s*from\s+flexicon\s+import\s+(.+)$")


class _Surface:
    """What flexicon exports: root names, module paths, per-module names."""

    def __init__(self) -> None:
        self.root_names: Set[str] = set()
        self.root_open = False             # __getattr__ / unresolved star import
        self.modules: Dict[str, str] = {}  # "flexicon.code.X" -> file path
        self.source_found = False
        self._module_names: Dict[str, Tuple[Set[str], bool]] = {}

    def module_names(self, dotted: str) -> Tuple[Set[str], bool]:
        """(names bound in module ``dotted``, is_open). Cached."""
        if dotted not in self._module_names:
            path = self.modules.get(dotted)
            if path is None:
                self._module_names[dotted] = (set(), True)
            else:
                names, is_open = _bound_names(path)
                prefix = dotted + "."
                names |= {m[len(prefix):].split(".", 1)[0]
                          for m in self.modules if m.startswith(prefix)}
                self._module_names[dotted] = (names, is_open)
        return self._module_names[dotted]


_SURFACE_CACHE: Dict[str, _Surface] = {}


def _bound_names(path: str) -> Tuple[Set[str], bool]:
    """Module-level names bound in the file at ``path``; True when open-ended."""
    try:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError, ValueError):
        return set(), True
    names: Set[str] = set()
    is_open = False
    stack: List[ast.stmt] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.If, ast.Try)) or type(node).__name__ == "TryStar":
            for field in ("body", "orelse", "finalbody"):
                stack.extend(getattr(node, field, []) or [])
            for handler in getattr(node, "handlers", []) or []:
                stack.extend(handler.body)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            if node.name == "__getattr__":
                is_open = True
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    is_open = True  # star re-export: do not guess its contents
                else:
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name):
                        names.add(sub.id)
            if (isinstance(node, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
                    and isinstance(node.value, (ast.List, ast.Tuple))):
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        names.add(elt.value)
    return names, is_open


def _scan_package(pkg_dir: str, root: str) -> Dict[str, str]:
    """Dotted module path -> file, for every module under ``pkg_dir``."""
    modules: Dict[str, str] = {root: os.path.join(pkg_dir, "__init__.py")}
    for dirpath, dirnames, filenames in os.walk(pkg_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith((".", "__pycache__"))
                       and d not in ("tests", "docs", "examples")]
        rel = os.path.relpath(dirpath, pkg_dir)
        parts = [] if rel == "." else rel.split(os.sep)
        if parts and not os.path.exists(os.path.join(dirpath, "__init__.py")):
            # Namespace dirs import too, but flexicon has none; skip their
            # children's .py files only if the dir itself is not a package.
            continue
        if parts:
            modules[".".join([root] + parts)] = os.path.join(dirpath, "__init__.py")
        for fn in filenames:
            if fn.endswith(".py") and fn != "__init__.py":
                modules[".".join([root] + parts + [fn[:-3]])] = os.path.join(dirpath, fn)
    return modules


def _index_names(api_index: Any) -> Set[str]:
    """Top-level importable names the API index knows about."""
    names: Set[str] = set()
    flexicon = getattr(api_index, "flexicon", None) or {}
    for name, entity in (flexicon.get("entities") or {}).items():
        if not isinstance(entity, dict):
            continue
        stmt = entity.get("import_statement") or ""
        m = _IMPORT_STMT_RE.match(stmt)
        if m:
            for part in m.group(1).split(","):
                part = part.strip().split(" as ")[0].strip("() ")
                if part:
                    names.add(part)
        if entity.get("top_level_importable"):
            names.add(name)
    return names


def load_surface(api_index: Any = None) -> Optional[_Surface]:
    """The flexicon export surface, or None when nothing is known (fail open)."""
    try:
        spec = importlib.util.find_spec("flexicon")
    except (ImportError, ValueError):
        spec = None
    origin = getattr(spec, "origin", None) if spec else None
    key = origin or ""
    if key and key in _SURFACE_CACHE:
        return _SURFACE_CACHE[key]
    surface = _Surface()
    if origin and os.path.isfile(origin):
        pkg_dir = os.path.dirname(origin)
        surface.modules = _scan_package(pkg_dir, "flexicon")
        names, is_open = _bound_names(origin)
        surface.root_names = names | {
            m.split(".", 2)[1] for m in surface.modules if m.count(".") >= 1
        }
        surface.root_open = is_open
        surface.source_found = True
        _SURFACE_CACHE[key] = surface
        return surface
    names = _index_names(api_index)
    if not names:
        return None
    surface.root_names = names
    return surface


def _canonical(module: str) -> str:
    """flexlibs2[.x] -> flexicon[.x]."""
    for root in ROOTS:
        if module == root or module.startswith(root + "."):
            return "flexicon" + module[len(root):]
    return module


def _stem(name: str) -> str:
    return (name[: -len("Operations")] if name.endswith("Operations") else name).lower()


def _close_names(name: str, candidates: List[str], limit: int = 3) -> List[str]:
    """Candidates close to ``name``, compared WITHOUT the Operations suffix.

    Comparing full names lets the shared ``Operations`` suffix inflate every
    score (``BogusOperations`` ~ ``NoteOperations``); the stem is what the
    model got wrong. A plural stem is also tried singular (InflectionFeatures
    -> InflectionFeature), and a stem that ends with a candidate's stem
    (WfiWordform -> Wordform) counts as close.
    """
    stems = {_stem(name)}
    if _stem(name).endswith("s"):
        stems.add(_stem(name)[:-1])
    scored: List[Tuple[float, str]] = []
    for cand in candidates:
        cstem = _stem(cand)
        if len(cstem) < 3:
            continue
        best = 0.0
        for stem in stems:
            ratio = difflib.SequenceMatcher(None, stem, cstem).ratio()
            if len(cstem) >= 5 and (stem.endswith(cstem) or cstem.endswith(stem)):
                ratio = max(ratio, 0.8)
            best = max(best, ratio)
        if best >= 0.75:
            scored.append((best, cand))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [c for _, c in scored[:limit]]


def suggest_name(
    name: str,
    surface: _Surface,
    accessor_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """did_you_mean + a one-line fix for a name flexicon does not export."""
    accessor_map = accessor_map or {}
    ops_to_accessor = {v: k for k, v in accessor_map.items()}
    candidates = sorted(n for n in surface.root_names if not n.startswith("_"))
    did_you_mean = _close_names(name, candidates)
    did_you_mean = did_you_mean[:3]
    accessor = name if name in accessor_map else None
    if accessor is None and did_you_mean:
        accessor = ops_to_accessor.get(did_you_mean[0])
    parts = [f"flexicon does not export {name!r}."]
    if name in accessor_map:
        parts.append(
            f"{name} is a FLExProject accessor, not an import: use project.{name} "
            "(no import needed)."
        )
    elif did_you_mean:
        parts.append(f"Did you mean: from flexicon import {did_you_mean[0]}?")
        if accessor:
            parts.append(f"Or skip the import and use project.{accessor}.")
    else:
        parts.append(
            "flexicon exports FLExProject, FLExInitialize/FLExCleanup and the "
            "*Operations classes; reach data through project.<Accessor>. Use "
            "flextools_search_by_capability to find the right API."
        )
    out: Dict[str, Any] = {"did_you_mean": did_you_mean, "suggestion": " ".join(parts)}
    if accessor:
        out["access_path"] = f"project.{accessor}"
    return out


def suggest_module(module: str, surface: _Surface) -> Dict[str, Any]:
    """did_you_mean + fix for an unknown ``flexicon.X`` module path."""
    module = _canonical(module)
    last = module.rsplit(".", 1)[-1]
    paths = sorted(surface.modules)
    exact_tail = [m for m in paths if m.rsplit(".", 1)[-1] == last and m != module]
    did_you_mean = exact_tail[:3] or difflib.get_close_matches(module, paths, n=3, cutoff=0.8)
    parts = [f"No module named {module!r}."]
    if did_you_mean:
        parts.append(f"Did you mean {did_you_mean[0]}?")
    parts.append(
        "Everything public is re-exported at the top level, so prefer "
        "`from flexicon import <Name>Operations` (or project.<Accessor>) over "
        "submodule paths."
    )
    return {"did_you_mean": did_you_mean, "suggestion": " ".join(parts)}


def check_imports(
    code_tree: Optional[ast.AST],
    api_index: Any = None,
    accessor_map: Optional[Dict[str, str]] = None,
    surface: Optional[_Surface] = None,
) -> Dict[str, Any]:
    """Find flexicon import names/paths that do not exist.

    Returns dict with ``has_unknown``, ``issues`` (list of {statement, kind
    ("name"|"module"), module, name, lineno, did_you_mean, suggestion[,
    access_path]}), ``did_you_mean`` (first issue's list) and ``suggestion``
    (first issue's text). Never raises.
    """
    result: Dict[str, Any] = {"has_unknown": False, "issues": [], "did_you_mean": [], "suggestion": ""}
    if code_tree is None:
        return result
    try:
        surface = surface or load_surface(api_index)
    except Exception:  # noqa: BLE001 -- fail open, see module docstring
        return result
    if surface is None:
        return result
    issues: List[Dict[str, Any]] = []

    def _add(node: ast.stmt, kind: str, module: str, name: str, info: Dict[str, Any]) -> None:
        stmt = (
            f"from {module} import {name}" if kind == "name" and name
            else f"import {module}"
        )
        issue = {
            "statement": stmt,
            "kind": kind,
            "module": module,
            "name": name,
            "lineno": getattr(node, "lineno", None),
            **info,
        }
        issues.append(issue)

    for node in ast.walk(code_tree):
        if isinstance(node, ast.ImportFrom) and not node.level:
            module = node.module or ""
            canon = _canonical(module)
            if not canon.startswith("flexicon"):
                continue
            if canon == "flexicon":
                if surface.root_open:
                    continue
                for alias in node.names:
                    if alias.name == "*" or alias.name in surface.root_names:
                        continue
                    if not surface.source_found and not (
                        alias.name.endswith("Operations") or alias.name == "FLExProject"
                    ):
                        # The index lists classes, not module-level helpers
                        # (cast_to_concrete, FLExInitialize, ...): without the
                        # package source, judge only Operations-shaped names
                        # (same rule as scripts/check_doc_snippets.py).
                        continue
                    _add(node, "name", module, alias.name,
                         suggest_name(alias.name, surface, accessor_map))
                continue
            if not surface.source_found:
                continue  # index fallback cannot see submodules
            if canon not in surface.modules:
                _add(node, "module", module, "", suggest_module(module, surface))
                continue
            names, is_open = surface.module_names(canon)
            if is_open:
                continue
            for alias in node.names:
                if alias.name == "*" or alias.name in names:
                    continue
                info = suggest_name(alias.name, surface, accessor_map)
                info["suggestion"] = (
                    f"{canon} has no {alias.name!r}. " + info["suggestion"]
                )
                _add(node, "name", module, alias.name, info)
        elif isinstance(node, ast.Import) and surface.source_found:
            for alias in node.names:
                canon = _canonical(alias.name)
                if canon.startswith("flexicon.") and canon not in surface.modules:
                    _add(node, "module", alias.name, "", suggest_module(alias.name, surface))
    if issues:
        result["has_unknown"] = True
        result["issues"] = issues
        result["did_you_mean"] = issues[0]["did_you_mean"]
        result["suggestion"] = issues[0]["suggestion"]
    return result


_CANNOT_IMPORT_RE = re.compile(r"cannot import name '([^']+)' from '(flexicon|flexlibs2)(?:\.[\w.]*)?'")
_NO_MODULE_RE = re.compile(r"No module named '((?:flexicon|flexlibs2)\.[\w.]+)'")


def diagnose_import_error(
    error_msg: str,
    api_index: Any = None,
    accessor_map: Optional[Dict[str, str]] = None,
    surface: Optional[_Surface] = None,
) -> Dict[str, Any]:
    """Runtime twin of check_imports: candidates for a raised ImportError."""
    out: Dict[str, Any] = {"is_unknown_import": False}
    if not error_msg:
        return out
    try:
        surface = surface or load_surface(api_index)
    except Exception:  # noqa: BLE001 -- fail open
        surface = None
    m = _CANNOT_IMPORT_RE.search(error_msg)
    if m:
        name = m.group(1)
        info = suggest_name(name, surface, accessor_map) if surface else {
            "did_you_mean": [], "suggestion": f"flexicon does not export {name!r}."}
        out.update(is_unknown_import=True, name=name, module=m.group(2), **info)
        return out
    m = _NO_MODULE_RE.search(error_msg)
    if m:
        module = m.group(1)
        info = suggest_module(module, surface) if surface and surface.source_found else {
            "did_you_mean": [], "suggestion": f"No module named {module!r}."}
        out.update(is_unknown_import=True, name="", module=module, **info)
    return out
