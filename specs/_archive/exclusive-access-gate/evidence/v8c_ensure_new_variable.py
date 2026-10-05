# ruff: noqa: F821 -- run_module bare snippet; project/report/modifyAllowed are injected by the runner
# V8c: the same new tag through a variable -- the gate cannot read it, so the
# run starts and flexicon's peer schema guard refuses at the moment of writing.
tag = "qaa-x-" + "zzexcl"
report.Info("before Ensure: exists in store = " + str(project.WritingSystems.ExistsInStore(tag)))
if modifyAllowed:
    ws, created = project.WritingSystems.Ensure(tag, "zz exclusive probe")
    report.Info("Ensure(tag): created = " + str(created))
