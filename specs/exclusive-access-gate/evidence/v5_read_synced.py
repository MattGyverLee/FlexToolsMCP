# ruff: noqa: F821 -- run_module bare snippet; project/report/modifyAllowed are injected by the runner
# V5 call B with sync-at-open: pull in peer commits first, then read.
# SaveChanges() at depth 0 is the undoable=True equivalent of
# SyncForeignChanges() (research R5); it raises FP_ReadOnlyError read-only.
if modifyAllowed:
    try:
        project.SaveChanges()
        report.Info("sync: SaveChanges ok")
    except Exception as exc:
        report.Info("sync: SaveChanges failed: " + type(exc).__name__ + ": " + str(exc))
entry = project.LexEntry.Find("zzExclTest")
if entry is None:
    report.Info("zzExclTest: absent")
else:
    glosses = [project.Senses.GetGloss(s) for s in project.LexEntry.GetSenses(entry)]
    report.Info("zzExclTest: present, glosses = " + repr(glosses))
