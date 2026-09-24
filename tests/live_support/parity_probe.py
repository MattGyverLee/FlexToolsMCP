#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The eligibility-port parity probe (parser-check CP4, T081; Principle VI).

`filing/eligibility.py` is a PORT of two private `HCLoader` predicates. This
probe is its pin: it opens a project READ ONLY, and computes the set of
lexical entries two ways --

  * PORT:   `eligibility.eligible_entries(project)`, the filing gate's view;
  * LOADER: `HCLoader.Load(cache, logger)`, the Language FieldWorks' own
            parser builds, walked for every loaded allomorph's form id
            (`HCParser.FormID` / `FormID2`, both set by the loader on each
            allomorph it accepts) and mapped back to the owning entry.

-- and prints both, and their differences, as one JSON object on stdout.

It runs in its own process (as the parse worker does) so the CLR, the LCM
cache and the grammar never live inside pytest. `HCLoader.Load` builds the
grammar in memory and writes nothing; the project is opened with
`writeEnabled=False`. Run it only against a `CP4-Scratch-` copy (FR-037) --
the caller refuses anything else, and so does this script.

    python tests/live_support/parity_probe.py CP4-Scratch-IndonesianHC-...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[2] / "src"))
sys.path.insert(0, str(_HERE.parent))

from make_disposable import require_disposable  # noqa: E402

#: `HCParser.FormID` and `HCParser.FormID2` (`HCParser.cs:37-38`).
_FORM_KEYS = ("ID", "ID2")


def _collect_form_hvos(language) -> set:
    """Every form hvo the loader attached to an allomorph it accepted."""
    hvos: set = set()

    # pythonnet 3 hands a stratum's rules back typed as the INTERFACE
    # (`IMorphologicalRule`), which has no `Allomorphs`; `__implementation__`
    # is the concrete object. Compounding rules carry no allomorphs and are
    # not an entry's form, so they yield [].
    def allomorphs_of(morpheme):
        concrete = getattr(morpheme, "__implementation__", morpheme)
        allomorphs = getattr(concrete, "Allomorphs", None)
        return list(allomorphs) if allomorphs is not None else []

    def take(allomorph):
        props = allomorph.Properties
        for key in _FORM_KEYS:
            try:
                if props.ContainsKey(key):
                    value = props[key]
                    if value is not None:
                        hvos.add(int(value))
            except Exception:  # noqa: BLE001
                continue

    for stratum in list(language.Strata):
        for entry in list(stratum.Entries):
            for allomorph in allomorphs_of(entry):
                take(allomorph)
        for rule in list(stratum.MorphologicalRules):
            for allomorph in allomorphs_of(rule):
                take(allomorph)
        for template in list(stratum.AffixTemplates):
            for slot in list(template.Slots):
                for rule in list(slot.Rules):
                    for allomorph in allomorphs_of(rule):
                        take(allomorph)
    return hvos


def _logger_class():
    from SIL.FieldWorks.WordWorks.Parser import IHCLoadErrorLogger  # type: ignore[import-not-found]

    class CountingLogger(IHCLoadErrorLogger):
        """Counts load errors; the probe reports them, it does not judge them."""

        __namespace__ = "FlexToolsMCP.ParityProbe"

        def __init__(self):
            super().__init__()
            self.errors = {}

        def _note(self, kind):
            self.errors[kind] = self.errors.get(kind, 0) + 1

        def InvalidShape(self, s, pos, msa):
            self._note("InvalidShape")

        def InvalidAffixProcess(self, ap, lhs, msa):
            self._note("InvalidAffixProcess")

        def InvalidPhoneme(self, ph):
            self._note("InvalidPhoneme")

        def DuplicateGrapheme(self, ph):
            self._note("DuplicateGrapheme")

        def InvalidEnvironment(self, form, env, reason, msa):
            self._note("InvalidEnvironment")

        def InvalidReduplicationForm(self, form, reason, msa):
            self._note("InvalidReduplicationForm")

        def InvalidRewriteRule(self, rule, reason):
            self._note("InvalidRewriteRule")

        def InvalidStrata(self, strata, reason):
            self._note("InvalidStrata")

        def OutOfScopeSlot(self, slot, template, reason):
            self._note("OutOfScopeSlot")

        def UnmatchedReduplicationIndexedClass(self, form, reason, env):
            self._note("UnmatchedReduplicationIndexedClass")

    return CountingLogger


def probe(project_name: str) -> dict:
    require_disposable(project_name)

    from flexicon import FLExCleanup, FLExInitialize, FLExProject

    from flextoolsmcp.server.filing.eligibility import eligible_entries
    from flextoolsmcp.server.parse.worker_main import headless_ui_kwargs

    FLExInitialize()
    project = FLExProject()
    try:
        project.OpenProject(
            projectName=project_name, writeEnabled=False, undoable=False,
            **headless_ui_kwargs(FLExProject),
        )
        port = {e["entry_guid"]: e["headword"] for e in eligible_entries(project)}

        import clr  # type: ignore[import-not-found]

        clr.AddReference("ParserCore")
        from SIL.FieldWorks.WordWorks.Parser import HCLoader  # type: ignore[import-not-found]

        cache = project.project
        logger = _logger_class()()
        language = HCLoader.Load(cache, logger)
        objects = cache.ServiceLocator.ObjectRepository

        loader: dict = {}
        unmapped = 0
        for hvo in _collect_form_hvos(language):
            try:
                owner = objects.GetObject(hvo).Owner
            except Exception:  # noqa: BLE001 -- an id the cache does not know
                owner = None
            guid = getattr(owner, "Guid", None)
            if guid is None:
                unmapped += 1
                continue
            loader[str(guid).lower()] = port.get(str(guid).lower(), "")

        port_only = sorted(set(port) - set(loader))
        loader_only = sorted(set(loader) - set(port))
        return {
            "project": project_name,
            "port_count": len(port),
            "loader_count": len(loader),
            "port_only": [{"entry_guid": g, "headword": port[g]} for g in port_only],
            "loader_only": loader_only,
            "unmapped_form_ids": unmapped,
            "load_errors": dict(logger.errors),
            "agree": not port_only and not loader_only,
        }
    finally:
        try:
            project.CloseProject()
        finally:
            FLExCleanup()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: parity_probe.py <CP4-Scratch-project>", file=sys.stderr)
        return 2
    # ASCII-escaped: the console codepage (cp1252) cannot carry headwords.
    print(json.dumps(probe(argv[0])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
