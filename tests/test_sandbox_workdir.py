"""parser-check CP5 T036: sandbox/workdir.py -- the per-run project copy's home
(FR-008, FR-011, FR-042; research R-11; data-model sections 1-2).

`workdir.py` does NOT copy: the PowerShell script copies the allowlist into
`-WorkDir`. It measures the allowlist, makes `work/<run_id>/` with its marker,
and deletes it (with retries and a root guard), reporting the cleanup.

API specified here (T045 implements it; T084 later adds the free-space check
and the marker sweep):

    workdir.MARKER_NAME           == ".flextoolsmcp-sandbox-work"
    workdir.ALLOWLIST_DIRS        == ("WritingSystemStore",)
    workdir.DELETE_RETRIES        == 3      # up to 1 + 3 attempts
    workdir.DELETE_RETRY_SECONDS  == 0.2    # patchable; tests set 0
    workdir.CLEANUP_DELETED / CLEANUP_FAILED / CLEANUP_NOT_MADE
                                  == "deleted" / "failed" / "not_made"
    workdir._rmtree(path)         the single delete seam (patchable)

    workdir.measure_allowlist(fwdata) -> AllowlistMeasure
        fwdata is `<project_dir>/<name>.fwdata`; raises FileNotFoundError
        when it is missing. Allowlist = that file + every file under
        `<project_dir>/WritingSystemStore/` (recursive). Nothing else.
    AllowlistMeasure (frozen): fwdata: Path, project_dir: Path,
        files: List[str]   # relative to project_dir, '/'-separated, sorted
        total_bytes: int   # sum of those files' sizes

    workdir.create(run_id, *, source_fwdata, pid=None) -> Path
        makes `paths.work_dir(run_id)` (parents too; FileExistsError if it
        exists) holding MARKER_NAME = JSON {"run_id", "pid", "created_at",
        "source_fwdata"} (pid defaults to os.getpid(); created_at ISO-8601
        UTC ending "Z"; source_fwdata the absolute path as str). Returns the
        directory's real path. A bad run id raises paths.SandboxPathError and
        a root inside a project raises ArtifactInsideProject -- nothing made.
    workdir.read_marker(directory) -> Optional[dict]   # None if absent/bad

    workdir.delete(target) -> CleanupResult
        refuses (paths.SandboxPathError, nothing touched) unless `target` is
        strictly under `paths.work_root()`; a missing target is `not_made`;
        otherwise `_rmtree` with DELETE_RETRIES retries DELETE_RETRY_SECONDS
        apart on OSError, then `deleted` or `failed` with the path.
    CleanupResult (frozen): cleanup: str, path_if_failed: Optional[str],
        attempts: int;  .as_dict() -> {"cleanup", "path_if_failed"}
        (the run meta's `copy` fields, data-model 6.2).

T081 (US6; T084 implements):

    workdir.check_free_space(fwdata, *, measure=None) -> Optional[SpaceShortfall]
        FR-012: None when the `work/` volume has at least 2x the ALLOWLIST's
        total_bytes free (via `backup.disk_space_ok`, looked up at call
        time, on the nearest existing ancestor of `paths.work_root()`; an
        unmeasurable volume fails open). Creates no directory. `measure`
        reuses an AllowlistMeasure already taken.
    SpaceShortfall (frozen): needed_bytes: int (= 2 x total_bytes),
        free_bytes: int

    workdir.sweep(live_run_ids: Iterable[str]) -> List[Path]
        FR-011: removes (via `delete`) each direct child of `work/` that
        holds a readable marker and whose run id (directory name or marker
        run_id) is not live; returns the removed paths. Unmarked dirs, live
        runs, plain files and anything outside `work/` are left alone; a
        missing `work/` root returns [] and is not created. A child that
        will not delete stays (and is not listed).
"""

import importlib
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import pytest

from flextoolsmcp.server.filing import paths as filing_paths
from flextoolsmcp.server.parse import record
from flextoolsmcp.server.sandbox import paths as sp


def _workdir():
    return importlib.import_module("flextoolsmcp.server.sandbox.workdir")


@pytest.fixture
def projects_dir(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    projects.mkdir(exist_ok=True)
    monkeypatch.setattr(filing_paths, "projects_directory", lambda: projects)
    return projects


class _LazyModule:
    """Imports the module under test on first use, so a missing module fails
    inside each test body (ImportError), not at fixture setup. Attribute
    sets and deletes are forwarded, so monkeypatch works through it."""

    def __init__(self, name, on_load):
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_on_load", on_load)
        object.__setattr__(self, "_mod", None)

    def _load(self):
        mod = object.__getattribute__(self, "_mod")
        if mod is None:
            mod = importlib.import_module(object.__getattribute__(self, "_name"))
            object.__setattr__(self, "_mod", mod)
            object.__getattribute__(self, "_on_load")(mod)
        return mod

    def __getattr__(self, attr):
        return getattr(self._load(), attr)

    def __setattr__(self, attr, value):
        setattr(self._load(), attr, value)

    def __delattr__(self, attr):
        delattr(self._load(), attr)


@pytest.fixture
def workdir(monkeypatch, sandbox_root, projects_dir):
    return _LazyModule(
        "flextoolsmcp.server.sandbox.workdir",
        lambda mod: monkeypatch.setattr(mod, "DELETE_RETRY_SECONDS", 0),
    )


def _populate(directory: Path):
    (directory / "Proj").mkdir()
    (directory / "Proj" / "Proj.fwdata").write_text("<languageproject />", encoding="utf-8")
    (directory / "Proj" / "WritingSystemStore").mkdir()
    (directory / "Proj" / "WritingSystemStore" / "en.ldml").write_text("<ldml />", encoding="utf-8")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_constants():
    workdir = _workdir()
    assert workdir.MARKER_NAME == ".flextoolsmcp-sandbox-work"
    assert workdir.ALLOWLIST_DIRS == ("WritingSystemStore",)
    assert workdir.DELETE_RETRIES == 3
    assert workdir.DELETE_RETRY_SECONDS == 0.2
    assert (workdir.CLEANUP_DELETED, workdir.CLEANUP_FAILED, workdir.CLEANUP_NOT_MADE) == (
        "deleted",
        "failed",
        "not_made",
    )


# ---------------------------------------------------------------------------
# Allowlist measure (FR-008)
# ---------------------------------------------------------------------------


def test_allowlist_measure(workdir, fake_project):
    measure = workdir.measure_allowlist(fake_project.fwdata)
    assert measure.fwdata == fake_project.fwdata
    assert measure.project_dir == fake_project.dir
    assert measure.files == [
        "FakeProj.fwdata",
        "WritingSystemStore/en.ldml",
        "WritingSystemStore/seh.ldml",
    ]
    expected = sum((fake_project.dir / f).stat().st_size for f in measure.files)
    assert measure.total_bytes == expected


def test_allowlist_excludes_everything_else(workdir, fake_project):
    d = fake_project.dir
    (d / "FakeProj.fwdata.bak").write_text("old", encoding="utf-8")
    (d / "ConfigurationSettings").mkdir()
    (d / "ConfigurationSettings" / "x.fwlayout").write_text("x", encoding="utf-8")
    (d / "notes.txt").write_text("x", encoding="utf-8")
    measure = workdir.measure_allowlist(fake_project.fwdata)
    for name in measure.files:
        assert not name.endswith(".lock")
        top = name.split("/", 1)[0]
        assert top in ("FakeProj.fwdata", "WritingSystemStore")
    for excluded in fake_project.excluded:
        rel = excluded.relative_to(d).as_posix()
        assert not any(f == rel or f.startswith(rel + "/") for f in measure.files)
    assert "FakeProj.fwdata.bak" not in measure.files
    assert "notes.txt" not in measure.files


def test_allowlist_recurses_into_writing_system_store(workdir, fake_project):
    nested = fake_project.writing_systems / "sub" / "deeper"
    nested.mkdir(parents=True)
    (nested / "x.ldml").write_text("12345", encoding="utf-8")
    measure = workdir.measure_allowlist(fake_project.fwdata)
    assert "WritingSystemStore/sub/deeper/x.ldml" in measure.files
    assert measure.files == sorted(measure.files)


def test_allowlist_without_writing_system_store(workdir, fake_project):
    import shutil

    shutil.rmtree(fake_project.writing_systems)
    measure = workdir.measure_allowlist(fake_project.fwdata)
    assert measure.files == ["FakeProj.fwdata"]
    assert measure.total_bytes == fake_project.fwdata.stat().st_size


def test_allowlist_name_with_a_space(workdir, fake_project_factory):
    project = fake_project_factory("Sena 3")
    measure = workdir.measure_allowlist(project.fwdata)
    assert measure.files[0] == "Sena 3.fwdata"


def test_allowlist_missing_fwdata_raises(workdir, tmp_path):
    with pytest.raises(FileNotFoundError):
        workdir.measure_allowlist(tmp_path / "projects" / "Gone" / "Gone.fwdata")


def test_measure_writes_nothing(workdir, fake_project):
    before = sorted((p, p.stat().st_mtime_ns) for p in fake_project.dir.rglob("*"))
    workdir.measure_allowlist(fake_project.fwdata)
    after = sorted((p, p.stat().st_mtime_ns) for p in fake_project.dir.rglob("*"))
    assert after == before


# ---------------------------------------------------------------------------
# create: work/<run_id>/ with its marker
# ---------------------------------------------------------------------------


def test_create_makes_work_dir_with_marker(workdir, fake_project):
    run_id = record.new_run_id()
    made = workdir.create(run_id, source_fwdata=fake_project.fwdata)
    assert made == sp.work_dir(run_id)
    assert made.is_dir()
    assert [p.name for p in made.iterdir()] == [workdir.MARKER_NAME]
    marker = json.loads((made / workdir.MARKER_NAME).read_text(encoding="utf-8"))
    assert set(marker) == {"run_id", "pid", "created_at", "source_fwdata"}
    assert marker["run_id"] == run_id
    assert marker["pid"] == os.getpid()
    assert marker["source_fwdata"] == str(Path(os.path.abspath(fake_project.fwdata)))
    assert marker["created_at"].endswith("Z")
    datetime.strptime(marker["created_at"][:19], "%Y-%m-%dT%H:%M:%S")
    assert workdir.read_marker(made) == marker


def test_create_records_an_explicit_pid(workdir, fake_project):
    made = workdir.create(record.new_run_id(), source_fwdata=fake_project.fwdata, pid=4242)
    assert workdir.read_marker(made)["pid"] == 4242


def test_create_removes_its_directory_when_the_marker_write_fails(workdir, fake_project,
                                                                   monkeypatch):
    """Pattern audit sweep 2: an unmarked dir would escape the startup sweep."""
    run_id = record.new_run_id()
    real_write_text = Path.write_text

    def failing_write_text(self, *args, **kwargs):
        if self.name == workdir.MARKER_NAME:
            raise OSError(28, "No space left on device")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", failing_write_text)
    with pytest.raises(OSError, match="No space"):
        workdir.create(run_id, source_fwdata=fake_project.fwdata)
    assert not sp.work_dir(run_id).exists()
    assert sp.work_root().is_dir()  # only the run's own directory went


def test_read_marker_absent_or_corrupt(workdir, tmp_path):
    assert workdir.read_marker(tmp_path) is None
    (tmp_path / _workdir().MARKER_NAME).write_text("{not json", encoding="utf-8")
    assert workdir.read_marker(tmp_path) is None


def test_create_twice_is_refused(workdir, fake_project):
    run_id = record.new_run_id()
    workdir.create(run_id, source_fwdata=fake_project.fwdata)
    with pytest.raises(FileExistsError):
        workdir.create(run_id, source_fwdata=fake_project.fwdata)


@pytest.mark.parametrize("bad", ["", "..", "../escape", "not-a-run-id", "A" * 32])
def test_create_refuses_a_bad_run_id(workdir, fake_project, sandbox_root, bad):
    with pytest.raises(sp.SandboxPathError):
        workdir.create(bad, source_fwdata=fake_project.fwdata)
    assert list(sandbox_root.rglob("*")) == []


def test_copy_root_is_outside_the_project(workdir, fake_project, projects_dir):
    made = workdir.create(record.new_run_id(), source_fwdata=fake_project.fwdata)
    assert not sp.is_under(made, fake_project.dir, strict=False)
    assert not sp.is_under(made, projects_dir, strict=False)
    assert sp.is_under(made, sp.work_root())
    filing_paths.assert_outside_project(made)


def test_create_refuses_a_root_inside_a_project(workdir, fake_project, monkeypatch):
    inside = fake_project.dir / "parse-root"
    monkeypatch.setenv(sp.ENV_VAR, str(inside))
    with pytest.raises(filing_paths.ArtifactInsideProject):
        workdir.create(record.new_run_id(), source_fwdata=fake_project.fwdata)
    assert not inside.exists()


# ---------------------------------------------------------------------------
# delete: retries, cleanup report, root guard (FR-011, data-model 1)
# ---------------------------------------------------------------------------


def test_delete_removes_everything(workdir, fake_project, sandbox_root):
    made = workdir.create(record.new_run_id(), source_fwdata=fake_project.fwdata)
    _populate(made)
    result = workdir.delete(made)
    assert result.cleanup == workdir.CLEANUP_DELETED
    assert result.path_if_failed is None
    assert result.attempts == 1
    assert result.as_dict() == {"cleanup": "deleted", "path_if_failed": None}
    assert not made.exists()
    assert list(sp.work_root().iterdir()) == []


def test_delete_of_a_missing_dir_is_not_made(workdir, sandbox_root):
    target = sp.work_dir(record.new_run_id())
    result = workdir.delete(target)
    assert result.cleanup == workdir.CLEANUP_NOT_MADE
    assert result.path_if_failed is None
    assert result.as_dict() == {"cleanup": "not_made", "path_if_failed": None}


def _flaky_rmtree(monkeypatch, workdir, failures):
    real = workdir._rmtree
    calls = []

    def fake(path):
        calls.append(str(path))
        if len(calls) <= failures:
            err = PermissionError(13, "The process cannot access the file because it is being used by another process")
            err.winerror = 32
            raise err
        return real(path)

    monkeypatch.setattr(workdir, "_rmtree", fake)
    return calls


def test_delete_retries_a_sharing_violation_then_succeeds(workdir, fake_project, monkeypatch):
    made = workdir.create(record.new_run_id(), source_fwdata=fake_project.fwdata)
    _populate(made)
    calls = _flaky_rmtree(monkeypatch, workdir, failures=2)
    result = workdir.delete(made)
    assert result.cleanup == workdir.CLEANUP_DELETED
    assert result.attempts == 3
    assert len(calls) == 3
    assert not made.exists()


def test_delete_waits_between_attempts(workdir, fake_project, monkeypatch):
    made = workdir.create(record.new_run_id(), source_fwdata=fake_project.fwdata)
    slept = []
    monkeypatch.setattr(workdir, "DELETE_RETRY_SECONDS", 0.2)
    monkeypatch.setattr(workdir.time, "sleep", lambda s: slept.append(s))
    _flaky_rmtree(monkeypatch, workdir, failures=99)
    workdir.delete(made)
    assert slept == [0.2] * workdir.DELETE_RETRIES


def test_persistent_failure_is_recorded_with_its_path(workdir, fake_project, monkeypatch):
    made = workdir.create(record.new_run_id(), source_fwdata=fake_project.fwdata)
    calls = _flaky_rmtree(monkeypatch, workdir, failures=99)
    result = workdir.delete(made)
    assert len(calls) == 1 + workdir.DELETE_RETRIES
    assert result.attempts == 1 + workdir.DELETE_RETRIES
    assert result.cleanup == workdir.CLEANUP_FAILED
    assert Path(result.path_if_failed) == made
    assert result.as_dict() == {"cleanup": "failed", "path_if_failed": result.path_if_failed}
    # Never hidden: the copy is still there for the sweep, marker included.
    assert (made / workdir.MARKER_NAME).exists()


@pytest.mark.windows_only
def test_delete_survives_a_real_short_lived_handle(workdir, fake_project, monkeypatch):
    monkeypatch.setattr(workdir, "DELETE_RETRY_SECONDS", 0.2)
    made = workdir.create(record.new_run_id(), source_fwdata=fake_project.fwdata)
    _populate(made)
    held = open(made / "Proj" / "Proj.fwdata", "rb")  # blocks delete on Windows
    timer = threading.Timer(0.1, held.close)
    timer.start()
    try:
        started = time.monotonic()
        result = workdir.delete(made)
    finally:
        timer.join()
        held.close()
    assert result.cleanup == workdir.CLEANUP_DELETED
    assert result.attempts >= 2
    assert time.monotonic() - started < 5
    assert not made.exists()


def _outside_targets(tmp_path, fake_project):
    """(label, factory) pairs; each factory makes an existing dir with a file."""

    def mk(path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        (path / "keep.txt").write_text("keep", encoding="utf-8")
        return path

    return {
        "elsewhere": lambda: mk(tmp_path / "elsewhere"),
        "project": lambda: mk(fake_project.dir / "Backups" / "victim"),
        "sandboxes": lambda: mk(sp.sandbox_dir("FakeProj", "mine")),
        "corpora": lambda: mk(sp.corpora_dir("FakeProj") / "c"),
        "config_cache": lambda: mk(sp.config_cache_dir("FakeProj") / "0123456789abcdef"),
        "sandbox_root": lambda: mk(sp.get_sandbox_root()),
        "work_root": lambda: mk(sp.get_sandbox_root() / "work"),
    }


@pytest.mark.parametrize(
    "label",
    ["elsewhere", "project", "sandboxes", "corpora", "config_cache", "sandbox_root", "work_root"],
)
def test_delete_refuses_a_target_outside_work(workdir, tmp_path, fake_project, monkeypatch, label):
    target = _outside_targets(tmp_path, fake_project)[label]()
    calls = []
    monkeypatch.setattr(workdir, "_rmtree", lambda p: calls.append(p))
    with pytest.raises(sp.SandboxPathError):
        workdir.delete(target)
    assert calls == []
    assert target.is_dir()
    assert any(target.rglob("keep.txt"))


def test_delete_refuses_a_traversal_out_of_work(workdir, fake_project, monkeypatch):
    victim = sp.get_sandbox_root() / "sandboxes" / "FakeProj" / "mine"
    victim.mkdir(parents=True)
    (sp.get_sandbox_root() / "work").mkdir(parents=True, exist_ok=True)
    sneaky = sp.get_sandbox_root() / "work" / ".." / "sandboxes" / "FakeProj" / "mine"
    monkeypatch.setattr(workdir, "_rmtree", lambda p: pytest.fail("must not delete"))
    with pytest.raises(sp.SandboxPathError):
        workdir.delete(sneaky)
    assert victim.is_dir()


# ---------------------------------------------------------------------------
# T081: free space (FR-012)
# ---------------------------------------------------------------------------


class _Usage:
    def __init__(self, free):
        self.total = 10**12
        self.used = 0
        self.free = free


def _patch_disk_usage(monkeypatch, free=None, error=None):
    from flextoolsmcp.server import backup

    seen = []

    def fake(path):
        seen.append(Path(path))
        if error is not None:
            raise error
        return _Usage(free)

    monkeypatch.setattr(backup.shutil, "disk_usage", fake)
    return seen


def test_free_space_below_twice_the_allowlist_refuses(workdir, fake_project, monkeypatch, sandbox_root):
    measure = workdir.measure_allowlist(fake_project.fwdata)
    needed = 2 * measure.total_bytes
    seen = _patch_disk_usage(monkeypatch, free=needed - 1)
    shortfall = workdir.check_free_space(fake_project.fwdata)
    assert shortfall is not None
    assert shortfall.needed_bytes == needed
    assert shortfall.free_bytes == needed - 1
    assert seen, "the check must go through backup.disk_space_ok"
    assert list(sandbox_root.rglob("*")) == []


def test_free_space_measures_the_allowlist_not_the_whole_folder(workdir, fake_project, monkeypatch):
    # A big excluded file must not count toward the need.
    (fake_project.dir / "LinkedFiles" / "AudioVisual" / "huge.wav").write_bytes(b"x" * 500_000)
    measure = workdir.measure_allowlist(fake_project.fwdata)
    _patch_disk_usage(monkeypatch, free=2 * measure.total_bytes)
    assert workdir.check_free_space(fake_project.fwdata) is None


def test_free_space_enough_is_none(workdir, fake_project, monkeypatch, sandbox_root):
    _patch_disk_usage(monkeypatch, free=10**12)
    assert workdir.check_free_space(fake_project.fwdata) is None
    assert list(sandbox_root.rglob("*")) == []


def test_free_space_checks_the_work_volume(workdir, fake_project, monkeypatch, sandbox_root):
    seen = _patch_disk_usage(monkeypatch, free=10**12)
    workdir.check_free_space(fake_project.fwdata)
    # work/ does not exist yet: its nearest existing ancestor is measured.
    assert seen[-1] == filing_paths._real(sandbox_root)
    (sandbox_root / "work").mkdir()
    workdir.check_free_space(fake_project.fwdata)
    assert seen[-1] == filing_paths._real(sandbox_root / "work")


def test_free_space_nothing_exists_yet(workdir, fake_project, monkeypatch, tmp_path):
    monkeypatch.setenv(sp.ENV_VAR, str(tmp_path / "not" / "yet" / "made"))
    seen = _patch_disk_usage(monkeypatch, free=10**12)
    assert workdir.check_free_space(fake_project.fwdata) is None
    assert seen[-1] == filing_paths._real(tmp_path)
    assert not (tmp_path / "not").exists()


def test_free_space_unmeasurable_fails_open(workdir, fake_project, monkeypatch):
    _patch_disk_usage(monkeypatch, error=OSError("no volume"))
    assert workdir.check_free_space(fake_project.fwdata) is None


def test_free_space_reuses_a_measure(workdir, fake_project, monkeypatch):
    measure = workdir.measure_allowlist(fake_project.fwdata)
    monkeypatch.setattr(workdir, "measure_allowlist", lambda f: pytest.fail("re-measured"))
    _patch_disk_usage(monkeypatch, free=0)
    shortfall = workdir.check_free_space(fake_project.fwdata, measure=measure)
    assert shortfall.needed_bytes == 2 * measure.total_bytes
    assert shortfall.free_bytes == 0


# ---------------------------------------------------------------------------
# T081: the startup sweep (FR-011)
# ---------------------------------------------------------------------------


def _marked(workdir, fake_project, run_id=None):
    run_id = run_id or record.new_run_id()
    made = workdir.create(run_id, source_fwdata=fake_project.fwdata)
    _populate(made)
    return run_id, made


def test_sweep_removes_a_marked_orphan(workdir, fake_project):
    _, orphan = _marked(workdir, fake_project)
    removed = workdir.sweep([])
    assert removed == [orphan]
    assert not orphan.exists()


def test_sweep_keeps_live_runs(workdir, fake_project):
    live_id, live = _marked(workdir, fake_project)
    _, orphan = _marked(workdir, fake_project)
    removed = workdir.sweep({live_id})
    assert removed == [orphan]
    assert live.is_dir()
    assert (live / workdir.MARKER_NAME).exists()


def test_sweep_keeps_a_run_live_by_its_marker_id(workdir, fake_project):
    live_id, made = _marked(workdir, fake_project)
    other = sp.work_root() / record.new_run_id()
    made.rename(other)
    assert workdir.sweep(iter([live_id])) == []
    assert other.is_dir()


def test_sweep_ignores_unmarked_dirs_and_files(workdir, fake_project):
    work = sp.work_root()
    work.mkdir(parents=True, exist_ok=True)
    unmarked = work / record.new_run_id()
    unmarked.mkdir()
    (unmarked / "keep.txt").write_text("keep", encoding="utf-8")
    corrupt = work / record.new_run_id()
    corrupt.mkdir()
    (corrupt / workdir.MARKER_NAME).write_text("{broken", encoding="utf-8")
    stray = work / "stray.txt"
    stray.write_text("keep", encoding="utf-8")
    _, orphan = _marked(workdir, fake_project)
    assert workdir.sweep([]) == [orphan]
    assert (unmarked / "keep.txt").exists()
    assert corrupt.is_dir()
    assert stray.exists()


def test_sweep_never_touches_anything_outside_work(workdir, fake_project):
    # Marked look-alikes in the other areas and in the project must survive.
    victims = [
        sp.sandbox_dir("FakeProj", "mine"),
        sp.corpora_dir("FakeProj"),
        sp.config_cache_dir("FakeProj") / "0123456789abcdef",
        fake_project.dir / "Backups" / "x",
    ]
    marker = {"run_id": record.new_run_id(), "pid": 1, "created_at": "x", "source_fwdata": "x"}
    for v in victims:
        v.mkdir(parents=True, exist_ok=True)
        (v / workdir.MARKER_NAME).write_text(json.dumps(marker), encoding="utf-8")
    _, orphan = _marked(workdir, fake_project)
    assert workdir.sweep([]) == [orphan]
    for v in victims:
        assert (v / workdir.MARKER_NAME).exists()


def test_sweep_without_a_work_root(workdir, sandbox_root):
    assert workdir.sweep([]) == []
    assert not (sandbox_root / "work").exists()


def test_sweep_leaves_an_undeletable_orphan(workdir, fake_project, monkeypatch):
    _, stuck = _marked(workdir, fake_project)
    _flaky_rmtree(monkeypatch, workdir, failures=99)
    assert workdir.sweep([]) == []
    assert (stuck / workdir.MARKER_NAME).exists()
