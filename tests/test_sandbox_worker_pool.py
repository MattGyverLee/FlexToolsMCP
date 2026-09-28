#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser-check CP5 Phase 11 (T122, issue #242, SC-006): `server/sandbox/pool.py`
-- the idle `--sandbox` worker pool -- against REAL `--stub --sandbox`
worker processes (no FieldWorks needed).

What this file pins
-------------------
  * checkout on an empty pool spawns a fresh worker (`reused` False);
  * checkin parks it; a later checkout of the same key reuses the SAME
    process (`reused` True, same pid), and the reused worker still parses;
  * the key: a changed config file, changed parameters, or a changed
    stub flag is a miss (a pooled worker can never serve a grammar it did
    not load);
  * concurrent checkouts of one key get distinct workers (F-13);
  * `evict_project` / `evict_keys` (and through them the
    `cache.invalidate` / `cache.prune` notifications) drop only the
    matching idle workers;
  * the idle sweeper reaps workers nobody reuses; a dead pooled worker is
    discarded, never handed out;
  * checkin refuses a dead worker or one with requests in flight;
  * `aclose()` reaps everything;
  * at hand-over the stderr sink is swapped and run listeners are cleared,
    so no diagnostic leaks into another run's record.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from flextoolsmcp.server.parse.worker_client import SandboxSpawn
from flextoolsmcp.server.sandbox import pool as pool_mod
from flextoolsmcp.server.sandbox.pool import (
    SandboxWorkerPool,
    compute_pool_key,
    notify_keys_pruned,
    notify_project_invalidated,
)

PROJECT = "PoolProj"


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "hc-config.json"
    path.write_text(json.dumps({"words": {}}), encoding="utf-8")
    return path


def spawn_for(config, *, named=False):
    return SandboxSpawn(
        config=str(config),
        hc_params=None,
        id_map=None,
        engine_dir=None,
        project=PROJECT,
        named_sandbox=named,
    )


def cache_key(config, params=None):
    return compute_pool_key(
        kind="cache", entry_key="entry1", parameters=params or {}, stub=True)


async def checkout(pool, key, config, **kw):
    return await pool.checkout(
        key, project_name=PROJECT, spawn=spawn_for(config), stub=True, **kw)


async def parse(worker, word, run_id):
    return await worker.parse_word(
        request_id=f"{run_id}-{word}", run_id=run_id, wordform=word)


async def wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.05)
    return False


# ---------------------------------------------------------------------------
# checkout / checkin / reuse
# ---------------------------------------------------------------------------


async def test_checkout_miss_spawns_a_fresh_worker(config):
    pool = SandboxWorkerPool()
    try:
        worker, reused = await checkout(pool, cache_key(config), config)
        assert reused is False
        assert worker.is_running()
        assert isinstance(worker.worker_pid, int)
    finally:
        await pool.aclose()


async def test_checkin_then_checkout_reuses_the_same_process(config):
    pool = SandboxWorkerPool()
    try:
        key = cache_key(config)
        worker, _ = await checkout(pool, key, config)
        pid = worker.worker_pid
        assert await pool.checkin(key, worker, project_name=PROJECT,
                                 entry_key="entry1") is True
        assert pool.idle_count() == 1
        worker2, reused = await checkout(pool, key, config)
        assert reused is True
        assert worker2 is worker
        assert worker2.worker_pid == pid
        assert pool.idle_count() == 0
    finally:
        await pool.aclose()


async def test_a_reused_worker_still_parses(config):
    """The warm path end to end: load on run 1, reuse on run 2."""
    pool = SandboxWorkerPool()
    try:
        key = cache_key(config)
        worker, _ = await checkout(pool, key, config)
        first = await parse(worker, "membaca", "run-1")
        assert first["parse"]["outcome"] == "parsed"
        assert await pool.checkin(key, worker, project_name=PROJECT,
                                 entry_key="entry1") is True
        worker2, reused = await checkout(pool, key, config)
        assert reused is True
        second = await parse(worker2, "baca", "run-2")
        assert second["parse"]["outcome"] == "parsed"
    finally:
        await pool.aclose()


async def test_concurrent_checkouts_of_one_key_get_distinct_workers(config):
    """F-13: checkout is exclusive -- no sharing a live worker."""
    pool = SandboxWorkerPool()
    try:
        key = cache_key(config)
        (w1, r1), (w2, r2) = await asyncio.gather(
            checkout(pool, key, config), checkout(pool, key, config))
        assert r1 is False and r2 is False
        assert w1 is not w2
        assert w1.worker_pid != w2.worker_pid
        # Both check back in; the pool now holds two idle workers.
        assert await pool.checkin(key, w1, project_name=PROJECT,
                                 entry_key="entry1") is True
        assert await pool.checkin(key, w2, project_name=PROJECT,
                                 entry_key="entry1") is True
        assert pool.idle_count() == 2
    finally:
        await pool.aclose()


# ---------------------------------------------------------------------------
# the key: a worker can never serve a grammar it did not load
# ---------------------------------------------------------------------------


async def test_changed_parameters_are_a_miss(config):
    pool = SandboxWorkerPool()
    try:
        key1 = cache_key(config, {"max_roots": 3})
        key2 = cache_key(config, {"max_roots": 4})
        assert key1 != key2
        worker, _ = await checkout(pool, key1, config)
        assert await pool.checkin(key1, worker, project_name=PROJECT,
                                 entry_key="entry1") is True
        worker2, reused = await checkout(pool, key2, config)
        assert reused is False and worker2 is not worker
    finally:
        await pool.aclose()


async def test_an_engine_dir_change_is_a_miss(config):
    pool = SandboxWorkerPool()
    try:
        key_a = compute_pool_key(kind="cache", entry_key="entry1",
                                 parameters={}, engine_dir="/fw/9.1", stub=True)
        key_b = compute_pool_key(kind="cache", entry_key="entry1",
                                 parameters={}, engine_dir="/fw/9.2", stub=True)
        assert key_a != key_b
        worker, _ = await checkout(pool, key_a, config)
        assert await pool.checkin(key_a, worker, project_name=PROJECT,
                                 entry_key="entry1") is True
        worker2, reused = await checkout(pool, key_b, config)
        assert reused is False
        assert worker2.worker_pid != worker.worker_pid
    finally:
        await pool.aclose()


async def test_a_parse_delay_change_is_a_miss(config):
    pool = SandboxWorkerPool()
    try:
        key_a = compute_pool_key(kind="cache", entry_key="entry1",
                                 parameters={}, parse_delay=0.0, stub=True)
        key_b = compute_pool_key(kind="cache", entry_key="entry1",
                                 parameters={}, parse_delay=2.5, stub=True)
        assert key_a != key_b
        worker, _ = await checkout(pool, key_a, config)
        assert await pool.checkin(key_a, worker, project_name=PROJECT,
                                 entry_key="entry1") is True
        worker2, reused = await checkout(pool, key_b, config)
        assert reused is False
        assert worker2.worker_pid != worker.worker_pid
    finally:
        await pool.aclose()


async def test_an_edited_named_config_is_a_miss(config):
    """Named sandboxes are user-editable in place: the key carries the
    file's mtime/size, so an edit can never reuse a stale grammar."""
    pool = SandboxWorkerPool()
    try:
        key1 = compute_pool_key(kind="named", config_path=str(config),
                                parameters={}, stub=True)
        worker, _ = await checkout(pool, key1, config)
        assert await pool.checkin(key1, worker, project_name=PROJECT) is True
        # Touch the config the way a user edit would (new mtime).
        config.write_text(json.dumps({"words": {"new": []}}), encoding="utf-8")
        key2 = compute_pool_key(kind="named", config_path=str(config),
                                parameters={}, stub=True)
        assert key2 != key1
        worker2, reused = await checkout(pool, key2, config)
        assert reused is False and worker2 is not worker
    finally:
        await pool.aclose()


async def test_stub_flag_is_part_of_the_key(config, monkeypatch):
    k_stub = compute_pool_key(kind="cache", entry_key="e", parameters={},
                              stub=True)
    k_real = compute_pool_key(kind="cache", entry_key="e", parameters={},
                              stub=False)
    assert k_stub != k_real
    pool = SandboxWorkerPool()
    try:
        worker, _ = await checkout(pool, k_stub, config)
        assert await pool.checkin(k_stub, worker, project_name=PROJECT,
                                 entry_key="e") is True

        def boom(*args, **kwargs):
            raise AssertionError("a stub worker must never serve a real run")

        monkeypatch.setattr(pool_mod, "_worker_client_class",
                            lambda: boom)
        with pytest.raises(AssertionError):
            await pool.checkout(k_real, project_name=PROJECT,
                                spawn=spawn_for(config), stub=False)
    finally:
        await pool.aclose()


# ---------------------------------------------------------------------------
# eviction
# ---------------------------------------------------------------------------


async def test_evict_project_drops_only_that_project(config):
    pool = SandboxWorkerPool()
    try:
        key_a = compute_pool_key(kind="cache", entry_key="entry-a",
                                 parameters={}, stub=True)
        key_b = compute_pool_key(kind="cache", entry_key="entry-b",
                                 parameters={}, stub=True)
        worker, _ = await checkout(pool, key_a, config)
        assert await pool.checkin(key_a, worker, project_name="A",
                                 entry_key="entry-a") is True
        worker_b, _ = await checkout(pool, key_b, config)
        assert worker_b is not worker
        assert await pool.checkin(key_b, worker_b, project_name="B",
                                 entry_key="entry-b") is True
        assert pool.idle_count() == 2
        pool.evict_project("A")
        assert pool.idle_count() == 1
        assert await wait_for(lambda: not worker.is_running()), \
            "evicted worker is reaped"
        assert worker_b.is_running()
        # B's worker is still there for reuse.
        worker2, reused = await checkout(pool, key_b, config)
        assert reused is True and worker2 is worker_b
    finally:
        await pool.aclose()


async def test_double_checkin_of_one_worker_is_refused(config):
    pool = SandboxWorkerPool()
    try:
        key = cache_key(config)
        worker, _ = await checkout(pool, key, config)
        assert await pool.checkin(key, worker, project_name=PROJECT,
                                 entry_key="entry1") is True
        # The same worker object checked in again: refused, so one process
        # can never be handed to two runs at once (F-13).
        assert await pool.checkin(key, worker, project_name=PROJECT,
                                 entry_key="entry1") is False
        assert pool.idle_count() == 1
    finally:
        await pool.aclose()


async def test_evict_keys_drops_pruned_entries(config):
    pool = SandboxWorkerPool()
    try:
        key1 = compute_pool_key(kind="cache", entry_key="gone",
                                parameters={}, stub=True)
        key2 = compute_pool_key(kind="cache", entry_key="kept",
                                parameters={}, stub=True)
        w1, _ = await checkout(pool, key1, config)
        w2, _ = await checkout(pool, key2, config)
        assert await pool.checkin(key1, w1, project_name=PROJECT,
                                 entry_key="gone") is True
        assert await pool.checkin(key2, w2, project_name=PROJECT,
                                 entry_key="kept") is True
        pool.evict_keys({"gone"})
        assert pool.idle_count() == 1
        assert await wait_for(lambda: not w1.is_running())
        assert w2.is_running()
    finally:
        await pool.aclose()


async def test_cache_notifications_reach_live_pools(config):
    """`cache.invalidate`/`cache.prune` fan out through the pool registry."""
    pool = SandboxWorkerPool()
    try:
        key = cache_key(config)
        worker, _ = await checkout(pool, key, config)
        assert await pool.checkin(key, worker, project_name=PROJECT,
                                 entry_key="entry1") is True
        notify_project_invalidated(PROJECT)
        assert await wait_for(lambda: pool.idle_count() == 0)
        assert await wait_for(lambda: not worker.is_running())

        worker2, _ = await checkout(pool, key, config)
        assert await pool.checkin(key, worker2, project_name=PROJECT,
                                 entry_key="entry1") is True
        notify_keys_pruned(["entry1"])
        assert await wait_for(lambda: pool.idle_count() == 0)
        assert await wait_for(lambda: not worker2.is_running())
    finally:
        await pool.aclose()


# ---------------------------------------------------------------------------
# health: only healthy workers are handed out or kept
# ---------------------------------------------------------------------------


async def test_a_dead_pooled_worker_is_discarded_never_handed_out(config):
    pool = SandboxWorkerPool()
    try:
        key = cache_key(config)
        worker, _ = await checkout(pool, key, config)
        assert await pool.checkin(key, worker, project_name=PROJECT,
                                 entry_key="entry1") is True
        await worker.terminate()
        assert await wait_for(lambda: not worker.is_running())
        worker2, reused = await checkout(pool, key, config)
        assert reused is False
        assert worker2 is not worker and worker2.is_running()
        assert pool.idle_count() == 0
    finally:
        await pool.aclose()


async def test_checkin_refuses_a_dead_worker(config):
    pool = SandboxWorkerPool()
    try:
        key = cache_key(config)
        worker, _ = await checkout(pool, key, config)
        await worker.terminate()
        assert await wait_for(lambda: not worker.is_running())
        assert await pool.checkin(key, worker, project_name=PROJECT,
                                 entry_key="entry1") is False
        assert pool.idle_count() == 0
    finally:
        await pool.aclose()


async def test_checkin_refuses_a_worker_with_requests_in_flight(config, tmp_path):
    # A word that sleeps in the stub engine, so the request stays in flight.
    slow_config = tmp_path / "slow-config.json"
    slow_config.write_text(json.dumps({"words": {"slow": {"sleep": 30}}}),
                           encoding="utf-8")
    pool = SandboxWorkerPool()
    try:
        key = cache_key(slow_config)
        worker, _ = await checkout(pool, key, slow_config)
        pending = asyncio.ensure_future(parse(worker, "slow", "run-9"))
        assert await wait_for(lambda: worker.has_pending_requests)
        assert await pool.checkin(key, worker, project_name=PROJECT,
                                 entry_key="entry1") is False
        assert pool.idle_count() == 0
        # The worker still answers its in-flight request afterwards.
        answer = await pending
        assert answer["parse"]["outcome"] == "parsed"
    finally:
        await pool.aclose()


async def test_idle_timeout_reaps_unused_workers(config):
    pool = SandboxWorkerPool(idle_timeout=0.2, sweep_interval=0.05)
    try:
        key = cache_key(config)
        worker, _ = await checkout(pool, key, config)
        assert await pool.checkin(key, worker, project_name=PROJECT,
                                 entry_key="entry1") is True
        assert await wait_for(lambda: pool.idle_count() == 0, timeout=10.0)
        assert not worker.is_running()
    finally:
        await pool.aclose()


async def test_aclose_reaps_everything_and_is_idempotent(config):
    pool = SandboxWorkerPool()
    key = cache_key(config)
    worker, _ = await checkout(pool, key, config)
    assert await pool.checkin(key, worker, project_name=PROJECT,
                             entry_key="entry1") is True
    await pool.aclose()
    assert pool.idle_count() == 0
    assert not worker.is_running()
    await pool.aclose()  # second close is a no-op
    # A closed pool still serves, it just never pools.
    worker2, reused = await checkout(pool, key, config)
    assert reused is False and worker2.is_running()
    await worker2.aclose()


# ---------------------------------------------------------------------------
# hand-over hygiene: no diagnostic leaks between runs
# ---------------------------------------------------------------------------


async def test_handover_resets_sink_and_listeners(config):
    pool = SandboxWorkerPool()
    try:
        key = cache_key(config)
        worker, _ = await checkout(pool, key, config)
        seen = []
        worker.set_stderr_sink(seen.append)
        worker.listen_to_run("run-1", lambda message: None)
        assert worker._stderr_sink is not None
        assert len(worker._run_listeners) == 1
        assert await pool.checkin(key, worker, project_name=PROJECT,
                                 entry_key="entry1") is True
        assert worker._stderr_sink is None
        assert worker._run_listeners == {}
        worker2, reused = await checkout(pool, key, config)
        assert reused is True and worker2 is worker
        assert worker2._stderr_sink is None
        assert worker2._run_listeners == {}
    finally:
        await pool.aclose()
