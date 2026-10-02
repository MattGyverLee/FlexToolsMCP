# ruff: noqa: F821 -- run_module bare snippet; project/report/modifyAllowed are injected by the runner
# V4 (and V5 call A): ordinary write with FLEx open. Creates a zzExclTest
# entry with one sense glossed "zzgloss-v4". Cleaned up by v_cleanup.py.
# (Nested guard: the write gate does not recognise `if modifyAllowed and ...:`.)
existing = project.LexEntry.Find("zzExclTest")
report.Info("pre: zzExclTest exists = " + str(existing is not None))
if modifyAllowed:
    if existing is None:
        entry = project.LexEntry.Create("zzExclTest", "stem", create_blank_sense=False)
        sense = project.LexEntry.AddSense(entry, "zzgloss-v4")
        report.Info("created zzExclTest, gloss = " + project.Senses.GetGloss(sense))
