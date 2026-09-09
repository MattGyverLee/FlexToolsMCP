"""Rebuild the parity corpus from the checked-in operation logs.

The corpus is byte-exact evidence: each file must reproduce the `sha256` prefix
and `bytes` count that `Code fingerprint:` recorded in the log, because those
are the bytes the MCP actually executed. Trailing whitespace is significant --
do not let a formatter near these files (see .gitattributes).

    python specs/vanilla-flextools-parity/evidence/corpus/regenerate.py [--check]

--check verifies without writing, and exits non-zero on any mismatch.
"""
import hashlib
import json
import pathlib
import re
import sys

# Stored with an inert extension on purpose: a formatter in this
# environment strips trailing whitespace from *.py, which silently breaks
# every fingerprint. Trailing whitespace is part of what the log hashed.
# The parity harness writes each module to a temp *.py before running it,
# so nothing needs these to be importable in place.
EXT = ".py.txt"
HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[3]
LOGDIR = REPO / "user-logs" / "Kendall"


def harvest():
    """fingerprint -> (raw bytes, [origin], declared byte count) from the logs."""
    blocks = {}
    for log in sorted(LOGDIR.glob("*.log")):
        op = fp = declared = None
        buf = None
        for ln in log.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.search(r"=== Operation #(\d+) Start", ln)
            if m:
                op = m.group(1)
            m = re.search(r"Code fingerprint: sha256=(\w+) bytes=(\d+)", ln)
            if m:
                fp, declared = m.group(1), int(m.group(2))
            if "| DEBUG   | Code:" in ln:
                buf = []
                continue
            if buf is None:
                continue
            if "| DEBUG   |" in ln:
                buf.append(ln.split("| DEBUG   |", 1)[1][1:])
            else:
                raw = "\n".join(buf).encode("utf-8")
                origin = f"{log.stem[8:14]} op#{op}"
                if fp in blocks:
                    blocks[fp][1].append(origin)
                else:
                    blocks[fp] = (raw, [origin], declared)
                buf = None
    return blocks


def main():
    check = "--check" in sys.argv
    blocks = harvest()
    if not blocks:
        print(f"[FAIL] no code blocks found under {LOGDIR}")
        return 1

    manifest, failures = [], []
    for fp, (raw, origins, declared) in sorted(blocks.items()):
        dest = HERE / f"{fp}{EXT}"
        if not check:
            with open(dest, "wb") as fh:      # binary: never translate newlines
                fh.write(raw)
        on_disk = dest.read_bytes() if dest.exists() else b""
        got = hashlib.sha256(on_disk).hexdigest()
        ok = got.startswith(fp) and len(on_disk) == declared
        if not ok:
            failures.append(
                f"{fp}: on disk {len(on_disk)} bytes / {got[:12]}, "
                f"log says {declared} bytes / {fp}"
            )
        manifest.append({
            "fingerprint": fp,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "origins": origins,
            "file": f"{fp}{EXT}",
            "expected_parity_verdict_pre_fix": "mcp_only_success",
        })

    if not check:
        (HERE / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
        )

    print(f"{len(manifest)} distinct modules from {LOGDIR.name}")
    for f in failures:
        print(f"  [FAIL] {f}")
    if failures:
        print("[FAIL] corpus does not match the logs -- a formatter probably "
              "rewrote these files; re-run without --check to restore.")
        return 1
    print("[OK] every file reproduces its logged sha256 and byte count")
    return 0


if __name__ == "__main__":
    sys.exit(main())
