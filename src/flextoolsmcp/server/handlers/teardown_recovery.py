# -*- coding: utf-8 -*-
"""Issue #302: teardown AbandonedMutexException recovery.

This module is deliberately stdlib-only with no package-relative imports:
its source text is embedded verbatim into the generated runner scripts
(``handle_run_module``'s runner and ``_build_scan_script``) via
:data:`RUNNER_HELPER_SOURCE`, and it is also imported normally by the
server (``teardown_next_steps``) and by the unit tests. The .NET pieces
(``System.Threading.Mutex``, SIL reflection) are imported lazily inside
the functions that need them, so importing this module never needs
pythonnet.

Background. ``LcmCache.Dispose`` saves the project's writing systems into
the machine-wide global writing-system store
(``C:\\ProgramData\\SIL\\WritingSystemRepository\\3``), which SIL guards
with a named OS mutex (``SIL.Threading.GlobalMutex``). The mutex name is
``GlobalWritingSystemRepository<T>.CurrentVersionPath(DefaultBasePath)``
with every backslash replaced by ``_`` -- e.g.
``C:_ProgramData_SIL_WritingSystemRepository_3`` (verified by reflection
against SIL.WritingSystems in FieldWorks 9: ``GlobalMutex._name`` and the
``WindowsGlobalMutexAdapter._name`` are both that string, and
``Mutex.OpenExisting`` finds it under that name / ``Local\\`` but not
``Global\\``).

When a process dies while holding that mutex, the next waiter gets an
``AbandonedMutexException`` -- which in .NET means the wait SUCCEEDED and
the waiting thread now OWNS the mutex. SIL's code lets the exception
propagate without releasing, the runner subprocess exits, and the mutex
is abandoned again: every later write run fails the same way. Releasing
the owned mutex (and clearing a stale one at run start) breaks the cycle.

Commit classification. flexicon ``CloseProject()`` runs
``usm.Save()`` (the data commit) and then, in a ``finally``,
``self.project.Dispose()``. A failure whose stack is inside
``LcmCache.Dispose`` -- and not inside the undo-stack / unit-of-work
``Save`` -- therefore happened AFTER the lexicon data was committed.
"""

import os as _tr_os

# Observed SIL writing-system store layout version (FieldWorks 9). Only
# used when the reflection lookup below is unavailable.
_TR_WS_REPO_VERSION_FALLBACK = "3"

# Markers proving where in CloseProject() the failure happened. Checked
# against the formatted Python traceback plus every exception's text and
# .NET StackTrace in the chain.
_TR_SAVE_MARKERS = (
    "UndoStackManager.Save",
    "UnitOfWorkService.Save",
    "usm.Save()",
)
_TR_DISPOSE_MARKERS = (
    "LcmCache.Dispose",
    "self.project.Dispose()",
)
_TR_ABANDONED_MARKER = "AbandonedMutexException"


def _tr_exception_chain(exc, limit=16):
    """Yield exc and its Python (__cause__/__context__) and .NET
    (InnerException) ancestors, without cycles."""
    seen = set()
    stack = [exc]
    while stack and len(seen) < limit:
        cur = stack.pop()
        if cur is None or id(cur) in seen:
            continue
        seen.add(id(cur))
        yield cur
        for attr in ("__cause__", "__context__", "InnerException"):
            try:
                nxt = getattr(cur, attr, None)
            except Exception:
                nxt = None
            if nxt is not None:
                stack.append(nxt)


def _tr_chain_text(exc, tb_text=""):
    parts = [tb_text or ""]
    for e in _tr_exception_chain(exc):
        parts.append(type(e).__name__)
        try:
            parts.append(str(e))
        except Exception:
            pass
        try:
            st = getattr(e, "StackTrace", None)
            if st:
                parts.append(str(st))
        except Exception:
            pass
    return "\n".join(parts)


def is_abandoned_mutex_error(exc, tb_text=""):
    """True when AbandonedMutexException appears anywhere in the chain."""
    for e in _tr_exception_chain(exc):
        if type(e).__name__ == _TR_ABANDONED_MARKER:
            return True
    return _TR_ABANDONED_MARKER in _tr_chain_text(exc, tb_text)


def classify_teardown_failure(exc, tb_text="", write_enabled=True, close_started=True):
    """Classify a teardown exception.

    Returns ``{"phase", "writes_committed", "abandoned_mutex"}`` where
    ``phase`` is ``"pre_close"`` (failed before CloseProject() ran),
    ``"save"`` (the data commit itself failed), ``"dispose"`` (failed in
    LcmCache.Dispose, after the commit) or ``"unknown"``; and
    ``writes_committed`` is True / False / None (unknown, or not
    applicable on a read-only run).
    """
    text = _tr_chain_text(exc, tb_text)
    abandoned = is_abandoned_mutex_error(exc, tb_text)
    if not close_started:
        phase = "pre_close"
    elif any(m in text for m in _TR_SAVE_MARKERS):
        phase = "save"
    elif any(m in text for m in _TR_DISPOSE_MARKERS):
        phase = "dispose"
    else:
        phase = "unknown"
    if not write_enabled:
        committed = None
    elif phase == "dispose":
        committed = True
    elif phase in ("save", "pre_close"):
        committed = False
    else:
        committed = None
    return {"phase": phase, "writes_committed": committed, "abandoned_mutex": abandoned}


def teardown_error_message(info, write_enabled=True):
    """Human-readable commit status for a classified teardown failure."""
    committed = info.get("writes_committed")
    if not write_enabled:
        status = "read-only run; there were no writes to commit"
    elif committed is True:
        status = ("writes WERE committed -- the failure came after the "
                  "data save, while syncing writing systems to the global store")
    elif committed is False:
        status = "writes were NOT committed"
    else:
        status = "writes may not have been committed"
    if info.get("abandoned_mutex"):
        status += ("; cause: an abandoned global writing-system mutex "
                   "(AbandonedMutexException)")
    return status


def teardown_next_steps(teardown_error, write_enabled=True):
    """next_steps for a TeardownError envelope (server side)."""
    info = teardown_error or {}
    committed = info.get("writes_committed")
    steps = []
    if write_enabled and committed is True:
        steps.append(
            "Do NOT re-run this write: the data was already committed, and "
            "re-running would duplicate the changes. Confirm them with a "
            "read-only query (write_enabled=false)."
        )
    elif write_enabled and committed is False:
        steps.append(
            "The writes were not committed. Check the project state with a "
            "read-only query before re-running the write."
        )
    elif write_enabled:
        steps.append(
            "Do NOT blindly re-run this write: it may already have been "
            "committed. First check with a read-only query "
            "(write_enabled=false) whether the changes are present."
        )
    if info.get("abandoned_mutex"):
        steps.append(
            "The global writing-system store mutex was abandoned by a "
            "process that exited while holding it. Close FieldWorks/FLEx "
            "and any other SIL apps (Paratext, Bloom, WeSay) that may be "
            "using writing systems."
        )
        steps.append(
            "The next run clears a stale writing-system mutex automatically "
            "before opening the project; do not retry in a loop -- if the "
            "same error recurs after one more run, report it (e.g. "
            "flextools_prepare_report) instead of retrying."
        )
    else:
        steps.append(
            "Do not retry in a loop. Check flextools_health, and make sure "
            "no other program has the project open."
        )
    return steps


# ---------------------------------------------------------------------------
# Runner-side (.NET) helpers. Every one is best-effort and never raises.
# ---------------------------------------------------------------------------

def ws_repo_mutex_names():
    """Candidate OS names of the global writing-system store mutex.

    Prefers SIL's own path logic
    (``GlobalWritingSystemRepository.CurrentVersionPath(DefaultBasePath)``,
    the static members of ``GlobalWritingSystemRepository<T>`` as
    pythonnet exposes them); falls back to
    ``%PROGRAMDATA%\\SIL\\WritingSystemRepository\\3``.
    """
    names = []
    try:
        import clr
        try:
            from SIL.WritingSystems import GlobalWritingSystemRepository as _G
        except ImportError:
            clr.AddReference("SIL.WritingSystems")
            from SIL.WritingSystems import GlobalWritingSystemRepository as _G
        vpath = _G.CurrentVersionPath(_G.DefaultBasePath)
        if vpath:
            names.append(str(vpath).replace("\\", "_"))
    except Exception:
        pass
    fallback = _tr_os.path.join(
        _tr_os.environ.get("PROGRAMDATA") or "C:\\ProgramData",
        "SIL", "WritingSystemRepository", _TR_WS_REPO_VERSION_FALLBACK,
    ).replace("\\", "_")
    if fallback not in names:
        names.append(fallback)
    return names


def clear_stale_ws_mutex(names=None):
    """Acquire-and-release each named mutex without waiting.

    An abandoned mutex raises AbandonedMutexException on acquisition --
    the caller then owns it, so it is released here and reported as
    ``cleared``. A mutex held by a live process is left alone
    (``held_by_other``). Never raises.
    """
    out = {"names": [], "cleared": False, "held_by_other": False, "errors": []}
    try:
        from System.Threading import Mutex
    except Exception as e:
        out["errors"].append("pythonnet unavailable: {}".format(type(e).__name__))
        return out
    for name in (names if names is not None else ws_repo_mutex_names()):
        out["names"].append(name)
        try:
            m = Mutex.OpenExisting(name)
        except Exception:
            continue  # no such mutex: nothing to clear
        try:
            owned = False
            try:
                owned = bool(m.WaitOne(0))
            except Exception as e:
                if type(e).__name__ == _TR_ABANDONED_MARKER:
                    owned = True
                    out["cleared"] = True
                else:
                    out["errors"].append("{}: {}".format(type(e).__name__, e))
            if owned:
                try:
                    m.ReleaseMutex()
                except Exception as e:
                    out["errors"].append("release: {}: {}".format(type(e).__name__, e))
            elif not out["errors"]:
                out["held_by_other"] = True
        finally:
            try:
                m.Dispose()
            except Exception:
                pass
    return out


def release_owned_ws_mutex(names=None, max_releases=16):
    """Release every recursion level of the named mutexes this thread owns.

    Called after a failed teardown so this process never exits holding
    (and so abandoning) the writing-system mutex. ReleaseMutex on a
    mutex the thread does not own raises immediately, which ends the
    loop. Returns the number of releases performed. Never raises.
    """
    released = 0
    try:
        from System.Threading import Mutex
    except Exception:
        return 0
    for name in (names if names is not None else ws_repo_mutex_names()):
        try:
            m = Mutex.OpenExisting(name)
        except Exception:
            continue
        try:
            for _ in range(max_releases):
                try:
                    m.ReleaseMutex()
                    released += 1
                except Exception:
                    break
        finally:
            try:
                m.Dispose()
            except Exception:
                pass
    return released


def retry_dispose_after_abandoned_mutex(project, names=None):
    """Release the now-owned mutex and retry the LCM dispose once.

    ``project`` is the flexicon FLExProject whose CloseProject() raised
    from ``self.project.Dispose()`` (so ``project.project`` -- the
    LcmCache -- is still attached). Returns ``{"released", "retried",
    "retry_ok", "retry_error"}``. Never raises, and always releases any
    mutex this thread still owns afterwards.
    """
    out = {"released": 0, "retried": False, "retry_ok": False, "retry_error": None}
    try:
        out["released"] = release_owned_ws_mutex(names)
        cache = getattr(project, "project", None)
        if cache is not None:
            out["retried"] = True
            try:
                if getattr(cache, "IsDisposed", False):
                    # Dispose already completed its own bookkeeping; only
                    # the writing-system sync is outstanding.
                    cache.ServiceLocator.WritingSystemManager.Save()
                else:
                    cache.Dispose()
                out["retry_ok"] = True
                try:
                    del project.project
                except Exception:
                    pass
            except Exception as e:
                out["retry_error"] = "{}: {}".format(type(e).__name__, e)
    except Exception as e:
        out["retry_error"] = out["retry_error"] or "{}: {}".format(type(e).__name__, e)
    finally:
        out["released"] += release_owned_ws_mutex(names)
    return out


def _tr_load_source():
    try:
        with open(__file__, encoding="utf-8") as f:
            src = f.read()
    except Exception:
        return ""
    # Everything from this loader down is server-side only.
    cut = src.find("\ndef _tr_load_source")
    return src[:cut] + "\n" if cut != -1 else src


# Embedded verbatim into generated runner scripts (see module docstring).
RUNNER_HELPER_SOURCE = _tr_load_source()
