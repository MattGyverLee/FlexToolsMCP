#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Issue #171: reset_session() must mutate, not rebind, session_state."""

from server.handlers import catalog as catalog_handler
from server.kernel import reset_session, session_state as kernel_session_state


def test_reset_session_mutates_handler_import_reference():
    """Handler modules import session_state at load time; reset must reach them."""
    catalog_handler.session_state.project_name = "leak-test-project"
    catalog_handler.session_state.record_discovered_api("LexEntry", "GetAll")

    before_id = id(catalog_handler.session_state)
    assert before_id == id(kernel_session_state)

    reset_session()

    assert id(catalog_handler.session_state) == before_id
    assert id(kernel_session_state) == before_id
    assert catalog_handler.session_state.project_name == ""
    assert catalog_handler.session_state.get_discovered_apis() == set()


def test_reset_session_state_fixture_clears_handler_import(reset_session_state):
    """conftest reset_session_state must reset the object handlers actually use."""
    assert catalog_handler.session_state.project_name == ""
    catalog_handler.session_state.project_name = "during-test"
    catalog_handler.session_state.record_validated_api("VariantOperations")

    reset_session()

    assert catalog_handler.session_state.project_name == ""
    assert catalog_handler.session_state.validated_apis == set()
