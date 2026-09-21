# Cycle 1 -- QC: implementation design for #168 / #169 / #170

Feature: project-adoption
Note: authored by the lex-qc agent (read-only, no write tool); persisted
verbatim by the main session.

## #169 mechanism (choice + rejected alternatives)

**Chosen: (c), scoped narrowly.** Add `cold_adopt_consumed: bool = False`
to `SessionState`, orthogonal to `initialized` and to `project_name`.
Change only the `is_run_module` branch's entry condition in `server.py`
(~891-898) to `not session_state.initialized or (not
session_state.cold_adopt_consumed and not session_state.project_name)`.
Inside that branch, unconditionally set
`session_state.cold_adopt_consumed = True` before falling through, so it
fires at most once per session regardless of outcome. The
`is_read_only_safe` branch is **untouched** -- still keyed on
`not session_state.initialized` only.

**Why not (a):** `configure()` unconditionally sets `initialized=True`
(session.py:296) for every caller, including the auto-init call at
server.py:906-910 (which also passes `project_name=""` for plain
READ_ONLY_SAFE cold-adopts). Making empty starts leave
`initialized=False` requires special-casing `configure()` itself, which
then leaves READ_ONLY_SAFE auto-inits ALSO at `initialized=False` -- the
outer gate re-fires on every subsequent read-only call. Victim:
`record_auto_init()`'s "0 or 1 per conversation" invariant (breaks
`test_second_auto_init_logs_warning`'s premise into constant WARNING
spam) and the hardcoded `api_mode="flexicon"` in the auto-init call
silently overwrites a user's explicit `liblcm`/`flexlibs_stable` choice
on every call.

**Why not (b) unscoped:** Keying the *outer* gate off
`not session_state.project_name` has the identical two failures as (a) --
record_auto_init() spam and api_mode stomp -- but for EVERY tool, not
just run_module, hitting the deliberately project-less discovery workflow
the docs explicitly bless ("project_name can be set now or provided
later").

**Why not full (c) as a general flag:** A flag that also gates the
READ_ONLY_SAFE branch reintroduces the same api_mode/spam risk; scoping
it to run_module only avoids touching configure()'s session-identity
rules (#42/P0), the same_project write_enabled inheritance in
admin.py:521-529, and #47's auto-discovery accounting -- zero blast
radius there.

## #168 exact diff

All three sites: change the guard from `if resolved and resolved !=
<local>:` to `if resolved:`. Keep both body lines (session update + local
reassignment) -- the reassignment is a harmless no-op on exact match,
load-bearing on typo-correction.

- `execution.py:2851`: `if resolved and resolved != project_name:` ->
  `if resolved:` (body: `session_state.project_name = resolved`;
  `project_name = resolved` -- both stay).
- `grammar_health.py:258`: same pattern, `project_name` local var, same
  fix.
- `parse.py:326`: `if resolved and resolved != name:` -> `if resolved:`
  (body: `session_state.project_name = resolved`; `name = resolved` --
  note local var is `name`, both stay).
- `admin.py:507` is explicitly OUT of scope -- `project_name` there is
  already fed into `configure()` two lines later regardless of this
  guard, so it's already correct; leave untouched.

## #170 hint strings (verbatim)

`project_not_open`:
"pick one of available_projects in this payload and call flextools_start
with it as project_name -- that's the durable fix. Passing project_name
directly to the failing call works too, but start with flextools_start."

`project_name_required`:
"pick one of available_projects in this payload and pass it as
project_name -- either to flextools_start now, or directly to this call."

Both keep the `available_projects` pointer; both name `flextools_start`
explicitly; `project_not_open` leads with `flextools_start`, not the
per-op route.

## Test plan

No existing assertion needs editing (substring checks still hold against
new strings). New tests, `tests/test_issue53_cold_start.py` +
integration:

1. Exact-name adoption then bare call, for run_module, parse, and
   grammar_health each: call with `project_name` that resolves to itself
   (no typo) -> assert `session_state.project_name` set; second bare call
   (no `project_name`) must not raise `project_name_required`.
2. Empty `flextools_start` -> explicit-project run_module call -> bare
   call: end-to-end proof of the (c) mechanism + #168 together.
3. `project_not_open` hint mentions `flextools_start` before any per-op
   phrasing (ordering assert); `project_name_required` hint now mentions
   `flextools_start` (new requirement -- current text omits it).
4. `cold_adopt_consumed` fires once: repeated bare run_module calls
   post-empty-start must not re-trigger `record_auto_init()` WARNING
   spam.

## Regression risks

- Exact-match persistence (#168) makes `configure()`'s new-session
  detection (session.py:249-255) trigger a discovery-state wipe on the
  FIRST successful adopt in cases that previously silently skipped
  persisting -- intended, but worth a QA pass.
- `cold_adopt_consumed` must not leak across a genuine project switch
  within one process lifetime; harmless in practice since once
  `project_name` is non-empty the run_module branch is dead code anyway.
- Confirmed zero touch to `configure()`, `same_project`/write_enabled
  inheritance (admin.py:521-529), and READ_ONLY_SAFE/#47 auto-discovery
  logic.
