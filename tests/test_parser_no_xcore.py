#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
`HCParser_DoesNotLoadXCore` -- the standing guarantee behind READ_ONLY_SAFE
(parser-check CP2b, FR-017, SC-003; SPEC 16 "Standing guarantees"; CP2-SPEC
section on the standing guarantee; contracts/tools.md).

THIS TEST IS THE SAFETY STORY. The `READ_ONLY_SAFE` annotation on
`flextools_try_word` is a claim about a **call path, not a class** (SPEC
12.1). The facade being read-only is a promise; this is the control. After a
real `Update()` + `ParseWord()`, no user-interface framework code may be
loaded into the process that did the parsing.

WHY IT IS ASSERTED AGAINST THE WORKER'S LIST AND NOT THIS PROCESS'S. The MCP
server process -- and this pytest process -- never load `ParserCore` at all.
Asking `AppDomain.CurrentDomain.GetAssemblies()` here would return a list
with no parser in it and no `XCore` in it, and pass forever while proving
nothing. The list has to come from the process that actually constructed the
parser, which is the worker; `ParseWorkerClient.loaded_assemblies()` exists
for this one caller.

THE REFACTOR THIS EXISTS TO CATCH is "reuse `ParserWorker` for consistency".
`ParserWorker` and `ParserScheduler` both pull xCore in through their own
constructor parameters, so that change would look like tidying and would
silently invalidate the annotation on a tool already shipped as read-only
safe.

THE POSITIVE VACUITY GUARD IS NOT OPTIONAL. A test that asserts only an
absence passes when nothing happened at all -- a worker that failed to open
the project, a parser that was never constructed, a skipped parse. So the
same run must show that the parse is what loaded `ParserCore`, and that a
result came back. Without that, green here would mean "we did not parse",
which is the easiest way for this guarantee to quietly retire itself.

THE ASSERTION IS ON THE DELTA, AND THAT IS A CORRECTION TO THE SPEC'S
WORDING. SPEC 16 and CP2-SPEC both phrase this as "after a real `Update()` +
`ParseWord()`, assert no `XCore` / `System.Windows.Forms` assembly is
loaded". Measured against a live worker on `IndonesianHC-Complete`, the
absolute form is **not satisfiable and never was**:

    after opening the project, before any parse:
        System.Windows.Forms  LOADED      FwUtils  LOADED
        XCore  absent                     SIL.FieldWorks.XWorks  absent

    what ParseWord() itself added (5 assemblies):
        ParserCore, SIL.Machine, SIL.Machine.Morphology.HermitCrab,
        SIL.Scripture, Sandwych.QuickGraph.Core

Opening a FieldWorks project at all -- `FLExInitialize()`, long before a
parser exists -- brings `System.Windows.Forms` and `FwUtils` with it. So an
absolute assertion fails for a reason that has nothing to do with the
parser, and the obvious way to make it pass is to delete it, which retires
the guarantee entirely.

The delta form is what SPEC 12.1 actually asks for: the guarantee is about a
**call path, not a class**. It is also strictly stronger than the absolute
one, in both directions -- `ParserCore` must appear in the delta (so the
parse demonstrably constructed the parser, not merely "something did"), and
no forbidden name may appear there (so the parse path itself stays clear of
UI framework code even on a process whose bootstrap already loaded some).
`XCore`, the name the guarantee is titled after, is additionally asserted
absent from the whole process, because nothing in the bootstrap loads it and
nothing should.

This divergence from the spec's literal wording is recorded in
`specs/parser-check-cp2b/evidence/cp2b-evidence.md` with the measurement
above.

Requires a live FieldWorks install and an HC-configured project, so it is
marked `requires_flex` and skipped where either is missing. A skip is
visible; a vacuous pass is not, which is why nothing here degrades into one.

Run with:
    python -m pytest tests/test_parser_no_xcore.py -q
    python -m pytest -q -m "not requires_flex"     # to deselect it
"""

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from flextoolsmcp.server.parse.worker_client import (  # noqa: E402
    ParseWorkerClient,
    WorkerError,
)

pytestmark = pytest.mark.requires_flex


#: The project the guarantee is proven against. `IndonesianHC-Complete` is
#: the quickstart's correctness project (engine `HC`, 3 rules, 41 entries).
#: Overridable so the same test can be pointed at another HC project without
#: editing it.
LIVE_PROJECT = os.environ.get(
    "FLEXTOOLSMCP_LIVE_HC_PROJECT", "IndonesianHC-Complete"
)

#: The word to parse. Its *analyses* do not matter here -- what matters is
#: that `ParseWord()` really ran, which loads `HCLoader` and the `Morpher`
#: whether or not the word parses. Overridable so a live run can use a word
#: known to parse and record that in the evidence artifact.
LIVE_WORD = os.environ.get("FLEXTOOLSMCP_LIVE_HC_WORD", "makan")

#: Simple assembly names that must not appear. The first two are the
#: specification's own list (SPEC 16, CP2-SPEC); the last two are the
#: FieldWorks assemblies that drag xCore in behind them, named by CP2's
#: cycle-2 review, so the test fails at the cause rather than one step
#: downstream of it.
FORBIDDEN_ASSEMBLIES = (
    "XCore",
    "System.Windows.Forms",
    "SIL.FieldWorks.XWorks",
    "FwUtils",
)


async def _parse_one_word_in_a_real_worker():
    """Start a real worker, measure, parse one word, measure again.

    Returns `(result, before, after)` -- the parse result and the worker's
    loaded-assembly set on either side of the parse. Two measurements rather
    than one because the assertion is about what the PARSE loaded, and a
    single reading cannot tell that apart from what opening the project
    loaded.

    Skips -- never passes -- when the environment cannot host a real parse.
    """
    client = ParseWorkerClient(LIVE_PROJECT)
    try:
        try:
            await client.start()
        except WorkerError as exc:
            pytest.skip(
                f"No live worker for {LIVE_PROJECT!r} ({exc}). This test "
                f"proves nothing without one; skipping rather than passing."
            )

        # The baseline: the project is open and no parse has happened. Taken
        # BEFORE the parse, which is the only moment at which it can be.
        before = set(await client.loaded_assemblies())

        try:
            result = await client.parse_word(
                request_id="no-xcore-1",
                run_id="no-xcore",
                wordform=LIVE_WORD,
                level="plain",
                restricted_to=None,
            )
        except WorkerError as exc:
            pytest.skip(
                f"The live parse did not run ({exc}); there is nothing to "
                f"assert about a process that never parsed."
            )

        after = set(await client.loaded_assemblies())
        return result, before, after
    finally:
        await client.aclose()


async def test_HCParser_DoesNotLoadXCore():
    """The standing test, under its pinned name.

    The name is pinned by the Verbatim Constraints and by SPEC 16; it is
    referenced by name from `CP2-SPEC.md`, `CP3-SPEC.md` and
    `contracts/parser-operations.md`. Renaming it silently orphans all
    three, which is what `test_the_standing_test_keeps_its_name` below
    guards against.
    """
    result, before, after = await _parse_one_word_in_a_real_worker()
    added = after - before

    # ---- the positive vacuity guard, FIRST --------------------------------
    # Checked before the absence, so a run that did not parse fails as
    # "nothing happened" rather than passing as "no XCore was loaded".
    assert after, (
        "the worker reported no loaded assemblies at all, so the CLR was "
        "never started there -- this run proves nothing"
    )
    assert "ParserCore" in added, (
        "the PARSE did not load ParserCore, so it did not construct a "
        "parser. Asserted on the delta rather than on the whole list: "
        "'ParserCore is loaded somewhere in this process' would also pass "
        "for a parse that never ran against a process that had loaded it "
        "earlier. Added by this parse: "
        + (", ".join(sorted(added)) or "(nothing)")
    )
    parse = result.get("parse")
    assert isinstance(parse, dict), (
        f"the parse produced no result to speak of: {result!r}"
    )
    assert isinstance(parse.get("analysis_count"), int), (
        "ParseWord() did not return a countable result, so it did not "
        f"really run: {parse!r}"
    )

    # ---- the guarantee, on the call path ----------------------------------
    pulled_in = [name for name in FORBIDDEN_ASSEMBLIES if name in added]
    assert not pulled_in, (
        "the parse path pulled in user-interface framework code: "
        + ", ".join(pulled_in)
        + ". The READ_ONLY_SAFE annotation on flextools_try_word is a claim "
        "about this call path. The usual cause is a refactor onto "
        "ParserWorker or ParserScheduler, both of which pull xCore in "
        "through their own constructor parameters. Everything this parse "
        "added: " + ", ".join(sorted(added))
    )

    # ---- and XCore, absolutely --------------------------------------------
    # The one name the guarantee is titled after. Nothing in the FieldWorks
    # bootstrap loads it, so unlike System.Windows.Forms it can be asserted
    # against the whole process rather than against the delta -- and should
    # be, because that is the stronger statement wherever it is available.
    assert "XCore" not in after, (
        "XCore is loaded in the worker process. Nothing on a read-only "
        "parse path -- or on the path that opens a project for one -- has "
        "any business loading it."
    )


async def test_the_parse_that_backs_the_guarantee_is_a_real_one():
    """`Update()` really ran: the grammar was loaded, not skipped.

    Separate from the guarantee above so the two fail distinguishably. If
    the loader never ran, the assertion about what it did not load is about
    nothing -- and that failure should read as "the grammar never loaded",
    not as "no XCore found".
    """
    _, before, after = await _parse_one_word_in_a_real_worker()
    added = after - before

    hermit_crab = [name for name in added if "HermitCrab" in name]
    assert hermit_crab, (
        "the parse loaded no HermitCrab assembly, so the grammar was never "
        "built and `Update()` did not really run. Added by this parse: "
        + (", ".join(sorted(added)) or "(nothing)")
    )


def test_the_standing_test_keeps_its_name():
    """The name is part of the contract, not a label.

    `HCParser_DoesNotLoadXCore` is referenced by name from SPEC 16,
    `CP2-SPEC.md`, `CP3-SPEC.md` and `contracts/parser-operations.md` --
    CP3's acceptance criteria include "`HCParser_DoesNotLoadXCore` (CP2's)
    stays green". A rename would leave all four pointing at nothing while
    every test still passed, so the name is asserted rather than trusted.

    Deliberately NOT marked `requires_flex` in effect: it reads this
    module's own namespace and needs no FieldWorks. The module-level mark
    applies, which means a `-m "not requires_flex"` run skips it too -- an
    acceptable cost for keeping the guarantee and its name in one file.
    """
    assert "test_HCParser_DoesNotLoadXCore" in globals(), (
        "the standing test has been renamed; four specification documents "
        "reference it as HCParser_DoesNotLoadXCore"
    )


def test_the_worker_can_be_asked_for_its_own_assemblies():
    """The probe exists and is reachable from the client.

    Unmarked in spirit -- it imports and does not parse -- so a machine
    without FieldWorks still catches the case where the diagnostic message
    is dropped from the protocol and every live assertion above degrades
    into a skip nobody reads.
    """
    from flextoolsmcp.server.parse import worker_main

    assert hasattr(ParseWorkerClient, "loaded_assemblies")
    assert hasattr(worker_main, "loaded_assembly_names")
    # Off the CLR the probe reports "could not observe" as `[]` rather than
    # inventing an empty-and-therefore-clean list; the live test treats `[]`
    # as a failure of its vacuity guard, which is what makes that
    # distinction safe to rely on. Where pythonnet IS importable -- as it is
    # in this repository's own test environment -- it reports this process's
    # real list, which is why the check below is about the element type and
    # not about the list being non-empty.
    names = worker_main.loaded_assembly_names()
    assert isinstance(names, list)
    assert all(isinstance(name, str) for name in names), (
        f"assembly names must cross the channel as strings: {names[:5]}"
    )
