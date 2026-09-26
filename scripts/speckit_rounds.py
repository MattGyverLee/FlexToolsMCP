#
#   speckit_rounds.py
#
#   Drive the post-clarify Companion pipeline (plan -> tasks -> implement)
#   unattended, one FRESH top-level Claude Code session per round.
#
#   A round is the plan step, the tasks step, or one implement phase (see
#   .claude/skills/speckit-round/SKILL.md). Each round is a separate
#   `claude -p` process, so it starts with an empty context and can
#   dispatch its own subagents. This script holds no model context at all;
#   between rounds it reads state from disk (status-context.py and the
#   tasks.md checkboxes) and decides whether to start another.
#
#   Stops on: pipeline complete, a round reporting BLOCKED, a round that
#   made no recorded progress twice in a row, a failed claude process, or
#   --max-rounds.
#
#   Usage:
#       python scripts/speckit_rounds.py [specs/NNN-name] [options]
#       python scripts/speckit_rounds.py --dry-run
#
#   Platform: any (needs the `claude` CLI on PATH)
#
#   Copyright 2026
#

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMPANION = REPO / ".specify" / "extensions" / "companion" / "scripts"
STATUS_SCRIPT = COMPANION / "status-context.py"

sys.path.insert(0, str(COMPANION))
from task_sync import parse_task_markers  # noqa: E402  (companion's own parser)

ROUND_RE = re.compile(r"^ROUND:\s*(DONE|COMPLETE|BLOCKED)\b\s*(.*)$", re.MULTILINE)
PHASE_HEADING_RE = re.compile(r"^#{2,3}\s+(.*)$")
TASK_ID_RE = re.compile(r"\b(T\d+)\b")


def resolve_feature_dir(arg):
    if arg:
        return Path(arg)
    feature_json = REPO / ".specify" / "feature.json"
    try:
        data = json.loads(feature_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        sys.exit("[ERROR] no feature dir given and .specify/feature.json is unreadable")
    return Path(data["feature_directory"])


def status(feature_dir):
    """Run status-context.py and return the parsed RESOLUTION dict."""
    out = subprocess.run(
        [sys.executable, str(STATUS_SCRIPT), "--feature-dir", str(feature_dir)],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
    )
    for line in reversed(out.stdout.splitlines()):
        if line.startswith("RESOLUTION:"):
            return json.loads(line[len("RESOLUTION:"):])
    sys.exit(f"[ERROR] status-context.py printed no RESOLUTION line:\n{out.stdout}{out.stderr}")


def phase_of(feature_dir, task_id):
    """The tasks.md heading the given task sits under, or None."""
    try:
        lines = (REPO / feature_dir / "tasks.md").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    heading = None
    for line in lines:
        m = PHASE_HEADING_RE.match(line)
        if m:
            heading = m.group(1).strip()
        elif task_id in TASK_ID_RE.findall(line) and re.match(r"^\s*[-*+]\s*\[", line):
            return heading
    return None


def fingerprint(feature_dir, res):
    """What counts as progress: step/status moved, or more tasks checked."""
    _, done = parse_task_markers(REPO / feature_dir / "tasks.md")
    return (res.get("currentStep"), res.get("status"), res.get("nextTask"), len(set(done)))


def round_label(res, feature_dir):
    step = "implement" if res.get("nextTask") else (res.get("nextStep") or res.get("currentStep"))
    if step != "implement":
        return step, None
    task = res.get("nextTask")
    if not task:
        all_ids, done = parse_task_markers(REPO / feature_dir / "tasks.md")
        task = next((t for t in all_ids if t not in set(done)), None)
    return step, phase_of(feature_dir, task) if task else None


def run_claude(claude, prompt, args):
    cmd = [claude, "-p", "--output-format", "json", "--permission-mode", args.permission_mode]
    if args.model:
        cmd += ["--model", args.model]
    if args.max_budget_usd:
        cmd += ["--max-budget-usd", str(args.max_budget_usd)]
    # Prompt goes on stdin: avoids cmd.exe quoting when `claude` is a .cmd shim.
    return subprocess.run(cmd, cwd=REPO, input=prompt, capture_output=True,
                          text=True, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("feature_dir", nargs="?", help="specs/NNN-name (default: .specify/feature.json)")
    ap.add_argument("--permission-mode", default="auto",
                    help="passed to claude (default: auto; acceptEdits will stall on Bash)")
    ap.add_argument("--model", help="passed to claude --model")
    ap.add_argument("--max-rounds", type=int, default=25)
    ap.add_argument("--max-budget-usd", type=float, help="per-round cap, passed to claude")
    ap.add_argument("--dry-run", action="store_true", help="print the next round's prompt and stop")
    args = ap.parse_args()

    feature_dir = resolve_feature_dir(args.feature_dir)
    claude = shutil.which("claude")
    if not claude and not args.dry_run:
        sys.exit("[ERROR] `claude` CLI not found on PATH")

    log_dir = REPO / feature_dir / "rounds"
    stalls, prev_fp = 0, None
    total_cost = 0.0

    for n in range(1, args.max_rounds + 1):
        res = status(feature_dir)
        if res.get("complete"):
            print(f"[DONE] pipeline complete after {n - 1} round(s), ${total_cost:.2f}")
            return 0
        step, phase = round_label(res, feature_dir)
        if res.get("empty") or step in (None, "specify", "clarify"):
            print(f"[STOP] next step is '{step}': run specify/clarify interactively first")
            return 1

        fp = fingerprint(feature_dir, res)
        if fp == prev_fp:
            stalls += 1
            if stalls >= 2:
                print(f"[STOP] no recorded progress in two rounds (still at {res.get('nextActionLabel')})")
                return 1
        else:
            stalls = 0
        prev_fp = fp

        prompt = f"Invoke the speckit-round skill with argument: {feature_dir.as_posix()}"
        label = f"{step}" + (f" / {phase}" if phase else "")
        if args.dry_run:
            print(f"[INFO] next round: {label}\n[INFO] prompt: {prompt}")
            return 0

        print(f"[INFO] round {n}: {label} ...", flush=True)
        started = time.time()
        proc = run_claude(claude, prompt, args)
        log_dir.mkdir(exist_ok=True)
        (log_dir / f"round-{n:02d}-{step}.json").write_text(proc.stdout or proc.stderr, encoding="utf-8")

        try:
            out = json.loads(proc.stdout)
        except ValueError:
            print(f"[FAIL] round {n}: claude exited {proc.returncode} without JSON\n{proc.stderr[-2000:]}")
            return 1
        cost = out.get("total_cost_usd") or 0.0
        total_cost += cost
        text = out.get("result") or ""
        m = ROUND_RE.findall(text)
        verdict, detail = m[-1] if m else ("?", text.strip().splitlines()[-1:] or [""])
        if isinstance(detail, list):
            detail = detail[0] if detail else ""
        print(f"      {verdict} in {time.time() - started:.0f}s, {out.get('num_turns')} turns, "
              f"${cost:.2f} -- {detail}")

        if out.get("is_error"):
            print(f"[FAIL] round {n} ended in error ({out.get('subtype')}); see {log_dir}")
            return 1
        if verdict == "BLOCKED":
            print(f"[STOP] blocked: {detail}")
            return 1

    print(f"[STOP] --max-rounds {args.max_rounds} reached, ${total_cost:.2f}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
