"""parser-check CP5 T011 (re-plan T107): sandbox/script.py -- version, argv,
tolerant loader. Generate is the script's one remaining mode."""

from pathlib import Path

import pytest

from flextoolsmcp.server.sandbox import script


def test_script_is_packaged():
    p = script.script_path()
    assert p.is_file()
    assert p.name == "hcparse.ps1"
    assert p.parent.name == "scripts" and p.parent.parent.name == "flextoolsmcp"


def test_version_declared_exactly_once():
    text = script.script_path().read_text(encoding="utf-8-sig")
    assert len(script.VERSION_RE.findall(text)) == 1
    # 6.0.0: Parse and Test retired (T107). The version is part of every
    # cache key, so the bump rebuilds cache entries made by 5.x.
    assert script.read_hcparse_version() == "6.0.0"
    assert script.read_hcparse_version() is script.read_hcparse_version()


@pytest.mark.parametrize("text", [
    "# nothing here\n",
    "$script:HCPARSE_VERSION = '1.0.0'\n$script:HCPARSE_VERSION = '2.0.0'\n",
    "  $script:HCPARSE_VERSION = '1.0.0'\n",  # not at line start
])
def test_version_parse_requires_exactly_one(text):
    with pytest.raises(script.HcparseVersionError):
        script._parse_version(text)


def test_version_parse_multiline():
    assert script._parse_version("x\n$script:HCPARSE_VERSION   =  '9.1.2'\ny") == "9.1.2"


def test_argv_prefix_and_list():
    argv = script.build_argv("Generate", GenerateHCConfigPath=Path("C:/fw/GenerateHCConfig.exe"),
                             FwData="p.fwdata", WorkDir=None, GenerateTimeoutSeconds=600,
                             RunDir="r d")
    assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
    assert argv[:7] == ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                        "Bypass", "-File", str(script.script_path())]
    assert argv[7:] == ["-Mode", "Generate",
                        "-GenerateHCConfigPath", str(Path("C:/fw/GenerateHCConfig.exe")),
                        "-FwData", "p.fwdata", "-GenerateTimeoutSeconds", "600",
                        "-RunDir", "r d"]


def test_argv_accepts_dashed_names():
    assert script.build_argv("Generate", **{"-FwData": "x"})[-2:] == ["-FwData", "x"]


@pytest.mark.parametrize("mode,params", [
    ("generate", {}),
    ("Bogus", {}),
    ("Parse", {}),          # retired
    ("Test", {}),           # retired
    ("Generate", {"Mode": "Test"}),
    ("Generate", {"bad name": "x"}),
    ("Generate", {"Flag": True}),
])
def test_argv_rejects_bad_input(mode, params):
    with pytest.raises(ValueError):
        script.build_argv(mode, **params)


@pytest.mark.parametrize("content", [
    None,
    b"",
    b"   \n",
    b'{"schema": "x", "ite',
    b"[1, 2]",
    b"\xff\xfe\x00garbage",
])
def test_loader_tolerant(tmp_path, content):
    if content is not None:
        (tmp_path / "run.json").write_bytes(content)
    assert script.load_run_json(tmp_path) is None


def test_loader_missing_dir(tmp_path):
    assert script.load_run_json(tmp_path / "nope") is None


def test_loader_reads_an_object(tmp_path):
    (tmp_path / "run.json").write_bytes(b'\xef\xbb\xbf{"schema": "flextoolsmcp.hcparse-run/1"}')
    assert script.load_run_json(str(tmp_path)) == {"schema": "flextoolsmcp.hcparse-run/1"}
