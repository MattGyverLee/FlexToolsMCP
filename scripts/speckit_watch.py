#
#   speckit_watch.py
#
#   Live terminal dashboard for a speckit rounds run. Run it in a second
#   terminal next to scripts/speckit_rounds_opencode.py.
#
#   Folds four on-disk sources, all written by other processes (this script
#   never writes):
#     * <feature>/rounds/progress.jsonl       driver events (run/round start/end)
#     * <feature>/rounds/*.opencode.jsonl     the live round's opencode events
#     * <feature>/tasks.md                    phases and checkboxes
#     * <feature>/.spec-context.events.jsonl  per-task finishes with `did`
#
#   Modeled on keyboard-studio's tools/triage-watch.mjs: poll, re-fold,
#   redraw. Stdlib only.
#
#   Usage:
#       python scripts/speckit_watch.py [specs/NNN-name]   # live, latest run
#       python scripts/speckit_watch.py --run <run_id>     # a specific run
#       python scripts/speckit_watch.py --list             # list runs
#       python scripts/speckit_watch.py --once             # render once and exit
#       python scripts/speckit_watch.py --raw              # tail the live round's events
#
#   Platform: any (ANSI; Windows Terminal, PowerShell, cmd on Win10+)
#
#   Copyright 2026
#

import argparse
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime

from speckit_rounds import REPO, ROUND_RE, feature_root, resolve_feature_dir
from speckit_rounds_opencode import (
    PROGRESS_FILE,
    context_tokens,
    describe_tool,
    fmt_context,
    model_context_limit,
)

POLL_S = 1.0
STALE_S = 5 * 60
# The driver starts the next round seconds after a verdict; longer means it exited.
IDLE_S = 60
WIDTH = 78

PHASE_RE = re.compile(r"^##\s+(.*)$")
TASK_RE = re.compile(r"^\s*-\s*\[([ xX])\]\s*\*\*(T\d+)\*\*\s*(.*)$")

# ---------- ANSI ----------

TTY = sys.stdout.isatty()
CODES = {"reset": "0", "bold": "1", "dim": "2", "red": "31", "green": "32",
         "yellow": "33", "blue": "34", "magenta": "35", "cyan": "36"}


def c(color, s):
    return f"\x1b[{CODES[color]}m{s}\x1b[0m" if TTY else str(s)


def pad(s, n):
    s = str(s)
    return s[:n] if len(s) >= n else s + " " * (n - len(s))


# Console output stays ASCII (Windows consoles, CLAUDE.md): fold the
# punctuation models like to emit, and drop the checkout parent from paths.
ASCII_FOLD = str.maketrans({"—": "--", "–": "-", "‘": "'", "’": "'",
                            "“": '"', "”": '"', "…": "...", "→": "->",
                            "·": "|", "⟶": "->"})
PARENT_RE = re.compile(re.escape(str(REPO.parent)).replace(r"\\", r"[\\/]") + r"[\\/]", re.I)


def fit(s, n):
    s = PARENT_RE.sub("", " ".join(str(s).split())).translate(ASCII_FOLD)
    s = s.encode("ascii", "replace").decode("ascii")
    return s if len(s) <= n else s[:n - 3] + "..."


def fmt_duration(seconds):
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def parse_ts(value):
    """ISO string or epoch-ms int -> epoch seconds (or None)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value / 1000 if value > 1e11 else value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def clock(epoch):
    return time.strftime("%H:%M:%S", time.localtime(epoch)) if epoch else "--:--:--"


# ---------- ingest ----------

class Tail:
    """Incrementally read complete JSON lines appended to a file."""

    def __init__(self, path):
        self.path, self.offset, self.buf = path, 0, b""

    def read(self):
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        if size < self.offset:          # truncated or replaced: start over
            self.offset, self.buf = 0, b""
        if size == self.offset:
            return []
        with open(self.path, "rb") as f:
            f.seek(self.offset)
            data = f.read(size - self.offset)
        self.offset = size
        self.buf += data
        *complete, self.buf = self.buf.split(b"\n")
        out = []
        for raw in complete:
            try:
                out.append(json.loads(raw.decode("utf-8", "replace")))
            except ValueError:
                pass
        return out


def read_jsonl(path):
    return Tail(path).read()


def load_tasks(tasks_md):
    """[(phase_title, [(task_id, done, text)])] in document order."""
    phases = []
    try:
        lines = tasks_md.read_text(encoding="utf-8").splitlines()
    except OSError:
        return phases
    for line in lines:
        m = PHASE_RE.match(line)
        if m:
            phases.append((m.group(1).strip(), []))
            continue
        m = TASK_RE.match(line)
        if m and phases:
            text = re.sub(r"^\[P\]\s*|\[US\d+\]\s*", "", m.group(3)).split(" · ")[0]
            phases[-1][1].append((m.group(2), m.group(1).lower() == "x", text.strip()))
    return [(title, tasks) for title, tasks in phases if tasks]


def load_finishes(events_path):
    """task_id -> (epoch, did) from the companion's per-task journal."""
    out = {}
    for ev in read_jsonl(events_path):
        if ev.get("task") and ev.get("kind") == "complete":
            out[ev["task"]] = (parse_ts(ev.get("at")), ev.get("did") or "")
    return out


def list_runs(events):
    runs = {}
    for ev in events:
        rid = ev.get("run_id")
        if not rid:
            continue
        r = runs.setdefault(rid, {"run_id": rid, "start": None, "end": None, "rounds": 0,
                                  "reason": "", "model": ""})
        if ev.get("phase") == "run-start":
            r["start"], r["model"] = ev.get("ts"), ev.get("model") or ""
        elif ev.get("phase") == "round-start":
            r["rounds"] = max(r["rounds"], ev.get("round") or 0)
        elif ev.get("phase") == "run-end":
            r["end"], r["reason"] = ev.get("ts"), ev.get("reason") or ""
    return sorted(runs.values(), key=lambda r: r["start"] or "", reverse=True)


# ---------- state ----------

class Watch:
    def __init__(self, feature_dir, run_id=None):
        self.feature_dir = feature_dir
        self.checkout = feature_root(feature_dir)
        self.root = self.checkout / feature_dir
        self.rounds_dir = self.root / "rounds"
        self.pinned_run = run_id
        self.progress = Tail(self.rounds_dir / PROGRESS_FILE)
        self.driver_events = []
        self.log_tail = None
        self.log_name = None
        self.live = []                  # (epoch, line) of the live round
        self.ctx = 0                    # context held on the live round's latest step
        self.peak_ctx = 0
        self.limit_cache = {}
        self.peak_cache = {}            # finished round log -> peak context           # model -> context window, for runs that didn't record it
        self.verdict = None             # (verdict, detail) once the round prints ROUND:
        self.log_mtime = None

    def run_events(self):
        rid = self.pinned_run or next((e.get("run_id") for e in reversed(self.driver_events)
                                       if e.get("run_id")), None)
        return rid, [e for e in self.driver_events if e.get("run_id") == rid]

    def current_log(self, events):
        """The round log to follow: the run's last round-start, else the newest log file."""
        for ev in reversed(events):
            if ev.get("phase") == "round-start" and ev.get("log"):
                return ev["log"]
        logs = sorted(self.rounds_dir.glob("*.opencode.jsonl"), key=lambda p: p.stat().st_mtime)
        return logs[-1].name if logs else None

    def poll(self):
        self.driver_events += self.progress.read()
        rid, events = self.run_events()
        name = self.current_log(events)
        if name != self.log_name:
            self.log_name, self.live, self.ctx, self.peak_ctx, self.verdict = name, [], 0, 0, None
            self.log_tail = Tail(self.rounds_dir / name) if name else None
        if self.log_tail:
            for ev in self.log_tail.read():
                self.fold_live(ev)
            try:
                self.log_mtime = (self.rounds_dir / self.log_name).stat().st_mtime
            except OSError:
                pass
        return rid, events

    def fold_live(self, ev):
        kind, part = ev.get("type"), ev.get("part") or {}
        stamp = parse_ts(ev.get("timestamp")) or time.time()
        if kind == "tool_use":
            self.live.append((stamp, "tool", describe_tool(part)))
        elif kind == "text" and (part.get("text") or "").strip():
            self.live.append((stamp, "say", part["text"].strip().splitlines()[0]))
            found = ROUND_RE.findall(part["text"])
            if found:
                self.verdict = found[-1]
        elif kind == "step_finish":
            self.ctx = context_tokens(part.get("tokens") or {})
            self.peak_ctx = max(self.peak_ctx, self.ctx)
        elif kind == "error":
            err = ev.get("error") or {}
            self.live.append((stamp, "error", (err.get("data") or {}).get("message") or err.get("name")))
        del self.live[:-200]


    def log_peak(self, name):
        """Peak context of a finished round, read from its log (for rounds whose
        round-end predates peak_ctx). Cached: a finished log never changes."""
        if name not in self.peak_cache:
            peak = 0
            for ev in read_jsonl(self.rounds_dir / name):
                if ev.get("type") == "step_finish":
                    peak = max(peak, context_tokens((ev.get("part") or {}).get("tokens") or {}))
            self.peak_cache[name] = peak
        return self.peak_cache[name]

    def context_limit(self, start_event):
        """The run's recorded context window, else look the model up once."""
        if start_event.get("context_limit"):
            return start_event["context_limit"]
        model = start_event.get("model")
        if model and model not in self.limit_cache:
            self.limit_cache[model] = model_context_limit(shutil.which("opencode"), model)
        return self.limit_cache.get(model)


# ---------- render ----------

def status_badge(events, w):
    """RUNNING, STALE (quiet mid-round), IDLE (round ended, no next one), DONE/STOPPED."""
    if any(e.get("phase") == "run-end" for e in events):
        end = next(e for e in reversed(events) if e.get("phase") == "run-end")
        return c("green", "DONE") if end.get("code") == 0 else c("red", "STOPPED")
    if not events and not w.log_mtime:
        return c("dim", "WAITING")
    quiet = time.time() - w.log_mtime if w.log_mtime else 0
    if w.verdict:
        if quiet < IDLE_S:
            return c("cyan", f"ROUND {w.verdict[0]}, next starting")
        return c("yellow", f"IDLE ({w.verdict[0]} {fmt_duration(quiet)} ago; driver not running?)")
    if quiet > STALE_S:
        return c("yellow", f"STALE (no events for {fmt_duration(quiet)})")
    return c("cyan", "RUNNING")


def verdict_color(v):
    return {"DONE": "green", "COMPLETE": "green", "BLOCKED": "yellow",
            "FAILED": "red", "TIMEOUT": "red"}.get(v, "dim")


def bar(done, total, width=10):
    filled = round(width * done / total) if total else 0
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def render(w, rid, events):
    cols, rows = shutil.get_terminal_size((WIDTH, 40))
    width = max(60, min(cols - 1, 120))
    out = []
    rule = c("bold", "=" * width)
    thin = c("bold", "-" * width)

    start = next((e for e in events if e.get("phase") == "run-start"), {})
    end = next((e for e in reversed(events) if e.get("phase") == "run-end"), None)
    t0 = parse_ts(start.get("ts"))
    t1 = parse_ts(end.get("ts")) if end else time.time()
    cost = sum(e.get("cost") or 0 for e in events if e.get("phase") == "round-end")

    out.append(rule)
    out.append(c("bold", f"speckit rounds: {w.feature_dir.as_posix()}") +
               f"   run {rid or '(none)'}   status: {status_badge(events, w)}")
    out.append(f"model: {start.get('model') or '?'}   started {clock(t0)}   "
               f"elapsed {fmt_duration(t1 - t0) if t0 else '-'}   cost ${cost:.2f}")
    limit = w.context_limit(start)
    if w.ctx:
        share = w.ctx / limit if limit else 0
        color = "red" if share > 0.85 else "yellow" if share > 0.60 else "green"
        gauge = c(color, bar(w.ctx, limit, 20)) + " " if limit else ""
        out.append(f"context: {gauge}{c(color, fmt_context(w.ctx, limit))}"
                   + c("dim", f"   peak {w.peak_ctx:,}   (live round, latest step)"))
    sync = next((e for e in reversed(events) if e.get("phase") == "spec-sync"), None)
    if sync:
        result = sync.get("result") or ""
        color = "green" if result.startswith(("pushed", "nothing")) else "yellow"
        out.append(f"spec -> branch after round {sync.get('round')}: " + c(color, fit(result, width - 30)))
    if end:
        out.append(c("dim", fit(end.get("reason") or "", width)))
    elif w.verdict:
        out.append(c("dim", fit(f"last round: {w.verdict[0]} {w.verdict[1]}", width)))
    out.append(rule)

    # Phases, and the tasks of the current one.
    phases = load_tasks(w.root / "tasks.md")
    finishes = load_finishes(w.root / ".spec-context.events.jsonl")
    current = next((i for i, (_, ts) in enumerate(phases) if not all(d for _, d, _ in ts)), None)
    out.append(c("bold", " Phases"))
    for i, (title, tasks) in enumerate(phases):
        done = sum(1 for _, d, _ in tasks if d)
        mark = c("cyan", "  <- current") if i == current else ""
        line = f"  {bar(done, len(tasks))} {done:>2}/{len(tasks):<2}  {fit(title, width - 30)}"
        out.append((c("green", line) if done == len(tasks) else line) + mark)

    if current is not None:
        title, tasks = phases[current]
        out.append(thin)
        out.append(c("bold", f" {fit(title, width - 2)}"))
        next_id = next((t for t, d, _ in tasks if not d), None)
        for tid, done, text in tasks:
            if done:
                did = finishes.get(tid, (None, ""))[1]
                out.append(c("green", "  [x] ") + pad(tid, 6) + c("dim", fit(did or text, width - 13)))
            else:
                arrow = c("cyan", "  <- next") if tid == next_id else ""
                out.append(f"  [ ] {pad(tid, 6)}{fit(text, width - 13 - (9 if arrow else 0))}{arrow}")

    # Rounds of this run.
    starts = {e["round"]: e for e in events if e.get("phase") == "round-start"}
    ends = {e["round"]: e for e in events if e.get("phase") == "round-end"}
    if starts:
        out.append(thin)
        out.append(c("bold", " Rounds"))
        out.append(c("dim", "    #  " + pad("label", 35) + pad("time", 10) + pad("steps", 7)
                     + pad("peak ctx", 10) + "verdict"))
        for n in sorted(starts):
            s, e = starts[n], ends.get(n)
            if e:
                took, steps = fmt_duration(e.get("seconds") or 0), str(e.get("steps") or 0)
                peak_ctx = e.get("peak_ctx") or (w.log_peak(s["log"]) if s.get("log") else 0)
                peak = f"{peak_ctx // 1000:,}k" if peak_ctx else "-"
                verdict = c(verdict_color(e.get("verdict")), pad(e.get("verdict") or "?", 8))
                detail = c("dim", fit(e.get("detail") or "", max(0, width - 85)))
            else:
                took = fmt_duration(time.time() - (parse_ts(s.get("ts")) or time.time()))
                steps, verdict, detail = "", c("cyan", pad("running", 8)), ""
                peak = f"{w.peak_ctx // 1000:,}k" if w.peak_ctx else ""
            out.append(f"  {n:>3}  {pad(fit(s.get('label') or s.get('step'), 34), 35)}"
                       f"{pad(took, 10)}{pad(steps, 7)}{pad(peak, 10)}{verdict} {detail}")

    # Live feed fills whatever height is left.
    out.append(thin)
    out.append(c("bold", f" Live: {w.log_name or '(no round log yet)'}"))
    room = max(4, rows - len(out) - 3)
    for stamp, kind, text in w.live[-room:]:
        color = {"say": "dim", "error": "red"}.get(kind)
        body = fit(text, width - 14)
        out.append(f"  {c('dim', clock(stamp))}  " + (c(color, body) if color else body))
    if not w.live:
        out.append(c("dim", "  (no events yet)"))
    out.append(rule)
    out.append(c("dim", f"watching {w.rounds_dir.as_posix()}  -  ctrl+c to exit"))
    return "\n".join(out) + "\n"


# ---------- modes ----------

def mode_list(w):
    runs = list_runs(read_jsonl(w.rounds_dir / PROGRESS_FILE))
    if not runs:
        print(f"No runs recorded in {w.rounds_dir / PROGRESS_FILE}")
        return
    print(c("bold", pad("run_id", 18) + pad("started", 27) + pad("rounds", 8) + "result"))
    for r in runs:
        print(pad(r["run_id"], 18) + pad(r["start"] or "-", 27) + pad(r["rounds"], 8) +
              fit(r["reason"] or "(running)", 60))


def mode_raw(w):
    while True:
        w.poll()
        for stamp, _kind, text in w.live:
            print(f"{clock(stamp)}  {text}", flush=True)
        w.live.clear()
        time.sleep(POLL_S)


def mode_render(w, once):
    if TTY:
        sys.stdout.write("\x1b[?25l")
    try:
        while True:
            rid, events = w.poll()
            frame = render(w, rid, events)
            sys.stdout.write(("\x1b[2J\x1b[H" if TTY else "") + frame)
            sys.stdout.flush()
            if once:
                return
            time.sleep(POLL_S)
    finally:
        if TTY:
            sys.stdout.write("\x1b[?25h")


def main():
    ap = argparse.ArgumentParser(description="Live dashboard for a speckit rounds run")
    ap.add_argument("feature_dir", nargs="?", help="specs/NNN-name (default: .specify/feature.json)")
    ap.add_argument("--run", help="run_id to show (default: the latest)")
    ap.add_argument("--list", action="store_true", help="list recorded runs and exit")
    ap.add_argument("--once", action="store_true", help="render once and exit")
    ap.add_argument("--raw", action="store_true", help="tail the live round's events, no board")
    args = ap.parse_args()
    if os.name == "nt":
        os.system("")                   # enable VT escape processing on older consoles
    sys.stdout.reconfigure(errors="replace")

    w = Watch(resolve_feature_dir(args.feature_dir), args.run)
    try:
        if args.list:
            mode_list(w)
        elif args.raw:
            mode_raw(w)
        else:
            mode_render(w, args.once)
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
