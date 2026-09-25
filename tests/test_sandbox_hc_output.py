#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parser-check CP5 T038 (FR-016..FR-019, SC-004): `server/sandbox/hc_output.py`,
the ONE parser of HermitCrab `hc`'s console format (parse mode).

Fixtures are byte-faithful to real hc (`C:\\Github\\machine`,
SIL.Machine.Morphology.HermitCrab.Tool: Program.cs banner and load errors,
ParseCommand.cs, StatsCommand.cs, Extensions.cs WriteParse, MorphInfo.cs).
Lines are handed to the parser as `hc-stdout.txt` holds them: hc's UTF-16
stream decoded by the script and written one line per hc line, with no line
terminator in a `lines` list and `\\r\\n` in raw text.

The API this file specifies
---------------------------
Outcome constants (the closed enum of data-model 6.4, in its order)::

    OUTCOME_PARSED = "parsed"            OUTCOME_NOT_EXPRESSIBLE = "not_expressible"
    OUTCOME_NOT_PARSED = "not_parsed"    OUTCOME_ERROR_NO_OUTPUT = "error_no_output"
    OUTCOME_INVALID_SEGMENT = "invalid_segment"
    OUTCOME_NOT_REACHED = "not_reached"
    OUTCOMES = (parsed, not_parsed, invalid_segment, not_expressible,
                error_no_output, not_reached)

Block kinds ``BLOCK_PARSE = "parse"``, ``BLOCK_TEST = "test"`` (US4, T069),
``BLOCK_STATS = "stats"``; ``MORPHS_PREFIX = "Morphs: "``,
``GLOSS_PREFIX = "Gloss:  "``; ``u16len(s) -> int`` (UTF-16 code units).

``Block`` (frozen dataclass)::

    kind: str                  # BLOCK_PARSE | BLOCK_TEST | BLOCK_STATS
    word: Optional[str]        # the word inside the `Parsing "..."` header; None for stats
    header: str                # the first line (for stats: the first counter line)
    body: tuple[str, ...]      # the lines after the header, terminator excluded
    complete: bool             # True only when ended by hc's blank terminator line

A block starts at a `Parsing "<w>"`, `Testing "<w>"`, `# of parses:` or
`# of tests:` line and ends at the next blank line. A new header arriving while
a block is open closes the open block with ``complete=False``. Lines outside
any block (the load banner, anything unrecognised) are kept in ``stray``. A
leading U+FEFF on the very first line is dropped.

``BlockReader()`` -- incremental, for the client tailing `hc-stdout.txt`::

    feed(lines: Iterable[str]) -> list[Block]   # blocks CLOSED by these lines, in order
    feed_text(text: str) -> list[Block]         # raw chunk; splits on \\n, drops a
                                                # trailing \\r, buffers a partial last line
    in_flight -> Optional[Block]                # the open block (complete=False), or None
    finish() -> list[Block]                     # end of stream: every block not yet
                                                # returned (a flushed partial line may
                                                # close one), then the open block
    close() -> Optional[Block]                  # end of stream: the open block
                                                # (complete=False), after flushing any
                                                # buffered partial line; None if none
    stray -> list[str]

``iter_blocks(lines) -> Iterator[Block]``: every closed block, then the block
still open at the end of the stream (``complete=False``) if there is one.

``Analysis`` (frozen dataclass)::

    readable: bool
    morphs: Optional[tuple[tuple[str, str], ...]]   # (form, gloss); None if unreadable
    raw: Optional[tuple[str, str]]                  # both printed lines, prefixes
                                                    # included; None when readable
    forms -> Optional[tuple[str, ...]]              # property: the forms, or None

``read_columns(morphs_line, gloss_line) -> Analysis`` implements R-08: take
each line after its 8-character prefix, tokenise on runs of spaces, and accept
only if the token counts are equal, non-zero, AND re-rendering with
WriteParse's rule (pad each column to max(u16len(form), u16len(gloss)), join
with one space) reproduces both lines (trailing spaces not significant).
Otherwise unreadable, raw kept, nothing guessed.

``WordResult`` (frozen dataclass)::

    word: Optional[str]
    outcome: str                       # one of OUTCOMES
    analyses: tuple[Analysis, ...]     # hc's order; () unless outcome == parsed
    position: Optional[int]            # invalid_segment only: the PRINTED (1-based) position
    parse_time_ms: Optional[int]       # from `Parse time: <n>ms`, when printed

``parse_block(block) -> WordResult`` (ValueError for a non-parse block): an
incomplete block, or a complete one whose body is not a recognised outcome, is
``error_no_output`` -- never ``not_parsed`` (FR-018).

``placeholder_result(word, outcome) -> WordResult`` for the outcomes hc never
prints (not_expressible, error_no_output, not_reached; ValueError otherwise);
``mark_not_reached(words) -> list[WordResult]``.

``ParseCounters(parses, successful, failed, error)`` with ``to_dict()``;
``parse_counters(line) -> Optional[ParseCounters]`` for the `stats -p` line.

``HcLoadError(kind, message, line)`` with kind ``"load_error"`` |
``"io_error"``; ``detect_load_error(text: str) -> Optional[HcLoadError]``
looks only before the first block header.

``strip_banner(text: str) -> str``: `hc-output.txt` = `hc-stdout.txt` minus the
four-line load banner (`Reading configuration file "<f>"... done.`,
`Compiling rules... done.`, `<language> loaded.`, blank). Unchanged when the
banner is not complete (a load failure keeps its message).

``read_parse_stream(lines, words, exit_code=None) -> ParseStream`` -- a whole
stream at once::

    results: list[WordResult]     # exactly len(words), in order; [] on a load failure
    counters: Optional[ParseCounters]
    load_error: Optional[HcLoadError]
    stray: list[str]

Parse blocks match sent ``words`` by order. A block closed incomplete, or open
at the end of the stream, is error_no_output; every sent word with no block
(after the stream ends) is not_reached. A load error (or exit -1 with no block
at all) gives zero results.

Test mode (T065; TestCommand.cs, F-7, F-8)
------------------------------------------
``render_parse(pairs) -> (morphs_line, gloss_line)``: WriteParse's two lines
for (form, gloss) pairs, zero-width morphs skipped, glosses printed as given
(hc prints EXPECTED parses without the `?` substitution; an expectation
`form:?` therefore prints and reads back as `?`).

``TEST_PASSED = "passed"``, ``TEST_FAILED = "failed"``; ``TEST_STATUSES =
("passed", "failed", "invalid_segment", "not_expressible", "error_no_output",
"not_reached")``.

``TestResult`` (frozen dataclass)::

    word: Optional[str]
    status: str                       # one of TEST_STATUSES
    expected: tuple[Analysis, ...]    # the printed UNMATCHED expected parses (F-8)
    actual: tuple[Analysis, ...]      # the printed UNMATCHED actual parses
    position: Optional[int]           # invalid_segment only

``parse_test_block(block) -> TestResult`` (ValueError for a non-test block):
`Test passed.` -> passed; `Test failed.` + `Expected parses:` (`None` or
Morphs/Gloss pairs) + `Actual parses:` (`None` or pairs) -> failed; the
invalid-segment line -> invalid_segment. Incomplete, or anything else
(including a failure with both sections `None`) -> error_no_output.

``placeholder_test_result(word, status)`` (not_expressible, error_no_output,
not_reached; ValueError otherwise); ``mark_tests_not_reached(words)``.

``TestCounters(tests, passed, failed, error)`` with ``to_dict()`` ->
``{"tests", "passed", "failed", "error"}`` (data-model 6.6 `hc_counters`);
``parse_test_counters(line) -> Optional[TestCounters]`` for `stats -t`.

``read_test_stream(lines, words, exit_code=None) -> TestStream`` with
``results: list[TestResult]``, ``counters: Optional[TestCounters]``,
``load_error``, ``stray`` -- the same rules as ``read_parse_stream``.

The data-model 6.6 reconciliation (``classify.reconcile_test_counters``) is
pinned here too: passed == pass, failed == regression + new_ambiguity +
changed, error == the invalid_segment errors, tests == all three.
"""

from __future__ import annotations

import dataclasses
import importlib
import random
import subprocess
import sys
from pathlib import Path

import pytest

HC_FAKE = Path(__file__).parent / "fakes" / "hc_fake.py"

# An astral-plane character: 1 Python code point, 2 UTF-16 code units.
ASTRAL = "\U00010400"

BANNER = [
    'Reading configuration file "hc-config.xml"... done.',
    "Compiling rules... done.",
    "Sena Fake loaded.",
    "",
]


def hco():
    """Import inside test bodies, so a missing module fails the test, not collection."""
    return importlib.import_module("flextoolsmcp.server.sandbox.hc_output")


# ---------------------------------------------------------------------------
# A byte-faithful renderer of hc's output (Extensions.WriteParse et al.)
# ---------------------------------------------------------------------------


def u16(text: str) -> int:
    return len(text.encode("utf-16-le", errors="surrogatepass")) // 2


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - u16(text))


def write_parse(parse):
    """The two lines WriteParse prints for a list of (form, gloss) morphs."""
    lines = []
    for prefix, pick in (("Morphs: ", 0), ("Gloss:  ", 1)):
        cols = []
        for morph in parse:
            width = max(u16(morph[0]), u16(morph[1]))
            if width > 0:
                cols.append(pad(morph[pick], width))
        lines.append(prefix + " ".join(cols))
    return lines


def parse_block_lines(word, parses, ms=3):
    """ParseCommand.Run for a word with these parses ([] = no valid parses)."""
    out = ['Parsing "%s"' % word]
    if not parses:
        out.append("No valid parses.")
    for n, parse in enumerate(parses, 1):
        out.append("Parse %d" % n)
        out.extend(write_parse([(f, g or "?") for f, g in parse]))
    out.append("Parse time: %dms" % ms)
    out.append("")
    return out


def invalid_block_lines(word, printed_position):
    return [
        'Parsing "%s"' % word,
        "The word contains an invalid segment at position %d." % printed_position,
        "",
    ]


def stats_p(n, s, f, e):
    return ["# of parses: %d, successful: %d, failed: %d, error: %d" % (n, s, f, e), ""]


MEMBACA = parse_block_lines("membaca", [[("mem", "ACT"), ("baca", "read")]])
XYZ = parse_block_lines("xyz", [])
QHASH = invalid_block_lines("q#", 2)
BACA2 = parse_block_lines("baca", [[("baca", "read")], [("baca", "")]])


# ---------------------------------------------------------------------------
# Enum and fixtures sanity
# ---------------------------------------------------------------------------


def test_outcome_enum_is_the_closed_data_model_set():
    m = hco()
    assert m.OUTCOMES == (
        "parsed",
        "not_parsed",
        "invalid_segment",
        "not_expressible",
        "error_no_output",
        "not_reached",
    )
    assert (m.OUTCOME_PARSED, m.OUTCOME_NOT_PARSED, m.OUTCOME_INVALID_SEGMENT) == (
        "parsed",
        "not_parsed",
        "invalid_segment",
    )
    assert (
        m.OUTCOME_NOT_EXPRESSIBLE,
        m.OUTCOME_ERROR_NO_OUTPUT,
        m.OUTCOME_NOT_REACHED,
    ) == (
        "not_expressible",
        "error_no_output",
        "not_reached",
    )
    assert (m.BLOCK_PARSE, m.BLOCK_TEST, m.BLOCK_STATS) == ("parse", "test", "stats")
    assert (m.MORPHS_PREFIX, m.GLOSS_PREFIX) == ("Morphs: ", "Gloss:  ")


def test_u16len_counts_code_units():
    m = hco()
    assert m.u16len("abc") == 3
    assert m.u16len(ASTRAL) == 2
    assert m.u16len("") == 0


def test_fixture_renderer_matches_the_fake_hc_bytes():
    # Guard the local renderer against the fake's (itself checked against hc).
    assert write_parse([(ASTRAL, "X"), ("a", "LONGGLOSS")]) == [
        "Morphs: %s a        " % ASTRAL,
        "Gloss:  X  LONGGLOSS",
    ]
    assert write_parse([("baca", "?")]) == ["Morphs: baca", "Gloss:  ?   "]


# ---------------------------------------------------------------------------
# Block splitting
# ---------------------------------------------------------------------------


def test_blocks_split_on_headers_and_blank_terminators():
    m = hco()
    lines = BANNER + MEMBACA + XYZ + QHASH + BACA2 + stats_p(4, 2, 1, 1)
    blocks = list(m.iter_blocks(lines))
    assert [b.kind for b in blocks] == ["parse"] * 4 + ["stats"]
    assert [b.word for b in blocks] == ["membaca", "xyz", "q#", "baca", None]
    assert all(b.complete for b in blocks)
    assert blocks[0].header == 'Parsing "membaca"'
    assert blocks[0].body == (
        "Parse 1",
        "Morphs: mem baca",
        "Gloss:  ACT read",
        "Parse time: 3ms",
    )
    assert blocks[2].body == ("The word contains an invalid segment at position 2.",)
    assert blocks[4].header.startswith("# of parses: 4")
    assert blocks[4].body == ()


def test_banner_lines_are_stray_not_blocks():
    m = hco()
    reader = m.BlockReader()
    closed = reader.feed(BANNER + MEMBACA)
    assert [b.word for b in closed] == ["membaca"]
    assert reader.stray[:3] == BANNER[:3]
    assert reader.in_flight is None
    assert reader.close() is None


def test_word_with_quote_and_space_keeps_the_header_word():
    m = hco()
    lines = parse_block_lines("don't \"x", []) + parse_block_lines("a b", [])
    words = [b.word for b in m.iter_blocks(lines)]
    assert words == ["don't \"x", "a b"]


def test_leading_bom_is_dropped():
    m = hco()
    lines = ["\ufeff" + BANNER[0]] + BANNER[1:] + MEMBACA
    blocks = list(m.iter_blocks(lines))
    assert [b.word for b in blocks] == ["membaca"]
    stream = m.read_parse_stream(lines, ["membaca"], exit_code=0)
    assert stream.results[0].outcome == "parsed"


def test_new_header_closes_an_unterminated_block_as_incomplete():
    m = hco()
    broken = ['Parsing "abc"', "Parse 1"]  # no Morphs/Gloss, no terminator
    blocks = list(m.iter_blocks(broken + MEMBACA))
    assert [(b.word, b.complete) for b in blocks] == [("abc", False), ("membaca", True)]
    assert m.parse_block(blocks[0]).outcome == "error_no_output"


# ---------------------------------------------------------------------------
# Incremental feeding (the client tails hc-stdout.txt live)
# ---------------------------------------------------------------------------


def test_partial_last_block_not_emitted_until_terminated():
    m = hco()
    reader = m.BlockReader()
    assert reader.feed(BANNER) == []
    assert reader.feed(MEMBACA[:-1]) == []  # everything but the blank terminator
    assert reader.in_flight is not None
    assert reader.in_flight.word == "membaca"
    assert reader.in_flight.complete is False
    done = reader.feed([""])
    assert [(b.word, b.complete) for b in done] == [("membaca", True)]
    assert reader.in_flight is None
    reader.feed(XYZ[:1])
    assert reader.in_flight.word == "xyz"
    tail = reader.close()
    assert tail is not None and tail.word == "xyz" and tail.complete is False


def test_feed_one_line_at_a_time_equals_whole_stream():
    m = hco()
    lines = BANNER + MEMBACA + XYZ + QHASH + BACA2 + stats_p(4, 2, 1, 1)
    reader = m.BlockReader()
    got = []
    for line in lines:
        got.extend(reader.feed([line]))
    assert reader.close() is None
    assert got == list(m.iter_blocks(lines))


def test_feed_text_buffers_partial_lines_and_split_crlf():
    m = hco()
    text = "\r\n".join(BANNER + MEMBACA + XYZ) + "\r\n"
    whole = list(m.iter_blocks(BANNER + MEMBACA + XYZ))
    for cut_points in ([5, 17, 60], [len("\r\n".join(BANNER + MEMBACA[:1])) + 1]):
        reader = m.BlockReader()
        got, start = [], 0
        for cut in cut_points + [len(text)]:
            got.extend(reader.feed_text(text[start:cut]))
            start = cut
        assert got == whole
    # A chunk that ends between \r and \n does not produce a stray "\r".
    reader = m.BlockReader()
    chunk = "\r\n".join(MEMBACA)
    assert reader.feed_text(chunk + "\r") == []
    assert [b.word for b in reader.feed_text("\n")] == ["membaca"]


def test_feed_text_mid_header_is_not_a_block_yet():
    m = hco()
    reader = m.BlockReader()
    reader.feed_text('Parsing "memb')
    assert reader.in_flight is None  # the header line itself is not complete
    reader.feed_text('aca"\r\n')
    assert reader.in_flight.word == "membaca"


# ---------------------------------------------------------------------------
# Outcomes of a parse block
# ---------------------------------------------------------------------------


def _one(m, lines):
    blocks = list(m.iter_blocks(lines))
    assert len(blocks) == 1
    return m.parse_block(blocks[0])


def test_no_valid_parses_is_not_parsed():
    m = hco()
    result = _one(m, XYZ)
    assert result.word == "xyz"
    assert result.outcome == "not_parsed"
    assert result.analyses == ()
    assert result.position is None
    assert result.parse_time_ms == 3


def test_invalid_segment_gives_its_printed_position():
    m = hco()
    result = _one(m, invalid_block_lines("q#", 2))
    assert result.outcome == "invalid_segment"
    assert result.position == 2
    assert result.analyses == ()
    assert result.parse_time_ms is None  # hc prints no time line on this path


def test_single_parse():
    m = hco()
    result = _one(m, MEMBACA)
    assert result.outcome == "parsed"
    assert len(result.analyses) == 1
    analysis = result.analyses[0]
    assert analysis.readable is True
    assert analysis.morphs == (("mem", "ACT"), ("baca", "read"))
    assert analysis.forms == ("mem", "baca")
    assert analysis.raw is None


def test_multiple_parses_keep_hc_order():
    m = hco()
    parses = [
        [("mem", "ACT"), ("baca", "read")],
        [("me", "X"), ("mbaca", "Y")],
        [("membaca", "reading")],
    ]
    result = _one(m, parse_block_lines("membaca", parses, ms=41))
    assert result.outcome == "parsed"
    assert [a.morphs for a in result.analyses] == [tuple(p) for p in parses]
    assert result.parse_time_ms == 41


def test_empty_gloss_prints_as_question_mark_and_reads_as_question_mark():
    m = hco()
    result = _one(m, BACA2)
    assert result.outcome == "parsed"
    assert [a.morphs for a in result.analyses] == [
        (("baca", "read"),),
        (("baca", "?"),),
    ]
    assert all(a.readable for a in result.analyses)


def test_incomplete_block_is_error_no_output_never_not_parsed():
    m = hco()
    for cut in range(1, len(MEMBACA)):  # header present, terminator missing
        blocks = list(m.iter_blocks(MEMBACA[:cut]))
        assert len(blocks) == 1 and blocks[0].complete is False
        result = m.parse_block(blocks[0])
        assert result.outcome == "error_no_output"
        assert result.analyses == ()
    # Even a block that already printed "No valid parses." is not not_parsed
    # until hc terminated it.
    blocks = list(m.iter_blocks(XYZ[:2]))
    assert m.parse_block(blocks[0]).outcome == "error_no_output"


def test_complete_but_unrecognised_body_is_error_no_output():
    m = hco()
    result = _one(m, ['Parsing "w"', "Something hc never prints.", ""])
    assert result.outcome == "error_no_output"
    result = _one(m, ['Parsing "w"', ""])
    assert result.outcome == "error_no_output"


def test_parse_block_rejects_non_parse_block():
    m = hco()
    block = next(iter(m.iter_blocks(stats_p(1, 1, 0, 0))))
    with pytest.raises(ValueError):
        m.parse_block(block)


# ---------------------------------------------------------------------------
# Column recovery (R-08, FR-019)
# ---------------------------------------------------------------------------


def test_astral_character_column_reads_correctly():
    m = hco()
    # Form is an astral char (2 UTF-16 units): hc pads the X gloss column to 2
    # units. A code-point-width reader re-renders "X " and fails the proof.
    morphs_line, gloss_line = write_parse([(ASTRAL, "X"), ("a", "LONGGLOSS")])
    assert gloss_line == "Gloss:  X  LONGGLOSS"
    analysis = m.read_columns(morphs_line, gloss_line)
    assert analysis.readable is True
    assert analysis.morphs == ((ASTRAL, "X"), ("a", "LONGGLOSS"))
    # Astral in a gloss, followed by more columns.
    parse = [("ab", ASTRAL * 2), ("c", "PL"), ("de" + ASTRAL, "Z")]
    analysis = m.read_columns(*write_parse(parse))
    assert analysis.readable is True
    assert analysis.morphs == tuple(parse)


def test_empty_form_is_unreadable_with_raw_kept():
    m = hco()
    lines = write_parse([("mem", "ACT"), ("", "PL"), ("baca", "read")])
    analysis = m.read_columns(*lines)
    assert analysis.readable is False
    assert analysis.morphs is None
    assert analysis.forms is None
    assert analysis.raw == tuple(lines)


def test_space_in_gloss_is_unreadable_with_raw_kept():
    m = hco()
    lines = write_parse([("mem", "ACT"), ("baca", "to read")])
    analysis = m.read_columns(*lines)
    assert analysis.readable is False
    assert analysis.morphs is None
    assert analysis.raw == tuple(lines)


def test_space_in_form_is_unreadable():
    m = hco()
    lines = write_parse([("a b", "X"), ("c", "Y")])
    assert m.read_columns(*lines).readable is False


def test_misaligned_columns_are_unreadable():
    m = hco()
    # Equal token counts, but the gloss column is not padded as hc pads it.
    analysis = m.read_columns("Morphs: mem baca", "Gloss:  ACTIVE read")
    assert analysis.readable is False
    assert analysis.raw == ("Morphs: mem baca", "Gloss:  ACTIVE read")


def test_trailing_padding_is_not_significant():
    m = hco()
    assert m.read_columns("Morphs: baca", "Gloss:  ?   ").morphs == (("baca", "?"),)
    assert m.read_columns("Morphs: baca", "Gloss:  ?").morphs == (("baca", "?"),)


def test_missing_prefix_or_empty_columns_are_unreadable():
    m = hco()
    assert m.read_columns("Morph: mem", "Gloss:  ACT").readable is False
    assert m.read_columns("Morphs: ", "Gloss:  ").readable is False


def test_unreadable_parse_still_counts_as_parsed():
    m = hco()
    lines = parse_block_lines(
        "membaca", [[("mem", "ACT"), ("", "PL")], [("membaca", "x y")]]
    )
    result = _one(m, lines)
    assert result.outcome == "parsed"
    assert len(result.analyses) == 2
    assert [a.readable for a in result.analyses] == [False, False]
    assert all(a.raw is not None for a in result.analyses)


# ---------------------------------------------------------------------------
# Counters (FR-017)
# ---------------------------------------------------------------------------


def test_parse_counters_line():
    m = hco()
    counters = m.parse_counters("# of parses: 12, successful: 7, failed: 3, error: 2")
    assert counters == m.ParseCounters(parses=12, successful=7, failed=3, error=2)
    assert counters.to_dict() == {
        "parses": 12,
        "successful": 7,
        "failed": 3,
        "error": 2,
    }
    assert m.parse_counters("# of tests: 1, passed: 1, failed: 0, error: 0") is None
    assert m.parse_counters("Parse time: 3ms") is None


def test_stream_counters_are_read_and_mismatch_is_not_overwritten():
    m = hco()
    # hc claims 3 successes; the per-word blocks show 1 parsed. The stream
    # reports both, untouched: reconciliation is classify.py's job.
    lines = BANNER + MEMBACA + XYZ + QHASH + stats_p(3, 3, 0, 0)
    stream = m.read_parse_stream(lines, ["membaca", "xyz", "q#"], exit_code=0)
    assert stream.counters == m.ParseCounters(parses=3, successful=3, failed=0, error=0)
    assert [r.outcome for r in stream.results] == [
        "parsed",
        "not_parsed",
        "invalid_segment",
    ]


def test_no_counters_on_a_timeout_stream():
    m = hco()
    lines = BANNER + MEMBACA + XYZ[:1]
    stream = m.read_parse_stream(lines, ["membaca", "xyz", "q#"], exit_code=None)
    assert stream.counters is None


# ---------------------------------------------------------------------------
# Load failures (FR-016)
# ---------------------------------------------------------------------------

LOAD_ERROR_TEXT = (
    'Reading configuration file "hc-config.xml"... \r\n'
    "Load Error: The feature 'bogus' is not defined.\r\n"
)
IO_ERROR_TEXT = (
    'Reading configuration file "hc-config.xml"... \r\n'
    "IO Error: Could not find file 'C:\\work\\hc-config.xml'.\r\n"
)


def test_detect_load_error():
    m = hco()
    err = m.detect_load_error(LOAD_ERROR_TEXT)
    assert err.kind == "load_error"
    assert err.message == "The feature 'bogus' is not defined."
    assert err.line == "Load Error: The feature 'bogus' is not defined."
    err = m.detect_load_error(IO_ERROR_TEXT)
    assert err.kind == "io_error"
    assert err.message == "Could not find file 'C:\\work\\hc-config.xml'."
    assert m.detect_load_error("\r\n".join(BANNER + MEMBACA)) is None


def test_load_error_text_after_a_header_is_not_a_load_error():
    m = hco()
    text = "\r\n".join(BANNER + ['Parsing "w"', "Load Error: nope", ""])
    assert m.detect_load_error(text) is None


def test_exit_minus_one_with_load_error_gives_zero_results():
    m = hco()
    lines = LOAD_ERROR_TEXT.split("\r\n")[:-1]
    stream = m.read_parse_stream(lines, ["membaca", "xyz"], exit_code=-1)
    assert stream.results == []
    assert stream.load_error.kind == "load_error"
    assert stream.counters is None
    stream = m.read_parse_stream(IO_ERROR_TEXT.split("\r\n")[:-1], ["a"], exit_code=-1)
    assert stream.results == []
    assert stream.load_error.kind == "io_error"


def test_exit_minus_one_without_any_block_gives_zero_results():
    m = hco()
    stream = m.read_parse_stream(["Usage: hc [OPTIONS]"], ["a", "b"], exit_code=-1)
    assert stream.results == []


def test_strip_banner():
    m = hco()
    body = "\r\n".join(MEMBACA + XYZ) + "\r\n"
    text = "\r\n".join(BANNER) + "\r\n" + body
    assert m.strip_banner(text) == body
    assert m.strip_banner("\ufeff" + text) == body
    assert m.strip_banner(body) == body
    assert m.strip_banner(LOAD_ERROR_TEXT) == LOAD_ERROR_TEXT
    # A language name with spaces and dots still ends the banner.
    other = text.replace("Sena Fake loaded.", "Sena 3 v.2 loaded.")
    assert m.strip_banner(other) == body


# ---------------------------------------------------------------------------
# Crash / timeout mid-list (FR-018, SC-004)
# ---------------------------------------------------------------------------


def test_crash_mid_list_error_no_output_then_not_reached():
    m = hco()
    words = ["membaca", "xyz", "q#", "baca", "zzz"]
    lines = BANNER + MEMBACA + XYZ + ['Parsing "q#"']  # hc died after the header
    stream = m.read_parse_stream(lines, words, exit_code=-532462766)
    assert [r.outcome for r in stream.results] == [
        "parsed",
        "not_parsed",
        "error_no_output",
        "not_reached",
        "not_reached",
    ]
    assert [r.word for r in stream.results] == words
    assert "not_parsed" not in [r.outcome for r in stream.results[2:]]


def test_killed_between_words_leaves_the_rest_not_reached():
    m = hco()
    words = ["membaca", "xyz", "q#"]
    stream = m.read_parse_stream(BANNER + MEMBACA, words, exit_code=1)
    assert [r.outcome for r in stream.results] == [
        "parsed",
        "not_reached",
        "not_reached",
    ]


def test_placeholder_and_mark_not_reached():
    m = hco()
    rest = m.mark_not_reached(["a", "b"])
    assert [(r.word, r.outcome, r.analyses, r.position) for r in rest] == [
        ("a", "not_reached", (), None),
        ("b", "not_reached", (), None),
    ]
    for outcome in ("not_expressible", "error_no_output", "not_reached"):
        r = m.placeholder_result("w", outcome)
        assert (r.word, r.outcome, r.analyses, r.position, r.parse_time_ms) == (
            "w",
            outcome,
            (),
            None,
            None,
        )
    for outcome in ("parsed", "not_parsed", "invalid_segment", "bogus"):
        with pytest.raises(ValueError):
            m.placeholder_result("w", outcome)


def test_results_are_frozen():
    m = hco()
    result = _one(m, MEMBACA)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.outcome = "not_parsed"


# ---------------------------------------------------------------------------
# Randomized invariant: n words sent -> exactly n results (SC-004)
# ---------------------------------------------------------------------------

_ALPHABET = ["a", "b", "k", "ng", "e", ASTRAL, "\u00e9", "\u0301", "'"]


def _rand_text(rng, allow_empty=False):
    if allow_empty and rng.random() < 0.2:
        return ""
    return "".join(rng.choice(_ALPHABET) for _ in range(rng.randint(1, 4)))


def _random_run(rng, n):
    words, lines, expected = [], list(BANNER), []
    for i in range(n):
        word = "w%d%s" % (i, _rand_text(rng))
        words.append(word)
        kind = rng.choice(["parsed", "parsed", "not_parsed", "invalid_segment"])
        if kind == "parsed":
            parses = [
                [
                    (_rand_text(rng), _rand_text(rng, allow_empty=True))
                    for _ in range(rng.randint(1, 4))
                ]
                for _ in range(rng.randint(1, 3))
            ]
            lines += parse_block_lines(word, parses, ms=rng.randint(0, 99))
            expected.append(
                ("parsed", [tuple((f, g or "?") for f, g in p) for p in parses], None)
            )
        elif kind == "not_parsed":
            lines += parse_block_lines(word, [])
            expected.append(("not_parsed", [], None))
        else:
            pos = rng.randint(1, 9)
            lines += invalid_block_lines(word, pos)
            expected.append(("invalid_segment", [], pos))
    return words, lines, expected


@pytest.mark.parametrize("seed", range(12))
def test_randomized_n_words_give_exactly_n_results(seed):
    m = hco()
    rng = random.Random(seed)
    n = rng.randint(1, 40)
    words, lines, expected = _random_run(rng, n)
    tally = [e[0] for e in expected]
    lines += stats_p(
        n,
        tally.count("parsed"),
        tally.count("not_parsed"),
        tally.count("invalid_segment"),
    )

    crash = seed % 3 == 0
    if crash:
        # Cut the stream right after the header of a random word.
        k = rng.randrange(n)
        header = lines.index('Parsing "%s"' % words[k])
        lines = lines[: header + 1]

    stream = m.read_parse_stream(
        lines, words, exit_code=0 if not crash else -1073741819
    )
    assert len(stream.results) == n
    assert [r.word for r in stream.results] == words
    for i, (result, (outcome, parses, pos)) in enumerate(
        zip(stream.results, expected, strict=True)
    ):
        if crash and i == k:
            assert result.outcome == "error_no_output"
        elif crash and i > k:
            assert result.outcome == "not_reached"
        else:
            assert result.outcome == outcome
            assert result.position == pos
            assert [a.morphs for a in result.analyses] == parses
            assert all(a.readable for a in result.analyses)
    if not crash:
        assert stream.counters.parses == n

    # The same stream fed live in random chunks closes the same blocks.
    text = "\r\n".join(lines) + ("\r\n" if not crash else "")
    reader = m.BlockReader()
    got, start = [], 0
    while start < len(text):
        step = rng.randint(1, 50)
        got.extend(reader.feed_text(text[start : start + step]))
        start += step
    tail = reader.close()
    if tail is not None:
        got.append(tail)
    assert got == list(m.iter_blocks(lines))
    assert sum(1 for b in got if b.kind == "parse") == (n if not crash else k + 1)


# ---------------------------------------------------------------------------
# End to end against the fake hc's real UTF-16 bytes
# ---------------------------------------------------------------------------

GRAMMAR = {
    "language": "Sena Fake",
    "words": {
        "membaca": [[["mem", "ACT"], ["baca", "read"]]],
        "baca": [[["baca", "read"]], [["baca", ""]]],
        "xyz": [],
        "q#": {"invalid_segment": 2},
        "\U00010400a": [[["\U00010400", "X"], ["a", "LONGGLOSS"]]],
        "mpl": [[["m", "A"], ["", "PL"]]],
    },
}


def test_fake_hc_stream_end_to_end(fake_hc, tmp_path):
    m = hco()
    config = fake_hc.write_config(tmp_path / "hc-config.xml", GRAMMAR)
    words = ["membaca", "baca", "xyz", "q#", "\U00010400a", "mpl"]
    script = tmp_path / "hc-script.txt"
    script.write_bytes(
        ("\n".join(['parse "%s"' % w for w in words] + ["stats -p"]) + "\n").encode(
            "utf-8"
        )
    )
    proc = subprocess.run(
        [sys.executable, str(HC_FAKE), "-i", str(config), "-s", str(script)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0
    text = proc.stdout.decode("utf-16-le")
    lines = text.split("\r\n")[:-1]
    stream = m.read_parse_stream(lines, words, exit_code=proc.returncode)
    assert [r.outcome for r in stream.results] == [
        "parsed",
        "parsed",
        "not_parsed",
        "invalid_segment",
        "parsed",
        "parsed",
    ]
    assert stream.results[1].analyses[1].morphs == (("baca", "?"),)
    assert stream.results[3].position == 2
    assert stream.results[4].analyses[0].morphs == (
        ("\U00010400", "X"),
        ("a", "LONGGLOSS"),
    )
    assert stream.results[5].analyses[0].readable is False
    assert stream.counters == m.ParseCounters(parses=6, successful=4, failed=1, error=1)
    assert stream.load_error is None
    assert m.strip_banner(text).startswith('Parsing "membaca"\r\n')


# ===========================================================================
# Test mode (T065): TestCommand.cs's sections, `stats -t`, data-model 6.6
# ===========================================================================


def hc_test_lines(word, missing=None, extras=None, passed=False):
    """TestCommand.Run: missing/extras are lists of (form, gloss) parses."""
    out = ['Testing "%s"' % word]
    if passed:
        out.append("Test passed.")
    else:
        out.append("Test failed.")
        out.append("Expected parses:")
        if not missing:
            out.append("None")
        for parse in missing or []:
            out.extend(write_parse(parse))  # expected: glosses printed as given
        out.append("Actual parses:")
        if not extras:
            out.append("None")
        for parse in extras or []:
            out.extend(write_parse([(f, g or "?") for f, g in parse]))
    out.append("")
    return out


def invalid_test_lines(word, pos):
    return [
        'Testing "%s"' % word,
        "The word contains an invalid segment at position %d." % pos,
        "",
    ]


def stats_t(n, p, f, e):
    return ["# of tests: %d, passed: %d, failed: %d, error: %d" % (n, p, f, e), ""]


MEM = [("mem", "ACT"), ("baca", "read")]
ALT = [("me", "X"), ("mbaca", "Y")]


def _test_one(m, lines):
    blocks = list(m.iter_blocks(lines))
    assert len(blocks) == 1 and blocks[0].kind == "test"
    return m.parse_test_block(blocks[0])


def test_test_status_enum_and_render_parse():
    m = hco()
    assert (m.TEST_PASSED, m.TEST_FAILED) == ("passed", "failed")
    assert m.TEST_STATUSES == (
        "passed",
        "failed",
        "invalid_segment",
        "not_expressible",
        "error_no_output",
        "not_reached",
    )
    assert m.render_parse(MEM) == ("Morphs: mem baca", "Gloss:  ACT read")
    assert m.render_parse([(ASTRAL, "X"), ("a", "LONGGLOSS")]) == tuple(
        write_parse([(ASTRAL, "X"), ("a", "LONGGLOSS")])
    )
    # Zero-width morphs are skipped, as WriteParse does.
    assert m.render_parse([("", ""), ("a", "B")]) == ("Morphs: a", "Gloss:  B")


def test_test_block_header_word():
    m = hco()
    blocks = list(m.iter_blocks(hc_test_lines("membaca", passed=True)))
    assert [(b.kind, b.word, b.complete) for b in blocks] == [("test", "membaca", True)]


def test_test_passed():
    m = hco()
    r = _test_one(m, hc_test_lines("membaca", passed=True))
    assert (r.word, r.status, r.expected, r.actual, r.position) == (
        "membaca",
        "passed",
        (),
        (),
        None,
    )


def test_test_failed_missing_only():
    m = hco()
    r = _test_one(m, hc_test_lines("membaca", missing=[MEM]))
    assert r.status == "failed"
    assert [a.morphs for a in r.expected] == [tuple(MEM)]
    assert r.actual == ()


def test_test_failed_extras_only():
    m = hco()
    r = _test_one(m, hc_test_lines("membaca", extras=[ALT, [("membaca", "")]]))
    assert r.status == "failed"
    assert r.expected == ()
    assert [a.morphs for a in r.actual] == [tuple(ALT), (("membaca", "?"),)]


def test_test_failed_both_sections():
    m = hco()
    lines = hc_test_lines("membaca", missing=[MEM, ALT], extras=[[("x", "Y")]])
    r = _test_one(m, lines)
    assert [a.morphs for a in r.expected] == [tuple(MEM), tuple(ALT)]
    assert [a.morphs for a in r.actual] == [(("x", "Y"),)]


def test_expected_question_mark_gloss_round_trips():
    m = hco()
    # An expectation seeded from an empty gloss is `baca:?`; hc prints it as-is.
    r = _test_one(m, hc_test_lines("baca", missing=[[("baca", "?")]]))
    assert [a.morphs for a in r.expected] == [(("baca", "?"),)]


def test_unreadable_section_parse_keeps_raw():
    m = hco()
    r = _test_one(m, hc_test_lines("mpl", extras=[[("m", "A"), ("", "PL")]]))
    assert r.status == "failed"
    assert r.actual[0].readable is False
    assert r.actual[0].raw == tuple(write_parse([("m", "A"), ("", "PL")]))


def test_test_invalid_segment():
    m = hco()
    r = _test_one(m, invalid_test_lines("q#", 3))
    assert (r.status, r.position, r.expected, r.actual) == (
        "invalid_segment",
        3,
        (),
        (),
    )


def test_test_incomplete_or_malformed_is_error_no_output():
    m = hco()
    full = hc_test_lines("membaca", missing=[MEM], extras=[ALT])
    for cut in range(1, len(full)):
        r = m.parse_test_block(list(m.iter_blocks(full[:cut]))[0])
        assert r.status == "error_no_output"
    # hc never prints a failure with both sections None.
    malformed = [
        'Testing "w"',
        "Test failed.",
        "Expected parses:",
        "None",
        "Actual parses:",
        "None",
        "",
    ]
    assert _test_one(m, malformed).status == "error_no_output"
    assert _test_one(m, ['Testing "w"', "Huh.", ""]).status == "error_no_output"
    # A Morphs line without its Gloss line is malformed.
    broken = [
        'Testing "w"',
        "Test failed.",
        "Expected parses:",
        "Morphs: mem",
        "Actual parses:",
        "None",
        "",
    ]
    assert _test_one(m, broken).status == "error_no_output"


def test_parse_test_block_rejects_parse_block():
    m = hco()
    with pytest.raises(ValueError):
        m.parse_test_block(next(iter(m.iter_blocks(MEMBACA))))


def test_test_placeholders():
    m = hco()
    for status in ("not_expressible", "error_no_output", "not_reached"):
        r = m.placeholder_test_result("w", status)
        assert (r.word, r.status, r.expected, r.actual, r.position) == (
            "w",
            status,
            (),
            (),
            None,
        )
    for status in ("passed", "failed", "invalid_segment", "x"):
        with pytest.raises(ValueError):
            m.placeholder_test_result("w", status)
    assert [r.status for r in m.mark_tests_not_reached(["a", "b"])] == [
        "not_reached",
        "not_reached",
    ]


def test_parse_test_counters():
    m = hco()
    c = m.parse_test_counters("# of tests: 5, passed: 2, failed: 2, error: 1")
    assert c == m.TestCounters(tests=5, passed=2, failed=2, error=1)
    assert c.to_dict() == {"tests": 5, "passed": 2, "failed": 2, "error": 1}
    assert (
        m.parse_test_counters("# of parses: 1, successful: 1, failed: 0, error: 0")
        is None
    )


def test_read_test_stream_n_words_n_results_and_counters():
    m = hco()
    words = ["membaca", "baca", "q#", "xyz", "zzz"]
    lines = (
        BANNER
        + hc_test_lines("membaca", passed=True)
        + hc_test_lines("baca", extras=[[("baca", "")]])
        + invalid_test_lines("q#", 2)
        + stats_t(3, 1, 1, 1)
    )
    stream = m.read_test_stream(lines, words, exit_code=0)
    assert [r.status for r in stream.results] == [
        "passed",
        "failed",
        "invalid_segment",
        "not_reached",
        "not_reached",
    ]
    assert stream.counters == m.TestCounters(tests=3, passed=1, failed=1, error=1)


def test_read_test_stream_crash_and_load_error():
    m = hco()
    words = ["membaca", "baca", "xyz"]
    lines = BANNER + hc_test_lines("membaca", passed=True) + ['Testing "baca"']
    stream = m.read_test_stream(lines, words, exit_code=-532462766)
    assert [r.status for r in stream.results] == [
        "passed",
        "error_no_output",
        "not_reached",
    ]
    assert stream.counters is None
    stream = m.read_test_stream(LOAD_ERROR_TEXT.split("\r\n")[:-1], words, exit_code=-1)
    assert stream.results == [] and stream.load_error.kind == "load_error"


def test_fake_hc_test_stream_end_to_end(fake_hc, tmp_path):
    m = hco()
    config = fake_hc.write_config(tmp_path / "hc-config.xml", GRAMMAR)
    script = tmp_path / "hc-script.txt"
    commands = [
        'test -p "mem:ACT|baca:read" "membaca"',  # pass
        'test -p "baca:read" "baca"',  # new ambiguity: baca:? is extra
        'test -p "x:y" "xyz"',  # regression
        'test "q#"',  # invalid segment
        "stats -t",
    ]
    script.write_bytes(("\n".join(commands) + "\n").encode("utf-8"))
    proc = subprocess.run(
        [sys.executable, str(HC_FAKE), "-i", str(config), "-s", str(script)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=60,
    )
    lines = proc.stdout.decode("utf-16-le").split("\r\n")[:-1]
    stream = m.read_test_stream(lines, ["membaca", "baca", "xyz", "q#"], exit_code=0)
    assert [r.status for r in stream.results] == [
        "passed",
        "failed",
        "failed",
        "invalid_segment",
    ]
    assert [a.morphs for a in stream.results[1].actual] == [(("baca", "?"),)]
    assert [a.morphs for a in stream.results[2].expected] == [(("x", "y"),)]
    assert stream.counters == m.TestCounters(tests=4, passed=1, failed=2, error=1)


# -- data-model 6.6 reconciliation ------------------------------------------


def _cls():
    return importlib.import_module("flextoolsmcp.server.sandbox.classify")


def test_test_counter_reconciliation_table():
    c = _cls()
    assert c.TEST_COUNTER_RECONCILIATION == (
        (
            "tests",
            ("pass", "regression", "new_ambiguity", "changed", "invalid_segment"),
        ),
        ("passed", ("pass",)),
        ("failed", ("regression", "new_ambiguity", "changed")),
        ("error", ("invalid_segment",)),
    )


def test_test_counters_agree_and_diverge():
    c, m = _cls(), hco()
    passed = m.TestResult("a", "passed", (), (), None)
    reg = _test_one(m, hc_test_lines("b", missing=[MEM]))
    amb = _test_one(m, hc_test_lines("c", extras=[ALT]))
    inv = m.TestResult("d", "invalid_segment", (), (), 2)
    nx = m.placeholder_test_result("e", "not_expressible")
    assertions = [c.classify_assertion([MEM], r) for r in (passed, reg, amb, inv, nx)]
    assert [a.classification for a in assertions] == [
        "pass",
        "regression",
        "new_ambiguity",
        "error",
        "error",
    ]
    agree = m.TestCounters(tests=4, passed=1, failed=2, error=1)
    # not_expressible is never sent, so hc's error counter excludes it.
    assert c.reconcile_test_counters(assertions, agree) == []
    wrong = m.TestCounters(tests=4, passed=2, failed=1, error=1)
    divergences = c.reconcile_test_counters(assertions, wrong)
    assert [(d.counter, d.hc, d.per_word) for d in divergences] == [
        ("passed", 2, 1),
        ("failed", 1, 2),
    ]
    assert all("stats -t" in d.text and d.text.isascii() for d in divergences)
    # Neither side corrected.
    assert wrong == m.TestCounters(tests=4, passed=2, failed=1, error=1)
    assert [a.classification for a in assertions][1] == "regression"
