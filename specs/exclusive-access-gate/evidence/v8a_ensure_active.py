# ruff: noqa: F821 -- run_module bare snippet; project/report/modifyAllowed are injected by the runner
# V8a: Ensure on an already-active analysis tag -- a no-op, allowed while FLEx is open.
if modifyAllowed:
    ws, created = project.WritingSystems.Ensure("en", "English", is_vernacular=False)
    report.Info("Ensure('en', analysis): created = " + str(created))
