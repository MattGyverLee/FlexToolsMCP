# CP2b Sweep-Pattern Audit — "truth-test on a key a code path never sets"

## 1. The two known instances, confirmed

**Instance A — parse.py:465.** `if level != "restricted" and not result.get("parsed", False):`
`result` is built by `_inline_response` (parse.py:513-557). `result["parsed"]` is set
ONLY inside `if level == "plain":` (line 536). The `else` branch (538-554, covering
both `explain` and `restricted`) never writes the key. So for `level="explain"`,
`result.get("parsed", False)` is always `False`, the guard at 465 is always true, and
`_propose_decomposition` (679-737) fires on every explain call, including one where
the word parsed successfully — contradicting contracts/tools.md:97 ("Agreement
produces no commentary") and FR-025. Confirmed by direct read of both branches.

**Instance B — parse.py:776-784 (`_level_guidance`, explain branch).** Compare the
`plain` branch (757-774), which is gated on `result.get("parsed")` and returns
`{"explains_failure": False, "next_step": None}` on success. The `explain` branch has
no such gate: it unconditionally returns `explains_failure: True` plus failure-flavored
guidance and `[_restricted_rung, _lookup_rung]`, for every explain call regardless of
outcome. Root cause is the same as Instance A: `result["parsed"]` is never populated
for `explain`, so there is no signal this branch *could* gate on even if it tried.

## 2. Siblings table

| Site | Key | Path that omits it | Verdict |
|---|---|---|---|
| parse.py:465 `_inline_response`/guard | `parsed` | `explain`/`restricted` branch (538-554) of `_inline_response` never sets it | **DEFECT** (Instance A) |
| parse.py:776-784 `_level_guidance` explain | `parsed` (implicit) | Same root cause; no gate exists at all | **DEFECT** (Instance B) |
| parse.py:891-892 `_result_summary`, `parse.get("parsed")` | `parsed` | `worker_main.py` `BackendFacade.parse()` (698-736): `restricted`/`explain` branches (715-732) return `{"parse": None, ...}`; only the `plain` branch (734-736) calls `_summarize_plain`, which is the only place that ever writes `"parsed"`. `runner.py:409` passes `result.get("parse")` straight into `entry["parse"]` unchanged. | **DEFECT (new sibling, HIGH)** — a `flextools_parse_status` poll on ANY completed `explain`/`restricted` run (including a single overflowed word, already reachable in CP2b scope) reports `result_summary.parsed: 0` unconditionally, indistinguishable from "every word failed to parse," even when the trace shows successful analyses. |
| parse.py:721 `answer.get("index_ready")` | `index_ready` | `worker_main.py` sets it explicitly on both branches (1076 `False`, 1109 `True`) of `_drain_resolve` | by-design |
| parse.py:723-724 `_propose_decomposition`, `rows = answer.get("resolutions") or []` / `rows[0].get("outcome")` | `resolutions`, `outcome` | Both worker branches always emit `resolutions` (`[]` at 1075, populated list at 1108) and every row dict always carries `outcome` (1094) | by-design |
| parse.py:203-211 `_resolve_restriction` (`answer.get("resolutions") or []`, `row.get("outcome")`, `row.get("msa_hvos") or []`) | same | Worker's per-row dict (worker_main.py:1092-1100) always includes all four fields | by-design (defensive fallback only) |
| parse.py:415 `detail.get("hint") or str(refused)` | `hint` | `refusal_detail()`/`_refusal_from_row` always populate `hint` per outcome | by-design |
| parse.py:894 `_result_summary`, `entry.get("trace_path")` | `trace_path` | Absent only for `plain`-level entries (runner.py:411-418: `trace_path` set only `if trace_xml:`), which correctly never write a trace | by-design |
| runner.py:409 `"parse": result.get("parse")` | `parse` | Verbatim pass-through of the worker's intentional `None` for explain/restricted | by-design at this layer — but this is the transmission point feeding the `_result_summary` defect above |
| worker_client.py:198-205 (`ready.get("type")`, `.get("message")`, `.get("protocol")`) | various | Malformed/absent handshake is handled by the `ready is None` branch above; a well-formed `ready` message always carries these | by-design |
| worker_client.py:335 `message.get("names") or []` | `names` | Always present for that message type; `[]` fallback matches "no names" semantics, not an inverted default | by-design |

11 sites inspected across parse.py, worker_main.py, runner.py, resolver.py, record.py,
worker_client.py, stages.py, queue.py, priority.py (the last three had no matching
`.get(...)`/truth-test hits).

## 3. Audit conclusion (quotable for cp2b-evidence.md)

11 sites inspected, 3 defects (2 previously known — parse.py:465 and parse.py:776-784,
both rooted in `_inline_response` never setting `result["parsed"]` outside `level ==
"plain"` — plus 1 new sibling at parse.py:891-892 where `_result_summary` inherits the
same missing-key shape from `worker_main.py`'s `BackendFacade.parse()` and silently
reports `parsed: 0` for every completed explain/restricted run), 8 sites confirmed
by-design (worker-side messages that always populate the key on every branch, or
fallbacks whose empty/false default matches rather than inverts the omitted case).
