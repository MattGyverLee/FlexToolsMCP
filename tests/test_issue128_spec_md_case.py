#!/usr/bin/env python3
"""Issue #128: Companion must see legacy uppercase SPEC.md on case-sensitive FS."""

import importlib
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_COMPANION_SCRIPTS = _REPO_ROOT / ".specify" / "extensions" / "companion" / "scripts"
sys.path.insert(0, str(_COMPANION_SCRIPTS))

sc = importlib.import_module("spec_context")
derive = importlib.import_module("derive-from-files")

# Directories called out in issue #128 (renamed to lowercase spec.md in this fix).
_ISSUE_128_SPEC_DIRS = (
    "broken-script-migration",
    "diagnostic-report",
    "flexicon-guidance-correction",
    "modifiesdb-parity",
    "portability-preflight",
    "shared-mode-access",
    "swahili-audit-2026-09",
    "vanilla-flextools-parity",
    "write-authorization-audit",
)


class TestIssue128SpecMdCase(unittest.TestCase):
    def test_legacy_spec_dirs_use_lowercase_spec_md(self):
        specs = _REPO_ROOT / "specs"
        for slug in _ISSUE_128_SPEC_DIRS:
            feature_dir = specs / slug
            # Use directory listing for exact case — Path.exists() is
            # case-insensitive on Windows NTFS, so SPEC.md.exists() is True
            # even when only lowercase spec.md is present.
            names = {p.name for p in feature_dir.iterdir()}
            self.assertIn(
                "spec.md",
                names,
                f"expected lowercase spec.md after rename in {slug} (issue #128)",
            )
            self.assertNotIn(
                "SPEC.md",
                names,
                f"uppercase SPEC.md should not remain alongside spec.md in {slug}",
            )

    def test_resolve_feature_spec_md_accepts_either_spelling(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            feature_dir = Path(tmp)
            upper = feature_dir / "SPEC.md"
            upper.write_text("# Feature\n", encoding="utf-8")
            resolved = sc.resolve_feature_spec_md(feature_dir)
            self.assertEqual(resolved, upper)

            lower = feature_dir / "spec.md"
            lower.write_text("# Feature lower\n", encoding="utf-8")
            # When both exist (should not happen in repo), prefer lowercase.
            self.assertEqual(sc.resolve_feature_spec_md(feature_dir), lower)

    def test_derive_from_files_infers_specify_from_uppercase_only(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            feature_dir = Path(tmp)
            (feature_dir / "SPEC.md").write_text("# X\n", encoding="utf-8")
            inferred = derive._infer(feature_dir)
            self.assertEqual(inferred, ("specify", "specified"))


if __name__ == "__main__":
    unittest.main()
