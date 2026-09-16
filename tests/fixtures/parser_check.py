#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared CP1 test fixtures for the parser-check feature
(specs/parser-check/SPEC.md, specs/parser-check/contracts/error-codes.md).

Everything here is a **plain Python stand-in** -- no live FieldWorks, no
pythonnet, no `LcmCache`. CP1 only reflects into `ParserCore.dll` and reads
raw LCM grammar objects (SPEC 5.4, 9.5.4/9.5.5); none of that needs a real
FieldWorks install to exercise the *logic* that consumes these shapes, so
the fixtures model exactly the attributes that logic will read and nothing
more.

Three groups:

1. **Fake ParserCore member sets** (`*_PARSER_CORE`) -- SPEC 5.4's
   capability probe binds positionally (never by keyword: `IParser` names
   these params ``word``, `HCParser` implements them as ``form``) against
   the enumerated set ``HCParser(LcmCache)``, ``Update()``,
   ``ParseWord(string)``, ``TraceWordXml(string, IEnumerable<int>)``,
   ``ParseWordXml(string)``, plus (spine 2 only) ``ParseFiler.ProcessParse``.
   Modeled as a `FakeParserCoreLocation` pairing a `frozenset[str]` of member
   names with the directory ParserCore.dll and SIL.LCModel.dll would each be
   reflected from, matching the closed `signal` enum on `parser_core_missing`
   (contracts/error-codes.md): ``incompatible_surface`` (a member absent) and
   ``foreign_install`` (both present, directories differ) are the two this
   module ships.

2. **`ParserParameters` XML variants** -- accepted `ActiveParser` values are
   exactly ``"XAmple"`` and ``"HC"``, case-sensitive; the getter defaults to
   ``"XAmple"`` on any parse failure, so a corrupt value reads as XAmple and
   callers refuse -- fail-safe, never silently HC (SPEC.md:672-680,
   contracts/error-codes.md `parser_engine_mismatch`). The XML shape below
   (a ``<HC>``/``<XAmple>`` element nested under ``<ParserParameters>``) is
   modeled on the one confirmed fragment in SPEC.md:1493
   (``<HC><MaxRoots>...``) and is illustrative, not independently verified
   against FieldWorks source -- only the three-way distinction (valid HC /
   valid XAmple / corrupt-reads-as-XAmple) is contractually load-bearing at
   CP1.

3. **LCM grammar-object stubs** -- `IMoForm`, `IPhPhoneme`,
   `IMoInflAffixSlot`, `IPhSegmentRule`, restricted to the properties CP1's
   scan (SPEC 9.5.4, research.md D4) actually reads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional


# ---------------------------------------------------------------------------
# 1. Fake ParserCore member sets (SPEC 5.4)
# ---------------------------------------------------------------------------

# Bound positionally -- names below are documentation only, not keywords.
HCPARSER_MEMBERS: tuple = (
    "HCParser(LcmCache)",                        # ctor -- HCParser.cs:50
    "Update()",                                  # HCParser.cs:67
    "ParseWord(string)",                         # HCParser.cs:84 -> ParseResult
    "TraceWordXml(string, IEnumerable<int>)",    # HCParser.cs:120 -> XDocument
    "ParseWordXml(string)",                      # HCParser.cs:127 -> XDocument
)
PARSE_FILER_MEMBERS: tuple = (
    "ParseFiler.ProcessParse",                   # spine 2 only, SPEC.md:425
)

COMPLETE_PARSER_CORE_MEMBERS: FrozenSet[str] = frozenset(HCPARSER_MEMBERS + PARSE_FILER_MEMBERS)
"""Every bound member SPEC 5.4 enumerates, `HCParser` plus `ParseFiler`."""

MISSING_PROCESS_PARSE_MEMBERS: FrozenSet[str] = frozenset(HCPARSER_MEMBERS)
"""`HCParser` fully present; `ParseFiler.ProcessParse` absent (`incompatible_surface`)."""


@dataclass(frozen=True)
class FakeParserCoreLocation:
    """A reflectively-resolved ParserCore.dll, paired with the members it
    would report present and the directory it (and SIL.LCModel.dll) were
    each loaded from.

    `same_install` mirrors the check behind the `foreign_install` signal
    (contracts/error-codes.md `parser_core_missing`): "ParserCore.dll must
    come from the same FieldWorks install as `SIL.LCModel.dll`... a
    ParserCore from a different install is refused."
    """

    members: FrozenSet[str]
    parser_core_dir: str
    lcmodel_dir: str

    @property
    def same_install(self) -> bool:
        return self.parser_core_dir == self.lcmodel_dir


COMPLETE_SAME_INSTALL_PARSER_CORE = FakeParserCoreLocation(
    members=COMPLETE_PARSER_CORE_MEMBERS,
    parser_core_dir=r"C:\Program Files\SIL\FieldWorks 9\ParserCore.dll",
    lcmodel_dir=r"C:\Program Files\SIL\FieldWorks 9\SIL.LCModel.dll",
)
"""Healthy baseline: full surface, resolved alongside SIL.LCModel.dll."""

MISSING_PROCESS_PARSE_PARSER_CORE = FakeParserCoreLocation(
    members=MISSING_PROCESS_PARSE_MEMBERS,
    parser_core_dir=r"C:\Program Files\SIL\FieldWorks 9\ParserCore.dll",
    lcmodel_dir=r"C:\Program Files\SIL\FieldWorks 9\SIL.LCModel.dll",
)
"""`signal=incompatible_surface`: same install, `ParseFiler.ProcessParse` absent."""

FOREIGN_DIRECTORY_PARSER_CORE = FakeParserCoreLocation(
    members=COMPLETE_PARSER_CORE_MEMBERS,
    parser_core_dir=r"C:\Program Files\SIL\FieldWorks 8\ParserCore.dll",
    lcmodel_dir=r"C:\Program Files\SIL\FieldWorks 9\SIL.LCModel.dll",
)
"""`signal=foreign_install`: full surface, but resolved from a different
FieldWorks install than the one supplying `SIL.LCModel.dll`."""


# ---------------------------------------------------------------------------
# 2. ParserParameters XML variants
# ---------------------------------------------------------------------------

PARSER_PARAMETERS_XML_HC = """<ParserParameters>
  <HC>
    <MaxRoots>2</MaxRoots>
    <DelReapps>0</DelReapps>
    <MergeAnalyses>true</MergeAnalyses>
  </HC>
</ParserParameters>"""
"""Valid, well-formed -- `ActiveParser == "HC"`."""

PARSER_PARAMETERS_XML_XAMPLE = """<ParserParameters>
  <XAmple>
    <MorphNamesPath>Grammar\\MorphNames.xml</MorphNamesPath>
  </XAmple>
</ParserParameters>"""
"""Valid, well-formed -- `ActiveParser == "XAmple"`."""

PARSER_PARAMETERS_XML_CORRUPT = "<ParserParameters><HC><MaxRoots>2</MaxRoots>"
"""Deliberately not well-formed (unterminated elements). Per SPEC.md:678 and
contracts/error-codes.md, the getter defaults to `"XAmple"` on any parse
failure -- a corrupt value must read as XAmple and refuse, fail-safe, never
silently HC. A test asserting on this fixture asserts the resolved engine
is `"XAmple"`, not that parsing raises."""


# ---------------------------------------------------------------------------
# 3. LCM grammar-object stubs (SPEC 9.5.4, research.md D4)
# ---------------------------------------------------------------------------

@dataclass
class FakeIMoForm:
    """Stand-in for `IMoForm`. `.Form` mirrors the real `IMultiUnicode`
    property (research.md D4 row 1). Values are plain `str`/`None` since the
    emptiness predicate under test is `form in (None, "", "***")` -- read
    directly off LCM on this path, which does **not** get Flexicon's
    Operations-layer `"***"` -> `""` normalization (CLAUDE.md, tasks.md T033).
    """

    Form: Optional[str]


def fake_imoform_triple_star() -> FakeIMoForm:
    """Zero-surface via the FLEx multistring "no value" placeholder."""
    return FakeIMoForm(Form="***")


def fake_imoform_none() -> FakeIMoForm:
    """Zero-surface: `Form` is `None`."""
    return FakeIMoForm(Form=None)


def fake_imoform_empty() -> FakeIMoForm:
    """Zero-surface: `Form` is the empty string."""
    return FakeIMoForm(Form="")


def fake_imoform_real(surface: str = "kal") -> FakeIMoForm:
    """Non-empty surface -- must never be counted as zero-surface."""
    return FakeIMoForm(Form=surface)


@dataclass
class FakeIPhPhoneme:
    """Stand-in for `IPhPhoneme`. `CodesOS` (inherited from
    `IPhTerminalUnit`) and `FeaturesOA` are the two properties research.md
    D4 marks VERIFIED (rows 2 and 9 respectively). Both require a pythonnet
    cast on a real LCM object; irrelevant here since this is a plain stub.
    """

    CodesOS: List[object] = field(default_factory=list)
    FeaturesOA: Optional[object] = None


def fake_iphphoneme(codes: Optional[List[object]] = None, features: Optional[object] = None) -> FakeIPhPhoneme:
    return FakeIPhPhoneme(CodesOS=list(codes) if codes is not None else [], FeaturesOA=features)


@dataclass
class FakeIMoInflAffixSlot:
    """Stand-in for `IMoInflAffixSlot` (research.md D4 row 10, VERIFIED).

    NOT an `ICmPossibility` -- its base is `CmObject` (`MasterLCModel.xml`),
    and its own `Name` is its own `IMultiUnicode`. Casting `ICmPossibility(obj)`
    on one of these is wrong (the index warns explicitly); this stub
    deliberately carries no `Name` so a test that mistakenly performs the
    `ICmPossibility` cast fails loudly (`AttributeError`) rather than
    silently reading the wrong field.
    """

    Optional: bool
    Affixes: List[object] = field(default_factory=list)


def fake_imoinflaffixslot(optional: bool = True, affixes: Optional[List[object]] = None) -> FakeIMoInflAffixSlot:
    return FakeIMoInflAffixSlot(Optional=optional, Affixes=list(affixes) if affixes is not None else [])


@dataclass
class FakeIPhSegmentRule:
    """Stand-in for `IPhSegmentRule`. `Disabled` must gate every rule-based
    check (research.md D4; data-model.md:123): a disabled rule contributes
    nothing to path multiplication and must never be counted.
    """

    Disabled: bool = False


def fake_iphsegmentrule(disabled: bool = False) -> FakeIPhSegmentRule:
    return FakeIPhSegmentRule(Disabled=disabled)
