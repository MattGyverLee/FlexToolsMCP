import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = r"D:/Apps/anaconda3/python.exe"
SCRIPT = os.path.join(HERE, "live_shared_peer.py")
READY = os.path.join(HERE, "peer_ready")
RELEASE = os.path.join(HERE, "peer_release")
MARKER = "TEST_cp4_peer"

for f in (READY, RELEASE):
    if os.path.exists(f):
        os.remove(f)


def run(mode, *extra):
    print(f"\n===== {mode} =====", flush=True)
    r = subprocess.run([PY, SCRIPT, mode, MARKER, *extra], capture_output=True, text=True)
    print(r.stdout.strip())
    if r.stderr.strip():
        print("--- stderr ---\n" + r.stderr.strip())
    print(f"(exit {r.returncode})")
    return r


print("===== hold (background) =====", flush=True)
holder = subprocess.Popen([PY, SCRIPT, "hold", MARKER, READY, RELEASE],
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

deadline = time.time() + 180
while not os.path.exists(READY) and time.time() < deadline:
    if holder.poll() is not None:
        print("HOLDER DIED EARLY:\n" + holder.stdout.read())
        sys.exit(2)
    time.sleep(0.5)

if not os.path.exists(READY):
    holder.kill()
    print("HOLDER NEVER BECAME READY")
    sys.exit(2)

holder_pid = open(READY).read().strip()
print(f"holder is up, PID {holder_pid}; project is now locked by a live python process")

# What does the CP4 probe say about the project RIGHT NOW, with the holder attached?
sys.path.insert(0, r"D:\Github\_Projects\_LEX\FlexToolsMCP\src")
from flextoolsmcp.server.project_access import probe_project_access  # noqa: E402
acc = probe_project_access("Target")
print(f"probe verdict while held: {acc.verdict} sharing={acc.sharing_enabled} holder={acc.holder}")

w = run("write")

open(RELEASE, "w").close()
holder.wait(timeout=180)
print("\n===== holder output =====")
print(holder.stdout.read().strip())

r = run("read")

run("cleanup")

print("\n===== VERDICT =====")
print("peer write while a second process held the project:",
      "PASS" if (w.returncode == 0 and r.returncode == 0) else "FAIL")
