#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The filing package -- THE ONLY WRITE SPINE in the parser area (parser-check CP4,
FR-029, R-09).

`flextools_parse_text(apply=true)` files HermitCrab results into a project
through FieldWorks' own `ParseFiler`, the filer FLEx's Parse Words in Text menu
uses. That deletes analyses and cannot be undone, so where the write happens is
a structural fact, not a convention:

  * `server/parse/` and `server/signals/` never write. A standing test
    (`tests/test_parse_no_project_writes.py`) scans them, byte for byte as they
    were at CP3, for any writable open.
  * This package is the one place a project may be opened for writing, and
    inside it exactly one module does so -- `worker_filing.py`, the
    `FILING_ROLE` worker's entry point. The INVERSE test
    (`tests/test_filing_write_confinement.py`) fails if a writable open appears
    anywhere else in the source tree.

Modules:

  * `claims`       -- the in-process per-project filing claim (not a lock) and
                      its startup sweep (FR-026..FR-028, R-11);
  * `paths`        -- nothing filing writes lives inside a project folder
                      (FR-042); Send/Receive detection (FR-043, R-14);
  * `wording`      -- the fixed sentences the contract transcribes;
  * `projection`   -- the deletion upper bound on FR-011's two conjuncts (R-01);
  * `eligibility`  -- the port of HCLoader's two private form predicates (R-12);
  * `gate`         -- the refuse-to-file gate: baseline, load-error and
                      eligibility diffs (FR-020..FR-024, FR-039);
  * `plan`         -- the mutation plan and its `plan_id` (FR-006, FR-010, R-08);
  * `filer`        -- a per-word `ParseFiler` driven through a paused
                      `IdleQueue` (FR-018, FR-019, R-03);
  * `classify`     -- the per-word sequence: the would-delete guard, the
                      captures, the pump, the outcome (FR-014, FR-031, R-02);
  * `worker_filing` -- the `FILING_ROLE` worker process (R-05, R-09).

The filing worker imports read-only helpers from `parse/` (scope, the segment
join, the backend's readers), never the other way round -- with one
deliberate exception: the read worker computes the eligibility baseline every
batch records, through `eligibility`, which is pure and writes nothing.
"""
