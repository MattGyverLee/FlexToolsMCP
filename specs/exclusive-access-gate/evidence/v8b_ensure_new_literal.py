# ruff: noqa: F821 -- run_module bare snippet; project/report/modifyAllowed are injected by the runner
# V8b: Ensure on a tag the project lacks, literal -- refused before the run.
if modifyAllowed:
    ws, created = project.WritingSystems.Ensure("qaa-x-zzexcl", "zz exclusive probe")
    report.Info("Ensure('qaa-x-zzexcl'): created = " + str(created))
