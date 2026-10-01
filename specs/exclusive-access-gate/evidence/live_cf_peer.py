"""Live Class B check: is a custom-field definition from a peer lost? (V7, T029)

specs/exclusive-access-gate research R9. With FLEx holding Sena 3 open in
shared mode, a SECOND process (this one) attaches as a non-master peer and
adds a custom-field DEFINITION the way FLEx's own Custom Fields dialog does
(FieldDescription.UpdateCustomField inside a non-undoable task), then commits.

LCM source says the definition cannot persist: CommitLogRecord carries only
object adds/updates/deletes (CommitLogRecord.cs:23-48) and PerformCommit
writes only the master's own custom-field list
(SharedXMLBackendProvider.cs:429,479). This harness observes whether that
holds live. It writes NO data to the field, so a lost definition cannot leave
orphan data behind.

Runs outside run_module on purpose: the MCP's own gate now refuses this
script while FLEx is open (requires_exclusive_access), which is the point.

Usage (FLEXLIBS_REQUIRE_LIVE=1, from the worktree):
    python live_cf_peer.py dry      # open read-only, report what WOULD be done
    python live_cf_peer.py add      # peer-add the zzExclTest definition, commit
    python live_cf_peer.py check    # fresh read-only open: is zzExclTest defined?

Plain ASCII output only.
"""
import os
import sys
import traceback

PROJECT = "Sena 3"  # the designated test project -- never a work project
FIELD_NAME = "zzExclTest"
OWNER_CLASS = "LexEntry"


def _require_test_project():
    assert PROJECT == "Sena 3", "V7 runs only on the Sena 3 test project"
    if os.environ.get("FLEXLIBS_REQUIRE_LIVE") != "1":
        print("[WARN] FLEXLIBS_REQUIRE_LIVE is not 1; set it for a recorded live run", flush=True)


def _open(write_enabled):
    from flexicon import FLExInitialize, FLExProject

    FLExInitialize()
    p = FLExProject()
    kwargs = {"writeEnabled": write_enabled}
    try:
        from flexicon.code.headless_ui import HeadlessLcmUI
        kwargs["ui"] = HeadlessLcmUI()
        ui_note = "HeadlessLcmUI"
    except Exception:
        ui_note = "default FwLcmUI"
    p.OpenProject(PROJECT, **kwargs)
    print(f"[INFO] opened {PROJECT!r} writeEnabled={write_enabled} ui={ui_note}", flush=True)
    return p


def _backend(cache):
    try:
        from SIL.LCModel.Infrastructure import IDataStorer
        return type(cache.ServiceLocator.GetInstance[IDataStorer]()).__name__
    except Exception as e:
        return f"(unavailable: {e})"


def _defined(cache):
    """Is FIELD_NAME a custom field on OWNER_CLASS in this cache?"""
    from SIL.LCModel import FieldDescription

    for fd in FieldDescription.FieldDescriptors(cache):
        try:
            if fd.IsCustomField and fd.Name == FIELD_NAME:
                return True
        except Exception:
            continue
    return False


def mode_dry():
    p = _open(False)
    cache = p.project
    print(f"[DRY ] backend = {_backend(cache)}", flush=True)
    print(f"[DRY ] {FIELD_NAME!r} already defined = {_defined(cache)}", flush=True)
    print(f"[DRY ] would add custom field {FIELD_NAME!r} on {OWNER_CLASS} "
          "(MultiUnicode, analysis WS) via FieldDescription.UpdateCustomField "
          "inside NonUndoableUnitOfWorkHelper.Do, then commit. No data written.", flush=True)
    p.CloseProject()


def mode_add():
    from System import Action
    from SIL.LCModel import FieldDescription, LexEntryTags
    from SIL.LCModel.Core.Cellar import CellarPropertyType
    from SIL.LCModel.DomainServices import WritingSystemServices
    from SIL.LCModel.Infrastructure import NonUndoableUnitOfWorkHelper

    p = _open(True)
    cache = p.project
    print(f"[INFO] backend = {_backend(cache)}", flush=True)
    pre = _defined(cache)
    print(f"[PRE ] {FIELD_NAME!r} defined = {pre}", flush=True)
    if pre:
        print("[STOP] definition already present; delete it in FLEx first", flush=True)
        p.CloseProject()
        sys.exit(3)

    def _add():
        fd = FieldDescription(cache)
        fd.Class = LexEntryTags.kClassId
        fd.Name = FIELD_NAME
        fd.Userlabel = FIELD_NAME
        fd.HelpString = "exclusive-access-gate V7 probe; safe to delete"
        fd.Type = CellarPropertyType.MultiUnicode
        fd.WsSelector = WritingSystemServices.kwsAnal
        fd.UpdateCustomField()
        try:
            FieldDescription.ClearDataAbout()
        except Exception as e:
            print(f"[WARN] ClearDataAbout failed: {e}", flush=True)

    NonUndoableUnitOfWorkHelper.Do(cache.ActionHandlerAccessor, Action(_add))
    print(f"[WRITE] UpdateCustomField returned; in-process defined = {_defined(cache)}", flush=True)
    p.CloseProject()  # commits as a non-master peer
    print("[POST] closed (committed). Now check FLEx's Custom Fields dialog, "
          "then close and reopen FLEx and check again; then run `check`.", flush=True)


def mode_check():
    """Re-query from a FRESH process: the value this harness passed in proves nothing."""
    p = _open(False)
    hit = _defined(p.project)
    print(f"[READ] {FIELD_NAME!r} defined after reopen = {hit}", flush=True)
    p.CloseProject()
    print("DEFINITION SURVIVED" if hit else "DEFINITION GONE", flush=True)


if __name__ == "__main__":
    try:
        _require_test_project()
        mode = sys.argv[1] if len(sys.argv) > 1 else "dry"
        globals()["mode_" + mode]()
    except Exception:
        traceback.print_exc()
        sys.exit(2)
