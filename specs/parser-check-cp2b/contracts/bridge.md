# Contract: CP2a-bridge -- the dependency floor and the bundled index

FR-011's repository-side half. Small, and the one place in CP2 where a silent
mismatch has already shipped once before.

**Entry condition: none beyond CP2a's evidence gate**, which is satisfied.
**Exit condition: CP2b's first parser task may not start until this has landed.**

---

## The failure this exists to prevent

The 2.10.0 incident: an index built at flexicon `4.5.2` shipped against a
`>=4.3.0` floor, which resolved to `4.4.1` in practice. The server served API
documentation for a version the user did not have. Nothing failed loudly; the
symptom was wrong answers about which methods exist.

The shape is **a version asserted in one file and produced in another, with nothing
comparing them.** A control, not a promise, is what closes it.

---

## Three facts that must agree

| # | Fact | Where it lives |
|---|---|---|
| 1 | the declared floor | `pyproject.toml` (`[project].dependencies`) and `requirements.txt` -- these mirror each other, and both say `pyflexicon>=4.9.0,<5` |
| 2 | the version the server resolves at runtime | `server/versioning.py`, live-module attribute first (`flexicon.version`), `importlib.metadata` only as fallback |
| 3 | the version suffix of every bundled flexicon-locked index artifact | `src/flextoolsmcp/index/` |

The standing test asserts **1 == 2 == 3**, by these three sources, and fails naming
which one disagrees.

### Why `importlib.metadata` is deliberately not one of the three

In this verification environment `pip show pyflexicon` reads `4.8.0` while the code
on `sys.path` is the `4.9.0` working tree. Comparing against distribution metadata
would make the test red on a correct tree. A test that is red for the wrong reason on
the maintainer's own machine gets muted, and a muted test is worse than an absent one.

Fact 2 is the right comparand because it is *the version the server actually uses to
choose an index file* -- which is precisely what went wrong at 2.10.0.

---

## The artifacts

Produced by one command:

```
python -m flextoolsmcp.refresh
```

There is no per-library flag; the refresh always scans every available API in one
pass, because the reverse mapping and pattern extraction cross-reference the
libraries and scanning one in isolation leaves the others stale.

| Artifact | Path | Named by the parent spec? |
|---|---|---|
| `flexicon_api_v4.9.0.json` | `src/flextoolsmcp/index/python/` | yes |
| `flexicon_lcm_bridge_v4.9.0.json` | `src/flextoolsmcp/index/python/` | yes |
| `common_patterns_flexicon-v4.9.0.json` | `src/flextoolsmcp/index/` | **no -- see below** |

### The third artifact

`common_patterns_flexicon-v<version>.json` is keyed to the flexicon version
(`extract_patterns.py:416-419`), lives one directory **above** the path the Verbatim
Constraints quote, and is produced by the same refresh (`refresh.py:584`). It is what
`curated_recipes.py` documents as the versioned file the server serves recipes from.

The Verbatim Constraints say the index under `index/python/` "currently comprises"
the first two. That is a statement about that directory, not a closed list of every
flexicon-version-locked file in the repository.

**Therefore the equality test asserts over the set of flexicon-version-locked
artifacts discovered by pattern, never over a hardcoded pair.** A hardcoded pair is
the same defect shape the test exists to prevent: it passes while a third file sits
at the old version.

### LibLCM is not in scope for this bridge

`refresh.py` regenerates LibLCM best-effort and skips it gracefully when FieldWorks
DLLs or pythonnet are unavailable, keeping the existing index. The bridge asserts
nothing about LibLCM's version and must not let a LibLCM skip fail it.

---

## What this bridge proves, and what it does not

**Proves.** Floor, runtime-resolved version and every bundled artifact name `4.9.0`.

**Does not prove.** That the published `pyflexicon 4.9.0` distribution installs and
satisfies the floor -- because it is not installed in this environment and will not
be within this session. `flexicon` here resolves to the working tree.

That is a separate check with its own task and its own evidence line:

```
# in a clean environment
pip install "pyflexicon>=4.9.0,<5"
python -c "import flexicon; print(flexicon.version)"     # expect 4.9.0
python -m pytest -q
```

It is scheduled separately rather than folded into the equality test, because a test
that cannot run here would either be skipped -- and a skip reported as a pass is the
failure Constitution Principle IV names -- or would force the equality test to depend
on an install this session cannot perform.

---

## Ordering

```
1. regenerate the index artifacts        (python -m flextoolsmcp.refresh)
2. raise the floor in both files         (pyproject.toml, requirements.txt)
3. add the equality test                 (fails before 1 and 2, passes after)
4. run the full suite                    (the floor change touches dependency tests)
5. the clean-environment install check   (separate evidence, may lag)
```

Step 3 must be **observed failing** against the pre-bridge tree before it is
accepted. A test that has never been red has not been shown to detect anything --
the same discipline CP2a applied when each of its AST detectors carried a self-test
that plants a known violation.
