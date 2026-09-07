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
import itertools
import json
import os
import time

import pytest

from server import versioning
from server.handlers.diagnostic_health import compute_library_match


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Cycle-7 CP-D D-2: versioning._dir_state_token() keys the file-discovery
# cache on `index_dir.stat().st_mtime`. The TestFileDiscoveryCacheInvalidation
# tests below write a file, look it up (caching a result keyed to the
# directory's current mtime), then write a SECOND file and expect the next
# lookup to see it. That only works if the directory's mtime visibly changes
# between the two writes. Two writes made microseconds apart do not reliably
# produce two distinguishable `st_mtime` values on Windows/NTFS -- the
# resolution/rounding the stdlib surfaces there is coarse enough that the
# second write can land in the same observable mtime as the first, so the
# cache silently keeps serving the stale (pre-second-write) result. That is
# an intrinsic race, not a sibling-test interaction, and not something a
# production cache-key fix belongs to (a monotonic per-write directory-
# content hash would be a legitimate production fix, but that's out of
# scope / out of this task's lock set).
#
# Measured rates (cycle 9, P2: the earlier "~15-25% ... confirmed
# empirically" range here was unsupported -- these are the real numbers,
# each from a distinct measurement, not interchangeable):
#   - 5/40 (12.5%) and 1/40 (2.5%): pre-fix, 40 isolated single-process runs
#     each of test_new_exact_file_visible_after_write and
#     test_new_latest_file_visible_after_write respectively
#     (specs/swahili-audit-2026-09/reviews/cycle7-programmer-p2.md).
#   - 40/300 (13.3%): a standalone probe calling the real production
#     find_latest_versioned_api_file back-to-back (write v1, prime cache,
#     write v2 immediately, re-lookup) -- the production-function analogue
#     of this fixture's race, not the test fixture itself
#     (specs/swahili-audit-2026-09/reviews/cycle8-verification.md).
#   - 58/200 (29%): rapid double-writes where st_mtime was observed
#     unchanged across the pair -- the underlying filesystem-resolution
#     mechanism this whole comment describes
#     (specs/swahili-audit-2026-09/reviews/cycle8-qc.md).
#
# _bump_dir_mtime() sidesteps filesystem timestamp-resolution entirely: it
# sets an EXPLICIT, strictly-increasing mtime via os.utime() rather than
# trusting the filesystem to have advanced its clock (or its rounding) far
# enough between two writes. A module-level monotonic counter guarantees
# every call produces a value later than the last, regardless of how fast
# the test runs or how coarse the OS's mtime granularity is.
_mtime_counter = itertools.count(1)


def _bump_dir_mtime(dir_path) -> None:
    """Force dir_path's mtime strictly forward so cache-key lookups that
    read it (versioning._dir_state_token) observe a real, distinguishable
    change -- see the module-level comment above for why this can't be left
    to the filesystem alone."""
    new_time = time.time() + next(_mtime_counter)
    os.utime(dir_path, (new_time, new_time))


def _write_api_file(lib_dir, prefix, version, entities=None):
    """Write a versioned API fixture file, then explicitly bump lib_dir's
    mtime (see _bump_dir_mtime) so a subsequent file-discovery cache lookup
    against lib_dir is guaranteed to observe this write as a change, even
    when two writes happen inside the same filesystem mtime-resolution
    window."""
    lib_dir.mkdir(parents=True, exist_ok=True)
    path = lib_dir / f"{prefix}_v{version}.json"
    data = {
        "_schema": "unified-api-doc/2.0",
        "entities": entities if entities is not None else {"ILexEntry": {}},
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    _bump_dir_mtime(lib_dir)
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
# Same-tick cache invalidation (cycle 10, CP-E)
#
# D-2 (cycle 7) introduced _bump_dir_mtime to force a distinguishable mtime
# between the two writes in every TestFileDiscoveryCacheInvalidation test.
# That made those tests reliable, but as a side effect it means the suite no
# longer exercises the literal race QC and Verification measured against the
# real production functions:
#   - 40/300 (13.3%) stale reads through find_latest_versioned_api_file
#     (cycle8-verification.md)
#   - 58/200 (29%) rapid double-writes leaving st_mtime unchanged
#     (cycle8-qc.md)
# The tests below restore that coverage. Instead of relying on real
# clock/filesystem timing to produce a same-tick collision (flaky by
# nature -- that's the whole reason the rate is 13-29%, not 100%), they PIN
# index_dir's mtime to an identical, fixed value across both writes via
# os.utime(). This is a deterministic stand-in for "the filesystem failed to
# advance mtime between two writes" -- not a mock of the functions under
# test. find_versioned_api_file() / find_latest_versioned_api_file() are
# called directly, unmocked, against a real tmp_path directory.
# ---------------------------------------------------------------------------

def _write_api_file_same_tick(lib_dir, prefix, version, frozen_mtime, entities=None):
    """Like _write_api_file(), but PINS lib_dir's (and the new file's) mtime
    to frozen_mtime instead of advancing it -- simulates two rapid writes
    that the filesystem's mtime resolution failed to distinguish."""
    lib_dir.mkdir(parents=True, exist_ok=True)
    path = lib_dir / f"{prefix}_v{version}.json"
    data = {
        "_schema": "unified-api-doc/2.0",
        "entities": entities if entities is not None else {"ILexEntry": {}},
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    os.utime(lib_dir, (frozen_mtime, frozen_mtime))
    os.utime(path, (frozen_mtime, frozen_mtime))
    return path


class TestSameTickCacheInvalidation:
    """Restores the same-tick race coverage D-2's _bump_dir_mtime removed
    (flagged cycle8-qc.md P2: 'same-tick invalidation is now covered
    nowhere'). Both tests pin index_dir's mtime identically across two
    writes, so a cache key built from bare st_mtime alone is guaranteed to
    collide -- the fixed _dir_state_token() must still notice the new file
    via a listing-shape signal (entry count / max child mtime), not mtime
    alone."""

    def test_new_exact_file_visible_same_dir_mtime(self, tmp_path):
        lib_dir = tmp_path / "python"
        frozen = 1_700_000_000.0
        _write_api_file_same_tick(lib_dir, "flexicon_api", "4.1.0", frozen)

        # First lookup: no exact match for 4.2.0 yet -- caches a miss.
        assert versioning.find_versioned_api_file(lib_dir, "flexicon_api", "4.2.0") is None

        # Second write pinned to the SAME directory mtime as the first --
        # a bare st_mtime cache key cannot observe this as a change.
        _write_api_file_same_tick(lib_dir, "flexicon_api", "4.2.0", frozen)

        found = versioning.find_versioned_api_file(lib_dir, "flexicon_api", "4.2.0")
        assert found is not None, (
            "stale cache: lookup after a same-mtime write still returned the "
            "pre-write miss (the regression measured in cycle8-qc.md: "
            "58/200, 29%; cycle8-verification.md: 40/300, 13.3%)"
        )
        assert found.name == "flexicon_api_v4.2.0.json"

    def test_new_latest_file_visible_same_dir_mtime(self, tmp_path):
        lib_dir = tmp_path / "python"
        frozen = 1_700_000_000.0
        _write_api_file_same_tick(lib_dir, "flexicon_api", "4.0.0", frozen)

        first = versioning.find_latest_versioned_api_file(lib_dir, "flexicon_api")
        assert first.name == "flexicon_api_v4.0.0.json"

        # Same frozen mtime as the first write -- st_mtime alone is blind
        # to this write.
        _write_api_file_same_tick(lib_dir, "flexicon_api", "4.5.0", frozen)

        second = versioning.find_latest_versioned_api_file(lib_dir, "flexicon_api")
        assert second is not None and second.name == "flexicon_api_v4.5.0.json", (
            "stale cache: expected v4.5.0 after a same-mtime write, got "
            f"{second.name if second else None}"
        )


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
        assert "project_access" in data["verbose"]
        assert "flexinit_importable" in data["verbose"]
        assert "pythonnet_available" in data["verbose"]
        assert "recent_operations" in data["verbose"]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
