#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Curated API deprecations: members the MCP must never teach or run.

The API indexes are generated from source (LibLCM by .NET reflection,
Flexicon by AST), so they faithfully list every member that exists --
including members that exist but do nothing useful. A generated index
cannot know that. This module is the single, hand-maintained source of
truth for that knowledge, in the same way ``curated_recipes.py`` is for
shipped recipes. It is:

  - applied by the index builders (``liblcm_extractor.py``,
    ``flexicon_analyzer.py``) right before they write JSON, so a refresh
    regenerates the annotations instead of dropping them,
  - applied again by the server when it loads an index
    (``server.APIIndex``), so an index generated before an entry was added
    here -- e.g. one a user regenerated locally, or the per-user overlay
    copy an installed wheel seeds -- still carries it,
  - read by the preflight validator ``detect_deprecated_members``
    (``server/validators.py``), which refuses code that uses a deprecated
    member at all (error code ``deprecated_member``), and
  - read by the discovery handlers, which flag, demote and redirect
    deprecated members in their output.

Applying is idempotent: re-applying rewrites the same annotation.

To regenerate only the annotations on the checked-in indexes without a full
refresh (no FieldWorks DLLs needed)::

    python -m flextoolsmcp.curated_deprecations --apply

Annotation shape added to an index member (property or method)::

    "deprecated": true,
    "deprecation": {
        "id": "...",                 # key in CURATED_DEPRECATIONS
        "note": "...",               # one-paragraph explanation + redirect
        "replacement_paths": [...],  # object PATHS, never a bare member name
        "replacement_owner": "...",  # interface that owns the replacement
        "example": "...",            # runnable bare-snippet code
        "evidence": [...],           # source citations
    }
"""

from __future__ import annotations

import ast
import copy
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

# ---------------------------------------------------------------------------
# DoNotUseForParsing
# ---------------------------------------------------------------------------
#
# IsAbstract lives on IMoForm (the entry's LexemeFormOA and each item of its
# AlternateFormsOS), NOT on ILexEntry -- `entry.IsAbstract` does not exist.
# Every redirect below names the forms explicitly for that reason; do not
# shorten any of them to "use IsAbstract".

_DNUFP_NOTE = (
    "Deprecated: no parser effect. ILexEntry.DoNotUseForParsing is not read "
    "by either FLEx parser -- HermitCrab (HCLoader.cs) loads every entry and "
    "skips only forms whose IsAbstract is set (HCLoader.cs:543 for affixes, "
    ":585 for stems), and XAmple (FxtM3ParserToXAmpleLex.xsl) filters only "
    "on @IsAbstract. The field is used only by LIFT import/export and is not "
    "shown in the FLEx UI. To hide an entry from the parser, set IsAbstract "
    "on its forms (IMoForm), not on the entry: entry.LexemeFormOA.IsAbstract "
    "= True, and on each allomorph in entry.AlternateFormsOS. The entry is "
    "fully hidden only when every form is abstract. There is no "
    "ILexEntry.IsAbstract. Caveat: HermitCrab does not check IsAbstract on "
    "IMoAffixProcess forms (HCLoader.cs:538-540)."
)

# Runnable bare snippet (CLAUDE.md "lightweight op form"). Walks from the
# entry to its forms, guards a missing LexemeFormOA, and guards the write.
# No cast: LexemeFormOA is typed IMoForm and AlternateFormsOS yields IMoForm
# items, and IsAbstract is declared on IMoForm itself (casting index:
# properties.IsAbstract.defined_on == ["IMoForm"]), so it is reachable on
# every concrete form (IMoStemAllomorph, IMoAffixAllomorph, ...) as-is.
_DNUFP_EXAMPLE = (
    "# Hide an entry from the parser: mark every one of its FORMS abstract.\n"
    "# IsAbstract is on IMoForm (entry.LexemeFormOA and each item of\n"
    "# entry.AlternateFormsOS), not on the entry -- entry.IsAbstract does not exist.\n"
    "TARGET = \"example-headword\"  # the entry to hide\n"
    "for entry in project.LexEntry.GetAll():\n"
    "    if project.LexEntry.GetHeadword(entry) != TARGET:\n"
    "        continue\n"
    "    forms = []\n"
    "    if entry.LexemeFormOA is not None:  # an entry can lack a lexeme form\n"
    "        forms.append(entry.LexemeFormOA)\n"
    "    forms.extend(entry.AlternateFormsOS)  # allomorphs, already IMoForm\n"
    "    if modifyAllowed:\n"
    "        for form in forms:\n"
    "            form.IsAbstract = True\n"
    "    report.Info(f\"{TARGET}: {len(forms)} form(s) marked abstract\")\n"
)

_DNUFP_REPLACEMENT_PATHS = [
    "ILexEntry.LexemeFormOA.IsAbstract",
    "ILexEntry.AlternateFormsOS[*].IsAbstract",
]

_DNUFP_EVIDENCE = [
    "FieldWorks Src/LexText/ParserCore/HCLoader.cs:543 (affix forms: skipped only when IsAbstract)",
    "FieldWorks Src/LexText/ParserCore/HCLoader.cs:585 (stem forms: skipped only when IsAbstract)",
    "FieldWorks Src/LexText/ParserCore/HCLoader.cs:538-540 (IMoAffixProcess forms bypass the IsAbstract check)",
    "FieldWorks Src/Transforms/Application/FxtM3ParserToXAmpleLex.xsl (XAmple filters only on @IsAbstract)",
]


# Keyed by deprecation id. ``targets`` are (library, entity, member) triples,
# where library is the APIIndex attribute name ("liblcm", "flexicon",
# "flexlibs_stable"). ``code_names`` are the attribute names the preflight
# refuses on ANY receiver -- the names are distinctive enough that an exact
# attribute-name match carries no realistic false-positive risk.
CURATED_DEPRECATIONS: Dict[str, Dict[str, Any]] = {
    "lexentry-donotuseforparsing": {
        "targets": [
            ("liblcm", "ILexEntry", "DoNotUseForParsing"),
            ("liblcm", "LexEntry", "DoNotUseForParsing"),
            ("flexicon", "LexEntryOperations", "GetDoNotUseForParsing"),
            ("flexicon", "LexEntryOperations", "SetDoNotUseForParsing"),
        ],
        "code_names": [
            "DoNotUseForParsing",
            "GetDoNotUseForParsing",
            "SetDoNotUseForParsing",
        ],
        # Search/capability queries about this intent get the redirect even
        # when no deprecated member is among the hits.
        "intent_terms": [
            "do not use for parsing",
            "donotuseforparsing",
            "hide from parser",
            "hide entry from parser",
            "exclude from parser",
            "exclude from parsing",
            "excluded from parsing",
            "skip parsing",
            "not used for parsing",
            "abstract form",
        ],
        "note": _DNUFP_NOTE,
        # Preflight next_steps specific to this deprecation (the generic
        # "remove it" / example / re-run steps are added around these).
        "fix_steps": [
            "To hide an entry from the parser, set IsAbstract on its FORMS: "
            "`entry.LexemeFormOA.IsAbstract` and `IsAbstract` on each item of "
            "`entry.AlternateFormsOS`. IsAbstract is on IMoForm, not ILexEntry "
            "(`entry.IsAbstract` does not exist). Check "
            "`entry.LexemeFormOA is not None` first. The entry is fully hidden "
            "only when every form is abstract.",
            "To test whether an entry is hidden, check its forms instead: "
            "`all(f.IsAbstract for f in forms)` where forms is "
            "entry.LexemeFormOA (if not None) plus entry.AlternateFormsOS.",
        ],
        "replacement_paths": _DNUFP_REPLACEMENT_PATHS,
        "replacement_owner": "IMoForm",
        "example": _DNUFP_EXAMPLE,
        "evidence": _DNUFP_EVIDENCE,
        # Temporary block, not a verdict on the field: FLEx may implement it
        # in the parsers (to take load off IsAbstract), with no timeline. When
        # it does, delete this entry (and the MISPLACED_MEMBERS row pointing
        # at it) and re-apply the indexes. Not part of the index annotation.
        "tracking": {
            "ticket": "LT-22810",
            "url": "https://jira.sil.org/browse/LT-22810",
            "unblock_when": (
                "FLEx and its parsers (HermitCrab via HCLoader.cs, XAmple via "
                "the M3 export/XSLTs) actually respect DoNotUseForParsing."
            ),
        },
        # Read by scripts/upstream_flag_watch.py (weekly workflow
        # upstream-flag-watch.yml). ``repos`` maps each watched repo to every
        # default-branch path that mentioned the term on 2026-09-25 -- all
        # storage, LIFT, copy and test-data uses with no parser effect. Any
        # other path, or any PR, issue or commit mentioning the term that is
        # not in ``baseline_refs``, is reported as a sign the block may be
        # ready to lift.
        "upstream_watch": {
            "term": "DoNotUseForParsing",
            "repos": {
                "sillsdev/FieldWorks": [
                    "DistFiles/Language Explorer/Import/LLImportPhase3.xsl",
                    "DistFiles/Templates/MasterFieldWorksModel7.0.xml",
                    "Src/LexText/LexTextControls/LiftExporter.cs",
                    "Src/LexText/LexTextControls/LiftMerger.cs",
                ],
                "sillsdev/liblcm": [
                    "src/SIL.LCModel/DomainImpl/OverridesLing_Lex.cs",
                    "tests/SIL.LCModel.FixData.Tests/TestData/HomographDrops/Test.fwdata",
                    "tests/SIL.LCModel.Tests/DomainImpl/LexEntryTests.cs",
                    "tests/SIL.LCModel.Tests/TestData/DataMigration7000024Tests.xml",
                    "tests/SIL.LCModel.Tests/TestData/DataMigration7000029Tests.xml",
                    "tests/SIL.LCModel.Tests/TestData/DataMigration7000030.xml",
                ],
                "sillsdev/machine": [],
            },
            "baseline_refs": [
                "https://github.com/sillsdev/liblcm/pull/38",
                "https://github.com/sillsdev/liblcm/pull/219",
            ],
        },
    },
}


# Members that people migrating away from a deprecated member tend to put on
# the WRONG object. Keyed by (receiver interface, attribute). Consulted by
# the interface-attribute validator so the rejection points at the right
# object instead of suggesting a spelling or a cast.
MISPLACED_MEMBERS: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("ILexEntry", "IsAbstract"): {
        "deprecation_id": "lexentry-donotuseforparsing",
        "correct_owner": "IMoForm",
        "correct_paths": _DNUFP_REPLACEMENT_PATHS,
        "hint": (
            "'IsAbstract' is not on ILexEntry -- it is on the entry's forms "
            "(IMoForm). Set entry.LexemeFormOA.IsAbstract (check that "
            "LexemeFormOA is not None first) and IsAbstract on each item of "
            "entry.AlternateFormsOS; the entry is hidden from the parser only "
            "when every form is abstract."
        ),
    },
}


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------

def _build_target_map() -> Dict[Tuple[str, str, str], str]:
    out: Dict[Tuple[str, str, str], str] = {}
    for dep_id, dep in CURATED_DEPRECATIONS.items():
        for lib, entity, member in dep["targets"]:
            out[(lib, entity, member)] = dep_id
    return out


def _build_code_name_map() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for dep_id, dep in CURATED_DEPRECATIONS.items():
        for name in dep.get("code_names", []):
            out[name] = dep_id
    return out


_TARGETS = _build_target_map()
_CODE_NAMES = _build_code_name_map()


def deprecation_record(dep_id: str) -> Dict[str, Any]:
    """The public annotation dict for a deprecation id (a fresh copy)."""
    dep = CURATED_DEPRECATIONS[dep_id]
    return {
        "id": dep_id,
        "note": dep["note"],
        "replacement_paths": list(dep["replacement_paths"]),
        "replacement_owner": dep["replacement_owner"],
        "example": dep["example"],
        "evidence": list(dep["evidence"]),
    }


def fix_steps(dep_id: str) -> List[str]:
    """Deprecation-specific preflight next_steps (may be empty)."""
    return list(CURATED_DEPRECATIONS.get(dep_id, {}).get("fix_steps", []))


def deprecated_code_names() -> Dict[str, str]:
    """{attribute/method name: deprecation id} for the preflight detector."""
    return dict(_CODE_NAMES)


def lookup_member(
    name: Optional[str],
    entity: Optional[str] = None,
    library: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Deprecation record for a member, or None.

    With ``entity`` (and optionally ``library``) the lookup is exact. Without
    ``entity`` it matches on the bare member name, which is what callers that
    only have a property/method name (resolve_property, find_wrappers_for_lcm)
    need.
    """
    if not name:
        return None
    # Tolerate dotted "Entity.Member" names.
    if entity is None and "." in name:
        entity, _, name = name.rpartition(".")
    for (lib, ent, member), dep_id in _TARGETS.items():
        if member != name:
            continue
        if entity is not None and ent != entity:
            continue
        if library is not None and lib != library:
            continue
        return deprecation_record(dep_id)
    return None


def match_intent(query: Optional[str]) -> List[Dict[str, Any]]:
    """Deprecations whose ``intent_terms`` (or member names) appear in a query."""
    if not query:
        return []
    q = " ".join(query.lower().replace("_", " ").replace("-", " ").split())
    compact = q.replace(" ", "")
    hits = []
    for dep_id, dep in CURATED_DEPRECATIONS.items():
        terms = [t.lower() for t in dep.get("intent_terms", [])]
        names = [n.lower() for n in dep.get("code_names", [])]
        if any(t in q for t in terms) or any(n in compact for n in names):
            hits.append(deprecation_record(dep_id))
    return hits


def misplaced_member(interface: str, attr: str) -> Optional[Dict[str, Any]]:
    """Curated hint for a member placed on the wrong object, or None."""
    info = MISPLACED_MEMBERS.get((interface, attr))
    return dict(info) if info else None


# ---------------------------------------------------------------------------
# Index overlay
# ---------------------------------------------------------------------------

def _annotate(member: Dict[str, Any], dep_id: str) -> bool:
    record = deprecation_record(dep_id)
    changed = member.get("deprecated") is not True or member.get("deprecation") != record
    member["deprecated"] = True
    member["deprecation"] = record
    return changed


def apply_to_api_index(api_data: Optional[Dict[str, Any]], library: str) -> int:
    """Annotate deprecated members of an API index in place.

    ``library`` is the APIIndex attribute name ("liblcm", "flexicon",
    "flexlibs_stable"). Returns the number of members annotated. Safe on
    None / malformed input.
    """
    if not isinstance(api_data, dict):
        return 0
    entities = api_data.get("entities")
    if not isinstance(entities, dict):
        return 0
    count = 0
    for (lib, entity_name, member_name), dep_id in _TARGETS.items():
        if lib != library:
            continue
        entity = entities.get(entity_name)
        if not isinstance(entity, dict):
            continue
        for bucket in ("properties", "methods"):
            for member in entity.get(bucket, []) or []:
                if isinstance(member, dict) and member.get("name") == member_name:
                    _annotate(member, dep_id)
                    count += 1
    return count


def apply_to_bridge(bridge: Optional[Dict[str, Any]], library: str) -> int:
    """Annotate deprecated methods in an LCM bridge (``by_method``) in place."""
    if not isinstance(bridge, dict):
        return 0
    by_method = bridge.get("by_method")
    if not isinstance(by_method, dict):
        return 0
    count = 0
    for (lib, entity_name, member_name), dep_id in _TARGETS.items():
        if lib != library:
            continue
        entry = by_method.get(f"{entity_name}.{member_name}")
        if isinstance(entry, dict):
            _annotate(entry, dep_id)
            count += 1
    return count


def apply_to_casting_index(casting: Optional[Dict[str, Any]]) -> int:
    """Annotate deprecated LibLCM properties in the casting index in place."""
    if not isinstance(casting, dict):
        return 0
    props = casting.get("properties")
    if not isinstance(props, dict):
        return 0
    count = 0
    # The casting index is keyed by bare property name, so ILexEntry and
    # LexEntry targets collapse onto one row.
    by_name = {m: d for (lib, _e, m), d in _TARGETS.items() if lib == "liblcm"}
    for member_name, dep_id in by_name.items():
        entry = props.get(member_name)
        if isinstance(entry, dict):
            _annotate(entry, dep_id)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Code scanning (used by server.validators.detect_deprecated_members)
# ---------------------------------------------------------------------------

_REFLECTION_CALLS = frozenset({"getattr", "setattr", "hasattr", "delattr"})


def iter_deprecated_uses(tree: Optional[ast.AST]) -> Iterator[Dict[str, Any]]:
    """Yield one dict per use of a deprecated member in a parsed module.

    AST-based, so comments and ordinary string literals can never match.
    Catches attribute access in any context (read, write, call, del), and
    ``getattr/setattr/hasattr/delattr(obj, "<name>")`` with a literal name.
    A bare Name that happens to equal a deprecated member (a local variable
    or function) is NOT flagged -- it is not an LCM/flexicon member access.
    """
    if tree is None:
        return
    names = _CODE_NAMES
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in names:
            if isinstance(node.ctx, ast.Store):
                access = "write"
            elif isinstance(node.ctx, ast.Del):
                access = "delete"
            else:
                access = "read"
            try:
                expr = ast.unparse(node)
            except Exception:  # pragma: no cover - unparse is total on valid trees
                expr = node.attr
            yield {
                "member": node.attr,
                "deprecation_id": names[node.attr],
                "access": access,
                "expr": expr,
                "line": getattr(node, "lineno", None),
                "col_offset": getattr(node, "col_offset", None),
            }
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _REFLECTION_CALLS
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
            and node.args[1].value in names
        ):
            member = node.args[1].value
            try:
                expr = ast.unparse(node)
            except Exception:  # pragma: no cover
                expr = f"{node.func.id}(..., {member!r})"
            yield {
                "member": member,
                "deprecation_id": names[member],
                "access": "write" if node.func.id in ("setattr", "delattr") else "read",
                "expr": expr,
                "line": getattr(node, "lineno", None),
                "col_offset": getattr(node, "col_offset", None),
            }


# ---------------------------------------------------------------------------
# CLI: re-apply the overlay to the checked-in indexes
# ---------------------------------------------------------------------------

def _dump(data: Dict[str, Any], path: Path) -> None:
    if __package__:
        from .json_utils import sort_json_arrays
    else:
        from json_utils import sort_json_arrays
    data = sort_json_arrays(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)


def _iter_index_files(index_dir: Path) -> Iterable[Tuple[Path, str, str]]:
    """(path, kind, library) for every index file the overlay applies to."""
    for p in sorted((index_dir / "liblcm").glob("liblcm_api_v*.json")):
        yield p, "api", "liblcm"
    for p in sorted((index_dir / "python").glob("flexicon_api_v*.json")):
        yield p, "api", "flexicon"
    for p in sorted((index_dir / "python").glob("flexlibs_api_v*.json")):
        yield p, "api", "flexlibs_stable"
    for p in sorted((index_dir / "python").glob("flexicon_lcm_bridge_v*.json")):
        yield p, "bridge", "flexicon"
    for p in sorted((index_dir / "python").glob("flexlibs_lcm_bridge_v*.json")):
        yield p, "bridge", "flexlibs_stable"
    for p in sorted(index_dir.glob("casting_index_liblcm-v*.json")):
        yield p, "casting", "liblcm"


def apply_to_index_dir(index_dir: Path, write: bool = True) -> Dict[str, int]:
    """Apply the overlay to every index file under ``index_dir``.

    Returns {file name: members annotated}. Files are rewritten only when the
    overlay changed something.
    """
    results: Dict[str, int] = {}
    for path, kind, library in _iter_index_files(index_dir):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        before = copy.deepcopy(data)
        if kind == "api":
            n = apply_to_api_index(data, library)
        elif kind == "bridge":
            n = apply_to_bridge(data, library)
        else:
            n = apply_to_casting_index(data)
        results[path.name] = n
        if write and data != before:
            _dump(data, path)
    return results


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="rewrite the index files in place")
    parser.add_argument(
        "--index-dir",
        default=str(Path(__file__).parent / "index"),
        help="index directory (default: the in-tree index)",
    )
    args = parser.parse_args(argv)
    results = apply_to_index_dir(Path(args.index_dir), write=args.apply)
    for name, n in results.items():
        print(f"[{'OK' if args.apply else 'DRY'}] {name}: {n} deprecated member(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
