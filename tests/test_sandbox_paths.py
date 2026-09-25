"""parser-check CP5 T010: sandbox/paths.py -- roots, name rule, FR-042 guard."""

from pathlib import Path

import pytest

from flextoolsmcp.server.filing import paths as filing_paths
from flextoolsmcp.server.sandbox import paths as sp


@pytest.fixture
def root(tmp_path, monkeypatch):
    projects = tmp_path / "Projects"
    (projects / "Demo").mkdir(parents=True)
    monkeypatch.setattr(filing_paths, "projects_directory", lambda: projects)
    sandbox = tmp_path / "sandbox-root"
    monkeypatch.setenv(sp.ENV_VAR, str(sandbox))
    return sandbox


def test_default_root_is_under_home(monkeypatch):
    monkeypatch.delenv(sp.ENV_VAR, raising=False)
    assert sp.get_sandbox_root() == Path.home() / ".flextoolsmcp" / "parse"


def test_env_override(root):
    assert sp.get_sandbox_root() == root
    assert sp.config_cache_dir("Demo") == filing_paths._real(root / "config-cache" / "Demo")
    assert sp.sandboxes_dir("Demo").parts[-2:] == ("sandboxes", "Demo")
    assert sp.corpora_dir("Demo").parts[-2:] == ("corpora", "Demo")
    assert sp.corpus_path("Demo", "base").parts[-3:] == ("corpora", "Demo", "base.json")
    assert sp.sandbox_dir("Demo", "tighten-env").parts[-3:] == ("sandboxes", "Demo", "tighten-env")


def test_helpers_do_not_create_directories(root):
    sp.sandbox_dir("Demo", "x")
    sp.config_cache_dir("Demo")
    assert not root.exists()


def test_work_dir_requires_a_server_run_id(root):
    run_id = "a" * 32
    assert sp.work_dir(run_id).parts[-2:] == ("work", run_id)
    for bad in ("..", "abc", "A" * 32, "../" + "a" * 29, ""):
        with pytest.raises(sp.SandboxPathError):
            sp.work_dir(bad)


@pytest.mark.parametrize("name,ok", [
    ("a", True),
    ("tighten-env", True),
    ("v1.2_x", True),
    ("0start", True),
    ("A" * 64, True),
    ("A" * 65, False),
    ("", False),
    (None, False),
    (42, False),
    ("-lead", False),
    (".hidden", False),
    ("_x", False),
    ("with space", False),
    ("a/b", False),
    ("a\\b", False),
    ("a:b", False),
    ("CON", False),
    ("con", False),
    ("nul.txt", False),
    ("Com1", False),
    ("LPT9.cfg.x", False),
    ("COM0", True),
    ("CONSOLE", True),
    ("x.CON", True),
    ("trail.", False),
    ("a..b", False),
    ("café", False),
])
def test_name_rule(name, ok):
    assert (sp.validate_name(name) is None) is ok
    if ok:
        assert sp.require_valid_name(name) == name
    else:
        with pytest.raises(sp.SandboxNameError) as exc:
            sp.require_valid_name(name)
        assert exc.value.reason == "name_invalid"
        assert exc.value.detail
        assert isinstance(exc.value, sp.SandboxPathError)


def test_invalid_name_refused_when_composing(root):
    with pytest.raises(sp.SandboxNameError):
        sp.sandbox_dir("Demo", "..")
    with pytest.raises(sp.SandboxNameError):
        sp.corpus_path("Demo", "aux")


@pytest.mark.parametrize("bad", ["", " ", ".", "..", "a/b", "a\\b", "C:x", "x.", "x ", None])
def test_project_component_refuses_non_components(bad):
    with pytest.raises(sp.SandboxPathError):
        sp.project_component(bad)


def test_project_component_is_verbatim():
    assert sp.project_component("Sena 3") == "Sena 3"


def test_root_inside_a_project_is_refused(tmp_path, monkeypatch):
    projects = tmp_path / "Projects"
    (projects / "Demo").mkdir(parents=True)
    monkeypatch.setattr(filing_paths, "projects_directory", lambda: projects)
    monkeypatch.setenv(sp.ENV_VAR, str(projects / "Demo" / "sandbox"))
    calls = (
        sp.sandbox_root,
        sp.config_cache_root,
        sp.sandboxes_root,
        sp.corpora_root,
        sp.work_root,
        lambda: sp.sandboxes_dir("Demo"),
        lambda: sp.corpus_path("Demo", "x"),
        lambda: sp.work_dir("b" * 32),
    )
    for call in calls:
        with pytest.raises(filing_paths.ArtifactInsideProject):
            call()
    # Case-insensitive, and the projects root itself counts.
    monkeypatch.setenv(sp.ENV_VAR, str(tmp_path / "PROJECTS"))
    with pytest.raises(filing_paths.ArtifactInsideProject):
        sp.sandbox_root()


def test_guard_runs_at_use_not_import(monkeypatch, root):
    assert sp.sandbox_root()
    monkeypatch.setattr(filing_paths, "projects_directory", lambda: root.parent)
    with pytest.raises(filing_paths.ArtifactInsideProject):
        sp.sandbox_root()


def test_is_under(tmp_path):
    area = tmp_path / "config-cache"
    assert sp.is_under(area / "P" / "k", area)
    assert sp.is_under(str(area / "p"), str(tmp_path / "CONFIG-CACHE"))
    assert not sp.is_under(area, area)
    assert sp.is_under(area, area, strict=False)
    assert not sp.is_under(tmp_path / "sandboxes" / "P", area)
    assert not sp.is_under(area / ".." / "sandboxes", area)
    assert not sp.is_under(tmp_path / "config-cache-evil", area)
    with pytest.raises(sp.SandboxPathError):
        sp.assert_under(tmp_path / "corpora" / "x.json", area)
    assert sp.assert_under(area / "x", area).name == "x"


def test_unknown_area_refused(root):
    with pytest.raises(sp.SandboxPathError):
        sp.area_root("elsewhere")
