# Contract: the CP2a evidence gate

CP2b may not start until this gate is satisfied. It is a contract rather
than a checklist because a different checkpoint, in a different repository,
consumes it as an entry condition.

**Authority**: Decision D4 in `spec.md` (the user's standing sequencing
constraint) and Constitution Principle IV (report the measurement, not the
impression).

---

## Why a green suite is not the gate

All four flexicon ratchets are structural -- stub parity, return-annotation
agreement, docstring examples, alias stability. **Every one of them would
have passed a reload bound to a bare update**, which is the defect cycle 1
actually found. A passing suite therefore cannot discharge the one claim
that matters most.

The gate is behavioural evidence, recorded as observations.

Two further reasons the measurement must be explicit here:

- **Nothing runs in CI.** No workflow invokes pytest on a hosted runner,
  and the self-hosted `[windows, fieldworks]` pool that the weekly
  compatibility workflow targets has zero registered runners. Every tier
  below is a local, manual measurement.
- **Bare `pytest` is prohibited.** It collects and executes the
  `requires_live_project` tests in-place against real projects. So is
  `pytest --ignore=tests/contract`, which applies no marker filter --
  Constitution Principle II calls it "a live-write command wearing the
  costume of a scoping flag".

---

## Required invocation

Quoted verbatim per Principle II, which requires every brief to carry it:

```
python -m pytest -m "not requires_live_project" -q
```

For tier A3 only, against the installed project:

```
$env:FLEXLIBS_REQUIRE_LIVE = "1"; python -m pytest tests/operations/test_parser_live.py -m requires_live_project -q
```

`FLEXLIBS_REQUIRE_LIVE=1` turns silent mock-degradation into a usage error,
so a run that quietly fell back to mocks cannot be mistaken for live
evidence. `tests/live_status.json` must show `"run_mode": "live"`.

---

## Tier A1 -- parser component absent, simulated

**Re-tiered from the cycle-1 brief** (D-A1): runs with FieldWorks
installed, simulating the parser component's absence. `import flexicon`
itself requires FieldWorks, so a genuinely FieldWorks-free run cannot
execute these checks.

| # | Observation required |
|---|---|
| A1.1 | With the parser component's resolution simulated as failing, import succeeds and the availability status reports unavailable **with a reason**, raising nothing (SC-001). |
| A1.2 | No code path compares a detected version against a minimum -- 0 occurrences (SC-002). |
| A1.3 | No module-scope parser import exists; loading is triggered by use only (FR-003), asserted by AST. |
| A1.4 | The public surface contains no method that records, files or writes a result (FR-002), asserted by enumeration. |
| A1.5 | Operations are bound positionally, not by parameter name (FR-005), asserted structurally. |
| A1.6 | FR-043's **stale** half against a stubbed change listener: a grammar reported stale produces a reload before any word is parsed. |

A1.1 has no template in the package -- flexicon raises or silently yields
`None`, with no third shape. Test it by simulating absence, never by
assuming it.

---

## Tier A2 -- FieldWorks installed, no project opened

No LCM cache, therefore no project, therefore no write risk of any kind.
This tier is Constitution Principle I's control: no design may assume a
member exists.

| # | Observation required |
|---|---|
| A2.1 | Every member the facade binds exists on the **real installed** parser component: construction from a cache, update, reset, currency read, plain parse, structured parse, trace. |
| A2.2 | **The reset and currency members specifically.** These are the two the shipped MCP-side check does not cover, and this is their first verification anywhere. |
| A2.3 | Same-installation directory equality holds on this machine (FR-004). |
| A2.4 | The detected version is reported, and unused. |

A2.2 is the direct remediation of cycle 1's domain finding. If it fails,
the facade cannot be built as designed and the plan returns to research --
which is the whole point of running this tier before the behaviour.

---

## Tier A3 -- live, read-only, one project open

**The tier that actually settles FR-043.** Target: `IndonesianHC-Complete`
(41 entries, 3 rules -- small enough that a cold grammar load stays fast),
opened with writing disabled. No write, no restore, **no human
authorisation required.**

Must be an *installed* project, never a `.fwbackup` sandbox: opening a
sandbox read-only triggers a modal liblcm dialog that freezes the suite.

| # | Observation required |
|---|---|
| A3.1 | The parser constructs against a real cache and a real update loads a grammar. |
| A3.2 | A word parses, and a trace returns. |
| A3.3 | **The unconditional-discard proof.** With no model change between calls: the plain update must **not** reload, and the reload **must**. Witness is the identity of the internal morpher across calls (D-A11); documented fallback is the rewrite of the `{ProjectName}HCLoadErrors.xml` side file. |
| A3.4 | FR-010's object-identity claim: plain-parse results carry live object references, not strings. |
| A3.5 | At most one grammar is held across a sequence spanning two projects; switching releases the previous one (SC-014). |
| A3.6 | The active parser is confirmed to be the expected engine on both live projects. |

**A3.3 is the gate within the gate. A reload that cannot be shown to
discard has not been proven, and CP2b does not start.**

---

## Tier A4 -- DEFERRED, not part of this gate

Proving FR-043's *stale* half **live** requires editing a project so the
model registers as changed. That is a live write, so Constitution Principle
II applies: it is deferred to CP2b, where the loop must stop with
`needs_human` and a person must authorise it against a backed-up or copied
project.

CP2a needs no write and no authorisation. A1.6 covers the stale branch
offline against a stub, which is what makes the deferral acceptable rather
than a hole.

---

## The recorded artifact

CP2a ends by writing:

```
specs/parser-check-cp2/evidence/cp2a-evidence.md
```

in the `FlexToolsMCP` repository -- the only file in this repository CP2a
touches. It records, per tier:

- the exact invocation that produced the result;
- full counts including failures, with pre-existing failures named as
  pre-existing and attributed, never rounded to "green" (Principle IV);
- for A3.3, the observed discard result and which witness produced it;
- for any tier not run, that it was not run, and why.

It is prose evidence, not a test count. Per D4, the next phase is
authorised by what was *observed* -- a future maintainer asking "how do we
know the reload discards?" must find an answer that is not "there is a test
named that".

---

## Gate status

| Condition | Required for CP2b entry |
|---|---|
| A1 complete and recorded | yes |
| A2 complete and recorded | yes |
| A3 complete and recorded, including A3.3 | yes |
| A4 | no -- deferred to CP2b with `needs_human` |
| `4.9.0` tag pushed | **no** -- the seam is at *proven*, not *released* |
| CP2a-bridge landed | yes, before CP2b's first parser task |

The tag and the gate are separate, on separate timelines. FR-011 was
amended in cycle 3 precisely because it had conflated them: the release's
existence and version alignment are a precondition for assistant-side work,
**not the gate that permits it**.
