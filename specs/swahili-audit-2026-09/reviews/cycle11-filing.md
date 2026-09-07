# Cycle 11 -- CP-E phantom-remedy issue filings

Target repo verified before filing: `MattGyverLee/FlexToolsMCP`
(`gh repo view --json nameWithOwner`).

## Issues filed (2)

**#112** -- https://github.com/MattGyverLee/FlexToolsMCP/issues/112
Phantom remedy: `CastingOperations.cast_to_concrete` advertised in 5
user-facing hints but does not exist in pyflexicon 4.5.2.
Contains: all five sites (`handlers/api.py:1621,1636`,
`handlers/discovery.py:163,168`, `validators.py:3642`), the correct
`flexicon.code.lcm_casting` remedy, the note that `validators.py:3927/3935`
already word it correctly, the weak-test flag at
`tests/test_issue48_inline_casting.py:92`, PRE-EXISTING marking, and the
same-failure-class link to #103.

**#113** -- https://github.com/MattGyverLee/FlexToolsMCP/issues/113
Shipped LibLCM template crashes: `cast_to_concrete` wrong arity +
non-exported `ILexEntry`.
Contains: runtime evidence (unary signature at `lcm_casting.py:408`;
`ILexEntry` function-local in `_ensure_interfaces()`), the served-to-users
path (`handlers/admin.py:102-104`), the full SEVERE / BENIGN /
ALREADY-CORRECT site split, the `user-logs/Dennis-Logs/` corroboration, and
PRE-EXISTING marking.

Both issues state that a fix is landing in the same cycle (another agent is
fixing them now) so a maintainer does not duplicate the work. Neither issue
claims to be fixed or closed.

## Scope confirmation

[OK] No existing issue was touched. Nothing was closed, commented on,
edited, labeled, or reopened -- specifically not #80, #97, #100, #101, #103,
#107, #111, nor flexicon#254/#261. Only two `gh issue create` calls were
made.

[OK] No source file edited; no commits pushed; no PRs opened. The only file
written in the repo is this report.
