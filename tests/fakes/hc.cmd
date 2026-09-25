@echo off
rem Fake HermitCrab `hc` for parser-check CP5 tests: runs hc_fake.py with the
rem interpreter in FAKE_PYTHON (set by the fixtures to sys.executable), else
rem `python`, forwarding every argument and propagating the exit code.
setlocal
set "_FAKE_PY=python"
if defined FAKE_PYTHON set "_FAKE_PY=%FAKE_PYTHON%"
"%_FAKE_PY%" "%~dp0hc_fake.py" %*
exit /b %ERRORLEVEL%
