"""
The parse backend seam (`_ParseBackend`) and the stub backend the queue,
interleave and cancellation machinery are proven against.

Worker-process only: imported by `worker_main.py` (the parse worker) and the
filing worker, never by the MCP server process -- see `worker_main.py`'s
header for why.
"""

from __future__ import annotations

import time
from typing import Any, Optional



# ---------------------------------------------------------------------------
# The parse backend seam
# ---------------------------------------------------------------------------


class _ParseBackend:
    """What the worker needs from a parser, and nothing more.

    Two implementations: `_StubBackend` and `_RealBackend`. Keeping the
    surface this small is what makes the stub an honest stand-in rather
    than a simplification that hides the parts that will actually be hard.
    """

    def is_open(self) -> bool:
        """Does this backend currently hold a project open (#223)?

        Default True: a backend with no project-open concept (the stub) is
        always ready. `_RealBackend` is the only implementation that can
        answer False, once `release()` has dropped the project between
        requests.
        """
        return True

    #: True for `_SandboxBackend`: no project, so the project-bound messages
    #: are refused (D1) and every run is sent its load baseline.
    SANDBOX = False

    def open(self) -> None:
        """(Re)open whatever `is_open()` reports as closed. Default no-op.

        Called by `ParseWorker._ensure_project_open()` before any request
        touches the backend, so a `release()` taken while idle (#223) is
        reversed on demand rather than left for the worker's whole
        remaining life.
        """
        return None

    def preflight(self) -> None:
        """The engine gate. Called FIRST, before anything else per request.

        Separate from `ensure_grammar` precisely so it cannot drift into
        being second: FR-015 wants nothing in the parser area touched
        before the active engine has been checked, and a gate folded into
        the grammar load would run after the load on any path that reuses
        a held grammar.
        """
        return None

    def ensure_grammar(self, run_id: str) -> bool:
        """Make a current grammar available. True if a load was performed.

        The return value is what lets the caller report `loading_grammar`
        only when a load really happened -- reporting it on every word
        would make the stage meaningless, and reporting it never would hide
        the step that most often exhausts memory (FR-034).
        """
        raise NotImplementedError

    def parse(
        self,
        wordform: str,
        level: str,
        restricted_to: Optional[tuple[int, ...]],
        *,
        vernacular_ws: Optional[str] = None,
    ) -> dict[str, Any]:
        """Parse one word. Returns `{"parse": ..., "trace_xml": ...}`."""
        raise NotImplementedError

    def lexicon_rows(self) -> list:
        """Every entry, as plain rows the resolver can index (FR-018).

        Plain data, never LCM objects: `LexiconIndex` must hold no reference
        into a cache, and the rows cross no process boundary carrying one.
        """
        raise NotImplementedError

    def active_engine(self) -> Optional[str]:
        """The project's active parser, READ -- not gated (CP3, FR-024).

        The gate (`preflight`) refuses; this only reports. A batch runs the
        gate once, at submission, and from then on its words observe the
        engine through this read so a mid-job change becomes a warning on the
        run rather than a refusal of the words still queued.
        """
        return None

    def resolve_scope(self, scope: dict[str, Any]) -> dict[str, Any]:
        """Resolve a `ParseScope` dump to a `ResolvedScope` dump (US1).

        Raises `scope.ScopeRefusal` (carrying its `detail`) for the two
        scope refusals, which `_report_exception` marshals unchanged.
        """
        raise NotImplementedError

    def project_state(self) -> Optional[dict[str, Any]]:
        """`ProjectParseState.to_dict()` from the one probe, or None."""
        return None

    def parser_parameters(self) -> Optional[dict[str, Any]]:
        """The stored parser parameters, summarised, or None (FR-055).

        A READ. The measurement reports them as context for a slow parse;
        nothing on any CP3 path writes them.
        """
        return None

    def load_error_baseline(self, load_started: float) -> Optional[dict[str, Any]]:
        """The grammar load errors of a load that began at `load_started`.

        Called after the parse that paid for a grammar load. Returns None
        when this backend cannot establish them; the baseline then records
        that it was not captured, rather than recording zero errors (FR-023).
        """
        return None

    # -- CP4: the filing preflight's reads (answered, never gated) ---------

    def agent_facts(self) -> dict[str, Any]:
        """Is the HermitCrab parser agent resolvable? (CP4 FR-025)."""
        raise NotImplementedError

    def filing_preview(self, words: list, vernacular_ws: Optional[str]) -> dict[str, Any]:
        """Stored-analysis facts for the deletion projection (CP4, R-02)."""
        raise NotImplementedError

    def gate_probe(
        self, probe_word: Optional[str], vernacular_ws: Optional[str]
    ) -> tuple[Optional[float], bool]:
        """Make the grammar current and ask whether the parser can be built.

        Returns `(load_started, morpher_null)`: the wall-clock time a grammar
        load began if this call paid for one (None when the held grammar was
        current), and whether a probe parse came back null -- which is what
        `HCParser.ParseWord` returns when the morpher could not be built
        (FR-020).
        """
        raise NotImplementedError

    def eligible_entries(self) -> dict[str, Any]:
        """The entries whose forms can reach the grammar (CP4 FR-039, D-1).

        `{"known": bool, "entries": [{"entry_guid", "headword"}]}`. `known`
        False means the eligibility half has no answer, never "no entries".
        """
        return {"known": False, "entries": []}

    def release(self) -> None:
        """Drop the held grammar and any project handle."""
        raise NotImplementedError


class _StubBackend(_ParseBackend):
    """A parse backend that cannot fail for parser reasons.

    Exists so the queue, the interleave, the cancellation boundary and the
    run record are provable on their own (plan.md Phase C). Its results are
    deterministic functions of the wordform, so a test can assert *which*
    word produced a line without a live project.

    It models the two timing facts the machinery actually depends on: the
    first word pays a grammar load and later words do not, and a parse
    takes non-zero time so a boundary exists to interleave at.
    """

    #: The stub's corpus for `resolve_scope(all_texts)`. Fixed, so a test can
    #: assert the resolved order: descending occurrence, then alphabetical.
    STUB_CORPUS: dict[str, int] = {"pukul": 3, "kirim": 3, "kosong": 1, "memukul": 2}

    def __init__(self, *, parse_seconds: float = 0.0) -> None:
        self._loaded = False
        self._parse_seconds = parse_seconds
        #: Counts every load. A test asserts this is exactly 1 across a
        #: batch and an interleaving urgent word (SC-009).
        self.load_count = 0
        #: What `active_engine()` reports. A test flips it mid-batch to
        #: exercise FR-024's warning-not-refusal path.
        self.engine = "HC"
        #: Per-word overrides for the batch level: word -> list of analysis
        #: dicts, and word -> list of human-analysis dicts. Absent words get
        #: the deterministic default below.
        self.analyses_by_word: dict[str, list] = {}
        self.human_by_word: dict[str, list] = {}
        #: #223: modeled "project open" state, so a test can assert the
        #: worker released it as soon as it went idle and reopened it for a
        #: later request. True at construction -- `main()` never calls
        #: `open()` for the stub branch, so it starts ready like the real
        #: backend does after its own startup `open()`.
        self._project_open = True
        self.open_count = 0
        self.release_count = 0

    def is_open(self) -> bool:
        return self._project_open

    def open(self) -> None:
        self._project_open = True
        self.open_count += 1

    def ensure_grammar(self, run_id: str) -> bool:
        if self._loaded:
            return False
        self._loaded = True
        self.load_count += 1
        return True

    def parse(
        self,
        wordform: str,
        level: str,
        restricted_to: Optional[tuple[int, ...]],
        *,
        vernacular_ws: Optional[str] = None,
    ) -> dict[str, Any]:
        if self._parse_seconds:
            time.sleep(self._parse_seconds)

        if level == "restricted" and not restricted_to:
            # The stub refuses exactly where the real backend refuses. It is
            # the offline oracle the queue, interleave and cancellation
            # tests assert against, so a stub that quietly accepted an empty
            # restriction would report the widening FR-019 forbids as a
            # clean unrestricted parse -- and those tests would go green
            # over the one failure they exist to catch.
            raise ValueError(
                "An empty restriction reached the parser. This is a refusal "
                "(parse_morph_unresolved), never a widening to an "
                "unrestricted parse (FR-019)."
            )

        if level == "batch":
            return {"parse": self._batch_parse(wordform), "trace_xml": None}

        analyses = [
            {
                "morphs": [wordform],
                # `is not None`, not a truthiness test: None means "no
                # restriction" and an empty sequence means "admit nothing".
                # Collapsing them here would make the echo lie about which
                # one the caller sent.
                "restricted_to": (
                    list(restricted_to) if restricted_to is not None else None
                ),
            }
        ]
        trace_xml = None
        if level in ("restricted", "explain"):
            trace_xml = (
                f"<trace stub='1' word='{wordform}' level='{level}'></trace>"
            )
        return {
            "parse": {"word": wordform, "analyses": analyses, "stub": True},
            "trace_xml": trace_xml,
        }

    def lexicon_rows(self) -> list:
        """A tiny fixed lexicon, shaped to exercise all three outcomes.

        `pukul` resolves; `kirim` is ambiguous between two entries; `kosong`
        exists and carries no analysis. Without the last two the stub would
        make `ambiguous` and `no_msa` unreachable, and a stub that can only
        produce success is the one that lets a collapse of the three
        outcomes pass unnoticed.
        """
        return [
            {"headword": "pukul", "entry_hvo": 101,
             "senses": ["hit"], "msa_hvos": [5001]},
            {"headword": "kirim", "entry_hvo": 102,
             "senses": ["send"], "msa_hvos": [5002]},
            {"headword": "kirim", "entry_hvo": 103,
             "senses": ["deliver"], "msa_hvos": [5003]},
            {"headword": "kosong", "entry_hvo": 104,
             "senses": ["empty"], "msa_hvos": []},
        ]

    def _batch_parse(self, wordform: str) -> dict[str, Any]:
        """A batch-level result, shaped exactly like `_RealBackend`'s.

        Default: one analysis per word whose signature is derived from the
        word, so two runs over the same words compare `unchanged` and a test
        that overrides one word's analyses sees exactly that word move.
        """
        if wordform in self.analyses_by_word:
            analyses = list(self.analyses_by_word[wordform])
        else:
            analyses = [
                {
                    "signature": [[f"stub-form:{wordform}", f"stub-msa:{wordform}", None]],
                    "rendered_morphs": [wordform],
                    "category_labels": ["stub"],
                    "has_guessed_form": False,
                }
            ]
        return {
            "parsed": len(analyses) > 0,
            "analysis_count": len(analyses),
            "analyses": analyses,
            "human_analyses": list(self.human_by_word.get(wordform, [])),
            "error_message": None,
            "parse_time_ms": 0,
        }

    def active_engine(self) -> Optional[str]:
        return self.engine

    def resolve_scope(self, scope: dict[str, Any]) -> dict[str, Any]:
        """`words` and `all_texts` only; the stub has no genres or texts.

        Goes through the real ordering helper so the stub cannot disagree
        with production about order-then-truncate (FR-009).
        """
        from .scope import ScopeRefusal, _order_and_limit, _nfc

        kind = scope.get("kind")
        limit = scope.get("limit")
        if kind == "words":
            counts: dict[str, int] = {}
            for word in scope.get("value") or []:
                form = _nfc(word)
                if form:
                    counts[form] = counts.get(form, 0) + 1
            value = sorted(counts)
            text_ids: list[int] = []
        elif kind == "all_texts":
            counts = dict(self.STUB_CORPUS)
            value = None
            text_ids = [1]
        else:
            raise ScopeRefusal(
                {
                    "error_code": "parse_scope_empty",
                    "scope": dict(scope),
                    "matched_texts": [],
                    "hint": (
                        "The stub backend holds no genres or named texts; use "
                        "kind='words' or kind='all_texts'."
                    ),
                }
            )
        words, total, truncated = _order_and_limit(counts, limit)
        return {
            "scope_kind": kind,
            "scope_value": value,
            "text_ids": text_ids,
            "words": words,
            "count_before_limit": total,
            "limit": limit,
            "truncated": truncated,
            "vernacular_ws": scope.get("vernacular_ws") or "stub-vern",
            "never_tokenized_text_ids": [],
            "unreadable_wordform_count": 0,
            "notes": [],
        }

    def load_error_baseline(self, load_started: float) -> Optional[dict[str, Any]]:
        return {"captured": True, "source": "stub", "errors": list(self.stub_load_errors)}

    #: CP4: what the stub reports to the filing preflight. Tests replace them.
    stub_load_errors: list = []
    stub_morpher_null: bool = False
    stub_agent: dict[str, Any] = {
        "state": "present", "agent_guid": "kguidAgentHermitCrabParser",
        "agent_name": "HermitCrab", "active_engine": "HC",
        "probe_source": None, "hint": None,
    }
    stub_eligible: list = [
        {"entry_guid": "stub-entry-pukul", "headword": "pukul"},
        {"entry_guid": "stub-entry-kirim", "headword": "kirim"},
    ]
    #: word -> stored-analysis facts, shaped as `preflight_reads.stored_analyses`
    #: shapes them, plus `stub_in_segment`. A word absent here has no wordform.
    stub_stored: dict[str, list] = {}

    def agent_facts(self) -> dict[str, Any]:
        return dict(self.stub_agent)

    def filing_preview(self, words: list, vernacular_ws: Optional[str]) -> dict[str, Any]:
        from ..signals.oracle import SegmentOccurrence
        from ..filing.projection import attach_segment_use

        stored = {w: (list(self.stub_stored[w]) if w in self.stub_stored else None) for w in words}
        in_use = {r["analysis_guid"] for rs in self.stub_stored.values() for r in rs
                  if r.get("stub_in_segment")}
        return {"words": attach_segment_use(stored, SegmentOccurrence(in_use)), "join_known": True}

    def gate_probe(
        self, probe_word: Optional[str], vernacular_ws: Optional[str]
    ) -> tuple[Optional[float], bool]:
        started = time.time()
        loaded = self.ensure_grammar("filing-gate")
        return (started if loaded else None), bool(self.stub_morpher_null)

    def eligible_entries(self) -> dict[str, Any]:
        return {"known": True, "entries": [dict(e) for e in self.stub_eligible]}

    #: What `project_state()` reports; a test may replace it.
    stub_project_state: dict[str, Any] = {
        "parser_has_ever_run": True, "analyses_total": 0, "parser_created_analyses": 1,
        "human_opinion_analyses": 0, "indeterminate_analyses": 0, "truncated": False,
    }

    def project_state(self) -> Optional[dict[str, Any]]:
        return dict(self.stub_project_state)

    #: What `parser_parameters()` summarises: a minimal stored-parameters
    #: document, run through the same summariser the real backend uses.
    STUB_PARSER_PARAMETERS = (
        "<ParserParameters><ActiveParser>HC</ActiveParser>"
        "<HC><GuessRoots>false</GuessRoots><MaxCompoundRules>4</MaxCompoundRules></HC>"
        "</ParserParameters>"
    )

    def parser_parameters(self) -> Optional[dict[str, Any]]:
        from .measure import summarize_parser_parameters

        return summarize_parser_parameters(self.STUB_PARSER_PARAMETERS)

    def release(self) -> None:
        self._loaded = False
        self._project_open = False
        self.release_count += 1
