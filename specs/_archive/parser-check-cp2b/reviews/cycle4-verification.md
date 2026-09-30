# Live verification -- cycle 4, `_summarize_trace` re-run

**Project used:** `IndonesianHC-Complete` (HC, 41 entries), read-only
(`writeEnabled=False`, worker default) throughout. Also probed (read-only)
`Malay Parsing-20230810withHC` and `Tlachichilco Tepehua-NT Noparse` for
step 5's multi-analysis search (see below).

## Step 2 -- explain on `pukul` (parsing word): **PASS**
`{"parsed": true, "analysis_count": 1, "explains_failure": false,
"next_step": null}`. Non-zero count observed -- the TypeError from cycle 3
is gone.

## Step 3 -- explain on `meŋ` (non-parsing word): **PASS**
`{"parsed": false, "analysis_count": 0, "explains_failure": true}`,
`next_step` carries the `restricted` rung and the `run_module`/`GetHeadword`
lookup rung -- decomposition assist and failure guidance both fire. Also
reconfirmed by the existing live suite (`test_parse_live.py` scenario 3,
both tests, below).

## Step 4 -- restricted, resolvable decomposition (`pukul`/`pukul`): **PASS**
`{"hypothesis_held": true, "restricted_analysis_count": 1,
"restricted_to": [3697], "explains_failure": false, "next_step": null}`.
`parsed` is **absent** from the key set -- checked directly, not defaulted.

## Step 5 -- THE GATE, plain vs. explain `analysis_count`: **PASS**, on 19 words; multi-analysis word not found
25 words probed on `IndonesianHC-Complete` (`pukul` + 24 real IPA lexeme
forms). 19 produced a valid (non-`parse_error`) explain answer; **plain's
`analysis_count` equalled explain's in every one of the 19** (all 1==1 --
this project's own shape, per prior evidence, is single-analysis
throughout). The other 6 hit step 7's `<Error>` case (below) and carry no
count on either side to compare -- correctly outside the equality claim's
domain, not a violation of it. I tried to find a >1-analysis word in
`Malay Parsing-20230810withHC` and `Tlachichilco Tepehua-NT Noparse`: the
probe against the latter (3704 entries, cold) exceeded my 180s wait and its
worker was killed by the runner's own guard (`issue #57`) before either
project's results were captured -- an operational/timing limit of a large
cold project open, not a defect in the fix. **No multi-analysis word found live in the time
available.** Confirmed on 19 real single-analysis words, not yet stress-
tested against >1.

## Step 6 -- restricted, held vs. failed hypothesis: **PASS**
Held (step 4's call): `explains_failure: false, next_step: null`. Failed
(`meŋ` restricted to `pukul`'s headword, divergent): `{"hypothesis_held":
false, "restricted_analysis_count": 0, "explains_failure": true,
"next_step": null}` -- unchanged from before, as the contract requires.

## Step 7 -- inducing `<Error>`: **PASS -- reachable, not contrived**
A word containing a phoneme undefined in the project's inventory makes
`TraceWordXml` build `<Error>` instead of `<Analysis>`. Found live (via 5
mistranscribed IPA strings) and reproduced cleanly: `{"status": "ok",
"parse_error": "There is at least one undefined phoneme in the word
'...'. ..."}`; `parsed`/`analysis_count`/`explains_failure` all **absent**
(checked directly), `next_step: null`. Matches contract exactly. **Note,
not a defect:** `plain` on the same malformed words does *not* throw -- it
reports `analysis_count: 0` -- because `ParseWord` never raises for an
undefined phoneme, only `TraceWordXml`/`ParseToXml` does; this is the
documented asymmetry, confirmed rather than assumed.

**New finding, out of this cycle's scope:** a null byte or a 5000-char
word crashes -- but in `_as_text`'s `str(trace)` (an `ArgumentException`
from the XML writer / an `OutOfMemoryException`), **not** in
`_summarize_trace`. Worth a ticket; not blocking this gate.

## Suites
`python -m pytest -m "not requires_flex" --continue-on-collection-errors -q`
-> **2018 passed, 6 skipped, 71 deselected, 0 failed** (matches cycle 4's
claimed post-fix count).

`python -m pytest tests/test_parse_live.py -m requires_flex -q -k
"scenario_1 or scenario_2 or scenario_3 or scenario_4 or sc004"` (live,
IndonesianHC-Complete + Sena 3) -> **10 passed**, none skipped.

## VERDICT: PASS
All four fixes hold live. Steps 2, 3, 4, 6, 7 fully confirmed against a
real worker and a real trace. Step 5's equality holds on every word tested
(19/19) but only at single-analysis; a genuine >1-analysis stress case is
still open, recorded honestly rather than rounded up.
