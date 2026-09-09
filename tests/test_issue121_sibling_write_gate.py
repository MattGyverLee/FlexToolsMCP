#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Issue #121 sibling bug (pattern-audit finding, bug 1 of 2): write-gate
BYPASS in `find_protected_ranges` / `ProtectionFinder`.

Same bug *class* as #121 (a conclusion about user code drawn from syntax
alone, with no dataflow): `_is_write_enabled_check` and `_is_modify_enabled`
matched an attribute purely by NAME (`.writeEnabled`, `.modifyEnabled`)
without checking who the receiver actually was. An unrelated local object
that happens to have an attribute spelled the same way
(`cfg.writeEnabled = True`) was accepted as a guard, certifying a real
mutation as read-only.

Fix: both checks now route through `_is_project_receiver`, which only
accepts a bare `project` name or `self.project` as the receiver.

Covers:
  - The exact verbatim bypass input from the audit (`cfg.writeEnabled`),
    for both `find_protected_ranges` directly and `certify_script_readonly`
    end-to-end.
  - The documented idioms that must keep working: bare `modifyAllowed`,
    `project.writeEnabled`, `self.project.writeEnabled`,
    `with project.modifyEnabled:`, `with self.project.modifyEnabled:`.
  - The same receiver-blind flaw in the `with`-form (`_is_modify_enabled`),
    which the audit flagged as a "check whether it has the same flaw"
    candidate -- confirmed it did, fixed the same way.
"""

import sys

sys.path.insert(0, "src")

from flextoolsmcp.server.validators import (  # noqa: E402
    certify_script_readonly,
    find_protected_ranges,
)


# ---------------------------------------------------------------------------
# Bug 1: write-gate bypass via receiver-blind attribute matching
# ---------------------------------------------------------------------------

class TestWriteGateBypassClosed:
    def test_unrelated_object_writeEnabled_attribute_not_protected(self):
        """Verbatim audit input: cfg.writeEnabled must NOT protect a mutation."""
        code = (
            "class C:\n"
            "    pass\n"
            "\n"
            "cfg = C(); cfg.writeEnabled = True\n"
            "if cfg.writeEnabled:\n"
            "    project.LexEntry.Create(\"x\")\n"
        )
        assert find_protected_ranges(code) == []

    def test_unrelated_object_writeEnabled_certify_not_readonly(self):
        """End-to-end: certify_script_readonly must reject, not certify readonly."""
        code = (
            "class C:\n"
            "    pass\n"
            "\n"
            "cfg = C(); cfg.writeEnabled = True\n"
            "if cfg.writeEnabled:\n"
            "    project.LexEntry.Create(\"x\")\n"
        )
        result = certify_script_readonly(code, api_index=None)
        assert result["is_certified_readonly"] is False
        assert result["mutating_calls"] == []  # regex/raw-LCM path, not index path
        assert len(result["unprotected_liblcm_calls"]) == 1
        assert result["protected_liblcm_calls"] == []

    def test_unrelated_object_modifyEnabled_with_form_not_protected(self):
        """Same receiver-blind flaw, `with`-form (_is_modify_enabled)."""
        code = (
            "cfg = object()\n"
            "cfg.modifyEnabled = True\n"
            "with cfg.modifyEnabled:\n"
            "    project.LexEntry.Create(\"x\")\n"
        )
        assert find_protected_ranges(code) == []

    def test_other_named_receiver_writeEnabled_not_protected(self):
        """A second unrelated-receiver spelling ('opts'), per the audit note."""
        code = (
            "opts = object()\n"
            "opts.writeEnabled = True\n"
            "if opts.writeEnabled:\n"
            "    project.LexEntry.Create(\"x\")\n"
        )
        assert find_protected_ranges(code) == []


# ---------------------------------------------------------------------------
# Legitimate idioms must keep protecting (regression guard for the fix itself)
# ---------------------------------------------------------------------------

class TestLegitimateGuardIdiomsStillProtect:
    def test_bare_modifyAllowed_still_protects(self):
        """THE canonical FLExTools guard (see CLAUDE.md's module template)."""
        code = (
            "def Main(project, report, modifyAllowed):\n"
            "    if modifyAllowed:\n"
            "        project.LexEntry.Create(\"x\")\n"
        )
        ranges = find_protected_ranges(code)
        assert ranges == [(2, 3)]

    def test_project_writeEnabled_still_protects(self):
        code = (
            "if project.writeEnabled:\n"
            "    project.LexEntry.Create(\"x\")\n"
        )
        assert find_protected_ranges(code) == [(1, 2)]

    def test_self_project_writeEnabled_still_protects(self):
        code = (
            "class Foo:\n"
            "    def run(self):\n"
            "        if self.project.writeEnabled:\n"
            "            self.project.LexEntry.Create(\"x\")\n"
        )
        assert find_protected_ranges(code) == [(3, 4)]

    def test_project_writeEnabled_compare_form_still_protects(self):
        code = (
            "if project.writeEnabled == True:\n"
            "    project.LexEntry.Create(\"x\")\n"
        )
        assert find_protected_ranges(code) == [(1, 2)]

    def test_with_project_modifyEnabled_still_protects(self):
        code = (
            "with project.modifyEnabled:\n"
            "    project.LexEntry.Create(\"x\")\n"
        )
        assert find_protected_ranges(code) == [(1, 2)]

    def test_with_self_project_modifyEnabled_still_protects(self):
        code = (
            "class Foo:\n"
            "    def run(self):\n"
            "        with self.project.modifyEnabled:\n"
            "            self.project.LexEntry.Create(\"x\")\n"
        )
        assert find_protected_ranges(code) == [(3, 4)]

    def test_certify_readonly_still_certifies_properly_guarded_mutation(self):
        """End-to-end sanity: a genuinely guarded mutation is still certified
        read-only (not over-corrected into rejecting everything)."""
        code = (
            "if project.writeEnabled:\n"
            "    project.LexEntry.Create(\"x\")\n"
        )
        result = certify_script_readonly(code, api_index=None)
        assert result["is_certified_readonly"] is True
        assert result["unprotected_liblcm_calls"] == []
        assert len(result["protected_liblcm_calls"]) == 1
