"""A queryable view of the LibLCM index, for type-aware source analysis.

The flexicon analyzer historically recognised an LCM property by the *shape of
its name*: a suffix from ``LCM_PROPERTY_SUFFIXES`` (``SensesOS``, ``MsaRA``, …)
or membership of the 14-name ``COMMON_LCM_PROPERTIES`` list. LCM has 1,522
distinct property names and 1,140 of them are not suffix-shaped, so the
detector could see at most 11 of those by name alone. ``ITsString.Text``,
``ILexEntry.HomographNumber`` and ``ILexSense.ScientificName`` were all
invisible.

This module supplies the missing half: what each LCM type actually owns, and
what a relationship property points at. With it the analyzer can resolve
``x.Foo`` against the inferred type of ``x`` and accept any name the index says
that type owns -- and, more usefully, record the access *qualified*
(``ILexSense.Gloss``) so member-level coverage becomes a measurement instead of
an inference.

Degradation is deliberate: if no LibLCM index is present (it needs pythonnet
and the FieldWorks DLLs to regenerate, which not every machine has), an empty
index is returned and every caller falls back to the name-shape rules.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, FrozenSet, Optional, Set

__all__ = ["LcmTypeIndex", "load_lcm_type_index", "clear_cache"]

_VERSIONED = re.compile(r"liblcm_api_v(\d+)\.(\d+)\.(\d+)\.json$")

#: Interfaces every LCM object implements. Typing a receiver as one of these
#: tells you nothing useful, and matching their members would let boilerplate
#: (``Hvo``, ``Guid``, ``ClassName``) masquerade as domain coverage.
UNINFORMATIVE_TYPES: FrozenSet[str] = frozenset({
    "ICmObject", "ICmObjectOrId", "ICmObjectInternal", "ICmObjectOrIdInternal",
    "ICmObjectOrSurrogate", "IReferenceSource",
})


class LcmTypeIndex:
    """Member ownership and relationship targets for LibLCM types."""

    def __init__(self, entities: Optional[Dict[str, Any]] = None):
        self.members: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.owners: Dict[str, Set[str]] = {}
        self.bases: Dict[str, Set[str]] = {}
        entities = entities or {}
        for name, ent in entities.items():
            own: Dict[str, Dict[str, Any]] = {}
            for p in ent.get("properties") or []:
                pname = p.get("name")
                if not pname:
                    continue
                own[pname] = {
                    "kind": p.get("kind") or "property",
                    "target_type": p.get("target_type"),
                    "is_multistring": bool(p.get("is_multistring")),
                    "member_type": "property",
                }
            for m in ent.get("methods") or []:
                mname = m.get("name")
                if mname and mname not in own:
                    own[mname] = {"kind": "method", "target_type": m.get("return_type"),
                                  "is_multistring": False, "member_type": "method"}
            self.members[name] = own
            self.bases[name] = set(ent.get("interfaces") or []) | set(ent.get("base_classes") or [])
            for mname in own:
                self.owners.setdefault(mname, set()).add(name)

    def __bool__(self) -> bool:
        return bool(self.members)

    def known_type(self, name: Optional[str]) -> bool:
        return bool(name) and name in self.members

    def owns(self, entity: str, member: str) -> bool:
        """Does `entity` own `member`, directly or through a base type?"""
        if member in self.members.get(entity, ()):
            return True
        seen, stack = set(), list(self.bases.get(entity, ()))
        while stack:
            b = stack.pop()
            if b in seen:
                continue
            seen.add(b)
            if member in self.members.get(b, ()):
                return True
            stack.extend(self.bases.get(b, ()))
        return False

    def declaring_type(self, entity: str, member: str) -> Optional[str]:
        """The type that actually declares `member` for a receiver of `entity`.

        Attributing an inherited member to the subtype would overstate the
        subtype's surface and understate the base's, so coverage is recorded
        against the declaring type.
        """
        if member in self.members.get(entity, ()):
            return entity
        seen, stack = set(), list(self.bases.get(entity, ()))
        while stack:
            b = stack.pop()
            if b in seen:
                continue
            seen.add(b)
            if member in self.members.get(b, ()):
                return b
            stack.extend(self.bases.get(b, ()))
        return None

    def member_info(self, entity: str, member: str) -> Optional[Dict[str, Any]]:
        owner = self.declaring_type(entity, member)
        return self.members[owner][member] if owner else None

    def target_of(self, entity: str, member: str) -> Optional[str]:
        """The LCM type a relationship property points at, if any."""
        info = self.member_info(entity, member)
        if not info:
            return None
        t = info.get("target_type")
        return t if self.known_type(t) else None

    def sole_owner(self, member: str) -> Optional[str]:
        """The owning type when a member name is unambiguous across all of LCM.

        28% of LCM member names are owned by exactly one type. For those, an
        untyped receiver can still be attributed safely.
        """
        owners = self.owners.get(member)
        if owners and len(owners) == 1:
            only = next(iter(owners))
            return None if only in UNINFORMATIVE_TYPES else only
        return None


_CACHE: Dict[str, LcmTypeIndex] = {}


def clear_cache() -> None:
    _CACHE.clear()


def _newest_index(index_dir: Path) -> Optional[Path]:
    best, best_key = None, ()
    for p in index_dir.glob("liblcm_api_v*.json"):
        m = _VERSIONED.search(p.name)
        key = tuple(int(x) for x in m.groups()) if m else (0, 0, 0)
        if key >= best_key:
            best, best_key = p, key
    return best


def load_lcm_type_index(index_dir: Optional[Path] = None) -> LcmTypeIndex:
    """Load the LibLCM type index, or an empty one when it is unavailable.

    An empty index is not an error: regenerating liblcm_api requires pythonnet
    and the FieldWorks assemblies. Callers fall back to name-shape detection.
    """
    if index_dir is None:
        index_dir = Path(__file__).parent / "index" / "liblcm"
    index_dir = Path(index_dir)
    key = str(index_dir.resolve())
    if key in _CACHE:
        return _CACHE[key]
    path = _newest_index(index_dir)
    if path is None or not path.exists():
        idx = LcmTypeIndex()
    else:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            idx = LcmTypeIndex(doc.get("entities") or {})
        except (OSError, ValueError):
            idx = LcmTypeIndex()
    _CACHE[key] = idx
    return idx
