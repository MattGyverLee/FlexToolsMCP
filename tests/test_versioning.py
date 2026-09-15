#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for server/versioning.py's get_resolved_fieldworks_dir().

get_resolved_fieldworks_dir() is a thin wrapper over locate_liblcm_dll():
it returns the DLL's parent directory, or None when the DLL isn't found.
This is the single shared accessor for "which FieldWorks install did we
bind to" -- see the docstring in versioning.py for why that matters.
"""

from pathlib import Path

from server.versioning import get_resolved_fieldworks_dir


class TestGetResolvedFieldworksDir:
    def test_returns_install_dir_when_dll_present(self, tmp_path):
        install_dir = tmp_path / "FieldWorks 9"
        install_dir.mkdir()
        (install_dir / "SIL.LCModel.dll").write_bytes(b"")

        result = get_resolved_fieldworks_dir(search_paths=[install_dir])

        assert result == install_dir

    def test_returns_none_when_dll_absent(self, tmp_path):
        empty_dir = tmp_path / "not-fieldworks"
        empty_dir.mkdir()

        result = get_resolved_fieldworks_dir(search_paths=[empty_dir])

        assert result is None

    def test_search_paths_passed_through_in_order(self, tmp_path):
        """Only the second search path has the DLL -- confirms both entries
        of the caller-supplied list are consulted, not just the first."""
        first_dir = tmp_path / "no-dll-here"
        second_dir = tmp_path / "real-install"
        first_dir.mkdir()
        second_dir.mkdir()
        (second_dir / "SIL.LCModel.dll").write_bytes(b"")

        result = get_resolved_fieldworks_dir(search_paths=[first_dir, second_dir])

        assert result == second_dir

    def test_defaults_to_none_search_paths_without_error(self):
        """No search_paths supplied -- falls back to locate_liblcm_dll()'s
        own default search list. Just confirms the pass-through of None
        doesn't blow up; the real machine may or may not have FieldWorks
        installed, so we only assert the return type contract."""
        result = get_resolved_fieldworks_dir()

        assert result is None or isinstance(result, Path)
