#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lifecycle tests for the sandbox spine (parser-check CP5, T059): FR-025,
SC-007; data-model section 1 (the three lifecycles and their invariant).

WHAT THESE TESTS SPECIFY
------------------------
SC-007. No cache operation changes a user-owned file. Around a sandbox made
  by `store.create_sandbox` and a corpus file at `paths.corpus_path`, every
  file under `sandboxes/` and `corpora/` keeps its bytes AND mtime across:
    - `cache.invalidate(project)`;
    - a rebuild (`cache.ensure_entry` after invalidation, and after a
      project change that gives a new key);
    - `cache.prune(project)` (US6, T085 -- xfail until it exists).

THE DELETER INVARIANT (AST, over `sandbox/cache.py` and `sandbox/workdir.py`)
  A "raw deleter" is a call to shutil.rmtree, os.remove, os.unlink, os.rmdir,
  or a `.unlink()` / `.rmdir()` method. A function holding one must either
    (a) call `paths.assert_under(<target>, paths.config_cache_root())` or
        `..., paths.work_root())` itself, or
    (b) be a private seam every one of whose in-module callers does (a).
  Every `assert_under` call there names `config_cache_root()` or
  `work_root()` as its root, never another area.

NO FUNCTION THERE ACCEPTS A USER-OWNED PATH
  - workdir.delete(<path under sandboxes/ or corpora/>) raises
    paths.SandboxPathError and touches nothing;
  - cache._remove_tree / cache._remove_file likewise;
  - cache.build_entry / cache.ensure_entry refuse a `work_dir` or `log_dir`
    under sandboxes/ or corpora/ with paths.SandboxPathError, BEFORE the
    script runs (both are write targets: the script copies the project into
    WorkDir, and the generation log is written into log_dir).
"""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pytest

from flextoolsmcp.server.parse import record
from flextoolsmcp.server.sandbox import cache, paths, workdir

try:  # tests/ is on sys.path under pytest's default (prepend) import mode
    from test_sandbox_cache import EmulatedScript, _work_dir
except ImportError:  # pragma: no cover
    from tests.test_sandbox_cache import EmulatedScript, _work_dir

SANDBOX_PKG = Path(__file__).resolve().parent.parent / "src" / "flextoolsmcp" / "server" / "sandbox"
GUARDED_MODULES = ("cache.py", "workdir.py")
ALLOWED_ROOTS = {"config_cache_root", "work_root"}

CORPUS = {
    "schema": "flextoolsmcp.hc-corpus/1",
    "name": "baseline",
    "project": "FakeProj",
    "created_at": "2026-09-24T00:00:00.000Z",
    "seeded_from": {"run_id": "0" * 32, "config_source": {"kind": "project_cache"}},
    "assertions": [{"word": "xyz", "expected": []}],
}


@pytest.fixture(autouse=True)
def _fresh_cache_state():
    yield
    cache.reset_state()


def _store():
    import importlib

    try:
        return importlib.import_module("flextoolsmcp.server.sandbox.store")
    except ImportError as exc:  # pragma: no cover - until T061 lands
        pytest.fail("flextoolsmcp.server.sandbox.store is missing: %s" % exc)


async def _ensure(project, fake_generator, runner=None):
    return await cache.ensure_entry(
        project.name, project.fwdata, fake_generator.path,
        work_dir=_work_dir(), run_script=runner or EmulatedScript())


def _bump_mtime(path: Path, seconds: int = 5) -> None:
    st = Path(path).stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + seconds * 1_000_000_000))


def _user_files(root: Path) -> dict:
    """{area/relative path: (bytes, mtime_ns)} for sandboxes/ and corpora/."""
    out = {}
    for area in ("sandboxes", "corpora"):
        base = root / area
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file():
                out[area + "/" + p.relative_to(base).as_posix()] = (
                    p.read_bytes(), p.stat().st_mtime_ns)
    return out


async def _user_owned(project, fake_generator):
    """A cache entry, an edited sandbox made from it, and a corpus file."""
    store = _store()
    entry = await _ensure(project, fake_generator)
    config = Path(store.create_sandbox(project.name, "keep-me", entry)["path"])
    config.write_bytes(config.read_bytes() + b"\n<!-- user edit -->\n")
    corpus = paths.corpus_path(project.name, "baseline")
    corpus.parent.mkdir(parents=True, exist_ok=True)
    corpus.write_text(json.dumps(CORPUS, indent=2), encoding="utf-8")
    return entry, config, corpus


# --------------------------------------------------------------------------
# SC-007: cache operations leave user-owned bytes identical
# --------------------------------------------------------------------------

async def test_invalidate_leaves_sandbox_and_corpus_identical(
        sandbox_root, fake_project, fake_generator):
    entry, config, corpus = await _user_owned(fake_project, fake_generator)
    before = _user_files(sandbox_root)
    assert len(before) == 3  # hc-config.xml, origin.json, the corpus
    assert cache.invalidate(fake_project.name) >= 1
    assert cache.lookup(fake_project.name, entry.key, touch=False) is None
    assert _user_files(sandbox_root) == before


async def test_rebuild_leaves_sandbox_and_corpus_identical(
        sandbox_root, fake_project, fake_generator):
    entry, config, corpus = await _user_owned(fake_project, fake_generator)
    before = _user_files(sandbox_root)

    cache.invalidate(fake_project.name)
    rebuilt = await _ensure(fake_project, fake_generator)
    assert rebuilt.built is True and rebuilt.key == entry.key
    assert _user_files(sandbox_root) == before

    _bump_mtime(fake_project.fwdata)
    newer = await _ensure(fake_project, fake_generator)
    assert newer.built is True and newer.key != entry.key
    assert _user_files(sandbox_root) == before


async def test_rebuild_after_failed_generation_leaves_user_files(
        sandbox_root, fake_project, fake_generator):
    await _user_owned(fake_project, fake_generator)
    before = _user_files(sandbox_root)
    _bump_mtime(fake_project.fwdata)
    fake_generator.set(mode="crash")
    with pytest.raises(cache.ParserConfigFailed):
        await _ensure(fake_project, fake_generator)
    assert _user_files(sandbox_root) == before


@pytest.mark.xfail(condition=not hasattr(cache, "prune"), strict=False,
                   reason="US6 T085: cache.prune is not implemented yet")
async def test_prune_leaves_sandbox_and_corpus_identical(
        sandbox_root, fake_project, fake_generator):
    await _user_owned(fake_project, fake_generator)
    # More entries than the prune keeps (3 per project), plus an invalidated one.
    for _ in range(4):
        _bump_mtime(fake_project.fwdata)
        await _ensure(fake_project, fake_generator)
    cache.invalidate(fake_project.name)
    before = _user_files(sandbox_root)
    cache.prune(fake_project.name)
    assert _user_files(sandbox_root) == before


# --------------------------------------------------------------------------
# No function in cache.py / workdir.py accepts a user-owned path
# --------------------------------------------------------------------------

@pytest.mark.parametrize("area", ["sandboxes", "corpora"])
async def test_workdir_delete_refuses_user_owned(
        sandbox_root, fake_project, fake_generator, area):
    _entry, config, corpus = await _user_owned(fake_project, fake_generator)
    before = _user_files(sandbox_root)
    targets = [config.parent, config] if area == "sandboxes" else [corpus, corpus.parent]
    targets.append(sandbox_root / area)
    for target in targets:
        with pytest.raises(paths.SandboxPathError):
            workdir.delete(target)
    assert _user_files(sandbox_root) == before


@pytest.mark.parametrize("area", ["sandboxes", "corpora"])
async def test_cache_removers_refuse_user_owned(
        sandbox_root, fake_project, fake_generator, area):
    _entry, config, corpus = await _user_owned(fake_project, fake_generator)
    before = _user_files(sandbox_root)
    tree = config.parent if area == "sandboxes" else corpus.parent
    file = config if area == "sandboxes" else corpus
    with pytest.raises(paths.SandboxPathError):
        cache._remove_tree(tree)
    with pytest.raises(paths.SandboxPathError):
        cache._remove_file(file)
    assert _user_files(sandbox_root) == before


def _user_dir(project_name: str, area: str) -> Path:
    base = paths.sandboxes_dir(project_name) if area == "sandboxes" else paths.corpora_dir(
        project_name)
    target = base / "not-a-work-dir"
    target.mkdir(parents=True, exist_ok=True)
    return target


@pytest.mark.parametrize("param", ["work_dir", "log_dir"])
@pytest.mark.parametrize("area", ["sandboxes", "corpora"])
async def test_build_refuses_user_owned_write_targets(
        sandbox_root, fake_project, fake_generator, area, param):
    await _user_owned(fake_project, fake_generator)
    _bump_mtime(fake_project.fwdata)  # a key with no entry: a build would run
    target = _user_dir(fake_project.name, area)
    before = _user_files(sandbox_root)
    runner = EmulatedScript()
    kwargs = {"work_dir": _work_dir(), "run_script": runner, param: target}
    with pytest.raises(paths.SandboxPathError):
        await cache.ensure_entry(
            fake_project.name, fake_project.fwdata, fake_generator.path, **kwargs)
    assert runner.calls == []
    assert list(target.iterdir()) == []
    assert _user_files(sandbox_root) == before

    inputs = cache.key_inputs(fake_project.fwdata, fake_generator.path)
    kwargs = {"work_dir": _work_dir(), "run_script": runner, param: target}
    with pytest.raises(paths.SandboxPathError):
        await cache.build_entry(fake_project.name, inputs, **kwargs)
    assert runner.calls == []
    assert list(target.iterdir()) == []
    assert _user_files(sandbox_root) == before


def test_workdir_create_never_lands_outside_work(sandbox_root):
    made = workdir.create(record.new_run_id(), source_fwdata=sandbox_root / "x.fwdata")
    assert paths.is_under(made, paths.work_root())


# --------------------------------------------------------------------------
# AST: every deleter in cache.py / workdir.py guards its root
# --------------------------------------------------------------------------

_RAW_METHODS = {"unlink", "rmdir"}
_RAW_QUALIFIED = {("shutil", "rmtree"), ("os", "remove"), ("os", "unlink"),
                  ("os", "rmdir"), ("os", "removedirs")}


def _functions(tree):
    return {node.name: node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _calls(fn):
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call)]


def _call_name(call):
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _is_raw_delete(call):
    func = call.func
    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name) and (func.value.id, func.attr) in _RAW_QUALIFIED:
            return True
        if func.attr in _RAW_METHODS:
            return True
    return False


def _guard_roots(fn):
    """The root-helper names each `assert_under(...)` call in fn passes."""
    roots = []
    for call in _calls(fn):
        if _call_name(call) != "assert_under":
            continue
        root = call.args[1] if len(call.args) > 1 else next(
            (k.value for k in call.keywords if k.arg == "root"), None)
        roots.append(_call_name(root) if isinstance(root, ast.Call) else None)
    return roots


@pytest.mark.parametrize("module", GUARDED_MODULES)
def test_every_deleter_guards_its_root(module):
    tree = ast.parse((SANDBOX_PKG / module).read_text(encoding="utf-8"))
    funcs = _functions(tree)

    raw = {name for name, fn in funcs.items() if any(_is_raw_delete(c) for c in _calls(fn))}
    assert raw, "%s: expected at least one deleter to check" % module
    guarded = {name for name, fn in funcs.items() if _guard_roots(fn)}

    problems = []
    for name, fn in funcs.items():
        roots = _guard_roots(fn)
        for root in roots:
            if root not in ALLOWED_ROOTS:
                problems.append("%s: assert_under root %r is not config-cache/ or work/"
                                % (name, root))
    for name in sorted(raw - guarded):
        # A private seam: every in-module caller must guard.
        callers = [caller for caller, fn in funcs.items()
                   if caller != name and any(_call_name(c) == name for c in _calls(fn))]
        if not name.startswith("_"):
            problems.append("%s deletes without assert_under" % name)
        elif not callers:
            problems.append("%s deletes without assert_under and has no caller" % name)
        else:
            for caller in callers:
                if caller not in guarded:
                    problems.append("%s calls unguarded deleter %s without assert_under"
                                    % (caller, name))
    assert problems == [], "%s:\n  %s" % (module, "\n  ".join(problems))


@pytest.mark.parametrize("module", GUARDED_MODULES)
def test_no_reference_to_user_owned_areas(module):
    """cache.py and workdir.py never name the user-owned areas' roots."""
    tree = ast.parse((SANDBOX_PKG / module).read_text(encoding="utf-8"))
    banned = {"sandboxes_root", "corpora_root", "sandboxes_dir", "corpora_dir",
              "sandbox_dir", "corpus_path", "SANDBOXES", "CORPORA"}
    hits = sorted({(node.lineno, node.attr) for node in ast.walk(tree)
                   if isinstance(node, ast.Attribute) and node.attr in banned}
                  | {(node.lineno, node.id) for node in ast.walk(tree)
                     if isinstance(node, ast.Name) and node.id in banned})
    assert hits == []
