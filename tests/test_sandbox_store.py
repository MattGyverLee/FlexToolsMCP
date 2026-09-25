#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the user-owned sandbox store, sandbox half (parser-check CP5, T058):
`src/flextoolsmcp/server/sandbox/store.py` (T061). FR-025, FR-028, FR-029,
SC-007, US3; data-model sections 1 and 4; contracts/tools.md sections 5.2
and 5.4 (the handler builds the envelope; the store returns data). The
shapes match the seam the handler tests (T060) pin.

THE API THESE TESTS SPECIFY (`flextoolsmcp.server.sandbox.store`)
-----------------------------------------------------------------
Constants
  SANDBOX_SCHEMA = "flextoolsmcp.hc-sandbox/1"
  SANDBOX_CONFIG_NAME = "hc-config.xml"; ORIGIN_JSON = "origin.json"
  ORIGIN_KEYS = ("schema", "name", "project", "created_at",
                 "from_cache_key", "from_inputs", "sha256_at_creation")
  LIST_ITEM_KEYS = ("name", "path", "created_at", "edited",
                    "predates_project_grammar")
  STATUS_KEYS = LIST_ITEM_KEYS + ("from_cache_key",)

Errors
  SandboxExists(FileExistsError): .reason "sandbox_exists", .name, .path
  A bad name raises paths.SandboxNameError (.reason "name_invalid").

Operations (paths in returned dicts are str)
  create_sandbox(project_name, name, entry: cache.CacheEntry) -> dict
      {"name", "path" (the new hc-config.xml), "origin": {"from_cache_key",
      "created_at"}}. Validates the name (paths.sandbox_dir); refuses an
      entry of another project (ValueError) or whose config is not under
      config-cache/ (paths.SandboxPathError). CLAIMS the directory with an
      exclusive mkdir: if `sandboxes/<project>/<name>/` exists AT ALL ->
      SandboxExists and nothing in it is touched. Then writes a byte-
      identical copy of entry.config_path with an exclusive-create open
      ("xb") and origin.json once ("x"). Never "w", never replace/delete.
  sandbox_config_path(project_name, name) -> Optional[Path]
      The hc-config.xml path if that FILE exists; origin.json NOT required.
      Bad name -> SandboxNameError. Creates nothing.
  read_origin(project_name, name) -> Optional[dict]  None if absent/unreadable.
  current_key(fwdata_path, generator_path, *, hcparse_version=None)
      -> Optional[str]   cache.compute_key(cache.key_inputs(...)): a stat
      alone, the project is never opened; None on OSError.
  project_current_key(project_name) -> Optional[str]
      current_key(filing.paths.project_dir_for(p) / "<p>.fwdata",
      parser_probe.discover_generate_hc_config().expected_path) -- both
      looked up on their modules at call time; None when either is
      unavailable (no projects dir, generator not found, stat fails).
  sandbox_status(project_name, name, current_key=<computed>) -> Optional[dict]
      STATUS_KEYS. None when <sandbox>/hc-config.xml is absent.
      edited = sha256(hc-config.xml) != origin.sha256_at_creation, None
      without a readable origin.json. predates_project_grammar =
      origin.from_cache_key != current key; False when the current key is
      unknown or there is no origin (never a false advisory).
      `current_key` defaults to project_current_key(project_name). Read-only.
  list_sandboxes(project_name, current_key=<computed>) -> list[dict]
      LIST_ITEM_KEYS, one per directory under sandboxes/<project>/ with a
      valid name and an hc-config.xml, sorted by name; the current key is
      computed once. An absent project dir gives [] and is not created.

CORPUS HALF (T066 -> T071; FR-030, research R-10, data-model section 5,
contracts/tools.md sections 3, 5.3, 5.4)
  CORPUS_SCHEMA = "flextoolsmcp.hc-corpus/1"
  CORPUS_KEYS = ("schema", "name", "project", "created_at", "seeded_from",
                 "assertions")
  SEED_RESULT_KEYS = ("name", "path", "assertion_count", "no_parse_count",
                      "excluded", "from_run_id")
  CORPUS_LIST_KEYS = ("name", "path", "assertion_count")

Errors (each has `.reason`, the parse_sandbox_refused reason or error code)
  RunNotFound(LookupError)        .error_code = .reason = "parse_run_not_found"; .run_id
  RunNotSeedable(ValueError)      reason "run_not_seedable"; .run_id, .detail
  CorpusExists(FileExistsError)   reason "corpus_exists"; .name, .path
  CorpusNotFound(LookupError)     reason "corpus_not_found"; .name, .path
  CorpusInvalid(ValueError)       reason "corpus_invalid"; .name, .path,
                                  .json_path ("$", "$.schema",
                                  "$.assertions[2].expected[0][1].gloss", ...),
                                  .detail

  seed_corpus(project_name, name, record: parse.record.RunRecord) -> dict
      Checks IN THIS ORDER: record exists (RunNotFound); it is a completed
      sandbox parse run of this project -- meta.effective_spine ==
      "sandbox", meta.sandbox["mode"] == "parse", stage "completed",
      meta.project_name == project_name (RunNotSeedable); the name is valid
      (SandboxNameError) and new (CorpusExists, exclusive "xb" create).
      Walks record.iter_results() in order:
        parsed, every analysis readable -> expected = the analyses' morphs
            in hc's order, each [{"form", "gloss"}];
        parsed with an unreadable analysis -> excluded, reason "unreadable";
        not_parsed -> expected [];
        any other outcome -> excluded, reason = the outcome;
        a word whose NFC form was already seen -> excluded, reason "duplicate".
      Words are stored NFC. seeded_from = {"run_id", "config_source"
      (meta.sandbox["config_source"])}. Returns SEED_RESULT_KEYS; `excluded`
      is [{"word", "reason"}] in results order; `path` is str.
  load_corpus(project_name, name) -> Corpus
      Corpus(name, path: Path, data: dict, assertions: list[{"word",
      "expected"}], duplicates: list[{"word", "index", "kept_index"}]).
      Missing file -> CorpusNotFound. The whole file is validated first;
      the first fault raises CorpusInvalid naming its JSON path. Words are
      NFC-normalized and de-duplicated keeping the first.
  list_corpora(project_name) -> list[dict]   CORPUS_LIST_KEYS, one per
      `<valid name>.json`, sorted by name; assertion_count is None for a
      file that does not validate. Absent dir -> [] (not created).
"""

from __future__ import annotations

import ast
import builtins
import hashlib
import importlib
import io
import json
import os
import types
from pathlib import Path

import pytest

from flextoolsmcp.server import parser_probe
from flextoolsmcp.server.filing import paths as filing_paths
from flextoolsmcp.server.sandbox import cache, paths

try:  # tests/ is on sys.path under pytest's default (prepend) import mode
    from test_sandbox_cache import EmulatedScript, _work_dir
except ImportError:  # pragma: no cover
    from tests.test_sandbox_cache import EmulatedScript, _work_dir

SRC_STORE = (Path(__file__).resolve().parent.parent / "src" / "flextoolsmcp"
             / "server" / "sandbox" / "store.py")

ORIGIN_KEYS = {"schema", "name", "project", "created_at", "from_cache_key",
               "from_inputs", "sha256_at_creation", "hc_parameters", "lcm_ids_path"}
LIST_ITEM_KEYS = {"name", "path", "created_at", "edited", "predates_project_grammar"}
STATUS_KEYS = LIST_ITEM_KEYS | {"from_cache_key"}


def _store():
    """Import the module under test inside the test body (test-first)."""
    try:
        return importlib.import_module("flextoolsmcp.server.sandbox.store")
    except ImportError as exc:  # pragma: no cover - until T061 lands
        pytest.fail("flextoolsmcp.server.sandbox.store is missing: %s" % exc)


@pytest.fixture(autouse=True)
def _fresh_cache_state():
    yield
    cache.reset_state()


@pytest.fixture
def located(monkeypatch, fake_project, fake_generator):
    """The project and generator the store's default key lookup will find."""
    monkeypatch.setattr(filing_paths, "projects_directory", lambda: fake_project.dir.parent)
    monkeypatch.setattr(
        parser_probe, "discover_generate_hc_config",
        lambda *a, **kw: types.SimpleNamespace(ok=True, signal=None,
                                               expected_path=str(fake_generator.path)))
    return fake_project


async def _entry(project, fake_generator):
    return await cache.ensure_entry(
        project.name, project.fwdata, fake_generator.path,
        work_dir=_work_dir(), run_script=EmulatedScript())


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _tree(root: Path) -> dict:
    """{relative posix path: (bytes, mtime_ns)} for every file under root."""
    if not root.exists():
        return {}
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def _bump_mtime(path) -> None:
    st = Path(path).stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


# --------------------------------------------------------------------------
# FR-028: create returns the path and records the origin
# --------------------------------------------------------------------------

async def test_create_returns_path_and_records_origin(
        sandbox_root, fake_project, fake_generator):
    store = _store()
    entry = await _entry(fake_project, fake_generator)
    made = store.create_sandbox(fake_project.name, "tighten-env", entry)

    sdir = paths.sandbox_dir(fake_project.name, "tighten-env")
    assert set(made) == {"name", "path", "origin"}
    assert made["name"] == "tighten-env"
    assert made["path"] == str(sdir / "hc-config.xml")
    assert store.SANDBOX_CONFIG_NAME == "hc-config.xml"
    config = Path(made["path"])
    assert config.read_bytes() == entry.config_path.read_bytes()

    assert store.ORIGIN_JSON == "origin.json"
    origin = json.loads((sdir / "origin.json").read_text(encoding="utf-8"))
    assert set(origin) == ORIGIN_KEYS == set(store.ORIGIN_KEYS)
    assert origin["schema"] == "flextoolsmcp.hc-sandbox/1" == store.SANDBOX_SCHEMA
    assert origin["name"] == "tighten-env"
    assert origin["project"] == fake_project.name
    assert origin["from_cache_key"] == entry.key
    assert origin["from_inputs"] == entry.meta["inputs"]
    assert origin["sha256_at_creation"] == _sha(config)
    assert origin["created_at"].endswith("Z")
    assert made["origin"] == {"from_cache_key": entry.key, "created_at": origin["created_at"]}
    assert store.read_origin(fake_project.name, "tighten-env") == origin
    # T101: the Morpher settings and the id-map sidecar travel with it.
    assert origin["hc_parameters"] == entry.hc_parameters is not None
    assert origin["lcm_ids_path"] == "lcm-ids.json"
    assert (sdir / "lcm-ids.json").read_bytes() == entry.lcm_ids_path.read_bytes()
    assert store.sandbox_lcm_ids_path(fake_project.name, "tighten-env") == sdir / "lcm-ids.json"
    # Only the three documented files.
    assert sorted(p.name for p in sdir.iterdir()) == [
        "hc-config.xml", "lcm-ids.json", "origin.json"]
    # The cache entry is still usable.
    assert cache.lookup(fake_project.name, entry.key, touch=False) is not None


async def test_create_from_entry_predating_sidecar_records_absent(
        sandbox_root, fake_project, fake_generator):
    store = _store()
    entry = await _entry(fake_project, fake_generator)
    old_meta = {k: v for k, v in entry.meta.items()
                if k not in ("hc_parameters", "lcm_ids_path")}
    old = cache.CacheEntry(project=entry.project, key=entry.key, path=entry.path,
                           meta=old_meta)
    store.create_sandbox(fake_project.name, "old-entry", old)
    sdir = paths.sandbox_dir(fake_project.name, "old-entry")
    origin = json.loads((sdir / "origin.json").read_text(encoding="utf-8"))
    assert origin["hc_parameters"] is None and origin["lcm_ids_path"] is None
    assert sorted(p.name for p in sdir.iterdir()) == ["hc-config.xml", "origin.json"]
    assert store.sandbox_lcm_ids_path(fake_project.name, "old-entry") is None


async def test_invalid_sidecar_is_copied_verbatim_never_dropped(
        sandbox_root, fake_project, fake_generator):
    store = _store()
    entry = await _entry(fake_project, fake_generator)
    bad = json.dumps({"schema": "flextoolsmcp.hc-lcm-ids/1", "valid": False, "ids": {},
                      "invalid_ids": ["7"], "error": None}).encode("utf-8")
    entry.lcm_ids_path.write_bytes(bad)
    store.create_sandbox(fake_project.name, "bad-map", entry)
    sdir = paths.sandbox_dir(fake_project.name, "bad-map")
    assert (sdir / "lcm-ids.json").read_bytes() == bad


async def test_recorded_sidecar_that_vanished_is_not_absent(
        sandbox_root, fake_project, fake_generator):
    store = _store()
    entry = await _entry(fake_project, fake_generator)
    store.create_sandbox(fake_project.name, "gone", entry)
    sdir = paths.sandbox_dir(fake_project.name, "gone")
    (sdir / "lcm-ids.json").unlink()  # the user deleted it by hand
    found = store.sandbox_lcm_ids_path(fake_project.name, "gone")
    assert found == sdir / "lcm-ids.json" and not found.exists()


async def test_second_create_refused_first_file_byte_identical(
        sandbox_root, fake_project, fake_generator):
    store = _store()
    entry = await _entry(fake_project, fake_generator)
    config = Path(store.create_sandbox(fake_project.name, "x", entry)["path"])
    config.write_bytes(config.read_bytes() + b"\n<!-- user edit -->\n")
    before = _tree(config.parent)

    with pytest.raises(store.SandboxExists) as caught:
        store.create_sandbox(fake_project.name, "x", entry)
    assert isinstance(caught.value, FileExistsError)
    assert caught.value.reason == "sandbox_exists"
    assert caught.value.name == "x"
    assert _tree(config.parent) == before

    # A fresh entry (the grammar moved on) is refused just the same.
    _bump_mtime(fake_project.fwdata)
    newer = await _entry(fake_project, fake_generator)
    assert newer.key != entry.key
    with pytest.raises(FileExistsError):
        store.create_sandbox(fake_project.name, "x", newer)
    assert _tree(config.parent) == before


async def test_existing_directory_without_config_is_refused_untouched(
        sandbox_root, fake_project, fake_generator):
    """The exclusive claim is the directory itself: whatever the user keeps
    there, create never writes into it."""
    store = _store()
    entry = await _entry(fake_project, fake_generator)
    sdir = paths.sandbox_dir(fake_project.name, "mine")
    sdir.mkdir(parents=True)
    (sdir / "notes.txt").write_text("mine\n", encoding="utf-8")
    before = _tree(sdir)
    with pytest.raises(store.SandboxExists):
        store.create_sandbox(fake_project.name, "mine", entry)
    assert _tree(sdir) == before
    assert not (sdir / "hc-config.xml").exists()


async def test_same_name_in_another_project_is_independent(
        sandbox_root, fake_project, fake_project_factory, fake_generator):
    store = _store()
    other = fake_project_factory("OtherProj")
    a = store.create_sandbox(fake_project.name, "x", await _entry(fake_project, fake_generator))
    b = store.create_sandbox(other.name, "x", await _entry(other, fake_generator))
    assert a["path"] != b["path"]
    assert Path(a["path"]).exists() and Path(b["path"]).exists()


@pytest.mark.parametrize("name", [
    "..", "../x", "a/b", "a\\b", "CON", "con", "con.txt", "Lpt1.xml", "", "a" * 65,
    "trailing.", "a..b", ".hidden", "-dash", "sp ace", "c:x", None,
])
async def test_bad_names_refused(sandbox_root, fake_project, fake_generator, name):
    store = _store()
    entry = await _entry(fake_project, fake_generator)
    before = _tree(sandbox_root / "sandboxes")
    with pytest.raises(paths.SandboxNameError) as caught:
        store.create_sandbox(fake_project.name, name, entry)
    assert caught.value.reason == "name_invalid"
    assert _tree(sandbox_root / "sandboxes") == before
    assert not list((sandbox_root / "sandboxes").rglob("hc-config.xml")) \
        if (sandbox_root / "sandboxes").exists() else True


async def test_longest_valid_name_accepted(sandbox_root, fake_project, fake_generator):
    store = _store()
    entry = await _entry(fake_project, fake_generator)
    name = "a" + "b" * 63
    assert Path(store.create_sandbox(fake_project.name, name, entry)["path"]).exists()


async def test_entry_of_another_project_refused(
        sandbox_root, fake_project, fake_project_factory, fake_generator):
    store = _store()
    other = fake_project_factory("OtherProj")
    entry = await _entry(other, fake_generator)
    with pytest.raises(ValueError):
        store.create_sandbox(fake_project.name, "x", entry)
    assert store.sandbox_config_path(fake_project.name, "x") is None


async def test_entry_config_outside_cache_refused(
        sandbox_root, fake_project, fake_generator, tmp_path):
    store = _store()
    entry = await _entry(fake_project, fake_generator)
    rogue_dir = tmp_path / "elsewhere"
    rogue_dir.mkdir()
    (rogue_dir / "hc-config.xml").write_text("<HermitCrabInput/>", encoding="utf-8")
    rogue = cache.CacheEntry(project=fake_project.name, key=entry.key,
                             path=rogue_dir, meta=entry.meta)
    with pytest.raises(paths.SandboxPathError):
        store.create_sandbox(fake_project.name, "x", rogue)
    assert store.sandbox_config_path(fake_project.name, "x") is None


# --------------------------------------------------------------------------
# sandbox_config_path: existence only (origin.json not required)
# --------------------------------------------------------------------------

def test_config_path_needs_only_the_xml(sandbox_root, fake_project):
    store = _store()
    assert store.sandbox_config_path(fake_project.name, "x") is None
    assert not (sandbox_root / "sandboxes").exists()
    sdir = paths.sandbox_dir(fake_project.name, "x")
    sdir.mkdir(parents=True)
    assert store.sandbox_config_path(fake_project.name, "x") is None
    (sdir / "hc-config.xml").write_text("<HermitCrabInput/>", encoding="utf-8")
    assert store.sandbox_config_path(fake_project.name, "x") == sdir / "hc-config.xml"
    assert store.read_origin(fake_project.name, "x") is None
    with pytest.raises(paths.SandboxNameError):
        store.sandbox_config_path(fake_project.name, "..")


# --------------------------------------------------------------------------
# Derived state: edited (sha256) and predates_project_grammar (stat only)
# --------------------------------------------------------------------------

async def test_status_shape(sandbox_root, located, fake_generator):
    store = _store()
    entry = await _entry(located, fake_generator)
    made = store.create_sandbox(located.name, "x", entry)
    status = store.sandbox_status(located.name, "x")
    assert set(status) == STATUS_KEYS == set(store.STATUS_KEYS)
    assert status == {"name": "x", "path": made["path"],
                      "created_at": made["origin"]["created_at"], "edited": False,
                      "predates_project_grammar": False, "from_cache_key": entry.key}


async def test_edited_comes_from_sha256(sandbox_root, located, fake_generator):
    store = _store()
    entry = await _entry(located, fake_generator)
    config = Path(store.create_sandbox(located.name, "x", entry)["path"])
    original = config.read_bytes()
    assert store.sandbox_status(located.name, "x")["edited"] is False

    # A touch without a content change is not an edit.
    _bump_mtime(config)
    assert store.sandbox_status(located.name, "x")["edited"] is False

    config.write_bytes(original + b"<!-- tweak -->")
    assert store.sandbox_status(located.name, "x")["edited"] is True

    config.write_bytes(original)
    assert store.sandbox_status(located.name, "x")["edited"] is False


async def test_predates_after_project_stat_change_sandbox_unchanged(
        sandbox_root, located, fake_generator):
    store = _store()
    entry = await _entry(located, fake_generator)
    config = Path(store.create_sandbox(located.name, "x", entry)["path"])
    assert store.project_current_key(located.name) == entry.key
    assert store.current_key(located.fwdata, fake_generator.path) == entry.key
    assert store.sandbox_status(located.name, "x")["predates_project_grammar"] is False
    before = _tree(config.parent)

    _bump_mtime(located.fwdata)  # a write to the project, seen by stat alone
    assert store.project_current_key(located.name) != entry.key
    status = store.sandbox_status(located.name, "x")
    assert status["predates_project_grammar"] is True
    assert status["edited"] is False
    assert store.list_sandboxes(located.name)[0]["predates_project_grammar"] is True
    # An explicit key overrides the lookup.
    assert store.sandbox_status(located.name, "x", entry.key)["predates_project_grammar"] \
        is False
    # FR-029: the sandbox is not altered.
    assert _tree(config.parent) == before


async def test_predates_false_when_current_key_unknown(
        sandbox_root, fake_project, fake_generator, monkeypatch):
    store = _store()
    store.create_sandbox(fake_project.name, "x", await _entry(fake_project, fake_generator))
    monkeypatch.setattr(
        parser_probe, "discover_generate_hc_config",
        lambda *a, **kw: types.SimpleNamespace(ok=False, signal="not_found",
                                               expected_path="GenerateHCConfig.exe"))
    monkeypatch.setattr(filing_paths, "projects_directory", lambda: fake_project.dir.parent)
    assert store.project_current_key(fake_project.name) is None
    assert store.sandbox_status(fake_project.name, "x")["predates_project_grammar"] is False
    monkeypatch.setattr(filing_paths, "projects_directory", lambda: None)
    assert store.project_current_key(fake_project.name) is None
    assert store.list_sandboxes(fake_project.name)[0]["predates_project_grammar"] is False


def test_current_key_is_stat_only(monkeypatch, located, fake_generator):
    """The project is never opened: the current key is metadata alone."""
    store = _store()
    opened = []
    real_open, real_io_open = builtins.open, io.open

    def spy(real):
        def _open(file, *a, **kw):
            opened.append(file)
            return real(file, *a, **kw)
        return _open

    monkeypatch.setattr(builtins, "open", spy(real_open))
    monkeypatch.setattr(io, "open", spy(real_io_open))
    try:
        key = store.current_key(located.fwdata, fake_generator.path, hcparse_version="5.0.0")
        store.project_current_key(located.name)
    finally:
        monkeypatch.setattr(builtins, "open", real_open)
        monkeypatch.setattr(io, "open", real_io_open)
    assert key == cache.compute_key(cache.key_inputs(
        located.fwdata, fake_generator.path, hcparse_version="5.0.0"))
    fw = os.path.normcase(str(Path(located.fwdata).resolve()))
    touched = [os.path.normcase(str(Path(p).resolve())) for p in opened
               if isinstance(p, (str, os.PathLike))]
    assert fw not in touched, opened


def test_current_key_none_when_project_missing(tmp_path, fake_generator):
    store = _store()
    assert store.current_key(tmp_path / "gone.fwdata", fake_generator.path) is None


def test_status_of_missing_sandbox_is_none(sandbox_root, located):
    store = _store()
    assert store.sandbox_status(located.name, "nope") is None
    assert not (sandbox_root / "sandboxes").exists()


def test_status_without_origin(sandbox_root, located):
    store = _store()
    sdir = paths.sandbox_dir(located.name, "hand")
    sdir.mkdir(parents=True)
    (sdir / "hc-config.xml").write_text("<HermitCrabInput/>", encoding="utf-8")
    (sdir / "origin.json").write_text("{trunc", encoding="utf-8")
    status = store.sandbox_status(located.name, "hand")
    assert status == {"name": "hand", "path": str(sdir / "hc-config.xml"),
                      "created_at": None, "edited": None,
                      "predates_project_grammar": False, "from_cache_key": None}


# --------------------------------------------------------------------------
# list (contracts/tools.md section 5.4, the sandboxes half)
# --------------------------------------------------------------------------

async def test_list_sandboxes(sandbox_root, located, fake_generator):
    store = _store()
    assert store.list_sandboxes(located.name) == []
    assert not (sandbox_root / "sandboxes").exists()

    entry = await _entry(located, fake_generator)
    b = store.create_sandbox(located.name, "b-second", entry)
    a = store.create_sandbox(located.name, "a-first", entry)
    Path(b["path"]).write_bytes(Path(b["path"]).read_bytes() + b"\n")
    # A hand-made sandbox with no origin.json is still listed.
    hand = paths.sandbox_dir(located.name, "c-hand")
    hand.mkdir()
    (hand / "hc-config.xml").write_text("<HermitCrabInput/>", encoding="utf-8")
    # Not sandboxes: a stray file, an empty dir, a dir with a bad name.
    sroot = paths.sandboxes_dir(located.name)
    (sroot / "stray.txt").write_text("x", encoding="utf-8")
    (sroot / "empty").mkdir()
    (sroot / "bad name").mkdir()
    (sroot / "bad name" / "hc-config.xml").write_text("<x/>", encoding="utf-8")

    before = _tree(sandbox_root / "sandboxes")
    listed = store.list_sandboxes(located.name)
    assert [item["name"] for item in listed] == ["a-first", "b-second", "c-hand"]
    for item in listed:
        assert set(item) == LIST_ITEM_KEYS == set(store.LIST_ITEM_KEYS)
        assert isinstance(item["path"], str)
    first, second, third = listed
    assert first == {"name": "a-first", "path": a["path"],
                     "created_at": a["origin"]["created_at"], "edited": False,
                     "predates_project_grammar": False}
    assert second["edited"] is True and second["predates_project_grammar"] is False
    assert third["created_at"] is None and third["edited"] is None
    assert third["predates_project_grammar"] is False
    # Listing reads; it changes nothing.
    assert _tree(sandbox_root / "sandboxes") == before


# --------------------------------------------------------------------------
# Never "w", never replace, never delete (FR-025 applied to the store)
# --------------------------------------------------------------------------

_FORBIDDEN_ATTRS = {"write_text", "write_bytes", "unlink", "rmdir", "rmtree", "remove",
                    "replace", "rename", "move", "copyfile", "copy", "copy2",
                    "copytree", "truncate"}


def test_store_source_never_overwrites_or_deletes():
    _store()
    tree = ast.parse(SRC_STORE.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name in _FORBIDDEN_ATTRS:
            bad.append((node.lineno, name))
        if name == "open":
            mode = None
            if isinstance(func, ast.Attribute) and not (
                    isinstance(func.value, ast.Name) and func.value.id in ("os", "io")):
                if node.args and isinstance(node.args[0], ast.Constant):  # Path.open(mode)
                    mode = node.args[0].value
            elif len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = node.args[1].value
            for kw in node.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = kw.value.value
            if isinstance(mode, str) and ("w" in mode or "a" in mode or "+" in mode):
                bad.append((node.lineno, "open(%r)" % mode))
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) \
                    and func.value.id == "os":
                flags = ast.unparse(node.args[1]) if len(node.args) > 1 else ""
                writes = "O_WRONLY" in flags or "O_RDWR" in flags
                if writes and ("O_EXCL" not in flags or "O_CREAT" not in flags):
                    bad.append((node.lineno, "os.open(%s)" % flags))
                if "O_TRUNC" in flags or "O_APPEND" in flags:
                    bad.append((node.lineno, "os.open(%s)" % flags))
    assert bad == [], "store.py may only exclusive-create files: %s" % bad


# ==========================================================================
# CORPUS HALF (T066): seeding, loading and listing corpora
# ==========================================================================

import unicodedata  # noqa: E402

from flextoolsmcp.server.parse import record as run_record  # noqa: E402
from flextoolsmcp.server.parse.stages import RunStage  # noqa: E402

CORPUS_KEYS = {"schema", "name", "project", "created_at", "seeded_from", "assertions"}
SEED_RESULT_KEYS = {"name", "path", "assertion_count", "no_parse_count", "excluded",
                    "from_run_id"}
CONFIG_SOURCE = {"kind": "project_cache", "cache_key": "abcdef0123456789"}

MEM_BACA = [{"form": "mem", "gloss": "ACT"}, {"form": "baca", "gloss": "read"}]
ME_MBACA = [{"form": "me", "gloss": "?"}, {"form": "mbaca", "gloss": "read"}]


def _analysis(morphs, readable=True):
    if not readable:
        return {"signature": None, "rendered_morphs": None, "morphs": None,
                "readable": False, "raw": ["Morphs: a b", "Gloss:  x"]}
    return {"signature": None, "rendered_morphs": [m["form"] for m in morphs],
            "morphs": morphs, "readable": True, "raw": None}


def _line(index, word, outcome, analyses=None):
    listed = outcome in ("parsed", "not_parsed")
    return {"index": index, "wordform": word, "parse": {
        "parsed": outcome == "parsed",
        "analysis_count": len(analyses or []),
        "outcome": outcome,
        "analyses": (analyses or []) if listed else None,
        "position": 2 if outcome == "invalid_segment" else None,
        "flags": [],
        "parse_time_ms": 3 if listed else None,
    }}


SEED_LINES = [
    _line(0, "membaca", "parsed", [_analysis(MEM_BACA), _analysis(ME_MBACA)]),
    _line(1, "xyz", "not_parsed", []),
    _line(2, "garbled", "parsed", [_analysis(MEM_BACA), _analysis(None, readable=False)]),
    _line(3, "q#", "invalid_segment"),
    _line(4, "boom", "error_no_output"),
    _line(5, "later", "not_reached"),
    _line(6, "a|b", "not_expressible"),
    _line(7, "café", "not_parsed", []),
    _line(8, "café", "parsed", [_analysis(MEM_BACA)]),  # NFC duplicate of 7
]


def _run(tmp_path, *, lines=SEED_LINES, project="FakeProj", spine="sandbox",
         mode="parse", stage=RunStage.COMPLETED):
    sandbox = None if spine is None else {"mode": mode, "config_source": CONFIG_SOURCE}
    rec = run_record.RunRecord.create(
        project_name=project, words_total=len(lines),
        record_dir=tmp_path / "records", spine=spine, sandbox=sandbox)
    for line in lines:
        rec.append_result(line)
    if stage is not None:
        rec.set_stage(stage)
    return rec


def _write_corpus(project_name, name, data):
    path = paths.corpus_path(project_name, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    path.write_text(text, encoding="utf-8")
    return path


def _good_corpus(assertions=None):
    return {"schema": "flextoolsmcp.hc-corpus/1", "name": "c", "project": "FakeProj",
            "created_at": "2026-09-24T00:00:00.000Z",
            "seeded_from": {"run_id": "0" * 32, "config_source": CONFIG_SOURCE},
            "assertions": assertions if assertions is not None else [
                {"word": "membaca", "expected": [MEM_BACA]},
                {"word": "xyz", "expected": []},
            ]}


def _with(assertions):
    return _good_corpus(assertions)


def _without(key):
    return {k: v for k, v in _good_corpus().items() if k != key}


# --------------------------------------------------------------------------
# seed_corpus (FR-030, R-10)
# --------------------------------------------------------------------------

def test_seed_keeps_exact_parses_and_lists_exclusions(sandbox_root, tmp_path):
    store = _store()
    rec = _run(tmp_path)
    seeded = store.seed_corpus("FakeProj", "baseline", rec)

    path = paths.corpus_path("FakeProj", "baseline")
    assert set(seeded) == SEED_RESULT_KEYS == set(store.SEED_RESULT_KEYS)
    assert seeded["name"] == "baseline"
    assert seeded["path"] == str(path)
    assert seeded["from_run_id"] == rec.run_id
    assert seeded["assertion_count"] == 3
    assert seeded["no_parse_count"] == 2
    assert seeded["excluded"] == [
        {"word": "garbled", "reason": "unreadable"},
        {"word": "q#", "reason": "invalid_segment"},
        {"word": "boom", "reason": "error_no_output"},
        {"word": "later", "reason": "not_reached"},
        {"word": "a|b", "reason": "not_expressible"},
        {"word": "café", "reason": "duplicate"},
    ]

    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == CORPUS_KEYS == set(store.CORPUS_KEYS)
    assert data["schema"] == "flextoolsmcp.hc-corpus/1" == store.CORPUS_SCHEMA
    assert data["name"] == "baseline" and data["project"] == "FakeProj"
    assert data["created_at"].endswith("Z")
    assert data["seeded_from"] == {"run_id": rec.run_id, "config_source": CONFIG_SOURCE}
    assert data["assertions"] == [
        # Exact parses, in hc's order; "?" glosses kept verbatim (F-7).
        {"word": "membaca", "expected": [MEM_BACA, ME_MBACA]},
        {"word": "xyz", "expected": []},
        {"word": unicodedata.normalize("NFC", "café"), "expected": []},
    ]


@pytest.mark.parametrize("kind", ["in_process", "incomplete", "failed", "cancelled",
                                  "test_mode", "other_project"])
def test_unseedable_runs(sandbox_root, tmp_path, kind):
    store = _store()
    kw = {
        "in_process": {"spine": None},
        "incomplete": {"stage": RunStage.PARSING},
        "failed": {"stage": RunStage.FAILED},
        "cancelled": {"stage": RunStage.CANCELLED},
        "test_mode": {"mode": "test"},
        "other_project": {"project": "OtherProj"},
    }[kind]
    rec = _run(tmp_path, **kw)
    with pytest.raises(store.RunNotSeedable) as caught:
        store.seed_corpus("FakeProj", "baseline", rec)
    assert caught.value.reason == "run_not_seedable"
    assert caught.value.run_id == rec.run_id
    assert caught.value.detail
    assert not paths.corpus_path("FakeProj", "baseline").exists()


def test_seed_of_missing_run(sandbox_root, tmp_path):
    store = _store()
    rec = run_record.RunRecord(run_record.new_run_id(), record_dir=tmp_path / "records")
    with pytest.raises(store.RunNotFound) as caught:
        store.seed_corpus("FakeProj", "baseline", rec)
    assert caught.value.reason == caught.value.error_code == "parse_run_not_found"
    assert caught.value.run_id == rec.run_id
    assert not (sandbox_root / "corpora").exists()


def test_seed_of_an_unreadable_run_is_not_run_not_found(sandbox_root, tmp_path, monkeypatch):
    """Pattern audit sweep 6: an existing meta.json that stays unreadable
    raises MetaUnreadable (transient; the handler answers it retryably),
    never RunNotFound."""
    store = _store()
    monkeypatch.setattr(run_record, "META_RETRY_DELAY_SECONDS", 0)
    rec = _run(tmp_path)
    rec.meta_path.write_text("{not json", encoding="utf-8")
    with pytest.raises(run_record.MetaUnreadable):
        store.seed_corpus("FakeProj", "baseline", rec)
    assert not paths.corpus_path("FakeProj", "baseline").exists()


def test_seed_check_order_run_before_name(sandbox_root, tmp_path):
    """contracts section 3: the run checks come before the name check."""
    store = _store()
    with pytest.raises(store.RunNotSeedable):
        store.seed_corpus("FakeProj", "../bad", _run(tmp_path, stage=RunStage.PARSING))
    with pytest.raises(paths.SandboxNameError):
        store.seed_corpus("FakeProj", "../bad", _run(tmp_path))


def test_corpus_exists_leaves_first_file_identical(sandbox_root, tmp_path):
    store = _store()
    store.seed_corpus("FakeProj", "baseline", _run(tmp_path))
    path = paths.corpus_path("FakeProj", "baseline")
    path.write_bytes(path.read_bytes() + b"\n")  # the user edits it
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    with pytest.raises(store.CorpusExists) as caught:
        store.seed_corpus("FakeProj", "baseline", _run(tmp_path))
    assert isinstance(caught.value, FileExistsError)
    assert caught.value.reason == "corpus_exists" and caught.value.name == "baseline"
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


# --------------------------------------------------------------------------
# load_corpus: whole-file validation, JSON path of the first fault
# --------------------------------------------------------------------------

def test_load_round_trips_a_seeded_corpus(sandbox_root, tmp_path):
    store = _store()
    store.seed_corpus("FakeProj", "baseline", _run(tmp_path))
    corpus = store.load_corpus("FakeProj", "baseline")
    assert corpus.name == "baseline"
    assert corpus.path == paths.corpus_path("FakeProj", "baseline")
    assert [a["word"] for a in corpus.assertions] == ["membaca", "xyz", "café"]
    assert corpus.assertions[0]["expected"] == [MEM_BACA, ME_MBACA]
    assert corpus.duplicates == []
    assert corpus.data["schema"] == "flextoolsmcp.hc-corpus/1"


def test_load_missing_corpus(sandbox_root):
    store = _store()
    with pytest.raises(store.CorpusNotFound) as caught:
        store.load_corpus("FakeProj", "nope")
    assert caught.value.reason == "corpus_not_found" and caught.value.name == "nope"
    with pytest.raises(paths.SandboxNameError):
        store.load_corpus("FakeProj", "..")


@pytest.mark.parametrize("data,json_path", [
    ("{trunc", "$"),
    ("[]", "$"),
    ({**_good_corpus(), "schema": "flextoolsmcp.hc-corpus/9"}, "$.schema"),
    (_without("schema"), "$.schema"),
    ({**_good_corpus(), "assertions": {}}, "$.assertions"),
    (_without("assertions"), "$.assertions"),
    (_with([{"word": "ok", "expected": []}, "nope"]), "$.assertions[1]"),
    (_with([{"word": "", "expected": []}]), "$.assertions[0].word"),
    (_with([{"word": 3, "expected": []}]), "$.assertions[0].word"),
    (_with([{"expected": []}]), "$.assertions[0].word"),
    (_with([{"word": "w"}]), "$.assertions[0].expected"),
    (_with([{"word": "w", "expected": "x"}]), "$.assertions[0].expected"),
    (_with([{"word": "w", "expected": [[]]}]), "$.assertions[0].expected[0]"),
    (_with([{"word": "w", "expected": [MEM_BACA, "x"]}]), "$.assertions[0].expected[1]"),
    (_with([{"word": "w", "expected": [[MEM_BACA[0], "m"]]}]),
     "$.assertions[0].expected[0][1]"),
    (_with([{"word": "w", "expected": [[{"gloss": "g"}]]}]),
     "$.assertions[0].expected[0][0].form"),
    (_with([{"word": "w", "expected": [[{"form": "f", "gloss": None}]]}]),
     "$.assertions[0].expected[0][0].gloss"),
    # The FIRST fault is named, not a later one.
    (_with([{"word": "ok", "expected": []}, {"word": ""}, {"word": 5}]),
     "$.assertions[1].word"),
])
def test_corpus_invalid_names_first_fault(sandbox_root, data, json_path):
    store = _store()
    _write_corpus("FakeProj", "bad", data)
    with pytest.raises(store.CorpusInvalid) as caught:
        store.load_corpus("FakeProj", "bad")
    assert caught.value.reason == "corpus_invalid"
    assert caught.value.name == "bad"
    assert caught.value.json_path == json_path
    assert caught.value.detail


def test_not_expressible_assertion_is_not_invalid(sandbox_root):
    """FR-027 is a run-time `error`, not a load refusal."""
    store = _store()
    _write_corpus("FakeProj", "c", _with([
        {"word": "w", "expected": [[{"form": "a b", "gloss": "x:y"}]]},
    ]))
    assert len(store.load_corpus("FakeProj", "c").assertions) == 1


def test_nfc_duplicates_dedupe_keeping_first(sandbox_root):
    store = _store()
    _write_corpus("FakeProj", "c", _with([
        {"word": "café", "expected": []},
        {"word": "x", "expected": [MEM_BACA]},
        {"word": "café", "expected": [MEM_BACA]},
        {"word": "x", "expected": []},
    ]))
    corpus = store.load_corpus("FakeProj", "c")
    assert corpus.assertions == [{"word": "café", "expected": []},
                                 {"word": "x", "expected": [MEM_BACA]}]
    assert corpus.duplicates == [
        {"word": "café", "index": 2, "kept_index": 0},
        {"word": "x", "index": 3, "kept_index": 1},
    ]


def test_load_accepts_a_bom(sandbox_root):
    store = _store()
    path = _write_corpus("FakeProj", "c", "")
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(_good_corpus()).encode("utf-8"))
    assert len(store.load_corpus("FakeProj", "c").assertions) == 2


# --------------------------------------------------------------------------
# list_corpora (contracts section 5.4, the corpora half)
# --------------------------------------------------------------------------

def test_list_corpora(sandbox_root, tmp_path):
    store = _store()
    assert store.list_corpora("FakeProj") == []
    assert not (sandbox_root / "corpora").exists()
    store.seed_corpus("FakeProj", "b-seeded", _run(tmp_path))
    _write_corpus("FakeProj", "a-hand", _good_corpus())
    _write_corpus("FakeProj", "c-broken", "{trunc")
    croot = paths.corpora_dir("FakeProj")
    (croot / "notes.txt").write_text("x", encoding="utf-8")
    (croot / "bad name.json").write_text(json.dumps(_good_corpus()), encoding="utf-8")
    before = _tree(croot)
    listed = store.list_corpora("FakeProj")
    assert listed == [
        {"name": "a-hand", "path": str(croot / "a-hand.json"), "assertion_count": 2},
        {"name": "b-seeded", "path": str(croot / "b-seeded.json"), "assertion_count": 3},
        {"name": "c-broken", "path": str(croot / "c-broken.json"), "assertion_count": None},
    ]
    assert set(store.CORPUS_LIST_KEYS) == {"name", "path", "assertion_count"}
    assert _tree(croot) == before
