#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for issue #56: flextools_health diagnostics tool + cache invalidation.

Covers:
- compute_library_match(): exact-match, fallback, and missing-index fixtures
  produce the correct `match` value (and index_loaded).
- The file-discovery cache (versioning.py) picks up files written to an
  index directory *after* an earlier (cached) lookup -- the regression test
  for the "flextools_health reflects post-refresh reality" requirement.
- handle_flextools_health() end-to-end: warnings are populated for a
  fallback_latest library and empty for an all-exact-match session.
"""

import asyncio
import json

import pytest

from server import versioning
from server.handlers.diagnostic_health import compute_library_match


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_api_file(lib_dir, prefix, version, entities=None):
    lib_dir.mkdir(parents=True, exist_ok=True)
    path = lib_dir / f"{prefix}_v{version}.json"
    data = {
        "_schema": "unified-api-doc/2.0",
        "entities": entities if entities is not None else {"ILexEntry": {}},
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _clear_cache():
    """Every test starts and ends with a clean file-discovery cache."""
    versioning.clear_file_discovery_cache()
    yield
    versioning.clear_file_discovery_cache()


# ---------------------------------------------------------------------------
# compute_library_match(): exact / fallback / missing
# ---------------------------------------------------------------------------

class TestComputeLibraryMatch:
    def test_exact_match(self, tmp_path):
        lib_dir = tmp_path / "python"
        _write_api_file(lib_dir, "flexicon_api", "4.2.1")

        result = compute_library_match(lib_dir, "flexicon_api", "4.2.1")

        assert result == {
            "installed": "4.2.1",
            "index_loaded": "4.2.1",
            "match": "exact",
        }

    def test_fallback_latest(self, tmp_path):
        lib_dir = tmp_path / "python"
        _write_api_file(lib_dir, "flexicon_api", "4.1.0")
        _write_api_file(lib_dir, "flexicon_api", "4.0.0")

        # Installed version (4.2.0) has no exact match; the latest shipped
        # index (4.1.0) is served instead.
        result = compute_library_match(lib_dir, "flexicon_api", "4.2.0")

        assert result["installed"] == "4.2.0"
        assert result["index_loaded"] == "4.1.0"
        assert result["match"] == "fallback_latest"

    def test_missing_index(self, tmp_path):
        lib_dir = tmp_path / "python"  # never created / never populated

        result = compute_library_match(lib_dir, "flexicon_api", "4.2.0")

        assert result == {
            "installed": "4.2.0",
            "index_loaded": None,
            "match": "missing",
        }

    def test_not_installed_but_index_present_reports_fallback(self, tmp_path):
        """installed_version=None (library not detected) with a shipped index
        present still surfaces the file as fallback_latest -- there's no
        installed version to compare against, but an index IS being served."""
        lib_dir = tmp_path / "python"
        _write_api_file(lib_dir, "flexlibs_api", "1.2.8")

        result = compute_library_match(lib_dir, "flexlibs_api", None)

        assert result["installed"] is None
        assert result["index_loaded"] == "1.2.8"
        assert result["match"] == "fallback_latest"


# ---------------------------------------------------------------------------
# Cache invalidation: a write to index_dir must be visible on the next lookup
# ---------------------------------------------------------------------------

class TestFileDiscoveryCacheInvalidation:
    def test_new_exact_file_visible_after_write(self, tmp_path):
        lib_dir = tmp_path / "python"
        _write_api_file(lib_dir, "flexicon_api", "4.1.0")

        # First lookup: no exact match for 4.2.0 yet -- caches a miss.
        assert versioning.find_versioned_api_file(lib_dir, "flexicon_api", "4.2.0") is None

        # Simulate an out-of-band refresh (this process's auto-refresh, or a
        # concurrent `python -m flextoolsmcp.refresh` run) writing the file
        # that was previously missing.
        _write_api_file(lib_dir, "flexicon_api", "4.2.0")

        # The cache must NOT still be serving the stale None from before --
        # the directory's mtime changed, which is baked into the cache key.
        found = versioning.find_versioned_api_file(lib_dir, "flexicon_api", "4.2.0")
        assert found is not None
        assert found.name == "flexicon_api_v4.2.0.json"

    def test_new_latest_file_visible_after_write(self, tmp_path):
        lib_dir = tmp_path / "python"
        _write_api_file(lib_dir, "flexicon_api", "4.0.0")

        first = versioning.find_latest_versioned_api_file(lib_dir, "flexicon_api")
        assert first.name == "flexicon_api_v4.0.0.json"

        _write_api_file(lib_dir, "flexicon_api", "4.5.0")

        second = versioning.find_latest_versioned_api_file(lib_dir, "flexicon_api")
        assert second.name == "flexicon_api_v4.5.0.json"

    def test_health_reflects_post_refresh_reality(self, tmp_path, monkeypatch):
        """End-to-end: compute_library_match(), called again after a file is
        written to the index dir, sees the new file without any explicit
        cache-clear call -- this is the literal acceptance criterion from
        issue #56 ("auto-refresh then health -> new file visible")."""
        lib_dir = tmp_path / "python"

        before = compute_library_match(lib_dir, "flexicon_api", "4.2.1")
        assert before["match"] == "missing"

        _write_api_file(lib_dir, "flexicon_api", "4.2.1")

        after = compute_library_match(lib_dir, "flexicon_api", "4.2.1")
        assert after["match"] == "exact"
        assert after["index_loaded"] == "4.2.1"


# ---------------------------------------------------------------------------
# handle_flextools_health(): end-to-end warnings behavior
# ---------------------------------------------------------------------------

class TestHandleFlexToolsHealth:
    def _run(self, args):
        from server.handlers.diagnostic_health import handle_flextools_health
        result = asyncio.run(handle_flextools_health(args))
        return json.loads(result[0].text)

    def test_no_warnings_when_all_exact(self, tmp_path, monkeypatch):
        index_dir = tmp_path / "index"
        _write_api_file(index_dir / "python", "flexicon_api", "4.2.1")
        _write_api_file(index_dir / "liblcm", "liblcm_api", "11.0.0")
        _write_api_file(index_dir / "python", "flexlibs_api", "1.2.8")

        import server.handlers.diagnostic_health as dh
        monkeypatch.setattr(dh, "get_index_dir", lambda: index_dir)
        monkeypatch.setattr(
            dh,
            "detect_installed_library_version",
            lambda display_name, **kw: {
                "Flexicon": "4.2.1",
                "LibLCM": "11.0.0",
                "FlexLibs stable": "1.2.8",
            }.get(display_name),
        )

        data = self._run({"verbose": False})

        assert data["libraries"]["flexicon"]["match"] == "exact"
        assert data["libraries"]["liblcm"]["match"] == "exact"
        assert data["libraries"]["flexlibs_stable"]["match"] == "exact"
        # No fallback warnings expected (startup lock warnings may still be
        # present from a real api_index, but the fallback message must not be).
        assert not any("Index fallback active" in w for w in data["warnings"])

    def test_warning_present_for_fallback_library(self, tmp_path, monkeypatch):
        index_dir = tmp_path / "index"
        # Flexicon: installed 4.2.1, only 4.1.0 shipped -> fallback_latest.
        _write_api_file(index_dir / "python", "flexicon_api", "4.1.0")
        _write_api_file(index_dir / "liblcm", "liblcm_api", "11.0.0")
        _write_api_file(index_dir / "python", "flexlibs_api", "1.2.8")

        import server.handlers.diagnostic_health as dh
        monkeypatch.setattr(dh, "get_index_dir", lambda: index_dir)
        monkeypatch.setattr(
            dh,
            "detect_installed_library_version",
            lambda display_name, **kw: {
                "Flexicon": "4.2.1",
                "LibLCM": "11.0.0",
                "FlexLibs stable": "1.2.8",
            }.get(display_name),
        )

        data = self._run({"verbose": False})

        assert data["libraries"]["flexicon"]["match"] == "fallback_latest"
        assert any("Index fallback active" in w for w in data["warnings"])
        assert "verbose" not in data

    def test_verbose_adds_diagnostic_block(self, tmp_path, monkeypatch):
        index_dir = tmp_path / "index"
        _write_api_file(index_dir / "python", "flexicon_api", "4.2.1")

        import server.handlers.diagnostic_health as dh
        monkeypatch.setattr(dh, "get_index_dir", lambda: index_dir)
        monkeypatch.setattr(dh, "detect_installed_library_version", lambda *a, **kw: None)

        data = self._run({"verbose": True})

        assert "verbose" in data
        assert "project_lock" in data["verbose"]
        assert "flexinit_importable" in data["verbose"]
        assert "pythonnet_available" in data["verbose"]
        assert "recent_operations" in data["verbose"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
