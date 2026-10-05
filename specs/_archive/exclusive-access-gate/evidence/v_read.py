# ruff: noqa: F821 -- run_module bare snippet; project/report/modifyAllowed are injected by the runner
# Read-back of the zzExclTest gloss (V4 post, V5 call B as-is, cleanup check).
entry = project.LexEntry.Find("zzExclTest")
if entry is None:
    report.Info("zzExclTest: absent")
else:
    glosses = [project.Senses.GetGloss(s) for s in project.LexEntry.GetSenses(entry)]
    report.Info("zzExclTest: present, glosses = " + repr(glosses))
