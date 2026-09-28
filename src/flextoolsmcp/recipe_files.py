#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recipe file format + loader (unified-recipes Phase 2, FR-001..005).

One-file-per-recipe sources under ``src/flextoolsmcp/recipe_library/*.py``.
Each file starts with a metadata docstring of ``key: value`` lines and an
MCPlayground-style ``# --- PARAMS ---`` block. This module owns everything
about the on-disk format (research R1):

- header parsing (R3),
- PARAMS parsing via AST/tokenize (R4),
- directory loading over ``importlib.resources`` (R2),
- malformed-file skip vs id-collision raise (R5),
- ``code_terms`` extraction with camelCase/underscore split + alias table,
- shared scrub patterns (GUID, Windows user path, forbidden names),
- the draft renderer used by ``promote`` (R13).

Files are parsed statically (``ast``/``tokenize``) and never executed.
"""

from __future__ import annotations

import ast
import importlib.resources
import io
import json
import logging
import re
import tokenize
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "REQUIRED_KEYS",
    "OPTIONAL_KEYS",
    "FORBIDDEN_NAMES",
    "GUID_RE",
    "USER_PATH_RE",
    "CODE_ALIASES",
    "parse_recipe_source",
    "parse_recipe_file",
    "parse_params",
    "extract_code_terms",
    "find_scrub_lines",
    "load_recipe_library",
    "merge_recipes",
    "render_draft",
]

logger = logging.getLogger(__name__)

REQUIRED_KEYS = (
    "id",
    "intent",
    "match_terms",
    "entities",
    "operations",
    "requires_write",
    "notes",
    "origin",
)

OPTIONAL_KEYS = ("verified_against", "takes_params", "raw_lcm_lines")

FORBIDDEN_NAMES = ("Claude-Swahili", "Target")

GUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
USER_PATH_RE = re.compile(r"[A-Za-z]:\\Users\\[^\s\"']*")

PARAMS_START = "# --- PARAMS ---"
PARAMS_END = "# --- END PARAMS ---"

# Alias table (research R10): code piece -> extra query words.
CODE_ALIASES: Dict[str, List[str]] = {
    "env": ["environment"],
    "msa": ["grammatical", "info"],
    "pos": ["part", "of", "speech"],
    "infl": ["inflection", "inflectional"],
    "feat": ["feature"],
    "feats": ["feature"],
    "wfi": ["wordform"],
    "allo": ["allomorph"],
    "phon": ["phonological"],
    "templ": ["template"],
    "occurrence": ["frequency", "count"],
}

_LCM_SUFFIX_RE = re.compile(r"(?<=[a-z0-9])(OA|OS|OC|RA|RS|RC)$")
_MUTATION_PREFIX_RE = re.compile(r"^(Get|Set|Add|Remove|Create)(?=[A-Z]|$)")


# ---------------------------------------------------------------------------
# Header parsing (R3)
# ---------------------------------------------------------------------------

def _parse_header_lines(docstring: str, filename: str) -> Dict[str, Any]:
    header: Dict[str, Any] = {}
    current_key: Optional[str] = None
    for lineno, raw_line in enumerate(docstring.splitlines(), start=1):
        if not raw_line.strip():
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", raw_line)
        if m:
            key, value_text = m.group(1), m.group(2).strip()
            try:
                value: Any = json.loads(value_text)
            except Exception:
                value = value_text
            header[key] = value
            current_key = key
        elif raw_line[0] in (" ", "\t") and current_key is not None:
            # Continuation line: indented deeper than its key, joined
            # with a single space.
            header[current_key] = f"{header[current_key]} {raw_line.strip()}"
        else:
            raise ValueError(
                f"{filename}: malformed header line {lineno}: {raw_line.strip()!r}"
            )
    return header


def _split_docstring(text: str, filename: str) -> Tuple[Dict[str, Any], str]:
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        raise ValueError(f"{filename}: malformed file: SyntaxError: {e}") from e
    if (
        not tree.body
        or not isinstance(tree.body[0], ast.Expr)
        or not isinstance(tree.body[0].value, ast.Constant)
        or not isinstance(tree.body[0].value.value, str)
    ):
        raise ValueError(f"{filename}: malformed file: missing metadata docstring")
    node = tree.body[0]
    docstring = node.value.value
    header = _parse_header_lines(docstring, filename)
    for key in REQUIRED_KEYS:
        if key not in header:
            raise ValueError(f"{filename}: malformed file: missing key {key!r}")
    lines = text.splitlines()
    end = node.end_lineno or 1
    code_lines = lines[end:]
    while code_lines and not code_lines[0].strip():
        code_lines.pop(0)
    code = "\n".join(code_lines)
    if code and not code.endswith("\n"):
        code += "\n"
    return header, code


def parse_recipe_source(text: str, filename: str = "<string>") -> Dict[str, Any]:
    """Parse one recipe file's text into a recipe dict.

    Raises ``ValueError`` naming the file and the key on malformed input.
    """
    header, code = _split_docstring(text, filename)
    recipe_id = header["id"]
    stem = Path(filename).stem
    if stem not in ("<string>", "<stdin>") and stem != recipe_id:
        raise ValueError(
            f"{filename}: malformed file: stem {stem!r} != id {recipe_id!r}"
        )
    params = parse_params(code)
    recipe: Dict[str, Any] = {
        "id": recipe_id,
        "intent": header["intent"],
        "match_terms": header["match_terms"],
        "entities": header["entities"],
        "operations": header["operations"],
        "requires_write": header["requires_write"],
        "code": code,
        "notes": header["notes"],
        "origin": header["origin"],
        "params": params,
        "code_terms": extract_code_terms(code),
        "source": "curated",
    }
    if "verified_against" in header:
        recipe["verified_against"] = header["verified_against"]
    recipe["takes_params"] = header.get("takes_params", bool(params))
    if "raw_lcm_lines" in header:
        recipe["raw_lcm_lines"] = header["raw_lcm_lines"]
    return recipe


def parse_recipe_file(path: Path) -> Dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    return parse_recipe_source(text, filename=Path(path).name)


# ---------------------------------------------------------------------------
# PARAMS parsing (R4)
# ---------------------------------------------------------------------------

def _params_block_lines(code: str) -> Optional[List[str]]:
    lines = code.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == PARAMS_START)
        end = next(i for i, ln in enumerate(lines) if ln.strip() == PARAMS_END)
    except StopIteration:
        return None
    if end <= start:
        return None
    return lines[start + 1 : end]


def _comment_tokens(slice_text: str) -> Dict[int, List[str]]:
    comments: Dict[int, List[str]] = {}
    try:
        tokens = tokenize.generate_tokens(io.StringIO(slice_text).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT:
                text = tok.string.lstrip("#").strip()
                comments.setdefault(tok.start[0], []).append(text)
    except Exception:
        return {}
    return comments


def parse_params(code: str) -> List[Dict[str, str]]:
    """Derive ``[{name, default, description}]`` from the PARAMS block.

    A missing block gives ``[]``; a block that does not parse gives ``[]``.
    """
    block = _params_block_lines(code)
    if not block:
        return []
    slice_text = "\n".join(block)
    try:
        tree = ast.parse(slice_text)
    except SyntaxError:
        return []
    comments = _comment_tokens(slice_text)
    params: List[Dict[str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            name = node.targets[0].id
            value_node = node.value
        elif isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name) or node.value is None:
                continue
            name = node.target.id
            value_node = node.value
        else:
            continue
        first_line = node.lineno
        last_line = node.end_lineno or first_line
        default = ast.get_source_segment(slice_text, value_node) or ""
        trailing = " ".join(comments.get(first_line, []))
        if trailing:
            base = trailing
        else:
            above: List[str] = []
            for i in range(first_line - 2, -1, -1):
                if i < 0 or i >= len(block):
                    break
                stripped = block[i].strip()
                if stripped.startswith("#"):
                    above.append(stripped.lstrip("#").strip())
                else:
                    break
            above.reverse()
            base = " ".join(above)
        inside: List[str] = []
        for ln in range(first_line + 1, last_line + 1):
            inside.extend(comments.get(ln, []))
        description = " ".join([p for p in [base, " ".join(inside)] if p])
        params.append({"name": name, "default": default, "description": description})
    return params


# ---------------------------------------------------------------------------
# code_terms (R10)
# ---------------------------------------------------------------------------

def _split_identifier(name: str) -> List[str]:
    parts = name.split("_")
    terms: List[str] = []
    for part in parts:
        spaced = re.sub(
            r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", part
        )
        terms.extend(spaced.split())
    return [t.lower() for t in terms if t]


def extract_code_terms(code: str) -> List[str]:
    """Extract function/attribute terms from code for ranking.

    Internal only, never serialized in rows (data-model section 1).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    raw_names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            raw_names.append(node.attr)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                raw_names.append(func.id)
    terms: List[str] = []
    for raw in raw_names:
        name = _MUTATION_PREFIX_RE.sub("", raw)
        name = _LCM_SUFFIX_RE.sub("", name)
        if not name:
            continue
        pieces = _split_identifier(name)
        terms.extend(pieces)
        for piece in pieces:
            terms.extend(CODE_ALIASES.get(piece, []))
    seen: Dict[str, None] = {}
    for term in terms:
        if term and term not in seen:
            seen[term] = None
    return sorted(seen.keys())


# ---------------------------------------------------------------------------
# Scrub patterns (shared by loader, validator, promote)
# ---------------------------------------------------------------------------

def find_scrub_lines(
    code: str, projects: Optional[List[str]] = None
) -> List[Tuple[int, str]]:
    """Flag lines containing GUIDs, Windows user paths, or project names."""
    hits: List[Tuple[int, str]] = []
    names = list(FORBIDDEN_NAMES) + list(projects or [])
    for lineno, line in enumerate(code.splitlines(), start=1):
        if GUID_RE.search(line) or USER_PATH_RE.search(line):
            hits.append((lineno, line.strip()))
            continue
        if any(n and n in line for n in names):
            hits.append((lineno, line.strip()))
    return hits


# ---------------------------------------------------------------------------
# Library loading (R2, R5)
# ---------------------------------------------------------------------------

def _default_library_dir() -> Optional[Path]:
    try:
        lib = importlib.resources.files("flextoolsmcp") / "recipe_library"
        if lib.is_dir():
            return Path(str(lib))
    except Exception:
        return None
    return None


def load_recipe_library(
    library_dir: Optional[Path] = None,
) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Load every ``*.py`` recipe file into ``{id: recipe}``.

    Returns ``(recipes, errors)``. A malformed file is skipped with one
    logged error naming the file and the key; an id collision raises
    ``ValueError`` (R5). Files are parsed statically, never executed.
    """
    directory = Path(library_dir) if library_dir is not None else _default_library_dir()
    if directory is None or not Path(directory).is_dir():
        return {}, []
    recipes: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []
    origins: Dict[str, str] = {}
    for path in sorted(Path(directory).rglob("*.py")):
        try:
            recipe = parse_recipe_file(path)
        except ValueError as e:
            message = str(e)
            errors.append(message)
            logger.error(message)
            continue
        recipe_id = recipe["id"]
        if recipe_id in recipes:
            raise ValueError(
                f"Duplicate recipe id {recipe_id!r}: "
                f"{origins[recipe_id]} and {path}"
            )
        recipes[recipe_id] = recipe
        origins[recipe_id] = str(path)
    return recipes, errors


def merge_recipes(
    base: Dict[str, Dict[str, Any]],
    incoming: Dict[str, Dict[str, Any]],
    default_flexicon_version: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Merge file recipes into a base dict, raising on id collision (R5)."""
    merged = dict(base)
    for recipe_id, recipe in incoming.items():
        if recipe_id in merged:
            raise ValueError(
                f"Duplicate recipe id {recipe_id!r}: file recipe collides "
                "with a dict entry"
            )
        if default_flexicon_version is not None:
            verified = recipe.get("verified_against")
            if (
                not isinstance(verified, dict)
                or verified.get("flexicon") is None
            ):
                recipe = dict(recipe)
                recipe["verified_against"] = {
                    "flexicon": default_flexicon_version,
                    "verified_by": (
                        verified.get("verified_by", "preflight")
                        if isinstance(verified, dict)
                        else "preflight"
                    ),
                }
        merged[recipe_id] = recipe
    return merged


# ---------------------------------------------------------------------------
# Draft renderer (R13, used by promote)
# ---------------------------------------------------------------------------

def render_draft(local_record: Dict[str, Any], new_id: str) -> str:
    """Render a draft recipe file from a local record.

    The draft intentionally fails validation until a human fills in
    ``match_terms`` and ``notes`` (research R13).
    """
    local_id = local_record.get("id", "local-unknown")
    intent = local_record.get("intent") or f"Promoted from {local_id}"
    entities = local_record.get("entities") or []
    requires_write = bool(local_record.get("requires_write", False))
    operations = ["read", "write"] if requires_write else ["read"]
    code = local_record.get("code", "")
    header_lines = [
        '"""',
        f"id: {new_id}",
        f"intent: {intent}",
        "match_terms: []",
        f"entities: {json.dumps(sorted(entities))}",
        f"operations: {json.dumps(operations)}",
        f"requires_write: {str(requires_write).lower()}",
        f'origin: "local:{local_id}"',
        'notes: "TODO"',
        '"""',
    ]
    body = code if code.endswith("\n") or not code else code + "\n"
    if PARAMS_START not in body:
        body += (
            "\n# --- PARAMS ---\n"
            "# TODO: move tunable values here\n"
            "# --- END PARAMS ---\n"
        )
    return "\n".join(header_lines) + "\n" + body
