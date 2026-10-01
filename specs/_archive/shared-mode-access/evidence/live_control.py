"""Control for the CP4 live check: the SAME two-process open against a
project with projectSharing="false" must FAIL, proving the peer write on
Target succeeded because of the sharing flag and not by accident.

Both opens are read-only -- this touches no data in 'Sena 3'.
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = r"D:/Apps/anaconda3/python.exe"
READY = os.path.join(HERE, "ctl_ready")
RELEASE = os.path.join(HERE, "ctl_release")
PROJECT = "Sena 3"

HOLD = f'''
import os, sys, time
from flexicon import FLExInitialize, FLExProject
from flexicon.code.headless_ui import HeadlessLcmUI
FLExInitialize()
p = FLExProject()
p.OpenProject({PROJECT!r}, writeEnabled=False, ui=HeadlessLcmUI())
open(r"{READY}", "w").write(str(os.getpid()))
d = time.time() + 180
while not os.path.exists(r"{RELEASE}") and time.time() < d:
    time.sleep(0.5)
p.CloseProject()
'''

SECOND = f'''
from flexicon import FLExInitialize, FLExProject
from flexicon.code.headless_ui import HeadlessLcmUI
FLExInitialize()
p = FLExProject()
try:
    p.OpenProject({PROJECT!r}, writeEnabled=False, ui=HeadlessLcmUI())
    print("SECOND OPEN SUCCEEDED (unexpected for a sharing=false project)")
    p.CloseProject()
    raise SystemExit(0)
except Exception as e:
    print(f"SECOND OPEN REFUSED BY LCM: {{type(e).__name__}}: {{e}}")
    raise SystemExit(1)
'''

for f in (READY, RELEASE):
    if os.path.exists(f):
        os.remove(f)

holder = subprocess.Popen([PY, "-c", HOLD], stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
deadline = time.time() + 180
while not os.path.exists(READY) and time.time() < deadline:
    if holder.poll() is not None:
        print("HOLDER DIED:\n" + holder.stdout.read())
        sys.exit(2)
    time.sleep(0.5)

print(f"holder up on {PROJECT!r} (sharing=false), PID {open(READY).read().strip()}")

sys.path.insert(0, r"D:\Github\_Projects\_LEX\FlexToolsMCP\src")
from flextoolsmcp.server.project_access import probe_project_access  # noqa: E402
acc = probe_project_access(PROJECT)
print(f"probe verdict while held: {acc.verdict} sharing={acc.sharing_enabled} holder={acc.holder}")

r = subprocess.run([PY, "-c", SECOND], capture_output=True, text=True)
print(r.stdout.strip() or r.stderr.strip()[-500:])

open(RELEASE, "w").close()
holder.wait(timeout=180)
print("\nCONTROL:", "PASS (second open refused, as expected)" if r.returncode == 1
      else "FAIL (second open was not refused)")
