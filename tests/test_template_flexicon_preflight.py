"""CP4 -- the flexicon template's environment pre-flight.

Spec: specs/flexicon-project-bridge (US5, tasks T023-T025)
Contract: specs/flexicon-project-bridge/contracts/from-open-project.md section 8

WHY THIS EXISTS
    SPEC 3d makes ``from flexicon import FLExProject`` load-bearing for the first
    time, so an emitted module now depends on whatever Python environment the
    user's FlexTools install happens to have. Two environment failures become
    possible, and neither reads as one:

      * ``pyflexicon`` absent      -> ImportError traceback at module load,
                                      before Main() runs
      * ``pyflexicon`` pre-bridge  -> imports cleanly, then dies on the first
                                      line of Main() with "type object
                                      'FLExProject' has no attribute
                                      'FromOpenProject'"

    Both are this feature's own failure class one layer out: the user cannot
    tell an environment problem from a bug in their module.

HOW IT TESTS
    No FieldWorks, and flexicon is never uninstalled. The template is loaded as
    SOURCE and exec'd into a throwaway namespace; because the helper reads its
    module globals, swapping ``ns["_flexicon"]`` / ``ns["FLExProject"]`` is
    enough to stand in either failure.

    The exec runs against a STUB ``flexicon`` installed in ``sys.modules`` for
    its duration, not the real package -- which is what actually keeps the file
    runnable in a bare checkout. It has to be a stub, because "flexicon is
    importable here" is not true even on a machine that has pyflexicon
    installed: without FieldWorks, ``import flexicon`` raises a bare
    ``Exception("64bit FieldWorks 9 not found")``. That is not an ImportError,
    so the template's guard does not catch it and it came straight back out of
    the exec -- every test in this file failed on the Windows CI runner for a
    reason that had nothing to do with the pre-flight.

    The stub is used unconditionally rather than only as a fallback, so a pass
    on a dev machine means the same thing as a pass on the runner.
    ``test_the_stub_matches_what_the_template_actually_imports`` keeps the stub
    from drifting away from the real package, and skips where flexicon cannot
    be imported.

    Deliberately NO marker -- neither ``requires_live_project`` (the pre-flight
    opens nothing) nor ``requires_flex`` (nothing here needs FieldWorks any
    more, which is the point of the stub).
"""

import json
import re
import sys
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _template_source():
    """The flexicon template exactly as the MCP would emit it."""
    from flextoolsmcp.server.handlers.admin import handle_get_module_template

    try:
        from tests.test_mcp_tools import run_async
    except ImportError:  # pragma: no cover - direct pytest invocation
        from test_mcp_tools import run_async

    result = run_async(handle_get_module_template({"flavor": "flexicon"}))
    payload = json.loads(result[0].text)
    assert payload.get("status") == "success", payload
    return payload["template"]


def _template_path():
    from flextoolsmcp.file_utils import get_bundled_templates_dir

    return Path(get_bundled_templates_dir()) / "2-flexicon-template.py"


#: Every name the template's ``from flexicon import (...)`` list asks for.
#: Kept in one place because both the stub and the drift check need it.
TEMPLATE_IMPORTS = (
    "FLExProject",
    "LexEntryOperations",
    "LexSenseOperations",
    "LexReferenceOperations",
    "WritingSystemOperations",
)


def _flexicon_stub(version="4.7.0", names=TEMPLATE_IMPORTS):
    """A module object that satisfies the template's import list.

    Deliberately NOT a package: with no ``__path__``, a name the stub does not
    carry produces the real ImportError CPython would raise for a bad name in
    a ``from flexicon import (...)`` list, which is what the bad-symbol tests
    need. Nothing here is called -- the pre-flight only ever probes
    ``hasattr(FLExProject, "FromOpenProject")``.
    """
    mod = types.ModuleType("flexicon")
    mod.__file__ = "<flexicon stub for tests>"
    mod.version = version
    for name in names:
        setattr(mod, name, type(str(name), (), {}))
    # The default exec should land in a *working* environment, so the bridge
    # has to be present; tests that want it missing swap FLExProject after.
    if "FLExProject" in names:
        mod.FLExProject = _CurrentFLExProject
    return mod


@contextmanager
def _stubbed_flexicon(**kwargs):
    """Install the stub as ``flexicon`` for the duration of the block."""
    saved = sys.modules.get("flexicon")
    sys.modules["flexicon"] = _flexicon_stub(**kwargs)
    try:
        yield sys.modules["flexicon"]
    finally:
        if saved is None:
            del sys.modules["flexicon"]
        else:
            sys.modules["flexicon"] = saved


def _exec_template(src, module_name="_flexicon_template_under_test"):
    """exec template source against the stub and hand back its namespace."""
    ns: "dict[str, Any]" = {"__name__": module_name}
    with _stubbed_flexicon():
        exec(compile(src, "2-flexicon-template.py", "exec"), ns)
    return ns


def _load_namespace():
    """exec the emitted template into a fresh namespace and hand it back.

    The import machinery really runs; only the package behind it is a stub (see
    HOW IT TESTS). Individual tests then overwrite the module globals they need
    in order to stand in an environment we do not have.
    """
    return _exec_template(_template_source())


class _FakeReport:
    """Records every call, so "said nothing" is assertable."""

    def __init__(self):
        self.calls = []

    def _record(self, kind):
        def f(msg, ref=None):
            self.calls.append((kind, msg, ref))

        return f

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._record(name)

    @property
    def text(self):
        return "\n".join(str(m) for _, m, _ in self.calls)


class _ExplodingMeta(type):
    """Attribute lookup on the class raises something hasattr will NOT swallow."""

    def __getattr__(cls, name):
        raise RuntimeError("probe exploded: %s" % name)


class _ExplodingFLExProject(metaclass=_ExplodingMeta):
    pass


class _BridgelessFLExProject:
    """A pre-bridge flexicon: imports fine, but has no FromOpenProject."""


class _CurrentFLExProject:
    @classmethod
    def FromOpenProject(cls, donor):  # noqa: N802 - mirrors the real API
        return donor


class _FakeFlexiconModule:
    def __init__(self, version: object = "4.6.0"):
        self.version = version


# ---------------------------------------------------------------------------
# T4.1 -- the template wires the pre-flight in
# ---------------------------------------------------------------------------

class TestPreflightIsWiredIn(unittest.TestCase):

    def test_t4_1a_template_defines_and_calls_preflight_first(self):
        src = _template_source()

        self.assertIn(
            "_flexicon_preflight", src,
            "The emitted flexicon template must carry the pre-flight helper; "
            "without it a stale or absent pyflexicon surfaces as a raw "
            "AttributeError/ImportError traceback (spec.md CP4).",
        )

        match = re.search(r"^def Main\(.*?\):\n(.*?)(?=\n\S)", src, re.S | re.M)
        self.assertIsNotNone(match, "Could not locate Main() in the template.")
        body = match.group(1)

        # First *statement*, skipping the docstring and blank/comment lines.
        lines = [ln for ln in body.splitlines() if ln.strip()]
        self.assertTrue(lines, "Main() body is empty.")

        idx = 0
        if lines[0].lstrip().startswith(('"""', "'''")):
            quote = lines[0].lstrip()[:3]
            # A one-line docstring opens and closes on the same line.
            if lines[0].lstrip().count(quote) >= 2 and len(lines[0].lstrip()) > 3:
                idx = 1
            else:
                idx = 1
                while idx < len(lines) and quote not in lines[idx]:
                    idx += 1
                idx += 1
        while idx < len(lines) and lines[idx].lstrip().startswith("#"):
            idx += 1

        self.assertLess(idx, len(lines), "Main() has no executable statement.")
        first = lines[idx].strip()
        self.assertIn(
            "_flexicon_preflight", first,
            "The pre-flight must be the FIRST statement of Main(), so a bad "
            "environment is reported before any project work is attempted. "
            "Found instead: %r" % first,
        )
        # The guard must short-circuit Main(). Two spellings are acceptable:
        # the compound `if not _flexicon_preflight(report): return`, or the
        # conventional two-line form -- which is what the template uses, since
        # users copy and edit it.
        if "return" not in first:
            self.assertTrue(
                first.startswith("if "),
                "A pre-flight call whose own line does not return must be a "
                "conditional, or nothing stops Main(). Found: %r" % first,
            )
            self.assertLess(
                idx + 1, len(lines),
                "The pre-flight guard is the last line of Main(); it has no "
                "body, so a bad environment would fall straight through.",
            )
            self.assertEqual(
                "return", lines[idx + 1].strip(),
                "The body of the pre-flight guard must be a bare `return` and "
                "nothing else -- any project work under it runs in the "
                "environment the pre-flight just rejected. Found: %r"
                % lines[idx + 1].strip(),
            )

    def test_the_stub_matches_what_the_template_actually_imports(self):
        """Keeps the sys.modules stub honest (see HOW IT TESTS).

        A stub can drift two ways, and both are silent. If the template's
        import list grows a name the stub lacks, every exec here quietly
        becomes a bad-symbol test. If flexicon stops exporting one of them,
        the stub hides a break that would hit every generated module.
        """
        src = _template_source()
        self.assertIn("from flexicon import (", src)
        block = src.split("from flexicon import (", 1)[1].split(")", 1)[0]
        imported = tuple(re.findall(r"^\s*([A-Za-z_]\w*)\s*,", block, re.M))

        self.assertEqual(
            set(TEMPLATE_IMPORTS), set(imported),
            "The template imports %r but the stub provides %r. Add the new "
            "name to TEMPLATE_IMPORTS, or the stubbed exec starts testing an "
            "ImportError path by accident."
            % (sorted(imported), sorted(TEMPLATE_IMPORTS)),
        )

        try:
            import flexicon
        except Exception as e:  # noqa: BLE001 - see the docstring
            self.skipTest(
                "flexicon is not importable here (%r), which is the situation "
                "the stub exists for. The half of this test that needs the "
                "real package cannot run." % e
            )

        missing = [n for n in imported if not hasattr(flexicon, n)]
        self.assertEqual(
            [], missing,
            "flexicon %s does not export %r, so the emitted template cannot "
            "load at all -- and the stub would go on saying it can."
            % (getattr(flexicon, "version", "?"), missing),
        )

    def test_t4_1a_template_uses_the_bridge_after_the_preflight(self):
        src = _template_source()
        self.assertIn(
            "FromOpenProject", src,
            "The template should teach the portable SPEC 3d shape "
            "(fx = FLExProject.FromOpenProject(project)); the pre-flight "
            "probes for exactly that attribute, so a template without it "
            "would be warning about a capability it never uses.",
        )


# ---------------------------------------------------------------------------
# T4.2 -- the two failures, and the no-version-floor ratchet
# ---------------------------------------------------------------------------

class TestPreflightFailurePaths(unittest.TestCase):

    def test_t4_2a_not_installed_names_the_install_command_and_quotes_the_error(self):
        ns = _load_namespace()
        ns["_flexicon"] = None
        ns["FLExProject"] = None
        ns["_FLEXICON_IMPORT_ERROR"] = "No module named 'flexicon'"

        report = _FakeReport()
        result = ns["_flexicon_preflight"](report)

        self.assertFalse(
            result,
            "With flexicon absent the pre-flight must return False so Main() "
            "returns instead of dying on the next line.",
        )
        self.assertTrue(report.calls, "The absent-flexicon path must say something.")
        text = report.text
        self.assertIn(
            "pip install pyflexicon", text,
            "The message must name the remedy verbatim. Got:\n%s" % text,
        )
        self.assertIn(
            "No module named 'flexicon'", text,
            "The captured ImportError text must be quoted, so the user can "
            "tell a missing package from a broken one. Got:\n%s" % text,
        )

    def test_a_bad_symbol_is_not_reported_as_a_missing_package(self):
        """PR #129 review finding 2.

        `except ImportError` cannot tell "no such package" from "no such name
        in the package", so a single try block around both imports made a wrong
        operations name take the not-installed branch. The user was then told
        flexicon "is not installed", to run `pip install pyflexicon`, and that
        "the module itself is fine" -- all three wrong, and the import list was
        the only thing that did need editing.

        This drives the REAL import machinery (an actual bad name, an actual
        ImportError), which is what the original 17 tests did not: they
        substituted a fully-blocked `import flexicon`, never a partial one.
        """
        src = _template_source()
        bad_src = src.replace(
            "        WritingSystemOperations,\n",
            "        WritingSystemOperations,\n        ReversalOperations,\n",
            1,
        )
        self.assertNotEqual(
            src, bad_src, "Could not inject a bad name into the import list."
        )

        ns = _exec_template(bad_src, "_flexicon_bad_symbol_under_test")

        self.assertIsNotNone(
            ns.get("_flexicon"),
            "`import flexicon` itself succeeded, so _flexicon must NOT be "
            "cleared -- clearing it is what drove the not-installed branch.",
        )
        self.assertIsNotNone(
            ns.get("_FLEXICON_SYMBOL_ERROR"),
            "The bad-name ImportError must be captured separately from the "
            "missing-package one.",
        )
        self.assertIsNone(
            ns.get("_FLEXICON_IMPORT_ERROR"),
            "Nothing is wrong with the package, so the not-installed error "
            "slot must stay empty.",
        )

        report = _FakeReport()
        result = ns["_flexicon_preflight"](report)

        self.assertFalse(
            result,
            "A module that cannot finish importing must still be stopped -- "
            "just for the right reason.",
        )
        text = report.text
        self.assertIn(
            "cannot import name 'ReversalOperations'", text,
            "The real ImportError must be quoted so the user knows WHICH name "
            "to fix. Got:\n%s" % text,
        )
        self.assertIn(
            "from flexicon import", text,
            "The message must point at the import list, which is the thing to "
            "edit. Got:\n%s" % text,
        )
        self.assertNotIn(
            "pip install pyflexicon", text,
            "flexicon IS installed here. Sending the user to pip is the "
            "finding-2 misreport. Got:\n%s" % text,
        )
        self.assertNotIn(
            "nothing here needs editing", text,
            "This is the one pre-flight case where the module is exactly what "
            "needs editing. Got:\n%s" % text,
        )

    def test_a_bad_symbol_message_is_ascii(self):
        """The bad-symbol branch is held to the same ASCII rule as the rest."""
        src = _template_source()
        bad_src = src.replace(
            "        WritingSystemOperations,\n",
            "        WritingSystemOperations,\n        ReversalOperations,\n",
            1,
        )
        ns = _exec_template(bad_src, "_flexicon_bad_symbol_ascii")

        report = _FakeReport()
        ns["_flexicon_preflight"](report)
        self.assertTrue(report.calls, "Expected the bad-symbol diagnostic.")
        for _kind, msg, _ref in report.calls:
            str(msg).encode("ascii")

    def test_the_two_imports_stay_separately_guarded(self):
        """Structural guard: re-merging the try blocks silently reintroduces
        finding 2, and the namespace tests above could not tell, since they
        assert on names the merged form still sets."""
        src = _template_source()
        head = src.split("def _flexicon_installed_version", 1)[0]

        self.assertIn("try:\n    import flexicon as _flexicon\n", head)
        package_try = head.index("try:\n    import flexicon as _flexicon\n")
        symbol_import = head.index("from flexicon import (")
        handler = head.index("except ImportError as _import_error:")
        self.assertLess(
            handler, symbol_import,
            "The missing-package handler must close BEFORE the `from flexicon "
            "import (...)` list, or a bad name lands in it again.",
        )
        self.assertLess(package_try, handler)

    def test_t4_2b_too_old_names_the_upgrade_command_and_the_version_found(self):
        ns = _load_namespace()
        ns["_flexicon"] = _FakeFlexiconModule(version="4.1.1")
        ns["FLExProject"] = _BridgelessFLExProject
        ns["_FLEXICON_IMPORT_ERROR"] = None

        report = _FakeReport()
        result = ns["_flexicon_preflight"](report)

        self.assertFalse(
            result,
            "A pre-bridge flexicon must be caught by the pre-flight, not by an "
            "AttributeError on the first line of Main().",
        )
        text = report.text
        self.assertIn(
            "pip install -U pyflexicon", text,
            "The too-old path must name the UPGRADE command (-U), which is a "
            "different remedy from a plain install. Got:\n%s" % text,
        )
        self.assertIn(
            "4.1.1", text,
            "The version actually found must appear, so the user can see that "
            "the environment -- not the module -- is behind. Got:\n%s" % text,
        )

    def test_t4_2b_version_falls_back_to_package_metadata(self):
        """Source 1 failing must fall through to source 2, not to 'unknown'.

        The contract specifies two guarded sources, tried in order:
        ``getattr(_flexicon, "version", None)`` then
        ``importlib.metadata.version("pyflexicon")``. Only when BOTH fail does
        the string become "unknown".
        """
        import importlib.metadata

        try:
            expected = importlib.metadata.version("pyflexicon")
        except importlib.metadata.PackageNotFoundError:
            self.skipTest(
                "pyflexicon has no installed distribution here, so source 2 "
                "has nothing to return and this test would assert on the "
                "'unknown' floor instead of the fallback."
            )

        ns = _load_namespace()

        class _HostileAttribute:
            @property
            def version(self):
                raise RuntimeError("no version attribute for you")

        ns["_flexicon"] = _HostileAttribute()
        ns["FLExProject"] = _BridgelessFLExProject
        ns["_FLEXICON_IMPORT_ERROR"] = None

        report = _FakeReport()
        result = ns["_flexicon_preflight"](report)

        self.assertFalse(result)
        self.assertIn(
            expected, report.text,
            "With the module attribute unreadable, the version must come from "
            "package metadata (%r) rather than degrading straight to "
            "'unknown'. Got:\n%s" % (expected, report.text),
        )

    def test_t4_2b_version_degrades_to_unknown_when_both_sources_fail(self):
        """"unknown" is the floor, and reaching it must not raise."""
        import importlib.metadata

        ns = _load_namespace()

        class _HostileAttribute:
            @property
            def version(self):
                raise RuntimeError("no version attribute for you")

        ns["_flexicon"] = _HostileAttribute()
        ns["FLExProject"] = _BridgelessFLExProject
        ns["_FLEXICON_IMPORT_ERROR"] = None

        original = importlib.metadata.version

        def _boom(_name):
            raise importlib.metadata.PackageNotFoundError("pyflexicon")

        importlib.metadata.version = _boom
        try:
            report = _FakeReport()
            result = ns["_flexicon_preflight"](report)
        finally:
            importlib.metadata.version = original

        self.assertFalse(result)
        self.assertIn(
            "unknown", report.text,
            "With both version sources failing, the message must still be "
            "emitted with 'unknown' rather than taking the pre-flight down. "
            "Got:\n%s" % report.text,
        )
        self.assertIn(
            "pip install -U pyflexicon", report.text,
            "Losing the version string must not cost the user the remedy.",
        )

    def test_t4_2c_ratchet_no_version_floor_machinery(self):
        """Third-party version-comparison libraries must not appear.

        The template runs in the user's FlexTools environment, where those
        packages may simply not exist -- and needing one at all would mean the
        comparison had grown past what a diagnostic note warrants.
        """
        src = _template_path().read_text(encoding="utf-8")

        for token in ["packaging", "pkg_resources", "LooseVersion",
                      "StrictVersion", "parse_version"]:
            self.assertNotIn(
                token, src,
                "Template must not use %r: that is version-floor machinery, "
                "and the version note is a plain dotted-integer comparison "
                "that must degrade to silence rather than pull a dependency "
                "into the user's FlexTools environment." % token,
            )

    def test_t4_2c_ratchet_a_version_comparison_can_never_gate(self):
        """THE ratchet: no version, however ancient, may stop the module.

        This replaces an earlier source-scanning ratchet that banned version
        comparison outright. The contract (section 8.2) bans a version *floor*
        -- a second source of truth deciding whether the module runs -- not an
        advisory note. So the property worth pinning is behavioural, and it is
        stronger than grepping: whatever the code says, a capable flexicon at
        any version must return True.

        Why the ban exists at all, in one machine's data: on the interpreter
        FlexTools uses, importlib.metadata reports pyflexicon 4.1.1 while
        flexicon.version reports 4.6.0, from the same editable install. A floor
        compared against the wrong one of those refuses a working install.
        """
        ancient = ["0.0.1", "1.0.0", "2.0.0", "4.0.0"]

        for version in ancient:
            with self.subTest(installed=version):
                ns = _load_namespace()
                ns["_flexicon"] = _FakeFlexiconModule(version)
                ns["FLExProject"] = _CurrentFLExProject
                ns["_FLEXICON_IMPORT_ERROR"] = None
                ns["_TESTED_AGAINST"] = "99.99.99"

                report = _FakeReport()
                result = ns["_flexicon_preflight"](report)

                self.assertTrue(
                    result,
                    "flexicon %s has the bridge, so the module MUST run. A "
                    "version comparison that can return False is a floor, and "
                    "floors are banned (contract 8.2)." % version,
                )
                kinds = set(kind for kind, _, _ in report.calls)
                self.assertNotIn(
                    "Error", kinds,
                    "Being behind is not an error -- it must be a Warning at "
                    "most. Got: %r" % (report.calls,),
                )

    def test_older_than_tested_warns_and_names_both_versions(self):
        ns = _load_namespace()
        ns["_flexicon"] = _FakeFlexiconModule("4.3.0")
        ns["FLExProject"] = _CurrentFLExProject
        ns["_FLEXICON_IMPORT_ERROR"] = None
        ns["_TESTED_AGAINST"] = "4.7.0"

        report = _FakeReport()
        result = ns["_flexicon_preflight"](report)

        self.assertTrue(result, "An older-but-capable flexicon must still run.")
        text = report.text
        self.assertIn("4.3.0", text, "The installed version must be named.")
        self.assertIn("4.7.0", text, "The tested-against version must be named.")
        self.assertIn(
            "pip install -U pyflexicon", text,
            "The note should offer the remedy, even though nothing is broken.",
        )
        self.assertEqual(
            {"Warning"}, set(kind for kind, _, _ in report.calls),
            "The version note must be Warning only -- not Error (which would "
            "read as a failure) and not Info (which would be invisible in a "
            "long run). Got: %r" % (report.calls,),
        )

    def test_same_or_newer_than_tested_is_silent(self):
        for version in ["4.7.0", "4.7.1", "4.8.0", "5.0.0", "4.10.0", "4.7"]:
            with self.subTest(installed=version):
                ns = _load_namespace()
                ns["_flexicon"] = _FakeFlexiconModule(version)
                ns["FLExProject"] = _CurrentFLExProject
                ns["_FLEXICON_IMPORT_ERROR"] = None
                ns["_TESTED_AGAINST"] = "4.7.0"

                report = _FakeReport()
                result = ns["_flexicon_preflight"](report)

                self.assertTrue(result)
                self.assertEqual(
                    [], report.calls,
                    "flexicon %s is not behind 4.7.0, so there is nothing to "
                    "say. (4.10.0 is in this list on purpose: a string "
                    "comparison would wrongly rank it below 4.7.0. So is "
                    "'4.7': unpadded tuple ordering ranks (4, 7) below "
                    "(4, 7, 0), reporting the same release as behind "
                    "itself.) Got: %r"
                    % (version, report.calls),
                )

    def test_unparseable_versions_produce_no_note_rather_than_a_wrong_one(self):
        """When we cannot compare honestly, say nothing."""
        cases = [
            ("unknown", "4.7.0"),
            ("4.7.0", "unknown"),
            ("4.7.0.dev1", "4.7.0"),
            ("4.7.0+g1234abc", "4.7.0"),
            # NOT included: installed="". An empty version attribute is
            # "absent", not "unparseable", so it falls through to
            # importlib.metadata by design and a real comparison follows --
            # pinned by test_t4_2b_version_falls_back_to_package_metadata.
        ]
        for installed, tested in cases:
            with self.subTest(installed=installed, tested=tested):
                ns = _load_namespace()
                ns["_flexicon"] = _FakeFlexiconModule(installed)
                ns["FLExProject"] = _CurrentFLExProject
                ns["_FLEXICON_IMPORT_ERROR"] = None
                ns["_TESTED_AGAINST"] = tested

                report = _FakeReport()
                result = ns["_flexicon_preflight"](report)

                self.assertTrue(result)
                self.assertEqual(
                    [], report.calls,
                    "installed=%r tested=%r is not a comparison we can trust, "
                    "so the pre-flight must stay quiet rather than guess. "
                    "Got: %r" % (installed, tested, report.calls),
                )

    def test_a_shorter_version_string_is_not_behind_a_longer_equal_one(self):
        """PR #129 review, minor: pad before comparing.

        Both directions, because tuple ordering is only wrong in one of them
        and a fix that reverses the operands would pass a one-sided test.
        """
        for installed, tested in [("4.7", "4.7.0"), ("4.7.0", "4.7"),
                                  ("4", "4.0.0"), ("5", "4.9.9")]:
            with self.subTest(installed=installed, tested=tested):
                ns = _load_namespace()
                ns["_flexicon"] = _FakeFlexiconModule(installed)
                ns["FLExProject"] = _CurrentFLExProject
                ns["_FLEXICON_IMPORT_ERROR"] = None
                ns["_TESTED_AGAINST"] = tested

                report = _FakeReport()
                self.assertTrue(ns["_flexicon_preflight"](report))
                self.assertEqual(
                    [], report.calls,
                    "installed=%r is not older than tested=%r once the "
                    "version tuples are padded to a common length. Got: %r"
                    % (installed, tested, report.calls),
                )

    def test_padding_does_not_silence_a_genuinely_older_short_version(self):
        """The padding must not cost the note it exists to keep honest."""
        ns = _load_namespace()
        ns["_flexicon"] = _FakeFlexiconModule("4.6")
        ns["FLExProject"] = _CurrentFLExProject
        ns["_FLEXICON_IMPORT_ERROR"] = None
        ns["_TESTED_AGAINST"] = "4.7.0"

        report = _FakeReport()
        self.assertTrue(ns["_flexicon_preflight"](report))
        self.assertIn("4.6", report.text)
        self.assertIn("4.7.0", report.text)

    def test_unstamped_template_never_warns(self):
        """A hand-copied template file keeps _TESTED_AGAINST = 'unknown'."""
        src = _template_path().read_text(encoding="utf-8")
        self.assertIn(
            '_TESTED_AGAINST = "unknown"', src,
            "The template FILE must ship with the placeholder; only the "
            "emitted copy is stamped. Otherwise a hand-maintained constant "
            "rots exactly the way the old 'Flexicon version 2.0+' line did.",
        )

        ns = _load_namespace()
        self.assertNotEqual(
            "unknown", ns["_TESTED_AGAINST"],
            "The EMITTED template should carry a real stamped version, so a "
            "generated module records what it was written against.",
        )


# ---------------------------------------------------------------------------
# T4.3 -- ASCII only
# ---------------------------------------------------------------------------

class TestPreflightIsAscii(unittest.TestCase):

    def test_t4_3a_every_emittable_message_is_ascii(self):
        scenarios = [
            ("not installed", None, None, "No module named 'flexicon'", None),
            ("too old", _FakeFlexiconModule("4.1.1"), _BridgelessFLExProject,
             None, None),
            ("too old, unknown version", _FakeFlexiconModule(None),
             _BridgelessFLExProject, None, None),
            ("behind the tested version", _FakeFlexiconModule("4.3.0"),
             _CurrentFLExProject, None, "4.7.0"),
        ]

        for label, flexicon_mod, cls, import_error, tested in scenarios:
            with self.subTest(scenario=label):
                ns = _load_namespace()
                ns["_flexicon"] = flexicon_mod
                ns["FLExProject"] = cls
                ns["_FLEXICON_IMPORT_ERROR"] = import_error
                if tested is not None:
                    ns["_TESTED_AGAINST"] = tested

                report = _FakeReport()
                ns["_flexicon_preflight"](report)

                self.assertTrue(
                    report.calls,
                    "Scenario %r emitted nothing; this test would then be "
                    "vacuous." % label,
                )

                for _, msg, _ref in report.calls:
                    try:
                        str(msg).encode("ascii")
                    except UnicodeEncodeError as e:
                        self.fail(
                            "Non-ASCII character in a pre-flight message "
                            "(%s). Windows terminals render these as mojibake "
                            "(CLAUDE.md). Offending message:\n%r\n%s"
                            % (label, msg, e)
                        )

    def test_t4_3a_the_whole_template_is_ascii(self):
        raw = _template_path().read_bytes()
        try:
            raw.decode("ascii")
        except UnicodeDecodeError as e:
            self.fail(
                "The flexicon template contains a non-ASCII byte. It is "
                "emitted into Windows FlexTools environments (CLAUDE.md):\n%s"
                % e
            )


# ---------------------------------------------------------------------------
# T4.4 -- silent on success, and fail open
# ---------------------------------------------------------------------------

class TestPreflightHappyPathAndFailOpen(unittest.TestCase):

    def test_t4_4a_happy_path_returns_true_and_says_nothing_at_all(self):
        ns = _load_namespace()
        ns["_flexicon"] = _FakeFlexiconModule("4.6.0")
        ns["FLExProject"] = _CurrentFLExProject
        ns["_FLEXICON_IMPORT_ERROR"] = None
        # Pinned rather than left at the stamped value, so this test asserts
        # "silent when current" and not "silent on whatever is installed here".
        ns["_TESTED_AGAINST"] = "4.6.0"

        report = _FakeReport()
        result = ns["_flexicon_preflight"](report)

        self.assertTrue(
            result,
            "With a current flexicon the pre-flight must return True so Main() "
            "proceeds.",
        )
        self.assertEqual(
            [], report.calls,
            "The pre-flight must be COMPLETELY silent on success -- not even "
            "report.Info. It is invisible under the MCP and on any current "
            "install (contract section 8.3). Got: %r" % (report.calls,),
        )

    def test_t4_4b_a_probe_that_raises_fails_open(self):
        ns = _load_namespace()
        ns["_flexicon"] = _FakeFlexiconModule("4.6.0")
        ns["FLExProject"] = _ExplodingFLExProject
        ns["_FLEXICON_IMPORT_ERROR"] = None
        ns["_TESTED_AGAINST"] = "4.6.0"

        report = _FakeReport()
        try:
            result = ns["_flexicon_preflight"](report)
        except Exception as e:  # noqa: BLE001 - that is the failure being tested
            self.fail(
                "The pre-flight let an exception escape (%r). It must never be "
                "the reason a working module stops running "
                "(contract section 8.3)." % e
            )

        self.assertTrue(
            result,
            "A probe that cannot determine the answer must FAIL OPEN and "
            "return True, letting the module run and fail on its own terms if "
            "it is going to.",
        )

    def test_t4_4b_fail_open_also_covers_a_hostile_report(self):
        """Even a report object that throws must not turn into a module crash."""
        ns = _load_namespace()
        ns["_flexicon"] = None
        ns["FLExProject"] = None
        ns["_FLEXICON_IMPORT_ERROR"] = "No module named 'flexicon'"

        class _HostileReport:
            def Error(self, msg, ref=None):
                raise RuntimeError("reporting is broken too")

        try:
            ns["_flexicon_preflight"](_HostileReport())
        except Exception as e:  # noqa: BLE001
            self.fail(
                "A failing report.Error must not propagate out of the "
                "pre-flight (%r); 'never raises' is unconditional "
                "(contract section 8.3)." % e
            )


if __name__ == "__main__":
    unittest.main()
