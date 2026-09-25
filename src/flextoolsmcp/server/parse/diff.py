#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comparing two runs: did my grammar edit help? (parser-check CP3, US4;
FR-012, FR-030..FR-034; data-model.md section 7.)

BUCKETS ARE EXACTLY `fixed | broken | changed | unchanged` (FR-030), and
every word is classified on its SIGNATURE SET (`signature.compare_word`),
never on its analysis count. A word identity change (FR-032) is reported
beside the buckets, in `identity_changes`, because it is neither a change in
how the word parses nor "unchanged".

COMPARABILITY FIRST (FR-012). Two runs whose fingerprints differ refuse with
`parse_scope_mismatch` naming the differing fields, unless forced; a forced
comparison covers the INTERSECTION of the two word lists only and says so.
The fingerprint says nothing about the grammar (D-3), so a grammar edit
between the runs -- the thing being measured -- never causes a refusal.

SHARED MODE (FR-034). If FieldWorks has the project open, an edit the user
just made may not be on disk yet, and the second run may have parsed the
grammar as it was before the edit. The comparison cannot tell. So when
`project_access.probe_project_access` reports `open_shared` or
`open_exclusive`, the result carries `staleness: "shared_mode_unverifiable"`,
the save-or-close note, and a `no_change` verdict is downgraded to
`no_change_unverifiable`. NO SAFE READ-BACK INTERVAL IS PROMISED: FieldWorks
writes on its own schedule and there is no interval after which the file is
known to be current.

SANDBOX RUNS (parser-check CP5; FR-032, FR-039, FR-040; research R-13,
R-14). The diff accepts runs from either spine (`RunMeta.effective_spine`):

  * Any pair with a sandbox side carries a `comparison` block --
    {same_spine, same_config_source, same_engine_version, note} -- whose note
    is built from fixed sentences whenever any of the three is not true. An
    in-process pair has no block, so CP3's result is unchanged.
  * A cross-spine pair is compared by morph FORMS only, a sandbox pair by
    (form, gloss) (`signature.spine_pair_mode`); the note says so.
  * A sandbox run records `vernacular_ws: ""` in its fingerprint, because
    the writing system is not known without opening the project. Against an
    in-process run that one field is not compared, and the note says so.
    Between two in-process runs nothing is loosened.
  * `no_change` is also downgraded when EITHER run's recorded
    `project_state.staleness` is `shared_mode_unverifiable` (R-13). The live
    rule above, `shared_mode_active`, is left exactly as CP3 shipped it.
  * A corpus-test line (one carrying `assertion`) in the CURRENT run is
    bucketed through `sandbox.classify.CLASSIFICATION_BUCKETS`: regression
    is broken, new_ambiguity and changed are changed (never unchanged),
    pass is unchanged, error is not compared. A corpus line in the BASELINE
    run lists only hc's unmatched parses, so it is never compared.

READ-ONLY, AND IT NEVER TOUCHES THE ENGINE (FR-024). Everything here reads
two run directories. The access probe reads a lock file's metadata; it opens
no project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from dataclasses import replace

from ..sandbox.classify import CLASS_ERROR, CLASSIFICATION_BUCKETS
from .fingerprint import (
    ScopeFingerprint,
    check_comparable,
    restrict_to_intersection,
)
from .record import SPINE_IN_PROCESS, SPINE_SANDBOX, RunMeta, RunRecord
from .signature import (
    FALLBACK_AMBIGUITY_NOTE,
    IDENTITY_CHANGE_NOTE,
    PROVISIONAL_NOTE,
    SignatureMode,
    compare_word,
    signature_mode,
    signatures_of,
    spine_pair_mode,
)

__all__ = [
    "BUCKETS",
    "SHARED_MODE_STALENESS",
    "SHARED_MODE_NOTE",
    "RunNotComparable",
    "RunComparison",
    "compare_runs",
    "shared_mode_active",
    "CROSS_SPINE_NOTE",
    "CONFIG_SOURCE_NOTE",
    "ENGINE_VERSION_NOTE",
    "ENGINE_VERSION_UNKNOWN_NOTE",
    "VERNACULAR_WS_NOTE",
]

#: Verbatim from contracts/tools.md section 1.
BUCKETS = ("fixed", "broken", "changed", "unchanged")

#: Verbatim from contracts/tools.md section 1 (FR-034).
SHARED_MODE_STALENESS = "shared_mode_unverifiable"
NO_CHANGE = "no_change"
NO_CHANGE_UNVERIFIABLE = "no_change_unverifiable"

#: The access verdicts that mean FieldWorks may hold unsaved edits.
_SHARED_VERDICTS = ("open_shared", "open_exclusive")

#: The save-or-close note (FR-034). Deliberately promises no interval.
SHARED_MODE_NOTE = (
    "FieldWorks has this project open, so a grammar edit you just made may not "
    "have been written to disk yet, and the later run may have parsed the "
    "grammar as it was before the edit. This comparison cannot tell the "
    "difference. Save your work in FieldWorks, or close the project there, and "
    "then parse again to get a comparison that reflects the edit."
)


#: CP5 comparison-block sentences (FR-039, R-14). Fixed text only.
CROSS_SPINE_NOTE = (
    "These runs come from different spines: one was parsed in-process by "
    "FieldWorks' own HermitCrab, the other by the stand-alone hc tool against "
    "a configuration generated from a copy of the project. They were "
    "compared by morph forms only; glosses and HVO-level identity are not "
    "compared across spines."
)
CONFIG_SOURCE_NOTE = (
    "These runs parsed against different HermitCrab configurations, so a "
    "difference may come from the configuration rather than from a grammar "
    "edit."
)
ENGINE_VERSION_NOTE = (
    "These runs used different HermitCrab engine versions, so a difference "
    "may come from the engine rather than from the grammar."
)
ENGINE_VERSION_UNKNOWN_NOTE = (
    "Whether both runs used the same HermitCrab engine version is not known."
)
VERNACULAR_WS_NOTE = (
    "The sandbox run does not record the vernacular writing system, because "
    "it never opens the project, so that part of the two runs' scope was not "
    "compared."
)

#: Why a word is not compared when a corpus line is involved (T074).
_BASELINE_ASSERTION_REASON = (
    "the baseline run is a corpus test: its line lists only the parses hc "
    "could not match, not the word's analyses"
)


class RunNotComparable(Exception):
    """A run cannot be compared at all (not a batch, or no fingerprint)."""


@dataclass
class RunComparison:
    """The comparison, ready to render (data-model.md section 7)."""

    baseline_run_id: str
    current_run_id: str
    mode: str
    buckets: Dict[str, List[Dict[str, Any]]]
    identity_changes: List[Dict[str, Any]]
    not_compared: List[Dict[str, Any]]
    verdict: str
    notes: List[str] = field(default_factory=list)
    forced: bool = False
    differing_fields: List[str] = field(default_factory=list)
    staleness: Optional[str] = None
    provisional_words: int = 0
    #: CP5: None for an in-process pair; the comparison block otherwise.
    comparison: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        counts = {name: len(self.buckets[name]) for name in BUCKETS}
        data: Dict[str, Any] = {
            "baseline_run_id": self.baseline_run_id,
            "current_run_id": self.current_run_id,
            "verdict": self.verdict,
            "comparison_mode": self.mode,
            "counts": counts,
            "buckets": {name: self.buckets[name] for name in BUCKETS},
            "identity_changes": self.identity_changes,
            "identity_change_count": len(self.identity_changes),
            "not_compared": self.not_compared,
            "provisional_words": self.provisional_words,
            "notes": self.notes,
        }
        if self.forced:
            data["forced"] = True
            data["differing_fields"] = self.differing_fields
        if self.staleness is not None:
            data["staleness"] = self.staleness
        if self.comparison is not None:
            data["comparison"] = self.comparison
        return data


def shared_mode_active(access: Any) -> bool:
    """True when the access probe says FieldWorks has the project open."""
    return getattr(access, "verdict", None) in _SHARED_VERDICTS


#: `RunRecord.read_meta` returns None on ANY OSError, and on Windows a
#: freshly replaced meta.json can be briefly unreadable (a scanner or indexer
#: holding it: a sharing violation). A missing read must never be mistaken
#: for "this run has no spine" -- that once made a sandbox run look
#: in-process while its fingerprint still loaded, so its empty
#: `vernacular_ws` refused the comparison under load only.
_META_READ_ATTEMPTS = 4
_META_RETRY_DELAY_SECONDS = 0.05


def _meta(record: RunRecord) -> Optional[RunMeta]:
    """The run's meta, read once for the whole comparison.

    Retries briefly when meta.json exists but could not be read, and raises
    `RunNotComparable` if it still cannot be: the spine, the fingerprint and
    the recorded staleness all come from this ONE read, so they can never
    disagree about the run.
    """
    import time

    for attempt in range(_META_READ_ATTEMPTS):
        meta = record.read_meta()
        if meta is not None or not record.meta_path.is_file():
            return meta
        if attempt + 1 < _META_READ_ATTEMPTS:
            time.sleep(_META_RETRY_DELAY_SECONDS)
    raise RunNotComparable(
        f"Run {record.run_id}'s record (meta.json) exists but could not be read, "
        f"so its scope and spine are unknown. Retry the comparison."
    )


def _fingerprint(record: RunRecord, meta: Optional[RunMeta]) -> ScopeFingerprint:
    if meta is None or not meta.scope_fingerprint:
        raise RunNotComparable(
            f"Run {record.run_id} has no scope fingerprint -- it is not a batch "
            f"run, so there is no scope to compare it on. Compare two runs made "
            f"with flextools_parse_text."
        )
    return ScopeFingerprint.from_dict(meta.scope_fingerprint)


def _lines_by_word(record: RunRecord) -> Dict[str, Dict[str, Any]]:
    """Result lines keyed by wordform. A word seen twice keeps its last line."""
    lines: Dict[str, Dict[str, Any]] = {}
    for line in record.iter_results():
        word = line.get("wordform")
        if isinstance(word, str):
            lines[word] = line
    return lines


def _word_order(record: RunRecord, lines: Dict[str, Dict[str, Any]]) -> List[str]:
    words = record.read_words()
    return words if words is not None else list(lines)


def _spine(meta: Optional[RunMeta]) -> str:
    return meta.effective_spine if meta is not None else SPINE_IN_PROCESS


def _sandbox(meta: Optional[RunMeta]) -> Dict[str, Any]:
    return (meta.sandbox or {}) if meta is not None else {}


def _recorded_staleness(meta: Optional[RunMeta]) -> Optional[str]:
    state = (meta.project_state or {}) if meta is not None else {}
    return state.get("staleness") if isinstance(state, dict) else None


def _tolerate_sandbox_ws(
    before: ScopeFingerprint,
    after: ScopeFingerprint,
    before_spine: str,
    after_spine: str,
) -> tuple:
    """Cross-spine only: a sandbox side's empty vernacular_ws takes the other's.

    Returns (before, after, tolerated). Two in-process runs, or two sandbox
    runs, are returned untouched.
    """
    if before_spine == after_spine:
        return before, after, False
    if before_spine == SPINE_SANDBOX and before.vernacular_ws == "" and after.vernacular_ws:
        return replace(before, vernacular_ws=after.vernacular_ws), after, True
    if after_spine == SPINE_SANDBOX and after.vernacular_ws == "" and before.vernacular_ws:
        return before, replace(after, vernacular_ws=before.vernacular_ws), True
    return before, after, False


def _engine_version(meta: Optional[RunMeta]) -> Optional[str]:
    """The HermitCrab version a sandbox run parsed with.

    CP5 re-plan: the worker reports the bundled engine's `FileVersion` per
    run (`engine_version`, else `versions.fieldworks_hermitcrab`). A record
    from the retired `hc` CLI era carries `versions.hc_tool` instead.
    """
    sandbox = _sandbox(meta)
    versions = sandbox.get("versions") or {}
    versions = versions if isinstance(versions, dict) else {}
    if versions.get("hc_tool"):
        return versions["hc_tool"]
    return sandbox.get("engine_version") or versions.get("fieldworks_hermitcrab")


def _ran_bundled_engine(meta: Optional[RunMeta]) -> bool:
    """A sandbox run on FieldWorks' own HermitCrab (the in-process worker
    design), rather than on a separately installed `hc` tool."""
    versions = _sandbox(meta).get("versions") or {}
    return not (isinstance(versions, dict) and versions.get("hc_tool"))


def _comparison_block(
    before: Optional[RunMeta],
    after: Optional[RunMeta],
    ws_tolerated: bool,
) -> Optional[Dict[str, Any]]:
    """The FR-039 block, or None for an in-process pair (CP3 unchanged)."""
    before_spine, after_spine = _spine(before), _spine(after)
    if before_spine == SPINE_IN_PROCESS and after_spine == SPINE_IN_PROCESS:
        return None
    same_spine = before_spine == after_spine
    if same_spine:
        before_source = _sandbox(before).get("config_source")
        after_source = _sandbox(after).get("config_source")
        same_config_source = before_source is not None and before_source == after_source
        before_version, after_version = _engine_version(before), _engine_version(after)
        if before_version and after_version:
            same_engine_version: Optional[bool] = before_version == after_version
        else:
            same_engine_version = None
    else:
        # In-process reads the live project; the sandbox reads a generated
        # configuration. Since the CP5 re-plan the sandbox runs FieldWorks'
        # own bundled HermitCrab, the engine the in-process spine uses, so a
        # sandbox run that recorded that engine's version is the same engine.
        # An `hc`-era record keeps its recorded skew as the only evidence.
        same_config_source = False
        sandbox_meta = before if before_spine == SPINE_SANDBOX else after
        if _ran_bundled_engine(sandbox_meta):
            same_engine_version = True if _engine_version(sandbox_meta) else None
        else:
            skew = _sandbox(sandbox_meta).get("version_skew")
            same_engine_version = (not skew) if isinstance(skew, bool) else None

    sentences = []
    if not same_spine:
        sentences.append(CROSS_SPINE_NOTE)
    if not same_config_source and same_spine:
        sentences.append(CONFIG_SOURCE_NOTE)
    if same_engine_version is False:
        sentences.append(ENGINE_VERSION_NOTE)
    elif same_engine_version is None:
        sentences.append(ENGINE_VERSION_UNKNOWN_NOTE)
    if ws_tolerated:
        sentences.append(VERNACULAR_WS_NOTE)
    return {
        "same_spine": same_spine,
        "same_config_source": same_config_source,
        "same_engine_version": same_engine_version,
        "note": " ".join(sentences) if sentences else None,
    }


def _assertion_entry(word: str, assertion: Dict[str, Any]) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "wordform": word,
        "classification": assertion.get("classification"),
    }
    if assertion.get("label") is not None:
        entry["label"] = assertion["label"]
    if assertion.get("missing"):
        entry["missing"] = assertion["missing"]
    if assertion.get("unexpected"):
        entry["unexpected"] = assertion["unexpected"]
    return entry


def compare_runs(
    baseline: RunRecord,
    current: RunRecord,
    *,
    force: bool = False,
    access: Any = None,
    mode: Optional[str] = None,
) -> RunComparison:
    """Compare `current` against `baseline`. Read-only; touches no engine.

    Raises:
        fingerprint.ScopeMismatch: the fingerprints differ and `force` is
            False (`parse_scope_mismatch`, FR-012).
        RunNotComparable: either run is not a batch run.
    """
    before_meta, after_meta = _meta(baseline), _meta(current)
    before_spine, after_spine = _spine(before_meta), _spine(after_meta)
    mode, key = spine_pair_mode(before_spine, after_spine, mode or signature_mode())
    before_fp, after_fp, ws_tolerated = _tolerate_sandbox_ws(
        _fingerprint(baseline, before_meta),
        _fingerprint(current, after_meta),
        before_spine,
        after_spine,
    )
    comparability = check_comparable(before_fp, after_fp, force=force)

    before_lines = _lines_by_word(baseline)
    after_lines = _lines_by_word(current)
    before_words = _word_order(baseline, before_lines)
    after_words = _word_order(current, after_lines)

    notes: List[str] = []
    if comparability.forced:
        words = restrict_to_intersection(before_words, after_words)
        notes.append(comparability.note)
    else:
        words = list(before_words)
        for word in after_words:
            if word not in before_lines and word not in words:
                words.append(word)

    buckets: Dict[str, List[Dict[str, Any]]] = {name: [] for name in BUCKETS}
    identity_changes: List[Dict[str, Any]] = []
    not_compared: List[Dict[str, Any]] = []
    provisional = 0

    for word in words:
        after_line = after_lines.get(word) or {}
        assertion = after_line.get("assertion")
        if isinstance(assertion, dict):
            # T074 (FR-032): a corpus assertion already compares the word with
            # its recorded expectation; its classification decides the bucket.
            classification = assertion.get("classification")
            if classification == CLASS_ERROR or classification not in CLASSIFICATION_BUCKETS:
                not_compared.append({
                    "wordform": word,
                    "reason": f"corpus assertion error: {assertion.get('error_reason')}",
                })
            else:
                buckets[CLASSIFICATION_BUCKETS[classification]].append(
                    _assertion_entry(word, assertion)
                )
            continue
        if isinstance((before_lines.get(word) or {}).get("assertion"), dict):
            not_compared.append({"wordform": word, "reason": _BASELINE_ASSERTION_REASON})
            continue
        before = signatures_of(before_lines.get(word))
        after = signatures_of(after_lines.get(word))
        if before is None or after is None:
            # A word one run never completed (killed, errored) is not a
            # regression and not a fix: nothing is known about it on that
            # side. Reported, never bucketed.
            missing = [
                name for name, sigs in (("baseline", before), ("current", after))
                if sigs is None
            ]
            not_compared.append({
                "wordform": word,
                "reason": f"no completed result in the {' and '.join(missing)} run",
            })
            continue
        outcome = compare_word(word, before, after, mode, key)
        if outcome.provisional:
            provisional += 1
        if outcome.identity_change:
            entry = outcome.to_dict()
            entry["note"] = IDENTITY_CHANGE_NOTE
            identity_changes.append(entry)
        else:
            buckets[outcome.bucket].append(outcome.to_dict())

    moved = any(buckets[name] for name in ("fixed", "broken", "changed")) or identity_changes
    verdict = "changes_found" if moved else NO_CHANGE

    staleness = None
    recorded = SHARED_MODE_STALENESS in (
        _recorded_staleness(before_meta),
        _recorded_staleness(after_meta),
    )
    if shared_mode_active(access) or recorded:
        staleness = SHARED_MODE_STALENESS
        notes.append(SHARED_MODE_NOTE)
        if verdict == NO_CHANGE:
            verdict = NO_CHANGE_UNVERIFIABLE

    # The fallback note speaks of category labels and lexical objects; a pair
    # with a sandbox side states its own basis in the comparison block.
    if mode == SignatureMode.RENDERED_FALLBACK and key is None:
        notes.append(FALLBACK_AMBIGUITY_NOTE)
    if provisional:
        notes.append(PROVISIONAL_NOTE)

    return RunComparison(
        baseline_run_id=baseline.run_id,
        current_run_id=current.run_id,
        mode=mode,
        buckets=buckets,
        identity_changes=identity_changes,
        not_compared=not_compared,
        verdict=verdict,
        notes=notes,
        forced=comparability.forced,
        differing_fields=list(comparability.differing_fields),
        staleness=staleness,
        provisional_words=provisional,
        comparison=_comparison_block(before_meta, after_meta, ws_tolerated),
    )
