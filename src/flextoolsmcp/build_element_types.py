#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build Element-Type Annotations for FlexToolsMCP (issue #121)

Cross-annotates Flexicon method records with the runtime element type of
the LibLCM collection property that feeds their return value, plus whether
that element type is polymorphic (i.e. pythonnet hands back a base
interface, so subtype-only members need an explicit cast before use).

This is deliberately a separate post-process step (not folded into
flexicon_analyzer.py) because it needs BOTH the just-scanned Flexicon index
(for `element_source_property`, set by
flexicon_analyzer._resolve_element_source_property) AND the LibLCM index
(for the authoritative `target_type` of that property) in scope at once --
the same reason build_reverse_mapping.py and build_casting_index.py are
their own steps rather than living inside a single-library extractor.

Root cause (issue #121): a casting preflight can only warn about a
collection-returning call if the index records what type the elements
actually arrive as. LibLCM property `target_type` is the runtime truth
(what pythonnet hands back before any cast) -- NOT the docstring prose,
which was measured to disagree with `target_type` for 15 flexicon methods
(prose describes the conceptual type; `target_type` describes the arrival
type). See flexicon_analyzer.py's "Element-source-property resolution"
comment block for how `element_source_property` itself is derived.

Scope of the target_type-over-prose rationale (issue #121 remediation,
defect 3): the above holds cleanly for RAW LCM property access -- a
method that returns `list(x.PropOS)` or similar with no further
processing hands the caller exactly what pythonnet handed the property.
It is NOT automatically true once the method body re-casts elements via
`_GetTypedElements`/`cast_all` (BaseOperations.py:1717-1757,
lcm_casting.py:471-614) before returning: those elements have ALREADY
been resolved to their concrete LCM interface, so the caller receives
concrete objects, not the abstract `target_type` this module records.
`element_cast_applied` (set by flexicon_analyzer.py when the resolved
`element_source_property` is piped through one of those helpers) records
that fact so a downstream consumer can distinguish "raw, needs an
explicit cast" from "already concrete, but possibly still a mix of
sibling concrete types" -- `LexEntryOperations.GetComplexFormComponents`
is the latter (docstring: "components can be entries OR senses", and
LCM's own data model genuinely stores either), so it correctly stays
`polymorphic: true` even after casting; `AnthropologyOperations.GetSubitems`
(`element_type: "ICmPossibility"`, one of `ICmPossibility`'s 13 sibling
interfaces per FieldWorks' `CmPossibilityList` design) is -- per the
FieldWorks domain convention that a given possibility list is
homogeneously typed to one `ItemClsid` -- *practically* always a single
concrete subtype (`ICmAnthroItem`) in real data, even though its
raw LCM property declaration is polymorphic in the general case.

This module does NOT attempt a general auto-resolution of that residual
ambiguity via docstring prose (e.g. "the docstring says 'X or Y objects'")
-- that was considered and rejected: it would reintroduce exactly the
prose-vs-target_type disagreement this module was built to avoid, on data
(hand-written docstrings) not consistently reliable across the ~114-method
corpus. It DOES resolve one reliable, purely-syntactic sub-case, found
while widening return_type coverage for defect 2 below:
`UnpackNestedPossibilityList(possList.PossibilitiesOS, ICmAnthroItem,
recursive)` (FLExProject.py, used by AnthropologyOperations,
LocationOperations, SemanticDomainOperations `GetAll`, ...) passes the
target concrete LCM interface as a LITERAL argument alongside the
collection -- an explicit, 100% AST-detectable author assertion, not an
inference from prose. flexicon_analyzer.py records that as
`element_type_hint` (see its "Explicit element-type-hint detection"
comment block); this module prefers it over the raw property target_type
when present and validated (a genuine interface-typed LCM entity).

That mechanism does NOT reach `GetSubitems`: its call
(`self._GetTypedElements(item.SubPossibilitiesOS)`) never names the
concrete type in the source at all -- the homogeneity is a FieldWorks
domain fact (a `CmPossibilityList` is homogeneously typed to one
`ItemClsid`), not something the calling code asserts syntactically.
`GetComplexFormComponents` has the same "no literal type named" shape,
but is genuinely mixed at the data level (LCM's own model: complex-form
components legitimately are either `ILexEntry` or `ILexSense`) -- both
therefore correctly retain `polymorphic: true`; distinguishing "no
literal type because genuinely mixed" from "no literal type because the
homogeneity is implicit/domain-known" for THIS class of method remains
unresolved and out of scope, for the reasons above. `element_cast_applied`
remains the reliable, general-purpose fallback signal: a downstream
consumer (e.g. the casting-preflight validator) can use it to stop
recommending `cast_to_concrete()` as a remedy for any method that has
already applied it, independent of whether `element_type_hint` narrowed
the type further.

Usage:
    python src/build_element_types.py
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Optional, Set

if __package__:
    from .file_utils import get_index_dir, load_json, save_json
    from .server.versioning import find_latest_versioned_api_file
    from .build_casting_index import KEY_HIERARCHY
else:
    from file_utils import get_index_dir, load_json, save_json
    from server.versioning import find_latest_versioned_api_file
    from build_casting_index import KEY_HIERARCHY


# ============================================================
# Constants (avoid stringly-typed dicts scattered through the code)
# ============================================================
KEY_ELEMENT_SOURCE_PROPERTY = "element_source_property"
KEY_ELEMENT_TYPE_HINT = "element_type_hint"
# Note: `element_cast_applied` is set by flexicon_analyzer.py directly on
# the method record (see `_element_source_uses_cast_helper`); this module
# doesn't read or write it, only documents the interaction above.
KEY_ELEMENT_TYPE = "element_type"
KEY_POLYMORPHIC = "polymorphic"
KEY_RETURN_TYPE = "return_type"
KEY_LCM_DEPENDENCIES = "lcm_dependencies"

# The one interface every genuinely mixed-type LCM reference/owning
# collection is declared over. Always polymorphic by construction.
ABSTRACT_ROOT_INTERFACE = "ICmObject"

_CASTING_INDEX_PATTERN = re.compile(r"casting_index_liblcm-v(\d+\.\d+\.\d+)\.json$")

# Issue #121 defect 2: behavioral-collection return-type shapes this API
# actually uses that name their element type directly in the annotation,
# needing no LCM bridge/target_type lookup at all. Surveyed across the
# whole flexicon_api_v4.6.0.json index: `EnumerableWrapper[IX]` (39
# methods, almost all `GetAll`) and `list[IX]` (18 methods, also mostly
# `GetAll`) are the only two bracketed shapes whose type parameter is an
# LCM interface. Other bracketed shapes found in the same survey --
# `AffixTemplateCollection[...]`, `AllomorphCollection[...]`,
# `CompoundRuleCollection[...]`, `RuleCollection[...]`, `tuple[...]` --
# are deliberately excluded: the four *Collection ones are flexicon's own
# fluent Python-level query-builder wrapper classes (`.filter()`,
# `.where()`, ...) that return MORE of the same wrapper type, not a raw
# pythonnet collection of LCM objects, so they carry no pythonnet-casting
# hazard for issue #121 to annotate; `tuple[...]` (a single
# `CatalogBackedMixin.FixGuidsAgainstCatalog` method) parameterizes on
# `tuple`, not an LCM interface.
_PARAMETERIZED_COLLECTION_PATTERN = re.compile(
    r"^(?:EnumerableWrapper|list)\[(I[A-Za-z]\w*)\]$"
)


# ---- LibLCM index helpers -----------------------------------------------------

def build_interface_children(liblcm_entities: Dict[str, Any]) -> Dict[str, list]:
    """Build parent -> [children] from each INTERFACE entity's declared
    `interfaces` (its own parent list). A non-empty children list means
    `parent` has at least one derived SIBLING INTERFACE in the LCM
    hierarchy -- i.e. an element typed as `parent` may genuinely be one of
    several distinct interfaces at runtime, the same signal
    build_casting_index.py uses for its
    `polymorphic_collections`/`interface_hierarchy` sections.

    Issue #121 defect 1 (severe false-positive bug): the LibLCM index holds
    BOTH interfaces (`ILexSense`) and their concrete implementing classes
    (`LexSense`) as top-level entities, and every concrete class's own
    `interfaces` list names the interface(s) it implements (e.g.
    `LexSense.interfaces == [..., "ILexSense", ...]`). Scanning ALL
    entities (not just interface-typed ones) therefore made
    `interface_children["ILexSense"] == ["LexSense"]` -- a single
    concrete class implementing an interface is NOT polymorphism, it's
    just "the interface has an implementation" (true of every interface
    in the index). That miscounted "has an implementing class" as "has a
    derived sibling interface", so `is_polymorphic_type()` returned True
    for nearly every LCM interface regardless of whether it actually had
    multiple derived interfaces -- confirmed as the root cause of all 102
    originally-annotated methods coming back `polymorphic: true`,
    including single-implementor properties like `ILexSense` (e.g.
    `LexEntryOperations.GetSenses`/`GetAllSenses`, where `SensesOS` is
    declared directly over `ILexSense` and no other interface can occupy
    that slot).

    Restricting to `entity_data.get("type") == "interface"` on BOTH sides
    (the child being recorded, implicitly the parent being a key some
    interface actually extends) fixes this: `ILexSense` has zero interface
    children (only the single concrete `LexSense` implementor, which is
    filtered out), while genuinely polymorphic interfaces like `ICmObject`
    (196 derived interfaces), `IMoForm` (4: `IMoAffixAllomorph`,
    `IMoAffixForm`, `IMoAffixProcess`, `IMoStemAllomorph`), and
    `IConstituentChartCellPart` (4) are unaffected.
    """
    children: Dict[str, list] = defaultdict(list)
    for entity_name, entity_data in liblcm_entities.items():
        if entity_data.get("type") != "interface":
            continue
        for parent in entity_data.get("interfaces", []) or []:
            children[parent].append(entity_name)
    return children


def build_property_target_map(liblcm_entities: Dict[str, Any]) -> Dict[str, Set[tuple]]:
    """property name -> set of distinct (declaring_entity, target_type)
    pairs declared for that property name across ALL LibLCM entities.

    Property names are NOT globally unique in LibLCM -- e.g. `RowsOS` is
    declared over both `IDsConstChart` (target `IConstChartRow`) and the
    unrelated `ICmFilter` (target `ICmRow`). A single property name can
    therefore map to more than one (declaring_entity, target_type) pair;
    `resolve_element_type()` below disambiguates using the declaring
    flexicon class's own `lcm_dependencies`.
    """
    mapping: Dict[str, Set[tuple]] = defaultdict(set)
    for entity_name, entity_data in liblcm_entities.items():
        for prop in entity_data.get("properties", []) or []:
            name = prop.get("name")
            target_type = prop.get("target_type")
            if name and target_type:
                mapping[name].add((entity_name, target_type))
    return mapping


def load_casting_hierarchy_keys(casting_index: Optional[Dict[str, Any]]) -> Set[str]:
    """Keys of casting_index["interface_hierarchy"], if a casting index was
    supplied. That section only lists a handful of well-known base types
    (see build_casting_index.py's `key_base_types`), so this is a secondary
    signal -- `build_interface_children()` above is the primary, complete
    one -- but it's included per the issue #121 spec so a type flagged by
    the existing casting-index tooling is never missed here even if our
    own LCM-derived children computation somehow disagrees.
    """
    if not casting_index:
        return set()
    return set(casting_index.get(KEY_HIERARCHY, {}).keys())


# ---- Resolution -----------------------------------------------------------

def resolve_element_type(
    prop_name: str,
    lcm_deps: Any,
    property_target_map: Dict[str, Set[tuple]],
) -> Optional[str]:
    """Resolve the LCM target_type for a collection property name.

    Prefers an unambiguous global answer (all LibLCM entities that declare
    this property name agree on its target_type). When they disagree (see
    `build_property_target_map` docstring), disambiguates using the
    declaring flexicon class's own `lcm_dependencies` (the LCM interfaces
    it imports from `SIL.LCModel`), tried two ways:

    1. Match on the property's DECLARING entity -- e.g.
       `ScrDraftOperations` imports `IScrDraft` (the object type its
       `__ResolveObject` helper returns and every docstring names), which
       picks the right `BooksOS` reading (`IScrDraft.BooksOS -> IScrBook`)
       over the unrelated `IScrRefSystem.BooksOS -> IScrBookRef`. This is
       the primary signal: measured against the real flexicon corpus, a
       class overwhelmingly imports the interface of the object it
       resolves/operates on, even for methods that never cast or
       type-check the elements they return.
    2. Match on the target_type itself -- e.g. a method that casts
       returned elements to a concrete subtype (`_GetTypedElements`,
       `cast_to_concrete`) may import that subtype without ever importing
       the property's declaring interface. Secondary signal, tried when
       (1) doesn't narrow it to exactly one candidate.

    If neither narrows it to exactly one candidate, returns None --
    guessing wrong here would be worse than not annotating at all.
    """
    candidates = property_target_map.get(prop_name)
    if not candidates:
        return None

    target_types = {target_type for _entity, target_type in candidates}
    if len(target_types) == 1:
        return next(iter(target_types))

    deps = set(lcm_deps or [])

    by_declaring_entity = {
        target_type for entity, target_type in candidates if entity in deps
    }
    if len(by_declaring_entity) == 1:
        return next(iter(by_declaring_entity))

    by_target_type = target_types & deps
    if len(by_target_type) == 1:
        return next(iter(by_target_type))

    return None


def resolve_element_type_from_return_type(return_type: str) -> Optional[str]:
    """Extract the element type directly from a parameterized behavioral-
    collection `return_type` shape (`EnumerableWrapper[IX]`, `list[IX]`).

    Issue #121 defect 2: `GetAll`-shaped methods (which return every
    instance of a type via a repository, not a `.PropOS` collection
    access) never carry an `element_source_property` -- there is no LCM
    property to trace to. But the element type is already spelled out in
    `return_type` itself, so no LCM bridge lookup is needed at all. See
    `_PARAMETERIZED_COLLECTION_PATTERN` for the survey of which bracketed
    return_type shapes actually occur in the index and why only these two
    qualify.
    """
    if not return_type:
        return None
    match = _PARAMETERIZED_COLLECTION_PATTERN.match(return_type)
    if not match:
        return None
    return match.group(1)


def is_polymorphic_type(
    element_type: str,
    interface_children: Dict[str, list],
    casting_hierarchy_keys: Set[str],
) -> bool:
    """True only when `element_type` is genuinely abstract -- i.e. pythonnet
    hands back a base interface that has real subtypes, so subtype-only
    members require an explicit cast before use.
    """
    if element_type == ABSTRACT_ROOT_INTERFACE:
        return True
    if element_type in casting_hierarchy_keys:
        return True
    if interface_children.get(element_type):
        return True
    return False


# ---- Annotation -----------------------------------------------------------

def annotate_element_types(
    flexicon_data: Dict[str, Any],
    liblcm_data: Dict[str, Any],
    casting_index: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    """Mutate `flexicon_data` in place, adding `element_type` (and
    `polymorphic` when true) to every method whose element type can be
    resolved, via either of two paths (issue #121 defect 2 -- see
    `resolve_element_type_from_return_type` for why a second path was
    needed):

    1. `element_type_hint` -- an explicit, literal concrete-type argument
       flexicon_analyzer.py found alongside the resolved property access
       (the `UnpackNestedPossibilityList(collection, ConcreteType, ...)`
       idiom -- see its docstring). Validated here against the LCM index
       (must be a genuine interface-typed entity) before being trusted;
       tried first because it's a more precise, author-asserted single
       concrete type than the property's own (often intentionally shared
       and abstract) `target_type`.
    2. `element_source_property` -> LibLCM `target_type` (an actual
       property access, cross-checked against the LCM reflection index).
       Tried when (1) is absent or fails validation.
    3. A parameterized behavioral-collection `return_type`
       (`EnumerableWrapper[IX]`/`list[IX]`) -- tried only when neither (1)
       nor (2) resolved, since a property-backed LCM lookup is the more
       authoritative source when available.

    Returns a stats dict covering all three paths plus the polymorphic
    count (see the dict literal below for exact keys).
    """
    liblcm_entities = liblcm_data.get("entities", {})
    property_target_map = build_property_target_map(liblcm_entities)
    interface_children = build_interface_children(liblcm_entities)
    casting_hierarchy_keys = load_casting_hierarchy_keys(casting_index)

    stats = {
        "source_property_candidates": 0,
        "resolved_via_explicit_hint": 0,
        "resolved_via_source_property": 0,
        "return_type_candidates": 0,
        "resolved_via_return_type": 0,
        "resolved": 0,
        "polymorphic": 0,
    }

    for _entity_name, entity in flexicon_data.get("entities", {}).items():
        lcm_deps = entity.get(KEY_LCM_DEPENDENCIES, [])
        for method in entity.get("methods", []):
            element_type = None
            resolution_path = None

            source_prop = method.get(KEY_ELEMENT_SOURCE_PROPERTY)
            if source_prop:
                stats["source_property_candidates"] += 1

                hint = method.get(KEY_ELEMENT_TYPE_HINT)
                if hint and liblcm_entities.get(hint, {}).get("type") == "interface":
                    element_type = hint
                    resolution_path = "resolved_via_explicit_hint"
                else:
                    element_type = resolve_element_type(source_prop, lcm_deps, property_target_map)
                    if element_type:
                        resolution_path = "resolved_via_source_property"

            if not element_type:
                param_type = resolve_element_type_from_return_type(method.get(KEY_RETURN_TYPE, ""))
                if param_type:
                    stats["return_type_candidates"] += 1
                    element_type = param_type
                    resolution_path = "resolved_via_return_type"

            if not element_type:
                continue

            stats["resolved"] += 1
            stats[resolution_path] += 1

            method[KEY_ELEMENT_TYPE] = element_type
            if is_polymorphic_type(element_type, interface_children, casting_hierarchy_keys):
                method[KEY_POLYMORPHIC] = True
                stats["polymorphic"] += 1

    return stats


# ---- CLI --------------------------------------------------------------------

def find_latest_casting_index(index_dir: Path) -> Optional[Path]:
    """Find the latest casting_index_liblcm-v*.json in `index_dir` (it
    lives directly under the index root, not a versioned-API subfolder, so
    it needs its own finder rather than find_latest_versioned_api_file).
    """
    versions = {}
    for file in index_dir.glob("casting_index_liblcm-v*.json"):
        match = _CASTING_INDEX_PATTERN.match(file.name)
        if match:
            versions[match.group(1)] = file
    if not versions:
        return None
    return versions[sorted(versions.keys())[-1]]


def main():
    """Annotate the latest Flexicon index in place and print a summary."""
    index_dir = get_index_dir()
    python_dir = index_dir / "python"
    liblcm_dir = index_dir / "liblcm"

    flexicon_path = find_latest_versioned_api_file(python_dir, "flexicon_api")
    liblcm_path = find_latest_versioned_api_file(liblcm_dir, "liblcm_api")

    if not flexicon_path:
        print("[ERROR] Flexicon API file not found")
        return 1
    if not liblcm_path:
        print("[ERROR] LibLCM API file not found")
        return 1

    casting_index_path = find_latest_casting_index(index_dir)
    casting_index = load_json(casting_index_path) if casting_index_path else None
    if not casting_index_path:
        print("[WARN] No casting index found -- proceeding without the "
              "interface_hierarchy secondary signal (LCM-derived interface "
              "children remain the primary polymorphism check)")

    flexicon_data = load_json(flexicon_path)
    liblcm_data = load_json(liblcm_path)

    print(f"[INFO] Annotating element types in {flexicon_path.name} "
          f"using {liblcm_path.name}")
    stats = annotate_element_types(flexicon_data, liblcm_data, casting_index)

    save_json(flexicon_data, flexicon_path)

    print(f"[OK] Element-type annotation complete for {flexicon_path.name}")
    print(f"     Methods with element_source_property: {stats['source_property_candidates']}")
    print(f"       -> resolved via explicit type-hint argument: {stats['resolved_via_explicit_hint']}")
    print(f"       -> resolved via LCM target_type: {stats['resolved_via_source_property']}")
    print(f"     Methods with a parameterized return_type (EnumerableWrapper[IX]/list[IX]): "
          f"{stats['return_type_candidates']}")
    print(f"       -> resolved via return_type parameter: {stats['resolved_via_return_type']}")
    print(f"     Total resolved element_type: {stats['resolved']}")
    print(f"     Flagged polymorphic: {stats['polymorphic']}")

    return 0


if __name__ == "__main__":
    exit(main())
