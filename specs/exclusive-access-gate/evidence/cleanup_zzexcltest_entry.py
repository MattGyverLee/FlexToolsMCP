# ruff: noqa: F821 -- run_module bare snippet; project/report/modifyAllowed are injected by the runner
# Cleanup: delete the zzExclTest entry created by V4 (2026-10-01), after V6.
entry = project.LexEntry.Find("zzExclTest")
report.Info("before: zzExclTest present = " + str(entry is not None))
if modifyAllowed:
    if entry is not None:
        project.LexEntry.Delete(entry)
        report.Info("deleted zzExclTest")
    report.Info("after: zzExclTest present = " + str(project.LexEntry.Find("zzExclTest") is not None))
