"""Live driver for quickstart V1-V5 (T036, T025): calls the WORKTREE's handlers.

This session's MCP server runs the main checkout, which has no exclusive-access
gate. This driver imports `flextoolsmcp` from this worktree's `src/` and
drives `handle_start` + `handle_run_module` exactly as the MCP tool would.

Usage (from the worktree, FLEXLIBS_REQUIRE_LIVE=1):
    python live_gate_driver.py probe
    python live_gate_driver.py ws-list          # read-only WS listing + .ldml mtimes
    python live_gate_driver.py v1 <ws-tag>      # write-enabled Ensure(<existing tag>)
    python live_gate_driver.py v2 <ws-tag>      # same, validate_only
    python live_gate_driver.py run <file.py> [--write]   # arbitrary snippet
Plain ASCII output.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parents[2]
# Both roots, as tests/conftest.py and the server entry point arrange them:
# validate_server_state() imports its helpers as top-level `server.*`.
sys.path.insert(0, str(WORKTREE / "src" / "flextoolsmcp"))
sys.path.insert(0, str(WORKTREE / "src"))

PROJECT = "Sena 3"
assert PROJECT == "Sena 3", "live gate checks run only on the Sena 3 test project"

from flextoolsmcp.server import kernel  # noqa: E402
from flextoolsmcp.server.handlers import admin, execution  # noqa: E402
from flextoolsmcp.server.project_access import probe_project_access  # noqa: E402


def _text(resp):
    item = resp[0]
    return item["text"] if isinstance(item, dict) else item.text


def _ascii(obj):
    return json.dumps(obj, indent=2, ensure_ascii=True)


async def _start(write_enabled):
    if kernel.get_operations_logger() is None:
        kernel.init_operations_logger()
    if kernel.get_api_index() is None:
        # As server.py does at startup; without it preflight falls back to
        # static lists that predate project.WritingSystems.
        from flextoolsmcp.server import APIIndex, get_index_dir

        kernel.set_api_index(APIIndex.load(get_index_dir()))
    data = json.loads(_text(await admin.handle_start({
        "project_name": PROJECT, "api_mode": "flexicon", "write_enabled": write_enabled,
    })))
    print(f"[START] status={data.get('status')} write_enabled={write_enabled}", flush=True)


async def _run(code, *, write_enabled, confirmed=True, validate_only=False):
    await _start(write_enabled)
    args = {
        "code": code, "project_name": PROJECT, "write_enabled": write_enabled,
        "confirmed": confirmed, "skip_api_check": True, "skip_module_check": True,
    }
    if validate_only:
        args["validate_only"] = True
    return json.loads(_text(await execution.handle_run_module(args)))


def _ldml_mtimes():
    from flextoolsmcp.server.project_discovery import get_projects_directory

    projects_dir = get_projects_directory()
    if isinstance(projects_dir, tuple):  # (path, source) on current builds
        projects_dir = projects_dir[0]
    store = Path(projects_dir) / PROJECT / "WritingSystemStore"
    return {p.name: p.stat().st_mtime for p in sorted(store.glob("*.ldml"))}


WS_LIST = (
    "for label, tags in (('vern', project.WritingSystems.GetVernacular()),\n"
    "                    ('anal', project.WritingSystems.GetAnalysis())):\n"
    "    report.Info(label + ': ' + ', '.join(str(project.WritingSystems.GetLanguageTag(t)) for t in tags))\n"
)


def main():
    mode = sys.argv[1]
    print(f"[ENV ] FLEXLIBS_REQUIRE_LIVE={os.environ.get('FLEXLIBS_REQUIRE_LIVE')}", flush=True)
    a = probe_project_access(PROJECT)
    print(f"[PROBE] verdict={a.verdict} sharing={a.sharing_enabled} holder={a.holder}", flush=True)
    if mode == "probe":
        return
    if mode == "ws-list":
        data = asyncio.run(_run(WS_LIST, write_enabled=False))
        for m in data.get("messages", []):
            print(f"[WS  ] {m.get('message') or m}", flush=True)
        print(f"[WS  ] success={data.get('success')} error={data.get('error')}", flush=True)
        print("[LDML] " + _ascii(_ldml_mtimes()), flush=True)
        return
    if mode in ("v1", "v2"):
        tag = sys.argv[2]
        code = f"if modifyAllowed:\n    project.WritingSystems.Ensure({tag!r})\n"
        pre = _ldml_mtimes()
        data = asyncio.run(_run(code, write_enabled=True, validate_only=(mode == "v2")))
        post = _ldml_mtimes()
        if mode == "v1":
            keys = ("status", "error_code", "message", "verdict", "holder_pid",
                    "holder_process", "operations", "guidance", "remedy", "op_id")
            print("[RESP] " + _ascii({k: data.get(k) for k in keys}), flush=True)
        else:
            print("[RESP] " + _ascii({
                "status": data.get("status"),
                "project_lock": data.get("project_lock"),
            }), flush=True)
        print(f"[LDML] unchanged={pre == post} files={len(pre)}", flush=True)
        return
    if mode == "run":
        code = Path(sys.argv[2]).read_text(encoding="utf-8")
        write = "--write" in sys.argv
        data = asyncio.run(_run(code, write_enabled=write))
        for m in data.get("messages", []):
            print(f"[MSG ] {m.get('message') or m}", flush=True)
        keys = ("success", "status", "error_code", "error", "message", "stage", "remedy",
                "operations", "exclusive_access", "peer_schema_guard", "warnings",
                "shared_mode", "shared_mode_read_back", "backup", "op_id")
        print("[RESP] " + _ascii({k: data.get(k) for k in keys if k in data}), flush=True)
        return
    raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
