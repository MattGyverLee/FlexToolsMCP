@echo off
rem Fake GenerateHCConfig for parser-check CP5 tests: runs generate_fake.py with the
rem interpreter in FAKE_PYTHON (set by the fixtures to sys.executable), else
rem `python`, forwarding every argument and propagating the exit code.
setlocal
if defined FAKE_PYTHON (set "_FAKE_PY=%FAKE_PYTHON%") else (set "_FAKE_PY=python")
"%_FAKE_PY%" "%~dp0generate_fake.py" %*
exit /b %ERRORLEVEL%
