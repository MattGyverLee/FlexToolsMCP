#
#   speckit_rounds_opencode.py
#
#   OpenCode port of speckit_rounds.py: drive the post-clarify Companion
#   pipeline (plan -> tasks -> implement) unattended, one FRESH top-level
#   `opencode run` session per round.
#
#   Round selection, progress detection and stop rules are shared with
#   speckit_rounds.py (imported, not copied). What differs is the session
#   runner:
#     * OpenCode discovers .claude/skills/*/SKILL.md and falls back to
#       CLAUDE.md, so the speckit-round skill and the project rules carry
#       over. Don't set OPENCODE_DISABLE_CLAUDE_CODE(_SKILLS|_PROMPT).
#     * `--format json` streams NDJSON events, not one result object. The
#       round's reply is the concatenated `text` parts; cost and tokens come
#       from `step_finish` parts; failures arrive as `error` events.
#     * There is no per-round budget flag. --max-total-cost-usd is checked
#       between rounds, and --round-timeout bounds each session.
#     * Driver events (run/round start and end) go to
#       <feature>/rounds/progress.jsonl, and each round's raw events to
#       <feature>/rounds/<run_id>-round-NN-<step>.opencode.jsonl. Watch both
#       from another terminal with `python scripts/speckit_watch.py`.
#     * The session runs in the feature's worktree (feature_root), where
#       its spec folder lives on the feature branch. After every round the
#       spec folder is committed and pushed on that branch
#       (scripts/speckit_git.py); feature code is committed per phase by the
#       round itself.
#     * Subagents and the compaction/summary/title agents are pinned to the
#       round's --model via OPENCODE_CONFIG_CONTENT (round_env), so a global
#       per-agent model (e.g. a local Ollama one) can't stall the workers.
#       --keep-agent-models opts out.
#     * Unattended permissions use `--auto` (on by default here; pass
#       --no-auto to let non-allowed permissions be refused instead).
#
#   Defaults to Muse Spark 1.3 free (opencode/muse-spark-1.3-contributor-free).
#   Any override (`-m provider/model`) must call tools and hold a round's
#   context; a small local model will stall or refuse.
#
#   Usage:
#       python scripts/speckit_rounds_opencode.py [specs/NNN-name] [options]
#       python scripts/speckit_rounds_opencode.py --dry-run
#
#   Platform: any (needs the `opencode` CLI on PATH)
#
#   Copyright 2026
#

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime

from speckit_git import sync_spec
from speckit_rounds import (
    ROUND_RE,
    feature_root,
    fingerprint,
    resolve_feature_dir,
    round_label,
    status,
)

# Muse Spark 1.3 (free tier). Override with -m provider/model.
DEFAULT_MODEL = "opencode/muse-spark-1.3-contributor-free"

# Agents a round's model is pinned onto (see round_env). "reviewer" is a
# custom subagent some global configs define; naming it is harmless if absent.
HELPER_AGENTS = ("general", "explore", "reviewer", "compaction", "summary", "title")

# Driver event stream under <feature>/rounds/, read by scripts/speckit_watch.py.
PROGRESS_FILE = "progress.jsonl"


# Which input field best describes a call, per opencode tool name.
TOOL_ARG_KEYS = ("command", "filePath", "path", "pattern", "name", "description", "url", "query")


def _short(text, width):
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[:width - 3] + "..."


def describe_tool(part):
    """One console line for a tool_use part: `tool  <key input>  [status]`."""
    state = part.get("state") or {}
    inp = state.get("input") or {}
    arg = next((inp[k] for k in TOOL_ARG_KEYS if inp.get(k)), None)
    if arg is None and part.get("tool") == "todowrite":
        todos = inp.get("todos") or []
        busy = [t.get("content") for t in todos if t.get("status") == "in_progress"]
        arg = f"{len(todos)} todos" + (f", now: {busy[0]}" if busy else "")
    if arg is None and inp:
        arg = json.dumps(inp, ensure_ascii=False)
    flag = "" if state.get("status") in (None, "completed") else f"  [{state.get('status')}]"
    return f"{part.get('tool', '?'):<10} {_short(arg or '', 100)}{flag}"


def echo(stamp, line):
    print(f"      {time.strftime('%H:%M:%S', time.localtime(stamp))}  {line}", flush=True)


def context_tokens(tokens):
    """Tokens the model held on a step: fresh input plus cache reads and writes."""
    cache = tokens.get("cache") or {}
    return (tokens.get("input") or 0) + (cache.get("read") or 0) + (cache.get("write") or 0)


def fmt_context(ctx, limit):
    """`89,199 / 1,048,576 (9%)`, or just `89,199` when the limit is unknown."""
    return f"{ctx:,} / {limit:,} ({100 * ctx / limit:.0f}%)" if limit else f"{ctx:,}"


def model_context_limit(opencode, model):
    """The model's context window from `opencode models <provider> --verbose`, or None."""
    if not (opencode and model and "/" in model):
        return None
    try:
        out = subprocess.run([opencode, "models", model.split("/", 1)[0], "--verbose"],
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=90).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    # The listing is `provider/model` on its own line, then that model's JSON.
    at = out.find(model + "\n")
    if at < 0:
        return None
    try:
        meta, _ = json.JSONDecoder().raw_decode(out[at + len(model):].lstrip())
    except ValueError:
        return None
    return (meta.get("limit") or {}).get("context")


def show_event(ev, started, limit=None):
    """Print the live view of one event (tools, text, per-step tokens)."""
    kind = ev.get("type")
    part = ev.get("part") or {}
    stamp = (ev.get("timestamp") or time.time() * 1000) / 1000
    if kind == "tool_use":
        echo(stamp, describe_tool(part))
    elif kind == "text" and (part.get("text") or "").strip():
        first = part["text"].strip().splitlines()[0]
        echo(stamp, f"{'say':<10} {_short(first, 100)}")
    elif kind == "step_finish":
        tok = part.get("tokens") or {}
        echo(stamp, f"{'step':<10} ctx {fmt_context(context_tokens(tok), limit)}  "
                    f"out {tok.get('output') or 0:,}  +{time.time() - started:.0f}s")
    elif kind == "error":
        err = ev.get("error") or {}
        echo(stamp, f"{'ERROR':<10} {(err.get('data') or {}).get('message') or err.get('name')}")


def round_env(args):
    """The session's environment: pin helper agents to the round's model.

    `--model` only sets the primary agent. Subagents (general, explore) and
    the compaction/summary/title agents keep whatever the user's global
    opencode config names -- e.g. a local Ollama model that times out under
    five parallel workers. OPENCODE_CONFIG_CONTENT merges over that config
    for this process only; any value already in the environment is kept and
    merged under ours.
    """
    env = os.environ.copy()
    if args.keep_agent_models or not args.model:
        return env
    try:
        config = json.loads(env.get("OPENCODE_CONFIG_CONTENT") or "{}")
    except ValueError:
        config = {}
    agents = config.setdefault("agent", {})
    for name in HELPER_AGENTS:
        agents.setdefault(name, {})["model"] = args.model
    config["small_model"] = args.model
    env["OPENCODE_CONFIG_CONTENT"] = json.dumps(config)
    return env


def run_opencode(opencode, prompt, args, log_path):
    """Run one round, streaming events to the console and log_path.

    Returns (lines, stderr, returncode, timed_out).
    """
    root = feature_root(args.feature_dir)
    cmd = [opencode, "run", "--format", "json", "--dir", str(root),
           "--title", "speckit-round"]
    if args.auto:
        cmd.append("--auto")
    if args.model:
        cmd += ["--model", args.model]
    if args.variant:
        cmd += ["--variant", args.variant]
    if args.agent:
        cmd += ["--agent", args.agent]
    # The prompt is a positional argument. It holds no cmd.exe metacharacters,
    # so it survives the opencode.CMD shim on Windows.
    cmd.append(prompt)

    started = time.time()
    proc = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace",
                            env=round_env(args))
    # stderr is drained on a thread so a chatty opencode can't block stdout.
    err_chunks = []
    err_thread = threading.Thread(target=lambda: err_chunks.append(proc.stderr.read()), daemon=True)
    err_thread.start()
    killed = threading.Event()
    watchdog = threading.Timer(args.round_timeout, lambda: (killed.set(), proc.kill()))
    watchdog.start()

    lines = []
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            for line in proc.stdout:
                log.write(line)
                log.flush()
                lines.append(line)
                if args.quiet:
                    continue
                try:
                    show_event(json.loads(line), started, args.context_limit)
                except ValueError:
                    pass
        proc.wait()
    finally:
        watchdog.cancel()
    err_thread.join(timeout=5)
    return lines, "".join(err_chunks), proc.returncode, killed.is_set()


def summarize_events(lines):
    """Fold the NDJSON events into (text, cost, out_tokens, steps, error, peak_ctx)."""
    texts, cost, out_tokens, steps, error, peak_ctx = [], 0.0, 0, 0, None, 0
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        kind = ev.get("type")
        part = ev.get("part") or {}
        if kind == "text":
            texts.append(part.get("text") or "")
        elif kind == "step_finish":
            steps += 1
            cost += part.get("cost") or 0.0
            # Each step's input re-counts the whole context, so only output sums.
            out_tokens += (part.get("tokens") or {}).get("output") or 0
            peak_ctx = max(peak_ctx, context_tokens(part.get("tokens") or {}))
        elif kind == "error":
            err = ev.get("error") or {}
            error = (err.get("data") or {}).get("message") or err.get("name") or "error"
    return "\n".join(texts), cost, out_tokens, steps, error, peak_ctx


def main():
    ap = argparse.ArgumentParser(description="OpenCode driver for speckit rounds")
    ap.add_argument("feature_dir", nargs="?", help="specs/NNN-name (default: .specify/feature.json)")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL,
                    help=f"provider/model, passed to opencode --model (default: {DEFAULT_MODEL})")
    ap.add_argument("--variant", help="reasoning effort, passed to opencode --variant")
    ap.add_argument("--agent", help="opencode agent to run the round as (default: its default agent)")
    ap.add_argument("--keep-agent-models", action="store_true",
                    help="don't pin subagents/compaction to --model; use the global opencode config's per-agent models")
    ap.add_argument("--no-auto", dest="auto", action="store_false",
                    help="don't pass --auto (non-allowed permissions are refused, which usually stalls a round)")
    ap.add_argument("--max-rounds", type=int, default=25)
    ap.add_argument("--round-timeout", type=int, default=3 * 3600,
                    help="seconds before a round's session is killed (default: 10800)")
    ap.add_argument("--max-total-cost-usd", type=float,
                    help="stop before the next round once reported cost reaches this")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="only print the per-round summary, not the live event feed")
    ap.add_argument("--dry-run", action="store_true", help="print the next round's prompt and stop")
    args = ap.parse_args()
    # Round text can carry vernacular or model punctuation; never crash cp1252.
    sys.stdout.reconfigure(errors="replace")

    feature_dir = args.feature_dir = resolve_feature_dir(args.feature_dir)
    opencode = shutil.which("opencode")
    if not opencode and not args.dry_run:
        sys.exit("[ERROR] `opencode` CLI not found on PATH")

    log_dir = feature_root(feature_dir) / feature_dir / "rounds"
    run_id = time.strftime("%Y%m%d-%H%M%S")
    emit = progress_emitter(log_dir / PROGRESS_FILE, run_id) if not args.dry_run else (lambda *a, **k: None)
    args.context_limit = None if args.dry_run else model_context_limit(opencode, args.model)
    if not args.dry_run:
        print(f"[INFO] model {args.model}, context window "
              f"{f'{args.context_limit:,} tokens' if args.context_limit else 'unknown'}", flush=True)
    emit("run-start", feature=feature_dir.as_posix(), model=args.model, max_rounds=args.max_rounds,
         context_limit=args.context_limit)
    code, reason, rounds, total_cost = drive(feature_dir, opencode, args, log_dir, run_id, emit)
    emit("run-end", code=code, reason=reason, rounds=rounds, cost=round(total_cost, 4))
    return code


def progress_emitter(path, run_id):
    """Append one JSON line per driver event; scripts/speckit_watch.py folds them."""
    def emit(phase, **fields):
        path.parent.mkdir(parents=True, exist_ok=True)
        # isoformat, not strftime("%z"): on Windows %z can yield a zone name.
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        ev = {"ts": ts, "run_id": run_id, "phase": phase, **fields}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    return emit


def drive(feature_dir, opencode, args, log_dir, run_id, emit):
    """The round loop. Returns (exit_code, reason, rounds_run, total_cost)."""
    stalls, prev_fp = 0, None
    total_cost = 0.0

    def stop(code, reason, n):
        print(reason)
        return code, reason, n, total_cost

    for n in range(1, args.max_rounds + 1):
        res = status(feature_dir)
        if res.get("complete"):
            return stop(0, f"[DONE] pipeline complete after {n - 1} round(s), ${total_cost:.2f}", n - 1)
        step, phase = round_label(res, feature_dir)
        if res.get("empty") or step in (None, "specify", "clarify"):
            return stop(1, f"[STOP] next step is '{step}': run specify/clarify interactively first", n - 1)
        if args.max_total_cost_usd is not None and total_cost >= args.max_total_cost_usd:
            return stop(1, f"[STOP] cost cap reached: ${total_cost:.2f} >= ${args.max_total_cost_usd:.2f}", n - 1)

        fp = fingerprint(feature_dir, res)
        if fp == prev_fp:
            stalls += 1
            if stalls >= 2:
                return stop(1, f"[STOP] no recorded progress in two rounds (still at {res.get('nextActionLabel')})", n - 1)
        else:
            stalls = 0
        prev_fp = fp

        prompt = f"Invoke the speckit-round skill with argument: {feature_dir.as_posix()}"
        label = f"{step}" + (f" / {phase}" if phase else "")
        if args.dry_run:
            print(f"[INFO] next round: {label}\n[INFO] prompt: {prompt}")
            return 0, "dry run", 0, 0.0

        print(f"[INFO] round {n}: {label} ...", flush=True)
        started = time.time()
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / f"{run_id}-round-{n:02d}-{step}.opencode.jsonl"
        print(f"      log: {log_path.relative_to(feature_root(feature_dir)).as_posix()}", flush=True)
        emit("round-start", round=n, step=step, label=label, log=log_path.name,
             next_task=res.get("nextTask"))
        lines, stderr, returncode, timed_out = run_opencode(opencode, prompt, args, log_path)

        text, cost, out_tokens, steps, error, peak_ctx = summarize_events(lines)
        total_cost += cost
        m = ROUND_RE.findall(text)
        verdict, detail = m[-1] if m else ("?", (text.strip().splitlines() or [""])[-1])
        if timed_out:
            verdict = "TIMEOUT"
        elif error or returncode:
            verdict = "FAILED"
        elapsed = time.time() - started
        print(f"      {verdict} in {elapsed:.0f}s, {steps} steps, "
              f"{out_tokens:,} output tokens, peak ctx {fmt_context(peak_ctx, args.context_limit)}, "
              f"${cost:.2f} -- {detail}")
        emit("round-end", round=n, verdict=verdict, detail=detail[:300], seconds=round(elapsed),
             steps=steps, out_tokens=out_tokens, peak_ctx=peak_ctx, cost=round(cost, 4), error=error)
        synced = sync_spec(feature_dir, f"spec({feature_dir.name}): round {n} {verdict} -- {label}")
        print(f"      spec sync: {synced}", flush=True)
        emit("spec-sync", round=n, result=synced)

        if timed_out:
            return stop(1, f"[FAIL] round {n} killed after {args.round_timeout}s; see {log_path}", n)
        if error or returncode:
            return stop(1, f"[FAIL] round {n}: opencode exited {returncode}"
                           f"{f' ({error})' if error else ''}\n{stderr[-2000:]}", n)
        if verdict == "BLOCKED":
            return stop(1, f"[STOP] blocked: {detail}", n)

    return stop(1, f"[STOP] --max-rounds {args.max_rounds} reached, ${total_cost:.2f}", args.max_rounds)


if __name__ == "__main__":
    sys.exit(main())
