#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for Phase 7 US5: promote CLI (FR-030, FR-031).

Contract under test (src/flextoolsmcp/recipe_cli.py):
- `flextools-mcp-recipe promote <local-id> --id <new-id> [--out DIR] [--force]`
- Writes `<DIR or ~/.flextoolsmcp/recipe-drafts>/<new-id>.py` and prints the path.
- Prints one `scrub before shipping: L<n>: <text>` line per GUID literal,
  Windows user path, or record-projects / forbidden-names hit.
- Exit codes: 0 written; 2 unknown local id (nearest ids); 3 target exists
  without --force; 4 bad new-id (not kebab-case) or shipped-id collision.
- Draft parses with `recipe_files` but fails validation on
  `match_terms` / `notes` (human must fill them).
"""

from pathlib import Path



def _import_cli():
    import importlib

    return importlib.import_module("flextoolsmcp.recipe_cli")


def _make_local_record(tmp_store: Path, code: str, intent="List entries test",
                        project="Sena 3"):
    import importlib

    lr = importlib.import_module("flextoolsmcp.server.local_recipes")
    import os

    old = os.environ.get("FLEXTOOLSMCP_RECIPE_DIR")
    os.environ["FLEXTOOLSMCP_RECIPE_DIR"] = str(tmp_store)
    try:
        rec = lr.capture(
            code,
            user_intent=intent,
            project=project,
            requires_write=False,
            op_id="op-promote-test-001",
        )
    finally:
        if old is None:
            os.environ.pop("FLEXTOOLSMCP_RECIPE_DIR", None)
        else:
            os.environ["FLEXTOOLSMCP_RECIPE_DIR"] = old
    assert rec is not None, "capture refused the fixture code"
    return rec


PROMOTE_CODE = (
    "from flexicon import LexEntryOperations\n"
    "entries = project.LexEntry.GetAll()\n"
    "for entry in entries:\n"
    "    headword = project.LexEntry.GetHeadword(entry)\n"
    "    report.Info(headword)\n"
)


def test_promote_default_out_dir_under_tmp_home(tmp_path, monkeypatch, capsys):
    cli = _import_cli()
    store = tmp_path / "store"
    store.mkdir()
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(store))
    rec = _make_local_record(store, PROMOTE_CODE)
    rc = cli.main(["promote", rec["id"], "--id", "promote-default-out"])
    assert rc == 0
    expected = fake_home / ".flextoolsmcp" / "recipe-drafts" / "promote-default-out.py"
    assert expected.is_file(), f"draft not at default out {expected}"
    out, _ = capsys.readouterr()
    assert "promote-default-out.py" in out


def test_promote_out_flag(tmp_path, monkeypatch):
    cli = _import_cli()
    store = tmp_path / "store"
    store.mkdir()
    outdir = tmp_path / "drafts"

    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(store))
    rec = _make_local_record(store, PROMOTE_CODE)
    rc = cli.main(["promote", rec["id"], "--id", "promote-out-flag",
                   "--out", str(outdir)])
    assert rc == 0
    assert (outdir / "promote-out-flag.py").is_file()


def test_promote_refuses_overwrite_without_force(tmp_path, monkeypatch):
    cli = _import_cli()
    store = tmp_path / "store"
    store.mkdir()
    outdir = tmp_path / "drafts"
    outdir.mkdir()
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(store))
    rec = _make_local_record(store, PROMOTE_CODE)
    rc1 = cli.main(["promote", rec["id"], "--id", "promote-overwrite",
                    "--out", str(outdir)])
    assert rc1 == 0
    rc2 = cli.main(["promote", rec["id"], "--id", "promote-overwrite",
                    "--out", str(outdir)])
    assert rc2 == 3
    rc3 = cli.main(["promote", rec["id"], "--id", "promote-overwrite",
                    "--out", str(outdir), "--force"])
    assert rc3 == 0


def test_promote_unknown_id_exit_2(tmp_path, monkeypatch, capsys):
    cli = _import_cli()
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(store))
    _make_local_record(store, PROMOTE_CODE)
    rc = cli.main(["promote", "local-doesnotexist", "--id", "promote-unknown"])
    assert rc == 2
    out, _ = capsys.readouterr()
    assert "local-" in out.lower() or "nearest" in out.lower() or "did you mean" in out.lower()


def test_promote_bad_id_exit_4(tmp_path, monkeypatch):
    cli = _import_cli()
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(store))
    rec = _make_local_record(store, PROMOTE_CODE)
    rc = cli.main(["promote", rec["id"], "--id", "Bad_ID"])
    assert rc == 4


def test_promote_shipped_collision_exit_4(tmp_path, monkeypatch):
    cli = _import_cli()
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(store))
    rec = _make_local_record(store, PROMOTE_CODE)
    rc = cli.main(["promote", rec["id"], "--id", "parser-coverage"])
    assert rc == 4


def test_promote_scrub_lines(tmp_path, monkeypatch, capsys):
    cli = _import_cli()
    store = tmp_path / "store"
    store.mkdir()
    outdir = tmp_path / "drafts"
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(store))
    code = (
        "from flexicon import LexEntryOperations\n"
        "GUID = \"12345678-1234-1234-1234-123456789abc\"\n"
        "p = \"C:\\\\Users\\\\someone\\\\data\\\\lexicon\"\n"
        "entries = project.LexEntry.GetAll()\n"
        "for entry in entries:\n"
        "    report.Info(project.LexEntry.GetHeadword(entry))\n"
    )
    rec = _make_local_record(store, code, project="Sena 3")
    rc = cli.main(["promote", rec["id"], "--id", "promote-scrub",
                   "--out", str(outdir)])
    assert rc == 0
    out, _ = capsys.readouterr()
    assert "scrub before shipping" in out.lower()
    assert "12345678-1234-1234-1234-123456789abc"[:8] in out
    # The user-path line itself must be flagged. Matching "C:" anywhere in
    # `out` passed on Windows only via the printed draft path.
    assert "L3: p = " in out


def test_promote_scrub_project_name(tmp_path, monkeypatch, capsys):
    cli = _import_cli()
    store = tmp_path / "store"
    store.mkdir()
    outdir = tmp_path / "drafts2"
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(store))
    code = (
        "from flexicon import LexEntryOperations\n"
        "# touched in MyTestProject run\n"
        "entries = project.LexEntry.GetAll()\n"
        "for entry in entries:\n"
        "    report.Info(project.LexEntry.GetHeadword(entry))\n"
    )
    rec = _make_local_record(store, code, project="MyTestProject")
    rc = cli.main(["promote", rec["id"], "--id", "promote-scrub-proj",
                   "--out", str(outdir)])
    assert rc == 0
    out, _ = capsys.readouterr()
    assert "MyTestProject" in out


def test_promote_draft_parses_but_fails_validation(tmp_path, monkeypatch):
    import importlib

    cli = _import_cli()
    rf = importlib.import_module("flextoolsmcp.recipe_files")
    rv = importlib.import_module("flextoolsmcp.recipe_validator")
    store = tmp_path / "store"
    store.mkdir()
    outdir = tmp_path / "drafts"
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(store))
    rec = _make_local_record(store, PROMOTE_CODE)
    rc = cli.main(["promote", rec["id"], "--id", "promote-draft-check",
                   "--out", str(outdir)])
    assert rc == 0
    text = (outdir / "promote-draft-check.py").read_text(encoding="utf-8")
    # Parses as a recipe file.
    recipe = rf.parse_recipe_source(text, filename="promote-draft-check.py")
    assert recipe["id"] == "promote-draft-check"
    # But fails shipped validation until a human fills match_terms/notes.
    result = rv.validate_recipe(recipe, None, shipped=True)
    assert not result["passed"]
    blob = " ".join(result["issues"]).lower()
    assert "match_terms" in blob or "notes" in blob


def test_promote_console_output_ascii_only(tmp_path, monkeypatch, capsys):
    cli = _import_cli()
    store = tmp_path / "store"
    store.mkdir()
    outdir = tmp_path / "drafts"
    monkeypatch.setenv("FLEXTOOLSMCP_RECIPE_DIR", str(store))
    rec = _make_local_record(store, PROMOTE_CODE)
    rc = cli.main(["promote", rec["id"], "--id", "promote-ascii",
                   "--out", str(outdir)])
    assert rc == 0
    out, err = capsys.readouterr()
    combined = out + err
    combined.encode("ascii")
