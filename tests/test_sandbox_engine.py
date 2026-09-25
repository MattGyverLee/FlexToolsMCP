"""parser-check CP5 T035: sandbox/engine.py -- the engine check (FR-036, research R-02).

The check reads the LIVE `.fwdata` as a plain file stream (read-only, sharing
read and write, so FLEx may hold it open), stops at the first
`<rt class="MoMorphData">`, takes its `ParserParameters` text and hands that
inner XML to `parse/measure.summarize_parser_parameters` (looked up on the
module at call time). It never imports flexicon, flexlibs, pythonnet or LCM and
never takes the `.fwdata.lock`. It fails SAFE: anything it cannot read counts
as XAmple, but with a hint saying the value "could not be read" -- distinct
from the "is XAmple" hint -- so a mid-save read is recognisable.

API specified here (T044 implements it):

    engine.HINT_UNREADABLE_PHRASE  == "could not be read"
    engine.READ_ATTEMPTS           == 2      # one retry
    engine.RETRY_DELAY_SECONDS     (float, patchable; tests set 0)
    engine.REASON_ABSENT / REASON_UNPARSEABLE / REASON_NO_MORPH_DATA /
        REASON_READ_ERROR          == "absent" / "unparseable" /
                                      "no_morph_data" / "read_error"
    engine._open_fwdata(path) -> binary file object
        the single open seam (patchable); every read goes through it.
    engine.file_key(fwdata) -> (abs_path: str, size: int, mtime_ns: int)
    engine.read_engine(fwdata) -> EngineReading       # never raises
    engine.check_engine(fwdata, *, supported_engines=("HC",)) -> EngineReading
        raises parser_probe.ParserEngineMismatchError whose .detail validates
        as response_models.ParserEngineMismatchDetail.
    engine.remember(key, active_parser) -> None
        prime the memo from a cache entry's key.json (warm job, no re-scan).
    engine.clear_engine_cache() -> None

    EngineReading (frozen):
        key: (str, int, int)          # file_key at read time
        readable: bool
        active_parser: Optional[str]  # raw text read; None when unreadable
        configured_engine: str        # active_parser if readable else "XAmple"
        reason: Optional[str]         # None when readable, else a REASON_*
        parameters: Optional[dict]    # summarize_parser_parameters' result

Memo: readable results are memoised by `file_key` (the `(path, size,
mtime_ns)` the cache entry's key.json records next to `active_parser`);
unreadable results are never memoised. A memo hit returns the same
EngineReading the scan produced; a reading primed by `remember` has
`parameters=None` (key.json does not store them).
"""

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import fake_fwdata_text


def _engine():
    return importlib.import_module("flextoolsmcp.server.sandbox.engine")


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
def engine(monkeypatch):
    loaded = []

    def on_load(mod):
        loaded.append(mod)
        mod.clear_engine_cache()
        monkeypatch.setattr(mod, "RETRY_DELAY_SECONDS", 0)

    yield _LazyModule("flextoolsmcp.server.sandbox.engine", on_load)
    for mod in loaded:
        mod.clear_engine_cache()


def _write_fwdata(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _counting_open(monkeypatch, engine, *, fail_first=0, exc=None):
    """Patch `_open_fwdata`: fail the first `fail_first` calls, count all."""
    real = engine._open_fwdata
    calls = []

    def fake(path):
        calls.append(str(path))
        if len(calls) <= fail_first:
            raise exc or PermissionError(13, "The process cannot access the file")
        return real(path)

    monkeypatch.setattr(engine, "_open_fwdata", fake)
    return calls


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_constants():
    engine = _engine()
    assert engine.HINT_UNREADABLE_PHRASE == "could not be read"
    assert engine.READ_ATTEMPTS == 2
    assert (
        engine.REASON_ABSENT,
        engine.REASON_UNPARSEABLE,
        engine.REASON_NO_MORPH_DATA,
        engine.REASON_READ_ERROR,
    ) == ("absent", "unparseable", "no_morph_data", "read_error")


# ---------------------------------------------------------------------------
# HC passes, XAmple refuses
# ---------------------------------------------------------------------------


def test_hc_project_passes(engine, fake_project):
    reading = engine.check_engine(fake_project.fwdata)
    assert reading.readable is True
    assert reading.active_parser == "HC"
    assert reading.configured_engine == "HC"
    assert reading.reason is None
    assert reading.key == engine.file_key(fake_project.fwdata)


def test_file_key_is_abspath_size_mtime_ns(engine, fake_project):
    st = os.stat(fake_project.fwdata)
    path, size, mtime_ns = engine.file_key(fake_project.fwdata)
    assert Path(path) == Path(os.path.abspath(fake_project.fwdata))
    assert (size, mtime_ns) == (st.st_size, st.st_mtime_ns)


def test_parameters_go_through_summarize_parser_parameters(engine, fake_project, monkeypatch):
    from flextoolsmcp.server.parse import measure

    real = measure.summarize_parser_parameters
    seen = []

    def spy(raw):
        seen.append(raw)
        return real(raw)

    monkeypatch.setattr(measure, "summarize_parser_parameters", spy)
    reading = engine.read_engine(fake_project.fwdata)
    assert len(seen) == 1
    # The inner XML, unescaped -- as a project stores it inside <Uni>.
    assert seen[0].strip().startswith("<ParserParameters>")
    assert "<ActiveParser>HC</ActiveParser>" in seen[0]
    assert reading.parameters == real(seen[0])
    assert reading.parameters["active_parser"] == "HC"
    assert reading.parameters["hc"] == {"GuessRoots": "false", "MaxCompoundRules": "4"}


def test_xample_project_refuses_with_mismatch(engine, fake_project_factory):
    from flextoolsmcp.server import parser_probe, response_models

    project = fake_project_factory("Sena 3", active_parser="XAmple")
    with pytest.raises(parser_probe.ParserEngineMismatchError) as info:
        engine.check_engine(project.fwdata)
    detail = info.value.detail
    model = response_models.ParserEngineMismatchDetail(**detail)
    assert model.error_code == "parser_engine_mismatch"
    assert model.configured_engine == "XAmple"
    assert model.supported_engines == ["HC"]
    assert "XAmple" in model.hint
    # "is XAmple" is a different statement from "could not be read".
    assert engine.HINT_UNREADABLE_PHRASE not in model.hint


def test_read_engine_never_raises_on_xample(engine, fake_project_factory):
    project = fake_project_factory(active_parser="XAmple")
    reading = engine.read_engine(project.fwdata)
    assert reading.readable is True
    assert reading.active_parser == "XAmple"
    assert reading.configured_engine == "XAmple"


def test_comparison_is_case_sensitive(engine, fake_project_factory):
    from flextoolsmcp.server import parser_probe

    project = fake_project_factory(active_parser="hc")
    with pytest.raises(parser_probe.ParserEngineMismatchError) as info:
        engine.check_engine(project.fwdata)
    assert info.value.detail["configured_engine"] == "hc"


def test_refusal_creates_nothing_under_the_sandbox_root(engine, fake_project_factory, sandbox_root):
    from flextoolsmcp.server import parser_probe

    project = fake_project_factory(active_parser="XAmple")
    with pytest.raises(parser_probe.ParserEngineMismatchError):
        engine.check_engine(project.fwdata)
    assert list(sandbox_root.iterdir()) == []


# ---------------------------------------------------------------------------
# Fail safe: unreadable counts as XAmple, with the "could not be read" hint
# ---------------------------------------------------------------------------


def _assert_unreadable_refusal(engine, fwdata, reason):
    from flextoolsmcp.server import parser_probe, response_models

    reading = engine.read_engine(fwdata)
    assert reading.readable is False
    assert reading.active_parser is None
    assert reading.configured_engine == "XAmple"
    assert reading.reason == reason
    with pytest.raises(parser_probe.ParserEngineMismatchError) as info:
        engine.check_engine(fwdata)
    model = response_models.ParserEngineMismatchDetail(**info.value.detail)
    assert model.configured_engine == "XAmple"
    assert model.supported_engines == ["HC"]
    assert engine.HINT_UNREADABLE_PHRASE in model.hint


def test_absent_active_parser_fails_safe(engine, fake_project_factory):
    project = fake_project_factory(active_parser=None)
    _assert_unreadable_refusal(engine, project.fwdata, engine.REASON_ABSENT)


def test_unparseable_parameters_fail_safe(engine, tmp_path):
    text = fake_fwdata_text("HC")
    start = text.index("<Uni>") + len("<Uni>")
    end = text.index("</Uni>")
    # Escaped, so the FILE is well-formed but the stored document is not.
    text = text[:start] + "&lt;ParserParameters&gt;&lt;ActiveParser&gt;HC" + text[end:]
    fwdata = _write_fwdata(tmp_path / "p" / "Broken" / "Broken.fwdata", text)
    _assert_unreadable_refusal(engine, fwdata, engine.REASON_UNPARSEABLE)


def test_truncated_file_fails_safe(engine, tmp_path):
    text = fake_fwdata_text("HC")
    cut = text.index('<rt class="MoMorphData"') + 40
    fwdata = _write_fwdata(tmp_path / "p" / "Cut" / "Cut.fwdata", text[:cut])
    _assert_unreadable_refusal(engine, fwdata, engine.REASON_UNPARSEABLE)


def test_no_morph_data_rt_fails_safe(engine, tmp_path):
    text = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<languageproject version="7000072">\n'
        '<rt class="LangProject" guid="98e6df3a-faa0-4882-8779-dc207d67ea05" />\n'
        "</languageproject>\n"
    )
    fwdata = _write_fwdata(tmp_path / "p" / "Empty" / "Empty.fwdata", text)
    _assert_unreadable_refusal(engine, fwdata, engine.REASON_NO_MORPH_DATA)


def test_missing_file_fails_safe(engine, tmp_path):
    _assert_unreadable_refusal(engine, tmp_path / "nope" / "nope.fwdata", engine.REASON_READ_ERROR)


# ---------------------------------------------------------------------------
# One retry
# ---------------------------------------------------------------------------


def test_read_error_is_retried_once_then_succeeds(engine, fake_project, monkeypatch):
    calls = _counting_open(monkeypatch, engine, fail_first=1)
    reading = engine.check_engine(fake_project.fwdata)
    assert reading.configured_engine == "HC"
    assert len(calls) == 2


def test_persistent_read_error_stops_after_one_retry(engine, fake_project, monkeypatch):
    calls = _counting_open(monkeypatch, engine, fail_first=99)
    reading = engine.read_engine(fake_project.fwdata)
    assert len(calls) == engine.READ_ATTEMPTS == 2
    assert reading.readable is False
    assert reading.reason == engine.REASON_READ_ERROR
    assert reading.configured_engine == "XAmple"


def test_retry_waits_retry_delay(engine, fake_project, monkeypatch):
    slept = []
    monkeypatch.setattr(engine, "RETRY_DELAY_SECONDS", 0.01)
    monkeypatch.setattr(engine.time, "sleep", lambda s: slept.append(s))
    _counting_open(monkeypatch, engine, fail_first=1)
    engine.read_engine(fake_project.fwdata)
    assert slept == [0.01]


# ---------------------------------------------------------------------------
# Streaming: stops at the first MoMorphData rt
# ---------------------------------------------------------------------------


def test_stops_at_first_morph_data_rt(engine, tmp_path, monkeypatch):
    text = fake_fwdata_text("HC")
    tail = "</languageproject>\n"
    assert text.endswith(tail)
    filler = "".join(
        '<rt class="LexEntry" guid="%08d-0000-0000-0000-000000000000"><HomographNumber val="0" /></rt>\n'
        % i
        for i in range(40000)
    )
    # Malformed after the filler: a full parse would fail; a stream that stops
    # at MoMorphData never reaches it.
    text = text[: -len(tail)] + filler + "<rt class='Broken' <<<\n"
    fwdata = _write_fwdata(tmp_path / "p" / "Big" / "Big.fwdata", text)
    total = fwdata.stat().st_size
    assert total > 2_000_000

    positions = []
    real = engine._open_fwdata

    class Tracked:
        def __init__(self, raw):
            self._raw = raw

        def read(self, *a):
            return self._raw.read(*a)

        def readinto(self, b):
            return self._raw.readinto(b)

        def close(self):
            if not self._raw.closed:
                positions.append(self._raw.tell())
            self._raw.close()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()
            return False

        def __getattr__(self, name):
            return getattr(self._raw, name)

    monkeypatch.setattr(engine, "_open_fwdata", lambda p: Tracked(real(p)))
    reading = engine.read_engine(fwdata)
    assert reading.configured_engine == "HC"
    assert reading.readable is True
    assert positions, "the stream must be closed"
    assert positions[0] < total // 2


# ---------------------------------------------------------------------------
# Memo keyed by (path, size, mtime_ns)
# ---------------------------------------------------------------------------


def test_readable_result_is_memoised_by_file_key(engine, fake_project, monkeypatch):
    calls = _counting_open(monkeypatch, engine)
    first = engine.read_engine(fake_project.fwdata)
    second = engine.read_engine(fake_project.fwdata)
    assert len(calls) == 1
    assert first == second


def test_changed_mtime_rereads(engine, fake_project, monkeypatch):
    calls = _counting_open(monkeypatch, engine)
    engine.read_engine(fake_project.fwdata)
    st = os.stat(fake_project.fwdata)
    fake_project.fwdata.write_text(fake_fwdata_text("XAmple"), encoding="utf-8")
    os.utime(fake_project.fwdata, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    reading = engine.read_engine(fake_project.fwdata)
    assert len(calls) == 2
    assert reading.configured_engine == "XAmple"


def test_unreadable_result_is_not_memoised(engine, fake_project, monkeypatch):
    calls = _counting_open(monkeypatch, engine, fail_first=2)
    assert engine.read_engine(fake_project.fwdata).readable is False
    reading = engine.read_engine(fake_project.fwdata)
    assert reading.configured_engine == "HC"
    assert len(calls) == 3


def test_remember_primes_the_memo_from_key_json(engine, fake_project, monkeypatch):
    key = engine.file_key(fake_project.fwdata)

    def boom(path):
        raise AssertionError("a warm job must not re-scan the .fwdata")

    monkeypatch.setattr(engine, "_open_fwdata", boom)
    engine.remember(key, "HC")
    reading = engine.check_engine(fake_project.fwdata)
    assert reading.configured_engine == "HC"
    assert reading.key == key


def test_remember_under_a_stale_key_is_ignored(engine, fake_project, monkeypatch):
    path, size, mtime_ns = engine.file_key(fake_project.fwdata)
    engine.remember((path, size, mtime_ns - 1), "HC")
    calls = _counting_open(monkeypatch, engine)
    engine.read_engine(fake_project.fwdata)
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Never opens the project: no lock, no write, no LCM import
# ---------------------------------------------------------------------------


def _snapshot(directory: Path):
    return {
        str(p.relative_to(directory)): (p.read_bytes() if p.is_file() else None)
        for p in sorted(directory.rglob("*"))
    }


def test_takes_no_lock_and_writes_nothing(engine, fake_project):
    fake_project.lock.unlink()
    before = _snapshot(fake_project.dir)
    engine.check_engine(fake_project.fwdata)
    after = _snapshot(fake_project.dir)
    assert after == before
    assert not list(fake_project.dir.glob("*.lock"))


def test_reads_while_the_project_is_held_open(engine, fake_project):
    # The lock file is present (someone else holds the project) and the file
    # is open for writing elsewhere: a shared-read stream still works.
    assert fake_project.lock.exists()
    with open(fake_project.fwdata, "r+b"):
        reading = engine.check_engine(fake_project.fwdata)
    assert reading.configured_engine == "HC"
    assert fake_project.lock.read_text(encoding="utf-8") == "12345\n"


_BANNED_PREFIXES = ("flexicon", "flexlibs", "clr", "clr_loader", "pythonnet", "SIL", "System")

_PROBE = r"""
import json, sys
banned = tuple(json.loads(sys.argv[2]))
def hits():
    return sorted(m for m in sys.modules if m.split('.')[0] in banned)
before = hits()
from flextoolsmcp.server.sandbox import engine
engine.read_engine(sys.argv[1])
try:
    engine.check_engine(sys.argv[1])
except Exception:
    pass
print(json.dumps({"before": before, "after": hits()}))
"""


@pytest.mark.parametrize("active_parser", ["HC", "XAmple", None])
def test_no_flexicon_or_lcm_import(fake_project_factory, active_parser):
    _engine()  # fail as an ImportError here, not a subprocess traceback
    project = fake_project_factory(active_parser=active_parser)
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE, str(project.fwdata), json.dumps(_BANNED_PREFIXES)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result["before"] == []
    assert result["after"] == []

