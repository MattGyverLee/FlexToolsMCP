"""Live shared-mode peer check for FlexToolsMCP #93 CP4.

Premise under test: with projectSharing="true", LCM promotes the backend to
SharedXMLBackendProvider and a SECOND process can attach and write while a
first process holds the project open. The CP4 gate is only correct if that
premise holds -- otherwise "proceed on open_shared" would just move the
failure from the pre-flight into LCM.

Runs against the real 'Target' scratch project (sharing=True, per
CLAUDE.md's write-path project). Created objects are TEST_ prefixed and
deleted in the reader pass.

Usage: python live_shared_peer.py <hold|write|read|cleanup> <marker> [readyfile] [releasefile]
"""
import os
import sys
import time
import traceback

PROJECT = "Target"


def _init():
    from flexicon import FLExInitialize
    FLExInitialize()


def _open(write_enabled):
    from flexicon import FLExProject
    p = FLExProject()
    kwargs = {"writeEnabled": write_enabled}
    try:
        from flexicon.code.headless_ui import HeadlessLcmUI
        kwargs["ui"] = HeadlessLcmUI()
        ui_note = "HeadlessLcmUI"
    except Exception:
        ui_note = "default FwLcmUI (headless_ui unavailable in this flexicon)"
    p.OpenProject(PROJECT, **kwargs)
    print(f"[INFO] opened {PROJECT} writeEnabled={write_enabled} ui={ui_note}", flush=True)
    return p


def _backend(p):
    """Name the LCM backend actually in use -- the whole point of the check."""
    try:
        sl = p.project.ServiceLocator
        from SIL.LCModel.Infrastructure import IDataStorer
        return type(sl.GetInstance[IDataStorer]()).__name__
    except Exception:
        try:
            return type(p.project.ServiceLocator.GetInstance(IDataStorer)).__name__
        except Exception as e:
            return f"(unavailable: {e})"


def mode_hold(marker, ready, release):
    _init()
    p = _open(False)
    print(f"[INFO] holder backend = {_backend(p)}", flush=True)
    with open(ready, "w") as f:
        f.write(str(os.getpid()))
    print(f"[HOLD] holding {PROJECT} as PID {os.getpid()}", flush=True)
    deadline = time.time() + 300
    while not os.path.exists(release) and time.time() < deadline:
        time.sleep(0.5)
    p.CloseProject()
    print("[HOLD] released", flush=True)


def mode_write(marker, *_):
    _init()
    p = _open(True)
    print(f"[INFO] writer backend = {_backend(p)}", flush=True)
    before = len(list(p.LexEntry.GetAll()))
    print(f"[PRE ] entry count = {before}", flush=True)
    created = p.LexEntry.Create(lexeme_form=marker)
    print(f"[WRITE] created {marker!r} -> {created is not None}", flush=True)
    p.CloseProject()
    print(f"[POST] closed; pre-state count was {before}", flush=True)


def mode_read(marker, *_):
    """Re-query the LCM in a FRESH process: asserting on the value we passed
    in would prove nothing."""
    _init()
    p = _open(False)
    forms = []
    for e in p.LexEntry.GetAll():
        try:
            forms.append(str(e.LexemeFormOA.Form.BestVernacularAlternative.Text))
        except Exception:
            pass
    hit = marker in forms
    print(f"[READ] total entries = {len(forms)}", flush=True)
    print(f"[READ] {marker!r} present after reopen = {hit}", flush=True)
    p.CloseProject()
    print("PASS" if hit else "FAIL", flush=True)
    sys.exit(0 if hit else 1)


def mode_cleanup(marker, *_):
    _init()
    p = _open(True)
    removed = 0
    for e in list(p.LexEntry.GetAll()):
        try:
            if str(e.LexemeFormOA.Form.BestVernacularAlternative.Text) == marker:
                p.LexEntry.Delete(e)
                removed += 1
        except Exception:
            pass
    p.CloseProject()
    print(f"[CLEAN] removed {removed} entr(ies) named {marker!r}", flush=True)


if __name__ == "__main__":
    try:
        globals()["mode_" + sys.argv[1]](*sys.argv[2:])
    except Exception:
        traceback.print_exc()
        sys.exit(2)
