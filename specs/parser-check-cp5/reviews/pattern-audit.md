# Pattern audit: parser-check CP5 (T092)

These are the five sweeps listed under plan.md "Pattern-audit obligations". Each one covers all of
`src/`, plus the packaged `hcparse.ps1` where the shape applies. The sweeps were done by grep over
the call sites, followed by reading each consumer.

The columns are:
- **confidence**: how sure the audit is that the row describes a real instance of the shape;
- **verdict**:
  - `fixed` means this change fixed it;
  - `intended` means the behaviour is deliberate and correct;
  - `follow-up` means it is real or plausible but left open. The row says why and who owns it.

`handlers/parse.py` and `sandbox/client.py` were being edited in parallel during this audit.
Findings in those files are follow-ups for the coordinator and were not edited here.

---

## Sweep 1: trusting a subprocess exit code

The shape: code treats `returncode == 0` as success where the program's contract says the exit
code does not decide the outcome (H4, FR-009).

| file:line | finding | confidence | verdict |
|---|---|---|---|
| `server/sandbox/cache.py:626` (`judge_generation`, def `:271`) | Generation is judged by R-05's three conditions: the generator exits 0, the config is non-empty, and the log has `Writing completed.`. The generator's exit code comes from `run.json` (`generate.exit_code`), not from the script's exit code. The script's exit code (`run_script_subprocess`, `:502`) is only logged | high | intended |
| `scripts/hcparse.ps1` (`Invoke-GenerateMode`) | The script applies the same three conditions before choosing exit 0 or 4. A generator that exits 0 with only the help text is exit 4 | high | intended |
| `scripts/hcparse.ps1` (`Invoke-HcRun`) | The outcome comes from hc's per-word output. Only hc exit -1 is used, and only to report a start failure (FR-016) | high | intended |
| `server/parser_probe.py:784` (`classify_hc_help`) | `hc -h` exits -1 by contract (F-2). Identity is decided from the usage text; the exit code is used only to recognise the .NET host-failure code | high | intended |
| `server/parser_probe.py:596` (`_find_hc_via_dotnet_tool_list`) | The listing is parsed first. A non-zero exit only feeds the diagnostic text | high | intended |
| `server/sandbox/client.py:833`, `:860` | The script's own exit code (6 or non-zero) is a cross-check beside `run.json` (`hc.timed_out`) and the stdout load-error detection. That matches contracts/hcparse.md section 3 ("the exit code only as a cross-check") | high | intended |
| `server/handlers/execution.py:4614`, `:4620` (`run_module`), `:5406` (scan modules) | The outcome comes from the `===FLEXTOOLS_RESULT_JSON===` / `USER_RESULT` markers. `returncode` is passed through for diagnostics only (`:4683`, `:5423`ff) | high | intended |
| `server/handlers/grammar_health.py:299`, `:321`, `:370` | The exit code is reported as `exit_code` detail on failures that were already decided from the scan envelope | high | intended |
| `server/project_discovery.py:153` | A non-zero exit from our own snippet (which `sys.exit(1)`s on error) means failure, and the stdout JSON is still validated | high | intended |
| `refresh.py:140`, `server.py:809` | Our own refresh scripts, where exit 0 is the success contract | high | intended |
| `server/parse/worker_client.py:207` and others | The exit code is used only as a liveness check (`returncode is None`) | high | intended |
| `server/subprocess_helpers.py:47` (`taskkill`) | Best effort; its exit code is ignored. Our `Stop-ProcessTree` in `hcparse.ps1` also falls back to `Process.Kill()` | medium | intended |

There are no siblings. Every consumer that decides an outcome decides it from output or a
structured file, not from the exit code alone.

## Sweep 2: cleanup on the happy path only

The shape is H6: a temporary file, directory or copy is deleted only when the code runs to the
end, not on every exit path.

| file:line | finding | confidence | verdict |
|---|---|---|---|
| `server/handlers/execution.py:4369` / `:5039` | `run_module`'s `NamedTemporaryFile(delete=False)` is deleted in the `finally` that covers every later return | high | intended |
| `server/handlers/execution.py:5391` / `:5409` | The scan temp script is deleted in a `finally` around `run_script_async` | high | intended |
| `server/project_discovery.py:137` | The snippet temp file is deleted in a `finally` | high | intended |
| `server/parse/worker_main.py:1463` | `gettempdir()/<P>HCLoadErrors.xml` is written by LCM, not by us, and is only read here | high | intended |
| `server/sandbox/cache.py:600`, `:676` | `<key>.partial/` is removed in a `finally`, and again at the start of the next build (for a killed server) | high | intended |
| `scripts/hcparse.ps1` (`Clear-WorkDir`) | The copy in `-WorkDir` is cleared in `finally` on every path. A tree kill skips it, and then `SandboxClient`'s `finally` plus the startup sweep delete it (R-11). tests/test_sandbox_client.py and tests/test_sandbox_no_project_writes.py prove `work/` is empty after every terminal path | high | intended |
| `server/backup.py:198` | **Sibling.** When `shutil.copy2` failed part-way (for example, the disk filled), it left a truncated `.fwdata` in the timestamp folder. Retention, or a person restoring, could take it for a real backup. It now removes the partial file and the empty timestamp folder, then re-raises into `backup_failed` | medium | **fixed** |
| `server/sandbox/workdir.py:190` (`create`) | If the marker write fails after `mkdir`, the directory has no marker, so the startup sweep (which needs the marker) never removes it. `SandboxClient`'s own `finally` still deletes it by path, so it leaks only if the server also dies | low | **fixed** (follow-up 4): the marker is written in a `try`; on any failure the guarded `delete` removes the just-made directory, then the error re-raises (`tests/test_sandbox_workdir.py::test_create_removes_its_directory_when_the_marker_write_fails`) |
| `server/sandbox/store.py:164` (`create_sandbox`) | If writing `hc-config.xml` or `origin.json` fails with a non-`FileExistsError` `OSError` (disk full), the claimed sandbox directory stays behind, possibly holding a truncated config. After that, `create_sandbox` reports `sandbox_exists` and `list` shows a broken sandbox. Any cleanup would delete in a user-owned area, which FR-025 guards, so this needs a deliberate decision | low | follow-up (store owner): remove only the directory this call created, only on that failure, with an explicit exception in the lifecycle test |

## Sweep 3: a verdict set that omits a member

The shape is F-16: a set lists some of `open_shared`, `open_exclusive` and `held_by_other` but not
all of them.

| file:line | set | omits | confidence | verdict |
|---|---|---|---|---|
| `server/parse/diff.py:105` (`_SHARED_VERDICTS`, `shared_mode_active`) | `open_shared`, `open_exclusive` | `held_by_other` | high | **intended**. See R-13 below |
| `server/handlers/parse.py:2648` (`SANDBOX_STALENESS_VERDICTS`) | all three | -- | medium | **fixed** (follow-up 1). See R-13 below |
| `server/write_ladder.py:91` (`REFUSING_VERDICTS`) | `open_exclusive`, `held_by_other` | `open_shared` | high | intended: shared mode does not block a write |
| `server/project_access.py:351` (`build_access_remedy`) | `open_exclusive`, `held_by_other` | `open_shared` | high | intended, as above. `stale_lock` has its own branch |
| `server/handlers/execution.py:2078` (`preflight project_lock.blocking`) | `open_exclusive`, `held_by_other` | `open_shared` | high | **fixed** (follow-up 3): the literal was equal to `write_ladder.REFUSING_VERDICTS` and is now the constant (`tests/test_issue49_validate_only.py::test_blocking_follows_the_write_ladder_refusing_set`) |
| `server/handlers/execution.py:4422` | `open_shared` only | the other two | high | intended: the read-back note is only for a fresh non-master peer. The other verdicts refuse, or fail at open |
| `server/handlers/parse.py:1410` (`_access_block`) | `open_shared` advisory | -- | high | intended: the other verdicts go through `decision.refusal` |
| `server/handlers/parse.py:1770` (filing `shared`) | `sharing` or `open_shared` | -- | high | intended and documented (`:1613`): sharing is read from the project setting, because the probe says `held_by_other` for any Python holder |
| `server/handlers/diagnostic_health.py:676`, `execution.py:1234` | pass the verdict through | -- | high | intended |

**R-13's in-process question.** Should `held_by_other` also downgrade in-process diffs? **No.
Leave `shared_mode_active` as CP3 shipped it.**

`held_by_other` is what the probe reports for any live non-FieldWorks holder, and this server's
own read-only parse worker is one (`handlers/parse.py:1613`). So a widened in-process rule would
mark almost every in-process diff `no_change_unverifiable` while the MCP's own worker holds the
lock, and that worker has no unsaved edits. The danger `shared_mode_active` guards against is
FieldWorks holding grammar edits in memory, and that only happens with a FieldWorks holder. CP3's
verdicts are unchanged by this audit.

**The same fact is a follow-up for the sandbox set.** `SANDBOX_STALENESS_VERDICTS` includes
`held_by_other`. So a sandbox run started while this server's own read worker holds the project
gets `staleness: shared_mode_unverifiable`, even though the `.fwdata` on disk is exactly what that
worker read. To fix it, `handlers/parse.py` `_sandbox_access` (being edited) would have to
exclude a holder whose pid is `runner.read_worker_pid(project)`. The filing path already makes
that check in `_held_by_own_read_worker`, `:1395` ff. This is a coordinator follow-up.

**Fixed (follow-up 1).** `_sandbox_access` now skips the staleness when the verdict is
`held_by_other` and the holder's pid is `runner.read_worker_pid(project)`, through
`_holder_is_own_read_worker`, which `_held_by_own_read_worker` (filing) now shares. Any failure
of that check keeps the staleness. Tests: `tests/test_sandbox_handler.py::TestParseStaleness`
(`test_own_read_worker_holder_is_not_stale`, `test_other_holder_pid_stays_stale`).

## Sweep 4: an implicit subprocess encoding

The shape is F-1's: `text=True` without `encoding=`, or a decode with no declared codec.

| file:line | finding | confidence | verdict |
|---|---|---|---|
| `server/parser_probe.py:576` (`_find_hc_via_dotnet_tool_list`) | Already fixed in CP5: `encoding="utf-8", errors="replace"` | high | fixed (earlier CP5 task) |
| `refresh.py:130` | **Sibling.** `text=True` with no encoding, so the refresh scripts' output (which prints paths) was decoded in the locale code page. A strict decode error raises inside `run()` and is reported as a failed refresh even when the child succeeded. It now uses `encoding="utf-8", errors="replace"`, with `PYTHONIOENCODING=utf-8` for the Python child | medium | **fixed** |
| `server.py:798` (auto-refresh) | **Sibling**, same shape and same fix | medium | **fixed** |
| `server/project_discovery.py:144` | **Sibling**, same shape. The snippet prints ASCII JSON, but stderr (a pythonnet / .NET message) was decoded implicitly. Same fix | low | **fixed** |
| `server/subprocess_helpers.py:113` (`run_script_async`) | Decodes UTF-8 with `replace`. The generated scripts reconfigure their own stdout and stderr to UTF-8 (`execution.py:3790`, `:5119`) | high | intended |
| `server/parser_probe.py:657` (`_decode_hc_stdout`) | UTF-16LE is declared, and a BOM is tolerated | high | intended |
| `server/sandbox/cache.py:528` | The script's console is decoded as ASCII, which it is by contract (FR-021) | high | intended |
| `server/sandbox/cache.py:624` + `scripts/hcparse.ps1` generator capture | The script copies the generator's bytes verbatim, and Python decodes them as UTF-8. The real GenerateHCConfig is a .NET Framework console app, so when redirected it may write in the OEM code page. A load-error line holding a vernacular form could then decode as mojibake inside `key.json`'s `load_errors`. The progress lines are ASCII, so the success judgement is unaffected | medium | follow-up: **LIVE** (M-1, with L-1). Capture a non-ASCII load error from the real generator. If the output is not UTF-8, decode it with the console code page in the script and write the log as UTF-8 |

## Sweep 5: a typed reader that silently drops keys a writer adds

The shape is F-12's.

| file:line | finding | confidence | verdict |
|---|---|---|---|
| `server/parse/record.py:571` (`read_meta`) | This is the known instance: it filters to `RunMeta` fields. CP5 declared `spine` and `sandbox`, as CP4 declared `filing`. The reader ignoring unknown keys is the forward-compatibility rule (CP3 artifact.md section 9) | high | intended |
| `server/parse/record.py:583` (`set_stage(**updates)`) | **Sibling, on the writer side.** `setattr` accepts any key, but `write_meta` serialises declared fields only (`asdict`), so an undeclared update vanished. The runner's `_set_stage` wraps the call in `contextlib.suppress`, so raising would have hidden the write entirely. It now logs a WARNING that names the undeclared keys. Today's callers pass only declared keys | medium | **fixed** |
| `server/sandbox/client.py:178` (`SandboxLaunch.from_value`) | Filters the handler's dict to declared fields, and ignores unknown keys by design. The handler's keys (`handlers/parse.py:3325`) are all declared today, including `assertion_file`. A key added to the handler but not to `SandboxLaunch` would be dropped silently | medium | **fixed** (follow-up 2): both. Undeclared keys (other than the `corpus_path` alias) are named in a WARNING, not raised; `tests/test_sandbox_client.py::test_every_key_the_handler_passes_is_declared` compares `_sandbox_launch`'s keys with `fields(SandboxLaunch)` |
| `server/parse/fingerprint.py:68` (`ScopeFingerprint.from_dict`) | Refuses extra keys loudly (`ValueError`); nothing is dropped silently. The sandbox writer (`_sandbox_fingerprint`) builds through the dataclass | high | intended |
| `server/sandbox/script.py:129` / `store.py:217` / `workdir.py:201` | Return the raw dict, with no filtering | high | intended |

## Sweep 6: a transient read treated as absence

The coordinator added this sweep. The shape: a reader returns the same `None` for "the file does
not exist" and "the file exists but could not be read right now". Callers then read the second
case as "no such run" or "pre-CP5". On Windows under load, an antivirus scanner or indexer can
hold `meta.json` for a moment and cause exactly that.

`RunRecord.read_meta` (`server/parse/record.py`) returned `None` on any `OSError` or
`JSONDecodeError`. It now works like this:

- `read_meta_strict()` returns `None` **only** when `meta.json` is missing. When the file exists
  but cannot be read, it retries `META_READ_ATTEMPTS` (4) times, `META_RETRY_DELAY_SECONDS`
  (50 ms) apart. If the file is still unreadable, it raises `MetaUnreadable`, a subclass of
  `OSError`. A non-object JSON document counts as unreadable.
- `read_meta()` keeps its contract (a `RunMeta` or `None`) and runs the same retry, so a brief lock
  no longer reads as absence. It returns `None` only for a missing file, or for a file that stays
  unreadable for about 200 ms.
- The writers `set_stage` and `set_section` now use `read_meta_strict`. **This was the worst
  sibling.** Before the change, one unreadable moment made them fall back to
  `RunMeta(run_id, stage=starting)` and **rewrite meta.json from blank**. That erased the
  fingerprint, `sandbox`, `filing`, counters and the load-error baseline. Now they raise instead.
  The runner's `_set_stage` already wraps the call in `contextlib.suppress`, so a persistently
  unreadable file skips that one stage write and loses no data.

Every caller, audited:

| caller (file:line) | what `None` meant before | effect of the fix | verdict |
|---|---|---|---|
| `parse/record.py` `set_stage` | A blank meta, then a rewrite (**data loss**) | Strict read: raises and never rewrites from blank | **fixed** |
| `parse/record.py` `set_section` | A blank meta, then a rewrite (**data loss**) | Strict read | **fixed** |
| `parse/diff.py:224` (`_read_meta`) | Its own local single read plus retry, raising `RunNotComparable` | Still correct: `read_meta` retries internally and returns `None` only after that, so diff's loop is now redundant but harmless | intended (the local fix could now call `read_meta_strict`: optional tidy-up) |
| `filing/claims.py:259` (crash sweep) | `None` meant no filing section, so the record was skipped | A transient lock is retried. A persistent one is still skipped, which is right for a sweep | fixed by the retry |
| `filing/gate.py:307` (baseline search) | `None` was skipped, inside `except Exception` | Same | fixed by the retry |
| `handlers/parse.py:2117`, `:2127` (`parse_log`) | `None` meant "not applicable" (sandbox sections) or an empty summary, a **misread** of an existing run | Strict read (follow-up 7): a persistent `MetaUnreadable` answers `server_state_error` (`server_state: run_record_unreadable`, component `parse_record`) with a retry rung naming the same call, never "not applicable" or an empty summary | **fixed** |
| `handlers/parse.py:2375` (`parse_diff`, access probe) | Probe skipped | Retried | fixed by the retry |
| `handlers/parse.py:3349`, `:3753` (`_sandbox_recorded`, sandbox meta) | Fell back to what was submitted | Retried | fixed by the retry |
| `sandbox/client.py:453`, `:971` | Existing counter divergences read as `[]`, then `set_section`, which could overwrite them | Retried, and `set_section` no longer rewrites from blank | fixed |
| `sandbox/client.py:881` (`_update_sandbox`) | Section read as `{}`, then written back, which could **erase `meta.sandbox`** | Strict read (follow-up 7): a persistent `MetaUnreadable` (on the read, or on `set_section`'s own read) skips that one update with a WARNING; nothing is written back | **fixed** |
| `sandbox/store.py:455` (`_check_seedable`) | `None` meant `RunNotFound`, a **misread** | Strict read (follow-up 7): `MetaUnreadable` propagates (not `RunNotFound`), and the handler's `_sandbox_seed` answers it with the same retryable `server_state_error` as `parse_log` (not `parse_sandbox_refused`, whose reason enum is closed) | **fixed** |

A related writer-side note (low confidence, follow-up): `write_meta`'s `os.replace` onto
`meta.json` can itself hit a Windows sharing violation while a reader has the file open. The
runner suppresses that, and the next stage write repairs it, but a retry there would complement
this change.

---

## Fixes applied here

- `src/flextoolsmcp/server/backup.py`: a failed backup copy is removed, together with its empty
  timestamp folder. The new helper is `_remove_partial_backup`.
- `src/flextoolsmcp/refresh.py`, `src/flextoolsmcp/server.py`,
  `src/flextoolsmcp/server/project_discovery.py`: each subprocess now declares its codec on both
  ends (`encoding="utf-8", errors="replace"`, and `PYTHONIOENCODING=utf-8` for the child).
- `src/flextoolsmcp/server/parse/record.py`:
  - `set_stage` names undeclared meta keys in a warning instead of dropping them silently;
  - adds `read_meta_strict`, `MetaUnreadable`, `META_READ_ATTEMPTS` and
    `META_RETRY_DELAY_SECONDS`;
  - `read_meta` now retries a meta.json that exists but cannot be read;
  - `set_stage` and `set_section` read strictly, so they never rewrite a record from blank
    (sweep 6).

## Follow-ups for the coordinator

1. **Fixed.** `handlers/parse.py` `_sandbox_access`: do not treat this server's own read worker (a
   `held_by_other` holder) as a staleness source for sandbox runs (sweep 3).
2. **Fixed.** `sandbox/client.py` `SandboxLaunch.from_value`: surface the handler keys it drops (sweep 5).
3. **Fixed.** `handlers/execution.py:2078`: use `write_ladder.REFUSING_VERDICTS` instead of a copied literal
   (sweep 3).
4. **Fixed.** `sandbox/workdir.py` `create`: remove the directory if the marker write fails (sweep 2).
5. `sandbox/store.py` `create_sandbox`: decide how to clean up a claim whose write failed, within
   FR-025 (sweep 2).
6. **LIVE:** find out the real GenerateHCConfig's redirected console encoding for non-ASCII
   load-error lines (sweep 4).
7. **Fixed** (the three callers below; the `parse/diff.py` tidy-up is not done). Use `read_meta_strict`, and map a persistent `MetaUnreadable` to a retryable error instead of
   absence, in:
   - `handlers/parse.py` `parse_log` (`:2117`, `:2127`);
   - `sandbox/client.py` `_update_sandbox` (`:881`);
   - `sandbox/store.py` `_check_seedable` (`:455`).

   `parse/diff.py`'s local retry can call `read_meta_strict` directly (sweep 6).
