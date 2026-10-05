# ruff: noqa: F821 -- run_module bare snippet; project/report/modifyAllowed are injected by the runner
# Cleanup: remove the qaa-x-zzexcl writing system that V8b created by mistake
# on 2026-10-01 (FLEx had been closed, so the gate correctly did not apply).
tag = "qaa-x-zzexcl"
ws = project.WritingSystems
report.Info("before: active vern = " + ", ".join(str(ws.GetLanguageTag(w)) for w in ws.GetVernacular()))
report.Info("before: exists (active) = " + str(ws.Exists(tag)) + ", in store = " + str(ws.ExistsInStore(tag)))
if modifyAllowed:
    ws.Delete(tag)
    report.Info("deleted " + tag)
    report.Info("after: active vern = " + ", ".join(str(ws.GetLanguageTag(w)) for w in ws.GetVernacular()))
