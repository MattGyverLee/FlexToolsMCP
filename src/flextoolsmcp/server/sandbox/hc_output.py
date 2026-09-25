#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
The ONE parser of HermitCrab `hc`'s console format (parser-check CP5, T046;
research F-1, F-6, F-7, R-06, R-08; data-model 6.4; FR-016..FR-019, SC-004).

Nothing else in the codebase reads hc's output. The strings matched here are
the ones `SIL.Machine.Morphology.HermitCrab.Tool` prints (Program.cs banner
and load errors, ParseCommand.cs, StatsCommand.cs, Extensions.cs WriteParse,
MorphInfo.cs). hc writes UTF-16LE (F-1); `hcparse.ps1` decodes it and writes
`hc-stdout.txt` one hc line per line, so this module works on `str` lines.

Layers
------
* `BlockReader` / `iter_blocks` -- split a (possibly still growing) stream
  into blocks. A block starts at a `Parsing "<w>"`, `Testing "<w>"`,
  `# of parses:` or `# of tests:` line and ends at hc's blank terminator
  line. Only a terminated block is `complete`; the client tailing the file
  hands complete blocks to the runner live and keeps the open one in flight.
* `parse_block` -- one parse block to a `WordResult` (outcome, analyses,
  position). A block without its terminator is `error_no_output`, never
  `not_parsed` (FR-018).
* `read_columns` -- R-08's column recovery for one `Morphs:` / `Gloss:` pair.
* `parse_counters`, `detect_load_error`, `strip_banner` -- the `stats -p`
  line, a start failure (exit -1), and `hc-output.txt`'s banner strip.
* `read_parse_stream` -- all of the above over a whole stream, giving exactly
  one result per sent word (SC-004).
* Test mode (US4) on the same `Block` machinery: `parse_test_block` reads a
  `Testing` block's `Test passed.` / `Test failed.` line and its
  `Expected parses:` / `Actual parses:` sections -- `None`, or hc's
  UNMATCHED parses only (F-8) -- into a `TestResult`; `parse_test_counters`
  reads `stats -t`; `read_test_stream` is the whole-stream form. hc prints
  expected parses with their glosses as given (no `?` substitution), so an
  expectation `form:?` seeded from an empty gloss prints, reads back and
  compares as `?` (F-7). `render_parse` is WriteParse's rule, for matching a
  printed parse back to a corpus expectation.

Column recovery and its one blind spot
--------------------------------------
WriteParse pads each column to max(len(form), len(gloss)) in UTF-16 code
units and joins columns with one space (F-6). A reading is accepted only
when re-rendering the tokens by that rule reproduces both printed lines, so
an empty form, a space in only one of form/gloss, or any misalignment is
`readable=False` with the raw lines kept. The check cannot see one case:
when a form AND its gloss both contain a space at the same column offset
(form "a b", gloss "x y"), the lines are byte-identical to two morphs
("a"/"x", "b"/"y"). The output itself carries no information to tell them
apart, so such a parse reads as the two-morph reading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

__all__ = [
    "OUTCOME_PARSED",
    "OUTCOME_NOT_PARSED",
    "OUTCOME_INVALID_SEGMENT",
    "OUTCOME_NOT_EXPRESSIBLE",
    "OUTCOME_ERROR_NO_OUTPUT",
    "OUTCOME_NOT_REACHED",
    "OUTCOMES",
    "BLOCK_PARSE",
    "BLOCK_TEST",
    "BLOCK_STATS",
    "MORPHS_PREFIX",
    "GLOSS_PREFIX",
    "u16len",
    "Block",
    "BlockReader",
    "iter_blocks",
    "Analysis",
    "read_columns",
    "WordResult",
    "parse_block",
    "placeholder_result",
    "mark_not_reached",
    "ParseCounters",
    "parse_counters",
    "HcLoadError",
    "detect_load_error",
    "strip_banner",
    "ParseStream",
    "read_parse_stream",
    "render_parse",
    "TEST_PASSED",
    "TEST_FAILED",
    "TEST_STATUSES",
    "TestResult",
    "parse_test_block",
    "placeholder_test_result",
    "mark_tests_not_reached",
    "TestCounters",
    "parse_test_counters",
    "TestStream",
    "read_test_stream",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The closed outcome enum of data-model 6.4, in its order.
OUTCOME_PARSED = "parsed"
OUTCOME_NOT_PARSED = "not_parsed"
OUTCOME_INVALID_SEGMENT = "invalid_segment"
OUTCOME_NOT_EXPRESSIBLE = "not_expressible"
OUTCOME_ERROR_NO_OUTPUT = "error_no_output"
OUTCOME_NOT_REACHED = "not_reached"
OUTCOMES: Tuple[str, ...] = (
    OUTCOME_PARSED,
    OUTCOME_NOT_PARSED,
    OUTCOME_INVALID_SEGMENT,
    OUTCOME_NOT_EXPRESSIBLE,
    OUTCOME_ERROR_NO_OUTPUT,
    OUTCOME_NOT_REACHED,
)
# Outcomes hc never prints: made by the caller, not read from a block.
_PLACEHOLDER_OUTCOMES = (
    OUTCOME_NOT_EXPRESSIBLE,
    OUTCOME_ERROR_NO_OUTPUT,
    OUTCOME_NOT_REACHED,
)

# A `test` command's statuses: hc's two verdicts, then the error outcomes.
TEST_PASSED = "passed"
TEST_FAILED = "failed"
TEST_STATUSES: Tuple[str, ...] = (
    TEST_PASSED,
    TEST_FAILED,
    OUTCOME_INVALID_SEGMENT,
    OUTCOME_NOT_EXPRESSIBLE,
    OUTCOME_ERROR_NO_OUTPUT,
    OUTCOME_NOT_REACHED,
)

BLOCK_PARSE = "parse"
BLOCK_TEST = "test"
BLOCK_STATS = "stats"

MORPHS_PREFIX = "Morphs: "
GLOSS_PREFIX = "Gloss:  "

_BOM = "\ufeff"
_HEADER_RE = re.compile(r'^(Parsing|Testing) "(.*)"$', re.S)
_STATS_PREFIXES = ("# of parses:", "# of tests:")
_PARSE_COUNTERS_RE = re.compile(
    r"^# of parses: (\d+), successful: (\d+), failed: (\d+), error: (\d+)$"
)
_INVALID_SEGMENT_RE = re.compile(
    r"^The word contains an invalid segment at position (-?\d+)\.$"
)
_PARSE_N_RE = re.compile(r"^Parse (\d+)$")
_PARSE_TIME_RE = re.compile(r"^Parse time: (\d+)ms$")
_NO_VALID_PARSES = "No valid parses."
_TEST_COUNTERS_RE = re.compile(
    r"^# of tests: (\d+), passed: (\d+), failed: (\d+), error: (\d+)$"
)
_TEST_PASSED = "Test passed."
_TEST_FAILED = "Test failed."
_EXPECTED_HEADER = "Expected parses:"
_ACTUAL_HEADER = "Actual parses:"
_NONE = "None"
_LOAD_ERROR_PREFIXES = (("Load Error: ", "load_error"), ("IO Error: ", "io_error"))
# Program.cs: the four banner lines hc prints after a successful load.
_BANNER_RE = re.compile(
    r'^\ufeff?Reading configuration file ".*"\.\.\. done\.\r?\n'
    r"Compiling rules\.\.\. done\.\r?\n"
    r"[^\r\n]* loaded\.\r?\n"
    r"\r?\n"
)


def u16len(text: str) -> int:
    """Length in UTF-16 code units, as .NET `string.Length` counts it."""
    return len(text.encode("utf-16-le", errors="surrogatepass")) // 2


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Block:
    """One hc output block: a header, its body, and whether hc terminated it."""

    kind: str
    word: Optional[str]
    header: str
    body: Tuple[str, ...]
    complete: bool


def _header_of(line: str) -> Optional[Tuple[str, Optional[str]]]:
    m = _HEADER_RE.match(line)
    if m:
        kind = BLOCK_PARSE if m.group(1) == "Parsing" else BLOCK_TEST
        return kind, m.group(2)
    if line.startswith(_STATS_PREFIXES):
        return BLOCK_STATS, None
    return None


class BlockReader:
    """Incremental block splitter for a growing `hc-stdout.txt`.

    `feed` / `feed_text` return only the blocks their input CLOSED: by hc's
    blank terminator (`complete=True`), or by a new header arriving while a
    block was still open (`complete=False`). The open block is `in_flight`
    until `close()` ends the stream.
    """

    def __init__(self) -> None:
        self._kind: Optional[str] = None
        self._word: Optional[str] = None
        self._header: Optional[str] = None
        self._body: List[str] = []
        self._partial = ""
        self._first = True
        self.stray: List[str] = []

    # -- internals --------------------------------------------------------
    def _snapshot(self, complete: bool) -> Block:
        return Block(self._kind, self._word, self._header, tuple(self._body), complete)

    def _reset(self) -> None:
        self._kind = self._word = self._header = None
        self._body = []

    def _take(self, line: str, out: List[Block]) -> None:
        if self._first:
            self._first = False
            if line.startswith(_BOM):
                line = line[1:]
        head = _header_of(line)
        if head is not None:
            if self._header is not None:
                out.append(self._snapshot(False))
            self._kind, self._word = head
            self._header = line
            self._body = []
            return
        if self._header is None:
            if line != "":
                self.stray.append(line)
            return
        if line == "":
            out.append(self._snapshot(True))
            self._reset()
        else:
            self._body.append(line)

    # -- public -----------------------------------------------------------
    def feed(self, lines: Iterable[str]) -> List[Block]:
        """Consume complete lines (no terminators); return the blocks closed."""
        out: List[Block] = []
        for line in lines:
            self._take(line, out)
        return out

    def feed_text(self, text: str) -> List[Block]:
        """Consume a raw chunk; a trailing partial line is buffered."""
        parts = (self._partial + text).split("\n")
        self._partial = parts.pop()
        return self.feed(p[:-1] if p.endswith("\r") else p for p in parts)

    @property
    def in_flight(self) -> Optional[Block]:
        """The block whose header was seen but whose terminator was not."""
        return None if self._header is None else self._snapshot(False)

    def finish(self) -> List[Block]:
        """End of stream: every block not yet returned, in order.

        Flushes a buffered partial line first (it may itself be a header that
        closes the open block), then appends the open block, complete=False.
        """
        out: List[Block] = []
        if self._partial:
            partial, self._partial = self._partial, ""
            if partial.endswith("\r"):
                partial = partial[:-1]
            self._take(partial, out)
        tail = self.in_flight
        if tail is not None:
            out.append(tail)
        self._reset()
        return out

    def close(self) -> Optional[Block]:
        """End of stream: the open block (complete=False), or None.

        Equivalent to the last block of `finish()` when that block is still
        open; prefer `finish()` when the stream may end in a partial line.
        """
        rest = self.finish()
        if rest and not rest[-1].complete:
            return rest[-1]
        return None


def iter_blocks(lines: Iterable[str]) -> Iterator[Block]:
    """Every closed block, then the still-open block (complete=False), if any."""
    reader = BlockReader()
    for line in lines:
        yield from reader.feed((line,))
    yield from reader.finish()


# ---------------------------------------------------------------------------
# Columns (R-08)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Analysis:
    """One printed parse. `morphs` is None and `raw` set when unreadable."""

    readable: bool
    morphs: Optional[Tuple[Tuple[str, str], ...]]
    raw: Optional[Tuple[str, str]]

    @property
    def forms(self) -> Optional[Tuple[str, ...]]:
        if self.morphs is None:
            return None
        return tuple(form for form, _ in self.morphs)


def _render(values: Sequence[str], others: Sequence[str]) -> str:
    """WriteParse's rule for one line: pad to max u16 width, join with ' '."""
    cols = []
    for value, other in zip(values, others, strict=True):
        width = max(u16len(value), u16len(other))
        cols.append(value + " " * (width - u16len(value)))
    return " ".join(cols)


def render_parse(pairs: Iterable[Sequence[str]]) -> Tuple[str, str]:
    """WriteParse's two lines for (form, gloss) pairs; zero-width morphs skipped."""
    kept = [(p[0], p[1]) for p in pairs if max(u16len(p[0]), u16len(p[1])) > 0]
    forms = [f for f, _ in kept]
    glosses = [g for _, g in kept]
    return (
        MORPHS_PREFIX + _render(forms, glosses),
        GLOSS_PREFIX + _render(glosses, forms),
    )


def read_columns(morphs_line: str, gloss_line: str) -> Analysis:
    """Recover (form, gloss) pairs, or flag the parse unreadable (FR-019)."""
    unreadable = Analysis(False, None, (morphs_line, gloss_line))
    if not (
        morphs_line.startswith(MORPHS_PREFIX) and gloss_line.startswith(GLOSS_PREFIX)
    ):
        return unreadable
    morphs_text = morphs_line[len(MORPHS_PREFIX) :]
    gloss_text = gloss_line[len(GLOSS_PREFIX) :]
    forms = [t for t in morphs_text.split(" ") if t]
    glosses = [t for t in gloss_text.split(" ") if t]
    if not forms or len(forms) != len(glosses):
        return unreadable
    # The round-trip proof: trailing padding is not significant.
    if _render(forms, glosses).rstrip(" ") != morphs_text.rstrip(" "):
        return unreadable
    if _render(glosses, forms).rstrip(" ") != gloss_text.rstrip(" "):
        return unreadable
    return Analysis(True, tuple(zip(forms, glosses, strict=True)), None)


# ---------------------------------------------------------------------------
# Word results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WordResult:
    """One word's outcome. `position` is hc's printed (1-based) position."""

    word: Optional[str]
    outcome: str
    analyses: Tuple[Analysis, ...] = ()
    position: Optional[int] = None
    parse_time_ms: Optional[int] = None


def placeholder_result(word: Optional[str], outcome: str) -> WordResult:
    """A result for an outcome hc never prints (no analyses, no position)."""
    if outcome not in _PLACEHOLDER_OUTCOMES:
        raise ValueError("not a placeholder outcome: %r" % (outcome,))
    return WordResult(word, outcome)


def mark_not_reached(words: Iterable[Optional[str]]) -> List[WordResult]:
    return [placeholder_result(word, OUTCOME_NOT_REACHED) for word in words]


def parse_block(block: Block) -> WordResult:
    """A parse block's outcome. Anything not recognisably whole is error_no_output."""
    if block.kind != BLOCK_PARSE:
        raise ValueError("not a parse block: %r" % (block.kind,))
    no_output = WordResult(block.word, OUTCOME_ERROR_NO_OUTPUT)
    body = list(block.body)
    if not block.complete or not body:
        return no_output

    m = _INVALID_SEGMENT_RE.match(body[0])
    if m and len(body) == 1:
        return WordResult(
            block.word, OUTCOME_INVALID_SEGMENT, (), int(m.group(1)), None
        )

    t = _PARSE_TIME_RE.match(body[-1])
    if not t:
        return no_output
    elapsed = int(t.group(1))
    body = body[:-1]
    if body == [_NO_VALID_PARSES]:
        return WordResult(block.word, OUTCOME_NOT_PARSED, (), None, elapsed)

    # `Parse <n>` / `Morphs: ` / `Gloss:  `, n = 1, 2, ...
    if not body or len(body) % 3:
        return no_output
    analyses = []
    for k in range(0, len(body), 3):
        n = _PARSE_N_RE.match(body[k])
        if not n or int(n.group(1)) != k // 3 + 1:
            return no_output
        analyses.append(read_columns(body[k + 1], body[k + 2]))
    return WordResult(block.word, OUTCOME_PARSED, tuple(analyses), None, elapsed)


# ---------------------------------------------------------------------------
# Counters, load errors, banner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParseCounters:
    """hc's `stats -p` line."""

    parses: int
    successful: int
    failed: int
    error: int

    def to_dict(self) -> dict:
        return {
            "parses": self.parses,
            "successful": self.successful,
            "failed": self.failed,
            "error": self.error,
        }


def parse_counters(line: str) -> Optional[ParseCounters]:
    m = _PARSE_COUNTERS_RE.match(line)
    if not m:
        return None
    return ParseCounters(*(int(g) for g in m.groups()))


@dataclass(frozen=True)
class HcLoadError:
    """A start failure: kind `load_error` or `io_error`, hc's message."""

    kind: str
    message: str
    line: str


def _load_error_in(lines: Iterable[str]) -> Optional[HcLoadError]:
    for i, line in enumerate(lines):
        if i == 0 and line.startswith(_BOM):
            line = line[1:]
        if _header_of(line) is not None:
            return None  # load errors only precede the first command
        for prefix, kind in _LOAD_ERROR_PREFIXES:
            if line.startswith(prefix):
                return HcLoadError(kind, line[len(prefix) :], line)
    return None


def detect_load_error(text: str) -> Optional[HcLoadError]:
    return _load_error_in(re.split(r"\r\n|\n", text))


def strip_banner(text: str) -> str:
    """`hc-output.txt`: the stream minus hc's four-line load banner."""
    m = _BANNER_RE.match(text)
    return text[m.end() :] if m else text


# ---------------------------------------------------------------------------
# Whole stream
# ---------------------------------------------------------------------------


def _split_stream(lines: Iterable[str]):
    """(load_error, blocks, stray) for a whole stream."""
    lines = list(lines)
    load_error = _load_error_in(lines)
    reader = BlockReader()
    blocks = reader.feed(lines)
    blocks.extend(reader.finish())
    return load_error, blocks, list(reader.stray)


def _last_counters(blocks: Sequence[Block], parse_line):
    counters = None
    for block in blocks:
        if block.kind == BLOCK_STATS:
            for line in (block.header,) + block.body:
                counters = parse_line(line) or counters
    return counters


@dataclass
class ParseStream:
    results: List[WordResult]
    counters: Optional[ParseCounters]
    load_error: Optional[HcLoadError]
    stray: List[str] = field(default_factory=list)


def read_parse_stream(
    lines: Iterable[str],
    words: Sequence[str],
    exit_code: Optional[int] = None,
) -> ParseStream:
    """Exactly one result per sent word, or none at all on a start failure."""
    load_error, blocks, stray = _split_stream(lines)
    if load_error is not None or (exit_code == -1 and not blocks):
        return ParseStream([], None, load_error, stray)
    counters = _last_counters(blocks, parse_counters)
    parse_blocks = [b for b in blocks if b.kind == BLOCK_PARSE]
    results = [parse_block(b) for b in parse_blocks[: len(words)]]
    results.extend(mark_not_reached(words[len(results) :]))
    return ParseStream(results, counters, None, stray)


# ---------------------------------------------------------------------------
# Test mode (TestCommand.cs; F-5, F-7, F-8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TestResult:
    """One `test` command. `expected` / `actual` are hc's UNMATCHED parses."""

    __test__ = False  # not a pytest class

    word: Optional[str]
    status: str
    expected: Tuple[Analysis, ...] = ()
    actual: Tuple[Analysis, ...] = ()
    position: Optional[int] = None


def placeholder_test_result(word: Optional[str], status: str) -> TestResult:
    """A test result for a status hc never prints."""
    if status not in _PLACEHOLDER_OUTCOMES:
        raise ValueError("not a placeholder status: %r" % (status,))
    return TestResult(word, status)


def mark_tests_not_reached(words: Iterable[Optional[str]]) -> List[TestResult]:
    return [placeholder_test_result(word, OUTCOME_NOT_REACHED) for word in words]


def _read_section(
    body: List[str], start: int, stop_at: Optional[str]
) -> Tuple[Optional[Tuple[Analysis, ...]], int]:
    """Read `None` or Morphs/Gloss pairs from body[start:]; (parses|None-on-error, next)."""
    if start < len(body) and body[start] == _NONE:
        return (), start + 1
    parses: List[Analysis] = []
    k = start
    while k < len(body) and body[k] != stop_at:
        if not (
            body[k].startswith(MORPHS_PREFIX)
            and k + 1 < len(body)
            and body[k + 1].startswith(GLOSS_PREFIX)
        ):
            return None, k
        parses.append(read_columns(body[k], body[k + 1]))
        k += 2
    if not parses:
        return None, k
    return tuple(parses), k


def parse_test_block(block: Block) -> TestResult:
    """A test block's status and sections. Anything not whole is error_no_output."""
    if block.kind != BLOCK_TEST:
        raise ValueError("not a test block: %r" % (block.kind,))
    no_output = TestResult(block.word, OUTCOME_ERROR_NO_OUTPUT)
    body = list(block.body)
    if not block.complete or not body:
        return no_output
    if body == [_TEST_PASSED]:
        return TestResult(block.word, TEST_PASSED)
    if len(body) == 1:
        m = _INVALID_SEGMENT_RE.match(body[0])
        if m:
            return TestResult(
                block.word, OUTCOME_INVALID_SEGMENT, (), (), int(m.group(1))
            )
        return no_output
    if body[0] != _TEST_FAILED or body[1] != _EXPECTED_HEADER:
        return no_output
    expected, k = _read_section(body, 2, _ACTUAL_HEADER)
    if expected is None or k >= len(body) or body[k] != _ACTUAL_HEADER:
        return no_output
    actual, k = _read_section(body, k + 1, None)
    if actual is None or k != len(body):
        return no_output
    if not expected and not actual:
        return no_output  # hc never prints a failure with nothing unmatched
    return TestResult(block.word, TEST_FAILED, expected, actual)


@dataclass(frozen=True)
class TestCounters:
    """hc's `stats -t` line (data-model 6.6 `hc_counters`)."""

    __test__ = False  # not a pytest class

    tests: int
    passed: int
    failed: int
    error: int

    def to_dict(self) -> dict:
        return {
            "tests": self.tests,
            "passed": self.passed,
            "failed": self.failed,
            "error": self.error,
        }


def parse_test_counters(line: str) -> Optional[TestCounters]:
    m = _TEST_COUNTERS_RE.match(line)
    if not m:
        return None
    return TestCounters(*(int(g) for g in m.groups()))


@dataclass
class TestStream:
    __test__ = False  # not a pytest class

    results: List[TestResult]
    counters: Optional[TestCounters]
    load_error: Optional[HcLoadError]
    stray: List[str] = field(default_factory=list)


def read_test_stream(
    lines: Iterable[str],
    words: Sequence[str],
    exit_code: Optional[int] = None,
) -> TestStream:
    """`read_parse_stream`'s rules for a test run: one result per sent word."""
    load_error, blocks, stray = _split_stream(lines)
    if load_error is not None or (exit_code == -1 and not blocks):
        return TestStream([], None, load_error, stray)
    counters = _last_counters(blocks, parse_test_counters)
    test_blocks = [b for b in blocks if b.kind == BLOCK_TEST]
    results = [parse_test_block(b) for b in test_blocks[: len(words)]]
    results.extend(mark_tests_not_reached(words[len(results) :]))
    return TestStream(results, counters, None, stray)
