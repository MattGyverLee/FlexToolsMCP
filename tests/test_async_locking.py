#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test suite for async concurrency locking.

Demonstrates that:
1. Read-only operations don't acquire locks
2. Metadata-only operations don't acquire locks
3. CUD operations serialize per-project
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from server.kernel import get_project_write_lock, project_write_locks
from server.validators import detect_cud_operations


def test_cud_detection():
    """Test that CUD detection works correctly."""

    # Read-only code
    read_only = """
    entries = LexEntryOperations(project).GetAll()
    for entry in entries:
        print(entry.Headword)
    """
    assert not detect_cud_operations(read_only)["is_cud"], "Read-only should not detect CUD"

    # Read operations (no CUD pattern)
    read_operations = """
    settings = project.ProjectSettings.GetValue("customField")
    ws = project.WritingSystems.GetAll()
    count = len(project.Entries.GetAll())
    """
    assert not detect_cud_operations(read_operations)["is_cud"], "Read operations should not detect CUD"

    # CREATE operation
    create_op = """
    entry = LexEntryOperations(project).Create(headword="water")
    """
    cud = detect_cud_operations(create_op)
    assert cud["is_cud"], "Should detect CREATE"
    assert "CREATE" in cud["operations"][0], f"Should identify as CREATE, got {cud['operations']}"

    # UPDATE operation
    update_op = """
    sense.set_String(sense.Gloss, "en", "water")
    """
    cud = detect_cud_operations(update_op)
    assert cud["is_cud"], "Should detect UPDATE"
    assert "UPDATE" in cud["operations"][0], f"Should identify as UPDATE, got {cud['operations']}"

    # DELETE operation
    delete_op = """
    LexEntryOperations(project).Delete(entry)
    """
    cud = detect_cud_operations(delete_op)
    assert cud["is_cud"], "Should detect DELETE"
    assert "DELETE" in cud["operations"][0], f"Should identify as DELETE, got {cud['operations']}"

    print("[OK] CUD detection working correctly")


async def test_lock_creation():
    """Test that locks are created per-project."""

    # Clear locks
    project_write_locks.clear()

    # Get locks for different projects
    lock_a1 = get_project_write_lock("ProjectA")
    lock_a2 = get_project_write_lock("ProjectA")
    lock_b = get_project_write_lock("ProjectB")

    # Same project should get same lock
    assert lock_a1 is lock_a2, "Same project should get same lock object"

    # Different projects should get different locks
    assert lock_a1 is not lock_b, "Different projects should get different locks"

    print("[OK] Lock creation working correctly")


async def test_lock_serialization():
    """Test that locks actually serialize access."""

    project_write_locks.clear()
    lock = get_project_write_lock("TestProject")

    execution_order = []

    async def operation_a():
        async with lock:
            execution_order.append("A_start")
            await asyncio.sleep(0.01)  # Hold lock briefly
            execution_order.append("A_end")

    async def operation_b():
        await asyncio.sleep(0.001)  # Let A start first
        async with lock:
            execution_order.append("B_start")
            execution_order.append("B_end")

    # Run both concurrently
    await asyncio.gather(operation_a(), operation_b())

    # B should not start until A ends
    assert execution_order.index("A_end") < execution_order.index("B_start"), \
        f"Operations should serialize, got order: {execution_order}"

    print("[OK] Lock serialization working correctly")


async def test_different_projects_parallel():
    """Test that different projects can run in parallel."""

    project_write_locks.clear()
    lock_a = get_project_write_lock("ProjectA")
    lock_b = get_project_write_lock("ProjectB")

    execution_order = []

    async def operation_on_a():
        async with lock_a:
            execution_order.append("A_acquire")
            await asyncio.sleep(0.01)
            execution_order.append("A_release")

    async def operation_on_b():
        await asyncio.sleep(0.002)  # Let A start first
        async with lock_b:
            execution_order.append("B_acquire")
            execution_order.append("B_release")

    # Run both concurrently
    await asyncio.gather(operation_on_a(), operation_on_b())

    # Both should acquire locks while the other is executing
    # If running in parallel: A_acquire, A_release, B_acquire, B_release OR
    #                        A_acquire, B_acquire, A_release, B_release
    # If serialized: A_acquire, A_release, B_acquire, B_release always
    b_acquire_idx = execution_order.index("B_acquire")
    a_release_idx = execution_order.index("A_release")

    # B should acquire before A releases (showing parallel execution)
    assert b_acquire_idx < a_release_idx, \
        f"B should acquire while A holds lock (parallel), but order was: {execution_order}"

    print("[OK] Different projects run in parallel")


async def main():
    """Run all tests."""
    print("Running async locking tests...\n")

    test_cud_detection()
    await test_lock_creation()
    await test_lock_serialization()
    await test_different_projects_parallel()

    print("\n[DONE] All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
